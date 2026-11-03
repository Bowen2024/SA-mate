"""AC5-01 gate-1: real stdio subprocess handshake, discovery and read-only switch.

Each test drives a freshly spawned ``mcp_server.py`` over newline JSON-RPC.
Gate 1 lists only the three read-only tools; write tool names must be rejected
with tool_not_enabled and must not touch the project tree. In-memory read_id
credentials never persist and never cross processes.
"""

import json
import os

from test_ui_accept import candidate_files, edit_candidate, request_id
from ui_test_support import MODERN_PROTOCOL, UiFixture, tree_snapshot


SERVER_NAME = "ui-designer-file-tools"
READ_CONTEXT = "ui_read_context"
INSPECT = "ui_inspect"
READ_HISTORY = "ui_read_history"
WRITE_TOOLS = ("ui_prepare_revision", "ui_accept_revision", "ui_recover_revision")
READ_ONLY_TOOLS = [READ_CONTEXT, INSPECT, READ_HISTORY]


def list_tools(fixture, child, identifier=2):
    response = fixture.rpc_child(
        child, {"jsonrpc": "2.0", "id": identifier, "method": "tools/list"})
    return [tool["name"] for tool in response["result"]["tools"]]


def tree_contains_text(root, needle):
    raw = needle.encode("utf-8") if isinstance(needle, str) else needle
    for current, _dirs, files in os.walk(root):
        for name in files:
            try:
                with open(os.path.join(current, name), "rb") as handle:
                    if raw in handle.read():
                        return True
            except OSError:
                continue
    return False


class HandshakeAndDiscoveryTests(UiFixture):
    def test_modern_handshake_lists_exactly_three_read_tools(self):
        child = self.spawn()
        response = self.initialize_child(child)
        self.assertEqual(response["result"]["protocolVersion"], MODERN_PROTOCOL)
        self.assertEqual(response["result"]["serverInfo"]["name"], SERVER_NAME)
        self.assertEqual(list_tools(self, child), READ_ONLY_TOOLS)
        _code, stderr_text = self.shutdown(child)
        self.assertEqual(stderr_text, "")

    def test_legacy_protocol_version_is_accepted(self):
        child = self.spawn()
        response = self.rpc_child(
            child, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}}})
        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.shutdown(child)


