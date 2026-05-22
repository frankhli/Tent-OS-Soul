"""Tent OS Skills 系统

参考 OpenClaw 的 Skill 设计：
- 每个 Skill 是一个目录，包含 SKILL.md
- SKILL.md 定义技能的触发条件、工具、prompt 补充
- 运行时根据任务关键词动态匹配和加载
"""

from tent_os.skills.manager import SkillManager
from tent_os.skills.router import SkillRouter
from tent_os.skills.loader import Skill, SkillLoader

__all__ = ["SkillManager", "SkillRouter", "Skill", "SkillLoader"]
