"""Tests for ToolPoolAssembler —— 动态工具池组装"""

import pytest

from tent_os.tools.assembler import ToolPoolAssembler, ToolPoolConfig


@pytest.fixture
def assembler():
    return ToolPoolAssembler(config={})


@pytest.mark.unit
class TestToolPoolConfig:
    def test_defaults(self):
        cfg = ToolPoolConfig()
        assert cfg.enable_mcp is False
        assert cfg.enable_physical is False


@pytest.mark.unit
class TestToolPoolAssembler:
    def test_init(self, assembler):
        assert assembler._cache is not None

    def test_assemble_basic(self, assembler):
        tools = assembler.assemble(session_id="sess_1")
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_assemble_with_context(self, assembler):
        tools = assembler.assemble(
            session_id="sess_1",
            context={"mode": "strict"},
        )
        assert isinstance(tools, list)

    def test_invalidate_cache(self, assembler):
        assembler._cache["sess_1"] = ["cached"]
        assembler.invalidate_cache("sess_1")
        assert "sess_1" not in assembler._cache

    def test_has_tool(self, assembler):
        assert assembler.has_tool("nonexistent_tool", "sess_1") is False

    def test_get_tool_by_name(self, assembler):
        tool = assembler.get_tool_by_name("nonexistent", "sess_1")
        assert tool is None

    def test_get_tool_names(self, assembler):
        names = assembler.get_tool_names("sess_1")
        assert isinstance(names, list)
