"""Tool Executor —— 统一工具执行入口

职责：
1. 接收 LLM 发出的 tool_call，路由到对应执行者
2. 执行工具并返回结果（JSON 字符串）
3. 安全：执行前检查 PolicyEngine，记录日志
"""

import json
import logging
from typing import Dict, Any, List, Optional

from tent_os.tools.definitions import get_executor_for_tool

logger = logging.getLogger("tent_os.tools")


class ToolExecutor:
    """工具执行器 —— 将 LLM 的 tool_call 映射到实际执行
    
    支持自定义工具注册：skill 可以注册自己的 Python 函数作为工具。
    """
    
    def __init__(self, local_executor=None, memory_store=None, browser_executor=None,
                 embedding_client=None):
        """
        Args:
            local_executor: LocalExecutor 实例（处理 shell/file/http 等）
            memory_store: TieredMemoryStore 实例（处理 memory_search/memory_get）
            browser_executor: BrowserExecutor 实例（处理浏览器操作）
            embedding_client: EmbeddingClient 实例（用于记忆向量搜索）
        """
        self.local = local_executor
        self.memory = memory_store
        self.browser = browser_executor
        self.embedding_client = embedding_client  # 向量搜索用
        self.mcp = None  # MCP Server 管理器（动态注入）
        self._execution_count: Dict[str, int] = {}  # 会话级工具调用计数
        self._custom_tools: Dict[str, callable] = {}  # 自定义工具注册表
        self._custom_tool_schemas: Dict[str, Dict] = {}  # 自定义工具的 schema
        self._scheduler_proxy: Optional[callable] = None  # 调度进程代理（物理执行者）
    
    def set_mcp_manager(self, mcp_manager):
        """设置 MCP Server 管理器（延迟注入，避免循环依赖）"""
        self.mcp = mcp_manager
        logger.info(f"[TOOL] MCP 管理器已注入，当前 {len(mcp_manager.get_all_tools())} 个 MCP 工具可用")
    
    def register_tool(self, name: str, handler: callable, schema: Dict = None):
        """注册自定义工具
        
        Args:
            name: 工具名（LLM 调用时使用）
            handler: 工具执行函数，签名: async def handler(arguments: Dict) -> Dict
            schema: OpenAI function calling 格式的 schema（可选）
        """
        self._custom_tools[name] = handler
        if schema:
            self._custom_tool_schemas[name] = schema
        logger.info(f"[TOOL] 注册自定义工具: {name}")
    
    def get_custom_tool_schemas(self) -> List[Dict]:
        """获取所有自定义工具的 schema 列表"""
        schemas = []
        for name, schema in self._custom_tool_schemas.items():
            s = dict(schema)
            s["function"] = dict(s.get("function", {}))
            s["function"]["name"] = name
            schemas.append(s)
        return schemas
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any],
                      session_id: str = "", max_calls: int = 100) -> str:
        """执行工具调用
        
        Args:
            tool_name: 工具名
            arguments: 工具参数
            session_id: 会话 ID（用于计数和日志）
            max_calls: 单会话工具调用上限（默认 100，PPT 生成等复杂任务需要更多）
        
        Returns:
            JSON 字符串格式的执行结果
        """
        # 计数限制：单会话最多 max_calls 次工具调用
        count = self._execution_count.get(session_id, 0) + 1
        if count > max_calls:
            return json.dumps({
                "status": "error",
                "error": f"单会话工具调用次数超过上限（{max_calls}次），请简化任务或分步执行。"
            }, ensure_ascii=False)
        self._execution_count[session_id] = count
        
        logger.info(f"[TOOL] 执行 {tool_name} [{session_id}] args={arguments}")
        
        try:
            result = await self._execute_internal(tool_name, arguments)
            logger.info(f"[TOOL] {tool_name} 完成 [{session_id}]")
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TOOL] {tool_name} 失败 [{session_id}]: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "tool": tool_name,
            }, ensure_ascii=False)
    
    async def _execute_internal(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """内部执行路由"""
        # 优先检查自定义工具
        if tool_name in self._custom_tools:
            handler = self._custom_tools[tool_name]
            result = await handler(arguments)
            if isinstance(result, dict):
                if "status" in result:
                    return result
                return {"status": "completed", "result": result}
            return {"status": "completed", "result": str(result)}
        
        # 检查 MCP 工具（外部 MCP Server 提供的工具）
        if self.mcp:
            mcp_result = await self.mcp.call_tool_any(tool_name, arguments)
            if "error" not in mcp_result:
                # MCP 返回格式: {"content": [...], "isError": bool}
                contents = mcp_result.get("content", [])
                texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
                return {
                    "status": "completed",
                    "result": "\n".join(texts) if texts else json.dumps(mcp_result, ensure_ascii=False),
                    "source": "mcp",
                }
            # 如果 call_tool_any 返回 error，继续尝试本地工具（可能名称冲突或 Server 未连接）
        
        executor_id = get_executor_for_tool(tool_name)
        
        # FIX: 物理执行者通过调度进程代理路由
        if executor_id in ("realman", "flashex", "scheduler") and self._scheduler_proxy:
            return await self._execute_scheduler(tool_name, arguments)
        
        if executor_id == "local" and self.local:
            return await self._execute_local(tool_name, arguments)
        elif executor_id == "memory" and self.memory:
            return await self._execute_memory(tool_name, arguments)
        elif executor_id == "web":
            return await self._execute_web(tool_name, arguments)
        elif executor_id == "browser" and self.browser:
            return await self._execute_browser(tool_name, arguments)
        else:
            return {
                "status": "error",
                "error": f"工具 {tool_name} 的执行者 ({executor_id}) 未配置"
            }
    
    async def _execute_scheduler(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """通过调度进程代理执行物理执行者任务"""
        if not self._scheduler_proxy:
            return {"status": "error", "error": "调度进程代理未配置"}
        
        # 映射工具名到 executor_id 和 action
        if tool_name == "realman":
            executor_id = "realman"
            action = arguments.get("action", "move")
            params = {k: v for k, v in arguments.items() if k != "action"}
        elif tool_name == "flashex":
            executor_id = "flashex"
            action = arguments.get("action", "deliver")
            params = {k: v for k, v in arguments.items() if k != "action"}
        elif tool_name == "scheduler_dispatch":
            executor_id = arguments.get("executor_id", "")
            action = arguments.get("action", "")
            params = arguments.get("params", {})
        else:
            return {"status": "error", "error": f"未知的调度工具: {tool_name}"}
        
        try:
            result = await self._scheduler_proxy(executor_id, action, params)
            return result
        except Exception as e:
            return {"status": "error", "error": f"调度执行失败: {e}"}
    
    async def _execute_local(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """通过 LocalExecutor 执行本地工具"""
        from tent_os.scheduler.executors.local import RequireApprovalError

        # LocalExecutor 的 action 映射
        action_map = {
            "shell": "shell",
            "file_read": "file_read",
            "file_write": "file_write",
            "directory_list": "directory_list",
            "http_request": "http_request",
        }
        action = action_map.get(tool_name, tool_name)
        
        try:
            result = await self.local.execute(action, arguments)
        except RequireApprovalError as e:
            # 内联确认：返回需要确认标记，不直接报错
            return {
                "status": "need_confirmation",
                "message": str(e),
                "operation": e.operation,
                "details": e.details,
                "hint": "用户确认后，请在下一轮工具调用中传入参数 __confirmed: true",
            }
        
        # 标准化返回格式
        if isinstance(result, dict):
            if "status" in result:
                # FIX: shell 命令 returncode != 0 时，明确标记为 error，并把 stderr/stdout 提上来
                if action == "shell" and result.get("status") == "completed":
                    inner = result.get("result", {})
                    if isinstance(inner, dict) and inner.get("returncode", 0) != 0:
                        stderr = inner.get("stderr", "")[:2000]
                        stdout = inner.get("stdout", "")[:2000]
                        return {
                            "status": "error",
                            "error": f"命令执行失败（退出码 {inner['returncode']}）\n\nSTDERR:\n{stderr}\n\nSTDOUT:\n{stdout}",
                            "command": inner.get("command", ""),
                            "returncode": inner["returncode"],
                        }
                return result
            return {"status": "completed", "result": result}
        return {"status": "completed", "result": str(result)}
    
    async def _execute_memory(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """通过 TieredMemoryStore 执行记忆工具

        修复：使用向量语义搜索替代关键词匹配。
        如果 embedding_client 不可用，优雅降级到关键词匹配。
        """
        if tool_name == "memory_search":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            persona = arguments.get("persona")

            if not query:
                return {"status": "completed", "query": "", "results": [], "total": 0}

            # ===== 主路径：向量语义搜索 =====
            if self.embedding_client and self.memory:
                try:
                    # 1. 生成查询向量
                    query_vector = await self.embedding_client.embed(query)
                    if query_vector:
                        # 2. 向量搜索（只搜 L0 层）
                        results = self.memory.search(
                            query_vector=query_vector,
                            limit=limit,
                            persona=persona,
                        )
                        return {
                            "status": "completed",
                            "query": query,
                            "results": results,
                            "total": len(results),
                            "search_type": "vector",
                        }
                except Exception as e:
                    logger.warning(f"[TOOL] 向量搜索失败，降级到关键词匹配: {e}")

            # ===== 降级路径：关键词匹配 =====
            try:
                all_memories = self.memory.get_recent(limit=100)
                query_lower = query.lower()
                query_words = set(query_lower.split())

                scored = []
                for mem in all_memories:
                    abstract = mem.get("abstract", "").lower()
                    score = 0
                    for word in query_words:
                        if len(word) > 1 and word in abstract:
                            score += 1
                    if score > 0:
                        scored.append((score, mem))

                scored.sort(key=lambda x: x[0], reverse=True)
                results = scored[:limit]

                return {
                    "status": "completed",
                    "query": query,
                    "results": [
                        {
                            "uri": mem.get("uri", ""),
                            "abstract": mem.get("abstract", ""),
                            "memory_type": mem.get("memory_type", ""),
                            "created_at": mem.get("created_at", ""),
                        }
                        for _, mem in results
                    ],
                    "total": len(results),
                    "search_type": "keyword_fallback",
                }
            except Exception as e:
                return {"status": "error", "error": f"记忆搜索失败: {e}"}
        
        elif tool_name == "memory_get":
            uri = arguments.get("uri", "")
            try:
                content = self.memory.read_l2_content(uri)
                if content is None:
                    return {"status": "error", "error": f"未找到记忆: {uri}"}
                return {
                    "status": "completed",
                    "uri": uri,
                    "content": content,
                }
            except Exception as e:
                return {"status": "error", "error": f"读取记忆失败: {e}"}
        
        return {"status": "error", "error": f"未知的记忆工具: {tool_name}"}
    
    async def _execute_browser(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """通过 BrowserExecutor 执行浏览器工具"""
        if not self.browser:
            return {"status": "error", "error": "BrowserExecutor 未配置"}
        
        # 映射 tool_name 到 BrowserExecutor 的 action
        action_map = {
            "browser_navigate": "browser_navigate",
            "browser_click": "browser_click",
            "browser_type": "browser_type",
            "browser_read": "browser_read",
            "browser_screenshot": "browser_screenshot",
        }
        action = action_map.get(tool_name, tool_name)
        
        result = await self.browser.execute(action, arguments)
        
        # 标准化返回格式
        if isinstance(result, dict):
            if "status" in result:
                return result
            return {"status": "completed", "result": result}
        return {"status": "completed", "result": str(result)}
    
    async def _execute_web(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Web 工具（搜索/抓取）"""
        from tent_os.tools.web_tools import web_search, web_fetch
        
        if tool_name == "web_search":
            return await web_search(
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 5),
            )
        elif tool_name == "web_fetch":
            return await web_fetch(
                url=arguments.get("url", ""),
                max_chars=arguments.get("max_chars", 8000),
            )
        else:
            return {"status": "error", "error": f"未知的 Web 工具: {tool_name}"}

    def set_scheduler_proxy(self, proxy: callable):
        """设置调度进程代理（用于物理执行者调用）
        
        Args:
            proxy: async def proxy(executor_id: str, action: str, params: Dict) -> Dict
        """
        self._scheduler_proxy = proxy
        
    def reset_session(self, session_id: str):
        """重置会话的工具调用计数"""
        self._execution_count[session_id] = 0
        
    def _audit_log(self, session_id: str, tool_name: str, arguments: Dict, result: Dict):
        """记录工具调用审计日志到 SQLite"""
        try:
            import sqlite3
            from datetime import datetime
            db = sqlite3.connect("./tent_scheduler.db")
            db.execute("""
                CREATE TABLE IF NOT EXISTS tool_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    session_id TEXT,
                    tool_name TEXT,
                    arguments TEXT,
                    status TEXT,
                    result_summary TEXT
                )
            """)
            summary = result.get("error", str(result.get("result", ""))[:200])
            db.execute(
                "INSERT INTO tool_audit_log (timestamp, session_id, tool_name, arguments, status, result_summary) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), session_id, tool_name,
                 json.dumps(arguments, ensure_ascii=False)[:500],
                 result.get("status", "unknown"), summary)
            )
            db.commit()
            db.close()
        except Exception:
            pass  # 审计失败不阻塞主流程
