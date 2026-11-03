"""5B candidate preparation, import mapping and workspace lifecycle.

Covers UI-T10–T12, T20 and the prepare-side slices of T30–T32/T46. B1/H
fixtures used by current/history modes are hand-built static fixtures; 5C
replaces them with real accept-produced collections in the integrated line.
All writes happen inside system temporary projects.
"""

from __future__ import annotations

import json
from pathlib import Path

from ui_test_support import (
    DEFAULT_ROOT,
    DESIGN_PATH,
    MANIFEST_PATH,
    STATE_DIR,
    UiFixture,
    sha,
)


def error_code(payload):
    return payload["error"]["code"]


def write_candidate(workspace_path, files, *, entrypoint, raw=None):
    workspace = Path(workspace_path)
    tree = workspace / "tree"
    for relative, content in files.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    candidate = {"schema_version": 1, "entrypoint": entrypoint,
                 "files": None if raw is not None else sorted(files)}
    if raw is not None:
        candidate = raw
    (workspace / "candidate.json").write_text(
        json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    return workspace


class PrepareModeTests(UiFixture):
    """UI-T10: empty/current preparation, base facts and public invariance."""

    def test_empty_prepare_on_clean_project(self):
        self.write_inputs()
        self.connect(allow_write=True)
        before = self.tree_snapshot(self.project_p1) if hasattr(self, "tree_snapshot") else None
        read = self.read_context()
        self.assertEqual(read["state"], "empty")
        prepared = self.prepare(read["read_id"],
                                "11111111-1111-4111-8111-111111111111", "empty")
        self.assertEqual(prepared["write_outcome"], "prepared")
        self.assertFalse(prepared["receipt_replay"])
        self.assertRegex(prepared["revision_id"], r"^R-[0-9a-f]{32}$")
        self.assertEqual(prepared["transaction_id"], None)
        self.assertEqual(prepared["revision_sha256"], None)
        workspace = Path(prepared["workspace_path"])
        base = json.loads((workspace / "base.json").read_text(encoding="utf-8"))
        self.assertEqual(base["mode"], "empty")
        self.assertEqual(base["artifact_root"], DEFAULT_ROOT)
        self.assertEqual(base["restored_from"], None)
        self.assertEqual(base["current"]["kind"], "none")
        self.assertEqual(base["base_digest"], prepared["base_digest"])
        candidate = json.loads((workspace / "candidate.json").read_text(encoding="utf-8"))
        self.assertEqual(candidate, {"schema_version": 1, "entrypoint": None, "files": []})
        # Public collection, sources and indices stay untouched; only private state appears.
        # Inputs created by the fixture remain; only UI-controlled paths are absent.
        for relative in ("docs/PRD.md", "docs/requirements.md", "README.md",
                         "project.json"):
            self.assertTrue((self.project_p1 / relative).exists(), relative)
        for relative in (MANIFEST_PATH, f"{STATE_DIR}/current.json"):
            self.assertFalse((self.project_p1 / relative).exists(), relative)
        self.assertFalse((self.project_p1 / DEFAULT_ROOT).exists())

    def test_current_prepare_copies_complete_managed_collection(self):
        self.write_inputs()
        files = self.v1_files()
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T10:00:00.000000Z")
        self.make_managed_current(self.project_p1, revision, files)
        public_before = {
            path: sha((self.project_p1 / path).read_bytes())
            for path in list(files) + [MANIFEST_PATH, f"{STATE_DIR}/current.json"]
        }
        self.connect(allow_write=True)
        read = self.read_context()
        self.assertEqual(read["state"], "stable")
        prepared = self.prepare(read["read_id"],
                                "22222222-2222-4222-8222-222222222222", "current")
        workspace = Path(prepared["workspace_path"])
        tree = workspace / "tree"
        copied = sorted(str(path.relative_to(tree))
                        for path in tree.rglob("*") if path.is_file())
        self.assertEqual(copied, sorted(files))
        for relative, content in files.items():
            expected = content.encode("utf-8") if isinstance(content, str) else content
            self.assertEqual((tree / relative).read_bytes(), expected)
        base = json.loads((workspace / "base.json").read_text(encoding="utf-8"))
        self.assertEqual(base["mode"], "current")
        self.assertEqual(base["current"]["kind"], "managed")
        self.assertEqual(base["current"]["revision_sha256"], revision)
        for relative, digest_before in public_before.items():
            self.assertEqual(sha((self.project_p1 / relative).read_bytes()), digest_before,
                             relative)

    def test_empty_mode_rejected_when_collection_exists(self):
        self.write_inputs()
        files = self.v1_files()
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T10:00:00.000000Z")
        self.make_managed_current(self.project_p1, revision, files)
        self.connect(allow_write=True)
        read = self.read_context()
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "33333333-3333-4333-8333-333333333333", "mode": "empty"},
            error=True)
        self.assertEqual(error_code(failed), "invalid_arguments")
        self.assertEqual(failed["write_outcome"], "not_written")

    def test_history_mode_requires_and_uses_revision(self):
        self.write_inputs()
        files = self.v1_files()
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T10:00:00.000000Z")
        self.make_managed_current(self.project_p1, revision, files)
        self.connect(allow_write=True)
        read = self.read_context()
        missing_arg = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "44444444-4444-4444-8444-444444444444", "mode": "history"},
            error=True)
        self.assertEqual(error_code(missing_arg), "invalid_arguments")
        stray_arg = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "55555555-5555-4555-8555-555555555555", "mode": "empty",
            "history_revision": revision}, error=True)
        self.assertEqual(error_code(stray_arg), "invalid_arguments")
        read_two = self.read_context(identifier=9)
        prepared = self.prepare(read_two["read_id"],
                                "66666666-6666-4666-8666-666666666666", "history",
                                history_revision=revision, identifier=10)
        base = json.loads((Path(prepared["workspace_path"]) / "base.json").read_text())
        self.assertEqual(base["restored_from"], revision)
        self.assertEqual(base["mode"], "history")


