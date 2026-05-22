"""Subagent Spawner —— 动态子代理生命周期管理

借鉴 Claude Code 的子代理架构，适配 Tent OS 的多进程/分布式特性：

内置子代理类型：
- ResearchAgent: 研究任务（信息收集、分析、总结）
- CodeAgent: 代码任务（编写、重构、测试、审查）
- VerifyAgent: 验证任务（事实核查、结果验证、安全审计）
- CustomAgent: 用户自定义（.tent/agents/*.md 定义）

关键技术：
1. Prompt Cache Sharing —— 子代理与父代理共享 system prompt 前缀
2. Sidechain 隔离 —— 每个子代理有自己的会话 ID 和 Redis key
3. 动态生命周期 —— 按需 spawn 的 asyncio Task，用完即销毁

Tent OS 差异化：
- 子代理可以是跨机器的 —— 利用 NATS 消费者组
- 父代理通过 governance.resume 异步接收子代理结果
- 不污染父代理上下文

使用方式：
    spawner = SubagentSpawner(bus, llm, state_store)
    
    # 启动研究子代理
    agent_id = await spawner.spawn(
        parent_session="abc",
        agent_type="research",
        task="研究最新的 React 19 特性",
        timeout_seconds=120,
    )
    
    # 结果通过 governance.resume 异步回调
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class SubagentType(Enum):
    """子代理类型"""
    RESEARCH = "research"
    CODE = "code"
    VERIFY = "verify"
    CUSTOM = "custom"


@dataclass
class SubagentConfig:
    """子代理配置"""
    name: str
    system_prompt: str
    allowed_tools: List[str]
    max_iterations: int = 15
    timeout_seconds: int = 120
    model_provider: str = "openai"
    max_tokens: int = 4096


@dataclass
class SubagentTask:
    """子代理任务"""
    agent_id: str
    parent_session: str
    agent_type: str
    task: str
    status: str = "pending"  # pending / running / completed / failed / cancelled
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    iterations: int = 0


# 内置子代理配置
BUILTIN_AGENT_CONFIGS = {
    SubagentType.RESEARCH: SubagentConfig(
        name="ResearchAgent",
        system_prompt="""你是一个研究专家子代理。你的任务是收集、分析和总结信息。

规则：
1. 使用 web_search 和 web_fetch 工具获取最新信息
2. 分析多个来源，交叉验证关键事实
3. 输出结构化的研究报告，包含：摘要、关键发现、来源、置信度
4. 不要编造信息，不确定的内容标注为"未验证"
5. 优先使用英文搜索获取最新技术信息
""",
        allowed_tools=["web_search", "web_fetch", "memory_search", "http_request"],
        max_iterations=10,
        timeout_seconds=120,
    ),
    SubagentType.CODE: SubagentConfig(
        name="CodeAgent",
        system_prompt="""你是一个代码专家子代理。你的任务是编写、重构和审查代码。

规则：
1. 使用 file_read 读取现有代码，file_write 写入新代码
2. 使用 shell 运行测试和 lint 工具
3. 遵循项目现有的代码风格和规范
4. 编写单元测试验证关键逻辑
5. 输出代码变更摘要和测试报告
6. 不要删除未备份的重要文件
""",
        allowed_tools=["shell", "file_read", "file_write", "directory_list", "http_request"],
        max_iterations=20,
        timeout_seconds=180,
    ),
    SubagentType.VERIFY: SubagentConfig(
        name="VerifyAgent",
        system_prompt="""你是一个验证专家子代理。你的任务是核查事实和验证结果。

