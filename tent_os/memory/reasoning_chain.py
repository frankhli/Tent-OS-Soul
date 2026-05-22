"""推理链 —— 认知层面的记忆关联推理

提供三种推理模式：
1. 多跳推理：从 A 经过 N 跳到达 B
2. 因果推理：找出事件的原因和后果
3. 时序推理：查询某个时间点的记忆状态

这些能力基于认知图谱的 GraphQueryEngine，提供更高级的语义封装。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.memory.graph import CognitiveGraph, MemoryNode
from tent_os.memory.graph_queries import GraphQueryEngine, ReasoningPath

logger = logging.getLogger("tent_os.memory.reasoning")


class ReasoningChain:
    """推理链引擎 —— 让记忆'思考'"""
    
    def __init__(self, graph: CognitiveGraph):
        self.graph = graph
        self.query_engine = GraphQueryEngine(graph)
    
    # ========== 多跳推理 ==========
    
    def infer_related(self, query: str, max_hops: int = 3) -> List[ReasoningPath]:
        """推断与查询相关的记忆路径
        
        示例：
            query="推荐晚餐"
            → Hop 1: "晚餐偏好" → "用户喜欢辣"
            → Hop 2: "辣" → "火锅"、"川菜"
            → Hop 3: 检查时效 → "用户上周吃火锅后不舒服"
            → 结论：推荐川菜，避开火锅
        """
        # 1. 先找到与查询最相关的起始节点
        start_nodes = self.query_engine.search_nodes(query)
        if not start_nodes:
            logger.debug(f"推理链：未找到与 '{query}' 相关的起始节点")
            return []
        
        # 2. 从每个起始节点出发做多跳推理
        all_paths = []
        for start_node in start_nodes[:3]:  # 最多从 3 个起始点出发
            paths = self.query_engine.multi_hop_reasoning(
                start_node.id, max_hops=max_hops, min_strength=0.3
            )
            all_paths.extend(paths)
        
        # 3. 去重并排序
        seen_targets = set()
        unique_paths = []
        for path in sorted(all_paths, key=lambda p: p.total_strength, reverse=True):
            target_id = path.nodes[-1].id if path.nodes else None
            if target_id and target_id not in seen_targets:
                seen_targets.add(target_id)
                unique_paths.append(path)
        
        return unique_paths[:10]
    
    def infer_preferences(self, topic: str) -> List[MemoryNode]:
        """推断用户在某个主题上的偏好
        
        示例：
            topic="食物"
            → 找到 "preference" 类型的相关节点
            → 返回 "用户喜欢辣"、"用户不吃香菜"等
        """
        # 搜索相关偏好节点
        pref_nodes = self.graph.get_nodes_by_type("preference", min_confidence=0.3, limit=50)
        
        # 过滤与主题相关的
        topic_lower = topic.lower()
        related = []
        for node in pref_nodes:
            if topic_lower in node.content.lower():
                related.append(node)
        
        # 按置信度排序
        related.sort(key=lambda n: n.confidence, reverse=True)
        return related[:10]
    
    # ========== 因果推理 ==========
    
    def explain_why(self, event_description: str) -> Dict[str, List[MemoryNode]]:
        """解释为什么——找出事件的原因
        
        示例：
            event="用户取消订单"
            → 原因："用户对价格不满意"、"用户找到了更便宜的替代品"
            → 后果："需要处理退款"、"用户可能流失"
        """
        # 找到与事件描述最匹配的节点
        nodes = self.query_engine.search_nodes(event_description, limit=5)
        if not nodes:
            return {"causes": [], "effects": [], "concurrent": []}
        
        # 取最匹配的节点进行因果推理
        target_node = nodes[0]
        return self.query_engine.causal_reasoning(target_node.id)
    
    def predict_consequences(self, action: str) -> List[str]:
        """预测行动后果
        
        基于因果链预测可能的后果。
        """
        causes_and_effects = self.explain_why(action)
        effects = causes_and_effects.get("effects", [])
        
        # 生成自然语言描述
        consequences = []
        for effect in effects[:5]:
            consequences.append(effect.content)
        
        return consequences
    
    # ========== 时序推理 ==========
    
    def what_happened_before(self, event: str) -> List[MemoryNode]:
        """某事之前发生了什么"""
        nodes = self.query_engine.search_nodes(event, limit=3)
        if not nodes:
            return []
        
        temporal = self.query_engine.temporal_reasoning(nodes[0].id)
        return temporal.get("before", [])
    
    def what_happened_after(self, event: str) -> List[MemoryNode]:
        """某事之后发生了什么"""
        nodes = self.query_engine.search_nodes(event, limit=3)
        if not nodes:
            return []
        
        temporal = self.query_engine.temporal_reasoning(nodes[0].id)
        return temporal.get("after", [])
    
    def what_was_true_at(self, timestamp: datetime, topic: str = None) -> List[MemoryNode]:
        """在某个时间点什么是真的
        
        示例："用户去年这个时候在做什么？"
        """
        return self.query_engine.query_at_time(timestamp, topic)
    
    def track_change(self, topic: str) -> List[Dict]:
        """追踪某个主题的变化历程
        
        示例："用户口味是什么时候变的？"
        → 返回按时间排序的信念/偏好变化
        """
        beliefs = self.query_engine.track_belief_change(topic)
        
        changes = []
        for i, node in enumerate(beliefs):
            changes.append({
                "time": node.created_at.isoformat(),
                "content": node.content,
                "confidence": node.confidence,
                "type": node.memory_type,
            })
        
        return changes
    
    # ========== 综合推理 ==========
    
    def answer_complex_question(self, question: str) -> Dict:
        """回答复杂问题（需要多步推理）
        
        示例问题：
            "上次推荐的那家餐厅，用户后来去了吗？"
            → 1. 找到"餐厅推荐"相关记忆
            → 2. 找到推荐的具体餐厅
            → 3. 搜索该餐厅名+用户行为
            → 4. 返回结论
        """
        result = {
            "answer": "",
            "reasoning_steps": [],
            "confidence": 0.0,
            "sources": [],
        }
        
        # 简单关键词匹配路由
        q_lower = question.lower()
        
        if any(kw in q_lower for kw in ["为什么", "why", "原因", "cause"]):
            # 因果推理
            causes = self.explain_why(question)
            result["reasoning_steps"].append("因果推理")
            result["sources"] = [n.content for n in causes.get("causes", [])]
            if result["sources"]:
                result["answer"] = f"可能的原因: {'; '.join(result['sources'][:3])}"
                result["confidence"] = 0.6
        
        elif any(kw in q_lower for kw in ["之前", "before", "以前", "之前"]):
            # 时序推理
            before = self.what_happened_before(question)
            result["reasoning_steps"].append("时序推理")
            result["sources"] = [n.content for n in before]
            if result["sources"]:
                result["answer"] = f"在此之前: {'; '.join(result['sources'][:3])}"
                result["confidence"] = 0.5
        
        elif any(kw in q_lower for kw in ["偏好", "喜欢", "preference", "like"]):
            # 偏好推理
            topic = question.replace("喜欢", "").replace("偏好", "").replace("preference", "").strip()
            prefs = self.infer_preferences(topic or "general")
            result["reasoning_steps"].append("偏好推理")
            result["sources"] = [n.content for n in prefs]
            if result["sources"]:
                result["answer"] = f"相关偏好: {'; '.join(result['sources'][:3])}"
                result["confidence"] = max((n.confidence for n in prefs), default=0)
        
        elif any(kw in q_lower for kw in ["上次", "上次", "last time", "previous"]):
            # 关联推理
            paths = self.infer_related(question)
            result["reasoning_steps"].append("关联推理")
            if paths:
                best = paths[0]
                result["answer"] = best.to_natural_language()
                result["confidence"] = best.total_strength
                result["sources"] = [n.content for n in best.nodes]
        
        else:
            # 默认：多跳推理
            paths = self.infer_related(question)
            result["reasoning_steps"].append("多跳推理")
            if paths:
                best = paths[0]
                result["answer"] = best.to_natural_language()
                result["confidence"] = best.total_strength
                result["sources"] = [n.content for n in best.nodes]
        
        if not result["answer"]:
            result["answer"] = "根据现有记忆，无法确定答案。"
            result["confidence"] = 0.0
        
        return result
