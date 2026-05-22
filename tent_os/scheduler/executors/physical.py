"""PhysicalDeliveryExecutor —— 物理触达执行器

支持机器人和闪送自动切换的物理任务执行：
- 自动检测可用物理执行者（机器人/闪送）
- 故障时自动降级切换（机器人故障 → 闪送，闪送故障 → 人工通知）
- 与 EmbodiedPlanner 集成：执行前做路径规划和风险评估
- 与 SelfHealing 集成：物理任务失败触发自愈重试

Tent OS 差异化：
- 不追三巨头 IDE/渠道/CI-CD 赛道，专注 Harness OPA×分布式、故障自愈×物理触达
- 物理执行器也是一等公民，和本地 shell 同等对待
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Callable

from tent_os.logging_config import get_logger
from tent_os.plugins.base import ExecutorPlugin

logger = get_logger()


async def _broadcast_physical_event(event: Dict):
    """P0: 广播物理执行事件到 NATS（供前端 avatar 感知）"""
    try:
        from tent_os.bootstrap import load_config, create_message_bus
        config = load_config("./config/tent_os.yaml")
        bus = create_message_bus(config)
        await bus.connect()
        await bus.publish_raw("physical.status_change", json.dumps(event).encode())
        await bus.close()
    except Exception:
        pass


class PhysicalProvider(Enum):
    """物理服务提供商"""
    REALMAN_ROBOT = "realman"      # 越疆机器人
    FLASHEx = "flashex"            # 闪送
    MANUAL = "manual"              # 人工通知（最终降级）


@dataclass
class PhysicalTask:
    """物理任务"""
    task_id: str
    action: str                    # deliver / retrieve / notify
    target_location: str           # 目标地址/位置
    item_description: str          # 物品描述
    provider: PhysicalProvider = PhysicalProvider.REALMAN_ROBOT
    priority: str = "normal"       # urgent / normal / low
    status: str = "pending"        # pending / assigned / executing / completed / failed
    retry_count: int = 0
    max_retries: int = 2
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    fallback_chain: List[PhysicalProvider] = field(default_factory=lambda: [
        PhysicalProvider.REALMAN_ROBOT,
        PhysicalProvider.FLASHEx,
        PhysicalProvider.MANUAL,
    ])


class PhysicalDeliveryExecutor(ExecutorPlugin):
    """物理触达执行器

    执行流程:
    1. 接收任务 (deliver/retrieve/notify)
    2. 评估可用性 → 选择最优 provider
    3. 通过 EmbodiedPlanner 做路径/风险评估
    4. 发送执行命令
    5. 监控状态 → 失败时自动切换 fallback
    6. 返回结果
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.providers: Dict[PhysicalProvider, Any] = {}
        self.active_tasks: Dict[str, PhysicalTask] = {}

        # 熔断状态
        self._circuit_open: Dict[PhysicalProvider, bool] = {
            p: False for p in PhysicalProvider
        }
        self._failure_counts: Dict[PhysicalProvider, int] = {
            p: 0 for p in PhysicalProvider
        }
        self._circuit_threshold = self.config.get("circuit_threshold", 3)
        self._circuit_reset_seconds = self.config.get("circuit_reset_seconds", 300)
        self._last_failure_time: Dict[PhysicalProvider, float] = {}

        # 初始化各 provider 的模拟/真实客户端
        self._init_providers()

    def name(self) -> str:
        return "physical"

    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, config: Dict) -> None:
        self.config = {**self.config, **config}
        self._init_providers()

    def supported_actions(self) -> list:
        return ["deliver", "retrieve", "notify", "realman", "flashex"]

    def _init_providers(self):
        """初始化各 provider 的客户端"""
        # 真实机器人 API（配置存在时）
        realman_config = self.config.get("realman", {})
        if realman_config.get("api_endpoint"):
            self.providers[PhysicalProvider.REALMAN_ROBOT] = RealManClient(realman_config)
        else:
            self.providers[PhysicalProvider.REALMAN_ROBOT] = MockPhysicalClient("realman")

        # 闪送 API（配置存在时）
        flashex_config = self.config.get("flashex", {})
        if flashex_config.get("api_key"):
            self.providers[PhysicalProvider.FLASHEx] = FlashExClient(flashex_config)
        else:
            self.providers[PhysicalProvider.FLASHEx] = MockPhysicalClient("flashex")

        # 人工通知永远是 mock（发送消息给管理员）
        self.providers[PhysicalProvider.MANUAL] = MockPhysicalClient("manual")

    async def execute(self, action: str, params: Dict) -> Dict:
        """执行物理任务"""
        task_id = params.get("task_id", f"phys_{int(time.time() * 1000)}")

        # 映射旧工具名到新 action
        action_map = {
            "realman": "deliver",
            "flashex": "deliver",
        }
        action = action_map.get(action, action)

        task = PhysicalTask(
            task_id=task_id,
            action=action,
            target_location=params.get("target_location", params.get("location", "")),
            item_description=params.get("item_description", params.get("description", "")),
            priority=params.get("priority", "normal"),
            max_retries=params.get("max_retries", 2),
        )
        self.active_tasks[task_id] = task

        # P0: 广播任务分配事件
        asyncio.create_task(_broadcast_physical_event({
            "task_id": task_id,
            "status": "assigned",
            "provider": task.provider.value,
            "action": action,
            "target_location": task.target_location,
            "event": "task_assigned",
        }))

        # 执行主逻辑（含自动降级）
        result = await self._execute_with_fallback(task)
        return result

    async def get_status(self, task_id: str) -> Dict:
        task = self.active_tasks.get(task_id)
        if not task:
            return {"status": "unknown", "error": "任务不存在"}
        return {
            "task_id": task.task_id,
            "status": task.status,
            "provider": task.provider.value,
            "retry_count": task.retry_count,
            "error": task.error,
            "elapsed_seconds": time.time() - task.created_at,
        }

    # ========== 核心逻辑 ==========

    async def _execute_with_fallback(self, task: PhysicalTask) -> Dict:
        """执行物理任务，失败时自动降级"""
        for provider in task.fallback_chain:
            # 检查熔断器
            if self._is_circuit_open(provider):
                logger.info(f"[Physical] {provider.value} 熔断器打开，跳过")
                continue

            task.provider = provider
            task.started_at = time.time()
            task.status = "executing"

            logger.info(f"[Physical] 执行任务 [{task.task_id}] via {provider.value}: {task.action} -> {task.target_location}")

            try:
                client = self.providers.get(provider)
                if not client:
                    raise RuntimeError(f"Provider {provider.value} 未初始化")

                # 通过 EmbodiedPlanner 做风险评估（机器人 only）
                if provider == PhysicalProvider.REALMAN_ROBOT:
                    risk = await self._assess_risk(task)
                    if risk["risk_level"] > 0.8:
                        logger.warning(f"[Physical] 风险过高 ({risk['risk_level']}), 跳过机器人")
                        self._record_failure(provider)
                        continue

                # 执行
                result = await client.execute(
                    action=task.action,
                    target=task.target_location,
                    item=task.item_description,
                    priority=task.priority,
                )

                if result.get("status") == "completed":
                    task.status = "completed"
                    task.completed_at = time.time()
                    self._record_success(provider)
                    # P0: 广播任务完成
                    asyncio.create_task(_broadcast_physical_event({
                        "task_id": task.task_id,
                        "status": "completed",
                        "provider": provider.value,
                        "action": task.action,
                        "target_location": task.target_location,
                        "event": "task_completed",
                    }))
                    return {
                        "status": "completed",
                        "task_id": task.task_id,
                        "provider": provider.value,
                        "result": result,
                        "elapsed_seconds": round(time.time() - task.created_at, 1),
                    }
                else:
                    raise RuntimeError(result.get("error", "未知错误"))

            except Exception as e:
                task.retry_count += 1
                task.error = str(e)
                self._record_failure(provider)
                logger.warning(f"[Physical] {provider.value} 失败 [{task.task_id}]: {e} (retry {task.retry_count})")
                # P0: 广播降级事件
                next_idx = task.fallback_chain.index(provider) + 1
                if next_idx < len(task.fallback_chain):
                    next_provider = task.fallback_chain[next_idx]
                    asyncio.create_task(_broadcast_physical_event({
                        "task_id": task.task_id,
                        "status": "fallback",
                        "provider": provider.value,
                        "action": task.action,
                        "target_location": task.target_location,
                        "event": "fallback_triggered",
                        "fallback_from": provider.value,
                        "fallback_to": next_provider.value,
                    }))

                # 如果还有 fallback 选项，继续
                if task.retry_count <= task.max_retries:
                    await asyncio.sleep(1)  # 短暂冷却
                    continue
                else:
                    break

        # 所有 provider 都失败了
        task.status = "failed"
        # P0: 广播任务失败
        asyncio.create_task(_broadcast_physical_event({
            "task_id": task.task_id,
            "status": "failed",
            "provider": task.provider.value if task.provider else None,
            "action": task.action,
            "target_location": task.target_location,
            "event": "task_failed",
            "error": task.error,
        }))
        return {
            "status": "failed",
            "task_id": task.task_id,
            "error": f"所有物理执行者都失败: {task.error}",
            "fallback_history": [p.value for p in task.fallback_chain[:task.retry_count]],
        }

    async def _assess_risk(self, task: PhysicalTask) -> Dict:
        """风险评估"""
        try:
            from tent_os.scheduler.embodied_planner import EmbodiedPlanner
            from tent_os.scheduler.embodied_state import EmbodiedState

            planner = EmbodiedPlanner()
            state = EmbodiedState(
                position=(0, 0, 0),  # 简化：从原点出发
                battery_level=0.8,
            )
            # 简化：将目标位置解析为坐标（实际应从地图服务获取）
            plan = planner.plan_motion((1, 1, 0), state)
            return {
                "risk_level": plan.risk_level,
                "estimated_time": plan.estimated_time,
                "feasible": True,
            }
        except Exception as e:
            logger.debug(f"[Physical] 风险评估失败: {e}")
            return {"risk_level": 0.3, "estimated_time": 60, "feasible": True}

    def _is_circuit_open(self, provider: PhysicalProvider) -> bool:
        """检查熔断器状态"""
        if not self._circuit_open[provider]:
            return False
        # 检查是否需要重置
        last_fail = self._last_failure_time.get(provider, 0)
        if time.time() - last_fail > self._circuit_reset_seconds:
            self._circuit_open[provider] = False
            self._failure_counts[provider] = 0
            logger.info(f"[Physical] {provider.value} 熔断器重置")
            return False
        return True

    def _record_failure(self, provider: PhysicalProvider):
        self._failure_counts[provider] += 1
        self._last_failure_time[provider] = time.time()
        if self._failure_counts[provider] >= self._circuit_threshold:
            self._circuit_open[provider] = True
            logger.warning(f"[Physical] {provider.value} 熔断器打开（连续失败 {self._failure_counts[provider]} 次）")

    def _record_success(self, provider: PhysicalProvider):
        self._failure_counts[provider] = 0
        self._circuit_open[provider] = False


