"""Controlled loading of the fixed requirements foundation for UI tools.

Only the standard library is used. The loader never imports the Solution
Designer running service and never falls back to cwd, legacy scripts or
same-named modules on sys.path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType


CONTRACT_VERSION = "ui-tools-v1"
SERVER_NAME = "ui-designer-file-tools"
SERVER_VERSION = "0.1.0"
CLIENT_ENTRY_NAME = "ui-designer"

SHARED_MODULES = (
    "__init__",
    "check_foundation",
    "project_state",
    "project_init",
    "requirements",
    "project_info",
    "artifact_records",
    "confirmation_records",
    "recovery",
)

# Runtime baseline documents (contract 2.2 / plan A1.3): role entry, file
# workflow convention and the local UI template. Build progress, test ledgers
# and the whole SOURCES document are deliberately excluded.
BASELINE_ROLE_DOCUMENTS = ("ui-design.md", "agent-file-workflow.md")
BASELINE_TEMPLATE = "templates/ui-style-template.md"


class FoundationError(RuntimeError):
    def __init__(self, code, message, *, details=None, next_action=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.next_action = next_action or "核对 foundation、来源记录与采用源码后重启服务"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FoundationError("foundation_invalid", f"无法读取 JSON：{path.name}",
                              details={"reason": str(error)}) from error
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
    alias = "_ui_shared_requirements_" + sha256_bytes(str(foundation).encode("utf-8"))[:16]
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


def _expected_index(source_data: dict):
    expected_shared = {}
    for item in source_data.get("planned_shared_dependencies", []):
        expected_shared[item["path"]] = item["sha256_at_inventory"]
    documents = {item["file"]: item["sha256"] for item in source_data.get("local_documents", [])}
    copies = {
        item["file"]: item["copy_sha256"]
        for item in source_data.get("local_copies", [])
        if item.get("copy_sha256")
    }
    runtime_section = source_data.get("runtime_sources")
    if not isinstance(runtime_section, dict) or not isinstance(runtime_section.get("files"), list):
        raise FoundationError(
            "foundation_invalid",
            "SOURCES.json 缺少 runtime_sources.files 运行源码采用记录",
        )
    runtime_files = {}
    for item in runtime_section["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) \
                or not isinstance(item.get("sha256"), str):
            raise FoundationError("foundation_invalid", "runtime_sources 记录格式错误")
        runtime_files[item["path"]] = item["sha256"]
    return expected_shared, documents, copies, runtime_files


def _link_target(path: Path):
    if not path.is_symlink():
        raise FoundationError("methods_invalid", f"方法入口必须是软链：{path}")
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise FoundationError("methods_invalid", f"方法入口断链：{path}",
                              details={"reason": str(error)}) from error


def load_shared(foundation: os.PathLike[str] | str, ui_root: os.PathLike[str] | str | None = None):
    foundation = Path(foundation).expanduser()
    ui_root = Path(ui_root or Path(__file__).resolve().parent).resolve(strict=True)
    if not foundation.is_absolute() or foundation.is_symlink() or not foundation.is_dir():
        raise FoundationError("foundation_invalid", "--foundation 必须是普通绝对目录")
    foundation = foundation.resolve(strict=True)
    sources_path = _regular_file(ui_root / "SOURCES.json", "SOURCES.json")
    source_data = read_json(sources_path)
    expected_sources, expected_documents, expected_copies, runtime_files = _expected_index(source_data)

    actual_sources = {}
    tools_root = foundation / "file_tools"
    for relative, expected in expected_sources.items():
        try:
            path = (ui_root / relative).resolve(strict=True)
            if path.parent != tools_root or path.is_symlink():
                raise FoundationError("dependency_missing", "共享依赖不在固定 foundation 布局内",
                                      details={"path": relative})
            actual = sha256_file(path)
        except FoundationError:
            raise
        except OSError as error:
            raise FoundationError("dependency_missing", f"共享依赖缺失：{relative}",
                                  details={"reason": str(error)}) from error
        actual_sources[f"file_tools/{path.name}"] = actual
        if actual != expected:
            raise FoundationError("dependency_changed", "共享依赖与采用摘要不一致",
                                  details={"path": relative})

    config_path = foundation / "config/local.json"
    lock_path = foundation / "upstream-lock.json"
    _regular_file(config_path, "config/local.json")
    _regular_file(lock_path, "upstream-lock.json")
    config = read_json(config_path)
    try:
        upstream = Path(config["upstream_root"]).resolve(strict=True)
        projects_root = Path(config["projects_root"]).resolve(strict=True)
    except (KeyError, OSError, TypeError) as error:
        raise FoundationError("foundation_invalid",
                              "foundation 配置缺少合法 upstream_root 或 projects_root") from error
    for path in (foundation, upstream, projects_root):
        if path.is_symlink():
            raise FoundationError("foundation_invalid", "安装、上游或业务根目录不能是软链")
    if foundation == ui_root or foundation in ui_root.parents or ui_root in foundation.parents:
        if ui_root != foundation.parent / "UI":
            raise FoundationError("foundation_invalid", "UI 安装目录与 foundation 布局不受支持")

    requirements_link = _link_target(foundation / "methods/develop-helper")
    ui_link = _link_target(ui_root / "methods/develop-helper")
    if requirements_link != upstream or ui_link != upstream:
        raise FoundationError("methods_invalid", "双方法入口必须解析到配置中的同一 upstream_root")

    local_documents = {}
    for relative in BASELINE_ROLE_DOCUMENTS:
        expected = expected_documents.get(relative)
        if not expected:
            raise FoundationError("dependency_missing", f"SOURCES 缺少采用文档摘要：{relative}")
        path = _regular_file(ui_root / relative, relative)
        actual = sha256_file(path)
        local_documents[relative] = actual
        if actual != expected:
            raise FoundationError("dependency_changed", "角色或约定文档与来源摘要不一致",
                                  details={"path": relative})
    template_path = _regular_file(ui_root / BASELINE_TEMPLATE, BASELINE_TEMPLATE)
    template_actual = sha256_file(template_path)
    if template_actual != expected_copies.get(BASELINE_TEMPLATE):
        raise FoundationError("dependency_changed", "UI 模板与来源摘要不一致",
                              details={"path": BASELINE_TEMPLATE})
    local_documents[BASELINE_TEMPLATE] = template_actual

    runtime_sources = {}
    for relative, expected in runtime_files.items():
        path = _regular_file(ui_root / relative, relative)
        try:
            path.resolve(strict=True).relative_to(ui_root)
        except ValueError as error:
            raise FoundationError("dependency_missing", "运行源码记录必须位于 UI 目录内",
                                  details={"path": relative}) from error
        actual = sha256_file(path)
        runtime_sources[relative] = actual
        if actual != expected:
            raise FoundationError("dependency_changed",
                                  "UI 运行源码与 SOURCES 采用摘要不一致；先核对变更并更新来源记录",
                                  details={"path": relative})

    shared = _load_alias_package(foundation)
    try:
        shared.check_foundation.check(foundation)
    except (OSError, ValueError, RuntimeError) as error:
        raise FoundationError("foundation_invalid", str(error)) from error

    baseline = {
        "foundation": str(foundation),
        "ui_root": str(ui_root),
        "config_local_sha256": sha256_file(config_path),
        "upstream_lock_sha256": sha256_file(lock_path),
        "shared_sources_sha256": sha256_bytes(
            json.dumps(actual_sources, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "local_documents_sha256": sha256_bytes(
            json.dumps(local_documents, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "runtime_sources_sha256": sha256_bytes(
            json.dumps(runtime_sources, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "methods": {
            "requirements_target": str(requirements_link),
            "ui_target": str(ui_link),
        },
    }
    return type(
        "SharedRuntime",
        (),
        {
            "foundation": foundation,
            "ui_root": ui_root,
            "modules": shared,
            "baseline": baseline,
            "config": config,
            "projects_root": projects_root,
            "upstream_root": upstream,
            "source_data": source_data,
        },
    )()


def verify_runtime_baseline(runtime) -> None:
    current = load_shared(runtime.foundation, runtime.ui_root)
    if current.baseline != runtime.baseline:
        raise FoundationError("runtime_baseline_changed", "运行基线已变化；请重新启动并核对服务")
