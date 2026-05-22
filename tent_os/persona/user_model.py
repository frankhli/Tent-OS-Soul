"""用户模型 —— 从记忆图谱中自动构建用户画像

自动提取的属性：
- 静态属性（变化慢）：偏好、沟通风格、专业领域
- 动态状态（变化快）：当前情绪、当前目标、注意力水平
- 关系历史：交互次数、信任度
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.memory.graph import CognitiveGraph

logger = logging.getLogger("tent_os.persona.user_model")


@dataclass
class UserModel:
    """用户模型"""
    user_id: str
    
    # 静态属性（变化慢）
    preferences: Dict[str, float] = None       # 偏好及强度
    communication_style: str = ""              # 沟通风格描述
    expertise_areas: List[str] = None          # 专业领域
    
    # 动态状态（变化快）
    current_mood: str = "neutral"              # 当前情绪
    current_goal: str = ""                     # 当前目标
    attention_level: float = 0.5               # 注意力水平 0-1
    
    # 关系历史
    interaction_count: int = 0
    last_interaction: Optional[str] = None
    trust_level: float = 0.5                   # 信任度 0-1
    
    # 时间上下文
    preferred_times: Dict[str, str] = None     # 偏好交互时间
    
    def __post_init__(self):
        if self.preferences is None:
            self.preferences = {}
        if self.expertise_areas is None:
            self.expertise_areas = []
        if self.preferred_times is None:
            self.preferred_times = {}


class UserModelBuilder:
    """用户模型构建器 —— 从认知图谱中提取用户画像"""
    
    def __init__(self, graph: CognitiveGraph):
        self.graph = graph
    
    def build(self, user_id: str) -> UserModel:
        """构建用户模型"""
        model = UserModel(user_id=user_id)
        
        # 1. 提取偏好（preference 类型节点）
        pref_nodes = self.graph.get_nodes_by_type("preference", min_confidence=0.3)
        for node in pref_nodes:
            # 提取关键词作为偏好名
            import re
            # 简单提取："用户喜欢辣" → "喜欢辣"
            content = node.content
            # 去掉常见前缀
            for prefix in ["用户", "他", "她", "我"]:
                if content.startswith(prefix):
                    content = content[len(prefix):].lstrip("，,、")
            
            key = content[:20]  # 取前 20 字作为偏好键
            model.preferences[key] = node.confidence
        
        # 2. 提取专业领域（entity 类型节点）
        entity_nodes = self.graph.get_nodes_by_type("entity")
        for node in entity_nodes:
            if any(kw in node.content for kw in ["项目", "project", "系统", "system", "平台", "platform"]):
                model.expertise_areas.append(node.content[:30])
        
        # 3. 统计交互次数（通过 source_session 计数）
        try:
            rows = self.graph.db.execute(
                "SELECT COUNT(DISTINCT source_session) as cnt FROM nodes WHERE source_session LIKE ?",
                (f"%{user_id}%",)
            ).fetchall()
            if rows and rows[0]["cnt"]:
                model.interaction_count = rows[0]["cnt"]
        except Exception:
            pass
        
        # 4. 最后交互时间
        try:
            row = self.graph.db.execute(
                "SELECT MAX(created_at) as last FROM nodes WHERE source_session LIKE ?",
                (f"%{user_id}%",)
            ).fetchone()
            if row and row["last"]:
                model.last_interaction = row["last"]
        except Exception:
            pass
        
        # 5. 信任度（基于授权行为推断）
        # TODO: 从授权记录中推断
        model.trust_level = min(1.0, 0.3 + model.interaction_count * 0.02)
        
        # 6. 沟通风格推断
        model.communication_style = self._infer_communication_style(user_id)
        
        return model
    
    def _infer_communication_style(self, user_id: str) -> str:
        """推断沟通风格"""
        try:
            # 获取用户最近的消息
            rows = self.graph.db.execute(
                """SELECT content FROM nodes 
                   WHERE source_session LIKE ? AND memory_type = 'conversation'
                   ORDER BY created_at DESC LIMIT 20""",
                (f"%{user_id}%",)
            ).fetchall()
            
            if not rows:
                return "未知"
            
            contents = [r["content"] for r in rows]
            avg_length = sum(len(c) for c in contents) / len(contents)
            
            # 简单推断
            if avg_length < 30:
                return "简洁直接"
            elif avg_length > 150:
                return "详尽描述"
            else:
                return "适中"
        except Exception:
            return "未知"
    
    def update_dynamic_state(self, model: UserModel, 
                             current_mood: str = None,
                             current_goal: str = None,
                             attention_level: float = None):
        """更新动态状态"""
        if current_mood:
            model.current_mood = current_mood
        if current_goal:
            model.current_goal = current_goal
        if attention_level is not None:
            model.attention_level = max(0.0, min(1.0, attention_level))
        model.last_interaction = datetime.now().isoformat()
    
    def to_prompt_segment(self, model: UserModel) -> str:
        """将用户模型转换为 prompt 片段"""
        lines = ["## 用户画像"]
        
        if model.preferences:
            lines.append("### 已知偏好")
            for pref, strength in sorted(model.preferences.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"- {pref} (确信度: {strength:.0%})")
        
        if model.expertise_areas:
            lines.append("### 专业领域")
            for area in model.expertise_areas[:5]:
                lines.append(f"- {area}")
        
        if model.communication_style:
            lines.append(f"### 沟通风格: {model.communication_style}")
        
        if model.current_goal:
            lines.append(f"### 当前目标: {model.current_goal}")
        
        if model.trust_level > 0.7:
            lines.append("- 用户信任度较高，可适当增加自主决策")
        elif model.trust_level < 0.3:
            lines.append("- 用户信任度较低，重要决策需确认")
        
        return "\n".join(lines)
