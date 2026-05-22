"""Tests for MCPGatewayRegistry —— MCP 网关注册表"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from tent_os.plugins.mcp_gateway import (
    MCPGatewayRegistry,
    MCPServerRegistration,
    MCPTransport,
    MCPHealthStatus,
)


@pytest.fixture
def gateway():
    return MCPGatewayRegistry(config={
        "health_check_interval": 1,
        "circuit_threshold": 2,
    })


@pytest.mark.unit
class TestMCPGatewayRegistry:

    def test_register_server(self, gateway):
        reg = gateway.register(
            name="test_server",
            url="http://localhost:8080",
            transport="http",
            auth={"Authorization": "Bearer test"},
            metadata={"version": "1.0"},
        )
        assert reg.name == "test_server"
        assert reg.url == "http://localhost:8080"
        assert reg.transport == MCPTransport.HTTP
        assert reg.enabled is True
        assert gateway.get_server("test_server") is reg

    def test_unregister(self, gateway):
        gateway.register("srv1", "http://a", "http")
        assert gateway.unregister("srv1") is True
        assert gateway.get_server("srv1") is None
        assert gateway.unregister("nonexistent") is False

    def test_list_servers(self, gateway):
        gateway.register("srv1", "http://a", "http")
        gateway.register("srv2", "http://b", "sse")
        servers = gateway.list_servers()
        assert len(servers) == 2

    def test_list_healthy_only(self, gateway):
        gateway.register("healthy", "http://a", "http")
        gateway.register("unhealthy", "http://b", "http")
        gateway.servers["healthy"].health = MCPHealthStatus.HEALTHY
        gateway.servers["unhealthy"].health = MCPHealthStatus.UNHEALTHY

        healthy = gateway.list_servers(healthy_only=True)
        assert len(healthy) == 1
        assert healthy[0].name == "healthy"

    def test_get_tool_server(self, gateway):
        gateway.register("myserver", "http://a", "http")
        server = gateway.get_tool_server("myserver__tool1")
        assert server is not None
        assert server.name == "myserver"

        assert gateway.get_tool_server("tool1") is None

    def test_copy_tool_with_prefix(self):
        tool = {
            "type": "function",
            "function": {"name": "read_file", "description": "Read a file"},
        }
        copied = MCPGatewayRegistry._copy_tool_with_prefix(tool, "myserver")
        assert copied["function"]["name"] == "myserver__read_file"
        # 原始工具不应被修改
        assert tool["function"]["name"] == "read_file"

    def test_convert_mcp_tool_to_openai(self):
        mcp_tool = {
            "name": "search",
            "description": "Search the web",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }
        openai_tool = MCPGatewayRegistry._convert_mcp_tool_to_openai(mcp_tool)
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "search"
        assert "parameters" in openai_tool["function"]

    def test_registry_manifest(self, gateway):
        gateway.register("srv1", "http://a", "http")
        gateway.servers["srv1"].tools = [{"name": "tool1"}, {"name": "tool2"}]
        gateway.servers["srv1"].health = MCPHealthStatus.HEALTHY
        gateway.servers["srv1"].total_requests = 10

        manifest = gateway.get_registry_manifest()
        assert manifest["total_servers"] == 1
        assert manifest["healthy_servers"] == 1
        assert manifest["total_tools"] == 2

    @pytest.mark.asyncio
    async def test_execute_tool_http(self, gateway):
        gateway.register("http_srv", "http://localhost:9000", "http")
        gateway.servers["http_srv"].tools = [
            {"type": "function", "function": {"name": "echo", "description": "Echo"}},
        ]

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json = MagicMock(return_value={"result": "ok"})
            result = await gateway.execute_tool("http_srv", "echo", {"msg": "hi"})
            assert result["status"] == "completed"
            assert result["result"] == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_execute_tool_error(self, gateway):
        gateway.register("err_srv", "http://localhost:9001", "http")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            result = await gateway.execute_tool("err_srv", "fail", {})
            assert result["status"] == "error"
            assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_unknown_server(self, gateway):
        result = await gateway.execute_tool("nonexistent", "tool", {})
        assert result["status"] == "error"
        assert "未注册" in result["error"]

    @pytest.mark.asyncio
    async def test_start_stop(self, gateway):
        with patch.object(gateway, '_health_check_loop', new_callable=AsyncMock) as mock_loop:
            await gateway.start()
            assert gateway._health_check_task is not None
            await gateway.stop()

    def test_parse_mcp_tools_response(self):
        text = 'data: {"jsonrpc":"2.0","result":{"tools":[{"name":"t1"}]}}\n\ndata: {"jsonrpc":"2.0","result":{"tools":[{"name":"t2"}]}}'
        tools = MCPGatewayRegistry._parse_mcp_tools_response(text)
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "t1"
        assert tools[1]["function"]["name"] == "t2"
