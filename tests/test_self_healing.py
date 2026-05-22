"""Tests for SelfHealing —— A.3 故障自愈系统"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tent_os.autonomy.self_healing import (
    SelfHealing,
    ValidationResult,
    StateSnapshot,
    LoopPattern,
)


@pytest.fixture
def healing():
    return SelfHealing()


@pytest.mark.unit
class TestSelfValidation:
    def test_default_validation_pass(self, healing):
        result = healing.validate_result("t1", "read", {"status": "ok", "data": []})
        assert len(result) == 1
        assert result[0].valid is True

    def test_default_validation_fail_status(self, healing):
        result = healing.validate_result("t1", "read", {"status": "failed"})
        assert result[0].valid is False
        assert "failed" in result[0].reason

    def test_default_validation_fail_error(self, healing):
        result = healing.validate_result("t1", "read", {"error": "connection refused"})
        assert result[0].valid is False
        assert "connection refused" in result[0].reason

    def test_custom_validation_rule(self, healing):
        def check_price(result):
            price = result.get("price", 0)
            if price < 0:
                return ValidationResult(valid=False, rule="price_check", reason="价格为负")
            return ValidationResult(valid=True, rule="price_check", reason="价格合法")

        healing.register_validation_rule("order", check_price)
        result = healing.validate_result("t1", "order", {"price": -10})
        assert result[0].valid is False
        assert result[0].rule == "price_check"

        result = healing.validate_result("t1", "order", {"price": 100})
        assert result[0].valid is True

    def test_validation_stats(self, healing):
        healing.validate_result("t1", "read", {"status": "ok"})
        stats = healing.get_stats()
        assert stats["self_validations"] == 1


@pytest.mark.unit
class TestLoopDetection:
    def test_detect_repeat_action(self, healing):
        # 模拟同一 action+params 重复执行
        for i in range(4):
            healing.log_execution(f"t{i}", "search", {"query": "python"}, "ok")

        loop = healing.detect_loop("t5", "search", {"query": "python"})
        assert loop.detected is True
        assert loop.pattern_type == "repeat_action"
        assert loop.confidence > 0.0

    def test_no_loop_different_params(self, healing):
        healing.log_execution("t1", "search", {"query": "python"}, "ok")
        healing.log_execution("t2", "search", {"query": "java"}, "ok")

        loop = healing.detect_loop("t3", "search", {"query": "rust"})
        assert loop.detected is False

    def test_fail_retry_loop(self, healing):
        # 同一任务反复失败（用不同 params 避免触发 repeat_action）
        for i in range(5):
            healing.log_execution("t1", "write", {"path": f"/tmp/{i}"}, "failed")

        loop = healing.detect_loop("t1", "write", {"path": "/tmp/5"})
        assert loop.detected is True
        assert loop.pattern_type == "fail_retry_loop"

    def test_loop_stats(self, healing):
        for i in range(4):
            healing.log_execution(f"t{i}", "search", {"q": "x"}, "ok")
        healing.detect_loop("t5", "search", {"q": "x"})

        stats = healing.get_stats()
        assert stats["loops_detected"] == 1


@pytest.mark.unit
class TestAutoRollback:
    @pytest.mark.asyncio
    async def test_rollback_success(self, healing):
        undone_actions = []

        def undo_write(data):
            undone_actions.append("write")
            return True

        def undo_delete(data):
            undone_actions.append("delete")
            return True

        healing.register_undo("write", undo_write)
        healing.register_undo("delete", undo_delete)

        healing.take_snapshot("task1", "write", {"path": "/tmp/a.txt"})
        healing.take_snapshot("task1", "delete", {"path": "/tmp/b.txt"})

        success, undone = await healing.rollback("task1")
        assert success is True
        assert undone == ["delete", "write"]  # LIFO

    @pytest.mark.asyncio
    async def test_rollback_async_undo(self, healing):
        async def async_undo(data):
            return True

        healing.register_undo("write", async_undo)
        healing.take_snapshot("task1", "write", {"path": "/tmp/a.txt"})

        success, undone = await healing.rollback("task1")
        assert success is True
        assert "write" in undone

    @pytest.mark.asyncio
    async def test_rollback_no_snapshots(self, healing):
        success, undone = await healing.rollback("no_such_task")
        assert success is True
        assert undone == []

    def test_clear_snapshots(self, healing):
        healing.take_snapshot("task1", "write", {"path": "/tmp/a.txt"})
        healing.clear_snapshots("task1")

        stats = healing.get_stats()
        assert stats["active_snapshots"] == 0

    def test_snapshot_stats(self, healing):
        healing.take_snapshot("t1", "write", {})
        healing.take_snapshot("t1", "delete", {})
        stats = healing.get_stats()
        assert stats["active_snapshots"] == 2


@pytest.mark.unit
class TestOriginalHealing:
    @pytest.mark.asyncio
    async def test_handle_failure_retry_success(self, healing):
        executor = AsyncMock(return_value="success")
        result = await healing.handle_failure("t1", "error", executor, {"x": 1})
        assert result.success is True
        assert "retry" in result.action_taken

    @pytest.mark.asyncio
    async def test_handle_failure_escalation(self, healing):
        executor = AsyncMock(side_effect=Exception("always fail"))
        # 模拟多次失败
        for i in range(10):
            await healing.handle_failure("t1", "error", executor, {"x": 1})

        result = await healing.handle_failure("t1", "error", executor, {"x": 1})
        assert result.escalation_required is True

    def test_circuit_breaker(self, healing):
        for i in range(6):
            if f"t1" not in healing._failure_history:
                healing._failure_history["t1"] = []
            healing._failure_history["t1"].append(__import__('datetime').datetime.now())

        assert healing.is_circuit_open("t1", threshold=5) is True
        assert healing.is_circuit_open("t1", threshold=10) is False

    def test_reset_circuit(self, healing):
        healing._failure_history["t1"] = [__import__('datetime').datetime.now()]
        healing.reset_circuit("t1")
        assert "t1" not in healing._failure_history

    def test_get_stats(self, healing):
        stats = healing.get_stats()
        assert "total_attempts" in stats
        assert "active_snapshots" in stats
