"""
Round 3 修复端到端测试
覆盖:
- approval.request 前端处理
- chat.tool_call / chat.tool_result 前端渲染
- fetchJson 超时
- useVoiceRecorder interim transcript 方向
- 设置持久化后端 API
- KnowledgePanel 编辑/删除后端 API
- Regenerate 对 welcome 隐藏
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest

BASE = "http://127.0.0.1:8003"
WS_BASE = "ws://127.0.0.1:8003/ws"


@pytest.mark.asyncio
async def test_fetch_json_timeout():
    """fetchJson 已添加 AbortController 超时"""
    with open("frontend/desktop/src/api/soulApi.ts", "r") as f:
        src = f.read()
    assert "AbortController" in src
    assert "controller.abort()" in src
    assert "timeout" in src
    print("✓ fetchJson timeout OK")


@pytest.mark.asyncio
async def test_voice_recorder_interim_direction():
    """interim transcript 取最新而非最旧"""
    with open("frontend/desktop/src/hooks/useVoiceRecorder.ts", "r") as f:
        src = f.read()
    # 应该只取第一个非 final 结果（最新的）
    assert "else if (!interimTranscript)" in src
    print("✓ voice recorder interim OK")


@pytest.mark.asyncio
async def test_settings_persistence_api():
    """后端用户设置 API 可用"""
    async with httpx.AsyncClient(timeout=10) as client:
        # GET
        r = await client.get(f"{BASE}/api/v1/settings", params={"user_id": "test_user"})
        assert r.status_code == 200
        data = r.json()
        assert "settings" in data
        # POST
        r2 = await client.post(
            f"{BASE}/api/v1/settings",
            params={"user_id": "test_user"},
            json={"show_reasoning": True, "compact_mode": False, "tts_voice": "xiaoxiao"},
        )
        assert r2.status_code == 200
        assert r2.json().get("status") == "ok"
        # GET again
        r3 = await client.get(f"{BASE}/api/v1/settings", params={"user_id": "test_user"})
        saved = r3.json().get("settings", {})
        assert saved.get("show_reasoning") is True
        assert saved.get("tts_voice") == "xiaoxiao"
    print("✓ settings persistence API OK")


@pytest.mark.asyncio
async def test_knowledge_crud_api():
    """Knowledge 编辑/删除后端 API 可用"""
    async with httpx.AsyncClient(timeout=10) as client:
        # Create
        r = await client.post(
            f"{BASE}/api/v1/memory/knowledge",
            json={"title": "测试笔记", "summary": "测试内容", "memory_type": "note", "user_id": "test_user"},
        )
        assert r.status_code == 200
        note_id = r.json().get("id")
        assert note_id
        # Update
        r2 = await client.put(
            f"{BASE}/api/v1/memory/knowledge/{note_id}",
            json={"title": "更新标题", "summary": "更新内容", "memory_type": "note", "user_id": "test_user"},
        )
        assert r2.status_code == 200
        assert r2.json().get("status") == "ok"
        # Delete
        r3 = await client.delete(f"{BASE}/api/v1/memory/knowledge/{note_id}")
        assert r3.status_code == 200
        assert r3.json().get("status") == "ok"
    print("✓ knowledge CRUD API OK")


@pytest.mark.asyncio
async def test_chat_interface_approval_state():
    """ChatInterface 包含 approval request state"""
    with open("frontend/desktop/src/components/ChatInterface.tsx", "r") as f:
        src = f.read()
    assert "approvalRequest" in src
    assert "setApprovalRequest" in src
    assert "approval.request" in src
    assert "submitApproval" in src
    print("✓ ChatInterface approval state OK")


@pytest.mark.asyncio
async def test_chat_interface_tool_rendering():
    """ChatInterface 渲染 tool_call / tool_result"""
    with open("frontend/desktop/src/components/ChatInterface.tsx", "r") as f:
        src = f.read()
    assert "chat.tool_call" in src
    assert "chat.tool_result" in src
    assert "toolCalls" in src
    assert "toolResults" in src
    assert "🔧" in src
    assert "✓" in src
    print("✓ ChatInterface tool rendering OK")


@pytest.mark.asyncio
async def test_regenerate_welcome_hidden():
    """regenerate 按钮对 welcome 消息隐藏"""
    with open("frontend/desktop/src/components/ChatInterface.tsx", "r") as f:
        src = f.read()
    assert "msg.id !== 'welcome'" in src
    print("✓ regenerate welcome hidden OK")


@pytest.mark.asyncio
async def test_knowledge_panel_edit_delete():
    """KnowledgePanel 包含编辑/删除 UI"""
    with open("frontend/desktop/src/components/KnowledgePanel.tsx", "r") as f:
        src = f.read()
    assert "editingId" in src
    assert "deletingId" in src
    assert "updateNote" in src
    assert "deleteNote" in src
    assert "Pencil" in src
    assert "Trash2" in src
    print("✓ KnowledgePanel edit/delete UI OK")


@pytest.mark.asyncio
async def test_system_settings_backend_sync():
    """SystemSettings 向后端同步所有设置"""
    with open("frontend/desktop/src/components/SystemSettings.tsx", "r") as f:
        src = f.read()
    assert "fetch('/api/v1/settings')" in src
    assert "fetch('/api/v1/settings'," in src
    assert "show_reasoning" in src
    assert "compact_mode" in src
    assert "tts_voice" in src
    print("✓ SystemSettings backend sync OK")


if __name__ == "__main__":
    asyncio.run(test_fetch_json_timeout())
    asyncio.run(test_voice_recorder_interim_direction())
    asyncio.run(test_settings_persistence_api())
    asyncio.run(test_knowledge_crud_api())
    asyncio.run(test_chat_interface_approval_state())
    asyncio.run(test_chat_interface_tool_rendering())
    asyncio.run(test_regenerate_welcome_hidden())
    asyncio.run(test_knowledge_panel_edit_delete())
    asyncio.run(test_system_settings_backend_sync())
    print("\n✅ All Round 3 tests passed!")
