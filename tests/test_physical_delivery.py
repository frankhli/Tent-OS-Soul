"""Tests for PhysicalDeliveryExecutor —— 物理触达执行器"""

import pytest

from tent_os.scheduler.executors.physical import (
    PhysicalDeliveryExecutor,
    PhysicalProvider,
    PhysicalTask,
)


@pytest.fixture
def physical_executor():
    return PhysicalDeliveryExecutor(config={
        "circuit_threshold": 2,
        "circuit_reset_seconds": 1,
    })


@pytest.mark.unit
class TestPhysicalDeliveryExecutor:

    def test_supported_actions(self, physical_executor):
        actions = physical_executor.supported_actions()
        assert "deliver" in actions
        assert "retrieve" in actions
        assert "notify" in actions
        assert "realman" in actions
        assert "flashex" in actions

    @pytest.mark.asyncio
    async def test_deliver_mock(self, physical_executor):
        """模拟交付任务"""
        result = await physical_executor.execute("deliver", {
            "target_location": "Room 101",
            "item_description": "Coffee",
            "priority": "normal",
        })
        assert result["status"] == "completed"
        assert result["provider"] == PhysicalProvider.REALMAN_ROBOT.value
        assert "elapsed_seconds" in result

    @pytest.mark.asyncio
    async def test_fallback_chain(self, physical_executor):
        """测试自动降级切换"""
        # 强制打开机器人熔断器
        physical_executor._circuit_open[PhysicalProvider.REALMAN_ROBOT] = True
        physical_executor._last_failure_time[PhysicalProvider.REALMAN_ROBOT] = __import__('time').time()

        result = await physical_executor.execute("deliver", {
            "target_location": "Room 202",
            "item_description": "Documents",
        })
        assert result["status"] == "completed"
        # 应该 fallback 到 flashex
        assert result["provider"] == PhysicalProvider.FLASHEx.value

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, physical_executor):
        """测试熔断器"""
        provider = PhysicalProvider.REALMAN_ROBOT
        assert not physical_executor._is_circuit_open(provider)

        physical_executor._record_failure(provider)
        physical_executor._record_failure(provider)
        assert physical_executor._is_circuit_open(provider)

        # 测试成功后重置
        physical_executor._record_success(provider)
        assert not physical_executor._is_circuit_open(provider)

    def test_task_creation(self):
        task = PhysicalTask(
            task_id="test_001",
            action="deliver",
            target_location="Room 101",
            item_description="Coffee",
        )
        assert task.status == "pending"
        assert task.retry_count == 0
        assert PhysicalProvider.REALMAN_ROBOT in task.fallback_chain

    @pytest.mark.asyncio
    async def test_get_status(self, physical_executor):
        result = await physical_executor.execute("deliver", {
            "target_location": "Room 303",
            "item_description": "Package",
            "task_id": "status_test_001",
        })
        status = await physical_executor.get_status("status_test_001")
        assert status is not None
        assert status["status"] in ("completed", "failed")
        assert "provider" in status

    @pytest.mark.asyncio
    async def test_notify_action(self, physical_executor):
        result = await physical_executor.execute("notify", {
            "target_location": "admin@company.com",
            "item_description": "System alert",
        })
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_all_providers_failed(self, physical_executor):
        """所有 provider 都熔断时的降级"""
        for provider in PhysicalProvider:
            physical_executor._circuit_open[provider] = True
            physical_executor._last_failure_time[provider] = __import__('time').time()

        result = await physical_executor.execute("deliver", {
            "target_location": "Room 404",
            "item_description": "Important",
            "max_retries": 0,
        })
        assert result["status"] == "failed"
        assert "所有物理执行者都失败" in result["error"]
