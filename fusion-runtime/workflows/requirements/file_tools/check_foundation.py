"""Read-only foundation validation. Never executes or writes upstream content."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


EXCLUDED = {".git", ".DS_Store", "__pycache__", "Projects_Repo", "node_modules", ".venv", "venv"}
POLICY = "source-tree-v1-no-projects-dependencies-git-cache-no-follow"
METHODS_LINK = "methods/develop-helper"
LEGACY_LINK = "upstream/develop-helper"


def snapshot(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("上游不是目录")
    files = {}

    def visit(directory):
        for path in sorted(directory.iterdir()):
            if path.name in EXCLUDED or path.name.endswith(".pyc"):
                continue
            key = path.relative_to(root).as_posix()
            if path.is_symlink():
                files[key] = {"kind": "symlink", "target": os.readlink(path)}
            elif path.is_dir():
                files[key] = {"kind": "directory"}
                visit(path)
            elif path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                files[key] = {"kind": "file", "sha256": digest.hexdigest()}
            else:
                raise ValueError(f"不支持的上游文件类型：{key}")

    visit(root)
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return {"schema_version": 1, "policy": POLICY, "entry_count": len(files),
            "sha256": hashlib.sha256(encoded).hexdigest()}


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"配置必须是 JSON 对象：{path.name}")
    return value


def configured_directory(config, field):
    value = config.get(field)
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"{field} 必须是绝对路径")
    path = Path(value).resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"{field} 不是目录")
    return path


def overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def check(foundation):
    foundation = Path(foundation).resolve(strict=True)
    config = read_json(foundation / "config/local.json")
    if config.get("schema_version") != 1:
        raise ValueError("不支持的本机配置版本")
    upstream = configured_directory(config, "upstream_root")
    projects = configured_directory(config, "projects_root")
    if any(overlaps(a, b) for a, b in (
        (foundation, upstream), (foundation, projects), (upstream, projects)
    )):
        raise ValueError("融合层、上游与业务项目父目录不得互相包含")
    link = foundation / METHODS_LINK
    if not link.is_symlink():
        if not os.path.lexists(link) and os.path.lexists(foundation / LEGACY_LINK):
            raise ValueError("foundation 是旧融合目录布局（upstream/develop-helper），不再作为需求运行入口；"
                             "请使用 requirements 本地目录并迁移启动配置")
        raise ValueError("上游入口不是软链")
    if link.resolve(strict=True) != upstream:
        raise ValueError("软链目标与配置不一致")
    locked = read_json(foundation / "upstream-lock.json")
    if locked.get("schema_version") != 1 or locked.get("policy") != POLICY:
        raise ValueError("不支持的上游锁定格式或校验范围")
    expected = locked.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64 or not locked.get("entry_count"):
        raise ValueError("上游基线为空或格式错误")
    actual = snapshot(upstream)
    if expected != actual["sha256"] or locked["entry_count"] != actual["entry_count"]:
        raise ValueError("上游版本漂移；停止相关调用，不自动更新基线")
    return {"status": "pass", "checked_entries": actual["entry_count"],
            "runtime_readonly_enforced": False,
            "buzz_connected": False,
            "note": "仅路径与内容基线通过；运行时权限和业务闭环未验证"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot_command = commands.add_parser("snapshot")
    snapshot_command.add_argument("root", type=Path)
    check_command = commands.add_parser("check")
    check_command.add_argument("--foundation", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = snapshot(args.root) if args.command == "snapshot" else check(args.foundation)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