class ImportPrepareTests(UiFixture):
    """UI-T11/T12: five-file import mapping, rights, conflicts and source drift."""

    def test_five_file_import_mapping_and_source_immutability(self):
        self.write_inputs()
        self.write_import_case()
        source_before = {
            str(path.relative_to(self.import_parent)): sha(path.read_bytes())
            for path in self.import_parent.rglob("*") if path.is_file()
        }
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        read = self.read_context(import_source=self.import_source())
        self.assertEqual(read["state"], "empty")
        prepared = self.prepare(read["read_id"],
                                "77777777-7777-4777-8777-777777777777", "import")
        workspace = Path(prepared["workspace_path"])
        tree = workspace / "tree"
        mapped = sorted(str(path.relative_to(tree))
                        for path in tree.rglob("*") if path.is_file())
        self.assertEqual(mapped, sorted([
            f"{DEFAULT_ROOT}/index.html", f"{DEFAULT_ROOT}/assets/app.js",
            f"{DEFAULT_ROOT}/assets/styles.css", f"{DEFAULT_ROOT}/README.md",
            DESIGN_PATH]))
        self.assertEqual((tree / f"{DEFAULT_ROOT}/README.md").read_bytes(),
                         (self.import_parent / "README.md").read_bytes())
        self.assertEqual((tree / DESIGN_PATH).read_bytes(),
                         (self.import_parent / "docs/ui-style.md").read_bytes())
        self.assertFalse(tree.is_symlink())
        self.assertFalse((tree / f"{DEFAULT_ROOT}/index.html").is_symlink())
        source_after = {
            str(path.relative_to(self.import_parent)): sha(path.read_bytes())
            for path in self.import_parent.rglob("*") if path.is_file()
        }
        self.assertEqual(source_after, source_before)

    def test_import_without_authorized_root_rejected(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(allow_write=True)
        failed = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_p1),
            "import_source": self.import_source()}, error=True)
        self.assertEqual(error_code(failed), "path_not_allowed")

    def test_import_entrypoint_must_be_listed(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        spec = self.import_source(files=["index.html"])
        spec["entrypoint"] = "assets/app.js"  # listed? no
        failed = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_p1), "import_source": spec}, error=True)
        self.assertEqual(error_code(failed), "invalid_arguments")

    def test_import_secret_file_rejected(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        spec = self.import_source(files=["index.html", ".env"])
        failed = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_p1), "import_source": spec}, error=True)
        self.assertEqual(error_code(failed), "path_not_allowed")

    def test_mapping_conflict_when_design_and_readme_collide(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        (self.import_parent / "docs").mkdir(parents=True, exist_ok=True)
        (self.import_parent / "docs/README.md").write_text(
            "# nested readme\n", encoding="utf-8")
        spec = self.import_source(files=["index.html", "README.md", "docs/README.md",
                                         "docs/ui-style.md"])
        # Both README.md (other-member rule) and docs/README.md (readme role) map
        # to docs/prototypes/demo/README.md.
        spec["readme_path"] = "docs/README.md"
        failed = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_p1), "import_source": spec}, error=True)
        self.assertEqual(error_code(failed), "mapping_conflict")

    def test_source_change_between_read_and_prepare_rejected(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        read = self.read_context(import_source=self.import_source())
        (self.import_parent / "assets/app.js").write_text("console.log('changed');\n",
                                                          encoding="utf-8")
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "88888888-8888-4888-8888-888888888888", "mode": "import"},
            error=True)
        self.assertEqual(error_code(failed), "source_changed")


