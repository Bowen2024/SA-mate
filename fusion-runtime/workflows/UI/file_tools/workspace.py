"""Candidate workspaces, import mapping and candidate inspection (step 5B).

Writes happen only inside the project's private ``ui/.ui-state`` tree. Public
collection members, manifests and pointers are never modified here; 5C adds the
controlled accept path. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .context import (
    CONTRACT_VERSION,
    CACHE_NAMES,
    DEFAULT_ARTIFACT_ROOT,
    DESIGN_PATH,
    MANIFEST_PATH,
    MAX_COLLECTION_BYTES,
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_MEMBERS,
    MAX_WORKSPACES,
    REQUESTS_DIR,
    WORK_DIR,
    Closure,
    ToolError,
    canonical_sha,
    digest,
    detect_current,
    import_mapping_view,
    resolve_project_path,
    validate_import_spec,
    validate_member_path,
)
from .versions import load_version_meta

REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
REVISION_ID_RE = re.compile(r"^R-[0-9a-f]{32}$")

JOURNAL_NAME = ".project-state-transaction.json"
PREPARE_OPERATION = "ui_prepare_revision"
ACCEPT_OPERATION = "ui_accept_revision"


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_private(path, raw)


def _atomic_private(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _check(code, scope, passed, message, *, paths=None, checked=True):
    return {"code": code, "scope": scope, "checked": checked, "passed": passed,
            "paths": paths or [], "message": message}


def _issue(code, paths, message, *, scope="candidate"):
    return {"code": code, "scope": scope, "checked": True, "passed": False,
            "paths": paths or [], "message": message}


def _prepare_params_digest(project_path, mode, history_revision):
    return canonical_sha({
        "operation": PREPARE_OPERATION,
        "project_path": project_path,
        "mode": mode,
        "history_revision": history_revision,
    })


def _receipt_path(root: Path, request_id: str) -> Path:
    return root / REQUESTS_DIR / f"{request_id}.json"


def _load_receipt(root: Path, request_id: str):
    path = _receipt_path(root, request_id)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ToolError("receipt_invalid", "持久回执不是独立普通文件")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("receipt_invalid", f"持久回执损坏：{request_id}",
                        details={"reason": str(error)}) from error
    required = {"schema_version", "project_id", "operation", "request_id",
                "params_digest", "status", "revision_id"}
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1 \
            or not required <= set(receipt):
        raise ToolError("receipt_invalid", f"持久回执结构不受支持：{request_id}")
    return receipt


def _accept_closed_revisions(root: Path):
    """Revision ids with a terminal accept receipt (5C writes them)."""
    closed = set()
    directory = root / REQUESTS_DIR
    if not directory.is_dir():
        return closed
    for path in directory.glob("*.json"):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(receipt, dict) and receipt.get("status") == "completed" \
                and receipt.get("operation") == ACCEPT_OPERATION:
            revision_id = receipt.get("revision_id")
            if isinstance(revision_id, str) and REVISION_ID_RE.match(revision_id):
                closed.add(revision_id)
    return closed


def _open_workspaces(root: Path):
    work = root / WORK_DIR
    if not work.is_dir():
        return set()
    closed = _accept_closed_revisions(root)
    return {
        child.name
        for child in work.iterdir()
        if child.is_dir() and not child.is_symlink()
        and REVISION_ID_RE.match(child.name) and child.name not in closed
    }


def _descriptor_views(closure):
    """Split closure descriptors into packet sources and protected targets."""
    sources = []
    targets = []
    for descriptor in closure.finalized_descriptors():
        roles = set(descriptor.get("role", "").split("|"))
        if descriptor["scope"] == "import" or "input" in roles:
            sources.append({
                "source_key": descriptor["key"],
                "state": descriptor["state"],
                "sha256": descriptor["sha256"],
            })
        if roles & {"current", "control", "registry_reference"} or descriptor["kind"] == "directory":
            target = {
                "key": descriptor["key"],
                "kind": descriptor["kind"],
                "state": descriptor["state"],
                "sha256": descriptor["sha256"],
            }
            if descriptor["kind"] == "directory":
                target["entries"] = descriptor.get("entries", [])
            targets.append(target)
    sources.sort(key=lambda item: item["source_key"])
    targets.sort(key=lambda item: item["key"])
    return sources, targets


def _history_pair(root):
    from .context import _history_summaries

    return _history_summaries(root)


def _rebuild_views(runtime, binding, artifact_root, source_paths, import_spec, current):
    summaries, history_error = _history_pair(binding["root"])
    closure = Closure(runtime, binding, artifact_root, source_paths, import_spec)
    closure.collect(binding["data"], current, summaries, history_error,
                    include_contents=False)
    sources, targets = _descriptor_views(closure)
    return closure.descriptor_digest(), sources, targets, history_error


def _candidate_digest(base_digest, candidate, members):
    return canonical_sha({
        "base_digest": base_digest,
        "candidate": candidate,
        "members": members,
    })


def _load_base(root: Path, revision_id: str):
    work_root = root / WORK_DIR / revision_id
    base_path = work_root / "base.json"
    if not work_root.is_dir() or work_root.is_symlink():
        raise ToolError("invalid_arguments", "revision_id 对应的候选工作区不存在或已结束")
    if base_path.is_symlink() or not base_path.is_file():
        raise ToolError("collection_invalid", "候选工作区缺少 base.json；不重建不可信基线")
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("collection_invalid", "base.json 不是有效 JSON") from error
    required = {"schema_version", "project", "revision_id", "request_id", "mode",
                "artifact_root", "restored_from", "prepared_at",
                "runtime_baseline_digest", "import", "source_paths", "sources",
                "current", "targets", "base_digest"}
    if not isinstance(base, dict) or not required <= set(base):
        raise ToolError("collection_invalid", "base.json 字段集合不符")
    recorded = base.pop("base_digest")
    if recorded != canonical_sha(base):
        raise ToolError("collection_invalid", "base_digest 与 base.json 内容不一致")
    base["base_digest"] = recorded
    return work_root, base


def _load_candidate(work_root: Path, artifact_root: str):
    candidate_path = work_root / "candidate.json"
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ToolError("collection_invalid", "候选缺少 candidate.json 声明")
    raw = candidate_path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ToolError("limit_exceeded", "candidate.json 超过 128 KiB")
    try:
        candidate = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolError("collection_invalid", "candidate.json 必须是 UTF-8 JSON") from error
    if not isinstance(candidate, dict) or set(candidate) != {"schema_version", "entrypoint", "files"} \
            or candidate.get("schema_version") != 1:
        raise ToolError("collection_invalid",
                        "candidate.json 只能包含 schema_version、entrypoint、files")
    entrypoint = candidate["entrypoint"]
    entrypoint_error = None
    if entrypoint is not None and not isinstance(entrypoint, str):
        raise ToolError("collection_invalid", "candidate.json entrypoint 必须为字符串或 null")
    files = candidate["files"]
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise ToolError("collection_invalid", "candidate.json files 必须是字符串数组")
    declared = []
    for item in files:
        try:
            declared.append(validate_member_path(item, artifact_root))
        except ToolError as error:
            raise ToolError("collection_invalid", f"候选声明路径非法：{item}（{error.code}）") from error
    entrypoint_raw = entrypoint
    if entrypoint is not None:
        try:
            entrypoint = validate_member_path(entrypoint, artifact_root)
        except ToolError as error:
            entrypoint_error = {"raw": entrypoint_raw, "code": error.code}
            entrypoint = None
    if len(set(declared)) != len(declared):
        raise ToolError("collection_invalid", "candidate.json files 含重复路径")
    candidate["entrypoint"] = entrypoint
    candidate["files"] = declared
    return candidate, entrypoint_error


def _scan_tree(work_root: Path):
    """Return {relative: (sha,size)} for regular files; raise on links/specials."""
    tree_root = work_root / "tree"
    actual = {}
    if not tree_root.exists():
        return actual
    if tree_root.is_symlink() or not tree_root.is_dir():
        raise ToolError("path_not_allowed", "候选 tree 必须是普通目录")
    for current, directories, files in os.walk(tree_root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            child = current_path / name
            if child.is_symlink():
                raise ToolError("path_not_allowed", f"候选 tree 含软链目录：{name}")
        for name in files:
            child = current_path / name
            relative = child.relative_to(tree_root).as_posix()
            if child.is_symlink() or child.stat().st_nlink != 1:
                raise ToolError("path_not_allowed", f"候选 tree 含软链或硬链：{relative}")
            if not child.is_file():
                raise ToolError("path_not_allowed", f"候选 tree 含非普通文件：{relative}")
            raw = child.read_bytes()
            actual[relative] = (digest(raw), len(raw))
    return actual


def _stored_import_view(spec):
    if spec is None:
        return None
    return {
        "root": spec["root"],
        "files": list(spec["files"]),
        "entrypoint": spec["entrypoint"],
        "design_path": spec["design_path"],
        "readme_path": spec["readme_path"],
        "mapping": dict(spec["mapping"]),
    }


def _import_spec_input(stored):
    return {key: stored[key] for key in
            ("root", "files", "entrypoint", "design_path", "readme_path")}


def _revalidate_import_spec(runtime, import_roots, record, artifact_root):
    stored = record.get("import_spec")
    if stored is None:
        return None
    if artifact_root != DEFAULT_ARTIFACT_ROOT:
        raise ToolError("invalid_arguments", "v1 导入映射仅支持默认 artifact_root")
    spec = validate_import_spec(runtime, _import_spec_input(stored), import_roots)
    if canonical_sha(import_mapping_view(spec)) != record["import_mapping_digest"]:
        raise ToolError("source_changed", "read_id 固定的导入映射与当前授权不一致")
    return spec


def prepare_revision(runtime, credentials, import_roots, *, binding_factory,
                     project_path, read_id, request_id, mode, history_revision, clock=None):
    del clock  # token expiry uses the credential manager's injected clock
    if not isinstance(project_path, str) or not project_path.strip():
        raise ToolError("invalid_arguments", "project_path 必须是非空字符串")
    if not isinstance(read_id, str) or not read_id:
        raise ToolError("invalid_arguments", "read_id 必须是非空字符串")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.match(request_id):
        raise ToolError("invalid_arguments", "request_id 必须是标准小写 UUID")
    if mode not in {"empty", "current", "import", "history"}:
        raise ToolError("invalid_arguments", "mode 必须是 empty、current、import 或 history")
    if mode == "history":
        if not isinstance(history_revision, str) or len(history_revision) != 64:
            raise ToolError("invalid_arguments", "mode=history 必须提供 64 位 history_revision")
    elif history_revision is not None:
        raise ToolError("invalid_arguments", "history_revision 只允许在 mode=history 时提供")

    binding = binding_factory(project_path)
    root = binding["root"]
    project_id = binding["project_id"]
    params_digest = _prepare_params_digest(str(root), mode, history_revision)

    project_state = runtime.modules.project_state
    if (root / JOURNAL_NAME).exists():
        raise ToolError(
            "main_transaction_pending",
            "项目根存在 Main 成果索引事务；UI 不接管，先由 Main 恢复",
        )
    lock = project_state.project_state_lock(root, "ui-prepare")
    try:
        lock.__enter__()
    except ValueError as error:
        raise ToolError("lock_busy", "项目状态写入锁已存在；先核对在途操作，不自动删除锁") from error
    try:
        from .transactions import active_transaction_id

        if active_transaction_id(root) is not None:
            raise ToolError(
                "operation_incomplete",
                "存在活动 UI 事务；先 ui_inspect(target=transaction) 核对并恢复，不开始新准备",
            )

        receipt = _load_receipt(root, request_id)
        if receipt is not None:
            if receipt.get("operation") != PREPARE_OPERATION:
                raise ToolError("request_reused", "request_id 已绑定其他操作")
            if receipt.get("project_id") != project_id \
                    or receipt.get("params_digest") != params_digest:
                raise ToolError("request_reused", "request_id 以不同参数复用")
            revision_id = receipt["revision_id"]
            if receipt.get("status") == "incomplete":
                raise ToolError(
                    "operation_incomplete",
                    "同一准备请求尚未完成；先核对残留工作区，再用新 request_id 重建",
                    details={"revision_id": revision_id,
                             "workspace_path": str(root / WORK_DIR / revision_id)})
            if receipt.get("status") != "completed":
                raise ToolError("receipt_invalid", "准备回执状态不受支持")
            work_root, base = _load_base(root, revision_id)
            return _prepared_payload(binding, base, receipt.get("candidate_digest"),
                                     revision_id, request_id, replay=True,
                                     tree_files=_tree_files(work_root))

        record = credentials.validate_read(read_id, project_path=str(root))
        artifact_root = record["artifact_root"]
        source_paths = record["source_paths"]
        import_spec = _revalidate_import_spec(runtime, import_roots, record, artifact_root)

        current = detect_current(runtime, root, artifact_root, project_id)
        if current["kind"] == "none" and current["unmanaged"]:
            raise ToolError("unmanaged_target_exists",
                            "目标位置存在未受管文件；不自动纳管或覆盖",
                            details={"paths": current["unmanaged"]})
        baseline_digest, sources, targets, history_error = _rebuild_views(
            runtime, binding, artifact_root, source_paths, import_spec, current)
        if baseline_digest != record["baseline_digest"]:
            raise ToolError("source_changed",
                            "读取基线已变化；差异需语义修订后重新读取，不以新凭证掩盖旧候选")
        if record["runtime_baseline_digest"] != canonical_sha(runtime.baseline):
            raise ToolError("runtime_baseline_changed",
                            "read_id 绑定的运行基线与当前服务不一致")
        if history_error:
            raise ToolError(history_error["code"], history_error["message"])

        restored_from = None
        history_loaded = None
        if mode == "empty":
            if current["kind"] != "none":
                raise ToolError("invalid_arguments",
                                "mode=empty 只允许在没有当前集合且目标清洁时使用")
            initial_members = []
            entrypoint = None
        elif mode == "current":
            if current["kind"] not in {"managed", "legacy"}:
                raise ToolError("invalid_arguments", "mode=current 需要合法当前集合")
            initial_members = [member["path"] for member in current["members"]]
            entrypoint = current["manifest"]["entrypoint"]
        elif mode == "import":
            if import_spec is None:
                raise ToolError("invalid_arguments", "该 read_id 未固定 import_source")
            initial_members = sorted(import_spec["mapping"].values())
            entrypoint = import_spec["mapping"][import_spec["entrypoint"]]
        else:
            history_loaded = load_version_meta(root, history_revision, full=True)
            packet = history_loaded["packet"]
            if packet["project_id"] != project_id:
                raise ToolError("history_invalid", "历史版本属于其他项目")
            if packet["artifact_root"] != artifact_root:
                raise ToolError("invalid_arguments",
                                "历史版本 artifact_root 与本次读取不一致；v1 不借恢复搬迁")
            initial_members = [item["path"] for item in packet["files"]]
            entrypoint = packet["entrypoint"]
            restored_from = history_revision

        if len(_open_workspaces(root)) >= MAX_WORKSPACES:
            raise ToolError("workspace_limit",
                            f"每项目未结束候选达到 {MAX_WORKSPACES} 个上限；不自动删除候选",
                            next_action="先由操作者核对并处理孤立试验工作区")

        credentials.consume_read(read_id, project_path=str(root))
        revision_id = "R-" + secrets.token_hex(16)
        work_root = root / WORK_DIR / revision_id
        work_root.mkdir(parents=True, exist_ok=False)

        descriptor_index = None
        if mode != "empty":
            closure = Closure(runtime, binding, artifact_root, source_paths, import_spec)
            closure.collect(binding["data"], current, *_history_pair(root),
                            include_contents=False)
            descriptor_index = closure.descriptor_index()

        manifest_sha = None
        manifest_descriptor = next((item for item in targets
                                    if item["key"] == f"project:{MANIFEST_PATH}"), None)
        if manifest_descriptor and manifest_descriptor["state"] == "present":
            manifest_sha = manifest_descriptor["sha256"]

        base = {
            "schema_version": 1,
            "project": {"project_id": project_id, "project_path": str(root)},
            "revision_id": revision_id,
            "request_id": request_id,
            "mode": mode,
            "artifact_root": artifact_root,
            "restored_from": restored_from,
            "prepared_at": _utc_now(),
            "runtime_baseline_digest": record["runtime_baseline_digest"],
            "import": _stored_import_view(import_spec),
            "source_paths": list(source_paths),
            "sources": sources,
            "current": {
                "kind": current["kind"],
                "revision_sha256": current["revision_sha256"],
                "manifest_sha256": manifest_sha,
                "members": [dict(member) for member in current["members"]],
            },
            "targets": targets,
        }
        base["base_digest"] = canonical_sha(base)

        receipt_incomplete = {
            "schema_version": 1,
            "project_id": project_id,
            "operation": PREPARE_OPERATION,
            "request_id": request_id,
            "params_digest": params_digest,
            "status": "incomplete",
            "write_outcome": None,
            "revision_id": revision_id,
            "workspace_path": str(work_root),
            "base_digest": base["base_digest"],
            "candidate_digest": None,
            "created_at": _utc_now(),
        }
        _write_json(work_root / "base.json", base)
        _write_json(_receipt_path(root, request_id), receipt_incomplete)

        try:
            if mode in {"current", "import", "history"}:
                _copy_initial_members(mode, work_root, root, import_spec,
                                      history_loaded, initial_members, descriptor_index)
        except ToolError:
            raise
        except OSError as error:
            raise ToolError("io_error", f"候选复制失败，残留保留在工作区：{error}",
                            details={"workspace_path": str(work_root)},
                            write_outcome="not_written") from error

        candidate = {"schema_version": 1, "entrypoint": entrypoint,
                     "files": sorted(initial_members)}
        _write_json(work_root / "candidate.json", candidate)
        member_map = _scan_tree(work_root)
        member_pairs = [[path, member_map[path][0]] for path in sorted(member_map)]
        candidate_digest = _candidate_digest(base["base_digest"], candidate, member_pairs)

        receipt_completed = dict(receipt_incomplete)
        receipt_completed.update({
            "status": "completed",
            "write_outcome": "prepared",
            "candidate_digest": candidate_digest,
            "completed_at": _utc_now(),
        })
        _write_json(_receipt_path(root, request_id), receipt_completed)

        return _prepared_payload(binding, base, candidate_digest, revision_id,
                                 request_id, replay=False, tree_files=_tree_files(work_root))
    finally:
        lock.__exit__(None, None, None)


def _copy_initial_members(mode, work_root, project_root, import_spec,
                          history_loaded, members, descriptor_index):
    tree_root = work_root / "tree"
    for relative in members:
        if mode == "import":
            source_rel = next(key for key, target in import_spec["mapping"].items()
                              if target == relative)
            source = import_spec["root_path"] / source_rel
            expected_key = f"import:{import_spec['root']}:{source_rel}"
        elif mode == "history":
            source = history_loaded["tree"] / relative
            expected_key = None
        else:
            source = resolve_project_path(project_root, relative)
            expected_key = f"project:{relative}"
        if source.is_symlink() or not source.is_file() or source.stat().st_nlink != 1:
            raise ToolError("io_error", f"初始成员不是独立普通文件：{relative}")
        raw = source.read_bytes()
        if expected_key is not None:
            descriptor = descriptor_index.get(expected_key)
            if descriptor is None or descriptor.get("sha256") != digest(raw):
                raise ToolError("source_changed", f"准备复制时来源已变化：{relative}")
        destination = tree_root / relative
        _atomic_private(destination, raw)


def _tree_files(work_root: Path):
    tree_root = work_root / "tree"
    files = []
    if tree_root.is_dir():
        for current, _dirs, names in os.walk(tree_root, followlinks=False):
            for name in names:
                child = Path(current) / name
                if not child.is_symlink() and child.is_file():
                    files.append(child)
    return sorted([work_root / "candidate.json", *files])


def _prepared_payload(binding, base, candidate_digest, revision_id, request_id, *,
                      replay, tree_files):
    work_root = binding["root"] / WORK_DIR / revision_id
    editable_paths = [str(work_root / "tree"), *[str(path) for path in tree_files]]
    return {
        "contract_version": CONTRACT_VERSION,
        "operation": PREPARE_OPERATION,
        "project": binding["project"],
        "state": "prepared",
        "diagnostics": [],
        "checks": [
            _check("runtime_baseline", "service", True, "运行基线核对通过"),
            _check("read_baseline", "project", True, "读取闭包与 read_id 基线一致"),
            _check("public_collection", "project", True, "公共成果、清单与指针未修改"),
        ],
        "write_outcome": "prepared",
        "request_id": request_id,
        "revision_id": revision_id,
        "transaction_id": None,
        "revision_sha256": None,
        "verification": None,
        "receipt_replay": replay,
        "error": None,
        "workspace_path": str(work_root),
        "editable_paths": editable_paths,
        "base_digest": base["base_digest"],
        "candidate_digest": candidate_digest,
        "mode": base["mode"],
        "artifact_root": base["artifact_root"],
        "restored_from": base["restored_from"],
        "next_action": "用普通编辑工具只修改候选 tree 与 candidate.json，再调用 ui_inspect(target=candidate)",
    }


def _rebuild_import_spec(runtime, stored):
    if stored is None:
        return None
    return validate_import_spec(runtime, _import_spec_input(stored), [stored["root"]])


def evaluate_candidate(runtime, binding, base, work_root, *, closed):
    """Re-validate a prepared workspace against current facts.

    Shared by ui_inspect(candidate) (5B) and ui_accept_revision (5C) so the
    accept path can never diverge from the inspection contract.
    """
    root = binding["root"]
    project_id = binding["project_id"]
    artifact_root = base["artifact_root"]

    if base["runtime_baseline_digest"] != canonical_sha(runtime.baseline):
        raise ToolError("runtime_baseline_changed", "候选准备时的运行基线与当前服务不一致")
    current = detect_current(runtime, root, artifact_root, project_id)
    import_spec = _rebuild_import_spec(runtime, base.get("import"))
    _baseline_digest, sources, targets, _history_error = _rebuild_views(
        runtime, binding, artifact_root, base["source_paths"], import_spec, current)
    if not closed and sources != base["sources"]:
        raise ToolError("source_changed",
                        "准备后的输入或导入来源发生变化；请基于当前来源重新准备候选")
    if not closed and targets != base["targets"]:
        raise ToolError("target_changed",
                        "准备后的当前成果、清单、指针或目录清单发生变化")

    candidate, entrypoint_error = _load_candidate(work_root, artifact_root)
    actual = _scan_tree(work_root)
    issues = []
    if entrypoint_error is not None:
        issues.append(_issue("collection_invalid", [entrypoint_error["raw"]],
                             "候选 entrypoint 不是合法的项目内成员路径："
                             + entrypoint_error["raw"]))

    declared = set(candidate["files"])
    present = set(actual)
    for relative in sorted(declared - present):
        issues.append(_issue("collection_invalid", [relative], f"声明成员缺失：{relative}"))
    for relative in sorted(present - declared):
        if Path(relative).name in CACHE_NAMES:
            continue
        issues.append(_issue("unlisted_file", [relative],
                             "tree 中存在未在 candidate.json 声明的普通文件：" + relative))

    total_bytes = 0
    for relative in sorted(present & declared):
        _sha, size = actual[relative]
        if size > MAX_FILE_BYTES:
            issues.append(_issue("limit_exceeded", [relative],
                                 f"成员超过单文件 32 MiB：{relative}"))
        total_bytes += size
    member_count = len(declared)
    if member_count > MAX_MEMBERS:
        issues.append(_issue("limit_exceeded", sorted(declared),
                             f"候选成员超过 {MAX_MEMBERS} 个上限"))
    if total_bytes > MAX_COLLECTION_BYTES:
        issues.append(_issue("limit_exceeded", [], "候选集合字节总量超过 64 MiB"))

    entrypoint = candidate["entrypoint"]
    if entrypoint is None:
        issues.append(_issue("candidate_incomplete", [], "candidate.json 尚未声明 entrypoint"))
    else:
        if entrypoint not in declared:
            issues.append(_issue("collection_invalid", [entrypoint], "entrypoint 未列入 files"))
        elif not entrypoint.endswith(".html"):
            issues.append(_issue("collection_invalid", [entrypoint], "entrypoint 必须是 .html 文件"))

    design_present = DESIGN_PATH in declared and DESIGN_PATH in present
    if not design_present:
        issues.append(_issue("candidate_incomplete", [DESIGN_PATH],
                             "完整候选必须包含设计说明 docs/ui-style.md"))
    readme_path = f"{artifact_root}/README.md"
    readme_present = readme_path in declared and readme_path in present
    if not readme_present:
        issues.append(_issue("candidate_incomplete", [readme_path],
                             "完整候选必须包含演示 README（不是项目根 README）"))

    base_members = {item["path"]: item["sha256"] for item in base["current"]["members"]}
    candidate_members = {path: actual[path][0] for path in sorted(present & declared)}
    added = sorted(path for path in candidate_members if path not in base_members)
    removed = sorted(path for path in base_members if path not in candidate_members)
    modified = sorted(path for path in candidate_members
                      if path in base_members and candidate_members[path] != base_members[path])
    changes = {"added": added, "modified": modified, "removed": removed}

    packet = {
        "schema_version": 1,
        "project_id": project_id,
        "artifact_root": artifact_root,
        "entrypoint": entrypoint,
        "design_path": DESIGN_PATH,
        "readme_path": readme_path,
        "files": [{"path": path, "sha256": candidate_members[path]}
                  for path in sorted(candidate_members)],
        "sources": sources,
        "restored_from": base["restored_from"],
    }
    proposed_revision_sha256 = canonical_sha(packet)
    member_pairs = [[path, candidate_members[path]] for path in sorted(candidate_members)]
    candidate_digest = _candidate_digest(base["base_digest"], candidate, member_pairs)

    if closed:
        issues.append(_issue("candidate_closed", [],
                             "该工作区已有终态接收回执，只读关闭；继续修改请重新 prepare",
                             scope="workspace"))
    return {
        "artifact_root": artifact_root,
        "current": current,
        "import_spec": import_spec,
        "sources": sources,
        "targets": targets,
        "candidate": candidate,
        "actual": actual,
        "issues": issues,
        "member_count": member_count,
        "total_bytes": total_bytes,
        "design_present": design_present,
        "readme_present": readme_present,
        "readme_path": readme_path,
        "base_members": base_members,
        "candidate_members": candidate_members,
        "changes": changes,
        "packet": packet,
        "proposed_revision_sha256": proposed_revision_sha256,
        "candidate_digest": candidate_digest,
        "ready": not issues and not closed,
    }


def inspect_candidate(runtime, credentials, binding, *, revision_id, clock=None):
    del clock
    if not isinstance(revision_id, str) or not REVISION_ID_RE.match(revision_id):
        raise ToolError("invalid_arguments", "revision_id 必须是 R- 加 32 位小写十六进制")
    root = binding["root"]
    project_id = binding["project_id"]

    closed = revision_id in _accept_closed_revisions(root)
    work_root, base = _load_base(root, revision_id)
    if base["project"]["project_id"] != project_id:
        raise ToolError("transaction_invalid", "候选工作区绑定了其他项目")
    evaluation = evaluate_candidate(runtime, binding, base, work_root, closed=closed)
    artifact_root = evaluation["artifact_root"]
    issues = evaluation["issues"]
    member_count = evaluation["member_count"]
    total_bytes = evaluation["total_bytes"]
    design_present = evaluation["design_present"]
    readme_present = evaluation["readme_present"]
    candidate_members = evaluation["candidate_members"]
    changes = evaluation["changes"]
    removed = changes["removed"]
    entrypoint = evaluation["candidate"]["entrypoint"]
    proposed_revision_sha256 = evaluation["proposed_revision_sha256"]
    candidate_digest = evaluation["candidate_digest"]
    ready = evaluation["ready"]
    sources = evaluation["sources"]
    targets = evaluation["targets"]
    inspection_id = None
    if ready:
        inspection_id = credentials.issue_inspect(
            project_path=str(root), revision_id=revision_id, artifact_root=artifact_root,
            removed=removed, base_digest=base["base_digest"],
            candidate_digest=candidate_digest,
            runtime_baseline_digest=canonical_sha(runtime.baseline))

    state = "candidate_closed" if closed else ("candidate_ready" if ready
                                               else "candidate_incomplete")

    diagnostics = [{
        "code": "browser_evidence_unverified",
        "paths": [],
        "message": "检查只核对文件结构、成员、入口、设计、README 与来源；不执行 HTML/JS，浏览器证据未验证",
    }]
    checks = [
        _check("candidate_declaration", "candidate", not any(
            issue["code"] in {"collection_invalid", "unlisted_file"} for issue in issues),
            "声明与实际 tree 一致"),
        _check("member_limits", "candidate", not (
            member_count > MAX_MEMBERS or total_bytes > MAX_COLLECTION_BYTES),
            "成员数量与集合字节限额"),
        _check("required_members", "candidate",
               design_present and readme_present and entrypoint in candidate_members,
               "入口、设计说明与演示 README 齐备"),
        _check("sources_current", "project",
               sources == base["sources"] and targets == base["targets"],
               "准备后的来源与当前目标未变化"),
        {"code": "browser_evidence", "scope": "candidate", "checked": False,
         "passed": None, "paths": [], "message": "浏览器实测不在文件检查范围"},
    ]

    return {
        "contract_version": CONTRACT_VERSION,
        "operation": "ui_inspect",
        "project": binding["project"],
        "state": state,
        "issues": issues,
        "verification_scope": checks,
        "inspection_id": inspection_id,
        "candidate_digest": candidate_digest,
        "base_digest": base["base_digest"],
        "proposed_revision_sha256": proposed_revision_sha256,
        "changes": changes,
        "transaction": None,
        "diagnostics": diagnostics,
        "checks": checks,
    }
