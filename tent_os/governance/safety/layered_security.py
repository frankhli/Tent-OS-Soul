"""7层独立安全架构 —— Claude Code 模式融合

Tent OS 安全架构 v2.0（7层 → 适配为多进程分布式安全）：

Layer 1: Tool Pre-filtering（治理进程）
  → 根据 mode 过滤可用工具，模型永远看不到被禁工具

Layer 2: Deny-first Rules（治理进程 PolicyEngine）
  → 已有的 PolicyEngine 升级：deny 规则优先级最高

Layer 3: Permission Mode（配置中心）
  → strict / standard / auto / unrestricted

Layer 4: Auto-Mode Classifier（独立轻量LLM调用）
  → 在治理进程内，用低成本模型评估操作风险
  → 独立于主 LLM，避免"自己审批自己"

Layer 5: Executor Sandbox（LocalExecutor / SandboxExecutor）
  → 已有的 local/sandbox/auto 模式，继续完善

Layer 6: Non-restoration（Redis TTL）
  → 已有的 1h TTL，会话过期后权限清零

Layer 7: Hooks（插件系统升级）
  → PreToolUse / PostToolUse / OnError / OnComplete 事件
  → Hook 可以拦截、修改、延迟、审计任何工具调用

使用方式：
    security = LayeredSecurity(config, policy_engine, mode_manager, classifier, hook_engine)
    result = await security.evaluate_tool_call(session_id, "shell", {"command": "rm -rf /"})
    # -> SecurityDecision(allowed=False, reason="Layer 2: 高危操作需审批")
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class SecurityDecision(Enum):
    """安全决策结果"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    CIRCUIT_BREAK = "circuit_break"


@dataclass
class SecurityResult:
    """安全评估结果"""
    allowed: bool
    decision: str
    layer: str  # 哪一层做出的决策
    reason: str
    eval_time_ms: float
    metadata: Dict[str, Any]


