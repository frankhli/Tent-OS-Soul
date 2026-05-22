"""Dreaming 梦境模式 —— OpenClaw 风格的记忆自整理

当系统空闲时，AI 进入"梦境"状态：
1. 回顾近期记忆，压缩冗余信息
2. 发现跨记忆的模式和关联
3. 检测记忆中的矛盾
4. 提取新的程序记忆规则
5. 将整个过程记录到"梦境日记"

用户可以通过 Control UI 查看梦境日记、开关梦境模式。
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


class DreamEntry:
    """梦境中的一个条目（一个整理动作）"""
    def __init__(self, phase: str, description: str, detail: str = ""):
        self.phase = phase          # e.g. "compress", "associate", "contradict", "insight"
        self.description = description
        self.detail = detail
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase,
            "description": self.description,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class DreamDiary:
    """梦境日记 —— 存储每次梦境的完整记录"""

    def __init__(self, db_path: str = "./tent_scheduler.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化梦境日记表"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dream_diary (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT DEFAULT 'dreaming',
                depth INTEGER DEFAULT 3,
                entries TEXT,        -- JSON array of DreamEntry
                insights TEXT,       -- JSON array of extracted insights
                summary TEXT,        -- human-readable summary
                memories_processed INTEGER DEFAULT 0,
                rules_extracted INTEGER DEFAULT 0,
                contradictions_found INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def start_dream(self, depth: int = 3) -> str:
        """开始一次新的梦境，返回梦境 ID"""
        dream_id = f"dream_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO dream_diary (id, started_at, status, depth) VALUES (?, ?, ?, ?)",
            (dream_id, datetime.now().isoformat(), "dreaming", depth)
        )
        conn.commit()
        conn.close()
        return dream_id

    def add_entry(self, dream_id: str, entry: DreamEntry):
        """向梦境中添加一个条目"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT entries FROM dream_diary WHERE id = ?", (dream_id,))
        row = cursor.fetchone()
        entries = json.loads(row[0]) if row and row[0] else []
        entries.append(entry.to_dict())
        conn.execute(
            "UPDATE dream_diary SET entries = ? WHERE id = ?",
            (json.dumps(entries, ensure_ascii=False), dream_id)
        )
        conn.commit()
        conn.close()

    def finish_dream(self, dream_id: str, summary: str, insights: List[str],
                     memories_processed: int = 0, rules_extracted: int = 0,
                     contradictions_found: int = 0):
        """完成一次梦境"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE dream_diary SET ended_at = ?, status = ?, summary = ?, insights = ?, "
            "memories_processed = ?, rules_extracted = ?, contradictions_found = ? WHERE id = ?",
            (datetime.now().isoformat(), "completed", summary,
             json.dumps(insights, ensure_ascii=False),
             memories_processed, rules_extracted, contradictions_found, dream_id)
        )
        conn.commit()
        conn.close()

    def get_recent(self, limit: int = 20) -> List[Dict]:
        """获取最近的梦境记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM dream_diary ORDER BY started_at DESC LIMIT ?",
            (limit,)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for r in rows:
            r["entries"] = json.loads(r["entries"]) if r.get("entries") else []
            r["insights"] = json.loads(r["insights"]) if r.get("insights") else []
        return rows

    def get_stats(self) -> Dict:
        """获取梦境统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(memories_processed) as total_memories, "
            "SUM(rules_extracted) as total_rules, "
            "SUM(contradictions_found) as total_contradictions "
            "FROM dream_diary WHERE status = 'completed'"
        )
        row = cursor.fetchone()
        conn.close()
        return {
            "total_dreams": row[0] or 0,
            "total_memories_processed": row[1] or 0,
            "total_rules_extracted": row[2] or 0,
            "total_contradictions_found": row[3] or 0,
        }


class DreamingEngine:
    """梦境引擎 —— 在系统空闲时自动整理记忆"""

    def __init__(self, bus, config: Dict = None, db_path: str = "./tent_scheduler.db",
                 llm=None, memory_store_path: str = "./tent_memory/memory.db"):
        self.bus = bus
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.schedule = self.config.get("schedule", "0 2 * * *")  # 默认每天凌晨 2 点
        self.depth = self.config.get("depth", 3)  # 1-5
        self.diary = DreamDiary(db_path)
        self.llm = llm
        self.memory_store_path = memory_store_path
        self._is_dreaming = False
        self._current_dream_id: Optional[str] = None
        self._task = None

    @property
    def is_dreaming(self) -> bool:
        return self._is_dreaming

    @property
    def current_dream_id(self) -> Optional[str]:
        return self._current_dream_id

    def get_status(self) -> Dict:
        """获取梦境引擎状态"""
        return {
            "enabled": self.enabled,
            "is_dreaming": self._is_dreaming,
            "current_dream_id": self._current_dream_id,
            "schedule": self.schedule,
            "depth": self.depth,
            "stats": self.diary.get_stats(),
        }

    async def start(self):
        """启动梦境引擎（后台循环）"""
        if not self.enabled:
            logger.info("Dreaming 已禁用，不启动")
            return

        logger.info(f"Dreaming 引擎启动，计划: {self.schedule}, 深度: {self.depth}")

        # 简化的调度：用 asyncio.sleep 轮询，实际生产环境可用 croniter
        while True:
            try:
                await self._wait_for_next_slot()
                if self.enabled:
                    await self._dream()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dreaming 循环出错: {e}")
                await asyncio.sleep(3600)

    async def _wait_for_next_slot(self):
        """等待下一个梦境时间槽"""
        # 简化实现：固定间隔（实际可用 croniter 解析 cron 表达式）
        # 默认每天凌晨 2 点 = 86400 秒周期，计算到下一个 2:00 的时间
        now = datetime.now()
        target = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if target <= now:
            target = target.replace(day=target.day + 1)
        wait_seconds = (target - now).total_seconds()
        logger.debug(f"Dreaming 等待 {wait_seconds/3600:.1f} 小时")
        await asyncio.sleep(wait_seconds)

    async def _dream(self):
        """执行一次梦境"""
        self._is_dreaming = True
        dream_id = self.diary.start_dream(self.depth)
        self._current_dream_id = dream_id

        logger.info(f"🌙 进入梦境... [{dream_id}] 深度={self.depth}")

        # 广播 dreaming 开始
        await self._broadcast_status("started", dream_id)

        try:
            entries = []
            insights = []
            memories_processed = 0
            rules_extracted = 0
            contradictions_found = 0

            # Phase 1: 记忆压缩
            await self._phase_compress(dream_id, entries)
            memories_processed += await self._count_memories()

            # Phase 2: 关联构建
            await self._phase_associate(dream_id, entries)

            # Phase 3: 矛盾检测
            contradictions = await self._phase_contradict(dream_id, entries)
            contradictions_found += len(contradictions)

            # Phase 4: 模式发现 / 规则提取
            rules = await self._phase_insight(dream_id, entries)
            rules_extracted += len(rules)
            insights.extend(rules)

            # 生成摘要
            summary = self._generate_summary(
                memories_processed, len(insights), contradictions_found
            )

            # 完成梦境
            self.diary.finish_dream(
                dream_id, summary, insights,
                memories_processed, rules_extracted, contradictions_found
            )

            logger.info(f"✨ 梦境完成 [{dream_id}]: {summary}")
            await self._broadcast_status("completed", dream_id, summary)

        except Exception as e:
            logger.error(f"梦境出错 [{dream_id}]: {e}")
            await self._broadcast_status("failed", dream_id, str(e))
        finally:
            self._is_dreaming = False
            self._current_dream_id = None

    async def _phase_compress(self, dream_id: str, entries: List):
        """Phase 1: 记忆压缩 —— 合并冗余记忆"""
        logger.debug("梦境 Phase 1: 记忆压缩")
        
        # 获取最近 7 天的 L0 记忆
        recent_memories = self._get_recent_memories(days=7, limit=50)
        detail = f"发现 {len(recent_memories)} 条近期记忆"
        
        # 如果有大量记忆，用 LLM 生成压缩摘要
        compressed_count = 0
        if len(recent_memories) > 20 and self.llm:
            try:
                summary = await self._llm_summarize_memories(recent_memories)
                # 将摘要写入 L1 索引（通过直接操作 SQLite）
                self._save_compressed_summary(summary, recent_memories)
                detail = f"压缩了 {len(recent_memories)} 条记忆为 1 条摘要"
                compressed_count = len(recent_memories)
            except Exception as e:
                logger.warning(f"记忆压缩失败: {e}")
        
        entry = DreamEntry(
            phase="compress",
            description="扫描并压缩冗余记忆",
            detail=detail
        )
        self.diary.add_entry(dream_id, entry)
        entries.append(entry)

    async def _phase_associate(self, dream_id: str, entries: List):
        """Phase 2: 关联构建 —— 建立记忆间连接"""
        logger.debug("梦境 Phase 2: 关联构建")
        
        associations = []
        try:
            # 获取最近记忆，计算相似度关联
            recent = self._get_recent_memories(days=7, limit=30)
            if len(recent) >= 2:
                # 简单的两两相似度：基于共享关键词
                for i in range(len(recent)):
                    for j in range(i+1, min(i+5, len(recent))):  # 只比较相邻的，减少计算
                        sim = self._text_similarity(recent[i]["abstract"], recent[j]["abstract"])
                        if sim > 0.5:
                            associations.append({
                                "uri_a": recent[i]["uri"],
                                "uri_b": recent[j]["uri"],
                                "similarity": round(sim, 2)
                            })
        except Exception as e:
            logger.warning(f"关联构建失败: {e}")
        
        detail = f"发现 {len(associations)} 对记忆关联"
        if associations:
            detail += f"（最高相似度 {max(a['similarity'] for a in associations):.0%}）"
        
        entry = DreamEntry(
            phase="associate",
            description="发现记忆间的隐藏关联",
            detail=detail
        )
        self.diary.add_entry(dream_id, entry)
        entries.append(entry)

    async def _phase_contradict(self, dream_id: str, entries: List) -> List[str]:
        """Phase 3: 矛盾检测 —— 发现记忆中的不一致"""
        logger.debug("梦境 Phase 3: 矛盾检测")
        contradictions = []
        
        try:
            # 获取语义相似但内容可能矛盾的记忆对
            recent = self._get_recent_memories(days=7, limit=20)
            if len(recent) >= 2 and self.llm:
                # 找相似度最高但文本差异明显的对
                candidates = []
                for i in range(len(recent)):
                    for j in range(i+1, len(recent)):
                        sim = self._text_similarity(recent[i]["abstract"], recent[j]["abstract"])
                        if 0.3 < sim < 0.7:  # 有一定关联但不太相同
                            candidates.append((recent[i], recent[j], sim))
                
                # 取前 3 对，用 LLM 检测矛盾
                candidates.sort(key=lambda x: abs(x[2] - 0.5))
                for mem_a, mem_b, sim in candidates[:3]:
                    is_contra = await self._llm_detect_contradiction(
                        mem_a["abstract"], mem_b["abstract"]
                    )
                    if is_contra:
                        contradictions.append(f"[{mem_a['uri']}] vs [{mem_b['uri']}]: {mem_a['abstract'][:40]}... vs {mem_b['abstract'][:40]}...")
        except Exception as e:
            logger.warning(f"矛盾检测失败: {e}")
        
        detail = f"检测到 {len(contradictions)} 处矛盾" if contradictions else "未发现明显矛盾"
        entry = DreamEntry(
            phase="contradict",
            description="检测记忆中的矛盾",
            detail=detail
        )
        self.diary.add_entry(dream_id, entry)
        entries.append(entry)
        return contradictions

    async def _phase_insight(self, dream_id: str, entries: List) -> List[str]:
        """Phase 4: 模式发现 —— 提取新规则"""
        logger.debug("梦境 Phase 4: 模式发现")
        insights = []
        
        try:
            # 获取最近对话记忆，用 LLM 提炼规则和主题
            recent = self._get_recent_memories(days=7, limit=30)
            if len(recent) >= 5 and self.llm:
                themes = await self._llm_extract_themes(recent)
                if themes:
                    insights.append(f"本周主题: {themes}")
                
                # 尝试提取程序记忆规则
                rules = await self._llm_extract_rules(recent)
                for rule in rules:
                    insights.append(f"规则: {rule}")
            else:
                # 降级：从任务历史统计
                insights = await self._extract_patterns_from_history()
        except Exception as e:
            logger.warning(f"模式提取失败: {e}")
        
        detail = f"提取了 {len(insights)} 个洞察"
        entry = DreamEntry(
            phase="insight",
            description="从记忆中提取行为模式",
            detail=detail
        )
        self.diary.add_entry(dream_id, entry)
        entries.append(entry)
        return insights

    async def _extract_patterns_from_history(self) -> List[str]:
        """从历史任务中提取模式（简化版）"""
        insights = []
        try:
            conn = sqlite3.connect(self.diary.db_path)
            cursor = conn.execute(
                "SELECT action, status, COUNT(*) as c FROM tasks "
                "WHERE created_at >= datetime('now', '-7 days') "
                "GROUP BY action, status ORDER BY c DESC LIMIT 20"
            )
            patterns = []
            for row in cursor.fetchall():
                action, status, count = row
                if status == "completed" and count >= 3:
                    patterns.append(f"{action} 成功率 {(count/10)*100:.0f}%")
            conn.close()

            if patterns:
                insights.append(f"近期高频成功模式: {', '.join(patterns[:3])}")
        except Exception:
            pass
        return insights
    
    # === LLM 辅助方法 ===
    
    async def _llm_summarize_memories(self, memories: List[Dict]) -> str:
        """用 LLM 压缩多条记忆为摘要"""
        texts = [f"- [{m['uri']}] {m['abstract']}" for m in memories[:20]]
        prompt = f"""以下是一周内的记忆片段，请生成一段 200 字以内的摘要，保留关键信息和主题：

