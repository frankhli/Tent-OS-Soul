"""失败自愈机制 —— 自主神经系统的"免疫系统"

策略：
1. 首次失败 → 自动重试（指数退避）
2. 多次失败同一任务 → 降级执行（简化目标）
3. 持续失败 → 上报用户，请求指导
4. 系统级失败 → 触发紧急停止，保护数据

A.3 增强：
5. 自验证（Self-Validation）→ 执行后验证结果，失败自动回滚
6. 循环检测（Loop Detection）→ 检测重复执行模式，防止无限循环
7. 自动回滚（Auto-Rollback）→ 失败时按 LIFO 撤销已执行操作
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("tent_os.autonomy.healing")


@dataclass
class HealingResult:
    """自愈结果"""
    success: bool
    action_taken: str
    retry_count: int
    final_result: Optional[str]
    escalation_required: bool


@dataclass
class ValidationResult:
    """自验证结果"""
    valid: bool
    rule: str
    reason: str
    severity: str = "warn"  # warn/error/critical


@dataclass
class StateSnapshot:
    """状态快照 —— 用于回滚"""
    snapshot_id: str
    task_id: str
    action: str
    timestamp: datetime
    data: Dict[str, Any]
    undo_callback: Optional[Callable] = None


@dataclass
class LoopPattern:
    """循环模式检测结果"""
    detected: bool
    pattern_type: str  # "repeat_action", "fail_retry_loop", "parameter Oscillation"
    confidence: float  # 0.0-1.0
    occurrences: int
    suggested_action: str


class SelfHealing:
    """失败自愈器 —— A.3 增强版"""

    # 退避策略：1s, 2s, 4s, 8s, 16s, 32s
    BACKOFF_BASE = 1
    BACKOFF_MAX = 5  # 最多 5 次重试

    # 循环检测阈值
    LOOP_REPEAT_THRESHOLD = 3       # 相同 action+params 重复3次视为循环
    LOOP_WINDOW_SECONDS = 60        # 检测窗口
    FAIL_RETRY_THRESHOLD = 4        # 失败-重试-失败循环阈值

    def __init__(self):
        self._failure_history: Dict[str, List[datetime]] = {}
        self._execution_log: List[Dict[str, Any]] = []  # A.3: 执行历史
        self._snapshots: Dict[str, List[StateSnapshot]] = {}  # A.3: 状态快照
        self._undo_registry: Dict[str, Callable] = {}  # A.3: 回滚函数注册表
        self._validation_rules: Dict[str, List[Callable]] = {}  # A.3: 验证规则
        self._healing_stats = {
            "total_attempts": 0,
            "successful_heals": 0,
            "escalations": 0,
            "self_validations": 0,
            "validation_failures": 0,
            "rollbacks": 0,
            "loops_detected": 0,
        }

    # ========== A.3.1 自验证（Self-Validation）==========

    def register_validation_rule(self, action: str, rule_fn: Callable):
        """为 action 注册验证规则

        rule_fn(result: Dict) -> ValidationResult
        """
        if action not in self._validation_rules:
            self._validation_rules[action] = []
        self._validation_rules[action].append(rule_fn)
        logger.info(f"[Healing] 验证规则已注册: {action}")

    def validate_result(self, task_id: str, action: str,
                        result: Dict[str, Any]) -> List[ValidationResult]:
        """执行后自验证"""
        self._healing_stats["self_validations"] += 1
        rules = self._validation_rules.get(action, [])
        if not rules:
            # 默认验证：检查结果是否包含 error/status 字段
            return [self._default_validation(result)]

        results = []
        for rule_fn in rules:
            try:
                vr = rule_fn(result)
                if isinstance(vr, ValidationResult):
                    results.append(vr)
            except Exception as e:
                logger.warning(f"[Healing] 验证规则异常: {e}")
                results.append(ValidationResult(
                    valid=False, rule="exception", reason=str(e), severity="warn"
                ))
        return results

    def _default_validation(self, result: Dict[str, Any]) -> ValidationResult:
        """默认验证规则"""
        if not isinstance(result, dict):
            return ValidationResult(valid=True, rule="default", reason="非字典结果跳过")

        if result.get("status") == "failed":
            return ValidationResult(
                valid=False, rule="status_check",
                reason="结果状态为 failed", severity="error"
            )
        if result.get("error"):
            return ValidationResult(
                valid=False, rule="error_check",
                reason=f"结果包含错误: {result['error']}", severity="error"
            )
        return ValidationResult(valid=True, rule="default", reason="通过")

    # ========== A.3.2 循环检测（Loop Detection）==========

    def log_execution(self, task_id: str, action: str,
                      params: Dict[str, Any], result_status: str):
        """记录执行历史，用于循环检测"""
        entry = {
            "task_id": task_id,
            "action": action,
            "params_hash": self._hash_params(params),
            "status": result_status,
            "timestamp": datetime.now(),
        }
        self._execution_log.append(entry)
        # 保持日志在合理大小（保留最近1000条）
        if len(self._execution_log) > 1000:
            self._execution_log = self._execution_log[-800:]

    def detect_loop(self, task_id: str, action: str,
                    params: Dict[str, Any]) -> LoopPattern:
        """检测是否存在循环模式

        检测三种循环：
        1. repeat_action: 相同 action+params 在短时间内重复执行
        2. fail_retry_loop: 失败→重试→失败的循环
        3. parameter_oscillation: 参数在几个值之间震荡
        """
        params_hash = self._hash_params(params)
        cutoff = datetime.now() - timedelta(seconds=self.LOOP_WINDOW_SECONDS)
        recent = [e for e in self._execution_log
                  if e["timestamp"] > cutoff and e["action"] == action]

        # 模式1: 重复执行检测
        repeat_count = sum(1 for e in recent if e["params_hash"] == params_hash)
        if repeat_count >= self.LOOP_REPEAT_THRESHOLD:
            self._healing_stats["loops_detected"] += 1
            return LoopPattern(
                detected=True,
                pattern_type="repeat_action",
                confidence=min(repeat_count / self.LOOP_REPEAT_THRESHOLD, 1.0),
                occurrences=repeat_count,
                suggested_action="等待或更换参数",
            )

        # 模式2: 失败-重试循环
        task_entries = [e for e in recent if e["task_id"] == task_id]
        if len(task_entries) >= self.FAIL_RETRY_THRESHOLD:
            fail_count = sum(1 for e in task_entries if e["status"] in ("failed", "error"))
            if fail_count >= self.FAIL_RETRY_THRESHOLD - 1:
                self._healing_stats["loops_detected"] += 1
                return LoopPattern(
                    detected=True,
                    pattern_type="fail_retry_loop",
                    confidence=min(fail_count / self.FAIL_RETRY_THRESHOLD, 1.0),
                    occurrences=fail_count,
                    suggested_action="降级执行或上报",
                )

        # 模式3: 参数震荡（简化检测：看是否有大量不同 params_hash）
        unique_hashes = set(e["params_hash"] for e in recent)
        if len(recent) >= 5 and len(unique_hashes) >= len(recent) * 0.8:
            return LoopPattern(
                detected=True,
                pattern_type="parameter_oscillation",
                confidence=0.6,
                occurrences=len(recent),
                suggested_action="固定参数或批量处理",
            )

        return LoopPattern(
            detected=False,
            pattern_type="none",
            confidence=0.0,
            occurrences=0,
            suggested_action="",
        )

    def _hash_params(self, params: Dict[str, Any]) -> str:
        """计算参数哈希"""
        try:
            return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        except Exception:
            return "unknown"

    # ========== A.3.3 自动回滚（Auto-Rollback）==========

    def register_undo(self, action: str, undo_fn: Callable):
        """为 action 注册回滚函数

        undo_fn(snapshot_data: Dict) -> bool
        """
        self._undo_registry[action] = undo_fn
        logger.info(f"[Healing] 回滚函数已注册: {action}")

    def take_snapshot(self, task_id: str, action: str,
                      data: Dict[str, Any]) -> StateSnapshot:
        """执行前保存状态快照"""
        snapshot_id = f"{task_id}_{action}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot = StateSnapshot(
            snapshot_id=snapshot_id,
            task_id=task_id,
            action=action,
            timestamp=datetime.now(),
            data=data,
            undo_callback=self._undo_registry.get(action),
        )
        if task_id not in self._snapshots:
            self._snapshots[task_id] = []
        self._snapshots[task_id].append(snapshot)
        return snapshot

    async def rollback(self, task_id: str, reason: str = "") -> Tuple[bool, List[str]]:
        """按 LIFO 顺序回滚任务的所有已执行操作

        Returns:
            (success: bool, undone_actions: List[str])
        """
        snapshots = self._snapshots.get(task_id, [])
        if not snapshots:
            logger.info(f"[Healing] 无快照可回滚: {task_id}")
            return True, []

        undone = []
        success = True

        # LIFO 回滚
        for snapshot in reversed(snapshots):
            if snapshot.undo_callback:
                try:
                    if asyncio.iscoroutinefunction(snapshot.undo_callback):
                        result = await snapshot.undo_callback(snapshot.data)
                    else:
                        result = snapshot.undo_callback(snapshot.data)

                    if result:
                        undone.append(snapshot.action)
                        logger.info(f"[Healing] 回滚成功: {snapshot.action} ({snapshot.snapshot_id})")
                    else:
                        logger.warning(f"[Healing] 回滚返回False: {snapshot.action}")
                        success = False
                except Exception as e:
                    logger.error(f"[Healing] 回滚异常 {snapshot.action}: {e}")
                    success = False
            else:
                logger.warning(f"[Healing] 无回滚函数: {snapshot.action}")
                success = False

        self._healing_stats["rollbacks"] += 1
        # 清除已回滚的快照
        self._snapshots.pop(task_id, None)
        return success, undone

    def clear_snapshots(self, task_id: str):
        """清除任务的快照（任务成功完成后调用）"""
        self._snapshots.pop(task_id, None)

    # ========== 原有自愈逻辑 ==========

    async def handle_failure(self, task_id: str, error: str,
                             executor: Callable, executor_params: Dict = None) -> HealingResult:
        """处理失败

        Args:
            task_id: 任务 ID
            error: 错误信息
            executor: 执行函数
            executor_params: 执行参数

        Returns:
            HealingResult: 自愈结果
        """
        self._healing_stats["total_attempts"] += 1

        # 记录失败历史
        if task_id not in self._failure_history:
            self._failure_history[task_id] = []
        self._failure_history[task_id].append(datetime.now())

        failure_count = len(self._failure_history[task_id])

        # 策略 1：首次/早期失败 → 重试
        if failure_count <= self.BACKOFF_MAX:
            delay = self.BACKOFF_BASE * (2 ** (failure_count - 1))
            logger.info(f"自愈：任务 {task_id} 第 {failure_count} 次失败，{delay}s 后重试")

            await asyncio.sleep(delay)

            try:
                if executor_params:
                    result = await executor(**executor_params)
                else:
                    result = await executor()

                # 成功！
                self._healing_stats["successful_heals"] += 1
                # 清除失败历史
                self._failure_history.pop(task_id, None)

                return HealingResult(
                    success=True,
                    action_taken=f"retry_{failure_count}",
                    retry_count=failure_count,
                    final_result=str(result),
                    escalation_required=False,
                )
            except Exception as e:
                logger.warning(f"自愈重试失败: {e}")
                # 继续下一步策略

        # 策略 2：多次失败 → 降级执行
        if failure_count > self.BACKOFF_MAX:
            logger.info(f"自愈：任务 {task_id} 多次失败，尝试降级执行")

            try:
                # 降级：简化目标或更换执行方式
                degraded_result = await self._degraded_execute(task_id, executor, executor_params)

                if degraded_result:
                    self._healing_stats["successful_heals"] += 1
                    self._failure_history.pop(task_id, None)

                    return HealingResult(
                        success=True,
                        action_taken="degraded_execute",
                        retry_count=failure_count,
                        final_result=str(degraded_result),
                        escalation_required=False,
                    )
            except Exception as e:
                logger.warning(f"降级执行失败: {e}")

        # 策略 3：持续失败 → 上报用户
        logger.error(f"自愈：任务 {task_id} 持续失败，需要人工干预")
        self._healing_stats["escalations"] += 1

        return HealingResult(
            success=False,
            action_taken="escalate",
            retry_count=failure_count,
            final_result=None,
            escalation_required=True,
        )

    async def _degraded_execute(self, task_id: str, executor: Callable, params: Dict) -> Optional[str]:
        """降级执行——简化目标或更换执行方式"""
        # 简化策略：
        # 1. 如果原任务是复杂查询，降级为简单查询
        # 2. 如果原任务涉及写入，降级为只读
        # 3. 如果原任务需要外部 API，降级为本地处理

        logger.info(f"降级执行: {task_id}")

        # 尝试不带某些参数执行（简化）
        if params:
            simplified = {k: v for k, v in params.items() if k not in ["complex", "async", "batch"]}
            try:
                return await executor(**simplified)
            except Exception:
                pass

        # 尝试用默认值执行
        try:
            return await executor()
        except Exception:
            pass

        return None

    def is_circuit_open(self, task_id: str, threshold: int = 5,
                        window_seconds: int = 300) -> bool:
        """检查是否应该熔断（Circuit Breaker）

        如果在 window_seconds 内失败超过 threshold 次，熔断。
        """
        if task_id not in self._failure_history:
            return False

        failures = self._failure_history[task_id]
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        recent_failures = [f for f in failures if f > cutoff]

        return len(recent_failures) >= threshold

    def reset_circuit(self, task_id: str):
        """重置熔断器"""
        self._failure_history.pop(task_id, None)
        logger.info(f"熔断器重置: {task_id}")

    def get_stats(self) -> Dict:
        """获取自愈统计"""
        return {
            **self._healing_stats,
            "active_failure_tracks": len(self._failure_history),
            "active_snapshots": sum(len(s) for s in self._snapshots.values()),
            "registered_undo_actions": len(self._undo_registry),
            "registered_validation_rules": len(self._validation_rules),
            "failure_distribution": {
                task_id: len(failures)
                for task_id, failures in self._failure_history.items()
            },
        }
