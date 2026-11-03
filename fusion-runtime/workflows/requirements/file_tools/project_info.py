"""Project selection fields in the root project.json.

Validates, reports and updates only project_type, target_platforms,
specification and repository_plan. Identity, execution facts (github,
initialization), artifacts and confirmations are never written here. No
network, Git mutation, dependency installation or scaffolding.
"""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

if __package__:
    from . import project_init
    from .check_foundation import configured_directory, read_json
    from .project_state import atomic_replace, project_state_lock
else:
    import project_init
    from check_foundation import configured_directory, read_json
    from project_state import atomic_replace, project_state_lock

FIELDS = ("project_type", "target_platforms", "specification", "repository_plan")
PROJECT_TYPES = ("web", "mobile", "api", "cli")
REPOSITORY_MODES = ("deferred", "none", "use_existing", "create_later")
PLATFORM = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
MAX_PLATFORMS = 8
MAX_SPECIFICATION = 64
MAX_URL = 2048
SPECIFICATION_DIRECTORY = ("harness-core", "specification")
HOST = r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?"
USER = r"[A-Za-z0-9._-]{1,64}"
NETLOC_HTTPS = re.compile(rf"{HOST}(?::[0-9]{{1,5}})?")
NETLOC_SSH = re.compile(rf"(?:{USER}@)?{HOST}(?::[0-9]{{1,5}})?")
SCP_LIKE = re.compile(rf"({USER})@({HOST}):([^\s@:]+)")
PATH = re.compile(r"/[^\s@:?#]+")


class InfoError(ValueError):
    """Rejected before any project file is written."""

    def __init__(self, reason, message, **data):
        super().__init__(message)
        self.reason, self.data = reason, data


class UnverifiedWrite(RuntimeError):
    """project.json was replaced but the read-back did not match."""

    def __init__(self, message, **data):
        super().__init__(message)
        self.data = data


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _invalid(field, message):
    return InfoError("invalid_value", f"{field} {message}", field=field)


def _safe_text(value):
    return not any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value)


def valid_url(value):
    """Credential-free https, ssh or scp-like address; percent-encoding cannot hide userinfo."""
    if type(value) is not str or not value or len(value) > MAX_URL or not _safe_text(value):
        return False
    decoded = unquote(value)
    if not _safe_text(decoded) or decoded.count("@") != value.count("@"):
        return False
    scp = SCP_LIKE.fullmatch(value)
    if scp is not None:
        return "://" not in value and ".." not in scp.group(3).split("/")
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    if parts.query or parts.fragment or "?" in value or "#" in value:
        return False
    if parts.scheme == "https":
        netloc = NETLOC_HTTPS
    elif parts.scheme == "ssh":
        netloc = NETLOC_SSH
    else:
        return False
    return (netloc.fullmatch(parts.netloc) is not None and PATH.fullmatch(parts.path) is not None
            and ".." not in parts.path.split("/"))


def safe_url(value):
    """Echo a recorded address only when it passes the credential-free rule."""
    return value if valid_url(value) else "[已隐藏：不符合地址规则]"


def validate_field(field, value):
    if field == "project_type":
        if type(value) is not str or value not in PROJECT_TYPES:
            raise _invalid(field, "必须是 web、mobile、api 或 cli")
        return value
    if field == "target_platforms":
        if (type(value) is not list or not 1 <= len(value) <= MAX_PLATFORMS
                or any(type(item) is not str or PLATFORM.fullmatch(item) is None for item in value)
                or len(set(value)) != len(value)):
            raise _invalid(field, "必须是 1—8 个不重复的小写平台名")
        return list(value)
    if field == "specification":
        if value is None:
            return None
        if (type(value) is not str or not value or value != value.strip() or len(value) > MAX_SPECIFICATION
                or value in {".", "..", "null"} or "/" in value or "\\" in value or not _safe_text(value)):
            raise _invalid(field, "必须是单层规范集名称或 JSON null")
        return value
    if field == "repository_plan":
        if type(value) is not dict or type(value.get("mode")) is not str or value["mode"] not in REPOSITORY_MODES:
            raise _invalid(field, "必须是含 deferred、none、use_existing 或 create_later 的 mode 对象")
        if value["mode"] == "use_existing":
            if set(value) != {"mode", "url"}:
                raise _invalid(field, "use_existing 只能且必须包含 mode 和 url")
            if not valid_url(value["url"]):
                raise InfoError("invalid_value", "repository_plan.url 只接受无凭据的 https、ssh 或 git@host:path 地址",
                                field="repository_plan.url")
            return {"mode": "use_existing", "url": value["url"]}
        if set(value) != {"mode"}:
            raise _invalid(field, "除 use_existing 外只能包含 mode")
        return {"mode": value["mode"]}
    raise InfoError("field_not_allowed", "不支持的项目信息字段", fields=[str(field)])


