"""Read-only recovery materials for one fixed project directory.

Reads the project's own files, then checks PRD confirmations with the local
read-only record validators bound to that directory. Never creates missing
documents, writes confirmations, registers, sends messages or starts downstream
work. Multiple files are not an atomic snapshot.
"""

import hashlib
import json
from pathlib import Path
import re

if __package__:
    from . import project_info
    from .requirements import read_document, safe_path
else:
    import project_info
    from requirements import read_document, safe_path

PROJECT_PATH = "project.json"
REQUIREMENTS_PATH = "docs/requirements.md"
PRD_PATH = "docs/PRD.md"
SOLUTION_PATHS = ("docs/solution.md", "docs/tech-spec.md")
DECISIONS_PATH = "docs/decisions.md"
SOLUTION_PURPOSE = "形成技术方案"
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SHA256 = re.compile(r"[0-9a-f]{64}")


def _read(root, relative):
    try:
        document = read_document(root, relative)
    except (OSError, ValueError) as error:
        return {"path": relative, "status": "unreadable", "sha256": None, "content": None, "error": str(error)}
    status = "missing" if document["content"] is None else "present"
    return {**document, "status": status}


def _version(root, relative):
    try:
        path = safe_path(root, relative)
        if not path.exists():
            return "missing"
        if not path.is_file() or path.stat().st_nlink != 1:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def _front_matter(content):
    match = FRONT_MATTER.match(content or "")
    if match is None:
        return None
    values = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _bound_sha(document, key):
    """Return (recorded, value); a malformed binding marks the document invalid."""
    values = _front_matter(document["content"])
    if values is None or key not in values:
        return False, None
    value = values[key]
    if value != "missing" and SHA256.fullmatch(value) is None:
        document.update(status="invalid", error=f"{key} 不是有效摘要")
        return True, None
    return True, value


def _project(root):
    document = _read(root, PROJECT_PATH)
    if document["status"] != "present":
        return document, {}
    try:
        data = json.loads(document["content"])
        if not isinstance(data, dict):
            raise ValueError("project.json 必须是对象")
    except ValueError as error:
        return {**document, "status": "invalid", "error": str(error)}, {}
    return {"path": PROJECT_PATH, "status": "present", "sha256": document["sha256"],
            "project_info": project_info.report(data), "artifacts": data.get("artifacts")}, data


def load_validators():
    """Return the local read-only record validators (confirmations, artifact registry)."""
    if __package__:
        from . import artifact_records, confirmation_records
    else:
        import artifact_records
        import confirmation_records
    return confirmation_records, artifact_records


