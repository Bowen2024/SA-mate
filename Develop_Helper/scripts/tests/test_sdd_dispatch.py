"""Gate behavior across parallel completion, user review, configuration and rework."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdd_dispatch import evaluate, validate


class DispatchTests(unittest.TestCase):
    def setUp(self):
        def task(i, kind, deps=(), status="pending"):
            return {"id": i, "type": kind, "dependencies": list(deps), "status": status}
        self.plan = {
            "external_services": [{"name": "model", "required": True, "status": "missing"}],
            "tasks": [task("UI1", "frontend"), task("UI2", "frontend", ["UI1"]),
                      task("API", "backend"), task("API2", "backend", ["API"]),
                      task("JOIN", "integration", ["API"]), task("DOC", "delivery", ["JOIN"])],
        }
        self.gate = {"kind": "frontend_mock_review", "frontend_task_ids": ["UI1", "UI2"],
                     "required_services": ["model"], "status": "pending", "user_confirmation": None,
                     "configuration_confirmation": None, "rework_task_ids": []}
        self.plan["tasks"][1]["user_gate"] = self.gate

    def finish_frontend(self):
        for t in self.plan["tasks"][:2]:
            t["status"] = "passed"

    def approve(self):
        self.finish_frontend()
        self.gate.update(status="passed", user_confirmation="User explicitly approved current Mock",
                         configuration_confirmation="Required fields present; no values logged")
        self.plan["external_services"][0]["status"] = "confirmed"

    def test_frontend_and_backend_can_start_together(self):
        result = evaluate(self.plan)
        self.assertEqual(result["developer_ready"], ["UI1", "API"])

    def test_integration_waits_even_when_its_dependencies_pass_before_gate(self):
        self.plan["tasks"][2]["status"] = "passed"
        result = evaluate(self.plan)
        self.assertIn("API2", result["developer_ready"])
        self.assertNotIn("JOIN", result["developer_ready"])

    def test_frontend_completion_closes_dispatch_before_status_writeback(self):
        self.finish_frontend()  # gate still pending: completion event must still close dispatch.
        self.plan["tasks"][2]["status"] = "testing"
        result = evaluate(self.plan)
        self.assertEqual(result["gate_phase"], "awaiting_user")
        self.assertEqual(result["developer_ready"], [])
        self.assertEqual(result["tester_ready"], [])

    def test_background_result_or_failure_does_not_bypass_gate(self):
        self.finish_frontend()
        for status in ("in_progress", "testing", "passed", "fixing", "blocked"):
            with self.subTest(status=status):
                self.plan["tasks"][2]["status"] = status
                result = evaluate(self.plan)
                self.assertEqual(result["developer_ready"], [])
                self.assertEqual(result["tester_ready"], [])

    def test_one_confirmation_cannot_open_gate(self):
        for key in ("user_confirmation", "configuration_confirmation"):
            with self.subTest(key=key):
                plan = deepcopy(self.plan)
                for t in plan["tasks"][:2]:
                    t["status"] = "passed"
                gate = plan["tasks"][1]["user_gate"]
                gate.update(status="passed")
                gate[key] = "confirmed"
                result = evaluate(plan)
                self.assertTrue(result["errors"])
                self.assertEqual(result["developer_ready"], [])

    def test_missing_or_mock_service_cannot_be_declared_ready(self):
        self.approve()
        for status in ("missing", "fallback"):
            self.plan["external_services"][0]["status"] = status
            self.assertTrue(evaluate(self.plan)["errors"])

    def test_release_unlocks_work_without_restarting_passed_tasks(self):
        self.approve()
        self.plan["tasks"][2]["status"] = "passed"
        result = evaluate(self.plan)
        self.assertEqual(result["developer_ready"], ["API2", "JOIN"])
        self.assertEqual(result["gate_phase"], "passed")

    def test_rework_only_dispatches_selected_frontend(self):
        self.finish_frontend()
        self.gate.update(status="changes_requested", rework_task_ids=["UI2"])
        self.plan["tasks"][1]["status"] = "fixing"
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["UI2"])
        self.plan["tasks"][1]["status"] = "testing"
        self.assertEqual(evaluate(self.plan)["tester_ready"], ["UI2"])
        self.plan["tasks"][1]["status"] = "passed"
        self.assertEqual(evaluate(self.plan)["gate_phase"], "awaiting_user")

    def test_gate_needs_all_frontend_and_final_join_dependency(self):
        for change in ("coverage", "dependency", "missing", "duplicate", "post_gate_dependency"):
            with self.subTest(change=change):
                p = deepcopy(self.plan)
                if change == "coverage": p["tasks"][1]["user_gate"]["frontend_task_ids"] = ["UI2"]
                elif change == "dependency": p["tasks"][1]["dependencies"] = []
                elif change == "missing": del p["tasks"][1]["user_gate"]
                elif change == "duplicate": p["tasks"][0]["user_gate"] = deepcopy(self.gate)
                else: p["tasks"][0]["dependencies"] = ["JOIN"]
                self.assertTrue(validate(p))

    def test_backend_only_project_needs_no_gate(self):
        p = {"tasks": [{"id": "API", "type": "backend", "status": "pending", "dependencies": []}]}
        self.assertEqual(evaluate(p)["developer_ready"], ["API"])

    def test_no_services_still_requires_explicit_not_applicable_record(self):
        self.approve()
        self.plan["external_services"] = []
        self.gate["required_services"] = []
        self.gate["configuration_confirmation"] = "No external services; not applicable"
        self.assertEqual(evaluate(self.plan)["gate_phase"], "passed")

    def test_cli_is_read_only_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "tasks.json"
            p.write_text(json.dumps(self.plan))
            before = p.read_bytes()
            script = Path(__file__).resolve().parents[1] / "sdd_dispatch.py"
            r = subprocess.run([sys.executable, str(script), "--tasks", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(p.read_bytes(), before)
            p.write_text('{"tasks": [null]}')
            r = subprocess.run([sys.executable, str(script), "--tasks", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(json.loads(r.stdout)["developer_ready"], [])


class StepModeTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "execution_mode": "step_by_step",
            "step_gate": {"kind": "task_review", "task_id": None, "status": "pending", "user_confirmation": None},
            "tasks": [{"id": i, "type": "backend", "status": "pending", "dependencies": []}
                      for i in ("A", "B", "C")],
        }

    def reserve(self, task_id="A"):
        self.plan["step_gate"].update(task_id=task_id, status="pending", user_confirmation=None)

    def no_dispatch(self, result):
        self.assertFalse(result["errors"], result)
        self.assertEqual(result["developer_ready"], [])
        self.assertEqual(result["tester_ready"], [])

    def test_step_selects_one_automatic_and_legacy_allow_parallel(self):
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["A"])
        self.plan["execution_mode"] = "automatic"
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["A", "B", "C"])
        del self.plan["execution_mode"]
        del self.plan["step_gate"]
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["A", "B", "C"])

    def test_current_task_development_testing_and_finite_rework(self):
        self.reserve()
        for status, developer, tester in [("pending", ["A"], []), ("in_progress", [], []),
                                          ("testing", [], ["A"]), ("fixing", ["A"], [])]:
            with self.subTest(status=status):
                self.plan["tasks"][0]["status"] = status
                r = evaluate(self.plan)
                self.assertEqual(r["developer_ready"], developer)
                self.assertEqual(r["tester_ready"], tester)

    def test_pass_stops_even_before_awaiting_writeback_then_approval_releases(self):
        self.reserve()
        self.plan["tasks"][0]["status"] = "passed"
        self.no_dispatch(evaluate(self.plan))
        self.assertEqual(evaluate(self.plan)["step_phase"], "awaiting_user")
        self.plan["step_gate"].update(status="passed", user_confirmation="User approved A and requested next task")
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["B"])

    def test_last_task_still_requires_approval(self):
        self.plan["tasks"] = self.plan["tasks"][:1]
        self.reserve()
        self.plan["tasks"][0]["status"] = "passed"
        self.assertEqual(evaluate(self.plan)["step_phase"], "awaiting_user")
        self.plan["step_gate"].update(status="passed", user_confirmation="User approved delivery")
        self.assertEqual(evaluate(self.plan)["step_phase"], "complete")

    def test_blocked_current_does_not_start_an_unrelated_task(self):
        self.reserve()
        self.plan["tasks"][0]["status"] = "blocked"
        self.no_dispatch(evaluate(self.plan))
        self.assertEqual(evaluate(self.plan)["step_phase"], "blocked")

    def test_user_rework_stays_scoped_even_after_switch_to_automatic(self):
        self.reserve()
        self.plan["step_gate"]["status"] = "changes_requested"
        self.plan["execution_mode"] = "automatic"
        for status, field in [("fixing", "developer_ready"), ("testing", "tester_ready")]:
            self.plan["tasks"][0]["status"] = status
            r = evaluate(self.plan)
            self.assertEqual(r[field], ["A"])
        self.plan["tasks"][0]["status"] = "passed"
        self.no_dispatch(evaluate(self.plan))

    def test_explicit_automatic_switch_releases_ordinary_step_wait(self):
        self.reserve()
        self.plan["tasks"][0]["status"] = "passed"
        self.plan["step_gate"]["status"] = "awaiting_user"
        self.plan["execution_mode"] = "automatic"
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["B", "C"])
        self.assertIsNone(self.plan["step_gate"]["user_confirmation"])

    def test_switch_drains_developers_then_serially_tests_existing_results(self):
        self.plan["tasks"][0]["status"] = "in_progress"
        self.plan["tasks"][1]["status"] = "in_progress"
        self.no_dispatch(evaluate(self.plan))
        self.plan["tasks"][0]["status"] = "testing"
        self.no_dispatch(evaluate(self.plan))
        self.plan["tasks"][1]["status"] = "testing"
        r = evaluate(self.plan)
        self.assertEqual(r["tester_ready"], ["A"])
        self.assertEqual(r["developer_ready"], [])

    def test_live_tester_blocks_new_work_and_is_not_dispatched_twice(self):
        self.plan["tasks"][1]["status"] = "testing"
        self.no_dispatch(evaluate(self.plan, ["B"]))
        self.reserve("B")
        self.no_dispatch(evaluate(self.plan, ["B"]))
        self.plan["execution_mode"] = "automatic"
        r = evaluate(self.plan, ["B"])
        self.assertEqual(r["tester_ready"], [])
        self.assertEqual(r["developer_ready"], ["A", "C"])

    def test_switch_reserves_inflight_checkpoint_and_reviews_drain_results(self):
        self.reserve()
        self.plan["tasks"][0]["status"] = "testing"
        self.plan["tasks"][1]["status"] = "testing"
        self.no_dispatch(evaluate(self.plan, ["A", "B"]))
        self.plan["tasks"][0]["status"] = "passed"
        self.no_dispatch(evaluate(self.plan, ["B"]))
        self.plan["tasks"][1]["status"] = "passed"
        r = evaluate(self.plan)
        self.no_dispatch(r)
        self.assertEqual(r["step_phase"], "awaiting_user")
        self.plan["step_gate"].update(status="passed", user_confirmation="User reviewed the returned A and B results")
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["C"])

    def test_step_selection_obeys_dependencies_even_when_priority_is_higher(self):
        self.plan["tasks"][0].update(dependencies=["B"], priority=1)
        self.plan["tasks"][1]["priority"] = 2
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["B"])

    def test_switch_does_not_reopen_passed_historical_tasks(self):
        self.plan["tasks"][0]["status"] = "passed"
        self.assertEqual(evaluate(self.plan)["developer_ready"], ["B"])

    def test_invalid_mode_or_gate_fails_closed(self):
        variants = [{"execution_mode": None}, {"execution_mode": "fast"},
                    {"execution_mode": []}, {"step_gate": False},
                    {"step_gate": {"kind": "task_review", "task_id": "unknown", "status": "pending", "user_confirmation": None}}]
        for patch in variants:
            with self.subTest(patch=patch):
                p = deepcopy(self.plan)
                p.update(patch)
                r = evaluate(p)
                self.assertTrue(r["errors"])
                self.assertEqual(r["developer_ready"], [])
        del self.plan["step_gate"]
        self.assertTrue(evaluate(self.plan)["errors"])

    def test_approval_requires_tester_pass_and_confirmation(self):
        self.reserve()
        self.plan["step_gate"].update(status="passed", user_confirmation="User says done")
        self.assertTrue(evaluate(self.plan)["errors"])
        self.plan["tasks"][0]["status"] = "passed"
        self.plan["step_gate"]["user_confirmation"] = None
        self.assertTrue(evaluate(self.plan)["errors"])

    def test_modes_cannot_bypass_frontend_gate_or_missing_config(self):
        fixture = DispatchTests()
        fixture.setUp()
        fixture.finish_frontend()
        for mode in ("automatic", "step_by_step"):
            p = deepcopy(fixture.plan)
            p["execution_mode"] = mode
            p["step_gate"] = {"kind": "task_review", "task_id": "UI2", "status": "passed", "user_confirmation": "User approved UI"}
            self.no_dispatch(evaluate(p))
            self.assertEqual(evaluate(p)["gate_phase"], "awaiting_user")
        fixture.approve()
        fixture.plan["execution_mode"] = "step_by_step"
        fixture.plan["step_gate"] = p["step_gate"]
        self.assertEqual(evaluate(fixture.plan)["developer_ready"], ["API"])

    def test_frontend_rework_is_serial_and_waits_after_retest(self):
        fixture = DispatchTests()
        fixture.setUp()
        fixture.finish_frontend()
        fixture.gate.update(status="changes_requested", rework_task_ids=["UI2"])
        p = fixture.plan
        p["execution_mode"] = "step_by_step"
        p["step_gate"] = {"kind": "task_review", "task_id": "UI2", "status": "changes_requested", "user_confirmation": None}
        p["tasks"][1]["status"] = "fixing"
        self.assertEqual(evaluate(p)["developer_ready"], ["UI2"])
        p["tasks"][1]["status"] = "passed"
        self.no_dispatch(evaluate(p))

    def test_cli_running_task_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            self.plan["tasks"][1]["status"] = "testing"
            path.write_text(json.dumps(self.plan))
            before = path.read_bytes()
            script = Path(__file__).resolve().parents[1] / "sdd_dispatch.py"
            r = subprocess.run([sys.executable, str(script), "--tasks", str(path), "--running-task", "B"],
                               capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.no_dispatch(json.loads(r.stdout))
            self.assertEqual(path.read_bytes(), before)
        self.assertTrue(evaluate(self.plan, ["unknown"])["errors"])


if __name__ == "__main__":
    unittest.main()
