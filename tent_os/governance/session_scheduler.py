"""
GovernanceWorker Session Scheduler —— 操作系统式会话调度器

核心设计：
- 每个 session 一个 asyncio.Queue（顺序执行，保证消息不乱序）
- 每个 session 一个 worker Task（独立运行）
- 全局 asyncio.Semaphore 控制并发度（防止压垮 LLM API）
- NATS callback 快速入队+ack，不阻塞消息流

符合 Tent OS 愿景：GovernanceWorker 不是单线程聊天机器人，
而是一个能同时调度多个会话（进程）执行的智能操作系统内核。
"""
import asyncio
import logging
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger("tent_os.governance.scheduler")


@dataclass
class SessionTask:
    """调度器中的任务单元"""
    coro_factory: Callable[[], Awaitable[None]]
    task_id: str
    # 可选：如果调用方需要等待结果，可以在这里放 Future
    # 当前设计为 fire-and-forget，结果通过 WebSocket / state_store 异步传递


class SessionScheduler:
    """
    GovernanceWorker 的会话级任务调度器。

    类比操作系统：
    - Session = Process（拥有独立的执行上下文）
    - Queue = 进程的就绪队列
    - Worker = 线程（实际执行代码）
    - Semaphore = CPU 核心数（全局并发限制）
    """

    def __init__(
        self,
        max_global_concurrent: int = 8,
        worker_name: str = "gov-session",
    ):
        # FIX v3.2: max_global_concurrent 保留参数但不再使用
        # 全局并发限制已下放到 KimiCodingLLM._request_sem（LLM调用级）
        # 这样记忆检索、工具执行等非LLM步骤不再占用并发槽位
        self.max_global_concurrent = max_global_concurrent
        self.worker_name = worker_name

        # 每会话一个队列
        self._queues: Dict[str, asyncio.Queue] = {}
        # 每会话一个 worker Task
        self._workers: Dict[str, asyncio.Task] = {}
        # 全局并发信号量已移除——见 KimiCodingLLM._request_sem
        # 保护 _queues/_workers 的锁
        self._lock = asyncio.Lock()
        # 关闭标志
        self._shutdown = False

    async def submit(self, session_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        """提交一个任务到指定 session 的队列。

        Args:
            session_id: 会话 ID
            coro_factory: 返回 awaitable 的工厂函数（不是直接的 coroutine，
                         避免在入队前就开始执行）
        """
        if self._shutdown:
            logger.warning(f"[SCHED] Scheduler 已关闭，拒绝任务 [{session_id}]")
            return

        async with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = asyncio.Queue()
                # 启动该 session 的专属 worker
                worker = asyncio.create_task(
                    self._worker_loop(session_id),
                    name=f"{self.worker_name}-{session_id}",
                )
                self._workers[session_id] = worker
                logger.debug(f"[SCHED] Session worker 启动 [{session_id}]")

        await self._queues[session_id].put(coro_factory)

    async def _worker_loop(self, session_id: str) -> None:
        """单个 session 的 worker 循环。

        关键保证：
        1. 同一会话的任务严格串行执行（顺序保证）
        2. 不同会话的 worker 可以并行（受全局信号量限制）
        3. worker 在没有任务 60 秒后自动退出（资源回收）
        """
        queue = self._queues[session_id]
        idle_count = 0

        while not self._shutdown:
            try:
                # 等待任务，最多 60 秒
                coro_factory = await asyncio.wait_for(queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                idle_count += 1
                if idle_count >= 1:
                    # 60 秒无任务，worker 退出
                    logger.debug(f"[SCHED] Session worker 空闲退出 [{session_id}]")
                    break
                continue

            idle_count = 0

            # FIX v3.2: 移除全局Semaphore，请求处理不再受请求级并发限制
            # LLM调用级限制已下放到 KimiCodingLLM._request_sem
            # 记忆检索、工具执行、状态更新等步骤现在可以真正并行
            try:
                await coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[SCHED] Session task 执行失败 [{session_id}]: {e}", exc_info=True)
            finally:
                queue.task_done()

        # Worker 退出，清理资源
        async with self._lock:
            self._queues.pop(session_id, None)
            self._workers.pop(session_id, None)

    async def drain_session(self, session_id: str, timeout: float = 30.0) -> bool:
        """等待指定 session 的所有待处理任务完成（优雅关闭用）。"""
        queue = self._queues.get(session_id)
        if not queue:
            return True
        try:
            await asyncio.wait_for(queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"[SCHED] Session drain 超时 [{session_id}]")
            return False

    async def shutdown(self, timeout: float = 30.0) -> None:
        """优雅关闭所有 worker。"""
        self._shutdown = True
        logger.info(f"[SCHED] 开始关闭，等待 {len(self._workers)} 个 worker...")

        # 等待所有队列排空
        drain_tasks = []
        for sid in list(self._queues.keys()):
            drain_tasks.append(self.drain_session(sid, timeout=timeout))
        if drain_tasks:
            await asyncio.gather(*drain_tasks, return_exceptions=True)

        # 取消所有 worker
        for sid, task in list(self._workers.items()):
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        logger.info("[SCHED] 已关闭")

    def get_stats(self) -> Dict:
        """获取调度器统计信息（用于监控）。"""
        return {
            "active_sessions": len(self._queues),
            "active_workers": len(self._workers),
            "max_concurrent": self.max_global_concurrent,
        }
