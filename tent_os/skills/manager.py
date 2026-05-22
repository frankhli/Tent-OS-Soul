"""Skill Manager —— 管理所有已加载的 Skills

职责：
1. 扫描 skills/ 目录，加载所有 SKILL.md
2. 根据用户输入匹配最佳 Skill
3. 返回匹配的 Skill 的 tools 和 prompt 补充
4. 支持动态重新加载（热更新）
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

from tent_os.skills.loader import Skill, SkillLoader

logger = logging.getLogger("tent_os.skills")


class SkillManager:
    """Skills 管理器"""
    
    def __init__(self, skills_dir: str = "./skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._load_all()
    
    def _load_all(self):
        """扫描并加载所有 Skills"""
        if not self.skills_dir.exists():
            logger.info(f"Skills 目录不存在: {self.skills_dir}")
            return
        
        count = 0
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill = SkillLoader.load_from_directory(item)
                if skill:
                    self.skills[skill.name] = skill
                    count += 1
                    logger.info(f"加载 Skill: {skill.name} (triggers: {skill.triggers})")
        
        logger.info(f"共加载 {count} 个 Skills")
    
    def reload(self):
        """热重新加载所有 Skills"""
        self.skills.clear()
        self._load_all()
    
    def match(self, text: str, threshold: float = 0.3) -> Optional[Skill]:
        """根据用户输入匹配最佳 Skill
        
        Args:
            text: 用户输入文本
            threshold: 匹配度阈值，低于此值返回 None
        
        Returns:
            最佳匹配的 Skill，或 None
        """
        if not self.skills:
            return None
        
        best_skill = None
        best_score = 0.0
        
        for skill in self.skills.values():
            score = skill.matches(text)
            if score > best_score:
                best_score = score
                best_skill = skill
        
        if best_score >= threshold:
            logger.info(f"匹配 Skill: {best_skill.name} (score={best_score:.2f})")
            return best_skill
        
        return None
    
    def get_all_tools(self) -> List[Dict]:
        """获取所有 Skill 定义的工具"""
        tools = []
        for skill in self.skills.values():
            tools.extend(skill.tools)
        return tools
    
    def get_prompt_for_task(self, text: str) -> str:
        """获取匹配任务的 prompt 补充"""
        skill = self.match(text)
        if skill and skill.prompt:
            return f"\n\n## Skill: {skill.name}\n{skill.prompt}"
        return ""
    
    def list_skills(self) -> List[Dict]:
        """列出所有已加载的 Skills"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "tools": [t["name"] for t in s.tools],
            }
            for s in self.skills.values()
        ]
