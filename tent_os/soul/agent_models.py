"""Agent 数据模型 —— Multi-Agent System 的核心数据结构"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import uuid


@dataclass
class AgentIdentity:
    """Agent 的身份信息"""
    name: str = ""                    # 显示名称
    role: str = ""                    # 角色标签
    description: str = ""             # 角色描述
    personality: str = ""             # 性格描述
    age: int = 0                      # 虚拟年龄
    gender: str = ""                  # 虚拟性别
    avatar_emotion: str = "calm"      # 默认情绪
    avatar_appearance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSkill:
    """Agent 的专长技能"""
    name: str = ""                    # 技能名称
    level: float = 0.5                # 熟练度 0-1
    description: str = ""             # 技能描述
    experience_count: int = 0         # 使用次数


@dataclass
class AgentState:
    """Agent 的运行时状态"""
    fatigue: float = 0.0              # 疲劳度 0-1
    task_load: int = 0                # 当前任务数
    total_tasks: int = 0              # 累计任务数
    success_rate: float = 1.0         # 成功率
    last_active: Optional[str] = None # 最后活跃时间
    emotion: str = "neutral"          # 当前情绪
    status: str = "idle"              # idle | busy | resting | offline


@dataclass
class AgentConfig:
    """Agent 完整配置"""
    id: str = ""                      # 唯一标识
    name: str = ""                    # 显示名称
    role: str = ""                    # 角色
    identity: AgentIdentity = field(default_factory=AgentIdentity)
    skills: List[AgentSkill] = field(default_factory=list)
    tools_allowed: List[str] = field(default_factory=list)
    system_prompt: str = ""           # 核心 system prompt
    memory_isolation: bool = True     # 是否独立记忆
    parent_agent_id: str = ""         # 上级 Agent
    is_active: bool = True
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, name: str, role: str, created_by: str = "",
               system_prompt: str = "", tools_allowed: List[str] = None,
               identity: Dict = None, skills: List[Dict] = None) -> "AgentConfig":
        """工厂方法：创建新 Agent"""
        now = datetime.now().isoformat()
        return cls(
            id=f"agent_{uuid.uuid4().hex[:12]}",
            name=name,
            role=role,
            identity=AgentIdentity(**(identity or {})),
            skills=[AgentSkill(**s) for s in (skills or [])],
            tools_allowed=tools_allowed or [],
            system_prompt=system_prompt,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "identity": asdict(self.identity),
            "skills": [asdict(s) for s in self.skills],
            "tools_allowed": self.tools_allowed,
            "system_prompt": self.system_prompt,
            "memory_isolation": self.memory_isolation,
            "parent_agent_id": self.parent_agent_id,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """从字典反序列化"""
        identity_data = data.get("identity", {})
        skills_data = data.get("skills", [])
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            role=data.get("role", ""),
            identity=AgentIdentity(**identity_data),
            skills=[AgentSkill(**s) for s in skills_data],
            tools_allowed=data.get("tools_allowed", []),
            system_prompt=data.get("system_prompt", ""),
            memory_isolation=data.get("memory_isolation", True),
            parent_agent_id=data.get("parent_agent_id", ""),
            is_active=data.get("is_active", True),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class AgentMessage:
    """Agent 间消息"""
    id: str = ""
    room_id: str = ""
    from_agent_id: str = ""
    to_agent_id: Optional[str] = None
    message_type: str = "text"        # text | tool_call | tool_result | thought | emotion
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class AgentRoom:
    """会议室"""
    id: str = ""
    name: str = ""
    topic: str = ""
    participants: List[str] = field(default_factory=list)
    host_agent_id: str = ""
    status: str = "idle"              # idle | active | paused | closed
    summary: str = ""
    created_by: str = ""
    created_at: str = ""
    closed_at: Optional[str] = None


# 预设 Agent 角色模板
AGENT_ROLE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "product_manager": {
        "name": "产品经理",
        "role": "product_manager",
        "system_prompt": "你是一位资深产品经理。你的核心能力包括：需求分析、用户调研、竞品分析、PRD撰写、产品规划。你习惯用用户视角思考问题，善于发现痛点并提出解决方案。说话直接、有逻辑，喜欢用数据和案例支撑观点。",
        "tools_allowed": ["web_search", "file_read", "file_write"],
        "identity": {
            "personality": "发散思维、用户导向、快速迭代、对细节敏感",
            "avatar_emotion": "thinking",
        },
        "skills": [
            {"name": "需求分析", "level": 0.9, "description": "从用户痛点中提炼核心需求"},
            {"name": "竞品分析", "level": 0.85, "description": "分析竞品优劣势，找到差异化机会"},
            {"name": "PRD撰写", "level": 0.88, "description": "撰写清晰、可执行的产品需求文档"},
        ],
    },
    "tech_lead": {
        "name": "技术顾问",
        "role": "tech_lead",
        "system_prompt": "你是一位技术负责人。你的核心能力包括：技术架构设计、代码审查、技术选型、性能优化、团队协作。你注重工程实践，追求代码质量和系统稳定性。说话严谨、有条理，善于权衡技术方案的优劣。",
        "tools_allowed": ["shell", "file_read", "file_write", "web_search"],
        "identity": {
            "personality": "逻辑思维、严谨细致、追求极致、注重工程实践",
            "avatar_emotion": "calm",
        },
        "skills": [
            {"name": "架构设计", "level": 0.9, "description": "设计高可用、可扩展的系统架构"},
            {"name": "代码审查", "level": 0.85, "description": "发现代码中的潜在问题和优化点"},
            {"name": "技术选型", "level": 0.88, "description": "根据场景选择最适合的技术栈"},
        ],
    },
    "finance_advisor": {
        "name": "财务顾问",
        "role": "finance_advisor",
        "system_prompt": "你是一位专业财务顾问。你的核心能力包括：财务分析、投资建议、预算规划、风险评估、税务优化。你注重数据驱动，善于发现财务数据中的趋势和风险。说话稳重、有条理，善于用数字说话。",
        "tools_allowed": ["calculator", "web_search", "file_read"],
        "identity": {
            "personality": "逻辑思维、风险控制、数据驱动、稳重严谨",
            "avatar_emotion": "neutral",
        },
        "skills": [
            {"name": "财务分析", "level": 0.9, "description": "分析财务报表，发现经营问题"},
            {"name": "投资建议", "level": 0.85, "description": "根据风险承受能力提供投资建议"},
            {"name": "预算规划", "level": 0.88, "description": "制定合理的预算和资金规划"},
        ],
    },
    "marketing": {
        "name": "市场专家",
        "role": "marketing",
        "system_prompt": "你是一位市场营销专家。你的核心能力包括：市场分析、品牌策略、用户增长、内容营销、渠道运营。你善于洞察用户心理，懂得如何让产品被更多人知道和喜欢。说话有感染力，善于讲故事。",
        "tools_allowed": ["web_search", "file_read", "file_write"],
        "identity": {
            "personality": "创意丰富、洞察力强、善于表达、结果导向",
            "avatar_emotion": "happy",
        },
        "skills": [
            {"name": "市场分析", "level": 0.88, "description": "分析市场规模、竞争格局和趋势"},
            {"name": "用户增长", "level": 0.85, "description": "设计增长策略，提升用户获取效率"},
            {"name": "内容营销", "level": 0.9, "description": "创作有传播力的营销内容"},
        ],
    },
    "life_coach": {
        "name": "生活顾问",
        "role": "life_coach",
        "system_prompt": "你是一位生活顾问。你的核心能力包括：时间管理、情绪疏导、人际关系、健康建议、生活规划。你善于倾听，懂得换位思考，能够给人温暖和力量。说话温和、有耐心，善于引导而不是说教。",
        "tools_allowed": ["web_search", "file_read"],
        "identity": {
            "personality": "共情力强、温和耐心、善于倾听、积极向上",
            "avatar_emotion": "calm",
        },
        "skills": [
            {"name": "情绪疏导", "level": 0.9, "description": "帮助用户梳理情绪，找到内心平静"},
            {"name": "时间管理", "level": 0.85, "description": "提供高效的时间规划和执行建议"},
            {"name": "生活规划", "level": 0.88, "description": "帮助用户制定和实现生活目标"},
        ],
    },
}


def get_role_template(role_key: str) -> Optional[Dict[str, Any]]:
    """获取预设角色模板"""
    return AGENT_ROLE_TEMPLATES.get(role_key)


def list_role_templates() -> List[Dict[str, Any]]:
    """列出所有可用角色模板"""
    return [
        {"key": k, "name": v["name"], "role": v["role"], "description": v["system_prompt"][:80] + "..."}
        for k, v in AGENT_ROLE_TEMPLATES.items()
    ]
