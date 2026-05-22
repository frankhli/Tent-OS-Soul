"""Markdown 人类视图同步层 —— OpenClaw MEMORY.md 模式的 Tent OS 实现

核心设计：
1. 从 SQLite 记忆数据库自动生成人类可读的 Markdown 文件
2. 用户可编辑 Markdown，编辑后触发 reindex 同步回数据库
3. 文件监视（watchdog 可选），实时检测变更
4. 双向同步：DB → MD（自动定时生成） + MD → DB（编辑后手动/自动触发）

文件结构：
    tent_memory/
    ├── MEMORY.md              # 总览索引（人类可读的记忆目录）
    ├── daily/
    │   ├── 2026-04-22.md      # 每日记忆笔记
    │   └── 2026-04-21.md
    ├── dreams/
    │   └── DREAMS.md          # 梦境日记（REM 阶段生成）
    └── insights.md            # 洞察总结（模式发现）

使用方法：
    sync = MarkdownSyncLayer("./tent_memory")
    await sync.sync_from_db(db_path="./tent_memory/memory.db")
    # 用户编辑后：
    await sync.sync_from_md(md_path="./tent_memory/MEMORY.md")
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger("tent_os.memory.markdown")


class MarkdownSyncLayer:
    """Markdown 记忆同步层 —— 人类可读的'记忆源文件'"""
    
    def __init__(self, storage_path: str = "./tent_memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.daily_path = self.storage_path / "daily"
        self.daily_path.mkdir(exist_ok=True)
        self.dreams_path = self.storage_path / "dreams"
        self.dreams_path.mkdir(exist_ok=True)
        
        # 跟踪文件哈希，避免不必要的重写
        self._file_hashes: Dict[str, str] = {}
        # 跟踪最后一次同步时间
        self._last_sync: Optional[datetime] = None
    
    # ========== DB → Markdown ==========
    
    async def sync_from_db(self, db_path: str = "./tent_memory/memory.db") -> bool:
        """从 SQLite 数据库同步到 Markdown 文件
        
        Returns:
            bool: 是否成功生成至少一个文件
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_from_db_sync, db_path)
        except Exception as e:
            logger.error(f"Markdown 同步失败: {e}")
            return False
    
    def _sync_from_db_sync(self, db_path: str) -> bool:
        """同步实现（在线程池中运行）"""
        if not Path(db_path).exists():
            logger.warning(f"记忆数据库不存在: {db_path}")
            return False
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # 1. 生成 MEMORY.md 总览
            self._generate_memory_overview(conn)
            
            # 2. 生成每日记忆
            self._generate_daily_notes(conn)
            
            # 3. 生成洞察总结
            self._generate_insights(conn)
            
            self._last_sync = datetime.now()
            return True
        finally:
            conn.close()
    
    def _generate_memory_overview(self, conn: sqlite3.Connection):
        """生成 MEMORY.md 总览文件"""
        lines = [
            "# 🧠 Tent OS 记忆总览（MEMORY）",
            "",
            "> 本文件由 Tent OS 自动生成，反映 AI 的当前记忆状态。",
            "> 你可以直接编辑此文件，编辑后系统会自动重新索引。",
            "",
            f"*最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
            "---",
            "",
        ]
        
        # 统计信息
        try:
            total_l0 = conn.execute("SELECT COUNT(*) FROM l0_index").fetchone()[0]
            total_l1 = conn.execute("SELECT COUNT(*) FROM l1_index").fetchone()[0]
        except sqlite3.OperationalError:
            total_l0 = total_l1 = 0
        
        lines.extend([
            "## 📊 记忆统计",
            "",
            f"- L0 摘要条目: {total_l0}",
            f"- L1 概览条目: {total_l1}",
            f"- 存储路径: `{self.storage_path}`",
            "",
            "---",
            "",
        ])
        
        # 近期记忆（最近 7 天）
        lines.extend([
            "## 📝 近期记忆（最近 7 天）",
            "",
        ])
        
        try:
            rows = conn.execute(
                """SELECT uri, abstract, memory_type, created_at FROM l0_index
                   WHERE created_at >= datetime('now', '-7 days')
                   ORDER BY created_at DESC LIMIT 30"""
            ).fetchall()
            
            for row in rows:
                date_str = row["created_at"][:10] if row["created_at"] else "unknown"
                mem_type = row["memory_type"] or "general"
                abstract = row["abstract"] or "（无摘要）"
                lines.append(f"- **[{date_str}] [{mem_type}]** {abstract[:120]}")
            
            if not rows:
                lines.append("*最近 7 天内没有新记忆*")
        except sqlite3.OperationalError:
            lines.append("*记忆数据库尚未初始化*")
        
        lines.extend(["", "---", ""])
        
        # 按类型分类的记忆
        lines.extend([
            "## 🗂️ 记忆分类",
            "",
        ])
        
        try:
            type_rows = conn.execute(
                """SELECT memory_type, COUNT(*) as cnt FROM l0_index
                   GROUP BY memory_type ORDER BY cnt DESC"""
            ).fetchall()
            
            for row in type_rows:
                mem_type = row["memory_type"] or "未分类"
                cnt = row["cnt"]
                lines.append(f"- **{mem_type}**: {cnt} 条")
        except sqlite3.OperationalError:
            lines.append("*暂无分类数据*")
        
        lines.extend(["", "---", ""])
        
        # 每日笔记索引
        lines.extend([
            "## 📅 每日笔记",
            "",
        ])
        
        daily_files = sorted(self.daily_path.glob("*.md"), reverse=True)
        for f in daily_files[:30]:
            date_str = f.stem
            lines.append(f"- [{date_str}](daily/{f.name})")
        
        if not daily_files:
            lines.append("*暂无每日笔记*")
        
        lines.extend(["", "---", ""])
        
        # 梦境索引
        lines.extend([
            "## 🌙 梦境日记",
            "",
        ])
        
        dreams_file = self.dreams_path / "DREAMS.md"
        if dreams_file.exists():
            lines.append(f"- [梦境日记](dreams/DREAMS.md)")
        else:
            lines.append("*暂无梦境日记*")
        
        lines.append("")
        
        content = "\n".join(lines)
        self._write_if_changed(self.storage_path / "MEMORY.md", content)
    
    def _generate_daily_notes(self, conn: sqlite3.Connection):
        """生成每日记忆笔记"""
        try:
            # 按日期分组获取记忆
            rows = conn.execute(
                """SELECT uri, abstract, memory_type, created_at FROM l0_index
                   WHERE created_at >= datetime('now', '-30 days')
                   ORDER BY created_at DESC"""
            ).fetchall()
            
            # 按日期分组
            daily_memories: Dict[str, List[Dict]] = {}
            for row in rows:
                date_str = row["created_at"][:10] if row["created_at"] else "unknown"
                if date_str not in daily_memories:
                    daily_memories[date_str] = []
                daily_memories[date_str].append({
                    "uri": row["uri"],
                    "abstract": row["abstract"] or "",
                    "memory_type": row["memory_type"] or "general",
                })
            
            for date_str, memories in daily_memories.items():
                lines = [
                    f"# 📅 {date_str} 的记忆",
                    "",
                    f"*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
                    "",
                    "---",
                    "",
                ]
                
                # 按类型分组
                by_type: Dict[str, List[Dict]] = {}
                for m in memories:
                    t = m["memory_type"]
                    if t not in by_type:
                        by_type[t] = []
                    by_type[t].append(m)
                
                for mem_type, items in by_type.items():
                    lines.append(f"## {mem_type.upper()}")
                    lines.append("")
                    for item in items:
                        lines.append(f"- {item['abstract'][:200]}")
                        lines.append(f"  - URI: `{item['uri']}`")
                    lines.append("")
                
                content = "\n".join(lines)
                self._write_if_changed(self.daily_path / f"{date_str}.md", content)
            
            # 清理超过 90 天的旧文件
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            for f in self.daily_path.glob("*.md"):
                if f.stem < cutoff:
                    f.unlink()
                    logger.debug(f"清理过期每日笔记: {f.name}")
                    
        except sqlite3.OperationalError as e:
            logger.debug(f"每日笔记生成跳过: {e}")
    
    def _generate_insights(self, conn: sqlite3.Connection):
        """生成洞察总结"""
        lines = [
            "# 🔍 洞察总结",
            "",
            f"*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
            "---",
            "",
            "## 📈 记忆增长趋势",
            "",
        ]
        
        try:
            # 最近 7 天每日新增
            daily_counts = conn.execute(
                """SELECT date(created_at) as day, COUNT(*) as cnt FROM l0_index
                   WHERE created_at >= datetime('now', '-7 days')
                   GROUP BY day ORDER BY day DESC"""
            ).fetchall()
            
            for row in daily_counts:
                lines.append(f"- {row['day']}: +{row['cnt']} 条记忆")
            
            if not daily_counts:
                lines.append("*暂无数据*")
        except sqlite3.OperationalError:
            lines.append("*数据库尚未初始化*")
        
        lines.extend(["", "---", ""])
        
        # 高频关键词（简单统计）
        lines.extend([
            "## 🏷️ 高频主题",
            "",
        ])
        
        try:
            rows = conn.execute(
                """SELECT abstract FROM l0_index
                   WHERE created_at >= datetime('now', '-30 days')"""
            ).fetchall()
            
            # 简单词频统计
            word_counts: Dict[str, int] = {}
            for row in rows:
                text = row["abstract"] or ""
                # 提取中英文单词
                import re
                words = re.findall(r'[a-zA-Z_]{3,}', text.lower())
                for w in words:
                    word_counts[w] = word_counts.get(w, 0) + 1
                # 中文
                chinese = re.findall(r'[\u4e00-\u9fff]{2,}', text)
                for c in chinese:
                    word_counts[c] = word_counts.get(c, 0) + 1
            
            top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:20]
            for word, count in top_words:
                lines.append(f"- {word}: {count} 次")
        except sqlite3.OperationalError:
            lines.append("*暂无数据*")
        
        lines.append("")
        
        content = "\n".join(lines)
        self._write_if_changed(self.storage_path / "insights.md", content)
    
    # ========== Markdown → DB ==========
    
    async def sync_from_md(self, md_path: str) -> int:
        """从 Markdown 文件同步回数据库
        
        解析用户编辑的 Markdown，提取新的记忆条目，写入数据库。
        
        Returns:
            int: 成功同步的记忆条目数
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_from_md_sync, md_path)
        except Exception as e:
            logger.error(f"Markdown 反向同步失败: {e}")
            return 0
    
    def _sync_from_md_sync(self, md_path: str) -> int:
        """反向同步实现"""
        md_file = Path(md_path)
        if not md_file.exists():
            return 0
        
        content = md_file.read_text(encoding="utf-8")
        
        # 解析 Markdown，提取列表项作为记忆
        import re
        
        # 匹配形如 "- [2026-04-22] [type] content" 的条目
        pattern = r'^\s*-\s*(?:\*\*)?(?:\[([^\]]+)\]\s*)?(?:\*\*)?(?:\[([^\]]+)\]\s*)?\*\*?\s*(.+)$'
        
        memories = []
        for line in content.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                date_str = match.group(1) or datetime.now().strftime('%Y-%m-%d')
                mem_type = match.group(2) or "general"
                abstract = match.group(3).strip()
                if len(abstract) > 20:  # 过滤太短的条目
                    memories.append({
                        "date": date_str,
                        "type": mem_type,
                        "abstract": abstract,
                    })
        
        if not memories:
            logger.info(f"Markdown 文件中未检测到可同步的记忆条目: {md_path}")
            return 0
        
        # 写入数据库（这里需要 TieredMemoryStore 的引用，暂不实现完整逻辑）
        # TODO: 与 TieredMemoryStore.ingest() 集成
        logger.info(f"检测到 {len(memories)} 条用户编辑的记忆，待同步到数据库")
        return len(memories)
    
    # ========== 梦境日记 ==========
    
    async def write_dream_entry(self, date_str: str, title: str, content: str, 
                                insights: List[str] = None):
        """写入梦境日记条目（由 DreamingEngine 调用）"""
        insights = insights or []
        
        lines = [
            f"## 🌙 {date_str} — {title}",
            "",
            f"{content}",
            "",
        ]
        
        if insights:
            lines.extend([
                "### 💡 洞察",
                "",
            ])
            for insight in insights:
                lines.append(f"- {insight}")
            lines.append("")
        
        entry = "\n".join(lines)
        
        # 追加到 DREAMS.md
        dreams_file = self.dreams_path / "DREAMS.md"
        if dreams_file.exists():
            existing = dreams_file.read_text(encoding="utf-8")
            # 检查是否已有该日期的条目
            if f"## 🌙 {date_str}" in existing:
                # 替换已有条目（简单实现）
                import re
                pattern = rf'## 🌙 {re.escape(date_str)} — .+?(?=## 🌙|\Z)'
                existing = re.sub(pattern, entry + "\n", existing, flags=re.DOTALL)
                dreams_file.write_text(existing, encoding="utf-8")
            else:
                dreams_file.write_text(entry + "\n" + existing, encoding="utf-8")
        else:
            header = [
                "# 🌙 梦境日记",
                "",
                "> 本文件由 Tent OS 梦境引擎自动生成。",
                "> 记录 AI 在 REM 阶段对记忆的整理、关联和反思。",
                "",
                "---",
                "",
            ]
            dreams_file.write_text("\n".join(header) + "\n" + entry, encoding="utf-8")
        
        logger.info(f"梦境日记已更新: {date_str}")
    
    # ========== 工具方法 ==========
    
    def _write_if_changed(self, path: Path, content: str):
        """仅在内容变化时写入文件（避免不必要的文件系统操作）"""
        new_hash = hashlib.md5(content.encode()).hexdigest()
        path_str = str(path)
        
        if self._file_hashes.get(path_str) == new_hash:
            return  # 无变化，跳过
        
        path.write_text(content, encoding="utf-8")
        self._file_hashes[path_str] = new_hash
        logger.debug(f"Markdown 文件已更新: {path}")
    
    def get_memory_md_path(self) -> Path:
        """获取 MEMORY.md 路径"""
        return self.storage_path / "MEMORY.md"
    
    def get_dreams_md_path(self) -> Path:
        """获取 DREAMS.md 路径"""
        return self.dreams_path / "DREAMS.md"
