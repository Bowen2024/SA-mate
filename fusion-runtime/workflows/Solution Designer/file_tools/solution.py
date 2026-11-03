"""Solution Designer read, inspect and controlled draft-save kernel."""

from __future__ import annotations

from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

from shared_loader import CONTRACT_VERSION, FoundationError, verify_runtime_baseline
from file_tools.dependencies import (
    CORE_DOCUMENTS,
    TARGET_PATH,
    canonical_sha,
    collect,
    digest,
    safe_project_path,
    bind_project,
)


READ_TTL_SECONDS = 900
MAX_READS = 64
PROFILES = ("Lite", "Standard", "AI")
SOLUTION_PURPOSE = "形成技术方案"
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"\b(REQ|AC)-\d{3,}\b")


class ToolError(RuntimeError):
    def __init__(self, code, message, *, next_action="修正输入后重试；写入冲突请先重新读取。", **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_action = next_action
        self.details = details


def _read_bytes(root: Path, relative: str, limit: int):
    try:
        path = safe_project_path(root, relative)
    except ValueError as error:
        return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": None,
                "content": None, "error": f"unsafe_file:{error}"}
    try:
        if not path.exists():
            return {"path": relative, "status": "missing", "sha256": "missing",
                    "size_bytes": 0, "content": None}
        if not path.is_file() or path.stat().st_nlink != 1:
            return {"path": relative, "status": "unreadable", "sha256": None,
                    "size_bytes": None, "content": None}
        raw = path.read_bytes()
    except OSError as error:
        return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": None,
                "content": None, "error": str(error)}
    if len(raw) > limit:
        return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": len(raw),
                "content": None, "error": "file_too_large"}
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": relative, "status": "unreadable", "sha256": None, "size_bytes": len(raw),
                "content": None, "error": "invalid_utf8"}
    status = "present"
    error = None
    if content == "":
        status = "present"
    return {"path": relative, "status": status, "sha256": digest(raw), "size_bytes": len(raw),
            "content": content, "error": error}


def parse_front_matter(content: str | None):
    if not content:
        return None, content or ""
    match = FRONT_MATTER.match(content)
    if match is None:
        return None, content
    values = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values, content[match.end():]


def _front_matter_value(raw_values, key):
    if not isinstance(raw_values, dict) or key not in raw_values:
        return False, None
    value = raw_values[key]
    if value in {"null", "~"}:
        return True, None
    try:
        return True, json.loads(value)
    except json.JSONDecodeError:
        return True, value.strip().strip('"\'')


def split_table_row(line: str) -> list[str]:
    cells = []
    current = []
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def strip_fenced_lines(content: str) -> list[str]:
    lines = content.splitlines()
    output = []
    inside = False
    for line in lines:
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            output.append(line)
    return output


