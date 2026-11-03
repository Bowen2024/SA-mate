"""Controlled loading of the fixed requirements foundation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType


CONTRACT_VERSION = "solution-tools-v1"
SERVER_NAME = "solution-designer-file-tools"
SERVER_VERSION = "0.1.0"
CLIENT_ENTRY_NAME = "solution-designer"

SHARED_MODULES = (
    "__init__",
    "check_foundation",
    "project_state",
    "project_init",
    "requirements",
    "project_info",
    "recovery",
    "confirmation_records",
    "artifact_records",
)

LOCAL_BASELINE_DOCUMENTS = (
    "solution-design.md",
    "agent-file-workflow.md",
    "templates/tech-spec-template.md",
    "templates/research-template.md",
    "README.md",
)


class FoundationError(RuntimeError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FoundationError("foundation_invalid", f"无法读取 JSON：{path.name}", details=str(error)) from error
    if not isinstance(value, dict):
        raise FoundationError("foundation_invalid", f"JSON 必须是对象：{path.name}")
    return value


def _regular_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise FoundationError("dependency_missing", f"{label} 不是独立普通文件")
    return path


def _load_alias_package(foundation: Path):
    tools_root = foundation / "file_tools"
    if not tools_root.is_dir() or tools_root.is_symlink():
        raise FoundationError("dependency_missing", "受信 file_tools 目录缺失或不是普通目录")
    alias = "_solution_shared_requirements_" + sha256_bytes(str(foundation).encode("utf-8"))[:16]
    if alias in sys.modules and getattr(sys.modules[alias], "__path__", None) == [str(foundation)]:
        cached = {"package_init": sys.modules[f"{alias}.file_tools"], "package_alias": alias}
        for module_name in SHARED_MODULES:
            if module_name != "__init__":
                cached[module_name] = sys.modules[f"{alias}.file_tools.{module_name}"]
        return type("SharedRequirements", (), cached)
    package = ModuleType(alias)
    package.__path__ = [str(foundation)]
    sys.modules[alias] = package
    loaded = {}
    for module_name in SHARED_MODULES:
        if module_name == "__init__":
            full_name = f"{alias}.file_tools"
            path = tools_root / "__init__.py"
            search_locations = [str(tools_root)]
        else:
            full_name = f"{alias}.file_tools.{module_name}"
            path = tools_root / f"{module_name}.py"
            search_locations = None
        _regular_file(path, f"共享模块 {module_name}")
        spec = importlib.util.spec_from_file_location(
            full_name, path, submodule_search_locations=search_locations
        )
        if spec is None or spec.loader is None:
            raise FoundationError("dependency_missing", f"无法加载共享模块：{module_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
        loaded["package_init" if module_name == "__init__" else module_name] = module
    loaded["package_alias"] = alias
    return type("SharedRequirements", (), loaded)


def _expected_source_index(sources: Path):
    data = read_json(sources)
    expected = {}
    for item in data.get("planned_shared_dependencies", []):
        expected[item["path"]] = item["sha256_at_inventory"]
    documents = {item["file"]: item["sha256"] for item in data.get("local_documents", [])}
    copies = {f"templates/{Path(item['file']).name}" if "/" not in item["file"] else item["file"]: item["copy_sha256"]
              for item in data.get("local_copies", [])}
    documents.update({key: value for key, value in copies.items() if value})
    return expected, documents


def _link_target(path: Path):
    if not path.is_symlink():
        raise FoundationError("methods_invalid", f"方法入口必须是软链：{path}")
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise FoundationError("methods_invalid", f"方法入口断链：{path}", details=str(error)) from error


def load_shared(foundation: os.PathLike[str] | str, solution_root: os.PathLike[str] | str | None = None):
    foundation = Path(foundation).expanduser()
    solution_root = Path(solution_root or Path(__file__).resolve().parent).resolve(strict=True)
    if not foundation.is_absolute() or foundation.is_symlink() or not foundation.is_dir():
        raise FoundationError("foundation_invalid", "--foundation 必须是普通绝对目录")
    foundation = foundation.resolve(strict=True)
    sources_path = _regular_file(solution_root / "SOURCES.json", "SOURCES.json")
    source_data = read_json(sources_path)
    expected_sources, expected_documents = _expected_source_index(sources_path)

    actual_sources = {}
    for relative, expected in expected_sources.items():
        try:
            path = (solution_root / relative).resolve(strict=True)
            if path.parent != foundation / "file_tools" or path.is_symlink():
                raise FoundationError("dependency_missing", "共享依赖不在固定 foundation 布局内",
                                      path=relative)
            actual = sha256_file(path)
        except FoundationError:
            raise
        except OSError as error:
            raise FoundationError("dependency_missing", f"共享依赖缺失：{relative}",
                                  details=str(error)) from error
        actual_sources[f"file_tools/{path.name}"] = actual
        if actual != expected:
            raise FoundationError("dependency_changed", "共享依赖与采用摘要不一致", path=relative)

    config_path = foundation / "config/local.json"
    lock_path = foundation / "upstream-lock.json"
    _regular_file(config_path, "config/local.json")
    _regular_file(lock_path, "upstream-lock.json")
    config = read_json(config_path)
    try:
        upstream = Path(config["upstream_root"]).resolve(strict=True)
        projects_root = Path(config["projects_root"]).resolve(strict=True)
    except (KeyError, OSError, TypeError) as error:
        raise FoundationError("foundation_invalid", "foundation 配置缺少合法 upstream_root 或 projects_root") from error
    for path in (foundation, upstream, projects_root):
        if path.is_symlink():
            raise FoundationError("foundation_invalid", "安装、上游或业务根目录不能是软链")
    if foundation == solution_root or foundation in solution_root.parents or solution_root in foundation.parents:
        if solution_root != foundation.parent / "Solution Designer":
            raise FoundationError("foundation_invalid", "方案安装目录与 foundation 布局不受支持")

    requirements_link = _link_target(foundation / "methods/develop-helper")
    solution_link = _link_target(solution_root / "methods/develop-helper")
    if requirements_link != upstream or solution_link != upstream:
        raise FoundationError("methods_invalid", "双方法入口必须解析到配置中的同一 upstream_root")
    research_link = solution_root / "templates/research-template.md"
    if not research_link.is_symlink() or research_link.resolve(strict=True) is None:
        raise FoundationError("methods_invalid", "调研模板入口断链")

    local_documents = {}
    for relative, expected in expected_documents.items():
        path = solution_root / relative
        if path.is_symlink():
            try:
                actual = sha256_bytes(path.resolve(strict=True).read_bytes())
            except OSError as error:
                raise FoundationError("dependency_missing", f"方案文档入口断链：{relative}",
                                      details=str(error)) from error
        else:
            _regular_file(path, relative)
            actual = sha256_file(path)
        local_documents[relative] = actual
        if actual != expected:
            raise FoundationError("dependency_changed", "方案文档与来源摘要不一致", path=relative)

    shared = _load_alias_package(foundation)
    try:
        shared.check_foundation.check(foundation)
    except (OSError, ValueError, RuntimeError) as error:
        raise FoundationError("foundation_invalid", str(error)) from error

    baseline = {
        "foundation": str(foundation),
        "solution_root": str(solution_root),
        "config_local_sha256": sha256_file(config_path),
        "upstream_lock_sha256": sha256_file(lock_path),
        "shared_sources_sha256": sha256_bytes(
            json.dumps(actual_sources, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "local_documents_sha256": sha256_bytes(
            json.dumps(local_documents, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "methods": {
            "requirements_target": str(requirements_link),
            "solution_target": str(solution_link),
            "research_target": str(research_link.resolve(strict=True)),
        },
    }
    return type(
        "SharedRuntime",
        (),
        {
            "foundation": foundation,
            "solution_root": solution_root,
            "modules": shared,
            "baseline": baseline,
            "config": config,
            "projects_root": projects_root,
            "upstream_root": upstream,
            "source_data": source_data,
        },
    )()


def verify_runtime_baseline(runtime) -> None:
    current = load_shared(runtime.foundation, runtime.solution_root)
    if current.baseline != runtime.baseline:
        raise FoundationError("runtime_baseline_changed", "运行基线已变化；请重新启动并核对服务")
