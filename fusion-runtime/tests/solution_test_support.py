"""Disposable filesystem and MCP support for Solution Designer tests."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
SOLUTION_SOURCE = RUNTIME_ROOT / "workflows/Solution Designer"
REQUIREMENTS_SOURCE = RUNTIME_ROOT / "workflows/requirements"
CONFIRMATION_ID = "C-" + "a" * 20
SOLUTION_PURPOSE = "形成技术方案"
START_MARKER = "<!-- buzz-develop-helper:confirmations:start -->"
END_MARKER = "<!-- buzz-develop-helper:confirmations:end -->"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_module(unique_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


class SolutionFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="solution-designer-tools-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.install = self.root / "install/fusion-runtime/workflows"
        self.foundation = self.install / "requirements"
        self.solution = self.install / "Solution Designer"
        self.upstream = self.root / "install/Develop_Helper"
        self.projects = self.root / "business"
        self.outside = self.root / "outside"
        self.client_config = self.root / "client/mcp.json"
        for path in (self.install, self.projects, self.outside, self.client_config.parent):
            path.mkdir(parents=True)
        ignore = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc")
        shutil.copytree(REQUIREMENTS_SOURCE, self.foundation,
                        ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", "methods"))
        shutil.copytree(SOLUTION_SOURCE, self.solution,
                        ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc",
                                                      "methods", "research-template.md"))
        self.create_upstream()
        self.project_a = self.projects / "meeting-helper"
        self.project_b = self.projects / "会议助手"
        self.config = {
            "schema_version": 1,
            "upstream_root": str(self.upstream),
            "projects_root": str(self.projects),
            "project_directories": {"meeting-b": self.project_b.name},
        }
        self.write_config()
        self.init_project(self.project_a, "meeting-helper")
        self.init_project(self.project_b, "meeting-b")
        solution_path = str(SOLUTION_SOURCE)
        if solution_path not in sys.path:
            sys.path.insert(0, solution_path)
        installed_path = str(self.solution)
        if installed_path not in sys.path:
            sys.path.insert(0, installed_path)
        self.now = 0
        self.server = None

    def create_upstream(self):
        spec_dir = self.upstream / "harness-core/specification/default"
        spec_dir.mkdir(parents=True)
        (spec_dir / "backend.md").write_text("# 默认规范\n\n仅用于隔离测试。\n", encoding="utf-8")
        reference = self.upstream / "harness-core/skills/sdd-product-design/references"
        reference.mkdir(parents=True)
        (reference / "research-template.md").write_text("# Research\n", encoding="utf-8")
        for base in (self.foundation, self.solution):
            link = base / "methods/develop-helper"
            link.parent.mkdir(exist_ok=True)
            link.symlink_to(self.upstream, target_is_directory=True)
        research = self.solution / "templates/research-template.md"
        research.symlink_to("../methods/develop-helper/harness-core/skills/sdd-product-design/"
                            "references/research-template.md")
        foundation_check = load_module(
            f"foundation_check_{id(self)}",
            self.foundation / "file_tools/check_foundation.py",
        )
        (self.foundation / "upstream-lock.json").write_text(
            json.dumps(foundation_check.snapshot(self.upstream)), encoding="utf-8"
        )

    def write_config(self):
        path = self.foundation / "config/local.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.config), encoding="utf-8")

    def spare_fixture(self):
        """A second isolated fixture; its temp root is cleaned with the owner test."""
        fixture = SolutionFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def relock_upstream(self):
        foundation_check = load_module(
            f"foundation_check_relock_{id(self)}",
            self.foundation / "file_tools/check_foundation.py",
        )
        (self.foundation / "upstream-lock.json").write_text(
            json.dumps(foundation_check.snapshot(self.upstream)), encoding="utf-8"
        )

    def add_budget_members(self, count=510):
        members = [f"docs/budget/m{index:04d}.md" for index in range(count)]
        for relative in members:
            path = self.project_a / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        manifest = {"schema_version": 1, "entrypoint": members[0],
                    "files": [{"path": relative} for relative in members]}
        manifest_path = "docs/registries/budget-file-set.json"
        self.write(self.project_a, manifest_path, json.dumps(manifest, ensure_ascii=False))
        data = json.loads((self.project_a / "project.json").read_text(encoding="utf-8"))
        registry = data.setdefault("artifact_registry", {
            "schema_version": 1, "confirmations_path": "docs/decisions.md",
            "handoffs_directory": "docs/handoffs", "entries": {}})
        registry.setdefault("entries", {})["budget"] = {
            "artifact_id": "budget", "kind": "solution", "current_version": "v1",
            "versions": [{"version": "v1",
                          "content": {"type": "file-set", "manifest": {"path": manifest_path}},
                          "confirmation_ids": [], "producer_role": "main", "purpose": "预算探针",
                          "summary": "budget", "document_status": "Draft", "open_items": [],
                          "availability": {"scope": "local-only", "git_commit": None},
                          "registration": {"actor": {"role": "main", "principal_id": "fixture",
                                                      "authority": "test"},
                                           "recorded_at": "2026-10-29T00:00:00Z"}}]}
        (self.project_a / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return members

    def init_project(self, path: Path, project_id: str, specification=...):
        path.mkdir(parents=True, exist_ok=True)
        (path / "README.md").write_text(f"# {project_id}\n", encoding="utf-8")
        (path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        steps = {
            name: {"status": "skipped", "detail": "隔离测试项目，不执行外部动作"}
            if name in {"local_git", "github_repository", "remote_link", "initial_commit", "initial_push"}
            else {"status": "succeeded"}
            for name in (
                "local_files", "local_git", "github_repository", "remote_link",
                "initial_commit", "initial_push", "buzz_mapping", "shared_read"
            )
        }
        data = {
            "schema_version": 1,
            "project_id": project_id,
            "name": path.name,
            "purpose": "Solution Designer 隔离测试",
            "initialization": steps,
        }
        if specification is not ...:
            data["specification"] = specification
        (path / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        (path / "docs").mkdir(exist_ok=True)

    def connect(self, *, allow_save=False, project=None):
        for module_name in ("shared_loader", "file_tools", "file_tools.solution",
                            "file_tools.dependencies"):
            sys.modules.pop(module_name, None)
        mcp = load_module(f"solution_mcp_{id(self)}_{allow_save}", self.solution / "mcp_server.py")
        runtime = mcp.load_shared(self.foundation)
        tools = mcp.SolutionTools(runtime, allow_save=allow_save, clock=lambda: self.now)
        self.server = mcp.McpServer(tools, runtime=runtime)
        self.mcp = mcp
        return self.server

    def rpc(self, method, params=None):
        message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        return self.server.handle(message)

    def initialize(self):
        return self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})

    def list_tools(self):
        return self.rpc("tools/list")["result"]["tools"]

    def call(self, name, arguments, *, error=False):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments})
        self.assertNotIn("error", response, response)
        result = response["result"]
        self.assertEqual(result["isError"], error, result)
        return json.loads(result["content"][0]["text"])

    def read_context(self, project=None, **arguments):
        project = project or self.project_a
        return self.call(self.mcp.READ_CONTEXT, {"project_path": str(project), **arguments})

    def inspect_candidate(self, content, profile="Lite", project=None):
        project = project or self.project_a
        return self.call(self.mcp.INSPECT, {"project_path": str(project), "target": "candidate",
                                            "content": content, "profile": profile})

    def write(self, project: Path, relative: str, content: str) -> str:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return sha(path.read_bytes())

    def requirements_body(self):
        return "# 源需求\n\n- REQ-001：用户发起会议。\n- REQ-002：失败时给出反馈。\n"

    def prd_body(self):
        return """# PRD

