"""预测性预加载 —— 类似 CPU 分支预测的记忆预加载

核心思想：
1. 预测用户下一步可能聊什么
2. 预加载预测话题的相关记忆到工作记忆缓存
3. 如果预测命中，立即可用；如果未命中，缓存自动过期

预测信号：
- 当前话题的 common follow-ups
- 用户历史的行为模式
- 时间/地点的上下文
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from tent_os.memory.graph import CognitiveGraph, MemoryNode
from tent_os.memory.graph_queries import GraphQueryEngine

logger = logging.getLogger("tent_os.memory.preloader")


class PredictivePreloader:
    """预测性预加载器"""
    
    def __init__(self, graph: CognitiveGraph, cache_ttl_seconds: int = 300):
        self.graph = graph
        self.query_engine = GraphQueryEngine(graph)
        self.cache_ttl = cache_ttl_seconds  # 缓存 5 分钟
        
        # 预加载缓存：topic → List[MemoryNode]
        self._cache: Dict[str, Dict] = {}
        
        # 话题转移统计：topic_a → {topic_b: count}
        self._transition_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # 常见 follow-ups（领域知识）
        self._common_followups = {
            " restaurant": ["menu", "reservation", "review", "location"],
            "餐厅": ["菜单", "预订", "评价", "地址"],
            " travel": ["hotel", "flight", "itinerary", "budget"],
            "旅行": ["酒店", "机票", "行程", "预算"],
            " project": ["timeline", "resource", "risk", "milestone"],
            "项目": ["时间线", "资源", "风险", "里程碑"],
            " code": ["bug", "feature", "review", "deploy"],
            "代码": ["bug", "功能", "review", "部署"],
            " health": ["exercise", "diet", "sleep", "checkup"],
            "健康": ["运动", "饮食", "睡眠", "体检"],
        }
    
    def predict_next_topics(self, current_context: str, 
                            user_history: List[str] = None) -> List[str]:
        """预测用户接下来可能聊什么
        
        Returns:
            List[str]: 预测的话题列表，按概率排序
        """
        predictions = []
        context_lower = current_context.lower()
        
        # 1. 基于领域知识的 follow-ups
        for keyword, followups in self._common_followups.items():
            if keyword.lower() in context_lower:
                predictions.extend(followups)
        
        # 2. 基于用户历史的行为模式
        if user_history:
            # 找到最近 3 个话题
            recent_topics = self._extract_topics(user_history[-3:])
            for topic in recent_topics:
                if topic in self._transition_stats:
                    # 找到最可能的下一个话题
                    next_topics = sorted(
                        self._transition_stats[topic].items(),
                        key=lambda x: -x[1]
                    )
                    predictions.extend([t for t, _ in next_topics[:3]])
        
        # 3. 基于时间上下文
        hour = datetime.now().hour
        if 7 <= hour < 9:
            predictions.extend(["早餐", "今日计划", "morning routine"])
        elif 11 <= hour < 14:
            predictions.extend(["午餐", "午餐推荐", "lunch"])
        elif 17 <= hour < 20:
            predictions.extend(["晚餐", "下班", "dinner"])
        elif 22 <= hour or hour < 1:
            predictions.extend(["睡眠", "明日计划", "sleep"])
        
        # 去重并返回
        seen = set()
        unique = []
        for p in predictions:
            p_lower = p.lower()
            if p_lower not in seen:
                seen.add(p_lower)
                unique.append(p)
        
        return unique[:5]
    
    def preload_for_prediction(self, predicted_topics: List[str]) -> int:
        """为预测话题预加载记忆
        
        Returns:
            int: 预加载的记忆数量
        """
        total_loaded = 0
        
        for topic in predicted_topics:
            # 检查缓存
            if topic in self._cache:
                cached = self._cache[topic]
                if (datetime.now() - cached["time"]).seconds < self.cache_ttl:
                    continue  # 缓存未过期，跳过
            
            # 搜索相关记忆
            nodes = self.query_engine.search_nodes(topic, limit=5)
            
            if nodes:
                self._cache[topic] = {
                    "nodes": nodes,
                    "time": datetime.now(),
                }
                total_loaded += len(nodes)
                logger.debug(f"预加载: '{topic}' → {len(nodes)} 条记忆")
        
        # 清理过期缓存
        self._cleanup_cache()
        
        return total_loaded
    
    def get_preloaded(self, topic: str) -> List[MemoryNode]:
        """获取预加载的记忆（如果命中）"""
        if topic not in self._cache:
            return []
        
        cached = self._cache[topic]
        if (datetime.now() - cached["time"]).seconds >= self.cache_ttl:
            return []
        
        return cached.get("nodes", [])
    
    def record_transition(self, from_topic: str, to_topic: str):
        """记录话题转移（用于学习用户行为模式）"""
        self._transition_stats[from_topic][to_topic] += 1
        logger.debug(f"话题转移记录: {from_topic} → {to_topic}")
    
    def _extract_topics(self, texts: List[str]) -> List[str]:
        """从文本中提取话题（简单实现）"""
        import re
        topics = []
        for text in texts:
            # 提取名词短语（简单规则）
            words = re.findall(r'[a-zA-Z_]{4,}', text.lower())
            words.extend(re.findall(r'[\u4e00-\u9fff]{2,}', text))
            topics.extend(words)
        return topics
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        now = datetime.now()
        expired = [
            topic for topic, data in self._cache.items()
            if (now - data["time"]).seconds >= self.cache_ttl
        ]
        for topic in expired:
            del self._cache[topic]
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            "cached_topics": len(self._cache),
            "total_transitions": sum(
                sum(counts.values()) for counts in self._transition_stats.values()
            ),
            "unique_transitions": sum(
                len(counts) for counts in self._transition_stats.values()
            ),
        }
