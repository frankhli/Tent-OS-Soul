"""MCPClient —— Model Context Protocol 客户端适配器

让 Tent OS 零代码接入任意 MCP Server：
1. 通过 YAML 配置连接 MCP Server（stdio 或 SSE 模式）
2. 自动发现 tools/list，注册为 Tent OS 执行者
3. 通过标准 MCP 协议调用工具

配置示例（config/tent_os.yaml）:
    plugins:
      - module: tent_os.plugins.mcp_client
        class: MCPClientPlugin
        config:
          name: filesystem
          transport: stdio
          command: python
          args: ["-m", "mcp_server_filesystem", "/tmp"]
      - module: tent_os.plugins.mcp_client
        class: MCPClientPlugin
        config:
          name: weather_api
          transport: sse
          url: http://localhost:3000/sse
"""

import asyncio
import json
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

import httpx

from tent_os.plugins.base import ExecutorPlugin


class MCPError(Exception):
    """MCP 协议错误"""
    pass


class MCPClientPlugin(ExecutorPlugin):
    """MCP 客户端插件——将外部 MCP Server 接入 Tent OS"""

    def __init__(self):
        self._name = "mcp"
        self._version = "1.0.0"
        self.transport = "stdio"
        self.command: Optional[str] = None
        self.args: List[str] = []
        self.url: Optional[str] = None
        self.headers: Dict[str, str] = {}
        self._tools: List[Dict] = []
        self._initialized = False
        self._request_counter = 0

        # stdio 模式用的子进程
        self._proc: Optional[subprocess.Process] = None
        self._stdio_lock = asyncio.Lock()

        # sse 模式用的 session
        self._sse_session: Optional[httpx.AsyncClient] = None
        self._sse_endpoint: Optional[str] = None

    def name(self) -> str:
        return self._name

    def version(self) -> str:
        return self._version

    async def initialize(self, config: Dict) -> None:
        """初始化 MCP 连接"""
        self._name = config.get("name", "mcp")
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command")
        self.args = config.get("args", [])
        self.url = config.get("url")
        self.headers = config.get("headers", {})

        if self.transport == "stdio":
            await self._init_stdio()
        elif self.transport == "sse":
            await self._init_sse()
        else:
            raise MCPError(f"不支持的传输方式: {self.transport}")

        # 发现工具
        self._tools = await self._list_tools()
        self._initialized = True

    # ── 传输层 ───────────────────────────────────────────────

    async def _init_stdio(self):
        """初始化 stdio 传输"""
        if not self.command:
            raise MCPError("stdio 模式需要配置 command")

        self._proc = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 发送 initialize 请求
        result = await self._request_stdio({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tent-os-mcp", "version": "1.0.0"},
            },
        })

        # 发送 initialized 通知
        await self._notify_stdio({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

    async def _init_sse(self):
        """初始化 SSE 传输"""
        if not self.url:
            raise MCPError("sse 模式需要配置 url")

        # SSE 第一步：GET /sse 获取 endpoint
        async with httpx.AsyncClient(trust_env=False) as client:
            async with client.stream("GET", self.url, headers=self.headers, timeout=30) as response:
                if response.status_code != 200:
                    raise MCPError(f"SSE 握手失败：HTTP {response.status_code}")
                
                endpoint = None
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if line.startswith("event: endpoint"):
                        # 下一行是 data: /message?session_id=xxx
                        pass
                    elif line.startswith("data: ") and endpoint is None:
                        endpoint = line[6:].strip()
                        break

                if not endpoint:
                    raise MCPError("SSE 握手失败：未获取到 endpoint")

        # 拼接完整 endpoint URL
        self._sse_endpoint = urljoin(self.url, endpoint)
        self._sse_session = httpx.AsyncClient(headers=self.headers, timeout=30, trust_env=False)

        # 发送 initialize
        result = await self._request_sse({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tent-os-mcp", "version": "1.0.0"},
            },
        })

        # 发送 initialized 通知
        await self._notify_sse({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

    # ── JSON-RPC 请求 ─────────────────────────────────────────

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def _request_stdio(self, request: Dict) -> Dict:
        """通过 stdio 发送请求并等待响应"""
        async with self._stdio_lock:
            req_json = json.dumps(request) + "\n"
            self._proc.stdin.write(req_json.encode())
            await self._proc.stdin.drain()

            # 读取响应（单行 JSON）
            line = await self._proc.stdout.readline()
            if not line:
                raise MCPError("MCP Server 断开连接")

            response = json.loads(line.decode())
            if "error" in response:
                raise MCPError(f"MCP Error: {response['error']}")
            return response.get("result", {})

    async def _notify_stdio(self, notification: Dict) -> None:
        """通过 stdio 发送通知（无需响应）"""
        async with self._stdio_lock:
            notif_json = json.dumps(notification) + "\n"
            self._proc.stdin.write(notif_json.encode())
            await self._proc.stdin.drain()

    async def _request_sse(self, request: Dict) -> Dict:
        """通过 SSE POST 发送请求"""
        response = await self._sse_session.post(
            self._sse_endpoint,
            json=request,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise MCPError(f"MCP Error: {data['error']}")
        return data.get("result", {})

    async def _notify_sse(self, notification: Dict) -> None:
        """通过 SSE POST 发送通知"""
        await self._sse_session.post(self._sse_endpoint, json=notification)

    # ── 工具发现与调用 ────────────────────────────────────────

    async def _list_tools(self) -> List[Dict]:
        """获取 MCP Server 的工具列表"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
        }
        if self.transport == "stdio":
            result = await self._request_stdio(request)
        else:
            result = await self._request_sse(request)
        return result.get("tools", [])

    async def _call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """调用 MCP 工具"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        if self.transport == "stdio":
            result = await self._request_stdio(request)
        else:
            result = await self._request_sse(request)
        return result

    def _convert_mcp_schema_to_openai(self, mcp_tool: Dict) -> Dict:
        """Convert MCP inputSchema to OpenAI function schema"""
        return {
            "type": "function",
            "function": {
                "name": mcp_tool["name"],
                "description": mcp_tool.get("description", ""),
                "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
            }
        }

    def get_tools(self, session_id: str = "") -> List[Dict]:
        """Return tools in OpenAI function-calling format"""
        if not self._initialized:
            return []
        return [self._convert_mcp_schema_to_openai(t) for t in self._tools]

    # ── ExecutorPlugin 接口 ───────────────────────────────────

    def supported_actions(self) -> list:
        """返回 MCP Server 提供的所有工具名"""
        if not self._initialized:
            return []
        return [t["name"] for t in self._tools]

    async def execute(self, action: str, params: Dict) -> Dict:
        """执行 MCP 工具调用

        action: MCP 工具名（支持带 server 前缀，如 server_name__tool_name）
        params: 工具参数（会去掉 task_id 等内部字段）
        """
        task_id = params.get("task_id", str(uuid.uuid4()))

        # 过滤掉内部参数
        tool_args = {k: v for k, v in params.items() if k not in ("task_id",)}

        # 去掉 server name 前缀（如果存在）
        prefix = f"{self._name}__"
        if action.startswith(prefix):
            action = action[len(prefix):]

        try:
            result = await self._call_tool(action, tool_args)
            return {"status": "completed", "task_id": task_id, "result": result}
        except Exception as e:
            return {"status": "failed", "error": str(e), "task_id": task_id}

    async def get_status(self, task_id: str) -> Dict:
        """MCP 工具调用是同步的"""
        return {"task_id": task_id, "status": "completed", "executor": self._name}

    async def shutdown(self):
        """关闭 MCP 连接"""
        if self.transport == "stdio" and self._proc:
            self._proc.terminate()
            await self._proc.wait()
        elif self.transport == "sse" and self._sse_session:
            await self._sse_session.aclose()
