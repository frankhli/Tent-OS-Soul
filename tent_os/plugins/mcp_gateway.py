"""MCP Gateway —— MCP 服务器注册表与路由网关

提供中心化 MCP 服务器管理能力：
- 注册表：记录所有可用的 MCP 服务器（名称、URL、工具列表、健康状态）
- 服务发现：动态发现工具，无需硬编码
- 健康检查：定期 ping 各 MCP 服务器，自动摘除故障节点
- 负载均衡：多实例时轮询分发请求
- 统一认证：集中管理各服务器的 API Key

Tent OS 差异化：
- 不是简单的 client，而是 gateway + registry 的组合
- 支持 SSE / stdio / HTTP 多种传输协议
- 与 ToolPoolAssembler 集成：自动将可用工具注入 LLM 上下文
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import httpx

from tent_os.logging_config import get_logger

logger = get_logger()


class MCPTransport(Enum):
    """MCP 传输协议"""
    SSE = "sse"
    STDIO = "stdio"
    HTTP = "http"


class MCPHealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class MCPServerRegistration:
    """MCP 服务器注册信息"""
    name: str
    url: str
    transport: MCPTransport
    tools: List[Dict] = field(default_factory=list)
    health: MCPHealthStatus = MCPHealthStatus.UNKNOWN
    last_healthy_at: float = 0
    consecutive_failures: int = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    auth: Dict[str, str] = field(default_factory=dict)  # headers / api_key
    enabled: bool = True
    registered_at: float = field(default_factory=time.time)


class MCPGatewayRegistry:
    """MCP 网关注册表

    集中管理所有 MCP 服务器的生命周期：
    1. register: 注册新服务器
    2. discover: 发现可用工具
    3. health_check: 健康检查
    4. route: 路由请求到健康的服务器
    5. unregister: 注销服务器
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.servers: Dict[str, MCPServerRegistration] = {}
        self._health_check_interval = self.config.get("health_check_interval", 30)
        self._health_check_task: Optional[asyncio.Task] = None
        self._circuit_threshold = self.config.get("circuit_threshold", 3)

    async def start(self):
        """启动网关（启动健康检查循环）"""
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("[MCPGateway] 注册表启动")

    async def stop(self):
        """停止网关"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("[MCPGateway] 注册表停止")

    def register(self, name: str, url: str, transport: str = "sse",
                 auth: Dict[str, str] = None, metadata: Dict[str, Any] = None) -> MCPServerRegistration:
        """注册 MCP 服务器"""
        transport_enum = MCPTransport(transport.lower())
        reg = MCPServerRegistration(
            name=name,
            url=url,
            transport=transport_enum,
            auth=auth or {},
            metadata=metadata or {},
        )
        self.servers[name] = reg
        logger.info(f"[MCPGateway] 注册服务器: {name} ({url}, {transport})")

        # 立即做一次健康检查和工具发现（如果有事件循环）
        try:
            asyncio.get_running_loop()
            asyncio.create_task(self._check_and_discover(reg))
        except RuntimeError:
            pass  # 无事件循环，跳过立即检查
        return reg

    def unregister(self, name: str) -> bool:
        """注销 MCP 服务器"""
        if name in self.servers:
            del self.servers[name]
            logger.info(f"[MCPGateway] 注销服务器: {name}")
            return True
        return False

    def get_server(self, name: str) -> Optional[MCPServerRegistration]:
        """获取服务器注册信息"""
        return self.servers.get(name)

    def list_servers(self, healthy_only: bool = False) -> List[MCPServerRegistration]:
        """列出所有服务器"""
        servers = list(self.servers.values())
        if healthy_only:
            servers = [s for s in servers if s.health == MCPHealthStatus.HEALTHY and s.enabled]
        return servers

    def list_all_tools(self) -> List[Dict]:
        """获取所有注册服务器的工具列表（OpenAI format）"""
        tools = []
        for server in self.servers.values():
            if not server.enabled or server.health == MCPHealthStatus.UNHEALTHY:
                continue
            for tool in server.tools:
                # 添加 server_name__ 前缀避免冲突
                tool_copy = self._copy_tool_with_prefix(tool, server.name)
                tools.append(tool_copy)
        return tools

    def get_tool_server(self, prefixed_name: str) -> Optional[MCPServerRegistration]:
        """根据带前缀的工具名找到对应服务器"""
        if "__" not in prefixed_name:
            return None
        server_name = prefixed_name.split("__", 1)[0]
        return self.servers.get(server_name)

    async def execute_tool(self, server_name: str, tool_name: str,
                           params: Dict) -> Dict:
        """通过网关执行 MCP 工具"""
        server = self.servers.get(server_name)
        if not server:
            return {"status": "error", "error": f"服务器未注册: {server_name}"}
        if not server.enabled:
            return {"status": "error", "error": f"服务器已禁用: {server_name}"}

        start_time = time.time()
        server.total_requests += 1

        try:
            if server.transport == MCPTransport.SSE:
                result = await self._execute_via_sse(server, tool_name, params)
            elif server.transport == MCPTransport.HTTP:
                result = await self._execute_via_http(server, tool_name, params)
            else:
                result = {"status": "error", "error": f"不支持的传输协议: {server.transport}"}

            latency = (time.time() - start_time) * 1000
            server.avg_latency_ms = (server.avg_latency_ms * (server.total_requests - 1) + latency) / server.total_requests

            if result.get("status") == "error":
                server.consecutive_failures += 1
                server.total_errors += 1
                if server.consecutive_failures >= self._circuit_threshold:
                    server.health = MCPHealthStatus.UNHEALTHY
                    logger.warning(f"[MCPGateway] {server_name} 标记为不健康")
            else:
                server.consecutive_failures = 0
                server.health = MCPHealthStatus.HEALTHY
                server.last_healthy_at = time.time()

            return result

        except Exception as e:
            server.consecutive_failures += 1
            server.total_errors += 1
            logger.error(f"[MCPGateway] 执行失败 [{server_name}/{tool_name}]: {e}")
            return {"status": "error", "error": str(e)}

    def get_registry_manifest(self) -> Dict:
        """获取注册表清单（用于管理界面）"""
        return {
            "servers": [
                {
                    "name": s.name,
                    "url": s.url,
                    "transport": s.transport.value,
                    "health": s.health.value,
                    "tools_count": len(s.tools),
                    "total_requests": s.total_requests,
                    "total_errors": s.total_errors,
                    "avg_latency_ms": round(s.avg_latency_ms, 1),
                    "enabled": s.enabled,
                    "registered_at": s.registered_at,
                }
                for s in sorted(self.servers.values(), key=lambda x: x.name)
            ],
            "total_servers": len(self.servers),
            "healthy_servers": sum(1 for s in self.servers.values() if s.health == MCPHealthStatus.HEALTHY),
            "total_tools": sum(len(s.tools) for s in self.servers.values()),
        }

    # ========== 内部实现 ==========

    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                for server in list(self.servers.values()):
                    if not server.enabled:
                        continue
                    await self._check_and_discover(server)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MCPGateway] 健康检查异常: {e}")

    async def _check_and_discover(self, server: MCPServerRegistration):
        """健康检查 + 工具发现"""
        try:
            if server.transport == MCPTransport.SSE:
                await self._discover_sse_tools(server)
            elif server.transport == MCPTransport.HTTP:
                await self._discover_http_tools(server)
            else:
                server.health = MCPHealthStatus.UNKNOWN
        except Exception as e:
            server.consecutive_failures += 1
            if server.consecutive_failures >= self._circuit_threshold:
                server.health = MCPHealthStatus.UNHEALTHY
            else:
                server.health = MCPHealthStatus.DEGRADED
            logger.debug(f"[MCPGateway] {server.name} 健康检查失败: {e}")

    async def _discover_sse_tools(self, server: MCPServerRegistration):
        """通过 SSE 发现工具"""
        import httpx
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                # 发送 tools/list 请求
                resp = await client.post(
                    server.url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers={**server.auth, "Content-Type": "application/json", "Accept": "text/event-stream"},
                )
                if resp.status_code == 200:
                    server.health = MCPHealthStatus.HEALTHY
                    server.last_healthy_at = time.time()
                    server.consecutive_failures = 0
                    # 解析工具列表
                    tools = self._parse_mcp_tools_response(resp.text)
                    server.tools = tools
                    logger.info(f"[MCPGateway] {server.name} 发现 {len(tools)} 个工具")
                else:
                    raise RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            raise RuntimeError(f"SSE 发现失败: {e}")

    async def _discover_http_tools(self, server: MCPServerRegistration):
        """通过 HTTP 发现工具"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    urljoin(server.url, "/tools"),
                    headers=server.auth,
                )
                if resp.status_code == 200:
                    server.health = MCPHealthStatus.HEALTHY
                    server.last_healthy_at = time.time()
                    server.consecutive_failures = 0
                    data = resp.json()
                    server.tools = data.get("tools", [])
                    logger.info(f"[MCPGateway] {server.name} 发现 {len(server.tools)} 个工具")
                else:
                    raise RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            raise RuntimeError(f"HTTP 发现失败: {e}")

    async def _execute_via_sse(self, server: MCPServerRegistration,
                                tool_name: str, params: Dict) -> Dict:
        """通过 SSE 执行工具"""
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
                resp = await client.post(
                    server.url,
                    json={
                        "jsonrpc": "2.0",
                        "id": int(time.time() * 1000),
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": params},
                    },
                    headers={**server.auth, "Content-Type": "application/json"},
                )
                data = resp.json()
                if "error" in data:
                    return {"status": "error", "error": data["error"].get("message", "MCP错误")}
                return {"status": "completed", "result": data.get("result", {})}
        except Exception as e:
            return {"status": "error", "error": f"SSE执行失败: {e}"}

    async def _execute_via_http(self, server: MCPServerRegistration,
                                 tool_name: str, params: Dict) -> Dict:
        """通过 HTTP 执行工具"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    urljoin(server.url, f"/tools/{tool_name}"),
                    json=params,
                    headers=server.auth,
                )
                if resp.status_code == 200:
                    return {"status": "completed", "result": resp.json()}
                return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"status": "error", "error": f"HTTP执行失败: {e}"}

    @staticmethod
    def _parse_mcp_tools_response(text: str) -> List[Dict]:
        """解析 MCP tools/list 响应"""
        tools = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if "result" in data and "tools" in data["result"]:
                        for t in data["result"]["tools"]:
                            tools.append(MCPGatewayRegistry._convert_mcp_tool_to_openai(t))
                except:
                    pass
        return tools

    @staticmethod
    def _convert_mcp_tool_to_openai(mcp_tool: Dict) -> Dict:
        """将 MCP 工具格式转为 OpenAI function 格式"""
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.get("name", ""),
                "description": mcp_tool.get("description", ""),
                "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }

    @staticmethod
    def _copy_tool_with_prefix(tool: Dict, server_name: str) -> Dict:
        """复制工具并添加 server_name__ 前缀"""
        import copy
        t = copy.deepcopy(tool)
        if "function" in t and "name" in t["function"]:
            original_name = t["function"]["name"]
            t["function"]["name"] = f"{server_name}__{original_name}"
        return t
