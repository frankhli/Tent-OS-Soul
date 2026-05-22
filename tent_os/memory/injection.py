import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
import numpy as np
import tiktoken

logger = logging.getLogger("tent_os.memory")


class MemoryInjectionService:
    """主动记忆注入——模拟人类大脑工作记忆
    
    核心设计原则（综合 Claude Code + OpenViking + Mem0 精华）：
    1. 容量限制：工作记忆最多容纳 7±2 个组块 → 限制为 ~1500 tokens
    2. 索引指针：Claude Code memory.md 模式，轻量路由，按需加载
    3. L2 绝不自动注入：修复 OpenViking #1549，只通过 tool_call 读取
    4. 分层加载：L0 摘要优先，L1 概览按需，L2 显式读取
    """
    
    MAX_INJECTION_TOKENS = 1500
    MAX_CHUNK_TOKENS = 200
    
    def __init__(self, store, embedding_model: callable):
        from tent_os.memory.tiered_store import TieredMemoryStore
        from tent_os.memory.index import MemoryIndex
        self.store: TieredMemoryStore = store
        self.index = MemoryIndex(str(store.storage_path))
        self.embedding_model = embedding_model
        self.last_topic_vector: Optional[List[float]] = None
        self.topic_threshold = 0.7
        self._encoder = tiktoken.get_encoding("cl100k_base")
    
    async def inject_on_session_start(self, user_id: str, heartbeat_md: str = "",
                                       task_query: str = "") -> str:
        """会话启动：注入用户画像、近期摘要和待办任务
        
        修复 OpenViking 污染：只注入 L0/L1，L2 绝不自动加载。
        """
        # 使用 Memory Index 指针层选择要加载的记忆
        selected = self.index.select_for_task(task_query or "")
        
        # 从索引读取内容
        hot_contents = []
        for ptr in selected["hot"]:
            content = self.index.read_content(ptr.uri)
            if content:
                hot_contents.append(f"### {ptr.title}\n{content[:300]}...")
        
        warm_contents = []
        for ptr in selected["warm"]:
            content = self.index.read_content(ptr.uri)
            if content:
                warm_contents.append(f"### {ptr.title}\n{content[:200]}...")
        
        # 传统三层作为 fallback
        profile = self._get_user_profile(user_id)
        recent = await self._get_recent_abstracts(days=7, limit=10, task_query=task_query)
        
        sections = []
        
        # Index 层（新增）
        if hot_contents:
            sections.append(("🔥 HOT 记忆（高优先级）", "\n\n".join(hot_contents), 0))
        if warm_contents:
            sections.append(("🌡️ WARM 记忆（按需加载）", "\n\n".join(warm_contents), 1))
        
        # 传统三层
        if recent:
            sections.append(("🕐 近期活动（我最近在做什么）", recent, 2))
        if profile:
            sections.append(("📋 用户画像（我是谁）", profile, 3))
        if heartbeat_md:
            sections.append(("📌 待办任务（我现在该干什么）", heartbeat_md, 0))
        
        if not sections:
            return ""
        
        result_parts = ["【系统注入】以下是你应该知道的背景信息：", ""]
        current_tokens = self._count_tokens("\n".join(result_parts))
        sections.sort(key=lambda x: x[2])
        
        for title, content, priority in sections:
            section_text = f"{'=' * 40}\n{title}\n{'=' * 40}\n{content}\n"
            section_tokens = self._count_tokens(section_text)
            
            if current_tokens + section_tokens > self.MAX_INJECTION_TOKENS:
                remaining = self.MAX_INJECTION_TOKENS - current_tokens - self._count_tokens(f"{'=' * 40}\n{title}\n{'=' * 40}\n\n")
                if remaining > 50:
                    truncated = self._truncate_to_tokens(content, remaining)
                    section_text = f"{'=' * 40}\n{title}\n{'=' * 40}\n{truncated}\n"
                    result_parts.append(section_text)
                    current_tokens += self._count_tokens(section_text)
                else:
                    result_parts.append(f"[内容过长，已省略 {title}]")
                break
            
            result_parts.append(section_text)
            current_tokens += section_tokens
        
        # 关键修复：明确告知 Agent L2 需要通过 tool_call 读取
        result_parts.append(
            "\n💡 记忆系统提示：\n"
            "- 上述内容来自 L0/L1 摘要层\n"
            "- 如需查看完整原始内容（L2），请使用 memory_read(uri) 工具按需读取\n"
            "- L2 内容不会自动加载，避免上下文污染"
        )
        
        final_text = "\n".join(result_parts)
        total_tokens = self._count_tokens(final_text)
        logger.debug(f"记忆注入完成: {total_tokens} tokens, {len(sections)} 个片段")
        
        return final_text
    
    async def check_topic_change(self, current_message: str) -> Optional[str]:
        """检测话题切换，返回新话题相关记忆（只返回 L0/L1）"""
        try:
            current_vector = await self.embedding_model(current_message)
        except Exception as e:
            logger.debug(f"Embedding 失败，跳过话题检测: {e}")
            return None
        
        if self.last_topic_vector:
            similarity = self._cosine_similarity(current_vector, self.last_topic_vector)
            if similarity < self.topic_threshold:
                results = await self.store.search(current_vector, limit=3)
                self.last_topic_vector = current_vector
                return self._format_injection(results)
        self.last_topic_vector = current_vector
        return None
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = np.sqrt(sum(x * x for x in a))
        norm_b = np.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    
    def _format_injection(self, results: List[Dict]) -> str:
        if not results:
            return ""
        context = "【系统注入】话题已切换，以下是相关记忆（L0/L1 摘要）：\n"
        for r in results:
            abstract = r.get("abstract", "")
            overview = r.get("overview", "")
            uri = r.get("uri", "")
            context += f"- [{r.get('memory_type', 'memory')}] {abstract[:120]}..."
            if overview:
                context += f"\n  概览: {overview[:150]}..."
            context += f"\n  [如需完整内容，调用 memory_read('{uri}')]\n"
        return context
    
    def _get_user_profile(self, user_id: str) -> str:
        profile_path = Path(f"./tent_memory/profiles/{user_id}.md")
        return profile_path.read_text() if profile_path.exists() else ""
    
    def _count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        tokens = self._encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._encoder.decode(tokens[:max_tokens]) + "..."
    
    async def _get_recent_abstracts(self, days: int, limit: int, task_query: str = "") -> str:
        """从 L0 索引表读取最近 N 天的记忆摘要（绝不读取 L2）"""
        try:
            # 优先语义搜索（只返回 L0/L1）
            if task_query and self.embedding_model:
                try:
                    query_vec = await self.embedding_model(task_query)
                    results = await self.store.search(query_vec, limit=limit)
                    if results:
                        lines = []
                        for r in results:
                            abstract = r.get("abstract", "")
                            overview = r.get("overview", "")
                            lines.append(f"- {abstract[:120]}...")
                            if overview:
                                lines.append(f"  概览: {overview[:150]}...")
                        return "\n".join(lines)
                except Exception as e:
                    logger.debug(f"语义搜索失败，回退到时间排序: {e}")
            
            # 降级：按时间倒序
            cursor = self.store.db.execute(
                """SELECT uri, abstract, memory_type, created_at 
                   FROM l0_index 
                   WHERE created_at >= datetime('now', '-{} days')
                   ORDER BY created_at DESC 
                   LIMIT ?""".format(days),
                (limit,)
            )
            rows = cursor.fetchall()
            if not rows:
                return ""
            
            lines = []
            for uri, abstract, mem_type, created_at in rows:
                lines.append(f"- [{mem_type or 'memory'}] {abstract[:120]}... ({created_at})")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"读取近期摘要失败: {e}")
            return ""
