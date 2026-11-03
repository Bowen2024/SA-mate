"""Project binding and conservative protected dependency collection."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from shared_loader import FoundationError


CORE_DOCUMENTS = (
    "project.json",
    "README.md",
    "docs/requirements.md",
    "docs/PRD.md",
    "docs/tech-spec.md",
    "docs/decisions.md",
)
TARGET_PATH = "docs/tech-spec.md"
TRANSACTION_PATH = ".project-state-transaction.json"
MAX_FILES = 512
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return digest(raw)


def safe_project_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.as_posix().startswith("/"):
        raise ValueError("项目路径必须是相对 POSIX 路径")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("项目路径越界")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"不允许软链：{relative}")
    if path.exists() and not path.is_dir():
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f"项目文件必须是独立普通文件：{relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"项目路径越界：{relative}")
    return path


def describe_file(root: Path, relative: str, *, limit: int = 128 * 1024) -> dict:
    try:
        path = safe_project_path(root, relative)
        if not path.exists():
            return {"path": relative, "status": "missing", "sha256": "missing", "size_bytes": 0}
        if not path.is_file() or path.stat().st_nlink != 1:
            return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": None}
        raw = path.read_bytes()
        if len(raw) > limit:
            return {"path": relative, "status": "unreadable", "sha256": None,
                    "size_bytes": len(raw), "error": "file_too_large"}
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            return {"path": relative, "status": "unreadable", "sha256": None,
                    "size_bytes": len(raw), "error": "invalid_utf8"}
        return {"path": relative, "status": "present", "sha256": digest(raw), "size_bytes": len(raw)}
    except (OSError, ValueError) as error:
        return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": None,
                "error": str(error)}


def bind_project(runtime, project_path: os.PathLike[str] | str):
    modules = runtime.modules
    supplied = Path(project_path).expanduser()
    if not supplied.is_absolute() or any(part == ".." for part in supplied.parts):
        raise FoundationError("path_not_allowed", "project_path 必须是不含 .. 的绝对路径")
    projects_root = runtime.projects_root
    try:
        canonical = supplied.resolve(strict=True)
    except OSError as error:
        raise FoundationError("path_not_allowed", "项目目录不存在或不可访问") from error
    if supplied.is_symlink() or canonical.parent != projects_root or canonical == projects_root:
        raise FoundationError("path_not_allowed", "项目必须是 projects_root 的直接普通子目录")
    directory_name = canonical.name
    mapping = runtime.config.get("project_directories", {})
    reverse = {value: key for key, value in mapping.items()}
    expected_id = reverse.get(directory_name, directory_name)
    project_file = canonical / "project.json"
    if not project_file.exists():
        raise FoundationError("project_not_initialized", "缺少 project.json；不自动初始化项目")
    try:
        data = modules.project_init.load_project(canonical, expected_id)
    except (OSError, ValueError, RuntimeError) as error:
        raise FoundationError("identity_conflict", "持久项目身份或初始化结构不匹配", details=str(error)) from error
    return {
        "root": canonical,
        "project_id": data["project_id"],
        "directory_name": directory_name,
        "data": data,
        "project": {
            "project_id": data["project_id"],
            "project_path": str(canonical),
            "identity_source": "persisted",
            "identity_persisted": True,
        },
    }


def _registry_paths(data: dict) -> tuple[set[str], list[str]]:
    paths: set[str] = set()
    diagnostics: list[str] = []
    registry = data.get("artifact_registry")
    if registry is None:
        return paths, diagnostics
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        return paths, ["artifact_registry_invalid"]
    entries = registry.get("entries")
    if not isinstance(entries, dict):
        return paths, ["artifact_registry_invalid"]
    for artifact_id, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("artifact_id") != artifact_id:
            diagnostics.append("artifact_registry_invalid")
            continue
        for version in entry.get("versions", []) if isinstance(entry.get("versions"), list) else []:
            if not isinstance(version, dict) or not isinstance(version.get("content"), dict):
                diagnostics.append("artifact_registry_invalid")
                continue
            content = version["content"]
            if content.get("type") == "file":
                if isinstance(content.get("path"), str):
                    paths.add(content["path"])
                else:
                    diagnostics.append("artifact_registry_invalid")
            elif content.get("type") == "file-set":
                manifest = content.get("manifest", {})
                manifest_path = None
                if isinstance(manifest, dict):
                    manifest_path = manifest.get("path")
                    nested = manifest.get("manifest")
                    if not isinstance(manifest_path, str) and isinstance(nested, dict):
                        manifest_path = nested.get("path")
                if not isinstance(manifest, dict) or not isinstance(manifest_path, str):
                    diagnostics.append("artifact_registry_invalid")
                    continue
                paths.add(manifest_path)
            else:
                diagnostics.append("artifact_registry_invalid")
    return paths, diagnostics


def _expand_file_sets(root: Path, paths: set[str], diagnostics: list[str]) -> set[str]:
    expanded = set(paths)
    for relative in list(paths):
        descriptor = describe_file(root, relative, limit=128 * 1024)
        if descriptor["status"] != "present":
            continue
        try:
            data = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "files" not in data:
            continue
        files = data.get("files")
        if not isinstance(files, list):
            diagnostics.append("artifact_file_set_invalid")
            continue
        for member in files:
            if not isinstance(member, dict) or not isinstance(member.get("path"), str):
                diagnostics.append("artifact_file_set_invalid")
            else:
                expanded.add(member["path"])
    return expanded


def _snapshot_paths(root: Path) -> tuple[set[str], list[str]]:
    decisions = root / "docs/decisions.md"
    if not decisions.exists():
        return set(), []
    descriptor = describe_file(root, "docs/decisions.md", limit=1024 * 1024)
    if descriptor["status"] != "present":
        return set(), ["decisions_unreadable"]
    try:
        text = decisions.read_text(encoding="utf-8")
        marker_start = "<!-- buzz-develop-helper:confirmations:start -->"
        marker_end = "<!-- buzz-develop-helper:confirmations:end -->"
        if marker_start not in text or marker_end not in text:
            return set(), ["decisions_invalid"]
        block = text.split(marker_start, 1)[1].split(marker_end, 1)[0]
        fenced = block.strip()
        if fenced.startswith("```"):
            fenced = fenced.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(fenced)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IndexError):
        return set(), ["decisions_invalid"]
    paths = set()
    for record in data.get("confirmations", []) if isinstance(data, dict) else []:
        if not isinstance(record, dict):
            continue
        snapshot = record.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        if isinstance(snapshot.get("path"), str):
            paths.add(snapshot["path"])
        if isinstance(snapshot.get("manifest_path"), str):
            paths.add(snapshot["manifest_path"])
        for member in snapshot.get("files", []) if isinstance(snapshot.get("files"), list) else []:
            if isinstance(member, dict) and isinstance(member.get("snapshot_path"), str):
                paths.add(member["snapshot_path"])
    return paths, []


def _specification(runtime, data: dict):
    modules = runtime.modules
    report = modules.project_info.report(data)
    field = report["fields"]["specification"]
    if field["status"] == "unrecorded":
        return {"state": "missing", "name": None, "files": [], "root": None, "diagnostics": []}
    if field["status"] == "invalid":
        return {"state": "invalid", "name": None, "files": [], "root": None,
                "diagnostics": ["specification_invalid"]}
    value = field["value"]
    if value is None:
        return {"state": "none", "name": None, "files": [], "root": None, "diagnostics": []}
    try:
        resolved = modules.project_info.resolve_specification(runtime.foundation, value)
        root = runtime.upstream_root.joinpath(*resolved["path"].split("/"))
    except (OSError, ValueError, RuntimeError) as error:
        return {"state": "invalid", "name": value, "files": [], "root": None,
                "diagnostics": [f"specification_invalid:{error}"]}
    files = []
    diagnostics = []
    for path in sorted(root.rglob("*")) if root.exists() else []:
        if path.is_symlink():
            diagnostics.append("specification_unsafe_link")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.stat().st_nlink != 1:
            diagnostics.append("specification_unsafe_link")
            continue
        raw = path.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            diagnostics.append("specification_unreadable")
            content = None
        files.append({"path": relative, "status": "present", "sha256": digest(raw),
                      "size_bytes": len(raw), "content": content})
    if not root.exists() or not root.is_dir():
        diagnostics.append("specification_unreadable")
    return {"state": "selected", "name": value, "files": files, "root": root,
            "diagnostics": diagnostics}


def collect(runtime, binding) -> dict:
    root = binding["root"]
    data = binding["data"]
    diagnostics: list[str] = []
    entries = []
    for index, relative in enumerate(CORE_DOCUMENTS):
        descriptor = describe_file(root, relative)
        descriptor["roles"] = ["project_identity_and_registry" if relative == "project.json" else "core"]
        if descriptor["status"] == "unreadable":
            diagnostics.append(f"core_document_unreadable:{relative}")
        entries.append(("project", relative, descriptor))

    registry_paths, registry_diagnostics = _registry_paths(data)
    diagnostics.extend(registry_diagnostics)
    registry_paths = _expand_file_sets(root, registry_paths, diagnostics)
    snapshot_paths, snapshot_diagnostics = _snapshot_paths(root)
    diagnostics.extend(snapshot_diagnostics)
    protected_extra = registry_paths | snapshot_paths
    for relative in sorted(protected_extra):
        descriptor = describe_file(root, relative, limit=32 * 1024 * 1024)
        roles = []
        if relative in registry_paths:
            roles.append("artifact_registry_closure")
        if relative in snapshot_paths:
            roles.append("confirmation_snapshot_closure")
        descriptor["roles"] = roles
        entries.append(("project", relative, descriptor))

    specification = _specification(runtime, data)
    diagnostics.extend(specification["diagnostics"])
    for descriptor in specification["files"]:
        entries.append(("specification", descriptor["path"], descriptor))

    transaction_exists = (root / TRANSACTION_PATH).exists()
    if transaction_exists:
        diagnostics.append("transaction_pending")

    for key, path in (("config", runtime.foundation / "config/local.json"),
                      ("upstream_lock", runtime.foundation / "upstream-lock.json")):
        descriptor = {"path": str(path), "status": "present", "sha256": digest(path.read_bytes()),
                      "size_bytes": path.stat().st_size}
        entries.append(("runtime", key, descriptor))

    descriptors_by_key = {}
    total_bytes = 0
    project_target_bound = False
    for scope, relative, descriptor in entries:
        key = (scope, relative)
        if key in descriptors_by_key:
            existing = descriptors_by_key[key]
            existing["roles"] = sorted(set(existing.get("roles", []) + descriptor.get("roles", [])))
            continue
        descriptors_by_key[key] = descriptor

    items = []
    descriptor_map = {
        (scope, relative): descriptor
        for (scope, relative), descriptor in descriptors_by_key.items()
    }

    def registry_hash_diagnostics() -> list[str]:
        result = []
        registry = data.get("artifact_registry")
        if not isinstance(registry, dict):
            return result
        for entry in registry.get("entries", {}).values() if isinstance(registry.get("entries"), dict) else []:
            for version in entry.get("versions", []) if isinstance(entry, dict) else []:
                content = version.get("content", {}) if isinstance(version, dict) else {}
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "file":
                    descriptor = descriptor_map.get(("project", content.get("path")))
                    if descriptor and descriptor.get("sha256") != content.get("sha256"):
                        result.append("artifact_registry_mismatch")
                elif content.get("type") == "file-set":
                    manifest = content.get("manifest", {})
                    nested = manifest.get("manifest", {}) if isinstance(manifest, dict) else {}
                    files = manifest.get("files") or (nested.get("files") if isinstance(nested, dict) else None)
                    for member in files or []:
                        descriptor = descriptor_map.get(("project", member.get("path")))
                        if descriptor and descriptor.get("sha256") != member.get("sha256"):
                            result.append("artifact_registry_mismatch")
        return result

    diagnostics.extend(registry_hash_diagnostics())

    for (scope, relative), descriptor in sorted(descriptors_by_key.items(),
                                                key=lambda pair: (pair[0][0], pair[0][1])):
        item = {"scope": scope, **descriptor}
        if scope == "project" and relative == TARGET_PATH:
            if "artifact_registry_closure" in descriptor.get("roles", []) or \
                    "confirmation_snapshot_closure" in descriptor.get("roles", []):
                project_target_bound = True
                item["roles"] = sorted(set(item.get("roles", []) + ["registry_target"]))
        items.append(item)
        total_bytes += descriptor.get("size_bytes") or 0
    if len(items) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
        diagnostics.append("dependency_limit_exceeded")

    normalized = [{key: item[key] for key in ("scope", "path", "status", "sha256", "size_bytes")}
                  for item in sorted(items, key=lambda value: (value["scope"], value["path"]))]
    return {
        "items": items,
        "normalized": normalized,
        "dependency_set_sha256": canonical_sha(normalized),
        "diagnostics": sorted(set(diagnostics)),
        "transaction_pending": transaction_exists,
        "specification": specification,
        "target_bound_to_registry": project_target_bound,
    }
