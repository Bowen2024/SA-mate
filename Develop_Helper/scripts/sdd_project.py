#!/usr/bin/env python3
"""Tiny project manager for SDD V7_2.

This script intentionally uses only the Python standard library so students can
inspect and run it without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "Projects_Repo"
REGISTRY_PATH = ROOT / "project-registry.json"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_registry() -> dict:
    return {
        "version": 1,
        "projects_root": "Projects_Repo",
        "active_project_id": None,
        "projects": [],
    }


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return default_registry()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry.setdefault("version", 1)
    registry.setdefault("projects_root", "Projects_Repo")
    registry.setdefault("active_project_id", None)
    registry.setdefault("projects", [])
    return registry


def save_registry(registry: dict) -> None:
    # Replace atomically: interrupted writes must not truncate the registry.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ROOT, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.replace(temporary, REGISTRY_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def get_project(registry: dict, project_id: str) -> dict | None:
    return next((p for p in registry.get("projects", []) if p["id"] == project_id), None)


def ensure_project_dirs(project_dir: Path) -> None:
    for rel in [
        ".sdd",
        ".sdd/test-reports",
        ".sdd/bug_fix",
        "docs",
    ]:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)


def copy_harness(project_dir: Path) -> None:
    """Copy project runtime scaffolding.

    Platform adapters (.cursor/.claude/.codex) stay in the Harness root.
    Copying them into every managed project causes rule drift.
    """
    for name in ["pycore"]:
        src = ROOT / name
        dst = project_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def run_git(project_dir: Path, *git_args: str) -> bool:
    try:
        result = subprocess.run(
            ["git", *git_args],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def configure_remote(project_dir: Path, repo_url: str) -> bool:
    """Configure git remote origin for a newly created project.

    Initializes a local git repository on demand (otherwise the git-workflow
    skill would do it later), then points origin at repo_url. No first push.
    """
    if not (project_dir / ".git").exists():
        if not run_git(project_dir, "init", "-b", "main"):
            return False
    if run_git(project_dir, "remote", "get-url", "origin"):
        return run_git(project_dir, "remote", "set-url", "origin", repo_url)
    return run_git(project_dir, "remote", "add", "origin", repo_url)


def write_project_entrypoints(project_dir: Path) -> None:
    """Write lightweight project-local entrypoints for users who open a project directly."""
    agents = project_dir / "AGENTS.md"
    if not agents.exists():
        agents.write_text(
            """# Managed Project Entry

This project is managed by SDD Harness V7_2.

Recommended workflow: open the Harness root, not this project folder:

```text
../../
```

Core rules live in:

```text
../../harness-core/
```

Project files live here:

```text
.sdd/
docs/
frontend/
backend/
```

