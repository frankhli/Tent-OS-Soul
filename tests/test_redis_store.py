#!/usr/bin/env python3
"""RedisSessionStateStore 分布式验证测试

验证：
1. 基本 CRUD 操作
2. TTL 自动过期
3. 多实例共享状态（模拟两个治理进程实例）
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.state.redis_store import RedisSessionStateStore


async def test_redis_store():
    print("=" * 60)
    print("Redis 分布式状态存储验证")
    print("=" * 60)

    store = RedisSessionStateStore(redis_url="redis://localhost:6379", ttl=3600)

    # 1. 创建会话
    print("\n📝 测试 1: 创建会话")
    await store.create(
        session_id="sess_001",
        task="获取远程数据并处理",
        tools=[{"name": "fetch_data"}, {"name": "process_data"}],
        user_id="user_001",
    )
    state = await store.load("sess_001")
    assert state["task"] == "获取远程数据并处理"
    assert state["step"] == 1
    assert state["user_id"] == "user_001"
    print("  ✅ 创建并加载会话正常")

    # 2. 更新 Plan
    print("\n📝 测试 2: 更新 Plan")
    plan = {"analysis": "test", "steps": [{"step": 1, "action": "fetch"}]}
    await store.update_plan("sess_001", plan, step=1)
    state = await store.load("sess_001")
    assert state["plan"] == plan
    assert state["step"] == 1
    print("  ✅ Plan 更新正常")

    # 3. 前进步骤
    print("\n📝 测试 3: 前进步骤")
    new_step = await store.advance_step("sess_001")
    assert new_step == 2
    state = await store.load("sess_001")
    assert state["step"] == 2
    print("  ✅ 步骤前进正常")

    # 4. 多实例共享（模拟两个治理进程实例访问同一份状态）
    print("\n📝 测试 4: 多实例共享状态")
    store2 = RedisSessionStateStore(redis_url="redis://localhost:6379", ttl=3600)

    state_from_instance2 = await store2.load("sess_001")
    assert state_from_instance2["step"] == 2
    assert state_from_instance2["plan"] == plan
    print("  ✅ 实例 2 能读取实例 1 创建的状态")

    # 实例 2 更新，实例 1 能看到
    await store2.advance_step("sess_001")
    state_from_instance1 = await store.load("sess_001")
    assert state_from_instance1["step"] == 3
    print("  ✅ 实例 2 更新后，实例 1 能读到最新状态")

    # 5. 删除会话
    print("\n📝 测试 5: 删除会话")
    await store.delete("sess_001")
    try:
        await store.load("sess_001")
        assert False, "应该抛出 KeyError"
    except KeyError:
        pass
    print("  ✅ 删除后无法加载")

    # 6. TTL 验证
    print("\n📝 测试 6: TTL 已设置")
    await store.create(session_id="sess_ttl", task="TTL test", tools=[])
    ttl = await store.redis.ttl("tent:session:sess_ttl")
    assert ttl > 0, f"TTL 应该大于 0，实际是 {ttl}"
    print(f"  ✅ TTL 已设置: {ttl}s")

    # 清理
    await store.redis.delete("tent:session:sess_ttl")
    await store.redis.close()
    await store2.redis.close()

    print("\n" + "=" * 60)
    print("✅ Redis 分布式状态存储验证全部通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_redis_store())
