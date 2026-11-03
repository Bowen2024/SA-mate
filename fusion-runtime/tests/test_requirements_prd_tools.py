"""PRD kernel binding, PRD history, inspection and save through MCP on temp projects."""

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import unittest
from unittest import mock

import test_requirements_cursor_tools as fixtures
import cursor_mcp as mcp

ID = "voice-meetup"
PRD = "docs/PRD.md"

# Test material shaped for inspect_prd, not a reviewed product requirement.
PRD_BODY = """# 语音约碰面地点 PRD（测试材料）

## 用户结果与成功指标
两位用户用一句语音说明各自位置后，得到可选的碰面地点并发出邀请。

## 具体案例
小李说“我在西湖文化广场，小王在滨江星光大道”，系统给出三个折中地点。

## 范围与边界
只包含语音输入、地点理解、候选推荐与结果反馈；公平标准仍待确认。

## REQ 与 AC

## REQ-001 语音生成候选地点

### AC-001 识别成功
- 结果类型：成功
- 前置条件：两处位置都能识别
- 操作：说出两处位置
- 可观察结果：显示至少一个候选地点
- 验证方式：测试脚本与人工检查

### AC-002 识别失败
- 结果类型：失败
- 前置条件：有一处位置无法识别
- 操作：说出模糊位置
- 可观察结果：提示补充位置且不生成候选
- 验证方式：测试脚本与人工检查

## 业务流程图
```mermaid
flowchart TD
A[语音输入] --> B[地点理解] --> C[候选推荐] --> D[结果反馈]
```

## 业务时序图
```mermaid
sequenceDiagram
U->>S: 语音说明两处位置
S-->>U: 候选碰面地点
```

## 事实、假设与待决事项
客户画像与价值目标为售前假设；公平标准待确认。

## 变更摘要
首次形成 PRD 候选。"""

PRD_BODY_B = PRD_BODY.replace("显示至少一个候选地点", "显示三个候选地点").replace(
    "首次形成 PRD 候选。", "候选地点数量改为三个。")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rendered(body, requirements_sha="missing"):
    return ("---\nartifact_kind: prd\nstatus: Draft\napproval_verified: false\n"
            "source_requirements_path: docs/requirements.md\n"
            f"source_requirements_sha256: {requirements_sha}\n---\n\n" + body.strip() + "\n")


