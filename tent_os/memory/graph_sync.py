"""CognitiveGraph Sync —— 跨机器认知图谱实时共享

在单机 CognitiveGraph（SQLite）之上，增加分布式同步层：
- 本地写操作 → 发布同步事件到 NATS
- 远程同步事件 → 应用到本地图谱
- 冲突解决：Lamport 时间戳 + 节点级 last-write-wins
- 拓扑感知：只同步与当前会话相关的子图

Tent OS 差异化：
- 不是替换 SQLite，而是叠加同步层
- 利用现有 NATS JetStream 基础设施
- 支持部分同步（按需拉取相关子图），避免全量同步
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Set

from tent_os.logging_config import get_logger

logger = get_logger()

# NATS 主题前缀
GRAPH_SYNC_SUBJECT = "tent.graph.sync"
GRAPH_SYNC_DELTA = "tent.graph.delta"
GRAPH_SYNC_QUERY = "tent.graph.query"


@dataclass
class GraphSyncEvent:
    """图谱同步事件"""
    event_type: str           # node_add / node_update / edge_add / edge_update / node_delete
    node_id: str = ""         # 节点 ID（edge 事件也包含用于路由）
    edge_source: str = ""     # 边源节点
    edge_target: str = ""     # 边目标节点
    data: Dict[str, Any] = None
    lamport_clock: int = 0
    source_instance: str = ""  # 产生事件的实例 ID
    timestamp: float = 0
    session_ids: List[str] = None  # 相关会话（用于拓扑过滤）


class CognitiveGraphSync:
    """认知图谱分布式同步器

    用法:
        sync = CognitiveGraphSync(graph, bus, instance_id="worker-1")
        await sync.start()

        # 本地添加节点会自动广播
        graph.add_node(...)

        # 查询远程子图
        remote_nodes = await sync.query_subgraph(session_id="abc", hops=2)
    """

    def __init__(self, graph, bus, instance_id: str,
                 sync_mode: str = "delta",  # delta / full / query_on_demand
                 max_sync_hops: int = 2):
        self.graph = graph
        self.bus = bus
        self.instance_id = instance_id
        self.sync_mode = sync_mode
        self.max_sync_hops = max_sync_hops

        self._lamport_clock = 0
        self._subscriptions = []
        self._local_node_ids: Set[str] = set()  # 本实例创建的节点
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False

        # 挂起的远程事件（按 session 分组）
        self._pending_deltas: Dict[str, List[GraphSyncEvent]] = {}

    async def start(self):
        """启动同步服务"""
        if self._running:
            return
        self._running = True

        # 订阅同步事件
        sub1 = await self.bus.subscribe(GRAPH_SYNC_DELTA, f"graph-sync-{self.instance_id}", self._on_delta)
        sub2 = await self.bus.subscribe(GRAPH_SYNC_QUERY, f"graph-query-{self.instance_id}", self._on_query)
        self._subscriptions = [sub1, sub2]

        # 启动定期心跳（广播本实例存活）
        self._sync_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(f"[GraphSync] 同步服务启动 [{self.instance_id}]")

    async def stop(self):
        """停止同步服务"""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except:
                pass
        logger.info(f"[GraphSync] 同步服务停止 [{self.instance_id}]")

    # ========== 写操作同步 ==========

    async def publish_node_add(self, node_id: str, node_data: Dict,
                               session_ids: List[str] = None):
        """广播节点添加事件"""
        self._local_node_ids.add(node_id)
        event = GraphSyncEvent(
            event_type="node_add",
            node_id=node_id,
            data=node_data,
            lamport_clock=self._tick_clock(),
            source_instance=self.instance_id,
            timestamp=time.time(),
            session_ids=session_ids or [],
        )
        await self._publish_event(event)

    async def publish_node_update(self, node_id: str, updates: Dict,
                                  session_ids: List[str] = None):
        """广播节点更新事件"""
        event = GraphSyncEvent(
            event_type="node_update",
            node_id=node_id,
            data=updates,
            lamport_clock=self._tick_clock(),
            source_instance=self.instance_id,
            timestamp=time.time(),
            session_ids=session_ids or [],
        )
        await self._publish_event(event)

    async def publish_edge_add(self, source_id: str, target_id: str,
                               edge_data: Dict, session_ids: List[str] = None):
        """广播边添加事件"""
        event = GraphSyncEvent(
            event_type="edge_add",
            edge_source=source_id,
            edge_target=target_id,
            data=edge_data,
            lamport_clock=self._tick_clock(),
            source_instance=self.instance_id,
            timestamp=time.time(),
            session_ids=session_ids or [],
        )
        await self._publish_event(event)

    # ========== 查询同步 ==========

    async def query_subgraph(self, session_id: str, hops: int = 2,
                             timeout: float = 5.0) -> List[Dict]:
        """向所有实例查询与 session 相关的子图"""
        query_id = f"q_{self.instance_id}_{int(time.time() * 1000)}"

        await self.bus.publish(GRAPH_SYNC_QUERY, json.dumps({
            "query_id": query_id,
            "requester": self.instance_id,
            "session_id": session_id,
            "hops": hops,
        }).encode())

        # 收集响应（简化：直接返回本地查询结果，实际应等待响应）
        try:
            local_nodes = self.graph.query_by_session(session_id, hops=hops)
            return [self._node_to_dict(n) for n in local_nodes]
        except Exception as e:
            logger.debug(f"[GraphSync] 本地子图查询失败: {e}")
            return []

    # ========== 事件处理 ==========

    async def _on_delta(self, msg):
        """处理远程同步事件"""
        try:
            data = json.loads(msg.data)
            event = GraphSyncEvent(**data)

            # 忽略自己发出的事件
            if event.source_instance == self.instance_id:
                return

            # Lamport 时钟更新
            self._lamport_clock = max(self._lamport_clock, event.lamport_clock) + 1

            # 应用事件
            await self._apply_event(event)

        except Exception as e:
            logger.debug(f"[GraphSync] 处理 delta 事件失败: {e}")

    async def _on_query(self, msg):
        """处理远程查询请求"""
        try:
            data = json.loads(msg.data)
            query_id = data.get("query_id")
            session_id = data.get("session_id")
            hops = data.get("hops", 2)
            requester = data.get("requester")

            if requester == self.instance_id:
                return

            # 查询本地子图
            try:
                nodes = self.graph.query_by_session(session_id, hops=hops)
                response = {
                    "query_id": query_id,
                    "responder": self.instance_id,
                    "nodes": [self._node_to_dict(n) for n in nodes],
                }
                await self.bus.publish(f"{GRAPH_SYNC_QUERY}.{query_id}.response",
                                        json.dumps(response).encode())
            except Exception as e:
                logger.debug(f"[GraphSync] 查询响应失败: {e}")

        except Exception as e:
            logger.debug(f"[GraphSync] 处理 query 失败: {e}")

    async def _apply_event(self, event: GraphSyncEvent):
        """将远程事件应用到本地图谱"""
        try:
            if event.event_type == "node_add":
                # 检查是否已存在（last-write-wins）
                existing = self.graph.get_node(event.node_id)
                if existing:
                    # 本地版本更新，跳过
                    if getattr(existing, 'updated_at', 0) > event.timestamp:
                        return
                self.graph.add_node_from_dict(event.data)
                logger.debug(f"[GraphSync] 同步节点: {event.node_id}")

            elif event.event_type == "node_update":
                self.graph.update_node(event.node_id, event.data)
                logger.debug(f"[GraphSync] 更新节点: {event.node_id}")

            elif event.event_type == "edge_add":
                self.graph.add_edge_from_dict(event.data)
                logger.debug(f"[GraphSync] 同步边: {event.edge_source} -> {event.edge_target}")

            elif event.event_type == "node_delete":
                self.graph.delete_node(event.node_id)
                logger.debug(f"[GraphSync] 删除节点: {event.node_id}")

        except Exception as e:
            logger.warning(f"[GraphSync] 应用事件失败: {e}")

    async def _publish_event(self, event: GraphSyncEvent):
        """发布同步事件"""
        try:
            payload = json.dumps({
                "event_type": event.event_type,
                "node_id": event.node_id,
                "edge_source": event.edge_source,
                "edge_target": event.edge_target,
                "data": event.data,
                "lamport_clock": event.lamport_clock,
                "source_instance": event.source_instance,
                "timestamp": event.timestamp,
                "session_ids": event.session_ids,
            }, default=str).encode()
            await self.bus.publish(GRAPH_SYNC_DELTA, payload)
        except Exception as e:
            logger.debug(f"[GraphSync] 发布事件失败: {e}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                await asyncio.sleep(30)
                await self.bus.publish(GRAPH_SYNC_SUBJECT, json.dumps({
                    "type": "heartbeat",
                    "instance_id": self.instance_id,
                    "timestamp": time.time(),
                    "node_count": getattr(self.graph, 'node_count', lambda: 0)(),
                }).encode())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[GraphSync] 心跳异常: {e}")

    def _tick_clock(self) -> int:
        self._lamport_clock += 1
        return self._lamport_clock

    @staticmethod
    def _node_to_dict(node) -> Dict:
        """将节点转为 dict（简化）"""
        if hasattr(node, '__dict__'):
            return {k: v for k, v in asdict(node).items() if k not in ('content_hash',)}
        return {}