规则：
1. 独立验证主代理提供的关键事实和数据
2. 检查代码变更是否有副作用
3. 验证外部信息来源的可靠性
4. 输出验证报告：通过/警告/失败的项
5. 对不确定的内容标注置信度
""",
        allowed_tools=["web_search", "web_fetch", "file_read", "shell"],
        max_iterations=8,
        timeout_seconds=90,
    ),
}


class SubagentSpawner:
    """子代理生成器

    管理子代理的生命周期：
    1. spawn: 创建并启动子代理任务
    2. cancel: 取消运行中的子代理
    3. get_status: 查询子代理状态
    4. list_active: 列出所有活跃子代理

    子代理执行完成后，结果通过消息总线发送到 governance.resume。
    """

    def __init__(self,
                 bus,
                 llm,
                 state_store=None,
                 tool_executor=None,
                 config: Dict[str, Any] = None,
                 jsonl_logger=None):
        self.bus = bus
        self.llm = llm
        self.state_store = state_store
        self.tool_executor = tool_executor
        self.config = config or {}
        self.jsonl_logger = jsonl_logger

        # 活跃的子代理任务: agent_id -> Task
        self._active_tasks: Dict[str, asyncio.Task] = {}

        # 子代理状态: agent_id -> SubagentTask
        self._agent_states: Dict[str, SubagentTask] = {}

        # 自定义代理配置
        self._custom_configs: Dict[str, SubagentConfig] = {}
        self._load_custom_agents()

    def _load_custom_agents(self):
        """加载用户自定义代理"""
        custom_dir = Path(".tent/agents")
        if not custom_dir.exists():
            return

        for md_file in custom_dir.glob("*.md"):
            try:
                # 解析 Markdown 文件（简化：第一行是名称，其余是 system prompt）
                text = md_file.read_text(encoding="utf-8")
                lines = text.strip().split("\n")
                name = lines[0].lstrip("# ").strip() if lines else md_file.stem
                prompt = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

                self._custom_configs[md_file.stem] = SubagentConfig(
                    name=name,
                    system_prompt=prompt,
                    allowed_tools=["shell", "file_read", "file_write", 
                                   "directory_list", "web_search", "web_fetch"],
                    max_iterations=15,
                    timeout_seconds=120,
                )
                logger.info(f"[Subagent] 加载自定义代理: {name}")
            except Exception as e:
                logger.warning(f"[Subagent] 加载自定义代理失败 {md_file}: {e}")

    async def spawn(self,
                    parent_session: str,
                    agent_type: str,
                    task: str,
                    timeout_seconds: int = None,
                    custom_config: Dict[str, Any] = None) -> str:
        """启动子代理

        Args:
            parent_session: 父会话ID
            agent_type: 代理类型 (research/code/verify/custom)
            task: 任务描述
            timeout_seconds: 超时时间（覆盖默认）
            custom_config: 自定义配置（覆盖默认）

        Returns:
            agent_id: 子代理ID
        """
        agent_id = f"agent_{agent_type}_{uuid.uuid4().hex[:8]}"

        # 获取配置
        config = self._get_config(agent_type, custom_config)
        if timeout_seconds:
            config.timeout_seconds = timeout_seconds

        # 创建任务记录
        agent_task = SubagentTask(
            agent_id=agent_id,
            parent_session=parent_session,
            agent_type=agent_type,
            task=task,
            status="pending",
        )
        self._agent_states[agent_id] = agent_task

        # 启动异步任务
        task_coro = self._run_subagent(agent_task, config)
        asyncio_task = asyncio.create_task(task_coro)
        self._active_tasks[agent_id] = asyncio_task

        # 注册回调：任务完成时清理
        asyncio_task.add_done_callback(
            lambda t, aid=agent_id: self._on_agent_done(aid, t)
        )

        logger.info(f"[Subagent] 启动 [{agent_id}]: {agent_type} -> {task[:50]}")

        # 审计日志
        if self.jsonl_logger:
            asyncio.create_task(self.jsonl_logger.log_event(
                event="subagent.spawn",
                session_id=parent_session,
                agent_id=agent_id,
                agent_type=agent_type,
                task=task[:200],
            ))

        return agent_id

    async def cancel(self, agent_id: str) -> bool:
        """取消子代理"""
        task = self._active_tasks.get(agent_id)
        if not task:
            return False

        task.cancel()
        agent = self._agent_states.get(agent_id)
        if agent:
            agent.status = "cancelled"

        logger.info(f"[Subagent] 取消 [{agent_id}]")
        return True

    def get_status(self, agent_id: str) -> Optional[Dict]:
        """获取子代理状态"""
        agent = self._agent_states.get(agent_id)
        if not agent:
            return None

        return {
            "agent_id": agent.agent_id,
            "parent_session": agent.parent_session,
            "agent_type": agent.agent_type,
            "status": agent.status,
            "task": agent.task,
            "result": agent.result,
            "error": agent.error,
            "iterations": agent.iterations,
            "elapsed_seconds": time.time() - agent.created_at,
        }

    def list_active(self, parent_session: str = None) -> List[Dict]:
        """列出活跃子代理"""
        results = []
        for agent in self._agent_states.values():
            if agent.status in ("pending", "running"):
                if parent_session and agent.parent_session != parent_session:
                    continue
                results.append(self.get_status(agent.agent_id))
        return results

    # ========== 内部实现 ==========

    def _get_config(self, agent_type: str, 
                    custom_config: Dict = None) -> SubagentConfig:
        """获取子代理配置"""
        # 尝试内置类型
        try:
            subagent_type = SubagentType(agent_type)
            config = BUILTIN_AGENT_CONFIGS.get(subagent_type)
            if config:
                return config
        except ValueError:
            pass

        # 尝试自定义类型
        if agent_type in self._custom_configs:
            return self._custom_configs[agent_type]

        # 默认配置
        return SubagentConfig(
            name=f"CustomAgent-{agent_type}",
            system_prompt=f"你是一个 {agent_type} 专家子代理。",
            allowed_tools=["shell", "file_read", "file_write", 
                          "directory_list", "web_search", "web_fetch"],
            max_iterations=15,
            timeout_seconds=120,
        )

    async def _run_subagent(self, agent: SubagentTask, config: SubagentConfig):
        """运行子代理 —— 复用完整 _handle_tool_loop 逻辑"""
        agent.status = "running"
        agent.started_at = time.time()

        try:
            # 构建子代理的消息列表
            messages = [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": f"任务：{agent.task}\n\n请使用工具完成任务，然后输出最终结果。"},
            ]

            # 使用完整的 Tool Loop 执行（复用 GovernanceWorker 核心逻辑）
            result = await self._handle_tool_loop_for_subagent(
                agent=agent,
                messages=messages,
                config=config,
            )

            agent.result = result
            agent.status = "completed"
            agent.completed_at = time.time()

            logger.info(f"[Subagent] 完成 [{agent.agent_id}]: {str(result)[:100]}")

        except asyncio.TimeoutError:
            agent.status = "failed"
            agent.error = "执行超时"
            logger.warning(f"[Subagent] 超时 [{agent.agent_id}]")
        except Exception as e:
            agent.status = "failed"
            agent.error = str(e)
            logger.error(f"[Subagent] 异常 [{agent.agent_id}]: {e}")

    async def _handle_tool_loop_for_subagent(self, agent: SubagentTask,
                                              messages: List[Dict],
                                              config: SubagentConfig) -> str:
        """子代理专用 Tool Loop —— 复用 GovernanceWorker _handle_tool_loop 完整逻辑

        包含：
        1. LLM chat_with_tools 调用
        2. 真实工具执行（通过 tool_executor）
        3. 工具结果格式化与截断
        4. 迭代控制与错误处理
        5. 连续失败检测与熔断
        """
        if not self.tool_executor:
            logger.warning(f"[Subagent] ToolExecutor 未配置，回退到直接回复 [{agent.agent_id}]")
            return await self._fallback_chat(messages, config)

        if not hasattr(self.llm, "chat_with_tools"):
            logger.warning(f"[Subagent] LLM 不支持 chat_with_tools，回退到直接回复 [{agent.agent_id}]")
            return await self._fallback_chat(messages, config)

        # 组装可用工具（过滤子代理允许的工具列表）
        tools = self._get_subagent_tools(config.allowed_tools)

        full_response = ""
        tool_call_count = 0
        consecutive_failures = 0
        last_failed_tool = None

        for iteration in range(config.max_iterations):
            agent.iterations = iteration + 1
            logger.info(f"[Subagent] Tool Loop 迭代 {iteration+1}/{config.max_iterations} [{agent.agent_id}]")

            # 调用 LLM（带 tools）
            try:
                result = await self.llm.chat_with_tools(messages, tools)
            except Exception as e:
                return f"LLM 调用失败: {e}"

            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            if not tool_calls:
                # 没有工具调用，直接返回
                full_response = content
                break

            # 执行工具调用
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}

                tool_call_count += 1
                logger.info(f"[Subagent] 执行工具 {tool_name} [{agent.agent_id}] args={json.dumps(arguments, ensure_ascii=False)[:200]}")

                # 检查工具是否在允许列表
                if tool_name not in config.allowed_tools and not any(
                    tool_name.startswith(prefix) for prefix in config.allowed_tools
                ):
                    tool_result = json.dumps({
                        "status": "error",
                        "error": f"工具 '{tool_name}' 不在子代理允许列表中"
                    }, ensure_ascii=False)
                else:
                    # 执行工具
                    try:
                        tool_result = await self.tool_executor.execute(
                            tool_name, arguments, session_id=agent.agent_id
                        )
                    except Exception as e:
                        tool_result = json.dumps({
                            "status": "error",
                            "error": str(e)
                        }, ensure_ascii=False)

                # 检查结果状态
                try:
                    result_data = json.loads(tool_result)
                    is_error = result_data.get("status") == "error"
                except:
                    is_error = False

                if is_error:
                    error_msg = result_data.get("error", "未知错误")
                    logger.warning(f"[Subagent] 工具 {tool_name} 失败 [{agent.agent_id}]: {error_msg}")

                    if last_failed_tool == tool_name:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 1
                        last_failed_tool = tool_name

                    if consecutive_failures >= 2:
                        return (
                            f"❌ 子代理任务执行失败。\n\n"
                            f"工具 `{tool_name}` 连续 {consecutive_failures} 次执行失败：{error_msg}\n\n"
                            f"建议：检查文件路径、参数格式或系统配置。"
                        )
                else:
                    consecutive_failures = 0
                    last_failed_tool = None

                # 工具结果截断（避免污染上下文）
                max_result_chars = 4000
                if len(tool_result) > max_result_chars:
                    try:
                        result_obj = json.loads(tool_result)
                        result_obj = self._truncate_result_object(result_obj, max_result_chars)
                        tool_result = json.dumps(result_obj, ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        tool_result = tool_result[:max_result_chars] + "\n\n[...结果已截断...]"

                # 追加到消息历史
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [tc],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_result,
                })

        if not full_response:
            full_response = f"⚠️ 子代理达到最大迭代次数（{config.max_iterations}次）。"

        return full_response

    async def _fallback_chat(self, messages: List[Dict], config: SubagentConfig) -> str:
        """无工具时的回退对话"""
        try:
            if hasattr(self.llm, "chat"):
                return await self.llm.chat(messages, max_tokens=config.max_tokens)
            return await self.llm(messages[-1]["content"] if messages else "", max_tokens=config.max_tokens)
        except Exception as e:
            return f"LLM 调用失败: {e}"

    def _get_subagent_tools(self, allowed_tools: List[str]) -> List[Dict]:
        """获取子代理允许的工具列表（OpenAI format）"""
        from tent_os.tools.definitions import BUILTIN_TOOLS

        tools = []
        for tool in BUILTIN_TOOLS:
            name = tool.get("function", {}).get("name", "")
            # 精确匹配或前缀匹配
            if name in allowed_tools or any(name.startswith(prefix) for prefix in allowed_tools):
                tools.append(tool)
        return tools

    @staticmethod
    def _truncate_result_object(obj: Dict, max_chars: int) -> Dict:
        """智能截断工具结果对象"""
        result_str = json.dumps(obj, ensure_ascii=False)
        if len(result_str) <= max_chars:
            return obj

        # 优先截断长字符串字段
        for key in list(obj.keys()):
            if isinstance(obj[key], str) and len(obj[key]) > 500:
                obj[key] = obj[key][:500] + "..."
            elif isinstance(obj[key], list) and len(obj[key]) > 20:
                obj[key] = obj[key][:20] + [f"... ({len(obj[key]) - 20} more items)"]

        # 如果还太长，直接截断
        result_str = json.dumps(obj, ensure_ascii=False)
        if len(result_str) > max_chars:
            return {"status": "completed", "result": "[结果过长，已截断]", "truncated": True}
        return obj

    def _on_agent_done(self, agent_id: str, task: asyncio.Task):
        """子代理完成回调"""
        # 清理任务引用
        self._active_tasks.pop(agent_id, None)

        agent = self._agent_states.get(agent_id)
        if not agent:
            return

        # 发送结果到父会话
        result_data = {
            "type": "subagent_complete",
            "session_id": agent.parent_session,
            "agent_id": agent_id,
            "agent_type": agent.agent_type,
            "status": agent.status,
            "result": agent.result,
            "error": agent.error,
            "iterations": agent.iterations,
        }

        # 通过消息总线发送结果
        asyncio.create_task(self.bus.publish(
            "governance.resume",
            json.dumps(result_data).encode(),
        ))

        # 审计日志
        if self.jsonl_logger:
            asyncio.create_task(self.jsonl_logger.log_event(
                event="subagent.complete" if agent.status == "completed" else "subagent.fail",
                session_id=agent.parent_session,
                agent_id=agent_id,
                agent_type=agent.agent_type,
                status=agent.status,
                error=agent.error,
                iterations=agent.iterations,
            ))

    def get_stats(self) -> Dict:
        """获取子代理统计"""
        total = len(self._agent_states)
        completed = sum(1 for a in self._agent_states.values() if a.status == "completed")
        failed = sum(1 for a in self._agent_states.values() if a.status == "failed")
        active = sum(1 for a in self._agent_states.values() if a.status in ("pending", "running"))

        return {
            "total_spawned": total,
            "active": active,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / max(total, 1), 2),
        }
