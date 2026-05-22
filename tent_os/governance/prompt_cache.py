"""SegmentedPromptCache —— 分层 Prompt 缓存系统

借鉴 Claude Code 的 prompt 分层思想，将 prompt 拆分为不同"变率"的段：
- L1 Identity（身份）：几乎不变——你是谁
- L2 Principles（原则）：很少变——行为准则
- L3 Tools（工具约束）：随配置变——可用工具列表
- L4 Context（注入记忆）：每次会话变——用户画像/历史/待办
- L5 Task（当前任务）：每次消息变——用户输入
- L6 Format（输出格式）：可配置——回复规范

分层价值：
- 静态段（L1-L3）可以长期缓存，减少 LLM 重复处理
- 动态段（L4-L6）按需加载，精准控制 token 消耗
- 支持 Anthropic cache_control 标记，真正利用 prompt caching
"""

from datetime import datetime
from typing import List, Dict, Optional


class SegmentedPromptCache:
    """分段 Prompt 缓存——不同段不同生命周期"""
    
    def build_prompt(
        self,
        model_provider: str,
        session_id: str,
        task: str,
        tools: List[Dict],
        injected_context: str = "",
        user_id: Optional[str] = None,
    ) -> Dict:
        """构建完整的分层 prompt
        
        Args:
            model_provider: "anthropic" | "openai" | "kimi"
            session_id: 当前会话ID
            task: 用户任务描述
            tools: 可用工具列表
            injected_context: 记忆进程注入的三层上下文
            user_id: 用户ID（可选，用于个性化）
        
        Returns:
            provider-specific 的 prompt 结构
        """
        # 六层构建
        l1_identity = self._l1_identity()
        l2_principles = self._l2_principles()
        l3_tools = self._l3_tools(tools)
        l4_context = self._l4_context(injected_context, user_id)
        l5_task = self._l5_task(session_id, task)
        l6_format = self._l6_format()
        
        # 合并静态段（L1-L3）——这些段变化慢，适合缓存
        static_parts = [l1_identity, l2_principles, l3_tools]
        static_text = "\n\n".join(static_parts)
        
        # 合并动态段（L4-L6）——这些段每次不同
        dynamic_parts = []
        if l4_context:
            dynamic_parts.append(l4_context)
        dynamic_parts.extend([l5_task, l6_format])
        dynamic_text = "\n\n".join(dynamic_parts)
        
        # 按 provider 格式化
        if model_provider == "anthropic":
            return self._format_anthropic(static_text, dynamic_text)
        elif model_provider == "openai":
            return self._format_openai(static_text, dynamic_text)
        else:
            # kimi / 其他 OpenAI 兼容格式
            return self._format_openai(static_text, dynamic_text)
    
    # ========== L1: Identity（身份）==========
    def _l1_identity(self) -> str:
        """L1 —— 身份定义。几乎不变。"""
        return (
            "【身份】你是 Tent OS 智能体——一个去 AI 化的自主任务执行系统。\n"
            "你不是在「聊天」，你是在「完成工作」。你的每一次输出都应该指向任务的推进或完成。"
        )
    
    # ========== L2: Principles（原则）==========
    def _l2_principles(self) -> str:
        """L2 —— 核心原则。很少变。"""
        return (
            "【核心原则】\n"
            "1. 安全第一：任何可能造成伤害的操作必须获得明确授权\n"
            "2. 诚实透明：不知道就直说，不编造数据或结果\n"
            "3. 可追溯：每个决策都有依据，每个操作都有记录\n"
            "4. 工具约束：只使用系统提供的工具，不虚构不存在的能力\n"
            "5. 自主执行：收到任务后主动规划并推进，不等待用户反复确认"
        )
    
    # ========== L3: Tools（工具约束）==========
    def _l3_tools(self, tools: List[Dict]) -> str:
        """L3 —— 工具约束。随配置改变。"""
        if not tools:
            return (
                "【可用工具】当前系统未配置任何外部工具。\n"
                "你只能基于已有知识和系统注入的信息进行分析和回复。"
            )
        
        lines = ["【可用工具】"]
        for t in tools:
            name = t.get("name", "unknown")
            desc = t.get("description", "")
            params = t.get("parameters", {})
            param_desc = ", ".join([f"{k}({v.get('type', 'str')})" for k, v in params.items()]) if params else "无参数"
            lines.append(f"  • {name}: {desc} (参数: {param_desc})")
        
        lines.append("\n【工具使用规范】")
        lines.append("  - 每个步骤只能调用一个工具")
        lines.append("  - 调用前确认所有必需参数已准备")
        lines.append("  - 工具返回错误时，分析原因并决定是否重试或上报")
        return "\n".join(lines)
    
    # ========== L4: Context（注入记忆）==========
    def _l4_context(self, injected_context: str, user_id: Optional[str]) -> str:
        """L4 —— 注入记忆。每次会话不同。"""
        parts = []
        if user_id:
            parts.append(f"【当前用户】{user_id}")
        if injected_context:
            parts.append(injected_context)
        return "\n\n".join(parts) if parts else ""
    
    # ========== L5: Task（当前任务）==========
    def _l5_task(self, session_id: str, task: str) -> str:
        """L5 —— 当前任务。每次消息不同。"""
        return (
            f"【当前任务】\n"
            f"会话ID: {session_id}\n"
            f"时间: {datetime.now().isoformat()}\n"
            f"任务内容: {task}\n\n"
            f"请根据上述身份、原则、工具约束和上下文信息，制定执行方案或直接回复。"
        )
    
    # ========== L6: Format（输出格式）==========
    def _l6_format(self) -> str:
        """L6 —— 输出格式。可配置。"""
        return (
            "【输出规范】\n"
            "  - 默认使用中文回复\n"
            "  - 需要制定计划时，输出 JSON 格式的执行方案\n"
            "  - 代码块标注编程语言\n"
            "  - 涉及数字或数据时，注明来源或不确定性"
        )
    
    # ========== Provider Formatters ==========
    def _format_anthropic(self, static: str, dynamic: str) -> Dict:
        """Anthropic 格式：支持 cache_control"""
        return {
            "system": [
                {
                    "type": "text",
                    "text": static,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "messages": [{"role": "user", "content": dynamic}]
        }
    
    def _format_openai(self, static: str, dynamic: str) -> Dict:
        """OpenAI / Kimi 兼容格式"""
        return {
            "messages": [
                {"role": "system", "content": static},
                {"role": "user", "content": dynamic}
            ]
        }
