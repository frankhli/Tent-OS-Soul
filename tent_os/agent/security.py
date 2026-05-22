"""安全管道 —— System 1 + System 2 双层安全架构

参考 Claude Code 的权限设计 + worker.py 的生产实践：
- 不过度安全：默认 standard 模式，只拦截极端危险操作
- 用户同意放行：dangerous 操作通过 approval workflow 让用户确认后执行
- System 1（0ms）：正则直觉层，只匹配极端危险模式
- System 2（LLM）：仅在直觉不确定时调用，分类器评估

权限模式：
- strict: 所有危险操作需 approval
- standard: 默认模式， deny-first + ML 分类器
- auto: 低危操作自动批准
- unrestricted: 无限制（仅用于测试）
"""

import re
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from tent_os.logging_config import get_logger

logger = get_logger()


# 极端危险模式（System 1 直觉层）
# 原则：只拦截系统级破坏命令，其他全部放行
DANGER_PATTERNS = [
    r'rm\s+-rf',
    r'drop\s+table',
    r'delete\s+from\s+\w+\s+where',
    r'format\s+[a-z]:',
    r'fdisk',
    r'mkfs',
    r'shutdown\s+-h',
    r'reboot',
    r'init\s+0',
    r'\bkill\s+-9\b',
    r'\bpkill\b',
    r'chmod\s+777\s+/etc',
    r'chown\s+-R\s+root',
    r'echo\s+.*>\s+/etc/',
    r'>\s+/dev/sd[a-z]',
    r'curl\s+.*\|\s*sh',
    r'wget\s+.*\|\s*sh',
    r'sudo\s+rm',
    r'rm\s+/etc',
]

# 模式优先级（越小越严格）
MODE_PRIORITY = {"strict": 0, "standard": 1, "auto": 2, "unrestricted": 3}


@dataclass
class SecurityAssessment:
    """安全评估结果"""
    safety_level: str = "safe"          # safe / suspicious / dangerous / critical
    suggested_mode: str = "standard"    # strict / standard / auto / unrestricted
    reasoning: str = ""
    confidence: float = 0.0
    source: str = ""                    # intuition / llm / skip
    mode_changed: bool = False
    old_mode: Optional[str] = None
    new_mode: Optional[str] = None


class ModeManager:
    """会话权限模式管理器

    每个 session 独立维护权限模式，支持持久化到 state_store。
    """

    def __init__(self, state_store=None):
        self.state_store = state_store
        # 内存缓存：session_id -> {mode, reason, task_hint, set_at}
        self._modes: Dict[str, Dict] = {}

    def get_mode(self, session_id: str) -> str:
        """获取当前会话的权限模式"""
        if session_id in self._modes:
            return self._modes[session_id]["mode"]
        # 尝试从 state_store 加载
        if self.state_store:
            try:
                import asyncio
                # 异步加载需要在外层处理，这里只读缓存
                pass
            except Exception:
                pass
        return "standard"

    def set_mode(self, session_id: str, mode: str, reason: str = "", task_hint: str = ""):
        """设置会话权限模式"""
        self._modes[session_id] = {
            "mode": mode,
            "reason": reason,
            "task_hint": task_hint,
            "set_at": __import__("time").time(),
        }
        logger.info(f"[Security] Mode 设置 [{session_id}]: {mode}, reason={reason}")

    def should_ask_approval(self, session_id: str, tool_name: str, arguments: Dict) -> bool:
        """判断是否需要用户确认

        策略：
        - strict 模式：所有非只读操作都需确认
        - standard 模式：shell/file_write 等危险操作需确认
        - auto 模式：只有极端危险操作需确认
        - unrestricted 模式：从不确认
        """
        mode = self.get_mode(session_id)

        if mode == "unrestricted":
            return False

        if mode == "strict":
            # strict 模式：所有修改性操作都需确认
            dangerous_tools = {"shell", "file_write", "file_delete", "directory_delete"}
            return tool_name in dangerous_tools

        if mode == "auto":
            # auto 模式：只有明确危险的命令需确认
            if tool_name == "shell":
                cmd = arguments.get("command", "")
                cmd_lower = cmd.lower()
                for pattern in DANGER_PATTERNS:
                    if re.search(pattern, cmd_lower):
                        return True
            return False

        # standard 模式（默认）
        dangerous_tools = {"shell", "file_write", "file_delete"}
        if tool_name not in dangerous_tools:
            return False

        if tool_name == "shell":
            cmd = arguments.get("command", "")
            cmd_lower = cmd.lower()
            # 检查是否是只读命令
            readonly_prefixes = ("ls", "cat", "pwd", "echo", "grep", "find", "head", "tail", "wc", "ps")
            if cmd_lower.strip().startswith(readonly_prefixes):
                return False
            # 检查危险模式
            for pattern in DANGER_PATTERNS:
                if re.search(pattern, cmd_lower):
                    return True
            # 其他 shell 命令需确认
            return True

        if tool_name == "file_write":
            # 写入敏感路径需确认
            path = arguments.get("path", "")
            sensitive_paths = ("/etc/", "/usr/", "/bin/", "/sbin/", "/lib", "/sys/", "/proc/")
            if path.startswith(sensitive_paths):
                return True
            return True  # 默认 file_write 需确认

        return False