Do not create local `.cursor/`, `.claude/`, or `.codex/` rule copies inside this project unless the Harness explicitly asks for it.
""",
            encoding="utf-8",
        )


def init_sdd_files(project_dir: Path, project_id: str, name: str, project_type: str, source: str, repo_url: str | None, specification: str | None = None) -> None:
    ensure_project_dirs(project_dir)

    project_json = project_dir / ".sdd/project.json"
    if not project_json.exists():
        project_json.write_text(
            json.dumps(
                {
                    "id": project_id,
                    "name": name,
                    "project_type": project_type,
                    "source": source,
                    "repo_url": repo_url,
                    "specification": specification,
                    "created_at": now(),
                    "last_active": now(),
                    "harness_version": "V7_2",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    status_json = project_dir / ".sdd/status.json"
    if not status_json.exists():
        status_json.write_text(
            json.dumps(
                {
                    "stage": "initialized",
                    "mode": source,
                    "design_ready": False,
                    "development_ready": False,
                    "current_task": None,
                    "blocked": False,
                    "notes": "",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    for filename in ["experience.md", "work-log.md"]:
        dst = project_dir / ".sdd" / filename
        if not dst.exists():
            template = ROOT / "templates/project/.sdd" / filename
            dst.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    readme = project_dir / "README.md"
    if not readme.exists():
        template = ROOT / "templates/project/README.md"
        readme.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    write_project_entrypoints(project_dir)


def register_project(project_id: str, name: str, project_type: str, source: str, repo_url: str | None = None, activate: bool = True, specification: str | None = None) -> None:
    registry = load_registry()
    projects = registry.setdefault("projects", [])
    rel_path = f"Projects_Repo/{project_id}"

    existing = get_project(registry, project_id)
    payload = {
        "id": project_id,
        "name": name,
        "path": rel_path,
        "source": source,
        "repo_url": repo_url,
        "project_type": project_type,
        "specification": specification,
        "status": "initialized",
        "created_at": existing.get("created_at") if existing else now(),
        "last_active": now(),
    }

    if existing:
        existing.update(payload)
    else:
        projects.append(payload)

    if activate:
        registry["active_project_id"] = project_id
    save_registry(registry)


def set_active_project(project_id: str) -> dict:
    registry = load_registry()
    project = get_project(registry, project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")

    project_dir = ROOT / project["path"]
    if not (project_dir / ".sdd/project.json").exists():
        raise SystemExit(f"Project is not initialized: {project_dir}")

    registry["active_project_id"] = project_id
    project["last_active"] = now()
    save_registry(registry)
    return project


def active_project(registry: dict | None = None) -> dict | None:
    registry = registry or load_registry()
    active_id = registry.get("active_project_id")
    if not active_id:
        return None
    return get_project(registry, active_id)


def validate_directory_name(value: str, label: str) -> None:
    if not value.strip() or value in {".", ".."} or any(c in value for c in ("/", "\\", "\0")):
        raise SystemExit(f"{label} must be a single directory name: {value!r}")


def validate_new_project(args: argparse.Namespace, *, allow_existing: bool = False) -> Path:
    """Check inputs and required scaffolding before creating any project files."""
    validate_directory_name(args.id, "Project ID")
    if not args.name.strip():
        raise SystemExit("Project name must not be empty")
    project_dir = PROJECTS_ROOT / args.id
    if PROJECTS_ROOT.resolve().parent != ROOT.resolve():
        raise SystemExit("Projects_Repo must be inside the Harness root")
    if project_dir.resolve().parent != PROJECTS_ROOT.resolve():
        raise SystemExit("Project path must be a direct child of Projects_Repo")
    if get_project(load_registry(), args.id):
        raise SystemExit(f"Project ID is already registered: {args.id}")
    if project_dir.is_symlink() or (project_dir.exists() and not allow_existing):
        raise SystemExit(f"Project path already exists; refusing to overwrite: {project_dir}")

    if args.specification is not None:
        validate_directory_name(args.specification, "Specification")
        if args.specification == "null":
            raise SystemExit("Use --no-specification for JSON null")
        specifications_root = ROOT / "harness-core/specification"
        specification_dir = specifications_root / args.specification
        if specification_dir.resolve().parent != specifications_root.resolve():
            raise SystemExit("Specification must be inside harness-core/specification")
        if not specification_dir.is_dir():
            raise SystemExit(f"Specification does not exist: {args.specification}")

    for rel in (".sdd/experience.md", ".sdd/work-log.md", "README.md"):
        template = ROOT / "templates/project" / rel
        if not template.is_file():
            raise SystemExit(f"Required project template is missing: {template}")
    if getattr(args, "cmd", "new") == "new" and args.specification == "default" and not (ROOT / "pycore").is_dir():
        raise SystemExit("Default runtime scaffolding is missing: pycore")
    return project_dir


def onboard_origin(source: Path) -> str | None:
    """Read only the source's own repository; never inherit the Harness repo."""
    if not (source / ".git").exists():
        return None
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=source,
                                capture_output=True, text=True, check=True)
        if Path(result.stdout.strip()).resolve() != source:
            raise SystemExit("Source Git root is not the project root")
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=source,
                                capture_output=True, text=True)
        return remote.stdout.strip() if remote.returncode == 0 else None
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Cannot verify source Git repository; no files changed") from exc