{chr(10).join(texts)}

摘要："""
        return await self._llm_complete(prompt)
    
    async def _llm_detect_contradiction(self, text_a: str, text_b: str) -> bool:
        """用 LLM 检测两段记忆是否矛盾"""
        prompt = f"""判断以下两段记忆是否相互矛盾：

记忆 A: {text_a}
记忆 B: {text_b}

如果矛盾，回复"矛盾"。如果不矛盾或只是角度不同，回复"一致"。"""
        result = await self._llm_complete(prompt)
        return "矛盾" in result
    
    async def _llm_extract_themes(self, memories: List[Dict]) -> str:
        """用 LLM 提取主题"""
        texts = [m["abstract"] for m in memories[:15]]
        prompt = f"""以下是一周内的记忆摘要，请提炼 1-3 个核心主题（用逗号分隔）：

{chr(10).join(texts)}

主题："""
        return await self._llm_complete(prompt)
    
    async def _llm_extract_rules(self, memories: List[Dict]) -> List[str]:
        """用 LLM 从记忆中提取行为规则"""
        texts = [m["abstract"] for m in memories[:15]]
        prompt = f"""以下是一周内的记忆，请从中提取 1-2 条可复用的行为规则（每条 30 字以内）。如果没有，回复"无"。

{chr(10).join(texts)}

