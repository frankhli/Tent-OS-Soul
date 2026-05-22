import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.main import TentOS
from tent_os.scheduler.executors.mock import MockExecutor
from tent_os.scheduler.router import ExecutorState, ExecutorStatus


async def demo():
    tent = TentOS("./config/tent_os.yaml")
    await tent.start()
    
    # 注册两个 Mock 执行者模拟不同类型的工具
    mock_worker_a = MockExecutor({"executor_id": "mock_worker_a", "delay_seconds": 2})
    mock_worker_b = MockExecutor({"executor_id": "mock_worker_b", "delay_seconds": 3})
    tent.scheduler.register_executor("mock_worker_a", mock_worker_a)
    tent.scheduler.register_executor("mock_worker_b", mock_worker_b)
    tent.scheduler.router.register(ExecutorState(
        executor_id="mock_worker_a", executor_type="automated", status=ExecutorStatus.IDLE,
        queue_depth=0, failure_rate_24h=0.0, avg_completion_seconds=2, cost_per_task=0.01,
        capabilities=["fetch", "process", "move"]
    ))
    tent.scheduler.router.register(ExecutorState(
        executor_id="mock_worker_b", executor_type="external", status=ExecutorStatus.IDLE,
        queue_depth=0, failure_rate_24h=0.0, avg_completion_seconds=5, cost_per_task=0.1,
        capabilities=["fetch", "notify"]
    ))
    
    session_id = "demo_session_001"
    
    # 设置响应监听
    future = asyncio.Future()
    async def on_response(msg):
        future.set_result(json.loads(msg.data))
    await tent.bus.subscribe(f"governance.response.{session_id}", "demo", on_response)
    
    # 发送请求
    await tent.bus.publish("governance.request", json.dumps({
        "session_id": session_id, "user_id": "demo_user",
        "task": "帮我获取远程数据并处理，然后发送通知",
        "tools": [{"name": "fetch_data"}, {"name": "process_data"}, {"name": "send_notification"}]
    }).encode())
    
    result = await asyncio.wait_for(future, timeout=60.0)
    print(f"✅ Demo完成，结果: {result}")
    await tent.shutdown()


if __name__ == "__main__":
    asyncio.run(demo())