def inspect_tech_spec(*, content: str, profile: str, prd_content: str, prd_sha256: str,
                      current_header: dict | None = None, is_current: bool = False) -> dict:
    issues = []

    def add(code, message, section=None, line=None, related_ids=None, severity="error"):
        issues.append({"code": code, "severity": severity, "message": message, "section": section,
                       "line": line, "related_ids": related_ids or []})

    expected = [
        "基线与用途", "用户结果与覆盖范围", "系统边界与接口", "数据与生命周期", "模型、提示词与工具",
        "算法、状态与体验影响", "异常、重试与恢复", "目录、运行与验证条件", "技术时序",
        "依据、假设与可行性", "取舍与未决项", "REQ/AC 覆盖表", "变更摘要与建议下一步",
    ]
    headings = {}
    for line_number, line_text in enumerate(content.splitlines(), start=1):
        match = re.match(r"^##\s+(\d+)\.\s*(.+?)\s*$", line_text)
        if match:
            number = int(match.group(1))
            title = match.group(2)
            if number < len(expected) and title != expected[number]:
                add("section_title_mismatch", f"第 {number} 节标题不符合统一模板", number, line_text)
            headings[number] = {"title": title, "line": line_text}
    for number, title in enumerate(expected):
        if number not in headings:
            add("section_missing", f"缺少第 {number} 节：{title}", number)
    duplicate_sections = re.findall(r"(?m)^##\s+(\d+)\.", content)
    for number in sorted({number for number in duplicate_sections if duplicate_sections.count(number) > 1},
                         key=int):
        add("section_duplicated", f"第 {number} 节重复", int(number))

    prd_requirements = OrderedDict()
    current_req = None
    ac_owner = {}
    for line_text in prd_content.splitlines():
        req_match = re.search(r"\bREQ-\d{3,}\b", line_text)
        if req_match and line_text.lstrip().startswith("#"):
            current_req = req_match.group(0)
            prd_requirements.setdefault(current_req, set())
        ac_match = re.search(r"\bAC-\d{3,}\b", line_text)
        if ac_match and line_text.lstrip().startswith("#"):
            if current_req is None:
                add("acceptance_without_requirement", "AC 缺少所属 REQ", 11, related_ids=[ac_match.group(0)])
            else:
                prd_requirements.setdefault(current_req, set()).add(ac_match.group(0))
                ac_owner[ac_match.group(0)] = current_req
    if not prd_requirements:
        add("prd_requirements_missing", "PRD 中未找到 REQ 定义", 11)

    lines = strip_fenced_lines(content)
    section = None
    table_rows = []
    for line_number, line_text in enumerate(lines, start=1):
        heading = re.match(r"^##\s+(\d+)\.", line_text)
        if heading:
            section = int(heading.group(1))
        if section == 11 and line_text.strip().startswith("|"):
            cells = split_table_row(line_text)
            if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            if cells and cells[0] in {"REQ", "---"}:
                if len(cells) != 7:
                    add("coverage_header_invalid", "覆盖表必须包含七列", 11, line_number)
                continue
            table_rows.append((line_number, cells))

    covered_ac = {}
    for line_number, cells in table_rows:
        if len(cells) != 7:
            add("coverage_row_invalid", "覆盖表每行必须是七列", 11, line_number)
            continue
        req_id, ac_text, design, success, failure, verification, status = (cell.strip() for cell in cells)
        req_ids = sorted(set(ID_PATTERN.findall_iter(req_id)[0] if False else re.findall(r"\bREQ-\d{3,}\b", req_id)))
        ac_ids = re.findall(r"\bAC-\d{3,}\b", ac_text)
        if len(req_ids) != 1:
            add("coverage_requirement_invalid", "覆盖行必须明确归属一个 REQ", 11, line_number)
            continue
        req_id = req_ids[0]
        if req_id not in prd_requirements:
            add("coverage_requirement_unknown", "覆盖表引用了 PRD 中不存在的 REQ", 11, line_number, [req_id])
        if len(ac_ids) != 1:
            add("coverage_ac_count_invalid", "每行只能覆盖一个 AC", 11, line_number, ac_ids)
            continue
        ac_id = ac_ids[0]
        if ac_id not in ac_owner:
            add("coverage_ac_unknown", "覆盖表引用了 PRD 中不存在的 AC", 11, line_number, [ac_id])
        elif ac_owner[ac_id] != req_id:
            add("coverage_ac_owner_mismatch", "AC 所属 REQ 不匹配", 11, line_number, [req_id, ac_id])
        if ac_id in covered_ac:
            add("coverage_ac_duplicated", "同一 AC 重复出现在覆盖表，应合并设计位置", 11, line_number, [ac_id])
        covered_ac[ac_id] = status
        if status not in {"covered", "not_applicable", "open", "blocked"}:
            add("coverage_status_invalid", "覆盖状态必须是 covered、not_applicable、open 或 blocked",
                11, line_number, [ac_id])
        if status == "covered" and not all((design, success, failure, verification)):
            add("coverage_details_missing", "covered 行必须填写设计、成功、失败和验证方式",
                11, line_number, [ac_id])
        if status == "not_applicable" and not (design or failure):
            add("coverage_reason_missing", "not_applicable 必须写明显式理由", 11, line_number, [ac_id])
    for req_id, ac_ids in prd_requirements.items():
        for ac_id in sorted(ac_ids):
            if ac_id not in covered_ac:
                add("coverage_ac_missing", "PRD AC 未出现在覆盖表", 11, related_ids=[ac_id])

    section4 = content.split("## 4.", 1)[1].split("## 5.", 1)[0] if "## 4." in content else ""
    if profile == "AI":
        for keyword in ("模型", "提示词", "输出", "工具", "评估", "回退"):
            if keyword not in section4:
                add("ai_section_incomplete", f"AI 方案第 4 节必须说明{keyword}", 4)
    elif "不适用" not in section4 and "无 AI" not in section4:
        add("non_ai_section_incomplete", "非 AI 方案应明确说明模型能力不适用及原因", 4)
    section8 = content.split("## 8.", 1)[1].split("## 9.", 1)[0] if "## 8." in content else ""
    if "→" not in section8 and "->" not in section8 and "sequenceDiagram" not in section8:
        add("technical_sequence_missing", "第 8 节必须描述可跟进的技术时序", 8)

    if is_current:
        if not current_header:
            add("managed_header_missing", "已保存方案缺少受管 front matter", 0)
        else:
            if current_header.get("artifact_kind") != "tech-spec" or current_header.get("status") != "Draft":
                add("managed_header_invalid", "受管头必须保持 artifact_kind=tech-spec、status=Draft", 0)
            if current_header.get("approval_verified", "").lower() == "true":
                add("managed_header_invalid", "approval_verified 必须为 false", 0)
            recorded_prd = current_header.get("prd_sha256")
            if recorded_prd != prd_sha256:
                add("managed_prd_binding_mismatch", "已保存方案绑定的 PRD 摘要不是当前版本", 0,
                    related_ids=[recorded_prd, prd_sha256])

    counts = {"requirements": len(prd_requirements), "acceptance_criteria": len(ac_owner),
              "coverage_rows": len(table_rows), "covered": sum(value == "covered" for value in covered_ac.values()),
              "open": sum(value == "open" for value in covered_ac.values()),
              "blocked": sum(value == "blocked" for value in covered_ac.values()),
              "not_applicable": sum(value == "not_applicable" for value in covered_ac.values())}
    return {
        "status": "pass" if not issues else "issues",
        "checker_version": "solution-structure-v1",
        "issues": issues,
        "coverage": {"counts": counts, "uncovered_acceptance_ids": sorted(set(ac_owner) - set(covered_ac))},
        "limitations": {"semantic_correctness_verified": False, "diagram_rendered": False,
                        "model_evaluated": profile != "AI"},
    }