class PrdToolsBase(unittest.TestCase):
    setUp = fixtures.CursorToolsTests.setUp
    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools
    tree = fixtures.CursorToolsTests.tree
    meta = staticmethod(fixtures.CursorToolsTests.meta)
    rpc = fixtures.CursorToolsTests.rpc
    call = fixtures.CursorToolsTests.call

    def snapshot(self, base):
        result = {}
        for directory, folders, files in os.walk(base):
            for name in folders + files:
                path = Path(directory) / name
                key = path.relative_to(base).as_posix()
                if path.is_symlink():
                    result[key] = "link:" + os.readlink(path)
                elif path.is_file():
                    result[key] = path.read_bytes()
                else:
                    result[key] = None
        return result

    def shared(self, **options):
        return mcp.SharedProjectTools(foundation=self.foundation, clock=lambda: self.now, **options)

    def init(self, path=None):
        arguments = {"name": "语音约碰面地点", "purpose": "PRD 工具临时测试"}
        if path is not None:
            arguments["project_path"] = str(path)
        return self.call(mcp.PROJECT_INITIALIZE, arguments)

    def read(self, **arguments):
        return self.call(mcp.READ_CONTEXT, arguments)

    def save_prd(self, content, receipt, *, error=False, **extra):
        return self.call(mcp.SAVE_PRD_DRAFT, {"content": content, "read_id": receipt["read_id"], **extra},
                         error=error)

    def save_light(self, content, receipt, **extra):
        return self.call(mcp.SAVE_DRAFT, {"content": content, "read_id": receipt["read_id"], **extra})

    def inspect(self, **arguments):
        return self.call(mcp.INSPECT_PRD, arguments)

    def write(self, relative, content, project=None):
        path = (project or self.project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def assert_no_locks(self, project=None):
        for name in (".prd.lock", ".project-state.lock"):
            self.assertFalse(((project or self.project) / name).exists(), name)

    def kernel(self, **options):
        return mock.patch.object(mcp.requirements, "save_prd_draft",
                                 wraps=mcp.requirements.save_prd_draft, **options)


class PrdKernelBindingTests(PrdToolsBase):
    """Step 3: directory binding of the copied PRD kernel."""

    def initialize(self, identifier=ID, path=None):
        options = {} if path is None else dict(expected_root=path, directory_name=path.name)
        if path is not None:
            path.mkdir()
        mcp.project_init.initialize_existing(self.foundation, identifier, "语音约碰面地点", "PRD 内核测试",
                                             **options)

    def test_mapped_directory_and_original_positional_calls(self):
        self.initialize()
        first = mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                                expected_root=self.project)
        self.assertEqual(Path(first["path"]), self.project / PRD)
        old = (self.project / PRD).read_bytes()
        self.assertEqual(old.decode("utf-8"), rendered(PRD_BODY))
        bound = mcp.requirements.inspect_prd(self.foundation, ID, expected_root=self.project)
        self.assertEqual(bound["prd"]["sha256"], first["sha256"])
        self.assertEqual(bound["issues"], [])
        second = mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY_B, first["sha256"], "missing")
        self.assertTrue(second["changed"])
        self.assertEqual((self.project / f"docs/prd-history/{first['sha256']}.md").read_bytes(), old)
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), rendered(PRD_BODY_B))
        self.assertEqual(mcp.requirements.inspect_prd(self.foundation, ID)["prd"]["sha256"], second["sha256"])
        before = self.tree()
        noop = mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY_B, second["sha256"], "missing")
        self.assertFalse(noop["changed"])
        self.assertEqual(self.tree(), before)
        self.assert_no_locks()

    def test_unmapped_chinese_directory_requires_explicit_binding(self):
        path = self.projects / "新的中文项目"
        self.initialize("req-cn", path)
        binding = dict(expected_root=path, directory_name=path.name)
        saved = mcp.requirements.save_prd_draft(self.foundation, "req-cn", PRD_BODY, "missing", "missing",
                                                **binding)
        self.assertEqual((path / PRD).read_text(encoding="utf-8"), rendered(PRD_BODY))
        inspected = mcp.requirements.inspect_prd(self.foundation, "req-cn", **binding)
        self.assertEqual(inspected["prd"]["sha256"], saved["sha256"])
        before = self.snapshot(self.projects)
        for options in ({}, {"expected_root": path}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    mcp.requirements.save_prd_draft(self.foundation, "req-cn", PRD_BODY_B, saved["sha256"],
                                                    "missing", **options)
                with self.assertRaises(ValueError):
                    mcp.requirements.inspect_prd(self.foundation, "req-cn", **options)
        self.assertEqual(self.snapshot(self.projects), before)

    def test_directory_identity_mismatch_is_rejected(self):
        path = self.projects / "另一个中文项目"
        self.initialize("req-b", path)
        before = self.snapshot(self.projects)
        with self.assertRaisesRegex(ValueError, "身份不匹配"):
            mcp.requirements.save_prd_draft(self.foundation, "req-c", PRD_BODY, "missing", "missing",
                                            expected_root=path, directory_name=path.name)
        with self.assertRaisesRegex(ValueError, "身份不匹配"):
            mcp.requirements.inspect_prd(self.foundation, "req-c", expected_root=path, directory_name=path.name)
        self.assertEqual(self.snapshot(self.projects), before)

    def test_scope_symlink_and_mapping_violations_are_rejected(self):
        self.initialize()
        outside = self.root / "outside"
        outside.mkdir()
        (self.projects / "链接目录").symlink_to(outside, target_is_directory=True)
        cases = (
            ("req-x", "../outside", self.root / "outside", "单层目录名"),
            ("req-x", "链接目录", self.projects / "链接目录", "软链"),
            ("req-x", self.project.name, self.project, "已绑定其他项目编号"),
            (ID, "另一个目录", self.projects / "另一个目录", "已有目录映射冲突"),
        )
        before, before_outside = self.snapshot(self.projects), self.snapshot(outside)
        for identifier, directory, root, message in cases:
            with self.subTest(directory=directory, identifier=identifier):
                with self.assertRaisesRegex(ValueError, message):
                    mcp.requirements.save_prd_draft(self.foundation, identifier, PRD_BODY, "missing", "missing",
                                                    expected_root=root, directory_name=directory)
                with self.assertRaisesRegex(ValueError, message):
                    mcp.requirements.inspect_prd(self.foundation, identifier, expected_root=root,
                                                 directory_name=directory)
        (self.project / "docs").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "软链"):
            mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                            expected_root=self.project)
        (self.project / "docs").unlink()
        self.assertEqual(self.snapshot(self.projects), before)
        self.assertEqual(self.snapshot(outside), before_outside)
        self.assert_no_locks()

    def test_fixed_directory_mismatch_is_rejected_without_switching_target(self):
        self.initialize()
        other = self.projects / "另一个目录"
        other.mkdir()
        before = self.snapshot(self.projects)
        with self.assertRaisesRegex(ValueError, "固定的目录不一致"):
            mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                            expected_root=other)
        with self.assertRaisesRegex(ValueError, "固定的目录不一致"):
            mcp.requirements.inspect_prd(self.foundation, ID, expected_root=other)
        with self.assertRaisesRegex(ValueError, "必须同时固定"):
            mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                            directory_name=self.project.name)
        self.assertEqual(self.snapshot(self.projects), before)

    def test_prd_and_requirements_version_conflicts_do_not_overwrite(self):
        self.initialize()
        saved = mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                                expected_root=self.project)
        before = self.tree()
        with self.assertRaisesRegex(ValueError, "PRD 版本冲突"):
            mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY_B, "missing", "missing",
                                            expected_root=self.project)
        self.assertEqual(self.tree(), before)
        self.write("docs/requirements.md", "concurrent requirements")
        before = self.tree()
        with self.assertRaisesRegex(ValueError, "轻量需求输入版本冲突"):
            mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY_B, saved["sha256"], "missing",
                                            expected_root=self.project)
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.project / "docs/prd-history").exists())
        self.assert_no_locks()

    def test_existing_write_locks_are_preserved(self):
        self.initialize()
        for name in (".prd.lock", ".project-state.lock"):
            with self.subTest(lock=name):
                lock = self.write(name, "another writer")
                before = self.tree()
                with self.assertRaisesRegex(ValueError, "锁已存在"):
                    mcp.requirements.save_prd_draft(self.foundation, ID, PRD_BODY, "missing", "missing",
                                                    expected_root=self.project)
                self.assertEqual(self.tree(), before)
                self.assertEqual(lock.read_text(encoding="utf-8"), "another writer")
                lock.unlink()
        self.assertFalse((self.project / PRD).exists())


