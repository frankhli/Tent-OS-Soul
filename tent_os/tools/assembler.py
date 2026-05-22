"""Tool Pool Assembler —— 工具池动态组装器

借鉴 Claude Code 的 5 步组装流程：
1. Base enumeration —— 枚举所有可用工具
2. Mode filtering —— 根据 permission mode 过滤
3. Deny rule pre-filtering —— PolicyEngine 预过滤
4. MCP integration —— 动态加载 MCP 工具
5. Deduplication + Hooks —— 去重 + Hook 注入

Tent OS 差异化：
- 5 步组装在治理进程内完成，结果通过 NATS 广播
- 支持物理执行器动态 schema 注册
- Hook 在 assemble 阶段注入，运行时零额外成本
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class ToolPoolConfig:
    """工具池配置"""
    permission_mode: str = "standard"  # strict / standard / auto / unrestricted
    profile: str = "full"              # full / coding / messaging / minimal
    allow_list: Set[str] = None
    deny_list: Set[str] = None
    enable_mcp: bool = False
    enable_physical: bool = False
    
    def __post_init__(self):
        if self.allow_list is None:
            self.allow_list = set()
        if self.deny_list is None:
            self.deny_list = set()


class ToolPoolAssembler:
    """工具池动态组装器
    
    使用方式：
        assembler = ToolPoolAssembler(config, policy_engine, hook_engine)
        tools = assembler.assemble(session_id="abc", context={"task": "写代码"})
    """
    
    # Permission Mode -> 允许的工具名映射
    MODE_TOOL_MAP = {
        "strict": {
            "file_read", "directory_list", "web_search", "web_fetch",
            "memory_search", "memory_get",
        },
        "standard": {
            "shell", "file_read", "file_write", "directory_list",
            "http_request", "web_search", "web_fetch",
            "memory_search", "memory_get",
            "browser_navigate", "browser_click", "browser_type", 
            "browser_read", "browser_screenshot",
            # FIX: 办公渲染工具 + 物理执行者调度
            "render_ppt", "render_excel", "render_word",
            "render_document", "render_contract", "render_webpage",
            "scheduler_dispatch", "realman", "flashex",
        },
        "auto": None,  # 由 Auto-Mode Classifier 动态决定
        "unrestricted": None,  # 所有工具
    }
    
    # Profile -> 允许的工具名映射
    PROFILE_TOOL_MAP = {
        "full": None,  # 所有工具
        "coding": {
            "shell", "file_read", "file_write", "directory_list",
            "http_request", "web_search", "web_fetch",
            "memory_search", "memory_get",
        },
        "messaging": {"message", "session_status", "memory_search"},
        "minimal": set(),
    }
    
    def __init__(self, 
                 config: Dict[str, Any] = None,
                 policy_engine=None,
                 hook_engine=None,
                 mcp_client=None,
                 tool_executor=None):
        self.config = config or {}
        self.policy_engine = policy_engine
        self.hook_engine = hook_engine
        self.mcp_client = mcp_client
        self.tool_executor = tool_executor
        
        # 缓存: session_id -> (timestamp, tools)
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl_seconds = 60
    
    def assemble(self, session_id: str, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """组装工具池
        
        Args:
            session_id: 会话ID
            context: 当前上下文（用于 PolicyEngine 评估和 Mode 决定）
        
        Returns:
            OpenAI function calling 格式的工具定义列表
        """
        context = context or {}
        
        # 检查缓存
        import time
        if session_id in self._cache:
            cached_ts, cached_tools = self._cache[session_id]
            if time.time() - cached_ts < self._cache_ttl_seconds:
                return cached_tools
        
        # Step 1: Base enumeration
        tools = self._get_base_tools()
        
        # Step 2: Mode filtering
        tools = self._filter_by_mode(tools, session_id, context)
        
        # Step 3: Deny rule pre-filtering
        tools = self._filter_by_policy(tools, context)
        
        # Step 4: MCP integration
        tools = self._integrate_mcp_tools(tools, session_id)
        
        # Step 5: Deduplication + Hooks
        tools = self._deduplicate(tools)
        tools = self._apply_hooks("tool.assemble", tools, context)
        
        # 缓存结果
        self._cache[session_id] = (time.time(), tools)
        
        logger.info(f"[ToolPool] 组装完成 [{session_id}]: {len(tools)} 个工具")
        return tools
    
    def invalidate_cache(self, session_id: str = None):
        """使缓存失效"""
        if session_id:
            self._cache.pop(session_id, None)
        else:
            self._cache.clear()
    
    # ========== Step 1: Base Enumeration ==========
    
    def _get_base_tools(self) -> List[Dict[str, Any]]:
        """获取所有基础工具"""
        from tent_os.tools.definitions import get_tool_schemas
        
        tools = get_tool_schemas()
        
        # 添加自定义工具
        if self.tool_executor:
            custom = self.tool_executor.get_custom_tool_schemas()
            # FIX v6 debug: 确保 render_webpage 被包含
            custom_names = [c.get("function", {}).get("name", "") for c in custom]
            if "render_webpage" not in custom_names:
                logger.warning(f"[ToolPool] 自定义工具中缺少 render_webpage，当前: {custom_names}")
            tools = tools + custom
        
        # 添加物理执行器工具
        physical = self._get_physical_tools()
        if physical:
            tools = tools + physical
        
        return tools
    
    def _get_physical_tools(self) -> List[Dict[str, Any]]:
        """获取物理执行器工具 schema"""
        schemas = []
        phys_config = self.config.get("physical_executors", {})
        
        # FIX: 始终暴露 scheduler_dispatch 通用调度工具
        schemas.append({
            "type": "function",
            "function": {
                "name": "scheduler_dispatch",
                "description": "调度 Tent OS 调度进程中的执行者完成物理世界或异步任务。可用执行者包括：mock（测试）、local（本地操作）、realman（睿尔曼机械臂）、flashex（闪送配送）、browser（浏览器自动化）等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "executor_id": {
                            "type": "string",
                            "description": "执行者ID，如 mock, local, realman, flashex, browser"
                        },
                        "action": {
                            "type": "string",
                            "description": "要执行的动作名"
                        },
                        "params": {
                            "type": "object",
                            "description": "动作参数"
                        }
                    },
                    "required": ["executor_id", "action"]
                }
            }
        })
        
        if phys_config.get("realman", {}).get("enabled", False):
            schemas.append({
                "type": "function",
                "function": {
                    "name": "realman",
                    "description": "操控睿尔曼机械臂执行物理操作。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["move", "pick", "place", "observe", "diagnose"],
                            },
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                            "object": {"type": "string"},
                        },
                        "required": ["action"],
                    }
                }
            })
        
        if phys_config.get("flashex", {}).get("enabled", False):
            schemas.append({
                "type": "function",
                "function": {
                    "name": "flashex",
                    "description": "通过闪送平台下单。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["deliver", "pickup"]},
                            "pickup_address": {"type": "string"},
                            "delivery_address": {"type": "string"},
                            "item_description": {"type": "string"},
                        },
                        "required": ["action"],
                    }
                }
            })
        
        return schemas
    
    # ========== Step 2: Mode Filtering ==========
    
    def _filter_by_mode(self, tools: List[Dict], 
                        session_id: str,
                        context: Dict) -> List[Dict]:
        """根据 Permission Mode 过滤工具"""
        # 获取当前 mode
        mode = self._get_session_mode(session_id, context)
        
        # 获取 Profile 配置
        tool_config = self.config.get("tools", {})
        profile = tool_config.get("profile", "full")
        allow_list = set(tool_config.get("allow", []))
        deny_list = set(tool_config.get("deny", []))
        
        allowed_names = set()
        
        # Mode 决定基础集合
        mode_tools = self.MODE_TOOL_MAP.get(mode)
        if mode_tools is None:
            allowed_names = {t["function"]["name"] for t in tools}
        else:
            allowed_names = mode_tools.copy()
        
        # Profile 进一步限制
        profile_tools = self.PROFILE_TOOL_MAP.get(profile)
        if profile_tools is not None:
            allowed_names &= profile_tools
        
        # allow 列表扩展
        if allow_list:
            allowed_names |= allow_list
        
        # deny 列表优先排除
        if deny_list:
            allowed_names -= deny_list
        
        filtered = []
        for t in tools:
            name = t["function"]["name"]
            if name in allowed_names:
                filtered.append(t)
        
        if deny_list:
            logger.debug(f"[ToolPool] Deny 过滤: 排除了 {deny_list}")
        
        return filtered
    
    def _get_session_mode(self, session_id: str, context: Dict) -> str:
        """获取会话的 Permission Mode"""
        # 优先从上下文中获取
        mode = context.get("permission_mode")
        if mode:
            return mode
        
        # 从配置获取默认 mode
        return self.config.get("security", {}).get("permission_mode", "standard")
    
    # ========== Step 3: Deny Rule Pre-filtering ==========
    
    def _filter_by_policy(self, tools: List[Dict], context: Dict) -> List[Dict]:
        """PolicyEngine 预过滤"""
        if not self.policy_engine:
            return tools
        
        filtered = []
        for t in tools:
            name = t["function"]["name"]
            
            # 构建评估上下文
            eval_context = {
                "task": context.get("task", ""),
                "action": name,
                "executor": {"authorized": True, "consecutive_failures": 0, "status": "online"},
            }
            
            result = self.policy_engine.evaluate(eval_context)
            
            if result["decision"] == "deny":
                logger.debug(f"[ToolPool] Policy 拒绝: {name} ({result.get('reason', '')})")
                continue
            
            filtered.append(t)
        
        return filtered
    
    # ========== Step 4: MCP Integration ==========
    
    def _integrate_mcp_tools(self, tools: List[Dict], session_id: str) -> List[Dict]:
        """动态加载 MCP 工具"""
        if not self.mcp_client or not self.config.get("enable_mcp", False):
            return tools
        
        try:
            mcp_tools = self.mcp_client.get_tools(session_id)
            if mcp_tools:
                existing_names = {t["function"]["name"] for t in tools}
                server_name = self.mcp_client.name()
                for mt in mcp_tools:
                    name = mt["function"]["name"]
                    prefixed_name = f"{server_name}__{name}"
                    if prefixed_name not in existing_names:
                        mt_copy = dict(mt)
                        mt_copy["function"] = dict(mt["function"])
                        mt_copy["function"]["name"] = prefixed_name
                        tools.append(mt_copy)
                        existing_names.add(prefixed_name)
                logger.info(f"[ToolPool] MCP 工具加载: {len(mcp_tools)} 个")
        except Exception as e:
            logger.warning(f"[ToolPool] MCP 工具加载失败: {e}")
        
        return tools
    
    # ========== Step 5: Deduplication + Hooks ==========
    
    def _deduplicate(self, tools: List[Dict]) -> List[Dict]:
        """去重 —— 按名称去重，保留第一个"""
        seen = set()
        result = []
        for t in tools:
            name = t["function"]["name"]
            if name not in seen:
                seen.add(name)
                result.append(t)
            else:
                logger.debug(f"[ToolPool] 去重: {name}")
        return result
    
    def _apply_hooks(self, event: str, tools: List[Dict], 
                     context: Dict) -> List[Dict]:
        """应用 Hook（同步版本，因为 assemble 通常是同步的）"""
        if not self.hook_engine:
            return tools
        
        # Hook 在 assemble 阶段只能做同步修改
        # 异步 Hook 在 tool.prefilter 阶段触发
        return tools
    
    # ========== 便捷方法 ==========
    
    def get_tool_names(self, session_id: str, context: Dict = None) -> List[str]:
        """获取组装后的工具名列表"""
        tools = self.assemble(session_id, context)
        return [t["function"]["name"] for t in tools]
    
    def has_tool(self, tool_name: str, session_id: str, context: Dict = None) -> bool:
        """检查工具是否在组装后的工具池中"""
        names = self.get_tool_names(session_id, context)
        return tool_name in names
    
    def get_tool_by_name(self, tool_name: str, session_id: str, 
                         context: Dict = None) -> Optional[Dict]:
        """按名称获取工具定义"""
        tools = self.assemble(session_id, context)
        for t in tools:
            if t["function"]["name"] == tool_name:
                return t
        return None
