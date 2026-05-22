from datetime import datetime
from typing import Dict, List, Optional

from tent_os.state.interface import SessionStateStore


class MockSessionStateStore(SessionStateStore):
    """内存字典实现的会话状态存储，用于Phase 1测试"""
    
    def __init__(self):
        self._store: Dict[str, Dict] = {}
    
    async def create(self, session_id: str, task: str = "", tools: List[Dict] = None,
                     user_id: str = None, title: str = None) -> None:
        self._store[session_id] = {
            "task": task, "tools": tools or [], "step": 1, "plan": None,
            "user_id": user_id, "title": title or task[:30] if task else "新会话",
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    async def load(self, session_id: str) -> Dict:
        if session_id not in self._store:
            raise KeyError(f"会话不存在: {session_id}")
        return self._store[session_id]
    
    async def update_plan(self, session_id: str, plan: Dict, step: int = 1) -> None:
        state = await self.load(session_id)
        state["plan"] = plan
        state["step"] = step
    
    async def advance_step(self, session_id: str) -> int:
        state = await self.load(session_id)
        state["step"] = state.get("step", 1) + 1
        return state["step"]
    
    async def get_step(self, session_id: str) -> int:
        state = await self.load(session_id)
        return state.get("step", 1)
    
    async def get_plan(self, session_id: str) -> Optional[Dict]:
        state = await self.load(session_id)
        return state.get("plan")
    
    async def delete(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]
    
    async def append_message(self, session_id: str, role: str, content: str, images: List[str] = None) -> None:
        state = await self.load(session_id)
        state["messages"] = state.get("messages", [])
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        if images:
            msg["images"] = images
        state["messages"].append(msg)
        state["updated_at"] = datetime.now().isoformat()
    
    async def get_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        state = await self.load(session_id)
        msgs = state.get("messages", [])
        return msgs[-limit:] if len(msgs) > limit else msgs
    
    async def update_title(self, session_id: str, title: str) -> None:
        state = await self.load(session_id)
        state["title"] = title
        state["updated_at"] = datetime.now().isoformat()
    
    async def update(self, session_id: str, updates: Dict) -> None:
        state = await self.load(session_id)
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()
    
    async def list_sessions(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        sessions = []
        for sid, state in self._store.items():
            if user_id and state.get("user_id") != user_id:
                continue
            sessions.append({
                "session_id": sid,
                "title": state.get("title", "未命名会话"),
                "updated_at": state.get("updated_at", state.get("created_at")),
                "message_count": len(state.get("messages", [])),
            })
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions[:limit]
    
    async def get_retry_count(self, session_id: str) -> int:
        state = self._store.get(session_id, {})
        return state.get("_retry_count", 0)
    
    async def set_retry_count(self, session_id: str, count: int) -> None:
        if session_id in self._store:
            self._store[session_id]["_retry_count"] = count
    
    async def clear_retry_count(self, session_id: str) -> None:
        if session_id in self._store:
            self._store[session_id].pop("_retry_count", None)