class PrdHistoryReadTests(PrdToolsBase):
    """Step 4: PRD history through requirements_read_context."""

    def test_existing_and_missing_prd_history(self):
        self.init()
        first = self.save_prd(PRD_BODY, self.read())
        old = (self.project / PRD).read_bytes()
        second = self.save_prd(PRD_BODY_B, self.read())
        before = self.tree()
        result = self.read(prd_history_sha256=first["sha256"])
        self.assertEqual(result["prd_history"], {"path": f"docs/prd-history/{first['sha256']}.md",
                                                 "content": old.decode("utf-8"), "sha256": first["sha256"]})
        self.assertEqual(second["history"], result["prd_history"])
        self.assertNotIn("history", result)
        missing = self.read(prd_history_sha256="0" * 64)["prd_history"]
        self.assertEqual((missing["sha256"], missing["content"]), ("missing", None))
        self.assertEqual(self.tree(), before)

    def test_invalid_digest_is_rejected_before_any_read(self):
        self.init()
        before = self.tree()
        with mock.patch.object(mcp.requirements, "read_document", side_effect=AssertionError("read")):
            for value in ("../../outside", "a" * 63, "A" * 64, "g" * 64, "a" * 64 + "/x", ""):
                with self.subTest(value=value):
                    self.call(mcp.READ_CONTEXT, {"prd_history_sha256": value}, error=True)
        self.assertEqual(self.tree(), before)

    def test_requirements_and_prd_histories_are_isolated(self):
        self.init()
        light = self.save_light("# 需求\n第一版", self.read())
        self.save_light("# 需求\n第二版", self.read())
        prd = self.save_prd(PRD_BODY, self.read())
        self.save_prd(PRD_BODY_B, self.read())
        self.assertEqual(self.read(prd_history_sha256=light["sha256"])["prd_history"]["sha256"], "missing")
        self.assertEqual(self.read(history_sha256=prd["sha256"])["history"]["sha256"], "missing")
        both = self.read(history_sha256=light["sha256"], prd_history_sha256=prd["sha256"])
        self.assertEqual(both["history"]["content"], light["document"]["content"])
        self.assertEqual(both["prd_history"]["content"], prd["document"]["content"])
        self.write(f"docs/requirements-history/{'b' * 64}.md", "legacy unchecked history")
        legacy = self.read(history_sha256="b" * 64)["history"]
        self.assertEqual(legacy["content"], "legacy unchecked history")

    def test_prd_history_is_scoped_to_the_selected_project(self):
        self.server = mcp.McpServer(self.shared(allow_initialize=True, allow_save=True))
        other = self.projects / "另一个项目"
        self.init(self.project)
        self.init(other)
        first = self.save_prd(PRD_BODY, self.read(project_path=str(self.project)), project_path=str(self.project))
        self.save_prd(PRD_BODY_B, self.read(project_path=str(self.project)), project_path=str(self.project))
        found = self.read(project_path=str(self.project), prd_history_sha256=first["sha256"])
        self.assertEqual(found["prd_history"]["content"], first["document"]["content"])
        crossed = self.read(project_path=str(other), prd_history_sha256=first["sha256"])
        self.assertEqual(crossed["prd_history"]["sha256"], "missing")
        self.assertFalse((other / "docs").exists())

    def test_unreadable_or_invalid_history_fails_instead_of_missing(self):
        self.init()
        outside = self.root / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        history = self.project / "docs/prd-history"
        history.mkdir(parents=True)
        (history / f"{'c' * 64}.md").write_text("tampered", encoding="utf-8")
        (history / f"{'d' * 64}.md").symlink_to(outside)
        (history / f"{'e' * 64}.md").mkdir()
        (history / f"{'f' * 64}.md").write_bytes(b"x" * (mcp.requirements.LIMIT + 1))
        before = self.snapshot(self.project)
        for value in ("c" * 64, "d" * 64, "e" * 64, "f" * 64):
            with self.subTest(value=value[0]):
                failure = self.call(mcp.READ_CONTEXT, {"prd_history_sha256": value}, error=True)
                self.assertNotIn("read_id", failure)
                self.assertNotIn("prd_history", failure)
        self.assertEqual(self.snapshot(self.project), before)
        self.assertEqual(len(self.tools.reads), 0)

    def test_history_read_keeps_current_version_as_save_baseline(self):
        self.init()
        first = self.save_prd(PRD_BODY, self.read())
        second = self.save_prd(PRD_BODY_B, self.read())
        receipt = self.read(prd_history_sha256=first["sha256"])
        restored = self.save_prd(PRD_BODY, receipt)
        self.assertEqual(restored["history"]["sha256"], second["sha256"])
        self.assertEqual(restored["document"]["content"], first["document"]["content"])


