"""requirements runtime localization: local methods, config, validators, migration and isolated stdio."""

import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_requirements_cursor_tools as fixtures
from test_requirements_prd_tools import PRD_BODY, PRD_BODY_B
import cursor_mcp as mcp
import configure_cursor
from file_tools import artifact_records, check_foundation, confirmation_records, project_init

TOOLS_ROOT = fixtures.TOOLS_ROOT.resolve()
WORKSPACE_ROOT = TOOLS_ROOT.parents[2]
CURRENT_DOCUMENTS = ("requirements.md", "agent-file-workflow.md", "references/handoff-boundary.md")
CONFIRMATION_ID = "C-" + "b" * 20
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() and not p.is_symlink() else None
            for p in sorted(Path(root).rglob("*"))}


def write_confirmation(root, project_id, *, tamper_snapshot=False, purpose="形成技术方案"):
    """Persist a Main-style PRD confirmation fixture; the tools under test only read it."""
    prd = (root / "docs/PRD.md").read_bytes()
    digest = sha(prd)
    snapshot = f"docs/confirmations/snapshots/{digest}/PRD.md"
    target = root / snapshot
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(prd + (b"tampered" if tamper_snapshot else b""))
    data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    data["artifact_registry"] = {
        "schema_version": 1, "confirmations_path": "docs/decisions.md", "handoffs_directory": "docs/handoffs",
        "entries": {"prd": {"artifact_id": "prd", "kind": "requirements", "current_version": "v1", "versions": [{
            "version": "v1", "content": {"type": "file", "path": snapshot, "sha256": sha(target.read_bytes()),
                                         "size": target.stat().st_size},
            "confirmation_ids": [CONFIRMATION_ID], "producer_role": "requirements", "purpose": "PRD",
            "summary": "PRD v1", "document_status": "Draft", "open_items": [],
            "availability": {"scope": "local-only", "git_commit": None},
            "registration": {"actor": {"role": "main", "principal_id": "main", "authority": "buzz"},
                             "recorded_at": "2026-10-30T00:00:00Z"}}]}}}
    (root / "project.json").write_text(project_init.json_text(data), encoding="utf-8")
    record = {"schema_version": 1, "confirmation_id": CONFIRMATION_ID, "status": "active", "project_id": project_id,
              "artifact": {"artifact_id": "prd", "kind": "requirements", "version": "v1",
                           "content_sha256": digest, "registered_path": "docs/PRD.md"},
              "snapshot": {"type": "file", "path": snapshot, "sha256": digest},
              "permitted_use": purpose, "confirmed_scope": "全部", "non_authorizations": [], "open_items": [],
              "evidence": {"type": "current-session", "provider": "buzz", "authority": "buzz",
                           "user_principal_id": "bowen", "session_id": "s", "message_id": "m",
                           "confirmed_at": "2026-10-30T00:00:00Z", "statement": "确认 PRD",
                           "runtime_authenticated": True},
              "recorded_by": {"principal_id": "main", "authority": "buzz"}, "recorded_at": "2026-10-30T00:00:00Z"}
    block = json.dumps({"schema_version": 1, "confirmations": [record]}, ensure_ascii=False, indent=2)
    (root / "docs/decisions.md").write_text(
        f"# 项目确认记录\n\n{confirmation_records.DECISIONS_START}\n```json\n{block}\n```\n"
        f"{confirmation_records.DECISIONS_END}\n", encoding="utf-8")
    return record


