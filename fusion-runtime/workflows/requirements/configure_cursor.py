"""Preview or install shared/global or legacy project-level Cursor MCP config.

Also migrates an exact legacy shared entry to this directory, rolls such a
migration back from its backup, and prepares the local config/local.json from
the legacy foundation without overwriting an existing file.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys

if __package__:
    from .cursor_mcp import ProjectTools, SharedProjectTools
    from .file_tools import project_state, requirements
    from .file_tools.check_foundation import read_json
else:
    from cursor_mcp import ProjectTools, SharedProjectTools
    from file_tools import project_state, requirements
    from file_tools.check_foundation import read_json

HERE = Path(__file__).resolve().parent
SHARED_NAME = "requirements"
BACKUPS_DIRECTORY = "config/migration-backups"
LOCK_NAME = ".requirements-mcp-config.lock"


def build_entry(*, foundation, python_executable, project_id=None, project_root=None):
    if (project_id is None) != (project_root is None):
        raise ValueError("固定项目模式必须同时指定项目编号与目录")
    tools = (ProjectTools(foundation=foundation, project_id=project_id, project_root=project_root)
             if project_id is not None else SharedProjectTools(foundation=foundation))
    interpreter = Path(python_executable).expanduser().resolve(strict=True)
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise ValueError("Python 解释器不可执行")
    entry = {"type": "stdio", "command": str(interpreter), "args": [
        "-B", str(Path(__file__).with_name("cursor_mcp.py").resolve()),
        "--foundation", str(tools.foundation),
    ]}
    if project_id is not None:
        entry["args"] += ["--project-id", tools.project_id, "--project-root", str(tools.project_root)]
    entry["args"] += ["--allow-initialize", "--allow-save"]
    return ("requirements-" + project_id if project_id is not None else "requirements"), entry


def legacy_entry(*, old_foundation, python_executable):
    """The exact shared entry the previous installer wrote; the old layout is not validated or loaded."""
    interpreter = Path(python_executable).expanduser().resolve(strict=True)
    return {"type": "stdio", "command": str(interpreter), "args": [
        "-B", str(Path(__file__).with_name("cursor_mcp.py").resolve()),
        "--foundation", str(Path(old_foundation).expanduser().resolve(strict=True)),
        "--allow-initialize", "--allow-save",
    ]}


def read_configuration(workspace):
    supplied = Path(workspace).expanduser()
    if not supplied.is_absolute() or supplied.is_symlink():
        raise ValueError("Cursor 工作区必须是绝对目录且不是软链")
    root = supplied.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Cursor 工作区不是目录")
    path = requirements.safe_path(root, ".cursor/mcp.json")
    document = requirements.read_document(root, ".cursor/mcp.json")
    data = json.loads(document["content"]) if document["content"] is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("已有 Cursor MCP 配置格式错误，未改写")
    return path, document["sha256"], data


def configure(*, workspace, expected_sha256=None, apply=False, **binding):
    name, entry = build_entry(**binding)
    path, before_sha, data = read_configuration(workspace)
    servers = dict(data.get("mcpServers", {}))
    if name in servers and servers[name] != entry:
        raise ValueError("同名 Cursor 工具配置已存在且不同，未覆盖")
    changed = name not in servers
    result = {"config_path": str(path), "server_name": name,
              "expected_config_sha256": before_sha, "server": entry,
              "changed": changed, "applied": False}
    if not apply:
        return result
    if expected_sha256 != before_sha:
        raise ValueError("Cursor 配置版本冲突，未覆盖；请重新预览")
    if not changed:
        return {**result, "applied": True}
    path.parent.mkdir(exist_ok=True)
    with project_state.exclusive_lock(path.parent / LOCK_NAME,
                                      "Cursor 工具配置锁已存在，未改写"):
        current_path, current_sha, current_data = read_configuration(workspace)
        if current_path != path or current_sha != before_sha:
            raise ValueError("Cursor 配置版本冲突，未覆盖；请重新预览")
        servers = dict(current_data.get("mcpServers", {}))
        servers[name] = entry
        raw = (json.dumps({**current_data, "mcpServers": servers}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if current_sha == "missing":
            with path.open("xb") as stream:
                stream.write(raw)
        else:
            project_state.atomic_replace(path, raw)
    return {**result, "applied": True, "config_sha256": hashlib.sha256(raw).hexdigest()}


def remove_scoped_entry(*, workspace, server_name, expected_entry, expected_sha256):
    """Remove only an exact known legacy entry; keep unrelated client settings."""
    path, before_sha, data = read_configuration(workspace)
    if before_sha != expected_sha256:
        raise ValueError("旧项目配置版本冲突，未改写")
    servers = dict(data.get("mcpServers", {}))
    if server_name not in servers:
        return {"config_path": str(path), "changed": False}
    if servers[server_name] != expected_entry:
        raise ValueError("旧项目入口已被修改，未移除")
    with project_state.exclusive_lock(path.parent / LOCK_NAME, "配置锁已存在"):
        current_path, current_sha, current_data = read_configuration(workspace)
        if current_path != path or current_sha != before_sha:
            raise ValueError("旧项目配置版本冲突，未改写")
        servers = dict(current_data["mcpServers"])
        del servers[server_name]
        raw = (json.dumps({**current_data, "mcpServers": servers}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        project_state.atomic_replace(path, raw)
    return {"config_path": str(path), "changed": True, "removed_server": server_name}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path):
    return _sha(path.read_bytes()) if path.is_file() else "missing"


def _code_digests():
    files = [HERE / "cursor_mcp.py", HERE / "configure_cursor.py", *sorted((HERE / "file_tools").glob("*.py"))]
    return {path.relative_to(HERE).as_posix(): _file_sha(path) for path in files}


def _swap_state(current, expected_before, expected_after):
    if current is None:
        return "entry_missing"
    if current == expected_after:
        return "already_applied"
    if current == expected_before:
        return "ready"
    return "entry_modified"


def _replace_entry(workspace, path, before_sha, name, expected_before, expected_after, write_backup=None):
    """Swap one exact entry under the config lock; anything else in the file is preserved."""
    with project_state.exclusive_lock(path.parent / LOCK_NAME, "Cursor 工具配置锁已存在，未改写"):
        current_path, current_sha, current_data = read_configuration(workspace)
        if current_path != path or current_sha != before_sha:
            raise ValueError("Cursor 配置版本冲突，未改写；请重新预览")
        servers = dict(current_data.get("mcpServers", {}))
        if servers.get(name) != expected_before:
            raise ValueError("目标条目已被改动，未改写")
        original = path.read_bytes()
        if _sha(original) != before_sha:
            raise ValueError("Cursor 配置版本冲突，未改写；请重新预览")
        servers[name] = expected_after
        raw = (json.dumps({**current_data, "mcpServers": servers}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        backup = write_backup(original, raw) if write_backup else None
        project_state.atomic_replace(path, raw)
    return raw, backup


def _write_backup(foundation, config_path, name, old, new, original, raw):
    """Write the pre-migration bytes and a manifest exclusively; any failure stops the migration."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = Path(foundation) / BACKUPS_DIRECTORY / stamp
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()
    manifest = {
        "schema_version": 1, "created_at": stamp, "config_path": str(config_path), "server_name": name,
        "before_sha256": _sha(original), "after_sha256": _sha(raw), "old_server": old, "new_server": new,
        "foundation": str(Path(foundation).resolve()),
        "local_config_sha256": _file_sha(Path(foundation) / "config/local.json"),
        "upstream_lock_sha256": _file_sha(Path(foundation) / "upstream-lock.json"),
        "code_sha256": _code_digests(),
        "note": "只恢复 Cursor 条目；代码与本地文件须按 code_sha256 等摘要另行成组核对恢复",
    }
    with (directory / "mcp.json.before").open("xb") as stream:
        stream.write(original)
    with (directory / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return str(directory)


def _apply_command(arguments, expected_sha):
    return shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), *arguments,
                       "--expected-config-sha", expected_sha, "--apply"])


