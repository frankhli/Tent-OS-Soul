"""Tests for LayeredSecurity —— 7层独立安全架构"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from tent_os.governance.safety.layered_security import (
    LayeredSecurity,
    SecurityResult,
)


@pytest.fixture
def mock_mode_manager():
    mm = MagicMock()
    mm.is_tool_allowed.return_value = True
    mm.get_mode.return_value = "standard"
    return mm


@pytest.fixture
def mock_policy_engine():
    pe = MagicMock()
    pe.evaluate.return_value = {
        "decision": "allow",
        "reason": "策略通过",
        "rule": "default",
        "eval_time_ms": 5.0,
    }
    return pe


@pytest.fixture
def mock_auto_classifier():
    ac = AsyncMock()
    result = MagicMock()
    result.safety_level = "safe"
    result.reasoning = "无风险"
    result.confidence = 0.5
    result.risks = []
    result.eval_time_ms = 10.0
    ac.evaluate.return_value = result
    return ac


@pytest.fixture
def mock_hook_engine():
    he = AsyncMock()
    result = MagicMock()
    result.allowed = True
    result.error = None
    result.latency_ms = 2.0
    result.modified = False
    he.trigger.return_value = result
    return he


@pytest.fixture
def security(mock_policy_engine, mock_mode_manager, mock_auto_classifier, mock_hook_engine):
    config = {"security": {"auto_classifier": True}}
    return LayeredSecurity(
        config=config,
        policy_engine=mock_policy_engine,
        mode_manager=mock_mode_manager,
        auto_classifier=mock_auto_classifier,
        hook_engine=mock_hook_engine,
    )


@pytest.mark.unit
class TestLayeredSecurity:

    @pytest.mark.asyncio
    async def test_evaluate_all_layers_allow(self, security):
        result = await security.evaluate_tool_call("sess_1", "web_search", {"query": "pytest"})
        assert result.allowed is True
        assert result.layer == "all"
        assert "所有安全层通过" in result.reason
        assert security._stats["total_evaluations"] == 1
        assert security._stats["allowed"] == 1

    @pytest.mark.asyncio
    async def test_l1_prefilter_denies_non_allowed_tool(self, security, mock_mode_manager):
        mock_mode_manager.is_tool_allowed.return_value = False
        result = await security.evaluate_tool_call("sess_1", "danger_tool", {})
        assert result.allowed is False
        assert result.layer == "L1"
        assert "不在当前 mode 允许列表中" in result.reason
        assert security._stats["denied"] == 1
        assert security._stats["layer_triggers"]["L1"] == 1

    @pytest.mark.asyncio
    async def test_l2_policy_deny(self, security, mock_policy_engine):
        mock_policy_engine.evaluate.return_value = {
            "decision": "deny",
            "reason": "高危操作需审批",
            "rule": "no_rm_rf",
            "eval_time_ms": 3.0,
        }
        result = await security.evaluate_tool_call("sess_1", "shell", {"command": "rm -rf /"})
        assert result.allowed is False
        assert result.layer == "L2"
        assert "高危操作需审批" in result.reason
        assert security._stats["layer_triggers"]["L2"] == 1

    @pytest.mark.asyncio
    async def test_l2_policy_require_approval(self, security, mock_policy_engine):
        mock_policy_engine.evaluate.return_value = {
            "decision": "require_approval",
            "reason": "需要管理员审批",
            "rule": "admin_only",
            "eval_time_ms": 4.0,
        }
        result = await security.evaluate_tool_call("sess_1", "file_write", {"path": "/etc/passwd"})
        assert result.allowed is False
        assert result.decision == "require_approval"
        assert result.layer == "L2"

    @pytest.mark.asyncio
    async def test_l2_policy_circuit_break(self, security, mock_policy_engine):
        mock_policy_engine.evaluate.return_value = {
            "decision": "circuit_break",
            "reason": "执行者已熔断",
            "eval_time_ms": 1.0,
        }
        result = await security.evaluate_tool_call("sess_1", "shell", {"command": "ls"})
        assert result.allowed is False
        assert result.decision == "circuit_break"
        assert result.layer == "L2"

    @pytest.mark.asyncio
    async def test_l3_mode_strict_blocks_write_tools(self, security, mock_mode_manager):
        mock_mode_manager.get_mode.return_value = "strict"
        result = await security.evaluate_tool_call("sess_1", "shell", {"command": "echo hi"})
        assert result.allowed is False
        assert result.layer == "L3"
        assert "strict mode 下不允许使用" in result.reason
        assert security._stats["layer_triggers"]["L3"] == 1

    @pytest.mark.asyncio
    async def test_l3_mode_strict_allows_readonly(self, security, mock_mode_manager):
        mock_mode_manager.get_mode.return_value = "strict"
        result = await security.evaluate_tool_call("sess_1", "file_read", {"path": "/tmp/a.txt"})
        assert result.allowed is True
        assert result.layer == "all"

    @pytest.mark.asyncio
    async def test_l4_classifier_critical_deny(self, security, mock_auto_classifier):
        result = MagicMock()
        result.safety_level = "critical"
        result.reasoning = "检测到不可逆操作"
        result.confidence = 0.95
        result.risks = ["data_loss"]
        result.eval_time_ms = 12.0
        mock_auto_classifier.evaluate.return_value = result

        res = await security.evaluate_tool_call("sess_1", "file_delete", {"path": "*"}, task_context="delete all")
        assert res.allowed is False
        assert res.layer == "L4"
        assert "Auto-Classifier" in res.reason
        assert res.metadata["safety_level"] == "critical"
        assert security._stats["layer_triggers"]["L4"] == 1

    @pytest.mark.asyncio
    async def test_l4_classifier_dangerous_high_confidence(self, security, mock_auto_classifier):
        result = MagicMock()
        result.safety_level = "dangerous"
        result.reasoning = "高风险"
        result.confidence = 0.85
        result.risks = ["system_damage"]
        result.eval_time_ms = 8.0
        mock_auto_classifier.evaluate.return_value = result

        res = await security.evaluate_tool_call("sess_1", "shell", {"command": "fdisk"}, task_context="partition")
        assert res.allowed is False
        assert res.layer == "L4"
        assert "高风险操作" in res.reason

    @pytest.mark.asyncio
    async def test_l4_classifier_safe_passes(self, security, mock_auto_classifier):
        result = MagicMock()
        result.safety_level = "safe"
        result.reasoning = "安全"
        result.confidence = 0.3
        result.eval_time_ms = 6.0
        mock_auto_classifier.evaluate.return_value = result

        res = await security.evaluate_tool_call("sess_1", "web_search", {"query": "x"}, task_context="search")
        assert res.allowed is True
        assert res.layer == "all"

    @pytest.mark.asyncio
    async def test_l5_sandbox_physical_executor(self, security):
        result = await security.evaluate_tool_call("sess_1", "realman", {"action": "move"})
        assert result.allowed is False
        assert result.layer == "L5"
        assert "物理操作需要人工确认" in result.reason
        assert result.metadata["executor_type"] == "physical"

    @pytest.mark.asyncio
    async def test_l5_sandbox_dangerous_shell(self, security):
        result = await security.evaluate_tool_call("sess_1", "shell", {"command": "rm -rf /data"})
        assert result.allowed is False
        assert result.layer == "L5"
        assert "检测到高危命令模式" in result.reason

    @pytest.mark.asyncio
    async def test_l5_sandbox_safe_shell(self, security):
        result = await security.evaluate_tool_call("sess_1", "shell", {"command": "ls -la"})
        assert result.allowed is True
        assert result.layer == "all"

    @pytest.mark.asyncio
    async def test_l6_restoration_always_passes(self, security):
        result = await security.evaluate_tool_call("sess_1", "web_search", {"query": "x"})
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_l7_hooks_interception(self, security, mock_hook_engine):
        hook_result = MagicMock()
        hook_result.allowed = False
        hook_result.error = "敏感操作被拦截"
        hook_result.latency_ms = 7.0
        hook_result.modified = False
        mock_hook_engine.trigger.return_value = hook_result

        result = await security.evaluate_tool_call("sess_1", "file_write", {"path": "/secret"})
        assert result.allowed is False
        assert result.layer == "L7"
        assert "Hook 拦截" in result.reason
        assert "敏感操作被拦截" in result.reason
        assert security._stats["layer_triggers"]["L7"] == 1

    @pytest.mark.asyncio
    async def test_l7_hooks_passes(self, security, mock_hook_engine):
        hook_result = MagicMock()
        hook_result.allowed = True
        hook_result.error = None
        hook_result.latency_ms = 3.0
        hook_result.modified = True
        mock_hook_engine.trigger.return_value = hook_result

        result = await security.evaluate_tool_call("sess_1", "web_search", {"query": "x"})
        assert result.allowed is True
        assert result.layer == "all"

    def test_get_stats(self, security):
        assert security.get_stats()["total_evaluations"] == 0
        assert security.get_stats()["allow_rate"] == 0.0
