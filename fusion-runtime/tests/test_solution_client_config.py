import json
import sys

from solution_test_support import SolutionFixture, load_module


class ClientConfigTests(SolutionFixture):
    def configure(self):
        return load_module(f"configure_client_{id(self)}", self.solution / "configure_client.py")

    def test_preview_is_zero_write_and_preserves_existing_servers(self):
        module = self.configure()
        self.client_config.parent.mkdir(parents=True, exist_ok=True)
        original = {"mcpServers": {"other": {"command": "other"}}, "topLevel": {"keep": True}}
        self.client_config.write_text(json.dumps(original), encoding="utf-8")
        before = self.client_config.read_bytes()
        preview = module.preview(config_path=self.client_config, foundation=self.foundation,
                                 python_executable=sys.executable, allow_save=True)
        self.assertFalse(preview["applied"])
        self.assertEqual(preview["other_server_names"], ["other"])
        self.assertEqual(self.client_config.read_bytes(), before)
        self.assertEqual(preview["after_entry"]["args"][-1], "--allow-save")

    def test_same_entry_is_unchanged_conflict_is_rejected_and_apply_creates_backup(self):
        module = self.configure()
        preview = module.preview(config_path=self.client_config, foundation=self.foundation,
                                 python_executable=sys.executable)
        self.assertEqual(preview["change_kind"], "missing")
        applied = module.apply_configuration(config_path=self.client_config, foundation=self.foundation,
                                             python_executable=sys.executable,
                                             expected_config_sha256=preview["expected_config_sha256"])
        self.assertTrue(applied["applied"])
        self.assertTrue(applied["backup"]["directory"])
        again = module.preview(config_path=self.client_config, foundation=self.foundation,
                               python_executable=sys.executable)
        self.assertEqual(again["change_kind"], "unchanged")
        data = json.loads(self.client_config.read_text(encoding="utf-8"))
        data["mcpServers"]["solution-designer"]["args"].append("--changed")
        self.client_config.write_text(json.dumps(data), encoding="utf-8")
        conflict = module.preview(config_path=self.client_config, foundation=self.foundation,
                                  python_executable=sys.executable)
        self.assertEqual(conflict["change_kind"], "entry_conflict")
        with self.assertRaisesRegex(ValueError, "不同"):
            module.apply_configuration(config_path=self.client_config, foundation=self.foundation,
                                       python_executable=sys.executable,
                                       expected_config_sha256=conflict["expected_config_sha256"])

    def test_rollback_removes_new_entry_without_touching_other_settings(self):
        module = self.configure()
        applied = module.apply_configuration(
            config_path=self.client_config, foundation=self.foundation,
            python_executable=sys.executable,
            expected_config_sha256=module.preview(
                config_path=self.client_config, foundation=self.foundation,
                python_executable=sys.executable)["expected_config_sha256"])
        data = json.loads(self.client_config.read_text(encoding="utf-8"))
        data["mcpServers"]["other"] = {"command": "keep"}
        data["topLevel"] = "keep"
        self.client_config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        backup = applied["backup"]["manifest"]
        rollback_preview = module.preview_rollback(config_path=self.client_config,
                                                   backup=applied["backup"]["directory"])
        self.assertTrue(rollback_preview["state"] == "rollback_available")
        rolled = module.apply_rollback(config_path=self.client_config,
                                       backup=applied["backup"]["directory"],
                                       expected_config_sha256=rollback_preview["expected_config_sha256"])
        self.assertTrue(rolled["applied"])
        result = json.loads(self.client_config.read_text(encoding="utf-8"))
        self.assertNotIn("solution-designer", result["mcpServers"])
        self.assertEqual(result["mcpServers"]["other"], {"command": "keep"})
        self.assertEqual(result["topLevel"], "keep")
        self.assertEqual(backup["server_name"], "solution-designer")

    def test_stdio_new_process_read_save_restart_history_and_no_legacy_runtime(self):
        self.write_requirements_and_prd()
        self.confirm_prd()
        def save_arguments(read):
            return {"project_path": str(self.project_a),
                    "read_id": read["read_receipt"]["read_id"],
                    "content": self.tech_spec(), "profile": "Lite"}

        read, saved = self.stdio_workflow([
            ("solution_read_context", {"project_path": str(self.project_a)}),
            ("solution_save_tech_spec_draft", save_arguments),
        ])
        self.assertEqual(read["confirmation"]["status"], "valid")
        self.assertEqual(saved["write_outcome"], "saved", saved)
        restart_messages = [
            {"method": "tools/call", "params": {"name": "solution_inspect",
                                                "arguments": {"project_path": str(self.project_a),
                                                              "target": "current"}}},
            {"method": "tools/call", "params": {"name": "solution_save_tech_spec_draft",
                                                "arguments": {"project_path": str(self.project_a),
                                                              "read_id": read["read_receipt"]["read_id"],
                                                              "content": self.tech_spec(),
                                                              "profile": "Lite"}}},
        ]
        restarted = self.stdio(input_messages=restart_messages)
        current = json.loads(restarted[1]["result"]["content"][0]["text"])
        expired = json.loads(restarted[2]["result"]["content"][0]["text"])
        self.assertEqual(current["structure"]["status"], "pass", current["structure"]["issues"])
        self.assertEqual(expired["error"]["code"], "read_id_invalid")
        self.assertFalse((self.install / "buzz-develop-helper").exists())
        self.assertFalse((self.foundation / "upstream").exists())

    def test_oversize_stdio_message_is_rejected_at_framing_layer(self):
        """P01：超过 1 MiB 的整条 JSON-RPC 消息在分派前被拒绝，进程继续存活且无文件副作用。"""
        responses = self.stdio(input_messages=[
            {"method": "tools/call", "params": {"name": "solution_inspect", "arguments": {
                "project_path": str(self.project_a), "target": "candidate",
                "content": "x" * (1024 * 1024 + 2048), "profile": "Lite"}}}])
        self.assertEqual(responses[1]["error"]["code"], -32600)
        self.assertIsNone(responses[1]["id"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_symlinked_config_path_is_rejected(self):
        """F01：配置路径为软链时明确拒绝，不通过链接越界写入。"""
        module = self.configure()
        target = self.outside / "real-mcp.json"
        target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        self.client_config.symlink_to(target)
        with self.assertRaises(ValueError):
            module.preview(config_path=self.client_config, foundation=self.foundation,
                           python_executable=sys.executable)

    def test_apply_rejects_stale_preview_digest_and_preserves_concurrent_file(self):
        """F01：预览后配置被他人修改时拒绝应用，不覆盖并发生成的内容。"""
        module = self.configure()
        preview = module.preview(config_path=self.client_config, foundation=self.foundation,
                                 python_executable=sys.executable)
        self.client_config.parent.mkdir(parents=True, exist_ok=True)
        self.client_config.write_text(
            json.dumps({"mcpServers": {"other": {"command": "keep"}}}, ensure_ascii=False),
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "预览不一致"):
            module.apply_configuration(config_path=self.client_config, foundation=self.foundation,
                                       python_executable=sys.executable,
                                       expected_config_sha256=preview["expected_config_sha256"])
        data = json.loads(self.client_config.read_text(encoding="utf-8"))
        self.assertNotIn("solution-designer", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["other"], {"command": "keep"})

    def test_existing_config_lock_blocks_apply_without_creating_target(self):
        """F01：配置锁存在时明确拒绝，不等待、不删锁、不创建目标配置。"""
        module = self.configure()
        preview = module.preview(config_path=self.client_config, foundation=self.foundation,
                                 python_executable=sys.executable)
        lock = self.client_config.parent / module.LOCK_NAME
        lock.write_text("other operation", encoding="utf-8")
        self.addCleanup(lock.unlink)
        with self.assertRaisesRegex(ValueError, "配置锁已存在"):
            module.apply_configuration(config_path=self.client_config, foundation=self.foundation,
                                       python_executable=sys.executable,
                                       expected_config_sha256=preview["expected_config_sha256"])
        self.assertFalse(self.client_config.exists())

    def test_rollback_rejects_when_solution_entry_was_modified(self):
        """F01：回退前方案条目自身被改时拒绝回退，不覆盖新条目，其他设置不受影响。"""
        module = self.configure()
        applied = module.apply_configuration(
            config_path=self.client_config, foundation=self.foundation,
            python_executable=sys.executable,
            expected_config_sha256=module.preview(
                config_path=self.client_config, foundation=self.foundation,
                python_executable=sys.executable)["expected_config_sha256"])
        data = json.loads(self.client_config.read_text(encoding="utf-8"))
        data["mcpServers"]["other"] = {"command": "keep"}
        data["mcpServers"]["solution-designer"]["args"].append("--changed")
        self.client_config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        rollback_preview = module.preview_rollback(config_path=self.client_config,
                                                   backup=applied["backup"]["directory"])
        self.assertEqual(rollback_preview["state"], "entry_modified")
        with self.assertRaisesRegex(ValueError, "精确条目"):
            module.apply_rollback(config_path=self.client_config,
                                  backup=applied["backup"]["directory"],
                                  expected_config_sha256=rollback_preview["expected_config_sha256"])
        after = json.loads(self.client_config.read_text(encoding="utf-8"))
        self.assertIn("--changed", after["mcpServers"]["solution-designer"]["args"])
        self.assertEqual(after["mcpServers"]["other"], {"command": "keep"})

    def test_stdio_full_chain_unchanged_modified_history_restore_and_invalid_confirmation(self):
        """E01：真子进程走通 首次保存→unchanged→修改保存→历史读取→旧稿恢复→无效确认拒绝。"""
        self.write_requirements_and_prd()
        self.confirm_prd()
        t1 = self.tech_spec("第一版")
        t2 = self.tech_spec("第二版")
        read_arguments = {"project_path": str(self.project_a)}

        def save_arguments(content):
            def build(last):
                return {"project_path": str(self.project_a),
                        "read_id": last["read_receipt"]["read_id"],
                        "content": content, "profile": "Lite"}
            return build

        def read_history(last):
            archives = list((self.project_a / "docs/tech-spec-history").glob("*.md"))
            self.assertEqual(len(archives), 1)
            return {"project_path": str(self.project_a), "history_sha256": archives[0].stem}

        def restore_from_history(last):
            self.assertEqual(last["history"]["status"], "present")
            stored = last["history"]["content"]
            marker = "\n---\n\n"
            body = stored[stored.index(marker) + len(marker):].rstrip("\n")
            return {"project_path": str(self.project_a),
                    "read_id": last["read_receipt"]["read_id"],
                    "content": body, "profile": "Lite"}

        def invalidate_then_read(last):
            self.confirm_prd(purpose="其他用途")
            return read_arguments

        results = self.stdio_workflow([
            ("solution_read_context", read_arguments),
            ("solution_save_tech_spec_draft", save_arguments(t1)),
            ("solution_read_context", read_arguments),
            ("solution_save_tech_spec_draft", save_arguments(t1)),
            ("solution_read_context", read_arguments),
            ("solution_save_tech_spec_draft", save_arguments(t2)),
            ("solution_read_context", read_history),
            ("solution_save_tech_spec_draft", restore_from_history),
            ("solution_read_context", invalidate_then_read),
            ("solution_save_tech_spec_draft", save_arguments(t1)),
        ])
        self.assertEqual(results[0]["confirmation"]["status"], "valid")
        self.assertEqual(results[1]["write_outcome"], "saved", results[1])
        self.assertEqual(results[3]["write_outcome"], "unchanged", results[3])
        self.assertEqual(results[5]["write_outcome"], "saved", results[5])
        self.assertEqual(results[6]["history"]["status"], "present")
        self.assertIn("第一版", results[6]["history"]["content"])
        self.assertEqual(results[7]["write_outcome"], "saved", results[7])
        self.assertEqual(results[9]["error"]["code"], "prd_confirmation_missing")
        target = self.project_a / "docs/tech-spec.md"
        self.assertIn("第一版", target.read_text(encoding="utf-8"))
        self.assertIn("approval_verified: false", target.read_text(encoding="utf-8"))
        self.assertEqual(list((self.project_a / "docs").glob(".tech-spec-*")), [])
        history_files = list((self.project_a / "docs/tech-spec-history").glob("*.md"))
        self.assertEqual(len(history_files), 2)
