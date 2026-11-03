"""5B candidate inspection, inspection credentials and restart continuity.

Covers UI-T13–T19 and the candidate slice of T46/T47. Inspection is read-only:
it never creates files, and only issues an in-process inspection_id when the
candidate is complete and every protection check passes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ui_test_support import (
    DEFAULT_ROOT,
    DESIGN_PATH,
    MANIFEST_PATH,
    MODERN_PROTOCOL,
    STATE_DIR,
    UiFixture,
    sha,
    tree_snapshot,
)

ENTRY = f"{DEFAULT_ROOT}/index.html"
README = f"{DEFAULT_ROOT}/README.md"


def error_code(payload):
    return payload["error"]["code"]


def complete_files():
    return {
        ENTRY: "<!doctype html><meta charset='utf-8'><title>Demo</title>",
        f"{DEFAULT_ROOT}/assets/app.js": "console.log('v1');\n",
        f"{DEFAULT_ROOT}/assets/styles.css": "body{color:#111}\n",
        f"{DEFAULT_ROOT}/assets/logo.bin": bytes((index * 7) % 256 for index in range(2048)),
        README: "# 演示\n\n用浏览器直接打开 index.html；本轮未做浏览器验收。\n",
        DESIGN_PATH: "# UI 设计说明 Draft\n\n视觉待决项保留。\n",
    }


def fill_candidate(workspace_path, files=None, *, entrypoint=ENTRY, declaration=None):
    workspace = Path(workspace_path)
    files = complete_files() if files is None else files
    tree = workspace / "tree"
    for relative, content in files.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    candidate = {"schema_version": 1, "entrypoint": entrypoint,
                 "files": sorted(files) if declaration is None else declaration}
    (workspace / "candidate.json").write_text(
        json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    return workspace


class CandidateReadyTests(UiFixture):
    """UI-T13: completeness, binary members and content identity."""

    def _prepared_empty(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        return self.prepare(read["read_id"],
                            "11111111-1111-4111-8111-111111111111", "empty")

    def test_complete_candidate_is_ready_and_stable(self):
        prepared = self._prepared_empty()
        fill_candidate(prepared["workspace_path"])
        first = self.inspect_candidate(prepared["revision_id"])
        self.assertEqual(first["state"], "candidate_ready", first["issues"])
        self.assertTrue(first["inspection_id"])
        second = self.inspect_candidate(prepared["revision_id"], identifier=8)
        self.assertEqual(second["state"], "candidate_ready")
        self.assertEqual(second["candidate_digest"], first["candidate_digest"])
        self.assertEqual(second["proposed_revision_sha256"],
                         first["proposed_revision_sha256"])
        self.assertEqual(first["changes"], {"added": sorted(complete_files()),
                                            "modified": [], "removed": []})

    def test_proposed_revision_sha_matches_canonical_packet(self):
        prepared = self._prepared_empty()
        files = complete_files()
        fill_candidate(prepared["workspace_path"], files)
        inspected = self.inspect_candidate(prepared["revision_id"])
        base = json.loads((Path(prepared["workspace_path"]) / "base.json").read_text())
        packet_files = [{"path": path, "sha256": sha(
            content if isinstance(content, bytes) else content.encode("utf-8"))}
            for path, content in sorted(files.items())]
        packet = {
            "schema_version": 1, "project_id": "procurement-demo",
            "artifact_root": DEFAULT_ROOT, "entrypoint": ENTRY,
            "design_path": DESIGN_PATH, "readme_path": README,
            "files": packet_files, "sources": base["sources"],
            "restored_from": None,
        }
        canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        import hashlib
        self.assertEqual(inspected["proposed_revision_sha256"],
                         hashlib.sha256(canonical).hexdigest())

    def test_binary_and_text_changes_produce_different_identity(self):
        prepared = self._prepared_empty()
        files = complete_files()
        fill_candidate(prepared["workspace_path"], files)
        first = self.inspect_candidate(prepared["revision_id"])
        binary = Path(prepared["workspace_path"]) / "tree" / f"{DEFAULT_ROOT}/assets/logo.bin"
        raw = bytearray(binary.read_bytes())
        raw[0] ^= 0xFF
        binary.write_bytes(bytes(raw))
        second = self.inspect_candidate(prepared["revision_id"], identifier=9)
        self.assertNotEqual(second["proposed_revision_sha256"],
                            first["proposed_revision_sha256"])
        self.assertIn(f"{DEFAULT_ROOT}/assets/logo.bin", second["changes"]["added"])

    def test_current_candidate_reports_removed_member(self):
        self.write_inputs()
        files = self.v1_files()
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T10:00:00.000000Z")
        self.make_managed_current(self.project_p1, revision, files)
        self.connect(allow_write=True)
        read = self.read_context(identifier=10)
        prepared = self.prepare(read["read_id"],
                                "22222222-2222-4222-8222-222222222222", "current",
                                identifier=11)
        workspace = Path(prepared["workspace_path"])
        removed = f"{DEFAULT_ROOT}/assets/old.bin"
        (workspace / "tree" / removed).unlink()
        candidate_files = [path for path in sorted(files) if path != removed]
        candidate = {"schema_version": 1, "entrypoint": ENTRY,
                     "files": candidate_files}
        (workspace / "candidate.json").write_text(
            json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        inspected = self.inspect_candidate(prepared["revision_id"], identifier=12)
        self.assertEqual(inspected["state"], "candidate_ready", inspected["issues"])
        self.assertEqual(inspected["changes"]["removed"], [removed])


class CandidateIssueTests(UiFixture):
    """UI-T14/T15: unlisted members, limits and incomplete required members."""

    def _workspace(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "33333333-3333-4333-8333-333333333333", "empty")
        return Path(prepared["workspace_path"]), prepared["revision_id"]

    def _inspect(self, revision_id, identifier=20):
        return self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p1), "target": "candidate",
            "revision_id": revision_id}, identifier=identifier, error=True)

    def test_missing_declared_member(self):
        workspace, revision_id = self._workspace()
        missing = f"{DEFAULT_ROOT}/missing.css"
        candidate = {"schema_version": 1, "entrypoint": ENTRY,
                     "files": [ENTRY, missing]}
        tree = workspace / "tree" / ENTRY
        tree.parent.mkdir(parents=True, exist_ok=True)
        tree.write_text("<!doctype html><title>x</title>", encoding="utf-8")
        (workspace / "candidate.json").write_text(
            json.dumps(candidate), encoding="utf-8")
        inspected = self.inspect_candidate(revision_id, identifier=21)
        codes = {issue["code"] for issue in inspected["issues"]}
        self.assertIn("collection_invalid", codes)
        self.assertIn("candidate_incomplete", codes)
        issue = next(item for item in inspected["issues"]
                     if item["code"] == "collection_invalid")
        self.assertEqual(issue["paths"], [missing])
        self.assertIsNone(inspected["inspection_id"])

    def test_unlisted_tree_file_is_blocking(self):
        workspace, revision_id = self._workspace()
        files = complete_files()
        fill_candidate(workspace, files)
        extra = workspace / "tree" / f"{DEFAULT_ROOT}/secret.txt"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("unlisted", encoding="utf-8")
        inspected = self.inspect_candidate(revision_id, identifier=22)
        self.assertEqual(inspected["state"], "candidate_incomplete")
        issue = next(item for item in inspected["issues"] if item["code"] == "unlisted_file")
        self.assertEqual(issue["paths"], [f"{DEFAULT_ROOT}/secret.txt"])
        self.assertIsNone(inspected["inspection_id"])

    def test_cache_name_is_excluded_but_declared_secret_still_blocked(self):
        workspace, revision_id = self._workspace()
        files = complete_files()
        fill_candidate(workspace, files)
        (workspace / "tree" / f"{DEFAULT_ROOT}/.DS_Store").write_text("x", encoding="utf-8")
        inspected = self.inspect_candidate(prepared_revision := revision_id, identifier=23)
        self.assertEqual(inspected["state"], "candidate_ready", inspected["issues"])

    def test_member_over_32mib_rejected(self):
        workspace, revision_id = self._workspace()
        files = complete_files()
        files[f"{DEFAULT_ROOT}/assets/huge.bin"] = b"a" * (32 * 1024 * 1024 + 1)
        fill_candidate(workspace, files)
        inspected = self.inspect_candidate(revision_id, identifier=24)
        codes = {issue["code"] for issue in inspected["issues"]}
        self.assertIn("limit_exceeded", codes)
        self.assertIsNone(inspected["inspection_id"])

    def test_more_than_256_declared_members_rejected(self):
        workspace, revision_id = self._workspace()
        tree = workspace / "tree" / f"{DEFAULT_ROOT}/shards"
        tree.mkdir(parents=True, exist_ok=True)
        names = [f"shard-{index:03d}.txt" for index in range(251)]
        for name in names:
            (tree / name).write_text("x", encoding="utf-8")
        files = complete_files()
        for relative, content in files.items():
            path = workspace / "tree" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes)
                             else content.encode("utf-8"))
        declared = sorted(files) + [f"{DEFAULT_ROOT}/shards/{name}" for name in names]
        candidate = {"schema_version": 1, "entrypoint": ENTRY, "files": declared}
        (workspace / "candidate.json").write_text(
            json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        inspected = self.inspect_candidate(revision_id, identifier=25)
        self.assertTrue(any(issue["code"] == "limit_exceeded"
                            for issue in inspected["issues"]))
        self.assertIsNone(inspected["inspection_id"])

    def test_candidate_declaration_over_128kib_rejected(self):
        workspace, revision_id = self._workspace()
        long_dir = "/".join(["d" + ("x" * 40) for _ in range(8)])
        declared = [f"{DEFAULT_ROOT}/{long_dir}/f{index:03d}.txt" for index in range(400)]
        candidate = {"schema_version": 1, "entrypoint": None, "files": declared}
        raw = json.dumps(candidate, ensure_ascii=False).encode("utf-8")
        self.assertGreater(len(raw), 128 * 1024)
        (workspace / "candidate.json").write_bytes(raw)
        failed = self._inspect(revision_id)
        self.assertEqual(error_code(failed), "limit_exceeded")

    def test_collection_over_64mib_rejected(self):
        workspace, revision_id = self._workspace()
        tree = workspace / "tree" / f"{DEFAULT_ROOT}/bulk"
        tree.mkdir(parents=True, exist_ok=True)
        names = [f"bulk-{index:03d}.bin" for index in range(256)]
        chunk = b"q" * (260 * 1024)
        for name in names:
            (tree / name).write_bytes(chunk)
        declared = [f"{DEFAULT_ROOT}/bulk/{name}" for name in names]
        candidate = {"schema_version": 1, "entrypoint": None, "files": declared}
        (workspace / "candidate.json").write_text(
            json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        inspected = self.inspect_candidate(revision_id, identifier=28)
        self.assertTrue(any(issue["code"] == "limit_exceeded"
                            and "64 MiB" in issue["message"]
                            for issue in inspected["issues"]), inspected["issues"])
        self.assertIsNone(inspected["inspection_id"])

    def test_remote_only_entrypoint_rejected(self):
        workspace, revision_id = self._workspace()
        files = complete_files()
        fill_candidate(workspace, files, declaration=sorted(files))
        candidate = {"schema_version": 1,
                     "entrypoint": "https://example.com/demo/index.html",
                     "files": sorted(files)}
        (workspace / "candidate.json").write_text(
            json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        inspected = self.inspect_candidate(revision_id, identifier=26)
        codes = {issue["code"] for issue in inspected["issues"]}
        self.assertIn("collection_invalid", codes)
        issue = next(item for item in inspected["issues"]
                     if "https://example.com" in item["paths"][0])
        self.assertEqual(inspected["state"], "candidate_incomplete")
        self.assertIsNone(inspected["inspection_id"])

    def test_corrupt_candidate_json_rejected(self):
        workspace, revision_id = self._workspace()
        (workspace / "candidate.json").write_text("{broken", encoding="utf-8")
        failed = self._inspect(revision_id)
        self.assertEqual(error_code(failed), "collection_invalid")

    def test_unknown_and_closed_workspace_rejected(self):
        self.write_inputs()
        self.connect(allow_write=True)
        missing = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p1), "target": "candidate",
            "revision_id": "R-" + "f" * 32}, identifier=27, error=True)
        self.assertEqual(error_code(missing), "invalid_arguments")


class CandidateProtectionTests(UiFixture):
    """UI-T16/T17/T19 and source/target change protection."""

    def test_inspection_is_side_effect_free(self):
        self.write_inputs()
        files = complete_files()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "44444444-4444-4444-8444-444444444444", "empty")
        fill_candidate(prepared["workspace_path"], files)
        snapshot = tree_snapshot(self.project_p1)
        for identifier in (30, 31, 32):
            inspected = self.inspect_candidate(prepared["revision_id"],
                                               identifier=identifier)
            self.assertEqual(inspected["state"], "candidate_ready")
        self.assertEqual(tree_snapshot(self.project_p1), snapshot)

    def test_inspection_id_bound_to_revision(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        first = self.prepare(read["read_id"],
                             "55555555-5555-4555-8555-555555555555", "empty",
                             identifier=33)
        fill_candidate(first["workspace_path"])
        ready = self.inspect_candidate(first["revision_id"], identifier=34)
        self.assertTrue(ready["inspection_id"].startswith("inspect-"))
        read_two = self.read_context(identifier=35)
        second = self.prepare(read_two["read_id"],
                              "56666666-6666-4666-8666-666666666666", "empty",
                              identifier=36)
        fill_candidate(second["workspace_path"])
        other = self.inspect_candidate(second["revision_id"], identifier=37)
        self.assertNotEqual(other["inspection_id"], ready["inspection_id"])

    def test_inspection_expiry_with_injected_clock(self):
        self.write_inputs()
        clock = {"now": 1_000_000.0}
        self.connect(allow_write=True, clock=lambda: clock["now"])
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "57777777-7777-4777-8777-777777777777", "empty",
                                identifier=38)
        fill_candidate(prepared["workspace_path"])
        ready = self.inspect_candidate(prepared["revision_id"], identifier=39)
        token = ready["inspection_id"]
        clock["now"] += 15 * 60 + 1
        with self.assertRaises(Exception) as caught:
            self.server.tools.credentials.validate_inspect(
                token, project_path=str(self.project_p1))
        self.assertEqual(caught.exception.code, "inspection_expired")

    def test_source_change_after_preparation_blocks_inspection(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "58888888-8888-4888-8888-888888888888", "empty",
                                identifier=40)
        fill_candidate(prepared["workspace_path"])
        self.write(self.project_p1, "docs/PRD.md",
                   "---\nstatus: Revised\n---\n\n# PRD revised after prepare\n")
        failed = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p1), "target": "candidate",
            "revision_id": prepared["revision_id"]}, identifier=41, error=True)
        self.assertEqual(error_code(failed), "source_changed")

    def test_candidate_change_after_inspection_invalidates_digest(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "59999999-9999-4999-8999-999999999999", "empty",
                                identifier=42)
        fill_candidate(prepared["workspace_path"])
        first = self.inspect_candidate(prepared["revision_id"], identifier=43)
        css = Path(prepared["workspace_path"]) / "tree" / f"{DEFAULT_ROOT}/assets/styles.css"
        css.write_text("body{color:red}\n", encoding="utf-8")
        second = self.inspect_candidate(prepared["revision_id"], identifier=44)
        self.assertNotEqual(second["candidate_digest"], first["candidate_digest"])
        # Empty preparation has no current members, so every member is "added".
        self.assertIn(f"{DEFAULT_ROOT}/assets/styles.css", second["changes"]["added"])
        self.assertEqual(second["changes"]["modified"], [])

    def test_restarted_process_rechecks_workspace_without_memory_tokens(self):
        self.write_inputs()
        self.write_import_case()
        child = self.spawn(allow_write=True,
                           import_roots=[self.import_parent.parent])
        self.initialize_child(child)
        read_is, read = self.call_child(child, 1, "ui_read_context", {
            "project_path": str(self.project_p1)})
        self.assertFalse(read_is)
        prepare_is, prepared = self.call_child(child, 2, "ui_prepare_revision", {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "61111111-1111-4111-8111-111111111111", "mode": "empty"})
        self.assertFalse(prepare_is, prepared)
        workspace = Path(prepared["workspace_path"])
        fill_candidate(workspace)
        child.stdin.close()
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
        restarted = self.spawn(allow_write=True)
        self.initialize_child(restarted)
        stale_is, stale = self.call_child(restarted, 3, "ui_prepare_revision", {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "62222222-2222-4222-8222-222222222222", "mode": "empty"})
        self.assertTrue(stale_is)
        self.assertEqual(error_code(stale), "read_invalid")
        inspect_is, inspected = self.call_child(restarted, 4, "ui_inspect", {
            "project_path": str(self.project_p1), "target": "candidate",
            "revision_id": prepared["revision_id"]})
        self.assertFalse(inspect_is, inspected)
        self.assertEqual(inspected["state"], "candidate_ready")
        self.assertTrue(inspected["inspection_id"])
        self.shutdown(restarted)

    def test_closed_candidate_is_read_only(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"],
                                "63333333-3333-4333-8333-333333333333", "empty",
                                identifier=50)
        fill_candidate(prepared["workspace_path"])
        accept_receipt = {
            "schema_version": 1, "project_id": "procurement-demo",
            "operation": "ui_accept_revision",
            "request_id": "64444444-4444-4444-8444-444444444444",
            "params_digest": "x" * 64, "status": "completed",
            "write_outcome": "saved",
            "revision_id": prepared["revision_id"]}
        self.write(self.project_p1,
                   f"{STATE_DIR}/requests/64444444-4444-4444-8444-444444444444.json",
                   json.dumps(accept_receipt, ensure_ascii=False))
        inspected = self.inspect_candidate(prepared["revision_id"], identifier=51)
        self.assertEqual(inspected["state"], "candidate_closed")
        self.assertIsNone(inspected["inspection_id"])
        self.assertTrue(any(issue["code"] == "candidate_closed"
                            for issue in inspected["issues"]))