class PrdInspectToolTests(PrdToolsBase):
    """Step 5: read-only PRD structure inspection."""

    def codes(self, content):
        self.write(PRD, content)
        before = self.tree()
        result = self.inspect()
        self.assertEqual(self.tree(), before)
        self.assertEqual(result["prd"]["sha256"], sha((self.project / PRD).read_bytes()))
        return {issue["code"]: issue for issue in result["issues"]}

    def test_discovery_and_read_only_availability(self):
        for shared in (False, True):
            with self.subTest(shared=shared):
                tools = self.shared() if shared else self.new_tools()
                self.server = mcp.McpServer(tools)
                listing = {tool["name"]: tool for tool in self.rpc("tools/list")["result"]["tools"]}
                tool = listing[mcp.INSPECT_PRD]
                self.assertEqual(tool["annotations"], {"readOnlyHint": True, "openWorldHint": False,
                                                       "destructiveHint": False, "idempotentHint": True})
                self.assertEqual(tool["inputSchema"]["required"], ["project_path"] if shared else [])
                self.assertEqual(set(tool["inputSchema"]["properties"]), {"project_path"} if shared else set())
                self.assertIn("不需要也不消费 read_id", tool["description"])
                self.assertNotIn(mcp.SAVE_PRD_DRAFT, listing)
        self.assertEqual(self.tree(), {})

    def test_missing_and_complete_prd(self):
        self.init()
        missing = self.inspect()
        self.assertEqual(missing["prd"]["sha256"], "missing")
        self.assertEqual([issue["code"] for issue in missing["issues"]], ["prd_missing"])
        self.assertEqual(self.codes(PRD_BODY), {})
        result = self.inspect()
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["prd"]["req_ids"], ["REQ-001"])
        self.assertEqual(result["prd"]["ac_ids"], ["AC-001", "AC-002"])
        self.assertEqual(result["project_path"], str(self.project))
        for flag in ("approval_checked", "semantic_correctness_checked", "diagram_rendering_checked"):
            self.assertIs(result[flag], False)
        self.call(mcp.INSPECT_PRD, {"read_id": "x"}, error=True)

    def test_structure_problems_are_reported_precisely(self):
        self.init()
        sections = self.codes(PRD_BODY.replace("## 具体案例\n", ""))
        self.assertEqual(set(sections), {"prd_sections_missing"})
        self.assertEqual(sections["prd_sections_missing"]["sections"], ["具体案例"])
        ids = self.codes(PRD_BODY.replace("REQ-001", "需求一"))
        self.assertEqual(set(ids), {"prd_ids_missing"})
        self.assertEqual(ids["prd_ids_missing"]["req_count"], 0)
        field = self.codes(PRD_BODY.replace("- 验证方式：测试脚本与人工检查\n\n### AC-002", "\n### AC-002"))
        self.assertEqual(set(field), {"acceptance_criteria_incomplete"})
        self.assertEqual(field["acceptance_criteria_incomplete"]["items"],
                         [{"ac": "AC-001", "missing": ["验证方式"]}])
        success = self.codes(PRD_BODY.replace("- 结果类型：失败", "- 结果类型：成功"))
        self.assertEqual(set(success), {"success_and_failure_coverage_missing"})
        self.assertEqual(success["success_and_failure_coverage_missing"]["observed"], ["成功"])
        self.assertEqual(set(self.codes(PRD_BODY.replace("flowchart TD", "graph TD"))),
                         {"business_flow_diagram_missing"})
        self.assertEqual(set(self.codes(PRD_BODY.replace("sequenceDiagram", "graph LR"))),
                         {"business_sequence_diagram_missing"})

    def test_inspection_does_not_consume_read_reference(self):
        self.init()
        self.write(PRD, "# 旧 PRD")
        receipt = self.read()
        before = self.tree()
        self.inspect()
        self.inspect()
        self.assertEqual(self.tree(), before)
        self.assertIn(receipt["read_id"], self.tools.reads)
        self.assertTrue(self.save_prd(PRD_BODY, receipt)["verified"])


