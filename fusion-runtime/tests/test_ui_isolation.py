"""AC5-14 gate-1: scrubbed new-process run, no-fallback loading, zero side effects.

The read-only mainline is driven in a real ``-I -S -B`` subprocess whose
PYTHONPATH points at a hostile decoy directory containing same-name
``shared_loader.py`` / ``file_tools`` modules and a ``sitecustomize.py``. Any
decoy import records a sentinel and raises. Success therefore proves the
process used the controlled UI install, ignored PYTHONPATH/user-site startup
hooks, wrote no bytecode, and never fell back to workspace sources.
"""

import os

from test_ui_accept import candidate_files, edit_candidate, request_id
from test_ui_recovery import RecoveryFixture
from ui_test_support import tree_snapshot


DECOY_LOADER = (
    "import os, pathlib\n"
    "_sentinel = os.environ.get('UI_DECOY_SENTINEL')\n"
    "if _sentinel:\n"
    "    pathlib.Path(_sentinel).write_text('decoy-loader', encoding='utf-8')\n"
    "raise RuntimeError('hostile decoy shared_loader must never import')\n"
)

DECOY_CONTEXT = (
    "import os, pathlib\n"
    "_sentinel = os.environ.get('UI_DECOY_SENTINEL')\n"
    "if _sentinel:\n"
    "    pathlib.Path(_sentinel).write_text('decoy-context', encoding='utf-8')\n"
    "raise RuntimeError('hostile decoy file_tools.context must never import')\n"
)

DECOY_SITECUSTOMIZE = (
    "import os, pathlib\n"
    "_sentinel = os.environ.get('UI_DECOY_SENTINEL')\n"
    "if _sentinel:\n"
    "    pathlib.Path(_sentinel).write_text('decoy-sitecustomize', encoding='utf-8')\n"
)


def has_bytecode(root):
    for current, dirs, files in os.walk(root):
        if "__pycache__" in dirs or any(name.endswith((".pyc", ".pyo")) for name in files):
            return True
    return False


