"""Tests for SpeculativeExecutor —— 推测执行引擎"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from tent_os.governance.speculative import (
    SpeculativeExecutor,
    SpeculativeIntent,
    READONLY_TOOLS,
)


@pytest.fixture
def mock_tool_executor():
    return AsyncMock()


@pytest.fixture
def speculative(mock_tool_executor):
    return SpeculativeExecutor(tool_executor=mock_tool_executor)


@pytest.mark.unit
class TestSpeculativeExecutor:

    def test_detect_intent_file_read(self, speculative):
        intent = speculative.detect_intent("让我看看 config.yaml 文件")
        assert intent is not None
        assert intent.tool == "file_read"
        assert "path" in intent.params
        assert intent.confidence == 0.7

    def test_detect_intent_web_search(self, speculative):
        intent = speculative.detect_intent("搜索 pytest asyncio 最佳实践")
        assert intent is not None
        assert intent.tool == "web_search"
        assert "query" in intent.params

    def test_detect_intent_web_fetch(self, speculative):
        intent = speculative.detect_intent("抓取 https://example.com/data")
        assert intent is not None
        assert intent.tool == "web_fetch"
        assert intent.params.get("url") == "https://example.com/data"

    def test_detect_intent_directory_list(self, speculative):
        intent = speculative.detect_intent("列出 /tmp 目录下的文件")
        assert intent is not None
        assert intent.tool == "directory_list"
        assert "path" in intent.params

    def test_detect_intent_no_match(self, speculative):
        intent = speculative.detect_intent("你好")
        assert intent is None

    def test_detect_intent_too_short(self, speculative):
        intent = speculative.detect_intent("hi")
        assert intent is None

    @pytest.mark.asyncio
    async def test_execute_if_safe_readonly(self, speculative, mock_tool_executor):
        mock_tool_executor.execute.return_value = "file content"
        intent = SpeculativeIntent(
            tool="file_read",
            params={"path": "/tmp/test.txt"},
            confidence=0.7,
            source_text="看看 /tmp/test.txt",
        )
        task = await speculative.execute_if_safe(intent, session_id="sess_1")
        assert task is not None
        await task
        assert speculative._stats["executed"] == 1
        assert speculative._stats["intents_detected"] == 1
        mock_tool_executor.execute.assert_awaited_once_with("file_read", {"path": "/tmp/test.txt"}, session_id="sess_1")

    @pytest.mark.asyncio
    async def test_execute_if_safe_non_readonly_skipped(self, speculative):
        intent = SpeculativeIntent(
            tool="shell",
            params={"command": "rm -rf /"},
            confidence=0.7,
            source_text="run shell",
        )
        result = await speculative.execute_if_safe(intent, session_id="sess_1")
        assert result is None
        assert speculative._stats["executed"] == 0

    @pytest.mark.asyncio
    async def test_execute_if_safe_deduplication(self, speculative, mock_tool_executor):
        mock_tool_executor.execute.return_value = "content"
        intent = SpeculativeIntent(
            tool="file_read",
            params={"path": "/tmp/a.txt"},
            confidence=0.7,
            source_text="read a",
        )
        first = await speculative.execute_if_safe(intent, session_id="sess_1")
        assert first is not None
        await first
        second = await speculative.execute_if_safe(intent, session_id="sess_1")
        assert second is None
        assert speculative._stats["executed"] == 1

    @pytest.mark.asyncio
    async def test_execute_if_safe_concurrent_limit(self, speculative, mock_tool_executor):
        speculative.max_concurrent = 1
        mock_tool_executor.execute.return_value = "content"
        intent = SpeculativeIntent(
            tool="file_read",
            params={"path": "/tmp/a.txt"},
            confidence=0.7,
            source_text="read a",
        )
        task1 = await speculative.execute_if_safe(intent, session_id="sess_1")
        assert task1 is not None

        intent2 = SpeculativeIntent(
            tool="file_read",
            params={"path": "/tmp/b.txt"},
            confidence=0.7,
            source_text="read b",
        )
        task2 = await speculative.execute_if_safe(intent2, session_id="sess_1")
        assert task2 is None
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass

    def test_get_result_cache_hit(self, speculative, mock_tool_executor):
        params_hash = speculative._hash_params({"path": "/tmp/x.txt"})
        speculative._results["sess_1"] = {f"file_read:{params_hash}": "cached content"}

        result = speculative.get_result("sess_1", "file_read", {"path": "/tmp/x.txt"})
        assert result == "cached content"
        assert speculative._stats["hits"] == 1

    def test_get_result_cache_miss(self, speculative):
        result = speculative.get_result("sess_1", "file_read", {"path": "/tmp/y.txt"})
        assert result is None
        assert speculative._stats["hits"] == 0

    def test_get_stats_initial(self, speculative):
        stats = speculative.get_stats()
        assert stats["intents_detected"] == 0
        assert stats["executed"] == 0
        assert stats["hits"] == 0
        assert stats["wasted"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["waste_rate"] == 0.0

    def test_get_stats_after_hit(self, speculative):
        speculative._stats["executed"] = 10
        speculative._stats["hits"] = 7
        speculative._stats["wasted"] = 2
        stats = speculative.get_stats()
        assert stats["hit_rate"] == 0.7
        assert stats["waste_rate"] == 0.2

    def test_mark_wasted(self, speculative):
        speculative._speculated["sess_1"] = {"file_read:aaa", "web_search:bbb"}
        speculative._results["sess_1"] = {"file_read:aaa": "ok"}
        speculative.mark_wasted("sess_1")
        assert speculative._stats["wasted"] == 1

    def test_reset_session(self, speculative):
        speculative._speculated["sess_1"] = {"file_read:aaa"}
        speculative._results["sess_1"] = {"file_read:aaa": "ok"}
        speculative.reset_session("sess_1")
        assert "sess_1" not in speculative._speculated
        assert "sess_1" not in speculative._results

    @pytest.mark.asyncio
    async def test_execute_if_safe_no_tool_executor(self, mock_tool_executor):
        spec = SpeculativeExecutor(tool_executor=None)
        intent = SpeculativeIntent(
            tool="file_read",
            params={"path": "/tmp/x.txt"},
            confidence=0.7,
            source_text="read",
        )
        task = await spec.execute_if_safe(intent, session_id="sess_1")
        assert task is not None
        await task
        assert spec._stats["executed"] == 1