class PrepareProtectionTests(UiFixture):
    """UI-T17/T20/T30/T31/T32 prepare slices and credential consumption timing."""

    def _empty_read(self):
        self.write_inputs()
        self.connect(allow_write=True)
        return self.read_context()

    def test_read_id_cross_project_rejected(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p2), "read_id": read["read_id"],
            "request_id": "99999999-9999-4999-8999-999999999999", "mode": "empty"},
            error=True)
        self.assertEqual(error_code(failed), "read_invalid")

    def test_prevalidation_rejection_does_not_consume_read_id(self):
        read = self._empty_read()
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "mode": "weird"},
            error=True)
        self.assertEqual(error_code(failed), "invalid_arguments")
        prepared = self.prepare(read["read_id"],
                                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "empty",
                                identifier=11)
        self.assertEqual(prepared["state"], "prepared")
        second_use = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "mode": "empty"},
            error=True, identifier=12)
        self.assertEqual(error_code(second_use), "read_invalid")

    def test_completed_prepare_request_is_idempotent_without_token(self):
        read = self._empty_read()
        prepared = self.prepare(read["read_id"],
                                "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "empty")
        replay = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": "read-garbage",
            "request_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "mode": "empty"},
            identifier=13)
        self.assertTrue(replay["receipt_replay"])
        self.assertEqual(replay["revision_id"], prepared["revision_id"])
        self.assertEqual(replay["candidate_digest"], prepared["candidate_digest"])
        work_root = Path(self.project_p1) / STATE_DIR / "work"
        self.assertEqual(len([p for p in work_root.iterdir() if p.is_dir()]), 1)

    def test_same_request_id_with_different_mode_rejected(self):
        read = self._empty_read()
        self.prepare(read["read_id"], "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "empty")
        read_two = self.read_context(identifier=14)
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read_two["read_id"],
            "request_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            "mode": "current"}, error=True, identifier=15)
        self.assertEqual(error_code(failed), "request_reused")

    def test_workspace_quota_is_eight(self):
        self.write_inputs()
        self.connect(allow_write=True)
        for index in range(8):
            read = self.read_context(identifier=20 + index)
            uid = f"1000000{index}-0000-4000-8000-00000000000{index}"
            prepared = self.prepare(read["read_id"], uid, "empty",
                                    identifier=30 + index)
            self.assertEqual(prepared["state"], "prepared")
        read = self.read_context(identifier=40)
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "20000000-0000-4000-8000-000000000000", "mode": "empty"},
            error=True, identifier=41)
        self.assertEqual(error_code(failed), "workspace_limit")
        work_root = self.project_p1 / STATE_DIR / "work"
        self.assertEqual(len([p for p in work_root.iterdir() if p.is_dir()]), 8)

    def test_incomplete_receipt_reports_operation_incomplete(self):
        read = self._empty_read()
        request_id = "30000000-0000-4000-8000-000000000000"
        prepared = self.prepare(read["read_id"], request_id, "empty", identifier=50)
        receipt = self.project_p1 / STATE_DIR / "requests" / f"{request_id}.json"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["status"] = "incomplete"
        receipt.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": "read-garbage",
            "request_id": request_id, "mode": "empty"}, error=True, identifier=51)
        self.assertEqual(error_code(failed), "operation_incomplete")
        self.assertEqual(failed["error"]["details"]["revision_id"],
                         prepared["revision_id"])

    def test_corrupt_receipt_rejected(self):
        read = self._empty_read()
        request_id = "40000000-0000-4000-8000-000000000000"
        self.prepare(read["read_id"], request_id, "empty", identifier=52)
        receipt = self.project_p1 / STATE_DIR / "requests" / f"{request_id}.json"
        receipt.write_text("{not-json", encoding="utf-8")
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": "read-garbage",
            "request_id": request_id, "mode": "empty"}, error=True, identifier=53)
        self.assertEqual(error_code(failed), "receipt_invalid")

    def test_existing_project_state_lock_blocks_prepare(self):
        read = self._empty_read()
        lock = self.project_p1 / ".project-state.lock"
        lock.write_text('{"operation":"other","pid":1}\n', encoding="utf-8")
        try:
            failed = self.call(self.mcp.PREPARE, {
                "project_path": str(self.project_p1), "read_id": read["read_id"],
                "request_id": "50000000-0000-4000-8000-000000000000",
                "mode": "empty"}, error=True, identifier=54)
            self.assertEqual(error_code(failed), "lock_busy")
        finally:
            lock.unlink()

    def test_main_root_transaction_blocks_prepare(self):
        read = self._empty_read()
        journal = self.project_p1 / ".project-state-transaction.json"
        journal.write_text('{"schema_version":1}\n', encoding="utf-8")
        try:
            failed = self.call(self.mcp.PREPARE, {
                "project_path": str(self.project_p1), "read_id": read["read_id"],
                "request_id": "60000000-0000-4000-8000-000000000000",
                "mode": "empty"}, error=True, identifier=55)
            self.assertEqual(error_code(failed), "main_transaction_pending")
        finally:
            journal.unlink()

    def test_active_ui_transaction_blocks_prepare(self):
        read = self._empty_read()
        self.build_static_transaction(
            self.project_p1, transaction_id="T-" + "a" * 32,
            request_id="70000000-0000-4000-8000-000000000000",
            targets=[{"path": f"{DEFAULT_ROOT}/index.html",
                      "before": None, "after": b"new"}], active=True)
        failed = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": read["read_id"],
            "request_id": "80000000-0000-4000-8000-000000000000",
            "mode": "empty"}, error=True, identifier=56)
        self.assertEqual(error_code(failed), "operation_incomplete")

    def test_interrupted_copy_leaves_incomplete_workspace_and_receipt(self):
        self.write_inputs()
        files = self.v1_files()
        revision = self.build_static_version(
            self.project_p1, files, created_at="2026-11-02T10:00:00.000000Z")
        self.make_managed_current(self.project_p1, revision, files)
        self.connect(allow_write=True)
        read = self.read_context()
        public_before = {path: sha((self.project_p1 / path).read_bytes())
                         for path in [*files, MANIFEST_PATH, f"{STATE_DIR}/current.json"]}
        import file_tools.workspace as workspace_module
        original = workspace_module._copy_initial_members

        def interrupted(*_args, **_kwargs):
            raise OSError("injected copy failure")

        workspace_module._copy_initial_members = interrupted
        request = "90000000-0000-4000-8000-000000000000"
        try:
            failed = self.call(self.mcp.PREPARE, {
                "project_path": str(self.project_p1), "read_id": read["read_id"],
                "request_id": request, "mode": "current"}, error=True)
        finally:
            workspace_module._copy_initial_members = original
        self.assertEqual(error_code(failed), "io_error")
        self.assertEqual(failed["write_outcome"], "not_written")
        receipt = json.loads((self.project_p1 / STATE_DIR / "requests"
                              / f"{request}.json").read_text())
        self.assertEqual(receipt["status"], "incomplete")
        self.assertIn(receipt["revision_id"], {
            path.name for path in (self.project_p1 / STATE_DIR / "work").iterdir()})
        replay = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": "read-garbage",
            "request_id": request, "mode": "current"}, error=True)
        self.assertEqual(error_code(replay), "operation_incomplete")
        for path, expected in public_before.items():
            self.assertEqual(sha((self.project_p1 / path).read_bytes()), expected)
