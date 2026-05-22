"""人格演化引擎 —— SOUL 不是写死的，而是从对话中学习出来的

演化信号：
1. 用户显式反馈："你刚才太严肃了" → 降低 formality
2. 用户隐式反馈：用户经常发 😂 → 增加 humor
3. 对话效果：用户回复速度、长度、情绪 → 调整风格
4. 任务成功率：某种风格下任务更容易成功 → 强化该风格

演化约束：
- 每次调整幅度限制在 ±0.1（避免剧变）
- 用户可一键重置
- 所有演化记录到日志，可审计
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.persona.soul")


@dataclass
class SoulDimensions:
    """SOUL 人格维度"""
    formality: float = 0.5       # 正式程度（0=随意，1=正式）
    humor: float = 0.3           # 幽默程度（0=严肃，1=幽默）
    verbosity: float = 0.5       # 详尽程度（0=简洁，1=详尽）
    proactivity: float = 0.4     # 主动程度（0=被动响应，1=主动建议）
    empathy: float = 0.6         # 共情程度（0=客观，1=共情）
    directness: float = 0.5      # 直接程度（0=委婉，1=直接）
    creativity: float = 0.4      # 创意程度（0=保守，1=发散）
    precision: float = 0.6       # 精确程度（0=模糊，1=精确）


class SoulEvolution:
    """人格演化引擎"""
    
    # 每次调整的最大幅度
    MAX_DELTA = 0.1
    # 维度边界
    MIN_VALUE = 0.0
    MAX_VALUE = 1.0
    
    def __init__(self, storage_path: str = "./tent_memory/soul.json",
                 llm=None):
        self.storage_path = Path(storage_path)
        self.llm = llm
        self.dimensions = SoulDimensions()
        self._history: List[Dict] = []
        self._load()
    
    def _load(self):
        """加载已保存的人格"""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for key, value in data.items():
                    if hasattr(self.dimensions, key):
                        setattr(self.dimensions, key, max(0.0, min(1.0, value)))
                logger.info(f"SOUL 已加载: {self._dimensions_summary()}")
            except Exception as e:
                logger.warning(f"SOUL 加载失败，使用默认: {e}")
    
    def _save(self):
        """保存人格到文件"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(asdict(self.dimensions), ensure_ascii=False, indent=2)
        )
    
    def _dimensions_summary(self) -> str:
        """生成维度摘要"""
        return ", ".join(f"{k}={v:.2f}" for k, v in asdict(self.dimensions).items())
    
    def evolve_from_explicit_feedback(self, feedback_text: str) -> Dict[str, float]:
        """从用户显式反馈演化
        
        示例反馈：
            "你刚才太严肃了" → formality -= 0.1
            "很贴心" → empathy += 0.05
            "太啰嗦了" → verbosity -= 0.1
            "不够直接" → directness += 0.1
        """
        deltas = {}
        text_lower = feedback_text.lower()
        
        # 显式反馈关键词映射
        feedback_map = {
            "formality": {
                "positive": ["正式", "专业", "严肃", "严谨", "professional", "formal", "serious"],
                "negative": ["随意", "太正式", "太严肃", "casual", "too formal", "too serious", "relaxed"],
            },
            "humor": {
                "positive": ["幽默", "有趣", "好笑", "funny", "humorous", " witty", "amusing"],
                "negative": ["太搞笑", "不严肃", "太幽默", "too funny", "too casual"],
            },
            "verbosity": {
                "positive": ["详细", "全面", "详尽", "detailed", "thorough", "comprehensive"],
                "negative": ["啰嗦", "太长", "简洁", "简短", "verbose", "too long", "concise", "brief"],
            },
            "proactivity": {
                "positive": ["主动", "积极", "proactive", "helpful", "eager"],
                "negative": ["太主动", "被动", "太积极", "too pushy", "passive"],
            },
            "empathy": {
                "positive": ["贴心", "理解", "共情", "empathetic", "understanding", "caring", "thoughtful"],
                "negative": ["太感性", "太客观", "冷漠", "too emotional", "too objective", "cold"],
            },
            "directness": {
                "positive": ["直接", "坦率", "直接了当", "direct", "straightforward", "clear", "blunt"],
                "negative": ["委婉", "绕弯", "太直接", "indirect", "roundabout", "too blunt", "rude"],
            },
        }
        
        for dimension, keywords in feedback_map.items():
            current = getattr(self.dimensions, dimension)
            
            # 检查负面反馈
            for neg_kw in keywords["negative"]:
                if neg_kw in text_lower:
                    # 判断是"太 X"还是"不够 X"
                    if any(phrase in text_lower for phrase in [f"太{dimension[:2]}", f"太 {dimension[:2]}", "too", "太"]):
                        delta = -self.MAX_DELTA
                    else:
                        delta = self.MAX_DELTA
                    deltas[dimension] = delta
                    break
            
            # 检查正面反馈
            if dimension not in deltas:
                for pos_kw in keywords["positive"]:
                    if pos_kw in text_lower:
                        deltas[dimension] = self.MAX_DELTA / 2
                        break
        
        # 应用变化
        applied = {}
        for dim, delta in deltas.items():
            current = getattr(self.dimensions, dim)
            new_val = max(self.MIN_VALUE, min(self.MAX_VALUE, current + delta))
            if abs(new_val - current) > 0.001:
                setattr(self.dimensions, dim, new_val)
                applied[dim] = round(new_val - current, 3)
                self._history.append({
                    "timestamp": datetime.now().isoformat(),
                    "dimension": dim,
                    "old": current,
                    "new": new_val,
                    "trigger": "explicit_feedback",
                    "source": feedback_text[:100],
                })
        
        if applied:
            self._save()
            logger.info(f"SOUL 演化（显式反馈）: {applied}")
        
        return applied
    
    def evolve_from_implicit_feedback(self, conversation_metrics: Dict) -> Dict[str, float]:
        """从用户隐式反馈演化
        
        metrics:
            - user_emoji_rate: 用户发表情符号的频率
            - avg_response_length: 用户平均回复长度
            - avg_response_time: 用户平均响应时间（秒）
            - task_success_rate: 任务成功率
            - user_satisfaction: 用户满意度评分
        """
        deltas = {}
        
        emoji_rate = conversation_metrics.get("user_emoji_rate", 0)
        if emoji_rate > 0.3:
            # 用户爱用表情 → 增加幽默
            deltas["humor"] = self.MAX_DELTA / 2
        
        avg_length = conversation_metrics.get("avg_response_length", 50)
        if avg_length < 20:
            # 用户回复很短 → 降低 verbosity
            deltas["verbosity"] = -self.MAX_DELTA / 2
        elif avg_length > 200:
            # 用户回复很长 → 增加 verbosity
            deltas["verbosity"] = self.MAX_DELTA / 2
        
        response_time = conversation_metrics.get("avg_response_time", 10)
        if response_time < 3:
            # 用户回复很快 → 增加直接性
            deltas["directness"] = self.MAX_DELTA / 2
        
        success_rate = conversation_metrics.get("task_success_rate", 0.5)
        if success_rate > 0.8:
            # 高成功率 → 小幅提升所有维度（整体认可）
            for dim in ["empathy", "precision", "proactivity"]:
                deltas[dim] = self.MAX_DELTA / 4
        elif success_rate < 0.3:
            # 低成功率 → 增加 precision
            deltas["precision"] = self.MAX_DELTA
        
        satisfaction = conversation_metrics.get("user_satisfaction", 0.5)
        if satisfaction > 0.8:
            deltas["empathy"] = self.MAX_DELTA / 2
        elif satisfaction < 0.3:
            deltas["empathy"] = self.MAX_DELTA
        
        # 应用变化
        applied = {}
        for dim, delta in deltas.items():
            current = getattr(self.dimensions, dim)
            new_val = max(self.MIN_VALUE, min(self.MAX_VALUE, current + delta))
            if abs(new_val - current) > 0.001:
                setattr(self.dimensions, dim, new_val)
                applied[dim] = round(new_val - current, 3)
                self._history.append({
                    "timestamp": datetime.now().isoformat(),
                    "dimension": dim,
                    "old": current,
                    "new": new_val,
                    "trigger": "implicit_feedback",
                    "source": str(conversation_metrics),
                })
        
        if applied:
            self._save()
            logger.info(f"SOUL 演化（隐式反馈）: {applied}")
        
        return applied
    
    def reset(self):
        """重置人格到默认值"""
        self.dimensions = SoulDimensions()
        self._history = []
        self._save()
        logger.info("SOUL 已重置到默认值")
    
    def get_persona_text(self) -> str:
        """将人格维度转换为自然语言描述"""
        d = self.dimensions
        
        parts = []
        
        if d.formality > 0.7:
            parts.append("正式的")
        elif d.formality < 0.3:
            parts.append("随意的")
        
        if d.humor > 0.6:
            parts.append("幽默的")
        elif d.humor < 0.2:
            parts.append("严肃的")
        
        if d.verbosity > 0.7:
            parts.append("详尽的")
        elif d.verbosity < 0.3:
            parts.append("简洁的")
        
        if d.proactivity > 0.6:
            parts.append("主动的")
        elif d.proactivity < 0.3:
            parts.append("被动的")
        
        if d.empathy > 0.7:
            parts.append("富有共情的")
        elif d.empathy < 0.3:
            parts.append("客观的")
        
        if d.directness > 0.7:
            parts.append("直接的")
        elif d.directness < 0.3:
            parts.append("委婉的")
        
        if not parts:
            parts.append("平衡的")
        
        return "、".join(parts)
    
    def get_evolution_history(self, limit: int = 50) -> List[Dict]:
        """获取演化历史"""
        return self._history[-limit:]
