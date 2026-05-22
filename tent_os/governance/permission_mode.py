"""Permission Mode 系统 —— Claude Code 模式融合

四档 Permission Mode：
- strict:     只允许只读操作（file_read, directory_list, web_search）
- standard:   标准开发模式（shell, file_read/write, http_request, browser）
- auto:       自动评估模式（由 Auto-Mode Classifier 动态决定）
- unrestricted: 完全开放（所有工具，包括物理执行器）

关键设计：
1. Mode 是可变的 —— 同一会话中可以根据任务动态切换
2. Mode 切换需要理由 —— 记录在审计日志中
3. Mode 不跨会话持久化 —— 新会话默认 standard
4. deny 永远覆盖 allow —— 无论 mode 如何，deny_list 始终生效

使用方式：
    mode_mgr = PermissionModeManager(config)
    mode = mode_mgr.get_mode(session_id)  # "standard"
    
    # 根据任务自动评估是否需要升级
    new_mode = await mode_mgr.evaluate_task(session_id, "帮我删除所有日志文件")
    # -> 可能返回 "standard"（需要审批）或保持当前 mode
"""

import time
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class PermissionMode(Enum):
    """权限模式枚举"""
    STRICT = "strict"
    STANDARD = "standard"
    AUTO = "auto"
    UNRESTRICTED = "unrestricted"


# Mode -> 允许的工具名集合
MODE_TOOL_ALLOWLIST = {
    PermissionMode.STRICT: {
        "file_read", "directory_list", "web_search", "web_fetch",
        "memory_search", "memory_get",
    },
    PermissionMode.STANDARD: {
        "shell", "file_read", "file_write", "directory_list",
        "http_request", "web_search", "web_fetch",
        "memory_search", "memory_get",
        "browser_navigate", "browser_click", "browser_type",
        "browser_read", "browser_screenshot",
        "render_ppt", "render_excel", "render_word",
        "render_document", "render_contract", "render_webpage",
        # FIX: 物理执行者调度工具
        "scheduler_dispatch", "realman", "flashex",
    },
    PermissionMode.AUTO: None,  # 由 Auto-Mode Classifier 动态决定
    PermissionMode.UNRESTRICTED: None,  # 所有工具
}

# 危险操作关键词 -> 需要的最低 mode
DANGEROUS_PATTERNS = {
    # 删除操作
    "rm ": PermissionMode.STANDARD,
    "rmdir": PermissionMode.STANDARD,
    "delete": PermissionMode.STANDARD,
    "drop": PermissionMode.STANDARD,
    # 系统级操作
    "sudo": PermissionMode.UNRESTRICTED,
    "chmod 777": PermissionMode.UNRESTRICTED,
    "mkfs": PermissionMode.UNRESTRICTED,
    "fdisk": PermissionMode.UNRESTRICTED,
    # 网络危险
    "curl.*-X DELETE": PermissionMode.STANDARD,
    # 物理操作
    "realman": PermissionMode.UNRESTRICTED,
    "flashex": PermissionMode.UNRESTRICTED,
}


@dataclass
class ModeTransition:
    """模式转换记录"""
    from_mode: str
    to_mode: str
    reason: str
    timestamp: float
    task_hint: str = ""
    approved: bool = False  # 是否需要审批


