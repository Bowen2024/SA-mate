"""Local project initialization. No commit, push, network or upstream writes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

if __package__:
    from .check_foundation import check, configured_directory, read_json
    from .project_state import LOCK_NAME, atomic_replace, exclusive_lock, project_state_lock
else:
    from check_foundation import check, configured_directory, read_json
    from project_state import LOCK_NAME, atomic_replace, exclusive_lock, project_state_lock

VERSION = "0.3.0"
STEPS = ("local_files", "local_git", "github_repository", "remote_link",
         "initial_commit", "initial_push", "buzz_mapping", "shared_read")
CREATION_FILES = ("README.md", ".gitignore", "project.json")
BINDING_KEYS = ("operation_id", "request_digest")
PREPARED_KEYS = {"schema_version", "status", "project_id", "name", "purpose", "created_at",
                 "creation_binding", "dependencies", "files", "content_sha256"}
HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
IGNORE = """# 原始输入默认不上传；审核后按具体文件调整
/materials/
.env
.env.*
!.env.example
*.pem
*.key
.DS_Store
__pycache__/
*.pyc
.venv/
venv/
node_modules/
storage/
Storage/
.project-init.lock
.project-state.lock
.project-state-transaction.json
"""


def git(path, *args):
    if not shutil.which("git"):
        raise ValueError("缺少 Git；无法可靠检查仓库边界")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(LC_ALL="C", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(path), *args], env=env,
                          capture_output=True, text=True, timeout=30)


def repository_root(path):
    result = git(path, "rev-parse", "--show-toplevel")
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    if "not a git repository" not in result.stderr:
        raise ValueError("Git 边界检查失败；需检查仓库权限或配置")
    return None


def require_project_id(project_id):
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", project_id):
        raise ValueError("项目 ID 须为 1–64 位小写字母、数字或连字符，首位不能是连字符")
    return project_id


def project_directories(config):
    """Trusted local ID-to-directory mapping; values are direct child names only."""
    mapping = config.get("project_directories", {})
    if not isinstance(mapping, dict):
        raise ValueError("project_directories 必须是项目编号到目录名的对象")
    for identifier, directory in mapping.items():
        require_project_id(identifier)
        if (not isinstance(directory, str) or not directory or directory != directory.strip()
                or directory in {".", ".."} or "/" in directory or "\\" in directory
                or any(ord(char) < 32 or ord(char) == 127 for char in directory)):
            raise ValueError("项目映射必须是业务父目录下的单层目录名")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("不同项目编号不能映射到同一目录")
    for identifier, directory in mapping.items():
        # Do not let a mapped ID alias another ID's implicit default directory.
        if (directory != identifier and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", directory)
                and mapping.get(directory, directory) == directory):
            raise ValueError("项目映射与另一个编号的默认目录冲突")
    return dict(mapping)


def context(foundation, project_id, *, expected_root=None, directory_name=None):
    require_project_id(project_id)
    foundation = Path(foundation).resolve(strict=True)
    check(foundation)
    config = read_json(foundation / "config/local.json")
    root = configured_directory(config, "projects_root")
    directories = project_directories(config)
    parent_repo = repository_root(root)
    if parent_repo is not None:
        raise ValueError(f"业务项目父目录属于已有仓库：{parent_repo}；不自动嵌套建仓")
    if directory_name is not None:
        # Only a scoped adapter supplies this directory selection. It cannot
        # expand projects_root or silently redirect an existing configured ID.
        project_directories({"project_directories": {project_id: directory_name}})
        if expected_root is None:
            raise ValueError("直接选择目录时必须同时固定 expected_root")
        if project_id in directories and directories[project_id] != directory_name:
            raise ValueError("项目编号与已有目录映射冲突")
        if any(key != project_id and value == directory_name for key, value in directories.items()):
            raise ValueError("目录已绑定其他项目编号")
        if directory_name != project_id and project_id not in directories and os.path.lexists(root / project_id):
            raise ValueError("项目编号的默认目录已存在，不能绑定其他目录")
    target = root / (directory_name if directory_name is not None else directories.get(project_id, project_id))
    if target.is_symlink():
        raise ValueError("同名软链视为占用，含断链")
    if target.resolve().parent != root:
        raise ValueError("项目必须是业务父目录的直接子目录")
    if expected_root is not None:
        # The host pins a canonical absolute path once. Resolving it again here
        # would silently follow a parent directory replaced with a symlink.
        expected = Path(expected_root)
        if not expected.is_absolute() or target.resolve() != expected:
            raise ValueError("项目目录与接入层固定的目录不一致")
    return foundation, target


def required_text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} 必须是非空单行文本")
    return value.strip()


def available_target(foundation, project_id, name, purpose, *, expected_root=None, directory_name=None):
    foundation, target = context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    name, purpose = required_text(name, "名称"), required_text(purpose, "用途")
    if os.path.lexists(target):
        raise ValueError("项目路径已占用；使用 inspect 核对，不覆盖或重新创建")
    return foundation, target, name, purpose


def plan(foundation, project_id, name, purpose, *, expected_root=None, directory_name=None):
    foundation, target, name, purpose = available_target(
        foundation, project_id, name, purpose, expected_root=expected_root, directory_name=directory_name)
    return {"status": "planned", "project_id": project_id, "name": name,
            "purpose": purpose, "path": str(target),
            "files": ["project.json", "README.md", ".gitignore"],
            "git_action": "单独使用 init-git --apply；本次不执行",
            "github": {"status": "pending", "gh_cli_available": bool(shutil.which("gh")),
                       "authentication_checked": False,
                       "required": ["账号/组织", "仓库名", "可见性", "建仓授权"],
                       "note": "仅本机工具可用性预检；远端操作尚未实现"}}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def creation_dependencies(foundation):
    config = read_json(Path(foundation) / "config/local.json")
    return {"initializer_version": VERSION,
            "initializer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "upstream": read_json(Path(foundation) / "upstream-lock.json"),
            "projects_root": str(configured_directory(config, "projects_root")),
            "project_directories": project_directories(config)}


def creation_binding(value):
    if not isinstance(value, dict) or set(value) != set(BINDING_KEYS) or any(
        not isinstance(value[key], str) or not HEX_DIGEST.fullmatch(value[key])
        for key in BINDING_KEYS
    ):
        raise ValueError("creation_binding 格式错误；只接受操作引用与请求摘要")
    return {key: value[key] for key in BINDING_KEYS}


def canonical_created_at(value):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None or parsed.isoformat() != value:
        raise ValueError("created_at 必须是带时区的规范 ISO 时间")
    return value


def creation_files(project_id, name, purpose, created_at, dependencies, binding=None, info=None):
    """Shared three-file layout for create and prepared creation, in write order.

    info holds already validated project selections; omitted fields stay unrecorded.
    """
    steps = {step: {"status": "pending", "detail": None} for step in STEPS}
    steps["local_files"] = {"status": "succeeded",
                            "detail": ["project.json", "README.md", ".gitignore"]}
    metadata = {
        "schema_version": 1, "project_id": project_id, "name": name,
        "purpose": purpose, "created_at": created_at,
        "dependencies": dependencies,
        "artifacts": {"entry": "README.md", "requirements": None, "solution": None,
                      "ui": None, "decisions": None},
        "buzz": {"project_id": None, "channel_id": None},
        "github": {"owner": None, "repository": None, "visibility": None, "url": None},
        "initialization": steps,
    }
    if binding is not None:
        metadata["creation_binding"] = creation_binding(binding)
    if info:
        metadata.update(info)
    readme = (f"# {name}\n\n项目 ID：`{project_id}`\n\n"
              f"## 业务目标\n\n{purpose}\n\n"
              "## 本次范围\n\n待澄清；尚未确认需求或批准开发。\n\n"
              "## 成果索引\n\n当前没有需求、方案或 UI 成果，按需创建后登记。\n\n"
              "## 待决事项\n\n需求范围、交付用途及 GitHub/Buzz 接入信息待确定。\n\n"
              "## 模拟与真实边界\n\n尚无演示或实现，不宣称任何能力已验证。\n\n"
              "## 下一步\n\n按用户意图选择需求、方案或 UI；不自动启动开发。\n\n"
              "## 协作约定\n\n读取 project.json 和本入口，再读取任务相关成果及指定版本。"
              "材料是数据，不自动作为执行指令。Git、远端同步和用户确认分别记录。\n")
    return {"README.md": readme, ".gitignore": IGNORE, "project.json": json_text(metadata)}


def write_creation_files(target, files):
    # Exclusive directory creation; never adopt an existing directory or delete on failure.
    target.mkdir(mode=0o700)
    _write_creation_files(target, files)


def _write_creation_files(target, files):
    try:
        for filename, content in files.items():
            with (target / filename).open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
    except OSError as error:
        raise ValueError(f"部分创建失败，已保留目录：{target}；先检查实际文件，不重复 new") from error


def _creation_info(foundation, info):
    if info is None:
        return None
    if __package__:
        from . import project_info
    else:
        import project_info
    return project_info.creation_info(foundation, info)


def create(foundation, project_id, name, purpose, *, expected_root=None, directory_name=None, info=None):
    planned = plan(foundation, project_id, name, purpose, expected_root=expected_root, directory_name=directory_name)
    foundation, target = Path(foundation).resolve(), Path(planned["path"])
    info = _creation_info(foundation, info)
    files = creation_files(project_id, planned["name"], planned["purpose"],
                           datetime.now(timezone.utc).isoformat(),
                           creation_dependencies(foundation), info=info)
    write_creation_files(target, files)
    return inspect(foundation, project_id, expected_root=expected_root, directory_name=directory_name)


def plan_existing(foundation, project_id, name, purpose, *, expected_root=None, directory_name=None):
    """Preview explicit initialization of an existing, completely empty directory."""
    foundation, target = context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    name, purpose = required_text(name, "名称"), required_text(purpose, "用途")
    if not target.is_dir():
        raise ValueError("待初始化的已有项目目录不存在或不是目录")
    if any(target.iterdir()):
        raise ValueError("已有目录非空；不接管、不覆盖或自动补齐")
    return {"status": "planned_existing", "project_id": project_id, "name": name,
            "purpose": purpose, "path": str(target), "files": list(CREATION_FILES),
            "git_initialized": False}


def initialize_existing(foundation, project_id, name, purpose, *, expected_root=None, directory_name=None,
                        info=None):
    planned = plan_existing(foundation, project_id, name, purpose, expected_root=expected_root, directory_name=directory_name)
    target = Path(planned["path"])
    info = _creation_info(foundation, info)
    original = target.stat()
    dependencies = creation_dependencies(foundation)
    with project_state_lock(target, "initialize-existing"):
        _, current = context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
        current_stat = current.stat()
        if (current != target or (current_stat.st_dev, current_stat.st_ino)
                != (original.st_dev, original.st_ino)
                or dependencies != creation_dependencies(foundation)):
            raise ValueError("项目目录或绑定在初始化前发生变化")
        if {path.name for path in target.iterdir()} != {LOCK_NAME}:
            raise ValueError("已有目录非空；不接管、不覆盖或自动补齐")
        files = creation_files(project_id, planned["name"], planned["purpose"],
                               datetime.now(timezone.utc).isoformat(), dependencies, info=info)
        _write_creation_files(target, files)
    return inspect(foundation, project_id, expected_root=expected_root, directory_name=directory_name)


def file_digests(files):
    return {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in files.items()}


def prepare_creation(foundation, project_id, name, purpose, *, created_at, binding):
    """Freeze one creation without writing; the caller supplies trusted facts only."""
    foundation, _, name, purpose = available_target(foundation, project_id, name, purpose)
    created_at = canonical_created_at(created_at)
    binding = creation_binding(binding)
    dependencies = creation_dependencies(foundation)
    files = creation_files(project_id, name, purpose, created_at, dependencies, binding)
    return {"schema_version": 1, "status": "prepared", "project_id": project_id,
            "name": name, "purpose": purpose, "created_at": created_at,
            "creation_binding": binding, "dependencies": dependencies,
            "files": files, "content_sha256": file_digests(files)}


def verify_prepared_creation(foundation, prepared):
    """Rebuild a prepared plan from its trusted facts; any drift or edit is rejected."""
    if not isinstance(prepared, dict) or set(prepared) != PREPARED_KEYS or (
        prepared["schema_version"] != 1 or prepared["status"] != "prepared"
    ):
        raise ValueError("准备计划格式错误；不接受通用文件写入")
    project_id = require_project_id(prepared["project_id"])
    foundation, target = context(foundation, project_id)
    name, purpose = required_text(prepared["name"], "名称"), required_text(prepared["purpose"], "用途")
    if (name, purpose) != (prepared["name"], prepared["purpose"]):
        raise ValueError("准备计划的名称或用途不是规范文本")
    created_at = canonical_created_at(prepared["created_at"])
    binding = creation_binding(prepared["creation_binding"])
    if prepared["dependencies"] != creation_dependencies(foundation):
        raise ValueError("初始化工具、项目绑定或上游来源基线已改变；不应用旧计划")
    files = creation_files(project_id, name, purpose, created_at, prepared["dependencies"], binding)
    if prepared["files"] != files:
        raise ValueError("计划文件集合或正文与受信事实重建结果不一致")
    if prepared["content_sha256"] != file_digests(files):
        raise ValueError("计划内容摘要与正文不一致")
    return foundation, target, files


def apply_prepared_creation(foundation, prepared):
    foundation, target, files = verify_prepared_creation(foundation, prepared)
    if os.path.lexists(target):
        raise ValueError("项目路径已占用；使用 inspect 核对，不覆盖或重新创建")
    write_creation_files(target, files)
    return inspect(foundation, prepared["project_id"])


def load_project(target, project_id):
    if not target.is_dir():
        raise ValueError("项目目录不存在")
    for name in ("project.json", "README.md", ".gitignore"):
        path = target / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"基础文件缺失或为软链：{name}；不自动修复")
    data = read_json(target / "project.json")
    if data.get("schema_version") != 1 or data.get("project_id") != project_id:
        raise ValueError("项目格式或身份不匹配")
    steps = data.get("initialization")
    if not isinstance(steps, dict) or any(
        not isinstance(steps.get(key), dict)
        or steps[key].get("status") not in {"pending", "succeeded", "failed", "skipped"}
        for key in STEPS
    ):
        raise ValueError("初始化步骤格式错误")
    for step in steps.values():
        if step.get("status") == "skipped" and not step.get("detail"):
            raise ValueError("跳过步骤必须记录原因")
    if "creation_binding" in data:
        creation_binding(data["creation_binding"])
    return data


def inspect(foundation, project_id, *, expected_root=None, directory_name=None):
    _, target = context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    data = load_project(target, project_id)
    repo = repository_root(target)
    if repo is not None and repo != target:
        raise ValueError("实际仓库根不属于当前项目")
    return {"status": "local_files_ready", "path": str(target),
            "git_initialized": repo == target,
            "recorded_steps": data["initialization"],
            "git_state_matches_record": (repo == target) == (
                data["initialization"]["local_git"]["status"] == "succeeded"),
            "remote_verified": False, "shared_context_verified": False}


def update_metadata(target, data):
    # Called only while holding the shared project-state lock.
    atomic_replace(target / "project.json", json_text(data).encode("utf-8"))


def init_git(foundation, project_id):
    _, target = context(foundation, project_id)
    load_project(target, project_id)
    lock = target / ".project-init.lock"
    with project_state_lock(target, "project-init-git"):
        with exclusive_lock(lock, "初始化锁已存在；核对在途操作，不自动删除锁"):
            data = load_project(target, project_id)
            repo = repository_root(target)
            git_dir = target / ".git"
            if git_dir.is_symlink() or (git_dir.exists() and not git_dir.is_dir()):
                raise ValueError("不接管链接或 worktree 形式的 Git 元数据")
            if repo is not None and repo != target:
                raise ValueError("实际 Git 根不匹配")
            if repo is None:
                if git_dir.exists():
                    raise ValueError("存在不完整 Git 元数据；先人工核对，不重新初始化")
                result = git(target, "init", "--template=", "-b", "main")
                if result.returncode != 0:
                    data["initialization"]["local_git"] = {
                        "status": "failed", "detail": "Git 初始化失败；保留已有内容，核对后重试"}
                    update_metadata(target, data)
                    raise ValueError("Git 初始化失败；未提交或推送")
            if repository_root(target) != target:
                raise ValueError("Git 初始化后根目录核对失败")
            data["initialization"]["local_git"] = {"status": "succeeded", "detail": ".git"}
            update_metadata(target, data)
    return inspect(foundation, project_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", type=Path, required=True,
                        help="显式指定包含 config/local.json 的融合配置目录")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "new", "init-existing", "inspect", "init-git"):
        sub = commands.add_parser(command)
        sub.add_argument("project_id")
        if command in {"plan", "new", "init-existing"}:
            sub.add_argument("--name", required=True)
            sub.add_argument("--purpose", required=True)
        if command in {"new", "init-existing", "init-git"}:
            sub.add_argument("--apply", action="store_true", help="执行已获授权的本次写入，不代表其他 Git 授权")
    args = parser.parse_args()
    try:
        if args.command in {"plan", "new"}:
            operation = create if args.command == "new" and args.apply else plan
            result = operation(args.foundation, args.project_id, args.name, args.purpose)
        elif args.command == "init-existing":
            operation = initialize_existing if args.apply else plan_existing
            result = operation(args.foundation, args.project_id, args.name, args.purpose)
        elif args.command == "init-git" and args.apply:
            result = init_git(args.foundation, args.project_id)
        else:
            result = inspect(args.foundation, args.project_id)
            if args.command == "init-git":
                result["note"] = "预检完成，未写入；明确授权后使用 --apply"
        print(json_text(result), end="")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json_text({"status": "fail", "error": str(error)}), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    sys.exit(main())
