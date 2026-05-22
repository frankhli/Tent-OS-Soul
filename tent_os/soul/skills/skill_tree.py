"""Agent 技能树系统

核心设计：
- 每个角色有一棵预设的技能树
- 技能分等级（1-5级），每级需要累积 XP
- 父技能达到指定等级后解锁子技能
- 技能等级影响 Agent 在调度时的评分权重
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SkillNode:
    """技能树节点"""
    id: str                          # 技能唯一标识
    name: str                        # 显示名称
    description: str = ""            # 描述
    level: int = 1                   # 当前等级（1-5）
    max_level: int = 5               # 最大等级
    current_xp: int = 0              # 当前 XP
    xp_required: List[int] = field(default_factory=list)  # 每级升级所需XP [100, 300, 600, 1000]
    parent_id: Optional[str] = None  # 父技能ID
    children_ids: List[str] = field(default_factory=list)  # 子技能ID列表
    unlock_parent_level: int = 2     # 父技能需要达到的等级才能解锁
    category: str = "general"        # 技能类别
    icon: str = "🎯"                 # 前端显示图标
    # 调度器权重加成：每级增加多少选择权重
    weight_bonus_per_level: float = 0.05


# ========== 预设技能树配置 ==========

TECH_LEAD_TREE: Dict[str, SkillNode] = {
    "root": SkillNode(
        id="root", name="技术顾问", description="技术方向总纲",
        level=1, max_level=1, current_xp=0, xp_required=[0],
        children_ids=["architecture", "code_review", "tech_selection"],
        category="root", icon="👨‍💻",
    ),
    "architecture": SkillNode(
        id="architecture", name="架构设计", description="系统架构设计与优化",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="root", children_ids=["cloud_native", "high_concurrency", "distributed"],
        category="architecture", icon="🏗️", weight_bonus_per_level=0.08,
    ),
    "cloud_native": SkillNode(
        id="cloud_native", name="云原生架构", description="Kubernetes、Docker、微服务",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="architecture", children_ids=["microservices", "container_orchestration"],
        unlock_parent_level=2, category="architecture", icon="☁️", weight_bonus_per_level=0.1,
    ),
    "microservices": SkillNode(
        id="microservices", name="微服务治理", description="服务拆分、服务网格、治理策略",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="cloud_native", category="architecture", icon="🔀", weight_bonus_per_level=0.12,
    ),
    "container_orchestration": SkillNode(
        id="container_orchestration", name="容器编排", description="K8s调度、资源管理、自动化部署",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="cloud_native", category="architecture", icon="📦", weight_bonus_per_level=0.1,
    ),
    "high_concurrency": SkillNode(
        id="high_concurrency", name="高并发设计", description="QPS优化、缓存策略、限流熔断",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="architecture", category="architecture", icon="⚡", weight_bonus_per_level=0.1,
    ),
    "distributed": SkillNode(
        id="distributed", name="分布式系统", description="CAP理论、一致性算法、分布式事务",
        level=1, max_level=5, xp_required=[120, 350, 700, 1100, 1600],
        parent_id="architecture", children_ids=["consistency"],
        unlock_parent_level=2, category="architecture", icon="🌐", weight_bonus_per_level=0.1,
    ),
    "consistency": SkillNode(
        id="consistency", name="一致性算法", description="Raft、Paxos、分布式锁",
        level=1, max_level=5, xp_required=[150, 400, 750, 1200, 1800],
        parent_id="distributed", category="architecture", icon="🔒", weight_bonus_per_level=0.12,
    ),
    "code_review": SkillNode(
        id="code_review", name="代码审查", description="代码质量、设计模式、重构",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["security_audit", "performance_opt"],
        category="code", icon="🔍", weight_bonus_per_level=0.06,
    ),
    "security_audit": SkillNode(
        id="security_audit", name="安全审计", description="漏洞扫描、安全编码、渗透测试",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="code_review", category="code", icon="🛡️", weight_bonus_per_level=0.1,
    ),
    "performance_opt": SkillNode(
        id="performance_opt", name="性能优化", description="Profiling、算法优化、内存管理",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="code_review", category="code", icon="🚀", weight_bonus_per_level=0.1,
    ),
    "tech_selection": SkillNode(
        id="tech_selection", name="技术选型", description="框架评估、数据库选型、中间件对比",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["database_selection", "framework_selection"],
        category="selection", icon="🎯", weight_bonus_per_level=0.06,
    ),
    "database_selection": SkillNode(
        id="database_selection", name="数据库选型", description="SQL/NoSQL、分库分表、索引优化",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="tech_selection", category="selection", icon="🗄️", weight_bonus_per_level=0.1,
    ),
    "framework_selection": SkillNode(
        id="framework_selection", name="框架选型", description="Spring/FastAPI/React/Vue 对比",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="tech_selection", category="selection", icon="📐", weight_bonus_per_level=0.1,
    ),
}


PRODUCT_MANAGER_TREE: Dict[str, SkillNode] = {
    "root": SkillNode(
        id="root", name="产品经理", description="产品方向总纲",
        level=1, max_level=1, current_xp=0, xp_required=[0],
        children_ids=["requirement_analysis", "competitive_analysis", "prd_writing", "user_research"],
        category="root", icon="👩‍💼",
    ),
    "requirement_analysis": SkillNode(
        id="requirement_analysis", name="需求分析", description="用户痛点挖掘、需求优先级排序",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["user_story", "priority_matrix"],
        category="analysis", icon="📊", weight_bonus_per_level=0.08,
    ),
    "user_story": SkillNode(
        id="user_story", name="用户故事", description="User Story、Acceptance Criteria",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="requirement_analysis", category="analysis", icon="📖", weight_bonus_per_level=0.1,
    ),
    "priority_matrix": SkillNode(
        id="priority_matrix", name="优先级矩阵", description="Kano模型、MoSCoW、RICE评分",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="requirement_analysis", category="analysis", icon="📈", weight_bonus_per_level=0.1,
    ),
    "competitive_analysis": SkillNode(
        id="competitive_analysis", name="竞品分析", description="SWOT、波特五力、竞品功能对比",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["market_positioning"],
        category="analysis", icon="🔭", weight_bonus_per_level=0.08,
    ),
    "market_positioning": SkillNode(
        id="market_positioning", name="市场定位", description="STP模型、差异化策略、蓝海战略",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="competitive_analysis", category="analysis", icon="🎯", weight_bonus_per_level=0.1,
    ),
    "prd_writing": SkillNode(
        id="prd_writing", name="PRD撰写", description="产品需求文档、原型说明、流程图",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["prototype_design"],
        category="document", icon="📝", weight_bonus_per_level=0.08,
    ),
    "prototype_design": SkillNode(
        id="prototype_design", name="原型设计", description="线框图、交互流程、UI规范",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="prd_writing", category="document", icon="🎨", weight_bonus_per_level=0.1,
    ),
    "user_research": SkillNode(
        id="user_research", name="用户研究", description="用户访谈、问卷设计、 personas",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["data_analysis"],
        category="research", icon="👥", weight_bonus_per_level=0.08,
    ),
    "data_analysis": SkillNode(
        id="data_analysis", name="数据分析", description="漏斗分析、留存分析、A/B测试",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="user_research", category="research", icon="📉", weight_bonus_per_level=0.1,
    ),
}


WRITER_TREE: Dict[str, SkillNode] = {
    "root": SkillNode(
        id="root", name="星尘织者", description="科幻创作总纲",
        level=1, max_level=1, current_xp=0, xp_required=[0],
        children_ids=["world_building", "narrative", "character_design"],
        category="root", icon="🌌",
    ),
    "world_building": SkillNode(
        id="world_building", name="世界观构建", description="物理规则、社会结构、历史沿革",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["hard_science", "alien_civilization"],
        category="creation", icon="🌍", weight_bonus_per_level=0.08,
    ),
    "hard_science": SkillNode(
        id="hard_science", name="硬科幻设定", description="科学原理、技术推演、物理约束",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="world_building", category="creation", icon="🔬", weight_bonus_per_level=0.12,
    ),
    "alien_civilization": SkillNode(
        id="alien_civilization", name="异星文明", description="非人类视角、外星生态、文明演化",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="world_building", category="creation", icon="👽", weight_bonus_per_level=0.12,
    ),
    "narrative": SkillNode(
        id="narrative", name="叙事技巧", description="长程叙事、多线结构、悬念设计",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["long_form", "multi_pov"],
        category="creation", icon="📚", weight_bonus_per_level=0.08,
    ),
    "long_form": SkillNode(
        id="long_form", name="长篇架构", description="三幕结构、章节节奏、伏笔回收",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="narrative", category="creation", icon="📜", weight_bonus_per_level=0.1,
    ),
    "multi_pov": SkillNode(
        id="multi_pov", name="多视角叙事", description="视角切换、信息差、群像刻画",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="narrative", category="creation", icon="🎭", weight_bonus_per_level=0.1,
    ),
    "character_design": SkillNode(
        id="character_design", name="角色塑造", description="人物弧光、动机系统、对话风格",
        level=1, max_level=5, xp_required=[80, 250, 500, 800, 1200],
        parent_id="root", children_ids=["dialogue_craft"],
        category="creation", icon="🎭", weight_bonus_per_level=0.08,
    ),
    "dialogue_craft": SkillNode(
        id="dialogue_craft", name="对话 craft", description="潜台词、口音差异、文化细节",
        level=1, max_level=5, xp_required=[100, 300, 600, 1000, 1500],
        parent_id="character_design", category="creation", icon="💬", weight_bonus_per_level=0.1,
    ),
}


# 角色 -> 技能树映射
ROLE_SKILL_TREES = {
    "tech_lead": TECH_LEAD_TREE,
    "product_manager": PRODUCT_MANAGER_TREE,
    "sci-fi novelist": WRITER_TREE,
}


def get_skill_tree(role: str) -> Dict[str, SkillNode]:
    """获取角色的技能树"""
    return ROLE_SKILL_TREES.get(role, {})


def get_default_tree() -> Dict[str, SkillNode]:
    """获取默认通用技能树"""
    return {
        "root": SkillNode(
            id="root", name="通用助手", description="通用能力",
            level=1, max_level=1, current_xp=0, xp_required=[0],
            children_ids=["reasoning", "communication"],
            category="root", icon="🤖",
        ),
        "reasoning": SkillNode(
            id="reasoning", name="逻辑推理", description="分析、归纳、演绎",
            level=1, max_level=5, xp_required=[50, 150, 300, 500, 800],
            parent_id="root", category="general", icon="🧠", weight_bonus_per_level=0.05,
        ),
        "communication": SkillNode(
            id="communication", name="沟通表达", description="清晰表达、换位思考、情绪感知",
            level=1, max_level=5, xp_required=[50, 150, 300, 500, 800],
            parent_id="root", category="general", icon="💬", weight_bonus_per_level=0.05,
        ),
    }
