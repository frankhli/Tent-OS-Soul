"""模式路由器 —— System Prompt 片段管理器

职责：
1. 为不同场景生成对应的 System Prompt 片段
2. 管理工具索引的格式化输出

注意：本模块不再做"用户意图预判断"。LLM 自主决定是否调用工具。
"""

from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


# 各场景对应的 System Prompt 片段
MODE_SYSTEM_PROMPT_FRAGMENTS = {
    "chat": """【当前模式：日常对话】
你只能进行纯文本对话，不能调用任何工具。
用自然、温暖的方式回复，适当简洁。
不要试图执行文件操作、搜索网页或调用API。""",

    "unified": """【当前模式：自主决策模式】
你拥有完整的工具调用能力。需要时可以调用工具来执行任务。

工具调用规则：
1. 分析用户的请求，自主判断是否需要调用工具
2. 需要工具时，直接调用对应工具，不要回复"我看不到"或"我无法访问"
3. 工具调用后，根据结果给用户清晰的自然语言回复
4. 闲聊、情感陪伴、简单问答不需要调用工具，直接文本回复即可
5. 如果任务需要多轮工具调用，连续调用直到完成

【危险操作确认规则】
某些操作（如删除文件 rm、移动文件 mv、覆盖重定向 >、覆盖写入已存在文件）被系统标记为危险。
如果工具返回 `status: need_confirmation`，说明这个操作需要用户确认。
你必须在回复中明确询问用户："我需要执行 [操作描述]，这可能有风险，你确认吗？"
如果用户回复"确认"、"y"或"yes"，你可以在下一轮工具调用中传入参数 `__confirmed: true`，系统会放行执行。
不要在没有用户确认的情况下重复调用同一个危险操作。

可用工具列表已注入到上下文。""",
}


class ModeRouter:
    """模式路由器
    
    职责：
    1. 为不同场景生成对应的 System Prompt 片段
    2. 格式化工具索引输出
    """
    
    def __init__(self):
        self._session_tool_call_count: Dict[str, int] = {}  # session_id -> 本轮工具调用次数
    
    def get_system_prompt_fragment(self, mode: str, tool_index_text: str = "") -> str:
        """获取指定场景对应的 System Prompt 片段"""
        return MODE_SYSTEM_PROMPT_FRAGMENTS.get(mode, "")
    
    def build_intuition_tool_index(self, tools: List[Dict]) -> str:
        """为直觉模式构建轻量工具索引文本
        
        格式：
        - tool_name: 一句话描述
        - tool_name: 一句话描述
        """
        lines = []
        for t in tools:
            func = t.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            # 截断到50字
            if len(desc) > 50:
                desc = desc[:50] + "..."
            lines.append(f"- {name}: {desc}")
        
        return "\n".join(lines) if lines else "（当前无可用工具）"
    
    def record_tool_call(self, session_id: str):
        """记录某session发生了工具调用"""
        self._session_tool_call_count[session_id] = self._session_tool_call_count.get(session_id, 0) + 1
    
    def get_session_stats(self, session_id: str) -> Dict:
        """获取session的模式统计"""
        return {
            "tool_call_count": self._session_tool_call_count.get(session_id, 0),
        }
    
    def reset_session(self, session_id: str):
        """重置session的状态"""
        self._session_tool_call_count.pop(session_id, None)


# 全局单例
_mode_router: Optional[ModeRouter] = None


def get_mode_router() -> ModeRouter:
    """获取全局模式路由器实例"""
    global _mode_router
    if _mode_router is None:
        _mode_router = ModeRouter()
    return _mode_router
