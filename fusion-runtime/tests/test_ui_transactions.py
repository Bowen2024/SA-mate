"""UI transaction read-only inspection against hand-built static fixtures.

These transaction plans, before/after blobs, active pointers and receipts are
constructed directly by the test support, not produced by ui_accept_revision.
They are recovery-classification evidence only and are never save proof.
ui_inspect(target=transaction) must never execute resume or rollback.
"""

import json

from ui_test_support import DEFAULT_ROOT, STATE_DIR, UiFixture, tree_snapshot


MEMBER = f"{DEFAULT_ROOT}/index.html"
OTHER = f"{DEFAULT_ROOT}/assets/app.js"
T_STAGED = "T-" + "1" * 32
T_APPLY = "T-" + "2" * 32
T_INTER = "T-" + "3" * 32
T_SAVED = "T-" + "4" * 32


def error_payload(fixture, response):
    payload = json.loads(response["result"]["content"][0]["text"])
    fixture.assertTrue(response["result"]["isError"], payload)
    return payload


class TransactionActivationTests(UiFixture):
    def test_no_active_transaction_reports_not_activated(self):
        self.connect()
        result = self.inspect("transaction", identifier=20)
        self.assertEqual(result["state"], "not_activated")
        self.assertIsNone(result["transaction"])
        self.assertEqual(result["targets"], [])
        self.assertEqual(result["available_actions"], [])

    def test_active_pointer_is_used_without_transaction_id(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}],
            active=True, stage="staged")
        self.write(self.project_p1, MEMBER, "old\n")
        self.connect()
        result = self.inspect("transaction", identifier=21)
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(result["transaction"]["transaction_id"], T_STAGED)
        self.assertTrue(result["transaction"]["active"])
        self.assertEqual(result["transaction"]["stage"], "staged")


class TransactionClassificationTests(UiFixture):
    def connect_and_inspect(self, transaction_id, identifier, **kwargs):
        self.connect()
        return self.inspect("transaction", transaction_id=transaction_id,
                            identifier=identifier, **kwargs)

    def test_all_before_is_staged_and_closable(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}])
        self.write(self.project_p1, MEMBER, "old\n")
        result = self.connect_and_inspect(T_STAGED, 22)
        self.assertEqual(result["transaction"]["status"], "staged")
        self.assertEqual(result["targets"][0]["actual"], "before")
        self.assertEqual(set(result["available_actions"]),
                         {"resume", "rollback", "close_private"})

    def test_all_after_is_applying_without_close_private(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_APPLY,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}])
        self.write(self.project_p1, MEMBER, "new\n")
        result = self.connect_and_inspect(T_APPLY, 23)
        self.assertEqual(result["transaction"]["status"], "applying")
        self.assertEqual(result["targets"][0]["actual"], "after")
        self.assertEqual(set(result["available_actions"]), {"resume", "rollback"})

    def test_mixed_progress_is_interrupted(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_INTER,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"},
                     {"path": OTHER, "before": b"a\n", "after": b"b\n"}])
        self.write(self.project_p1, MEMBER, "new\n")
        self.write(self.project_p1, OTHER, "a\n")
        result = self.connect_and_inspect(T_INTER, 24)
        self.assertEqual(result["transaction"]["status"], "interrupted")
        self.assertEqual({item["actual"] for item in result["targets"]},
                         {"before", "after"})
        self.assertEqual(set(result["available_actions"]), {"resume", "rollback"})

    def test_saved_receipt_is_committed(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_SAVED, request_id="Q-saved",
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}],
            receipt={"status": "completed", "write_outcome": "saved"})
        self.write(self.project_p1, MEMBER, "new\n")
        result = self.connect_and_inspect(T_SAVED, 25)
        self.assertEqual(result["transaction"]["status"], "committed")
        self.assertEqual(result["available_actions"], ["verify_and_close"])
        self.assertEqual(result["transaction"]["saved_receipt"]["write_outcome"], "saved")

    def test_before_after_evidence_is_echoed(self):
        from ui_test_support import sha
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": None}])
        result = self.connect_and_inspect(T_STAGED, 26)
        target = result["targets"][0]
        self.assertEqual(target["before"],
                         {"state": "present", "sha256": sha(b"old\n")})
        self.assertEqual(target["after"], {"state": "missing", "sha256": "missing"})

    def test_inspect_transaction_is_side_effect_free(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}],
            active=True)
        self.write(self.project_p1, MEMBER, "old\n")
        self.connect()
        before = tree_snapshot(self.project_p1)
        self.inspect("transaction", identifier=27)
        self.inspect("transaction", transaction_id=T_STAGED, identifier=28)
        self.assertEqual(before, tree_snapshot(self.project_p1))


class TransactionRejectionTests(UiFixture):
    def inspect_raw(self, transaction_id, identifier):
        response = self.rpc(
            "tools/call",
            {"name": self.mcp.INSPECT,
             "arguments": {"project_path": str(self.project_p1), "target": "transaction",
                           "transaction_id": transaction_id}}, identifier)
        return error_payload(self, response)

    def test_invalid_transaction_id_format(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}])
        self.connect()
        payload = self.inspect_raw("T-xyz", 29)
        self.assertEqual(payload["error"]["code"], "invalid_arguments")

    def test_missing_plan_is_transaction_invalid(self):
        self.connect()
        payload = self.inspect_raw("T-" + "a" * 32, 30)
        self.assertEqual(payload["error"]["code"], "transaction_invalid")

    def test_tampered_plan_hash_is_transaction_invalid(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED,
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}])
        plan_path = (self.project_p1 / STATE_DIR / "transactions"
                     / T_STAGED / "plan.json")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["plan_sha256"] = "0" * 64
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        self.connect()
        payload = self.inspect_raw(T_STAGED, 31)
        self.assertEqual(payload["error"]["code"], "transaction_invalid")

    def test_project_identity_mismatch_rejected(self):
        self.build_static_transaction(
            self.project_p1, transaction_id=T_STAGED, project_id="meeting-b",
            targets=[{"path": MEMBER, "before": b"old\n", "after": b"new\n"}])
        self.connect()
        payload = self.inspect_raw(T_STAGED, 32)
        self.assertEqual(payload["error"]["code"], "transaction_invalid")
