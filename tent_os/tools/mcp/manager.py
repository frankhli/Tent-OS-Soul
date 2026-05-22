"""MCP Server 管理器

管理多个 MCP Server 连接，提供统一的工具发现和调用接口。
支持持久化配置（SQLite）、动态增删改查。
"""

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.tools.mcp.client import MCPClient, MCPServerConfig, MCPTool

logger = logging.getLogger("tent_os.tools.mcp")


class MCPServerManager:
    """MCP Server 管理器"""

    def __init__(self, db_path: str = "./tent_memory/mcp_servers.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clients: Dict[str, MCPClient] = {}
        self._init_db()

    def _init_db(self):
        """初始化配置数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    name TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    args TEXT DEFAULT '[]',
                    env TEXT DEFAULT '{}',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    # ========== 配置管理 ==========

    def add_server(self, name: str, command: str, args: List[str] = None,
                   env: Dict[str, str] = None, enabled: bool = True) -> bool:
        """添加 MCP Server 配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO mcp_servers
                       (name, command, args, env, enabled, updated_at)
                       VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                    (name, command, json.dumps(args or []), json.dumps(env or {}),
                     1 if enabled else 0)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[MCPManager] 添加 Server 失败: {e}")
            return False

    def remove_server(self, name: str) -> bool:
        """删除 MCP Server 配置"""
        try:
            # 先断开连接
            asyncio.create_task(self.disconnect_server(name))
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM mcp_servers WHERE name = ?", (name,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[MCPManager] 删除 Server 失败: {e}")
            return False

    def list_servers(self) -> List[Dict]:
        """列出所有 MCP Server 配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT name, command, args, env, enabled FROM mcp_servers ORDER BY name"
                ).fetchall()
                return [
                    {
                        "name": r["name"],
                        "command": r["command"],
                        "args": json.loads(r["args"]),
                        "env": json.loads(r["env"]),
                        "enabled": bool(r["enabled"]),
                        "connected": r["name"] in self._clients and self._clients[r["name"]]._initialized,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[MCPManager] 列出 Server 失败: {e}")
            return []

    def get_server(self, name: str) -> Optional[Dict]:
        """获取单个 Server 配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM mcp_servers WHERE name = ?", (name,)
                ).fetchone()
                if row:
                    return {
                        "name": row["name"],
                        "command": row["command"],
                        "args": json.loads(row["args"]),
                        "env": json.loads(row["env"]),
                        "enabled": bool(row["enabled"]),
                    }
        except Exception as e:
            logger.error(f"[MCPManager] 获取 Server 失败: {e}")
        return None

    # ========== 连接管理 ==========

    async def connect_server(self, name: str) -> bool:
        """连接到指定 MCP Server"""
        if name in self._clients and self._clients[name]._initialized:
            return True
        
        cfg = self.get_server(name)
        if not cfg or not cfg.get("enabled"):
            return False
        
        config = MCPServerConfig(
            name=cfg["name"],
            command=cfg["command"],
            args=cfg["args"],
            env=cfg["env"],
        )
        client = MCPClient(config)
        if await client.connect():
            self._clients[name] = client
            # 自动获取工具列表
            try:
                await client.list_tools()
                logger.info(f"[MCPManager] {name} 已连接，发现 {len(client.tools)} 个工具")
            except Exception as e:
                logger.warning(f"[MCPManager] {name} 获取工具列表失败: {e}")
            return True
        return False

    async def disconnect_server(self, name: str):
        """断开指定 MCP Server"""
        if name in self._clients:
            await self._clients[name].disconnect()
            del self._clients[name]

    async def connect_all(self):
        """连接所有启用的 MCP Server"""
        servers = self.list_servers()
        for s in servers:
            if s.get("enabled"):
                await self.connect_server(s["name"])

    async def disconnect_all(self):
        """断开所有 MCP Server"""
        for name in list(self._clients.keys()):
            await self.disconnect_server(name)

    # ========== 工具发现和调用 ==========

    def get_all_tools(self) -> List[MCPTool]:
        """获取所有已连接 Server 的工具列表"""
        tools = []
        for client in self._clients.values():
            if client._initialized:
                tools.extend(client.tools)
        return tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Dict:
        """调用指定 Server 的工具"""
        if server_name not in self._clients:
            # 尝试自动连接
            if not await self.connect_server(server_name):
                return {"error": f"MCP Server '{server_name}' 未连接"}
        client = self._clients[server_name]
        if not client._initialized:
            return {"error": f"MCP Server '{server_name}' 未初始化"}
        return await client.call_tool(tool_name, arguments)

    async def call_tool_any(self, tool_name: str, arguments: Dict) -> Dict:
        """在所有已连接 Server 中查找并调用工具（按名称匹配第一个）"""
        for name, client in self._clients.items():
            if client._initialized and any(t.name == tool_name for t in client.tools):
                return await client.call_tool(tool_name, arguments)
        return {"error": f"工具 '{tool_name}' 未在任何已连接的 MCP Server 中找到"}

    def get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """获取工具的输入 schema"""
        for client in self._clients.values():
            for t in client.tools:
                if t.name == tool_name:
                    return t.input_schema
        return None
