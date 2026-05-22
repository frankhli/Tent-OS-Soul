import hashlib
import logging
import re
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import tiktoken

try:
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    sqlite_vec = None
    SQLITE_VEC_AVAILABLE = False

from tent_os.memory.vector_search import PurePythonVectorSearch
from tent_os.memory.index import MemoryIndex

logger = logging.getLogger("tent_os.memory")


class TieredMemoryStore:
    """三层记忆存储：L0摘要(~100 tokens) / L1概览(~500-1000 tokens) / L2完整内容
    
    关键设计（修复 OpenViking #1549）：
    1. L0 是唯一的向量搜索目标 —— 不直接搜 L1/L2
    2. L1 由 LLM 生成结构化摘要 —— 不是原始文本截断
    3. L2 存储完整内容 —— 绝不自动注入 Prompt，只通过 tool_call 读取
    """
    
    def __init__(self, storage_path: str = "./tent_memory", llm: Optional[Any] = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.storage_path / "index.db", check_same_thread=False)
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.llm = llm  # 用于生成 L1 摘要
        self._init_db()
        self._load_vec_extension()
        self._pure_search = PurePythonVectorSearch(self.db)
    
    def _init_db(self):
        # L0: 索引层 —— 抽象摘要 + 向量，用于语义搜索
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS l0_index (
                uri TEXT PRIMARY KEY,
                abstract TEXT,
                embedding BLOB,
                memory_type TEXT,
                user_id TEXT,
                valid_from TEXT DEFAULT (datetime('now')),
                valid_to TEXT,
                superseded_by TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                content_hash TEXT
            )
        """)
        # 迁移：为已有表添加新列（兼容旧数据库）
        for col, col_type in [("content_hash", "TEXT"), ("user_id", "TEXT"), ("persona", "TEXT")]:
            try:
                self.db.execute(f"ALTER TABLE l0_index ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        try:
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_l0_hash ON l0_index(content_hash)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_l0_user ON l0_index(user_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_l0_user_time ON l0_index(user_id, created_at)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_l0_persona ON l0_index(persona)")
        except Exception:
            pass
        # L1: 概览层 —— LLM 生成的结构化摘要，用于决策
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS l1_index (
                uri TEXT PRIMARY KEY,
                overview TEXT,  -- LLM 生成的结构化摘要
                overview_tokens INTEGER,
                file_path TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # L2: 完整内容存储在文件系统中，不在数据库中
        if not SQLITE_VEC_AVAILABLE:
            self._vec_enabled = False
        else:
            try:
                self.db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_index USING vec0(
                        embedding float[1536]
                    )
                """)
            except Exception:
                logger.warning("sqlite-vec vec0虚拟表创建失败，向量检索将不可用")
                self._vec_enabled = False
        self.db.commit()
    
    def _load_vec_extension(self):
        if not SQLITE_VEC_AVAILABLE:
            self._vec_enabled = False
            return
        try:
            self.db.enable_load_extension(True)
            sqlite_vec.load(self.db)
            self._vec_enabled = True
        except Exception:
            self._vec_enabled = False
    
    async def ingest(self, content: str, uri: str, memory_type: str = "conversation",
                     user_id: str = None, embedding_model: callable = None, persona: str = None) -> None:
        """摄入内容：自动切片 → L0摘要 → L1 LLM生成 → L2存储 → 向量索引
        
        增量摄入：基于 content_hash 去重，已存在的 chunk 跳过。
        """
        chunks = self._slice_content(content, chunk_size=400, overlap=80)
        skipped = 0
        inserted = 0
        
        for i, chunk in enumerate(chunks):
            chunk_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()
            
            # 检查是否已存在相同内容的 chunk
            existing = self.db.execute(
                "SELECT uri FROM l0_index WHERE content_hash = ? LIMIT 1",
                (chunk_hash,)
            ).fetchone()
            
            if existing:
                skipped += 1
                continue
            
            chunk_uri = f"{uri}#chunk{i}"
            
            # L0摘要：提取式摘要，零成本
            l0 = self._extract_abstract(chunk)
            
            # L1概览：LLM 生成结构化摘要（如果 LLM 可用）
            l1 = None
            l1_tokens = 0
            if self.llm:
                try:
                    l1 = await self._generate_l1_overview(chunk)
                    l1_tokens = len(self.encoder.encode(l1)) if l1 else 0
                except Exception as e:
                    logger.warning(f"L1 生成失败，URI={chunk_uri}: {e}")
                    l1 = None
            
            # L2存储到文件系统
            l2_path = self.storage_path / "full" / f"{chunk_uri.replace('/', '_')}.txt"
            l2_path.parent.mkdir(exist_ok=True)
            l2_path.write_text(chunk)
            
            # 向量索引（只索引 L0，不直接搜 L1/L2）
            embedding = None
            if embedding_model:
                try:
                    embedding = await embedding_model(chunk)
                except Exception as e:
                    logger.warning(f"Embedding 生成失败: {e}")
            
            self.db.execute(
                "INSERT OR REPLACE INTO l0_index (uri, abstract, embedding, memory_type, user_id, content_hash, persona) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chunk_uri, l0, self._serialize_vector(embedding), memory_type, user_id, chunk_hash, persona)
            )
            self.db.execute(
                "INSERT OR REPLACE INTO l1_index (uri, overview, overview_tokens, file_path) VALUES (?, ?, ?, ?)",
                (chunk_uri, l1, l1_tokens, str(l2_path))
            )
            if embedding and self._vec_enabled:
                self.db.execute(
                    "INSERT INTO vec_index (rowid, embedding) VALUES ((SELECT rowid FROM l0_index WHERE uri=?), ?)",
                    (chunk_uri, self._serialize_vector(embedding))
                )
            inserted += 1
        
        self.db.commit()
        
        # 自动更新 MemoryIndex（关键修复：新记忆必须加入索引才能被注入时检索到）
        if inserted > 0:
            self._update_memory_index(uri, memory_type, chunks, persona)
        if skipped > 0:
            logger.info(f"[MEM] 增量摄入: {uri}, 新增 {inserted} chunks, 跳过 {skipped} 重复")
        else:
            logger.debug(f"摄入完成: {uri}, {inserted} chunks")
    
    
    def _update_memory_index(self, uri: str, memory_type: str, chunks: List[str], persona: str = None):
        """将新摄入的记忆更新到 MemoryIndex（修复跨会话记忆丢失）"""
        try:
            index = MemoryIndex(str(self.storage_path))
            # 根据 memory_type 决定温度
            from tent_os.memory.index import Temperature
            if memory_type in ("profile", "preference", "task"):
                temperature = Temperature.HOT
            elif memory_type in ("decision", "learning", "entity"):
                temperature = Temperature.WARM
            else:
                temperature = Temperature.WARM
            
            # 提取关键词用于检索
            import re
            keywords = set(re.findall(r'[a-zA-Z_]{3,}', " ".join(chunks).lower()))
            keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', " ".join(chunks)))
            
            # 为整个内容添加一个索引指针
            index.add_pointer(
                uri=f"tent://memory/{uri}",
                title=f"{memory_type}: {chunks[0][:50]}..." if chunks else uri,
                temperature=temperature,
                memory_type=memory_type,
                keywords=list(keywords)[:10],
                persona=persona
            )
            
            # 自动晋升：如果访问超过阈值，WARM → HOT
            index.auto_promote(access_threshold=5)
            logger.debug(f"MemoryIndex 已更新: {uri} ({memory_type}, {temperature})")
        except Exception as e:
            logger.warning(f"MemoryIndex 更新失败（非关键）: {e}")
    
    def _slice_content(self, content: str, chunk_size: int, overlap: int) -> List[str]:
        tokens = self.encoder.encode(content)
        chunks = []
        for i in range(0, len(tokens), chunk_size - overlap):
            chunk_tokens = tokens[i:i + chunk_size]
            chunks.append(self.encoder.decode(chunk_tokens))
        return chunks
    
    def _extract_abstract(self, chunk: str) -> str:
        """提取式摘要：基于词频+句子位置的关键句提取
        
        替代原"前150字"方案，生成更有语义的摘要，提升向量搜索召回质量。
        """
        # 分句（支持中英文）
        sentences = re.split(r'[。！？.!?]\s*', chunk)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        
        if not sentences:
            return chunk[:200]
        
        if len(sentences) == 1:
            return sentences[0][:200]
        
        # 计算词频（中文2字+词，英文3字母+词）
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', chunk.lower())
        word_freq = {}
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1
        
        # 计算句子得分 = 词频和 × 位置权重
        scored = []
        for i, sent in enumerate(sentences):
            sent_words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', sent.lower())
            score = sum(word_freq.get(w, 0) for w in sent_words)
            # 位置权重：开头句子更重要
            pos_weight = 1.5 if i == 0 else (1.3 if i == len(sentences) - 1 else 1.0)
            scored.append((score * pos_weight, sent))
        
        # 取 Top-2 句子，按原文顺序排列
        scored.sort(reverse=True)
        top_sentences = {s for _, s in scored[:2]}
        ordered = [s for s in sentences if s in top_sentences]
        
        abstract = " | ".join(ordered)[:250]
        return abstract
    
    async def _generate_l1_overview(self, chunk: str) -> str:
        """调用 LLM 生成结构化 L1 摘要
        
        成本优化：
        - 批量生成（一次处理多个 chunks）
        - 异步后台进行
        - 非阻塞主流程
        
        FIX: 不再回退到 chunk[:500] 截断——假 L1 比没有更糟。
        失败时抛异常，由调用方决定是否跳过该 chunk 的 L1。
        """
        if not self.llm:
            raise RuntimeError("LLM unavailable for L1 generation")
        
        prompt = f"""用简洁的中文总结以下内容的核心要点（200字内）：

{chunk[:12000]}

格式要求：
- 一句话摘要
- 3-5个核心要点（bullet）
- 涉及的关键实体"""
        
        if hasattr(self.llm, 'complete'):
            summary = await self.llm.complete(prompt)
        elif hasattr(self.llm, 'chat'):
            summary = await self.llm.chat([{"role": "user", "content": prompt}])
        else:
            summary = await self.llm(prompt)
        return summary.strip()
    
    async def search(self, query_vector: List[float], limit: int = 5, persona: str = None) -> List[Dict]:
        """向量语义搜索 —— 只搜 L0 层
        
        修复 OpenViking #1549：绝不直接返回 L2 内容。
        返回结果包含 L0 摘要 + L1 概览（如果可用）。
        """
        if self._vec_enabled:
            # Phase 2: 人格记忆隔离 —— 按 persona 过滤（当前人格 + 共享记忆）
            if persona:
                cursor = self.db.execute("""
                    SELECT l0.uri, l0.abstract, l1.overview,
                           vec_distance_cosine(v.embedding, ?) AS distance
                    FROM l0_index l0
                    JOIN vec_index v ON l0.rowid = v.rowid
                    LEFT JOIN l1_index l1 ON l0.uri = l1.uri
                    WHERE l0.persona = ? OR l0.persona = '__shared__' OR l0.persona IS NULL
                    ORDER BY distance ASC LIMIT ?
                """, (self._serialize_vector(query_vector), persona, limit))
            else:
                cursor = self.db.execute("""
                    SELECT l0.uri, l0.abstract, l1.overview,
                           vec_distance_cosine(v.embedding, ?) AS distance
                    FROM l0_index l0
                    JOIN vec_index v ON l0.rowid = v.rowid
                    LEFT JOIN l1_index l1 ON l0.uri = l1.uri
                    ORDER BY distance ASC LIMIT ?
                """, (self._serialize_vector(query_vector), limit))
            results = []
            for row in cursor.fetchall():
                results.append({
                    "uri": row[0],
                    "abstract": row[1],
                    "overview": row[2] or "",
                    "score": 1 - row[3],
                    "level": "l0"  # 明确标记层级
                })
            return results
        
        # 降级：纯 Python 余弦相似度计算
        return self._pure_search.search(query_vector, limit=limit, persona=persona)
    
    def get_recent(self, limit: int = 10, memory_type: str = None,
                    user_id: str = None, hours: int = None, persona: str = None) -> List[Dict]:
        """按时间倒序获取最近摄入的记忆（支持用户过滤和时间段过滤）
        
        Args:
            limit: 最多返回几条
            memory_type: 按类型过滤
            user_id: 按用户过滤（解决跨用户记忆混淆问题）
            hours: 只返回最近 N 小时的记忆（如 24, 168=7天）
        """
        conditions = []
        params = []
        
        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if hours:
            conditions.append("created_at >= datetime('now', '-{} hours')".format(hours))
        if persona:
            # Phase 2: 人格记忆隔离 —— 检索当前人格 + 共享记忆
            conditions.append("(persona = ? OR persona = '__shared__' OR persona IS NULL)")
            params.append(persona)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT uri, abstract, memory_type, created_at, user_id, persona FROM l0_index {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.db.execute(sql, params)
        return [
            {"uri": row[0], "abstract": row[1], "memory_type": row[2], "created_at": row[3], "user_id": row[4], "persona": row[5]}
            for row in cursor.fetchall()
        ]
    
    def read_l2_content(self, uri: str) -> Optional[str]:
        """读取 L2 完整内容 —— 按需加载，不自动注入 Prompt
        
        这是 Tent OS 修复 OpenViking #1549 的关键设计：
        L2 只通过显式的 tool_call memory_read(uri) 读取，绝不自动注入。
        """
        cursor = self.db.execute(
            "SELECT file_path FROM l1_index WHERE uri = ?", (uri,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            path = Path(row[0])
            if path.exists():
                return path.read_text()
        return None
    
    def update_memory_validity(self, uri: str, valid_to: str, superseded_by: Optional[str] = None):
        """更新时间维度：标记记忆失效时间和替代版本（Zep 模式）"""
        self.db.execute(
            "UPDATE l0_index SET valid_to = ?, superseded_by = ? WHERE uri = ?",
            (valid_to, superseded_by, uri)
        )
        self.db.commit()
    
    def search_at_time(self, query: str, timestamp: str, limit: int = 5, persona: str = None) -> List[Dict]:
        """时间切片查询：查询某个时间点的记忆状态（Zep 精华）"""
        # Phase 2: 人格记忆隔离
        if persona:
            cursor = self.db.execute(
                """SELECT uri, abstract, memory_type, created_at 
                   FROM l0_index 
                   WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
                     AND (persona = ? OR persona = '__shared__' OR persona IS NULL)
                   ORDER BY created_at DESC LIMIT ?""",
                (timestamp, timestamp, persona, limit)
            )
        else:
            cursor = self.db.execute(
                """SELECT uri, abstract, memory_type, created_at 
                   FROM l0_index 
                   WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
                   ORDER BY created_at DESC LIMIT ?""",
                (timestamp, timestamp, limit)
            )
        return [
            {"uri": row[0], "abstract": row[1], "memory_type": row[2], "created_at": row[3]}
            for row in cursor.fetchall()
        ]
    
    def _serialize_vector(self, vec: Optional[List[float]]) -> Optional[bytes]:
        if vec is None:
            return None
        if SQLITE_VEC_AVAILABLE:
            return sqlite_vec.serialize_float32(vec)
        return struct.pack(f"{len(vec)}f", *vec)

    async def auto_compress_l0_to_l1(self, user_id: str = None, hours: int = 24, persona: str = None) -> Dict:
        """自动压缩L0层记录到L1层摘要
        
        将最近N小时的L0记录聚合，调用LLM生成结构化摘要，存入L1层。
        这是"记忆整理"的核心机制，让AI从近期经验中提炼长期知识。
        
        Args:
            user_id: 指定用户（None则处理所有用户）
            hours: 回顾时间窗口（默认24小时）
            
        Returns:
            {"compressed_count": int, "generated_uris": [str], "summary_preview": str}
        """
        # 查询L0层最近记录（Phase 2: 按 persona 分组压缩）
        where_clause = "WHERE created_at >= datetime('now', '-{} hours')".format(hours)
        params = []
        if user_id:
            where_clause += " AND user_id = ?"
            params.append(user_id)
        if persona:
            where_clause += " AND (persona = ? OR persona = '__shared__' OR persona IS NULL)"
            params.append(persona)
        
        cursor = self.db.execute(
            f"SELECT uri, abstract, memory_type, created_at FROM l0_index {where_clause} ORDER BY created_at DESC",
            params
        )
        rows = cursor.fetchall()
        
        if len(rows) < 3:
            return {"compressed_count": 0, "generated_uris": [], "summary_preview": "记录不足，无需压缩"}
        
        # 按memory_type分组
        by_type: Dict[str, List[str]] = {}
        for row in rows:
            uri, abstract, mem_type, created_at = row
            by_type.setdefault(mem_type, []).append(f"[{created_at}] {abstract}")
        
        generated_uris = []
        total_compressed = 0
        summaries = []
        
        for mem_type, abstracts in by_type.items():
            combined = "\n".join(abstracts)
            total_compressed += len(abstracts)
            
            # 生成L1摘要
            summary = None
            if self.llm and len(combined) > 200:
                prompt = f"""将以下{mem_type}类型的记忆记录，压缩成5条关键摘要。
保留用户偏好、重要事实和决策依据。用中文输出。

记录（共{len(abstracts)}条）：
{combined[:12000]}

输出格式（每行一条，无前缀）：
- 摘要1
- 摘要2
..."""
                try:
                    if hasattr(self.llm, 'complete'):
                        summary = await self.llm.complete(prompt)
                    elif hasattr(self.llm, 'chat'):
                        # FIX: KimiCodingLLM 使用 chat(messages) 接口
                        summary = await self.llm.chat([{"role": "user", "content": prompt}])
                    else:
                        summary = await self.llm(prompt)
                    summary = summary.strip()
                except Exception as e:
                    logger.warning(f"[TieredMemory] L1压缩LLM失败: {e}")
                    summary = None
            
            if not summary:
                # LLM 不可用时跳过该类型，不生成假摘要
                continue
            
            # 存入L1层
            uri = f"l1://compress/{mem_type}/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.db.execute(
                """INSERT OR REPLACE INTO l1_index (uri, overview, overview_tokens, updated_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (uri, summary, len(self.encoder.encode(summary)))
            )
            generated_uris.append(uri)
            summaries.append(f"[{mem_type}] {summary[:100]}...")
        
        self.db.commit()
        logger.info(f"[TieredMemory] L0→L1压缩完成: {total_compressed}条 → {len(generated_uris)}个L1摘要")
        
        return {
            "compressed_count": total_compressed,
            "generated_uris": generated_uris,
            "summary_preview": "\n".join(summaries),
        }
