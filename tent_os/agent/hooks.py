"""Hook 系统 —— 在 Agent Loop 的关键节点注入自定义逻辑

参考 Claude Code 的 hooks 设计：
- tool.assemble: 修改工具池（增删改工具）
- pre_tool_use: 批准/拦截/重写工具调用
- post_tool_use: 修改输出或注入上下文
- stop: 强制循环继续

使用方式：
    hooks = HookEngine()
    hooks.register("tool.assemble", my_tool_filter)
    hooks.register("pre_tool_use", my_approval_check)
    result = await hooks.trigger("tool.assemble", session_id="abc", data={...})
"""

from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class HookResult:
    """Hook 执行结果"""
    modified: bool = False      # 数据是否被修改
    data: Dict = None           # 修改后的数据
    blocked: bool = False       # 是否被拦截
    reason: str = ""            # 拦截原因

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class HookEngine:
    """Hook 引擎"""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {}

    def register(self, event: str, handler: Callable, priority: int = 0):
        """注册 Hook 处理器

        Args:
            event: 事件名称
            handler: async def handler(session_id, data) -> HookResult
            priority: 优先级（越高越先执行）
        """
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append((priority, handler))
        # 按优先级排序
        self._hooks[event].sort(key=lambda x: -x[0])
        logger.info(f"[Hook] 注册 {event}: {handler.__name__} (priority={priority})")

    def unregister(self, event: str, handler: Callable):
        """注销 Hook 处理器"""
        if event in self._hooks:
            self._hooks[event] = [
                (p, h) for p, h in self._hooks[event] if h != handler
            ]

    async def trigger(self, event: str, session_id: str = "", data: Dict = None) -> HookResult:
        """触发事件

        Args:
            event: 事件名称
            session_id: 会话 ID
            data: 事件数据

        Returns:
            HookResult
        """
        data = data or {}
        result = HookResult(data=dict(data))

        handlers = self._hooks.get(event, [])
        if not handlers:
            return result

        for priority, handler in handlers:
            try:
                hook_result = await handler(session_id=session_id, data=result.data)
                if hook_result is None:
                    continue

                if hook_result.blocked:
                    # 被拦截，停止后续处理
                    return hook_result

                if hook_result.modified and hook_result.data:
                    result.modified = True
                    result.data.update(hook_result.data)

            except Exception as e:
                logger.warning(f"[Hook] {event} 处理器异常: {e}")
                continue

        return result

    def list_events(self) -> List[str]:
        """列出所有已注册的事件"""
        return list(self._hooks.keys())

    def count_handlers(self, event: str) -> int:
        """获取某个事件的处理器数量"""
        return len(self._hooks.get(event, []))


# ========== 预置 Hook 示例 ==========

async def tool_assemble_filter(session_id: str, data: Dict) -> HookResult:
    """工具池过滤 Hook 示例

    根据 session 的权限模式过滤危险工具。
    """
    tools = data.get("tools", [])
    # 示例：移除所有 shell 工具（如果需要）
    # filtered = [t for t in tools if t.get("function", {}).get("name") != "shell"]
    # return HookResult(modified=True, data={"tools": filtered})
    return HookResult(data=data)


async def pre_tool_approval(session_id: str, data: Dict) -> HookResult:
    """工具调用前审批 Hook 示例"""
    tool_name = data.get("tool_name", "")
    arguments = data.get("arguments", {})
    # 这里可以接入 SecurityPipeline
    # if should_block(tool_name, arguments):
    #     return HookResult(blocked=True, reason="安全策略拦截")
    return HookResult(data=data)