class ReadOnlyCallTests(UiFixture):
    def test_read_only_tools_succeed_on_empty_project(self):
        child = self.spawn()
        self.initialize_child(child)
        is_error, context = self.call_child(
            child, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        self.assertFalse(is_error, context)
        self.assertEqual(context["state"], "empty")
        self.assertEqual(context["current"]["kind"], "none")
        self.assertTrue(context["read_id"].startswith("read-"))
        is_error, inspect = self.call_child(
            child, 4, INSPECT, {"project_path": str(self.project_p1),
                                "target": "current"})
        self.assertFalse(is_error, inspect)
        self.assertEqual(inspect["state"], "empty")
        is_error, history = self.call_child(
            child, 5, READ_HISTORY, {"project_path": str(self.project_p1)})
        self.assertFalse(is_error, history)
        self.assertEqual(history["state"], "history_list")
        self.assertEqual(history["versions"], [])
        self.shutdown(child)

    def test_write_tools_are_disabled_and_side_effect_free(self):
        child = self.spawn()
        self.initialize_child(child)
        before = tree_snapshot(self.project_p1)
        for index, name in enumerate(WRITE_TOOLS):
            is_error, payload = self.call_child(
                child, 10 + index, name,
                {"project_path": str(self.project_p1), "read_id": "read-deadbeef"})
            self.assertTrue(is_error, payload)
            self.assertEqual(payload["error"]["code"], "tool_not_enabled")
            self.assertEqual(payload["write_outcome"], "not_written")
        self.assertEqual(before, tree_snapshot(self.project_p1))
        self.shutdown(child)


class CredentialProcessIsolationTests(UiFixture):
    def test_read_id_is_memory_only_and_not_shared_between_processes(self):
        child_a = self.spawn()
        self.initialize_child(child_a)
        _error, context_a = self.call_child(
            child_a, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        token_a = context_a["read_id"]

        child_b = self.spawn()
        self.initialize_child(child_b)
        _error, context_b = self.call_child(
            child_b, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        token_b = context_b["read_id"]

        self.assertNotEqual(token_a, token_b)
        self.assertTrue(token_a.startswith("read-") and token_b.startswith("read-"))
        self.assertFalse(tree_contains_text(self.project_p1, token_a),
                         "read_id 不得写入项目或状态目录")
        self.shutdown(child_a)
        self.shutdown(child_b)
        # A token issued before restart cannot be re-derived: a third process
        # gets its own independent credential, and the old one stays absent.
        child_c = self.spawn()
        self.initialize_child(child_c)
        _error, context_c = self.call_child(
            child_c, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        self.assertNotEqual(context_c["read_id"], token_a)
        self.assertFalse(tree_contains_text(self.project_p1, token_a))
        self.shutdown(child_c)


class ProtocolErrorTests(UiFixture):
    def raw(self, child, message):
        return self.rpc_child(child, message)

    def test_tools_cannot_be_called_before_initialize(self):
        child = self.spawn()
        response = self.raw(
            child, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["error"]["code"], -32000)
        self.shutdown(child)

    def test_unsupported_protocol_version_rejected(self):
        child = self.spawn()
        response = self.raw(
            child, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "1999-01-01", "capabilities": {}}})
        self.assertEqual(response["error"]["code"], -32602)
        self.shutdown(child)

    def test_unknown_method_is_jsonrpc_error(self):
        child = self.spawn()
        self.initialize_child(child)
        response = self.raw(
            child, {"jsonrpc": "2.0", "id": 7, "method": "nope/method"})
        self.assertEqual(response["error"]["code"], -32601)
        self.shutdown(child)

    def test_malformed_json_is_parse_error(self):
        child = self.spawn()
        child.stdin.write(b'{"jsonrpc": "2.0", broken\n')
        child.stdin.flush()
        response = json.loads(child.stdout.readline())
        self.assertEqual(response["error"]["code"], -32700)
        self.shutdown(child)

    def test_oversized_message_is_rejected(self):
        child = self.spawn()
        self.initialize_child(child)
        padding = b"A" * (1024 * 1024 + 256)
        message = (b'{"jsonrpc":"2.0","id":8,"method":"tools/call",'
                   b'"params":{"name":"x","arguments":{"pad":"' + padding + b'"}}}\n')
        child.stdin.write(message)
        child.stdin.flush()
        response = json.loads(child.stdout.readline())
        self.assertEqual(response["error"]["code"], -32600)
        self.shutdown(child)


class WriteGateTests(UiFixture):
    """UI-T44: --allow-write exposes all six tools with strict arguments."""

    def test_allow_write_lists_six_tools_and_prepare_works(self):
        self.write_inputs()
        child = self.spawn(allow_write=True)
        self.initialize_child(child)
        self.assertEqual(
            list_tools(self, child),
            READ_ONLY_TOOLS + list(WRITE_TOOLS))
        _error, context = self.call_child(
            child, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        is_error, prepared = self.call_child(
            child, 4, "ui_prepare_revision",
            {"project_path": str(self.project_p1), "read_id": context["read_id"],
             "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "mode": "empty"})
        self.assertFalse(is_error, prepared)
        self.assertEqual(prepared["write_outcome"], "prepared")
        workspace = prepared["workspace_path"]
        self.assertTrue(os.path.isdir(workspace))
        self.shutdown(child)

    def test_accept_and_recover_argument_errors_do_not_write(self):
        self.write_inputs()
        child = self.spawn(allow_write=True)
        self.initialize_child(child)
        before = tree_snapshot(self.project_p1)
        for index, name in enumerate(("ui_accept_revision", "ui_recover_revision")):
            is_error, payload = self.call_child(
                child, 10 + index, name, {"project_path": str(self.project_p1)})
            self.assertTrue(is_error, payload)
            self.assertEqual(payload["error"]["code"], "invalid_arguments")
            self.assertEqual(payload["write_outcome"], "not_written")
            self.assertIn("revision_id", payload)
            self.assertIn("transaction_id", payload)
            self.assertIn("receipt_replay", payload)
        self.assertEqual(before, tree_snapshot(self.project_p1))
        self.shutdown(child)

    def test_prepare_argument_errors_are_business_errors_without_writes(self):
        self.write_inputs()
        child = self.spawn(allow_write=True)
        self.initialize_child(child)
        before = tree_snapshot(self.project_p1)
        is_error, bad_uuid = self.call_child(
            child, 1, "ui_prepare_revision",
            {"project_path": str(self.project_p1), "read_id": "read-x",
             "request_id": "not-a-uuid", "mode": "empty"})
        self.assertTrue(is_error)
        self.assertEqual(bad_uuid["error"]["code"], "invalid_arguments")
        is_error, unknown = self.call_child(
            child, 2, "ui_prepare_revision",
            {"project_path": str(self.project_p1), "read_id": "read-x",
             "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
             "mode": "empty", "force": True})
        self.assertTrue(is_error)
        self.assertEqual(unknown["error"]["code"], "invalid_arguments")
        self.assertEqual(before, tree_snapshot(self.project_p1))
        self.shutdown(child)

    def test_accept_receipt_replays_after_real_process_restart(self):
        self.write_inputs()
        child = self.spawn(allow_write=True)
        self.initialize_child(child)
        _error, context = self.call_child(
            child, 3, READ_CONTEXT, {"project_path": str(self.project_p1)})
        _error, prepared = self.call_child(
            child, 4, "ui_prepare_revision",
            {"project_path": str(self.project_p1), "read_id": context["read_id"],
             "request_id": request_id(), "mode": "empty"})
        edit_candidate(prepared["workspace_path"], candidate_files())
        _error, inspected = self.call_child(
            child, 5, INSPECT,
            {"project_path": str(self.project_p1), "target": "candidate",
             "revision_id": prepared["revision_id"]})
        arguments = {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": [],
        }
        is_error, accepted = self.call_child(child, 6, "ui_accept_revision", arguments)
        self.assertFalse(is_error, accepted)
        self.assertEqual(accepted["write_outcome"], "saved")
        self.shutdown(child)

        restarted = self.spawn(allow_write=True)
        self.initialize_child(restarted)
        is_error, replay = self.call_child(restarted, 7, "ui_accept_revision", arguments)
        self.assertFalse(is_error, replay)
        self.assertTrue(replay["receipt_replay"])
        self.assertEqual(replay["current_revision"], accepted["current_revision"])
        _error, history = self.call_child(
            restarted, 8, READ_HISTORY, {"project_path": str(self.project_p1)})
        self.assertEqual(len(history["versions"]), 1)
        self.shutdown(restarted)

    def test_accept_and_recover_reject_wrong_types_and_unknown_fields(self):
        self.write_inputs()
        child = self.spawn(allow_write=True)
        self.initialize_child(child)
        before = tree_snapshot(self.project_p1)
        cases = [
            ("ui_accept_revision", {"project_path": str(self.project_p1),
             "revision_id": "R-" + "0" * 32, "inspection_id": "inspect-x",
             "request_id": request_id(), "delete_paths": "not-an-array"}),
            ("ui_accept_revision", {"project_path": str(self.project_p1),
             "revision_id": "R-" + "0" * 32, "inspection_id": "inspect-x",
             "request_id": request_id(), "delete_paths": [], "force": True}),
            ("ui_recover_revision", {"project_path": str(self.project_p1),
             "transaction_id": "T-" + "0" * 32, "request_id": request_id(),
             "action": "automatic"}),
        ]
        for index, (name, arguments) in enumerate(cases):
            is_error, payload = self.call_child(child, 30 + index, name, arguments)
            self.assertTrue(is_error, payload)
            self.assertEqual(payload["error"]["code"], "invalid_arguments")
        self.assertEqual(tree_snapshot(self.project_p1), before)
        self.shutdown(child)
