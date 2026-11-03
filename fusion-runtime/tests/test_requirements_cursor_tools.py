"""Cursor MCP transport and fixed-project calls against disposable real files."""

import io
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS_ROOT = Path(__file__).resolve().parents[1] / "workflows/requirements"
sys.path.insert(0, str(TOOLS_ROOT))
import cursor_mcp as mcp
import configure_cursor


class CursorToolsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cursor-requirements-tools-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.foundation = self.root / "foundation"
        self.source = self.root / "source"
        self.projects = self.root / "projects"
        for path in (self.foundation / "config", self.foundation / "methods", self.source, self.projects):
            path.mkdir(parents=True)
        (self.source / "rules.md").write_text("fixture source", encoding="utf-8")
        (self.foundation / "methods/develop-helper").symlink_to(self.source, target_is_directory=True)
        from file_tools.check_foundation import snapshot
        (self.foundation / "upstream-lock.json").write_text(json.dumps(snapshot(self.source)), encoding="utf-8")
        self.project = self.projects / "语音约碰面地点"
        self.project.mkdir()
        self.config = {"schema_version": 1, "upstream_root": str(self.source),
                       "projects_root": str(self.projects),
                       "project_directories": {"voice-meetup": self.project.name}}
        self.write_config()
        self.now = 0
        self.tools = self.new_tools(allow_initialize=True, allow_save=True)
        self.server = mcp.McpServer(self.tools)

    def write_config(self):
        (self.foundation / "config/local.json").write_text(json.dumps(self.config), encoding="utf-8")

    def new_tools(self, **options):
        return mcp.ProjectTools(foundation=self.foundation, project_id="voice-meetup",
                                project_root=self.project, clock=lambda: self.now, **options)

    def tree(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() if p.is_file() else None
                for p in sorted(self.project.rglob("*"))}

    @staticmethod
    def meta(version=mcp.MODERN_VERSION):
        return {mcp.META_PREFIX + "protocolVersion": version,
                mcp.META_PREFIX + "clientCapabilities": {},
                mcp.META_PREFIX + "clientInfo": {"name": "test-client", "version": "1"}}

    def rpc(self, method, params=None, *, modern=True):
        params = dict(params or {})
        if modern:
            params["_meta"] = self.meta()
        return self.server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

    def call(self, name, arguments=None, *, error=False):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        self.assertNotIn("error", response, response)
        self.assertEqual(response["result"]["isError"], error, response)
        return json.loads(response["result"]["content"][0]["text"])

    def initialize(self):
        return self.call(mcp.PROJECT_INITIALIZE, {"name": "语音约碰面地点", "purpose": "临时工具测试"})

    def save(self, content, receipt, *, error=False):
        return self.call(mcp.SAVE_DRAFT, {"content": content, "read_id": receipt["read_id"]}, error=error)

    def binding(self):
        return dict(workspace=self.project, foundation=self.foundation, project_id="voice-meetup",
                    project_root=self.project, python_executable=Path(sys.executable))

    def test_modern_discovery_and_list_are_read_only(self):
        discovery = self.rpc("server/discover")["result"]
        self.assertIn(mcp.MODERN_VERSION, discovery["supportedVersions"])
        self.assertEqual(discovery["resultType"], "complete")
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {mcp.PROJECT_INSPECT, mcp.PROJECT_INITIALIZE,
                                                     mcp.READ_CONTEXT, mcp.SAVE_DRAFT,
                                                     mcp.INSPECT_PRD, mcp.SAVE_PRD_DRAFT, mcp.UPDATE_INFO})
        for tool in tools:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertNotIn("project_id", tool["inputSchema"]["properties"])
        self.assertEqual(self.tree(), {})

    def test_legacy_handshake_and_ping(self):
        self.assertIn("error", self.rpc("tools/list", modern=False))
        initialized = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}, modern=False)
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(len(self.rpc("tools/list", modern=False)["result"]["tools"]), 7)
        self.assertEqual(self.rpc("ping", modern=False)["result"], {})

    def test_main_document_hint_does_not_read_rules_or_gate_project_inspection(self):
        original_open = Path.open

        def without_rules(path, *args, **kwargs):
            if path == mcp.MAIN_RULES_PATH:
                raise AssertionError("工具发现和单独项目检查不应读取主规则正文")
            return original_open(path, *args, **kwargs)

        self.assertTrue(mcp.MAIN_RULES_PATH.is_absolute())
        self.assertEqual(mcp.MAIN_RULES_PATH, TOOLS_ROOT.resolve() / "requirements.md")
        before = self.tree()
        with mock.patch.object(Path, "open", without_rules):
            for shared in (False, True):
                for initialize, save in ((False, False), (True, False), (False, True), (True, True)):
                    with self.subTest(shared=shared, initialize=initialize, save=save):
                        options = dict(allow_initialize=initialize, allow_save=save)
                        tools = (mcp.SharedProjectTools(foundation=self.foundation, **options)
                                 if shared else self.new_tools(**options))
                        self.server = mcp.McpServer(tools)
                        listing = self.rpc("tools/list")["result"]["tools"]
                        self.assertEqual(len(listing), 3 + initialize + 3 * save)
                        for tool in listing:
                            self.assertIn(str(mcp.MAIN_RULES_PATH), tool["description"])
                            self.assertIn("无须额外加载需求方法", tool["description"])
                            self.assertNotIn("rules_path", tool["inputSchema"]["properties"])
                        arguments = {"project_path": str(self.project)} if shared else {}
                        state = self.call(mcp.PROJECT_INSPECT, arguments)
                        self.assertEqual(state["status"], "empty_directory")
        self.assertEqual(self.tree(), before)

    def test_notifications_cannot_execute_writes(self):
        request = {"jsonrpc": "2.0", "method": "tools/call", "params": {
            "name": mcp.PROJECT_INITIALIZE, "arguments": {"name": "Injected", "purpose": "ignored"}}}
        self.assertIsNone(self.server.handle(request))
        self.assertEqual(self.tree(), {})

    def test_modern_metadata_and_unknown_versions_are_rejected(self):
        missing = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "server/discover"})
        self.assertEqual(missing["error"]["code"], -32602)
        unknown = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                                      "params": {"_meta": self.meta("2099-01-01")}})
        self.assertEqual(unknown["error"]["code"], -32022)
        self.assertEqual(unknown["error"]["data"]["requested"], "2099-01-01")

    def test_read_only_launcher_grants_cannot_be_expanded_by_arguments(self):
        self.server = mcp.McpServer(self.new_tools())
        self.assertEqual({t["name"] for t in self.rpc("tools/list")["result"]["tools"]},
                         {mcp.PROJECT_INSPECT, mcp.READ_CONTEXT, mcp.INSPECT_PRD})
        self.call(mcp.PROJECT_INITIALIZE, {"name": "x", "purpose": "x", "allow_initialize": True}, error=True)
        self.call(mcp.SAVE_DRAFT, {"content": "x", "read_id": "x", "allow_save": True}, error=True)
        self.call(mcp.SAVE_PRD_DRAFT, {"content": "x", "read_id": "x", "allow_save": True}, error=True)
        self.assertEqual(self.tree(), {})

    def test_initialization_and_existing_project_check(self):
        state = self.call(mcp.PROJECT_INSPECT)
        self.assertEqual(state["status"], "empty_directory")
        self.assertTrue(self.initialize()["changed"])
        self.assertEqual(set(self.tree()), {"README.md", ".gitignore", "project.json"})
        before = self.tree()
        again = self.initialize()
        self.assertFalse(again["changed"])
        self.assertEqual(self.tree(), before)
        self.assertTrue(self.call(mcp.PROJECT_INSPECT)["initialized"])

    def test_nonempty_uninitialized_directory_is_not_adopted(self):
        (self.project / "notes.md").write_text("user content", encoding="utf-8")
        before = self.tree()
        self.call(mcp.PROJECT_INITIALIZE, {"name": "x", "purpose": "x"}, error=True)
        self.assertEqual(self.tree(), before)

    def test_missing_directory_can_be_created_only_by_enabled_initialization(self):
        self.project.rmdir()
        self.assertEqual(self.call(mcp.PROJECT_INSPECT)["status"], "not_created")
        self.assertTrue(self.initialize()["changed"])
        self.assertTrue((self.project / "project.json").is_file())

    def test_exact_save_readback_history_and_noop(self):
        self.initialize()
        first = self.save("# 需求\n第一版", self.call(mcp.READ_CONTEXT))
        old = (self.project / "docs/requirements.md").read_bytes()
        self.assertTrue(first["verified"])
        self.assertFalse(first["registered"])
        second = self.save("# 需求\n第二版", self.call(mcp.READ_CONTEXT))
        self.assertEqual(second["document"]["content"],
                         "---\nstatus: Draft\napproval_verified: false\n---\n\n# 需求\n第二版\n")
        self.assertEqual(second["history"]["content"].encode("utf-8"), old)
        history = self.call(mcp.READ_CONTEXT, {"history_sha256": first["sha256"]})
        self.assertEqual(history["history"]["content"].encode("utf-8"), old)
        before = self.tree()
        self.assertFalse(self.save("# 需求\n第二版", self.call(mcp.READ_CONTEXT))["changed"])
        self.assertEqual(self.tree(), before)
        restored = self.save("# 需求\n第一版", self.call(mcp.READ_CONTEXT))
        self.assertEqual(restored["document"]["content"].encode("utf-8"), old)
        self.assertEqual(restored["history"]["content"], second["document"]["content"])
        for saved in (first, second):
            history = self.call(mcp.READ_CONTEXT, {"history_sha256": saved["sha256"]})
            self.assertEqual(history["history"]["content"], saved["document"]["content"])
        self.assertEqual(len(list((self.project / "docs/requirements-history").glob("*.md"))), 2)

    def test_target_version_conflict_never_overwrites(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        (self.project / "docs").mkdir()
        (self.project / "docs/requirements.md").write_text("concurrent edit", encoding="utf-8")
        before = self.tree()
        failure = self.save("overwrite", receipt, error=True)
        self.assertEqual(failure["write_outcome"], "not_written")
        self.assertEqual(self.tree(), before)

    def test_source_version_conflict_requires_review_instead_of_refreshing_expected_version(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        (self.project / "README.md").write_text("changed source", encoding="utf-8")
        failure = self.save("draft", receipt, error=True)
        self.assertIn("README.md", failure["changed"])
        self.assertFalse((self.project / "docs").exists())

    def test_fake_expired_or_reused_read_reference_is_rejected(self):
        self.initialize()
        self.save("draft", {"read_id": "forged"}, error=True)
        receipt = self.call(mcp.READ_CONTEXT)
        self.now = mcp.READ_TTL + 1
        self.save("draft", receipt, error=True)
        fresh = self.call(mcp.READ_CONTEXT)
        self.save("draft", fresh)
        before = self.tree()
        self.save("draft", fresh, error=True)
        self.assertEqual(self.tree(), before)

    def test_body_metadata_invalid_history_and_reserved_identity_fields_are_rejected(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        for content in ("---\nstatus: Confirmed\n---\nbody", "x" * mcp.requirements.LIMIT):
            with self.subTest(content_length=len(content)):
                self.save(content, receipt, error=True)
        for field in ("project_id", "project_root", "expected_root", "role", "authorized"):
            with self.subTest(field=field):
                self.call(mcp.READ_CONTEXT, {field: "injected"}, error=True)
        self.call(mcp.READ_CONTEXT, {"history_sha256": "../../outside"}, error=True)
        self.assertFalse((self.project / "docs").exists())

    def test_configuration_remap_is_rejected_by_the_bound_server(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        self.config["project_directories"]["voice-meetup"] = "另一个项目"
        self.write_config()
        self.save("draft", receipt, error=True)
        self.assertFalse((self.project / "docs").exists())
        self.assertFalse((self.projects / "另一个项目").exists())

    def test_remap_inside_save_kernel_cannot_escape_the_fixed_root(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        original = mcp.requirements.save_draft

        def changed_binding(*args, **kwargs):
            self.config["project_directories"]["voice-meetup"] = "另一个项目"
            self.write_config()
            return original(*args, **kwargs)

        with mock.patch.object(mcp.requirements, "save_draft", side_effect=changed_binding):
            failure = self.save("draft", receipt, error=True)
        self.assertIn("固定的目录", failure["error"])
        self.assertFalse((self.project / "docs").exists())
        self.assertFalse((self.projects / "另一个项目").exists())

    def test_replaced_parent_directory_cannot_redirect_an_existing_server(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        previous = self.projects.with_name("previous-projects")
        self.projects.rename(previous)
        outside = self.root / "outside"
        outside.mkdir()
        shutil.copytree(previous / self.project.name, outside / self.project.name)
        self.projects.symlink_to(outside, target_is_directory=True)
        failure = self.save("redirected write", receipt, error=True)
        self.assertIn("固定的目录", failure["error"])
        self.assertFalse((outside / self.project.name / "docs").exists())
        self.assertFalse((previous / self.project.name / "docs").exists())

    def test_post_write_read_failure_reports_saved_unverified_and_never_retries(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        original_save = mcp.requirements.save_draft
        original_read = mcp.requirements.read_document
        wrote = False

        def save(*args, **kwargs):
            nonlocal wrote
            result = original_save(*args, **kwargs)
            wrote = True
            return result

        def read(root, relative):
            if wrote and relative == "docs/requirements.md":
                raise OSError("readback unavailable")
            return original_read(root, relative)

        with mock.patch.object(mcp.requirements, "save_draft", side_effect=save) as saving:
            with mock.patch.object(mcp.requirements, "read_document", side_effect=read):
                failure = self.save("draft", receipt, error=True)
            self.assertEqual(saving.call_count, 1)
        self.assertEqual(failure["write_outcome"], "saved_unverified")
        self.assertTrue((self.project / "docs/requirements.md").is_file())

    def test_source_change_during_save_does_not_report_full_success(self):
        self.initialize()
        receipt = self.call(mcp.READ_CONTEXT)
        original = mcp.requirements.save_draft

        def save(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.project / "README.md").write_text("source changed during save", encoding="utf-8")
            return result

        with mock.patch.object(mcp.requirements, "save_draft", side_effect=save):
            failure = self.save("draft", receipt, error=True)
        self.assertEqual(failure["write_outcome"], "saved_unverified")

    def test_framing_recovers_from_bad_json_and_limits_message_size(self):
        valid = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": self.meta()}}
        output = io.StringIO()
        mcp.serve(self.server, io.BytesIO(b"{broken\n" + json.dumps(valid).encode() + b"\n"), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(len(responses[1]["result"]["tools"]), 7)
        output = io.StringIO()
        mcp.serve(self.server, io.BytesIO(b"x" * (mcp.MAX_MESSAGE + 1)), output)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], -32600)
        self.assertEqual(self.tree(), {})

    def test_stdio_subprocess_runs_legacy_and_modern_without_workflow(self):
        command = [sys.executable, "-B", mcp.__file__, "--foundation", str(self.foundation),
                   "--project-id", "voice-meetup", "--project-root", str(self.project),
                   "--allow-initialize", "--allow-save"]
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)

        def send(method, params=None, *, modern=True, notification=False):
            params = dict(params or {})
            if modern:
                params["_meta"] = self.meta()
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if not notification:
                message["id"] = 1
            child.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
            child.stdin.flush()
            if notification:
                return None
            self.assertTrue(select.select([child.stdout], [], [], 5)[0], "MCP response timed out")
            response = json.loads(child.stdout.readline())
            self.assertNotIn("error", response, response)
            return response["result"]

        send("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}, modern=False)
        send("notifications/initialized", modern=False, notification=True)
        self.assertEqual(len(send("tools/list", modern=False)["tools"]), 7)
        self.assertIn(mcp.MODERN_VERSION, send("server/discover")["supportedVersions"])
        send("tools/call", {"name": mcp.PROJECT_INITIALIZE,
                            "arguments": {"name": "语音约碰面地点", "purpose": "stdio 临时测试"}})
        read = send("tools/call", {"name": mcp.READ_CONTEXT})
        receipt = json.loads(read["content"][0]["text"])
        saved = send("tools/call", {"name": mcp.SAVE_DRAFT,
                                   "arguments": {"content": "# stdio 测试", "read_id": receipt["read_id"]}})
        self.assertFalse(saved["isError"])
        self.assertTrue(json.loads(saved["content"][0]["text"])["verified"])
        child.stdin.close()
        self.assertEqual(child.wait(timeout=5), 0)
        self.assertEqual(child.stderr.read(), b"")
        child.stdout.close()
        child.stderr.close()

    def test_package_entry_loads_without_retired_workflow_or_runtime_dependencies(self):
        runtime = TOOLS_ROOT.parents[1]
        script = """
import sys
sys.path.insert(0, sys.argv[1])
import workflows.requirements as requirements_package
import workflows.requirements.cursor_mcp
assert not any(hasattr(requirements_package, name) for name in (
    'run_turn', 'WorkflowDependencies', 'RequirementsTools', 'Progress', 'Action'))
assert not any('.hardcode' in name or name.startswith('fusion_runtime') for name in sys.modules)
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(runtime)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_configuration_preview_merge_and_repeat_preserve_other_servers(self):
        folder = self.project / ".cursor"
        folder.mkdir()
        path = folder / "mcp.json"
        original = {"mcpServers": {"unrelated": {"command": "existing-tool"}}, "otherSetting": 42}
        path.write_text(json.dumps(original), encoding="utf-8")
        before = path.read_bytes()
        preview = configure_cursor.configure(**self.binding())
        self.assertFalse(preview["applied"])
        self.assertEqual(path.read_bytes(), before)
        result = configure_cursor.configure(**self.binding(), apply=True,
                                             expected_sha256=preview["expected_config_sha256"])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["otherSetting"], 42)
        self.assertEqual(data["mcpServers"]["unrelated"], original["mcpServers"]["unrelated"])
        self.assertIn("requirements-voice-meetup", data["mcpServers"])
        self.assertTrue(result["applied"])
        before = path.read_bytes()
        again = configure_cursor.configure(**self.binding())
        configure_cursor.configure(**self.binding(), apply=True,
                                    expected_sha256=again["expected_config_sha256"])
        self.assertEqual(path.read_bytes(), before)

    def test_configuration_conflicts_and_symlinks_are_rejected(self):
        preview = configure_cursor.configure(**self.binding())
        folder = self.project / ".cursor"
        folder.mkdir()
        path = folder / "mcp.json"
        path.write_text('{"mcpServers":{}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "版本冲突"):
            configure_cursor.configure(**self.binding(), apply=True,
                                        expected_sha256=preview["expected_config_sha256"])
        path.write_text('{"mcpServers":{"requirements-voice-meetup":{"command":"user-edited"}}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "同名"):
            configure_cursor.configure(**self.binding())
        path.unlink()
        path.symlink_to(self.source / "rules.md")
        with self.assertRaisesRegex(ValueError, "软链"):
            configure_cursor.configure(**self.binding())


if __name__ == "__main__":
    unittest.main()
