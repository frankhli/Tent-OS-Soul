"""LLM Provider 抽象接口 —— 参考 OpenClaw provider 设计

支持 provider/model 格式，如:
    - kimi_coding/kimi-k2.6
    - openai/gpt-4o
    - anthropic/claude-3-opus

每个 provider 实现统一的 chat/chat_stream/generate_plan 接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable


class LLMProvider(ABC):
    """LLM Provider 抽象基类"""
    
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """非流式对话"""
        pass
    
    @abstractmethod
    async def chat_stream(
        self, 
        messages: List[Dict[str, str]], 
        on_chunk: Callable[[str], None],
        **kwargs
    ) -> str:
        """流式对话
        
        Args:
            messages: [{role, content}, ...]
            on_chunk: 每收到一个 text chunk 调用一次
        
        Returns:
            完整响应文本
        """
        pass
    
    @abstractmethod
    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        """生成任务执行方案（返回 JSON Plan）"""
        pass

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """非流式 tool calling

        Returns:
            {"content": str, "tool_calls": [{"id": str, "type": "function", "function": {"name": str, "arguments": str}}]}
        """
        pass

    @abstractmethod
    async def chat_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        on_chunk: Callable[[str, str], None],
        on_tool_calls: Callable[[List[Dict]], None],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """流式 tool calling

        Args:
            messages: 对话历史
            tools: 可用工具列表
            on_chunk: 回调函数，每收到一个 chunk 调用一次 on_chunk(text, chunk_type)
                chunk_type: "reasoning" | "content"
            on_tool_calls: 回调函数，当检测到 tool_calls 时调用
            temperature: 温度
            max_tokens: 最大生成 token 数

        Returns:
            完整响应文本（仅 content 部分，不含 reasoning）
        """
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """provider/model 格式的模型 ID"""
        pass
