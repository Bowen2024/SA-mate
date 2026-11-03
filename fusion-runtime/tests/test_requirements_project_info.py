"""Project selections: field rules, initialization, identity, specification, repository plan and updates."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_requirements_cursor_tools as fixtures
import cursor_mcp as mcp
from file_tools import project_info, project_init
from file_tools.check_foundation import snapshot

URL = "https://github.com/example/demo.git"
SECRET = "s3cr3t-token"
LEGACY_KEYS = {"schema_version", "project_id", "name", "purpose", "created_at", "dependencies",
               "artifacts", "buzz", "github", "initialization"}
FULL_INFO = {"project_type": "cli", "target_platforms": ["macos", "linux"], "specification": "default",
             "repository_plan": {"mode": "use_existing", "url": URL}}


class ProjectInfoTests(unittest.TestCase):
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools
    tree = fixtures.CursorToolsTests.tree
    meta = staticmethod(fixtures.CursorToolsTests.meta)
    rpc = fixtures.CursorToolsTests.rpc
    call = fixtures.CursorToolsTests.call

    def setUp(self):
        fixtures.CursorToolsTests.setUp(self)
        library = self.source / "harness-core/specification"
        for name in ("default", "my-standards"):
            (library / name).mkdir(parents=True)
            (library / name / "README.md").write_text(name, encoding="utf-8")
        (library / "README.md").write_text("index", encoding="utf-8")
        self.relock()

    def relock(self):
        (self.foundation / "upstream-lock.json").write_text(json.dumps(snapshot(self.source)), encoding="utf-8")

    def shared(self, **options):
        self.server = mcp.McpServer(mcp.SharedProjectTools(foundation=self.foundation, clock=lambda: self.now,
                                                           **options))

    def metadata(self, root=None):
        return json.loads(((root or self.project) / "project.json").read_text(encoding="utf-8"))

    def write_metadata(self, data, root=None):
        ((root or self.project) / "project.json").write_text(project_init.json_text(data), encoding="utf-8")

    def initialize(self, error=False, **info):
        return self.call(mcp.PROJECT_INITIALIZE, {"name": "语音约碰面地点", "purpose": "临时工具测试", **info},
                         error=error)

    def read(self):
        return self.call(mcp.READ_CONTEXT)

    def update(self, read_id, changes, error=False):
        return self.call(mcp.UPDATE_INFO, {"read_id": read_id, "changes": changes}, error=error)

    def assert_rejected(self, failure, reason):
        self.assertEqual(failure.get("reason"), reason, failure)
        self.assertEqual(failure.get("write_outcome"), "not_written", failure)

    # Step 2/4: field contract and initialization kernel

    def test_field_contract_accepts_legal_values_and_rejects_impostors(self):
        legal = {"project_type": ["web", "mobile", "api", "cli"],
                 "target_platforms": [["ios"], ["ios", "android", "harmonyos"], ["a"] + [f"p{i}" for i in range(7)]],
                 "specification": [None, "default", "my-standards", "集合"],
                 "repository_plan": [{"mode": "deferred"}, {"mode": "none"}, {"mode": "create_later"},
                                     {"mode": "use_existing", "url": URL}]}
        illegal = {"project_type": [None, "", "Web", "unknown", "null", ["web"], 1, True],
                   "target_platforms": [[], None, "ios", ["iOS"], ["ios", "ios"], [""], [1],
                                        [f"p{i}" for i in range(9)], ["-ios"], ["a" * 33]],
                   "specification": ["", "null", "../x", "a/b", "a\\b", " default", "default ", ".", "..",
                                     True, {}, [], "x" * 65, "tab\tname"],
                   "repository_plan": [None, "none", {}, {"mode": "later"}, {"mode": "use_existing"},
                                       {"mode": "none", "url": URL}, {"mode": "deferred", "note": "x"},
                                       {"mode": "use_existing", "url": URL, "owner": "x"},
                                       {"mode": "use_existing", "url": None}, {"mode": ["none"]}]}
        for field, values in legal.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertEqual(project_info.validate_field(field, value), value)
        for field, values in illegal.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(project_info.InfoError) as caught:
                    project_info.validate_field(field, value)
                self.assertEqual(caught.exception.reason, "invalid_value")
        report = project_info.report({"project_type": "Web", "specification": None})
        self.assertEqual(report["fields"]["project_type"], {"status": "invalid"})
        self.assertEqual(report["fields"]["specification"], {"status": "recorded", "value": None})
        self.assertEqual(report["unrecorded"], ["target_platforms", "repository_plan"])

    def test_url_rules_cover_credentials_percent_encoding_and_do_not_echo(self):
        valid = [URL, "https://gitlab.example.com:8443/group/sub/repo", "ssh://git@github.com/o/r.git",
                 "ssh://github.com:22/o/r", "git@github.com:o/r.git", "git@host.example:/srv/repo.git"]
        invalid = ["https://user:" + SECRET + "@github.com/o/r", "https://user@github.com/o/r",
                   "https://user%3A" + SECRET + "%40github.com/o/r", "https://github.com/o/r%40" + SECRET,
                   "https://github.com/o/r?token=" + SECRET, "https://github.com/o/r#" + SECRET,
                   "ssh://git:" + SECRET + "@github.com/o/r", "ssh://git%3A" + SECRET + "@github.com/o/r",
                   "git:" + SECRET + "@github.com:o/r", "git@github.com:o/r%40" + SECRET,
                   "http://github.com/o/r", "file:///tmp/r", "https://github.com", "https://github.com/",
                   " https://github.com/o/r", "https://github.com/o r", "https://github.com/../r",
                   "https://github.com/o/r%0a", "", "x" * 3000, 7]
        for value in valid:
            with self.subTest(value=value):
                self.assertTrue(project_info.valid_url(value))
        for value in invalid:
            with self.subTest(value=value):
                self.assertFalse(project_info.valid_url(value))
                with self.assertRaises(project_info.InfoError) as caught:
                    project_info.validate_field("repository_plan", {"mode": "use_existing", "url": value})
                self.assertNotIn(SECRET, str(caught.exception) + json.dumps(caught.exception.data))

    def test_legacy_initialize_keeps_three_identical_files_and_reports_unrecorded(self):
        args = ("voice-meetup", "n", "u", "2026-10-29T00:00:00+00:00", {"d": 1})
        self.assertEqual(project_init.creation_files(*args), project_init.creation_files(*args, info=None))
        self.assertEqual(project_init.creation_files(*args), project_init.creation_files(*args, info={}))
        result = self.initialize()
        self.assertTrue(result["changed"])
        self.assertEqual(set(self.tree()), {"README.md", ".gitignore", "project.json"})
        self.assertEqual(set(self.metadata()), LEGACY_KEYS)
        state = self.call(mcp.PROJECT_INSPECT)
        self.assertEqual(state["project_info"]["unrecorded"], list(project_info.FIELDS))
        self.assertEqual((state["identity_source"], state["identity_persisted"]), ("launcher", True))
        self.assertEqual(state["project_json_sha256"],
                         hashlib.sha256((self.project / "project.json").read_bytes()).hexdigest())

    def test_initialize_records_exact_selections_and_keeps_execution_pending(self):
        result = self.initialize(**FULL_INFO)
        data = self.metadata()
        self.assertEqual({field: data[field] for field in project_info.FIELDS}, FULL_INFO)
        self.assertEqual(result["project_info"]["unrecorded"], [])
        self.assertEqual(result["impacts"][0]["code"], "specification_type_mismatch")
        self.assertEqual(data["github"], {"owner": None, "repository": None, "visibility": None, "url": None})
        self.assertEqual({key: step["status"] for key, step in data["initialization"].items()},
                         {key: "succeeded" if key == "local_files" else "pending" for key in project_init.STEPS})
        self.assertEqual(set(self.tree()), {"README.md", ".gitignore", "project.json"})
        self.assertFalse(result["remote_actions"])

    def test_explicit_null_and_partial_selections_are_distinct_from_unrecorded(self):
        self.initialize(specification=None, project_type="api")
        raw = (self.project / "project.json").read_text(encoding="utf-8")
        self.assertIn('"specification": null', raw)
        data = self.metadata()
        self.assertIsNone(data["specification"])
        self.assertNotIn("target_platforms", data)
        self.assertNotIn("repository_plan", data)
        report = self.call(mcp.PROJECT_INSPECT)["project_info"]
        self.assertEqual(report["fields"]["specification"], {"status": "recorded", "value": None})
        self.assertEqual(report["unrecorded"], ["target_platforms", "repository_plan"])

    def test_invalid_selections_are_rejected_before_any_file_is_created(self):
        cases = [({"project_type": "unknown"}, "invalid_value"), ({"specification": "null"}, "invalid_value"),
                 ({"specification": ""}, "invalid_value"), ({"specification": "../outside"}, "invalid_value"),
                 ({"specification": "missing-set"}, "specification_not_found"),
                 ({"target_platforms": []}, "invalid_value"),
                 ({"repository_plan": {"mode": "use_existing", "url": "https://u:" + SECRET + "@h.example/r"}},
                  "invalid_value")]
        for info, reason in cases:
            with self.subTest(info=info):
                failure = self.initialize(error=True, **info)
                self.assert_rejected(failure, reason)
                self.assertNotIn(SECRET, json.dumps(failure, ensure_ascii=False))
                self.assertEqual(self.tree(), {})
        self.assertIn("未知字段", self.initialize(error=True, owner="x")["error"])
        self.assertIn("必须是非空文本", self.call(mcp.PROJECT_INITIALIZE, {"name": 5, "purpose": "x"}, error=True)["error"])
        self.assertEqual(self.tree(), {})

    def test_repeat_initialize_reports_differences_without_applying_and_still_rejects_errors(self):
        self.initialize(project_type="web")
        before = self.tree()
        again = self.initialize(project_type="cli", specification=None)
        self.assertEqual((again["changed"], again["info_applied"]), (False, False))
        self.assertEqual(again["differences"], ["project_type", "specification"])
        self.assertIn(mcp.UPDATE_INFO, again["next_action"])
        same = self.initialize(project_type="web")
        self.assertEqual(same["differences"], [])
        self.assertNotIn("next_action", same)
        self.assert_rejected(self.initialize(error=True, project_type="Web"), "invalid_value")
        self.assert_rejected(self.initialize(error=True, specification="missing-set"), "specification_not_found")
        self.assertEqual(self.tree(), before)

    def test_partial_creation_failure_is_preserved_and_not_retried(self):
        original = Path.open

        def failing(path, *args, **kwargs):
            if path.name == "project.json" and args and args[0] == "x":
                raise OSError("simulated disk failure")
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "open", failing):
            failure = self.initialize(error=True, project_type="web")
        self.assertEqual(failure["write_outcome"], "unknown")
        partial = self.tree()
        self.assertEqual(set(partial), {"README.md", ".gitignore"})
        self.initialize(error=True, project_type="web")
        self.assertEqual(self.tree(), partial)

    # Step 5: identity and directories

    def test_shared_explicit_id_creates_and_reopens_with_the_same_identity(self):
        self.shared(allow_initialize=True, allow_save=True)
        path = self.projects / "中文新项目"
        before_config = (self.foundation / "config/local.json").read_bytes()
        state = self.call(mcp.PROJECT_INSPECT, {"project_path": str(path)})
        self.assertEqual((state["identity_source"], state["identity_persisted"]), ("path_digest", False))
        self.assertTrue(state["project_id"].startswith("req-"))
        created = self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(path), "name": "中文新项目",
                                                     "purpose": "显式 ID", "project_id": "zh-new"})
        self.assertEqual((created["project_id"], created["identity_persisted"]), ("zh-new", True))
        self.assertEqual(self.metadata(path)["project_id"], "zh-new")
        self.shared(allow_initialize=True, allow_save=True)
        again = self.call(mcp.PROJECT_INSPECT, {"project_path": str(path)})
        self.assertEqual((again["project_id"], again["identity_source"]), ("zh-new", "persisted"))
        self.assertEqual(self.call(mcp.READ_CONTEXT, {"project_path": str(path)})["project_id"], "zh-new")
        self.assertEqual((self.foundation / "config/local.json").read_bytes(), before_config)
        self.assertFalse((self.projects / "zh-new").exists())

    def test_explicit_id_conflicts_and_invalid_values_do_not_rebind_or_write(self):
        self.shared(allow_initialize=True, allow_save=True)
        (self.projects / "taken").mkdir()
        new = self.projects / "中文二"
        cases = [(self.project, "other-id", "identity_conflict"),
                 (new, "voice-meetup", "identity_conflict"),
                 (new, "taken", "identity_conflict"),
                 (new, "../escape", "invalid_value"), (new, "Bad", "invalid_value"), (new, 5, "invalid_value")]
        for path, identifier, reason in cases:
            with self.subTest(identifier=identifier):
                failure = self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(path), "name": "x", "purpose": "x",
                                                             "project_id": identifier}, error=True)
                self.assert_rejected(failure, reason)
        self.assertEqual(self.tree(), {})
        self.assertFalse(new.exists())
        self.assertEqual(list((self.projects / "taken").iterdir()), [])
        self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.project), "name": "x", "purpose": "x",
                                           "project_id": "voice-meetup"})
        before = self.tree()
        self.assert_rejected(self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.project), "name": "x",
                                                                "purpose": "x", "project_id": "renamed"},
                                       error=True), "identity_conflict")
        same = self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.project), "name": "x", "purpose": "x",
                                                  "project_id": "voice-meetup"})
        self.assertFalse(same["changed"])
        self.assertEqual(self.tree(), before)
        self.server = mcp.McpServer(self.new_tools(allow_initialize=True, allow_save=True))
        self.assertIn("未知字段", self.initialize(error=True, project_id="voice-meetup")["error"])
        self.assertEqual(self.tree(), before)

    def test_inspect_identity_is_suggested_until_persisted_and_mapping_is_reported(self):
        self.shared(allow_initialize=True)
        ascii_path = self.projects / "plain-name"
        state = self.call(mcp.PROJECT_INSPECT, {"project_path": str(ascii_path)})
        self.assertEqual((state["project_id"], state["identity_source"], state["identity_persisted"]),
                         ("plain-name", "directory_name", False))
        mapped = self.call(mcp.PROJECT_INSPECT, {"project_path": str(self.project)})
        self.assertEqual((mapped["project_id"], mapped["identity_source"]), ("voice-meetup", "mapping"))
        self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(ascii_path), "name": "p", "purpose": "p"})
        after = self.call(mcp.PROJECT_INSPECT, {"project_path": str(ascii_path)})
        self.assertEqual((after["identity_source"], after["identity_persisted"]), ("persisted", True))

    # Step 6: specification and repository plan

    def test_specification_null_is_never_resolved_and_names_stay_inside_the_library(self):
        with mock.patch.object(project_info, "specification_root", side_effect=AssertionError("resolved")):
            self.assertEqual(project_info.resolve_specification(self.foundation, None), {"status": "not_used"})
            self.initialize(specification=None)
        self.assertEqual(project_info.resolve_specification(self.foundation, "my-standards")["path"],
                         "harness-core/specification/my-standards")
        outside = self.root / "outside-spec"
        outside.mkdir()
        library = self.source / "harness-core/specification"
        (library / "linked").symlink_to(outside, target_is_directory=True)
        (library / "plain-file").write_text("x", encoding="utf-8")
        self.relock()
        for name in ("linked", "plain-file", "absent"):
            with self.subTest(name=name), self.assertRaises(project_info.InfoError) as caught:
                project_info.resolve_specification(self.foundation, name)
            self.assertEqual(caught.exception.reason, "specification_not_found")

    def test_type_and_specification_impacts_are_reported_without_rewriting(self):
        self.assertEqual(project_info.impacts({"project_type": "web", "specification": "default"}), [])
        self.assertEqual(project_info.impacts({"project_type": "cli", "specification": None}), [])
        for project_type in ("api", "cli", "mobile"):
            notes = project_info.impacts({"project_type": project_type, "specification": "default"})
            self.assertEqual(notes[0]["project_type"], project_type)
        result = self.initialize(project_type="api", specification="default")
        self.assertEqual((self.metadata()["project_type"], self.metadata()["specification"]), ("api", "default"))
        self.assertEqual(len(result["impacts"]), 1)

    def test_repository_plans_are_recorded_without_remote_or_scaffold_side_effects(self):
        calls = []
        original = project_init.git

        def recording(path, *args):
            calls.append(args)
            return original(path, *args)

        with mock.patch.object(project_init, "git", recording):
            self.initialize(repository_plan={"mode": "create_later"}, specification="default", project_type="web")
            receipt = self.read()
            self.update(receipt["read_id"], {"repository_plan": {"mode": "use_existing", "url": URL}})
        self.assertTrue(calls)
        self.assertTrue(all(args[0] == "rev-parse" for args in calls), calls)
        data = self.metadata()
        self.assertEqual(data["repository_plan"], {"mode": "use_existing", "url": URL})
        self.assertIsNone(data["github"]["url"])
        self.assertEqual(data["initialization"]["remote_link"]["status"], "pending")
        self.assertEqual(set(self.tree()), {"README.md", ".gitignore", "project.json"})

    def test_repository_conflicts_use_recorded_and_local_git_facts_without_echoing_credentials(self):
        self.initialize()
        data = self.metadata()
        data["github"]["url"] = URL
        self.write_metadata(data)
        for plan in ({"mode": "none"}, {"mode": "deferred"}, {"mode": "create_later"},
                     {"mode": "use_existing", "url": "https://github.com/example/other.git"}):
            with self.subTest(plan=plan):
                failure = self.update(self.read()["read_id"], {"repository_plan": plan}, error=True)
                self.assert_rejected(failure, "repository_fact_conflict")
                self.assertEqual(failure["facts"]["github_url"], URL)
        self.assertEqual(self.update(self.read()["read_id"], {"repository_plan": {"mode": "use_existing",
                                                                                  "url": URL}})["write_outcome"], "saved")
        data = self.metadata()
        data["github"]["url"] = "https://user:" + SECRET + "@github.com/example/demo.git"
        data.pop("repository_plan")
        self.write_metadata(data)
        failure = self.update(self.read()["read_id"], {"repository_plan": {"mode": "none"}}, error=True)
        self.assertNotIn(SECRET, json.dumps(failure, ensure_ascii=False))
        data["github"]["url"] = None
        self.write_metadata(data)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "origin", URL], check=True)
        failure = self.update(self.read()["read_id"], {"repository_plan": {"mode": "create_later"}}, error=True)
        self.assertEqual(failure["facts"]["git_remotes"], [URL])
        self.update(self.read()["read_id"], {"repository_plan": {"mode": "use_existing", "url": URL}})
        data["initialization"]["remote_link"] = {"status": "succeeded", "detail": "origin"}
        self.write_metadata({**self.metadata(), "initialization": data["initialization"]})
        self.assert_rejected(self.update(self.read()["read_id"], {"repository_plan": {"mode": "none"}}, error=True),
                             "repository_fact_conflict")

    # Step 7: controlled update kernel

    def kernel_update(self, changes, expected=None):
        raw = (self.project / "project.json").read_bytes()
        return project_info.update(self.foundation, "voice-meetup", changes,
                                   expected or hashlib.sha256(raw).hexdigest(), expected_root=self.project)

    def test_kernel_updates_only_requested_fields_and_is_idempotent(self):
        self.initialize(project_type="web")
        data = self.metadata()
        data["x_extension"] = {"keep": [1, 2]}
        self.write_metadata(data)
        (self.project / "docs").mkdir()
        (self.project / "docs/requirements.md").write_text("keep", encoding="utf-8")
        others = {key: value for key, value in self.tree().items() if key != "project.json"}
        result = self.kernel_update({"target_platforms": ["ios"], "specification": None})
        self.assertEqual((result["changed"], result["updated_fields"]), (True, ["target_platforms", "specification"]))
        after = self.metadata()
        self.assertEqual({key: value for key, value in after.items() if key not in ("target_platforms", "specification")},
                         data)
        self.assertEqual({key: value for key, value in self.tree().items() if key != "project.json"}, others)
        stat = (self.project / "project.json").stat()
        again = self.kernel_update({"target_platforms": ["ios"], "specification": None})
        self.assertEqual((again["changed"], again["sha256"]), (False, result["sha256"]))
        self.assertEqual((self.project / "project.json").stat().st_mtime_ns, stat.st_mtime_ns)
        modified = self.kernel_update({"project_type": "mobile"})
        self.assertEqual(modified["updated_fields"], ["project_type"])

    def test_kernel_rejects_forbidden_fields_conflicts_and_foreign_locks(self):
        self.initialize()
        before = self.tree()
        for changes in ({}, {"name": "x"}, {"project_id": "x"}, {"github": {}}, {"initialization": {}},
                        {"artifacts": {}}, {"artifact_registry": {}}, {"dependencies": {}}, {"surprise": 1},
                        {"project_type": "web", "purpose": "x"}):
            with self.subTest(changes=changes), self.assertRaises(project_info.InfoError) as caught:
                self.kernel_update(changes)
            self.assertIn(caught.exception.reason, {"invalid_arguments", "field_not_allowed"})
        with self.assertRaises(project_info.InfoError) as caught:
            self.kernel_update({"project_type": "web"}, expected="0" * 64)
        self.assertEqual(caught.exception.reason, "version_conflict")
        lock = self.project / ".project-state.lock"
        lock.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "写入锁已存在"):
            self.kernel_update({"project_type": "web"})
        self.assertTrue(lock.exists())
        lock.unlink()
        self.assertEqual(self.tree(), before)

    def test_old_project_without_fields_and_handwritten_invalid_values(self):
        self.initialize()
        data = self.metadata()
        state = self.call(mcp.PROJECT_INSPECT)
        self.assertEqual(state["project_info"]["unrecorded"], list(project_info.FIELDS))
        data["project_type"] = "Web"
        data["repository_plan"] = {"mode": "use_existing", "url": "https://u:" + SECRET + "@h.example/r"}
        self.write_metadata(data)
        state = self.call(mcp.PROJECT_INSPECT)
        self.assertEqual(state["project_info"]["invalid"], ["project_type", "repository_plan"])
        self.assertNotIn(SECRET, json.dumps(state, ensure_ascii=False))
        result = self.update(self.read()["read_id"], {"project_type": "web"})
        self.assertEqual(result["project_info"]["fields"]["project_type"], {"status": "recorded", "value": "web"})

    def test_unverified_and_unknown_write_results_are_reported(self):
        self.initialize()

        def corrupting(path, raw):
            path.write_bytes(raw + b"\n")

        with mock.patch.object(project_info, "atomic_replace", corrupting):
            failure = self.update(self.read()["read_id"], {"project_type": "web"}, error=True)
        self.assertEqual(failure["write_outcome"], "saved_unverified")
        with mock.patch.object(project_info, "atomic_replace", side_effect=OSError("disk full")):
            failure = self.update(self.read()["read_id"], {"project_type": "cli"}, error=True)
        self.assertEqual(failure["write_outcome"], "unknown")
        self.assertIn("勿盲目重试", failure["next_action"])

    # Step 8: MCP tool

    def test_update_tool_flow_and_read_reference_rules(self):
        self.initialize()
        first, other = self.read(), self.read()
        saved = self.update(first["read_id"], {"project_type": "web", "target_platforms": ["web"]})
        self.assertEqual((saved["write_outcome"], saved["verified"], saved["read_id_consumed"]), ("saved", True, True))
        self.assertEqual((saved["remote_actions"], saved["downstream_started"], saved["registered"]),
                         (False, False, False))
        self.assertEqual(saved["sha256"], hashlib.sha256((self.project / "project.json").read_bytes()).hexdigest())
        self.assertEqual(self.metadata()["target_platforms"], ["web"])
        self.assert_rejected(self.update(first["read_id"], {"project_type": "cli"}, error=True), "read_id_invalid")
        self.assert_rejected(self.update(other["read_id"], {"project_type": "cli"}, error=True), "version_conflict")
        conflict = self.call(mcp.SAVE_DRAFT, {"content": "# 需求", "read_id": other["read_id"]}, error=True)
        self.assertIn("project.json", conflict["changed"])
        fresh = self.read()
        unchanged = self.update(self.read()["read_id"], {"project_type": "web"})
        self.assertEqual(unchanged["write_outcome"], "unchanged")
        self.assertFalse(self.call(mcp.SAVE_DRAFT, {"content": "# 需求", "read_id": fresh["read_id"]})["history"])

    def test_update_rejections_do_not_write_or_consume_the_reference(self):
        self.initialize()
        receipt = self.read()
        before = self.tree()
        bad = [({"changes": {"project_type": "web"}}, None), ({"read_id": receipt["read_id"]}, "invalid_arguments"),
               ({"read_id": 5, "changes": {"project_type": "web"}}, None),
               ({"read_id": receipt["read_id"], "changes": ["project_type"]}, "invalid_arguments"),
               ({"read_id": receipt["read_id"], "changes": {}}, "invalid_arguments"),
               ({"read_id": receipt["read_id"], "changes": {"name": "x"}}, "field_not_allowed"),
               ({"read_id": receipt["read_id"], "changes": {"project_type": "Web"}}, "invalid_value"),
               ({"read_id": receipt["read_id"], "changes": {"specification": "absent"}}, "specification_not_found"),
               ({"read_id": "forged", "changes": {"project_type": "web"}}, "read_id_invalid"),
               ({"read_id": receipt["read_id"], "changes": {"project_type": "web"}, "allow_save": True}, None)]
        for arguments, reason in bad:
            with self.subTest(arguments=arguments):
                failure = self.call(mcp.UPDATE_INFO, arguments, error=True)
                self.assertEqual(failure["write_outcome"], "not_written")
                if reason:
                    self.assertEqual(failure["reason"], reason)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.update(receipt["read_id"], {"project_type": "web"})["write_outcome"], "saved")
        stale = self.read()
        self.now += mcp.READ_TTL + 1
        self.assert_rejected(self.update(stale["read_id"], {"project_type": "cli"}, error=True), "read_id_invalid")

    def test_update_tool_follows_capabilities_and_project_scope(self):
        for options, listed in (({}, False), ({"allow_initialize": True}, False), ({"allow_save": True}, True)):
            with self.subTest(options=options):
                self.server = mcp.McpServer(self.new_tools(**options))
                names = {tool["name"] for tool in self.rpc("tools/list")["result"]["tools"]}
                self.assertEqual(mcp.UPDATE_INFO in names, listed)
                if not listed:
                    failure = self.call(mcp.UPDATE_INFO, {"read_id": "x", "changes": {"project_type": "web"}},
                                        error=True)
                    self.assertEqual(failure["write_outcome"], "not_written")
        self.shared(allow_initialize=True, allow_save=True)
        other = self.projects / "other-project"
        for path in (self.project, other):
            self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(path), "name": "p", "purpose": "p"})
        receipt = self.call(mcp.READ_CONTEXT, {"project_path": str(self.project)})
        failure = self.call(mcp.UPDATE_INFO, {"project_path": str(other), "read_id": receipt["read_id"],
                                             "changes": {"project_type": "web"}}, error=True)
        self.assert_rejected(failure, "read_id_invalid")
        self.assertNotIn("project_type", self.metadata(other))
        self.call(mcp.UPDATE_INFO, {"project_path": str(self.project), "read_id": receipt["read_id"],
                                    "changes": {"project_type": "web"}})
        self.assertEqual(self.metadata()["project_type"], "web")

    def test_shared_entry_keeps_original_argument_protection(self):
        self.shared(allow_initialize=True, allow_save=True)
        path = {"project_path": str(self.project)}
        self.call(mcp.PROJECT_INITIALIZE, {**path, "name": "p", "purpose": "p"})
        receipt = self.call(mcp.READ_CONTEXT, path)
        before = self.tree()
        cases = [(mcp.SAVE_DRAFT, {"content": 5, "read_id": receipt["read_id"]}),
                 (mcp.SAVE_DRAFT, {"content": "x", "read_id": None}),
                 (mcp.SAVE_PRD_DRAFT, {"content": ["x"], "read_id": receipt["read_id"]}),
                 (mcp.READ_CONTEXT, {"history_sha256": ["a" * 64]}),
                 (mcp.READ_CONTEXT, {"include_recovery": "true"}), (mcp.READ_CONTEXT, {"include_recovery": 1}),
                 (mcp.PROJECT_INITIALIZE, {"name": None, "purpose": "p"}),
                 (mcp.PROJECT_INITIALIZE, {"name": "p", "purpose": "p", "project_type": ["web"]}),
                 (mcp.PROJECT_INSPECT, {"project_id": "x"}), (mcp.INSPECT_PRD, {"extra": True}),
                 (mcp.UPDATE_INFO, {"read_id": receipt["read_id"], "changes": "project_type=web"})]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                self.call(name, {**path, **arguments}, error=True)
        self.call(mcp.PROJECT_INSPECT, {"project_path": 5}, error=True)
        self.assertEqual(self.tree(), before)
        self.call(mcp.SAVE_DRAFT, {**path, "content": "# 仍可保存", "read_id": receipt["read_id"]})

    def test_stdio_process_discovers_and_calls_the_update_tool(self):
        command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "cursor_mcp.py"), "--foundation",
                   str(self.foundation), "--allow-initialize", "--allow-save"]
        path = self.projects / "stdio-info"

        def request(number, name, arguments):
            return {"jsonrpc": "2.0", "id": number, "method": "tools/call",
                    "params": {"_meta": self.meta(), "name": name, "arguments": {"project_path": str(path), **arguments}}}

        first = [{"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {"_meta": self.meta()}},
                 request(1, mcp.PROJECT_INITIALIZE, {"name": "stdio", "purpose": "t", "specification": None}),
                 request(2, mcp.READ_CONTEXT, {})]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            outputs = []
            for message in first:
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
                outputs.append(json.loads(process.stdout.readline())["result"])
            read_id = json.loads(outputs[2]["content"][0]["text"])["read_id"]
            process.stdin.write(json.dumps(request(3, mcp.UPDATE_INFO, {
                "read_id": read_id, "changes": {"project_type": "cli", "repository_plan": {"mode": "none"}}})) + "\n")
            process.stdin.flush()
            outputs.append(json.loads(process.stdout.readline())["result"])
        finally:
            process.stdin.close()
            process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()
        self.assertIn(mcp.UPDATE_INFO, {tool["name"] for tool in outputs[0]["tools"]})
        self.assertTrue(all(not output["isError"] for output in outputs[1:]), outputs)
        data = self.metadata(path)
        self.assertEqual((data["specification"], data["project_type"], data["repository_plan"]),
                         (None, "cli", {"mode": "none"}))


if __name__ == "__main__":
    unittest.main()
