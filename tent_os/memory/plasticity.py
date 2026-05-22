"""神经可塑性引擎 —— Tent OS 2.0 记忆巩固与演化系统

替代原有 DreamingEngine，实现：
1. 事件驱动（而非定时批处理）
2. 动态权重（而非固定权重）
3. 主动遗忘（模拟艾宾浩斯曲线）
4. 情绪维度（人类对情绪记忆更深刻）

四阶段架构：
    Light   —— 实时处理，新记忆摄入后立即执行
    Deep    —— 近实时处理，session 结束或每 30 分钟
    REM     —— 定时处理，每天凌晨 3 点全局反思
    Forgetting —— 持续处理，后台定期衰减

事件触发器：
    memory.ingest       → Light 阶段
    memory.contradiction → 冲突解决
    user.feedback        → 权重调整
    session.end          → Deep 阶段
    scheduler.cron       → REM 阶段
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.memory.graph import CognitiveGraph, MemoryNode, MemoryEdge, generate_node_id, generate_content_hash
from tent_os.memory.graph_queries import GraphQueryEngine
from tent_os.memory.emotion_detector import EmotionDetector, EmotionState
from tent_os.memory.forgetting import ForgettingEngine
from tent_os.memory.budget import MemoryBudget

logger = logging.getLogger("tent_os.memory.plasticity")


class PlasticityEngine:
    """神经可塑性引擎"""
    
    def __init__(self, bus=None, config: Dict = None, llm=None,
                 graph_db_path: str = "./tent_memory/graph.db",
                 memory_db_path: str = "./tent_memory/memory.db"):
        self.bus = bus
        self.config = config or {}
        self.llm = llm
        
        # 子系统
        self.graph = CognitiveGraph(graph_db_path)
        self.query_engine = GraphQueryEngine(self.graph)
        self.emotion_detector = EmotionDetector(llm)
        self.forgetting = ForgettingEngine(graph_db_path, memory_db_path)
        self.budget = MemoryBudget(
            budget_config=self.config.get("memory_budget"),
            graph_db_path=graph_db_path
        )
        
        # 配置
        self.enabled = self.config.get("dreaming_enabled", True)
        self.light_enabled = self.config.get("light_enabled", True)
        self.deep_enabled = self.config.get("deep_enabled", True)
        self.rem_enabled = self.config.get("rem_enabled", True)
        self.forgetting_enabled = self.config.get("forgetting_enabled", True)
        
        # 深度阶段配置
        self.deep_interval_minutes = self.config.get("deep_interval_minutes", 30)
        self.rem_schedule = self.config.get("rem_schedule", "0 3 * * *")  # 每天凌晨 3 点
        
        # 短期记忆缓存（24h 过期）
        self._short_term: List[MemoryNode] = []
        self._short_term_max = 100
        
        # 运行状态
        self._running = False
        self._deep_task = None
        self._rem_task = None
        self._forgetting_task = None
    
    async def start(self):
        """启动可塑性引擎"""
        if not self.enabled:
            logger.info("神经可塑性引擎已禁用")
            return
        
        self._running = True
        
        # 启动后台任务
        if self.deep_enabled:
            self._deep_task = asyncio.create_task(self._deep_loop())
        if self.rem_enabled:
            self._rem_task = asyncio.create_task(self._rem_loop())
        if self.forgetting_enabled:
            self._forgetting_task = asyncio.create_task(self._forgetting_loop())
        
        logger.info("神经可塑性引擎已启动")
        
        if self.bus:
            await self.bus.publish("memory.plasticity.status", json.dumps({
                "status": "started",
                "timestamp": datetime.now().isoformat(),
            }).encode())
    
    async def stop(self):
        """停止可塑性引擎"""
        self._running = False
        
        for task in [self._deep_task, self._rem_task, self._forgetting_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.graph.close()
        logger.info("神经可塑性引擎已停止")
    
    # ========== Light 阶段：实时处理 ==========
    
    async def on_memory_ingest(self, content: str, uri: str, memory_type: str = "conversation",
                                user_id: str = None, source_session: str = "",
                                emotion: Optional[EmotionState] = None) -> MemoryNode:
        """Light 阶段 —— 新记忆摄入时实时处理
        
        触发：每次 memory.ingest 后
        功能：
            1. 初步分类
            2. 去重（content_hash）
            3. 情绪标记
            4. 写入 short-term graph
            5. 尝试提取关系边
        """
        if not self.light_enabled:
            return None
        
        # 计算内容哈希
        content_hash = generate_content_hash(content)
        
        # 检查是否已存在
        existing = self.graph.find_by_content_hash(content_hash)
        if existing:
            # 更新访问统计
            self.graph.record_access(existing.id)
            logger.debug(f"Light: 记忆已存在，更新访问 {existing.id}")
            return existing
        
        # 情绪检测（如果没有传入）
        if emotion is None:
            emotion = self.emotion_detector.detect_fast(content)
        
        # 根据情绪调整初始置信度
        base_confidence = 0.5
        if emotion.intensity > 0.7:
            # 情绪强烈 → 置信度提升（人类对情绪记忆更深刻）
            base_confidence = min(0.9, 0.5 + emotion.intensity * 0.3)
        
        # 创建节点
        node = MemoryNode(
            id=generate_node_id(content, source_session, uri),
            content=content[:500],  # 摘要长度限制
            content_hash=content_hash,
            confidence=base_confidence,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            source_session=source_session,
            source_chunk=uri,
            memory_type=memory_type,
            access_count=1,
            last_accessed=datetime.now(),
        )
        
        # 写入图谱
        is_new = self.graph.add_node(node)
        
        # 存入短期记忆缓存
        self._short_term.append(node)
        if len(self._short_term) > self._short_term_max:
            self._short_term.pop(0)
        
        # 尝试提取简单关系边（关键词匹配）
        self._extract_simple_edges(node)
        
        # 广播事件
        if self.bus:
            await self.bus.publish("memory.plasticity.light", json.dumps({
                "node_id": node.id,
                "memory_type": memory_type,
                "is_new": is_new,
                "confidence": node.confidence,
                "emotion": {
                    "primary": emotion.primary,
                    "intensity": emotion.intensity,
                },
                "timestamp": datetime.now().isoformat(),
            }).encode())
        
        logger.debug(f"Light: {'新增' if is_new else '更新'}记忆 {node.id} ({memory_type}, conf={node.confidence:.2f})")
        return node
    
    def _extract_simple_edges(self, node: MemoryNode):
        """从节点内容中提取简单的关系边"""
        # 简单策略：如果内容与已有节点共享关键词，建立 related 边
        import re
        
        # 提取关键词（简单分词）
        words = set(re.findall(r'[a-zA-Z_]{4,}', node.content.lower()))
        words.update(re.findall(r'[\u4e00-\u9fff]{2,}', node.content))
        
        if len(words) < 2:
            return
        
        # 检查与其他节点的相似度
        all_nodes = self.graph.get_all_nodes(limit=200)
        for other in all_nodes:
            if other.id == node.id:
                continue
            
            other_words = set(re.findall(r'[a-zA-Z_]{4,}', other.content.lower()))
            other_words.update(re.findall(r'[\u4e00-\u9fff]{2,}', other.content))
            
            if len(other_words) < 2:
                continue
            
            # Jaccard 相似度
            intersection = words & other_words
            union = words | other_words
            if not union:
                continue
            
            similarity = len(intersection) / len(union)
            
            if similarity >= 0.3:
                # 建立 related 边
                edge = MemoryEdge(
                    source_id=node.id,
                    target_id=other.id,
                    relation_type="related",
                    strength=min(1.0, similarity),
                    evidence=f"共享 {len(intersection)} 个关键词",
                    created_at=datetime.now(),
                )
                self.graph.add_edge(edge)
                logger.debug(f"Light: 建立 related 边 {node.id} -> {other.id} (sim={similarity:.2f})")
    
    # ========== Deep 阶段：近实时处理 ==========
    
    async def _deep_loop(self):
        """Deep 阶段后台循环"""
        while self._running:
            try:
                await asyncio.sleep(self.deep_interval_minutes * 60)
                if not self._running:
                    break
                await self._run_deep_phase()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Deep 阶段错误: {e}")
                await asyncio.sleep(60)
    
    async def on_session_end(self, session_id: str):
        """Session 结束时触发 Deep 阶段"""
        if self.deep_enabled:
            await self._run_deep_phase(session_id)
    
    async def _run_deep_phase(self, session_id: str = None):
        """Deep 阶段 —— 批量巩固短期记忆
        
        功能：
            1. 从 short-term 缓存中按动态权重评分
            2. 超过阈值的晋升到 long-term
            3. 检查并解决矛盾
            4. 执行记忆预算压缩
        """
        logger.info(f"Deep 阶段开始{' [' + session_id + ']' if session_id else ''}")
        
        promoted = 0
        resolved = 0
        
        # 处理短期记忆缓存
        for node in list(self._short_term):
            # 动态权重评分
            score = self._calculate_dynamic_score(node)
            
            if score >= 0.6:
                # 晋升到 long-term（提升置信度）
                self.graph.update_confidence(node.id, 0.05)
                promoted += 1
                logger.debug(f"Deep: 记忆晋升 {node.id} (score={score:.2f})")
            elif score < 0.3:
                # 未通过评估，从 short-term 移除
                self._short_term.remove(node)
                logger.debug(f"Deep: 记忆丢弃 {node.id} (score={score:.2f})")
        
        # 矛盾检测与解决
        contradictions = self.query_engine.detect_contradictions(min_confidence=0.4)
        for report in contradictions[:5]:  # 每次最多处理 5 个
            # 降低矛盾双方的置信度
            self.graph.record_contradiction(report.node_a.id)
            self.graph.record_contradiction(report.node_b.id)
            self.graph.update_confidence(report.node_a.id, -0.1)
            self.graph.update_confidence(report.node_b.id, -0.1)
            resolved += 1
            logger.info(f"Deep: 矛盾检测 {report.node_a.id} vs {report.node_b.id} (severity={report.severity:.2f})")
        
        # 记忆预算压缩
        evicted = self.budget.compact_if_needed()
        
        logger.info(
            f"Deep 阶段完成: 晋升 {promised}, 矛盾 {resolved}, 压缩 {evicted}"
        )
        
        # 广播
        if self.bus:
            await self.bus.publish("memory.plasticity.deep", json.dumps({
                "promoted": promoted,
                "contradictions_resolved": resolved,
                "evicted": evicted,
                "timestamp": datetime.now().isoformat(),
            }).encode())
    
    def _calculate_dynamic_score(self, node: MemoryNode) -> float:
        """计算动态权重分数
        
        综合维度：
            - 情绪强度（0-0.3）
            - 用户反馈（0-0.3）
            - 引用次数（0-0.2）
            - 关联度（0-0.2）
        """
        score = 0.0
        
        # 1. 基础置信度
        score += node.confidence * 0.2
        
        # 2. 访问频率（被引用的次数）
        access_bonus = min(0.2, node.access_count * 0.02)
        score += access_bonus
        
        # 3. 关联度（出边数量）
        edges = self.graph.get_edges(node.id, direction="outgoing")
        relation_bonus = min(0.2, len(edges) * 0.05)
        score += relation_bonus
        
        # 4. 验证次数
        verification_bonus = min(0.2, node.verification_count * 0.05)
        score += verification_bonus
        
        # 5. 矛盾惩罚
        contradiction_penalty = min(0.3, node.contradiction_count * 0.1)
        score -= contradiction_penalty
        
        return max(0.0, min(1.0, score))
    
    # ========== REM 阶段：定时全局反思 ==========
    
    async def _rem_loop(self):
        """REM 阶段后台循环"""
        while self._running:
            try:
                # 计算到下次 REM 的等待时间
                wait_seconds = self._calculate_rem_wait()
                await asyncio.sleep(wait_seconds)
                if not self._running:
                    break
                await self._run_rem_phase()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"REM 阶段错误: {e}")
                await asyncio.sleep(3600)
    
    def _calculate_rem_wait(self) -> float:
        """计算到下次 REM 的等待秒数"""
        import croniter
        now = datetime.now()
        cron = croniter.croniter(self.rem_schedule, now)
        next_run = cron.get_next(datetime)
        return (next_run - now).total_seconds()
    
    async def _run_rem_phase(self):
        """REM 阶段 —— 全局反思和主题提取
        
        功能：
            1. 主题提取：最近 7 天的记忆聚类
            2. 模式发现
            3. 生成 DREAMS.md
            4. 预测性预加载（为明天的对话做准备）
        """
        logger.info("REM 阶段开始（全局反思）")
        
        # 1. 获取最近 7 天的记忆
        recent_nodes = self.graph.get_recent_nodes(hours=24 * 7, limit=200)
        
        # 2. 按类型统计
        type_stats = {}
        for node in recent_nodes:
            t = node.memory_type
            type_stats[t] = type_stats.get(t, 0) + 1
        
        # 3. 主题聚类（简单实现：按关键词聚类）
        clusters = self._cluster_by_keywords(recent_nodes)
        
        # 4. 模式发现（如果配置了 LLM）
        patterns = []
        if self.llm and len(recent_nodes) > 20:
            patterns = await self._discover_patterns(recent_nodes)
        
        # 5. 生成梦境日记
        await self._write_dream_diary(clusters, patterns, type_stats)
        
        # 6. 遗忘处理
        forgetting_result = self.forgetting.run_forgetting_cycle()
        
        # 7. 记忆预算检查
        budget_summary = self.budget.get_budget_summary()
        
        logger.info(
            f"REM 阶段完成: 主题 {len(clusters)}, 模式 {len(patterns)}, "
            f"遗忘 {forgetting_result.archived_count} 归档 / {forgetting_result.deleted_count} 删除"
        )
        
        # 广播
        if self.bus:
            await self.bus.publish("memory.plasticity.rem", json.dumps({
                "clusters": len(clusters),
                "patterns": len(patterns),
                "forgetting": {
                    "archived": forgetting_result.archived_count,
                    "deleted": forgetting_result.deleted_count,
                },
                "budget": budget_summary,
                "timestamp": datetime.now().isoformat(),
            }).encode())
    
    def _cluster_by_keywords(self, nodes: List[MemoryNode]) -> Dict[str, List[MemoryNode]]:
        """按关键词简单聚类"""
        import re
        from collections import defaultdict
        
        clusters = defaultdict(list)
        
        for node in nodes:
            # 提取关键词
            keywords = set(re.findall(r'[a-zA-Z_]{4,}', node.content.lower()))
            keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', node.content))
            
            # 分配到最匹配的主题
            assigned = False
            for kw in keywords:
                if len(kw) >= 4 or len(kw.encode('utf-8')) >= 6:  # 过滤短词
                    clusters[kw].append(node)
                    assigned = True
                    break
            
            if not assigned:
                clusters["other"].append(node)
        
        # 只保留有多个节点的簇
        return {k: v for k, v in clusters.items() if len(v) >= 2}
    
    async def _discover_patterns(self, nodes: List[MemoryNode]) -> List[str]:
        """使用 LLM 发现模式"""
        # 选取代表性记忆
        samples = nodes[:30]
        sample_texts = []
        for i, node in enumerate(samples):
            sample_texts.append(f"{i+1}. [{node.memory_type}] {node.content[:100]}")
        
        prompt = f"""分析以下记忆，发现其中的模式和规律。输出 3-5 条简洁的洞察：