def validate_changes(changes, *, allow_empty=False):
    if type(changes) is not dict:
        raise InfoError("invalid_arguments", "项目信息必须是对象")
    if not changes and not allow_empty:
        raise InfoError("invalid_arguments", "changes 至少包含一个字段")
    forbidden = sorted(str(key) for key in changes if key not in FIELDS)
    if forbidden:
        raise InfoError("field_not_allowed", "只能补录 " + "、".join(FIELDS), fields=forbidden)
    return {field: validate_field(field, changes[field]) for field in FIELDS if field in changes}


def report(data):
    fields, unrecorded, invalid = {}, [], []
    for field in FIELDS:
        if field not in data:
            fields[field] = {"status": "unrecorded"}
            unrecorded.append(field)
            continue
        try:
            fields[field] = {"status": "recorded", "value": validate_field(field, data[field])}
        except InfoError:
            fields[field] = {"status": "invalid"}
            invalid.append(field)
    return {"fields": fields, "unrecorded": unrecorded, "invalid": invalid}


def specification_root(foundation):
    config = read_json(Path(foundation) / "config/local.json")
    return configured_directory(config, "upstream_root").joinpath(*SPECIFICATION_DIRECTORY)


def resolve_specification(foundation, name):
    """Locate a named set without reading its rules; null is never resolved."""
    if name is None:
        return {"status": "not_used"}
    validate_field("specification", name)
    base = specification_root(foundation)
    target = base / name
    if base.is_symlink() or not base.is_dir():
        raise InfoError("specification_not_found", "共享规范库不可用", specification=name)
    if target.is_symlink() or not target.is_dir() or target.resolve().parent != base.resolve():
        raise InfoError("specification_not_found", "规范集不存在或不在共享规范库内", specification=name)
    return {"status": "selected", "name": name, "path": "/".join((*SPECIFICATION_DIRECTORY, name))}


def impacts(info):
    """Directional notes for type/specification combinations; never rejects or rewrites."""
    project_type, specification = info.get("project_type"), info.get("specification")
    if specification != "default" or project_type not in {"api", "cli", "mobile"}:
        return []
    details = {
        "api": "default 含 React 前端规则；api 项目只取后端与共享规则，不生成界面",
        "cli": "default 面向 Web 前端与 FastAPI 服务；cli 不隐式继承 Web 服务层，缺少匹配规则时可选自建集或 null",
        "mobile": "default 前端规则面向 React Web；mobile 需核对适用范围，必要时选自建集",
    }
    return [{"code": "specification_type_mismatch", "project_type": project_type,
             "specification": specification, "detail": details[project_type]}]


