"""Tests for ContextCompressionPipeline —— 5层上下文压缩"""

import pytest

from tent_os.governance.compression import (
    ContextCompressionPipeline,
    TokenCounter,
)


@pytest.fixture
def pipeline():
    return ContextCompressionPipeline(config={})


@pytest.fixture
def sample_messages():
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, can you help me?"},
        {"role": "assistant", "content": "Sure! What do you need?"},
    ]


@pytest.mark.unit
class TestTokenCounter:
    def test_count_text(self, pipeline):
        tc = pipeline.counter
        n = tc.count("Hello world")
        assert n > 0
        assert n < 100

    def test_count_messages(self, pipeline, sample_messages):
        tc = pipeline.counter
        n = tc.count_messages(sample_messages)
        assert n > 0
        assert n < 500


@pytest.mark.unit
class TestContextCompressionPipeline:
    @pytest.mark.asyncio
    async def test_compress_under_budget(self, pipeline, sample_messages):
        result = await pipeline.compress(sample_messages, max_tokens=10000)
        assert len(result) == len(sample_messages)

    @pytest.mark.asyncio
    async def test_compress_triggers_budget_reduce(self, pipeline):
        big_msg = {"role": "user", "content": "x" * 20000}
        result = await pipeline.compress([big_msg], max_tokens=100)
        assert len(result) == 1
        assert len(result[0]["content"]) < 20000

    @pytest.mark.asyncio
    async def test_compress_snip_old_history(self, pipeline):
        messages = [
            {"role": "system", "content": "Sys"},
            {"role": "user", "content": "Old question 1"},
            {"role": "assistant", "content": "Old answer 1" * 500},
            {"role": "user", "content": "Old question 2"},
            {"role": "assistant", "content": "Old answer 2" * 500},
            {"role": "user", "content": "Current question"},
        ]
        result = await pipeline.compress(messages, max_tokens=200)
        assert len(result) < len(messages)
        assert any("Current question" in str(m.get("content", "")) for m in result)

    @pytest.mark.asyncio
    async def test_compress_with_working_memory(self, pipeline, sample_messages):
        result = await pipeline.compress(
            sample_messages,
            max_tokens=10000,
            working_memory_text="Key fact: user likes Python",
        )
        assert len(result) >= len(sample_messages)

    @pytest.mark.asyncio
    async def test_compress_empty_messages(self, pipeline):
        result = await pipeline.compress([], max_tokens=1000)
        assert result == []

    @pytest.mark.asyncio
    async def test_compress_tool_messages(self, pipeline):
        messages = [
            {"role": "user", "content": "Run tool"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "t1", "function": {"name": "search", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "result" * 1000},
        ]
        result = await pipeline.compress(messages, max_tokens=200)
        assert len(result) <= len(messages)

    def test_token_counter_encoding_fallback(self):
        tc = TokenCounter(model="unknown-model-xyz")
        n = tc.count("test")
        assert n > 0
