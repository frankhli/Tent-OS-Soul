"""Memory Index 指针层 —— Claude Code memory.md 模式

核心设计：
- index.md 不是存储文件，而是轻量级路由表（~150 字符/条目）
- Agent 先读索引，再按需加载具体文件
- 支持 hot（常加载）/ warm（按需加载）/ cold（仅检索）三级
- Self-healing: Agent 可以更新自己的索引

文件结构：
    tent://memory/index.md          # 主索引（始终加载）
    tent://memory/user/profile.md   # 用户画像（hot）
    tent://memory/user/preferences/ # 偏好（warm）
    tent://memory/session/2026/     # 会话历史（cold）
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger("tent_os.memory")


class Temperature:
    """记忆温度：决定加载策略"""
    HOT = "hot"      # 始终加载（用户画像、当前任务）
    WARM = "warm"    # 按需加载（相关历史、偏好）
    COLD = "cold"    # 仅检索（归档记忆）


@dataclass
class MemoryPointer:
    """记忆指针 —— 一条索引条目"""
    uri: str                    # 唯一标识符
    title: str                  # 简短标题（50字内）
    temperature: str = Temperature.WARM  # hot/warm/cold
    memory_type: str = "general"  # fact/preference/entity/decision/pattern/error
    keywords: List[str] = None  # 检索关键词
    last_accessed: str = ""     # 最后访问时间
    access_count: int = 0       # 访问次数
    persona: str = ""           # Phase 2: 人格归属（空字符串 = 共享记忆）
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class MemoryIndex:
    """记忆索引管理器
    
    职责：
    1. 维护轻量级索引文件
    2. 根据 task_query 决定加载哪些文件
    3. 追踪访问频率，自动调整温度
    4. 支持 Self-healing（更新索引）
    """
    
    def __init__(self, storage_path: str = "./tent_memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.index_path = self.storage_path / "index.json"
        self.pointers: Dict[str, MemoryPointer] = {}
        self._load_index()
    
    def _load_index(self):
        """加载索引文件"""
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
                for uri, ptr_data in data.items():
                    self.pointers[uri] = MemoryPointer(**ptr_data)
                logger.debug(f"加载索引: {len(self.pointers)} 条指针")
            except Exception as e:
                logger.warning(f"索引加载失败，创建新索引: {e}")
                self._init_default_index()
        else:
            self._init_default_index()
    
    def _init_default_index(self):
        """初始化默认索引结构"""
        defaults = [
            MemoryPointer("tent://memory/user/profile.md", "用户画像", Temperature.HOT, "profile"),
            MemoryPointer("tent://memory/user/preferences.md", "用户偏好", Temperature.HOT, "preference"),
            MemoryPointer("tent://memory/decisions/active.md", "关键决策", Temperature.WARM, "decision"),
            MemoryPointer("tent://memory/learnings/recent.md", "近期教训", Temperature.WARM, "learning"),
            MemoryPointer("tent://memory/tasks/active.md", "待办任务", Temperature.HOT, "task"),
            MemoryPointer("tent://memory/entities/projects.md", "项目实体", Temperature.WARM, "entity"),
            MemoryPointer("tent://memory/entities/people.md", "人物实体", Temperature.WARM, "entity"),
            MemoryPointer("tent://memory/session/current.md", "当前会话", Temperature.HOT, "conversation"),
        ]
        for ptr in defaults:
            self.pointers[ptr.uri] = ptr
        self._save_index()
    
    def _save_index(self):
        """保存索引到文件"""
        data = {uri: asdict(ptr) for uri, ptr in self.pointers.items()}
        self.index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def get_pointers(self, temperature: Optional[str] = None,
                     memory_type: Optional[str] = None, persona: Optional[str] = None) -> List[MemoryPointer]:
        """获取符合条件的指针"""
        results = []
        for ptr in self.pointers.values():
            if temperature and ptr.temperature != temperature:
                continue
            if memory_type and ptr.memory_type != memory_type:
                continue
            if persona and ptr.persona and ptr.persona != persona and ptr.persona != "__shared__":
                continue
            results.append(ptr)
        return results
    
    def select_for_task(self, task_query: str, max_hot: int = 5,
                        max_warm: int = 3, max_tokens: int = 1500, persona: str = None) -> Dict[str, List[MemoryPointer]]:
        """根据任务查询选择要加载的记忆
        
        策略：
        1. 加载所有 HOT 记忆
        2. 根据 task_query 关键词匹配选择 WARM 记忆
        3. COLD 记忆不加载，仅在检索时命中
        4. 总内容不超过 max_tokens
        
        Returns:
            {"hot": [...], "warm": [...], "cold_hits": [...]}
        """
        hot = self.get_pointers(Temperature.HOT, persona=persona)
        warm_all = self.get_pointers(Temperature.WARM, persona=persona)
        
        # 关键词匹配选择 WARM 记忆（Phase 2: 人格记忆加权）
        task_lower = task_query.lower()
        warm_selected = []
        for ptr in warm_all:
            score = 0
            # 标题匹配
            if ptr.title.lower() in task_lower or any(w in ptr.title.lower() for w in task_lower.split()):
                score += 2
            # 关键词匹配
            for kw in ptr.keywords:
                if kw.lower() in task_lower:
                    score += 1
            # 类型匹配
            if ptr.memory_type in task_lower:
                score += 1
            # Phase 2: 人格匹配加权（当前人格的记忆优先）
            if persona and ptr.persona == persona:
                score += 3
            elif ptr.persona == "__shared__" or not ptr.persona:
                score += 1
            if score > 0:
                warm_selected.append((score, ptr))
        
        warm_selected.sort(key=lambda x: x[0], reverse=True)
        warm = [ptr for _, ptr in warm_selected[:max_warm]]
        
        # 记录访问
        for ptr in hot + warm:
            ptr.access_count += 1
            ptr.last_accessed = datetime.now().isoformat()
        
        self._save_index()
        
        return {
            "hot": hot,
            "warm": warm,
            "cold_hits": [],  # COLD 记忆不在启动时加载
        }
    
    def add_pointer(self, uri: str, title: str, temperature: str = Temperature.WARM,
                    memory_type: str = "general", keywords: List[str] = None, persona: str = None):
        """添加新指针（Self-healing 用）"""
        ptr = MemoryPointer(uri, title, temperature, memory_type, keywords or [], persona=persona or "")
        self.pointers[uri] = ptr
        self._save_index()
        logger.debug(f"索引新增: {uri}")
    
    def update_pointer(self, uri: str, **kwargs):
        """更新指针属性（Self-healing 用）"""
        if uri not in self.pointers:
            return False
        ptr = self.pointers[uri]
        for key, value in kwargs.items():
            if hasattr(ptr, key):
                setattr(ptr, key, value)
        ptr.last_accessed = datetime.now().isoformat()
        self._save_index()
        return True
    
    def remove_pointer(self, uri: str):
        """删除指针"""
        if uri in self.pointers:
            del self.pointers[uri]
            self._save_index()
    
    def auto_promote(self, access_threshold: int = 5):
        """自动升温：访问超过阈值的 WARM 记忆提升为 HOT"""
        promoted = []
        for ptr in self.pointers.values():
            if ptr.temperature == Temperature.WARM and ptr.access_count >= access_threshold:
                ptr.temperature = Temperature.HOT
                promoted.append(ptr.uri)
        if promoted:
            self._save_index()
            logger.info(f"记忆自动升温: {promoted}")
        return promoted
    
    def auto_demote(self, days_inactive: int = 30):
        """自动降温：长期未访问的 HOT 记忆降级为 WARM"""
        from datetime import timedelta
        demoted = []
        cutoff = (datetime.now() - timedelta(days=days_inactive)).isoformat()
        for ptr in self.pointers.values():
            if ptr.temperature == Temperature.HOT and ptr.last_accessed < cutoff:
                ptr.temperature = Temperature.WARM
                demoted.append(ptr.uri)
        if demoted:
            self._save_index()
            logger.info(f"记忆自动降温: {demoted}")
        return demoted
    
    def read_content(self, uri: str) -> Optional[str]:
        """读取指针指向的文件内容"""
        # 将 tent:// URI 映射到本地路径
        if uri.startswith("tent://memory/"):
            local_path = self.storage_path / uri.replace("tent://memory/", "")
            if local_path.exists():
                # 更新访问记录
                if uri in self.pointers:
                    self.pointers[uri].access_count += 1
                    self.pointers[uri].last_accessed = datetime.now().isoformat()
                    self._save_index()
                return local_path.read_text()
        return None
    
    def render_index(self) -> str:
        """渲染索引为文本（用于 Prompt 注入）"""
        lines = ["# 记忆索引（Memory Index）", ""]
        
        # HOT 记忆
        hot = self.get_pointers(Temperature.HOT)
        if hot:
            lines.append("## 🔥 HOT（始终加载）")
            for ptr in hot:
                lines.append(f"- [{ptr.memory_type}] {ptr.title} → `{ptr.uri}`")
            lines.append("")
        
        # WARM 记忆
        warm = self.get_pointers(Temperature.WARM)
        if warm:
            lines.append("## 🌡️ WARM（按需加载）")
            for ptr in warm:
                lines.append(f"- [{ptr.memory_type}] {ptr.title} → `{ptr.uri}`")
            lines.append("")
        
        # 统计
        cold_count = len([p for p in self.pointers.values() if p.temperature == Temperature.COLD])
        lines.append(f"## 📊 统计")
        lines.append(f"- HOT: {len(hot)}, WARM: {len(warm)}, COLD: {cold_count}")
        lines.append(f"- 总计: {len(self.pointers)} 条记忆")
        lines.append("")
        lines.append("如需读取完整内容，使用 memory_read(uri) 工具")
        
        return "\n".join(lines)