## 用户结果与成功指标

### REQ-001
用户可以发起会议。

### AC-001
- 结果类型：成功
- 前置条件：已登录
- 操作：提交会议信息
- 可观察结果：会议创建
- 验证方式：看到会议详情

### AC-002
- 结果类型：失败
- 前置条件：网络不可用
- 操作：提交会议信息
- 可观察结果：显示失败
- 验证方式：错误提示可见

### REQ-002
系统反馈失败。

### AC-003
- 结果类型：成功
- 前置条件：服务拒绝
- 操作：提交会议信息
- 可观察结果：展示可重试错误
- 验证方式：重试入口可见

## 具体案例

用户在手机和网页上创建会议。

## 范围与边界

包含会议创建，不包含付费。

## REQ 与 AC

REQ-001 包含 AC-001、AC-002；REQ-002 包含 AC-003。

## 业务流程图

```mermaid
flowchart TD
  A --> B
```

## 业务时序图

```mermaid
sequenceDiagram
  participant U
  U->>S: create
```

## 事实、假设与待决事项

- 事实：离线夹具。
- 假设：无外部支付。

## 变更摘要

首版 PRD。
"""

    def write_requirements_and_prd(self, project=None, requirements_text=None, prd_text=None):
        project = project or self.project_a
        requirements_text = requirements_text or self.requirements_body()
        req_sha = self.write(project, "docs/requirements.md", requirements_text)
        prd_text = prd_text or self.prd_body()
        raw = (
            "---\nartifact_kind: prd\nstatus: Draft\napproval_verified: false\n"
            "source_requirements_path: docs/requirements.md\n"
            f"source_requirements_sha256: {req_sha}\n---\n\n{prd_text}"
        )
        prd_sha = self.write(project, "docs/PRD.md", raw)
        return req_sha, prd_sha

    def add_g1_file_set(self, project=None, *, tamper_after=False):
        project = project or self.project_a
        member = "docs/research/g1-note.md"
        self.write(project, member, "# G1 成员\n")
        member_raw = (project / member).read_bytes()
        manifest = {
            "schema_version": 1,
            "entrypoint": member,
            "files": [{"path": member, "sha256": sha(member_raw)}],
        }
        manifest_path = "docs/registries/g1-file-set.json"
        self.write(project, manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        data = json.loads((project / "project.json").read_text(encoding="utf-8"))
        registry = data.setdefault("artifact_registry", {
            "schema_version": 1, "confirmations_path": "docs/decisions.md",
            "handoffs_directory": "docs/handoffs", "entries": {}})
        registry["entries"]["g1"] = {
            "artifact_id": "g1", "kind": "solution", "current_version": "v1",
            "versions": [{
                "version": "v1",
                "content": {"type": "file-set",
                            "manifest": {"type": "file-set",
                                         "manifest": {"sha256": sha((project / manifest_path).read_bytes()),
                                                      "path": manifest_path, "files": manifest["files"]},
                                         "entrypoint": member, "files": manifest["files"]}},
                "confirmation_ids": [], "producer_role": "main", "purpose": "其他登记",
                "summary": "G1", "document_status": "Draft", "open_items": [],
                "availability": {"scope": "local-only", "git_commit": None},
                "registration": {"actor": {"role": "main", "principal_id": "fixture", "authority": "test"},
                                 "recorded_at": "2026-10-29T00:00:00Z"},
            }]}
        (project / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        if tamper_after:
            self.write(project, member, "# G1 成员被修改\n")
        return manifest_path, member

    def confirm_prd(self, project=None, project_id=None, *, purpose=SOLUTION_PURPOSE,
                    open_items=(), tamper_snapshot=False):
        project = project or self.project_a
        project_id = project_id or json.loads((project / "project.json").read_text())["project_id"]
        prd_raw = (project / "docs/PRD.md").read_bytes()
        snapshot_relative = f"docs/confirmations/snapshots/{sha(prd_raw)}/PRD.md"
        snapshot = project / snapshot_relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(prd_raw + (b"tampered" if tamper_snapshot else b""))
        data = json.loads((project / "project.json").read_text(encoding="utf-8"))
        registry = data.setdefault("artifact_registry", {
            "schema_version": 1, "confirmations_path": "docs/decisions.md",
            "handoffs_directory": "docs/handoffs", "entries": {}})
        registry["entries"]["prd"] = {
            "artifact_id": "prd", "kind": "requirements", "current_version": "v1",
            "versions": [{
                "version": "v1",
                "content": {"type": "file", "path": snapshot_relative,
                            "sha256": sha(snapshot.read_bytes()), "size": snapshot.stat().st_size},
                "confirmation_ids": [CONFIRMATION_ID], "producer_role": "requirements",
                "purpose": "PRD", "summary": "PRD v1", "document_status": "Draft",
                "open_items": list(open_items),
                "availability": {"scope": "local-only", "git_commit": None},
                "registration": {"actor": {"role": "main", "principal_id": "fixture", "authority": "test"},
                                 "recorded_at": "2026-10-29T00:00:00Z"}}]}
        (project / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        record = {
            "schema_version": 1, "confirmation_id": CONFIRMATION_ID, "status": "active",
            "project_id": project_id,
            "artifact": {"artifact_id": "prd", "kind": "requirements", "version": "v1",
                         "content_sha256": sha(prd_raw), "registered_path": "docs/PRD.md"},
            "snapshot": {"type": "file", "path": snapshot_relative, "sha256": sha(prd_raw)},
            "permitted_use": purpose, "confirmed_scope": "形成技术方案", "non_authorizations": [],
            "open_items": list(open_items),
            "evidence": {"type": "current-session", "provider": "buzz", "authority": "test",
                         "user_principal_id": "bowen", "session_id": "offline-fixture",
                         "message_id": "offline-fixture", "confirmed_at": "2026-10-29T00:00:00Z",
                         "statement": "离线夹具确认 PRD", "runtime_authenticated": True},
            "recorded_by": {"principal_id": "fixture", "authority": "test"},
            "recorded_at": "2026-10-29T00:00:00Z",
        }
        block = json.dumps({"schema_version": 1, "confirmations": [record]}, ensure_ascii=False, indent=2)
        self.write(project, "docs/decisions.md",
                   f"# 项目确认记录\n\n{START_MARKER}\n```json\n{block}\n```\n{END_MARKER}\n")
        return sha(prd_raw)

    def tech_spec(self, title="首版方案"):
        rows = "\n".join(
            f"| REQ-00{1 if ac in {'AC-001','AC-002'} else 2} | {ac} | {title}设计 | 成功路径 | 失败路径 | 验证 | covered |"
            for ac in ("AC-001", "AC-002", "AC-003")
        )
        return f"""# {title}

