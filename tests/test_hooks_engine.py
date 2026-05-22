"""Tests for HookEngine —— 17事件点Hook系统"""

import pytest
from unittest.mock import AsyncMock

from tent_os.hooks.engine import HookEngine, HookResult, Hook, HookType


@pytest.fixture
def engine():
    return HookEngine()


@pytest.mark.unit
class TestHookEngine:
    @pytest.mark.asyncio
    async def test_register_and_trigger(self, engine):
        handler = AsyncMock(return_value=HookResult(allowed=True))
        hook = Hook(name="test_hook", event="tool.preuse", hook_type=HookType.ASYNC, handler=handler)
        engine.register(hook)

        result = await engine.trigger("tool.preuse", "sess_1", data={"tool": "ls"})
        assert result.allowed is True
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_no_hooks(self, engine):
        result = await engine.trigger("tool.preuse", "sess_1", data={"tool": "ls"})
        assert result.allowed is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_trigger_hook_denies(self, engine):
        handler = AsyncMock(return_value=HookResult(allowed=False, error="blocked"))
        hook = Hook(name="blocker", event="tool.preuse", hook_type=HookType.ASYNC, handler=handler)
        engine.register(hook)

        result = await engine.trigger("tool.preuse", "sess_1", data={"tool": "rm"})
        assert result.allowed is False
        assert "blocked" in result.error

    @pytest.mark.asyncio
    async def test_trigger_multiple_hooks_priority(self, engine):
        calls = []

        async def h1(*args, **kwargs):
            calls.append("h1")
            return HookResult(allowed=True)

        async def h2(*args, **kwargs):
            calls.append("h2")
            return HookResult(allowed=True)

        engine.register(Hook(name="second", event="session.start", hook_type=HookType.ASYNC, handler=h2, priority=0))
        engine.register(Hook(name="first", event="session.start", hook_type=HookType.ASYNC, handler=h1, priority=10))

        await engine.trigger("session.start", "sess_1", data={})
        assert calls[0] == "h1"
        assert calls[1] == "h2"

    @pytest.mark.asyncio
    async def test_trigger_handler_receives_event(self, engine):
        received = {}
        async def capture(event):
            received["name"] = event.name
            received["data"] = dict(event.data)
            return HookResult(allowed=True)

        engine.register(Hook(name="cap", event="tool.preuse", hook_type=HookType.ASYNC, handler=capture))
        result = await engine.trigger("tool.preuse", "sess_1", data={"tool": "ls"})
        assert result.allowed is True
        assert received["name"] == "tool.preuse"

    @pytest.mark.asyncio
    async def test_trigger_fire_and_forget(self, engine):
        handler = AsyncMock(return_value=HookResult(allowed=True))
        engine.register(Hook(name="cleanup", event="session.end", hook_type=HookType.ASYNC, handler=handler))

        await engine.trigger_fire_and_forget("session.end", "sess_1", data={})

    def test_unregister(self, engine):
        engine.register(Hook(name="h1", event="tool.preuse", hook_type=HookType.ASYNC, handler=AsyncMock()))
        engine.unregister("h1")
        assert "h1" not in [h.name for h in engine._hooks.get("tool.preuse", [])]

    def test_list_hooks(self, engine):
        engine.register(Hook(name="h1", event="tool.preuse", hook_type=HookType.ASYNC, handler=AsyncMock()))
        engine.register(Hook(name="h2", event="tool.postuse", hook_type=HookType.ASYNC, handler=AsyncMock()))
        hooks = engine.list_hooks()
        assert len(hooks) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self, engine):
        engine.register(Hook(name="h1", event="tool.preuse", hook_type=HookType.ASYNC, handler=AsyncMock(return_value=HookResult(allowed=True))))
        await engine.trigger("tool.preuse", "sess_1", data={"tool": "ls"})
        stats = engine.get_stats()
        assert len(stats) > 0

    def test_create_audit_hook(self, engine):
        hook = engine.create_audit_hook(None)
        assert hook is not None

    def test_create_cost_hook(self, engine):
        def cb(data): pass
        hook = engine.create_cost_hook(cb)
        assert hook is not None
