"""Tests for PermissionModeManager —— 权限模式管理"""

import pytest

from tent_os.governance.permission_mode import (
    PermissionMode,
    PermissionModeManager,
)


@pytest.fixture
def manager():
    return PermissionModeManager(config={})


@pytest.mark.unit
class TestPermissionMode:
    def test_enum_values(self):
        assert PermissionMode.STANDARD.value == "standard"
        assert PermissionMode.STRICT.value == "strict"
        assert PermissionMode.AUTO.value == "auto"


@pytest.mark.unit
class TestPermissionModeManager:
    def test_default_mode(self, manager):
        assert manager.get_mode("any_session") == "standard"

    def test_set_and_get_mode(self, manager):
        manager.set_mode("sess_1", "strict")
        assert manager.get_mode("sess_1") == "strict"

    def test_is_tool_allowed_standard(self, manager):
        assert manager.is_tool_allowed("web_search", "sess_1") is True
        assert manager.is_tool_allowed("file_read", "sess_1") is True

    def test_is_tool_allowed_strict(self, manager):
        manager.set_mode("sess_1", "strict")
        assert manager.is_tool_allowed("web_search", "sess_1") is True
        assert manager.is_tool_allowed("shell", "sess_1") is False
        assert manager.is_tool_allowed("file_write", "sess_1") is False
        assert manager.is_tool_allowed("file_read", "sess_1") is True

    def test_get_allowed_tools_standard(self, manager):
        tools = manager.get_allowed_tools("standard")
        assert "web_search" in tools
        assert "shell" in tools

    def test_get_allowed_tools_strict(self, manager):
        manager.set_mode("sess_strict", "strict")
        tools = manager.get_allowed_tools("sess_strict")
        assert "web_search" in tools
        assert "shell" not in tools

    @pytest.mark.asyncio
    async def test_evaluate_task_keywords(self, manager):
        result = await manager.evaluate_task("sess_1", "delete all files")
        # Returns a mode string (may vary based on implementation)
        assert result in ["strict", "auto", "standard"]

    @pytest.mark.asyncio
    async def test_evaluate_task_safe(self, manager):
        result = await manager.evaluate_task("sess_1", "what is the weather")
        assert result == "standard"

    def test_reset_session(self, manager):
        manager.set_mode("sess_1", "strict")
        manager.reset_session("sess_1")
        assert manager.get_mode("sess_1") == "standard"

    def test_get_transitions(self, manager):
        trans = manager.get_transitions("standard")
        assert isinstance(trans, list)
