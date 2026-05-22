"""Anthropic Provider —— Claude API 适配器

支持 Claude 3/4 系列模型（claude-opus-4, claude-sonnet-4, claude-haiku 等）。
Anthropic API 与 OpenAI 格式不同，需要特殊处理 system prompt 和流式输出。
"""

import json
from typing import Dict, List, Optional, Callable

import httpx

from tent_os.llm.provider import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API 适配器"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        base_url: str = "https://api.anthropic.com/v1",
        temperature: float = 0.3,
        timeout: float = 60.0,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return f"anthropic/{self.model}"

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple:
        """将 OpenAI 格式消息转换为 Anthropic 格式
        
        Returns:
            (system: str, anthropic_messages: List[Dict])
        """
        system = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                system = content
            elif role == "tool":
                # Anthropic 工具结果格式
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "content": content}]
                })
            else:
                anthropic_messages.append({"role": role, "content": content})
        
        return system, anthropic_messages

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> str:
        system, anthropic_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": anthropic_messages,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Anthropic 返回 content 数组
            contents = data.get("content", [])
            texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
            return "".join(texts)

    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        system_prompt = "你是 Tent OS 的规划引擎。请为给定任务制定执行方案，输出严格JSON格式。"

        context_block = f"\n\n【经验规则】\n{extra_context}\n" if extra_context else ""
        user_prompt = f"""任务：{task}
可用工具：{json.dumps(tools, ensure_ascii=False)}{context_block}
输出严格JSON：{{"analysis": "...", "steps": [{{"step": 1, "action": "...", "executor": "...", "params": {{}}}}]}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        content = await self.chat(messages)
        try:
            plan = json.loads(content)
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Plan 缺少 steps")
            return plan
        except Exception as e:
            return {
                "analysis": f"解析失败({e})，使用 Fallback",
                "steps": [{"step": 1, "action": "chat", "executor": "default", "params": {}}]
            }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        on_chunk: Callable[[str], None],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        system, anthropic_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": anthropic_messages,
            "stream": True,
        }
        if system:
            payload["system"] = system

        full_text = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("delta", {})
                        # Anthropic 流式格式: delta.text
                        text = delta.get("text", "")
                        if text:
                            full_text += text
                            on_chunk(text, "content")
                    except (json.JSONDecodeError, KeyError):
                        continue
        return full_text

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """Anthropic tool calling"""
        system, anthropic_messages = self._convert_messages(messages)
        
        # 转换 tools 为 Anthropic 格式
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析响应
        contents = data.get("content", [])
        text_parts = []
        tool_calls = []
        
        for content in contents:
            if content.get("type") == "text":
                text_parts.append(content.get("text", ""))
            elif content.get("type") == "tool_use":
                tool_calls.append({
                    "id": content.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": content.get("name", ""),
                        "arguments": json.dumps(content.get("input", {})),
                    }
                })

        return {
            "content": "".join(text_parts),
            "tool_calls": tool_calls,
            "reasoning_content": "",
        }

    async def chat_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        on_chunk: Callable[[str, str], None],
        on_tool_calls: Callable[[List[Dict]], None],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """流式 tool calling（Anthropic 流式工具调用较复杂，先完整获取后模拟流式输出）"""
        # Anthropic 的流式 SSE 中 tool_use 分散在多个事件里，处理较复杂。
        # 安全做法：完整获取响应后，模拟流式输出 content，再通知 tool_calls。
        result = await self.chat_with_tools(
            messages, tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = result.get("content", "")
        if content:
            # 模拟流式：按词发送（避免一次性输出破坏流式体验）
            for word in content:
                on_chunk(word, "content")
        if result.get("tool_calls"):
            on_tool_calls(result["tool_calls"])
        return content