class PrdSavePreCheckTests(PrdToolsBase):
    """Step 6: every rejection happens before the kernel is called."""

    def rejected(self, arguments, *, kernel):
        before = self.tree()
        failure = self.call(mcp.SAVE_PRD_DRAFT, arguments, error=True)
        self.assertEqual(failure["write_outcome"], "not_written", failure)
        self.assertEqual(kernel.call_count, 0)
        self.assertEqual(self.tree(), before)
        return failure

    def test_closed_tool_and_invalid_arguments_are_rejected(self):
        self.init()
        receipt = self.read()
        with self.kernel() as kernel:
            self.server = mcp.McpServer(self.new_tools(allow_initialize=True))
            self.rejected({"content": PRD_BODY, "read_id": receipt["read_id"]}, kernel=kernel)
            self.server = mcp.McpServer(self.tools)
            for arguments in ({"read_id": receipt["read_id"]}, {"content": PRD_BODY},
                              {"content": PRD_BODY, "read_id": receipt["read_id"], "path": "docs/other.md"},
                              {"content": PRD_BODY, "read_id": receipt["read_id"], "status": "Confirmed"},
                              {"content": 1, "read_id": receipt["read_id"]},
                              {"content": PRD_BODY, "read_id": 1}, []):
                with self.subTest(arguments=arguments):
                    self.rejected(arguments, kernel=kernel)
            for content in ("   ", "x" * (mcp.requirements.LIMIT - 511), "---\nstatus: Confirmed\n---\nbody",
                            "\n  ---\nartifact_kind: prd\n---\nbody"):
                with self.subTest(content=content[:20]):
                    self.rejected({"content": content, "read_id": receipt["read_id"]}, kernel=kernel)
            self.rejected({"content": PRD_BODY, "read_id": "forged"}, kernel=kernel)
        self.assertTrue(self.save_prd(PRD_BODY, receipt)["verified"])

    def test_expired_and_restarted_references_are_rejected(self):
        self.init()
        receipt = self.read()
        with self.kernel() as kernel:
            self.now = mcp.READ_TTL + 1
            self.rejected({"content": PRD_BODY, "read_id": receipt["read_id"]}, kernel=kernel)
            self.now = 0
            fresh = self.read()
            self.server = mcp.McpServer(self.new_tools(allow_save=True))
            self.rejected({"content": PRD_BODY, "read_id": fresh["read_id"]}, kernel=kernel)
        self.assertFalse((self.project / "docs").exists())

    def test_cross_project_reference_is_rejected(self):
        self.server = mcp.McpServer(self.shared(allow_initialize=True, allow_save=True))
        other = self.projects / "另一个项目"
        self.init(self.project)
        self.init(other)
        receipt = self.read(project_path=str(self.project))
        before_other = self.snapshot(other)
        with self.kernel() as kernel:
            self.rejected({"project_path": str(other), "content": PRD_BODY, "read_id": receipt["read_id"]},
                          kernel=kernel)
            self.rejected({"project_path": str(self.root / "outside"), "content": PRD_BODY,
                           "read_id": receipt["read_id"]}, kernel=kernel)
        self.assertEqual(self.snapshot(other), before_other)
        self.save_prd(PRD_BODY, receipt, project_path=str(self.project))

    def test_any_context_version_change_is_reported_without_writing(self):
        self.init()
        changes = (("project.json", lambda p: p.write_bytes(p.read_bytes() + b"\n")),
                   ("README.md", lambda p: p.write_text("changed readme", encoding="utf-8")),
                   ("docs/requirements.md", lambda p: self.write("docs/requirements.md", "concurrent")),
                   (PRD, lambda p: self.write(PRD, "concurrent PRD")))
        with self.kernel() as kernel:
            for relative, change in changes:
                with self.subTest(path=relative):
                    receipt = self.read()
                    change(self.project / relative)
                    failure = self.rejected({"content": PRD_BODY, "read_id": receipt["read_id"]}, kernel=kernel)
                    self.assertEqual(failure["changed"], [relative])
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), "concurrent PRD")

    def test_rejected_conflict_does_not_consume_reference(self):
        self.init()
        receipt = self.read()
        readme = self.project / "README.md"
        original = readme.read_bytes()
        readme.write_text("temporary change", encoding="utf-8")
        with self.kernel() as kernel:
            self.rejected({"content": PRD_BODY, "read_id": receipt["read_id"]}, kernel=kernel)
        readme.write_bytes(original)
        self.assertTrue(self.save_prd(PRD_BODY, receipt)["verified"])

    def test_kernel_receives_reference_versions_and_bound_directory(self):
        self.init()
        receipt = self.read()
        with self.kernel() as kernel:
            first = self.save_prd(PRD_BODY, receipt)
        kernel.assert_called_once_with(self.foundation, ID, PRD_BODY, "missing", "missing",
                                       expected_root=self.project, directory_name=None)
        light = self.save_light("# 需求\n第一版", self.read())
        with self.kernel() as kernel:
            self.save_prd(PRD_BODY_B, self.read())
        kernel.assert_called_once_with(self.foundation, ID, PRD_BODY_B, first["sha256"], light["sha256"],
                                       expected_root=self.project, directory_name=None)
        self.server = mcp.McpServer(self.shared(allow_initialize=True, allow_save=True))
        path = self.projects / "新的中文项目"
        self.init(path)
        receipt = self.read(project_path=str(path))
        with self.kernel() as kernel:
            self.save_prd(PRD_BODY, receipt, project_path=str(path))
        kernel.assert_called_once_with(self.foundation, receipt["project_id"], PRD_BODY, "missing", "missing",
                                       expected_root=path, directory_name=path.name)


