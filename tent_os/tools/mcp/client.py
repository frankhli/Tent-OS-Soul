"""MCP (Model Context Protocol) Client — stdio 传输实现

基于 JSON-RPC 2.0，通过子进程 stdin/stdout 与 MCP Server 通信。
支持工具发现、调用、资源读取。

MCP 协议规范: https://modelcontextprotocol.io
"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("tent_os.tools.mcp")


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict
    server_name: str = ""


@dataclass
class MCPResource:
    """MCP 资源定义"""
    uri: str
    name: str
    mime_type: str = ""
    description: str = ""


@dataclass
class MCPServerConfig:
    """MCP Server 配置"""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPClient:
    """MCP Client —— 通过 stdio 与 MCP Server 通信"""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self.tools: List[MCPTool] = []
        self.resources: List[MCPResource] = []
        self._initialized = False
        self._read_task: Optional[asyncio.Task] = None

    async def connect(self, timeout: float = 10.0) -> bool:
        """启动 MCP Server 进程并建立连接"""
        try:
            env = {**dict(subprocess.os.environ), **self.config.env}
            self.process = subprocess.Popen(
                [self.config.command, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=False,
            )
            # 将同步管道包装为异步流
            loop = asyncio.get_event_loop()
            self._reader = asyncio.StreamReader()
            await loop.connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(self._reader),
                self.process.stdout,
            )
            # 启动读取循环
            self._read_task = asyncio.create_task(self._read_loop())
            # 发送 initialize 请求
            init_result = await self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False},
                },
                "clientInfo": {"name": "tent-os", "version": "3.0.0"},
            }, timeout=timeout)
            if init_result is None:
                logger.error(f"[MCP] {self.config.name} initialize 失败")
                await self.disconnect()
                return False
            # 发送 initialized 通知
            await self._notify("notifications/initialized", {})
            self._initialized = True
            logger.info(f"[MCP] {self.config.name} 连接成功，协议版本: {init_result.get('protocolVersion', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"[MCP] {self.config.name} 连接失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self):
        """断开连接并清理资源"""
        self._initialized = False
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(0.5)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass
        self.process = None
        logger.info(f"[MCP] {self.config.name} 已断开")

    async def list_tools(self, timeout: float = 10.0) -> List[MCPTool]:
        """获取 MCP Server 提供的工具列表"""
        if not self._initialized:
            return []
        result = await self._request("tools/list", {}, timeout=timeout)
        if not result:
            return []
        raw_tools = result.get("tools", [])
        self.tools = [
            MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=self.config.name,
            )
            for t in raw_tools
        ]
        return self.tools

    async def call_tool(self, name: str, arguments: Dict, timeout: float = 30.0) -> Dict:
        """调用 MCP 工具"""
        if not self._initialized:
            return {"error": "MCP Client 未初始化"}
        result = await self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        }, timeout=timeout)
        if result is None:
            return {"error": "工具调用超时或失败"}
        return result

    async def list_resources(self, timeout: float = 10.0) -> List[MCPResource]:
        """获取资源列表"""
        if not self._initialized:
            return []
        result = await self._request("resources/list", {}, timeout=timeout)
        if not result:
            return []
        raw = result.get("resources", [])
        self.resources = [
            MCPResource(
                uri=r["uri"],
                name=r.get("name", ""),
                mime_type=r.get("mimeType", ""),
                description=r.get("description", ""),
            )
            for r in raw
        ]
        return self.resources

    async def read_resource(self, uri: str, timeout: float = 10.0) -> Dict:
        """读取资源内容"""
        if not self._initialized:
            return {"error": "MCP Client 未初始化"}
        result = await self._request("resources/read", {"uri": uri}, timeout=timeout)
        if result is None:
            return {"error": "资源读取超时或失败"}
        return result

    # ========== 内部方法 ==========

    async def _read_loop(self):
        """持续从 stdout 读取 JSON-RPC 消息"""
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.debug(f"[MCP] 收到非 JSON 行: {line[:200]}")
                except Exception as e:
                    logger.debug(f"[MCP] 消息处理错误: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[MCP] 读取循环异常: {e}")

    async def _handle_message(self, msg: Dict):
        """处理从 Server 收到的消息"""
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if "error" in msg:
                future.set_exception(Exception(msg["error"].get("message", "Unknown error")))
            else:
                future.set_result(msg.get("result", {}))
        elif "method" in msg:
            # Server 发送的通知/请求（如 tools/listChanged）
            logger.debug(f"[MCP] Server 通知: {msg.get('method')}")

    async def _request(self, method: str, params: Dict, timeout: float = 10.0) -> Optional[Dict]:
        """发送 JSON-RPC 请求并等待响应"""
        self._request_id += 1
        req_id = self._request_id
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        try:
            await self._send(msg)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            logger.warning(f"[MCP] {self.config.name} 请求超时: {method}")
            return None
        except Exception as e:
            self._pending.pop(req_id, None)
            logger.warning(f"[MCP] {self.config.name} 请求失败 {method}: {e}")
            return None

    async def _notify(self, method: str, params: Dict):
        """发送 JSON-RPC 通知（无需响应）"""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(msg)

    async def _send(self, msg: Dict):
        """发送消息到 Server 的 stdin"""
        if not self.process or self.process.stdin.closed:
            raise RuntimeError("MCP Server 进程未运行")
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        self.process.stdin.flush()
