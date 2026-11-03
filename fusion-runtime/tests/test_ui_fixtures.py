"""S5-00 / UI-T01: fixture repeatability and controlled foundation loading."""

import json
import os
from pathlib import Path
import shutil

from ui_test_support import (
    REQUIREMENTS_SOURCE,
    UI_SOURCE,
    UiFixture,
    load_module,
    tree_snapshot,
)


SHARED_FILES = (
    "__init__.py", "check_foundation.py", "project_state.py", "project_init.py",
    "requirements.py", "project_info.py", "artifact_records.py",
    "confirmation_records.py", "recovery.py",
)


class FixtureBaselineTests(UiFixture):
    def test_fixture_is_repeatable_and_projects_use_init_capability(self):
        first = tree_snapshot(self.projects)
        spare = self.spare = UiFixture()
        spare.setUp()
        self.addCleanup(spare.doCleanups)
        self.assertNotEqual(str(self.root), str(spare.root))
        self.assertTrue((self.project_p1 / "project.json").is_file())
        data = json.loads((self.project_p1 / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(data["project_id"], "procurement-demo")
        loader = self.load_foundation_module("project_init")
        loaded = loader.load_project(self.project_p1, "procurement-demo")
        self.assertEqual(loaded["project_id"], "procurement-demo")
        self.assertTrue((spare.project_p1 / "project.json").is_file())
        spare.doCleanups()
        self.assertTrue(self.project_p1.exists())
        self.assertEqual(first, tree_snapshot(self.projects))

    def test_business_parent_is_outside_git_and_temp(self):
        self.assertNotIn(str(self.root), str(UI_SOURCE))
        self.assertTrue(str(self.projects).startswith(str(self.root)))
        self.assertFalse((self.projects / ".git").exists())


class ControlledLoaderTests(UiFixture):
    def test_load_shared_uses_temp_foundation_modules(self):
        mcp = self.load_mcp(suffix="ok")
        import sys
        install_path = str(self.ui)
        sys.path.insert(0, install_path)
        self.addCleanup(sys.path.remove, install_path)
        runtime = mcp.load_shared(self.foundation)
        for name in ("check_foundation", "project_state", "project_init", "requirements",
                     "project_info", "artifact_records", "confirmation_records", "recovery"):
            module_file = Path(getattr(runtime.modules, name).__file__).resolve()
            self.assertTrue(str(module_file).startswith(str(self.foundation)),
                            (name, module_file))
            self.assertEqual(module_file.name, f"{name}.py")
        for name in SHARED_FILES:
            self.assertTrue((self.foundation / "file_tools" / name).is_file())
        self.assertEqual(runtime.projects_root, self.projects.resolve())
        self.assertEqual(runtime.config["schema_version"], 1)

    def test_missing_shared_source_is_dependency_missing(self):
        (self.foundation / "file_tools/recovery.py").unlink()
        mcp = self.load_mcp(suffix="miss")
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "dependency_missing")

    def test_changed_shared_source_is_dependency_changed(self):
        target = self.foundation / "file_tools/requirements.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        mcp = self.load_mcp(suffix="chg")
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "dependency_changed")

    def test_changed_role_doc_template_is_dependency_changed(self):
        for relative in ("ui-design.md", "agent-file-workflow.md",
                         "templates/ui-style-template.md"):
            with self.subTest(relative):
                spare = UiFixture()
                spare.setUp()
                self.addCleanup(spare.doCleanups)
                path = spare.ui / relative
                path.write_bytes(path.read_bytes() + b"\nchange\n")
                mcp = spare.load_mcp(suffix="doc")
                with self.assertRaises(Exception) as caught:
                    mcp.load_shared(spare.foundation)
                self.assertEqual(caught.exception.code, "dependency_changed")

    def test_runtime_source_tamper_is_dependency_changed(self):
        target = self.ui / "mcp_server.py"
        target.write_bytes(target.read_bytes() + b"\n# unauthorized runtime edit\n")
        mcp = self.load_mcp(suffix="rt")
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "dependency_changed")

    def test_missing_config_and_lock_fail_closed(self):
        mcp = self.load_mcp(suffix="cfg")
        (self.foundation / "config/local.json").unlink()
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertIn(caught.exception.code, {"dependency_missing", "foundation_invalid"})

    def test_broken_and_divergent_methods_links(self):
        mcp = self.load_mcp(suffix="link")
        link = self.ui / "methods/develop-helper"
        link.unlink()
        link.symlink_to(self.foundation, target_is_directory=True)
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "methods_invalid")

        spare = UiFixture()
        spare.setUp()
        self.addCleanup(spare.doCleanups)
        other = spare.root / "other-upstream"
        other.mkdir()
        spare_link = spare.ui / "methods/develop-helper"
        spare_link.unlink()
        spare_link.symlink_to(other, target_is_directory=True)
        spare_mcp = spare.load_mcp(suffix="link2")
        with self.assertRaises(Exception) as caught:
            spare_mcp.load_shared(spare.foundation)
        self.assertEqual(caught.exception.code, "methods_invalid")

    def test_overlapping_roots_rejected(self):
        self.config["projects_root"] = str(self.foundation / "inside")
        (self.foundation / "inside").mkdir()
        self.write_config()
        self.relock_upstream()
        mcp = self.load_mcp(suffix="ov")
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "foundation_invalid")

    def test_upstream_drift_is_foundation_invalid(self):
        (self.upstream / "drift.md").write_text("drift", encoding="utf-8")
        mcp = self.load_mcp(suffix="drift")
        with self.assertRaises(Exception) as caught:
            mcp.load_shared(self.foundation)
        self.assertEqual(caught.exception.code, "foundation_invalid")

    def test_reading_creates_no_files_or_bytecode(self):
        before = tree_snapshot(self.foundation)
        before_ui = tree_snapshot(self.ui)
        self.connect()
        self.initialize()
        self.read_context()
        after = tree_snapshot(self.foundation)
        after_ui = tree_snapshot(self.ui)
        self.assertEqual(before, after)
        self.assertEqual(before_ui, after_ui)
        pycache = list(self.ui.rglob("__pycache__")) + list(self.foundation.rglob("__pycache__"))
        self.assertEqual(pycache, [])

    def test_fixture_excludes_real_source_and_candidate_content(self):
        installed = list(self.ui.rglob("*"))
        self.assertFalse(any("buzz-develop-helper" in str(item) for item in installed))
        self.assertFalse(any(str(item).startswith(str(UI_SOURCE)) for item in installed))
        self.assertFalse(any(str(item).startswith(str(REQUIREMENTS_SOURCE)) for item in installed))
