"""Immutable UI content versions and read-only history access."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

from .context import (
    CONTRACT_VERSION,
    CURRENT_POINTER,
    DESIGN_PATH,
    MANIFEST_PATH,
    STATE_DIR,
    VERSIONS_DIR,
    CONTENT_BUDGET,
    ToolError,
    canonical_bytes,
    canonical_sha,
    digest,
)


def state_root(project_root: Path) -> Path:
    return project_root / STATE_DIR


def versions_root(project_root: Path) -> Path:
    return project_root / VERSIONS_DIR


def verify_packet(packet: dict):
    if not isinstance(packet, dict):
        raise ToolError("history_invalid", "版本 packet 不是对象")
    required = {"schema_version", "project_id", "artifact_root", "entrypoint",
                "design_path", "readme_path", "files", "sources", "restored_from"}
    if set(packet) != required:
        raise ToolError("history_invalid", "版本 packet 字段集合不符")
    if packet["schema_version"] != 1:
        raise ToolError("history_invalid", "版本 packet schema_version 必须为 1")
    if not isinstance(packet["files"], list) or not packet["files"]:
        raise ToolError("history_invalid", "版本 packet files 必须是非空数组")
    seen = set()
    for item in packet["files"]:
        if set(item) != {"path", "sha256"}:
            raise ToolError("history_invalid", "版本成员只能含 path 和 sha256")
        if item["path"] in seen:
            raise ToolError("history_invalid", "版本成员路径重复")
        seen.add(item["path"])
    return canonical_sha(packet)


def build_packet(*, project_id, artifact_root, entrypoint, member_items, sources,
                 restored_from):
    """Canonical content packet. Time never enters the identity; sources and
    artifacts both participate, so identical bytes with changed sources produce
    a different revision.
    """
    files = [{"path": path, "sha256": sha} for path, sha in sorted(member_items)]
    packet = {
        "schema_version": 1,
        "project_id": project_id,
        "artifact_root": artifact_root,
        "entrypoint": entrypoint,
        "design_path": DESIGN_PATH,
        "readme_path": f"{artifact_root}/README.md",
        "files": files,
        "sources": sources,
        "restored_from": restored_from,
    }
    verify_packet(packet)
    return packet


def manifest_for_packet(packet: dict):
    return {
        "schema_version": 1,
        "entrypoint": packet["entrypoint"],
        "files": [dict(item) for item in packet["files"]],
    }


def encode_manifest(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8") + b"\n"


def _fsync_directory(path: Path):
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _tree_member_paths(tree: Path):
    found = set()
    for current, directories, files in os.walk(tree, followlinks=False):
        current_path = Path(current)
        for name in files:
            child = current_path / name
            relative = child.relative_to(tree).as_posix()
            found.add(relative)
    return found


def store_version(project_root: Path, *, packet, member_blobs, manifest_raw, origin,
                  created_at, diagnostics=None):
    """Persist an immutable version (members + manifest snapshot + meta).

    A directory already holding the same SHA is fully verified and reused; a
    partial or corrupt directory is never repaired.
    """
    revision = verify_packet(packet)
    version_dir = versions_root(project_root) / revision
    if version_dir.exists():
        if version_dir.is_symlink() or not version_dir.is_dir():
            raise ToolError("history_invalid", "版本目录不是独立普通目录")
        meta_path = version_dir / "version.json"
        if not meta_path.is_file():
            raise ToolError("history_invalid",
                            "同 SHA 版本目录缺少 version.json；不修补损坏版本")
        loaded = load_version_meta(project_root, revision, full=True)
        if digest(manifest_raw) != loaded["meta"]["manifest_sha256"]:
            raise ToolError("history_invalid",
                            "同 SHA 版本清单快照字节不一致；不覆盖复用")
        expected = {item["path"] for item in packet["files"]} | {MANIFEST_PATH}
        if _tree_member_paths(version_dir / "tree") != expected:
            raise ToolError("history_invalid",
                            "同 SHA 版本 tree 成员集合不符；不修补损坏版本")
        return revision, True
    tree = version_dir / "tree"
    tree.mkdir(parents=True, exist_ok=False)
    for item in packet["files"]:
        raw = member_blobs[item["path"]]
        if digest(raw) != item["sha256"]:
            raise ToolError("history_invalid",
                            f"版本成员摘要与 packet 不符：{item['path']}")
        _write_private(tree / item["path"], raw)
    _write_private(tree / MANIFEST_PATH, manifest_raw)
    meta = {
        "schema_version": 1,
        "packet": packet,
        "revision_sha256": revision,
        "manifest_sha256": digest(manifest_raw),
        "created_at": created_at,
        "origin": origin,
        "diagnostics": diagnostics or [],
    }
    _write_private(version_dir / "version.json",
                   json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
                   + b"\n")
    _fsync_directory(version_dir)
    return revision, False


def current_pointer(project_root: Path):
    """Return the persisted current revision SHA, or None. Corrupt pointer is
    collection_invalid; this function never repairs it."""
    pointer_path = project_root / CURRENT_POINTER
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("collection_invalid", "当前指针不是有效 JSON") from error
    revision = pointer.get("revision_sha256") if isinstance(pointer, dict) else None
    if not isinstance(revision, str) or len(revision) != 64:
        raise ToolError("collection_invalid", "当前指针缺少合法 revision_sha256")
    return revision


def parse_created_at(value):
    if not isinstance(value, str):
        raise ToolError("history_invalid", "版本 created_at 非法")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise ToolError("history_invalid", "版本 created_at 格式非法") from None
    return parsed


def load_version_meta(project_root: Path, revision: str, *, full: bool):
    version_dir = versions_root(project_root) / revision
    version_file = version_dir / "version.json"
    if not revision or len(revision) != 64 or not all(ch in "0123456789abcdef" for ch in revision):
        raise ToolError("invalid_arguments", "revision_sha256 必须是 64 位小写十六进制")
    if not version_dir.is_dir() or version_dir.is_symlink():
        raise ToolError("history_not_found", f"历史版本不存在：{revision}")
    if not version_file.is_file() or version_file.is_symlink():
        raise ToolError("history_invalid", "版本缺少 version.json")
    try:
        meta = json.loads(version_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("history_invalid", "version.json 无法读取") from error
    if not isinstance(meta, dict) or meta.get("schema_version") != 1:
        raise ToolError("history_invalid", "version.json schema_version 必须为 1")
    packet = meta.get("packet")
    packet_sha = verify_packet(packet)
    if meta.get("revision_sha256") != revision or packet_sha != revision:
        raise ToolError("history_invalid", "版本摘要与 packet 或目录名不一致")
    parse_created_at(meta.get("created_at"))
    manifest_sha = meta.get("manifest_sha256")
    if not isinstance(manifest_sha, str) or len(manifest_sha) != 64:
        raise ToolError("history_invalid", "版本缺少合法 manifest_sha256")
    result = {"meta": meta, "packet": packet, "version_dir": version_dir,
              "created_at": meta["created_at"]}
    if full:
        tree = version_dir / "tree"
        manifest_snapshot = tree / MANIFEST_PATH
        if not manifest_snapshot.is_file() or digest(manifest_snapshot.read_bytes()) != manifest_sha:
            raise ToolError("history_invalid", "版本清单快照缺失或摘要不符")
        for item in packet["files"]:
            member = tree / item["path"]
            if not member.is_file() or member.is_symlink():
                raise ToolError("history_invalid", f"版本成员缺失：{item['path']}")
            if digest(member.read_bytes()) != item["sha256"]:
                raise ToolError("history_invalid", f"版本成员摘要不符：{item['path']}")
        result["tree"] = tree
    return result


def list_versions(project_root: Path, *, limit=20, after_revision=None):
    root = versions_root(project_root)
    if not root.is_dir():
        return [], None
    entries = []
    for child in root.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        loaded = load_version_meta(project_root, child.name, full=False)
        entries.append(loaded)
    entries.sort(key=lambda item: item["meta"]["revision_sha256"])
    entries.sort(key=lambda item: parse_created_at(item["meta"]["created_at"]), reverse=True)
    ordered = entries
    if after_revision is not None:
        index = next((i for i, item in enumerate(ordered)
                      if item["meta"]["revision_sha256"] == after_revision), None)
        if index is None:
            raise ToolError("invalid_arguments", "after_revision 游标不存在")
        ordered = ordered[index + 1:]
    page = ordered[:limit]
    next_after = page[-1]["meta"]["revision_sha256"] if len(ordered) > limit and page else None
    return page, next_after


def version_summary(loaded: dict):
    packet = loaded["packet"]
    return {
        "revision_sha256": loaded["meta"]["revision_sha256"],
        "created_at": loaded["meta"]["created_at"],
        "origin": loaded["meta"].get("origin"),
        "artifact_root": packet["artifact_root"],
        "entrypoint": packet["entrypoint"],
        "restored_from": packet.get("restored_from"),
        "file_count": len(packet["files"]),
    }


def version_detail(project_root: Path, revision: str):
    loaded = load_version_meta(project_root, revision, full=True)
    packet = loaded["packet"]
    tree = loaded["tree"]
    contents = []
    budget = CONTENT_BUDGET
    for item in packet["files"]:
        raw = (tree / item["path"]).read_bytes()
        text = None
        omitted = False
        try:
            text = raw.decode("utf-8")
            encoded = raw
            if len(encoded) <= budget:
                budget -= len(encoded)
            else:
                text = None
                omitted = True
        except UnicodeDecodeError:
            text = None
        contents.append({"key": f"project:{item['path']}", "path": item["path"],
                         "content": text, "content_omitted": omitted})
    return {
        "revision_sha256": revision,
        "created_at": loaded["meta"]["created_at"],
        "origin": loaded["meta"].get("origin"),
        "packet": packet,
        "manifest_sha256": loaded["meta"]["manifest_sha256"],
        "contents": contents,
    }