class PrdSaveChainTests(PrdToolsBase):
    """Step 7: real temp-file save chain and post-write verification."""

    def test_first_repeat_and_consecutive_saves(self):
        self.init()
        first = self.save_prd(PRD_BODY, self.read())
        raw = (self.project / PRD).read_bytes()
        self.assertEqual(raw.decode("utf-8"), rendered(PRD_BODY))
        self.assertEqual(first["write_outcome"], "saved")
        self.assertEqual((first["sha256"], first["document"]["sha256"]), (sha(raw), sha(raw)))
        self.assertEqual((first["status"], first["approval_verified"], first["verified"]), ("Draft", False, True))
        self.assertEqual(first["source_requirements_sha256"], "missing")
        self.assertIsNone(first["history"])
        self.assertEqual((first["registered"], first["downstream_started"]), (False, False))
        self.assertEqual(first["structure"]["prd_sha256"], first["sha256"])
        self.assertTrue(first["structure"]["checked"])
        self.assertEqual((first["structure"]["status"], first["structure"]["issues"]), ("ready_for_review", []))
        before = self.tree()
        for body in (PRD_BODY, "\n\n" + PRD_BODY + "\n\n  "):
            again = self.save_prd(body, self.read())
            self.assertEqual((again["write_outcome"], again["changed"]), ("unchanged", False))
            self.assertIs(again["approval_verified"], False)
            self.assertIsNone(again["history"])
            self.assertEqual(self.tree(), before)
        second = self.save_prd(PRD_BODY_B, self.read())
        self.assertEqual(second["history"]["content"].encode("utf-8"), raw)
        self.assertEqual(second["history"]["sha256"], first["sha256"])
        self.assertEqual((self.project / f"docs/prd-history/{first['sha256']}.md").read_bytes(), raw)
        third = self.save_prd(PRD_BODY, self.read())
        self.assertEqual(third["history"]["content"], second["document"]["content"])
        self.assertEqual(third["document"]["content"].encode("utf-8"), raw)
        self.assertEqual(len(list((self.project / "docs/prd-history").iterdir())), 2)
        self.assert_no_locks()

    def test_identical_existing_history_is_reused(self):
        self.init()
        first = self.save_prd(PRD_BODY, self.read())
        raw = (self.project / PRD).read_bytes()
        self.write(f"docs/prd-history/{first['sha256']}.md", raw)
        second = self.save_prd(PRD_BODY_B, self.read())
        self.assertEqual(second["history"]["content"].encode("utf-8"), raw)
        self.assertEqual(len(list((self.project / "docs/prd-history").iterdir())), 1)

    def test_source_record_and_requirements_isolation(self):
        self.init()
        self.save_light("# 需求\n第一版", self.read())
        light = self.save_light("# 需求\n第二版", self.read())
        light_files = {key: value for key, value in self.tree().items() if "requirements" in key}
        saved = self.save_prd(PRD_BODY, self.read())
        self.assertEqual(saved["source_requirements_sha256"], light["sha256"])
        self.assertEqual(saved["document"]["content"], rendered(PRD_BODY, light["sha256"]))
        self.assertEqual({key: value for key, value in self.tree().items() if "requirements" in key}, light_files)

    def test_input_change_during_save_is_not_reported_as_verified(self):
        self.init()
        receipt = self.read()
        original = mcp.requirements.save_prd_draft

        def save(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.project / "README.md").write_text("changed during save", encoding="utf-8")
            return result

        with mock.patch.object(mcp.requirements, "save_prd_draft", side_effect=save) as kernel:
            failure = self.save_prd(PRD_BODY, receipt, error=True)
        self.assertEqual(kernel.call_count, 1)
        self.assertEqual((failure["write_outcome"], failure["failed_check"]), ("saved_unverified", "inputs"))
        self.assertEqual(failure["changed"], ["README.md"])
        self.assertEqual(failure["save_result"]["sha256"], sha((self.project / PRD).read_bytes()))

    def test_target_changed_after_save_is_detected_and_preserved(self):
        self.init()
        receipt = self.read()
        original = mcp.requirements.save_prd_draft

        def save(*args, **kwargs):
            result = original(*args, **kwargs)
            self.write(PRD, "external edit")
            return result

        with mock.patch.object(mcp.requirements, "save_prd_draft", side_effect=save) as kernel:
            failure = self.save_prd(PRD_BODY, receipt, error=True)
        self.assertEqual(kernel.call_count, 1)
        self.assertEqual((failure["write_outcome"], failure["failed_check"]), ("saved_unverified", "document"))
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), "external edit")

    def test_structure_result_is_bound_to_the_saved_version(self):
        self.init()
        problem = self.save_prd("# 只有标题的 PRD", self.read())
        self.assertEqual((problem["write_outcome"], problem["verified"]), ("saved", True))
        self.assertEqual(problem["structure"]["status"], "attention_required")
        self.assertIn("prd_sections_missing", {issue["code"] for issue in problem["structure"]["issues"]})
        other = {"prd": {"sha256": "0" * 64, "req_ids": [], "ac_ids": []}, "status": "ready_for_review",
                 "issues": []}
        with mock.patch.object(mcp.requirements, "inspect_prd", return_value=other):
            saved = self.save_prd(PRD_BODY, self.read())
        self.assertTrue(saved["verified"])
        self.assertEqual(saved["structure"], {"checked": False, "observed_sha256": "0" * 64})


