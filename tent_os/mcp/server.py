"""MCP Server —— 数字灵魂的对外标准接口

第三方设备（仿生机器人、智能音箱、车载系统）通过 MCP 协议
调用 Tent OS 的数字灵魂能力。

支持的传输方式：
- HTTP POST（当前实现）

支持的能力：
- Tools: chat, query_persona, query_memories, query_relations, synthesize_tts
- Resources: soul://{user_id}/persona, soul://{user_id}/memories, etc.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from tent_os.mcp.protocol import (
    JSONRPCMessage, MCPTool, MCPResource, MCPError,
)
from tent_os.logging_config import get_logger

logger = get_logger()


class MCPServer:
    """MCP Server 核心"""

    def __init__(self, state=None):
        self.state = state
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self._initialized = False
        self._client_capabilities: Optional[Dict] = None
        self._audit_log: List[Dict] = []
        self._max_audit_entries = 10000

    def register_tool(self, tool: MCPTool):
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info(f"[MCP] 工具注册: {tool.name}")

    def register_resource(self, resource: MCPResource):
        """注册资源"""
        self.resources[resource.uri] = resource
        logger.info(f"[MCP] 资源注册: {resource.uri}")

    async def handle_message(self, raw_body: str, auth_context: Optional[Dict] = None) -> Dict:
        """处理 MCP JSON-RPC 消息"""
        try:
            data = JSONRPCMessage.from_dict(__import__('json').loads(raw_body))
        except Exception as e:
            return JSONRPCMessage.error(
                None, MCPError.PARSE_ERROR, f"Parse error: {e}"
            ).to_dict()

        # 审计日志
        self._audit(data, auth_context)

        if data.method == "initialize":
            return await self._handle_initialize(data)
        elif data.method == "tools/list":
            return await self._handle_tools_list(data)
        elif data.method == "tools/call":
            return await self._handle_tools_call(data, auth_context)
        elif data.method == "resources/list":
            return await self._handle_resources_list(data)
        elif data.method == "resources/read":
            return await self._handle_resources_read(data, auth_context)
        elif data.method == "ping":
            return JSONRPCMessage.response(data.id, {}).to_dict()
        else:
            return JSONRPCMessage.error(
                data.id, MCPError.METHOD_NOT_FOUND, f"Unknown method: {data.method}"
            ).to_dict()

    async def _handle_initialize(self, msg: JSONRPCMessage) -> Dict:
        """初始化 MCP 连接"""
        params = msg.params or {}
        self._client_capabilities = params.get("capabilities", {})
        self._initialized = True

        return JSONRPCMessage.response(
            msg.id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "tent-os-soul-mcp",
                    "version": "3.0.0",
                },
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": True},
                },
            }
        ).to_dict()

    async def _handle_tools_list(self, msg: JSONRPCMessage) -> Dict:
        """列出可用工具"""
        if not self._initialized:
            return JSONRPCMessage.error(
                msg.id, MCPError.INVALID_REQUEST, "Not initialized"
            ).to_dict()

        return JSONRPCMessage.response(
            msg.id,
            {"tools": [t.to_dict() for t in self.tools.values()]}
        ).to_dict()

    async def _handle_tools_call(self, msg: JSONRPCMessage, auth_context: Optional[Dict]) -> Dict:
        """调用工具"""
        if not self._initialized:
            return JSONRPCMessage.error(
                msg.id, MCPError.INVALID_REQUEST, "Not initialized"
            ).to_dict()

        params = msg.params or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool = self.tools.get(tool_name)
        if not tool:
            return JSONRPCMessage.error(
                msg.id, MCPError.INVALID_PARAMS, f"Tool not found: {tool_name}"
            ).to_dict()

        if not tool.handler:
            return JSONRPCMessage.error(
                msg.id, MCPError.INTERNAL_ERROR, f"Tool has no handler: {tool_name}"
            ).to_dict()

        try:
            result = await tool.handler(arguments, auth_context)
            return JSONRPCMessage.response(
                msg.id,
                {"content": [{"type": "text", "text": __import__('json').dumps(result, ensure_ascii=False)}]}
            ).to_dict()
        except Exception as e:
            logger.warning(f"[MCP] 工具调用失败 [{tool_name}]: {e}")
            return JSONRPCMessage.error(
                msg.id, MCPError.TOOL_EXECUTION_ERROR, str(e)
            ).to_dict()

    async def _handle_resources_list(self, msg: JSONRPCMessage) -> Dict:
        """列出可用资源"""
        if not self._initialized:
            return JSONRPCMessage.error(
                msg.id, MCPError.INVALID_REQUEST, "Not initialized"
            ).to_dict()

        return JSONRPCMessage.response(
            msg.id,
            {"resources": [r.to_dict() for r in self.resources.values()]}
        ).to_dict()

    async def _handle_resources_read(self, msg: JSONRPCMessage, auth_context: Optional[Dict]) -> Dict:
        """读取资源"""
        if not self._initialized:
            return JSONRPCMessage.error(
                msg.id, MCPError.INVALID_REQUEST, "Not initialized"
            ).to_dict()

        params = msg.params or {}
        uri = params.get("uri", "")

        resource = self.resources.get(uri)
        if not resource:
            return JSONRPCMessage.error(
                msg.id, MCPError.RESOURCE_NOT_FOUND, f"Resource not found: {uri}"
            ).to_dict()

        if not resource.handler:
            return JSONRPCMessage.error(
                msg.id, MCPError.INTERNAL_ERROR, f"Resource has no handler: {uri}"
            ).to_dict()

        try:
            result = await resource.handler(params, auth_context)
            return JSONRPCMessage.response(
                msg.id,
                {
                    "contents": [{
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": __import__('json').dumps(result, ensure_ascii=False),
                    }]
                }
            ).to_dict()
        except Exception as e:
            logger.warning(f"[MCP] 资源读取失败 [{uri}]: {e}")
            return JSONRPCMessage.error(
                msg.id, MCPError.INTERNAL_ERROR, str(e)
            ).to_dict()

    def _audit(self, msg: JSONRPCMessage, auth_context: Optional[Dict]):
        """记录审计日志"""
        entry = {
            "timestamp": time.time(),
            "method": msg.method,
            "client": auth_context.get("client_id") if auth_context else None,
            "user": auth_context.get("user_id") if auth_context else None,
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]

    def get_audit_log(self, limit: int = 100) -> List[Dict]:
        return self._audit_log[-limit:]
