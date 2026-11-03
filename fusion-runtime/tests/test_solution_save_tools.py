import json
import re
import stat
import sys

from solution_test_support import sha
from solution_test_support import SolutionFixture


class SaveToolsTests(SolutionFixture):
    def prepare_valid(self):
        self.connect(allow_save=True)
        self.initialize()
        self.write_requirements_and_prd()
        self.confirm_prd()
        return self.read_context()

    def test_first_save_unchanged_modified_save_and_history_are_durable(self):
        read = self.prepare_valid()
        first = self.save(read, self.tech_spec("首版方案"))
        self.assertEqual(first["write_outcome"], "saved", first)
        self.assertTrue(first["changed"])
        self.assertTrue(first["read_id_consumed"])
        target = self.project_a / "docs/tech-spec.md"
        self.assertEqual(sha(target.read_bytes()), first["target"]["sha256"])
        self.assertIn("prd_sha256:", target.read_text(encoding="utf-8"))
        self.assertIn("approval_verified: false", target.read_text(encoding="utf-8"))
        read = self.read_context()
        unchanged = self.save(read, self.tech_spec("首版方案"))
        self.assertEqual(unchanged["write_outcome"], "unchanged")
        self.assertFalse(unchanged["changed"])
        self.assertEqual(unchanged["history"]["status"], "not_applicable")
        read = self.read_context()
        second = self.save(read, self.tech_spec("第二版方案"))
        self.assertEqual(second["write_outcome"], "saved")
        history = self.project_a / f"docs/tech-spec-history/{first['target']['sha256']}.md"
        self.assertTrue(history.is_file())
        self.assertEqual(sha(history.read_bytes()), first["target"]["sha256"])
        self.assertEqual(second["post_write"]["target_verified"], True)
        self.assertEqual(second["confirmation"]["status"] if "confirmation" in second else "valid", "valid")

    def test_invalid_or_stale_inputs_are_rejected_before_consuming_receipt(self):
        read = self.prepare_valid()
        receipt = read["read_receipt"]["read_id"]
        self.confirm_prd(tamper_snapshot=True)
        invalid = self.save(read, self.tech_spec(), error=True)
        self.assertEqual(invalid["error"]["code"], "prd_confirmation_invalid")
        self.assertFalse(invalid["read_id_consumed"])
        self.assertIn(receipt, self.server.tools.reads)
        self.confirm_prd()
        self.write(self.project_a, "docs/PRD.md",
                   (self.project_a / "docs/PRD.md").read_text(encoding="utf-8") + "\n改动\n")
        stale = self.save(read, self.tech_spec(), error=True)
        self.assertEqual(stale["error"]["code"], "prd_confirmation_outdated")
        self.assertFalse(stale["read_id_consumed"])

    def test_unknown_and_cross_project_read_ids_are_rejected(self):
        self.prepare_valid()
        other = self.read_context(project=self.project_b)
        wrong = self.call(self.mcp.SAVE_DRAFT, {
            "project_path": str(self.project_a), "read_id": other["read_receipt"]["read_id"],
            "content": self.tech_spec(), "profile": "Lite"}, error=True)
        self.assertEqual(wrong["error"]["code"], "dependency_set_changed")
        missing = self.call(self.mcp.SAVE_DRAFT, {
            "project_path": str(self.project_a), "read_id": "missing",
            "content": self.tech_spec(), "profile": "Lite"}, error=True)
        self.assertEqual(missing["error"]["code"], "read_id_invalid")

    def test_lock_conflict_consumes_receipt_but_does_not_replace_target(self):
        read = self.prepare_valid()
        lock = self.project_a / ".solution.lock"
        lock.write_text('{"operation":"other"}\n', encoding="utf-8")
        locked = self.save(read, self.tech_spec(), error=True)
        self.assertEqual(locked["error"]["code"], "lock_conflict")
        self.assertTrue(locked["read_id_consumed"])
        self.assertFalse(locked["side_effects"]["target_replaced"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_target_that_belongs_to_registry_cannot_change(self):
        read = self.prepare_valid()
        first = self.save(read, self.tech_spec("首版方案"))
        data = json.loads((self.project_a / "project.json").read_text(encoding="utf-8"))
        target_raw = (self.project_a / "docs/tech-spec.md").read_bytes()
        data["artifact_registry"]["entries"]["old-spec"] = {
            "artifact_id": "old-spec", "kind": "solution", "current_version": "v1",
            "versions": [{
                "version": "v1",
                "content": {"type": "file", "path": "docs/tech-spec.md",
                            "sha256": sha(target_raw), "size": len(target_raw)},
                "confirmation_ids": [], "producer_role": "main", "purpose": "旧方案",
                "summary": "target", "document_status": "Draft", "open_items": [],
                "availability": {"scope": "local-only", "git_commit": None},
                "registration": {"actor": {"role": "main", "principal_id": "fixture",
                                            "authority": "test"},
                                 "recorded_at": "2026-10-29T00:00:00Z"}}]}
        (self.project_a / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                                      encoding="utf-8")
        read = self.read_context()
        rejected = self.save(read, self.tech_spec("第二版方案"), error=True)
        self.assertEqual(rejected["error"]["code"], "target_bound_to_registry", rejected)
        self.assertTrue(rejected["read_id_consumed"])
        self.assertEqual(sha((self.project_a / "docs/tech-spec.md").read_bytes()),
                         first["target"]["sha256"])

    def test_saved_file_passes_independent_current_inspection(self):
        read = self.prepare_valid()
        self.save(read, self.tech_spec())
        current = self.call(self.mcp.INSPECT, {"project_path": str(self.project_a),
                                               "target": "current"})
        self.assertEqual(current["structure"]["status"], "pass", current["structure"]["issues"])
        self.assertEqual(current["checked_object"]["file_sha256"],
                         sha((self.project_a / "docs/tech-spec.md").read_bytes()))

    def test_candidate_with_structure_issues_can_save_draft_with_separate_inspection(self):
        """W08：结构 issues 不阻止 Draft 保存；inspection 独立且摘要匹配被保存版本。"""
        read = self.prepare_valid()
        body = self.tech_spec("有问题方案")
        missing_row = next(line for line in body.splitlines() if "AC-003" in line)
        saved = self.save(read, body.replace(missing_row + "\n", ""))
        self.assertEqual(saved["write_outcome"], "saved", saved)
        self.assertEqual(saved["inspection"]["status"], "issues")
        self.assertIn("coverage_ac_missing", saved["inspection"]["issue_codes"])
        self.assertEqual(saved["inspection"]["checked_file_sha256"], saved["target"]["sha256"])

    def test_same_body_with_different_profile_versions_history_and_submitted_hashes(self):
        """W02：仅元数据变化产生新版本与历史；提交/归一化摘要与实际正文一致。"""
        read = self.prepare_valid()
        body = self.tech_spec("元数据版本")
        lite = self.save(read, body, profile="Lite")
        self.assertEqual(lite["write_outcome"], "saved")
        self.assertEqual(lite["submitted_content_sha256"], sha(body.encode("utf-8")))
        read = self.read_context()
        standard = self.save(read, body, profile="Standard")
        self.assertEqual(standard["write_outcome"], "saved")
        self.assertNotEqual(lite["target"]["sha256"], standard["target"]["sha256"])
        self.assertEqual(lite["submitted_content_sha256"], standard["submitted_content_sha256"])
        self.assertEqual(lite["normalized_content_sha256"], standard["normalized_content_sha256"])
        history = self.project_a / f"docs/tech-spec-history/{lite['target']['sha256']}.md"
        self.assertTrue(history.is_file())
        self.assertEqual(sha(history.read_bytes()), lite["target"]["sha256"])
        read = self.read_context()
        again = self.save(read, body, profile="Standard")
        self.assertEqual(again["write_outcome"], "unchanged")
        self.assertFalse(again["changed"])
        self.assertEqual(again["history"]["status"], "not_applicable")

    def test_transaction_appearing_after_read_blocks_before_consumption(self):
        """W06：读取后出现未完成公共事务时 transaction_pending、不消费、目标不写。"""
        read = self.prepare_valid()
        (self.project_a / ".project-state-transaction.json").write_text(
            '{"status":"open"}', encoding="utf-8")
        blocked = self.save(read, self.tech_spec(), error=True)
        self.assertEqual(blocked["error"]["code"], "transaction_pending")
        self.assertFalse(blocked["read_id_consumed"])
        self.assertEqual(blocked["write_outcome"], "not_written")
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_unbound_prd_is_readable_but_blocked_and_explicit_missing_binding_can_save(self):
        """W07/8.3：缺绑定旧 PRD 可读取但拒绝保存；显式绑定 missing 且源需求缺失允许保存。"""
        self.prepare_valid()
        self.write(self.project_a, "docs/PRD.md",
                   "---\nartifact_kind: prd\n---\n\n" + self.prd_body())
        self.confirm_prd()
        result = self.read_context()
        self.assertEqual(result["source_alignment"]["status"], "unbound")
        blocked = self.save(result, self.tech_spec(), error=True)
        self.assertEqual(blocked["error"]["code"], "source_binding_missing")
        self.assertFalse(blocked["read_id_consumed"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())
        isolated = self.spare_fixture()
        isolated.connect(allow_save=True)
        isolated.initialize()
        isolated.write_requirements_and_prd()
        prd_path = isolated.project_a / "docs/PRD.md"
        rebound = re.sub(r"source_requirements_sha256: [0-9a-f]{64}",
                         "source_requirements_sha256: missing", prd_path.read_text(encoding="utf-8"))
        prd_path.write_text(rebound, encoding="utf-8")
        (isolated.project_a / "docs/requirements.md").unlink()
        isolated.confirm_prd()
        read = isolated.read_context()
        self.assertEqual(read["source_alignment"]["status"], "missing_source")
        saved = isolated.save(read, isolated.tech_spec())
        self.assertEqual(saved["write_outcome"], "saved", saved)

    def test_wrong_purpose_confirmation_is_ignored_until_valid_record_exists(self):
        """A01：错用途记录不满足资格，valid 记录恢复后可正向保存。"""
        self.prepare_valid()
        self.confirm_prd(purpose="其他用途")
        result = self.read_context()
        self.assertEqual(result["confirmation"]["status"], "missing")
        blocked = self.save(result, self.tech_spec(), error=True)
        self.assertEqual(blocked["error"]["code"], "prd_confirmation_missing")
        self.assertFalse(blocked["read_id_consumed"])
        self.confirm_prd()
        saved = self.save(self.read_context(), self.tech_spec())
        self.assertEqual(saved["write_outcome"], "saved")

    def test_confirmation_change_before_replace_not_written_and_after_replace_saved_unverified(self):
        """A02/W05：替换前确认失效不覆盖并保留历史副作用；替换后失效如实报 saved_unverified。"""
        read = self.prepare_valid()
        first = self.save(read, self.tech_spec("首版"))
        read = self.read_context()
        calls = {"count": 0}
        original = self.server.tools._gather

        def invalidate_before_replace(project_path):
            calls["count"] += 1
            if calls["count"] == 3:
                self.confirm_prd(purpose="其他用途")
            return original(project_path)

        self.server.tools._gather = invalidate_before_replace
        rejected = self.save(read, self.tech_spec("第二版"), error=True)
        self.server.tools._gather = original
        self.assertEqual(rejected["error"]["code"], "prd_confirmation_missing")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertEqual(sha((self.project_a / "docs/tech-spec.md").read_bytes()),
                         first["target"]["sha256"])
        self.assertTrue((self.project_a /
                         f"docs/tech-spec-history/{first['target']['sha256']}.md").is_file())
        isolated = self.spare_fixture()
        isolated.connect(allow_save=True)
        isolated.initialize()
        isolated.write_requirements_and_prd()
        isolated.confirm_prd()
        read = isolated.read_context()
        isolated_calls = {"count": 0}
        isolated_original = isolated.server.tools._gather

        def invalidate_after_replace(project_path):
            isolated_calls["count"] += 1
            if isolated_calls["count"] == 4:
                isolated.confirm_prd(purpose="其他用途")
            return isolated_original(project_path)

        isolated.server.tools._gather = invalidate_after_replace
        outcome = isolated.save(read, isolated.tech_spec("首版"))
        isolated.server.tools._gather = isolated_original
        self.assertEqual(outcome["write_outcome"], "saved_unverified")
        self.assertTrue(outcome["post_write"]["target_verified"])
        self.assertFalse(outcome["post_write"]["confirmation_rechecked"])
        self.assertTrue((isolated.project_a / "docs/tech-spec.md").is_file())
        self.assertEqual(sha((isolated.project_a / "docs/tech-spec.md").read_bytes()),
                         outcome["target"]["sha256"])

    def test_rendered_draft_over_128_kib_is_rejected_inside_kernel_without_replace(self):
        """P01：正文未超输入上限但渲染受管头后超过 128 KiB 时拒绝，消费凭证但不替换。"""
        read = self.prepare_valid()
        body = "# " + "x" * (128 * 1024 - 8)
        rejected = self.save(read, body, error=True)
        self.assertEqual(rejected["error"]["code"], "content_too_large")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_trailing_newline_variants_normalize_to_same_draft(self):
        """W02：只规范化末尾换行；同正文多余尾部换行不产生新版本。"""
        read = self.prepare_valid()
        first = self.save(read, self.tech_spec() + "\n\n")
        self.assertEqual(first["write_outcome"], "saved")
        read = self.read_context()
        again = self.save(read, self.tech_spec())
        self.assertEqual(again["write_outcome"], "unchanged")
        self.assertEqual(first["normalized_content_sha256"], again["normalized_content_sha256"])

    def test_concurrent_target_after_read_is_refused_without_replace(self):
        """W03：替换前发现目标已被并发创建时 version_conflict，保留并发稿并消费凭证。"""
        read = self.prepare_valid()
        original = self.server.tools._gather
        counts = {"n": 0}

        def create_concurrent(project_path):
            result = original(project_path)
            counts["n"] += 1
            if counts["n"] == 3:
                self.write(self.project_a, "docs/tech-spec.md", "并发稿\n")
            return result

        self.server.tools._gather = create_concurrent
        try:
            rejected = self.save(read, self.tech_spec(), error=True)
        finally:
            self.server.tools._gather = original
        self.assertEqual(rejected["error"]["code"], "version_conflict")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertEqual((self.project_a / "docs/tech-spec.md").read_text(encoding="utf-8"),
                         "并发稿\n")
        self.assertEqual(list((self.project_a / "docs").glob(".tech-spec-*")), [])

    def test_corrupt_history_is_rejected_and_old_draft_is_restored_as_new_candidate(self):
        """W04：同名坏历史 history_conflict 不修补；历史摘要不符读为 unreadable；
        旧稿剥受管头后以当前输入作为新候选保存，旧确认不复活。"""
        read = self.prepare_valid()
        first = self.save(read, self.tech_spec("第一版"))
        read = self.read_context()
        second = self.save(read, self.tech_spec("第二版"))
        history = self.project_a / f"docs/tech-spec-history/{second['target']['sha256']}.md"
        history.write_text("坏历史\n", encoding="utf-8")
        read = self.read_context()
        conflict = self.save(read, self.tech_spec("第三版"), error=True)
        self.assertEqual(conflict["error"]["code"], "history_conflict")
        self.assertEqual(conflict["write_outcome"], "not_written")
        self.assertTrue(conflict["read_id_consumed"])
        self.assertIn("第二版", (self.project_a / "docs/tech-spec.md").read_text(encoding="utf-8"))
        bad_history = self.read_context(history_sha256=second["target"]["sha256"])
        self.assertEqual(bad_history["history"]["status"], "unreadable")
        self.assertEqual(bad_history["history"]["error"], "history_digest_mismatch")

        isolated = self.spare_fixture()
        isolated.connect(allow_save=True)
        isolated.initialize()
        isolated.write_requirements_and_prd()
        isolated.confirm_prd()
        read = isolated.read_context()
        old_body = isolated.tech_spec("旧版正文")
        first_iso = isolated.save(read, old_body)
        read = isolated.read_context()
        second_iso = isolated.save(read, isolated.tech_spec("新版"))
        read = isolated.read_context(history_sha256=first_iso["target"]["sha256"])
        self.assertEqual(read["history"]["status"], "present")
        stored = read["history"]["content"]
        marker = "\n---\n\n"
        restored_body = stored[stored.index(marker) + len(marker):].rstrip("\n")
        self.assertIn("旧版正文", restored_body)
        self.assertNotIn("approval_verified", restored_body)
        restored = isolated.save(read, restored_body)
        self.assertEqual(restored["write_outcome"], "saved")
        target_raw = (isolated.project_a / "docs/tech-spec.md").read_text(encoding="utf-8")
        self.assertIn("旧版正文", target_raw)
        self.assertIn("approval_verified: false", target_raw)
        self.assertTrue((isolated.project_a /
                         f"docs/tech-spec-history/{second_iso['target']['sha256']}.md").is_file())
        self.assertEqual(restored["input_binding"]["prd_confirmation_ids"],
                         read["confirmation"]["valid_confirmation_ids"])

    def test_failure_before_replace_is_not_written_and_across_replace_is_unknown(self):
        """W05：替换前辅助失败可证明未替换→not_written；替换后失败无法判定→unknown，
        两类都消费凭证、释放锁，允许重新读取后继续。"""
        read = self.prepare_valid()
        solution_module = sys.modules[type(self.server.tools).__module__]
        real_replace = solution_module.os.replace

        def fail_replace(source, destination):
            raise OSError("注入：原子替换失败")

        solution_module.os.replace = fail_replace
        try:
            failed = self.save(read, self.tech_spec(), error=True)
        finally:
            solution_module.os.replace = real_replace
        self.assertEqual(failed["error"]["code"], "write_failed")
        self.assertEqual(failed["write_outcome"], "not_written")
        self.assertTrue(failed["read_id_consumed"])
        self.assertFalse(failed["side_effects"]["target_replaced"])
        self.assertTrue(failed["side_effects"]["temporary_created"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())
        self.assertEqual(list((self.project_a / "docs").glob(".tech-spec-*")), [])
        read = self.read_context()
        saved = self.save(read, self.tech_spec())
        self.assertEqual(saved["write_outcome"], "saved")

        isolated = self.spare_fixture()
        isolated.connect(allow_save=True)
        isolated.initialize()
        isolated.write_requirements_and_prd()
        isolated.confirm_prd()
        read = isolated.read_context()
        isolated_module = sys.modules[type(isolated.server.tools).__module__]
        real_fsync = isolated_module.os.fsync

        def fsync_fail_on_directories(descriptor):
            if stat.S_ISDIR(isolated_module.os.fstat(descriptor).st_mode):
                raise OSError("注入：替换后目录刷盘失败")
            return real_fsync(descriptor)

        isolated_module.os.fsync = fsync_fail_on_directories
        try:
            ambiguous = isolated.save(read, isolated.tech_spec(), error=True)
        finally:
            isolated_module.os.fsync = real_fsync
        self.assertEqual(ambiguous["error"]["code"], "write_failed")
        self.assertEqual(ambiguous["write_outcome"], "unknown")
        self.assertTrue(ambiguous["read_id_consumed"])
        self.assertTrue(ambiguous["side_effects"]["target_replaced"])
        self.assertTrue((isolated.project_a / "docs/tech-spec.md").is_file())
        read = isolated.read_context()
        unchanged = isolated.save(read, isolated.tech_spec())
        self.assertEqual(unchanged["write_outcome"], "unchanged")
