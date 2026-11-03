"""Read-only confirmation record and snapshot validation for requirements recovery.

Copied from the persisted-record checks of buzz-develop-helper/scripts/
collaboration.py, plus trusted_context.required_statement. Never confirms,
signs, registers, sends, prepares handoffs or mutates project files.
"""

import hashlib
import json
from pathlib import Path
import re

if __package__:
    from . import artifact_records as artifacts
else:
    import artifact_records as artifacts


SCHEMA_VERSION = 1
DECISIONS_PATH = "docs/decisions.md"
DECISIONS_START = "<!-- buzz-develop-helper:confirmations:start -->"
DECISIONS_END = "<!-- buzz-develop-helper:confirmations:end -->"
MAX_RECORD_BYTES = 1024 * 1024
CONFIRMATION_ID_RE = re.compile(r"^C-[0-9a-f]{20}$")
TIMESTAMP_RE = artifacts.TIMESTAMP_RE
EFFECT_BINDING_KEYS = (
    "workflow_id",
    "run_id",
    "step_id",
    "attempt",
    "idempotency_key",
    "operation",
    "command_digest",
    "input_digest",
)
_STATEMENT_WHITESPACE = frozenset("\n\r\t")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(root, relative, *, missing_ok=False, limit=MAX_RECORD_BYTES):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("记录路径必须是项目内 POSIX 相对路径")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("记录路径必须是项目内规范相对路径")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"记录文件不能经过软链：{relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("记录路径越界")
    if not path.exists():
        if missing_ok:
            return None
        raise ValueError(f"记录文件不存在：{relative}")
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"记录文件不是独立普通文件：{relative}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"记录文件超过大小限制：{relative}")
    return raw


def empty_decisions():
    return {"schema_version": SCHEMA_VERSION, "confirmations": []}


def parse_decisions_text(text):
    if DECISIONS_START not in text and DECISIONS_END not in text:
        raise ValueError("decisions.md 缺少受管确认记录块")
    if text.count(DECISIONS_START) != 1 or text.count(DECISIONS_END) != 1:
        raise ValueError("decisions.md 确认记录标记不完整或重复")
    start = text.index(DECISIONS_START) + len(DECISIONS_START)
    end = text.index(DECISIONS_END, start)
    body = text[start:end].strip()
    if not body.startswith("```json\n") or not body.endswith("\n```"):
        raise ValueError("decisions.md 受管块必须包含 JSON code block")
    try:
        value = json.loads(body[len("```json\n"):-len("\n```")])
    except json.JSONDecodeError as error:
        raise ValueError("decisions.md 确认记录 JSON 无效") from error
    validate_decisions_shape(value)
    return value


def read_decisions(root):
    raw = read_regular(root, DECISIONS_PATH, missing_ok=True)
    if raw is None:
        return "", empty_decisions(), "missing"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("decisions.md 必须是 UTF-8") from error
    return text, parse_decisions_text(text), digest(raw)


def required_text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} 必须是非空单行文本")
    return value.strip()


