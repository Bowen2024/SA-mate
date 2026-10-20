#!/usr/bin/env python3
"""Check Harness reading-chain links and project/task template contracts.

For framework maintenance, not a required step for each project plan.
Does not inspect live project tasks, PRD/AC coverage, referenced section
contents, semantic task dependencies, or business acceptance results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote

from sdd_dispatch import validate as validate_dispatch_gate


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "AGENTS.md",
    ".claude/CLAUDE.md",
    ".cursor/rules/00-harness-router.mdc",
)
PENDING_ROUTES: set[str] = set()  # All currently declared branches must exist.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
INLINE = re.compile(r"`([^`\n]+)`")
BARE_CORE_PATH = re.compile(r"^\s*(harness-core/[A-Za-z0-9_./-]+\.(?:md|toml))\s*$")
ROOT_PREFIXES = ("harness-core/", ".codex/", ".claude/", ".cursor/", "scripts/", "templates/")
ROOT_FILES = {"AGENTS.md", "project-registry.json"}


def local_reference(root: Path, source: Path, text: str, *, markdown: bool) -> Path | None:
    target = unquote(text.strip().split("#", 1)[0])
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    if target.startswith("scripts/") and not markdown:
        target = target.split()[0]
    if any(character in target for character in ("*", "<", ">", "{", "}", "\n")):
        return None
    if target.startswith(ROOT_PREFIXES) or target in ROOT_FILES:
        return root / target
    if target.startswith("specification/"):
        return root / "harness-core" / target
    if markdown or target.startswith("references/") or re.fullmatch(r"phase-[\w-]+\.md", target):
        return source.parent / target
    return None


def reading_files(root: Path) -> list[Path]:
    files = []
    for relative in ("AGENTS.md", "README.md", "docs", "harness-core",
                     ".codex", ".claude", ".cursor", "templates"):
        path = root / relative
        candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
        files.extend(candidate for candidate in candidates
                     if candidate.is_file() and candidate.suffix in {".md", ".mdc", ".toml"})
    return sorted(set(files))


def check_links(root: Path) -> tuple[list[str], list[str]]:
    problems, warnings = [], []
    router = root / "harness-core/router.md"
    for relative in (*ENTRYPOINTS, "harness-core/router.md"):
        if not (root / relative).is_file():
            problems.append(f"Missing entry file: {relative}")
    for source in reading_files(root):
        linked_paths = set()
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            references = [(m.group(1), True) for m in LINK.finditer(line)]
            references += [(m.group(1), False) for m in INLINE.finditer(line)]
            references += [(m.group(1), False) for m in BARE_CORE_PATH.finditer(line)]
            for text, markdown in references:
                target = local_reference(root, source, text, markdown=markdown)
                if target is None:
                    continue
                target = target.resolve()
                linked_paths.add(target)
                try:
                    relative_target = target.relative_to(root).as_posix()
                except ValueError:
                    problems.append(f"{source.relative_to(root)}:{number}: link escapes Harness: {text}")
                    continue
                if target.exists():
                    continue
                message = f"{source.relative_to(root)}:{number}: missing reference {relative_target}"
                if relative_target in PENDING_ROUTES and any(mark in line for mark in ("待创建", "待编写")):
                    warnings.append(message + " (explicitly pending)")
                else:
                    problems.append(message)
        if source.relative_to(root).as_posix() in ENTRYPOINTS and router.resolve() not in linked_paths:
            problems.append(f"{source.relative_to(root)}: entry does not link to harness-core/router.md")
    return problems, warnings


def load_object(root: Path, relative: str, problems: list[str]) -> dict | None:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        problems.append(f"{relative}: cannot read JSON: {error}")
        return None
    if not isinstance(value, dict):
        problems.append(f"{relative}: expected a JSON object")
        return None
    return value


def project_relative_path(value: object) -> bool:
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts)


def check_feature_links(tasks: dict, task_file: str) -> list[str]:
    """Validate the new plan structure; do not infer whether a PRD proves its claims."""
    if "features" not in tasks:
        return []  # Existing projects retain their original source_feature -> PRD links.
    features = tasks["features"]
    if not isinstance(features, list):
        return [f"{task_file}: features must be an array"]
    problems, feature_ids = [], set()
    for feature in features:
        if not isinstance(feature, dict):
            problems.append(f"{task_file}: each feature must be an object")
            continue
        feature_id = feature.get("id")
        if not isinstance(feature_id, str) or not re.fullmatch(r"[^\s\[\]]+", feature_id):
            problems.append(f"{task_file}: feature IDs must be nonempty strings without whitespace or brackets")
        elif feature_id in feature_ids:
            problems.append(f"{task_file}: duplicate feature ID: {feature_id}")
        else:
            feature_ids.add(feature_id)
        if not isinstance(feature.get("title"), str) or not feature["title"].strip():
            problems.append(f"{task_file}: feature {feature_id} needs a nonempty title")
        requirements = feature.get("source_requirements")
        if (not isinstance(requirements, list) or not requirements
                or any(not isinstance(item, str) or not re.fullmatch(r"[^\s\[\]]+", item)
                       for item in requirements)
                or len(set(requirements)) != len(requirements)):
            problems.append(f"{task_file}: feature {feature_id} source_requirements must be a nonempty array of unique IDs without whitespace or brackets")
    for task in tasks["tasks"]:
        feature_id = task.get("source_feature")
        if not isinstance(feature_id, str) or feature_id not in feature_ids:
            problems.append(f"{task_file}: {task['id']} references an unknown or invalid feature")
        criteria = task.get("acceptanceCriteria")
        if criteria == [] and task.get("type") == "frontend":
            checks = task.get("technicalChecks")
            # Only a structural check: the Planner/Tester must still verify the
            # precise downstream AC ownership and whether the checks suffice.
            has_business_task = any(
                other.get("id") != task.get("id")
                and other.get("source_feature") == feature_id
                and isinstance(other.get("acceptanceCriteria"), list)
                and bool(other["acceptanceCriteria"])
                for other in tasks["tasks"]
            )
            if (not isinstance(checks, list) or not checks
                    or any(not isinstance(item, str) or not item.strip() for item in checks)
                    or not isinstance(task.get("description"), str)
                    or not task["description"].strip() or not has_business_task):
                problems.append(f"{task_file}: {task['id']} frontend stage needs checks, a description, and a business acceptance task in the same feature")
            continue
        if (not isinstance(criteria, list) or not criteria
                or any(not isinstance(item, str) or not re.fullmatch(r"\[[^\s\[\]]+\]\s+\S.*", item)
                       for item in criteria)):
            problems.append(f"{task_file}: {task['id']} acceptanceCriteria must contain [ID] result strings")
    return problems


def check_templates(root: Path) -> list[str]:
    problems: list[str] = []
    project = load_object(root, "templates/project/.sdd/project.json", problems)
    status = load_object(root, "templates/project/.sdd/status.json", problems)
    task_file = "templates/tasks.json"
    tasks = load_object(root, task_file, problems)
    for label, value in (("project template", project), ("task template", tasks)):
        if value is None:
            continue
        if "specification" not in value:
            problems.append(f"{label}: specification must be explicit (set name or null)")
        elif value["specification"] is not None:
            selected = value["specification"]
            if (not isinstance(selected, str) or not selected or selected in {".", "..", "null"}
                    or "/" in selected or "\\" in selected
                    or not (root / "harness-core/specification" / selected).is_dir()):
                problems.append(f"{label}: specification must name an existing set, or be JSON null")
    if status is not None and "tasks" in status:
        problems.append("status template: task lists belong in .sdd/tasks.json")
    if tasks is None:
        return problems
    if "execution_mode" not in tasks or "step_gate" not in tasks:
        problems.append(f"{task_file}: new plan template must include execution_mode and step_gate")
    sources = tasks.get("source_files")
    if not isinstance(sources, dict) or not all(sources.get(key) for key in ("prd", "tech_spec")):
        problems.append(f"{task_file}: source_files must identify prd and tech_spec")
    elif not all(project_relative_path(path) for path in sources.values()):
        problems.append(f"{task_file}: source_files must use project-relative paths")
    items = tasks.get("tasks")
    if not isinstance(items, list):
        return problems + [f"{task_file}: tasks must be an array"]
    ids = [item.get("id") if isinstance(item, dict) else None for item in items]
    if any(not isinstance(item_id, str) or not item_id for item_id in ids) or len(set(ids)) != len(ids):
        return problems + [f"{task_file}: task IDs must be nonempty, unique strings"]
    problems.extend(check_feature_links(tasks, task_file))
    problems.extend(f"{task_file}: {error}" for error in validate_dispatch_gate(tasks))
    dependencies: dict[str, list[str]] = {}
    for item in items:
        task_id = item["id"]
        deps = item.get("dependencies", [])
        if not isinstance(deps, list) or any(not isinstance(dep, str) or dep not in ids for dep in deps):
            problems.append(f"{task_file}: {task_id} has an unknown or invalid dependency")
        else:
            dependencies[task_id] = deps
        contexts = item.get("context_files", [])
        if not isinstance(contexts, list) or any(
            not isinstance(context, dict) or not project_relative_path(context.get("path"))
            for context in contexts
        ):
            problems.append(f"{task_file}: {task_id} context_files must stay inside the project")
        rules = item.get("rules_files", [])
        if not isinstance(rules, list) or any(not isinstance(rule, str) for rule in rules):
            problems.append(f"{task_file}: {task_id} rules_files must be an array of paths")
            continue
        selected = tasks.get("specification")
        if selected is None and rules:
            problems.append(f"{task_file}: {task_id} must have empty rules_files when specification is null")
        elif isinstance(selected, str):
            prefix = f"specification/{selected}/"
            for rule in rules:
                if not rule.startswith(prefix) or not project_relative_path(rule) or not (root / "harness-core" / rule).is_file():
                    problems.append(f"{task_file}: {task_id} references a missing or mismatched rule: {rule}")
    remaining = dict(dependencies)
    while remaining:
        ready = [task_id for task_id, deps in remaining.items() if not any(dep in remaining for dep in deps)]
        if not ready:
            problems.append(f"{task_file}: cyclic task dependencies: {', '.join(sorted(remaining))}")
            break
        for task_id in ready:
            del remaining[task_id]
    return problems


def check(root: Path) -> tuple[list[str], list[str]]:
    root = root.resolve()
    problems, warnings = check_links(root)
    problems.extend(check_templates(root))
    return sorted(set(problems)), sorted(set(warnings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Harness root to inspect")
    args = parser.parse_args()
    problems, warnings = check(args.root)
    for warning in warnings:
        print(f"WARN: {warning}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1
    print("PASS: Harness reading links and template contracts are valid")
    print("SCOPE: Framework/templates only; project plans and business acceptance were not checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