def cmd_onboard(args: argparse.Namespace) -> None:
    target = validate_new_project(args, allow_existing=args.mode == "register")
    given = Path(args.from_path).expanduser()
    if not given.is_absolute() or given.is_symlink() or not given.is_dir():
        raise SystemExit("Source must be an existing absolute directory, not a symbolic link")
    source = given.resolve()
    if args.mode == "register":
        if source != target.resolve() or not target.is_dir():
            raise SystemExit("Register mode requires the existing Projects_Repo/<id> directory")
    elif source == ROOT or ROOT in source.parents or source in ROOT.parents:
        raise SystemExit("Copy mode requires a source outside the Harness, not its ancestor")
    if (source / ".git").exists() and not (source / ".git").is_dir():
        raise SystemExit("Git worktree/submodule pointer cannot be copied; prepare an independent clone")
    for rel in (".git", ".sdd", ".sdd/test-reports", ".sdd/bug_fix", "docs"):
        path = source / rel
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise SystemExit(f"Unsafe or conflicting directory: {rel}")
    for rel in (".sdd/project.json", ".sdd/status.json", ".sdd/tasks.json"):
        if (source / rel).exists() or (source / rel).is_symlink():
            raise SystemExit(f"Existing SDD metadata requires explicit migration before onboarding: {rel}")
    for rel in ("AGENTS.md", "README.md", ".sdd/experience.md", ".sdd/work-log.md"):
        path = source / rel
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise SystemExit(f"Unsafe or conflicting file: {rel}")
    origin = onboard_origin(source)
    if args.repo_url and origin and args.repo_url != origin:
        raise SystemExit("Requested repo_url conflicts with existing origin; choose before onboarding")
    repo_url = origin or args.repo_url
    if args.mode == "copy":
        ignore_runtime = shutil.ignore_patterns(
            "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
            ".mypy_cache", ".ruff_cache", ".DS_Store")
        def ignore(directory: str, names: list[str]) -> list[str] | set[str]:
            # Git refs may have names such as 'venv'; repository internals are not caches.
            if Path(directory).is_relative_to(source / ".git"):
                return []
            return ignore_runtime(directory, names)
        shutil.copytree(source, target, symlinks=True, ignore=ignore)
    try:
        if args.repo_url and not origin and not configure_remote(target, args.repo_url):
            raise RuntimeError("Git remote configuration failed")
        init_sdd_files(target, args.id, args.name, args.type, "onboarded", repo_url,
                       specification=args.specification)
        register_project(args.id, args.name, args.type, "onboarded", repo_url=repo_url,
                         specification=args.specification)
    except Exception as exc:
        raise SystemExit(f"Onboarding incomplete at {target}; preserve and inspect partial files before retrying: {exc}") from exc
    print(f"Project onboarded: {target}")
    print(f"Source preserved: {source}")
    print(f"Specification: {json.dumps(args.specification, ensure_ascii=False)}")


def cmd_remove(args: argparse.Namespace) -> None:
    """Archive one identified project and unregister it; never delete permanently."""
    validate_directory_name(args.id, "Project ID")
    registry = load_registry()
    entries = [p for p in registry["projects"] if p["id"] == args.id]
    target = PROJECTS_ROOT / args.id
    if len(entries) != 1 or entries[0]["path"] != f"Projects_Repo/{args.id}":
        raise SystemExit("Project registration missing or inconsistent")
    if PROJECTS_ROOT.resolve() != ROOT / "Projects_Repo" or target.is_symlink() or not target.is_dir():
        raise SystemExit("Project path is missing or unsafe")
    metadata = target / ".sdd/project.json"
    if (target / ".sdd").is_symlink() or metadata.is_symlink():
        raise SystemExit("Project metadata must not be a symbolic link")
    if json.loads(metadata.read_text(encoding="utf-8")).get("id") != args.id:
        raise SystemExit("Project identity does not match its registration")
    backup = Path(args.backup_dir).expanduser()
    if not backup.is_absolute() or backup.is_symlink():
        raise SystemExit("Backup must be an absolute path, not a symbolic link")
    backup = backup.resolve()
    if backup == ROOT or ROOT in backup.parents or backup in ROOT.parents:
        raise SystemExit("Backup must be outside the Harness, not its ancestor")
    if backup.exists() or backup.is_symlink() or not backup.parent.is_dir():
        raise SystemExit("Backup must not exist; its parent directory must exist")
    if backup.parent.stat().st_dev != target.stat().st_dev:
        raise SystemExit("Backup must be on the same filesystem; project unchanged")
    original = REGISTRY_PATH.read_bytes()
    backup.mkdir(mode=0o700)
    (backup / "project-registry.before.json").write_bytes(original)
    os.rename(target, backup / args.id)
    registry["projects"] = [p for p in registry["projects"] if p["id"] != args.id]
    if registry.get("active_project_id") == args.id:
        registry["active_project_id"] = None
    try:
        save_registry(registry)
    except Exception:
        os.rename(backup / args.id, target)
        raise
    print(f"Project removed from Harness: {target}")
    print(f"Recoverable backup: {backup}")
    print("No services stopped or remote repositories modified by this command")


