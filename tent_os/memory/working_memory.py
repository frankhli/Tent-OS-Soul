"""工作记忆管理 —— 人类工作记忆的 AI 模拟

核心设计：
1. 容量限制：最多 7±2 个组块（符合人类认知科学）
2. 动态更新：话题切换时自动替换
3. 优先级排序：相关性 + 时效性 + 情绪强度
4. 预加载集成：与 PredictivePreloader 协作

工作记忆组块来源：
- 用户画像（HOT 记忆）
- 当前话题相关记忆（WARM 记忆）
- 推理链结果（关联记忆）
- 预加载记忆（预测命中）
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.memory.graph import CognitiveGraph, MemoryNode
from tent_os.memory.graph_queries import GraphQueryEngine
from tent_os.memory.predictive_preloader import PredictivePreloader

logger = logging.getLogger("tent_os.memory.working")


# 人类工作记忆容量：7±2
WORKING_MEMORY_CAPACITY = 7
# 高优先级记忆预留槽位
RESERVED_SLOTS = 2


@dataclass
class WorkingMemorySlot:
    """工作记忆槽位"""
    node: MemoryNode
    priority: float        # 优先级 0-1
    source: str            # 来源：user_profile / topic_related / reasoning / preloaded
    loaded_at: datetime


class WorkingMemoryManager:
    """工作记忆管理器"""
    
    def __init__(self, graph: CognitiveGraph, preloader: PredictivePreloader = None):
        self.graph = graph
        self.query_engine = GraphQueryEngine(graph)
        self.preloader = preloader or PredictivePreloader(graph)
        
        # 当前工作记忆
        self._slots: List[WorkingMemorySlot] = []
        self._capacity = WORKING_MEMORY_CAPACITY
        
        # 当前话题（用于检测话题切换）
        self._current_topic: Optional[str] = None
    
    def update(self, 
               user_query: str,
               user_profile_nodes: List[MemoryNode] = None,
               emotion_intensity: float = 0) -> List[WorkingMemorySlot]:
        """更新工作记忆
        
        Args:
            user_query: 用户当前输入
            user_profile_nodes: 用户画像节点（HOT 记忆）
            emotion_intensity: 当前情绪强度
            
        Returns:
            List[WorkingMemorySlot]: 当前工作记忆中的槽位
        """
        # 1. 检测话题切换
        topic_changed = self._detect_topic_change(user_query)
        if topic_changed:
            logger.info(f"话题切换: {self._current_topic} → {user_query[:30]}")
            self._current_topic = user_query[:50]
            # 话题切换时，保留用户画像，替换其他记忆
            self._slots = [s for s in self._slots if s.source == "user_profile"]
        
        # 2. 收集候选记忆
        candidates = []
        
        # 2.1 用户画像（预留槽位）
        if user_profile_nodes:
            for node in user_profile_nodes[:RESERVED_SLOTS]:
                candidates.append(WorkingMemorySlot(
                    node=node,
                    priority=0.9,
                    source="user_profile",
                    loaded_at=datetime.now(),
                ))
        
        # 2.2 当前话题相关记忆
        related = self.query_engine.search_nodes(user_query, limit=10)
        for node in related:
            candidates.append(WorkingMemorySlot(
                node=node,
                priority=self._calculate_priority(node, user_query, emotion_intensity),
                source="topic_related",
                loaded_at=datetime.now(),
            ))
        
        # 2.3 推理链结果
        paths = self.query_engine.multi_hop_reasoning(
            self._get_relevant_node_id(user_query), max_hops=2, min_strength=0.3
        )
        for path in paths[:3]:
            if len(path.nodes) > 1:
                end_node = path.nodes[-1]
                candidates.append(WorkingMemorySlot(
                    node=end_node,
                    priority=path.total_strength * 0.8,
                    source="reasoning",
                    loaded_at=datetime.now(),
                ))
        
        # 2.4 预加载记忆
        preloaded = self.preloader.get_preloaded(user_query)
        for node in preloaded:
            candidates.append(WorkingMemorySlot(
                node=node,
                priority=0.6,
                source="preloaded",
                loaded_at=datetime.now(),
            ))
        
        # 3. 去重（同一节点只保留优先级最高的）
        seen_nodes = {}
        for slot in candidates:
            nid = slot.node.id
            if nid not in seen_nodes or seen_nodes[nid].priority < slot.priority:
                seen_nodes[nid] = slot
        
        # 4. 按优先级排序，取前 capacity 个
        sorted_slots = sorted(seen_nodes.values(), key=lambda s: s.priority, reverse=True)
        
        # 5. 保留用户画像，填充其他槽位
        profile_slots = [s for s in sorted_slots if s.source == "user_profile"]
        other_slots = [s for s in sorted_slots if s.source != "user_profile"]
        
        available_slots = self._capacity - len(profile_slots)
        self._slots = profile_slots + other_slots[:available_slots]
        
        # 6. 记录访问（复习效应）
        for slot in self._slots:
            self.graph.record_access(slot.node.id)
        
        # 7. 触发预加载（为下一轮做准备）
        predicted_topics = self.preloader.predict_next_topics(user_query)
        if predicted_topics:
            self.preloader.preload_for_prediction(predicted_topics)
        
        return self._slots
    
    def get_context_text(self, max_chars: int = 2000) -> str:
        """将工作记忆转换为文本（用于 prompt 注入）"""
        if not self._slots:
            return ""
        
        lines = ["## 相关记忆"]
        
        # 按来源分组
        by_source: Dict[str, List[WorkingMemorySlot]] = {}
        for slot in self._slots:
            if slot.source not in by_source:
                by_source[slot.source] = []
            by_source[slot.source].append(slot)
        
        source_names = {
            "user_profile": "用户画像",
            "topic_related": "话题相关",
            "reasoning": "推理关联",
            "preloaded": "预加载",
        }
        
        for source, slots in by_source.items():
            name = source_names.get(source, source)
            lines.append(f"### {name}")
            for slot in slots:
                confidence_marker = "✓" if slot.node.confidence > 0.7 else "?" if slot.node.confidence < 0.4 else "~"
                lines.append(f"{confidence_marker} {slot.node.content[:120]}")
            lines.append("")
        
        text = "\n".join(lines)
        
        # 截断到最大长度
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...（更多记忆已省略）"
        
        return text
    
    def get_slot_count(self) -> int:
        """获取当前工作记忆数量"""
        return len(self._slots)
    
    def clear(self):
        """清空工作记忆"""
        self._slots = []
        self._current_topic = None
    
    def _detect_topic_change(self, user_query: str) -> bool:
        """检测话题是否切换"""
        if not self._current_topic:
            return True
        
        # 简单判断：如果查询与当前话题没有共享关键词，认为切换了
        current_words = set(self._current_topic.lower().split())
        query_words = set(user_query.lower().split())
        
        # 提取中文
        import re
        current_words.update(re.findall(r'[\u4e00-\u9fff]{2,}', self._current_topic.lower()))
        query_words.update(re.findall(r'[\u4e00-\u9fff]{2,}', user_query.lower()))
        
        if not current_words or not query_words:
            return False
        
        shared = current_words & query_words
        similarity = len(shared) / max(len(current_words), len(query_words))
        
        return similarity < 0.3  # 共享词 < 30% 认为话题切换
    
    def _calculate_priority(self, node: MemoryNode, query: str, emotion_intensity: float) -> float:
        """计算记忆优先级"""
        score = 0.0
        
        # 1. 置信度
        score += node.confidence * 0.3
        
        # 2. 时效性（越新越高）
        if node.created_at:
            days_old = (datetime.now() - node.created_at).days
            recency_score = max(0, 1.0 - days_old / 30)  # 30 天内线性衰减
            score += recency_score * 0.2
        
        # 3. 访问频率
        score += min(0.2, node.access_count * 0.02)
        
        # 4. 情绪强度加成
        if emotion_intensity > 0.5:
            score += emotion_intensity * 0.1
        
        # 5. 验证次数
        score += min(0.1, node.verification_count * 0.02)
        
        # 6. 矛盾惩罚
        score -= min(0.2, node.contradiction_count * 0.05)
        
        return max(0.0, min(1.0, score))
    
    def _get_relevant_node_id(self, query: str) -> Optional[str]:
        """获取与查询最相关的节点 ID（用于推理起点）"""
        nodes = self.query_engine.search_nodes(query, limit=1)
        if nodes:
            return nodes[0].id
        return None
    
    def get_stats(self) -> Dict:
        """获取工作记忆统计"""
        by_source = {}
        for slot in self._slots:
            by_source[slot.source] = by_source.get(slot.source, 0) + 1
        
        return {
            "total_slots": len(self._slots),
            "capacity": self._capacity,
            "utilization": round(len(self._slots) / self._capacity, 2),
            "by_source": by_source,
            "current_topic": self._current_topic,
        }
