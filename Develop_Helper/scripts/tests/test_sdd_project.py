"""Exercise project creation through the CLI in disposable Harness directories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HARNESS_SOURCE = Path(__file__).resolve().parents[2]


class ProjectCreationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="sdd-project-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "harness"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        shutil.copy2(
            HARNESS_SOURCE / "scripts/sdd_project.py",
            self.root / "scripts/sdd_project.py",
        )
        for relative in (
            "templates/project/README.md",
            "templates/project/.sdd/experience.md",
            "templates/project/.sdd/work-log.md",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HARNESS_SOURCE / relative, destination)
        for specification in ("default", "custom"):
            directory = self.root / "harness-core/specification" / specification
            directory.mkdir(parents=True)
            (directory / "README.md").write_text("Test specification\n", encoding="utf-8")
        (self.root / "pycore").mkdir()
        (self.root / "pycore/sentinel.py").write_text("VALUE = 42\n", encoding="utf-8")
        self.projects = self.root / "Projects_Repo"
        self.projects.mkdir()
        self.registry_path = self.root / "project-registry.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "projects_root": "Projects_Repo",
                    "active_project_id": None,
                    "projects": [],
                }
            ) + "\n",
            encoding="utf-8",
        )

    def run_cli(
        self, *arguments: str, env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/sdd_project.py"), *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )

    def snapshot(self) -> dict[str, tuple[str, bytes | str]]:
        """Include siblings and symlink targets; never traverse symbolic links."""
        contents = {}
        for directory, directories, filenames in os.walk(self.workspace, followlinks=False):
            for name in directories + filenames:
                path = Path(directory) / name
                key = str(path.relative_to(self.workspace))
                if path.is_symlink():
                    contents[key] = ("symlink", os.readlink(path))
                elif path.is_dir():
                    contents[key] = ("directory", "")
                else:
                    contents[key] = ("file", path.read_bytes())
        return contents

    def assert_rejected_without_changes(self, *arguments: str) -> None:
        before = self.snapshot()
        result = self.run_cli(*arguments)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before, result.stdout + result.stderr)

    def test_all_explicit_specification_choices_for_supported_types(self) -> None:
        for project_type in ("web", "mobile", "api", "cli"):
            for specification in ("default", "custom", None):
                with self.subTest(project_type=project_type, specification=specification):
                    project_id = f"{project_type}-{specification or 'none'}"
                    selection = (
                        ["--no-specification"] if specification is None
                        else ["--specification", specification]
                    )
                    result = self.run_cli(
                        "new", project_id, "--name", "课堂项目",
                        "--type", project_type, *selection,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    project = self.projects / project_id
                    metadata = json.loads((project / ".sdd/project.json").read_text())
                    registry = json.loads(self.registry_path.read_text())
                    entry = next(p for p in registry["projects"] if p["id"] == project_id)
                    self.assertIn("specification", metadata)
                    self.assertIn("specification", entry)
                    for record in (metadata, entry):
                        self.assertEqual(record["specification"], specification)
                        self.assertEqual(record["name"], "课堂项目")
                        self.assertEqual(record["project_type"], project_type)
                    self.assertEqual(registry["active_project_id"], project_id)
                    self.assertEqual(entry["path"], f"Projects_Repo/{project_id}")
                    self.assertTrue((project / ".sdd/status.json").is_file())
                    self.assertTrue((project / "docs").is_dir())
                    self.assertEqual((project / "pycore").exists(), specification == "default")
                    if specification == "default":
                        self.assertEqual(
                            (project / "pycore/sentinel.py").read_text(), "VALUE = 42\n"
                        )

    def test_specification_selection_is_required_and_mutually_exclusive(self) -> None:
        for selection in ([], ["--specification", "default", "--no-specification"]):
            with self.subTest(selection=selection):
                self.assert_rejected_without_changes(
                    "new", "example", "--name", "Example", "--type", "web", *selection
                )

    def test_invalid_project_ids_are_rejected_before_writing(self) -> None:
        for project_id in ("", ".", "..", "../outside", "nested/project", "nested\\project",
                           str(self.workspace / "absolute-project")):
            with self.subTest(project_id=project_id):
                self.assert_rejected_without_changes(
                    "new", project_id, "--name", "Example", "--type", "web",
                    "--no-specification",
                )

    def test_occupied_project_directory_and_file_are_preserved(self) -> None:
        directory = self.projects / "existing-directory"
        (directory / "pycore").mkdir(parents=True)
        (directory / "pycore/user-code.py").write_text("USER_CODE = True\n")
        (self.projects / "existing-file").write_text("user content\n")
        for project_id in ("existing-directory", "existing-file"):
            with self.subTest(project_id=project_id):
                self.assert_rejected_without_changes(
                    "new", project_id, "--name", "Example", "--type", "web",
                    "--specification", "default",
                )

    def test_project_symlinks_are_not_followed_or_replaced(self) -> None:
        outside = self.workspace / "outside-project"
        outside.mkdir()
        (outside / "keep.txt").write_text("preserve me\n")
        (self.projects / "linked").symlink_to(outside, target_is_directory=True)
        (self.projects / "dangling").symlink_to(self.workspace / "missing")
        for project_id in ("linked", "dangling"):
            with self.subTest(project_id=project_id):
                self.assert_rejected_without_changes(
                    "new", project_id, "--name", "Example", "--type", "web",
                    "--no-specification",
                )

    def test_projects_root_symlink_cannot_escape_harness(self) -> None:
        outside = self.workspace / "outside-projects"
        outside.mkdir()
        self.projects.rmdir()
        self.projects.symlink_to(outside, target_is_directory=True)
        self.assert_rejected_without_changes(
            "new", "example", "--name", "Example", "--type", "web",
            "--no-specification",
        )

    def test_duplicate_registered_id_is_preserved_even_without_directory(self) -> None:
        registry = json.loads(self.registry_path.read_text())
        registry["active_project_id"] = "registered"
        registry["projects"] = [
            {"id": "registered", "name": "Original", "status": "in_progress",
             "path": "Projects_Repo/registered", "specification": "custom"}
        ]
        self.registry_path.write_text(json.dumps(registry) + "\n")
        self.assert_rejected_without_changes(
            "new", "registered", "--name", "Replacement", "--type", "web",
            "--specification", "default",
        )

    def test_missing_or_escaping_specification_is_rejected(self) -> None:
        outside = self.workspace / "outside-specification"
        outside.mkdir()
        for specification in ("missing", "../specification", str(outside)):
            with self.subTest(specification=specification):
                self.assert_rejected_without_changes(
                    "new", "example", "--name", "Example", "--type", "web",
                    "--specification", specification,
                )

    def test_missing_required_template_is_rejected_before_writing(self) -> None:
        (self.root / "templates/project/.sdd/work-log.md").unlink()
        self.assert_rejected_without_changes(
            "new", "example", "--name", "Example", "--type", "web",
            "--no-specification",
        )

    def test_no_specification_works_without_any_specification_or_pycore(self) -> None:
        shutil.rmtree(self.root / "harness-core/specification")
        shutil.rmtree(self.root / "pycore")
        result = self.run_cli(
            "new", "unrestricted", "--name", "No specifications", "--type", "mobile",
            "--no-specification",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        project = self.projects / "unrestricted"
        metadata = json.loads((project / ".sdd/project.json").read_text())
        self.assertIn("specification", metadata)
        self.assertIsNone(metadata["specification"])
        self.assertFalse((project / "pycore").exists())

    def test_remote_configuration_failure_is_explicit_and_cannot_be_overwritten(self) -> None:
        remote = str(self.workspace / "unavailable-remote.git")
        arguments = (
            "new", "remote-failure", "--name", "Remote failure", "--type", "web",
            "--no-specification", "--repo-url", remote,
        )
        environment = dict(os.environ, PATH="")
        result = self.run_cli(*arguments, env=environment)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("created and registered", result.stderr)
        self.assertIn("Git remote configuration failed", result.stderr)
        self.assertNotIn("Active project:", result.stdout)
        project = self.projects / "remote-failure"
        self.assertTrue((project / ".sdd/project.json").is_file())
        registry = json.loads(self.registry_path.read_text())
        self.assertEqual(registry["projects"][0]["repo_url"], remote)
        self.assertFalse((project / ".git").exists())
        self.assert_rejected_without_changes(*arguments)

    @unittest.skipUnless(shutil.which("git"), "Git is unavailable")
    def test_repo_url_is_recorded_and_configures_local_origin(self) -> None:
        # This path does not exist: configuring origin requires no remote access.
        remote = str(self.workspace / "unavailable-remote.git")
        result = self.run_cli(
            "new", "remote-project", "--name", "Remote", "--type", "web",
            "--no-specification", "--repo-url", remote,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        project = self.projects / "remote-project"
        origin = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=project,
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(origin.returncode, 0, origin.stderr)
        self.assertEqual(origin.stdout.strip(), remote)
        self.assertFalse(Path(remote).exists())
        metadata = json.loads((project / ".sdd/project.json").read_text())
        registry = json.loads(self.registry_path.read_text())
        self.assertEqual(metadata["repo_url"], remote)
        self.assertEqual(registry["projects"][0]["repo_url"], remote)


    def make_external_source(self) -> Path:
        source = self.workspace / "existing-app"
        source.mkdir()
        (source / "app.py").write_text("print('existing business')\n")
        (source / "README.md").write_text("Existing README\n")
        (source / "AGENTS.md").write_text("Existing entry\n")
        (source / "pycore").mkdir()
        (source / "pycore/owned.py").write_text("EXISTING = True\n")
        return source

    def onboard_args(self, source: Path, mode: str = "copy") -> tuple[str, ...]:
        return ("onboard", "imported", "--name", "Existing", "--type", "api",
                "--from-path", str(source), "--mode", mode, "--specification", "default")

    def test_onboard_copy_preserves_source_code_and_entries_without_default_runtime(self) -> None:
        source = self.make_external_source()
        (source / "node_modules").mkdir()
        (source / "node_modules/cache.js").write_text("temporary")
        (source / "asset-link").symlink_to("app.py")
        before = self.snapshot()
        result = self.run_cli(*self.onboard_args(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        for key, value in before.items():
            if key.startswith("existing-app/"):
                self.assertEqual(after[key], value)
        target = self.projects / "imported"
        for rel in ("app.py", "README.md", "AGENTS.md", "pycore/owned.py"):
            self.assertEqual((target / rel).read_bytes(), (source / rel).read_bytes())
        self.assertFalse((target / "node_modules").exists())
        self.assertFalse((target / "pycore/sentinel.py").exists())
        self.assertTrue((target / "asset-link").is_symlink())
        meta = json.loads((target / ".sdd/project.json").read_text())
        self.assertEqual(meta['source'], 'onboarded')
        self.assertEqual(meta['specification'], 'default')
        self.assertFalse(json.loads((target / '.sdd/status.json').read_text())['development_ready'])
        self.assert_rejected_without_changes(*self.onboard_args(source))

    def test_onboard_register_existing_target(self) -> None:
        source = self.make_external_source()
        target = self.projects / 'imported'
        source.rename(target)
        result = self.run_cli(*self.onboard_args(target, 'register'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((target / 'app.py').read_text(), "print('existing business')\n")
        self.assertEqual(json.loads(self.registry_path.read_text())['active_project_id'], 'imported')

    def test_onboard_rejects_wrong_location_metadata_and_symlink_before_writing(self) -> None:
        source = self.make_external_source()
        self.assert_rejected_without_changes(*self.onboard_args(source, 'register'))
        self.assert_rejected_without_changes(*self.onboard_args(self.root))
        self.assert_rejected_without_changes(*self.onboard_args(self.workspace))
        (source / '.sdd').mkdir()
        (source / '.sdd/project.json').write_text('{"id":"legacy"}')
        self.assert_rejected_without_changes(*self.onboard_args(source))
        (source / '.sdd/project.json').unlink()
        (source / '.sdd/project.json').symlink_to(self.registry_path)
        self.assert_rejected_without_changes(*self.onboard_args(source))

    @unittest.skipUnless(shutil.which('git'), 'Git is unavailable')
    def test_onboard_preserves_git_origin_and_rejects_conflicting_remote(self) -> None:
        source = self.make_external_source()
        for args in [('init', '-b', 'custom'), ('remote', 'add', 'origin', 'https://example.invalid/source.git')]:
            subprocess.run(['git', *args], cwd=source, capture_output=True, check=True)
        # Runtime filtering must not discard an identically named Git ref file.
        (source / '.git/refs/heads/venv').write_text('0' * 40 + '\n')
        self.assert_rejected_without_changes(*self.onboard_args(source), '--repo-url', 'https://example.invalid/other.git')
        result = self.run_cli(*self.onboard_args(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.projects / 'imported'
        self.assertEqual((target / '.git/config').read_bytes(), (source / '.git/config').read_bytes())
        self.assertTrue((target / '.git/refs/heads/venv').exists())
        self.assertEqual(json.loads((target / '.sdd/project.json').read_text())['repo_url'], 'https://example.invalid/source.git')

    def create_simple_project(self, project_id: str) -> Path:
        result = self.run_cli('new', project_id, '--name', project_id, '--type', 'cli', '--no-specification')
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.projects / project_id

    def test_remove_preserves_other_project_and_frees_id_for_recreation(self) -> None:
        target = self.create_simple_project('first')
        (target / 'data.txt').write_text('recover this')
        self.create_simple_project('second')
        old = json.loads(self.registry_path.read_text())
        backup = self.workspace / 'archive-first'
        result = self.run_cli('remove', 'first', '--backup-dir', str(backup))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual((backup / 'first/data.txt').read_text(), 'recover this')
        registry = json.loads(self.registry_path.read_text())
        self.assertEqual(registry['active_project_id'], 'second')
        self.assertEqual(registry['projects'], [old['projects'][1]])
        self.assertEqual(json.loads((backup / 'project-registry.before.json').read_text()), old)
        self.create_simple_project('first')
        self.assertFalse((target / 'data.txt').exists())

    def test_remove_active_clears_active_id(self) -> None:
        self.create_simple_project('active')
        result = self.run_cli('remove', 'active', '--backup-dir', str(self.workspace / 'archive'))
        self.assertEqual(result.returncode, 0, result.stderr)
        registry = json.loads(self.registry_path.read_text())
        self.assertIsNone(registry['active_project_id'])
        self.assertEqual(registry['projects'], [])

    def test_remove_rejects_unsafe_backup_or_wrong_identity_without_changes(self) -> None:
        target = self.create_simple_project('safe')
        for backup in (self.root / 'archive', target / 'archive', self.workspace, Path('relative')):
            self.assert_rejected_without_changes('remove', 'safe', '--backup-dir', str(backup))
        meta = target / '.sdd/project.json'
        data = json.loads(meta.read_text());data['id'] = 'someone-else';meta.write_text(json.dumps(data))
        self.assert_rejected_without_changes('remove', 'safe', '--backup-dir', str(self.workspace / 'archive'))
        self.assert_rejected_without_changes('remove', '../safe', '--backup-dir', str(self.workspace / 'archive'))

    def test_remove_registry_write_failure_restores_project_directory(self) -> None:
        import importlib.util
        from types import SimpleNamespace
        from unittest.mock import patch
        target = self.create_simple_project('safe')
        spec = importlib.util.spec_from_file_location('isolated_sdd_manager', self.root / 'scripts/sdd_project.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        before = self.registry_path.read_bytes()
        with patch.object(module, 'save_registry', side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError):
                module.cmd_remove(SimpleNamespace(id='safe', backup_dir=str(self.workspace / 'archive')))
        self.assertTrue((target / '.sdd/project.json').exists())
        self.assertEqual(self.registry_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
