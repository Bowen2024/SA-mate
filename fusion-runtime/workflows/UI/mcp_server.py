#!/usr/bin/env python3
"""stdio MCP entry for UI file tools. Standard library only.

Read-only launches expose the three read tools. --allow-write exposes all six
tools, including controlled accept and explicit transaction recovery.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Isolated launches (`-I`, which implies `-P`) do not put the script directory
# on sys.path. Prepend this file's real install directory explicitly so sibling
# modules load from the controlled UI copy rather than cwd or PYTHONPATH.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from shared_loader import (
    CLIENT_ENTRY_NAME,
    CONTRACT_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    FoundationError,
    load_shared,
)
from file_tools.context import UiTools, ToolError


MAX_MESSAGE = 1024 * 1024
MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

READ_CONTEXT = "ui_read_context"
INSPECT = "ui_inspect"
READ_HISTORY = "ui_read_history"
PREPARE = "ui_prepare_revision"
ACCEPT = "ui_accept_revision"
RECOVER = "ui_recover_revision"

WRITE_TOOLS = (PREPARE, ACCEPT, RECOVER)


def _string(name):
    return {"type": "string", "description": f"{name}（项目内规范相对路径或绝对路径，按工具要求）"}


TOOL_SCHEMAS = {
    READ_CONTEXT: {
        "name": READ_CONTEXT,
        "description": "读取 UI 角色固定项目上下文、当前集合、历史摘要与导入映射；只读，签发进程内 read_id。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "artifact_root": {"type": "string", "minLength": 1},
                "source_paths": {"type": "array", "items": {"type": "string"}},
                "import_source": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["root", "files", "entrypoint", "design_path", "readme_path"],
                    "properties": {
                        "root": {"type": "string", "minLength": 1},
                        "files": {"type": "array", "items": {"type": "string"}},
                        "entrypoint": {"type": "string"},
                        "design_path": {"type": "string"},
                        "readme_path": {"type": "string"},
                    },
                },
            },
        },
    },
    INSPECT: {
        "name": INSPECT,
        "description": "只读检查当前集合、候选或事务；不写文件。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "target"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "target": {"type": "string", "enum": ["current", "candidate", "transaction"]},
                "revision_id": {"type": "string", "pattern": "^R-[0-9a-f]{32}$"},
                "transaction_id": {"type": "string", "pattern": "^T-[0-9a-f]{32}$"},
            },
        },
    },
    READ_HISTORY: {
        "name": READ_HISTORY,
        "description": "只读列出或读取不可变 UI 版本历史。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "after_revision": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    PREPARE: {
        "name": PREPARE,
        "description": "在私有工作区准备候选（empty/current/import/history），消费 read_id；不修改公共成果。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "read_id", "request_id", "mode"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "read_id": {"type": "string", "minLength": 1},
                "request_id": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                },
                "mode": {"type": "string", "enum": ["empty", "current", "import", "history"]},
                "history_revision": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
        },
    },
    ACCEPT: {
        "name": ACCEPT,
        "description": "按有效 inspection_id 受控接收完整候选；delete_paths 必须与 removed 精确一致。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "revision_id", "inspection_id", "request_id", "delete_paths"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "revision_id": {"type": "string", "pattern": "^R-[0-9a-f]{32}$"},
                "inspection_id": {"type": "string", "minLength": 1},
                "request_id": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                },
                "delete_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    RECOVER: {
        "name": RECOVER,
        "description": "显式 resume 或 rollback 已核对事务；不自动清理锁或覆盖第三方状态。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "transaction_id", "request_id", "action"],
            "properties": {
                "project_path": {"type": "string", "minLength": 1},
                "transaction_id": {"type": "string", "pattern": "^T-[0-9a-f]{32}$"},
                "request_id": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                },
                "action": {"type": "string", "enum": ["resume", "rollback"]},
            },
        },
    },
}


def validate_arguments(name, arguments):
    schema = TOOL_SCHEMAS[name]["inputSchema"]
    properties = schema["properties"]
    if not isinstance(arguments, dict):
        raise ToolError("invalid_arguments", "arguments 必须是对象")
    unknown = set(arguments) - set(properties)
    if unknown:
        raise ToolError("invalid_arguments", "包含未知字段：" + ", ".join(sorted(unknown)))
    missing = set(schema.get("required", [])) - set(arguments)
    if missing:
        raise ToolError("invalid_arguments", "缺少必填字段：" + ", ".join(sorted(missing)))
    project_path = arguments.get("project_path")
    if not isinstance(project_path, str) or not project_path.strip():
        raise ToolError("invalid_arguments", "project_path 必须是非空字符串")
    if "artifact_root" in arguments and (not isinstance(arguments["artifact_root"], str)
                                         or not arguments["artifact_root"].strip()):
        raise ToolError("invalid_arguments", "artifact_root 必须是非空字符串")
    if "source_paths" in arguments:
        value = arguments["source_paths"]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ToolError("invalid_arguments", "source_paths 必须是字符串数组")
    if "import_source" in arguments and not isinstance(arguments["import_source"], dict):
        raise ToolError("invalid_arguments", "import_source 必须是对象")
    if "revision_id" in arguments and not isinstance(arguments["revision_id"], str):
        raise ToolError("invalid_arguments", "revision_id 必须是字符串")
    if "transaction_id" in arguments and not isinstance(arguments["transaction_id"], str):
        raise ToolError("invalid_arguments", "transaction_id 必须是字符串")
    if "revision_sha256" in arguments and not isinstance(arguments["revision_sha256"], str):
        raise ToolError("invalid_arguments", "revision_sha256 必须是字符串")
    if "after_revision" in arguments and not isinstance(arguments["after_revision"], str):
        raise ToolError("invalid_arguments", "after_revision 必须是字符串")
    if "limit" in arguments and (isinstance(arguments["limit"], bool)
                                 or not isinstance(arguments["limit"], int)):
        raise ToolError("invalid_arguments", "limit 必须是整数")
    if name == PREPARE:
        for field in ("read_id", "request_id", "mode"):
            if not isinstance(arguments.get(field), str) or not arguments[field].strip():
                raise ToolError("invalid_arguments", f"{field} 必须是非空字符串")
        import re
        if not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            arguments["request_id"],
        ):
            raise ToolError("invalid_arguments", "request_id 必须是标准小写 UUID")
        if arguments["mode"] not in {"empty", "current", "import", "history"}:
            raise ToolError("invalid_arguments", "mode 非法")
        if "history_revision" in arguments:
            if arguments["mode"] != "history":
                raise ToolError("invalid_arguments", "history_revision 只允许 mode=history")
            if not isinstance(arguments["history_revision"], str) \
                    or len(arguments["history_revision"]) != 64:
                raise ToolError("invalid_arguments", "history_revision 必须是 64 位十六进制")
        elif arguments["mode"] == "history":
            raise ToolError("invalid_arguments", "mode=history 必须提供 history_revision")
    if name in {ACCEPT, RECOVER}:
        import re
        request_id = arguments.get("request_id")
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            request_id,
        ):
            raise ToolError("invalid_arguments", "request_id 必须是标准小写 UUID")
    if name == ACCEPT:
        for field in ("revision_id", "inspection_id"):
            if not isinstance(arguments.get(field), str) or not arguments[field].strip():
                raise ToolError("invalid_arguments", f"{field} 必须是非空字符串")
        if not isinstance(arguments.get("delete_paths"), list) or any(
            not isinstance(item, str) for item in arguments["delete_paths"]
        ):
            raise ToolError("invalid_arguments", "delete_paths 必须是字符串数组（无删除传 []）")
    if name == RECOVER:
        if not isinstance(arguments.get("transaction_id"), str) \
                or not arguments["transaction_id"].strip():
            raise ToolError("invalid_arguments", "transaction_id 必须是非空字符串")
        if arguments.get("action") not in {"resume", "rollback"}:
            raise ToolError("invalid_arguments", "action 必须是 resume 或 rollback")


class McpServer:
    def __init__(self, tools, *, runtime=None):
        self.tools = tools
        self.runtime = runtime
        self.initialized = False

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self.error(message.get("id") if isinstance(message, dict) else None, -32600,
                             "无效 JSON-RPC 请求")
        method = message.get("method")
        params = message.get("params") or {}
        identifier = message.get("id")
        if method == "initialize":
            version = params.get("protocolVersion")
            if version not in {MODERN_VERSION, *LEGACY_VERSIONS}:
                return self.error(identifier, -32602, "不支持的 MCP 协议版本")
            self.initialized = True
            return self.result(identifier, {"protocolVersion": version,
                                            "capabilities": {"tools": {"listChanged": False}},
                                            "serverInfo": {"name": SERVER_NAME,
                                                           "version": SERVER_VERSION}})
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return self.result(identifier, {})
        if method == "server/discover":
            return self.result(identifier, {"supportedVersions": [MODERN_VERSION, *LEGACY_VERSIONS],
                                            "resultType": "complete", "contract": CONTRACT_VERSION,
                                            "clientEntryName": CLIENT_ENTRY_NAME})
        if not self.initialized:
            return self.error(identifier, -32000, "initialize 完成前不能调用工具")
        if method == "tools/list":
            return self.result(identifier, {"tools": self.list_tools()})
        if method == "tools/call":
            return self.call_tool(identifier, params)
        return self.error(identifier, -32601, f"未知方法：{method}")

    def list_tools(self):
        names = [READ_CONTEXT, INSPECT, READ_HISTORY]
        if getattr(self.tools, "allow_write", False):
            names.extend(WRITE_TOOLS)
        return [TOOL_SCHEMAS[name] for name in names]

    def call_tool(self, identifier, params):
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name in WRITE_TOOLS:
            if not getattr(self.tools, "allow_write", False):
                payload = self._error_envelope(name, ToolError(
                    "tool_not_enabled", "写工具未开放：本服务以只读模式启动",
                    next_action="需要写入时由宿主以 --allow-write 重启服务"))
                return self.tool_result(identifier, payload, is_error=True)
        if name not in TOOL_SCHEMAS:
            payload = self._error_envelope(name, ToolError("invalid_arguments", f"未知工具：{name}"))
            return self.tool_result(identifier, payload, is_error=True)
        try:
            validate_arguments(name, arguments)
            payload = self.dispatch(name, arguments)
        except (ToolError, FoundationError) as error:
            return self.tool_result(identifier, self._error_envelope(name, error), is_error=True)
        return self.tool_result(identifier, payload, is_error=False)

    def dispatch(self, name, arguments):
        if name == READ_CONTEXT:
            return self.tools.read_context(
                arguments["project_path"],
                artifact_root=arguments.get("artifact_root"),
                source_paths=arguments.get("source_paths"),
                import_source=arguments.get("import_source"),
            )
        if name == INSPECT:
            target = arguments["target"]
            if target == "candidate" and not arguments.get("revision_id"):
                raise ToolError("invalid_arguments", "target=candidate 时必须提供 revision_id")
            if target != "candidate" and "revision_id" in arguments:
                raise ToolError("invalid_arguments", "只有 target=candidate 允许 revision_id")
            if target == "current" and "transaction_id" in arguments:
                raise ToolError("invalid_arguments", "target=current 不接受 transaction_id")
            return self.tools.inspect(
                arguments["project_path"], target,
                revision_id=arguments.get("revision_id"),
                transaction_id=arguments.get("transaction_id"),
                artifact_root=arguments.get("artifact_root"),
            )
        if name == PREPARE:
            return self.tools.prepare_revision(
                arguments["project_path"],
                arguments["read_id"],
                arguments["request_id"],
                arguments["mode"],
                history_revision=arguments.get("history_revision"),
            )
        if name == ACCEPT:
            return self.tools.accept_revision(
                arguments["project_path"],
                arguments["revision_id"],
                arguments["inspection_id"],
                arguments["request_id"],
                arguments["delete_paths"],
            )
        if name == RECOVER:
            return self.tools.recover_revision(
                arguments["project_path"],
                arguments["transaction_id"],
                arguments["request_id"],
                arguments["action"],
            )
        if name == READ_HISTORY:
            return self.tools.read_history(
                arguments["project_path"],
                revision_sha256=arguments.get("revision_sha256"),
                after_revision=arguments.get("after_revision"),
                limit=arguments.get("limit", 20),
            )
        raise ToolError("invalid_arguments", f"未知工具：{name}")

    @staticmethod
    def _error_envelope(operation, error):
        code = getattr(error, "code", "io_error")
        details = getattr(error, "details", {}) or {}
        paths = details.get("paths", []) if isinstance(details, dict) else []
        payload = {
            "contract_version": CONTRACT_VERSION,
            "operation": operation,
            "project": None,
            "state": "unavailable",
            "diagnostics": [{"code": code, "message": str(error), "paths": paths}],
            "checks": [],
            "write_outcome": getattr(error, "write_outcome", "not_written"),
            "error": {
                "code": code,
                "message": str(error),
                "details": details,
                "next_action": getattr(error, "next_action", "核对参数与当前文件后重试"),
            },
        }
        if operation in WRITE_TOOLS:
            payload.update({
                "request_id": details.get("request_id"),
                "revision_id": details.get("revision_id"),
                "transaction_id": details.get("transaction_id"),
                "revision_sha256": details.get("revision_sha256"),
                "verification": None,
                "receipt_replay": False,
            })
        return payload

    @staticmethod
    def tool_result(identifier, payload, *, is_error):
        result = {"content": [{"type": "text",
                               "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}],
                  "isError": is_error}
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    @staticmethod
    def result(identifier, result):
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    @staticmethod
    def error(identifier, code, message):
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def serve(server, input_stream, output_stream):
    for raw_line in input_stream:
        if not raw_line.strip():
            continue
        if len(raw_line) > MAX_MESSAGE:
            response = server.error(None, -32600, "消息超过 1 MiB")
        else:
            try:
                message = json.loads(raw_line.decode("utf-8"))
                response = server.handle(message)
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = server.error(None, -32700, "无效 JSON")
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
            output_stream.flush()


def build_server(foundation: Path, import_roots=(), allow_write=False):
    runtime = load_shared(foundation)
    return McpServer(UiTools(runtime, allow_write=allow_write, import_roots=import_roots),
                     runtime=runtime)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", required=True, type=Path, help="受信 requirements 绝对目录")
    parser.add_argument("--import-root", action="append", default=[],
                        help="获准只读导入的普通绝对目录，可重复")
    parser.add_argument("--allow-write", action="store_true",
                        help="开放候选准备、受控接收和显式恢复能力")
    args = parser.parse_args(argv)
    if not args.foundation.is_absolute():
        parser.error("--foundation 必须是绝对路径")
    for root in args.import_root:
        if not Path(root).is_absolute():
            parser.error("--import-root 必须是绝对路径")
    try:
        server = build_server(args.foundation, args.import_root,
                              allow_write=args.allow_write)
    except FoundationError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error),
                                    "details": error.details}}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    serve(server, sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