def cmd_new(args: argparse.Namespace) -> None:
    project_dir = validate_new_project(args)
    project_dir.mkdir(parents=True, exist_ok=False)
    if args.specification == "default":
        copy_harness(project_dir)
    init_sdd_files(project_dir, args.id, args.name, args.type, "new", args.repo_url, specification=args.specification)
    register_project(args.id, args.name, args.type, "new", repo_url=args.repo_url, activate=True, specification=args.specification)
    if args.repo_url and not configure_remote(project_dir, args.repo_url):
        raise SystemExit(
            f"Project created and registered at {project_dir}, but Git remote configuration failed. "
            "Verify origin inside this project before continuing; do not run new again."
        )
    if args.repo_url:
        print(f"Git remote origin: {args.repo_url}")
    print(f"Project created: {project_dir}")
    print(f"Active project: {args.id}")
    print(f"active_project_path: Projects_Repo/{args.id}/")
    print(f"Specification: {json.dumps(args.specification, ensure_ascii=False)}")


def cmd_use(args: argparse.Namespace) -> None:
    project = set_active_project(args.id)
    print(f"Active project: {project['id']}")
    print(f"active_project_path: {project['path']}/")


def cmd_current(_: argparse.Namespace) -> None:
    registry = load_registry()
    project = active_project(registry)
    if not project:
        print("No active project. Use `python scripts/sdd_project.py list` then `python scripts/sdd_project.py use <id>`.")
        return
    print(f"Active project: {project['id']}")
    print(f"Name: {project['name']}")
    print(f"Type: {project['project_type']}")
    print(f"Status: {project['status']}")
    print(f"active_project_path: {project['path']}/")


def cmd_list(_: argparse.Namespace) -> None:
    registry = load_registry()
    active_id = registry.get("active_project_id")
    for project in registry.get("projects", []):
        marker = "*" if project["id"] == active_id else " "
        print(f"{marker} {project['id']}	{project['project_type']}	{project['status']}	{project['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SDD V7_2 project manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="Create a new managed project and set it active")
    new.add_argument("id", help="project id, e.g. customer-service")
    new.add_argument("--name", required=True, help="human-readable project name")
    new.add_argument("--type", default="unknown", choices=["web", "mobile", "api", "cli", "unknown"])
    new.add_argument("--repo-url", default=None, help="optional remote repository URL; configures git remote origin (git init + git remote add, no push) and is written to the registry")
    specification = new.add_mutually_exclusive_group(required=True)
    specification.add_argument("--specification", help="existing specification set name, e.g. default")
    specification.add_argument("--no-specification", dest="specification", action="store_const", const=None, help="use no specification set; save JSON null and omit default runtime scaffolding")
    new.set_defaults(func=cmd_new)

    onboard = sub.add_parser("onboard", help="Copy an existing local project or register its managed-directory copy")
    onboard.add_argument("id")
    onboard.add_argument("--name", required=True)
    onboard.add_argument("--type", required=True, choices=["web", "mobile", "api", "cli"])
    onboard.add_argument("--from-path", required=True)
    onboard.add_argument("--mode", required=True, choices=["copy", "register"])
    onboard.add_argument("--repo-url", default=None)
    onboard_spec = onboard.add_mutually_exclusive_group(required=True)
    onboard_spec.add_argument("--specification")
    onboard_spec.add_argument("--no-specification", dest="specification", action="store_const", const=None)
    onboard.set_defaults(func=cmd_onboard)

    remove = sub.add_parser("remove", help="Move one project to an external backup and remove its registration")
    remove.add_argument("id")
    remove.add_argument("--backup-dir", required=True)
    remove.set_defaults(func=cmd_remove)

    use = sub.add_parser("use", help="Set active project")
    use.add_argument("id", help="project id")
    use.set_defaults(func=cmd_use)

    current = sub.add_parser("current", help="Show active project")
    current.set_defaults(func=cmd_current)

    list_cmd = sub.add_parser("list", help="List registered projects")
    list_cmd.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