规则："""
        result = await self._llm_complete(prompt)
        if "无" in result:
            return []
        return [line.strip("- •").strip() for line in result.split("\n") if line.strip() and "规则" not in line.lower()]
    
    async def _llm_complete(self, prompt: str) -> str:
        """调用 LLM 完成 prompt"""
        if not self.llm:
            return ""
        try:
            if hasattr(self.llm, "complete"):
                return await self.llm.complete(prompt)
            elif hasattr(self.llm, "chat"):
                return await self.llm.chat([{"role": "user", "content": prompt}])
            else:
                return ""
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return ""
    
    # === 记忆存储辅助方法 ===
    
    def _get_recent_memories(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """从记忆存储获取近期记忆"""
        try:
            conn = sqlite3.connect(self.memory_store_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT uri, abstract, memory_type, created_at FROM l0_index "
                "WHERE created_at >= datetime('now', '-{} days') "
                "ORDER BY created_at DESC LIMIT ?".format(days),
                (limit,)
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.debug(f"读取记忆失败: {e}")
            return []
    
    def _save_compressed_summary(self, summary: str, source_memories: List[Dict]):
        """将压缩摘要保存到记忆存储"""
        try:
            conn = sqlite3.connect(self.memory_store_path)
            source_uris = ",".join(m["uri"] for m in source_memories[:5])
            conn.execute(
                "INSERT OR REPLACE INTO l1_index (uri, overview, overview_tokens, file_path) "
                "VALUES (?, ?, ?, ?)",
                (f"dream/compress/{datetime.now().strftime('%Y%m%d')}",
                 summary, len(summary), source_uris)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"保存压缩摘要失败: {e}")
    
    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """计算两段文本的简单相似度（Jaccard）"""
        if not a or not b:
            return 0.0
        import re
        set_a = set(re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', a.lower()))
        set_b = set(re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', b.lower()))
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    async def _count_memories(self) -> int:
        """统计当前记忆数量"""
        try:
            mem_path = Path(self.memory_store_path)
            if mem_path.exists():
                conn = sqlite3.connect(str(mem_path))
                cursor = conn.execute("SELECT COUNT(*) FROM l0_index")
                count = cursor.fetchone()[0]
                conn.close()
                return count
        except Exception:
            pass
        return 0

    def _generate_summary(self, memories: int, insights: int, contradictions: int) -> str:
        """生成梦境摘要"""
        parts = []
        if memories > 0:
            parts.append(f"整理了 {memories} 条记忆")
        if insights > 0:
            parts.append(f"发现了 {insights} 个新洞察")
        if contradictions > 0:
            parts.append(f"检测到 {contradictions} 处矛盾")
        if not parts:
            return "本次梦境平静，记忆库状态良好"
        return "；".join(parts)

    async def _broadcast_status(self, status: str, dream_id: str, detail: str = ""):
        """广播梦境状态到 NATS"""
        if self.bus:
            try:
                await self.bus.publish("dreaming.status", json.dumps({
                    "status": status,
                    "dream_id": dream_id,
                    "detail": detail,
                    "timestamp": datetime.now().isoformat(),
                }).encode())
            except Exception:
                pass

    def toggle(self, enabled: bool):
        """开关梦境模式"""
        self.enabled = enabled
        logger.info(f"Dreaming 已{'启用' if enabled else '禁用'}")

    async def trigger_now(self) -> str:
        """手动触发一次梦境（用于测试）"""
        if self._is_dreaming:
            raise RuntimeError("已在梦境中")
        asyncio.create_task(self._dream())
        return self._current_dream_id or "dreaming"