{chr(10).join(sample_texts)}

请输出中文，每条不超过 50 字。"""
        
        try:
            response = await self.llm.complete(prompt)
            patterns = [line.strip("- •") for line in response.split("\n") if line.strip() and len(line) > 10]
            return patterns[:5]
        except Exception as e:
            logger.warning(f"模式发现失败: {e}")
            return []
    
    async def _write_dream_diary(self, clusters: Dict, patterns: List[str], type_stats: Dict):
        """写入梦境日记（Markdown 格式）"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        lines = [
            f"## 🌙 {date_str} 梦境日记",
            "",
            f"*REM 阶段生成于 {datetime.now().strftime('%H:%M')}*",
            "",
            "### 📊 记忆统计",
            "",
        ]
        
        for mem_type, count in sorted(type_stats.items(), key=lambda x: -x[1]):
            lines.append(f"- {mem_type}: {count} 条")
        
        lines.extend(["", "### 🗂️ 主题聚类", ""])
        
        for theme, nodes in sorted(clusters.items(), key=lambda x: -len(x[1]))[:10]:
            lines.append(f"**{theme}** ({len(nodes)} 条)")
            for node in nodes[:3]:
                lines.append(f"  - {node.content[:80]}")
            lines.append("")
        
        if patterns:
            lines.extend(["### 💡 模式发现", ""])
            for pattern in patterns:
                lines.append(f"- {pattern}")
            lines.append("")
        
        content = "\n".join(lines)
        
        # 写入文件
        dreams_dir = Path("./tent_memory/dreams")
        dreams_dir.mkdir(parents=True, exist_ok=True)
        dreams_file = dreams_dir / "DREAMS.md"
        
        if dreams_file.exists():
            existing = dreams_file.read_text(encoding="utf-8")
            if f"## 🌙 {date_str}" in existing:
                # 替换当日条目
                import re
                pattern = rf'## 🌙 {re.escape(date_str)} .+?(?=## 🌙 |\Z)'
                existing = re.sub(pattern, content + "\n", existing, flags=re.DOTALL)
                dreams_file.write_text(existing, encoding="utf-8")
            else:
                dreams_file.write_text(content + "\n" + existing, encoding="utf-8")
        else:
            header = [
                "# 🌙 梦境日记",
                "",
                "> 本文件由 Tent OS 神经可塑性引擎自动生成。",
                "> 记录 AI 在 REM 阶段对记忆的整理、关联和反思。",
                "",
                "---",
                "",
            ]
            dreams_file.write_text("\n".join(header) + "\n" + content, encoding="utf-8")
    
    # ========== Forgetting 阶段：持续衰减 ==========
    
    async def _forgetting_loop(self):
        """遗忘后台循环"""
        while self._running:
            try:
                # 每 6 小时运行一次遗忘检查
                await asyncio.sleep(6 * 3600)
                if not self._running:
                    break
                self.forgetting.run_forgetting_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"遗忘阶段错误: {e}")
                await asyncio.sleep(3600)
    
    # ========== 用户反馈处理 ==========
    
    async def on_user_feedback(self, node_id: str, feedback_type: str):
        """处理用户反馈（调整权重）
        
        feedback_type:
            - "confirm": 用户确认记忆正确 → 置信度 +0.1
            - "correct": 用户纠正记忆 → 置信度 -0.1，创建新节点
            - "like": 用户点赞 → 置信度 +0.05
            - "dislike": 用户点踩 → 置信度 -0.05
        """
        delta_map = {
            "confirm": 0.1,
            "correct": -0.1,
            "like": 0.05,
            "dislike": -0.05,
        }
        
        delta = delta_map.get(feedback_type, 0)
        if delta == 0:
            return
        
        new_confidence = self.graph.update_confidence(node_id, delta)
        logger.info(f"用户反馈 [{feedback_type}] → {node_id} confidence={new_confidence:.2f}")
        
        if feedback_type == "correct" and self.llm:
            # 用户纠正 → 提取正确信息创建新节点
            # TODO: 需要传入正确内容
            pass
    
    # ========== 状态查询 ==========
    
    def get_status(self) -> Dict:
        """获取引擎状态"""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "short_term_count": len(self._short_term),
            "graph_stats": self.graph.get_statistics(),
            "budget": self.budget.get_budget_summary(),
            "forgetting": self.forgetting.get_forgetting_stats(),
        }
