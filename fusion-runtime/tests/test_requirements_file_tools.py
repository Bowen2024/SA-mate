"""The copied file tools work independently and preserve filesystem behavior."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

_HERE = Path(__file__).resolve()
if str(_HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(_HERE.parents[1]))

from workflows.requirements.file_tools import check_foundation, project_init, requirements


class LocalFileToolsTests(unittest.TestCase):
    IDENTIFIER = "voice-meetup"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="requirements-local-tools-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.foundation = self.root / "foundation"
        self.source = self.root / "source"
        self.projects = self.root / "projects"
        for directory in (self.foundation / "config", self.foundation / "methods",
                          self.source, self.projects):
            directory.mkdir(parents=True)
        (self.source / "rules.md").write_text("fixture source", encoding="utf-8")
        (self.foundation / "methods/develop-helper").symlink_to(self.source, target_is_directory=True)
        (self.foundation / "upstream-lock.json").write_text(
            json.dumps(check_foundation.snapshot(self.source)), encoding="utf-8",
        )
        self.config = {"schema_version": 1, "upstream_root": str(self.source),
                       "projects_root": str(self.projects),
                       "project_directories": {self.IDENTIFIER: "语音约碰面地点"}}
        self.write_config()
        self.project = self.projects / "语音约碰面地点"
        self.project.mkdir()

    def write_config(self):
        (self.foundation / "config/local.json").write_text(json.dumps(self.config), encoding="utf-8")

    def initialize(self):
        return project_init.initialize_existing(
            self.foundation, self.IDENTIFIER, "语音约碰面地点", "临时项目工具测试",
        )

    def tree(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() if p.is_file() else None
                for p in sorted(self.project.rglob("*"))}

    def test_package_loads_without_original_scripts_or_runtime_dependencies(self):
        package_parent = Path(project_init.__file__).resolve().parents[1]
        script = """
import json, pathlib, sys, types
sys.path.insert(0, sys.argv[1])
for name in ('project_init', 'requirements', 'project_state', 'check_foundation'):
    sys.modules[name] = types.ModuleType(name)
from file_tools import project_init, requirements, project_state, check_foundation
expected = pathlib.Path(sys.argv[1]) / 'file_tools'
assert all(pathlib.Path(m.__file__).parent == expected for m in (
    project_init, requirements, project_state, check_foundation))
assert requirements.project_context is project_init.context
assert project_init.project_state_lock is project_state.project_state_lock
assert not any(name.startswith('fusion_runtime') for name in sys.modules)
print('local package only')
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(package_parent)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "local package only")

    def test_existing_project_initialization_and_context_are_local_and_read_only(self):
        preview = project_init.plan_existing(self.foundation, self.IDENTIFIER, "语音约碰面地点", "工具测试")
        self.assertEqual(preview["path"], str(self.project))
        self.assertEqual(self.tree(), {})
        result = self.initialize()
        self.assertFalse(result["git_initialized"])
        self.assertEqual(set(self.tree()), {"README.md", "project.json", ".gitignore"})
        before = self.tree()
        context = requirements.context(self.foundation, self.IDENTIFIER)
        self.assertEqual(context["project_path"], str(self.project))
        self.assertEqual(context["documents"][-1]["sha256"], "missing")
        self.assertEqual(self.tree(), before)
        with self.assertRaisesRegex(ValueError, "非空"):
            self.initialize()
        self.assertEqual(self.tree(), before)

    def test_save_readback_history_and_noop_keep_exact_content(self):
        self.initialize()
        first = requirements.save_draft(self.foundation, self.IDENTIFIER, "# 测试需求\n第一版", "missing")
        old = (self.project / "docs/requirements.md").read_bytes()
        second = requirements.save_draft(self.foundation, self.IDENTIFIER, "# 测试需求\n第二版", first["sha256"])
        current = requirements.read_document(self.project, "docs/requirements.md")
        self.assertEqual((current["sha256"], current["content"]), (
            second["sha256"], "---\nstatus: Draft\napproval_verified: false\n---\n\n# 测试需求\n第二版\n",
        ))
        archive = requirements.read_document(self.project, f"docs/requirements-history/{first['sha256']}.md")
        self.assertEqual(archive["content"].encode("utf-8"), old)
        self.assertEqual(archive["sha256"], first["sha256"])
        before = self.tree()
        noop = requirements.save_draft(self.foundation, self.IDENTIFIER, "# 测试需求\n第二版", second["sha256"])
        self.assertFalse(noop["changed"])
        self.assertEqual(self.tree(), before)

    def test_stale_save_is_rejected_without_file_changes(self):
        self.initialize()
        requirements.save_draft(self.foundation, self.IDENTIFIER, "第一版", "missing")
        before = self.tree()
        with self.assertRaisesRegex(ValueError, "版本冲突"):
            requirements.save_draft(self.foundation, self.IDENTIFIER, "stale overwrite", "missing")
        self.assertEqual(self.tree(), before)

    def test_invalid_mapping_and_symlink_reads_or_writes_are_rejected(self):
        self.config["project_directories"][self.IDENTIFIER] = "../outside"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "单层目录名"):
            self.initialize()
        self.assertEqual(self.tree(), {})
        self.config["project_directories"][self.IDENTIFIER] = self.project.name
        self.write_config()
        self.initialize()
        (self.project / "docs").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "软链"):
            requirements.save_draft(self.foundation, self.IDENTIFIER, "escape", "missing")
        with self.assertRaisesRegex(ValueError, "软链"):
            requirements.read_document(self.project, "docs/rules.md")
        self.assertFalse((self.source / "requirements.md").exists())

    def test_source_drift_blocks_initialization_without_refreshing_baseline(self):
        locked = (self.foundation / "upstream-lock.json").read_bytes()
        (self.source / "rules.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "漂移"):
            self.initialize()
        self.assertEqual(self.tree(), {})
        self.assertEqual((self.foundation / "upstream-lock.json").read_bytes(), locked)

    def test_foreign_lock_is_preserved_on_save(self):
        self.initialize()
        lock = self.project / ".project-state.lock"
        lock.write_text("another writer", encoding="utf-8")
        before = self.tree()
        with self.assertRaisesRegex(ValueError, "锁已存在"):
            requirements.save_draft(self.foundation, self.IDENTIFIER, "draft", "missing")
        self.assertEqual(self.tree(), before)

    def test_direct_cli_uses_explicit_configuration_and_local_siblings(self):
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

        def run(module, *arguments, body=None):
            return subprocess.run([sys.executable, "-B", module.__file__, *arguments],
                                  input=body, capture_output=True, text=True, env=environment)

        missing = run(project_init, "inspect", self.IDENTIFIER)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--foundation", missing.stderr)
        command = ["--foundation", str(self.foundation), "init-existing", self.IDENTIFIER,
                   "--name", "语音约碰面地点", "--purpose", "CLI 工具测试"]
        preview = run(project_init, *command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(json.loads(preview.stdout)["status"], "planned_existing")
        self.assertEqual(self.tree(), {})
        applied = run(project_init, *command, "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        saved = run(requirements, "--foundation", str(self.foundation), "save-draft", self.IDENTIFIER,
                    "--expected-sha", "missing", "--apply", body="# CLI 需求\n测试材料")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        read = run(requirements, "--foundation", str(self.foundation), "context", self.IDENTIFIER)
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["documents"][-1]["sha256"], json.loads(saved.stdout)["sha256"])


if __name__ == "__main__":
    unittest.main()
