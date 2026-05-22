"""Tests for SegmentedPromptCacheV2 —— 跨代理分段缓存共享"""

import pytest
from unittest.mock import MagicMock

from tent_os.governance.prompt_cache_v2 import SegmentedPromptCacheV2


@pytest.fixture
def cache_no_redis():
    return SegmentedPromptCacheV2(redis_client=None, file_builder=None)


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get.return_value = None
    return r


@pytest.mark.unit
class TestSegmentedPromptCacheV2:

    def test_initialization(self, cache_no_redis):
        assert cache_no_redis.redis is None
        assert cache_no_redis._local_cache == {}
        assert cache_no_redis._local_cache_ttl == 300

    def test_build_anthropic_format(self, cache_no_redis):
        tools = [
            {
                "function": {
                    "name": "shell",
                    "description": "Run shell command",
                    "parameters": {"properties": {"command": {"type": "string"}}},
                }
            }
        ]
        result = cache_no_redis.build(
            model_provider="anthropic",
            session_id="sess_1",
            task="write code",
            tools=tools,
            injected_context="ctx",
            user_id="user_1",
        )
        assert "system" in result
        assert "messages" in result
        assert isinstance(result["system"], list)
        assert result["messages"][0]["role"] == "user"
        assert "write code" in result["messages"][0]["content"]

    def test_build_openai_format(self, cache_no_redis):
        tools = [
            {
                "function": {
                    "name": "web_search",
                    "description": "Search web",
                    "parameters": {"properties": {"query": {"type": "string"}}},
                }
            }
        ]
        result = cache_no_redis.build(
            model_provider="openai",
            session_id="sess_2",
            task="search docs",
            tools=tools,
            injected_context="",
            user_id="user_2",
        )
        assert "messages" in result
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][1]["role"] == "user"
        assert "search docs" in result["messages"][1]["content"]
        assert "web_search" in result["messages"][0]["content"]

    def test_build_anthropic_cache_control(self, cache_no_redis):
        tools = [
            {
                "function": {
                    "name": "file_read",
                    "description": "Read file",
                    "parameters": {"properties": {"path": {"type": "string"}}},
                }
            }
        ]
        result = cache_no_redis.build(
            model_provider="anthropic",
            session_id="sess_3",
            task="read file",
            tools=tools,
        )
        tool_parts = [p for p in result["system"] if p.get("cache_control")]
        assert len(tool_parts) == 1
        assert tool_parts[0]["cache_control"]["type"] == "ephemeral"

    def test_format_tools_empty(self, cache_no_redis):
        text = cache_no_redis._format_tools([])
        assert "当前未配置任何外部工具" in text

    def test_format_tools_with_entries(self, cache_no_redis):
        tools = [
            {
                "function": {
                    "name": "shell",
                    "description": "Run commands",
                    "parameters": {"properties": {"command": {"type": "string"}, "cwd": {"type": "string"}}},
                }
            },
            {
                "function": {
                    "name": "noop",
                    "description": "No op",
                    "parameters": {"properties": {}},
                }
            },
        ]
        text = cache_no_redis._format_tools(tools)
        assert "shell" in text
        assert "Run commands" in text
        assert "command(string)" in text
        assert "noop" in text
        assert "无参数" in text
        assert "工具使用规范" in text

    def test_build_dynamic(self, cache_no_redis):
        dynamic = cache_no_redis._build_dynamic("my task", "extra context", "sess_99")
        assert "【当前任务】my task" in dynamic
        assert "【注入上下文】extra context" in dynamic
        assert "【会话ID】sess_99" in dynamic

    def test_build_dynamic_no_context(self, cache_no_redis):
        dynamic = cache_no_redis._build_dynamic("task only", "", "sess_1")
        assert "【当前任务】task only" in dynamic
        assert "【注入上下文】" not in dynamic

    def test_invalidate_segment_local_only(self, cache_no_redis):
        cache_no_redis._local_cache["prompt_cache:system:global"] = ("content", 12345)
        cache_no_redis.invalidate_segment("system")
        assert "prompt_cache:system:global" not in cache_no_redis._local_cache

    def test_invalidate_segment_with_redis(self, mock_redis):
        cache = SegmentedPromptCacheV2(redis_client=mock_redis)
        cache._local_cache["prompt_cache:agents:project"] = ("agents", 12345)
        cache.invalidate_segment("agents", scope="project")
        assert "prompt_cache:agents:project" not in cache._local_cache
        mock_redis.delete.assert_called_once_with("prompt_cache:agents:project")

    def test_get_segment_from_local_cache(self, cache_no_redis):
        cache_no_redis._local_cache["prompt_cache:system:global"] = ("cached_system", 9999999999)
        content = cache_no_redis._get_segment("system", "global")
        assert content == "cached_system"

    def test_get_segment_from_redis(self, mock_redis):
        mock_redis.get.return_value = b"redis_content"
        cache = SegmentedPromptCacheV2(redis_client=mock_redis)
        content = cache._get_segment("identity", "default")
        assert content == "redis_content"
        assert "prompt_cache:identity:default" in cache._local_cache

    def test_get_segment_default_fallback(self, cache_no_redis):
        content = cache_no_redis._get_segment("system", "global")
        assert "Tent OS" in content