class LayeredSecurity:
    """7层安全架构协调器

    每一层独立评估，按顺序执行：
    1. 如果任何一层拒绝，立即停止
    2. 每层可以修改工具参数
    3. 最终结果汇总所有层的意见
    """

    def __init__(self,
                 config: Dict[str, Any] = None,
                 policy_engine=None,
                 opa_engine=None,
                 mode_manager=None,
                 auto_classifier=None,
                 hook_engine=None,
                 jsonl_logger=None):
        self.config = config or {}
        self.policy_engine = policy_engine
        self.opa_engine = opa_engine  # OPA 引擎优先
        self.mode_manager = mode_manager
        self.auto_classifier = auto_classifier
        self.hook_engine = hook_engine
        self.jsonl_logger = jsonl_logger

        # 各层启用状态
        self.layers_enabled = {
            "L1_prefilter": True,
            "L2_policy": True,
            "L3_mode": True,
            "L4_classifier": self.config.get("security", {}).get("auto_classifier", False),
            "L5_sandbox": True,
            "L6_restoration": True,
            "L7_hooks": hook_engine is not None,
        }

        # 统计
        self._stats = {
            "total_evaluations": 0,
            "allowed": 0,
            "denied": 0,
            "require_approval": 0,
            "layer_triggers": {f"L{i}": 0 for i in range(1, 8)},
        }

    async def evaluate_tool_call(self,
                                  session_id: str,
                                  tool_name: str,
                                  params: Dict[str, Any],
                                  task_context: str = "") -> SecurityResult:
        """评估工具调用请求

        依次通过7层安全评估，任何一层拒绝都会立即停止。

        Returns:
            SecurityResult
        """
        start_time = time.time()
        self._stats["total_evaluations"] += 1

        # ========== Layer 1: Tool Pre-filtering ==========
        if self.layers_enabled["L1_prefilter"]:
            l1_result = self._l1_prefilter(session_id, tool_name)
            if not l1_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L1"] += 1
                return l1_result

        # ========== Layer 2: Deny-first Rules ==========
        if self.layers_enabled["L2_policy"] and self.policy_engine:
            l2_result = self._l2_policy(session_id, tool_name, params, task_context)
            if not l2_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L2"] += 1
                return l2_result

        # ========== Layer 3: Permission Mode ==========
        if self.layers_enabled["L3_mode"] and self.mode_manager:
            l3_result = self._l3_mode(session_id, tool_name)
            if not l3_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L3"] += 1
                return l3_result

        # ========== Layer 4: Auto-Mode Classifier ==========
        if self.layers_enabled["L4_classifier"] and self.auto_classifier and task_context:
            l4_result = await self._l4_classifier(session_id, tool_name, params, task_context)
            if not l4_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L4"] += 1
                return l4_result

        # ========== Layer 5: Executor Sandbox ==========
        if self.layers_enabled["L5_sandbox"]:
            l5_result = self._l5_sandbox(session_id, tool_name, params)
            if not l5_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L5"] += 1
                return l5_result

        # ========== Layer 6: Non-restoration ==========
        # 在 state_store 层面处理，这里只做检查
        if self.layers_enabled["L6_restoration"]:
            l6_result = self._l6_restoration(session_id)
            if not l6_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L6"] += 1
                return l6_result

        # ========== Layer 7: Hooks ==========
        if self.layers_enabled["L7_hooks"] and self.hook_engine:
            l7_result = await self._l7_hooks(session_id, tool_name, params)
            if not l7_result.allowed:
                self._stats["denied"] += 1
                self._stats["layer_triggers"]["L7"] += 1
                return l7_result

        # 所有层通过
        self._stats["allowed"] += 1
        eval_time_ms = (time.time() - start_time) * 1000

        return SecurityResult(
            allowed=True,
            decision="allow",
            layer="all",
            reason="所有安全层通过",
            eval_time_ms=eval_time_ms,
            metadata={},
        )

    # ========== Layer 1: Tool Pre-filtering ==========

    def _l1_prefilter(self, session_id: str, tool_name: str) -> SecurityResult:
        """工具预过滤 —— 检查工具是否在 mode 允许列表中"""
        if not self.mode_manager:
            return SecurityResult(allowed=True, decision="allow", layer="L1", reason="无模式管理器", eval_time_ms=0, metadata={})

        allowed = self.mode_manager.is_tool_allowed(tool_name, session_id)
        if not allowed:
            return SecurityResult(
                allowed=False,
                decision="deny",
                layer="L1",
                reason=f"工具 {tool_name} 不在当前 mode 允许列表中",
                eval_time_ms=0,
                metadata={"tool": tool_name},
            )
        return SecurityResult(allowed=True, decision="allow", layer="L1", reason="工具在允许列表中", eval_time_ms=0, metadata={})

    # ========== Layer 2: Deny-first Rules ==========

    def _l2_policy(self, session_id: str, tool_name: str,
                   params: Dict, task_context: str) -> SecurityResult:
        """策略引擎评估 —— OPA 优先，回退旧 PolicyEngine"""
        context = {
            "task": task_context,
            "action": tool_name,
            "params": params,
            "executor": {"authorized": True, "consecutive_failures": 0, "status": "online"},
            "hour": int(time.time() // 3600 % 24),
        }

        # 优先使用 OPA 引擎
        if self.opa_engine:
            result = self.opa_engine.evaluate(context)
        elif self.policy_engine:
            result = self.policy_engine.evaluate(context)
        else:
            return SecurityResult(allowed=True, decision="allow", layer="L2", reason="无策略引擎", eval_time_ms=0, metadata={})

        if result["decision"] == "deny":
            return SecurityResult(
                allowed=False,
                decision="deny",
                layer="L2",
                reason=result.get("reason", "策略拒绝"),
                eval_time_ms=result.get("eval_time_ms", 0),
                metadata={"rule": result.get("rule", "unknown")},
            )
        elif result["decision"] == "require_approval":
            return SecurityResult(
                allowed=False,  # 需要审批，暂时不允许
                decision="require_approval",
                layer="L2",
                reason=result.get("reason", "需要审批"),
                eval_time_ms=result.get("eval_time_ms", 0),
                metadata={"rule": result.get("rule", "unknown")},
            )
        elif result["decision"] == "circuit_break":
            return SecurityResult(
                allowed=False,
                decision="circuit_break",
                layer="L2",
                reason="执行者已熔断",
                eval_time_ms=result.get("eval_time_ms", 0),
                metadata={},
            )

        return SecurityResult(allowed=True, decision="allow", layer="L2", reason="策略通过", eval_time_ms=result.get("eval_time_ms", 0), metadata={})

    # ========== Layer 3: Permission Mode ==========

    def _l3_mode(self, session_id: str, tool_name: str) -> SecurityResult:
        """Permission Mode 检查"""
        mode = self.mode_manager.get_mode(session_id) if self.mode_manager else "standard"

        # strict mode 下只允许只读工具
        if mode == "strict":
            readonly_tools = {"file_read", "directory_list", "web_search", "web_fetch", "memory_search", "memory_get"}
            if tool_name not in readonly_tools:
                return SecurityResult(
                    allowed=False,
                    decision="deny",
                    layer="L3",
                    reason=f"strict mode 下不允许使用 {tool_name}",
                    eval_time_ms=0,
                    metadata={"mode": mode},
                )

        return SecurityResult(allowed=True, decision="allow", layer="L3", reason=f"mode={mode} 允许", eval_time_ms=0, metadata={"mode": mode})

    # ========== Layer 4: Auto-Mode Classifier ==========

    async def _l4_classifier(self, session_id: str, tool_name: str,
                             params: Dict, task_context: str) -> SecurityResult:
        """自动模式分类器评估"""
        try:
            result = await self.auto_classifier.evaluate(task_context)

            if result.safety_level == "critical":
                return SecurityResult(
                    allowed=False,
                    decision="require_approval",
                    layer="L4",
                    reason=f"Auto-Classifier: {result.reasoning}",
                    eval_time_ms=result.eval_time_ms,
                    metadata={"safety_level": result.safety_level, "confidence": result.confidence},
                )

            if result.safety_level == "dangerous" and result.confidence > 0.8:
                return SecurityResult(
                    allowed=False,
                    decision="require_approval",
                    layer="L4",
                    reason=f"高风险操作: {result.reasoning}",
                    eval_time_ms=result.eval_time_ms,
                    metadata={"risks": result.risks},
                )

            return SecurityResult(
                allowed=True,
                decision="allow",
                layer="L4",
                reason=f"安全等级: {result.safety_level}",
                eval_time_ms=result.eval_time_ms,
                metadata={"safety_level": result.safety_level},
            )
        except Exception as e:
            logger.warning(f"[Security L4] Classifier 评估失败: {e}")
            # Classifier 失败不阻断，降级通过
            return SecurityResult(allowed=True, decision="allow", layer="L4", reason="Classifier 降级通过", eval_time_ms=0, metadata={})

    # ========== Layer 5: Executor Sandbox ==========

    def _l5_sandbox(self, session_id: str, tool_name: str,
                    params: Dict) -> SecurityResult:
        """执行器沙箱检查"""
        # 检查是否是物理执行器
        if tool_name in ("realman", "flashex"):
            # 物理操作需要额外确认
            return SecurityResult(
                allowed=False,
                decision="require_approval",
                layer="L5",
                reason="物理操作需要人工确认",
                eval_time_ms=0,
                metadata={"executor_type": "physical"},
            )

        # 检查 shell 命令中的危险模式
        if tool_name == "shell":
            cmd = params.get("command", "")
            dangerous = ["rm -rf /", "mkfs", "fdisk", "dd if=/dev/zero", ":(){:|:&};:"]
            for d in dangerous:
                if d in cmd:
                    return SecurityResult(
                        allowed=False,
                        decision="deny",
                        layer="L5",
                        reason=f"检测到高危命令模式: {d}",
                        eval_time_ms=0,
                        metadata={"command": cmd[:50]},
                    )

        return SecurityResult(allowed=True, decision="allow", layer="L5", reason="沙箱检查通过", eval_time_ms=0, metadata={})

    # ========== Layer 6: Non-restoration ==========

    def _l6_restoration(self, session_id: str) -> SecurityResult:
        """非持久化检查 —— 会话是否有效"""
        # 这里主要依赖 state_store 的 TTL 机制
        # 如果会话已过期，state_store.load 会抛出 KeyError
        # 治理进程的 _handle_resume 已处理这种情况
        return SecurityResult(allowed=True, decision="allow", layer="L6", reason="会话有效", eval_time_ms=0, metadata={})

    # ========== Layer 7: Hooks ==========

    async def _l7_hooks(self, session_id: str, tool_name: str,
                        params: Dict) -> SecurityResult:
        """Hook 拦截检查"""
        if not self.hook_engine:
            return SecurityResult(allowed=True, decision="allow", layer="L7", reason="无 Hook 引擎", eval_time_ms=0, metadata={})

        hook_result = await self.hook_engine.trigger(
            "tool.preuse",
            session_id=session_id,
            data={"tool": tool_name, "params": params},
        )

        if not hook_result.allowed:
            return SecurityResult(
                allowed=False,
                decision="deny",
                layer="L7",
                reason=f"Hook 拦截: {hook_result.error or '未指定原因'}",
                eval_time_ms=hook_result.latency_ms,
                metadata={},
            )

        return SecurityResult(
            allowed=True,
            decision="allow",
            layer="L7",
            reason="Hook 通过",
            eval_time_ms=hook_result.latency_ms,
            metadata={"modified": hook_result.modified},
        )

    def get_stats(self) -> Dict:
        """获取安全层统计"""
        return {
            **self._stats,
            "allow_rate": round(
                self._stats["allowed"] / max(self._stats["total_evaluations"], 1), 2
            ),
        }
