"""MCP Protocol —— Model Context Protocol 兼容层

基于 Anthropic MCP 规范的简化实现：
- JSON-RPC 2.0 消息格式
- Tools: 可调用的数字灵魂能力
- Resources: 只读数据（人格、记忆、关系）
- HTTP POST 传输

参考: https://modelcontextprotocol.io
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import json


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    handler: Optional[Callable] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """MCP 资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"
    handler: Optional[Callable] = None

    def to_dict(self) -> Dict:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class JSONRPCMessage:
    """JSON-RPC 2.0 消息"""
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: Optional[str] = None
    params: Optional[Dict] = None
    result: Optional[Any] = None
    error: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "JSONRPCMessage":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )

    def to_dict(self) -> Dict:
        msg = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            msg["id"] = self.id
        if self.method:
            msg["method"] = self.method
            if self.params:
                msg["params"] = self.params
        if self.result is not None:
            msg["result"] = self.result
        if self.error:
            msg["error"] = self.error
        return msg

    def is_request(self) -> bool:
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        return self.result is not None or self.error is not None

    @classmethod
    def response(cls, id: Any, result: Any = None) -> "JSONRPCMessage":
        return cls(id=id, result=result)

    @classmethod
    def error(cls, id: Any, code: int, message: str, data: Any = None) -> "JSONRPCMessage":
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return cls(id=id, error=err)


class MCPError:
    """MCP 标准错误码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP 特定错误码
    AUTH_ERROR = -32001
    RATE_LIMIT = -32002
    RESOURCE_NOT_FOUND = -32003
    TOOL_EXECUTION_ERROR = -32004
