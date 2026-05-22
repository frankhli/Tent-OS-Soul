"""Tent OS MCP Server —— 将 Tent OS 暴露为 MCP Server

让 Claude Desktop / Cursor / 其他 MCP Client 调用 Tent OS：
1. POST /mcp        — JSON-RPC endpoint
2. GET  /mcp/sse    — SSE transport (optional)

暴露的工具：
- tent_shell_execute, tent_file_read, tent_file_write
- tent_directory_list, tent_http_request
- tent_web_search, tent_web_fetch
- tent_memory_search, tent_memory_get
- tent_task_submit
- tent_community_message, tent_community_resident_list
"""

import asyncio
import json
import os
import sqlite3
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tent_os.logging_config import get_logger
from tent_os.tools.definitions import get_tool_schemas

logger = get_logger()


class MCPServer:
    """Tent OS MCP Server —— JSON-RPC 2.0"""

    def __init__(self):
        self._initialized = False
        self._tool_executor = None

    async def initialize(self):
        """初始化 ToolExecutor"""
        from tent_os.scheduler.executors.local import LocalExecutor
        from tent_os.tools.executor import ToolExecutor
        from tent_os.memory.tiered_store import TieredMemoryStore

        local_executor = LocalExecutor()
        await local_executor.initialize({
            "mode": "local",
            "auto_approve": True,
            "timeout_seconds": 60,
        })

        memory_store = TieredMemoryStore("./tent_memory")

        self._tool_executor = ToolExecutor(
            local_executor=local_executor,
            memory_store=memory_store,
        )
        self._initialized = True
        logger.info("[MCP] Server initialized with ToolExecutor")

    def _to_mcp_tools(self) -> List[Dict]:
        """将 OpenAI function schema 转换为 MCP tool schema"""
        schemas = get_tool_schemas()
        tools = []
        for s in schemas:
            fn = s.get("function", {})
            tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "inputSchema": fn.get("parameters", {"type": "object", "properties": {}})
            })

        # 添加 AI 社会专用工具
        tools.extend([
            {
                "name": "tent_community_message",
                "description": "向 Tent OS AI 社区发送消息，与 AI 居民交流。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to_ai_id": {"type": "string", "description": "目标 AI 居民 ID"},
                        "content": {"type": "string", "description": "消息内容"}
                    },
                    "required": ["to_ai_id", "content"]
                }
            },
            {
                "name": "tent_community_resident_list",
                "description": "列出 Tent OS AI 社区中的所有居民。",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "tent_task_submit",
                "description": "向 Tent OS 提交一个任务。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "任务描述"},
                        "user_id": {"type": "string", "description": "用户 ID（可选）"}
                    },
                    "required": ["task"]
                }
            }
        ])
        return tools

    async def _execute_tool(self, name: str, arguments: Dict) -> Dict:
        """执行工具调用"""
        # AI 社会专用工具
        if name == "tent_community_message":
            return await self._exec_community_message(arguments)
        if name == "tent_community_resident_list":
            return await self._exec_community_resident_list()
        if name == "tent_task_submit":
            return await self._exec_task_submit(arguments)

        # 标准工具
        if not self._tool_executor:
            raise RuntimeError("ToolExecutor not initialized")

        result = await self._tool_executor.execute(
            name, arguments, session_id=f"mcp_{uuid.uuid4().hex[:8]}"
        )
        return {
            "content": [{"type": "text", "text": result}],
            "isError": False
        }

    async def _exec_community_message(self, args: Dict) -> Dict:
        """执行社区消息发送"""
        db_path = "./tent_scheduler.db"
        conn = sqlite3.connect(db_path)
        to_ai_id = args["to_ai_id"]
        content = args["content"]
        from_ai_id = args.get("from_ai_id", "mcp_user")

        conn.execute(
            "INSERT INTO community_messages (from_ai_id, to_ai_id, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (from_ai_id, to_ai_id, content)
        )
        conn.commit()
        conn.close()

        return {
            "content": [{"type": "text", "text": f"消息已发送给 {to_ai_id}"}],
            "isError": False
        }

    async def _exec_community_resident_list(self) -> Dict:
        """列出社区居民"""
        db_path = "./tent_scheduler.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, name, persona, status FROM ai_residents").fetchall()
        conn.close()

        residents = [dict(r) for r in rows]
        text = "\n".join(f"- {r['name']} ({r['persona']}, {r['status']})" for r in residents)
        return {
            "content": [{"type": "text", "text": text or "暂无居民"}],
            "isError": False
        }

    async def _exec_task_submit(self, args: Dict) -> Dict:
        """提交任务"""
        return {
            "content": [{
                "type": "text",
                "text": f"任务已记录: {args.get('task', '')}。请通过 Tent OS UI (http://localhost:8002/ui/) 查看进度。"
            }],
            "isError": False
        }

    async def handle_request(self, request: Dict) -> Optional[Dict]:
        """处理 JSON-RPC 请求"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "tent-os-mcp",
                        "version": "0.1.0"
                    }
                }
            }

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self._to_mcp_tools()}
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = await self._execute_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
            except Exception as e:
                logger.error(f"[MCP] Tool execution failed: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True
                    }
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


# 全局 MCP Server 实例
_mcp_server = MCPServer()

router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.post("")
async def mcp_jsonrpc(request: Request):
    """MCP JSON-RPC endpoint"""
    body = await request.json()
    response = await _mcp_server.handle_request(body)
    if response is None:
        return JSONResponse(content={}, status_code=202)
    return JSONResponse(content=response)


@router.get("/sse")
async def mcp_sse():
    """MCP SSE endpoint (for Claude Desktop)"""
    async def event_stream():
        yield f"event: endpoint\ndata: /mcp\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def init_mcp_server():
    """初始化 MCP Server"""
    await _mcp_server.initialize()
