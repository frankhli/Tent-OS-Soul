"""永恒模式端到端测试"""

import asyncio
import sys
import time

sys.path.insert(0, '.')

from fastapi.testclient import TestClient


async def test_eternal():
    from tent_os.api.server import app, state
    from tent_os.api import soul_state
    from tent_os.bootstrap import load_config

    config = load_config('./config/tent_os.yaml')
    await state.setup(config)
    await soul_state.state.setup(config)

    client = TestClient(app)
    user_id = "test_user_eternal"

    print("=" * 60)
    print("永恒模式端到端测试")
    print("=" * 60)

    # 1. 获取永恒模式状态
    print("\n[1] 获取永恒模式状态...")
    res = client.get(f"/api/v1/soul/eternal/status/{user_id}")
    print(f"  status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"  activated: {data.get('activated')}")
        print(f"  guardian_enabled: {data.get('guardian_enabled')}")
        print(f"  completeness: {data.get('completeness')}")
    else:
        print(f"  error: {res.text[:200]}")

    # 2. 访问验证（模拟继承者访问）
    print("\n[2] 继承者访问验证...")
    res = client.post(
        f"/api/v1/soul/eternal/access/{user_id}",
        json={"heir_id": "heir_001", "heir_name": "测试继承者", "token": "test_token_123"},
    )
    print(f"  status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"  granted: {data.get('granted')}")
        print(f"  message: {data.get('message')}")
    else:
        print(f"  error: {res.text[:200]}")

    # 3. 获取记忆
    print("\n[3] 获取永恒记忆...")
    res = client.get(f"/api/v1/soul/eternal/memories/{user_id}?limit=5")
    print(f"  status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        memories = data.get("memories", [])
        print(f"  memories_count: {len(memories)}")
        for m in memories[:3]:
            print(f"    - {m.get('title', 'untitled')} ({m.get('memory_type', 'unknown')})")
    else:
        print(f"  error: {res.text[:200]}")

    # 4. 永恒对话
    print("\n[4] 永恒模式对话...")
    res = client.post(
        f"/api/v1/soul/eternal/chat/{user_id}",
        json={
            "heir_id": "heir_001",
            "heir_name": "测试继承者",
            "token": "test_token_123",
            "message": "你好，我想念你",
            "mode": "text",
        },
    )
    print(f"  status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"  reply: {data.get('reply', '')[:100]}")
        print(f"  speaker: {data.get('speaker')}")
        print(f"  eternal: {data.get('eternal')}")
    else:
        print(f"  error: {res.text[:200]}")

    # 5.  farewell（告别语）
    print("\n[5] 获取告别语...")
    res = client.get(f"/api/v1/soul/eternal/farewell/{user_id}")
    print(f"  status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"  farewell: {data.get('farewell', '')[:100]}")
    else:
        print(f"  error: {res.text[:200]}")

    print("\n" + "=" * 60)
    print("永恒模式测试完成")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(test_eternal())
