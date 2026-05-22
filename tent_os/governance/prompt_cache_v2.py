"""Prompt Cache v2 —— 跨代理分段缓存共享

借鉴 Claude Code 的 6 层精细化 prompt cache：
- L0 system:       System prompt（身份、价值观）— 全局共享
- L1 identity:     IDENTITY.md + SOUL.md — 用户级共享
- L2 agents:       AGENTS.md 规则 — 项目级共享
- L3 user_profile: USER.md 用户画像 — 用户级共享
- L4 tools:        可用工具列表 — 会话级共享
- L5 dynamic:      当前任务 + 历史对话 — 每轮更新

Tent OS 差异化：
- 静态段通过 Redis Hash 共享（跨进程/跨机器）
- 支持 Anthropic cache_control 标记
- 与 FileDrivenPromptBuilder 集成

使用方式：
    cache = SegmentedPromptCacheV2(redis_client)
    
    # 构建 prompt
    prompt = cache.build(
        model_provider="anthropic",
        session_id="abc",
        task="写一个Python函数",
        tools=[...],
        injected_context="...",
        user_id="frank",
    )
"""

import json
import time
from typing import Dict, List, Optional, Any
from pathlib import Path

from tent_os.logging_config import get_logger

logger = get_logger()


class SegmentedPromptCacheV2:
    """分段 Prompt 缓存 v2

    6 层精细化缓存，静态段跨会话共享。
    """

    SEGMENTS = ["system", "identity", "agents", "user_profile", "tools", "dynamic"]

    def __init__(self, redis_client=None, file_builder=None):
        self.redis = redis_client
        self.file_builder = file_builder

        # 本地内存缓存（减少 Redis 查询）
        self._local_cache: Dict[str, tuple] = {}  # key -> (content, timestamp)
        self._local_cache_ttl = 300  # 5 分钟

    def build(self,
              model_provider: str,
              session_id: str,
              task: str,
              tools: List[Dict],
              injected_context: str = "",
              user_id: Optional[str] = None,
              system_prompt_override: str = None) -> Dict:
        """构建完整的分层 prompt

        Returns:
            provider-specific 的 prompt 结构
        """
        # 构建各段
        segments = {}

        # L0: System
        segments["system"] = system_prompt_override or self._get_segment("system", "global")

        # L1: Identity
        segments["identity"] = self._get_segment("identity", user_id or "default")

        # L2: Agents
        segments["agents"] = self._get_segment("agents", "project")

        # L3: User Profile
        segments["user_profile"] = self._get_segment("user_profile", user_id or "anonymous")

        # L4: Tools
        segments["tools"] = self._format_tools(tools)

        # L5: Dynamic
        segments["dynamic"] = self._build_dynamic(task, injected_context, session_id)

        # 按 provider 格式化
        if model_provider == "anthropic":
            return self._format_anthropic(segments)
        else:
            return self._format_openai(segments)

    def invalidate_segment(self, segment: str, scope: str = None):
        """使某一段缓存失效"""
        cache_key = f"prompt_cache:{segment}:{scope or 'global'}"
        self._local_cache.pop(cache_key, None)

        if self.redis:
            self.redis.delete(cache_key)

        logger.info(f"[PromptCache] 缓存失效: {segment} ({scope or 'global'})")

    # ========== 内部实现 ==========

    def _get_segment(self, segment: str, scope: str) -> str:
        """获取某一段的内容（带缓存）"""
        cache_key = f"prompt_cache:{segment}:{scope}"

        # 1. 检查本地缓存
        if cache_key in self._local_cache:
            content, ts = self._local_cache[cache_key]
            if time.time() - ts < self._local_cache_ttl:
                return content

        # 2. 检查 Redis 缓存
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    content = cached.decode("utf-8")
                    self._local_cache[cache_key] = (content, time.time())
                    return content
            except Exception:
                pass

        # 3. 从文件系统加载
        content = self._load_from_files(segment, scope)

        # 4. 更新缓存
        self._local_cache[cache_key] = (content, time.time())
        if self.redis and content:
            try:
                self.redis.setex(cache_key, 3600, content)
            except Exception:
                pass

        return content

    def _load_from_files(self, segment: str, scope: str) -> str:
        """从文件系统加载 segment"""
        # 映射 segment 到文件路径
        file_map = {
            "system": ["config/system_prompt.md", "SYSTEM.md"],
            "identity": [f"config/IDENTITY.md", ".tent/IDENTITY.md"],
            "agents": ["AGENTS.md", ".tent/AGENTS.md"],
            "user_profile": [f"tent_memory/files/users/{scope}.md"],
        }

        paths = file_map.get(segment, [])
        for path_str in paths:
            path = Path(path_str)
            if path.exists():
                return path.read_text(encoding="utf-8")

        # 返回默认内容
        defaults = {
            "system": "你是 Tent OS 智能体——一个去 AI 化的自主任务执行系统。",
            "identity": "",
            "agents": "",
            "user_profile": "",
        }
        return defaults.get(segment, "")

    def _format_tools(self, tools: List[Dict]) -> str:
        """格式化工具列表为文本"""
        if not tools:
            return "【可用工具】当前未配置任何外部工具。"

        lines = ["【可用工具】"]
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_desc = ", ".join(
                [f"{k}({v.get('type', 'str')})" for k, v in params.items()]
            ) if params else "无参数"
            lines.append(f"  • {name}: {desc} (参数: {param_desc})")

        lines.append("\n【工具使用规范】")
        lines.append("  - 每个步骤只能调用一个工具")
        lines.append("  - 调用前确认所有必需参数已准备")
        return "\n".join(lines)

    def _build_dynamic(self, task: str, injected_context: str, session_id: str) -> str:
        """构建动态段"""
        parts = [f"【当前任务】{task}"]
        if injected_context:
            parts.append(f"【注入上下文】{injected_context}")
        parts.append(f"【会话ID】{session_id}")
        return "\n\n".join(parts)

    def _format_anthropic(self, segments: Dict[str, str]) -> Dict:
        """Anthropic 格式（支持 cache_control）"""
        # 静态段合并
        static_parts = []
        static_segments = ["system", "identity", "agents", "user_profile"]

        for seg_name in static_segments:
            content = segments.get(seg_name, "")
            if content:
                static_parts.append({
                    "type": "text",
                    "text": content,
                })

        # 工具段（带 cache_control）
        tools_content = segments.get("tools", "")
        if tools_content:
            static_parts.append({
                "type": "text",
                "text": tools_content,
                "cache_control": {"type": "ephemeral"},
            })

        # 动态段
        dynamic_content = segments.get("dynamic", "")

        return {
            "system": static_parts,
            "messages": [{"role": "user", "content": dynamic_content}],
        }

    def _format_openai(self, segments: Dict[str, str]) -> Dict:
        """OpenAI / Kimi 兼容格式"""
        # 合并所有段为一个 system prompt
        static_parts = []
        for seg_name in ["system", "identity", "agents", "user_profile", "tools"]:
            content = segments.get(seg_name, "")
            if content:
                static_parts.append(content)

        system_content = "\n\n".join(static_parts)
        dynamic_content = segments.get("dynamic", "")

        return {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": dynamic_content},
            ]
        }
