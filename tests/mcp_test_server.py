#!/usr/bin/env python3
"""最小化 MCP Server —— 用于测试 MCPClient

支持：
- initialize / notifications/initialized
- tools/list
- tools/call (echo, add, get_time)

运行方式：python tests/mcp_test_server.py
通信方式：stdin/stdout JSON-RPC 2.0
"""

import json
import sys
from datetime import datetime


def send_message(msg: dict):
    """发送 JSON-RPC 消息到 stdout"""
    line = json.dumps(msg, ensure_ascii=False)
    print(line, flush=True)


def handle_initialize(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        },
    }


def handle_tools_list(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "tools": [
                {
                    "name": "echo",
                    "description": "回显输入文本",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                        "required": ["message"],
                    },
                },
                {
                    "name": "add",
                    "description": "两数相加",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
                {
                    "name": "get_time",
                    "description": "获取当前时间",
                    "inputSchema": {"type": "object", "properties": {}},
                },
            ]
        },
    }


def handle_tools_call(msg_id, params):
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "echo":
        result = {"content": [{"type": "text", "text": f"Echo: {arguments.get('message', '')}"}]}
    elif tool_name == "add":
        result = {"content": [{"type": "text", "text": str(arguments.get("a", 0) + arguments.get("b", 0))}]}
    elif tool_name == "get_time":
        result = {"content": [{"type": "text", "text": datetime.now().isoformat()}]}
    else:
        result = {"error": f"未知工具: {tool_name}"}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": result,
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            send_message(handle_initialize(msg_id))
        elif method == "notifications/initialized":
            pass  # 无需响应
        elif method == "tools/list":
            send_message(handle_tools_list(msg_id))
        elif method == "tools/call":
            send_message(handle_tools_call(msg_id, msg.get("params", {})))
        else:
            send_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
