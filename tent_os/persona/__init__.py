"""人格系统 —— Tent OS 2.0 动态人格演化

核心模块：
- soul_evolution: 人格演化引擎（从反馈中学习）
- user_model: 用户模型构建（从记忆图谱中提取）
- persona_compressor: 人格压缩器（将完整人格压缩为 prompt）
- multi_persona: 多人格管理（工作/休闲/紧急模式）
"""

from tent_os.persona.soul_evolution import SoulEvolution, SoulDimensions
from tent_os.persona.user_model import UserModel, UserModelBuilder
from tent_os.persona.persona_compressor import PersonaCompressor
from tent_os.persona.multi_persona import MultiPersonaManager, PersonaMode

__all__ = [
    "SoulEvolution", "SoulDimensions",
    "UserModel", "UserModelBuilder",
    "PersonaCompressor",
    "MultiPersonaManager", "PersonaMode",
]
