#!/usr/bin/env python3
"""stdio MCP entry for Solution Designer file tools. Standard library only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from shared_loader import (
    CLIENT_ENTRY_NAME,
    CONTRACT_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    FoundationError,
    load_shared,
)
from file_tools.solution import PROFILES, SolutionTools, ToolError


MAX_MESSAGE = 1024 * 1024
MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
READ_CONTEXT = "solution_read_context"
INSPECT = "solution_inspect"
SAVE_DRAFT = "solution_save_tech_spec_draft"


def project_path_schema():
    return {"project_path": {"type": "string", "description": "用户显式选择的项目绝对路径"}}


TOOL_SCHEMAS = {
    READ_CONTEXT: {
        "name": READ_CONTEXT,
        "description": "读取方案角色固定项目上下文、PRD 用途确认、保护依赖和可选方案历史；只读。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path"],
            "properties": {
                **project_path_schema(),
                "history_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$",
                                   "description": "可选：已返回的方案历史完整文件摘要"},
            },
        },
    },
    INSPECT: {
        "name": INSPECT,
        "description": "检查当前方案或候选方案的 0—12 章节、REQ/AC 覆盖和受管头；不写文件。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "target"],
            "properties": {
                **project_path_schema(),
                "target": {"type": "string", "enum": ["current", "candidate"]},
                "content": {"type": "string", "minLength": 1, "description": "target=candidate 时必填"},
                "profile": {"type": "string", "enum": list(PROFILES)},
            },
        },
    },
    SAVE_DRAFT: {
        "name": SAVE_DRAFT,
        "description": "仅在 --allow-save 启动时开放；保存 docs/tech-spec.md Draft，不签发确认或启动下游。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_path", "read_id", "content", "profile"],
            "properties": {
                **project_path_schema(),
                "read_id": {"type": "string", "minLength": 1},
                "content": {"type": "string", "minLength": 1},
                "profile": {"type": "string", "enum": list(PROFILES)},
            },
        },
    },
}


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
                                            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
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
        names = [READ_CONTEXT, INSPECT]
        if self.tools.allow_save:
            names.append(SAVE_DRAFT)
        return [TOOL_SCHEMAS[name] for name in names]

    def call_tool(self, identifier, params):
        name = params.get("name")
        arguments = params.get("arguments")
        if name not in TOOL_SCHEMAS or (name == SAVE_DRAFT and not self.tools.allow_save):
            payload = {"contract_version": CONTRACT_VERSION, "operation": name,
                       "error": {"code": "tool_not_enabled", "message": "工具未开放",
                                 "details": {}, "next_action": "核对启动参数和工具名"}}
            return self.result(identifier, {"content": [{"type": "text", "text": json.dumps(payload,
                                                                                           ensure_ascii=False)}],
                                            "isError": True})
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            self.validate_arguments(name, arguments)
            if name == READ_CONTEXT:
                result = self.tools.read_context(arguments)
            elif name == INSPECT:
                result = self.tools.inspect(arguments)
            else:
                result = self.tools.save_draft(arguments)
            is_error = False
        except (ToolError, FoundationError, OSError, ValueError, RuntimeError) as error:
            result = self.error_payload(name, error)
            is_error = True
        return self.result(identifier, {"content": [{"type": "text",
                                                     "text": json.dumps(result, ensure_ascii=False)}],
                                        "isError": is_error})

    @staticmethod
    def validate_arguments(name, arguments):
        schema = TOOL_SCHEMAS[name]["inputSchema"]
        allowed = set(schema["properties"])
        unknown = set(arguments) - allowed
        if unknown:
            raise ToolError("invalid_arguments", "包含未知字段：" + ", ".join(sorted(unknown)))
        missing = set(schema.get("required", [])) - set(arguments)
        if missing:
            raise ToolError("invalid_arguments", "缺少字段：" + ", ".join(sorted(missing)))
        for field in ("project_path", "read_id", "content"):
            if field in arguments and (not isinstance(arguments[field], str) or not arguments[field].strip()):
                raise ToolError("invalid_arguments", f"{field} 必须是非空字符串")
        if "history_sha256" in arguments and not isinstance(arguments["history_sha256"], str):
            raise ToolError("invalid_arguments", "history_sha256 必须是字符串")
        if name == INSPECT:
            if arguments["target"] == "candidate":
                if not isinstance(arguments.get("content"), str) or not arguments["content"].strip():
                    raise ToolError("content_invalid", "candidate 必须提供非空 content")
                if arguments.get("profile") not in PROFILES:
                    raise ToolError("profile_invalid", "candidate 必须指定 Lite、Standard 或 AI")
                if arguments["content"].lstrip().startswith("---"):
                    raise ToolError("content_invalid", "候选正文不能自带 YAML front matter")
            else:
                if "content" in arguments or "profile" in arguments:
                    raise ToolError("invalid_arguments", "current 检查不接受 content 或 profile")
        if name == SAVE_DRAFT:
            if arguments.get("profile") not in PROFILES:
                raise ToolError("profile_invalid", "profile 必须是 Lite、Standard 或 AI")
            content = arguments.get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise ToolError("content_invalid", "方案正文必须非空")
            if content.lstrip().startswith("---"):
                raise ToolError("content_invalid", "候选正文不能自带 YAML front matter")
            if len(content.encode("utf-8")) > 128 * 1024:
                raise ToolError("content_too_large", "候选正文超过 128 KiB")

    @staticmethod
    def error_payload(operation, error):
        code = getattr(error, "code", "write_failed" if operation == SAVE_DRAFT else "runtime_error")
        details = getattr(error, "details", {}) or {}
        payload = {
            "contract_version": CONTRACT_VERSION,
            "operation": operation,
            "error": {
                "code": code,
                "message": str(error),
                "details": details,
                "next_action": getattr(error, "next_action", "核对输入与当前文件后重试"),
            },
        }
        if operation == SAVE_DRAFT:
            payload.update({
                "write_outcome": getattr(error, "details", {}).get("write_outcome", "not_written"),
                "read_id_consumed": getattr(error, "details", {}).get("read_id_consumed", False),
                "side_effects": getattr(error, "details", {}).get(
                    "side_effects",
                    {"target_replaced": False, "history_created": False,
                     "temporary_created": False, "cleanup_complete": True},
                ),
                "confirmation_written": False,
                "artifact_registered": False,
                "downstream_started": False,
            })
        return payload

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


def build_server(foundation: Path, allow_save: bool):
    runtime = load_shared(foundation)
    return McpServer(SolutionTools(runtime, allow_save=allow_save), runtime=runtime)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", required=True, type=Path, help="受信 requirements 绝对目录")
    parser.add_argument("--allow-save", action="store_true", help="开放 Draft 保存工具")
    args = parser.parse_args(argv)
    if not args.foundation.is_absolute():
        parser.error("--foundation 必须是绝对路径")
    try:
        server = build_server(args.foundation, args.allow_save)
    except FoundationError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error), "details": error.details}},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    serve(server, sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

