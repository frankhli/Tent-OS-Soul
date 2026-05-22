"""Tent OS 集成测试 —— 多组件模式 + HTTP API + 真实 Kimi LLM"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.bootstrap import (
    load_config, create_message_bus, create_state_store,
    create_memory_worker, create_governance_worker,
    create_scheduler_worker, create_webhook_gateway
)
from tent_os.scheduler.executors.mock import MockExecutor
from tent_os.scheduler.router import ExecutorState, ExecutorStatus


async def test_multicomponent():
    """测试多组件协同：memory + governance + scheduler + api server"""
    config = load_config("./config/tent_os.yaml")
    
    # 创建共享 bus
    bus = create_message_bus(config)
    await bus.connect()
    
    # 状态存储
    state_store = create_state_store(config)
    
    # 1. 启动记忆进程
    memory_worker = create_memory_worker(bus, config)
    asyncio.create_task(memory_worker.start())
    print("🧠 Memory Worker 启动")
    
    # 2. 启动治理进程
    governance_worker = create_governance_worker(bus, config, state_store)
    asyncio.create_task(governance_worker.start())
    print("🧠 Governance Worker 启动")
    
    # 3. 启动调度进程
    scheduler = await create_scheduler_worker(bus, config)
    
    # 注册 Mock 执行者
    mock_robot = MockExecutor()
    await mock_robot.initialize({"executor_id": "mock_robot", "delay_seconds": 1, "supported_actions": ["inspect", "pick", "place", "move"]})
    mock_delivery = MockExecutor()
    await mock_delivery.initialize({"executor_id": "mock_delivery", "delay_seconds": 1, "supported_actions": ["deliver", "pickup"]})
    scheduler.register_executor("mock_robot", mock_robot)
    scheduler.register_executor("mock_delivery", mock_delivery)
    scheduler.router.register(ExecutorState(
        executor_id="mock_robot", executor_type="robot", status=ExecutorStatus.IDLE,
        queue_depth=0, failure_rate_24h=0.0, avg_completion_seconds=2, cost_per_task=0.01,
        capabilities=["inspect", "pick", "place", "move"]
    ))
    scheduler.router.register(ExecutorState(
        executor_id="mock_delivery", executor_type="human", status=ExecutorStatus.IDLE,
        queue_depth=0, failure_rate_24h=0.0, avg_completion_seconds=5, cost_per_task=18.0,
        capabilities=["deliver", "pickup"]
    ))
    
    asyncio.create_task(scheduler.start())
    print("⚙️ Scheduler Worker 启动（含 Mock 执行者）")
    
    # 4. 启动 Webhook Gateway
    gateway = create_webhook_gateway(bus, config)
    asyncio.create_task(gateway.start())
    print("🌐 Webhook Gateway 启动")
    
    # 等待所有组件就绪
    await asyncio.sleep(2)
    
    # 5. 通过消息总线提交任务（模拟 API 入口的行为）
    session_id = "integration_test_001"
    
    # 监听结果
    future = asyncio.Future()
    async def result_handler(msg):
        data = json.loads(msg.data)
        if data.get("session_id") == session_id:
            future.set_result(data.get("result", {}))
    
    await bus.nats.subscribe(f"governance.response.{session_id}", cb=result_handler)
    
    print(f"\n[SEND] 提交任务: 帮我获取远程数据并处理，然后发送通知")
    await bus.publish("governance.request", json.dumps({
        "session_id": session_id,
        "user_id": "integration_user",
        "task": "帮我获取远程数据并处理，然后发送通知",
        "tools": [{"name": "fetch_data"}, {"name": "process_data"}, {"name": "send_notification"}]
    }).encode())
    
    # 等待结果
    try:
        result = await asyncio.wait_for(future, timeout=90.0)
        print(f"\n✅ 集成测试通过！")
        print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    except asyncio.TimeoutError:
        print("\n❌ 集成测试超时")
        try:
            s = await state_store.load(session_id)
            print(f"当前状态: {json.dumps(s, ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"状态查询失败: {e}")
    
    await bus.close()
    print("\n测试完成")


if __name__ == "__main__":
    asyncio.run(test_multicomponent())
