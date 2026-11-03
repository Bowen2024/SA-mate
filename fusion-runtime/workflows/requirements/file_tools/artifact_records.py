"""Read-only artifact registry validation for requirements recovery.

Copied from the registry checks of buzz-develop-helper/scripts/artifacts.py.
Only validates persisted records; never registers, previews, writes project
files or starts downstream work.
"""

import hashlib
import json
from pathlib import Path
import re


REGISTRY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
KINDS = ("requirements", "solution", "ui")
MAX_METADATA_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def safe_project_file(root, relative, limit=MAX_ARTIFACT_BYTES):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("成果路径必须是项目内 POSIX 相对路径")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("成果路径必须是项目内规范相对路径")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("不允许通过软链登记成果")
    if not path.exists() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"成果文件缺失或不是独立普通文件：{relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("成果路径越界")
    size = path.stat().st_size
    if size > limit:
        raise ValueError(f"成果文件超过首版 {limit // (1024 * 1024)} MiB 限制：{relative}")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return {"path": candidate.as_posix(), "sha256": hasher.hexdigest(), "size": size}


def read_manifest(root, relative):
    metadata = safe_project_file(root, relative, MAX_METADATA_BYTES)
    path = root / relative
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("成果清单必须是 UTF-8 JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("不支持的成果清单 schema_version")
    entrypoint = manifest.get("entrypoint")
    members = manifest.get("files")
    if not isinstance(entrypoint, str) or not isinstance(members, list) or not members:
        raise ValueError("成果清单必须包含 entrypoint 和非空 files")
    verified = []
    seen = set()
    for item in members:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("成果清单 files 仅接受 path 和 sha256")
        relative_path, expected = item["path"], item["sha256"]
        if relative_path in seen:
            raise ValueError("成果清单包含重复路径")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise ValueError("成果清单包含无效 SHA-256")
        actual = safe_project_file(root, relative_path)
        if actual["sha256"] != expected:
            raise ValueError(f"成果清单摘要不匹配：{relative_path}")
        verified.append(actual)
        seen.add(relative_path)
    if entrypoint not in seen:
        raise ValueError("成果清单 entrypoint 必须列入 files")
    return {
        "type": "file-set",
        "manifest": metadata,
        "entrypoint": entrypoint,
        "files": verified,
    }


def validate_registry(root, data):
    registry = data.get("artifact_registry")
    if registry is None:
        return None, []
    if not isinstance(registry, dict) or registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError("不支持的 artifact_registry schema_version")
    if registry.get("confirmations_path") != "docs/decisions.md":
        raise ValueError("artifact_registry.confirmations_path 不受支持")
    if registry.get("handoffs_directory") != "docs/handoffs":
        raise ValueError("artifact_registry.handoffs_directory 不受支持")
    entries = registry.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("artifact_registry.entries 必须是对象")
    verified = []
    for artifact_id, entry in entries.items():
        if not ARTIFACT_ID_RE.fullmatch(artifact_id) or not isinstance(entry, dict):
            raise ValueError("成果 ID 或登记结构无效")
        if entry.get("artifact_id") != artifact_id or entry.get("kind") not in KINDS:
            raise ValueError(f"成果登记身份不匹配：{artifact_id}")
        versions = entry.get("versions")
        current = entry.get("current_version")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"成果登记没有版本：{artifact_id}")
        seen_versions = set()
        for version in versions:
            if not isinstance(version, dict) or not VERSION_RE.fullmatch(str(version.get("version", ""))):
                raise ValueError(f"成果版本格式无效：{artifact_id}")
            label = version["version"]
            if label in seen_versions:
                raise ValueError(f"成果版本重复：{artifact_id}@{label}")
            content = version.get("content")
            if not isinstance(content, dict) or content.get("type") not in {"file", "file-set"}:
                raise ValueError(f"成果内容结构无效：{artifact_id}@{label}")
            if content["type"] == "file":
                actual = safe_project_file(root, content.get("path"))
                if content.get("sha256") != actual["sha256"] or content.get("size") != actual["size"]:
                    raise ValueError(f"成果版本摘要不匹配：{artifact_id}@{label}")
            else:
                manifest = content.get("manifest")
                if not isinstance(manifest, dict):
                    raise ValueError(f"成果清单记录无效：{artifact_id}@{label}")
                actual = read_manifest(root, manifest.get("path"))
                if actual != content:
                    raise ValueError(f"成果集合与清单不匹配：{artifact_id}@{label}")
            confirmations = version.get("confirmation_ids")
            if not isinstance(confirmations, list) or any(not isinstance(value, str) for value in confirmations):
                raise ValueError(f"确认引用格式无效：{artifact_id}@{label}")
            for field in ("producer_role", "purpose", "summary"):
                if not isinstance(version.get(field), str) or not version[field].strip():
                    raise ValueError(f"成果版本缺少 {field}：{artifact_id}@{label}")
            if version.get("document_status") is not None and not isinstance(version["document_status"], str):
                raise ValueError(f"文档状态格式无效：{artifact_id}@{label}")
            if not isinstance(version.get("open_items"), list):
                raise ValueError(f"未决项格式无效：{artifact_id}@{label}")
            availability = version.get("availability")
            if not isinstance(availability, dict) or availability.get("scope") not in {"local-only", "git-commit"}:
                raise ValueError(f"可见范围格式无效：{artifact_id}@{label}")
            commit = availability.get("git_commit")
            if availability["scope"] == "local-only" and commit is not None:
                raise ValueError(f"本地成果不能声称 Git 提交：{artifact_id}@{label}")
            if availability["scope"] == "git-commit" and (
                not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit)
            ):
                raise ValueError(f"Git 可见成果缺少有效提交：{artifact_id}@{label}")
            registration = version.get("registration")
            actor = registration.get("actor") if isinstance(registration, dict) else None
            if (
                not isinstance(actor, dict)
                or actor.get("role") != "main"
                or not isinstance(actor.get("principal_id"), str)
                or not actor["principal_id"].strip()
                or not isinstance(actor.get("authority"), str)
                or not actor["authority"].strip()
                or not isinstance(registration.get("recorded_at"), str)
                or not TIMESTAMP_RE.fullmatch(registration["recorded_at"])
            ):
                raise ValueError(f"登记身份必须由运行时绑定 Main：{artifact_id}@{label}")
            seen_versions.add(label)
            verified.append({"artifact_id": artifact_id, "version": label})
        if current is not None and current not in seen_versions:
            raise ValueError(f"current_version 不存在：{artifact_id}")
    return registry, verified


def content_sha(content):
    return content["sha256"] if content["type"] == "file" else content["manifest"]["sha256"]