class PrdSaveFailureTests(PrdToolsBase):
    """Step 8: failure classification and read reference consumption."""

    def test_kernel_exception_before_write_is_unknown_and_consumes_reference(self):
        self.init()
        receipt = self.read()
        before = self.tree()
        with mock.patch.object(mcp.requirements, "save_prd_draft", side_effect=OSError("disk unavailable")):
            failure = self.save_prd(PRD_BODY, receipt, error=True)
        self.assertEqual(failure["write_outcome"], "unknown")
        self.assertIn("勿盲目重试", failure["next_action"])
        self.assertEqual(self.tree(), before)
        again = self.save_prd(PRD_BODY, receipt, error=True)
        self.assertEqual(again["write_outcome"], "not_written")
        self.call(mcp.SAVE_DRAFT, {"content": "# 需求", "read_id": receipt["read_id"]}, error=True)
        self.assertEqual(self.tree(), before)

    def test_kernel_exception_after_write_is_not_reported_as_unsaved(self):
        self.init()
        receipt = self.read()
        original = mcp.requirements.save_prd_draft

        def save(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("lost response")

        with mock.patch.object(mcp.requirements, "save_prd_draft", side_effect=save) as kernel:
            failure = self.save_prd(PRD_BODY, receipt, error=True)
        self.assertEqual(kernel.call_count, 1)
        self.assertEqual(failure["write_outcome"], "unknown")
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), rendered(PRD_BODY))
        self.assert_no_locks()

    def test_history_conflict_keeps_conflicting_history_and_current_prd(self):
        self.init()
        first = self.save_prd(PRD_BODY, self.read())
        current = (self.project / PRD).read_bytes()
        conflict = self.write(f"docs/prd-history/{first['sha256']}.md", "conflicting history")
        failure = self.save_prd(PRD_BODY_B, self.read(), error=True)
        self.assertEqual(failure["write_outcome"], "unknown")
        self.assertIn("PRD 历史版本冲突", failure["error"])
        self.assertEqual(conflict.read_text(encoding="utf-8"), "conflicting history")
        self.assertEqual((self.project / PRD).read_bytes(), current)
        self.assert_no_locks()

    def readback_failure(self, failing_prefix, receipt):
        original_save, original_read = mcp.requirements.save_prd_draft, mcp.requirements.read_document
        wrote = False

        def save(*args, **kwargs):
            nonlocal wrote
            result = original_save(*args, **kwargs)
            wrote = True
            return result

        def read(root, relative):
            if wrote and relative.startswith(failing_prefix):
                raise OSError("readback unavailable")
            return original_read(root, relative)

        with mock.patch.object(mcp.requirements, "save_prd_draft", side_effect=save) as kernel:
            with mock.patch.object(mcp.requirements, "read_document", side_effect=read):
                failure = self.save_prd(PRD_BODY_B if failing_prefix != PRD else PRD_BODY, receipt, error=True)
        self.assertEqual(kernel.call_count, 1)
        self.assertEqual(failure["write_outcome"], "saved_unverified")
        self.assertIn("勿重复写入", failure["next_action"])
        self.assert_no_locks()
        return failure

    def test_document_and_history_readback_failures_are_saved_unverified(self):
        self.init()
        failure = self.readback_failure(PRD, self.read())
        self.assertEqual(failure["failed_check"], "document")
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), rendered(PRD_BODY))
        first_sha = failure["save_result"]["sha256"]
        failure = self.readback_failure("docs/prd-history/", self.read())
        self.assertEqual(failure["failed_check"], "history")
        self.assertTrue((self.project / f"docs/prd-history/{first_sha}.md").is_file())
        self.assertEqual((self.project / PRD).read_text(encoding="utf-8"), rendered(PRD_BODY_B))

    def test_structure_check_exception_keeps_verified_save(self):
        self.init()
        with mock.patch.object(mcp.requirements, "inspect_prd", side_effect=OSError("inspection unavailable")):
            saved = self.save_prd(PRD_BODY, self.read())
        self.assertEqual((saved["write_outcome"], saved["verified"]), ("saved", True))
        self.assertEqual(saved["structure"], {"checked": False, "error": "inspection unavailable"})

    def test_reference_consumed_by_either_save_tool_cannot_be_reused(self):
        self.init()
        receipt = self.read()
        self.save_light("# 需求", receipt)
        self.assertEqual(self.save_prd(PRD_BODY, receipt, error=True)["write_outcome"], "not_written")
        receipt = self.read()
        self.save_prd(PRD_BODY, receipt)
        self.call(mcp.SAVE_DRAFT, {"content": "# 需求 2", "read_id": receipt["read_id"]}, error=True)
        self.assertEqual(self.save_prd(PRD_BODY_B, receipt, error=True)["write_outcome"], "not_written")