class SolutionTools:
    def __init__(self, runtime, *, allow_save=False, clock=time.monotonic):
        self.runtime = runtime
        self.allow_save = allow_save
        self.clock = clock
        self.reads = OrderedDict()

    def capabilities(self):
        return {"read": True, "inspect": True, "save": self.allow_save}

    def common(self, binding):
        return {
            "contract_version": CONTRACT_VERSION,
            "project": binding["project"],
            "capabilities": self.capabilities(),
            "atomic_snapshot": False,
            "warnings": [],
            "confirmation_written": False,
            "artifact_registered": False,
            "downstream_started": False,
        }

    def _bind(self):
        verify_runtime_baseline(self.runtime)

    def _snapshot_once(self, binding):
        modules = self.runtime.modules
        root = binding["root"]
        project_id = binding["project_id"]
        dependencies = collect(self.runtime, binding)
        documents = []
        for relative in CORE_DOCUMENTS:
            limit = 1024 * 1024 if relative == "docs/decisions.md" else 128 * 1024
            documents.append(_read_bytes(root, relative, limit))
        by_path = {item["path"]: item for item in documents}
        prd = by_path["docs/PRD.md"]
        requirements_doc = by_path["docs/requirements.md"]
        tech = by_path[TARGET_PATH]
        header, _ = parse_front_matter(tech.get("content"))
        recorded, prd_bound = _front_matter_value(header, "prd_sha256")
        tech_binding = {"recorded": recorded, "prd_sha256": prd_bound,
                        "matches_current": None if not recorded else prd_bound == prd["sha256"]}
        prd_header, _ = parse_front_matter(prd.get("content"))
        recorded_source, source_sha = _front_matter_value(prd_header, "source_requirements_sha256")
        current_source = requirements_doc["sha256"]
        if prd["status"] != "present":
            source_status = "unavailable"
        elif not recorded_source:
            source_status = "unbound"
        elif not isinstance(source_sha, str) or (source_sha != "missing" and not SHA256.match(source_sha)):
            source_status = "invalid"
        elif source_sha == "missing":
            source_status = "missing_source" if current_source == "missing" else "outdated"
        elif source_sha == current_source:
            source_status = "matched"
        else:
            source_status = "outdated"
        try:
            prd_structure = modules.requirements.inspect_prd(
                self.runtime.foundation, project_id, expected_root=root,
                directory_name=binding["directory_name"]
            )
        except (OSError, ValueError, RuntimeError) as error:
            prd_structure = {"status": "unavailable", "issues": [{"code": "prd_checker_unavailable",
                                                                 "message": str(error)}]}
        confirmation = modules.recovery.verify_prd_confirmation(
            self.runtime.foundation, root, project_id, binding["data"], prd["sha256"]
        )
        valid_ids = sorted(item["confirmation_id"] for item in confirmation.get("records", [])
                           if item.get("result") == "valid")
        return {
            "dependencies": dependencies,
            "documents": documents,
            "project_info": modules.project_info.report(binding["data"]),
            "specification": dependencies["specification"],
            "source_alignment": {
                "status": source_status,
                "bound_requirements_sha256": source_sha if recorded_source else None,
                "current_requirements_sha256": current_source,
                "reasons": [] if source_status in {"matched", "missing_source"} else [source_status],
            },
            "tech_spec_binding": tech_binding,
            "prd_structure": prd_structure,
            "confirmation": {**confirmation, "valid_confirmation_ids": valid_ids},
        }

    def _gather(self, project_path):
        binding = bind_project(self.runtime, project_path)
        first = self._snapshot_once(binding)
        second = self._snapshot_once(binding)
        changed_paths = []
        before = {item["path"]: item for item in first["dependencies"]["normalized"] if item["scope"] == "project"}
        after = {item["path"]: item for item in second["dependencies"]["normalized"] if item["scope"] == "project"}
        for path in sorted(set(before) | set(after)):
            if before.get(path) != after.get(path):
                changed_paths.append(path)
        return binding, second, changed_paths, first

    def _receipt(self, binding, snapshot, changed_paths):
        now = self.clock()
        self.reads = OrderedDict((key, item) for key, item in self.reads.items()
                                 if now - item["issued_at"] < READ_TTL_SECONDS)
        if changed_paths or snapshot["dependencies"]["diagnostics"]:
            return None, False
        while len(self.reads) >= MAX_READS:
            self.reads.popitem(last=False)
        read_id = secrets.token_urlsafe(24)
        project_items = [item for item in snapshot["dependencies"]["normalized"] if item["scope"] == "project"]
        non_target = [item for item in project_items if item["path"] != TARGET_PATH]
        docs = {item["path"]: item for item in snapshot["documents"]}
        spec = snapshot["specification"]
        self.reads[read_id] = {
            "issued_at": now,
            "project_id": binding["project_id"],
            "project_path": binding["root"],
            "dependency_set_sha256": snapshot["dependencies"]["dependency_set_sha256"],
            "non_target_set_sha256": canonical_sha(non_target),
            "target_sha256": docs[TARGET_PATH]["sha256"],
            "prd_sha256": docs["docs/PRD.md"]["sha256"],
            "requirements_sha256": docs["docs/requirements.md"]["sha256"],
            "specification_state": spec["state"],
            "specification_set_sha256": canonical_sha(spec["files"]),
            "valid_confirmation_ids": snapshot["confirmation"]["valid_confirmation_ids"],
        }
        return read_id, True

    def read_context(self, arguments):
        history_sha = arguments.get("history_sha256")
        if history_sha is not None and not SHA256.match(history_sha):
            raise ToolError("invalid_arguments", "history_sha256 必须是 64 位小写 SHA-256")
        self._bind()
        binding, snapshot, changed_paths, _ = self._gather(arguments["project_path"])
        read_id, _ = self._receipt(binding, snapshot, changed_paths)
        eligible_code, _ = self._eligibility(snapshot, changed_paths)
        read_receipt = None
        if read_id is not None:
            read_receipt = {
                "read_id": read_id,
                "valid_seconds": READ_TTL_SECONDS,
                "save_eligible_at_read": eligible_code is None,
                "ineligible_reasons": [] if eligible_code is None else [eligible_code],
            }
        result = {**self.common(binding), "operation": "solution_read_context"}
        result.update({
            "documents": snapshot["documents"],
            "project_info": snapshot["project_info"],
            "specification": {key: snapshot["specification"][key] for key in ("state", "name", "files")},
            "source_alignment": snapshot["source_alignment"],
            "tech_spec_binding": snapshot["tech_spec_binding"],
            "prd_structure": snapshot["prd_structure"],
            "confirmation": snapshot["confirmation"],
            "read_receipt": read_receipt,
            "protection": {
                "protected_versions": snapshot["dependencies"]["normalized"],
                "dependency_set_sha256": snapshot["dependencies"]["dependency_set_sha256"],
                "additional_reads": [f"docs/tech-spec-history/{history_sha}.md"] if history_sha else [],
                "atomic_snapshot": False,
                "changed_during_read": changed_paths,
                "diagnostics": snapshot["dependencies"]["diagnostics"],
            },
            "history": None,
        })
        if history_sha:
            relative = f"docs/tech-spec-history/{history_sha}.md"
            history = _read_bytes(binding["root"], relative, 128 * 1024)
            if history["status"] == "present" and history["sha256"] != history_sha:
                history = {**history, "status": "unreadable", "sha256": None, "error": "history_digest_mismatch"}
            result["history"] = history
        total_content = sum(len((item.get("content") or "").encode("utf-8")) for item in result["documents"])
        total_content += sum(len(item.get("content", "").encode("utf-8"))
                             for item in result["specification"]["files"] if item.get("content"))
        if total_content > 1024 * 1024:
            raise ToolError("content_too_large", "返回正文合计超过 1 MiB；不静默截断或分页冒充完整读取")
        return result

    def inspect(self, arguments):
        self._bind()
        target = arguments["target"]
        binding, snapshot, changed_paths, _ = self._gather(arguments["project_path"])
        docs = {item["path"]: item for item in snapshot["documents"]}
        prd = docs["docs/PRD.md"]
        if prd["status"] != "present":
            prd_content = ""
        else:
            _, prd_content = parse_front_matter(prd["content"])
        if target == "current":
            tech = docs[TARGET_PATH]
            if tech["status"] == "missing":
                structure = {"status": "missing", "checker_version": "solution-structure-v1", "issues": []}
                content_sha = "missing"
                body = ""
                header = None
            else:
                header, body = parse_front_matter(tech.get("content"))
                content_sha = tech["sha256"]
                structure = inspect_tech_spec(content=body, profile=header.get("profile", "Standard")
                                              if header else "Standard", prd_content=prd_content,
                                              prd_sha256=prd["sha256"], current_header=header,
                                              is_current=True)
            checked_object = {"target": "current", "file_sha256": content_sha, "prd_sha256": prd["sha256"]}
        else:
            body = arguments["content"]
            profile = arguments["profile"]
            structure = inspect_tech_spec(content=body, profile=profile, prd_content=prd_content,
                                          prd_sha256=prd["sha256"])
            checked_object = {"target": "candidate", "content_sha256": digest(body.encode("utf-8")),
                              "profile": profile, "prd_sha256": prd["sha256"]}
        return {**self.common(binding), "operation": "solution_inspect",
                "checked_object": checked_object, "structure": structure,
                "prd_structure": snapshot["prd_structure"],
                "source_alignment": snapshot["source_alignment"],
                "confirmation": snapshot["confirmation"],
                "coverage": structure.get("coverage"),
                "consistency": {"stable": not changed_paths, "changed_paths": changed_paths},
                "limitations": structure.get("limitations", {
                    "semantic_correctness_verified": False, "diagram_rendered": False, "model_evaluated": False})}

    def _eligibility(self, snapshot, changed_paths):
        if changed_paths:
            return "dependency_set_changed", "读取期间文件发生变化"
        diagnostics = snapshot["dependencies"]["diagnostics"]
        if "transaction_pending" in diagnostics:
            return "transaction_pending", "存在未完成公共事务"
        docs = {item["path"]: item for item in snapshot["documents"]}
        prd = docs["docs/PRD.md"]
        if prd["status"] == "missing":
            return "prd_missing", "PRD 不存在"
        if prd["status"] != "present":
            return "prd_unreadable", "PRD 不可读或不是有效 UTF-8"
        if any(item.startswith("specification_unreadable") for item in diagnostics):
            return "specification_unreadable", "项目指定规范存在不可读文件"
        if any(item.startswith("specification") for item in diagnostics):
            return "specification_invalid", "项目指定规范无效或包含越界链接"
        if diagnostics:
            return "dependency_set_changed", "保护依赖不完整或已失效"
        if snapshot["prd_structure"].get("issues"):
            return "prd_structure_invalid", "PRD 结构检查未通过"
        source_status = snapshot["source_alignment"]["status"]
        if source_status not in {"matched", "missing_source"}:
            return {
                "unbound": "source_binding_missing",
                "invalid": "source_binding_invalid",
                "outdated": "source_alignment_conflict",
                "unavailable": "source_alignment_conflict",
            }.get(source_status, "source_alignment_conflict"), "源需求绑定不满足保存条件"
        confirmation = snapshot["confirmation"]
        if confirmation["status"] != "valid" or not confirmation["valid_confirmation_ids"]:
            return f"prd_confirmation_{confirmation['status']}", "当前 PRD 缺少有效的形成技术方案确认"
        spec_state = snapshot["specification"]["state"]
        if spec_state in {"invalid", "unavailable"}:
            return "specification_invalid", "项目指定规范无效或不可读"
        return None, None

    def _consume(self, arguments, snapshot, binding):
        receipt = self.reads.get(arguments["read_id"])
        if receipt is None:
            return None
        now = self.clock()
        if now - receipt["issued_at"] >= READ_TTL_SECONDS:
            self.reads.pop(arguments["read_id"], None)
            raise ToolError("read_id_expired", "read_id 已过期", read_id_consumed=False)
        docs = {item["path"]: item for item in snapshot["documents"]}
        spec = snapshot["specification"]
        checks = {
            "project_id": receipt["project_id"],
            "dependency_set": receipt["dependency_set_sha256"],
            "target": receipt["target_sha256"],
            "prd": receipt["prd_sha256"],
            "requirements": receipt["requirements_sha256"],
            "spec_state": receipt["specification_state"],
            "spec_set": receipt["specification_set_sha256"],
            "confirmation_ids": receipt["valid_confirmation_ids"],
        }
        current_project_items = [item for item in snapshot["dependencies"]["normalized"]
                                 if item["scope"] == "project"]
        values = (
            checks["project_id"], checks["dependency_set"], checks["target"], checks["prd"],
            checks["requirements"], checks["spec_state"], checks["spec_set"], checks["confirmation_ids"],
        )
        expected = (
            binding["project_id"],
            snapshot["dependencies"]["dependency_set_sha256"],
            docs[TARGET_PATH]["sha256"], docs["docs/PRD.md"]["sha256"],
            docs["docs/requirements.md"]["sha256"], spec["state"], canonical_sha(spec["files"]),
            snapshot["confirmation"]["valid_confirmation_ids"],
        )
        if values != expected:
            raise ToolError("dependency_set_changed", "read_id 绑定的保护集合或输入版本已变化",
                            read_id_consumed=False)
        return self.reads.pop(arguments["read_id"])

    def render_draft(self, content, snapshot, profile):
        normalized = content.rstrip("\r\n") + "\n"
        confirmation_ids = snapshot["confirmation"]["valid_confirmation_ids"]
        spec = snapshot["specification"]
        header = (
            "---\n"
            "artifact_kind: tech-spec\n"
            "status: Draft\n"
            "approval_verified: false\n"
            f"profile: {profile}\n"
            "prd_path: docs/PRD.md\n"
            f"prd_sha256: {next(item for item in snapshot['documents'] if item['path'] == 'docs/PRD.md')['sha256']}\n"
            f"prd_confirmation_ids: {json.dumps(confirmation_ids, ensure_ascii=False)}\n"
            f"specification_state: {spec['state']}\n"
            f"specification_name: {json.dumps(spec['name'], ensure_ascii=False)}\n"
            "---\n\n"
        )
        return (header + normalized).encode("utf-8"), normalized

    def save_draft(self, arguments):
        if not self.allow_save:
            raise ToolError("tool_not_enabled", "保存工具未在本进程启用", read_id_consumed=False,
                            write_outcome="not_written",
                            side_effects={"target_replaced": False, "history_created": False,
                                          "temporary_created": False, "cleanup_complete": True})
        self._bind()
        binding, snapshot, changed_paths, _ = self._gather(arguments["project_path"])
        code, message = self._eligibility(snapshot, changed_paths)
        receipt = None
        if code is not None:
            raise ToolError(code, message, read_id_consumed=False, write_outcome="not_written",
                            side_effects={"target_replaced": False, "history_created": False,
                                          "temporary_created": False, "cleanup_complete": True})
        receipt = self._consume(arguments, snapshot, binding)
        if receipt is None:
            raise ToolError("read_id_invalid", "read_id 不存在、已消费或不属于本服务进程",
                            read_id_consumed=False, write_outcome="not_written",
                            side_effects={"target_replaced": False, "history_created": False,
                                          "temporary_created": False, "cleanup_complete": True})
        root = binding["root"]
        modules = self.runtime.modules
        target = safe_project_path(root, TARGET_PATH)
        side_effects = {"target_replaced": False, "history_created": False, "temporary_created": False,
                        "cleanup_complete": True}
        try:
            with modules.project_state.project_state_lock(root, "solution-tech-spec-save"):
                class _TranslatedLock:
                    def __init__(self, context_manager):
                        self.context_manager = context_manager

                    def __enter__(self):
                        try:
                            return self.context_manager.__enter__()
                        except ValueError as error:
                            raise ToolError("lock_conflict", str(error), read_id_consumed=True,
                                            write_outcome="not_written",
                                            side_effects=side_effects) from error

                    def __exit__(self, exc_type, exc, traceback):
                        return self.context_manager.__exit__(exc_type, exc, traceback)

                with _TranslatedLock(modules.project_state.exclusive_lock(
                        root / ".solution.lock", "方案写入锁已存在；先核对在途操作，不自动删除"
                    )):
                    binding, locked_snapshot, changed, _ = self._gather(root)
                    code, message = self._eligibility(locked_snapshot, changed)
                    if code is not None:
                        raise ToolError(code, message, read_id_consumed=True, write_outcome="not_written",
                                        side_effects=side_effects)
                    raw, normalized = self.render_draft(arguments["content"], locked_snapshot,
                                                        arguments["profile"])
                    if len(raw) > 128 * 1024:
                        raise ToolError("content_too_large", "渲染受管头后的最终文件超过 128 KiB",
                                        read_id_consumed=True, write_outcome="not_written",
                                        side_effects=side_effects)
                    previous = _read_bytes(root, TARGET_PATH, 128 * 1024)
                    previous_raw = target.read_bytes() if previous["status"] == "present" else None
                    if previous_raw == raw:
                        inspection = self._saved_inspection(root, locked_snapshot, raw)
                        return self._success(binding, locked_snapshot, "unchanged", False, raw,
                                             normalized, arguments["content"],
                                             previous_raw, None, inspection, receipt)
                    if locked_snapshot["dependencies"]["target_bound_to_registry"]:
                        raise ToolError("target_bound_to_registry",
                                        "目标仍是登记或确认快照依赖；变化写入会破坏既有固定版本",
                                        read_id_consumed=True, write_outcome="not_written",
                                        side_effects=side_effects)
                    history_info = None
                    if previous_raw is not None:
                        history_info = self._write_history(root, previous["sha256"], previous_raw)
                        side_effects["history_created"] = history_info["created"]
                    temporary_path = None
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                                         prefix=".tech-spec-", delete=False) as stream:
                            temporary_path = Path(stream.name)
                            stream.write(raw)
                            stream.flush()
                            os.fsync(stream.fileno())
                        side_effects["temporary_created"] = True
                        pre_replace = self._gather(root)[1]
                        pre_code, _ = self._eligibility(pre_replace, [])
                        current_target = _read_bytes(root, TARGET_PATH, 128 * 1024)
                        if pre_code is not None or current_target["sha256"] != receipt["target_sha256"]:
                            raise ToolError(pre_code or "version_conflict",
                                            "替换前发现输入或目标版本变化；未覆盖方案",
                                            read_id_consumed=True, write_outcome="not_written",
                                            side_effects=side_effects)
                        os.replace(temporary_path, target)
                        temporary_path = None
                        side_effects["target_replaced"] = True
                        side_effects["temporary_created"] = False
                        self._fsync_directory(target.parent)
                        post = self._gather(root)[1]
                        post_doc = _read_bytes(root, TARGET_PATH, 128 * 1024)
                        non_target_before = [item for item in locked_snapshot["dependencies"]["normalized"]
                                             if item["scope"] == "project" and item["path"] != TARGET_PATH]
                        non_target_after = [item for item in post["dependencies"]["normalized"]
                                            if item["scope"] == "project" and item["path"] != TARGET_PATH]
                        inputs_unchanged = canonical_sha(non_target_before) == canonical_sha(non_target_after)
                        target_verified = post_doc["status"] == "present" and post_doc["sha256"] == digest(raw)
                        confirmation_rechecked = post["confirmation"]["status"] == "valid"
                        inspection = self._saved_inspection(root, post, raw)
                        if not target_verified or not inputs_unchanged or not confirmation_rechecked:
                            return self._success(binding, post, "saved_unverified", True, raw,
                                                 normalized, arguments["content"],
                                                 previous_raw, history_info, inspection, receipt,
                                                 target_verified=target_verified,
                                                 inputs_unchanged=inputs_unchanged,
                                                 confirmation_rechecked=confirmation_rechecked)
                        return self._success(binding, post, "saved", True, raw, normalized,
                                             arguments["content"], previous_raw,
                                             history_info, inspection, receipt)
                    finally:
                        if temporary_path is not None:
                            temporary_path.unlink(missing_ok=True)
        except ToolError:
            raise
        except (OSError, ValueError, RuntimeError) as error:
            if side_effects.get("target_replaced"):
                outcome = "unknown"
            else:
                outcome = "not_written"
            raise ToolError("write_failed", str(error), read_id_consumed=True,
                            write_outcome=outcome, side_effects=side_effects) from error

    @staticmethod
    def _fsync_directory(path: Path):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_history(self, root, previous_sha, previous_raw):
        directory = safe_project_path(root, "docs/tech-spec-history")
        directory.mkdir(parents=True, exist_ok=True)
        path = safe_project_path(root, f"docs/tech-spec-history/{previous_sha}.md")
        if path.exists():
            current = path.read_bytes()
            if current != previous_raw:
                raise ToolError("history_conflict", "同名历史已存在但内容不同",
                                read_id_consumed=True, write_outcome="not_written")
            return {"previous_sha256": previous_sha, "path": str(path.relative_to(root)),
                    "created": False, "verified": True, "status": "reused"}
        with path.open("xb") as stream:
            stream.write(previous_raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != previous_raw:
            raise ToolError("history_digest_mismatch", "历史写入后复读不一致",
                            read_id_consumed=True, write_outcome="saved_unverified")
        return {"previous_sha256": previous_sha, "path": f"docs/tech-spec-history/{previous_sha}.md",
                "created": True, "verified": True}

    def _saved_inspection(self, root, snapshot, raw):
        try:
            text = raw.decode("utf-8")
            header, body = parse_front_matter(text)
            prd_sha = next(item for item in snapshot["documents"] if item["path"] == "docs/PRD.md")["sha256"]
            prd_body = parse_front_matter(next(
                item for item in snapshot["documents"] if item["path"] == "docs/PRD.md"
            )["content"])[1]
            checked = inspect_tech_spec(content=body, profile=header.get("profile", "Standard"),
                                        prd_content=prd_body, prd_sha256=prd_sha,
                                        current_header=header, is_current=True)
            return {"checked_file_sha256": digest(raw), "status": checked["status"],
                    "issue_codes": [item["code"] for item in checked["issues"]], "checked": checked}
        except (OSError, UnicodeDecodeError, ValueError, RuntimeError) as error:
            return {"checked_file_sha256": digest(raw), "status": "unavailable", "issue_codes": [],
                    "error": str(error)}

    def _success(self, binding, snapshot, outcome, changed, raw, normalized, submitted, previous_raw,
                 history_info, inspection, receipt, *, target_verified=True, inputs_unchanged=True,
                 confirmation_rechecked=True):
        docs = {item["path"]: item for item in snapshot["documents"]}
        spec = snapshot["specification"]
        target_info = {"path": TARGET_PATH, "sha256": digest(raw), "status": "Draft",
                       "approval_verified": False, "profile": arguments_profile(snapshot, raw)}
        return {
            **self.common(binding),
            "operation": "solution_save_tech_spec_draft",
            "write_outcome": outcome,
            "changed": changed,
            "read_id_consumed": receipt is not None,
            "submitted_content_sha256": digest(submitted.encode("utf-8")),
            "target": target_info,
            "normalized_content_sha256": digest(normalized.encode("utf-8")),
            "input_binding": {
                "prd_sha256": docs["docs/PRD.md"]["sha256"],
                "prd_confirmation_ids": snapshot["confirmation"]["valid_confirmation_ids"],
                "dependency_set_sha256": snapshot["dependencies"]["dependency_set_sha256"],
                "specification_state": spec["state"],
                "specification_name": spec["name"],
            },
            "history": history_info or {"previous_sha256": None, "path": None, "created": False,
                                        "verified": None, "status": "not_applicable"},
            "post_write": {
                "target_verified": target_verified,
                "metadata_verified": target_verified,
                "history_verified": (history_info or {}).get("verified", True),
                "inputs_unchanged": inputs_unchanged,
                "confirmation_rechecked": confirmation_rechecked,
                "cleanup_complete": True,
            },
            "inspection": inspection,
        }


def arguments_profile(snapshot, raw):
    header, _ = parse_front_matter(raw.decode("utf-8"))
    return header.get("profile") if header else None