class PermissionModeManager:
    """权限模式管理器

    管理每个会话的 Permission Mode，支持：
    1. 查询当前 mode
    2. 根据任务评估是否需要切换 mode
    3. 手动切换 mode（带审计）
    4. 检查工具是否在允许列表中
    """

    def __init__(self, config: Dict[str, Any] = None,
                 state_store=None,
                 jsonl_logger=None):
        self.config = config or {}
        self.state_store = state_store
        self.jsonl_logger = jsonl_logger

        # 全局默认 mode
        self.default_mode = self.config.get("security", {}).get(
            "permission_mode", "standard"
        )

        # 会话级 mode 缓存（不持久化，进程内缓存）
        self._session_modes: Dict[str, str] = {}

        # 转换历史（每会话）
        self._transition_history: Dict[str, List[ModeTransition]] = {}

        # 自动评估配置
        self.auto_evaluate = self.config.get("security", {}).get(
            "auto_mode_evaluate", True
        )

    def get_mode(self, session_id: str) -> str:
        """获取会话的当前 Permission Mode

        优先顺序：
        1. 内存缓存
        2. Redis state_store（如果可用）
        3. 全局默认
        """
        # 1. 内存缓存
        if session_id in self._session_modes:
            return self._session_modes[session_id]

        # 2. 尝试从 state_store 加载（但 mode 不跨会话持久化）
        # 新会话始终使用默认 mode
        mode = self.default_mode
        self._session_modes[session_id] = mode
        return mode

    def set_mode(self, session_id: str, mode: str, reason: str = "",
                 task_hint: str = "", approved: bool = False) -> bool:
        """手动设置会话的 Permission Mode

        Args:
            session_id: 会话ID
            mode: 目标 mode (strict/standard/auto/unrestricted)
            reason: 切换原因
            task_hint: 触发切换的任务描述
            approved: 是否已获审批（unrestricted 需要审批）

        Returns:
            是否成功切换
        """
        if mode not in ("strict", "standard", "auto", "unrestricted"):
            logger.warning(f"[Mode] 无效的 mode: {mode}")
            return False

        old_mode = self._session_modes.get(session_id, self.default_mode)

        # unrestricted 需要审批
        if mode == "unrestricted" and not approved:
            logger.warning(f"[Mode] 切换到 unrestricted 需要审批 [{session_id}]")
            return False

        # 记录转换
        transition = ModeTransition(
            from_mode=old_mode,
            to_mode=mode,
            reason=reason,
            timestamp=time.time(),
            task_hint=task_hint,
            approved=approved,
        )

        if session_id not in self._transition_history:
            self._transition_history[session_id] = []
        self._transition_history[session_id].append(transition)

        # 更新 mode
        self._session_modes[session_id] = mode

        logger.info(f"[Mode] 权限切换 [{session_id}]: {old_mode} -> {mode} ({reason})")

        # 审计日志
        if self.jsonl_logger:
            asyncio = __import__("asyncio")
            asyncio.create_task(self.jsonl_logger.log_security(
                event="audit.permission_change",
                session_id=session_id,
                action="mode_change",
                reason=f"{old_mode} -> {mode}: {reason}",
                old_mode=old_mode,
                new_mode=mode,
            ))

        return True

    async def evaluate_task(self, session_id: str, task: str,
                            auto_classifier=None) -> str:
        """根据任务评估是否需要切换 mode

        策略：
        1. 检查任务中是否包含危险操作关键词
        2. 如果当前 mode 不足以支持，建议升级（但不自动升级）
        3. 如果 auto_classifier 可用，用 LLM 做更精细的评估

        Returns:
            建议的 mode（不一定切换）
        """
        current_mode = self.get_mode(session_id)
        task_lower = task.lower()

        # 1. 关键词启发式评估
        required_mode = self._evaluate_by_keywords(task_lower)

        # 2. 如果 auto_classifier 可用，做 LLM 评估
        if auto_classifier and required_mode == PermissionMode.STANDARD:
            llm_required = await auto_classifier.evaluate(task)
            if llm_required == "unrestricted":
                required_mode = PermissionMode.UNRESTRICTED

        # 3. 比较当前 mode 和所需 mode
        mode_priority = {
            "strict": 0,
            "standard": 1,
            "auto": 2,
            "unrestricted": 3,
        }

        current_priority = mode_priority.get(current_mode, 1)
        required_priority = mode_priority.get(required_mode.value, 1)

        if required_priority > current_priority:
            # 需要升级，但不自动执行（返回建议）
            logger.info(
                f"[Mode] 任务需要更高权限 [{session_id}]: "
                f"当前={current_mode}, 建议={required_mode.value}"
            )
            return required_mode.value

        return current_mode

    def is_tool_allowed(self, tool_name: str, session_id: str) -> bool:
        """检查工具是否在当前 mode 下允许使用"""
        mode_str = self.get_mode(session_id)

        # unrestricted 允许所有
        if mode_str == "unrestricted":
            return True

        # 获取允许列表
        mode_enum = PermissionMode(mode_str)
        allowed = MODE_TOOL_ALLOWLIST.get(mode_enum)

        if allowed is None:
            # auto mode：暂时允许所有，由 classifier 在运行时拦截
            return True

        return tool_name in allowed

    def get_allowed_tools(self, session_id: str) -> Set[str]:
        """获取当前 mode 下允许的工具名集合"""
        mode_str = self.get_mode(session_id)

        if mode_str == "unrestricted":
            return None  # 表示所有工具

        mode_enum = PermissionMode(mode_str)
        allowed = MODE_TOOL_ALLOWLIST.get(mode_enum)

        if allowed is None:
            return None  # auto mode

        return allowed.copy()

    def get_transitions(self, session_id: str) -> List[Dict]:
        """获取会话的模式转换历史"""
        history = self._transition_history.get(session_id, [])
        return [
            {
                "from": t.from_mode,
                "to": t.to_mode,
                "reason": t.reason,
                "timestamp": t.timestamp,
                "task_hint": t.task_hint,
            }
            for t in history
        ]

    def _evaluate_by_keywords(self, task_lower: str) -> PermissionMode:
        """通过关键词评估需要的 Permission Mode"""
        # 检查是否包含危险操作
        for pattern, required_mode in DANGEROUS_PATTERNS.items():
            import re
            if re.search(pattern, task_lower):
                return required_mode

        # 默认标准模式
        return PermissionMode.STANDARD

    def reset_session(self, session_id: str):
        """重置会话 mode（会话结束时调用）"""
        self._session_modes.pop(session_id, None)
        self._transition_history.pop(session_id, None)