def remote_facts(root, data):
    """Facts verifiable inside this project: recorded github/remote_link and local Git remote URLs."""
    github = data.get("github") if isinstance(data.get("github"), dict) else {}
    url = github.get("url") if isinstance(github.get("url"), str) and github.get("url") else None
    steps = data.get("initialization") if isinstance(data.get("initialization"), dict) else {}
    link = steps.get("remote_link") if isinstance(steps.get("remote_link"), dict) else {}
    remotes = []
    git_dir = Path(root) / ".git"
    if git_dir.is_dir() and not git_dir.is_symlink() and project_init.repository_root(root) == Path(root):
        result = project_init.git(root, "config", "--get-regexp", r"^remote\..*\.url$")
        if result.returncode not in (0, 1):
            raise ValueError("无法读取本地 Git 远端配置；先人工核对")
        remotes = sorted({line.split(" ", 1)[1] for line in result.stdout.splitlines() if " " in line})
    return {"github_url": url, "remote_link_succeeded": link.get("status") == "succeeded", "git_remotes": remotes}


def check_repository_plan(root, data, plan):
    facts = remote_facts(root, data)
    if not (facts["github_url"] or facts["remote_link_succeeded"] or facts["git_remotes"]):
        return facts
    known = [value for value in (facts["github_url"], *facts["git_remotes"]) if value]
    conflict = plan["mode"] != "use_existing" or any(value != plan["url"] for value in known)
    if conflict:
        raise InfoError("repository_fact_conflict", "仓库安排与项目已有远端事实冲突；未覆盖任何一方",
                        requested={"mode": plan["mode"], **({"url": safe_url(plan["url"])} if "url" in plan else {})},
                        facts={"github_url": safe_url(facts["github_url"]) if facts["github_url"] else None,
                               "remote_link_succeeded": facts["remote_link_succeeded"],
                               "git_remotes": [safe_url(value) for value in facts["git_remotes"]]})
    return facts


def creation_info(foundation, info):
    """Validate optional selections for a new project; nothing is written here."""
    info = validate_changes(info or {}, allow_empty=True)
    if isinstance(info.get("specification"), str):
        resolve_specification(foundation, info["specification"])
    return info


def precheck(foundation, root, data, changes):
    if isinstance(changes.get("specification"), str):
        resolve_specification(foundation, changes["specification"])
    if "repository_plan" in changes:
        check_repository_plan(root, data, changes["repository_plan"])


def _read_metadata(root):
    path = Path(root) / "project.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("project.json 不是独立普通文件")
    return path.read_bytes()


def update(foundation, project_id, changes, expected_sha256, *, expected_root=None, directory_name=None):
    """Replace only requested selection fields under the project-state lock."""
    changes = validate_changes(changes)
    foundation, root = project_init.context(foundation, project_id, expected_root=expected_root,
                                            directory_name=directory_name)
    project_init.load_project(root, project_id)
    with project_state_lock(root, "project-info-update"):
        _, current_root = project_init.context(foundation, project_id, expected_root=expected_root,
                                               directory_name=directory_name)
        if current_root != root:
            raise InfoError("identity_conflict", "项目目录在补录前发生变化")
        raw = _read_metadata(root)
        before_sha = digest(raw)
        if before_sha != expected_sha256:
            raise InfoError("version_conflict", "project.json 已变化；请重新读取后再补录",
                            expected_sha256=expected_sha256, current_sha256=before_sha)
        data = project_init.load_project(root, project_id)
        if json.loads(raw.decode("utf-8")) != data:
            raise InfoError("version_conflict", "project.json 在锁内读取期间发生变化")
        precheck(foundation, root, data, changes)
        merged = dict(data)
        merged.update(changes)
        updated = [field for field in FIELDS if field in changes and (field not in data or data[field] != changes[field])]
        if not updated:
            return {"changed": False, "updated_fields": [], "before_sha256": before_sha,
                    "sha256": before_sha, "project_info": report(data)}
        new_raw = project_init.json_text(merged).encode("utf-8")
        atomic_replace(root / "project.json", new_raw)
        after = _read_metadata(root)
    if digest(after) != digest(new_raw) or json.loads(after.decode("utf-8")) != merged:
        raise UnverifiedWrite("project.json 写后复读不一致", before_sha256=before_sha, sha256=digest(after))
    return {"changed": True, "updated_fields": updated, "before_sha256": before_sha,
            "sha256": digest(after), "project_info": report(merged)}
