"""Verify the checker against temporary reading chains and broken contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "check_harness_consistency.py"


class HarnessConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sdd-consistency-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for path in ("AGENTS.md", ".claude/CLAUDE.md", ".cursor/rules/00-harness-router.mdc"):
            self.write(path, "Read `harness-core/router.md`.\n")
        self.write("harness-core/router.md", "[Project](skills/project-management/SKILL.md)\n")
        self.write("harness-core/skills/project-management/SKILL.md", "Project work.\n")
        self.write_json("templates/project/.sdd/project.json", {"specification": None})
        self.write_json("templates/project/.sdd/status.json", {"stage": "initialized"})
        self.tasks = {
            "execution_mode": "automatic",
            "step_gate": {"kind": "task_review", "task_id": None, "status": "pending", "user_confirmation": None},
            "specification": None,
            "source_files": {"prd": "docs/PRD.md", "tech_spec": "docs/tech-spec.md"},
            "features": [{"id": "F-001", "title": "Upload a document",
                          "source_requirements": ["REQ-001"]}],
            "tasks": [{"id": "T-001", "dependencies": [], "rules_files": [],
                       "source_feature": "F-001", "acceptanceCriteria": ["[AC-001] Document accepted"],
                       "context_files": [{"path": "docs/PRD.md", "section": "REQ-001 Upload"}]}],
        }
        self.write_json("templates/tasks.json", self.tasks)

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_json(self, relative: str, value: dict) -> None:
        self.write(relative, json.dumps(value))

    def run_checker(self, success: bool) -> subprocess.CompletedProcess[str]:
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(self.root)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        after = {path.relative_to(self.root): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before, "Checker must be read-only")
        return result

    def test_minimal_chain_and_null_specification_are_valid(self) -> None:
        self.run_checker(True)

    def test_new_template_requires_valid_mode_and_step_gate(self) -> None:
        for change in ("missing_mode", "invalid_mode", "missing_gate", "invalid_gate"):
            with self.subTest(change=change):
                plan = deepcopy(self.tasks)
                if change == "missing_mode": del plan["execution_mode"]
                elif change == "invalid_mode": plan["execution_mode"] = "fast"
                elif change == "missing_gate": del plan["step_gate"]
                else: plan["step_gate"] = False
                self.write_json("templates/tasks.json", plan)
                self.run_checker(False)

    def test_frontend_stage_can_precede_full_business_acceptance(self) -> None:
        frontend = deepcopy(self.tasks["tasks"][0])
        frontend.update(id="T-UI", type="frontend", acceptanceCriteria=[],
                        description="Verify the upload UI; T-001 verifies AC-001 with the real backend",
                        technicalChecks=["Upload interaction follows the confirmed API using Mock"],
                        user_gate={"kind": "frontend_mock_review", "status": "pending",
                                   "frontend_task_ids": ["T-UI"], "required_services": [],
                                   "user_confirmation": None, "configuration_confirmation": None,
                                   "rework_task_ids": []})
        self.tasks["tasks"][0]["dependencies"] = ["T-UI"]
        self.tasks["tasks"].insert(0, frontend)
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(True)

    def test_frontend_stage_cannot_omit_checks_or_business_acceptance(self) -> None:
        business = deepcopy(self.tasks["tasks"][0])
        frontend = dict(business, id="T-UI", type="frontend", acceptanceCriteria=[],
                        description="Frontend stage", technicalChecks=["Verify upload UI with Mock"])
        for tasks in ([frontend], [dict(frontend, technicalChecks=[]), business],
                      [dict(frontend, technicalChecks=[""]), business],
                      [dict(frontend, type="integration"), business]):
            with self.subTest(tasks=tasks):
                self.tasks["tasks"] = tasks
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)

    def test_legacy_plan_without_features_is_preserved(self) -> None:
        del self.tasks["features"]
        self.tasks["tasks"][0].update({"source_feature": "F-042",
                                       "acceptanceCriteria": ["[AC-F042-01] Document accepted"],
                                       "status": "passed", "notes": "Previously verified"})
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(True)

    def test_multiple_features_may_trace_the_same_requirement(self) -> None:
        self.tasks["features"].append({"id": "F-002", "title": "Read the uploaded document",
                                        "source_requirements": ["REQ-001", "REQ-002"]})
        second = deepcopy(self.tasks["tasks"][0])
        second.update({"id": "T-002", "source_feature": "F-002", "dependencies": ["T-001"]})
        self.tasks["tasks"].append(second)
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(True)

    def test_new_feature_structure_can_map_original_prd_ids(self) -> None:
        self.tasks["features"][0]["source_requirements"] = ["F-042"]
        self.tasks["tasks"][0].update({"acceptanceCriteria": ["[AC-F042-01] Document accepted"],
                                       "context_files": [{"path": "docs/PRD.md", "section": "F-042 Upload"}]})
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(True)

    def test_invalid_or_duplicate_features_are_rejected(self) -> None:
        original = deepcopy(self.tasks["features"])
        for features in ({}, [], [None], [dict(original[0], id=[])],
                         [dict(original[0], id=" ")], [dict(original[0], id="F 001")],
                         [dict(original[0], title=" ")], original + original):
            with self.subTest(features=features):
                self.tasks["features"] = features
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)

    def test_missing_or_unknown_task_feature_is_rejected(self) -> None:
        for feature_id in (None, "F-999", [], ""):
            with self.subTest(feature_id=feature_id):
                self.tasks["tasks"][0]["source_feature"] = feature_id
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)
        del self.tasks["tasks"][0]["source_feature"]
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(False)

    def test_invalid_requirement_id_lists_are_rejected(self) -> None:
        for requirements in (None, "REQ-001", [], ["REQ-001", "REQ-001"], [""], ["REQ 001"],
                             ["REQ-001", {}], [42]):
            with self.subTest(requirements=requirements):
                self.tasks["features"][0]["source_requirements"] = requirements
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)

    def test_acceptance_criteria_need_bracketed_ids_and_results(self) -> None:
        for criteria in (None, "[AC-001] Accepted", [], ["[] Accepted"], ["[AC 001] Accepted"],
                         ["[AC-001] "], ["Accepted"], [{}]):
            with self.subTest(criteria=criteria):
                self.tasks["tasks"][0]["acceptanceCriteria"] = criteria
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)

    def test_completed_routes_cannot_regress_to_pending_placeholders(self) -> None:
        self.write("harness-core/router.md",
                   "`harness-core/skills/technical-discussion/SKILL.md`（待创建）\n")
        self.run_checker(False)
        self.write("harness-core/router.md",
                   "`harness-core/skills/technical-discussion/SKILL.md`\n")
        self.run_checker(False)
        self.write("harness-core/router.md", "`harness-core/skills/typo/SKILL.md`（待创建）\n")
        self.run_checker(False)

    def test_broken_relative_link_is_reported(self) -> None:
        (self.root / "harness-core/skills/project-management/SKILL.md").unlink()
        result = self.run_checker(False)
        self.assertIn("harness-core/skills/project-management/SKILL.md", result.stdout)

    def test_platform_toml_core_reference_is_checked(self) -> None:
        self.write(".codex/agents/planner.toml", 'developer_instructions = """\nharness-core/agents/planner.md\n"""\n')
        self.run_checker(False)
        self.write("harness-core/agents/planner.md", "Planner role.\n")
        self.run_checker(True)

    def test_entrypoint_must_link_to_router(self) -> None:
        self.write("AGENTS.md", "Standalone instructions without a route.\n")
        self.run_checker(False)

    def test_invalid_json_and_missing_specification_are_rejected(self) -> None:
        self.write("templates/project/.sdd/project.json", "{broken")
        self.run_checker(False)
        self.write_json("templates/project/.sdd/project.json", {})
        self.run_checker(False)

    def test_null_cannot_load_rules_and_named_rules_must_exist(self) -> None:
        self.tasks["tasks"][0]["rules_files"] = ["specification/custom/backend/api.md"]
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(False)
        self.tasks["specification"] = "custom"
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(False)
        self.write("harness-core/specification/custom/backend/api.md", "API rules.\n")
        self.run_checker(True)

    def test_invalid_dependency_graphs_are_rejected(self) -> None:
        task = deepcopy(self.tasks["tasks"][0])
        for tasks in (
            [dict(task, dependencies=["missing"])],
            [dict(task), dict(task)],
            [dict(task, dependencies=["T-002"]), dict(task, id="T-002", dependencies=["T-001"])],
        ):
            with self.subTest(tasks=tasks):
                self.tasks["tasks"] = tasks
                self.write_json("templates/tasks.json", self.tasks)
                self.run_checker(False)

    def test_project_input_paths_cannot_escape_project(self) -> None:
        self.tasks["source_files"]["prd"] = "../other-project/PRD.md"
        self.write_json("templates/tasks.json", self.tasks)
        self.run_checker(False)


if __name__ == "__main__":
    unittest.main()
