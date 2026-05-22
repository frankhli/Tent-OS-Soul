"""Agent 调度器 —— Multi-Agent System 的核心大脑

负责：
1. 分析用户意图，判断是否需要子 Agent、需要几个
2. 智能选择最合适的 Agent（技能匹配 + 疲劳度 + 负载均衡）
3. 任务委派（单Agent / 多Agent并行 / 多Agent顺序协作）
4. 结果整合（多Agent输出合并为统一回复）
5. 动态生成高质量 Agent（超出预设模板范围）
"""

import json
import re
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from tent_os.soul.agent_models import AgentConfig, AgentSkill, AgentIdentity, get_role_template
from tent_os.soul.agent_runtime import AgentRuntimePool, AgentRuntime
from tent_os.soul.agent_manager import AgentManager
from tent_os.logging_config import get_logger

logger = get_logger()


class AgentOrchestrator:
    """Agent 调度器

    主 Agent 的调度中枢。所有用户消息先经过这里，
    Orchestrator 决定是自己处理还是委派给子 Agent。
    """

    def __init__(self, llm=None, agent_manager: AgentManager = None,
                 runtime_pool: AgentRuntimePool = None, skill_manager=None,
                 config: Dict = None):
        self.llm = llm
        self.agent_manager = agent_manager
        self.runtime_pool = runtime_pool
        self.skill_manager = skill_manager
        self.config = config or {}

    # ──────────────────────────────
    #  主入口
    # ──────────────────────────────

    async def handle_message(self, user_id: str, message: str,
                             context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户消息的主入口

        完整调度流程：
        1. 意图分析 → 判断需求类型、所需Agent数量、协作模式
        2. 如果需要子Agent → 选择最佳Agent(s) → 委派 → 整合
        3. 如果是创建Agent请求 → 直接处理
        4. 普通对话 → 主Agent直接回复

        Returns:
            {
                "type": "direct" | "delegated" | "multi_delegated" | "agent_created" | "error",
                "content": str,                    # 最终回复内容
                "intent": Dict,                    # 意图分析结果
                "delegations": List[Dict],         # 委派详情（如有）
                "synthesis": str,                  # 整合说明（如有）
                "trace": List[Dict],               # 调度轨迹（用于前端展示）
            }
        """
        context = context or {}
        trace = []

        # ── Step 1: 意图分析 ──
        t0 = datetime.now().isoformat()
        intent = await self._analyze_intent(message)
        trace.append({"step": "intent_analysis", "time": t0, "result": intent})
        logger.info(f"[Orchestrator] 意图分析: {intent.get('action')} | "
                    f"子Agent={intent.get('requires_sub_agent')} | "
                    f"数量={intent.get('agent_count', 1)}")

        # ── 情况 A: 创建/配置 Agent ──
        if intent.get("action") == "create_agent":
            result = await self._handle_create_agent_request(user_id, message, intent)
            result["intent"] = intent
            result["trace"] = trace
            return result

        # ── 情况 B: 需要子 Agent 处理 ──
        if intent.get("requires_sub_agent", False):
            agent_count = intent.get("agent_count", 1)
            collaboration = intent.get("collaboration_mode", "single")

            if agent_count == 1 or collaboration == "single":
                # 单 Agent 委派
                result = await self._delegate_single(
                    user_id=user_id, message=message,
                    intent=intent, context=context, trace=trace,
                )
            else:
                # 多 Agent 协作委派
                result = await self._delegate_multi(
                    user_id=user_id, message=message,
                    intent=intent, context=context, trace=trace,
                )
            result["intent"] = intent
            result["trace"] = trace
            return result

        # ── 情况 C: 普通对话，主 Agent 自己处理 ──
        return {
            "type": "direct",
            "content": None,  # 由上层调用主 Agent 的 chat 处理
            "intent": intent,
            "trace": trace,
        }

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 对象（处理 LLM 返回的杂散内容）"""
        text = text.strip()
        # 1. 先清理 markdown 代码块
        if text.startswith("```"):
            parts = text.split("```", 2)
            if len(parts) >= 3:
                text = parts[1]
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.strip()
        # 2. 用正则提取最外层的 JSON 对象
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        return None

    # ──────────────────────────────
    #  意图分析
    # ──────────────────────────────

    async def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """深度意图分析

        输出包含：
        - action: 动作类型
        - requires_sub_agent: 是否需要子Agent
        - agent_count: 需要几个Agent（1-N）
        - collaboration_mode: single | parallel | sequential
        - target_domains: 涉及领域列表
        - target_agent_name: 用户提到的具体Agent名
        - task_complexity: 复杂度 1-5
        - confidence: 置信度
        - reasoning: 分析理由
        """
        if not self.llm:
            return self._fallback_intent_analysis(message)

        prompt = f"""你是 Multi-Agent 调度系统的意图分析引擎。请分析用户输入，输出结构化调度决策。

【用户输入】
{message}

【输出格式】严格按以下 JSON 输出（只输出 JSON，不要 markdown）：
{{
    "action": "direct_chat | create_agent | delegate_task",
    "requires_sub_agent": true/false,
    "agent_count": 1-3,
    "collaboration_mode": "single | parallel | sequential",
    "target_domains": ["领域1", "领域2"],
    "target_agent_name": "用户提到的具体Agent名字，无则为空",
    "task_complexity": 1-5,
    "confidence": 0.0-1.0,
    "reasoning": "分析理由（50字内）"
}}

【判断规则】
1. action="create_agent"：用户在说"我要一个XX Agent""帮我创建""添加一个""给我设计一个"等
2. action="delegate_task"：用户在问专业问题（财务/技术/产品/市场/生活/法律/医疗/教育等）
3. action="direct_chat"：普通闲聊、情感倾诉、日常问候、简单事实问答

【agent_count 判断】
- 1：单一领域问题（如"帮我写个Python函数"）
- 2：跨两个领域（如"帮我设计一个APP，要考虑技术可行性"→产品+技术）
- 3：复杂项目需要多角色协作（如"我要创业做SaaS，帮我做商业计划"→产品+市场+财务）

【collaboration_mode 判断】
- single：一个Agent独立完成
- parallel：多个Agent各自独立分析，结果汇总
- sequential：Agent A 的输出作为 Agent B 的输入
"""
        try:
            result = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=600,
                thinking={"type": "disabled"},
            )
            json_str = self._extract_json(result)
            if not json_str:
                raise ValueError("无法从LLM输出中提取JSON")
            intent = json.loads(json_str)
            # 确保字段存在
            intent.setdefault("agent_count", 1)
            intent.setdefault("collaboration_mode", "single")
            intent.setdefault("target_domains", [intent.get("target_domain", "")])
            intent.setdefault("task_complexity", 3)
            return intent
        except Exception as e:
            logger.warning(f"[Orchestrator] LLM 意图分析失败: {e}，回退到关键词匹配")
            return self._fallback_intent_analysis(message)

    def _fallback_intent_analysis(self, message: str) -> Dict[str, Any]:
        """关键词回退分析（LLM不可用时）"""
        msg = message.lower()

        # 创建 Agent 关键词
        create_keywords = ["创建一个", "给我设计", "添加一个", "我要一个", "新建一个",
                           "帮我做一个", "给我配一个", "给我建一个", "agent", "助手"]
        for kw in create_keywords:
            if kw in msg:
                return {
                    "action": "create_agent",
                    "requires_sub_agent": False,
                    "agent_count": 0,
                    "collaboration_mode": "single",
                    "target_domains": [],
                    "target_agent_name": "",
                    "task_complexity": 1,
                    "confidence": 0.7,
                    "reasoning": "关键词匹配：用户想要创建 Agent",
                }

        # 多领域复杂任务关键词
        multi_domain_hints = {
            3: ["创业", "商业计划", "完整方案", "全套", "全流程", "从0到1"],
            2: ["技术实现", "产品设计", "营销方案", "推广策略", "成本分析"],
        }
        for count, kws in multi_domain_hints.items():
            for kw in kws:
                if kw in msg:
                    return self._build_delegate_intent(msg, agent_count=count)

        # 单一领域委派关键词
        return self._build_delegate_intent(msg, agent_count=1)

    def _build_delegate_intent(self, msg: str, agent_count: int = 1) -> Dict[str, Any]:
        """构建委派意图"""
        delegate_keywords = {
            "product": ["产品", "需求", "prd", "竞品", "用户调研", "功能设计", "原型", "用户体验"],
            "tech": ["代码", "架构", "技术", "编程", "bug", "优化", "数据库", "api", "算法", "python", "java", "javascript"],
            "finance": ["财务", "投资", "理财", "预算", "税务", "股票", "基金", "省钱", "成本", "利润", "估值"],
            "marketing": ["市场", "营销", "品牌", "推广", "增长", "获客", "投放", "seo", "内容", "运营"],
            "life": ["压力", "焦虑", "情绪", "时间管理", "健康", "睡眠", "人际关系", "心理", "困惑"],
            "legal": ["法律", "合同", "法规", "合规", "知识产权", "劳动法", "风险"],
            "writing": ["写作", "文案", "小说", "文章", "脚本", "故事", "诗歌", "编辑"],
        }
        matched_domains = []
        for domain, kws in delegate_keywords.items():
            for kw in kws:
                if kw in msg:
                    matched_domains.append(domain)
                    break

        if matched_domains:
            return {
                "action": "delegate_task",
                "requires_sub_agent": True,
                "agent_count": min(agent_count, len(matched_domains)) if matched_domains else agent_count,
                "collaboration_mode": "parallel" if agent_count > 1 else "single",
                "target_domains": matched_domains,
                "target_agent_name": "",
                "task_complexity": 3 if agent_count > 1 else 2,
                "confidence": 0.6 + 0.1 * len(matched_domains),
                "reasoning": f"关键词匹配：涉及 {', '.join(matched_domains)} 领域",
            }

        return {
            "action": "direct_chat",
            "requires_sub_agent": False,
            "agent_count": 0,
            "collaboration_mode": "single",
            "target_domains": [],
            "target_agent_name": "",
            "task_complexity": 1,
            "confidence": 0.5,
            "reasoning": "未匹配到专业领域关键词，视为普通对话",
        }

    # ──────────────────────────────
    #  Agent 选择
    # ──────────────────────────────

    async def _select_agents(self, intent: Dict, user_id: str,
                             max_agents: int = 3) -> List[AgentConfig]:
        """智能选择最合适的 Agent 列表

        评分维度：
        1. 领域匹配度（role 匹配 target_domains）
        2. 技能相关度（skills 名称与任务关键词匹配）
        3. 疲劳度惩罚（fatigue 越高，分数越低）
        4. 当前负载惩罚（task_load 越高，分数越低）
        5. 最近活跃奖励（最近活跃的Agent更了解上下文）

        Returns:
            按匹配度排序的 AgentConfig 列表
        """
        agents = self.agent_manager.list_agents(created_by=user_id)
        if not agents:
            return []

        domains = intent.get("target_domains", [])
        name_hint = intent.get("target_agent_name", "")
        task_complexity = intent.get("task_complexity", 3)

        # 领域 → role 映射
        domain_role_map = {
            "product": ["product_manager"],
            "tech": ["tech_lead"],
            "finance": ["finance_advisor"],
            "marketing": ["marketing"],
            "life": ["life_coach"],
        }
        target_roles = []
        for d in domains:
            target_roles.extend(domain_role_map.get(d, []))

        scored = []
        for agent in agents:
            score = 0.0
            reasons = []

            # 1. 领域匹配
            if agent.role in target_roles:
                score += 0.4
                reasons.append(f"role匹配({agent.role})")

            # 2. 名字匹配
            if name_hint and (name_hint in agent.name or name_hint in agent.role):
                score += 0.3
                reasons.append("名字匹配")

            # 3. 技能相关度（原有skills + 技能树加成）
            if domains and agent.skills:
                for skill in agent.skills:
                    for domain in domains:
                        domain_kws = self._get_domain_keywords(domain)
                        if any(kw in skill.name for kw in domain_kws):
                            _orch_cfg = self.config.get("thresholds", {}).get("agent_orchestrator", {})
                            score += _orch_cfg.get("skill_match_score", 0.15) * skill.level
                            reasons.append(f"技能匹配({skill.name})")
            
            # 3.5 技能树权重加成（P4: Agent成长系统）
            if self.skill_manager:
                try:
                    bonus = self.skill_manager.get_skill_weight_bonus(agent.id)
                    score += bonus
                    if bonus > 0.1:
                        reasons.append(f"技能树加成+{bonus:.2f}")
                except Exception:
                    pass

            # 4. 运行时状态惩罚/奖励
            runtime = self.runtime_pool.get(agent.id)
            if runtime:
                state = runtime.state
                # 疲劳度惩罚
                fatigue_penalty = state.fatigue * 0.2
                score -= fatigue_penalty
                # 负载惩罚
                load_penalty = min(state.task_load * 0.1, 0.3)
                score -= load_penalty
                # 成功率奖励
                score += state.success_rate * 0.05
                if fatigue_penalty > 0.1:
                    reasons.append(f"疲劳-{fatigue_penalty:.2f}")
                if load_penalty > 0.05:
                    reasons.append(f"负载-{load_penalty:.2f}")

            scored.append({"agent": agent, "score": max(score, 0.05), "reasons": reasons})

        # 按分数降序排序
        scored.sort(key=lambda x: x["score"], reverse=True)

        # 选取 top N，确保不超过 max_agents
        count = min(intent.get("agent_count", 1), max_agents, len(scored))
        selected = [s["agent"] for s in scored[:count]]

        logger.info(f"[Orchestrator] 选中 {len(selected)} 个Agent: " +
                    ", ".join([f"{a.name}({scored[i]['score']:.2f})" for i, a in enumerate(selected)]))
        return selected
    
    def _reward_xp_after_task(self, agent_id: str, intent: Dict, result: Dict):
        """任务完成后奖励 XP（P4: Agent成长系统）"""
        if not self.skill_manager:
            return
        try:
            task_type = intent.get("target_domains", ["general"])[0]
            # 根据任务结果质量计算系数
            quality = 1.0
            if result.get("type") == "delegated":
                content = result.get("content", "")
                # 内容越长、结构越完整，质量越高（简单启发式）
                quality = min(1.0 + len(content) / 5000, 2.0)
            upgrades = self.skill_manager.add_xp_by_task(agent_id, task_type, quality)
            if upgrades:
                for up in upgrades:
                    logger.info(f"[Orchestrator] 🎉 {agent_id} 升级: {up['skill_name']} {up['old_level']}→{up['new_level']}")
        except Exception as e:
            logger.debug(f"[Orchestrator] XP奖励失败: {e}")

    def _get_domain_keywords(self, domain: str) -> List[str]:
        """获取领域的关联关键词"""
        keywords = {
            "product": ["产品", "需求", "用户", "设计", "体验", "功能", "竞品", "分析"],
            "tech": ["技术", "代码", "架构", "编程", "开发", "系统", "算法", "数据库"],
            "finance": ["财务", "投资", "理财", "预算", "成本", "税务", "股票", "基金"],
            "marketing": ["市场", "营销", "品牌", "推广", "增长", "获客", "内容", "运营"],
            "life": ["情绪", "心理", "健康", "时间", "人际", "压力", "睡眠", "生活"],
            "legal": ["法律", "合同", "法规", "合规", "知识产权", "风险"],
            "writing": ["写作", "文案", "小说", "文章", "创作", "编辑", "故事"],
        }
        return keywords.get(domain, [domain])

    # ──────────────────────────────
    #  单 Agent 委派
    # ──────────────────────────────

    async def _delegate_single(self, user_id: str, message: str,
                               intent: Dict, context: Dict,
                               trace: List[Dict]) -> Dict[str, Any]:
        """委派任务给单个 Agent"""
        # 1. 选择最佳 Agent
        agents = await self._select_agents(intent, user_id, max_agents=1)
        agent = agents[0] if agents else None

        # 2. 没有合适 Agent → 动态创建
        if not agent:
            domain = intent.get("target_domains", ["通用"])[0]
            logger.info(f"[Orchestrator] 未找到合适Agent，动态创建 domain={domain}")
            create_result = await self._generate_agent_with_llm(
                user_id, f"帮我创建一位{domain}领域的专家Agent"
            )
            trace.append({"step": "auto_create_agent", "result": create_result})
            if create_result.get("type") == "agent_created":
                agent = self.agent_manager.get_agent(create_result["agent"]["id"])
            else:
                return {
                    "type": "error",
                    "content": "没有找到合适的 Agent，自动创建也失败了。你可以先手动创建一个。",
                    "trace": trace,
                }

        # 3. 执行委派
        runtime = self.runtime_pool.get_or_create(agent)
        delegation = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_role": agent.role,
            "task": message,
            "start_time": datetime.now().isoformat(),
        }

        result = await runtime.run(
            task=message,
            context={
                "user_intent": intent.get("reasoning", ""),
                "delegated_by": "主Agent",
                "task_complexity": intent.get("task_complexity", 2),
                **context,
            },
        )

        delegation["end_time"] = datetime.now().isoformat()
        delegation["result"] = result.get("content", "")[:500]
        delegation["status"] = "error" if result.get("error") else "success"
        trace.append({"step": "delegate_single", "agent": agent.name, "status": delegation["status"]})

        # 4. 任务完成后奖励 XP（P4: Agent成长系统）
        self._reward_xp_after_task(agent.id, intent, {
            "type": "delegated",
            "content": result.get("content", ""),
        })
        
        # 5. 构建返回
        return {
            "type": "delegated",
            "content": result.get("content", ""),
            "agent_id": agent.id,
            "agent_name": agent.name,
            "task": message,
            "delegations": [delegation],
            "trace": trace,
        }

    # ──────────────────────────────
    #  多 Agent 协作委派
    # ──────────────────────────────

    async def _delegate_multi(self, user_id: str, message: str,
                              intent: Dict, context: Dict,
                              trace: List[Dict]) -> Dict[str, Any]:
        """委派任务给多个 Agent 并行协作

        流程：
        1. 选择 N 个最佳 Agent
        2. 并行执行（每个Agent独立分析同一任务，从不同角度）
        3. 收集所有结果
        4. LLM 整合为多Agent联合回复
        """
        # 1. 选择 Agent
        agents = await self._select_agents(intent, user_id)
        if not agents:
            # 降级为单Agent处理
            logger.warning("[Orchestrator] 多Agent委派无可用Agent，降级为单Agent")
            intent["agent_count"] = 1
            intent["collaboration_mode"] = "single"
            return await self._delegate_single(user_id, message, intent, context, trace)

        # 2. 并行委派
        delegations = []
        tasks = []
        for idx, agent in enumerate(agents):
            runtime = self.runtime_pool.get_or_create(agent)
            # 为每个Agent定制任务描述（强调其专业角度）
            angle_prompt = self._build_agent_angle_prompt(agent, message, idx, len(agents))
            tasks.append(self._run_agent_with_timeout(
                runtime, angle_prompt, agent, message, context, intent, trace
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 收集结果
        agent_outputs = []
        for i, res in enumerate(results):
            agent = agents[i]
            if isinstance(res, Exception):
                agent_outputs.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "content": f"[{agent.name}] 执行出错: {res}",
                    "status": "error",
                })
                delegations.append({
                    "agent_id": agent.id, "agent_name": agent.name,
                    "task": message, "status": "error",
                    "error": str(res),
                })
            else:
                agent_outputs.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "content": res.get("content", ""),
                    "status": "success",
                })
                delegations.append({
                    "agent_id": agent.id, "agent_name": agent.name,
                    "task": message, "status": "success",
                    "result": res.get("content", "")[:500],
                })

        trace.append({"step": "delegate_multi", "agent_count": len(agents),
                      "results": [{"name": o["agent_name"], "status": o["status"]} for o in agent_outputs]})

        # 4. 整合结果
        synthesis = await self._synthesize_results(message, agent_outputs, intent)
        trace.append({"step": "synthesize", "synthesis_length": len(synthesis)})

        return {
            "type": "multi_delegated",
            "content": synthesis,
            "agent_outputs": agent_outputs,
            "delegations": delegations,
            "synthesis": synthesis,
            "trace": trace,
        }

    async def _run_agent_with_timeout(self, runtime: AgentRuntime, angle_prompt: str,
                                       agent: AgentConfig, original_message: str,
                                       context: Dict, intent: Dict, trace: List[Dict],
                                       timeout: int = 120) -> Dict[str, Any]:
        """运行Agent并设置超时"""
        try:
            return await asyncio.wait_for(
                runtime.run(
                    task=angle_prompt,
                    context={
                        "user_intent": intent.get("reasoning", ""),
                        "delegated_by": "主Agent",
                        "task_complexity": intent.get("task_complexity", 3),
                        "original_message": original_message,
                        **context,
                    },
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Orchestrator] Agent {agent.name} 执行超时")
            return {
                "content": f"[{agent.name}] 思考超时了，没能及时完成分析。",
                "agent_id": agent.id,
                "agent_name": agent.name,
                "error": "timeout",
            }

    def _build_agent_angle_prompt(self, agent: AgentConfig, message: str,
                                   idx: int, total: int) -> str:
        """为每个Agent构建带角度提示的任务描述"""
        angle_hints = {
            "product_manager": "请从【产品需求与用户体验】角度分析：",
            "tech_lead": "请从【技术实现与架构设计】角度分析：",
            "finance_advisor": "请从【财务成本与投资回报】角度分析：",
            "marketing": "请从【市场推广与用户增长】角度分析：",
            "life_coach": "请从【个人成长与身心健康】角度分析：",
        }
        angle = angle_hints.get(agent.role, f"请从【{agent.name}的专业角度】分析：")
        return f"{angle}\n\n{message}"

    # ──────────────────────────────
    #  结果整合
    # ──────────────────────────────

    async def _synthesize_results(self, original_message: str,
                                   agent_outputs: List[Dict],
                                   intent: Dict) -> str:
        """将多Agent的输出整合为统一回复

        策略：
        1. 如果只有一个有效输出 → 直接返回
        2. 如果有LLM → 让LLM做专业整合
        3. 如果LLM不可用 → 简单拼接 + 格式化
        """
        valid_outputs = [o for o in agent_outputs if o.get("status") == "success" and o.get("content")]
        if not valid_outputs:
            return "抱歉，Agent 团队在处理这个任务时遇到了问题，没有获得有效结果。"
        if len(valid_outputs) == 1:
            return valid_outputs[0]["content"]

        if not self.llm:
            # 无LLM时简单拼接
            parts = [f"### {o['agent_name']} 的分析\n\n{o['content']}\n" for o in valid_outputs]
            return f"【多 Agent 联合分析】\n\n{'---\n'.join(parts)}"

        # 用LLM整合
        synthesis_prompt = f"""你是多Agent协作系统的结果整合专家。请将多位Agent的分析整合为一份统一、连贯、有结构的回复。

【用户原始问题】
{original_message}

【各位Agent的分析】
"""
        for o in valid_outputs:
            synthesis_prompt += f"\n--- {o['agent_name']} ---\n{o['content']}\n"

        synthesis_prompt += """

【整合要求】
1. 综合各位Agent的观点，去重合并
2. 如果观点有冲突，客观呈现不同角度
3. 给出结构化的最终建议（分点列出）
4. 语气专业但不生硬，像一位资深顾问在汇报
5. 在开头简要说明"这是XX位Agent联合分析的结果"
6. 不要简单罗列，要有机整合
"""
        try:
            synthesis = await self.llm.chat(
                [{"role": "user", "content": synthesis_prompt}],
                temperature=0.5, max_tokens=4000,
                thinking={"type": "disabled"},
            )
            return synthesis.strip()
        except Exception as e:
            logger.warning(f"[Orchestrator] LLM 结果整合失败: {e}，降级为简单拼接")
            parts = [f"### {o['agent_name']}\n\n{o['content']}\n" for o in valid_outputs]
            return f"【多 Agent 联合分析】\n\n{'---\n'.join(parts)}"

    # ──────────────────────────────
    #  创建 Agent 处理
    # ──────────────────────────────

    async def _handle_create_agent_request(self, user_id: str, message: str,
                                           intent: Dict) -> Dict[str, Any]:
        """处理创建 Agent 的请求"""
        # 先检查是否匹配已有模板
        templates = {
            "产品经理": "product_manager", "产品": "product_manager",
            "技术": "tech_lead", "程序员": "tech_lead", "开发": "tech_lead",
            "财务": "finance_advisor", "理财": "finance_advisor", "投资": "finance_advisor",
            "市场": "marketing", "营销": "marketing",
            "生活": "life_coach", "心理": "life_coach", "情绪": "life_coach",
        }
        matched_template = None
        for name, key in templates.items():
            if name in message:
                matched_template = key
                break

        if matched_template:
            agent = self.agent_manager.create_from_template(
                template_key=matched_template,
                created_by=user_id,
            )
            if agent:
                self.runtime_pool.get_or_create(agent)
                return {
                    "type": "agent_created",
                    "agent": agent.to_dict(),
                    "content": f"已为你创建「{agent.name}」，现在可以开始使用啦！",
                }

        # 动态生成 Agent
        return await self._generate_agent_with_llm(user_id, message)

    async def _generate_agent_with_llm(self, user_id: str, message: str) -> Dict[str, Any]:
        """用 LLM 动态生成高质量 Agent 配置"""
        if not self.llm:
            return {
                "type": "error",
                "content": "LLM 未配置，无法动态生成 Agent。请使用预设模板创建。",
            }

        prompt = f"""你是一位专业的 AI Agent 设计师。用户想要创建一个新的 AI Agent，请根据用户的描述，生成一份高质量的 Agent 配置文件。

用户需求：{message}

【重要】你必须只输出以下格式的纯 JSON，不要任何解释、思考过程、markdown代码块标记或其他文字：
{{"name":"名称","role":"english_role","system_prompt":"200-500字的角色定义","identity":{{"personality":"性格","avatar_emotion":"calm"}},"skills":[{{"name":"技能1","level":0.85,"description":"描述"}}],"tools_allowed":["web_search"],"reasoning":"设计理由"}}

设计原则：
1. system_prompt 要写得像真人一样，有温度、有特点
2. 技能要具体，不要泛泛而谈
3. 性格要有记忆点
4. 工具选择要符合角色实际需要
"""
        try:
            result = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=2000,
                thinking={"type": "disabled"},
            )
            json_str = self._extract_json(result)
            if not json_str:
                raise ValueError("无法从LLM输出中提取JSON")
            config_data = json.loads(json_str)

            agent = AgentConfig.create(
                name=config_data["name"],
                role=config_data["role"],
                created_by=user_id,
                system_prompt=config_data["system_prompt"],
                tools_allowed=config_data.get("tools_allowed", []),
                identity=config_data.get("identity", {}),
                skills=config_data.get("skills", []),
            )
            agent = self.agent_manager.create_agent(agent)
            self.runtime_pool.get_or_create(agent)

            return {
                "type": "agent_created",
                "agent": agent.to_dict(),
                "content": f"已为你专属设计「{agent.name}」！{config_data.get('reasoning', '')}",
                "design_notes": config_data.get("reasoning", ""),
            }

        except Exception as e:
            logger.error(f"[Orchestrator] 动态生成 Agent 失败: {e}")
            return {
                "type": "error",
                "content": f"生成 Agent 时出错了：{e}。你可以尝试用更具体的描述，或者选择预设模板。",
            }

    # ──────────────────────────────
    #  公开 API
    # ──────────────────────────────

    async def generate_agent_from_description(self, user_id: str, description: str) -> Dict[str, Any]:
        """公开方法：根据描述生成 Agent（供前端直接调用）"""
        return await self._generate_agent_with_llm(user_id, description)

    def get_team_status(self, user_id: str = "") -> Dict[str, Any]:
        """获取 Agent 团队整体状态

        Returns:
            {
                "agents": [Agent运行时状态列表],
                "summary": {"total", "busy", "idle", "avg_fatigue"},
            }
        """
        agents = self.agent_manager.list_agents(created_by=user_id)
        agent_statuses = []
        busy_count = 0
        idle_count = 0
        total_fatigue = 0.0

        for agent in agents:
            runtime = self.runtime_pool.get(agent.id)
            if runtime:
                stats = runtime.get_stats()
                agent_statuses.append(stats)
                if stats.get("status") == "busy":
                    busy_count += 1
                else:
                    idle_count += 1
                total_fatigue += stats.get("fatigue", 0)
            else:
                agent_statuses.append({
                    "agent_id": agent.id,
                    "name": agent.name,
                    "status": "offline",
                    "fatigue": 0,
                    "task_load": 0,
                    "total_tasks": 0,
                })
                idle_count += 1

        total = len(agents)
        return {
            "agents": agent_statuses,
            "summary": {
                "total": total,
                "busy": busy_count,
                "idle": idle_count,
                "offline": total - busy_count - idle_count,
                "avg_fatigue": round(total_fatigue / total, 2) if total > 0 else 0,
            },
        }

    # ──────────────────────────────
    #  P3: Agent 会议室
    # ──────────────────────────────

    async def start_meeting(self, room_id: str, topic: str,
                            participant_ids: List[str],
                            rounds: int = 2) -> Dict[str, Any]:
        """启动 Agent 会议室讨论

        流程：
        1. 主持人开场（确定讨论框架）
        2. 每轮：各Agent依次发言（基于前面所有发言）
        3. 主持人总结 → 生成结构化纪要
        """
        room = self.agent_manager.get_room(room_id)
        if not room:
            return {"type": "error", "content": "会议室不存在"}

        # 更新会议室状态为进行中
        self.agent_manager.update_room(room_id, status="active")

        # 加载参与者
        participants = []
        for pid in participant_ids:
            agent = self.agent_manager.get_agent(pid)
            if agent:
                participants.append(agent)

        if not participants:
            return {"type": "error", "content": "没有有效的参与者"}

        # 主持人开场（让第一个Agent或LLM做开场）
        host_agent = participants[0]
        host_opening = await self._generate_host_opening(topic, participants)
        self.agent_manager.add_message(
            room_id=room_id,
            from_agent_id="host",
            content=host_opening,
            message_type="system",
        )

        all_messages = [{"agent": "主持人", "content": host_opening}]

        # 多轮讨论
        for round_num in range(1, rounds + 1):
            round_results = await self._run_meeting_round(
                room_id, topic, round_num, participants, all_messages
            )
            all_messages.extend(round_results)

        # 生成纪要
        summary = await self._generate_meeting_summary(topic, all_messages)

        # 保存纪要到会议室
        self.agent_manager.update_room(room_id, status="closed", summary=summary)

        # P5: 记录协作关系（所有参与者两两之间）
        try:
            pids = [p.id for p in participants]
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    self.agent_manager.record_collaboration(
                        agent_a_id=pids[i],
                        agent_b_id=pids[j],
                        room_id=room_id,
                        task_type="meeting",
                        result="success",
                        quality_score=0.7,
                    )
        except Exception as e:
            logger.debug(f"[Orchestrator] 协作记录失败: {e}")

        # 添加系统消息标记会议结束
        self.agent_manager.add_message(
            room_id=room_id,
            from_agent_id="host",
            content=f"【会议结束】\n\n{summary}",
            message_type="summary",
        )

        return {
            "type": "meeting_completed",
            "room_id": room_id,
            "topic": topic,
            "rounds": rounds,
            "messages": all_messages,
            "summary": summary,
        }

    async def _generate_host_opening(self, topic: str,
                                      participants: List[AgentConfig]) -> str:
        """生成主持人开场白"""
        participant_desc = "、".join([
            f"{p.name}（{p.role}）" for p in participants
        ])
        if not self.llm:
            return f"今天讨论的主题是「{topic}」。参与的Agent有：{participant_desc}。请大家依次发表观点。"

        prompt = f"""你是Agent会议室的主持人。请为以下讨论生成一段简短有力的开场白（100字内）。

主题：{topic}
参与者：{participant_desc}

要求：
1. 简要说明讨论目的
2. 提示各位Agent从自己的专业角度发言
3. 简短、有号召力
"""
        try:
            opening = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.6, max_tokens=300,
                thinking={"type": "disabled"},
            )
            return opening.strip()
        except Exception as e:
            logger.warning(f"[Meeting] 开场白生成失败: {e}")
            return f"今天讨论的主题是「{topic}」。请各位专家从自己的专业角度发表看法。"

    async def _run_meeting_round(self, room_id: str, topic: str,
                                  round_num: int,
                                  participants: List[AgentConfig],
                                  history: List[Dict]) -> List[Dict]:
        """执行一轮讨论"""
        round_results = []

        # 构建本轮上下文字符串
        context = f"【第{round_num}轮讨论】\n\n主题：{topic}\n\n"
        if history:
            context += "前面的发言：\n"
            for h in history[-10:]:  # 只取最近10条
                context += f"{h['agent']}：{h['content'][:200]}...\n"

        for agent in participants:
            runtime = self.runtime_pool.get_or_create(agent)

            # 为每个Agent构建带轮次提示的任务
            task = (
                f"{context}\n\n"
                f"现在轮到你了。请从【{agent.name}（{agent.role}）】的专业角度，"
                f"针对「{topic}」发表你的看法。"
            )
            if round_num > 1:
                task += "可以回应前面Agent的观点，提出补充或不同意见。"

            try:
                result = await asyncio.wait_for(
                    runtime.run(task, context={"meeting_round": round_num, "topic": topic}),
                    timeout=120,
                )
                content = result.get("content", "")
            except asyncio.TimeoutError:
                content = f"[{agent.name}] 本轮思考超时。"

            # 持久化到会议室消息
            self.agent_manager.add_message(
                room_id=room_id,
                from_agent_id=agent.id,
                content=content,
                message_type="text",
            )

            round_results.append({
                "round": round_num,
                "agent": agent.name,
                "agent_id": agent.id,
                "content": content,
            })

        return round_results

    async def _generate_meeting_summary(self, topic: str,
                                         messages: List[Dict]) -> str:
        """生成会议纪要"""
        if not self.llm:
            # 无LLM时简单拼接
            lines = [f"### {m['agent']}\n{m['content'][:300]}" for m in messages]
            return f"【{topic}会议纪要】\n\n" + "\n\n".join(lines)

        transcript = f"会议主题：{topic}\n\n"
        for m in messages:
            transcript += f"【{m['agent']}】\n{m['content']}\n\n"

        prompt = f"""请将以下Agent讨论记录整理为一份结构化会议纪要。

{transcript}

请按以下格式输出：
1. 讨论主题
2. 各方核心观点（分点列出，标注提出者）
3. 共识与分歧
4. 后续行动建议

要求：条理清晰、去重合并、不遗漏关键观点。"""

        try:
            summary = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4, max_tokens=3000,
                thinking={"type": "disabled"},
            )
            return summary.strip()
        except Exception as e:
            logger.warning(f"[Meeting] 纪要生成失败: {e}")
            lines = [f"- {m['agent']}：{m['content'][:200]}" for m in messages]
            return f"【{topic}会议纪要】\n\n" + "\n".join(lines)

    # ──────────────────────────────
    #  P4: Agent 心跳与自治
    # ──────────────────────────────

    async def run_heartbeat(self, user_id: str = "") -> Dict[str, Any]:
        """运行所有 Agent 的心跳自检

        每个Agent检查：
        1. 疲劳度（近期任务量）
        2. 技能成长（使用频率→等级提升）
        3. 主动建议（基于最近任务内容）

        Returns:
            {"checks": [...], "suggestions": [...]}
        """
        agents = self.agent_manager.list_agents(created_by=user_id)
        checks = []
        suggestions = []

        for agent in agents:
            runtime = self.runtime_pool.get_or_create(agent)

            check = self._agent_self_check(agent, runtime)
            checks.append(check)

            # 生成主动建议
            if check.get("suggestion"):
                suggestions.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "type": check["status"],
                    "message": check["suggestion"],
                })

        return {
            "checks": checks,
            "suggestions": suggestions,
            "timestamp": datetime.now().isoformat(),
        }

    def _agent_self_check(self, agent: AgentConfig,
                          runtime: AgentRuntime) -> Dict[str, Any]:
        """单个Agent自检"""
        stats = runtime.get_stats()
        state = runtime.state

        # 1. 疲劳度评估
        fatigue = state.fatigue
        recent_tasks = state.total_tasks

        # 自动降低疲劳（休息效应）
        if fatigue > 0:
            state.fatigue = max(0, fatigue - 0.05)

        # 2. 技能成长
        skill_updates = []
        for skill in agent.skills:
            if skill.experience_count > 0:
                # 每5次经验提升0.01等级，上限0.95
                level_gain = min(skill.experience_count // 5 * 0.01, 0.95 - skill.level)
                if level_gain > 0:
                    skill.level += level_gain
                    skill_updates.append({
                        "name": skill.name,
                        "new_level": round(skill.level, 2),
                    })

        # 3. 状态判定
        if fatigue > 0.7:
            status = "exhausted"
            suggestion = f"{agent.name} 已经连续处理了很多任务，建议让它休息一下。"
        elif fatigue > 0.4:
            status = "tired"
            suggestion = f"{agent.name} 有些疲劳了，可以适当减轻任务负载。"
        elif recent_tasks > 20 and skill_updates:
            status = "growing"
            skills_str = "、".join([s["name"] for s in skill_updates])
            suggestion = f"{agent.name} 的 {skills_str} 技能有所提升！"
        else:
            status = "healthy"
            suggestion = ""

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "status": status,
            "fatigue": round(fatigue, 2),
            "task_load": state.task_load,
            "total_tasks": recent_tasks,
            "skill_updates": skill_updates,
            "suggestion": suggestion,
        }

    async def generate_team_suggestion(self, user_id: str = "") -> str:
        """生成团队级主动建议（给用户推送）"""
        team_status = self.get_team_status(user_id)
        heartbeat = await self.run_heartbeat(user_id)

        if not self.llm:
            suggestions = [s["message"] for s in heartbeat.get("suggestions", [])]
            return "\n".join(suggestions) if suggestions else "团队状态良好。"

        prompt = f"""你是Agent团队的管家。基于以下团队状态，给用户生成一段温馨的主动建议（100字内）。

团队概况：
- 总Agent数：{team_status['summary']['total']}
- 忙碌：{team_status['summary']['busy']}，空闲：{team_status['summary']['idle']}
- 平均疲劳度：{team_status['summary']['avg_fatigue']}%

自检结果：
"""
        for check in heartbeat.get("checks", []):
            prompt += f"- {check['agent_name']}: 状态={check['status']}, 疲劳={check['fatigue']}, 任务={check['total_tasks']}\n"

        prompt += """
要求：
1. 语气像一位贴心的管家，温暖但不啰嗦
2. 如果有Agent疲劳，提醒用户让它休息
3. 如果有技能成长，恭喜用户
4. 如果一切正常，给一句鼓励
"""
        try:
            suggestion = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.6, max_tokens=300,
                thinking={"type": "disabled"},
            )
            return suggestion.strip()
        except Exception as e:
            logger.warning(f"[Heartbeat] 建议生成失败: {e}")
            return "Agent团队正在正常运转。"