class RealTreeTests(unittest.TestCase):
    """Step 3／8 (L01, L02, L10): the delivered requirements directory itself."""

    def test_methods_link_templates_and_handoff_entry_resolve_to_original_text(self):
        link = TOOLS_ROOT / "methods/develop-helper"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../../../../Develop_Helper")
        upstream = (WORKSPACE_ROOT / "Develop_Helper").resolve()
        self.assertEqual(link.resolve(strict=True), upstream)
        skills = link / "harness-core/skills"
        for relative in ("sdd-product-design/phase-A.md", "sdd-product-design/phase-R.md",
                         "solution-design/SKILL.md"):
            self.assertTrue((skills / relative).is_file(), relative)
        research = TOOLS_ROOT / "templates/research-template.md"
        self.assertTrue(research.is_symlink())
        self.assertTrue(os.readlink(research).startswith("../methods/develop-helper/"))
        self.assertEqual(research.resolve(strict=True),
                         upstream / "harness-core/skills/sdd-product-design/references/research-template.md")
        sources = json.loads((TOOLS_ROOT / "file_tools/SOURCES.json").read_text(encoding="utf-8"))
        copies = {item["file"]: item for item in sources["local_copies"]}
        for name in ("templates/prd-template.md", "upstream-lock.json", "config/local.example.json"):
            raw = (TOOLS_ROOT / name).read_bytes()
            self.assertEqual(sha(raw), copies[name]["copy_sha256"], name)
            if name == "upstream-lock.json":
                adaptation = copies[name]["publication_adaptation"]
                self.assertEqual(json.loads(raw), adaptation["published_lock"])
                self.assertEqual(set(adaptation["reviewed_differences"]),
                                 {"project-registry.json", "learning/technical-terms/index.md"})
            else:
                self.assertEqual(copies[name]["copy_sha256"], copies[name]["source_sha256"], name)

    def test_current_documents_link_locally_and_never_through_the_old_directory(self):
        for document in CURRENT_DOCUMENTS:
            path = TOOLS_ROOT / document
            targets = [target for target in LINK.findall(path.read_text(encoding="utf-8"))
                       if "://" not in target]
            self.assertTrue(targets, document)
            for target in targets:
                with self.subTest(document=document, target=target):
                    self.assertNotIn("buzz-develop-helper", target)
                    resolved = (path.parent / target).resolve(strict=True)
                    self.assertNotIn("buzz-develop-helper", resolved.as_posix())

    def test_readme_uses_the_local_foundation_and_step_ten_candidate_commands(self):
        readme = (TOOLS_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("--prepare-local-config-from buzz-develop-helper", readme)
        self.assertIn("--migrate-from-foundation buzz-develop-helper", readme)
        self.assertNotIn("--foundation buzz-develop-helper", readme)
        self.assertNotIn("当前继续使用 `buzz-develop-helper` 的本机配置", readme)

    def test_lock_copy_still_matches_the_original_source_without_refreshing(self):
        locked = json.loads((TOOLS_ROOT / "upstream-lock.json").read_text(encoding="utf-8"))
        actual = check_foundation.snapshot((TOOLS_ROOT / "methods/develop-helper").resolve(strict=True))
        self.assertEqual((locked["sha256"], locked["entry_count"], locked["policy"]),
                         (actual["sha256"], actual["entry_count"], actual["policy"]))

    def test_tests_and_runtime_code_do_not_load_the_old_directory(self):
        for path in [*TOOLS_ROOT.glob("*.py"), *(TOOLS_ROOT / "file_tools").glob("*.py"),
                     *(path for path in Path(__file__).parent.glob("test_requirements*.py")
                       if path.name != Path(__file__).name)]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotRegex(text, r"buzz-develop-helper/scripts\"|/ \"buzz-develop-helper")
                self.assertNotIn("sys.path.insert(0, str(scripts", text)
                self.assertNotIn("load_upstream", text)

    def test_real_tree_has_no_switched_config_or_migration_backup(self):
        self.assertFalse((TOOLS_ROOT / "config/local.json").exists())
        self.assertFalse((TOOLS_ROOT / "config/migration-backups").exists())
        ignored = (TOOLS_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("config/local.json", ignored)
        self.assertIn("config/migration-backups/", ignored)


class FoundationCheckTests(unittest.TestCase):
    """Step 4 (L02, L03): local foundation layout and rejection paths on temp copies."""

    setUp = fixtures.CursorToolsTests.setUp
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools

    def test_methods_link_errors_are_rejected_without_touching_the_source(self):
        before = tree(self.source)
        self.assertEqual(check_foundation.check(self.foundation)["status"], "pass")
        link = self.foundation / "methods/develop-helper"
        other = self.root / "other"
        other.mkdir()
        cases = {
            "wrong_target": (lambda: (link.unlink(), link.symlink_to(other, target_is_directory=True)),
                             "软链目标与配置不一致"),
            "dangling": (lambda: (link.unlink(), link.symlink_to(self.root / "missing")), ""),
            "not_a_link": (lambda: (link.unlink(), link.mkdir()), "不是软链"),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(case=name):
                mutate()
                with self.assertRaisesRegex((ValueError, OSError), message):
                    check_foundation.check(self.foundation)
                if link.is_dir() and not link.is_symlink():
                    link.rmdir()
                elif link.is_symlink():
                    link.unlink()
                link.symlink_to(self.source, target_is_directory=True)
        self.assertEqual(tree(self.source), before)

    def test_legacy_layout_is_rejected_explicitly_not_used_as_fallback(self):
        legacy = self.root / "legacy"
        (legacy / "config").mkdir(parents=True)
        (legacy / "upstream").mkdir()
        (legacy / "upstream/develop-helper").symlink_to(self.source, target_is_directory=True)
        shutil.copyfile(self.foundation / "config/local.json", legacy / "config/local.json")
        shutil.copyfile(self.foundation / "upstream-lock.json", legacy / "upstream-lock.json")
        with self.assertRaisesRegex(ValueError, "旧融合目录布局"):
            check_foundation.check(legacy)
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(TOOLS_ROOT / "cursor_mcp.py"),
                                 "--foundation", str(legacy)], input=b"", capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("旧融合目录布局", result.stderr.decode("utf-8"))

    def test_bad_configuration_and_overlaps_are_rejected(self):
        original = dict(self.config)
        cases = {"schema": {**original, "schema_version": 2},
                 "relative": {**original, "projects_root": "projects"},
                 "overlap": {**original, "projects_root": str(self.source)}}
        for name, config in cases.items():
            with self.subTest(case=name):
                self.config = config
                self.write_config()
                with self.assertRaises(ValueError):
                    check_foundation.check(self.foundation)
        self.config = original
        self.write_config()
        self.assertEqual(check_foundation.check(self.foundation)["status"], "pass")

    def test_new_project_records_the_lock_verbatim_and_existing_records_are_not_rewritten(self):
        project_init.initialize_existing(self.foundation, "voice-meetup", "语音约碰面地点", "本地化")
        data = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(data["dependencies"]["upstream"],
                         json.loads((self.foundation / "upstream-lock.json").read_text(encoding="utf-8")))
        before = tree(self.project)
        project_init.inspect(self.foundation, "voice-meetup")
        mcp.McpServer(self.new_tools())
        self.assertEqual(tree(self.project), before)


class LocalValidatorTests(unittest.TestCase):
    """Step 5 (L04): local pure validators on temp records; read-only."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="requirements-local-validators-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "project"
        (self.root / "docs").mkdir(parents=True)
        (self.root / "docs/PRD.md").write_text("# PRD\n", encoding="utf-8")
        (self.root / "project.json").write_text(json.dumps({"project_id": "local-check"}), encoding="utf-8")
        self.record = write_confirmation(self.root, "local-check")

    def decisions(self, records):
        block = json.dumps({"schema_version": 1, "confirmations": records}, ensure_ascii=False)
        (self.root / "docs/decisions.md").write_text(
            f"{confirmation_records.DECISIONS_START}\n```json\n{block}\n```\n{confirmation_records.DECISIONS_END}\n",
            encoding="utf-8")

    def test_valid_records_registry_and_snapshot_are_read_without_writes(self):
        before = tree(self.root)
        _, decisions, decisions_sha = confirmation_records.read_decisions(self.root)
        self.assertRegex(decisions_sha, "^[0-9a-f]{64}$")
        data = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        registry, verified = artifact_records.validate_registry(self.root, data)
        self.assertEqual(verified, [{"artifact_id": "prd", "version": "v1"}])
        _, version = confirmation_records.artifact_version(registry, "prd", "v1")
        self.assertEqual(artifact_records.content_sha(version["content"]), self.record["artifact"]["content_sha256"])
        confirmation_records.validate_snapshot(self.root, decisions["confirmations"][0])
        self.assertIn("buzz-develop-helper", confirmation_records.DECISIONS_START)
        self.assertEqual(tree(self.root), before)

    def test_malformed_duplicate_and_unauthenticated_records_are_invalid(self):
        bad_statement = json.loads(json.dumps(self.record))
        bad_statement["evidence"]["statement"] = "确认\x00"
        unauthenticated = json.loads(json.dumps(self.record))
        unauthenticated["evidence"]["runtime_authenticated"] = False
        bad_binding = {**self.record, "effect_binding": {"workflow_id": "w"}}
        cases = {"duplicate": [self.record, self.record], "bad_id": [{**self.record, "confirmation_id": "C-1"}],
                 "bad_statement": [bad_statement], "unauthenticated": [unauthenticated],
                 "bad_binding": [bad_binding], "bad_kind": [{**self.record, "artifact": {
                     **self.record["artifact"], "kind": "other"}}]}
        for name, records in cases.items():
            with self.subTest(case=name):
                self.decisions(records)
                with self.assertRaises(ValueError):
                    confirmation_records.read_decisions(self.root)
        (self.root / "docs/decisions.md").write_text(
            confirmation_records.DECISIONS_START * 2 + confirmation_records.DECISIONS_END, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "重复"):
            confirmation_records.read_decisions(self.root)

    def test_snapshot_and_registry_paths_cannot_escape_or_follow_links(self):
        outside = self.root.parent / "outside.md"
        outside.write_text("# PRD\n", encoding="utf-8")
        for path in ("../outside.md", "/etc/hosts", "docs/../../outside.md"):
            with self.subTest(path=path):
                record = {**self.record, "snapshot": {**self.record["snapshot"], "path": path}}
                with self.assertRaises(ValueError):
                    confirmation_records.validate_snapshot(self.root, record)
        (self.root / "docs/link.md").symlink_to(outside)
        record = {**self.record, "snapshot": {**self.record["snapshot"], "path": "docs/link.md"}}
        with self.assertRaisesRegex(ValueError, "软链"):
            confirmation_records.validate_snapshot(self.root, record)
        data = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        data["artifact_registry"]["entries"]["prd"]["versions"][0]["content"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "摘要不匹配"):
            artifact_records.validate_registry(self.root, data)

    def test_file_set_snapshots_check_every_member(self):
        manifest = self.root / "docs/set.json"
        member = self.root / "docs/member.md"
        member.write_text("member", encoding="utf-8")
        manifest.write_text("{}", encoding="utf-8")
        record = {**self.record, "artifact": {**self.record["artifact"], "content_sha256": sha(manifest.read_bytes())},
                  "snapshot": {"type": "file-set", "manifest_path": "docs/set.json",
                               "manifest_sha256": sha(manifest.read_bytes()),
                               "files": [{"snapshot_path": "docs/member.md", "sha256": sha(b"member")}]}}
        confirmation_records.validate_snapshot(self.root, record)
        member.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "成员摘要不匹配"):
            confirmation_records.validate_snapshot(self.root, record)

    def test_local_validators_import_no_signing_sending_or_initializer_code(self):
        script = """
import sys
sys.path.insert(0, sys.argv[1])
from file_tools import confirmation_records, artifact_records
loaded = set(sys.modules)
assert not loaded & {'hmac', 'trusted_context', 'collaboration', 'artifacts', 'project_init',
                     'file_tools.project_init', 'subprocess'}, loaded
for module in (confirmation_records, artifact_records):
    for name in ('render_decisions', 'validate_handoff', 'read_handoffs', 'preview_register', 'inspect',
                 'main', 'confirmation_map', 'preview_readme', 'empty_registry'):
        assert not hasattr(module, name), name
print('pure validators only')
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(TOOLS_ROOT)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pure validators only")


class MigrationTests(unittest.TestCase):
    """Step 7 (L08): config migration, idempotence, conflicts, backup and rollback on temp copies only."""

    setUp_fixture = fixtures.CursorToolsTests.setUp
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools

    def setUp(self):
        self.setUp_fixture()
        self.home = self.root / "home"
        (self.home / ".cursor").mkdir(parents=True)
        self.legacy = self.root / "legacy"
        (self.legacy / "upstream").mkdir(parents=True)
        self.config_path = self.home / ".cursor/mcp.json"
        self.old = configure_cursor.legacy_entry(old_foundation=self.legacy, python_executable=sys.executable)
        self.original = {"mcpServers": {"requirements": self.old, "unrelated": {"command": "existing"}},
                         "otherSetting": 42}
        self.config_path.write_text(json.dumps(self.original, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(self.assert_real_tree_untouched)

    def assert_real_tree_untouched(self):
        self.assertFalse((TOOLS_ROOT / "config/migration-backups").exists())
        self.assertFalse((TOOLS_ROOT / "config/local.json").exists())

    def migrate(self, **options):
        return configure_cursor.migrate(workspace=self.home, old_foundation=self.legacy, foundation=self.foundation,
                                        python_executable=sys.executable, **options)

    def backups(self):
        directory = self.foundation / configure_cursor.BACKUPS_DIRECTORY
        return sorted(directory.iterdir()) if directory.exists() else []

    def test_preview_backup_exact_replacement_and_idempotent_repeat(self):
        raw_before = self.config_path.read_bytes()
        preview = self.migrate()
        self.assertEqual((preview["state"], preview["applied"]), ("ready", False))
        self.assertEqual(preview["other_servers"], ["unrelated"])
        self.assertEqual(self.config_path.read_bytes(), raw_before)
        self.assertEqual(preview["old_server"]["args"][:3], preview["server"]["args"][:3])
        self.assertEqual(preview["old_server"]["args"][4:], preview["server"]["args"][4:])
        self.assertEqual(preview["server"]["args"][-2:], ["--allow-initialize", "--allow-save"])
        self.assertNotIn("--project-id", preview["server"]["args"])
        with self.assertRaisesRegex(ValueError, "冲突"):
            self.migrate(apply=True, expected_sha256="0" * 64)
        self.assertEqual(self.config_path.read_bytes(), raw_before)
        self.assertEqual(self.backups(), [])
        applied = self.migrate(apply=True, expected_sha256=preview["expected_config_sha256"])
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["mcpServers"]["requirements"], preview["server"])
        self.assertEqual(data["mcpServers"]["unrelated"], {"command": "existing"})
        self.assertEqual(data["otherSetting"], 42)
        [backup] = self.backups()
        self.assertEqual(Path(applied["backup"]), backup)
        self.assertEqual((backup / "mcp.json.before").read_bytes(), raw_before)
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["old_server"], manifest["new_server"]), (self.old, preview["server"]))
        self.assertEqual(manifest["after_sha256"], sha(self.config_path.read_bytes()))
        self.assertIn("cursor_mcp.py", manifest["code_sha256"])
        after = self.config_path.read_bytes()
        again = self.migrate()
        self.assertEqual((again["state"], again["changed"]), ("already_applied", False))
        self.assertEqual(self.migrate(apply=True, expected_sha256="ignored")["state"], "already_applied")
        self.assertEqual(self.config_path.read_bytes(), after)
        self.assertEqual(len(self.backups()), 1)

    def test_modified_missing_and_concurrently_changed_entries_are_not_overwritten(self):
        changed = json.loads(json.dumps(self.original))
        changed["mcpServers"]["requirements"]["args"].append("--extra")
        self.config_path.write_text(json.dumps(changed), encoding="utf-8")
        raw = self.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "不一致"):
            self.migrate()
        del changed["mcpServers"]["requirements"]
        self.config_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "没有共用"):
            self.migrate()
        self.config_path.write_text(json.dumps(self.original), encoding="utf-8")
        preview = self.migrate()
        self.config_path.write_text(json.dumps({**self.original, "otherSetting": 43}), encoding="utf-8")
        raw = self.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "冲突"):
            self.migrate(apply=True, expected_sha256=preview["expected_config_sha256"])
        self.assertEqual(self.config_path.read_bytes(), raw)
        self.assertEqual(self.backups(), [])

    def test_backup_failure_stops_before_any_config_write(self):
        (self.foundation / "config/migration-backups").write_text("not a directory", encoding="utf-8")
        raw = self.config_path.read_bytes()
        preview = self.migrate()
        with self.assertRaises(OSError):
            self.migrate(apply=True, expected_sha256=preview["expected_config_sha256"])
        self.assertEqual(self.config_path.read_bytes(), raw)

    def test_rollback_restores_only_the_migrated_entry_and_reports_code_separately(self):
        preview = self.migrate()
        backup = self.migrate(apply=True, expected_sha256=preview["expected_config_sha256"])["backup"]
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["mcpServers"]["added-later"] = {"command": "kept"}
        self.config_path.write_text(json.dumps(data), encoding="utf-8")
        plan = configure_cursor.rollback(workspace=self.home, backup=backup)
        self.assertEqual((plan["state"], plan["code_restored"]), ("ready", False))
        configure_cursor.rollback(workspace=self.home, backup=backup, apply=True,
                                  expected_sha256=plan["expected_config_sha256"])
        restored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(restored["mcpServers"]["requirements"], self.old)
        self.assertEqual(restored["mcpServers"]["added-later"], {"command": "kept"})
        self.assertEqual(configure_cursor.rollback(workspace=self.home, backup=backup)["state"], "already_applied")
        restored["mcpServers"]["requirements"] = {"command": "user-edited"}
        self.config_path.write_text(json.dumps(restored), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不是该备份"):
            configure_cursor.rollback(workspace=self.home, backup=backup)

    def test_command_line_preview_prints_a_ready_apply_command(self):
        command = [sys.executable, "-B", str(TOOLS_ROOT / "configure_cursor.py"), "--workspace", str(self.home),
                   "--foundation", str(self.foundation), "--migrate-from-foundation", str(self.legacy)]
        preview = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        apply_command = json.loads(preview.stdout)["apply_command"]
        applied = subprocess.run(shlex.split(apply_command), capture_output=True, text=True, timeout=30)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(json.loads(applied.stdout)["applied"])
        self.assertEqual(len(self.backups()), 1)

    def test_local_config_is_copied_verbatim_and_never_overwritten(self):
        (self.legacy / "config").mkdir()
        legacy_config = self.legacy / "config/local.json"
        shutil.copyfile(self.foundation / "config/local.json", legacy_config)
        target = self.foundation / "config/local.json"
        command = [sys.executable, "-B", str(TOOLS_ROOT / "configure_cursor.py"),
                   "--foundation", str(self.foundation),
                   "--prepare-local-config-from", str(self.legacy)]
        target.unlink()
        preview = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual((json.loads(preview.stdout)["state"], target.exists()), ("absent", False))
        preview = configure_cursor.prepare_local_config(foundation=self.foundation, source_foundation=self.legacy)
        self.assertEqual((preview["state"], preview["written"]), ("absent", False))
        self.assertFalse(target.exists())
        written = configure_cursor.prepare_local_config(foundation=self.foundation, source_foundation=self.legacy,
                                                        apply=True)
        self.assertEqual(written["state"], "written")
        self.assertEqual(target.read_bytes(), legacy_config.read_bytes())
        self.assertEqual(configure_cursor.prepare_local_config(
            foundation=self.foundation, source_foundation=self.legacy, apply=True)["state"], "identical")
        target.write_text(json.dumps({**self.config, "project_directories": {}}), encoding="utf-8")
        changed = target.read_bytes()
        with self.assertRaisesRegex(ValueError, "project_directories"):
            configure_cursor.prepare_local_config(foundation=self.foundation, source_foundation=self.legacy,
                                                  apply=True)
        self.assertEqual(target.read_bytes(), changed)


class IsolatedRuntimeTests(unittest.TestCase):
    """Step 9 (L05, L06, L07, L09): a copy of requirements with only the upstream text and temp projects."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="requirements-isolated-")
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.workspace = base / "vibe"
        self.copy = self.workspace / "fusion-runtime/workflows/requirements"
        shutil.copytree(TOOLS_ROOT, self.copy, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "local.json",
                                                      "migration-backups"))
        upstream = (TOOLS_ROOT / "methods/develop-helper").resolve(strict=True)
        (self.workspace / "Develop_Helper").symlink_to(upstream, target_is_directory=True)
        self.projects = base / "projects"
        self.projects.mkdir()
        (self.copy / "config/local.json").write_text(json.dumps({
            "schema_version": 1, "upstream_root": str(upstream), "projects_root": str(self.projects),
            "project_directories": {}}), encoding="utf-8")
        self.assertFalse(any("buzz-develop-helper" in path.name for path in base.rglob("*")))
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("PYTHON")}
        self.cwd = base
        self.children = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def start(self, *flags):
        child = subprocess.Popen([sys.executable, "-E", "-s", "-B", str(self.copy / "cursor_mcp.py"), *flags],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd=self.cwd, env=self.environment)
        self.children.append(child)
        return child

    def send(self, child, method, params=None):
        message = {"jsonrpc": "2.0", "id": 1, "method": method,
                   "params": {**(params or {}), "_meta": fixtures.CursorToolsTests.meta()}}
        child.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        child.stdin.flush()
        self.assertTrue(select.select([child.stdout], [], [], 20)[0], "MCP response timed out")
        response = json.loads(child.stdout.readline())
        self.assertNotIn("error", response, response)
        return response["result"]

    def tool(self, child, tool_name, path, *, error=False, **arguments):
        result = self.send(child, "tools/call", {"name": tool_name,
                                                 "arguments": {"project_path": str(path), **arguments}})
        self.assertEqual(result["isError"], error, result)
        return json.loads(result["content"][0]["text"])

    def test_module_sources_are_only_the_copy_and_standard_library(self):
        script = """
import json, sys
sys.path.insert(0, sys.argv[1])
import cursor_mcp
from file_tools import recovery
recovery.load_validators()
files = sorted({m.__file__ for m in list(sys.modules.values()) if getattr(m, '__file__', None)})
print(json.dumps(files))
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(self.copy)], capture_output=True,
                                text=True, cwd=self.cwd, env=self.environment, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = json.loads(result.stdout)
        local = [path for path in files if path.startswith(str(self.copy))]
        self.assertTrue({"cursor_mcp.py", "recovery.py", "confirmation_records.py", "artifact_records.py"}
                        <= {Path(path).name for path in local})
        self.assertFalse([path for path in files if "buzz-develop-helper" in path or "fusion-runtime/tests" in path])
        self.assertFalse([path for path in files if "/workflows/requirements/" in path
                          and not path.startswith(str(self.copy))])

    def test_default_foundation_full_tool_chain_and_confirmation_checks(self):
        child = self.start("--allow-initialize", "--allow-save")
        names = {item["name"] for item in self.send(child, "tools/list")["tools"]}
        self.assertEqual(len(names), 7)
        path = self.projects / "隔离项目"
        created = self.tool(child, mcp.PROJECT_INITIALIZE, path, name="隔离项目", purpose="本地化独立运行")
        identifier = created["project_id"]
        data = json.loads((path / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(data["dependencies"]["upstream"],
                         json.loads((self.copy / "upstream-lock.json").read_text(encoding="utf-8")))
        read = self.tool(child, mcp.READ_CONTEXT, path)
        info = self.tool(child, mcp.UPDATE_INFO, path, read_id=read["read_id"], changes={"specification": None})
        self.assertFalse(info["remote_actions"])
        first = self.tool(child, mcp.SAVE_DRAFT, path, content="# 需求 v1", read_id=self.tool(
            child, mcp.READ_CONTEXT, path)["read_id"])
        stale = self.tool(child, mcp.READ_CONTEXT, path)["read_id"]
        self.tool(child, mcp.SAVE_DRAFT, path, content="# 需求 v2", read_id=self.tool(
            child, mcp.READ_CONTEXT, path)["read_id"])
        self.tool(child, mcp.SAVE_DRAFT, path, content="# 需求 v3", read_id=stale, error=True)
        history = self.tool(child, mcp.READ_CONTEXT, path, history_sha256=first["sha256"])["history"]
        self.assertEqual(history["sha256"], first["sha256"])
        self.assertTrue(history["content"].endswith("# 需求 v1\n"))
        prd = self.tool(child, mcp.SAVE_PRD_DRAFT, path, content=PRD_BODY, read_id=self.tool(
            child, mcp.READ_CONTEXT, path)["read_id"])
        self.tool(child, mcp.SAVE_PRD_DRAFT, path, content=PRD_BODY_B, read_id=self.tool(
            child, mcp.READ_CONTEXT, path)["read_id"])
        prd_history = self.tool(child, mcp.READ_CONTEXT, path, prd_history_sha256=prd["sha256"])["prd_history"]
        self.assertEqual(prd_history["sha256"], prd["sha256"])
        self.assertIn("status", self.tool(child, mcp.INSPECT_PRD, path))
        recovered = self.tool(child, mcp.READ_CONTEXT, path, include_recovery=True)["recovery"]
        self.assertEqual((recovered["confirmations"]["status"], recovered["confirmations"]["reasons"]),
                         ("missing", ["decisions_missing"]))

        write_confirmation(path, identifier)
        before = tree(path)
        valid = self.tool(child, mcp.READ_CONTEXT, path, include_recovery=True)["recovery"]["confirmations"]
        self.assertEqual((valid["status"], valid["records"][0]["result"]), ("valid", "valid"))
        self.assertFalse(valid["confirmation_written"])
        self.assertEqual(tree(path), before)
        write_confirmation(path, identifier, tamper_snapshot=True)
        invalid = self.tool(child, mcp.READ_CONTEXT, path, include_recovery=True)["recovery"]["confirmations"]
        self.assertEqual(invalid["status"], "invalid")
        self.assertIn("snapshot_mismatch", invalid["records"][0]["reasons"])
        write_confirmation(path, identifier, purpose="其他用途")
        other = self.tool(child, mcp.READ_CONTEXT, path, include_recovery=True)["recovery"]["confirmations"]
        self.assertEqual((other["status"], other["reasons"]), ("missing", ["purpose_mismatch"]))

        outside = self.cwd / "outside-project"
        outside.mkdir()
        self.tool(child, mcp.READ_CONTEXT, outside, error=True)
        held = self.tool(child, mcp.READ_CONTEXT, path)["read_id"]
        child.stdin.close()
        self.assertEqual(child.wait(timeout=10), 0)
        self.assertEqual(child.stderr.read(), b"")

        restarted = self.start("--allow-initialize", "--allow-save")
        failure = self.tool(restarted, mcp.SAVE_DRAFT, path, content="# 旧凭证", read_id=held, error=True)
        self.assertIn("error", failure)
        read_only = self.start()
        self.assertEqual({item["name"] for item in self.send(read_only, "tools/list")["tools"]},
                         {mcp.PROJECT_INSPECT, mcp.READ_CONTEXT, mcp.INSPECT_PRD})
        self.tool(read_only, mcp.SAVE_DRAFT, path, content="# 不应写入", read_id=held, error=True)
        self.assertNotIn("不应写入", (path / "docs/requirements.md").read_text(encoding="utf-8"))
        self.assertNotIn("旧凭证", (path / "docs/requirements.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
