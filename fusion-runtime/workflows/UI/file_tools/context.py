"""Project binding, protected closure collection and read-only UI tools."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import unicodedata


CONTRACT_VERSION = "ui-tools-v1"

DESIGN_PATH = "docs/ui-style.md"
DEFAULT_ARTIFACT_ROOT = "docs/prototypes/demo"
MANIFEST_PATH = "ui/artifact-manifest.json"
STATE_DIR = "ui/.ui-state"
CURRENT_POINTER = "ui/.ui-state/current.json"
ACTIVE_TRANSACTION = "ui/.ui-state/transaction.json"
WORK_DIR = "ui/.ui-state/work"
VERSIONS_DIR = "ui/.ui-state/versions"
TRANSACTIONS_DIR = "ui/.ui-state/transactions"
REQUESTS_DIR = "ui/.ui-state/requests"

FIXED_INPUTS = (
    "project.json",
    "README.md",
    "docs/requirements.md",
    "docs/PRD.md",
    "docs/tech-spec.md",
    "docs/decisions.md",
)

FORBIDDEN_ROOT_NAMES = {"", ".", "..", "docs", "materials", ".git", ".sdd", "ui"}
CACHE_NAMES = {".DS_Store"}
IMPORT_FORBIDDEN_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".ui-state"}

MAX_MEMBERS = 256
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_COLLECTION_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 128 * 1024
MAX_SOURCE_PATHS = 64
MAX_DESCRIPTORS = 1024
MAX_PATH_BYTES = 1024
MAX_PATH_SEGMENTS = 16
MAX_WORKSPACES = 8
CREDENTIAL_TTL_SECONDS = 15 * 60
MAX_CREDENTIALS = 128
CONTENT_BUDGET = 768 * 1024
MAX_MESSAGE_BYTES = 1024 * 1024


class ToolError(RuntimeError):
    def __init__(self, code, message, *, details=None, next_action=None, write_outcome="not_written"):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.next_action = next_action or "核对参数、项目与当前文件后重试"
        self.write_outcome = write_outcome


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return digest(raw)


def canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_relative_path(value, *, label="路径"):
    if not isinstance(value, str):
        raise ToolError("invalid_arguments", f"{label} 必须是字符串")
    if len(value.encode("utf-8")) > MAX_PATH_BYTES or value != value.strip():
        raise ToolError("path_not_supported", f"{label} 超过长度限制或含首尾空白")
    if "\\" in value or value.startswith("/") or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ToolError("path_not_allowed", f"{label} 含反斜线、绝对前缀或控制字符")
    if unicodedata.normalize("NFC", value) != value:
        raise ToolError("path_not_allowed", f"{label} 必须是 NFC 规范文本")
    parts = value.split("/")
    if len(parts) > MAX_PATH_SEGMENTS or any(part in {"", ".", ".."} for part in parts):
        raise ToolError("path_not_allowed", f"{label} 含空段、. .. 或段数超限")
    lowered = [part.casefold() for part in parts]
    if len(set(lowered)) != len(lowered):
        raise ToolError("path_not_allowed", f"{label} 存在大小写折叠后冲突的路径段")
    return parts


def validate_artifact_root(value):
    parts = validate_relative_path(value, label="artifact_root")
    posix = "/".join(parts)
    if posix in FORBIDDEN_ROOT_NAMES or posix.startswith("ui/") or posix == DESIGN_PATH:
        raise ToolError("path_not_allowed", "artifact_root 不能是项目根、docs、materials、.git、.sdd 或 UI 状态区")
    if posix == os.path.dirname(DESIGN_PATH):
        raise ToolError("path_not_allowed", "artifact_root 不得与设计说明路径重叠")
    if posix.endswith(".env") or "/.env" in posix or any(part.startswith(".env") for part in parts):
        raise ToolError("path_not_allowed", "artifact_root 不得位于环境密钥区域")
    return posix


def validate_member_path(value, artifact_root):
    parts = validate_relative_path(value, label="成员路径")
    posix = "/".join(parts)
    if posix == DESIGN_PATH:
        return posix
    if posix == MANIFEST_PATH or posix.startswith(STATE_DIR + "/"):
        raise ToolError("path_not_allowed", "成员路径不能占用公共清单或 UI 私有状态区")
    if not posix.startswith(artifact_root + "/"):
        raise ToolError("path_not_allowed", f"成员必须位于 artifact_root 下或精确为 {DESIGN_PATH}")
    return posix


def resolve_project_path(root: Path, relative: str) -> Path:
    """Resolve a validated relative path, rejecting links at every segment."""
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise ToolError("path_not_allowed", f"不允许软链：{relative}")
    try:
        if not path.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            raise ToolError("path_not_allowed", f"路径越界：{relative}")
    except OSError as error:
        raise ToolError("path_not_supported", f"路径无法解析：{relative}",
                        details={"reason": str(error)}) from error
    return path


def bind_project(runtime, project_path):
    supplied = Path(project_path)
    if not isinstance(project_path, str) or not supplied.is_absolute() or ".." in supplied.parts:
        raise ToolError("path_not_allowed", "project_path 必须是不含 .. 的绝对路径")
    projects_root = runtime.projects_root
    try:
        canonical = supplied.resolve(strict=True)
    except OSError as error:
        raise ToolError("path_not_allowed", "项目目录不存在或不可访问",
                        details={"reason": str(error)}) from error
    if supplied.is_symlink() or canonical.parent != projects_root or canonical == projects_root:
        raise ToolError("path_not_allowed", "项目必须是 projects_root 的直接普通子目录")
    directory_name = canonical.name
    mapping = runtime.config.get("project_directories", {})
    reverse = {value: key for key, value in mapping.items()}
    expected_id = reverse.get(directory_name, directory_name)
    project_file = canonical / "project.json"
    if not project_file.exists() or project_file.is_symlink():
        raise ToolError("project_not_initialized", "缺少 project.json；不自动初始化项目")
    try:
        data = runtime.modules.project_init.load_project(canonical, expected_id)
    except (OSError, ValueError, RuntimeError) as error:
        raise ToolError("identity_conflict", "持久项目身份或初始化结构不匹配",
                        details={"reason": str(error)}) from error
    return {
        "root": canonical,
        "project_id": data["project_id"],
        "directory_name": directory_name,
        "data": data,
        "project": {"project_id": data["project_id"], "project_path": str(canonical),
                    "identity_source": "persisted", "identity_persisted": True},
    }


def _descriptor(key, scope, relative, file_path: Path, role, *, import_root=None,
                want_content=False, limit=MAX_SOURCE_BYTES):
    """Return (descriptor, content_bytes or None). Unreadable is distinct from missing."""
    descriptor = {"key": key, "scope": scope, "path": relative, "import_root": import_root,
                  "role": role, "kind": "file", "state": "missing",
                  "sha256": "missing", "size_bytes": 0}
    if not file_path.exists():
        return descriptor, None
    if file_path.is_symlink() or file_path.is_dir() or not file_path.is_file() \
            or file_path.stat().st_nlink != 1:
        descriptor.update(state="present", sha256=None)
        descriptor["unreadable"] = "not_regular_file"
        return descriptor, None
    raw = file_path.read_bytes()
    descriptor.update(state="present", sha256=digest(raw), size_bytes=len(raw))
    if len(raw) > limit:
        descriptor["unreadable"] = "too_large"
        return descriptor, None
    return descriptor, (raw if want_content else b"")


def _directory_descriptor(root: Path, relative: str):
    path = root / relative if relative else root
    entries = []
    unreadable = False
    if path.exists() and not path.is_symlink() and path.is_dir():
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            if child.name in CACHE_NAMES:
                continue
            if child.is_symlink():
                entries.append(f"L:{child.name}")
                unreadable = True
            elif child.is_dir():
                entries.append(f"D:{child.name}")
            elif child.is_file():
                entries.append(f"F:{child.name}")
            else:
                entries.append(f"O:{child.name}")
                unreadable = True
    descriptor = {"key": f"project:{relative or '.'}", "scope": "project", "path": relative or ".",
                  "import_root": None, "role": "current", "kind": "directory",
                  "state": "present" if path.exists() else "missing",
                  "sha256": digest(canonical_bytes(sorted(entries))),
                  "size_bytes": 0, "entries": sorted(entries)}
    if unreadable:
        descriptor["unreadable"] = "link_or_special_entry"
    return descriptor


def parse_manifest(raw: bytes):
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("collection_invalid", "公共清单必须是 UTF-8 JSON",
                        details={"reason": str(error)}) from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ToolError("collection_invalid", "公共清单 schema_version 必须为 1")
    entrypoint = manifest.get("entrypoint")
    files = manifest.get("files")
    if not isinstance(entrypoint, str) or not isinstance(files, list) or not files:
        raise ToolError("collection_invalid", "公共清单必须包含 entrypoint 和非空 files")
    seen = set()
    members = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ToolError("collection_invalid", "清单 files 每项只能包含 path 和 sha256")
        path, sha = item["path"], item["sha256"]
        if path in seen:
            raise ToolError("collection_invalid", f"清单包含重复路径：{path}")
        if not isinstance(sha, str) or not (len(sha) == 64 and all(ch in "0123456789abcdef" for ch in sha)):
            raise ToolError("collection_invalid", f"清单摘要非法：{path}")
        seen.add(path)
        members.append({"path": path, "sha256": sha})
    members.sort(key=lambda item: item["path"])
    if entrypoint not in seen:
        raise ToolError("collection_invalid", "entrypoint 必须列入 files")
    return {"schema_version": 1, "entrypoint": entrypoint, "files": members}


class Closure:
    def __init__(self, runtime, binding, artifact_root, source_paths, import_spec):
        self.runtime = runtime
        self.root = binding["root"]
        self.artifact_root = artifact_root
        self.source_paths = source_paths
        self.import_spec = import_spec
        self.descriptors = []
        self.contents = []
        self.diagnostics = []
        self.checks = []
        self.current = None
        self.history_summaries = None
        self.history_error = None

    def _add(self, descriptor, content=None, *, text=False, key_for_content=None):
        self.descriptors.append(descriptor)
        if len(self.descriptors) > MAX_DESCRIPTORS:
            raise ToolError("limit_exceeded", f"保护描述超过 {MAX_DESCRIPTORS} 个上限")
        if content is not None:
            self.contents.append({"key": key_for_content or descriptor["key"], "raw": content,
                                  "text": text})

    def _read_text_input(self, relative, role):
        path = resolve_project_path(self.root, relative)
        descriptor, raw = _descriptor(f"project:{relative}", "project", relative, path, role,
                                      want_content=True)
        if descriptor.get("unreadable") == "too_large":
            raise ToolError("input_too_large", f"输入文档超过 {MAX_SOURCE_BYTES // 1024} KiB：{relative}")
        if descriptor["state"] == "present" and descriptor.get("unreadable"):
            raise ToolError("input_unreadable", f"输入文档不可读：{relative}")
        text = False
        if raw is not None:
            try:
                raw.decode("utf-8")
                text = True
            except UnicodeDecodeError:
                raise ToolError("input_unreadable", f"输入文档不是有效 UTF-8：{relative}")
        self._add(descriptor, raw, text=text)

    def _registry_closure(self):
        data = self._project_data
        registry = data.get("artifact_registry")
        if registry is None:
            return
        if not isinstance(registry, dict) or registry.get("schema_version") != 1 \
                or not isinstance(registry.get("entries"), dict):
            self.diagnostics.append({"code": "registry_unreadable", "paths": [],
                                      "message": "project.json 的 artifact_registry 结构不受支持"})
            raise ToolError("registry_unreadable", "成果登记结构损坏；不跳过登记引用保护")
        referenced = set()

        def walk_manifest(manifest_value, manifest_path):
            if not isinstance(manifest_value, dict):
                raise ToolError("registry_unreadable", f"登记引用清单不是对象：{manifest_path}")
            inner = manifest_value.get("manifest", manifest_value)
            if not isinstance(inner, dict):
                raise ToolError("registry_unreadable", f"登记引用清单损坏：{manifest_path}")
            files = inner.get("files")
            if not isinstance(files, list):
                raise ToolError("registry_unreadable", f"登记引用清单缺少 files：{manifest_path}")
            for member in files:
                if not isinstance(member, dict) or not isinstance(member.get("path"), str):
                    raise ToolError("registry_unreadable", f"登记引用成员非法：{manifest_path}")
                referenced.add(member["path"])

        entries = registry["entries"]
        for artifact_id, entry in entries.items():
            if not isinstance(entry, dict) or entry.get("artifact_id") != artifact_id:
                raise ToolError("registry_unreadable", f"登记条目损坏：{artifact_id}")
            versions = entry.get("versions")
            if not isinstance(versions, list):
                raise ToolError("registry_unreadable", f"登记版本损坏：{artifact_id}")
            for version in versions:
                if not isinstance(version, dict):
                    raise ToolError("registry_unreadable", f"登记版本损坏：{artifact_id}")
                content = version.get("content")
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "file" and isinstance(content.get("path"), str):
                    referenced.add(content["path"])
                elif content.get("type") == "file-set":
                    manifest_ref = content.get("manifest", {})
                    nested_ref = manifest_ref.get("manifest") if isinstance(
                        manifest_ref.get("manifest"), dict) else manifest_ref
                    manifest_path = nested_ref.get("path")
                    if not isinstance(manifest_path, str):
                        if isinstance(nested_ref.get("files"), list):
                            walk_manifest({"manifest": nested_ref}, f"entry:{artifact_id}")
                            continue
                        raise ToolError("registry_unreadable",
                                        f"登记 file-set 缺少清单路径：{artifact_id}")
                    referenced.add(manifest_path)
                    candidate = resolve_project_path(self.root, manifest_path)
                    if not candidate.exists():
                        raise ToolError("registry_unreadable",
                                        f"登记引用的清单不存在：{manifest_path}")
                    try:
                        nested = parse_manifest(candidate.read_bytes())
                    except ToolError as error:
                        if error.code == "collection_invalid":
                            raise ToolError("registry_unreadable",
                                            f"登记引用清单损坏：{manifest_path}") from error
                        raise
                    walk_manifest({"manifest": nested}, manifest_path)
        for relative in sorted(referenced):
            validate_relative_path(relative, label="登记引用路径")
            descriptor, _ = _descriptor(f"project:{relative}", "project", relative,
                                        resolve_project_path(self.root, relative),
                                        "registry_reference")
            self._add(descriptor)

    def collect(self, project_data, current_info, history_summaries, history_error,
                include_contents=True):
        self._project_data = project_data
        self._include_contents = include_contents
        for relative in FIXED_INPUTS:
            self._read_text_input(relative, "input")
        for relative in self.source_paths:
            if relative in FIXED_INPUTS or relative == MANIFEST_PATH:
                raise ToolError("invalid_arguments", f"source_paths 不能重复固定输入：{relative}")
            self._read_text_input(relative, "input")

        self._registry_closure()

        if self.import_spec:
            self._collect_import()

        for relative, role in ((MANIFEST_PATH, "control"), (CURRENT_POINTER, "control"),
                               (ACTIVE_TRANSACTION, "control")):
            descriptor, _ = _descriptor(f"project:{relative}", "project", relative,
                                        resolve_project_path(self.root, relative), role)
            self._add(descriptor)

        if current_info["kind"] in {"managed", "legacy"}:
            for member in current_info["members"]:
                relative = member["path"]
                descriptor, raw = _descriptor(f"project:{relative}", "project", relative,
                                              resolve_project_path(self.root, relative),
                                              "current", want_content=True,
                                              limit=MAX_FILE_BYTES)
                text = False
                if raw is not None:
                    try:
                        raw.decode("utf-8")
                        text = True
                    except UnicodeDecodeError:
                        text = False
                if include_contents:
                    self._add(descriptor, raw, text=text)
                else:
                    self._add(descriptor)

        artifact_dir = resolve_project_path(self.root, self.artifact_root) \
            if self.artifact_root else self.root
        self._add(_directory_descriptor(self.root, self.artifact_root))
        if artifact_dir.exists():
            for current, directories, files in os.walk(artifact_dir, followlinks=False):
                current_path = Path(current)
                rel = current_path.relative_to(self.root).as_posix()
                if current_path != artifact_dir:
                    self._add(_directory_descriptor(self.root, rel))
                for name in sorted(files):
                    child = current_path / name
                    relative = child.relative_to(self.root).as_posix()
                    if name in CACHE_NAMES or child.is_symlink() or child.stat().st_nlink != 1:
                        descriptor, _ = _descriptor(f"project:{relative}", "project", relative,
                                                     child, "current")
                        if child.is_symlink() or child.stat().st_nlink != 1:
                            descriptor["unreadable"] = "link_or_hardlink"
                        self._add(descriptor)
                        continue
                    raw = child.read_bytes()
                    descriptor = {"key": f"project:{relative}", "scope": "project",
                                  "path": relative, "import_root": None, "role": "current",
                                  "kind": "file", "state": "present", "sha256": digest(raw),
                                  "size_bytes": len(raw)}
                    if include_contents:
                        self._add(descriptor, raw, text=False)
                    else:
                        self._add(descriptor)
                directories[:] = [name for name in directories
                                  if not (current_path / name).is_symlink()
                                  and name not in CACHE_NAMES]
        self.current = current_info
        self.history_summaries = history_summaries
        self.history_error = history_error

    def _collect_import(self):
        spec = self.import_spec
        root = spec["root_path"]
        for relative in spec["files"]:
            path = root / relative
            descriptor, raw = _descriptor(f"import:{spec['root']}:{relative}", "import", relative,
                                          path, "input", import_root=spec["root"], want_content=True,
                                          limit=MAX_FILE_BYTES)
            if descriptor["state"] == "missing":
                raise ToolError("input_unreadable", f"导入文件不存在：{relative}")
            if descriptor.get("unreadable"):
                raise ToolError("input_unreadable", f"导入文件不可读：{relative}")
            if self._include_contents:
                self._add(descriptor, raw, text=False)
            else:
                self._add(descriptor)

    def descriptor_index(self):
        return {item["key"]: item for item in self.finalized_descriptors()}

    def finalized_descriptors(self):
        merged = {}
        for descriptor in self.descriptors:
            key = descriptor["key"]
            if key in merged:
                existing = merged[key]
                roles = set(existing.get("role", "").split("|"))
                roles.add(descriptor.get("role", ""))
                existing["role"] = "|".join(sorted(role for role in roles if role))
                if descriptor.get("unreadable"):
                    existing["unreadable"] = descriptor["unreadable"]
                continue
            merged[key] = dict(descriptor)
        return [merged[key] for key in sorted(merged)]

    def descriptor_digest(self):
        canonical = [{key: value for key, value in item.items() if key != "unreadable"}
                     for item in self.finalized_descriptors()]
        return canonical_sha(canonical)


def validate_import_spec(runtime, import_source, import_roots):
    if import_source is None:
        return None
    if not isinstance(import_source, dict):
        raise ToolError("invalid_arguments", "import_source 必须是对象")
    allowed = {"root", "files", "entrypoint", "design_path", "readme_path"}
    if set(import_source) != allowed:
        raise ToolError("invalid_arguments",
                        "import_source 必须且只能包含 root、files、entrypoint、design_path、readme_path")
    root_text = import_source["root"]
    if not isinstance(root_text, str) or not Path(root_text).is_absolute():
        raise ToolError("path_not_allowed", "import root 必须是普通绝对目录")
    root = Path(root_text)
    if root.is_symlink() or not root.is_dir():
        raise ToolError("path_not_allowed", "import root 必须是已存在普通目录")
    authorized = False
    for candidate in import_roots:
        candidate_resolved = Path(candidate).resolve(strict=False)
        if root == candidate_resolved or root.resolve(strict=False).is_relative_to(candidate_resolved):
            authorized = True
            break
    if not authorized:
        raise ToolError("path_not_allowed", "import root 不在 --import-root 授权范围内")
    root = root.resolve(strict=True)
    for restricted in (runtime.foundation, runtime.ui_root, runtime.upstream_root,
                       runtime.projects_root):
        if root == restricted or root.is_relative_to(restricted) or restricted.is_relative_to(root):
            raise ToolError("path_not_allowed", "import root 不得与项目、UI、foundation 或上游重叠")
    files = import_source["files"]
    if not isinstance(files, list) or not files or len(files) > MAX_MEMBERS:
        raise ToolError("invalid_arguments", f"files 必须是非空且不超过 {MAX_MEMBERS} 项的数组")
    normalized = []
    for item in files:
        parts = validate_relative_path(item, label="导入文件")
        if any(part in IMPORT_FORBIDDEN_PARTS for part in parts) \
                or any(part.startswith(".env") or part.endswith((".pem", ".key")) for part in parts):
            raise ToolError("path_not_allowed", f"禁止导入密钥、缓存或状态文件：{item}")
        normalized.append("/".join(parts))
    if len(set(normalized)) != len(normalized):
        raise ToolError("invalid_arguments", "导入 files 含重复路径")
    entrypoint, design_path, readme_path = (import_source["entrypoint"],
                                            import_source["design_path"],
                                            import_source["readme_path"])
    for label, value in (("entrypoint", entrypoint), ("design_path", design_path),
                         ("readme_path", readme_path)):
        if not isinstance(value, str) or value not in normalized:
            raise ToolError("invalid_arguments", f"{label} 必须列入 files")
    mapping = {}
    for relative in normalized:
        if relative == design_path:
            target = DESIGN_PATH
        elif relative == readme_path:
            target = f"{DEFAULT_ARTIFACT_ROOT}/README.md"
        else:
            target = f"{DEFAULT_ARTIFACT_ROOT}/{relative}"
        validate_member_path(target, DEFAULT_ARTIFACT_ROOT)
        if target in mapping.values():
            raise ToolError("mapping_conflict", f"导入映射目标冲突：{target}")
        mapping[relative] = target
    return {"root": str(root), "root_path": root, "files": normalized,
            "entrypoint": entrypoint, "design_path": design_path,
            "readme_path": readme_path, "mapping": mapping}


def import_mapping_view(spec):
    if spec is None:
        return []
    return [{"source_path": key, "target_path": value}
            for key, value in sorted(spec["mapping"].items())]


class CredentialManager:
    def __init__(self, clock=None):
        self.clock = clock or time.time
        self._read_tokens = {}
        self._inspect_tokens = {}

    def issue_read(self, *, project_path, artifact_root, source_paths, import_spec,
                   baseline_digest, runtime_baseline_digest, import_mapping_digest):
        self._expire()
        if len(self._read_tokens) + len(self._inspect_tokens) >= MAX_CREDENTIALS:
            raise ToolError("limit_exceeded", f"进程内凭证达到 {MAX_CREDENTIALS} 个上限")
        token = "read-" + secrets.token_hex(16)
        self._read_tokens[token] = {
            "project_path": project_path,
            "artifact_root": artifact_root,
            "source_paths": list(source_paths),
            "import_spec": _json_safe_import_spec(import_spec),
            "baseline_digest": baseline_digest,
            "runtime_baseline_digest": runtime_baseline_digest,
            "import_mapping_digest": import_mapping_digest,
            "expires_at": self.clock() + CREDENTIAL_TTL_SECONDS,
            "consumed": False,
        }
        return token

    def consume_read(self, token, *, project_path):
        record = self._validate_read(token, project_path=project_path)
        record["consumed"] = True
        return record

    def validate_read(self, token, *, project_path):
        return self._validate_read(token, project_path=project_path)

    def issue_inspect(self, *, project_path, revision_id, artifact_root, removed,
                      base_digest, candidate_digest, runtime_baseline_digest):
        self._expire()
        if len(self._read_tokens) + len(self._inspect_tokens) >= MAX_CREDENTIALS:
            raise ToolError("limit_exceeded", f"进程内凭证达到 {MAX_CREDENTIALS} 个上限")
        token = "inspect-" + secrets.token_hex(16)
        self._inspect_tokens[token] = {
            "project_path": project_path,
            "revision_id": revision_id,
            "artifact_root": artifact_root,
            "removed": sorted(removed),
            "base_digest": base_digest,
            "candidate_digest": candidate_digest,
            "runtime_baseline_digest": runtime_baseline_digest,
            "expires_at": self.clock() + CREDENTIAL_TTL_SECONDS,
            "consumed": False,
        }
        return token

    def validate_inspect(self, token, *, project_path):
        if not isinstance(token, str) or token not in self._inspect_tokens:
            raise ToolError("inspection_invalid", "inspection_id 无效：不属于本进程或项目")
        record = self._inspect_tokens[token]
        if record["project_path"] != project_path:
            raise ToolError("inspection_invalid", "inspection_id 绑定了其他项目")
        if record["consumed"]:
            raise ToolError("inspection_invalid", "inspection_id 已被消费")
        if self.clock() >= record["expires_at"]:
            self._inspect_tokens.pop(token, None)
            raise ToolError("inspection_expired", "inspection_id 已超过 15 分钟有效期")
        return record

    def consume_inspect(self, token, *, project_path):
        record = self.validate_inspect(token, project_path=project_path)
        record["consumed"] = True
        return record

    def _validate_read(self, token, *, project_path):
        if not isinstance(token, str) or token not in self._read_tokens:
            raise ToolError("read_invalid", "read_id 无效：不属于本进程或项目")
        record = self._read_tokens[token]
        if record["project_path"] != project_path:
            raise ToolError("read_invalid", "read_id 绑定了其他项目")
        if record["consumed"]:
            raise ToolError("read_invalid", "read_id 已被消费")
        if self.clock() >= record["expires_at"]:
            self._read_tokens.pop(token, None)
            raise ToolError("read_expired", "read_id 已超过 15 分钟有效期")
        return record

    def _expire(self):
        now = self.clock()
        for store in (self._read_tokens, self._inspect_tokens):
            for token in [key for key, value in store.items() if now >= value["expires_at"]]:
                store.pop(token, None)


def _json_safe_import_spec(import_spec):
    if import_spec is None:
        return None
    return {
        "root": import_spec["root"],
        "files": list(import_spec["files"]),
        "entrypoint": import_spec["entrypoint"],
        "design_path": import_spec["design_path"],
        "readme_path": import_spec["readme_path"],
        "mapping": dict(import_spec["mapping"]),
    }


def _verify_member_layout(members, entrypoint, artifact_root):
    for member in members:
        validate_member_path(member["path"], artifact_root)
    entry_path = validate_member_path(entrypoint, artifact_root)
    if not entry_path.endswith(".html") or entry_path == DESIGN_PATH:
        raise ToolError("unsupported_layout", "entrypoint 必须是 artifact_root 下的 .html 文件")


def _unmanaged_targets(root, artifact_root):
    found = []
    design = root / DESIGN_PATH
    if design.exists() and not design.is_symlink() and design.is_file():
        found.append(DESIGN_PATH)
    target = root / artifact_root
    if target.exists():
        for current, directories, files in os.walk(target, followlinks=False):
            current_path = Path(current)
            for name in files:
                child = current_path / name
                if name in CACHE_NAMES:
                    continue
                found.append(child.relative_to(root).as_posix())
            directories[:] = [name for name in directories
                             if not (current_path / name).is_symlink()]
    return sorted(found)


def detect_current(runtime, root, requested_root, project_id):
    from .versions import load_version_meta

    manifest_path = root / MANIFEST_PATH
    pointer_path = root / CURRENT_POINTER
    manifest_exists = manifest_path.exists()
    pointer_exists = pointer_path.exists()
    if manifest_exists and (manifest_path.is_symlink() or not manifest_path.is_file()):
        raise ToolError("collection_invalid", "公共清单不是独立普通文件")
    if pointer_exists and (pointer_path.is_symlink() or not pointer_path.is_file()):
        raise ToolError("collection_invalid", "当前指针不是独立普通文件")

    if not manifest_exists and not pointer_exists:
        unmanaged = _unmanaged_targets(root, requested_root)
        return {"kind": "none", "revision_sha256": None, "artifact_root": requested_root,
                "manifest": None, "members": [], "unmanaged": unmanaged}

    if pointer_exists and not manifest_exists:
        raise ToolError("collection_invalid", "存在当前指针但缺少公共清单；不自动修复")

    raw_manifest = manifest_path.read_bytes()
    if len(raw_manifest) > MAX_MANIFEST_BYTES:
        raise ToolError("collection_invalid", "公共清单超过 128 KiB")
    try:
        manifest = parse_manifest(raw_manifest)
    except ToolError:
        raise
    members = manifest["files"]
    if len(members) > MAX_MEMBERS:
        raise ToolError("limit_exceeded", "当前集合成员超过 256 个")

    if not pointer_exists:
        artifact_root = requested_root
        try:
            _verify_member_layout(members, manifest["entrypoint"], artifact_root)
        except ToolError as error:
            if error.code in {"path_not_allowed", "unsupported_layout"}:
                raise ToolError("unsupported_layout", "旧集合成员布局不受支持；不迁移或覆盖")
            raise
        for member in members:
            path = resolve_project_path(root, member["path"])
            if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != member["sha256"]:
                raise ToolError("collection_invalid",
                                f"legacy 集合成员缺失或摘要不符：{member['path']}")
        return {"kind": "legacy", "revision_sha256": None, "artifact_root": artifact_root,
                "manifest": manifest, "members": members, "unmanaged": []}

    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("collection_invalid", "当前指针不是有效 JSON") from error
    if not isinstance(pointer, dict) or pointer.get("schema_version") != 1:
        raise ToolError("collection_invalid", "当前指针 schema_version 必须为 1")
    if pointer.get("project_id") != project_id:
        raise ToolError("collection_invalid", "当前指针的项目身份不匹配")
    artifact_root = pointer.get("artifact_root")
    if artifact_root != requested_root:
        raise ToolError("collection_invalid",
                        "请求的 artifact_root 与当前指针不一致；不允许借保存搬迁")
    if pointer.get("manifest_sha256") != digest(raw_manifest):
        raise ToolError("collection_invalid", "公共清单摘要与当前指针不一致")
    revision = pointer.get("revision_sha256")
    if not isinstance(revision, str) or len(revision) != 64:
        raise ToolError("collection_invalid", "当前指针缺少合法 revision_sha256")
    _verify_member_layout(members, manifest["entrypoint"], artifact_root)
    total = 0
    for member in members:
        path = resolve_project_path(root, member["path"])
        if not path.is_file() or path.is_symlink():
            raise ToolError("collection_invalid", f"当前集合成员缺失：{member['path']}")
        raw = path.read_bytes()
        total += len(raw)
        if len(raw) > MAX_FILE_BYTES or total > MAX_COLLECTION_BYTES:
            raise ToolError("limit_exceeded", "当前集合超过文件或总量上限")
        if digest(raw) != member["sha256"]:
            raise ToolError("collection_invalid",
                            f"公共成员被外部修改且与清单不符：{member['path']}")
    try:
        load_version_meta(root, revision, full=True)
    except ToolError as error:
        if error.code in {"history_not_found", "history_invalid"}:
            raise ToolError("collection_invalid", f"当前版本不可核验：{error}")
        raise
    return {"kind": "managed", "revision_sha256": revision, "artifact_root": artifact_root,
            "manifest": manifest, "members": members, "unmanaged": []}


def _history_summaries(root):
    from .versions import list_versions, version_summary
    try:
        entries, _ = list_versions(root, limit=100)
        return [version_summary(entry) for entry in entries], None
    except ToolError as error:
        return None, {"code": error.code, "message": str(error)}


def _build_contents(closure):
    contents = []
    budget = CONTENT_BUDGET
    for entry in closure.contents:
        raw = entry["raw"]
        if raw is None:
            continue
        if entry["text"]:
            if len(raw) <= budget:
                budget -= len(raw)
                contents.append({"key": entry["key"], "content": raw.decode("utf-8"),
                                 "content_omitted": False})
            else:
                contents.append({"key": entry["key"], "content": None,
                                 "content_omitted": True})
        else:
            contents.append({"key": entry["key"], "content": None,
                             "content_omitted": False})
    return contents


def _check(code, scope, passed, message, *, paths=None, checked=True):
    return {"code": code, "scope": scope, "checked": checked, "passed": passed,
            "paths": paths or [], "message": message}


class UiTools:
    def __init__(self, runtime, *, allow_write=False, import_roots=(), clock=None,
                 between_closure_passes=None, credentials=None):
        self.runtime = runtime
        self.allow_write = allow_write
        self.import_roots = tuple(Path(item) for item in import_roots)
        self.clock = clock or time.time
        self.between_closure_passes = between_closure_passes
        self.credentials = credentials or CredentialManager(clock=self.clock)
        # In-process interrupt injection for failure/recovery tests. Never
        # exposed as an MCP parameter; None in production launches.
        self.failpoint = None

    def _verify(self):
        from shared_loader import verify_runtime_baseline
        verify_runtime_baseline(self.runtime)

    def _bind(self, project_path):
        return bind_project(self.runtime, project_path)

    def _validate_source_paths(self, source_paths):
        if source_paths is None:
            return []
        if not isinstance(source_paths, list) or len(source_paths) > MAX_SOURCE_PATHS:
            raise ToolError("invalid_arguments",
                            f"source_paths 必须是不超过 {MAX_SOURCE_PATHS} 项的数组")
        result = []
        for item in source_paths:
            parts = validate_relative_path(item, label="source_paths")
            if any(part.startswith(".env") or part.endswith((".pem", ".key")) for part in parts) \
                    or "/".join(parts).startswith(STATE_DIR + "/"):
                raise ToolError("path_not_allowed", "source_paths 不能指向凭据或 UI 私有状态")
            result.append("/".join(parts))
        if len(set(result)) != len(result):
            raise ToolError("invalid_arguments", "source_paths 含重复路径")
        return result

    def read_context(self, project_path, artifact_root=None, source_paths=None, import_source=None):
        self._verify()
        if not isinstance(project_path, str) or not project_path.strip():
            raise ToolError("invalid_arguments", "project_path 必须是非空字符串")
        artifact_root = validate_artifact_root(artifact_root or DEFAULT_ARTIFACT_ROOT)
        source_paths = self._validate_source_paths(source_paths)
        import_spec = validate_import_spec(self.runtime, import_source, self.import_roots)
        binding = self._bind(project_path)

        current = detect_current(self.runtime, binding["root"], artifact_root,
                                 binding["project_id"])
        if current["kind"] == "none" and current["unmanaged"]:
            raise ToolError("unmanaged_target_exists",
                            "无清单但目标位置已存在文件；不自动纳管或覆盖",
                            details={"paths": current["unmanaged"]},
                            next_action="先人工确认既有文件的归属")
        history_summaries, history_error = _history_summaries(binding["root"])

        closure = Closure(self.runtime, binding, artifact_root, source_paths, import_spec)
        closure.collect(binding["data"], current, history_summaries, history_error)
        if self.between_closure_passes:
            self.between_closure_passes(binding["root"])
        closure_two = Closure(self.runtime, binding, artifact_root, source_paths, import_spec)
        closure_two.collect(binding["data"], current, history_summaries, history_error,
                            include_contents=False)
        stable = closure.descriptor_digest() == closure_two.descriptor_digest()

        diagnostics = list(closure.diagnostics)
        if history_error:
            diagnostics.append({"code": history_error["code"], "paths": [],
                                 "message": history_error["message"]})
        checks = [
            _check("runtime_baseline", "service", True, "运行基线核对通过"),
            _check("project_identity", "project", True, "持久项目身份核对通过"),
            _check("closure_stability", "project", stable,
                   "完整闭包读取前后一致" if stable else "读取期间闭包发生变化"),
            _check("current_collection", "project", current["kind"] != "none",
                   f"当前集合类型：{current['kind']}"),
            _check("history", "project", history_error is None,
                   "历史版本可列" if history_error is None else history_error["message"]),
            _check("import_mapping", "import", import_spec is None,
                   "无导入" if import_spec is None else "导入映射有效"),
        ]

        from .transactions import active_transaction_id
        active = active_transaction_id(binding["root"])
        if not stable:
            state = "unstable"
            diagnostics.append({"code": "closure_changed", "paths": [],
                                 "message": "读取期间输入或目标发生变化；不发 read_id"})
        elif active is not None:
            state = "incomplete"
            diagnostics.append({"code": "transaction_pending", "paths": [],
                                 "message": "存在活动 UI 事务；不发新的有效写凭证"})
        elif current["kind"] == "none":
            state = "empty"
        else:
            state = "stable"

        read_id = None
        if state in {"empty", "stable"}:
            import_digest = canonical_sha(import_mapping_view(import_spec)) if import_spec else None
            read_id = self.credentials.issue_read(
                project_path=str(binding["root"]),
                artifact_root=artifact_root,
                source_paths=source_paths,
                import_spec=import_spec,
                baseline_digest=closure.descriptor_digest(),
                runtime_baseline_digest=canonical_sha(self.runtime.baseline),
                import_mapping_digest=import_digest,
            )

        payload = {
            "contract_version": CONTRACT_VERSION,
            "operation": "ui_read_context",
            "project": binding["project"],
            "state": state,
            "dependency_descriptors": closure.finalized_descriptors(),
            "baseline_digest": closure.descriptor_digest(),
            "runtime_baseline_digest": canonical_sha(self.runtime.baseline),
            "current": {
                "kind": current["kind"],
                "revision_sha256": current["revision_sha256"],
                "artifact_root": current["artifact_root"],
                "manifest": current["manifest"],
            },
            "history": history_summaries or [],
            "import_mapping": import_mapping_view(import_spec),
            "contents": _build_contents(closure),
            "read_id": read_id,
            "diagnostics": diagnostics,
            "checks": checks,
        }
        if len(canonical_bytes(payload)) > MAX_MESSAGE_BYTES:
            raise ToolError("response_too_large", "完整保护描述超过消息上限")
        return payload

    def prepare_revision(self, project_path, read_id, request_id, mode,
                         history_revision=None):
        self._verify()
        if not self.allow_write:
            raise ToolError("tool_not_enabled", "写工具未开放：本服务以只读模式启动",
                            next_action="需要写入时由宿主以 --allow-write 重启服务")
        from .workspace import prepare_revision
        return prepare_revision(
            self.runtime, self.credentials, self.import_roots, binding_factory=self._bind,
            project_path=project_path, read_id=read_id, request_id=request_id,
            mode=mode, history_revision=history_revision, clock=self.clock)

    def accept_revision(self, project_path, revision_id, inspection_id, request_id,
                        delete_paths):
        self._verify()
        if not self.allow_write:
            raise ToolError("tool_not_enabled", "写工具未开放：本服务以只读模式启动",
                            next_action="需要写入时由宿主以 --allow-write 重启服务")
        from .transactions import accept_revision
        return accept_revision(
            self.runtime, self.credentials, self.import_roots,
            binding_factory=self._bind, project_path=project_path,
            revision_id=revision_id, inspection_id=inspection_id,
            request_id=request_id, delete_paths=delete_paths,
            failpoint=self.failpoint)

    def recover_revision(self, project_path, transaction_id, request_id, action):
        self._verify()
        if not self.allow_write:
            raise ToolError("tool_not_enabled", "写工具未开放：本服务以只读模式启动",
                            next_action="需要写入时由宿主以 --allow-write 重启服务")
        from .transactions import recover_revision
        return recover_revision(
            self.runtime, binding_factory=self._bind, project_path=project_path,
            transaction_id=transaction_id, request_id=request_id, action=action,
            failpoint=self.failpoint)

    def inspect(self, project_path, target, *, revision_id=None, transaction_id=None,
                artifact_root=None):
        self._verify()
        binding = self._bind(project_path)
        if target == "candidate":
            if not isinstance(revision_id, str):
                raise ToolError("invalid_arguments", "target=candidate 必须提供 revision_id")
            from .workspace import inspect_candidate
            return inspect_candidate(self.runtime, self.credentials, binding,
                                     revision_id=revision_id, clock=self.clock)
        if revision_id is not None:
            raise ToolError("invalid_arguments", "只有 target=candidate 允许 revision_id")
        if target == "current":
            artifact_root = validate_artifact_root(artifact_root or DEFAULT_ARTIFACT_ROOT)
            current = detect_current(self.runtime, binding["root"], artifact_root,
                                     binding["project_id"])
            from .transactions import active_transaction_id
            active = active_transaction_id(binding["root"])
            state = "incomplete" if active is not None else (
                "empty" if current["kind"] == "none" else "stable")
            return {
                "contract_version": CONTRACT_VERSION,
                "operation": "ui_inspect",
                "project": binding["project"],
                "state": state,
                "issues": [],
                "verification_scope": "current",
                "inspection_id": None,
                "candidate_digest": None,
                "base_digest": None,
                "proposed_revision_sha256": None,
                "changes": None,
                "transaction": None,
                "current": {"kind": current["kind"],
                            "revision_sha256": current["revision_sha256"],
                            "artifact_root": current["artifact_root"]},
                "diagnostics": [],
                "checks": [_check("current_collection", "project", True,
                                  f"当前集合类型：{current['kind']}")],
            }
        if target == "transaction":
            from .transactions import inspect_transaction
            result = inspect_transaction(binding["root"], binding, transaction_id=transaction_id)
            result.update({
                "contract_version": CONTRACT_VERSION,
                "operation": "ui_inspect",
                "project": binding["project"],
                "issues": [],
                "verification_scope": "transaction",
                "inspection_id": None,
                "candidate_digest": None,
                "base_digest": None,
                "proposed_revision_sha256": None,
                "changes": None,
                "diagnostics": [],
                "checks": [_check("transaction_readonly", "project", True,
                                  "事务只读检查完成，未执行恢复")],
            })
            return result
        raise ToolError("invalid_arguments", "target 必须是 current、candidate 或 transaction")

    def read_history(self, project_path, *, revision_sha256=None, after_revision=None,
                     limit=20):
        self._verify()
        from .versions import list_versions, version_summary, version_detail
        binding = self._bind(project_path)
        if revision_sha256 is not None:
            if after_revision is not None or limit != 20:
                raise ToolError("invalid_arguments",
                                "指定 revision_sha256 时禁止 after_revision 和 limit")
            detail = version_detail(binding["root"], revision_sha256)
            return {
                "contract_version": CONTRACT_VERSION,
                "operation": "ui_read_history",
                "project": binding["project"],
                "state": "history",
                "versions": [{"revision_sha256": detail["revision_sha256"],
                              "created_at": detail["created_at"], "origin": detail["origin"]}],
                "next_after_revision": None,
                "version": detail,
                "contents": detail["contents"],
                "diagnostics": [],
                "checks": [_check("history_version", "project", True, "版本 packet 与成员核验通过")],
            }
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ToolError("invalid_arguments", "limit 必须是 1—100 的整数")
        if after_revision is not None and (not isinstance(after_revision, str)
                                           or len(after_revision) != 64):
            raise ToolError("invalid_arguments", "after_revision 必须是 64 位小写十六进制")
        entries, next_after = list_versions(binding["root"], limit=limit,
                                            after_revision=after_revision)
        return {
            "contract_version": CONTRACT_VERSION,
            "operation": "ui_read_history",
            "project": binding["project"],
            "state": "history_list",
            "versions": [version_summary(entry) for entry in entries],
            "next_after_revision": next_after,
            "version": None,
            "contents": [],
            "diagnostics": [],
            "checks": [_check("history_list", "project", True, "历史列表核验通过")],
        }