## 0. 基线与用途

- 项目与本次范围：会议创建。
- 读者和建议确认用途：形成技术方案。
- 输入材料、版本与状态：当前 PRD。
- 工程配置及选择理由：本地 stdio。
- 明确不覆盖：支付。

## 1. 用户结果与覆盖范围

围绕 REQ-001、REQ-002 描述用户输入 → 系统处理 → 用户结果，包含成功和失败。

## 2. 系统边界与接口

Lite 无网络接口，使用本地命令模块边界；真实命令从输入到输出可追踪。

## 3. 数据与生命周期

会议字段为字符串，Draft 数据只保存在临时项目，不使用真实敏感数据。

## 4. 模型、提示词与工具

无 AI，本方案不适用模型、提示词或外部工具。

## 5. 算法、状态与体验影响

处理步骤为校验 → 创建 → 返回；重复请求保持幂等，失败时停止并提示。

## 6. 异常、重试与恢复

校验失败 → 错误状态 → 用户看到提示 → 修改后重试 → 清理临时资源。

## 7. 目录、运行与验证条件

目录包含 mcp_server.py 和 file_tools；运行只依赖标准库与受信 requirements；无付费授权。

## 8. 技术时序

用户 → 工具 → 文件存储 → 复读结果 → 用户；失败路径为工具 → 错误提示。

