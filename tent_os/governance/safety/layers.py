"""Tent OS 安全层 v2.0 —— 7层独立安全架构

Layer 1: Tool Pre-filtering（治理进程）
  -> 根据 mode 过滤可用工具，模型永远看不到被禁工具

Layer 2: Deny-first Rules（治理进程 PolicyEngine）
  -> 已有的 PolicyEngine 升级：deny 规则优先级最高

Layer 3: Permission Mode（配置中心）
  -> strict / standard / auto / unrestricted

Layer 4: Auto-Mode Classifier（独立轻量LLM调用）
  -> 用低成本模型评估操作风险，独立于主 LLM

Layer 5: Executor Sandbox（LocalExecutor / SandboxExecutor）
  -> 已有的 local/sandbox/auto 模式

Layer 6: Non-restoration（Redis TTL）
  -> 已有的 1h TTL，会话过期后权限清零

Layer 7: Hooks（插件系统升级）
  -> PreToolUse / PostToolUse / OnError / OnComplete 事件
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class SecurityLayer(Enum):
    """安全层枚举"""
    TOOL_PREFILTER = 1
    DENY_RULES = 2
    PERMISSION_MODE = 3
    AUTO_CLASSIFIER = 4
    EXECUTOR_SANDBOX = 5
    NON_RESTORATION = 6
    HOOKS = 7


@dataclass
class SecurityDecision:
    """安全决策结果"""
    allowed: bool
    layer: int  # 哪一层做出的决策
    layer_name: str
    decision: str  # allow / deny / require_approval
    reason: str
    confidence: float = 1.0


class SecurityPipeline:
    """安全管道 —— 7层顺序执行

    使用方式：
        pipeline = SecurityPipeline(
            tool_pool_assembler=assembler,
            policy_engine=policy_engine,
            permission_manager=permission_manager,
            auto_classifier=classifier,
            hook_engine=hook_engine,
        )
        result = await pipeline.evaluate(session_id, tool_name, params, context)
        if not result.allowed:
            raise SecurityError(result.reason)
    """

    def __init__(self,
                 tool_pool_assembler=None,
                 policy_engine=None,
                 permission_manager=None,
                 auto_classifier=None,
                 hook_engine=None):
        self.tool_pool_assembler = tool_pool_assembler
        self.policy_engine = policy_engine
        self.permission_manager = permission_manager
        self.auto_classifier = auto_classifier
        self.hook_engine = hook_engine

        # 统计
        self._stats = {layer.name: {"allowed": 0, "denied": 0, "approval": 0} for layer in SecurityLayer}

    async def evaluate(self, session_id: str, tool_name: str,
                       params: Dict[str, Any],
                       context: Dict[str, Any] = None) -> SecurityDecision:
        """执行7层安全评估

        按 Layer 1 -> 7 顺序执行，任何一层 deny 就停止。
        返回最终决策。
        """
        context = context or {}

        # Layer 1: Tool Pre-filtering
        if self.tool_pool_assembler:
            if not self.tool_pool_assembler.has_tool(tool_name, session_id, context):
                self._stats["TOOL_PREFILTER"]["denied"] += 1
                return SecurityDecision(
                    allowed=False,
                    layer=1,
                    layer_name="TOOL_PREFILTER",
                    decision="deny",
                    reason=f"工具 {tool_name} 不在当前工具池中（被 mode/profile 过滤）",
                )

        # Layer 2: Deny-first Rules
        if self.policy_engine:
            eval_context = {
                "task": context.get("task", ""),
                "action": tool_name,
                "params": params,
                "executor": {"authorized": True, "consecutive_failures": 0, "status": "online"},
            }
            result = self.policy_engine.evaluate(eval_context)
            if result["decision"] == "deny":
                self._stats["DENY_RULES"]["denied"] += 1
                return SecurityDecision(
                    allowed=False,
                    layer=2,
                    layer_name="DENY_RULES",
                    decision="deny",
                    reason=result.get("reason", "PolicyEngine 拒绝"),
                )
            elif result["decision"] == "require_approval":
                self._stats["DENY_RULES"]["approval"] += 1
                return SecurityDecision(
                    allowed=True,
                    layer=2,
                    layer_name="DENY_RULES",
                    decision="require_approval",
                    reason=result.get("reason", "需要审批"),
                )

        # Layer 3: Permission Mode
        if self.permission_manager:
            check = self.permission_manager.check_operation(session_id, tool_name, params)
            if not check["allowed"]:
                self._stats["PERMISSION_MODE"]["denied"] += 1
                return SecurityDecision(
                    allowed=False,
                    layer=3,
                    layer_name="PERMISSION_MODE",
                    decision="deny",
                    reason=check["reason"],
                )
            if check["requires_approval"]:
                self._stats["PERMISSION_MODE"]["approval"] += 1
                return SecurityDecision(
                    allowed=True,
                    layer=3,
                    layer_name="PERMISSION_MODE",
                    decision="require_approval",
                    reason=check["reason"],
                )

        # Layer 4: Auto-Mode Classifier
        if self.auto_classifier and self.permission_manager:
            mode_config = self.permission_manager.get_mode_config(session_id)
            if mode_config.auto_classifier_enabled:
                assessment = await self.auto_classifier.assess(
                    tool_name=tool_name,
                    params=params,
                    context={"task": context.get("task", ""), "user_id": context.get("user_id", "")},
                )
                if assessment.decision == "deny":
                    self._stats["AUTO_CLASSIFIER"]["denied"] += 1
                    return SecurityDecision(
                        allowed=False,
                        layer=4,
                        layer_name="AUTO_CLASSIFIER",
                        decision="deny",
                        reason=f"AI 分类器判定风险过高: {assessment.reasoning}",
                        confidence=assessment.confidence,
                    )
                elif assessment.decision == "require_approval":
                    self._stats["AUTO_CLASSIFIER"]["approval"] += 1
                    return SecurityDecision(
                        allowed=True,
                        layer=4,
                        layer_name="AUTO_CLASSIFIER",
                        decision="require_approval",
                        reason=f"AI 分类器建议确认: {assessment.reasoning}",
                        confidence=assessment.confidence,
                    )

        # Layer 5: Executor Sandbox
        # 这一步在执行器层面处理，不在治理进程拦截
        # 但这里做预检查
        if tool_name in ("realman", "flashex"):
            mode_config = self.permission_manager.get_mode_config(session_id) if self.permission_manager else None
            if mode_config and not mode_config.allow_physical:
                self._stats["EXECUTOR_SANDBOX"]["denied"] += 1
                return SecurityDecision(
                    allowed=False,
                    layer=5,
                    layer_name="EXECUTOR_SANDBOX",
                    decision="deny",
                    reason="物理执行器在当前模式下被禁用",
                )

        # Layer 6: Non-restoration
        # 会话过期检查已在 state_store 中处理
        # 这里不做额外检查

        # Layer 7: Hooks
        if self.hook_engine:
            hook_result = await self.hook_engine.trigger(
                "tool.preuse",
                session_id=session_id,
                data={"tool": tool_name, "params": params, "context": context},
            )
            if not hook_result.allowed:
                self._stats["HOOKS"]["denied"] += 1
                return SecurityDecision(
                    allowed=False,
                    layer=7,
                    layer_name="HOOKS",
                    decision="deny",
                    reason=f"Hook 拦截: {hook_result.error}",
                )

        # 全部通过
        self._stats["HOOKS"]["allowed"] += 1
        return SecurityDecision(
            allowed=True,
            layer=7,
            layer_name="HOOKS",
            decision="allow",
            reason="通过全部7层安全检查",
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取安全管道统计"""
        return {
            "layers": self._stats,
            "total_evaluations": sum(
                s["allowed"] + s["denied"] + s["approval"]
                for s in self._stats.values()
            ),
        }
