#!/usr/bin/env python3
"""最小化 MCP Server (SSE 模式) —— 用于测试 MCPClient SSE

运行方式：python tests/mcp_test_server_sse.py
默认监听: http://localhost:8765/sse
"""

import json
import uuid
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn


app = FastAPI()

# 存储会话状态
sessions: dict = {}


@app.post("/message")
async def message(request: Request):
    """接收 JSON-RPC 请求"""
    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test-sse-server", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "multiply",
                    "description": "两数相乘",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                        "required": ["x", "y"],
                    },
                },
                {
                    "name": "uppercase",
                    "description": "转大写",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            ]
        }
    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        if tool_name == "multiply":
            result = {"content": [{"type": "text", "text": str(args.get("x", 0) * args.get("y", 0))}]}
        elif tool_name == "uppercase":
            result = {"content": [{"type": "text", "text": args.get("text", "").upper()}]}
        else:
            result = {"error": f"未知工具: {tool_name}"}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}

    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


@app.get("/sse")
async def sse():
    """SSE 握手端点"""
    session_id = str(uuid.uuid4())

    async def event_stream():
        # MCP SSE 协议：先发送 endpoint 事件
        yield f"event: endpoint\ndata: /message?session_id={session_id}\n\n"
        # 保持连接打开
        import asyncio
        while True:
            await asyncio.sleep(10)
            yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