def migrate(*, workspace, old_foundation, foundation, python_executable, expected_sha256=None, apply=False,
            command_arguments=()):
    """Replace the exact legacy shared entry with this directory's entry, after an exclusive backup."""
    name, entry = build_entry(foundation=foundation, python_executable=python_executable)
    old = legacy_entry(old_foundation=old_foundation, python_executable=python_executable)
    if old == entry:
        raise ValueError("旧入口与新入口相同，无需迁移")
    path, before_sha, data = read_configuration(workspace)
    servers = data.get("mcpServers", {})
    state = _swap_state(servers.get(name), old, entry)
    result = {"mode": "migrate", "config_path": str(path), "server_name": name, "state": state,
              "expected_config_sha256": before_sha, "old_server": old, "server": entry,
              "other_servers": sorted(key for key in servers if key != name),
              "changed": False, "applied": False}
    if state == "entry_missing":
        raise ValueError("配置中没有共用 requirements 条目，未迁移；新装请使用普通安装")
    if state == "entry_modified":
        raise ValueError("共用 requirements 条目与预期旧条目不一致（可能已被用户改动），未迁移")
    if state == "already_applied":
        return {**result, "applied": apply}
    if not apply:
        return {**result, "changed": True, "apply_command": _apply_command(command_arguments, before_sha)}
    if expected_sha256 != before_sha:
        raise ValueError("Cursor 配置版本冲突，未改写；请重新预览")
    raw, backup = _replace_entry(
        workspace, path, before_sha, name, old, entry,
        write_backup=lambda original, raw: _write_backup(foundation, path, name, old, entry, original, raw))
    return {**result, "changed": True, "applied": True, "config_sha256": _sha(raw), "backup": backup}


