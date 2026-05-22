"""Agent 运行时 —— 每个 Agent 的独立执行环境"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from tent_os.soul.agent_models import AgentConfig, AgentState, AgentIdentity
from tent_os.soul.agent_memory import AgentMemoryStore
from tent_os.logging_config import get_logger

logger = get_logger()


class AgentRuntime:
    """Agent 运行时

    每个 Agent 拥有独立的：
    - 记忆存储
    - 情绪状态
    - 工具执行上下文
    - 运行状态
    """

    def __init__(self, config: AgentConfig, llm=None, tool_executor=None):
        self.config = config
        self.llm = llm
        self.tool_executor = tool_executor
        self.memory = AgentMemoryStore(config.id)
        self.state = AgentState()
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history = 20

    @property
    def agent_id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    def build_system_prompt(self) -> str:
        """构建该 Agent 的 system prompt"""
        parts = []

        # 核心角色定义
        base = self.config.system_prompt or f"你是一位{self.config.name}。"
        parts.append(base)

        # 身份信息
        identity = self.config.identity
        if identity.name or identity.personality:
            id_parts = []
            if identity.name:
                id_parts.append(f"你的名字是{identity.name}")
            if identity.personality:
                id_parts.append(f"性格特点：{identity.personality}")
            parts.append("".join(id_parts))

        # 技能列表
        if self.config.skills:
            skill_text = "；".join([
                f"{s.name}（{s.description}）"
                for s in self.config.skills
            ])
            parts.append(f"你的专长：{skill_text}")

        # 工具能力
        if self.config.tools_allowed:
            parts.append(f"你可以使用的工具：{', '.join(self.config.tools_allowed)}")

        # 记忆上下文（最近的相关记忆）
        recent_memories = self.memory.get_recent(3)
        if recent_memories:
            mem_text = "\n".join([f"- {m['abstract'][:100]}" for m in recent_memories])
            parts.append(f"你最近记住的事情：\n{mem_text}")

        return "\n\n".join(parts)

    async def run(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行一次任务

        Args:
            task: 任务描述
            context: 额外上下文（如用户原始需求、其他 Agent 的输出等）

        Returns:
            {content: str, tool_calls: [...], memory_ingested: bool}
        """
        context = context or {}

        # 更新状态
        self.state.status = "busy"
        self.state.task_load += 1
        self.state.last_active = datetime.now().isoformat()

        try:
            # 构建消息
            system_prompt = self.build_system_prompt()
            messages = [{"role": "system", "content": system_prompt}]

            # 添加历史对话
            for msg in self._conversation_history[-self._max_history:]:
                messages.append(msg)

            # 添加上下文
            ctx_text = ""
            if context.get("user_intent"):
                ctx_text += f"用户需求：{context['user_intent']}\n"
            if context.get("delegated_by"):
                ctx_text += f"这是主 Agent '{context['delegated_by']}' 委派给你的任务。\n"
            if context.get("previous_results"):
                ctx_text += f"其他 Agent 的参考意见：{context['previous_results']}\n"

            user_msg = ctx_text + f"任务：{task}"
            messages.append({"role": "user", "content": user_msg})

            # 调用 LLM
            if self.llm and hasattr(self.llm, 'chat'):
                reply = await self.llm.chat(messages, temperature=0.7, max_tokens=4096)
            else:
                reply = f"[{self.name}] 收到任务：{task}\n\n（LLM 未配置，这是模拟回复）"

            # 保存对话到历史
            self._conversation_history.append({"role": "user", "content": user_msg})
            self._conversation_history.append({"role": "assistant", "content": reply})

            # 保存到记忆
            await self.memory.ingest(
                content=f"任务：{task}\n回复：{reply}",
                uri=f"task/{datetime.now().isoformat()}",
                memory_type="task_execution",
                metadata={"agent_id": self.agent_id, "task": task[:100]}
            )

            # 更新技能经验
            for skill in self.config.skills:
                skill.experience_count += 1

            # 更新状态
            self.state.total_tasks += 1
            self.state.status = "idle"
            self.state.task_load = max(0, self.state.task_load - 1)

            return {
                "content": reply,
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "memory_ingested": True,
            }

        except Exception as e:
            logger.error(f"[AgentRuntime:{self.agent_id}] 执行失败: {e}")
            self.state.status = "idle"
            self.state.task_load = max(0, self.state.task_load - 1)
            return {
                "content": f"抱歉，我在处理这个任务时遇到了问题：{e}",
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "error": str(e),
            }

    async def chat(self, message: str) -> str:
        """简单的对话模式（不走完整任务流程）"""
        result = await self.run(message)
        return result.get("content", "")

    def get_stats(self) -> Dict[str, Any]:
        """获取运行时统计"""
        mem_stats = self.memory.get_stats()
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.state.status,
            "fatigue": self.state.fatigue,
            "task_load": self.state.task_load,
            "total_tasks": self.state.total_tasks,
            "success_rate": self.state.success_rate,
            "memory_count": mem_stats["l0_count"],
            "skills": [
                {"name": s.name, "level": s.level, "experience": s.experience_count}
                for s in self.config.skills
            ],
        }


class AgentRuntimePool:
    """Agent 运行时池 —— 管理所有 Agent 的运行时实例"""

    def __init__(self):
        self.runtimes: Dict[str, AgentRuntime] = {}
        self._llm = None
        self._tool_executor = None

    def set_dependencies(self, llm=None, tool_executor=None):
        """设置全局依赖"""
        self._llm = llm
        self._tool_executor = tool_executor

    def get_or_create(self, config: AgentConfig) -> AgentRuntime:
        """获取或创建运行时"""
        if config.id not in self.runtimes:
            self.runtimes[config.id] = AgentRuntime(
                config=config,
                llm=self._llm,
                tool_executor=self._tool_executor,
            )
            logger.info(f"[AgentRuntimePool] 创建运行时: {config.name} ({config.id})")
        return self.runtimes[config.id]

    def get(self, agent_id: str) -> Optional[AgentRuntime]:
        """获取运行时"""
        return self.runtimes.get(agent_id)

    def remove(self, agent_id: str):
        """移除运行时"""
        if agent_id in self.runtimes:
            del self.runtimes[agent_id]

    def list_active(self) -> List[Dict[str, Any]]:
        """列出所有活跃运行时"""
        return [rt.get_stats() for rt in self.runtimes.values()]

    async def run_agent(self, agent_id: str, task: str, context: Dict = None) -> Dict[str, Any]:
        """运行指定 Agent"""
        from tent_os.soul.agent_manager import AgentManager
        # 需要从 manager 获取 config
        # 这里假设 caller 已经传入了 config
        # 实际实现中可能需要通过 manager 查找
        runtime = self.runtimes.get(agent_id)
        if not runtime:
            return {"error": f"Agent {agent_id} 未初始化"}
        return await runtime.run(task, context)
