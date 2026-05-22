"""Tests for OutputSlotManager —— 输出槽位预留系统"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from tent_os.llm.slot_manager import OutputSlotManager, SlotTier, PROVIDER_SLOT_CONFIG


@pytest.fixture
def slot_manager():
    config = {
        "llm": {"provider": "openai"},
        "slot": {"escalation_threshold": 0.95, "downgrade_after": 5},
    }
    return OutputSlotManager(config=config)


@pytest.mark.unit
class TestOutputSlotManager:

    def test_get_slot_size_default(self, slot_manager):
        size = slot_manager.get_slot_size("sess_1")
        assert size == 4096

    def test_get_slot_size_anthropic(self, slot_manager):
        size = slot_manager.get_slot_size("sess_1", provider="anthropic")
        assert size == 4096

    def test_get_slot_size_extended(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.EXTENDED
        size = slot_manager.get_slot_size("sess_1", provider="openai")
        assert size == 16384

    def test_get_slot_size_maximum(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.MAXIMUM
        size = slot_manager.get_slot_size("sess_1", provider="kimi")
        assert size == 16384

    def test_get_next_tier_default_to_extended(self, slot_manager):
        assert slot_manager._get_next_tier(SlotTier.DEFAULT) == SlotTier.EXTENDED

    def test_get_next_tier_extended_to_maximum(self, slot_manager):
        assert slot_manager._get_next_tier(SlotTier.EXTENDED) == SlotTier.MAXIMUM

    def test_get_next_tier_maximum_stays(self, slot_manager):
        assert slot_manager._get_next_tier(SlotTier.MAXIMUM) == SlotTier.MAXIMUM

    def test_was_truncated_dict_response_length(self, slot_manager):
        response = {"choices": [{"finish_reason": "length"}]}
        assert slot_manager._was_truncated(response) is True

    def test_was_truncated_dict_response_stop(self, slot_manager):
        response = {"choices": [{"finish_reason": "stop"}]}
        assert slot_manager._was_truncated(response) is False

    def test_was_truncated_dict_empty_choices(self, slot_manager):
        response = {"choices": []}
        assert slot_manager._was_truncated(response) is False

    def test_was_truncated_string(self, slot_manager):
        assert slot_manager._was_truncated("some text") is False

    def test_was_truncated_object(self, slot_manager):
        obj = MagicMock()
        obj.choices = [MagicMock(finish_reason="length")]
        assert slot_manager._was_truncated(obj) is True

    def test_extract_token_usage_dict(self, slot_manager):
        response = {"usage": {"completion_tokens": 150}}
        assert slot_manager._extract_token_usage(response) == 150

    def test_extract_token_usage_object(self, slot_manager):
        obj = MagicMock()
        obj.usage = MagicMock(completion_tokens=200)
        assert slot_manager._extract_token_usage(obj) == 200

    def test_extract_token_usage_missing(self, slot_manager):
        assert slot_manager._extract_token_usage({}) == 0

    def test_extract_content_dict(self, slot_manager):
        response = {"choices": [{"message": {"content": "hello"}}]}
        assert slot_manager._extract_content(response) == "hello"

    def test_extract_content_object(self, slot_manager):
        obj = MagicMock()
        obj.choices = [MagicMock(message=MagicMock(content="world"))]
        assert slot_manager._extract_content(obj) == "world"

    def test_extract_content_string(self, slot_manager):
        assert slot_manager._extract_content("raw text") == "raw text"

    def test_maybe_downgrade(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.EXTENDED
        slot_manager._session_consecutive_defaults["sess_1"] = 5
        slot_manager._maybe_downgrade("sess_1")
        assert slot_manager._session_tiers["sess_1"] == SlotTier.DEFAULT
        assert slot_manager._session_extended_uses.get("sess_1", 0) == 0

    def test_maybe_downgrade_not_enough(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.EXTENDED
        slot_manager._session_consecutive_defaults["sess_1"] = 3
        slot_manager._maybe_downgrade("sess_1")
        assert slot_manager._session_tiers["sess_1"] == SlotTier.EXTENDED

    def test_get_session_stats_default(self, slot_manager):
        stats = slot_manager.get_session_stats("sess_new")
        assert stats["current_tier"] == "default"
        assert stats["extended_uses"] == 0
        assert stats["consecutive_defaults"] == 0

    def test_get_session_stats_with_state(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.EXTENDED
        slot_manager._session_extended_uses["sess_1"] = 3
        slot_manager._session_consecutive_defaults["sess_1"] = 2
        stats = slot_manager.get_session_stats("sess_1")
        assert stats["current_tier"] == "extended"
        assert stats["extended_uses"] == 3
        assert stats["consecutive_defaults"] == 2

    def test_reset_session(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.MAXIMUM
        slot_manager._session_extended_uses["sess_1"] = 5
        slot_manager._session_default_uses["sess_1"] = 2
        slot_manager._session_consecutive_defaults["sess_1"] = 1
        slot_manager.reset_session("sess_1")
        assert "sess_1" not in slot_manager._session_tiers
        assert "sess_1" not in slot_manager._session_extended_uses
        assert "sess_1" not in slot_manager._session_default_uses
        assert "sess_1" not in slot_manager._session_consecutive_defaults

    @pytest.mark.asyncio
    async def test_call_with_slot_no_truncation(self, slot_manager):
        mock_llm = AsyncMock(return_value={
            "choices": [{"message": {"content": "result"}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 100},
        })
        result = await slot_manager.call_with_slot(mock_llm, [], session_id="sess_1")
        assert result.content == "result"
        assert result.tier_used == "default"
        assert result.was_truncated is False
        assert result.upgraded is False
        assert result.calls_made == 1

    @pytest.mark.asyncio
    async def test_call_with_slot_truncation_upgrades(self, slot_manager):
        mock_llm = AsyncMock()
        mock_llm.side_effect = [
            {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}], "usage": {"completion_tokens": 4096}},
            {"choices": [{"message": {"content": "full result"}, "finish_reason": "stop"}], "usage": {"completion_tokens": 5000}},
        ]
        result = await slot_manager.call_with_slot(mock_llm, [], session_id="sess_1")
        assert result.content == "full result"
        assert result.tier_used == "extended"
        assert result.upgraded is True
        assert result.calls_made == 2
        assert slot_manager._session_tiers["sess_1"] == SlotTier.EXTENDED

    @pytest.mark.asyncio
    async def test_call_with_slot_maximum_no_double_upgrade(self, slot_manager):
        slot_manager._session_tiers["sess_1"] = SlotTier.MAXIMUM
        mock_llm = AsyncMock(return_value={
            "choices": [{"message": {"content": "still truncated"}, "finish_reason": "length"}],
            "usage": {"completion_tokens": 32000},
        })
        result = await slot_manager.call_with_slot(mock_llm, [], session_id="sess_1")
        assert result.was_truncated is True
        assert result.upgraded is False
        assert result.calls_made == 1

    @pytest.mark.asyncio
    async def test_call_with_slot_downgrade_via_maybe_downgrade(self, slot_manager):
        # Directly test _maybe_downgrade path
        slot_manager._session_tiers["sess_1"] = SlotTier.EXTENDED
        slot_manager._session_consecutive_defaults["sess_1"] = 5
        slot_manager._maybe_downgrade("sess_1")
        assert slot_manager._session_tiers["sess_1"] == SlotTier.DEFAULT
