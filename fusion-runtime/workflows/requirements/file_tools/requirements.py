"""Project-scoped draft tools. No model calls, Git mutations or approvals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

if __package__:
    from .project_init import context as project_context, load_project
    from .project_state import exclusive_lock, project_state_lock
else:
    from project_init import context as project_context, load_project
    from project_state import exclusive_lock, project_state_lock

LIMIT = 128 * 1024
SOURCE_DOCUMENTS = ("project.json", "README.md")
PRD_SOURCE_DOCUMENTS = ("project.json", "README.md", "docs/requirements.md")
ID_PATTERN = re.compile(r"\b(REQ|AC)-\d{3,}\b")
AC_HEADING_PATTERN = re.compile(r"(?m)^###\s+(AC-\d{3,})\b.*$")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def safe_path(root, relative):
    path = root
    for part in Path(relative).parts:
        if part in {"..", "/"}:
            raise ValueError("路径越界")
        path = path / part
        if path.is_symlink():
            raise ValueError("不允许通过软链读写项目文档")
    if not path.resolve().is_relative_to(root):
        raise ValueError("路径越界")
    return path


def read_document(root, relative):
    path = safe_path(root, relative)
    if not path.exists():
        return {"path": relative, "content": None, "sha256": "missing"}
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("文档不是独立普通文件")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("文档超过首版 128 KiB 限制")
    return {"path": relative, "content": raw.decode("utf-8"), "sha256": digest(raw)}


def context(foundation, project_id, *, expected_root=None, directory_name=None):
    _, root = project_context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    load_project(root, project_id)
    return {"project_id": project_id, "project_path": str(root),
            "documents": [read_document(root, p) for p in (
                "project.json", "README.md", "docs/PRD.md", "docs/requirements.md")],
            "approval_verified": False}


def _prd_ids(content):
    result = {"REQ": set(), "AC": set()}
    if content:
        for match in ID_PATTERN.finditer(content):
            result[match.group(1)].add(match.group(0))
    return result


def _section_has_mermaid(content, heading, required_term=None):
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", content or ""
    )
    if not match or "```mermaid" not in match.group(1):
        return False
    return required_term is None or required_term in match.group(1)


def inspect_prd(foundation, project_id, *, expected_root=None, directory_name=None):
    current = context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    documents = {item["path"]: item for item in current["documents"]}
    document = documents["docs/PRD.md"]
    content = document["content"] or ""
    ids = _prd_ids(content)
    issues = []
    required_sections = (
        "用户结果与成功指标", "具体案例", "范围与边界", "REQ 与 AC",
        "业务流程图", "业务时序图", "事实、假设与待决事项", "变更摘要",
    )
    if not content:
        issues.append({"code": "prd_missing"})
    else:
        missing_sections = [
            heading for heading in required_sections
            if not re.search(rf"(?m)^##\s+{re.escape(heading)}\s*$", content)
        ]
        if missing_sections:
            issues.append({"code": "prd_sections_missing", "sections": missing_sections})
        if not ids["REQ"] or not ids["AC"]:
            issues.append({
                "code": "prd_ids_missing",
                "req_count": len(ids["REQ"]),
                "ac_count": len(ids["AC"]),
            })
        ac_matches = list(AC_HEADING_PATTERN.finditer(content))
        incomplete = []
        result_types = set()
        for index, match in enumerate(ac_matches):
            block = content[match.end():ac_matches[index + 1].start() if index + 1 < len(ac_matches) else len(content)]
            missing = [
                label for label in ("结果类型", "前置条件", "操作", "可观察结果", "验证方式")
                if not re.search(rf"(?m)^-\s*{label}\s*[::：]", block)
            ]
            type_match = re.search(r"(?m)^-\s*结果类型\s*[::：]\s*(成功|失败)\s*$", block)
            if type_match:
                result_types.add(type_match.group(1))
            else:
                missing.append("结果类型=成功|失败")
            if missing:
                incomplete.append({"ac": match.group(1), "missing": sorted(set(missing))})
        if incomplete:
            issues.append({"code": "acceptance_criteria_incomplete", "items": incomplete})
        if ids["AC"] and result_types != {"成功", "失败"}:
            issues.append({"code": "success_and_failure_coverage_missing", "observed": sorted(result_types)})
        if not _section_has_mermaid(content, "业务流程图", "flowchart"):
            issues.append({"code": "business_flow_diagram_missing"})
        if not _section_has_mermaid(content, "业务时序图", "sequenceDiagram"):
            issues.append({"code": "business_sequence_diagram_missing"})
    return {
        "mode": "read-only",
        "status": "ready_for_review" if not issues else "attention_required",
        "project_id": project_id,
        "prd": {
            "path": document["path"],
            "sha256": document["sha256"],
            "req_ids": sorted(ids["REQ"]),
            "ac_ids": sorted(ids["AC"]),
        },
        "issues": issues,
        "approval_checked": False,
        "semantic_correctness_checked": False,
    }


def validate_source_digests(body, sources):
    """Reject source SHA claims that disagree with the current project files."""
    for name, expected in sources.items():
        for line in body.splitlines():
            if name not in line or "sha" not in line.lower():
                continue
            match = re.search(r"sha(?:-?256)?\s*[：:]\s*`?([0-9a-z_-]+)", line, re.IGNORECASE)
            if match and match.group(1).lower() != expected:
                raise ValueError(f"{name} 来源摘要不匹配；重新读取项目背景")


def save_draft(foundation, project_id, body, expected, *, expected_root=None, directory_name=None):
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > LIMIT - 100:
        raise ValueError("草案必须是非空 UTF-8 文本，且小于 128 KiB")
    _, root = project_context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    load_project(root, project_id)
    target = safe_path(root, "docs/requirements.md")
    lock = root / ".requirements.lock"
    with project_state_lock(root, "requirements-save"):
        with exclusive_lock(lock, "需求写入锁已存在；先核对在途操作"):
            temporary = None
            try:
                previous = read_document(root, "docs/requirements.md")
                if previous["sha256"] != expected:
                    raise ValueError("需求版本冲突；重新读取，不覆盖新版本")
                sources = {name: read_document(root, name)["sha256"] for name in SOURCE_DOCUMENTS}
                validate_source_digests(body, sources)
                rendered = "---\nstatus: Draft\napproval_verified: false\n---\n\n" + body.strip() + "\n"
                raw = rendered.encode("utf-8")
                if digest(raw) == previous["sha256"]:
                    return {"path": str(target), "sha256": digest(raw), "status": "Draft", "changed": False,
                            "source_sha256": sources}
                docs = safe_path(root, "docs")
                docs.mkdir(exist_ok=True)
                if previous["content"] is not None:
                    history = safe_path(root, "docs/requirements-history")
                    history.mkdir(exist_ok=True)
                    archive = safe_path(root, f"docs/requirements-history/{previous['sha256']}.md")
                    if archive.exists():
                        archived = read_document(root, archive.relative_to(root).as_posix())
                        if archived["sha256"] != previous["sha256"]:
                            raise ValueError("历史版本冲突")
                    else:
                        with archive.open("x", encoding="utf-8") as stream:
                            stream.write(previous["content"])
                with tempfile.NamedTemporaryFile(mode="wb", dir=docs, prefix=".requirements-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                temporary = None
                return {"path": str(target), "sha256": digest(raw), "status": "Draft", "changed": True,
                        "approval_verified": False, "index_update_required": True,
                        "source_sha256": sources}
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def save_prd_draft(foundation, project_id, body, expected_prd_sha, expected_requirements_sha, *,
                   expected_root=None, directory_name=None):
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > LIMIT - 512:
        raise ValueError("PRD 草案必须是非空 UTF-8 文本，且预留元数据后小于 128 KiB")
    if body.lstrip().startswith("---"):
        raise ValueError("正文不得自带 front matter；状态与输入摘要由工具生成")
    _, root = project_context(foundation, project_id, expected_root=expected_root, directory_name=directory_name)
    load_project(root, project_id)
    target = safe_path(root, "docs/PRD.md")
    lock = root / ".prd.lock"
    with project_state_lock(root, "prd-save"):
        with exclusive_lock(lock, "PRD 写入锁已存在；先核对在途操作"):
            temporary = None
            try:
                previous = read_document(root, "docs/PRD.md")
                if previous["sha256"] != expected_prd_sha:
                    raise ValueError("PRD 版本冲突；重新读取，不覆盖新版本")
                requirements_document = read_document(root, "docs/requirements.md")
                if requirements_document["sha256"] != expected_requirements_sha:
                    raise ValueError("轻量需求输入版本冲突；重新读取后再整理 PRD")
                sources = {
                    name: read_document(root, name)["sha256"] for name in PRD_SOURCE_DOCUMENTS
                }
                validate_source_digests(body, sources)
                rendered = (
                    "---\n"
                    "artifact_kind: prd\n"
                    "status: Draft\n"
                    "approval_verified: false\n"
                    "source_requirements_path: docs/requirements.md\n"
                    f"source_requirements_sha256: {requirements_document['sha256']}\n"
                    "---\n\n" + body.strip() + "\n"
                )
                raw = rendered.encode("utf-8")
                if digest(raw) == previous["sha256"]:
                    return {
                        "path": str(target), "sha256": digest(raw), "status": "Draft",
                        "changed": False, "source_requirements_sha256": requirements_document["sha256"],
                        "source_sha256": sources,
                    }
                docs = safe_path(root, "docs")
                docs.mkdir(exist_ok=True)
                if previous["content"] is not None:
                    history = safe_path(root, "docs/prd-history")
                    history.mkdir(exist_ok=True)
                    archive_relative = f"docs/prd-history/{previous['sha256']}.md"
                    archive = safe_path(root, archive_relative)
                    if archive.exists():
                        if read_document(root, archive_relative)["sha256"] != previous["sha256"]:
                            raise ValueError("PRD 历史版本冲突")
                    else:
                        with archive.open("x", encoding="utf-8") as stream:
                            stream.write(previous["content"])
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=docs, prefix=".prd-", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                temporary = None
                return {
                    "path": str(target), "sha256": digest(raw), "status": "Draft",
                    "approval_verified": False, "changed": True,
                    "source_requirements_sha256": requirements_document["sha256"],
                    "index_update_required": True, "source_sha256": sources,
                }
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", type=Path, required=True,
                        help="显式指定包含 config/local.json 的融合配置目录")
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("context")
    read.add_argument("project_id")
    save = commands.add_parser("save-draft")
    save.add_argument("project_id")
    save.add_argument("--expected-sha", required=True, help="context 返回的摘要；首次为 missing")
    save.add_argument("--apply", action="store_true")
    inspect_prd_command = commands.add_parser("inspect-prd")
    inspect_prd_command.add_argument("project_id")
    save_prd = commands.add_parser("save-prd-draft")
    save_prd.add_argument("project_id")
    save_prd.add_argument("--expected-prd-sha", required=True)
    save_prd.add_argument("--expected-requirements-sha", required=True)
    save_prd.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "context":
            result = context(args.foundation, args.project_id)
        elif args.command == "inspect-prd":
            result = inspect_prd(args.foundation, args.project_id)
        elif not args.apply:
            raise ValueError("保存需要 --apply；正文通过标准输入传入")
        else:
            raw = sys.stdin.buffer.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("输入过大")
            if args.command == "save-draft":
                result = save_draft(
                    args.foundation, args.project_id, raw.decode("utf-8"), args.expected_sha
                )
            else:
                result = save_prd_draft(
                    args.foundation, args.project_id, raw.decode("utf-8"),
                    args.expected_prd_sha, args.expected_requirements_sha,
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
