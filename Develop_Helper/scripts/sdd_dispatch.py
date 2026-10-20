#!/usr/bin/env python3
"""Read one tasks.json and report gate-aware dispatch candidates; never mutate or spawn."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


TASK_STATES = {"pending", "in_progress", "testing", "fixing", "passed", "blocked"}
GATE_STATES = {"pending", "awaiting_user", "changes_requested", "passed"}
EXECUTION_MODES = {"automatic", "step_by_step"}


def id_list(value: object) -> bool:
    return (isinstance(value, list) and all(isinstance(x, str) and x for x in value)
            and len(set(value)) == len(value))


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_execution(plan: dict, by_id: dict) -> list[str]:
    mode = plan.get("execution_mode", "automatic")  # Legacy plans retain their behavior.
    if not isinstance(mode, str) or mode not in EXECUTION_MODES:
        return ["execution_mode must be automatic or step_by_step"]
    if "step_gate" not in plan:
        return ["step_by_step requires step_gate"] if mode == "step_by_step" else []
    gate = plan["step_gate"]
    if not isinstance(gate, dict) or gate.get("kind") != "task_review":
        return ["step_gate must be a task_review object"]
    state = gate.get("status")
    if not isinstance(state, str) or state not in GATE_STATES:
        return ["invalid step_gate status"]
    if "task_id" not in gate or "user_confirmation" not in gate:
        return ["step_gate requires task_id and user_confirmation"]
    task_id, confirmation = gate["task_id"], gate["user_confirmation"]
    if task_id is None:
        return [] if state == "pending" and confirmation is None else ["empty step_gate must be pending without confirmation"]
    if not isinstance(task_id, str) or task_id not in by_id:
        return ["step_gate references an unknown task"]
    if state in {"passed", "awaiting_user"} and by_id[task_id].get("status") != "passed":
        return ["step_gate cannot await approval or pass before Tester PASS"]
    if state == "passed":
        return [] if nonempty(confirmation) else ["step_gate needs explicit user confirmation"]
    return [] if confirmation is None else ["unapproved step_gate must clear prior confirmation"]


def validate(plan: dict) -> list[str]:
    """Check dependencies, execution mode and gates; not business AC or source code."""
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or any(not isinstance(t, dict) for t in tasks):
        return ["tasks must be an array of objects"]
    ids = [t.get("id") for t in tasks]
    if not id_list(ids):
        return ["task IDs must be unique nonempty strings"]
    by_id = {t["id"]: t for t in tasks}
    errors = validate_execution(plan, by_id)
    for task in tasks:
        deps = task.get("dependencies", [])
        if not id_list(deps) or any(d not in by_id for d in deps):
            errors.append(f"{task['id']}: invalid dependencies")
    if errors:
        return errors
    remaining = set(ids)
    while remaining:
        ready = {i for i in remaining if not remaining.intersection(by_id[i].get("dependencies", []))}
        if not ready:
            return ["cyclic task dependencies"]
        remaining -= ready
    frontend = {t["id"] for t in tasks if t.get("type") == "frontend"}
    owners = [t for t in tasks if "user_gate" in t]
    if not frontend:
        return ["a frontend gate requires frontend tasks"] if owners else []
    if len(owners) != 1:
        return ["frontend plan requires exactly one user_gate on its final frontend task"]
    owner = owners[0]
    gate = owner["user_gate"]
    if owner["id"] not in frontend or not isinstance(gate, dict):
        return ["user_gate must be an object on a frontend task"]
    if gate.get("kind") != "frontend_mock_review":
        errors.append("unsupported gate kind")
    state = gate.get("status")
    if not isinstance(state, str) or state not in GATE_STATES:
        errors.append("invalid gate status")
    covered = gate.get("frontend_task_ids")
    if not id_list(covered) or set(covered) != frontend:
        errors.append("gate must cover every frontend task including its owner")
    ancestors = set()
    queue = list(owner.get("dependencies", []))
    while queue:
        dep = queue.pop()
        if dep not in ancestors:
            ancestors.add(dep)
            queue.extend(by_id[dep].get("dependencies", []))
    if not (frontend - {owner["id"]}).issubset(ancestors):
        errors.append("gate owner must depend on all other frontend tasks")
    # A gate cannot wait for an integration task that itself waits for this gate.
    for task_id in frontend:
        queue = list(by_id[task_id].get("dependencies", []))
        seen = set()
        while queue:
            dep = queue.pop()
            if dep in seen:
                continue
            seen.add(dep)
            if by_id[dep].get("type") in {"integration", "delivery"}:
                errors.append(f"{task_id}: frontend gate depends on post-gate work")
                break
            queue.extend(by_id[dep].get("dependencies", []))
    services = plan.get("external_services", [])
    if (not isinstance(services, list) or any(not isinstance(s, dict) for s in services)
            or not id_list([s.get("name") for s in services])):
        return errors + ["external_services must have unique nonempty names"]
    service_map = {s["name"]: s for s in services}
    required = gate.get("required_services")
    if (not id_list(required) or any(s not in service_map for s in required)
            or not {s["name"] for s in services if s.get("required") is True}.issubset(required)):
        errors.append("gate required_services must reference and cover required external services")
    rework = gate.get("rework_task_ids")
    if not id_list(rework) or not set(rework).issubset(frontend):
        errors.append("gate rework_task_ids must be frontend IDs")
    elif state == "changes_requested" and not rework:
        errors.append("changes_requested requires explicit rework_task_ids")
    for key in ("user_confirmation", "configuration_confirmation"):
        if key not in gate or (gate[key] is not None and not nonempty(gate[key])):
            errors.append(f"{key} must be null or a nonempty evidence summary")
    if state == "changes_requested" and gate.get("user_confirmation") is not None:
        errors.append("rework must clear prior user confirmation")
    if state == "passed":
        if not all(by_id[i].get("status") == "passed" for i in frontend):
            errors.append("gate cannot pass before all frontend tasks pass")
        if not all(nonempty(gate.get(key)) for key in ("user_confirmation", "configuration_confirmation")):
            errors.append("gate needs explicit user and configuration confirmations")
        if id_list(required) and any(service_map.get(s, {}).get("status") != "confirmed" for s in required):
            errors.append("gate cannot pass with missing or fallback required services")
        if rework:
            errors.append("passed gate must clear rework_task_ids")
    return errors


def evaluate(plan: dict, running_task_ids: list[str] | None = None) -> dict:
    errors = validate(plan)
    for task in plan.get("tasks", []) if isinstance(plan.get("tasks"), list) else []:
        if isinstance(task, dict) and (not isinstance(task.get("status"), str) or task["status"] not in TASK_STATES):
            errors.append(f"{task.get('id')}: invalid task status")
    running_task_ids = [] if running_task_ids is None else running_task_ids
    task_ids = {t.get("id") for t in plan.get("tasks", []) if isinstance(t, dict) and isinstance(t.get("id"), str)} if isinstance(plan.get("tasks"), list) else set()
    if not id_list(running_task_ids) or any(i not in task_ids for i in running_task_ids):
        errors.append("running task IDs must be unique and exist in the plan")
    if errors:
        return {"gate_phase": "invalid", "developer_ready": [], "tester_ready": [], "errors": errors}
    tasks = plan["tasks"]
    by_id = {t["id"]: t for t in tasks}
    owner = next((t for t in tasks if "user_gate" in t), None)
    phase = "not_applicable"
    allowed_ids = set(by_id)
    if owner:
        gate = owner["user_gate"]
        all_passed = all(by_id[i]["status"] == "passed" for i in gate["frontend_task_ids"])
        if gate["status"] == "passed":
            phase = "passed"
        elif gate["status"] == "changes_requested" and not all_passed:
            phase = "changes_requested"
            allowed_ids = set(gate["rework_task_ids"])
        elif all_passed or gate["status"] == "awaiting_user":
            phase = "awaiting_user"
            allowed_ids = set()
        else:
            phase = "frontend_in_progress"
            allowed_ids = {t["id"] for t in tasks if t.get("type") in {"frontend", "backend"}}
    def ready(task: dict) -> bool:
        return task["id"] in allowed_ids and all(by_id[d]["status"] == "passed" for d in task.get("dependencies", []))
    ordered = sorted(tasks, key=lambda t: t.get("priority", 999) if isinstance(t.get("priority", 999), (int, float)) else 999)
    developer_ready = [t["id"] for t in ordered if ready(t) and t["status"] in {"pending", "fixing"}]
    tester_ready = [t["id"] for t in ordered if ready(t) and t["status"] == "testing"]
    mode = plan.get("execution_mode", "automatic")
    step = plan.get("step_gate") or {}
    current = step.get("task_id")
    step_phase, selected = "not_applicable", None
    running = set(running_task_ids) | {t["id"] for t in tasks if t["status"] == "in_progress"}
    # A rejected task remains restricted even after switching to automatic mode.
    restricted = mode == "step_by_step" or step.get("status") == "changes_requested"
    if restricted:
        if current and step["status"] != "passed":
            selected = current
            status = by_id[current]["status"]
            if running - {current}:
                step_phase = "draining"
            elif status == "passed" or step["status"] == "awaiting_user":
                step_phase = "awaiting_user"
            elif status == "blocked":
                step_phase = "blocked"
            else:
                step_phase = "in_progress" if current in running else "current_task"
        elif running:
            step_phase = "draining"
        else:
            # Finish already implemented work before starting another Developer.
            candidates = tester_ready + developer_ready
            selected = candidates[0] if candidates else None
            step_phase = "ready" if selected else ("complete" if all(t["status"] == "passed" for t in tasks) else "blocked")
        if step_phase in {"draining", "awaiting_user", "blocked", "complete", "in_progress"}:
            developer_ready, tester_ready = [], []
        else:
            developer_ready = [i for i in developer_ready if i == selected]
            tester_ready = [i for i in tester_ready if i == selected]
    # Never re-dispatch a live Tester (whose task is still marked testing).
    developer_ready = [i for i in developer_ready if i not in running]
    tester_ready = [i for i in tester_ready if i not in running]
    reason = "Candidates only; check live agents, file/resource conflicts and authorization before dispatch."
    if phase == "awaiting_user":
        reason = "Waiting for frontend Mock approval and backend configuration; do not dispatch."
    elif step_phase == "awaiting_user":
        reason = "Waiting for user approval of the current task; do not dispatch."
    elif step_phase == "draining":
        reason = "Let live agents finish their current scope; do not dispatch until they return."
    elif step_phase == "ready":
        reason = "Reserve step_gate.task_id for this single candidate before dispatch; recheck after writing."
    return {
        "execution_mode": mode,
        "step_phase": step_phase,
        "step_task_id": selected,
        "gate_phase": phase,
        "gate_task_id": owner["id"] if owner else None,
        "developer_ready": developer_ready,
        "tester_ready": tester_ready,
        "in_flight_or_queued": [t["id"] for t in tasks if t["status"] in {"in_progress", "testing", "fixing"}],
        "reason": reason,
        "scope": "Read-only task/gate checks; no credentials, source code or real API validation.",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--running-task", action="append", default=[], help="Live Developer/Tester task ID; repeat for each running task")
    args = parser.parse_args()
    try:
        plan = json.loads(args.tasks.read_text(encoding="utf-8"))
        result = evaluate(plan, args.running_task) if isinstance(plan, dict) else {"errors": ["plan must be an object"]}
    except (OSError, ValueError) as error:
        result = {"errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
