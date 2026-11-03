"""Read-only recovery materials and fixed-directory PRD confirmation checks on temp projects."""

import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_requirements_cursor_tools as fixtures
import cursor_mcp as mcp
from file_tools import project_init, recovery

LOCAL_TOOLS = Path(recovery.__file__).resolve().parent
LEGACY_MODULES = ("collaboration", "artifacts", "trusted_context")
CONFIRMATION_ID = "C-" + "a" * 20
START = "<!-- buzz-develop-helper:confirmations:start -->"
END = "<!-- buzz-develop-helper:confirmations:end -->"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class RecoveryTests(unittest.TestCase):
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools
    meta = staticmethod(fixtures.CursorToolsTests.meta)
    rpc = fixtures.CursorToolsTests.rpc
    call = fixtures.CursorToolsTests.call

    def setUp(self):
        fixtures.CursorToolsTests.setUp(self)
        self.shared_server = None
        self.root_path = self.project
        self.identifier = "voice-meetup"
        self.call(mcp.PROJECT_INITIALIZE, {"name": "语音约碰面地点", "purpose": "恢复测试"})

    def tree(self, root=None):
        root = root or self.root_path
        return {p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else None
                for p in sorted(root.rglob("*"))}

    def use_shared_unmapped(self):
        self.server = mcp.McpServer(mcp.SharedProjectTools(foundation=self.foundation, allow_initialize=True,
                                                           allow_save=True, clock=lambda: self.now))
        self.root_path = self.projects / "未映射中文项目"
        state = self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.root_path), "name": "中文",
                                                   "purpose": "固定目录"})
        self.identifier = state["project_id"]
        self.assertTrue(self.identifier.startswith("req-"))

    def args(self, **arguments):
        if self.root_path != self.project:
            arguments["project_path"] = str(self.root_path)
        return arguments

    def recover(self, **arguments):
        return self.call(mcp.READ_CONTEXT, self.args(include_recovery=True, **arguments))

    def write(self, relative, text):
        path = self.root_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return sha(path.read_bytes())

    def write_prd(self, body="# PRD\n\nREQ-001", requirements_sha="missing"):
        return self.write("docs/PRD.md", "---\nartifact_kind: prd\nstatus: Draft\napproval_verified: false\n"
                                         f"source_requirements_path: docs/requirements.md\n"
                                         f"source_requirements_sha256: {requirements_sha}\n---\n\n{body}\n")

    def confirm(self, *, purpose="形成技术方案", project_id=None, open_items=(), tamper_snapshot=False):
        prd = (self.root_path / "docs/PRD.md").read_bytes()
        digest = sha(prd)
        snapshot = f"docs/confirmations/snapshots/{digest}/PRD.md"
        target = self.root_path / snapshot
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(prd + (b"tampered" if tamper_snapshot else b""))
        data = json.loads((self.root_path / "project.json").read_text(encoding="utf-8"))
        data["artifact_registry"] = {
            "schema_version": 1, "confirmations_path": "docs/decisions.md", "handoffs_directory": "docs/handoffs",
            "entries": {"prd": {"artifact_id": "prd", "kind": "requirements", "current_version": "v1", "versions": [{
                "version": "v1", "content": {"type": "file", "path": snapshot, "sha256": sha(target.read_bytes()),
                                             "size": target.stat().st_size},
                "confirmation_ids": [CONFIRMATION_ID], "producer_role": "requirements", "purpose": "PRD",
                "summary": "PRD v1", "document_status": "Draft", "open_items": list(open_items),
                "availability": {"scope": "local-only", "git_commit": None},
                "registration": {"actor": {"role": "main", "principal_id": "main", "authority": "buzz"},
                                 "recorded_at": "2026-10-29T00:00:00Z"}}]}}}
        (self.root_path / "project.json").write_text(project_init.json_text(data), encoding="utf-8")
        record = {"schema_version": 1, "confirmation_id": CONFIRMATION_ID, "status": "active",
                  "project_id": project_id or self.identifier,
                  "artifact": {"artifact_id": "prd", "kind": "requirements", "version": "v1",
                               "content_sha256": digest, "registered_path": "docs/PRD.md"},
                  "snapshot": {"type": "file", "path": snapshot, "sha256": digest},
                  "permitted_use": purpose, "confirmed_scope": "全部", "non_authorizations": [],
                  "open_items": list(open_items),
                  "evidence": {"type": "current-session", "provider": "buzz", "authority": "buzz",
                               "user_principal_id": "bowen", "session_id": "s", "message_id": "m",
                               "confirmed_at": "2026-10-29T00:00:00Z", "statement": "确认 PRD",
                               "runtime_authenticated": True},
                  "recorded_by": {"principal_id": "main", "authority": "buzz"},
                  "recorded_at": "2026-10-29T00:00:00Z"}
        block = json.dumps({"schema_version": 1, "confirmations": [record]}, ensure_ascii=False, indent=2)
        self.write("docs/decisions.md", f"# 项目确认记录\n\n{START}\n```json\n{block}\n```\n{END}\n")
        return digest

    def confirmation(self):
        before = self.tree()
        result = self.recover()["recovery"]["confirmations"]
        self.assertEqual(self.tree(), before)
        self.assertFalse(result["confirmation_written"])
        self.assertFalse(result["downstream_started"])
        return result

    # Step 9: recovery materials

    def test_recovery_is_opt_in_and_keeps_the_four_file_reference(self):
        plain = self.call(mcp.READ_CONTEXT)
        self.assertNotIn("recovery", plain)
        self.assertNotIn("recovery", self.call(mcp.READ_CONTEXT, {"include_recovery": False}))
        held = self.call(mcp.READ_CONTEXT)
        recovered = self.recover()
        self.assertEqual([item["path"] for item in recovered["documents"]],
                         [item["path"] for item in plain["documents"]])
        tool = self.server.tools
        self.assertEqual(set(tool.reads[recovered["read_id"]][1]),
                         {"project.json", "README.md", "docs/PRD.md", "docs/requirements.md"})
        self.assertFalse(recovered["recovery"]["consumes_read_id"])
        self.assertFalse(recovered["recovery"]["atomic_snapshot"])
        self.assertEqual(tool.reads[recovered["read_id"]][1], tool.reads[held["read_id"]][1])
        self.call(mcp.SAVE_DRAFT, {"content": "# 仍可保存", "read_id": held["read_id"]})

    def test_materials_versions_and_source_relationships_match_files(self):
        requirements_sha = self.write("docs/requirements.md", "# 需求\n")
        prd_sha = self.write_prd(requirements_sha=requirements_sha)
        self.write("docs/tech-spec.md", f"---\nstatus: Draft\nprd_sha256: {prd_sha}\n---\n\n# 方案\n")
        material = self.recover()["recovery"]
        self.assertEqual(material["project"]["project_info"]["unrecorded"][0], "project_type")
        self.assertEqual(material["requirements"]["sha256"], requirements_sha)
        self.assertEqual(material["prd"]["source"], {"recorded": True, "requirements_sha256": requirements_sha,
                                                     "matches_current": True})
        solution, tech = material["solutions"]
        self.assertEqual(solution["status"], "missing")
        self.assertEqual((tech["status"], tech["prd_binding"]["matches_current"]), ("present", True))
        self.assertIn("# 方案", tech["content"])
        for path, version in material["read_versions"].items():
            if version not in (None, "missing"):
                self.assertEqual(version, sha((self.root_path / path).read_bytes()), path)
        self.assertEqual(material["changed_during_read"], [])
        self.write("docs/requirements.md", "# 需求 第二版\n")
        changed = self.recover()["recovery"]
        self.assertFalse(changed["prd"]["source"]["matches_current"])
        self.write_prd(body="# PRD v2")
        self.assertFalse(self.recover()["recovery"]["solutions"][1]["prd_binding"]["matches_current"])

    def test_missing_unreadable_and_invalid_materials_are_distinct_and_never_created(self):
        (self.root_path / "docs/solution.md").mkdir(parents=True)
        self.write("docs/tech-spec.md", "---\nprd_sha256: not-a-digest\n---\n\n# 方案\n")
        self.write("docs/PRD.md", "# 旧版 PRD 无来源\n")
        data = json.loads((self.root_path / "project.json").read_text(encoding="utf-8"))
        data["specification"] = "null"
        (self.root_path / "project.json").write_text(project_init.json_text(data), encoding="utf-8")
        before = self.tree()
        material = self.recover()["recovery"]
        self.assertEqual(self.tree(), before)
        solution, tech = material["solutions"]
        self.assertEqual((solution["status"], tech["status"]), ("unreadable", "invalid"))
        self.assertEqual(material["requirements"]["status"], "missing")
        self.assertEqual(material["prd"]["source"], {"recorded": False, "requirements_sha256": None,
                                                     "matches_current": None})
        self.assertEqual(material["project"]["project_info"]["invalid"], ["specification"])
        self.assertFalse((self.root_path / "docs/requirements.md").exists())

    def test_changes_during_recovery_are_reported_not_hidden(self):
        original = recovery.verify_prd_confirmation

        def changing(*args, **kwargs):
            self.write("docs/requirements.md", "# 读取期间被修改\n")
            return original(*args, **kwargs)

        with mock.patch.object(recovery, "verify_prd_confirmation", changing):
            material = self.recover()["recovery"]
        self.assertIn("docs/requirements.md", material["changed_during_read"])
        self.assertFalse(material["atomic_snapshot"])

    def test_symlinked_material_and_other_projects_are_not_read(self):
        self.use_shared_unmapped()
        outside = self.root / "outside.md"
        outside.write_text("secret outside", encoding="utf-8")
        (self.root_path / "docs").mkdir()
        (self.root_path / "docs/tech-spec.md").symlink_to(outside)
        other = self.projects / "other-project"
        self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(other), "name": "o", "purpose": "o"})
        (other / "docs").mkdir()
        (other / "docs/solution.md").write_text("other project solution", encoding="utf-8")
        material = self.recover()["recovery"]
        tech = material["solutions"][1]
        self.assertEqual((tech["status"], tech["content"]), ("unreadable", None))
        self.assertNotIn("other project solution", json.dumps(material, ensure_ascii=False))
        self.assertNotIn("secret outside", json.dumps(material, ensure_ascii=False))

    # Step 10: confirmation checks

    def test_valid_confirmation_on_unmapped_chinese_directory(self):
        self.use_shared_unmapped()
        self.write_prd()
        self.confirm()
        result = self.confirmation()
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual(result["records"][0]["result"], "valid")
        for name in LEGACY_MODULES:
            self.assertNotIn(name, sys.modules)
        confirmations, registry = recovery.load_validators()
        for module in (confirmations, registry):
            self.assertEqual(Path(module.__file__).resolve().parent, LOCAL_TOOLS)
        self.assertFalse(any("buzz-develop-helper" in entry for entry in sys.path))
        self.assertFalse((self.foundation / "scripts").exists())

    def test_changed_prd_makes_a_valid_confirmation_outdated(self):
        self.write_prd()
        self.confirm()
        self.write_prd(body="# PRD 已修改")
        result = self.confirmation()
        self.assertEqual((result["status"], result["records"][0]["reasons"]), ("outdated", ["prd_changed"]))

    def test_other_purpose_project_open_items_and_snapshot_are_not_authorization(self):
        cases = [({"purpose": "其他用途"}, "missing", ["purpose_mismatch"]),
                 ({"project_id": "another-project"}, "missing", ["other_project"]),
                 ({"open_items": ["待定"]}, "invalid", None), ({"tamper_snapshot": True}, "invalid", None)]
        for options, status, reasons in cases:
            with self.subTest(options=options):
                self.write_prd()
                self.confirm(**options)
                result = self.confirmation()
                self.assertEqual(result["status"], status, result)
                if reasons:
                    self.assertEqual(result["reasons"], reasons)
        self.confirm(open_items=["待定"])
        self.assertIn("open_items_pending", self.confirmation()["records"][0]["reasons"])
        self.confirm(tamper_snapshot=True)
        self.assertIn("snapshot_mismatch", self.confirmation()["records"][0]["reasons"])

    def test_missing_records_malformed_records_and_drafts_are_not_confirmation(self):
        self.assertEqual(self.confirmation()["reasons"], ["prd_missing"])
        self.write_prd()
        result = self.confirmation()
        self.assertEqual((result["status"], result["reasons"]), ("missing", ["decisions_missing"]))
        self.write("docs/decisions.md", "# 项目确认记录\n\n用户已确认 PRD，可以形成技术方案。\n")
        self.assertEqual(self.confirmation()["status"], "invalid")
        self.write("docs/decisions.md", f"{START}\n```json\n{{\"schema_version\": 1, \"confirmations\": [{{}}]}}\n```\n{END}\n")
        self.assertEqual(self.confirmation()["reasons"], ["decisions_invalid"])

    def test_unavailable_validator_keeps_other_recovery_results(self):
        self.write_prd()
        with mock.patch.object(recovery, "load_validators", side_effect=ImportError("validators missing")):
            material = self.recover()["recovery"]
        self.assertEqual(material["confirmations"]["status"], "unavailable")
        self.assertEqual(material["confirmations"]["reasons"], ["validator_unavailable"])
        self.assertEqual(material["prd"]["status"], "present")
        self.assertEqual(material["project"]["status"], "present")


if __name__ == "__main__":
    unittest.main()