## 9. 依据、假设与可行性

| 结论 | 类型：项目事实/外部事实/假设/建议/未知 | 来源 | 可行性：verified/reasoned/unknown/blocked | 影响 |
| --- | --- | --- | --- | --- |
| 离线夹具可验证文件行为 | 项目事实 | 临时 PRD | verified | 限定结论 |

## 10. 取舍与未决项

### 已决定

首版只做本地 Draft。

### 待决定

真实客户端配置留待步骤 8。

### 暂不阻塞

模型效果不纳入本地工具验收。

## 11. REQ/AC 覆盖表

| REQ | AC | 实现设计/API | 成功路径 | 失败路径 | 验证方式 | 状态：covered/not_applicable/open/blocked |
| --- | --- | --- | --- | --- | --- | --- |
{rows}

## 12. 变更摘要与建议下一步

- 相对上一版的变化：{title}。
- 影响的需求/UI/任务：REQ-001、REQ-002。
- 建议 Main 确认的版本与用途：当前 Draft 仅供评审。
- 未获授权的动作：不启动下游。
"""

    def save(self, read, content=None, profile="Lite", *, error=False):
        content = content or self.tech_spec()
        return self.call(self.mcp.SAVE_DRAFT, {
            "project_path": str(self.project_a), "read_id": read["read_receipt"]["read_id"],
            "content": content, "profile": profile,
        }, error=error)

    def stdio(self, *arguments, input_messages=(), allow_save=True):
        command = [sys.executable, "-B", str(self.solution / "mcp_server.py"),
                   "--foundation", str(self.foundation)]
        if allow_save:
            command.append("--allow-save")
        command.extend(arguments)
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)

        def send(message):
            child.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
            child.stdin.flush()
            self.assertTrue(select.select([child.stdout], [], [], 5)[0], "stdio 响应超时")
            return json.loads(child.stdout.readline())

        initialize_response = send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
        child.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()
        responses = [initialize_response]
        for index, message in enumerate(input_messages, start=2):
            responses.append(send({"jsonrpc": "2.0", "id": index, **message}))
        child.stdin.close()
        self.assertEqual(child.wait(timeout=5), 0, child.stderr.read().decode("utf-8"))
        child.stdout.close()
        child.stderr.close()
        return responses

    def stdio_workflow(self, steps, *, allow_save=True):
        command = [sys.executable, "-B", str(self.solution / "mcp_server.py"),
                   "--foundation", str(self.foundation)]
        if allow_save:
            command.append("--allow-save")
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)

        def send(method, params=None, identifier=1):
            child.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method,
                                          "params": params or {}}, ensure_ascii=False).encode() + b"\n")
            child.stdin.flush()
            self.assertTrue(select.select([child.stdout], [], [], 5)[0], "stdio 响应超时")
            return json.loads(child.stdout.readline())

        send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        child.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()
        results = []
        for index, (name, arguments) in enumerate(steps, start=2):
            if callable(arguments):
                arguments = arguments(results[-1] if results else None)
            response = send("tools/call", {"name": name, "arguments": arguments}, index)
            result = json.loads(response["result"]["content"][0]["text"])
            results.append(result)
        child.stdin.close()
        self.assertEqual(child.wait(timeout=5), 0, child.stderr.read().decode("utf-8"))
        child.stdout.close()
        child.stderr.close()
        return results
