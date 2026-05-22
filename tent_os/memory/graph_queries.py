"""认知图谱查询引擎 —— 多跳推理、因果推理、时序推理、矛盾检测

基于 SQLite CTE（Common Table Expression）递归查询实现图遍历。
无需引入 Neo4j 等外部依赖。

查询类型：
1. 多跳推理（Multi-hop）：从 A 出发经过 N 跳到达 B
2. 因果推理（Causal）：找出事件的原因和后果
3. 时序推理（Temporal）：查询某个时间点的记忆状态
4. 矛盾检测（Contradiction）：发现记忆间的冲突
5. 关联发现（Association）：找到与查询最相关的记忆簇
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from tent_os.memory.graph import CognitiveGraph, MemoryNode, MemoryEdge

logger = logging.getLogger("tent_os.memory.graph_queries")


@dataclass
class ReasoningPath:
    """推理路径 —— 从起点到终点的一系列节点和边"""
    nodes: List[MemoryNode]
    edges: List[MemoryEdge]
    total_strength: float      # 路径总强度（各边强度的乘积）
    hops: int
    
    def to_natural_language(self) -> str:
        """将推理路径转换为自然语言描述"""
        if not self.nodes:
            return ""
        parts = [self.nodes[0].content]
        for edge, node in zip(self.edges, self.nodes[1:]):
            relation_desc = {
                "causal": "导致",
                "similar": "类似于",
                "contradictory": "与...矛盾",
                "temporal": "在...之前/之后",
                "hierarchical": "属于",
                "related": "与...相关",
            }.get(edge.relation_type, "关联")
            parts.append(f" → [{relation_desc}] → {node.content}")
        return "".join(parts)


@dataclass
class ContradictionReport:
    """矛盾检测报告"""
    node_a: MemoryNode
    node_b: MemoryNode
    relation: MemoryEdge
    severity: float            # 严重程度 0-1
    suggestion: str            # 解决建议


class GraphQueryEngine:
    """图查询引擎 —— 认知图谱的高级查询能力"""
    
    def __init__(self, graph: CognitiveGraph):
        self.graph = graph
        self.db = graph.db
    
    # ========== 多跳推理 ==========
    
    def multi_hop_reasoning(self, start_node_id: str, target_keyword: Optional[str] = None,
                           max_hops: int = 3, min_strength: float = 0.3) -> List[ReasoningPath]:
        """多跳推理——从起始节点出发，找到可达的相关节点
        
        示例：
            "用户喜欢辣" → (similar) → "火锅" → (related) → "重庆"
            
        Args:
            start_node_id: 起始节点 ID
            target_keyword: 目标关键词（可选，用于过滤终点）
            max_hops: 最大跳数
            min_strength: 最小边强度阈值
            
        Returns:
            List[ReasoningPath]: 找到的推理路径，按总强度排序
        """
        # 使用 CTE 递归查询
        sql = """
        WITH RECURSIVE paths(path, node_id, hops, total_strength) AS (
            -- 起始节点
            SELECT 
                json_array(?),
                ?,
                0,
                1.0
            
            UNION ALL
            
            -- 递归扩展
            SELECT 
                json_insert(p.path, '$[#]', e.target_id),
                e.target_id,
                p.hops + 1,
                p.total_strength * e.strength
            FROM paths p
            JOIN edges e ON p.node_id = e.source_id
            WHERE p.hops < ?
              AND e.strength >= ?
              AND json_type(json_extract(p.path, '$')) = 'array'
              AND e.target_id NOT IN (
                  SELECT value FROM json_each(p.path)
              )
        )
        SELECT path, node_id, hops, total_strength FROM paths
        WHERE hops > 0
        ORDER BY total_strength DESC
        LIMIT 50
        """
        
        try:
            rows = self.db.execute(sql, (start_node_id, start_node_id, max_hops, min_strength)).fetchall()
        except sqlite3.OperationalError as e:
            # SQLite 可能不支持 json_insert/json_each（旧版本）
            logger.warning(f"CTE 递归查询失败（SQLite 版本可能过旧）: {e}")
            # 回退到 Python 实现的 BFS
            return self._multi_hop_bfs(start_node_id, target_keyword, max_hops, min_strength)
        
        paths = []
        seen_targets = set()
        
        for row in rows:
            try:
                path_ids = json.loads(row["path"])
                if not isinstance(path_ids, list):
                    continue
                
                target_id = row["node_id"]
                if target_id in seen_targets:
                    continue
                seen_targets.add(target_id)
                
                # 如果指定了目标关键词，过滤终点
                if target_keyword:
                    target_node = self.graph.get_node(target_id)
                    if not target_node or target_keyword.lower() not in target_node.content.lower():
                        continue
                
                # 构建完整路径
                nodes = []
                edges = []
                for i in range(len(path_ids) - 1):
                    src = self.graph.get_node(path_ids[i])
                    dst = self.graph.get_node(path_ids[i + 1])
                    if src and dst:
                        nodes.append(src)
                        # 获取边
                        edge_rows = self.db.execute(
                            "SELECT * FROM edges WHERE source_id = ? AND target_id = ?",
                            (path_ids[i], path_ids[i + 1])
                        ).fetchall()
                        if edge_rows:
                            edges.append(MemoryEdge(
                                source_id=edge_rows[0]["source_id"],
                                target_id=edge_rows[0]["target_id"],
                                relation_type=edge_rows[0]["relation_type"],
                                strength=edge_rows[0]["strength"],
                                evidence=edge_rows[0]["evidence"] or "",
                                created_at=datetime.fromisoformat(edge_rows[0]["created_at"]),
                            ))
                
                if nodes and len(nodes) > 1:
                    paths.append(ReasoningPath(
                        nodes=nodes,
                        edges=edges,
                        total_strength=row["total_strength"],
                        hops=row["hops"]
                    ))
            except Exception as e:
                logger.debug(f"路径解析失败: {e}")
                continue
        
        return paths
    
    def _multi_hop_bfs(self, start_node_id: str, target_keyword: Optional[str],
                       max_hops: int, min_strength: float) -> List[ReasoningPath]:
        """Python 实现的 BFS 多跳推理（SQLite 不支持 JSON CTE 时的回退）"""
        from collections import deque
        
        queue = deque([(start_node_id, [start_node_id], [], 1.0)])
        results = []
        seen = set()
        
        while queue:
            current_id, path_ids, edges, strength = queue.popleft()
            
            if len(path_ids) > max_hops + 1:
                continue
            
            # 获取出边
            edge_rows = self.db.execute(
                "SELECT * FROM edges WHERE source_id = ? AND strength >= ?",
                (current_id, min_strength)
            ).fetchall()
            
            for row in edge_rows:
                target_id = row["target_id"]
                if target_id in path_ids:  # 避免循环
                    continue
                
                new_strength = strength * row["strength"]
                new_path = path_ids + [target_id]
                new_edges = edges + [MemoryEdge(
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    relation_type=row["relation_type"],
                    strength=row["strength"],
                    evidence=row["evidence"] or "",
                    created_at=datetime.fromisoformat(row["created_at"]),
                )]
                
                # 检查是否到达目标
                if len(new_path) > 1:
                    target_node = self.graph.get_node(target_id)
                    if target_node:
                        if target_keyword is None or target_keyword.lower() in target_node.content.lower():
                            path_key = tuple(new_path)
                            if path_key not in seen:
                                seen.add(path_key)
                                nodes = [self.graph.get_node(nid) for nid in new_path]
                                nodes = [n for n in nodes if n]
                                if len(nodes) > 1:
                                    results.append(ReasoningPath(
                                        nodes=nodes, edges=new_edges,
                                        total_strength=new_strength, hops=len(new_path) - 1
                                    ))
                
                if len(new_path) <= max_hops:
                    queue.append((target_id, new_path, new_edges, new_strength))
        
        # 去重并按强度排序
        results.sort(key=lambda p: p.total_strength, reverse=True)
        return results[:20]
    
    # ========== 因果推理 ==========
    
    def causal_reasoning(self, event_node_id: str) -> Dict[str, List[MemoryNode]]:
        """因果推理——找出事件的原因和后果
        
        Returns:
            {"causes": [...], "effects": [...]}
        """
        # 原因：指向该节点的 causal 边（作为 target）
        cause_rows = self.db.execute(
            "SELECT source_id FROM edges WHERE target_id = ? AND relation_type = 'causal' ORDER BY strength DESC",
            (event_node_id,)
        ).fetchall()
        causes = [self.graph.get_node(r["source_id"]) for r in cause_rows]
        causes = [n for n in causes if n]
        
        # 后果：从该节点出发的 causal 边（作为 source）
        effect_rows = self.db.execute(
            "SELECT target_id FROM edges WHERE source_id = ? AND relation_type = 'causal' ORDER BY strength DESC",
            (event_node_id,)
        ).fetchall()
        effects = [self.graph.get_node(r["target_id"]) for r in effect_rows]
        effects = [n for n in effects if n]
        
        return {"causes": causes, "effects": effects}
    
    # ========== 时序推理 ==========
    
    def temporal_reasoning(self, node_id: str) -> Dict[str, List[MemoryNode]]:
        """时序推理——找出事件的前后关系
        
        Returns:
            {"before": [...], "after": [...], "concurrent": [...]}
        """
        # 之前的事件：temporal 边，direction = "before"
        before_rows = self.db.execute(
            """SELECT target_id FROM edges
               WHERE source_id = ? AND relation_type = 'temporal' AND direction = 'after'""",
            (node_id,)
        ).fetchall()
        before = [self.graph.get_node(r["target_id"]) for r in before_rows]
        before = [n for n in before if n]
        
        # 之后的事件：temporal 边，direction = "after"
        after_rows = self.db.execute(
            """SELECT target_id FROM edges
               WHERE source_id = ? AND relation_type = 'temporal' AND direction = 'before'""",
            (node_id,)
        ).fetchall()
        after = [self.graph.get_node(r["target_id"]) for r in after_rows]
        after = [n for n in after if n]
        
        # 并发事件：创建时间接近的节点
        node = self.graph.get_node(node_id)
        concurrent = []
        if node:
            window = timedelta(hours=1)
            start = (node.created_at - window).isoformat()
            end = (node.created_at + window).isoformat()
            rows = self.db.execute(
                "SELECT id FROM nodes WHERE created_at BETWEEN ? AND ? AND id != ? LIMIT 10",
                (start, end, node_id)
            ).fetchall()
            concurrent = [self.graph.get_node(r["id"]) for r in rows]
            concurrent = [n for n in concurrent if n]
        
        return {"before": before, "after": after, "concurrent": concurrent}
    
    def query_at_time(self, timestamp: datetime, keyword: Optional[str] = None) -> List[MemoryNode]:
        """查询某个时间点的记忆状态
        
        返回在该时间点之前创建、且尚未失效的记忆。
        
        示例："用户去年这个时候在做什么？"
        """
        ts_str = timestamp.isoformat()
        
        if keyword:
            pattern = f"%{keyword}%"
            rows = self.db.execute(
                """SELECT * FROM nodes
                   WHERE created_at <= ?
                     AND (valid_to IS NULL OR valid_to >= ?)
                     AND content LIKE ?
                   ORDER BY created_at DESC
                   LIMIT 20""",
                (ts_str, ts_str, pattern)
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT * FROM nodes
                   WHERE created_at <= ?
                     AND (valid_to IS NULL OR valid_to >= ?)
                   ORDER BY created_at DESC
                   LIMIT 20""",
                (ts_str, ts_str)
            ).fetchall()
        
        return [self.graph._row_to_node(r) for r in rows]
    
    def track_belief_change(self, keyword: str) -> List[MemoryNode]:
        """追踪信念变化——找到关于某个主题的所有记忆，按时间排序
        
        示例："用户口味是什么时候变的？"
        """
        pattern = f"%{keyword}%"
        rows = self.db.execute(
            """SELECT * FROM nodes
               WHERE content LIKE ? AND memory_type IN ('preference', 'belief')
               ORDER BY created_at ASC""",
            (pattern,)
        ).fetchall()
        return [self.graph._row_to_node(r) for r in rows]
    
    # ========== 矛盾检测 ==========
    
    def detect_contradictions(self, node_id: Optional[str] = None,
                              min_confidence: float = 0.3) -> List[ContradictionReport]:
        """矛盾检测——发现记忆间的直接矛盾和间接矛盾
        
        Args:
            node_id: 如果指定，只检测与该节点相关的矛盾；否则全局扫描
            min_confidence: 只检查置信度高于此阈值的节点
            
        Returns:
            List[ContradictionReport]: 矛盾报告列表
        """
        reports = []
        
        # 1. 直接矛盾：通过 contradictory 边连接
        if node_id:
            rows = self.db.execute(
                """SELECT * FROM edges
                   WHERE (source_id = ? OR target_id = ?) AND relation_type = 'contradictory'""",
                (node_id, node_id)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM edges WHERE relation_type = 'contradictory'"
            ).fetchall()
        
        for row in rows:
            node_a = self.graph.get_node(row["source_id"])
            node_b = self.graph.get_node(row["target_id"])
            if node_a and node_b and node_a.confidence >= min_confidence and node_b.confidence >= min_confidence:
                severity = (node_a.confidence + node_b.confidence) / 2 * row["strength"]
                reports.append(ContradictionReport(
                    node_a=node_a, node_b=node_b,
                    relation=MemoryEdge(
                        source_id=row["source_id"], target_id=row["target_id"],
                        relation_type="contradictory", strength=row["strength"],
                        evidence=row["evidence"] or "", created_at=datetime.fromisoformat(row["created_at"]),
                    ),
                    severity=severity,
                    suggestion=self._suggest_resolution(node_a, node_b)
                ))
        
        # 2. 间接矛盾：通过类型冲突检测
        # 例如：两个 preference 类型节点，内容互相矛盾
        if not node_id:  # 全局扫描时才做
            reports.extend(self._detect_indirect_contradictions(min_confidence))
        
        # 按严重程度排序
        reports.sort(key=lambda r: r.severity, reverse=True)
        return reports
    
    def _detect_indirect_contradictions(self, min_confidence: float) -> List[ContradictionReport]:
        """检测间接矛盾——基于关键词冲突"""
        reports = []
        
        # 获取高置信度的 preference/belief 节点
        rows = self.db.execute(
            """SELECT * FROM nodes
               WHERE memory_type IN ('preference', 'belief')
                 AND confidence >= ?""",
            (min_confidence,)
        ).fetchall()
        
        nodes = [self.graph._row_to_node(r) for r in rows]
        
        # 简单策略：检查否定词对
        negation_pairs = [
            ("喜欢", "讨厌"), ("喜欢", "不喜欢"), ("爱", "恨"),
            ("能", "不能"), ("会", "不会"), ("是", "不是"),
            ("有", "没有"), ("要", "不要"), ("想", "不想"),
            ("支持", "反对"), ("同意", "不同意"),
            ("yes", "no"), ("true", "false"), ("can", "cannot"),
            ("like", "dislike"), ("love", "hate"), ("want", "don't want"),
        ]
        
        for i, node_a in enumerate(nodes):
            for node_b in nodes[i+1:]:
                # 检查是否共享主题但有否定词对
                for pos, neg in negation_pairs:
                    if pos in node_a.content and neg in node_b.content:
                        # 进一步检查是否有共享上下文词（避免误报）
                        a_words = set(node_a.content.lower().split())
                        b_words = set(node_b.content.lower().split())
                        shared = a_words & b_words - {pos.lower(), neg.lower()}
                        if len(shared) >= 2:
                            severity = (node_a.confidence + node_b.confidence) / 2
                            reports.append(ContradictionReport(
                                node_a=node_a, node_b=node_b,
                                relation=MemoryEdge(
                                    source_id=node_a.id, target_id=node_b.id,
                                    relation_type="contradictory", strength=0.5,
                                    evidence=f"关键词冲突: {pos} vs {neg}",
                                    created_at=datetime.now(),
                                ),
                                severity=severity,
                                suggestion=self._suggest_resolution(node_a, node_b)
                            ))
        
        return reports
    
    def _suggest_resolution(self, node_a: MemoryNode, node_b: MemoryNode) -> str:
        """生成矛盾解决建议"""
        # 优先保留：更高置信度、更近期、更多验证的
        if node_a.confidence > node_b.confidence + 0.2:
            return f"保留 '{node_a.content[:30]}...'（置信度更高: {node_a.confidence:.2f} > {node_b.confidence:.2f}）"
        elif node_b.confidence > node_a.confidence + 0.2:
            return f"保留 '{node_b.content[:30]}...'（置信度更高: {node_b.confidence:.2f} > {node_a.confidence:.2f}）"
        elif node_a.created_at > node_b.created_at:
            return f"保留 '{node_a.content[:30]}...'（更近期）"
        else:
            return f"两个记忆都可能有效，建议用户确认：'{node_a.content[:30]}...' vs '{node_b.content[:30]}...'"
    
    # ========== 关联发现 ==========
    
    def find_related_cluster(self, node_id: str, max_depth: int = 2) -> List[MemoryNode]:
        """找到与节点相关的记忆簇（子图）
        
        类似于社区发现，但针对单个节点的局部簇。
        """
        # 使用 BFS 收集邻居
        visited = {node_id}
        queue = [(node_id, 0)]
        cluster_ids = []
        
        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            
            # 出边和入边
            rows = self.db.execute(
                """SELECT target_id as id FROM edges WHERE source_id = ? AND strength >= 0.3
                   UNION
                   SELECT source_id as id FROM edges WHERE target_id = ? AND strength >= 0.3""",
                (current_id, current_id)
            ).fetchall()
            
            for row in rows:
                nid = row["id"]
                if nid not in visited:
                    visited.add(nid)
                    cluster_ids.append(nid)
                    queue.append((nid, depth + 1))
        
        return [self.graph.get_node(nid) for nid in cluster_ids if nid != node_id]
    
    def search_nodes(self, keyword: str, limit: int = 20) -> List[MemoryNode]:
        """关键词搜索节点 —— 委托给 CognitiveGraph"""
        return self.graph.search_nodes(keyword, limit)
    
    def get_memory_timeline(self, node_ids: List[str]) -> List[MemoryNode]:
        """将一组记忆按时间排序，形成时间线"""
        if not node_ids:
            return []
        
        placeholders = ",".join("?" * len(node_ids))
        rows = self.db.execute(
            f"SELECT * FROM nodes WHERE id IN ({placeholders}) ORDER BY created_at ASC",
            node_ids
        ).fetchall()
        return [self.graph._row_to_node(r) for r in rows]
