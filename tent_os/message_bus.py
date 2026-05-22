import inspect
import json
import logging
from nats.aio.client import Client as NATS
from nats.js.api import StreamConfig, RetentionPolicy, ConsumerConfig, AckPolicy, DeliverPolicy
from datetime import datetime, timezone
from nats.js.client import JetStreamContext

logger = logging.getLogger("tent_os.message_bus")


class MessageBus:
    """NATS JetStream消息总线封装"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nats: NATS = None
        self.js: JetStreamContext = None
    
    async def connect(self):
        self.nats = NATS()
        await self.nats.connect(self.nats_url)
        self.js = self.nats.jetstream()
        
        jsm = self.nats.jsm()
        desired_subjects = {"memory.>", "governance.>", "scheduler.>", "session.>"}
        try:
            # 尝试获取已有 Stream
            info = await jsm.stream_info("TENT_OS")
            logger.info(f"复用已有 Stream TENT_OS (msgs={info.state.messages}, consumers={info.state.consumer_count})")
            # 检查配置是否兼容（需要支持 BY_START_TIME 的 consumer）
            current_subjects = set(info.config.subjects)
            needs_recreate = (
                current_subjects != desired_subjects or
                info.config.retention != RetentionPolicy.LIMITS
            )
            if needs_recreate:
                logger.warning(f"Stream 配置不兼容，删除重建: retention={info.config.retention}, subjects={current_subjects}")
                await jsm.delete_stream("TENT_OS")
                raise Exception("stream deleted, will recreate")
        except Exception as e:
            # Stream 不存在或被删除，创建新的
            err_str = str(e).lower()
            if "not found" in err_str or "does not exist" in err_str or "stream deleted" in err_str:
                await self.js.add_stream(
                    name="TENT_OS",
                    subjects=list(desired_subjects),
                    retention=RetentionPolicy.LIMITS,
                    max_msgs=-1,
                    max_bytes=-1,
                    max_age=3600 * 24 * 7,  # 7天
                )
                logger.info("Stream TENT_OS 创建成功 (LIMITS retention)")
            else:
                raise
    
    async def publish(self, subject: str, data: bytes, timeout: float = 30.0):
        """发布消息到 JetStream（持久化，至少一次投递）
        
        适用于关键消息（memory、scheduler、governance）。
        FIX: JetStream 无响应时自动回退到 NATS Core，避免任务完全失败。
        """
        try:
            ack = await self.js.publish(subject, data, timeout=timeout)
            return ack
        except Exception as e:
            err_str = str(e).lower()
            if "no response from stream" in err_str or "timeout" in err_str:
                logger.warning(f"JetStream publish 失败，回退到 NATS Core: {subject} | {e}")
                await self.nats.publish(subject, data)
                return None
            raise
    
    async def publish_raw(self, subject: str, data: bytes):
        """发布消息到 NATS Core（fire-and-forget，不经过 JetStream）
        
        适用于非关键事件广播（emotion、scene、visual observation），
        不阻塞、不等待 ACK、不占用 JetStream stream。
        """
        await self.nats.publish(subject, data)
    
    async def subscribe(
        self, subject: str, durable: str, cb,
        ack_policy=AckPolicy.EXPLICIT,
        concurrent: bool = False,
    ):
        """订阅主题，返回订阅对象
        
        回调函数签名为 async def cb(msg)，其中 msg.data 已被解码为字符串。
        注意：callback内部不要再调用msg.ack()，由wrapper统一处理。
        
        Args:
            concurrent: 为 True 时，为每条消息 spawn 独立 task 并立即 ack。
                       适用于 handler 内部有长时间阻塞（如 LLM 调用）的场景。
                       为 False（默认）时，串行处理，ack 在 handler 完成后发送。
        
        自动清理同名旧 consumer（解决重启后 consumer 残留冲突）。
        """
        import asyncio
        async def wrapper(msg):
            # 统一解码
            if isinstance(msg.data, bytes):
                msg.data = msg.data.decode()
            
            if concurrent:
                # === 并发模式：spawn task + 立即 ack ===
                # 适用于 LLM 调用等长时间阻塞场景
                # 注意：此模式下消息最多投递一次（at-most-once）
                async def _handle():
                    try:
                        if inspect.iscoroutinefunction(cb):
                            await cb(msg)
                        else:
                            cb(msg)
                    except Exception as e:
                        logger.error(f"并发消息处理失败 [{subject}]: {e}", exc_info=True)
                asyncio.create_task(_handle())
                await msg.ack()
            else:
                # === 串行模式：await handler + 完成后 ack ===
                # 适用于轻量、快速完成的 handler
                try:
                    if inspect.iscoroutinefunction(cb):
                        await cb(msg)
                    else:
                        cb(msg)
                    await msg.ack()
                except Exception as e:
                    # 处理失败，发送 NAK 让消息重新投递（有限次）
                    logger.warning(f"消息处理失败: {e}, 发送NAK")
                    await msg.nak()
        
        jsm = self.nats.jsm()
        
        # 尝试复用已有 durable consumer（避免消息丢失）
        consumer_exists = False
        try:
            info = await jsm.consumer_info("TENT_OS", durable)
            consumer_exists = True
            logger.info(f"复用已有 consumer: {durable} (delivered={info.delivered.consumer_seq}, pending={info.num_pending})")
        except Exception:
            pass  # consumer 不存在，需要新建
        
        if not consumer_exists:
            # 新建 consumer：消费所有未确认消息（避免 BY_START_TIME 导致的消息丢失）
            await asyncio.sleep(0.2)  # 串行化间隔
            consumer_config = ConsumerConfig(
                durable_name=durable,
                ack_policy=ack_policy,
                deliver_policy=DeliverPolicy.ALL,  # 消费所有未确认消息
                ack_wait=120,  # 给 LLM 调用足够时间
            )
            sub = await self.js.subscribe(
                subject, cb=wrapper, config=consumer_config,
                stream="TENT_OS", manual_ack=True
            )
            logger.info(f"Consumer 创建成功: {durable} -> {subject} (DeliverPolicy.ALL)")
        else:
            # 复用已有 consumer：NATS 会自动从上次确认位置继续
            sub = await self.js.subscribe(
                subject, cb=wrapper,
                stream="TENT_OS", durable=durable, manual_ack=True
            )
        
        return sub
    

    
    async def close(self):
        if self.nats:
            await self.nats.close()
