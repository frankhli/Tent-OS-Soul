"""Tests for SubagentSpawner —— 动态子代理生命周期管理"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from tent_os.governance.subagent import (
    SubagentSpawner,
    SubagentConfig,
    SubagentType,
    BUILTIN_AGENT_CONFIGS,
)


@pytest.fixture
def spawner(mock_bus, mock_llm):
    return SubagentSpawner(bus=mock_bus, llm=mock_llm)


@pytest.mark.unit
class TestSubagentSpawner:

    def test_load_custom_agents_empty(self, spawner, tmp_path):
        with patch.object(Path, "exists", return_value=False):
            spawner._load_custom_agents()
        assert len(spawner._custom_configs) == 0

    def test_get_config_builtin_research(self, spawner):
        cfg = spawner._get_config("research")
        assert cfg.name == "ResearchAgent"
        assert "web_search" in cfg.allowed_tools

    def test_get_config_builtin_code(self, spawner):
        cfg = spawner._get_config("code")
        assert cfg.name == "CodeAgent"
        assert "shell" in cfg.allowed_tools

    def test_get_config_builtin_verify(self, spawner):
        cfg = spawner._get_config("verify")
        assert cfg.name == "VerifyAgent"
        assert "web_search" in cfg.allowed_tools

    def test_get_config_unknown_returns_default(self, spawner):
        cfg = spawner._get_config("unknown_type")
        assert cfg.name == "CustomAgent-unknown_type"
        assert "shell" in cfg.allowed_tools

    def test_get_config_custom_override(self, spawner):
        override = {"max_iterations": 5, "timeout_seconds": 30}
        cfg = spawner._get_config("research", custom_config=override)
        assert cfg.name == "ResearchAgent"

    @pytest.mark.asyncio
    async def test_spawn_returns_agent_id(self, spawner):
        agent_id = await spawner.spawn(
            parent_session="parent_1",
            agent_type="research",
            task="study python",
        )
        assert agent_id.startswith("agent_research_")
        assert agent_id in spawner._agent_states
        assert spawner._agent_states[agent_id].status in ("pending", "running")
        if agent_id in spawner._active_tasks:
            spawner._active_tasks[agent_id].cancel()
            try:
                await spawner._active_tasks[agent_id]
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_get_status_existing(self, spawner):
        agent_id = await spawner.spawn(
            parent_session="parent_1",
            agent_type="verify",
            task="check facts",
        )
        status = spawner.get_status(agent_id)
        assert status is not None
        assert status["agent_id"] == agent_id
        assert status["parent_session"] == "parent_1"
        assert status["agent_type"] == "verify"
        assert "elapsed_seconds" in status
        if agent_id in spawner._active_tasks:
            spawner._active_tasks[agent_id].cancel()
            try:
                await spawner._active_tasks[agent_id]
            except asyncio.CancelledError:
                pass

    def test_get_status_missing(self, spawner):
        assert spawner.get_status("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_active(self, spawner):
        agent_id = await spawner.spawn(
            parent_session="parent_2",
            agent_type="code",
            task="write tests",
        )
        active = spawner.list_active()
        assert len(active) >= 1
        assert any(a["agent_id"] == agent_id for a in active)

        filtered = spawner.list_active(parent_session="parent_2")
        assert any(a["agent_id"] == agent_id for a in filtered)

        filtered_empty = spawner.list_active(parent_session="no_one")
        assert all(a["parent_session"] != "parent_2" for a in filtered_empty)
        if agent_id in spawner._active_tasks:
            spawner._active_tasks[agent_id].cancel()
            try:
                await spawner._active_tasks[agent_id]
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_cancel(self, spawner):
        agent_id = await spawner.spawn(
            parent_session="parent_1",
            agent_type="research",
            task="long task",
        )
        ok = await spawner.cancel(agent_id)
        assert ok is True
        assert spawner._agent_states[agent_id].status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_missing(self, spawner):
        ok = await spawner.cancel("nonexistent")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_stats(self, spawner):
        stats = spawner.get_stats()
        assert stats["total_spawned"] == 0
        assert stats["success_rate"] == 0.0

        agent_id = await spawner.spawn(
            parent_session="parent_1",
            agent_type="research",
            task="study",
        )
        stats = spawner.get_stats()
        assert stats["total_spawned"] == 1
        assert stats["active"] >= 1
        if agent_id in spawner._active_tasks:
            spawner._active_tasks[agent_id].cancel()
            try:
                await spawner._active_tasks[agent_id]
            except asyncio.CancelledError:
                pass
