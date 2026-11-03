"""UI-T26/T27 read side against hand-built static H fixtures.

These histories are constructed directly by the test support, not produced by
ui_accept_revision; they are read-only evidence and are never save-success proof.
"""

import json
from pathlib import Path

from ui_test_support import DEFAULT_ROOT, DESIGN_PATH, MANIFEST_PATH, STATE_DIR, UiFixture, tree_snapshot


def version_files(marker, *, old_bin=False):
    files = {
        f"{DEFAULT_ROOT}/index.html": f"<!doctype html><title>{marker}</title>",
        f"{DEFAULT_ROOT}/assets/app.js": f"const v='{marker}';\n",
        f"{DEFAULT_ROOT}/assets/styles.css": "body{}\n",
        f"{DEFAULT_ROOT}/README.md": f"# 演示 {marker}\n",
        DESIGN_PATH: f"# 设计 {marker}\n",
    }
    if old_bin:
        files[f"{DEFAULT_ROOT}/assets/old.bin"] = bytes(range(256))
    return files


class HistoryListTests(UiFixture):
    def build_three(self):
        first = self.build_static_version(
            self.project_p1, version_files("V1", old_bin=True),
            created_at="2026-11-02T03:00:00.000000Z")
        second = self.build_static_version(
            self.project_p1, version_files("V2"),
            created_at="2026-11-02T04:00:00.000000Z")
        third_files = version_files("V2-tie")
        third = self.build_static_version(
            self.project_p1, third_files,
            created_at="2026-11-02T04:00:00.000000Z")
        return first, second, third

    def test_list_ordering_pagination_and_cursor(self):
        first, second, third = self.build_three()
        self.connect()
        listing = self.read_history()
        shas = [item["revision_sha256"] for item in listing["versions"]]
        self.assertEqual(shas, sorted([second, third]) + [first])
        self.assertIsNone(listing["next_after_revision"])
        tied = sorted([second, third])
        page1 = self.read_history(identifier=10, limit=1)
        self.assertEqual(len(page1["versions"]), 1)
        self.assertEqual(page1["next_after_revision"], tied[0])
        page2 = self.call(self.mcp.READ_HISTORY,
                          {"project_path": str(self.project_p1), "limit": 1,
                           "after_revision": tied[0]}, identifier=11)
        self.assertEqual(
            [item["revision_sha256"] for item in page2["versions"]], [tied[1]])
        self.assertEqual(page2["next_after_revision"], tied[1])

    def test_invalid_limit_and_cursor(self):
        self.build_three()
        self.connect()
        for arguments in ({"limit": 0}, {"limit": 101}, {"limit": "5"},
                          {"limit": True}, {"after_revision": "a" * 64}):
            with self.subTest(arguments):
                response = self.rpc(
                    "tools/call",
                    {"name": self.mcp.READ_HISTORY,
                     "arguments": {"project_path": str(self.project_p1), **arguments}}, 12)
                payload = json.loads(response["result"]["content"][0]["text"])
                self.assertTrue(response["result"]["isError"], payload)
                self.assertEqual(payload["error"]["code"], "invalid_arguments")

    def test_specified_version_forbids_paging_arguments(self):
        first, _, _ = self.build_three()
        self.connect()
        response = self.rpc(
            "tools/call",
            {"name": self.mcp.READ_HISTORY,
             "arguments": {"project_path": str(self.project_p1),
                           "revision_sha256": first, "limit": 5}}, 13)
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "invalid_arguments")


class HistoryReadTests(UiFixture):
    def test_single_version_verifies_packet_members_and_contents(self):
        files = version_files("V1", old_bin=True)
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T03:00:00.000000Z")
        self.connect()
        detail = self.read_history(revision_sha256=revision)
        self.assertEqual(detail["state"], "history")
        packet = detail["version"]["packet"]
        self.assertEqual(len(packet["files"]), 6)
        self.assertEqual(packet["restored_from"], None)
        paths = {item["path"] for item in detail["contents"]}
        self.assertIn(f"{DEFAULT_ROOT}/assets/old.bin", paths)
        binary = [item for item in detail["contents"]
                  if item["path"].endswith("old.bin")][0]
        self.assertIsNone(binary["content"])

    def test_history_read_is_side_effect_free(self):
        revision = self.build_static_version(
            self.project_p1, version_files("V1"),
            created_at="2026-11-02T03:00:00.000000Z")
        self.connect()
        before = tree_snapshot(self.project_p1)
        self.read_history(revision_sha256=revision)
        self.read_history(identifier=14, limit=1)
        self.assertEqual(before, tree_snapshot(self.project_p1))

    def test_missing_version_is_history_not_found(self):
        self.connect()
        response = self.rpc(
            "tools/call",
            {"name": self.mcp.READ_HISTORY,
             "arguments": {"project_path": str(self.project_p1),
                           "revision_sha256": "a" * 64}}, 15)
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "history_not_found")


class HistoryCorruptionTests(UiFixture):
    def tamper_copy(self, tamper):
        spare = UiFixture()
        spare.setUp()
        self.addCleanup(spare.doCleanups)
        spare.build_static_version(
            spare.project_p1, version_files("V1"),
            created_at="2026-11-02T03:00:00.000000Z")
        root = spare.project_p1 / STATE_DIR / "versions"
        revision = root.iterdir().__next__().name
        tamper(spare, root / revision, revision)
        spare.connect()
        return spare, revision

    def test_tampered_packet_is_history_invalid(self):
        def tamper(spare, version_dir, revision):
            meta_path = version_dir / "version.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["packet"]["entrypoint"] = f"{DEFAULT_ROOT}/other.html"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        spare, revision = self.tamper_copy(tamper)
        response = spare.rpc(
            "tools/call",
            {"name": spare.mcp.READ_HISTORY,
             "arguments": {"project_path": str(spare.project_p1)}}, 16)
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "history_invalid")

    def test_tampered_member_is_history_invalid_on_single_read(self):
        def tamper(spare, version_dir, revision):
            member = version_dir / "tree" / DEFAULT_ROOT / "assets/app.js"
            member.write_text("corrupt\n", encoding="utf-8")
        spare, revision = self.tamper_copy(tamper)
        response = spare.rpc(
            "tools/call",
            {"name": spare.mcp.READ_HISTORY,
             "arguments": {"project_path": str(spare.project_p1),
                           "revision_sha256": revision}}, 17)
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "history_invalid")

    def test_missing_member_and_manifest_snapshot_are_history_invalid(self):
        for index, kind in enumerate(("member", "manifest")):
            def tamper(spare, version_dir, revision, kind=kind):
                if kind == "member":
                    (version_dir / "tree" / DEFAULT_ROOT / "README.md").unlink()
                else:
                    (version_dir / "tree" / MANIFEST_PATH).unlink()
            spare, revision = self.tamper_copy(tamper)
            response = spare.rpc(
                "tools/call",
                {"name": spare.mcp.READ_HISTORY,
                 "arguments": {"project_path": str(spare.project_p1),
                               "revision_sha256": revision}}, 18 + index)
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertTrue(response["result"]["isError"], payload)
            self.assertEqual(payload["error"]["code"], "history_invalid")