class ScrubbedProcessTests(RecoveryFixture):
    def plant_decoy(self):
        decoy = self.root / "decoy"
        decoy.mkdir(exist_ok=True)
        (decoy / "shared_loader.py").write_text(DECOY_LOADER, encoding="utf-8")
        (decoy / "sitecustomize.py").write_text(DECOY_SITECUSTOMIZE, encoding="utf-8")
        package_dir = decoy / "file_tools"
        package_dir.mkdir(exist_ok=True)
        (package_dir / "__init__.py").write_text(DECOY_LOADER, encoding="utf-8")
        (package_dir / "context.py").write_text(DECOY_CONTEXT, encoding="utf-8")
        return decoy

    def test_isolated_mainline_ignores_decoy_and_is_bytecode_free(self):
        decoy = self.plant_decoy()
        sentinel = self.root / "decoy-hit"
        child = self.spawn(
            isolated=True,
            extra_env={"PYTHONPATH": str(decoy),
                       "UI_DECOY_SENTINEL": str(sentinel)})
        response = self.initialize_child(child)
        self.assertEqual(response["result"]["serverInfo"]["name"],
                         "ui-designer-file-tools")

        before = tree_snapshot(self.project_p1)
        _error, context = self.call_child(
            child, 3, "ui_read_context", {"project_path": str(self.project_p1)})
        self.assertFalse(_error, context)
        self.assertEqual(context["state"], "empty")
        _error, inspect = self.call_child(
            child, 4, "ui_inspect",
            {"project_path": str(self.project_p1), "target": "current"})
        self.assertFalse(_error, inspect)
        _error, history = self.call_child(
            child, 5, "ui_read_history", {"project_path": str(self.project_p1)})
        self.assertFalse(_error, history)
        self.assertEqual(history["versions"], [])

        _code, stderr_text = self.shutdown(child)
        self.assertEqual(stderr_text, "")
        self.assertFalse(sentinel.exists(),
                         "净化进程导入了 PYTHONPATH 同名/启动诱导模块")
        self.assertEqual(before, tree_snapshot(self.project_p1),
                         "只读主线产生了文件副作用")
        self.assertFalse(has_bytecode(self.ui), "-B 下 UI 安装副本不得产生字节码")

    def test_isolated_recovery_resume_uses_controlled_transaction_module(self):
        decoy = self.plant_decoy()
        sentinel = self.root / "decoy-hit-recovery"
        (decoy / "file_tools" / "transactions.py").write_text(
            "import os, pathlib\n"
            "_s = os.environ.get('UI_DECOY_SENTINEL')\n"
            "if _s:\n"
            "    pathlib.Path(_s).write_text('decoy-transactions', encoding='utf-8')\n"
            "raise RuntimeError('hostile decoy transactions must never import')\n",
            encoding="utf-8")
        interrupted, _prepared = self.interrupt_accept("member_after:0")
        transaction_id = interrupted["error"]["details"]["transaction_id"]
        child = self.spawn(
            isolated=True, allow_write=True,
            extra_env={"PYTHONPATH": str(decoy), "UI_DECOY_SENTINEL": str(sentinel)})
        self.initialize_child(child)
        is_error, recovered = self.call_child(
            child, 3, "ui_recover_revision",
            {"project_path": str(self.project_p1), "transaction_id": transaction_id,
             "request_id": request_id(), "action": "resume"})
        self.assertFalse(is_error, recovered)
        self.assertEqual(recovered["write_outcome"], "saved")
        _error, current = self.call_child(
            child, 4, "ui_inspect",
            {"project_path": str(self.project_p1), "target": "current"})
        self.assertEqual(current["state"], "stable")
        _code, stderr_text = self.shutdown(child)
        self.assertEqual(stderr_text, "")
        self.assertFalse(sentinel.exists())
        self.assertFalse(has_bytecode(self.ui))
        self.assertFalse(has_bytecode(self.foundation / "file_tools"),
                         "-B 下受信 foundation 不得产生字节码")

    def test_isolated_process_rejects_unauthorized_import_source(self):
        decoy = self.plant_decoy()
        sentinel = self.root / "decoy-hit-2"
        child = self.spawn(
            isolated=True,
            extra_env={"PYTHONPATH": str(decoy),
                       "UI_DECOY_SENTINEL": str(sentinel)})
        self.initialize_child(child)
        import_source = {"root": str(self.outside),
                         "files": ["index.html"], "entrypoint": "index.html",
                         "design_path": "index.html", "readme_path": "index.html"}
        is_error, payload = self.call_child(
            child, 6, "ui_read_context",
            {"project_path": str(self.project_p1), "import_source": import_source})
        self.assertTrue(is_error, payload)
        self.assertEqual(payload["error"]["code"], "path_not_allowed")
        self.shutdown(child)
        self.assertFalse(sentinel.exists())

    def test_isolated_allow_write_mainline_uses_controlled_modules(self):
        """5C: prepare/inspect/accept work in -I -S -B; hostile workspace
        and transaction modules must never be imported."""
        decoy = self.plant_decoy()
        workspace_decoy = decoy / "file_tools" / "workspace.py"
        sentinel = self.root / "decoy-hit-3"
        workspace_decoy.write_text(
            "import os, pathlib\n"
            "_s = os.environ.get('UI_DECOY_SENTINEL')\n"
            "if _s:\n"
            "    pathlib.Path(_s).write_text('decoy-workspace', encoding='utf-8')\n"
            "raise RuntimeError('hostile decoy file_tools.workspace must never import')\n",
            encoding="utf-8")
        (decoy / "file_tools" / "transactions.py").write_text(
            "raise RuntimeError('hostile decoy file_tools.transactions must never import')\n",
            encoding="utf-8")
        self.write_inputs()
        child = self.spawn(
            isolated=True, allow_write=True,
            extra_env={"PYTHONPATH": str(decoy),
                       "UI_DECOY_SENTINEL": str(sentinel)})
        self.initialize_child(child)
        _error, context = self.call_child(
            child, 3, "ui_read_context", {"project_path": str(self.project_p1)})
        self.assertFalse(_error, context)
        is_error, prepared = self.call_child(
            child, 4, "ui_prepare_revision",
            {"project_path": str(self.project_p1), "read_id": context["read_id"],
             "request_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "mode": "empty"})
        self.assertFalse(is_error, prepared)
        self.assertEqual(prepared["write_outcome"], "prepared")
        self.assertTrue(os.path.isdir(prepared["workspace_path"]))
        edit_candidate(prepared["workspace_path"], candidate_files())
        is_error, inspected = self.call_child(
            child, 5, "ui_inspect",
            {"project_path": str(self.project_p1), "target": "candidate",
             "revision_id": prepared["revision_id"]})
        self.assertFalse(is_error, inspected)
        is_error, accepted = self.call_child(
            child, 6, "ui_accept_revision",
            {"project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
             "inspection_id": inspected["inspection_id"], "request_id": request_id(),
             "delete_paths": []})
        self.assertFalse(is_error, accepted)
        self.assertEqual(accepted["write_outcome"], "saved")
        _error, current = self.call_child(
            child, 7, "ui_inspect",
            {"project_path": str(self.project_p1), "target": "current"})
        self.assertEqual(current["state"], "stable")
        _error, history = self.call_child(
            child, 8, "ui_read_history", {"project_path": str(self.project_p1)})
        self.assertEqual(len(history["versions"]), 1)
        _code, stderr_text = self.shutdown(child)
        self.assertEqual(stderr_text, "")
        self.assertFalse(sentinel.exists(),
                         "净化进程导入了 PYTHONPATH 同名 file_tools.workspace")
        self.assertFalse(has_bytecode(self.ui), "-B 下 UI 安装副本不得产生字节码")