def required_statement(value, label="statement"):
    """Keep the admitted event body. Newlines are valid; other controls are not."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空文本")
    if any(ord(char) < 32 and char not in _STATEMENT_WHITESPACE for char in value):
        raise ValueError(f"{label} 含有非法控制字符")
    return value.strip()


def validate_actor(actor, label):
    if not isinstance(actor, dict):
        raise ValueError(f"{label} 身份无效")
    required_text(actor.get("principal_id"), f"{label} principal_id")
    required_text(actor.get("authority"), f"{label} authority")


def validate_effect_binding(value):
    if not isinstance(value, dict):
        raise ValueError("effect_binding 必须是对象")
    unknown = set(value) - set(EFFECT_BINDING_KEYS)
    if unknown:
        raise ValueError("effect_binding 包含未知字段")
    normalized = {}
    for field in ("workflow_id", "run_id", "step_id", "idempotency_key", "operation"):
        normalized[field] = required_text(value.get(field), f"effect_binding.{field}")
    attempt = value.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("effect_binding.attempt 无效")
    normalized["attempt"] = attempt
    for field in ("command_digest", "input_digest"):
        digest_value = required_text(value.get(field), f"effect_binding.{field}")
        if not artifacts.SHA256_RE.fullmatch(digest_value):
            raise ValueError(f"effect_binding.{field} 无效")
        normalized[field] = digest_value
    return normalized


def validate_decisions_shape(value):
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("不支持的确认记录 schema_version")
    confirmations = value.get("confirmations")
    if not isinstance(confirmations, list):
        raise ValueError("confirmations 必须是数组")
    seen = set()
    for record in confirmations:
        if not isinstance(record, dict) or not CONFIRMATION_ID_RE.fullmatch(str(record.get("confirmation_id", ""))):
            raise ValueError("确认记录 ID 无效")
        confirmation_id = record["confirmation_id"]
        if confirmation_id in seen:
            raise ValueError(f"确认记录重复：{confirmation_id}")
        if record.get("schema_version") != SCHEMA_VERSION or record.get("status") != "active":
            raise ValueError(f"确认记录状态无效：{confirmation_id}")
        if not TIMESTAMP_RE.fullmatch(str(record.get("recorded_at", ""))):
            raise ValueError(f"确认记录时间无效：{confirmation_id}")
        validate_actor(record.get("recorded_by"), "记录 Main")
        artifact = record.get("artifact")
        if not isinstance(artifact, dict) or not artifacts.ARTIFACT_ID_RE.fullmatch(str(artifact.get("artifact_id", ""))):
            raise ValueError(f"确认对象无效：{confirmation_id}")
        if artifact.get("kind") not in artifacts.KINDS or not artifacts.VERSION_RE.fullmatch(str(artifact.get("version", ""))):
            raise ValueError(f"确认对象类型或版本无效：{confirmation_id}")
        if not artifacts.SHA256_RE.fullmatch(str(artifact.get("content_sha256", ""))):
            raise ValueError(f"确认对象摘要无效：{confirmation_id}")
        required_text(record.get("permitted_use"), "确认用途")
        required_text(record.get("confirmed_scope"), "确认范围")
        if not isinstance(record.get("non_authorizations"), list) or not isinstance(record.get("open_items"), list):
            raise ValueError(f"确认边界无效：{confirmation_id}")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("type") != "current-session":
            raise ValueError(f"确认依据类型无效：{confirmation_id}")
        for field in ("provider", "authority", "user_principal_id", "session_id", "message_id"):
            required_text(evidence.get(field), f"确认依据 {field}")
        required_statement(evidence.get("statement"), "确认依据 statement")
        if not TIMESTAMP_RE.fullmatch(str(evidence.get("confirmed_at", ""))) or evidence.get("runtime_authenticated") is not True:
            raise ValueError(f"当前会话确认依据未认证：{confirmation_id}")
        snapshot = record.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("type") not in {"file", "file-set"}:
            raise ValueError(f"确认快照结构无效：{confirmation_id}")
        if "effect_binding" in record:
            try:
                validate_effect_binding(record.get("effect_binding"))
            except ValueError as error:
                raise ValueError(
                    f"确认记录 effect_binding 无效：{confirmation_id}"
                ) from error
        seen.add(confirmation_id)


def artifact_version(registry, artifact_id, version):
    entry = registry.get("entries", {}).get(artifact_id) if registry else None
    if entry is None:
        raise ValueError(f"成果尚未登记：{artifact_id}")
    for item in entry["versions"]:
        if item["version"] == version:
            return entry, item
    raise ValueError(f"成果版本尚未登记：{artifact_id}@{version}")


def validate_snapshot(root, record):
    snapshot = record["snapshot"]
    if snapshot["type"] == "file":
        raw = read_regular(root, snapshot.get("path"), limit=artifacts.MAX_ARTIFACT_BYTES)
        if digest(raw) != snapshot.get("sha256") or snapshot["sha256"] != record["artifact"]["content_sha256"]:
            raise ValueError(f"确认快照摘要不匹配：{record['confirmation_id']}")
        return
    manifest_raw = read_regular(root, snapshot.get("manifest_path"))
    if digest(manifest_raw) != snapshot.get("manifest_sha256") or snapshot["manifest_sha256"] != record["artifact"]["content_sha256"]:
        raise ValueError(f"确认清单快照摘要不匹配：{record['confirmation_id']}")
    files = snapshot.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"确认集合快照缺少成员：{record['confirmation_id']}")
    for item in files:
        raw = read_regular(root, item.get("snapshot_path"), limit=artifacts.MAX_ARTIFACT_BYTES)
        if digest(raw) != item.get("sha256"):
            raise ValueError(f"确认集合成员摘要不匹配：{record['confirmation_id']}")
