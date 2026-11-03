"""Disposable filesystem and MCP support for UI step-5 tests.

All writes happen inside a system temporary directory. Projects are created
through the shared project_init capability (never hand-faked project.json for
P fixtures). Static H/transaction fixtures are clearly marked in tests as
hand-built read-only evidence, not save-success evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = RUNTIME_ROOT / "workflows/UI"
REQUIREMENTS_SOURCE = RUNTIME_ROOT / "workflows/requirements"

DESIGN_PATH = "docs/ui-style.md"
DEFAULT_ROOT = "docs/prototypes/demo"
MANIFEST_PATH = "ui/artifact-manifest.json"
STATE_DIR = "ui/.ui-state"
MODERN_PROTOCOL = "2026-07-28"

# Each fixture gets a process-wide unique token. id(self) is reused after the
# TestCase is garbage collected, which previously collided with stale modules
# left in sys.modules and reloaded project_init from a deleted temp install.
_FIXTURE_SEQUENCE = itertools.count(1)


def purge_shared_ui_modules():
    for name in list(sys.modules):
        if name == "shared_loader" or name == "file_tools" or name.startswith("file_tools."):
            del sys.modules[name]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def load_module(unique_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


def tree_snapshot(root: Path):
    entries = {}
    root = Path(root)
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root).as_posix()
        if rel_dir != ".":
            entries[rel_dir + "/"] = ["dir"]
        for name in sorted(directories + files):
            child = current_path / name
            rel = child.relative_to(root).as_posix()
            if child.is_symlink():
                entries[rel] = ["symlink", os.readlink(child)]
            elif child.is_dir():
                continue
            else:
                entries[rel] = ["file", sha(child.read_bytes())]
    return dict(sorted(entries.items()))


class UiFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ui-tools-")
        self.addCleanup(temp.cleanup)
        self._fixture_token = f"f{next(_FIXTURE_SEQUENCE)}"
        self._injected_modules = []
        self.addCleanup(self._cleanup_modules)
        self.root = Path(temp.name).resolve()
        self.install = self.root / "install/fusion-runtime/workflows"
        self.foundation = self.install / "requirements"
        self.ui = self.install / "UI"
        self.upstream = self.root / "install/Develop_Helper"
        self.projects = self.root / "business"
        self.import_parent = self.root / "imports/外部素材"
        self.outside = self.root / "outside"
        for path in (self.install, self.projects, self.outside, self.import_parent,
                     self.root / "decoy"):
            path.mkdir(parents=True)
        shutil.copytree(
            REQUIREMENTS_SOURCE, self.foundation,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", "methods"),
        )
        shutil.copytree(
            UI_SOURCE, self.ui,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", "methods"),
        )
        self.create_upstream()
        self.project_p1 = self.projects / "采购演示"
        self.project_p2 = self.projects / "会议助手"
        self.config = {
            "schema_version": 1,
            "upstream_root": str(self.upstream),
            "projects_root": str(self.projects),
            "project_directories": {"procurement-demo": self.project_p1.name,
                                     "meeting-b": self.project_p2.name},
        }
        self.write_config()
        self.init_projects()
        self.now = time.time()
        self.server = None
        self._sys_path_inserted = str(self.ui)
        sys.path.insert(0, self._sys_path_inserted)
        self.addCleanup(lambda: sys.path.remove(self._sys_path_inserted)
                        if self._sys_path_inserted in sys.path else None)

    def create_upstream(self):
        spec_dir = self.upstream / "harness-core/specification/default"
        spec_dir.mkdir(parents=True)
        (spec_dir / "backend.md").write_text("# 默认规范\n\n仅用于隔离测试。\n", encoding="utf-8")
        style = self.upstream / "harness-core/skills/ui-design-standard"
        style.mkdir(parents=True)
        (style / "SKILL.md").write_text("# UI 设计方法（隔离夹具）\n", encoding="utf-8")
        phase_b = self.upstream / "harness-core/skills/sdd-product-design"
        phase_b.mkdir(parents=True)
        (phase_b / "phase-B.md").write_text("# 阶段 B（隔离夹具）\n", encoding="utf-8")
        for base in (self.foundation, self.ui):
            link = base / "methods/develop-helper"
            link.parent.mkdir(exist_ok=True)
            link.symlink_to(self.upstream, target_is_directory=True)
        check_name = f"foundation_check_{self._fixture_token}"
        self._injected_modules.append(check_name)
        check = load_module(check_name,
                            self.foundation / "file_tools/check_foundation.py")
        (self.foundation / "upstream-lock.json").write_text(
            json.dumps(check.snapshot(self.upstream)), encoding="utf-8")

    def relock_upstream(self):
        check_name = f"foundation_check_relock_{self._fixture_token}"
        self._injected_modules.append(check_name)
        check = load_module(check_name,
                            self.foundation / "file_tools/check_foundation.py")
        (self.foundation / "upstream-lock.json").write_text(
            json.dumps(check.snapshot(self.upstream)), encoding="utf-8")

    def write_config(self):
        path = self.foundation / "config/local.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.config), encoding="utf-8")

    def _cleanup_modules(self):
        alias = f"_ui_fix_tools_{self._fixture_token}"
        for name in list(sys.modules):
            if name == alias or name.startswith(alias + "."):
                sys.modules.pop(name, None)
        for name in self._injected_modules:
            sys.modules.pop(name, None)
        purge_shared_ui_modules()

    def _project_init(self):
        tools_dir = self.foundation / "file_tools"
        alias = f"_ui_fix_tools_{self._fixture_token}"
        if alias not in sys.modules:
            import types
            package = types.ModuleType(alias)
            package.__path__ = [str(tools_dir)]
            sys.modules[alias] = package
            init_spec = importlib.util.spec_from_file_location(
                f"{alias}.project_init", tools_dir / "project_init.py",
                submodule_search_locations=None)
            module = importlib.util.module_from_spec(init_spec)
            sys.modules[f"{alias}.project_init"] = module
            init_spec.loader.exec_module(module)
            return module
        return sys.modules[f"{alias}.project_init"]

    def load_foundation_module(self, name: str):
        tools_dir = self.foundation / "file_tools"
        alias = f"_ui_fix_tools_{self._fixture_token}"
        full = f"{alias}.{name}"
        if full in sys.modules:
            return sys.modules[full]
        import types
        if alias not in sys.modules:
            package = types.ModuleType(alias)
            package.__path__ = [str(tools_dir)]
            sys.modules[alias] = package
        spec = importlib.util.spec_from_file_location(full, tools_dir / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
        return module

    def load_mcp(self, *, suffix=""):
        purge_shared_ui_modules()
        mcp_name = f"ui_mcp_{self._fixture_token}_{suffix}"
        self._injected_modules.append(mcp_name)
        return load_module(mcp_name, self.ui / "mcp_server.py")

    def init_projects(self):
        project_init = self._project_init()
        project_init.create(self.foundation, "procurement-demo", "采购演示",
                            "UI 工具隔离测试项目",
                            expected_root=self.project_p1, directory_name=self.project_p1.name)
        project_init.create(self.foundation, "meeting-b", "会议助手",
                            "跨项目凭证隔离测试",
                            expected_root=self.project_p2, directory_name=self.project_p2.name)

    # -- in-process server -------------------------------------------------

    def connect(self, *, import_roots=(), between_passes=None, clock=None,
                allow_write=False):
        install_path = str(self.ui)
        if install_path in sys.path:
            sys.path.remove(install_path)
        sys.path.insert(0, install_path)
        mcp = self.load_mcp(suffix=f"conn{len(import_roots)}{'w' if allow_write else ''}")
        runtime = mcp.load_shared(self.foundation)
        tools = mcp.UiTools(runtime, allow_write=allow_write,
                            import_roots=import_roots,
                            clock=clock or (lambda: self.now),
                            between_closure_passes=between_passes)
        self.server = mcp.McpServer(tools, runtime=runtime)
        self.mcp = mcp
        self.initialize()
        return self.server

    def rpc(self, method, params=None, identifier=1):
        message = {"jsonrpc": "2.0", "id": identifier, "method": method,
                   "params": params or {}}
        return self.server.handle(message)

    def initialize(self, identifier=1, protocol=MODERN_PROTOCOL):
        return self.rpc("initialize", {"protocolVersion": protocol, "capabilities": {}},
                        identifier)

    def list_tools(self, identifier=2):
        return self.rpc("tools/list", {}, identifier)["result"]["tools"]

    def call(self, name, arguments, *, identifier=3, error=False):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments}, identifier)
        self.assertNotIn("error", response, response)
        result = response["result"]
        self.assertEqual(result["isError"], error, result)
        return json.loads(result["content"][0]["text"])

    def read_context(self, project=None, identifier=3, **arguments):
        return self.call(self.mcp.READ_CONTEXT,
                         {"project_path": str(project or self.project_p1), **arguments},
                         identifier=identifier)

    def prepare(self, read_id, request_id, mode="empty", *, project=None,
                identifier=6, history_revision=None, import_roots=(),
                allow_write=True, **arguments):
        if self.server is None:
            self.connect(import_roots=import_roots, allow_write=allow_write)
        payload = {"project_path": str(project or self.project_p1),
                   "read_id": read_id, "request_id": request_id, "mode": mode}
        if history_revision is not None:
            payload["history_revision"] = history_revision
        payload.update(arguments)
        return self.call(self.mcp.PREPARE, payload, identifier=identifier)

    def inspect_candidate(self, revision_id, *, project=None, identifier=7):
        return self.call(self.mcp.INSPECT,
                         {"project_path": str(project or self.project_p1),
                          "target": "candidate", "revision_id": revision_id},
                         identifier=identifier)

    def inspect(self, target, *, project=None, identifier=4, **arguments):
        return self.call(self.mcp.INSPECT,
                         {"project_path": str(project or self.project_p1),
                          "target": target, **arguments}, identifier=identifier)

    def read_history(self, *, project=None, identifier=5, **arguments):
        return self.call(self.mcp.READ_HISTORY,
                         {"project_path": str(project or self.project_p1), **arguments},
                         identifier=identifier)

    def accept(self, revision_id, inspection_id, request_id, delete_paths=(), *,
               project=None, identifier=8):
        return self.call(self.mcp.ACCEPT, {
            "project_path": str(project or self.project_p1),
            "revision_id": revision_id,
            "inspection_id": inspection_id,
            "request_id": request_id,
            "delete_paths": list(delete_paths),
        }, identifier=identifier)

    def recover(self, transaction_id, request_id, action, *, project=None,
                identifier=9):
        return self.call(self.mcp.RECOVER, {
            "project_path": str(project or self.project_p1),
            "transaction_id": transaction_id,
            "request_id": request_id,
            "action": action,
        }, identifier=identifier)

    # -- filesystem helpers ------------------------------------------------

    def write(self, project: Path, relative: str, content) -> str:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_bytes(content)
        return sha(path.read_bytes())

    def write_inputs(self, project=None):
        project = project or self.project_p1
        self.write(project, "docs/requirements.md",
                   "# 源需求\n\n- REQ-001：查看采购列表。\n")
        self.write(project, "docs/PRD.md",
                   "---\nartifact_kind: prd\nstatus: Draft\n---\n\n# PRD Draft\n\n待完善。\n")

    def write_import_case(self, root=None):
        root = root or self.import_parent
        (root / "assets").mkdir(parents=True, exist_ok=True)
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(
            "<!doctype html><script src=\"assets/app.js\"></script>"
            "<link rel=\"stylesheet\" href=\"assets/styles.css\">", encoding="utf-8")
        (root / "assets/app.js").write_text("console.log('I1 V1');\n", encoding="utf-8")
        (root / "assets/styles.css").write_text("body{}\n", encoding="utf-8")
        (root / "README.md").write_text("# 外部演示说明\n", encoding="utf-8")
        (root / "docs/ui-style.md").write_text("# 外部设计说明 Draft\n", encoding="utf-8")
        return root

    def import_source(self, root=None, *, files=None):
        root = root or self.import_parent
        files = files or ["index.html", "assets/app.js", "assets/styles.css",
                          "README.md", "docs/ui-style.md"]
        return {"root": str(root), "files": files, "entrypoint": "index.html",
                "design_path": "docs/ui-style.md", "readme_path": "README.md"}

    # -- static H (history) fixtures; never save-success evidence ----------

    def build_static_version(self, project, member_files, *, created_at, sources=None,
                             restored_from=None, origin="accepted",
                             artifact_root=DEFAULT_ROOT, entrypoint=None):
        """member_files: {project-relative path: bytes or str}. Hand-built."""
        entrypoint = entrypoint or f"{artifact_root}/index.html"
        files = [{"path": path, "sha256": sha(raw if isinstance(raw, bytes)
                                              else raw.encode("utf-8"))}
                 for path, raw in sorted(member_files.items())]
        packet = {"schema_version": 1, "project_id": "procurement-demo",
                  "artifact_root": artifact_root, "entrypoint": entrypoint,
                  "design_path": DESIGN_PATH, "readme_path": f"{artifact_root}/README.md",
                  "files": files, "sources": sources or [],
                  "restored_from": restored_from}
        revision = hashlib.sha256(canonical(packet)).hexdigest()
        version_dir = project / STATE_DIR / "versions" / revision
        tree = version_dir / "tree"
        for path, raw in member_files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        manifest = {"schema_version": 1, "entrypoint": entrypoint,
                    "files": sorted(
                        ({"path": item["path"], "sha256": item["sha256"]}
                         for item in files), key=lambda item: item["path"])}
        manifest_raw = json.dumps(manifest, ensure_ascii=False,
                                  separators=(",", ":")).encode("utf-8")
        manifest_target = tree / MANIFEST_PATH
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_bytes(manifest_raw)
        meta = {"schema_version": 1, "packet": packet, "revision_sha256": revision,
                "manifest_sha256": sha(manifest_raw), "created_at": created_at,
                "origin": origin, "diagnostics": []}
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / "version.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return revision

    def make_managed_current(self, project, revision, member_files, *,
                            artifact_root=DEFAULT_ROOT, entrypoint=None):
        """Materialize a hand-built B1 current collection from H fixtures."""
        entrypoint = entrypoint or f"{artifact_root}/index.html"
        for path, raw in member_files.items():
            self.write(project, path, raw)
        files = sorted(({"path": path, "sha256": sha(raw if isinstance(raw, bytes)
                                                      else raw.encode("utf-8"))}
                        for path, raw in member_files.items()), key=lambda item: item["path"])
        manifest_raw = json.dumps(
            {"schema_version": 1, "entrypoint": entrypoint, "files": files},
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.write(project, MANIFEST_PATH, manifest_raw.decode("utf-8"))
        pointer = {"schema_version": 1, "project_id": "procurement-demo",
                   "revision_sha256": revision, "manifest_sha256": sha(manifest_raw),
                   "artifact_root": artifact_root,
                   "last_transaction_id": None, "last_request_id": None}
        self.write(project, f"{STATE_DIR}/current.json",
                   json.dumps(pointer, ensure_ascii=False))

    def build_static_transaction(self, project, *, transaction_id, request_id="Q-0001",
                                 mode="current", targets, active=False, stage=None,
                                 receipt=None, project_id="procurement-demo",
                                 revision_id=None, version=None, delete_paths=None,
                                 base_digest=None, candidate_digest=None):
        """Hand-built read-only transaction evidence; never produced by accept.

        targets items: {"path": project-relative, "before": bytes|None,
                        "after": bytes|None}; None records a missing blob.
        Materializes before/after under transactions/<T>/ and plan/pointer/receipt.
        """
        txn_dir = project / STATE_DIR / "transactions" / transaction_id
        target_entries = []
        for item in targets:
            relative = item["path"]
            states = {}
            for phase in ("before", "after"):
                raw = item.get(phase)
                if raw is None:
                    states[phase] = {"state": "missing", "sha256": "missing"}
                else:
                    blob = txn_dir / phase / relative
                    blob.parent.mkdir(parents=True, exist_ok=True)
                    blob.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
                    states[phase] = {"state": "present", "sha256": sha(raw if isinstance(raw, bytes)
                                                                        else raw.encode("utf-8"))}
            target_entries.append({"path": relative, "before": states["before"],
                                   "after": states["after"]})
        plan = {"schema_version": 1, "project_id": project_id,
                "transaction_id": transaction_id, "request_id": request_id, "mode": mode,
                "revision_id": revision_id or "R-" + "0" * 32,
                "base_digest": base_digest or "b" * 64,
                "candidate_digest": candidate_digest or "c" * 64,
                "sources": [], "targets": target_entries, "version": version,
                "delete_paths": delete_paths or []}
        plan["plan_sha256"] = sha(canonical(plan))
        txn_dir.mkdir(parents=True, exist_ok=True)
        (txn_dir / "plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        if active:
            pointer = {"schema_version": 1, "transaction_id": transaction_id,
                       "stage": stage or "staged"}
            self.write(project, f"{STATE_DIR}/transaction.json",
                       json.dumps(pointer, ensure_ascii=False))
        if receipt is not None:
            record = {"schema_version": 1, **receipt}
            self.write(project, f"{STATE_DIR}/requests/{request_id}.json",
                       json.dumps(record, ensure_ascii=False))
        return transaction_id

    def v1_files(self):
        return {
            f"{DEFAULT_ROOT}/index.html": "<!doctype html><title>V1</title>",
            f"{DEFAULT_ROOT}/assets/app.js": "const v='V1';\n",
            f"{DEFAULT_ROOT}/assets/styles.css": "body{color:black}\n",
            f"{DEFAULT_ROOT}/assets/old.bin": bytes(range(32)),
            f"{DEFAULT_ROOT}/README.md": "# 演示 V1\n\n未做浏览器验收。\n",
            DESIGN_PATH: "# UI 设计说明 Draft V1\n",
        }

    # -- stdio subprocess --------------------------------------------------

    def scrubbed_env(self, *, isolated=False, extra=None):
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}}
        env["PYTHONNOUSERSITE"] = "1"
        if extra:
            env.update(extra)
        env["_UI_ISOLATED"] = "1" if isolated else "0"
        return env

    def spawn(self, *, allow_write=False, import_roots=(), isolated=False, cwd=None,
              extra_args=(), extra_env=None):
        flags = ["-B"]
        if isolated:
            flags = ["-I", "-S", "-B"]
        command = [sys.executable, *flags, str(self.ui / "mcp_server.py"),
                   "--foundation", str(self.foundation)]
        if allow_write:
            command.append("--allow-write")
        for root in import_roots:
            command.extend(["--import-root", str(root)])
        command.extend(extra_args)
        child = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(cwd or self.root),
            env=self.scrubbed_env(isolated=isolated, extra=extra_env))
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        return child

    def rpc_child(self, child, message, timeout=5):
        child.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        child.stdin.flush()
        self.assertTrue(select.select([child.stdout], [], [], timeout)[0], "stdio 响应超时")
        return json.loads(child.stdout.readline())

    def initialize_child(self, child, identifier=1):
        response = self.rpc_child(child, {"jsonrpc": "2.0", "id": identifier,
                                          "method": "initialize",
                                          "params": {"protocolVersion": MODERN_PROTOCOL,
                                                     "capabilities": {}}})
        child.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()
        return response

    def call_child(self, child, identifier, name, arguments):
        response = self.rpc_child(child, {"jsonrpc": "2.0", "id": identifier,
                                          "method": "tools/call",
                                          "params": {"name": name, "arguments": arguments}})
        return response["result"]["isError"], json.loads(
            response["result"]["content"][0]["text"])

    def shutdown(self, child, assert_zero=True):
        child.stdin.close()
        code = child.wait(timeout=5)
        stderr_text = child.stderr.read().decode("utf-8")
        child.stdout.close()
        child.stderr.close()
        if assert_zero:
            self.assertEqual(code, 0, stderr_text)
        return code, stderr_text
