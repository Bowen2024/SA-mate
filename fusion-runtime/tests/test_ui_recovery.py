"""5C minimum recovery set: real accept transactions plus internal failpoints."""

from __future__ import annotations

import json

from test_ui_accept import AcceptFixture, APP, OLD, candidate_files, request_id
from ui_test_support import MANIFEST_PATH, STATE_DIR, tree_snapshot


class RecoveryFixture(AcceptFixture):
    def interrupt_accept(self, event, *, mode="empty", files=None):
        if mode == "empty":
            self.write_inputs()
            self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready(mode=mode, files=files)

        def fail(actual_event, _context):
            if actual_event == event:
                raise RuntimeError(f"injected:{actual_event}")

        self.server.tools.failpoint = fail
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1),
            "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"],
            "request_id": request_id(),
            "delete_paths": inspected["changes"]["removed"],
        }, error=True)
        self.server.tools.failpoint = None
        return rejected, prepared

    def transaction_id(self, payload):
        transaction_id = payload["error"]["details"].get("transaction_id")
        self.assertRegex(transaction_id, r"^T-[0-9a-f]{32}$", payload)
        return transaction_id


class BasicRecoveryTests(RecoveryFixture):
    def test_pre_activation_rollback_closes_private_record_without_public_writes(self):
        rejected, _prepared = self.interrupt_accept("evidence_fixed")
        self.assertEqual(rejected["error"]["code"], "io_error")
        self.assertEqual(rejected["write_outcome"], "not_written")
        transaction_id = self.transaction_id(rejected)
        inspected = self.inspect("transaction", transaction_id=transaction_id)
        self.assertEqual(inspected["transaction"]["status"], "not_activated")
        self.assertTrue(all(item["actual"] == "before" for item in inspected["targets"]))
        before = tree_snapshot(self.project_p1 / "docs")
        recovered = self.recover(transaction_id, request_id(), "rollback")
        self.assertEqual(recovered["write_outcome"], "not_written")
        self.assertEqual(recovered["transaction_status"], "rolled_back")
        self.assertIsNone(recovered["current_revision"])
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), before)
        self.assertFalse((self.project_p1 / STATE_DIR / "transaction.json").exists())

    def test_partial_first_accept_resumes_to_complete_saved_collection(self):
        rejected, _prepared = self.interrupt_accept("member_after:0")
        self.assertEqual(rejected["write_outcome"], "unknown")
        transaction_id = self.transaction_id(rejected)
        inspected = self.inspect("transaction", transaction_id=transaction_id)
        self.assertEqual({item["actual"] for item in inspected["targets"]},
                         {"before", "after"})
        resumed = self.recover(transaction_id, request_id(), "resume")
        self.assertEqual(resumed["write_outcome"], "saved")
        self.assertEqual(resumed["transaction_status"], "resumed")
        self.assertFalse((self.project_p1 / STATE_DIR / "transaction.json").exists())
        for relative, content in candidate_files().items():
            expected = content if isinstance(content, bytes) else content.encode("utf-8")
            self.assertEqual((self.project_p1 / relative).read_bytes(), expected)
        replayed = self.recover(transaction_id, request_id(), "resume")
        self.assertEqual(replayed["transaction_status"], "already_closed")

    def test_partial_first_accept_rollback_removes_only_known_after_files(self):
        rejected, _prepared = self.interrupt_accept("member_after:0")
        transaction_id = self.transaction_id(rejected)
        unknown = "docs/prototypes/demo/user-note.txt"
        self.write(self.project_p1, unknown, "keep\n")
        rollback = self.recover(transaction_id, request_id(), "rollback")
        self.assertEqual(rollback["write_outcome"], "saved")
        self.assertEqual(rollback["transaction_status"], "rolled_back")
        self.assertIsNone(rollback["current_revision"])
        for relative in candidate_files():
            self.assertFalse((self.project_p1 / relative).exists(), relative)
        self.assertEqual((self.project_p1 / unknown).read_text(), "keep\n")

    def test_source_change_rejects_resume_but_allows_explicit_rollback(self):
        rejected, _prepared = self.interrupt_accept("member_after:0")
        transaction_id = self.transaction_id(rejected)
        self.write(self.project_p1, "docs/PRD.md", "# changed source\n")
        source_before = (self.project_p1 / "docs/PRD.md").read_bytes()
        rejected_resume = self.call(self.mcp.RECOVER, {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "resume"}, error=True)
        self.assertEqual(rejected_resume["error"]["code"], "source_changed")
        self.assertTrue((self.project_p1 / STATE_DIR / "transaction.json").exists())
        rollback = self.recover(transaction_id, request_id(), "rollback")
        self.assertEqual(rollback["transaction_status"], "rolled_back")
        self.assertEqual((self.project_p1 / "docs/PRD.md").read_bytes(), source_before)

    def test_third_party_other_blocks_both_actions_without_overwrite(self):
        rejected, _prepared = self.interrupt_accept("member_after:0")
        transaction_id = self.transaction_id(rejected)
        inspected = self.inspect("transaction", transaction_id=transaction_id)
        target = next(item["path"] for item in inspected["targets"]
                      if item["actual"] == "after")
        self.write(self.project_p1, target, "third party bytes\n")
        for action in ("resume", "rollback"):
            rejected_recovery = self.call(self.mcp.RECOVER, {
                "project_path": str(self.project_p1), "transaction_id": transaction_id,
                "request_id": request_id(), "action": action}, error=True)
            self.assertEqual(rejected_recovery["error"]["code"], "recovery_conflict")
            self.assertEqual((self.project_p1 / target).read_text(), "third party bytes\n")
        self.assertTrue((self.project_p1 / STATE_DIR / "transaction.json").exists())

    def test_saved_receipt_rejects_rollback_and_resume_only_closes_log(self):
        rejected, _prepared = self.interrupt_accept("after_saved_receipt")
        self.assertEqual(rejected["write_outcome"], "saved")
        transaction_id = self.transaction_id(rejected)
        public_before = tree_snapshot(self.project_p1 / "docs")
        committed = self.call(self.mcp.RECOVER, {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "rollback"}, error=True)
        self.assertEqual(committed["error"]["code"], "already_committed")
        recover_request = request_id()
        resumed = self.recover(transaction_id, recover_request, "resume")
        self.assertEqual(resumed["transaction_status"], "already_closed")
        self.assertEqual(resumed["write_outcome"], "saved")
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), public_before)
        self.assertFalse((self.project_p1 / STATE_DIR / "transaction.json").exists())
        replay = self.recover(transaction_id, recover_request, "resume")
        self.assertTrue(replay["receipt_replay"])
        self.assertEqual(replay["current_revision"], resumed["current_revision"])

    def test_invalid_plan_and_before_evidence_are_never_used_for_writes(self):
        rejected, _prepared = self.interrupt_accept("member_after:0")
        transaction_id = self.transaction_id(rejected)
        plan_path = (self.project_p1 / STATE_DIR / "transactions"
                     / transaction_id / "plan.json")
        plan = json.loads(plan_path.read_text())
        plan["plan_sha256"] = "0" * 64
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        before = tree_snapshot(self.project_p1 / "docs")
        invalid = self.call(self.mcp.RECOVER, {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "rollback"}, error=True)
        self.assertEqual(invalid["error"]["code"], "transaction_invalid")
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), before)

    def test_partial_existing_collection_rollback_restores_exact_old_bytes(self):
        first, _protected = self.save_v1()
        old_public = tree_snapshot(self.project_p1 / "docs")
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        del files[OLD]
        rejected, _prepared = self.interrupt_accept("member_after:0", mode="current", files=files)
        transaction_id = self.transaction_id(rejected)
        rollback = self.recover(transaction_id, request_id(), "rollback")
        self.assertEqual(rollback["transaction_status"], "rolled_back")
        self.assertEqual(rollback["current_revision"], first["current_revision"])
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), old_public)
        manifest = json.loads((self.project_p1 / MANIFEST_PATH).read_text())
        self.assertIn(OLD, {item["path"] for item in manifest["files"]})

    def test_partial_existing_collection_resume_finishes_new_pointer_and_history(self):
        first, _protected = self.save_v1()
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        rejected, _prepared = self.interrupt_accept("member_after:0", mode="current", files=files)
        transaction_id = self.transaction_id(rejected)
        resumed = self.recover(transaction_id, request_id(), "resume")
        self.assertEqual(resumed["transaction_status"], "resumed")
        self.assertNotEqual(resumed["current_revision"], first["current_revision"])
        current = self.read_context()
        self.assertEqual(current["current"]["revision_sha256"], resumed["current_revision"])
        self.assertEqual(len(self.read_history()["versions"]), 2)

    def test_all_after_readback_interruption_is_saved_unverified_not_saved(self):
        rejected, _prepared = self.interrupt_accept("after_pointer")
        self.assertEqual(rejected["write_outcome"], "saved_unverified")
        transaction_id = self.transaction_id(rejected)
        receipt_path = (self.project_p1 / STATE_DIR / "requests"
                        / f"{rejected['request_id']}.json")
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["status"], "incomplete")
        self.assertTrue((self.project_p1 / STATE_DIR / "transaction.json").exists())
        resumed = self.recover(transaction_id, request_id(), "resume")
        self.assertEqual(resumed["write_outcome"], "saved")

    def test_incomplete_accept_request_replay_does_not_start_second_transaction(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        args = {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": [],
        }
        self.server.tools.failpoint = lambda event, _context: (
            (_ for _ in ()).throw(RuntimeError("injected")) if event == "member_after:0" else None)
        interrupted = self.call(self.mcp.ACCEPT, args, error=True)
        self.server.tools.failpoint = None
        transaction_id = self.transaction_id(interrupted)
        replay = self.call(self.mcp.ACCEPT, args, error=True)
        self.assertEqual(replay["error"]["code"], "operation_incomplete")
        self.assertEqual(replay["error"]["details"]["transaction_id"], transaction_id)
        transactions = list((self.project_p1 / STATE_DIR / "transactions").iterdir())
        self.assertEqual(len(transactions), 1)

    def test_tampered_before_blob_is_transaction_invalid_and_public_bytes_stay(self):
        self.save_v1()
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        rejected, _prepared = self.interrupt_accept("member_after:0", mode="current", files=files)
        transaction_id = self.transaction_id(rejected)
        inspected = self.inspect("transaction", transaction_id=transaction_id)
        target = next(item for item in inspected["targets"] if item["before"]["state"] == "present")
        blob = (self.project_p1 / STATE_DIR / "transactions" / transaction_id
                / "before" / target["path"])
        original = blob.read_bytes()
        blob.write_bytes(original + b"tampered")
        public_before = tree_snapshot(self.project_p1 / "docs")
        invalid = self.call(self.mcp.RECOVER, {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "rollback"}, error=True)
        self.assertEqual(invalid["error"]["code"], "transaction_invalid")
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), public_before)
