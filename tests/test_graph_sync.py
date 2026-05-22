"""Tests for CognitiveGraphSync —— 跨机器认知图谱同步"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tent_os.memory.graph_sync import CognitiveGraphSync, GraphSyncEvent


@pytest.fixture
def mock_graph():
    """模拟 CognitiveGraph"""
    graph = MagicMock()
    graph.node_count = MagicMock(return_value=100)
    graph.get_node = MagicMock(return_value=None)
    graph.add_node_from_dict = MagicMock()
    graph.update_node = MagicMock()
    graph.add_edge_from_dict = MagicMock()
    graph.delete_node = MagicMock()
    graph.query_by_session = MagicMock(return_value=[])
    return graph


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.subscribe = AsyncMock(return_value=AsyncMock())
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def sync(mock_graph, mock_bus):
    return CognitiveGraphSync(
        graph=mock_graph,
        bus=mock_bus,
        instance_id="test-instance-1",
    )


@pytest.mark.unit
class TestCognitiveGraphSync:

    @pytest.mark.asyncio
    async def test_start_stop(self, sync):
        await sync.start()
        assert sync._running is True
        assert sync._sync_task is not None

        await sync.stop()
        assert sync._running is False

    @pytest.mark.asyncio
    async def test_publish_node_add(self, sync):
        await sync.start()
        await sync.publish_node_add(
            node_id="node_001",
            node_data={"content": "test content", "confidence": 0.9},
            session_ids=["sess_1"],
        )
        sync.bus.publish.assert_called()
        call_args = sync.bus.publish.call_args
        assert call_args[0][0] == "tent.graph.delta"
        payload = json.loads(call_args[0][1])
        assert payload["event_type"] == "node_add"
        assert payload["node_id"] == "node_001"
        assert payload["source_instance"] == "test-instance-1"
        assert payload["lamport_clock"] > 0

    @pytest.mark.asyncio
    async def test_publish_node_update(self, sync):
        await sync.start()
        await sync.publish_node_update(
            node_id="node_001",
            updates={"confidence": 0.95},
        )
        sync.bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_publish_edge_add(self, sync):
        await sync.start()
        await sync.publish_edge_add(
            source_id="node_A",
            target_id="node_B",
            edge_data={"relation_type": "causal", "strength": 0.8},
            session_ids=["sess_1"],
        )
        sync.bus.publish.assert_called()
        payload = json.loads(sync.bus.publish.call_args[0][1])
        assert payload["event_type"] == "edge_add"
        assert payload["edge_source"] == "node_A"
        assert payload["edge_target"] == "node_B"

    @pytest.mark.asyncio
    async def test_on_delta_ignores_own_events(self, sync):
        """忽略自己发出的事件"""
        await sync.start()
        msg = MagicMock()
        msg.data = json.dumps({
            "event_type": "node_add",
            "node_id": "node_001",
            "source_instance": "test-instance-1",
            "lamport_clock": 5,
            "data": {"content": "test"},
        })
        await sync._on_delta(msg)
        sync.graph.add_node_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_delta_applies_remote_event(self, sync):
        """应用远程事件"""
        await sync.start()
        msg = MagicMock()
        msg.data = json.dumps({
            "event_type": "node_add",
            "node_id": "node_remote",
            "source_instance": "other-instance",
            "lamport_clock": 3,
            "timestamp": 1000,
            "data": {"content": "remote content"},
        })
        await sync._on_delta(msg)
        sync.graph.add_node_from_dict.assert_called_once()
        # Lamport 时钟应更新
        assert sync._lamport_clock > 3

    @pytest.mark.asyncio
    async def test_on_delta_last_write_wins(self, sync):
        """本地版本更新时跳过远程事件"""
        await sync.start()
        existing_node = MagicMock()
        existing_node.updated_at = 9999  # 本地版本非常新
        sync.graph.get_node.return_value = existing_node

        msg = MagicMock()
        msg.data = json.dumps({
            "event_type": "node_add",
            "node_id": "node_old",
            "source_instance": "other-instance",
            "lamport_clock": 1,
            "timestamp": 100,
            "data": {"content": "old"},
        })
        await sync._on_delta(msg)
        sync.graph.add_node_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_delta_update(self, sync):
        await sync.start()
        msg = MagicMock()
        msg.data = json.dumps({
            "event_type": "node_update",
            "node_id": "node_001",
            "source_instance": "other-instance",
            "lamport_clock": 2,
            "timestamp": 1000,
            "data": {"confidence": 0.99},
        })
        await sync._on_delta(msg)
        sync.graph.update_node.assert_called_once_with("node_001", {"confidence": 0.99})

    @pytest.mark.asyncio
    async def test_on_delta_delete(self, sync):
        await sync.start()
        msg = MagicMock()
        msg.data = json.dumps({
            "event_type": "node_delete",
            "node_id": "node_001",
            "source_instance": "other-instance",
            "lamport_clock": 2,
            "timestamp": 1000,
            "data": {},
        })
        await sync._on_delta(msg)
        sync.graph.delete_node.assert_called_once_with("node_001")

    @pytest.mark.asyncio
    async def test_query_subgraph(self, sync):
        from dataclasses import dataclass

        @dataclass
        class FakeNode:
            id: str
            content: str

        sync.graph.query_by_session.return_value = [
            FakeNode(id="n1", content="fact 1"),
            FakeNode(id="n2", content="fact 2"),
        ]
        nodes = await sync.query_subgraph("sess_1", hops=2)
        assert len(nodes) == 2
        sync.bus.publish.assert_called()

    def test_tick_clock(self, sync):
        assert sync._lamport_clock == 0
        assert sync._tick_clock() == 1
        assert sync._tick_clock() == 2
        assert sync._lamport_clock == 2
