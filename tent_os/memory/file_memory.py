"""文件记忆系统 —— Claude Code 模式融合

核心设计：
1. Markdown + YAML frontmatter —— 人类可读、可直接编辑、版本可控
2. LLM 相关性召回 —— 不用 embedding，用低成本 LLM 扫描文件头评估相关性
3. 三级混合架构：Redis（热）+ SQLite（温）+ Markdown（冷）

目录结构：
./tent_memory/files/
├── projects/
│   └── shadow-bees-v52.md      # 项目上下文
├── users/
│   └── frank.md                # 用户长期画像
├── experiences/
│   └── 2026-04-fix-sqlite-lock.md  # 经验沉淀
└── skills/
    └── render-ppt-best-practice.md   # 技能最佳实践

Markdown 格式：
---
type: project
id: shadow-bees-v52
title: Shadow Bees V5.2 项目
created: 2026-04-01
updated: 2026-04-23
tags: [hotel, pms, ai]
relevance_score: 0.0  # 运行时动态计算
---

# Shadow Bees V5.2

项目概述...
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class FileMemory:
    """文件记忆对象"""
    path: Path
    frontmatter: Dict[str, Any]
    content: str
    relevance_score: float = 0.0
    
    @property
    def memory_type(self) -> str:
        return self.frontmatter.get("type", "unknown")
    
    @property
    def memory_id(self) -> str:
        return self.frontmatter.get("id", self.path.stem)
    
    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.path.stem)
    
    @property
    def tags(self) -> List[str]:
        return self.frontmatter.get("tags", [])
    
    @property
    def summary(self) -> str:
        """返回前500字作为摘要"""
        lines = self.content.strip().split("\n")
        # 跳过 frontmatter 分隔线
        text_lines = []
        in_frontmatter = False
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                text_lines.append(line)
        text = "\n".join(text_lines).strip()
        return text[:500] + "..." if len(text) > 500 else text


class FileMemoryStore:
    """文件记忆存储
    
    召回机制：
    1. 扫描 files/ 目录下所有 .md 文件
    2. 读取 YAML frontmatter 快速筛选（tags/type匹配）
    3. 用低成本 LLM 评估每个文件与当前任务的相关性
    4. 选择 top-K 最相关文件，读取全文注入上下文
    """
    
    def __init__(self, base_dir: str = "./tent_memory/files",
                 relevance_llm: Optional[Any] = None,
                 cache_ttl_seconds: int = 300):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建默认子目录
        for subdir in ("projects", "users", "experiences", "skills"):
            (self.base_dir / subdir).mkdir(exist_ok=True)
        
        self.relevance_llm = relevance_llm
        self.cache_ttl = cache_ttl_seconds
        
        # 内存缓存: path_str -> (mtime, FileMemory)
        self._cache: Dict[str, Tuple[float, FileMemory]] = {}
        
        # 相关性评估缓存: (task_hash, file_path) -> (score, timestamp)
        self._relevance_cache: Dict[str, Tuple[float, float]] = {}
    
    # ========== CRUD ==========
    
    def create(self, memory_type: str, memory_id: str, title: str,
               content: str, tags: List[str] = None, **extra_meta) -> Path:
        """创建新的文件记忆"""
        subdir = self.base_dir / memory_type if memory_type in ("projects", "users", "experiences", "skills") else self.base_dir / "experiences"
        subdir.mkdir(exist_ok=True)
        
        file_path = subdir / f"{memory_id}.md"
        
        frontmatter = {
            "type": memory_type,
            "id": memory_id,
            "title": title,
            "created": time.strftime("%Y-%m-%d"),
            "updated": time.strftime("%Y-%m-%d"),
            "tags": tags or [],
        }
        frontmatter.update(extra_meta)
        
        yaml_lines = ["---"]
        for k, v in frontmatter.items():
            if isinstance(v, list):
                yaml_lines.append(f"{k}: [{', '.join(v)}]")
            else:
                yaml_lines.append(f"{k}: {v}")
        yaml_lines.append("---")
        yaml_lines.append("")
        yaml_lines.append(f"# {title}")
        yaml_lines.append("")
        yaml_lines.append(content)
        
        file_path.write_text("\n".join(yaml_lines), encoding="utf-8")
        logger.info(f"[FileMem] 创建记忆: {file_path}")
        return file_path
    
    def read(self, memory_id: str, memory_type: str = None) -> Optional[FileMemory]:
        """读取单个文件记忆"""
        if memory_type:
            path = self.base_dir / memory_type / f"{memory_id}.md"
            if path.exists():
                return self._parse_file(path)
        else:
            # 搜索所有子目录
            for subdir in self.base_dir.iterdir():
                if subdir.is_dir():
                    path = subdir / f"{memory_id}.md"
                    if path.exists():
                        return self._parse_file(path)
        return None
    
    def update(self, memory_id: str, content: str = None, 
               memory_type: str = None, **meta_updates) -> bool:
        """更新文件记忆"""
        mem = self.read(memory_id, memory_type)
        if not mem:
            return False
        
        # 更新 frontmatter
        if meta_updates:
            mem.frontmatter.update(meta_updates)
        mem.frontmatter["updated"] = time.strftime("%Y-%m-%d")
        
        # 更新内容
        if content:
            mem.content = content
        
        # 重新写入
        yaml_lines = ["---"]
        for k, v in mem.frontmatter.items():
            if isinstance(v, list):
                yaml_lines.append(f"{k}: [{', '.join(v)}]")
            else:
                yaml_lines.append(f"{k}: {v}")
        yaml_lines.append("---")
        yaml_lines.append("")
        yaml_lines.append(f"# {mem.title}")
        yaml_lines.append("")
        yaml_lines.append(mem.content)
        
        mem.path.write_text("\n".join(yaml_lines), encoding="utf-8")
        
        # 清除缓存
        cache_key = str(mem.path)
        self._cache.pop(cache_key, None)
        return True
    
    def delete(self, memory_id: str, memory_type: str = None) -> bool:
        """删除文件记忆"""
        mem = self.read(memory_id, memory_type)
        if not mem:
            return False
        mem.path.unlink()
        self._cache.pop(str(mem.path), None)
        return True
    
    # ========== 召回机制 ==========
    
    async def recall(self, task_query: str, 
                     top_k: int = 5,
                     memory_types: List[str] = None,
                     use_llm: bool = True) -> List[FileMemory]:
        """召回与任务相关的文件记忆
        
        流程：
        1. 扫描所有 .md 文件
        2. 快速标签/类型筛选
        3. 用 LLM 评估相关性（可选，缓存结果）
        4. 返回 top-K
        """
        # 1. 扫描所有文件
        all_files = self._scan_files()
        
        # 2. 类型过滤
        if memory_types:
            all_files = [f for f in all_files if f.memory_type in memory_types]
        
        if not all_files:
            return []
        
        # 3. 快速启发式预筛选（tags匹配+标题关键词）
        query_lower = task_query.lower()
        query_keywords = set(re.findall(r'[a-zA-Z_]{3,}', query_lower))
        query_keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', query_lower))
        
        scored = []
        for mem in all_files:
            score = 0.0
            # 标题匹配
            title_lower = mem.title.lower()
            if any(kw in title_lower for kw in query_keywords):
                score += 0.3
            # tags匹配
            for tag in mem.tags:
                if tag.lower() in query_lower:
                    score += 0.2
            # 摘要匹配
            summary_lower = mem.summary.lower()
            if any(kw in summary_lower for kw in query_keywords):
                score += 0.1
            
            if score > 0:
                mem.relevance_score = score
                scored.append(mem)
        
        # 如果没有启发式匹配，取所有文件
        if not scored:
            scored = all_files
        
        # 4. LLM 细粒度相关性评估（可选）
        if use_llm and self.relevance_llm and len(scored) > top_k:
            scored = await self._llm_rerank(task_query, scored)
        
        # 5. 排序取 top-K
        scored.sort(key=lambda x: x.relevance_score, reverse=True)
        return scored[:top_k]
    
    async def _llm_rerank(self, task_query: str, 
                          candidates: List[FileMemory]) -> List[FileMemory]:
        """用低成本 LLM 评估文件与任务的相关性"""
        # 检查缓存
        task_hash = str(hash(task_query) % 100000)
        results = []
        uncached = []
        
        for mem in candidates:
            cache_key = f"{task_hash}:{str(mem.path)}"
            if cache_key in self._relevance_cache:
                cached_score, cached_ts = self._relevance_cache[cache_key]
                if time.time() - cached_ts < self.cache_ttl:
                    mem.relevance_score = cached_score
                    results.append(mem)
                    continue
            uncached.append(mem)
        
        if not uncached:
            return results
        
        # 批量评估（每次最多10个，避免 prompt 太长）
        batch_size = 10
        for i in range(0, len(uncached), batch_size):
            batch = uncached[i:i+batch_size]
            try:
                scored_batch = await self._evaluate_batch(task_query, batch)
                for mem, score in scored_batch:
                    mem.relevance_score = score
                    results.append(mem)
                    cache_key = f"{task_hash}:{str(mem.path)}"
                    self._relevance_cache[cache_key] = (score, time.time())
            except Exception as e:
                logger.warning(f"[FileMem] LLM 相关性评估失败: {e}")
                for mem in batch:
                    mem.relevance_score = 0.1  # 保底分数
                    results.append(mem)
        
        return results
    
    async def _evaluate_batch(self, task_query: str, 
                              batch: List[FileMemory]) -> List[Tuple[FileMemory, float]]:
        """评估一批文件的相关性"""
        # 构建评估 prompt
        lines = [f"任务: {task_query}", "", "评估以下文件与任务的相关性（0-1分）：", ""]
        for i, mem in enumerate(batch):
            lines.append(f"[{i}] {mem.title}")
            lines.append(f"类型: {mem.memory_type} | 标签: {', '.join(mem.tags)}")
            lines.append(f"摘要: {mem.summary[:200]}")
            lines.append("")
        
        lines.append("请返回 JSON 格式: [{\"index\": 0, \"score\": 0.85}, ...]")
        prompt = "\n".join(lines)
        
        # 调用 LLM（低成本模型）
        if hasattr(self.relevance_llm, "chat"):
            response = await self.relevance_llm.chat([
                {"role": "system", "content": "你是一个文件相关性评估专家。只输出 JSON 数组。"},
                {"role": "user", "content": prompt},
            ])
        else:
            response = await self.relevance_llm(prompt)
        
        # 解析 JSON
        try:
            # 尝试提取 JSON 数组
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                scores = json.loads(json_match.group())
                result = []
                for item in scores:
                    idx = item.get("index", 0)
                    score = float(item.get("score", 0))
                    if 0 <= idx < len(batch):
                        result.append((batch[idx], min(max(score, 0.0), 1.0)))
                return result
        except Exception as e:
            logger.debug(f"[FileMem] 解析相关性分数失败: {e}")
        
        # 解析失败，返回默认分数
        return [(mem, 0.1) for mem in batch]
    
    def format_for_injection(self, memories: List[FileMemory]) -> str:
        """将文件记忆格式化为注入上下文字符串"""
        if not memories:
            return ""
        
        parts = ["📁 项目/经验记忆（来自文件系统）：", ""]
        for mem in memories:
            parts.append(f"## {mem.title}")
            parts.append(f"[类型: {mem.memory_type} | 相关度: {mem.relevance_score:.0%}]")
            parts.append(mem.summary)
            parts.append("")
        
        return "\n".join(parts)
    
    # ========== 内部方法 ==========
    
    def _scan_files(self) -> List[FileMemory]:
        """扫描所有 .md 文件"""
        files = []
        for subdir in self.base_dir.iterdir():
            if not subdir.is_dir():
                continue
            for md_file in subdir.glob("*.md"):
                try:
                    mem = self._parse_file(md_file)
                    if mem:
                        files.append(mem)
                except Exception as e:
                    logger.debug(f"[FileMem] 解析文件失败 {md_file}: {e}")
        return files
    
    def _parse_file(self, path: Path) -> Optional[FileMemory]:
        """解析 Markdown 文件，提取 frontmatter 和内容"""
        path_str = str(path)
        mtime = path.stat().st_mtime
        
        # 检查缓存
        if path_str in self._cache:
            cached_mtime, cached_mem = self._cache[path_str]
            if cached_mtime == mtime:
                return cached_mem
        
        text = path.read_text(encoding="utf-8")
        frontmatter: Dict[str, Any] = {}
        content = text
        
        # 解析 YAML frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                yaml_text = parts[1].strip()
                content = parts[2].strip()
                frontmatter = self._parse_yaml(yaml_text)
        
        mem = FileMemory(
            path=path,
            frontmatter=frontmatter,
            content=content,
        )
        
        # 更新缓存
        self._cache[path_str] = (mtime, mem)
        return mem
    
    def _parse_yaml(self, yaml_text: str) -> Dict[str, Any]:
        """极简 YAML 解析（只处理简单键值对和列表）"""
        result = {}
        for line in yaml_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                # 处理列表 [a, b, c]
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip().strip('"\'') for v in value[1:-1].split(",") if v.strip()]
                
                result[key] = value
        return result
    
    def list_all(self, memory_type: str = None) -> List[Dict]:
        """列出所有文件记忆的元信息"""
        files = self._scan_files()
        if memory_type:
            files = [f for f in files if f.memory_type == memory_type]
        
        return [
            {
                "id": f.memory_id,
                "type": f.memory_type,
                "title": f.title,
                "tags": f.tags,
                "path": str(f.path),
                "created": f.frontmatter.get("created", ""),
                "updated": f.frontmatter.get("updated", ""),
            }
            for f in files
        ]