class PrdCompatibilityTests(PrdToolsBase):
    """Process-level entry and the original kernel command line."""

    def test_shared_stdio_process_routes_prd_tools(self):
        command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "cursor_mcp.py"), "--foundation",
                   str(self.foundation), "--allow-initialize", "--allow-save"]
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        path = self.projects / "stdio-prd"

        def send(method, params=None):
            message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": self.meta()}}
            child.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
            child.stdin.flush()
            self.assertTrue(select.select([child.stdout], [], [], 5)[0], "MCP response timed out")
            response = json.loads(child.stdout.readline())
            self.assertNotIn("error", response, response)
            return response["result"]

        def tool(tool_name, **arguments):
            result = send("tools/call", {"name": tool_name,
                                         "arguments": {"project_path": str(path), **arguments}})
            self.assertFalse(result["isError"], result)
            return json.loads(result["content"][0]["text"])

        names = {item["name"] for item in send("tools/list")["tools"]}
        self.assertTrue({mcp.INSPECT_PRD, mcp.SAVE_PRD_DRAFT, mcp.SAVE_DRAFT} <= names)
        tool(mcp.PROJECT_INITIALIZE, name="stdio", purpose="test")
        first = tool(mcp.SAVE_PRD_DRAFT, content=PRD_BODY, read_id=tool(mcp.READ_CONTEXT)["read_id"])
        tool(mcp.SAVE_PRD_DRAFT, content=PRD_BODY_B, read_id=tool(mcp.READ_CONTEXT)["read_id"])
        self.assertEqual(tool(mcp.INSPECT_PRD)["status"], "ready_for_review")
        history = tool(mcp.READ_CONTEXT, prd_history_sha256=first["sha256"])["prd_history"]
        self.assertEqual(history["content"], first["document"]["content"])
        child.stdin.close()
        self.assertEqual(child.wait(timeout=5), 0)
        self.assertEqual(child.stderr.read(), b"")
        child.stdout.close()
        child.stderr.close()

    def test_original_kernel_command_line_is_unchanged(self):
        self.init()
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        script = mcp.requirements.__file__

        def run(*arguments, body=None):
            return subprocess.run([sys.executable, "-B", script, "--foundation", str(self.foundation), *arguments],
                                  input=body, capture_output=True, text=True, env=environment)

        saved = run("save-prd-draft", ID, "--expected-prd-sha", "missing", "--expected-requirements-sha",
                    "missing", "--apply", body=PRD_BODY)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        inspected = run("inspect-prd", ID)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["prd"]["sha256"], json.loads(saved.stdout)["sha256"])


if __name__ == "__main__":
    unittest.main()
