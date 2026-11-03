"""Shared MCP routing, project isolation and global configuration on temp files."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_requirements_cursor_tools as fixtures
import cursor_mcp as mcp
import configure_cursor


class SharedToolsTests(unittest.TestCase):
    setUp = fixtures.CursorToolsTests.setUp
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools
    tree = fixtures.CursorToolsTests.tree
    meta = staticmethod(fixtures.CursorToolsTests.meta)
    rpc = fixtures.CursorToolsTests.rpc
    call = fixtures.CursorToolsTests.call

    def shared(self, **options):
        return mcp.SharedProjectTools(foundation=self.foundation, clock=lambda: self.now, **options)

    def connect(self, **options):
        self.server = mcp.McpServer(self.shared(**options))

    def operation(self, operation_name, path, **arguments):
        return self.call(operation_name, {"project_path": str(path), **arguments})

    def init(self, path):
        return self.operation(mcp.PROJECT_INITIALIZE, path, name=path.name, purpose="共用入口临时测试")

    def test_shared_discovery_exposes_explicit_path_and_instructions_without_project_access(self):
        self.connect(allow_initialize=True, allow_save=True)
        for tool in self.rpc("tools/list")["result"]["tools"]:
            self.assertIn("project_path", tool["inputSchema"]["required"])
            self.assertNotIn("project_id", tool["inputSchema"]["required"])
            if tool["name"] != mcp.PROJECT_INITIALIZE:
                self.assertNotIn("project_id", tool["inputSchema"]["properties"])
            if tool["name"] == mcp.READ_CONTEXT:
                self.assertIn(mcp.AGENT_WORKFLOW_PATH.read_text(encoding="utf-8"), tool["description"])
        self.assertEqual(self.tree(), {})
        self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}, modern=False)
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(len(self.rpc("tools/list", modern=False)["result"]["tools"]), 7)
        self.call(mcp.PROJECT_INSPECT, {}, error=True)

    def test_interleaved_projects_cannot_exchange_read_references_or_histories(self):
        self.connect(allow_initialize=True, allow_save=True)
        other = self.projects / "另一个项目"
        before_config = (self.foundation / "config/local.json").read_bytes()
        self.init(self.project)
        self.init(other)
        a = self.operation(mcp.READ_CONTEXT, self.project)
        b = self.operation(mcp.READ_CONTEXT, other)
        self.call(mcp.SAVE_DRAFT, {"project_path": str(other), "content": "wrong project",
                                   "read_id": a["read_id"]}, error=True)
        first = self.operation(mcp.SAVE_DRAFT, self.project, content="# A 第一版", read_id=a["read_id"])
        second = self.operation(mcp.SAVE_DRAFT, other, content="# B 第一版", read_id=b["read_id"])
        a = self.operation(mcp.READ_CONTEXT, self.project)
        self.operation(mcp.SAVE_DRAFT, self.project, content="# A 第二版", read_id=a["read_id"])
        history = self.operation(mcp.READ_CONTEXT, self.project, history_sha256=first["sha256"])
        self.assertEqual(history["history"]["content"], first["document"]["content"])
        self.assertEqual(self.operation(mcp.READ_CONTEXT, other)["documents"][-1]["content"],
                         second["document"]["content"])
        self.assertEqual(self.operation(mcp.READ_CONTEXT, other, history_sha256=first["sha256"])["history"]["sha256"], "missing")
        self.assertEqual((self.foundation / "config/local.json").read_bytes(), before_config)

    def test_unmapped_chinese_directory_initializes_and_reopens_without_config_change(self):
        self.connect(allow_initialize=True, allow_save=True)
        path = self.projects / "新的中文项目"
        state = self.operation(mcp.PROJECT_INSPECT, path)
        self.assertFalse(path.exists())
        self.assertTrue(state["project_id"].startswith("req-"))
        self.init(path)
        self.connect(allow_initialize=True, allow_save=True)
        again = self.operation(mcp.PROJECT_INSPECT, path)
        self.assertEqual(again["project_id"], state["project_id"])
        self.assertTrue(again["initialized"])
        self.assertFalse(self.init(path)["changed"])
        self.assertFalse((path / ".git").exists())

    def test_ascii_directory_and_existing_identity_are_reused(self):
        self.connect(allow_initialize=True, allow_save=True)
        path = self.projects / "second-project"
        self.assertEqual(self.operation(mcp.PROJECT_INSPECT, path)["project_id"], path.name)
        self.init(path)
        self.connect()
        self.assertEqual(self.operation(mcp.READ_CONTEXT, path)["project_id"], path.name)

    def test_scope_traversal_symlink_and_root_rebinding_are_rejected(self):
        self.connect(allow_initialize=True, allow_save=True)
        outside = self.root / "outside"
        outside.mkdir()
        link = self.projects / "linked"
        link.symlink_to(outside, target_is_directory=True)
        for path in (outside, self.projects, self.projects / "nested/child", link,
                     self.projects / "../projects/语音约碰面地点"):
            with self.subTest(path=path):
                self.call(mcp.PROJECT_INSPECT, {"project_path": str(path)}, error=True)
        self.config["projects_root"] = str(outside)
        self.write_config()
        failure = self.call(mcp.PROJECT_INSPECT, {"project_path": str(self.project)}, error=True)
        self.assertIn("根目录已改变", failure["error"])

    def test_parent_replacement_and_metadata_identity_collision_cannot_redirect(self):
        self.connect(allow_initialize=True, allow_save=True)
        self.init(self.project)
        receipt = self.operation(mcp.READ_CONTEXT, self.project)
        import shutil
        duplicate = self.projects / "重复身份"
        shutil.copytree(self.project, duplicate)
        self.call(mcp.PROJECT_INSPECT, {"project_path": str(duplicate)}, error=True)
        old = self.projects.with_name("original-projects")
        self.projects.rename(old)
        replacement = self.root / "replacement"
        replacement.mkdir()
        self.projects.symlink_to(replacement, target_is_directory=True)
        self.call(mcp.SAVE_DRAFT, {"project_path": str(self.project), "content": "blocked",
                                   "read_id": receipt["read_id"]}, error=True)
        self.assertFalse((old / self.project.name / "docs").exists())
        self.assertEqual(list(replacement.iterdir()), [])

    def test_read_only_and_identity_parameters_cannot_expand_capabilities(self):
        self.connect()
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {mcp.PROJECT_INSPECT, mcp.READ_CONTEXT, mcp.INSPECT_PRD})
        self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.project), "name": "x", "purpose": "x"}, error=True)
        self.call(mcp.PROJECT_INSPECT, {"project_path": str(self.project), "project_id": "injected"}, error=True)
        self.assertEqual(self.tree(), {})

    def test_nonempty_uninitialized_directory_is_preserved(self):
        self.connect(allow_initialize=True)
        (self.project / "notes.md").write_text("keep", encoding="utf-8")
        before = self.tree()
        self.call(mcp.PROJECT_INITIALIZE, {"project_path": str(self.project), "name": "x", "purpose": "x"}, error=True)
        self.assertEqual(self.tree(), before)

    def test_global_entry_merges_once_without_fixed_project_arguments(self):
        home = self.root / "home"
        home.mkdir()
        (home / ".cursor").mkdir()
        path = home / ".cursor/mcp.json"
        path.write_text('{"mcpServers":{"other":{"command":"keep"}},"setting":42}', encoding="utf-8")
        binding = dict(workspace=home, foundation=self.foundation, python_executable=sys.executable)
        preview = configure_cursor.configure(**binding)
        self.assertEqual(preview["server_name"], "requirements")
        self.assertNotIn("--project-id", preview["server"]["args"])
        self.assertNotIn("--project-root", preview["server"]["args"])
        result = configure_cursor.configure(**binding, apply=True, expected_sha256=preview["expected_config_sha256"])
        data = json.loads(path.read_text())
        self.assertEqual(data["mcpServers"]["other"], {"command": "keep"})
        self.assertEqual(data["setting"], 42)
        self.assertTrue(result["applied"])
        again = configure_cursor.configure(**binding)
        self.assertFalse(again["changed"])

    def test_legacy_entry_migration_preserves_other_settings_and_rejects_drift(self):
        folder = self.project / ".cursor"
        folder.mkdir()
        path = folder / "mcp.json"
        entry = {"command": "old"}
        data = {"mcpServers": {"requirements-voice-meetup": entry, "other": {"command": "keep"}}, "setting": 1}
        path.write_text(json.dumps(data), encoding="utf-8")
        _, sha, _ = configure_cursor.read_configuration(self.project)
        binding = dict(workspace=self.project, server_name="requirements-voice-meetup", expected_entry=entry)
        with self.assertRaisesRegex(ValueError, "版本冲突"):
            configure_cursor.remove_scoped_entry(**binding, expected_sha256="missing")
        configure_cursor.remove_scoped_entry(**binding, expected_sha256=sha)
        result = json.loads(path.read_text())
        self.assertEqual(result, {"mcpServers": {"other": {"command": "keep"}}, "setting": 1})

    def test_shared_stdio_subprocess_routes_a_project_selected_in_call(self):
        command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "cursor_mcp.py"), "--foundation", str(self.foundation),
                   "--allow-initialize", "--allow-save"]
        path = self.projects / "stdio-new"
        def request(number, name, arguments):
            return {"jsonrpc": "2.0", "id": number, "method": "tools/call",
                    "params": {"_meta": self.meta(), "name": name,
                               "arguments": {"project_path": str(path), **arguments}}}
        messages = [request(1, mcp.PROJECT_INSPECT, {}),
                    request(2, mcp.PROJECT_INITIALIZE, {"name": "stdio", "purpose": "test"}),
                    request(3, mcp.READ_CONTEXT, {})]
        response = subprocess.run(command, input="".join(json.dumps(m) + "\n" for m in messages),
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        results = [json.loads(line)["result"] for line in response.stdout.splitlines()]
        self.assertEqual(len(results), 3)
        self.assertTrue(all(not result["isError"] for result in results))
        context = json.loads(results[-1]["content"][0]["text"])
        self.assertEqual(context["project_id"], path.name)
        self.assertIn("read_id", context)


if __name__ == "__main__":
    unittest.main()