def verify_prd_confirmation(foundation, root, project_id, data, prd_sha):
    """Classify confirmations of the current PRD for forming a technical solution.

    foundation is kept for caller compatibility; validators are local and never
    loaded from it.
    """
    result = {"status": "missing", "reasons": [], "records": [], "current_prd_sha256": prd_sha,
              "required_permitted_use": SOLUTION_PURPOSE, "confirmation_written": False,
              "downstream_started": False}
    if prd_sha in (None, "missing"):
        result["reasons"].append("prd_missing" if prd_sha == "missing" else "prd_unreadable")
        return result
    try:
        collaboration, artifacts = load_validators()
    except Exception as error:  # Any import failure means the capability is unavailable.
        return {**result, "status": "unavailable", "reasons": ["validator_unavailable"],
                "error": f"{type(error).__name__}: {error}"}
    try:
        _, decisions, decisions_sha = collaboration.read_decisions(root)
    except (OSError, ValueError) as error:
        return {**result, "status": "invalid", "reasons": ["decisions_invalid"], "error": str(error)}
    result["decisions_sha256"] = decisions_sha
    if decisions_sha == "missing":
        result["reasons"].append("decisions_missing")
        return result
    try:
        registry, _ = artifacts.validate_registry(root, data)
        registry_error = None
    except (OSError, ValueError) as error:
        registry, registry_error = None, str(error)
    for record in decisions["confirmations"]:
        artifact = record["artifact"]
        if artifact["kind"] != "requirements":
            continue
        version = None
        if registry is not None:
            try:
                _, version = collaboration.artifact_version(registry, artifact["artifact_id"], artifact["version"])
            except ValueError:
                version = None
        content = version["content"] if version else None
        targets_prd = (artifact["content_sha256"] == prd_sha or artifact.get("registered_path") == PRD_PATH
                       or (isinstance(content, dict) and content.get("type") == "file"
                           and content.get("path") == PRD_PATH))
        if not targets_prd:
            continue
        entry = {"confirmation_id": record["confirmation_id"], "artifact_id": artifact["artifact_id"],
                 "version": artifact["version"], "content_sha256": artifact["content_sha256"], "reasons": []}
        result["records"].append(entry)
        if record.get("project_id") != project_id:
            entry.update(result="ignored", reasons=["other_project"])
            continue
        if record["permitted_use"] != SOLUTION_PURPOSE:
            entry.update(result="ignored", reasons=["purpose_mismatch"])
            continue
        reasons = []
        if record["open_items"]:
            reasons.append("open_items_pending")
        if registry_error is not None:
            reasons.append("registry_invalid")
        elif version is None:
            reasons.append("not_registered")
        elif (record["confirmation_id"] not in version["confirmation_ids"]
              or artifacts.content_sha(version["content"]) != artifact["content_sha256"]):
            reasons.append("registry_mismatch")
        try:
            collaboration.validate_snapshot(root, record)
        except (OSError, ValueError):
            reasons.append("snapshot_mismatch")
        if reasons:
            entry.update(result="invalid", reasons=reasons)
        elif artifact["content_sha256"] == prd_sha:
            entry["result"] = "valid"
        else:
            entry.update(result="outdated", reasons=["prd_changed"])
    outcomes = {entry["result"] for entry in result["records"]}
    for status in ("valid", "outdated", "invalid"):
        if status in outcomes:
            result["status"] = status
            break
    else:
        result["reasons"] = sorted({reason for entry in result["records"] for reason in entry["reasons"]}) or [
            "no_matching_record"]
    return result


def read(foundation, root, project_id, base_versions=None):
    """Collect recovery materials; base_versions are the four-file read used for read_id."""
    root = Path(root)
    project, data = _project(root)
    requirements = _read(root, REQUIREMENTS_PATH)
    prd = _read(root, PRD_PATH)
    recorded, value = _bound_sha(prd, "source_requirements_sha256")
    prd_source = {"recorded": recorded, "requirements_sha256": value,
                  "matches_current": None if value is None else value == requirements["sha256"]}
    solutions = []
    for path in SOLUTION_PATHS:
        document = _read(root, path)
        recorded, value = _bound_sha(document, "prd_sha256")
        solutions.append({**document, "prd_binding": {
            "recorded": recorded, "prd_sha256": value,
            "matches_current": None if value is None else value == prd["sha256"]}})
    if project["status"] == "present" and prd["status"] in ("present", "missing"):
        confirmations = verify_prd_confirmation(foundation, root, project_id, data, prd["sha256"])
    else:
        confirmations = {"status": "unavailable", "reasons": ["inputs_unreadable"], "records": [],
                         "confirmation_written": False, "downstream_started": False}
    versions = {PROJECT_PATH: project["sha256"], REQUIREMENTS_PATH: requirements["sha256"],
                PRD_PATH: prd["sha256"], **{item["path"]: item["sha256"] for item in solutions}}
    versions[DECISIONS_PATH] = confirmations.get("decisions_sha256")
    after = {path: _version(root, path) for path in versions}
    changed = sorted(path for path, sha in versions.items()
                     if after[path] != sha and not (path == DECISIONS_PATH and sha is None))
    changed += sorted(path for path, sha in (base_versions or {}).items()
                      if path in versions and versions[path] != sha and path not in changed)
    for document in (requirements, prd):
        document.pop("content", None)
    return {"atomic_snapshot": False, "read_versions": versions, "changed_during_read": changed,
            "project": project, "requirements": requirements,
            "prd": {**prd, "source": prd_source}, "solutions": solutions,
            "confirmations": confirmations, "consumes_read_id": False}