class SecurityPipeline:
    """安全管道 —— System 1 + System 2 双层架构"""

    def __init__(
        self,
        mode_manager: Optional[ModeManager] = None,
        llm_classifier=None,  # 可选的 LLM 分类器
    ):
        self.mode_manager = mode_manager or ModeManager()
        self.llm_classifier = llm_classifier

    def intuition_check(self, task: str) -> SecurityAssessment:
        """System 1: 0ms 直觉层

        只拦截极端危险模式，其他全部放行。
        """
        task_lower = task.lower().strip()

        for pattern in DANGER_PATTERNS:
            if re.search(pattern, task_lower):
                return SecurityAssessment(
                    safety_level="dangerous",
                    suggested_mode="strict",
                    reasoning=f"检测到危险模式: {pattern}",
                    confidence=0.98,
                    source="intuition",
                )

        # 简单问候/闲聊 → skip
        if len(task) < 20 and not any(
            c in task_lower for c in ['rm', 'drop', 'delete', 'format', 'shutdown', 'kill', 'chmod']
        ):
            return SecurityAssessment(
                safety_level="safe",
                suggested_mode="standard",
                reasoning="简单消息，跳过评估",
                confidence=0.99,
                source="skip",
            )

        # 默认放行
        return SecurityAssessment(
            safety_level="safe",
            suggested_mode="standard",
            source="skip",
        )

    async def assess(self, session_id: str, task: str) -> SecurityAssessment:
        """完整安全评估 —— System 1 + System 2

        Args:
            session_id: 会话 ID
            task: 用户输入文本

        Returns:
            SecurityAssessment
        """
        # ===== System 1: 直觉层 =====
        result = self.intuition_check(task)

        if result.source == "skip":
            logger.debug(f"[Security] 跳过评估 [{session_id}]: {result.reasoning}")
            return result

        if result.source == "intuition" and result.confidence > 0.95:
            logger.info(f"[Security] 直觉拦截 [{session_id}]: {result.reasoning}")
            self._apply_mode_change(session_id, result)
            return result

        # ===== System 2: LLM 分类器（仅在直觉不确定时）=====
        if self.llm_classifier:
            try:
                llm_result = await self.llm_classifier.evaluate(task)
                result = SecurityAssessment(
                    safety_level=llm_result.safety_level,
                    suggested_mode=llm_result.suggested_mode,
                    reasoning=llm_result.reasoning,
                    confidence=llm_result.confidence,
                    source="llm",
                )
                logger.info(
                    f"[Security] LLM 评估 [{session_id}]: "
                    f"{result.safety_level} -> {result.suggested_mode}"
                )
            except Exception as e:
                logger.warning(f"[Security] LLM 评估失败: {e}")

        self._apply_mode_change(session_id, result)
        return result

    def _apply_mode_change(self, session_id: str, assessment: SecurityAssessment):
        """应用权限模式变更"""
        suggested = assessment.suggested_mode
        current = self.mode_manager.get_mode(session_id)

        # 只有建议模式比当前更严格时才降级
        should_downgrade = (
            MODE_PRIORITY.get(suggested, 1) < MODE_PRIORITY.get(current, 1)
            and assessment.confidence > 0.85
            and assessment.safety_level in ("dangerous", "critical")
        )

        if should_downgrade:
            self.mode_manager.set_mode(
                session_id,
                suggested,
                reason=assessment.reasoning,
                task_hint=assessment.reasoning[:100],
            )
            assessment.mode_changed = True
            assessment.old_mode = current
            assessment.new_mode = suggested
            logger.info(f"[Security] Mode 降级 [{session_id}]: {current} -> {suggested}")
        else:
            assessment.mode_changed = False

    def permit_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict,
        user_confirmed: bool = False,
    ) -> Dict:
        """判断工具调用是否被允许

        Returns:
            {"allowed": bool, "reason": str, "needs_approval": bool}
        """
        mode = self.mode_manager.get_mode(session_id)

        # unrestricted 模式直接放行
        if mode == "unrestricted":
            return {"allowed": True, "reason": "unrestricted mode", "needs_approval": False}

        # 检查是否需要 approval
        needs_approval = self.mode_manager.should_ask_approval(
            session_id, tool_name, arguments
        )

        if needs_approval and not user_confirmed:
            return {
                "allowed": False,
                "reason": f"工具 {tool_name} 需要用户确认",
                "needs_approval": True,
            }

        return {"allowed": True, "reason": "permitted", "needs_approval": False}