def rollback(*, workspace, backup, expected_sha256=None, apply=False, command_arguments=()):
    """Restore only the migrated entry recorded in a backup manifest; code is not restored here."""
    manifest = read_json(Path(backup) / "manifest.json")
    name, old, new = manifest.get("server_name"), manifest.get("old_server"), manifest.get("new_server")
    if manifest.get("schema_version") != 1 or name != SHARED_NAME or not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("迁移备份清单格式错误，未回退")
    path, before_sha, data = read_configuration(workspace)
    if str(path) != manifest.get("config_path"):
        raise ValueError("备份对应的配置文件与当前目标不同，未回退")
    state = _swap_state(data.get("mcpServers", {}).get(name), new, old)
    result = {"mode": "rollback", "config_path": str(path), "server_name": name, "state": state,
              "expected_config_sha256": before_sha, "server": old, "code_restored": False,
              "code_sha256": manifest.get("code_sha256"), "changed": False, "applied": False}
    if state == "entry_missing":
        raise ValueError("配置中没有共用 requirements 条目，未回退")
    if state == "entry_modified":
        raise ValueError("当前条目不是该备份记录的迁移结果，未回退")
    if state == "already_applied":
        return {**result, "applied": apply}
    if not apply:
        return {**result, "changed": True, "apply_command": _apply_command(command_arguments, before_sha)}
    if expected_sha256 != before_sha:
        raise ValueError("Cursor 配置版本冲突，未改写；请重新预览")
    raw, _ = _replace_entry(workspace, path, before_sha, name, new, old)
    return {**result, "changed": True, "applied": True, "config_sha256": _sha(raw)}


def prepare_local_config(*, foundation, source_foundation, apply=False):
    """Copy the legacy config/local.json byte for byte; never overwrite a different existing file."""
    source = Path(source_foundation).expanduser().resolve(strict=True) / "config/local.json"
    raw = source.read_bytes()
    config = read_json(source)
    if config.get("schema_version") != 1:
        raise ValueError("不支持的本机配置版本")
    target = Path(foundation).expanduser().resolve(strict=True) / "config/local.json"
    result = {"mode": "prepare-local-config", "target": str(target), "source_sha256": _sha(raw),
              "written": False}
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file():
            raise ValueError("本地配置不是普通文件，未改写")
        existing = target.read_bytes()
        if existing == raw:
            return {**result, "state": "identical"}
        current = read_json(target)
        differing = sorted(key for key in set(current) | set(config) if current.get(key) != config.get(key))
        raise ValueError("本地配置已存在且不同，未覆盖；差异字段：" + ("、".join(differing) or "格式"))
    if not apply:
        return {**result, "state": "absent"}
    target.parent.mkdir(exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    return {**result, "state": "written", "written": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--workspace", type=Path)
    location.add_argument("--global", action="store_true", dest="global_config",
                          help="安装到用户 ~/.cursor/mcp.json，在所有项目中可见")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--migrate-from-foundation", type=Path,
                      help="将准确匹配的旧共用条目迁移到本目录；先预览，备份后才替换")
    mode.add_argument("--rollback", type=Path, help="按迁移备份目录恢复该次迁移前的共用条目")
    mode.add_argument("--prepare-local-config-from", type=Path,
                      help="从旧融合目录逐字节复制 config/local.json；已存在且不同则拒绝")
    parser.add_argument("--foundation", type=Path, default=HERE,
                        help="包含 config/local.json、upstream-lock.json 与 methods/develop-helper 的目录；默认本目录")
    parser.add_argument("--project-id")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--expected-config-sha")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    preparing_local_config = args.prepare_local_config_from is not None
    if not preparing_local_config and args.workspace is None and not args.global_config:
        parser.error("必须指定 --workspace 或 --global")
    if args.global_config and (args.project_id is not None or args.project_root is not None):
        parser.error("全局入口不接受单项目绑定参数")
    if (args.migrate_from_foundation or args.rollback) and (args.project_id is not None or args.project_root is not None):
        parser.error("迁移与回退只处理共用入口")
    workspace = Path.home() if args.global_config else args.workspace
    location_arguments = ["--global"] if args.global_config else (
        ["--workspace", str(workspace)] if workspace is not None else [])
    try:
        if args.prepare_local_config_from is not None:
            result = prepare_local_config(foundation=args.foundation, source_foundation=args.prepare_local_config_from,
                                          apply=args.apply)
        elif args.migrate_from_foundation is not None:
            result = migrate(
                workspace=workspace, old_foundation=args.migrate_from_foundation, foundation=args.foundation,
                python_executable=args.python_executable, expected_sha256=args.expected_config_sha,
                apply=args.apply, command_arguments=[
                    *location_arguments, "--migrate-from-foundation", str(args.migrate_from_foundation),
                    "--foundation", str(args.foundation), "--python-executable", str(args.python_executable)])
        elif args.rollback is not None:
            result = rollback(workspace=workspace, backup=args.rollback, expected_sha256=args.expected_config_sha,
                              apply=args.apply, command_arguments=[*location_arguments, "--rollback", str(args.rollback)])
        else:
            result = configure(workspace=workspace, foundation=args.foundation, project_id=args.project_id,
                               project_root=args.project_root, python_executable=args.python_executable,
                               expected_sha256=args.expected_config_sha, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
