from solution_test_support import SolutionFixture


class InspectToolsTests(SolutionFixture):
    def test_current_missing_and_complete_lite_candidate_pass_structure(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        current = self.call(self.mcp.INSPECT, {"project_path": str(self.project_a),
                                               "target": "current"})
        self.assertEqual(current["structure"]["status"], "missing")
        candidate = self.inspect_candidate(self.tech_spec())
        self.assertEqual(candidate["structure"]["status"], "pass", candidate["structure"]["issues"])
        self.assertEqual(candidate["coverage"]["counts"]["acceptance_criteria"], 3)
        self.assertEqual(candidate["coverage"]["counts"]["covered"], 3)
        self.assertFalse(candidate["limitations"]["diagram_rendered"])

    def test_candidate_requires_profile_and_rejects_front_matter(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        bad = self.call(self.mcp.INSPECT, {"project_path": str(self.project_a), "target": "candidate",
                                           "content": "# x"}, error=True)
        self.assertEqual(bad["error"]["code"], "profile_invalid")
        bad_fm = self.call(self.mcp.INSPECT, {"project_path": str(self.project_a), "target": "candidate",
                                              "content": "---\nstatus: Draft\n---\n# x",
                                              "profile": "Lite"}, error=True)
        self.assertEqual(bad_fm["error"]["code"], "content_invalid")

    def test_unknown_ac_owner_duplicate_and_multi_ac_rows_are_locatable(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        content = self.tech_spec().replace(
            "| REQ-001 | AC-002 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | covered |",
            "| REQ-002 | AC-002 | 错误归属 | 成功路径 | 失败路径 | 验证 | covered |\n"
            "| REQ-001 | AC-001/AC-002 | 多 AC | 成功路径 | 失败路径 | 验证 | covered |\n"
            "| REQ-001 | AC-999 | 未知 AC | 成功路径 | 失败路径 | 验证 | covered |",
        )
        result = self.inspect_candidate(content)
        codes = {issue["code"] for issue in result["structure"]["issues"]}
        self.assertIn("coverage_ac_owner_mismatch", codes)
        self.assertIn("coverage_ac_count_invalid", codes)
        self.assertIn("coverage_ac_unknown", codes)

    def test_escaped_pipes_inside_code_fence_do_not_become_coverage_rows(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        content = self.tech_spec() + "\n```\n| REQ-001 | AC-001 | escaped \\| still code |\n```\n"
        result = self.inspect_candidate(content)
        self.assertEqual(result["structure"]["status"], "pass", result["structure"]["issues"])

    def test_ai_profile_requires_model_tool_evaluation_and_fallback_sections(self):
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        weak = self.inspect_candidate(self.tech_spec(), profile="AI")
        self.assertIn("ai_section_incomplete",
                      {issue["code"] for issue in weak["structure"]["issues"]})
        ai = self.tech_spec().replace(
            "无 AI，本方案不适用模型、提示词或外部工具。",
            "模型负责生成建议；提示词位于受管配置；动态输入受校验，输出必须通过 JSON schema 解析校验；"
            "工具参数与权限只读；使用离线评估集和质量阈值评估；工具失败时回退到人工复核。",
        )
        strong = self.inspect_candidate(ai, profile="AI")
        self.assertEqual(strong["structure"]["status"], "pass", strong["structure"]["issues"])

    def test_current_illegal_header_is_locatable_and_standard_candidate_passes(self):
        """I01：已保存文件受管头非法可定位；Standard 候选按同一 0—12 结构检查通过。"""
        self.write_requirements_and_prd()
        self.write(self.project_a, "docs/tech-spec.md",
                   "---\nstatus: Proposed\n---\n\n" + self.tech_spec())
        self.connect()
        self.initialize()
        current = self.call(self.mcp.INSPECT, {"project_path": str(self.project_a),
                                               "target": "current"})
        codes = {issue["code"] for issue in current["structure"]["issues"]}
        self.assertIn("managed_header_invalid", codes)
        standard = self.inspect_candidate(self.tech_spec(), profile="Standard")
        self.assertEqual(standard["structure"]["status"], "pass", standard["structure"]["issues"])

    def test_consistency_reports_change_during_inspection(self):
        """I03：检查的两次采集之间 PRD 变化时 consistency.stable=false，不沿用稳定结论。"""
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        prd = self.project_a / "docs/PRD.md"
        original = self.server.tools._snapshot_once
        state = {"calls": 0}

        def racing(binding):
            result = original(binding)
            state["calls"] += 1
            if state["calls"] == 1:
                with prd.open("a", encoding="utf-8") as stream:
                    stream.write("\n检查期间变化\n")
            return result

        self.server.tools._snapshot_once = racing
        try:
            result = self.inspect_candidate(self.tech_spec())
        finally:
            self.server.tools._snapshot_once = original
        self.assertFalse(result["consistency"]["stable"])
        self.assertIn("docs/PRD.md", result["consistency"]["changed_paths"])

    def test_invalid_status_bad_column_count_and_missing_reason_are_locatable(self):
        """I02：非法状态枚举、列数错误行和无理由 not_applicable 各自产生可定位 issue。"""
        self.connect()
        self.initialize()
        self.write_requirements_and_prd()
        base = self.tech_spec()
        bad_status = base.replace(
            "| REQ-001 | AC-001 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | covered |",
            "| REQ-001 | AC-001 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | done |")
        self.assertIn("coverage_status_invalid",
                      {issue["code"] for issue in self.inspect_candidate(bad_status)["structure"]["issues"]})
        bad_row = base.replace(
            "| REQ-001 | AC-002 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | covered |",
            "| REQ-001 | AC-002 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | covered | 多余列 |")
        bad_row_codes = {issue["code"] for issue in self.inspect_candidate(bad_row)["structure"]["issues"]}
        self.assertIn("coverage_row_invalid", bad_row_codes)
        no_reason = base.replace(
            "| REQ-002 | AC-003 | 首版方案设计 | 成功路径 | 失败路径 | 验证 | covered |",
            "| REQ-002 | AC-003 |  |  |  |  | not_applicable |")
        self.assertIn("coverage_reason_missing",
                      {issue["code"] for issue in self.inspect_candidate(no_reason)["structure"]["issues"]})

