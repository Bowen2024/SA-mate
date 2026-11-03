from pathlib import Path
import json
import os
import sys
import unittest

from solution_test_support import SolutionFixture, load_module


class ContextToolsTests(SolutionFixture):
    def test_tools_are_explicitly_gated_and_paths_are_bound_to_persistent_project(self):
        self.connect()
        self.initialize()
        self.assertEqual([tool["name"] for tool in self.list_tools()],
                         ["solution_read_context", "solution_inspect"])
        missing = self.call("solution_save_tech_spec_draft",
                            {"project_path": str(self.project_a), "read_id": "x", "content": "x",
                             "profile": "Lite"}, error=True)
        self.assertEqual(missing["error"]["code"], "tool_not_enabled")
        for path in (self.outside, self.projects, self.project_a / "docs", self.projects / "../outside"):
            with self.subTest(path=path):
                result = self.call("solution_read_context", {"project_path": str(path)}, error=True)
                self.assertEqual(result["error"]["code"], "path_not_allowed")

    def test_chinese_and_ascii_projects_use_persistent_identity_without_cross_binding(self):
        self.connect()
        self.initialize()
        a = self.read_context()
        b = self.read_context(project=self.project_b)
        self.assertEqual(a["project"]["project_id"], "meeting-helper")
        self.assertEqual(b["project"]["project_id"], "meeting-b")
        self.assertNotEqual(a["read_receipt"]["read_id"], b["read_receipt"]["read_id"])
        self.assertTrue(a["project"]["identity_persisted"])

    def test_six_core_documents_include_present_missing_empty_and_invalid_utf8_states(self):
        self.connect()
        self.initialize()
        self.write(self.project_a, "README.md", "")
        self.write(self.project_a, "docs/requirements.md", "# 源需求\n")
        invalid = self.project_a / "docs/PRD.md"
        invalid.write_bytes(b"\xff\xfe")
        result = self.read_context()
        by_path = {item["path"]: item for item in result["documents"]}
        self.assertEqual([item["path"] for item in result["documents"]], [
            "project.json", "README.md", "docs/requirements.md", "docs/PRD.md",
            "docs/tech-spec.md", "docs/decisions.md"])
        self.assertEqual(by_path["README.md"]["status"], "present")
        self.assertEqual(by_path["README.md"]["sha256"],
                         __import__("hashlib").sha256(b"").hexdigest())
        self.assertEqual(by_path["docs/tech-spec.md"]["status"], "missing")
        self.assertEqual(by_path["docs/PRD.md"]["status"], "unreadable")
        self.assertIsNone(by_path["docs/PRD.md"]["sha256"])
        self.assertIsNone(result["read_receipt"])
        self.assertIn("core_document_unreadable:docs/PRD.md", result["protection"]["diagnostics"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root bypasses file permission bits")
    def test_core_document_with_no_read_permission_degrades_to_unreadable(self):
        self.connect()
        self.initialize()
        self.write(self.project_a, "README.md", "# 项目\n")
        self.write(self.project_a, "docs/requirements.md", "# 源需求\n")
        target = self.project_a / "docs/PRD.md"
        target.write_text("# PRD\n", encoding="utf-8")
        original_mode = target.stat().st_mode
        target.chmod(0o000)
        self.addCleanup(target.chmod, original_mode)
        result = self.read_context()
        by_path = {item["path"]: item for item in result["documents"]}
        prd = by_path["docs/PRD.md"]
        self.assertEqual(prd["status"], "unreadable")
        self.assertIsNone(prd["sha256"])
        self.assertIsNone(prd["content"])
        self.assertTrue(prd["error"])
        self.assertEqual(by_path["README.md"]["status"], "present")
        self.assertEqual(by_path["docs/requirements.md"]["status"], "present")
        self.assertIsNone(result["read_receipt"])
        self.assertIn("core_document_unreadable:docs/PRD.md",
                      result["protection"]["diagnostics"])

    def test_valid_confirmation_and_prd_binding_are_classified_with_five_states(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        missing = self.read_context()["confirmation"]
        self.assertEqual(missing["status"], "missing")
        self.confirm_prd()
        valid = self.read_context()
        self.assertEqual(valid["source_alignment"]["status"], "matched")
        self.assertEqual(valid["confirmation"]["status"], "valid")
        self.assertEqual(valid["confirmation"]["valid_confirmation_ids"], ["C-" + "a" * 20])
        self.write(self.project_a, "docs/requirements.md", "# 改变的源需求\n")
        outdated = self.read_context()
        self.assertEqual(outdated["source_alignment"]["status"], "outdated")

    def test_registry_file_set_and_non_prd_versions_enter_protection_closure(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        self.add_g1_file_set()
        before = self.read_context()["protection"]["dependency_set_sha256"]
        self.write(self.project_a, "docs/research/g1-note.md", "# G1 成员被修改\n")
        after = self.read_context()
        self.assertNotEqual(before, after["protection"]["dependency_set_sha256"])
        self.assertIn("docs/research/g1-note.md", str(after["protection"]["protected_versions"]))

    def test_specification_null_missing_and_selected_are_distinct(self):
        self.connect()
        self.initialize()
        self.assertEqual(self.read_context()["specification"]["state"], "missing")
        self.init_project(self.project_a, "meeting-helper", specification=None)
        self.assertEqual(self.read_context()["specification"]["state"], "none")
        self.init_project(self.project_a, "meeting-helper", specification="default")
        selected = self.read_context()
        self.assertEqual(selected["specification"]["state"], "selected")
        self.assertEqual(selected["specification"]["name"], "default")
        self.assertTrue(selected["specification"]["files"])
        backend = next(item for item in selected["specification"]["files"]
                       if item["path"] == "backend.md")
        self.assertEqual(backend["content"],
                         (self.upstream / "harness-core/specification/default/backend.md").read_text(
                             encoding="utf-8"))

    def test_unknown_arguments_and_illegal_history_digest_are_rejected(self):
        """R03/C01：未开放字段和非法历史摘要在分派前被拒绝，不扩大读取范围。"""
        self.connect()
        self.initialize()
        bad = self.call(self.mcp.READ_CONTEXT,
                        {"project_path": str(self.project_a), "additional_paths": ["outside"]}, error=True)
        self.assertEqual(bad["error"]["code"], "invalid_arguments")
        bad = self.call(self.mcp.READ_CONTEXT,
                        {"project_path": str(self.project_a), "history_sha256": "A" * 64}, error=True)
        self.assertEqual(bad["error"]["code"], "invalid_arguments")

    def test_path_safety_rejects_symlinks_hardlinks_and_traversal_but_allows_real_directories(self):
        """C03：软链、硬链、绝对路径与越界路径拒绝；真实历史目录可重复解析。"""
        deps = load_module(f"dependencies_{id(self)}",
                           self.solution / "file_tools/dependencies.py")
        docs = self.project_a / "docs"
        docs.mkdir(exist_ok=True)
        sentinel = self.outside / "sentinel.md"
        sentinel.write_text("outside", encoding="utf-8")
        (docs / "escape-link.md").symlink_to(sentinel)
        source = docs / "source.md"
        source.write_text("a", encoding="utf-8")
        os.link(source, docs / "hard-link.md")
        for relative in ("docs/escape-link.md", "docs/hard-link.md",
                         "../outside/sentinel.md", "/etc/hosts"):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    deps.safe_project_path(self.project_a, relative)
        history_dir = deps.safe_project_path(self.project_a, "docs/tech-spec-history")
        history_dir.mkdir(parents=True, exist_ok=True)
        self.assertEqual(deps.safe_project_path(self.project_a, "docs/tech-spec-history"), history_dir)

    def test_loader_rejects_missing_or_changed_dependencies_broken_methods_and_pins_origin(self):
        """C04：缺文件、摘要漂移和断链给出准确原因；共享模块原点固定在 foundation。"""
        missing = self.spare_fixture()
        sys.path.insert(0, str(missing.solution))
        from shared_loader import FoundationError, load_shared
        (missing.foundation / "file_tools/recovery.py").unlink()
        with self.assertRaises(FoundationError) as caught:
            load_shared(missing.foundation, missing.solution)
        self.assertEqual(caught.exception.code, "dependency_missing")
        changed = self.spare_fixture()
        (changed.foundation / "file_tools/recovery.py").write_text("# tampered\n", encoding="utf-8")
        with self.assertRaises(FoundationError) as caught:
            load_shared(changed.foundation, changed.solution)
        self.assertEqual(caught.exception.code, "dependency_changed")
        broken = self.spare_fixture()
        (broken.solution / "methods/develop-helper").unlink()
        with self.assertRaises(FoundationError) as caught:
            load_shared(broken.foundation, broken.solution)
        self.assertEqual(caught.exception.code, "methods_invalid")
        runtime = load_shared(self.foundation, self.solution)
        for name in ("check_foundation", "project_state", "project_init", "requirements",
                     "project_info", "recovery", "confirmation_records", "artifact_records"):
            self.assertTrue(getattr(runtime.modules, name).__file__.startswith(str(self.foundation)))

    def test_invalid_specification_and_escaping_spec_link_block_receipt(self):
        """C05：非法规范名与规范目录越界链接明确诊断，不签发可保存凭证。"""
        invalid = self.spare_fixture()
        invalid.connect()
        invalid.initialize()
        invalid.init_project(invalid.project_a, "meeting-helper", specification="no-such")
        result = invalid.read_context()
        self.assertEqual(result["specification"]["state"], "invalid")
        self.assertIsNone(result["read_receipt"])
        self.assertTrue(any(item.startswith("specification_invalid")
                            for item in result["protection"]["diagnostics"]))
        escaping = self.spare_fixture()
        sentinel = escaping.outside / "spec-sentinel.md"
        sentinel.write_text("x", encoding="utf-8")
        (escaping.upstream / "harness-core/specification/default/escape.md").symlink_to(sentinel)
        escaping.relock_upstream()
        escaping.connect()
        escaping.initialize()
        escaping.init_project(escaping.project_a, "meeting-helper", specification="default")
        result = escaping.read_context()
        self.assertIn("specification_unsafe_link", result["protection"]["diagnostics"])
        self.assertIsNone(result["read_receipt"])

    def test_read_receipt_reports_eligibility_and_transaction_blocks_issuance(self):
        """R01/W06：凭证标注保存资格；未完成事务存在时 read_receipt 为 null。"""
        self.connect(allow_save=True)
        self.initialize()
        receipt = self.read_context()["read_receipt"]
        self.assertTrue(receipt["read_id"])
        self.assertFalse(receipt["save_eligible_at_read"])
        self.assertEqual(receipt["ineligible_reasons"], ["prd_missing"])
        self.write_requirements_and_prd()
        self.confirm_prd()
        self.assertTrue(self.read_context()["read_receipt"]["save_eligible_at_read"])
        (self.project_a / ".project-state-transaction.json").write_text(
            '{"status":"open"}', encoding="utf-8")
        blocked = self.read_context()
        self.assertIsNone(blocked["read_receipt"])
        self.assertIn("transaction_pending", blocked["protection"]["diagnostics"])

    def test_receipt_pool_evicts_oldest_after_64_entries(self):
        """R04：单进程最多 64 个凭证，按签发顺序淘汰。"""
        self.connect()
        self.initialize()
        ids = [self.read_context()["read_receipt"]["read_id"] for _ in range(65)]
        self.assertNotIn(ids[0], self.server.tools.reads)
        self.assertIn(ids[-1], self.server.tools.reads)
        self.assertEqual(len(self.server.tools.reads), 64)

    def test_dependency_collection_over_512_files_blocks_receipt(self):
        """P01：依赖闭包超过 512 个唯一文件时报告 dependency_limit_exceeded，不签发凭证。"""
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        self.add_budget_members(510)
        result = self.read_context()
        self.assertIsNone(result["read_receipt"])
        self.assertIn("dependency_limit_exceeded", result["protection"]["diagnostics"])

    def test_history_is_additional_read_and_receipt_is_not_issued_when_graph_changes(self):
        self.connect(allow_save=True)
        self.initialize()
        self.write_requirements_and_prd()
        self.confirm_prd()
        read = self.read_context()
        saved = self.save(read, self.tech_spec())
        read_two = self.read_context()
        changed = self.tech_spec("第二版")
        saved_two = self.save(read_two, changed)
        history = self.read_context(history_sha256=saved["target"]["sha256"])
        self.assertEqual(history["history"]["sha256"], saved["target"]["sha256"])
        self.assertTrue(history["read_receipt"]["read_id"])
        self.write(self.project_a, "docs/research/external.md", "# read race\n")
        self.add_g1_file_set(tamper_after=True)
        raced = self.read_context()
        self.assertIsNone(raced["read_receipt"])
        self.assertIn("docs/research/g1-note.md", str(raced["protection"]["protected_versions"]))

    def test_ttl_cross_project_and_receipt_eviction(self):
        self.connect(allow_save=True)
        self.initialize()
        self.write_requirements_and_prd()
        receipt = self.read_context()["read_receipt"]["read_id"]
        self.now = 899
        self.assertIn(receipt, self.server.tools.reads)
        self.now = 900
        self.read_context()
        self.assertNotIn(receipt, self.server.tools.reads)

    def test_unknown_protocol_version_and_pre_initialize_calls_are_rejected(self):
        """C01：未知协议版本在 initialize 协商阶段拒绝；未 initialize 不能调用工具。"""
        self.connect()
        bad = self.rpc("initialize", {"protocolVersion": "1999-01-01", "capabilities": {}})
        self.assertEqual(bad["error"]["code"], -32602)
        early = self.rpc("tools/list")
        self.assertEqual(early["error"]["code"], -32000)

    def test_uninitialized_project_and_persistent_identity_conflicts_are_rejected(self):
        """R01/C02：缺 project.json 报 project_not_initialized；同 ID 异目录与错误映射报 identity_conflict。"""
        self.connect()
        self.initialize()
        stray = self.projects / "stray-meeting"
        stray.mkdir()
        result = self.call(self.mcp.READ_CONTEXT, {"project_path": str(stray)}, error=True)
        self.assertEqual(result["error"]["code"], "project_not_initialized")
        clone = self.projects / "meeting-helper-clone"
        self.init_project(clone, "meeting-helper")
        result = self.call(self.mcp.READ_CONTEXT, {"project_path": str(clone)}, error=True)
        self.assertEqual(result["error"]["code"], "identity_conflict")
        mapped = self.spare_fixture()
        mapped.config["project_directories"] = {
            "meeting-b": "other-dir", "wrong-id": mapped.project_b.name}
        mapped.write_config()
        mapped.connect()
        mapped.initialize()
        result = mapped.call(mapped.mcp.READ_CONTEXT,
                             {"project_path": str(mapped.project_b)}, error=True)
        self.assertEqual(result["error"]["code"], "identity_conflict")

    def test_change_between_the_two_collection_passes_blocks_receipt(self):
        """R05：两次依赖采集之间修改 PRD 时 changed_during_read 可定位、不签发凭证。"""
        self.connect(allow_save=True)
        self.initialize()
        self.write_requirements_and_prd()
        self.confirm_prd()
        prd = self.project_a / "docs/PRD.md"
        original = self.server.tools._snapshot_once
        state = {"calls": 0}

        def racing(binding):
            result = original(binding)
            state["calls"] += 1
            if state["calls"] == 1:
                with prd.open("a", encoding="utf-8") as stream:
                    stream.write("\n读取期间变化\n")
            return result

        self.server.tools._snapshot_once = racing
        try:
            result = self.read_context()
        finally:
            self.server.tools._snapshot_once = original
        self.assertIsNone(result["read_receipt"])
        self.assertIn("docs/PRD.md", result["protection"]["changed_during_read"])
        self.assertFalse(result["protection"]["atomic_snapshot"])

    def test_inspect_neither_consumes_nor_refreshes_receipt(self):
        """R04/I03：重复 inspect 不消费、不续期凭证，随后保存仍可使用同一 read_id。"""
        self.connect(allow_save=True)
        self.initialize()
        self.write_requirements_and_prd()
        self.confirm_prd()
        read = self.read_context()
        read_id = read["read_receipt"]["read_id"]
        self.inspect_candidate(self.tech_spec())
        self.inspect_candidate(self.tech_spec(), profile="Standard")
        self.assertIn(read_id, self.server.tools.reads)
        saved = self.save(read, self.tech_spec())
        self.assertEqual(saved["write_outcome"], "saved")

    def test_oversize_prd_is_unreadable_and_return_budget_is_rejected(self):
        """P01/R01：单文件超过 128 KiB 不截断返回；返回正文合计超过 1 MiB 直接拒绝。"""
        self.connect()
        self.initialize()
        (self.project_a / "docs/PRD.md").write_bytes(b"x" * (128 * 1024 + 1))
        result = self.read_context()
        prd = next(item for item in result["documents"] if item["path"] == "docs/PRD.md")
        self.assertEqual(prd["status"], "unreadable")
        self.assertEqual(prd["error"], "file_too_large")
        self.assertIsNone(result["read_receipt"])
        budget = self.spare_fixture()
        budget.connect()
        budget.initialize()
        budget.write(budget.project_a, "docs/decisions.md", "x" * (1024 * 1024))
        raised = budget.call(budget.mcp.READ_CONTEXT,
                             {"project_path": str(budget.project_a)}, error=True)
        self.assertEqual(raised["error"]["code"], "content_too_large")

    def test_change_in_each_protected_category_voids_stale_receipt(self):
        """R02：各类保护闭包成员变化都使旧 read_id 在消费前被拒绝，目标不写。"""
        unchanged = object()

        def prepare(fixture, specification=unchanged):
            if specification is not unchanged:
                fixture.init_project(fixture.project_a, "meeting-helper", specification=specification)
            fixture.connect(allow_save=True)
            fixture.initialize()
            fixture.write_requirements_and_prd()
            fixture.confirm_prd()
            return fixture.read_context()

        cases = []

        project_json = self.spare_fixture()
        read = prepare(project_json)
        data = json.loads((project_json.project_a / "project.json").read_text(encoding="utf-8"))
        data["probe"] = 1
        (project_json.project_a / "project.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        cases.append(("project_json", project_json, read, "dependency_set_changed"))

        readme = self.spare_fixture()
        read = prepare(readme)
        readme.write(readme.project_a, "README.md", "# changed\n")
        cases.append(("readme", readme, read, "dependency_set_changed"))

        decisions = self.spare_fixture()
        read = prepare(decisions)
        with (decisions.project_a / "docs/decisions.md").open("a", encoding="utf-8") as stream:
            stream.write("\n探针：记录正文之外的说明\n")
        cases.append(("decisions", decisions, read, "dependency_set_changed"))

        snapshot_case = self.spare_fixture()
        read = prepare(snapshot_case)
        snapshot_file = next(snapshot_case.project_a.glob("docs/confirmations/snapshots/*/PRD.md"))
        with snapshot_file.open("ab") as stream:
            stream.write(b"probe")
        cases.append(("confirmation_snapshot", snapshot_case, read, "dependency_set_changed"))

        registry = self.spare_fixture()
        prepare(registry)
        registry.add_g1_file_set()
        read = registry.read_context()
        registry.write(registry.project_a, "docs/research/g1-note.md", "# G1 成员被修改\n")
        cases.append(("registry_file_set", registry, read, "dependency_set_changed"))

        specification_case = self.spare_fixture()
        read = prepare(specification_case, "default")
        with (specification_case.upstream / "harness-core/specification/default/backend.md").open(
                "a", encoding="utf-8") as stream:
            stream.write("\n规范成员变化\n")
        specification_case.relock_upstream()
        cases.append(("specification", specification_case, read, "runtime_baseline_changed"))

        for label, fixture, stale_read, expected_code in cases:
            with self.subTest(case=label):
                rejected = fixture.save(stale_read, fixture.tech_spec(), error=True)
                self.assertEqual(rejected["error"]["code"], expected_code, label)
                self.assertFalse(rejected["read_id_consumed"], label)
                self.assertFalse((fixture.project_a / "docs/tech-spec.md").exists(), label)
