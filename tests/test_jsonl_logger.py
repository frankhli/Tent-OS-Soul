"""Tests for JSONLLogger —— 结构化日志系统"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from tent_os.logging.jsonl_logger import JSONLLogger, LogEntry, get_jsonl_logger


def _find_jsonl_files(base_dir):
    """Recursively find all .jsonl files."""
    results = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".jsonl"):
                results.append(os.path.join(root, f))
    return results


@pytest.fixture
def tmp_base_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.mark.unit
class TestLogEntry:
    def test_creation(self):
        entry = LogEntry(
            ts=1704067200.0,
            level="info",
            event="test_event",
            session_id="s1",
            task_id=None,
            agent_id=None,
            data={"key": "val"},
        )
        assert entry.level == "info"
        assert entry.event == "test_event"


@pytest.mark.unit
class TestJSONLLogger:
    @pytest.mark.asyncio
    async def test_start_stop(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        assert lg._shutdown is False
        await lg.stop()
        assert lg._shutdown is True

    @pytest.mark.asyncio
    async def test_log_event(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir, flush_interval_ms=50)
        await lg.start()
        await lg.log_event("security", level="warn", session_id="s1", tool="shell")
        await lg._flush_all()
        await lg.stop()

        files = _find_jsonl_files(tmp_base_dir)
        assert any(f.endswith(".jsonl") for f in files)

    @pytest.mark.asyncio
    async def test_log_tool(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir, flush_interval_ms=50)
        await lg.start()
        await lg.log_tool(
            "tool_called", "sess_1", "web_search",
            {"query": "x"}, "allow", 120.0,
        )
        await lg._flush_all()
        await lg.stop()

        files = _find_jsonl_files(tmp_base_dir)
        assert len(files) > 0
        with open(files[0]) as fh:
            line = json.loads(fh.readline())
        assert line["event"] == "tool_called"

    @pytest.mark.asyncio
    async def test_log_llm(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        await lg.log_llm(
            "llm_response", "sess_1", "gpt-4",
            100, 50, 500.0, 0.002,
        )
        await lg._flush_all()
        stats = lg.get_stats()
        await lg.stop()
        assert stats["total_events"] >= 1

    @pytest.mark.asyncio
    async def test_log_error(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        await lg.log_error("runtime_error", "sess_1", "something broke")
        await lg._flush_all()
        stats = lg.get_stats()
        await lg.stop()
        assert stats["total_events"] >= 1

    @pytest.mark.asyncio
    async def test_log_security(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        await lg.log_security("evaluated", "sess_1", "deny", "高危操作")
        await lg._flush_all()
        stats = lg.get_stats()
        await lg.stop()
        assert stats["total_events"] >= 1

    @pytest.mark.asyncio
    async def test_replay_session(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        await lg.log_event("session_start", session_id="s1")
        await lg.log_tool("search", "s1", "web_search", {}, "allow", 100.0)
        await lg.log_event("session_end", session_id="s1")
        await lg._flush_all()

        events = lg.replay_session("s1")
        await lg.stop()
        assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_query_with_filters(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        await lg.log_event("deny", level="warn", session_id="s1")
        await lg.log_event("allow", level="info", session_id="s2")
        await lg._flush_all()

        results = lg.query(level="warn")
        await lg.stop()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self, tmp_base_dir):
        lg = JSONLLogger(base_dir=tmp_base_dir)
        await lg.start()
        stats = lg.get_stats()
        await lg.stop()
        assert "total_events" in stats


@pytest.mark.unit
class TestGlobal:
    def test_get_jsonl_logger_singleton(self, tmp_base_dir):
        with patch("tent_os.logging.jsonl_logger._jsonl_logger", None):
            lg1 = get_jsonl_logger(base_dir=tmp_base_dir)
            lg2 = get_jsonl_logger()
            assert lg1 is lg2
