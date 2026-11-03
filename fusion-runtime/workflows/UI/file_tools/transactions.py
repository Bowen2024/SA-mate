"""Transaction inspection (5A) plus controlled accept and recovery (5C).

Public collection mutations only happen through per-file atomic replacements
ordered members -> manifest -> current pointer. Whole-directory atomicity is
never promised; fixed plan/before/after evidence plus the active transaction
log make every interrupt point inspectable and explicitly recoverable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
from datetime import datetime, timezone

from .context import (
    ACTIVE_TRANSACTION,
    CURRENT_POINTER,
    DESIGN_PATH,
    MANIFEST_PATH,
    REQUESTS_DIR,
    STATE_DIR,
    TRANSACTIONS_DIR,
    ToolError,
    canonical_bytes,
    canonical_sha,
    digest,
    resolve_project_path,
    validate_relative_path,
    validate_member_path,
)
from .versions import (
    current_pointer,
    encode_manifest,
    load_version_meta,
    manifest_for_packet,
    state_root,
    store_version,
    verify_packet,
)


ACCEPT_OPERATION = "ui_accept_revision"
RECOVER_OPERATION = "ui_recover_revision"
JOURNAL_NAME = ".project-state-transaction.json"
REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
REVISION_ID_RE = re.compile(r"^R-[0-9a-f]{32}$")
TRANSACTION_ID_RE = re.compile(r"^T-[0-9a-f]{32}$")

VERIFICATION_CODES = (
    "document_set", "manifest", "pointer", "history", "inputs", "unknown_files",
)


PLAN_EXPECTED_KEYS = {
    "schema_version", "project_id", "transaction_id", "request_id", "mode",
    "revision_id", "base_digest", "candidate_digest", "sources", "targets",
    "version", "delete_paths", "plan_sha256",
}


def active_transaction_id(project_root: Path):
    pointer = project_root / ACTIVE_TRANSACTION
    if not pointer.exists():
        return None
    if pointer.is_symlink() or not pointer.is_file():
        raise ToolError("transaction_invalid", "活动事务指针不是独立普通文件")
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("transaction_invalid", "活动事务日志损坏") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ToolError("transaction_invalid", "活动事务日志 schema_version 必须为 1")
    transaction_id = data.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise ToolError("transaction_invalid", "活动事务日志缺少 transaction_id")
    return transaction_id, data.get("stage")


def _load_plan(project_root: Path, transaction_id: str):
    if not isinstance(transaction_id, str) or not transaction_id.startswith("T-") \
            or len(transaction_id) != 34:
        raise ToolError("invalid_arguments", "transaction_id 必须是 T- 加 32 位小写十六进制")
    txn_dir = project_root / TRANSACTIONS_DIR / transaction_id
    plan_path = txn_dir / "plan.json"
    if not plan_path.is_file():
        raise ToolError("transaction_invalid", f"事务计划不存在：{transaction_id}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("transaction_invalid", "事务计划不是有效 JSON") from error
    if not isinstance(plan, dict) or set(plan) != PLAN_EXPECTED_KEYS:
        raise ToolError("transaction_invalid", "事务计划字段集合不符")
    recorded = plan.pop("plan_sha256")
    if recorded != canonical_sha(plan):
        raise ToolError("transaction_invalid", "plan_sha256 与计划内容不一致")
    plan["plan_sha256"] = recorded
    return plan, txn_dir


def _blob_state(base: Path, relative: str):
    path = base / relative
    if not path.exists():
        return {"state": "missing", "sha256": "missing"}
    if path.is_symlink() or not path.is_file():
        raise ToolError("transaction_invalid", f"事务证据不是普通文件：{relative}")
    return {"state": "present", "sha256": digest(path.read_bytes())}


def _saved_receipt(project_root: Path, request_id):
    if not isinstance(request_id, str):
        return None
    receipt_path = project_root / REQUESTS_DIR / f"{request_id}.json"
    if not receipt_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "invalid"}
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        return {"status": "invalid"}
    return {"status": receipt.get("status"), "write_outcome": receipt.get("write_outcome")}


def inspect_transaction(project_root: Path, binding, *, transaction_id=None):
    """Read-only transaction check; never executes resume or rollback."""
    active = active_transaction_id(project_root)
    if transaction_id is None:
        if active is None:
            return {
                "state": "not_activated",
                "transaction": None,
                "targets": [],
                "available_actions": [],
            }
        transaction_id, stage = active
    else:
        stage = active[1] if active and active[0] == transaction_id else None

    plan, txn_dir = _load_plan(project_root, transaction_id)
    if plan["project_id"] != binding["project_id"]:
        raise ToolError("transaction_invalid", "事务项目身份不匹配")
    targets = _classify_targets(project_root, plan, txn_dir)
    receipt = _saved_receipt(project_root, plan.get("request_id"))
    saved = bool(receipt and receipt.get("status") == "completed"
                 and receipt.get("write_outcome") == "saved")
    closed_record = _recovery_closed_record(project_root, transaction_id)
    pre_activation = bool(
        receipt and receipt.get("status") == "completed"
        and receipt.get("write_outcome") == "not_written"
        and not (active and active[0] == transaction_id))
    if closed_record is not None:
        actions = []
        status = "closed"
    elif saved:
        actions = ["verify_and_close"]
        status = "committed"
    elif not (active and active[0] == transaction_id) \
            and all(item["actual"] == "before" for item in targets) and pre_activation:
        actions = []
        status = "not_activated"
    elif all(item["actual"] == "before" for item in targets):
        actions = ["resume", "rollback", "close_private"]
        status = "staged"
    elif all(item["actual"] == "after" for item in targets):
        actions = ["resume", "rollback"]
        status = "applying"
    else:
        actions = ["resume", "rollback"]
        status = "interrupted"
    return {
        "state": "incomplete",
        "transaction": {
            "transaction_id": transaction_id,
            "request_id": plan["request_id"],
            "stage": stage,
            "status": status,
            "active": active is not None and active[0] == transaction_id,
            "saved_receipt": receipt,
            "recovery_receipt": closed_record,
            "version": plan.get("version"),
            "delete_paths": plan.get("delete_paths", []),
        },
        "targets": targets,
        "available_actions": actions,
    }


# ---------------------------------------------------------------------------
# 5C: controlled accept, persistent receipts and explicit recovery
# ---------------------------------------------------------------------------


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _fsync_dir(path: Path):
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_private(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_json(path: Path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_private(path, raw)


def _fail(failpoint, event, context=None):
    if failpoint is not None:
        failpoint(event, context or {})


def _check(code, scope, passed, message, *, paths=None, checked=True):
    return {"code": code, "scope": scope, "checked": checked, "passed": passed,
            "paths": paths or [], "message": message}


def _receipt_path(root: Path, request_id: str) -> Path:
    return root / REQUESTS_DIR / f"{request_id}.json"


def _load_receipt_record(root: Path, request_id: str):
    path = _receipt_path(root, request_id)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ToolError("receipt_invalid", "持久回执不是独立普通文件")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("receipt_invalid", f"持久回执损坏：{request_id}") from error
    required = {"schema_version", "project_id", "operation", "request_id",
                "params_digest", "status"}
    if not isinstance(record, dict) or record.get("schema_version") != 1 \
            or not required <= set(record):
        raise ToolError("receipt_invalid", f"持久回执结构不受支持：{request_id}")
    return record


def _write_receipt(root: Path, record: dict):
    _write_json(_receipt_path(root, record["request_id"]), record)


def _receipt_gate(root: Path, *, operation, project_id, params_digest, request_id):
    record = _load_receipt_record(root, request_id)
    if record is None:
        return None
    if record.get("operation") != operation or record.get("project_id") != project_id \
            or record.get("params_digest") != params_digest:
        raise ToolError("request_reused",
                        "request_id 已绑定其他操作或不同参数；不能复用")
    return record


def _incomplete_details(record: dict):
    details = {"request_id": record["request_id"]}
    if record.get("revision_id"):
        details["revision_id"] = record["revision_id"]
    if record.get("transaction_id"):
        details["transaction_id"] = record["transaction_id"]
    if record.get("workspace_path"):
        details["workspace_path"] = record["workspace_path"]
    return details


def _public_state(root: Path, relative: str):
    path = resolve_project_path(root, relative)
    if not path.exists():
        return {"state": "missing", "sha256": "missing"}, None
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ToolError("collection_invalid", f"公共目标不是独立普通文件：{relative}")
    raw = path.read_bytes()
    return {"state": "present", "sha256": digest(raw)}, raw


def _member_raw(root: Path, relative: str):
    state, raw = _public_state(root, relative)
    if state["state"] != "present":
        raise ToolError("collection_invalid", f"公共成员缺失：{relative}")
    return raw


def _current_sources(runtime, binding, base, current):
    from .context import Closure
    from .workspace import _descriptor_views, _history_pair, _rebuild_import_spec

    import_spec = _rebuild_import_spec(runtime, base.get("import"))
    closure = Closure(runtime, binding, base["artifact_root"],
                      base["source_paths"], import_spec)
    closure.collect(binding["data"], current, *_history_pair(binding["root"]),
                    include_contents=False)
    sources, _targets = _descriptor_views(closure)
    referenced = set()
    for descriptor in closure.finalized_descriptors():
        roles = set(descriptor.get("role", "").split("|"))
        if "registry_reference" in roles:
            referenced.add(descriptor["key"].split(":", 1)[1])
    return sources, referenced, closure


def _unknown_public_paths(root: Path, artifact_root: str, member_paths):
    from .context import CACHE_NAMES

    known = set(member_paths)
    unknown = []
    base = resolve_project_path(root, artifact_root)
    if base.exists():
        for current, _dirs, names in os.walk(base, followlinks=False):
            current_path = Path(current)
            for name in sorted(names):
                if name in CACHE_NAMES:
                    continue
                child = current_path / name
                if child.is_symlink():
                    continue
                relative = child.relative_to(root).as_posix()
                if relative not in known:
                    unknown.append(relative)
    design = root / DESIGN_PATH
    if design.exists() and not design.is_symlink() and DESIGN_PATH not in known:
        unknown.append(DESIGN_PATH)
    return sorted(unknown)


def _readback_checks(runtime, binding, base, *, member_items, manifest_raw,
                     pointer_raw, new_revision, old_revision, expected_sources):
    """Six-item verification against actual public bytes and current facts."""
    root = binding["root"]
    artifact_root = base["artifact_root"]
    member_paths = {path for path, _sha in member_items}
    checks = []

    document_bad = []
    for path, expected_sha in member_items:
        state, raw = _public_state(root, path)
        if state != {"state": "present", "sha256": expected_sha}:
            document_bad.append(path)
    checks.append(_check("document_set", "public", not document_bad,
                         "公共成员与版本 packet 逐字节一致" if not document_bad
                         else "公共成员复读失败", paths=document_bad))

    state, raw = _public_state(root, MANIFEST_PATH)
    manifest_ok = (state["state"] == "missing" if manifest_raw is None
                   else state["state"] == "present" and raw == manifest_raw)
    checks.append(_check("manifest", "public", manifest_ok,
                         "公共清单与固定新字节一致"))

    pointer_state, pointer_actual = _public_state(root, CURRENT_POINTER)
    if pointer_raw is None:
        pointer_ok = pointer_state["state"] == "missing"
    else:
        pointer_ok = pointer_state["state"] == "present" and pointer_actual == pointer_raw
    checks.append(_check("pointer", "public", pointer_ok,
                         "当前指针与固定新字节一致" if pointer_raw is not None
                         else "当前指针已撤除"))

    history_bad = []
    try:
        load_version_meta(root, new_revision, full=True)
    except ToolError as error:
        history_bad.append(f"{new_revision[:12]}：{error.code}")
    if old_revision:
        try:
            load_version_meta(root, old_revision, full=True)
        except ToolError as error:
            history_bad.append(f"{old_revision[:12]}：{error.code}")
    checks.append(_check("history", "private", not history_bad,
                         "新旧不可变版本均可完整核验" if not history_bad
                         else "版本历史核验失败", paths=history_bad))

    current = {"kind": "none"}
    inputs_ok = True
    try:
        from .context import detect_current

        current = detect_current(runtime, root, artifact_root, binding["project_id"])
        sources, _refs, _closure = _current_sources(runtime, binding, base, current)
        inputs_ok = sources == expected_sources
    except ToolError as error:
        inputs_ok = False
        inputs_message = f"输入复读失败：{error.code}"
    else:
        inputs_message = "输入来源与计划一致" if inputs_ok else "输入或登记来源在接收期间变化"
    checks.append(_check("inputs", "project", inputs_ok, inputs_message))

    unknown = _unknown_public_paths(root, artifact_root, member_paths)
    checks.append(_check("unknown_files", "public", True,
                         "未知文件保持原样、未被自动登记或删除" if not unknown
                         else "未知文件仍保留、未被自动登记", paths=unknown))
    return checks, unknown


def _encode_pointer(project_id, revision_sha, manifest_sha, artifact_root,
                    transaction_id, request_id) -> bytes:
    pointer = {
        "schema_version": 1,
        "project_id": project_id,
        "revision_sha256": revision_sha,
        "manifest_sha256": manifest_sha,
        "artifact_root": artifact_root,
        "last_transaction_id": transaction_id,
        "last_request_id": request_id,
    }
    return (json.dumps(pointer, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")


def _active_log(root: Path, transaction_id: str, plan_sha: str, project_id: str, stage: str):
    _write_json(root / ACTIVE_TRANSACTION, {
        "schema_version": 1,
        "project_id": project_id,
        "transaction_id": transaction_id,
        "plan_sha256": plan_sha,
        "stage": stage,
    })


def _classify_targets(root: Path, plan: dict, txn_dir: Path):
    targets = []
    for target in plan["targets"]:
        if set(target) != {"path", "before", "after"}:
            raise ToolError("transaction_invalid", "事务目标字段非法")
        relative = target["path"]
        validate_relative_path(relative, label="事务目标路径")
        before = _blob_state(txn_dir / "before", relative)
        after = _blob_state(txn_dir / "after", relative)
        if target["before"] != before or target["after"] != after:
            raise ToolError("transaction_invalid",
                            f"事务 before/after 证据与计划不符：{relative}")
        actual = _blob_state(root, relative) if (root / relative).exists() \
            else {"state": "missing", "sha256": "missing"}
        actual_path = resolve_project_path(root, relative)
        if actual_path.exists():
            if actual_path.is_symlink() or not actual_path.is_file():
                actual = {"state": "other", "sha256": "other"}
            else:
                actual = {"state": "present", "sha256": digest(actual_path.read_bytes())}
        classification = "after" if actual == after else ("before" if actual == before
                                                           else "other")
        targets.append({"path": relative, "actual": classification,
                        "before": before, "after": after})
    return targets


def _plan_record(root: Path, transaction_id: str):
    plan, txn_dir = _load_plan(root, transaction_id)
    targets = _classify_targets(root, plan, txn_dir)
    return plan, txn_dir, targets


def _recovery_closed_record(root: Path, transaction_id: str):
    directory = root / REQUESTS_DIR
    if not directory.is_dir():
        return None
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("operation") == RECOVER_OPERATION \
                and record.get("transaction_id") == transaction_id \
                and record.get("status") == "completed":
            return record
    return None


def _accept_params_digest(root, revision_id, inspection_id, delete_paths):
    return canonical_sha({
        "operation": ACCEPT_OPERATION,
        "project_path": str(root),
        "revision_id": revision_id,
        "inspection_id": inspection_id,
        "delete_paths": sorted(delete_paths),
    })


def accept_revision(runtime, credentials, import_roots, *, binding_factory, project_path,
                    revision_id, inspection_id, request_id, delete_paths, failpoint=None):
    del import_roots  # imports were bound to the read_id and live in base.json
    if not isinstance(project_path, str) or not isinstance(revision_id, str) \
            or not isinstance(inspection_id, str) or not isinstance(request_id, str):
        raise ToolError("invalid_arguments", "接收参数必须为字符串")
    if not REVISION_ID_RE.match(revision_id):
        raise ToolError("invalid_arguments", "revision_id 必须为 R- 加 32 位小写十六进制")
    if not REQUEST_ID_RE.match(request_id):
        raise ToolError("invalid_arguments", "request_id 必须是标准小写 UUID")
    if not isinstance(delete_paths, list) or not all(isinstance(item, str) for item in delete_paths):
        raise ToolError("invalid_arguments", "delete_paths 必须是字符串数组（无删除传 []）")

    binding = binding_factory(project_path)
    root = binding["root"]
    project_id = binding["project_id"]
    params_digest = _accept_params_digest(root, revision_id, inspection_id, delete_paths)
    project_state = runtime.modules.project_state

    if (root / JOURNAL_NAME).exists():
        raise ToolError("main_transaction_pending",
                        "项目根存在 Main 成果索引事务；UI 不接管，先由 Main 恢复")
    try:
        lock = project_state.project_state_lock(root, "ui-accept")
        lock.__enter__()
    except ValueError as error:
        raise ToolError("lock_busy", "项目状态写入锁已存在；先核对在途操作，不自动删除锁") from error
    try:
        return _accept_locked(
            runtime, credentials, binding=binding, root=root, project_id=project_id,
            params_digest=params_digest, revision_id=revision_id,
            inspection_id=inspection_id, request_id=request_id,
            delete_paths=delete_paths, failpoint=failpoint)
    finally:
        lock.__exit__(None, None, None)


def _write_evidence(txn_dir: Path, phase: str, relative: str, raw: bytes):
    target = txn_dir / phase / relative
    _atomic_private(target, raw)


def _fix_plan_targets(runtime, root, txn_dir, *, project_id, request_id,
                      transaction_id, revision_id, base, evaluation, changes, candidate_blobs,
                      new_manifest_raw, new_sha, old_sha):
    """Fix before/after bytes and the immutable plan before activating a log."""
    del runtime
    plan_targets = []

    def fix_target(relative, before_raw, after_raw):
        before_state = {"state": "present", "sha256": digest(before_raw)} \
            if before_raw is not None else {"state": "missing", "sha256": "missing"}
        after_state = {"state": "present", "sha256": digest(after_raw)} \
            if after_raw is not None else {"state": "missing", "sha256": "missing"}
        actual_state, _actual_raw = _public_state(root, relative)
        if actual_state != before_state:
            raise ToolError("target_changed",
                            f"固定事务前发现公共目标已变化：{relative}",
                            details={"paths": [relative]}, write_outcome="not_written")
        if before_raw is not None:
            _write_evidence(txn_dir, "before", relative, before_raw)
        if after_raw is not None:
            _write_evidence(txn_dir, "after", relative, after_raw)
        plan_targets.append({"path": relative, "before": before_state,
                             "after": after_state})

    member_order = sorted(set(changes["added"]) | set(changes["modified"])
                          | set(changes["removed"]))
    current_blobs = {path: _member_raw(root, path)
                     for path in set(changes["modified"]) | set(changes["removed"])}
    for path in member_order:
        fix_target(path, current_blobs.get(path), candidate_blobs.get(path))

    manifest_before = (root / MANIFEST_PATH).read_bytes() \
        if (root / MANIFEST_PATH).exists() else None
    pointer_before_path = root / CURRENT_POINTER
    pointer_before = pointer_before_path.read_bytes() if pointer_before_path.exists() else None
    pointer_after = _encode_pointer(
        project_id, new_sha, digest(new_manifest_raw), base["artifact_root"],
        transaction_id, request_id)
    fix_target(MANIFEST_PATH, manifest_before, new_manifest_raw)
    fix_target(CURRENT_POINTER, pointer_before, pointer_after)

    plan = {
        "schema_version": 1,
        "project_id": project_id,
        "transaction_id": transaction_id,
        "request_id": request_id,
        "mode": base["mode"],
        "revision_id": revision_id,
        "base_digest": base["base_digest"],
        "candidate_digest": evaluation["candidate_digest"],
        "sources": evaluation["packet"]["sources"],
        "targets": plan_targets,
        "version": {"old": old_sha, "new": new_sha},
        "delete_paths": changes["removed"],
    }
    plan["plan_sha256"] = canonical_sha(plan)
    _write_json(txn_dir / "plan.json", plan)
    return {"plan": plan, "targets": plan_targets,
            "member_order": member_order, "pointer_after": pointer_after}


def _ensure_public_parent(runtime, path: Path):
    if not path.parent.exists():
        _ensure_public_parent(runtime, path.parent)
        path.parent.mkdir(parents=False, exist_ok=True)
        _fsync_dir(path.parent)


def _write_public(runtime, path: Path, raw: bytes):
    _ensure_public_parent(runtime, path)
    runtime.modules.project_state.atomic_replace(path, raw)


def _remove_public(path: Path):
    path.unlink()
    _fsync_dir(path.parent)


def _map_blocking_issues(issues):
    for issue in issues:
        code = issue["code"]
        if code == "candidate_incomplete":
            code = "collection_invalid"
        if code in {"collection_invalid", "unlisted_file", "limit_exceeded"}:
            raise ToolError(code, issue["message"], details={"paths": issue.get("paths", [])})


def _accept_payload(binding, *, state, outcome, request_id, revision_id, transaction_id,
                    revision_sha, changes, versions_pair, verification, receipt_replay,
                    next_action=None):
    return {
        "contract_version": "ui-tools-v1",
        "operation": ACCEPT_OPERATION,
        "project": binding["project"],
        "state": state,
        "diagnostics": [],
        "checks": verification or [],
        "write_outcome": outcome,
        "request_id": request_id,
        "revision_id": revision_id,
        "transaction_id": transaction_id,
        "revision_sha256": revision_sha,
        "current_revision": revision_sha,
        "versions": versions_pair,
        "changes": changes,
        "verification": verification,
        "receipt_replay": receipt_replay,
        "error": None,
        "next_action": next_action or "用只读工具复读当前集合；保存只证明文件接收，浏览器证据仍未验证",
    }


def _legacy_packet(project_id, current):
    return {
        "schema_version": 1,
        "project_id": project_id,
        "artifact_root": current["artifact_root"],
        "entrypoint": current["manifest"]["entrypoint"],
        "design_path": DESIGN_PATH,
        "readme_path": f"{current['artifact_root']}/README.md",
        "files": [dict(item) for item in current["members"]],
        "sources": [],
        "restored_from": None,
    }


def _accept_locked(runtime, credentials, *, binding, root, project_id, params_digest,
                   revision_id, inspection_id, request_id, delete_paths, failpoint):
    from . import workspace as workspace_mod

    receipt = _receipt_gate(root, operation=ACCEPT_OPERATION, project_id=project_id,
                            params_digest=params_digest, request_id=request_id)
    if receipt is not None:
        if receipt["status"] == "incomplete":
            raise ToolError("operation_incomplete",
                            "同一接收请求尚未完成；先 inspect(target=transaction) 核对并恢复",
                            details=_incomplete_details(receipt),
                            next_action="ui_inspect(target=transaction) 后显式 resume/rollback")
        if receipt["status"] != "completed":
            raise ToolError("receipt_invalid", "接收回执状态不受支持")
        return _accept_replay(runtime, binding, root, project_id, receipt)

    active = active_transaction_id(root)
    if active is not None:
        raise ToolError("operation_incomplete",
                        "存在活动 UI 事务；先核对并恢复，不开始第二笔接收",
                        details={"transaction_id": active[0]})

    try:
        record = credentials.validate_inspect(inspection_id, project_path=str(root))

        work_root, base = workspace_mod._load_base(root, revision_id)
        if base["project"]["project_id"] != project_id:
            raise ToolError("transaction_invalid", "候选工作区绑定了其他项目")
        if revision_id in workspace_mod._accept_closed_revisions(root):
            raise ToolError("inspection_invalid",
                            "该工作区已有终态接收回执；继续修改请重新 prepare")
        artifact_root = base["artifact_root"]

        evaluation = workspace_mod.evaluate_candidate(
            runtime, binding, base, work_root, closed=False)
        _map_blocking_issues(evaluation["issues"])

        changes = evaluation["changes"]
        if record["revision_id"] != revision_id:
            raise ToolError("inspection_invalid", "inspection_id 绑定了其他候选")
        if record.get("artifact_root") != artifact_root:
            raise ToolError("inspection_invalid", "inspection_id 绑定的 artifact_root 不一致")
        if record["removed"] != changes["removed"]:
            raise ToolError("inspection_invalid", "inspection_id 绑定的 removed 集合已失效")
        if record["base_digest"] != base["base_digest"]:
            raise ToolError("inspection_invalid", "inspection_id 绑定的基线已失效")
        if record["runtime_baseline_digest"] != canonical_sha(runtime.baseline):
            raise ToolError("runtime_baseline_changed", "检查凭证绑定的运行基线与当前服务不一致")
        if record["candidate_digest"] != evaluation["candidate_digest"]:
            raise ToolError("candidate_changed",
                            "检查后候选 tree 或声明发生变化；请重新比较差异并检查")

        normalized_delete = []
        for item in delete_paths:
            normalized_delete.append(validate_member_path(item, artifact_root))
        if sorted(normalized_delete) != changes["removed"]:
            raise ToolError("invalid_arguments",
                            "delete_paths 必须与检查结果 removed 精确相同（无删除传 []）")

        current = evaluation["current"]
        candidate_members = evaluation["candidate_members"]
        packet = evaluation["packet"]
        verify_packet(packet)
        new_sha = evaluation["proposed_revision_sha256"]

        for path in changes["added"]:
            if resolve_project_path(root, path).exists():
                raise ToolError("unmanaged_target_exists",
                                f"计划新成员路径已存在未受管文件：{path}；不覆盖",
                                details={"paths": [path]})
        for path in changes["modified"] + changes["removed"]:
            if not resolve_project_path(root, path).is_file():
                raise ToolError("target_changed",
                                f"检查后公共成员消失：{path}", details={"paths": [path]})

        _sources, referenced, _closure = _current_sources(
            runtime, binding, base, current)
        write_paths = set(changes["added"]) | set(changes["modified"]) \
            | set(changes["removed"]) | {MANIFEST_PATH, CURRENT_POINTER}
        crossed = sorted(referenced & write_paths)
        if crossed:
            raise ToolError("registered_path_in_use",
                            "拟修改成员或公共清单被正式登记引用；先处理既有登记",
                            details={"paths": crossed})

        candidate_blobs = {}
        for path in candidate_members:
            candidate_blobs[path] = (work_root / "tree" / path).read_bytes()
        new_manifest = manifest_for_packet(packet)
        new_manifest_raw = encode_manifest(new_manifest)

        if current["kind"] == "managed" and current["revision_sha256"] == new_sha:
            return _accept_unchanged(
                runtime, binding, root, project_id, base=base, current=current,
                evaluation=evaluation, packet=packet, params_digest=params_digest,
                revision_id=revision_id, request_id=request_id, changes=changes)

        created_at = _utc_now()
        if current["kind"] == "legacy":
            legacy_packet = _legacy_packet(project_id, current)
            legacy_blobs = {item["path"]: _member_raw(root, item["path"])
                            for item in legacy_packet["files"]}
            legacy_manifest_raw = (root / MANIFEST_PATH).read_bytes()
            old_sha, _reused = store_version(
                root, packet=legacy_packet, member_blobs=legacy_blobs,
                manifest_raw=legacy_manifest_raw, origin="legacy", created_at=created_at)
        elif current["kind"] == "managed":
            old_sha = current["revision_sha256"]
            load_version_meta(root, old_sha, full=True)
        else:
            old_sha = None
        _fail(failpoint, "legacy_archived", {"old": old_sha})

        new_sha, _reused = store_version(
            root, packet=packet, member_blobs=candidate_blobs,
            manifest_raw=new_manifest_raw, origin="accepted", created_at=created_at)
        _fail(failpoint, "version_stored", {"new": new_sha})

        transaction_id = "T-" + secrets.token_hex(16)
        txn_dir = root / TRANSACTIONS_DIR / transaction_id
        txn_dir.mkdir(parents=True, exist_ok=False)
        prepared = _fix_plan_targets(
            runtime, root, txn_dir, project_id=project_id, request_id=request_id,
            transaction_id=transaction_id, revision_id=revision_id, base=base,
            evaluation=evaluation,
            changes=changes, candidate_blobs=candidate_blobs,
            new_manifest_raw=new_manifest_raw, new_sha=new_sha, old_sha=old_sha)
        _fail(failpoint, "evidence_fixed", {"transaction_id": transaction_id})
    except ToolError:
        raise
    except Exception as error:
        residue = []
        if "new_sha" in locals():
            residue.append(str(root / "versions" / new_sha))
        if "txn_dir" in locals() and txn_dir.exists():
            residue.append(str(txn_dir))
        terminal = {
            "schema_version": 1,
            "project_id": project_id,
            "operation": ACCEPT_OPERATION,
            "request_id": request_id,
            "params_digest": params_digest,
            "status": "completed",
            "write_outcome": "not_written",
            "revision_id": revision_id,
            "transaction_id": locals().get("transaction_id"),
            "residue": residue,
            "created_at": _utc_now(),
            "completed_at": _utc_now(),
        }
        _write_receipt(root, terminal)
        raise ToolError(
            "io_error", f"活动事务落盘前中断：{error}；公共成果未改",
            details={"request_id": request_id, "revision_id": revision_id,
                     "transaction_id": transaction_id, "residue": residue},
            write_outcome="not_written",
            next_action="指定 transaction_id 用 ui_recover_revision(rollback) 关闭私有记录") from error

    plan = prepared["plan"]
    plan_targets = prepared["targets"]
    member_order = prepared["member_order"]
    pointer_after = prepared["pointer_after"]

    receipt_incomplete = {
        "schema_version": 1,
        "project_id": project_id,
        "operation": ACCEPT_OPERATION,
        "request_id": request_id,
        "params_digest": params_digest,
        "status": "incomplete",
        "write_outcome": None,
        "revision_id": revision_id,
        "transaction_id": transaction_id,
        "workspace_path": str(work_root),
        "version": {"old": old_sha, "new": new_sha},
        "created_at": _utc_now(),
    }
    _write_receipt(root, receipt_incomplete)
    _active_log(root, transaction_id, plan["plan_sha256"], project_id, "staged")
    credentials.consume_inspect(inspection_id, project_path=str(root))

    try:
        _fail(failpoint, "before_first_write", {"transaction_id": transaction_id})
        _active_log(root, transaction_id, plan["plan_sha256"], project_id, "applying")
        for index, path in enumerate(member_order):
            _recheck_before(root, plan_targets, path)
            public_path = resolve_project_path(root, path)
            if path in candidate_blobs:
                _write_public(runtime, public_path, candidate_blobs[path])
            else:
                _remove_public(public_path)
            _fail(failpoint, f"member_after:{index}", {"path": path})
        _fail(failpoint, "after_members", {})

        _recheck_before(root, plan_targets, MANIFEST_PATH)
        _write_public(runtime, root / MANIFEST_PATH, new_manifest_raw)
        _fail(failpoint, "after_manifest", {})

        _recheck_before(root, plan_targets, CURRENT_POINTER)
        _write_public(runtime, root / CURRENT_POINTER, pointer_after)
        _fail(failpoint, "after_pointer", {})
    except ToolError:
        raise
    except Exception as error:
        _handle_apply_exception(root, plan, receipt_incomplete, error)

    _active_log(root, transaction_id, plan["plan_sha256"], project_id, "verifying")
    _fail(failpoint, "before_verify", {"transaction_id": transaction_id})
    member_items = [(item["path"], item["sha256"]) for item in packet["files"]]
    verification, _unknown = _readback_checks(
        runtime, binding, base, member_items=member_items,
        manifest_raw=new_manifest_raw, pointer_raw=pointer_after,
        new_revision=new_sha, old_revision=old_sha,
        expected_sources=packet["sources"])

    if not all(item["passed"] for item in verification):
        all_after = all(_public_state(root, item["path"])[0] == item["after"]
                        for item in plan_targets)
        outcome = "saved_unverified" if all_after else "unknown"
        receipt_incomplete.update({
            "status": "incomplete", "write_outcome": outcome,
            "verification": verification, "updated_at": _utc_now(),
        })
        _write_receipt(root, receipt_incomplete)
        next_action = "用 ui_inspect(target=transaction) 核对；saved_unverified 禁止盲目重试" \
            if outcome == "saved_unverified" else "用 ui_inspect(target=transaction) 核对逐项事实后显式恢复"
        return _accept_payload(
            binding, state="incomplete", outcome=outcome, request_id=request_id,
            revision_id=revision_id, transaction_id=transaction_id,
            revision_sha=current_pointer(root), changes=changes,
            versions_pair={"old": old_sha, "new": new_sha},
            verification=verification, receipt_replay=False, next_action=next_action)

    _active_log(root, transaction_id, plan["plan_sha256"], project_id, "committed")
    receipt_saved = dict(receipt_incomplete)
    receipt_saved.update({
        "status": "completed",
        "write_outcome": "saved",
        "packet": packet,
        "sources": packet["sources"],
        "manifest_sha256": digest(new_manifest_raw),
        "changes": changes,
        "current_revision": new_sha,
        "verification": verification,
        "completed_at": _utc_now(),
    })
    _write_receipt(root, receipt_saved)
    try:
        _fail(failpoint, "after_saved_receipt", {"transaction_id": transaction_id})
    except Exception as error:
        raise ToolError(
            "io_error",
            "终态 saved 回执已落盘，但活动日志清理前中断；公共结果已提交",
            details={"transaction_id": transaction_id, "receipt_request_id": request_id},
            write_outcome="saved",
            next_action="ui_recover_revision(action=resume) 核验并关闭遗留活动日志") from error
    _remove_active_log(root)

    return _accept_payload(
        binding, state="stable", outcome="saved", request_id=request_id,
        revision_id=revision_id, transaction_id=transaction_id,
        revision_sha=new_sha, changes=changes,
        versions_pair={"old": old_sha, "new": new_sha},
        verification=verification, receipt_replay=False)


def _recheck_before(root, plan_targets, relative):
    target = next(item for item in plan_targets if item["path"] == relative)
    actual_state, _raw = _public_state(root, relative)
    if actual_state != target["before"]:
        raise ToolError("target_changed",
                        f"写入前公共目标已被外部修改：{relative}；停止覆盖",
                        details={"paths": [relative]}, write_outcome="unknown",
                        next_action="ui_inspect(target=transaction) 核对后显式恢复")


def _remove_active_log(root: Path):
    pointer = root / ACTIVE_TRANSACTION
    if pointer.exists():
        pointer.unlink()
        _fsync_dir(pointer.parent)


def _handle_apply_exception(root, plan, receipt_incomplete, error):
    targets = _classify_targets(root, plan, root / TRANSACTIONS_DIR / plan["transaction_id"])
    all_after = all(item["actual"] == "after" for item in targets)
    outcome = "saved_unverified" if all_after else "unknown"
    receipt_incomplete.update({
        "status": "incomplete", "write_outcome": outcome,
        "interrupted": True, "updated_at": _utc_now(),
    })
    _write_receipt(root, receipt_incomplete)
    raise ToolError(
        "io_error", f"接收在公共写入阶段中断：{error}",
        details={"request_id": plan["request_id"], "revision_id": plan["revision_id"],
                 "transaction_id": plan["transaction_id"],
                 "targets": [{"path": item["path"], "actual": item["actual"]}
                             for item in targets]},
        write_outcome=outcome,
        next_action="ui_inspect(target=transaction) 核对后显式 resume/rollback") from error


def _accept_unchanged(runtime, binding, root, project_id, *, base, current, evaluation,
                      packet, params_digest, revision_id, request_id, changes):
    manifest_raw = (root / MANIFEST_PATH).read_bytes()
    pointer_raw = (root / CURRENT_POINTER).read_bytes()
    revision_sha = current["revision_sha256"]
    member_items = [(item["path"], item["sha256"]) for item in packet["files"]]
    verification, _unknown = _readback_checks(
        runtime, binding, base, member_items=member_items,
        manifest_raw=manifest_raw, pointer_raw=pointer_raw,
        new_revision=revision_sha, old_revision=None,
        expected_sources=packet["sources"])
    receipt = {
        "schema_version": 1,
        "project_id": project_id,
        "operation": ACCEPT_OPERATION,
        "request_id": request_id,
        "params_digest": params_digest,
        "status": "completed",
        "write_outcome": "unchanged",
        "revision_id": revision_id,
        "transaction_id": None,
        "packet": packet,
        "sources": packet["sources"],
        "manifest_sha256": digest(manifest_raw),
        "changes": changes,
        "version": {"old": revision_sha, "new": revision_sha},
        "current_revision": revision_sha,
        "verification": verification,
        "created_at": _utc_now(),
        "completed_at": _utc_now(),
    }
    _write_receipt(root, receipt)
    return _accept_payload(
        binding, state="stable", outcome="unchanged", request_id=request_id,
        revision_id=revision_id, transaction_id=None, revision_sha=revision_sha,
        changes=changes, versions_pair={"old": revision_sha, "new": revision_sha},
        verification=verification, receipt_replay=False)


def _replay_verification(runtime, binding, root, base, receipt):
    """Fresh six-item verification for a replay; independent of stored claims."""
    packet = receipt.get("packet") or {}
    member_items = [(item["path"], item["sha256"]) for item in packet.get("files", [])]
    saved = receipt.get("write_outcome") == "saved"
    try:
        independent = current_pointer(root)
        if saved and receipt.get("current_revision"):
            load_version_meta(root, receipt["current_revision"], full=True)
        if receipt.get("write_outcome") == "unchanged":
            load_version_meta(root, receipt["version"]["new"], full=True)
    except ToolError as error:
        raise ToolError("receipt_invalid",
                        f"回执引用的不可变版本无法核验：{error.code}；不重造已结束成果") from error
    manifest_state, manifest_raw = _public_state(root, MANIFEST_PATH)
    pointer_state, pointer_raw = _public_state(root, CURRENT_POINTER)
    document_bad = []
    for path, expected_sha in member_items:
        state, _raw = _public_state(root, path)
        if state != {"state": "present", "sha256": expected_sha}:
            document_bad.append(path)
    checks = [
        _check("document_set", "public", not document_bad,
               "回放复读：公共成员与回执版本一致" if not document_bad
               else "回放复读：公共成员已不是回执版本", paths=document_bad),
        _check("manifest", "public",
               manifest_state["state"] == "present"
               and manifest_state["sha256"] == receipt.get("manifest_sha256"),
               "回放复读：公共清单与回执一致"),
        _check("pointer", "public",
               pointer_state["state"] == "present"
               and independent == receipt.get("current_revision"),
               "当前指针与回执版本一致" if independent == receipt.get("current_revision")
               else "当前版本已前进，回执仅代表历史结果"),
        _check("history", "private",
               bool(saved and independent) or receipt.get("write_outcome") == "unchanged",
               "回执引用版本可核验" if independent else "回执无已保存版本"),
    ]
    inputs_ok = False
    try:
        from .context import detect_current

        current = detect_current(runtime, root, base["artifact_root"],
                                 binding["project_id"])
        sources, _refs, _closure = _current_sources(runtime, binding, base, current)
        inputs_ok = sources == receipt.get("sources")
    except ToolError:
        inputs_ok = False
    checks.append(_check("inputs", "project", inputs_ok,
                         "输入来源与回执一致" if inputs_ok
                         else "输入来源已变化；回执只代表当时结果"))
    unknown = _unknown_public_paths(
        root, base["artifact_root"], {path for path, _sha in member_items})
    checks.append(_check("unknown_files", "public", True,
                         "未知文件保持原样", paths=unknown))
    return checks, independent


def _accept_replay(runtime, binding, root, project_id, receipt):
    from . import workspace as workspace_mod

    revision_id = receipt.get("revision_id")
    if not isinstance(revision_id, str) or not REVISION_ID_RE.match(revision_id):
        raise ToolError("receipt_invalid", "接收回执缺少合法 revision_id")
    _work_root, base = workspace_mod._load_base(root, revision_id)
    verification, independent = _replay_verification(runtime, binding, root, base, receipt)
    return _accept_payload(
        binding, state="stable", outcome=receipt.get("write_outcome", "saved"),
        request_id=receipt["request_id"], revision_id=revision_id,
        transaction_id=receipt.get("transaction_id"),
        revision_sha=independent,
        changes=receipt.get("changes") or {"added": [], "modified": [], "removed": []},
        versions_pair=receipt.get("version") or {"old": None, "new": independent},
        verification=verification, receipt_replay=True,
        next_action="receipt_replay=true：结果来自已完成回执；current_revision 为独立复读的当前版本")


def _recover_params_digest(root, transaction_id, action):
    return canonical_sha({
        "operation": RECOVER_OPERATION,
        "project_path": str(root),
        "transaction_id": transaction_id,
        "action": action,
    })


def _recovery_payload(binding, *, outcome, action, transaction_status, request_id,
                      transaction_id, current_revision, verification, receipt_replay,
                      next_action=None, state="stable"):
    return {
        "contract_version": "ui-tools-v1",
        "operation": RECOVER_OPERATION,
        "project": binding["project"],
        "state": state,
        "diagnostics": [],
        "checks": verification or [],
        "write_outcome": outcome,
        "request_id": request_id,
        "revision_id": None,
        "transaction_id": transaction_id,
        "revision_sha256": current_revision,
        "current_revision": current_revision,
        "recovery_action": action,
        "transaction_status": transaction_status,
        "verification": verification,
        "receipt_replay": receipt_replay,
        "error": None,
        "next_action": next_action or "用只读工具复读当前集合与历史",
    }


def recover_revision(runtime, *, binding_factory, project_path, transaction_id,
                     request_id, action, failpoint=None):
    del failpoint
    if not isinstance(project_path, str) or not isinstance(transaction_id, str) \
            or not isinstance(request_id, str):
        raise ToolError("invalid_arguments", "恢复参数必须为字符串")
    if not TRANSACTION_ID_RE.match(transaction_id):
        raise ToolError("invalid_arguments", "transaction_id 必须为 T- 加 32 位小写十六进制")
    if not REQUEST_ID_RE.match(request_id):
        raise ToolError("invalid_arguments", "request_id 必须是标准小写 UUID")
    if action not in {"resume", "rollback"}:
        raise ToolError("invalid_arguments", "action 必须是 resume 或 rollback")

    binding = binding_factory(project_path)
    root = binding["root"]
    project_id = binding["project_id"]
    params_digest = _recover_params_digest(root, transaction_id, action)
    project_state = runtime.modules.project_state

    if (root / JOURNAL_NAME).exists():
        raise ToolError("main_transaction_pending",
                        "项目根存在 Main 成果索引事务；UI 不接管，先由 Main 恢复")
    try:
        lock = project_state.project_state_lock(root, "ui-recover")
        lock.__enter__()
    except ValueError as error:
        raise ToolError("lock_busy", "项目状态写入锁已存在；先核对在途进程，不自动删除锁") from error
    try:
        return _recover_locked(
            runtime, binding=binding, root=root, project_id=project_id,
            transaction_id=transaction_id, request_id=request_id, action=action,
            params_digest=params_digest)
    finally:
        lock.__exit__(None, None, None)


def _evidence_raw(txn_dir: Path, phase: str, relative: str):
    path = txn_dir / phase / relative
    return path.read_bytes() if path.exists() else None


def _ordered_targets(targets):
    members = [item for item in targets
               if item["path"] not in {MANIFEST_PATH, CURRENT_POINTER}]
    members.sort(key=lambda item: item["path"])
    manifest = next((item for item in targets if item["path"] == MANIFEST_PATH), None)
    pointer = next((item for item in targets if item["path"] == CURRENT_POINTER), None)
    return [*members, *([manifest] if manifest else []), *([pointer] if pointer else [])]


def _write_after_state(runtime, root, txn_dir, item):
    relative = item["path"]
    public_path = resolve_project_path(root, relative)
    if item["after"]["state"] == "present":
        _write_public(runtime, public_path, _evidence_raw(txn_dir, "after", relative))
    elif public_path.exists():
        _remove_public(public_path)


def _write_before_state(runtime, root, txn_dir, item):
    relative = item["path"]
    public_path = resolve_project_path(root, relative)
    if item["before"]["state"] == "present":
        _write_public(runtime, public_path, _evidence_raw(txn_dir, "before", relative))
    elif public_path.exists():
        _remove_public(public_path)


def _version_views(runtime, binding, root, base, revision):
    loaded = load_version_meta(root, revision, full=True)
    packet = loaded["packet"]
    manifest_snapshot = loaded["tree"] / MANIFEST_PATH
    pointer_state, pointer_raw = _public_state(root, CURRENT_POINTER)
    return loaded, packet, manifest_snapshot.read_bytes(), pointer_state, pointer_raw


def _write_recover_receipt(root, *, project_id, request_id, params_digest, transaction_id,
                           action, outcome, transaction_status, current_revision,
                           verification):
    record = {
        "schema_version": 1,
        "project_id": project_id,
        "operation": RECOVER_OPERATION,
        "request_id": request_id,
        "params_digest": params_digest,
        "status": "completed",
        "write_outcome": outcome,
        "transaction_id": transaction_id,
        "action": action,
        "transaction_status": transaction_status,
        "current_revision": current_revision,
        "verification": verification,
        "created_at": _utc_now(),
        "completed_at": _utc_now(),
    }
    _write_receipt(root, record)
    return record


def _recover_locked(runtime, *, binding, root, project_id, transaction_id, request_id,
                    action, params_digest):
    from . import workspace as workspace_mod

    receipt = _receipt_gate(root, operation=RECOVER_OPERATION, project_id=project_id,
                            params_digest=params_digest, request_id=request_id)
    if receipt is not None:
        if receipt["status"] == "incomplete":
            raise ToolError("operation_incomplete", "同一恢复请求尚未完成",
                            details=_incomplete_details(receipt))
        return _recovery_payload(
            binding, outcome=receipt["write_outcome"], action=receipt["action"],
            transaction_status=receipt["transaction_status"],
            request_id=request_id, transaction_id=transaction_id,
            current_revision=current_pointer(root),
            verification=receipt.get("verification", []), receipt_replay=True,
            next_action="receipt_replay=true：结果来自已完成恢复回执；current_revision 为独立复读")

    plan, txn_dir = _load_plan(root, transaction_id)
    if plan["project_id"] != project_id:
        raise ToolError("transaction_invalid", "事务项目身份不匹配")

    active = active_transaction_id(root)
    if active is not None and active[0] != transaction_id:
        raise ToolError("operation_incomplete",
                        "存在其他活动 UI 事务；先处理该事务，不并发恢复",
                        details={"transaction_id": active[0]})
    is_active = active is not None and active[0] == transaction_id

    closed_record = _recovery_closed_record(root, transaction_id)
    targets = _classify_targets(root, plan, txn_dir)

    for label, revision in (("old", plan["version"]["old"]), ("new", plan["version"]["new"])):
        if revision is not None:
            try:
                load_version_meta(root, revision, full=True)
            except ToolError as error:
                raise ToolError("transaction_invalid",
                                f"事务引用的 {label} 版本不可核验：{error.code}；不生成覆盖动作") from error

    work_root, base = workspace_mod._load_base(root, plan["revision_id"])
    artifact_root = base["artifact_root"]
    source_view = {"kind": "none", "revision_sha256": None,
                   "artifact_root": artifact_root, "manifest": None,
                   "members": [], "unmanaged": []}
    sources_now, _refs, _closure = _current_sources(runtime, binding, base, source_view)
    source_changed = sources_now != plan["sources"]

    accept_receipt = _load_receipt_record(root, plan["request_id"])
    saved = bool(accept_receipt and accept_receipt.get("status") == "completed"
                 and accept_receipt.get("write_outcome") == "saved")
    other_targets = [item["path"] for item in targets if item["actual"] == "other"]

    if closed_record is not None:
        return _recovery_payload(
            binding, outcome=closed_record["write_outcome"],
            action=closed_record["action"], transaction_status="already_closed",
            request_id=request_id, transaction_id=transaction_id,
            current_revision=current_pointer(root),
            verification=closed_record.get("verification", []), receipt_replay=False,
            next_action="该事务已有终态恢复回执；证据保留，不重复执行")

    if other_targets:
        raise ToolError("recovery_conflict",
                        "目标含既非 before 也非 after 的第三方状态；两种恢复动作都拒绝覆盖",
                        details={"paths": other_targets}, write_outcome="not_written")

    new_loaded, new_packet, new_manifest_raw, _pointer_state, _pointer_raw = \
        _version_views(runtime, binding, root, base, plan["version"]["new"])

    if saved:
        if action == "rollback":
            raise ToolError("already_committed",
                            "终态 saved 回执已落盘；已提交版本回退请走 prepare(history) 重新接收",
                            write_outcome="not_written")
        if any(item["actual"] != "after" for item in targets):
            raise ToolError("recovery_conflict",
                            "终态接收后公共目标发生变化；不为清理日志覆盖改动",
                            details={"paths": [item["path"] for item in targets
                                               if item["actual"] != "after"]},
                            write_outcome="not_written")
        if source_changed:
            raise ToolError("recovery_conflict",
                            "终态接收后输入来源发生变化；只保留校验，不代为处置",
                            write_outcome="not_written")
        member_items = [(item["path"], item["sha256"]) for item in new_packet["files"]]
        pointer_after = _evidence_raw(txn_dir, "after", CURRENT_POINTER)
        verification, _unknown = _readback_checks(
            runtime, binding, base, member_items=member_items,
            manifest_raw=new_manifest_raw, pointer_raw=pointer_after,
            new_revision=plan["version"]["new"], old_revision=plan["version"]["old"],
            expected_sources=plan["sources"])
        if not all(item["passed"] for item in verification):
            raise ToolError("recovery_conflict",
                            "终态回执复读失败；保留事务与日志，不盲目关闭",
                            write_outcome="saved_unverified")
        if is_active:
            _remove_active_log(root)
        _write_recover_receipt(
            root, project_id=project_id, request_id=request_id, params_digest=params_digest,
            transaction_id=transaction_id, action=action, outcome="saved",
            transaction_status="already_closed",
            current_revision=plan["version"]["new"], verification=verification)
        return _recovery_payload(
            binding, outcome="saved", action=action,
            transaction_status="already_closed", request_id=request_id,
            transaction_id=transaction_id, current_revision=plan["version"]["new"],
            verification=verification, receipt_replay=False,
            next_action="终态 saved 已核验并关闭遗留活动日志；未重写公共成员")

    if action == "resume":
        if not is_active:
            if all(item["actual"] == "before" for item in targets):
                raise ToolError("transaction_invalid",
                                "无活动日志且无终态回执；不推断续接，请用显式 rollback 关闭私有记录",
                                write_outcome="not_written")
            raise ToolError("transaction_invalid",
                            "无活动日志但发现 after 状态；证据不足，不自动续接",
                            write_outcome="not_written")
        if source_changed:
            raise ToolError("source_changed",
                            "恢复时输入或登记来源已变化；resume 拒绝，可显式 rollback 已知公共写入",
                            details={"current_revision": current_pointer(root)},
                            write_outcome="not_written")
        for item in _ordered_targets(targets):
            if item["actual"] == "before":
                _write_after_state(runtime, root, txn_dir, item)
        _active_log(root, transaction_id, plan["plan_sha256"], project_id, "verifying")
        pointer_after = _evidence_raw(txn_dir, "after", CURRENT_POINTER)
        member_items = [(item["path"], item["sha256"]) for item in new_packet["files"]]
        verification, _unknown = _readback_checks(
            runtime, binding, base, member_items=member_items,
            manifest_raw=new_manifest_raw, pointer_raw=pointer_after,
            new_revision=plan["version"]["new"], old_revision=plan["version"]["old"],
            expected_sources=plan["sources"])
        if not all(item["passed"] for item in verification):
            raise ToolError("saved_unverified",
                            "resume 写入完成但复读失败；保留事务，禁止盲目重试",
                            write_outcome="saved_unverified",
                            next_action="ui_inspect(target=transaction) 核对后选择 rollback")
        _active_log(root, transaction_id, plan["plan_sha256"], project_id, "committed")
        _finalize_accept_receipt(
            root, accept_receipt, plan=plan, packet=new_packet,
            manifest_raw=new_manifest_raw, changes=_plan_changes(plan),
            verification=verification, recovered_by=request_id)
        _remove_active_log(root)
        _write_recover_receipt(
            root, project_id=project_id, request_id=request_id, params_digest=params_digest,
            transaction_id=transaction_id, action=action, outcome="saved",
            transaction_status="resumed", current_revision=plan["version"]["new"],
            verification=verification)
        return _recovery_payload(
            binding, outcome="saved", action=action, transaction_status="resumed",
            request_id=request_id, transaction_id=transaction_id,
            current_revision=plan["version"]["new"], verification=verification,
            receipt_replay=False,
            next_action="resume 已完成原计划并复读；终态 saved 回执已补落盘")

    if not is_active and all(item["actual"] == "before" for item in targets):
        verification = [
            _check("document_set", "public", True, "公共目标仍全为 before，未发生写入"),
            _check("manifest", "public", True, "公共清单未修改"),
            _check("pointer", "public", True, "当前指针未修改"),
            _check("history", "private", True, "不可变版本证据保留"),
            _check("inputs", "project", not source_changed,
                   "输入来源未变化" if not source_changed else "输入来源已变化（私有关闭不触碰输入）"),
            _check("unknown_files", "public", True, "未知文件不清理"),
        ]
        _mark_accept_rolled_back(root, accept_receipt, plan, current_revision=None,
                                 recovered_by=request_id, public_writes=False)
        _write_recover_receipt(
            root, project_id=project_id, request_id=request_id, params_digest=params_digest,
            transaction_id=transaction_id, action=action, outcome="not_written",
            transaction_status="rolled_back", current_revision=current_pointer(root),
            verification=verification)
        return _recovery_payload(
            binding, outcome="not_written", action=action,
            transaction_status="rolled_back", request_id=request_id,
            transaction_id=transaction_id, current_revision=current_pointer(root),
            verification=verification, receipt_replay=False,
            next_action="活动日志落盘前的私有记录已关闭，公共字节未修改")

    for item in _ordered_targets(targets):
        if item["actual"] == "after":
            _write_before_state(runtime, root, txn_dir, item)
    old_revision = plan["version"]["old"]
    if old_revision is not None:
        old_loaded = load_version_meta(root, old_revision, full=True)
        old_packet = old_loaded["packet"]
        old_manifest_raw = (old_loaded["tree"] / MANIFEST_PATH).read_bytes()
        pointer_before = _evidence_raw(txn_dir, "before", CURRENT_POINTER)
        member_items = [(item["path"], item["sha256"]) for item in old_packet["files"]]
    else:
        old_packet = {"files": []}
        old_manifest_raw = None
        pointer_before = None
        member_items = []
    verification, _unknown = _readback_checks(
        runtime, binding, base, member_items=member_items,
        manifest_raw=old_manifest_raw, pointer_raw=pointer_before,
        new_revision=plan["version"]["new"], old_revision=old_revision,
        expected_sources=plan["sources"])
    if source_changed:
        verification = [dict(item, passed=False if item["code"] == "inputs" else item["passed"],
                             message="输入来源已变化；rollback 只恢复公共写入，不回退输入")
                      if item["code"] == "inputs" else item for item in verification]
    if not all(item["passed"] for item in verification if item["code"] != "inputs"):
        raise ToolError("saved_unverified",
                        "rollback 后复读失败；保留事务证据",
                        write_outcome="saved_unverified")
    _mark_accept_rolled_back(root, accept_receipt, plan,
                             current_revision=old_revision, recovered_by=request_id,
                             public_writes=True)
    _remove_active_log(root)
    _write_recover_receipt(
        root, project_id=project_id, request_id=request_id, params_digest=params_digest,
        transaction_id=transaction_id, action=action, outcome="saved",
        transaction_status="rolled_back", current_revision=old_revision,
        verification=verification)
    return _recovery_payload(
        binding, outcome="saved", action=action, transaction_status="rolled_back",
        request_id=request_id, transaction_id=transaction_id,
        current_revision=old_revision, verification=verification, receipt_replay=False,
        next_action="已按已知前像回滚公共目标；不可变历史与事务证据保留")


def _plan_changes(plan):
    added, modified, removed = [], [], list(plan["delete_paths"])
    for item in plan["targets"]:
        path = item["path"]
        if path in {MANIFEST_PATH, CURRENT_POINTER}:
            continue
        if item["before"]["state"] == "missing" and item["after"]["state"] == "present":
            added.append(path)
        elif item["after"]["state"] == "missing":
            if path not in removed:
                removed.append(path)
        elif item["before"]["state"] == "present" and item["after"]["state"] == "present" \
                and item["before"]["sha256"] != item["after"]["sha256"]:
            modified.append(path)
    return {"added": sorted(added), "modified": sorted(modified), "removed": sorted(removed)}


def _finalize_accept_receipt(root, accept_receipt, *, plan, packet, manifest_raw,
                             changes, verification, recovered_by):
    record = dict(accept_receipt or {})
    record.update({
        "schema_version": 1,
        "project_id": plan["project_id"],
        "operation": ACCEPT_OPERATION,
        "request_id": plan["request_id"],
        "status": "completed",
        "write_outcome": "saved",
        "revision_id": plan["revision_id"],
        "transaction_id": plan["transaction_id"],
        "version": plan["version"],
        "packet": packet,
        "sources": plan["sources"],
        "manifest_sha256": digest(manifest_raw),
        "changes": changes,
        "current_revision": plan["version"]["new"],
        "verification": verification,
        "recovered_by": recovered_by,
        "completed_at": _utc_now(),
    })
    _write_receipt(root, record)


def _mark_accept_rolled_back(root, accept_receipt, plan, *, current_revision,
                             recovered_by, public_writes):
    record = dict(accept_receipt or {})
    record.update({
        "schema_version": 1,
        "project_id": plan["project_id"],
        "operation": ACCEPT_OPERATION,
        "request_id": plan["request_id"],
        "status": "completed",
        "write_outcome": "not_written",
        "revision_id": plan["revision_id"],
        "transaction_id": plan["transaction_id"],
        "version": plan["version"],
        "current_revision": current_revision,
        "rolled_back_by": recovered_by,
        "public_writes_reverted": public_writes,
        "completed_at": _utc_now(),
    })
    _write_receipt(root, record)
