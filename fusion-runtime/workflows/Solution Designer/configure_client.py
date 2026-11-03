"""Preview, apply and roll back the Cursor JSON entry for Solution Designer."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from shared_loader import CLIENT_ENTRY_NAME, SERVER_NAME, SERVER_VERSION


LOCK_NAME = ".solution-designer-config.lock"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_config_path(config_path: os.PathLike[str] | str) -> Path:
    path = Path(config_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("配置路径必须是绝对普通文件路径")
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError("配置路径祖先不能是软链")
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError("配置路径必须是独立普通文件")
    return path


def build_entry(*, foundation, solution_root=None, python_executable, allow_save=False):
    foundation = Path(foundation).resolve(strict=True)
    solution_root = Path(solution_root or Path(__file__).resolve().parent).resolve(strict=True)
    interpreter = Path(python_executable).expanduser().resolve(strict=True)
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise ValueError("Python 解释器不可执行")
    server = solution_root / "mcp_server.py"
    if not server.is_file() or server.is_symlink():
        raise ValueError("mcp_server.py 不是普通文件")
    args = ["-B", str(server), "--foundation", str(foundation)]
    if allow_save:
        args.append("--allow-save")
    return {"type": "stdio", "command": str(interpreter), "args": args}


def read_config(path: Path):
    if not path.exists():
        return {}, "missing", b""
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("客户端配置必须是 UTF-8 JSON") from error
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("客户端配置必须包含 mcpServers 对象")
    return data, sha(raw), raw


def preview(*, config_path, foundation, python_executable, allow_save=False, solution_root=None):
    path = safe_config_path(config_path)
    entry = build_entry(foundation=foundation, python_executable=python_executable,
                        allow_save=allow_save, solution_root=solution_root)
    data, before_sha, _ = read_config(path)
    servers = data.get("mcpServers", {})
    existing = servers.get(CLIENT_ENTRY_NAME)
    if existing is None:
        change_kind = "missing"
    elif existing == entry:
        change_kind = "unchanged"
    else:
        change_kind = "entry_conflict"
    return {
        "config_path": str(path),
        "expected_config_sha256": before_sha,
        "server_name": CLIENT_ENTRY_NAME,
        "before_entry": existing,
        "after_entry": entry,
        "change_kind": change_kind,
        "other_server_names": sorted(name for name in servers if name != CLIENT_ENTRY_NAME),
        "would_create_backup": change_kind == "missing",
        "applied": False,
    }


def _exclusive_lock(path: Path):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)


def _write_backup(path: Path, data: dict, before_raw: bytes, entry: dict, after_raw: bytes):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = path.parent / ".solution-designer-backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    (backup_dir / "mcp.json.before").write_bytes(before_raw)
    manifest = {
        "schema_version": 1,
        "created_at": stamp,
        "config_path": str(path),
        "server_name": CLIENT_ENTRY_NAME,
        "before_sha256": sha(before_raw),
        "after_entry": entry,
        "after_sha256": sha(after_raw),
        "before_entry": data.get("mcpServers", {}).get(CLIENT_ENTRY_NAME),
        "config_existed": before_raw != b"",
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    return backup_dir, manifest


def apply_configuration(*, config_path, foundation, python_executable, allow_save=False,
                        expected_config_sha256, solution_root=None):
    result = preview(config_path=config_path, foundation=foundation,
                     python_executable=python_executable, allow_save=allow_save,
                     solution_root=solution_root)
    if result["change_kind"] == "entry_conflict":
        raise ValueError("同名配置已存在且内容不同；首版不强制覆盖")
    if expected_config_sha256 != result["expected_config_sha256"]:
        raise ValueError("配置版本与预览不一致；请重新预览")
    path = Path(result["config_path"])
    if result["change_kind"] == "unchanged":
        return {**result, "applied": True, "changed": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / LOCK_NAME
    try:
        _exclusive_lock(lock)
        try:
            data, current_sha, before_raw = read_config(path)
            if current_sha != result["expected_config_sha256"]:
                raise ValueError("配置在预览后发生变化；未覆盖")
            servers = dict(data.get("mcpServers", {}))
            servers[CLIENT_ENTRY_NAME] = result["after_entry"]
            merged = {**data, "mcpServers": servers}
            raw = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            backup_dir, manifest = _write_backup(path, data, before_raw, result["after_entry"], raw)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                                 prefix=".solution-mcp-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if current_sha == "missing":
                    with path.open("xb") as output:
                        output.write(raw)
                else:
                    os.replace(temporary, path)
                    temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            observed, observed_sha, _ = read_config(path)
            if observed_sha != sha(raw) or observed["mcpServers"][CLIENT_ENTRY_NAME] != result["after_entry"]:
                raise RuntimeError("配置写后复读失败")
            return {**result, "applied": True, "changed": True, "config_sha256": observed_sha,
                    "backup": {"directory": str(backup_dir), "manifest": manifest}}
        finally:
            lock.unlink(missing_ok=True)
    except FileExistsError as error:
        raise ValueError("配置锁已存在；未覆盖") from error


def preview_rollback(*, config_path, backup):
    path = safe_config_path(config_path)
    backup_dir = Path(backup).resolve(strict=True)
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("server_name") != CLIENT_ENTRY_NAME:
        raise ValueError("回退备份清单不属于 solution-designer")
    data, current_sha, _ = read_config(path)
    current_entry = data.get("mcpServers", {}).get(CLIENT_ENTRY_NAME)
    if current_entry != manifest.get("after_entry"):
        state = "entry_modified"
    elif current_entry is None:
        state = "entry_missing"
    else:
        state = "rollback_available"
    return {"config_path": str(path), "expected_config_sha256": current_sha, "state": state,
            "backup_manifest": manifest, "applied": False}


def apply_rollback(*, config_path, backup, expected_config_sha256):
    result = preview_rollback(config_path=config_path, backup=backup)
    if expected_config_sha256 != result["expected_config_sha256"]:
        raise ValueError("配置版本与回退预览不一致")
    if result["state"] != "rollback_available":
        raise ValueError("当前条目不是备份记录的精确条目；不回退")
    path = Path(config_path)
    manifest = result["backup_manifest"]
    data, _, _ = read_config(path)
    servers = dict(data["mcpServers"])
    if manifest.get("before_entry") is None:
        servers.pop(CLIENT_ENTRY_NAME, None)
    else:
        servers[CLIENT_ENTRY_NAME] = manifest["before_entry"]
    raw = (json.dumps({**data, "mcpServers": servers}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return {**result, "applied": True, "config_sha256": sha(raw)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=["cursor"])
    parser.add_argument("--config-path", required=True, type=Path)
    parser.add_argument("--foundation", required=True, type=Path)
    parser.add_argument("--python-executable", required=True)
    parser.add_argument("--allow-save", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-config-sha")
    parser.add_argument("--rollback")
    arguments = parser.parse_args(argv)
    if arguments.rollback:
        action = apply_rollback if arguments.apply else preview_rollback
        value = action(config_path=arguments.config_path, backup=arguments.rollback,
                       expected_config_sha256=arguments.expected_config_sha)
    else:
        action = apply_configuration if arguments.apply else preview
        kwargs = {"config_path": arguments.config_path, "foundation": arguments.foundation,
                  "python_executable": arguments.python_executable,
                  "allow_save": arguments.allow_save}
        if arguments.apply:
            kwargs["expected_config_sha256"] = arguments.expected_config_sha
        value = action(**kwargs)
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