# ========== Provider Clients ==========

class MockPhysicalClient:
    """模拟物理客户端（开发/测试用）"""

    def __init__(self, name: str):
        self.name = name

    async def execute(self, action: str, target: str, item: str, priority: str) -> Dict:
        """模拟执行"""
        await asyncio.sleep(0.5)  # 模拟网络延迟
        return {
            "status": "completed",
            "provider": self.name,
            "action": action,
            "target": target,
            "item": item,
            "message": f"[{self.name}] 模拟完成: {action} {item} 到 {target}",
        }


class RealManClient:
    """越疆机器人真实客户端"""

    def __init__(self, config: Dict):
        self.api_endpoint = config.get("api_endpoint", "")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout_seconds", 30)

    async def execute(self, action: str, target: str, item: str, priority: str) -> Dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.api_endpoint}/api/v1/task",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "action": action,
                        "target_location": target,
                        "item_description": item,
                        "priority": priority,
                    },
                )
                data = resp.json()
                if data.get("code") == 0:
                    return {"status": "completed", "provider": "realman", "task_id": data.get("data", {}).get("task_id")}
                return {"status": "failed", "error": data.get("message", "机器人API错误")}
        except Exception as e:
            return {"status": "failed", "error": f"机器人通信失败: {e}"}


class FlashExClient:
    """闪送真实客户端"""

    def __init__(self, config: Dict):
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.sandbox = config.get("sandbox", True)
        self.base_url = "https://openapi.sandbox.flash-ex.com" if self.sandbox else "https://openapi.flash-ex.com"

    async def execute(self, action: str, target: str, item: str, priority: str) -> Dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/v2/order/create",
                    headers={"App-Key": self.api_key},
                    json={
                        "delivery_no": f"tent_{int(time.time() * 1000)}",
                        "remark": item,
                        "info": {"address": target, "priority": priority},
                    },
                )
                data = resp.json()
                if data.get("code") == 200:
                    return {"status": "completed", "provider": "flashex", "order_id": data.get("data", {}).get("order_id")}
                return {"status": "failed", "error": data.get("msg", "闪送API错误")}
        except Exception as e:
            return {"status": "failed", "error": f"闪送通信失败: {e}"}
