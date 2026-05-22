"""Pytest 全局配置和 Fixtures

为 Tent OS 测试提供统一的：
1. 事件循环管理
2. 临时目录和数据库
3. Mock 对象工厂
4. 常用 fixtures
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
import pytest
import pytest_asyncio

# 确保 tent_os 在路径中
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)


# ========== 事件循环 ==========

@pytest.fixture(scope="session")
def event_loop():
    """创建一个 session 级别的事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ========== 临时资源 Fixtures ==========

@pytest_asyncio.fixture
async def temp_dir():
    """提供临时目录，测试结束后自动清理"""
    path = tempfile.mkdtemp(prefix="tent_test_")
    yield Path(path)
    # 清理
    import shutil
    shutil.rmtree(path, ignore_errors=True)


@pytest_asyncio.fixture
async def temp_db():
    """提供临时 SQLite 数据库路径"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="tent_test_")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest_asyncio.fixture
async def temp_jsonl_dir():
    """提供临时 JSONL 日志目录"""
    path = tempfile.mkdtemp(prefix="tent_jsonl_test_")
    yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


# ========== Mock 对象工厂 ==========

class MockLLM:
    """Mock LLM 客户端"""
    
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_history = []
    
    async def chat(self, messages, **kwargs):
        self.call_history.append(("chat", messages, kwargs))
        # 返回最后一个消息的内容作为响应
        if messages:
            content = messages[-1].get("content", "")
            return self.responses.get(content, "Mock response")
        return "Mock response"
    
    async def __call__(self, prompt, **kwargs):
        self.call_history.append(("call", prompt, kwargs))
        return self.responses.get(prompt, "Mock response")


class MockMessageBus:
    """Mock 消息总线 —— 增强版，支持 wait_for 和消息解析"""
    
    def __init__(self):
        self.subscriptions = {}
        self.published = []
    
    async def subscribe(self, subject, queue, handler):
        self.subscriptions[subject] = handler
    
    async def publish(self, subject, data):
        self.published.append((subject, data))
    
    async def close(self):
        pass
    
    def get_messages(self, subject_substring: str = ""):
        """获取匹配 subject 的所有消息（自动解码 JSON）"""
        import json
        results = []
        for subj, data in self.published:
            if subject_substring and subject_substring not in subj:
                continue
            try:
                if isinstance(data, bytes):
                    data = data.decode()
                payload = json.loads(data)
            except Exception:
                payload = data
            results.append({"subject": subj, "payload": payload})
        return results
    
    async def wait_for(self, subject_substring: str, min_count: int = 1, timeout: float = 30.0):
        """等待匹配 subject 的消息出现至少 min_count 条"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            count = len([s for s, _ in self.published if subject_substring in s])
            if count >= min_count:
                return self.get_messages(subject_substring)
            await asyncio.sleep(0.3)
        return self.get_messages(subject_substring)


class MockStateStore:
    """Mock 状态存储"""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._messages: Dict[str, list] = {}
    
    async def create(self, session_id, **kwargs):
        self._data[session_id] = {"session_id": session_id, **kwargs, "step": 1}
    
    async def load(self, session_id):
        if session_id not in self._data:
            raise KeyError(session_id)
        return self._data[session_id]
    
    async def update(self, session_id, data):
        if session_id not in self._data:
            raise KeyError(session_id)
        self._data[session_id].update(data)
    
    async def append_message(self, session_id, role, content, images=None):
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].append({"role": role, "content": content})
    
    async def get_messages(self, session_id, limit=50):
        return self._messages.get(session_id, [])[-limit:]
    
    async def list_sessions(self, user_id, limit=10):
        return [
            {"session_id": k, "user_id": v.get("user_id", "")}
            for k, v in self._data.items()
            if v.get("user_id") == user_id
        ][:limit]
    
    async def update_plan(self, session_id, plan, step=1):
        await self.update(session_id, {"plan": plan, "step": step})
    
    async def advance_step(self, session_id):
        state = await self.load(session_id)
        new_step = state.get("step", 1) + 1
        await self.update(session_id, {"step": new_step})
        return new_step
    
    async def get_retry_count(self, session_id: str) -> int:
        state = self._data.get(session_id, {})
        return state.get("_retry_count", 0)
    
    async def set_retry_count(self, session_id: str, count: int) -> None:
        if session_id in self._data:
            self._data[session_id]["_retry_count"] = count
    
    async def clear_retry_count(self, session_id: str) -> None:
        if session_id in self._data:
            self._data[session_id].pop("_retry_count", None)


class MockToolExecutor:
    """Mock 工具执行器"""
    
    def __init__(self):
        self._tools = {}
        self._calls = []
    
    def register_tool(self, name, handler, schema):
        self._tools[name] = {"handler": handler, "schema": schema}
    
    def get_custom_tool_schemas(self):
        return [t["schema"] for t in self._tools.values()]
    
    async def execute(self, tool_name, params, session_id="", max_calls=10):
        self._calls.append((tool_name, params, session_id))
        if tool_name in self._tools:
            return await self._tools[tool_name]["handler"](params)
        return f"Mock result for {tool_name}"
    
    def reset_session(self, session_id):
        pass


# ========== Fixtures ==========

@pytest_asyncio.fixture
async def mock_llm():
    return MockLLM()


@pytest_asyncio.fixture
async def mock_bus():
    return MockMessageBus()


@pytest_asyncio.fixture
async def mock_store():
    return MockStateStore()


@pytest_asyncio.fixture
async def mock_executor():
    return MockToolExecutor()


# ========== 真实 LLM + GovernanceWorker Fixtures ==========

@pytest.fixture
def real_llm():
    """创建真实 LLM（从环境变量读取 API key）
    
    如果没有 API key，自动跳过所有依赖此 fixture 的测试。
    """
    api_key = os.environ.get("TENT_OS_API_KEY", "")
    if not api_key:
        pytest.skip("TENT_OS_API_KEY 环境变量未设置，跳过真实 LLM 测试")
    
    from tent_os.llm.kimi_coding import KimiCodingLLM
    return KimiCodingLLM(
        api_key=api_key,
        model="kimi-k2.6",
        temperature=0.3,
    )


@pytest_asyncio.fixture
async def real_governance_worker(real_llm, temp_dir):
    """创建 GovernanceWorker，使用真实 LLM + 真实 ToolExecutor
    
    这是一个"重" fixture，每个测试函数会创建一个新的 worker 实例。
    brain_v2 默认禁用以减少测试时间和不可预测性。
    """
    from tent_os.scheduler.executors.local import LocalExecutor
    from tent_os.tools.executor import ToolExecutor
    from tent_os.governance.worker import GovernanceWorker
    from tent_os.state.mock_store import MockSessionStateStore
    
    bus = MockMessageBus()
    state_store = MockSessionStateStore()
    
    # 创建 LocalExecutor（真实本地执行，限制在临时目录）
    local_executor = LocalExecutor()
    workspace_path = temp_dir / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # 创建测试文件供集成测试使用（只读操作）
    (workspace_path / "README.md").write_text("# Test Workspace\n\nThis is a test file for integration tests.")
    (workspace_path / "config.json").write_text('{"version": "1.0", "mode": "test"}')
    (workspace_path / "subdir").mkdir(exist_ok=True)
    (workspace_path / "subdir" / "notes.txt").write_text("Some notes here.")
    
    await local_executor.initialize({
        "workspace_mode": "workspace",
        "workspace_path": str(workspace_path),
        "timeout_seconds": 30,
        "allow_write": False,  # 测试中禁止写入
        "blocked_patterns": ["rm -rf", "rm -fr", "mkfs", "fdisk", "> /dev/sda", "dd if="],
    })
    
    # 创建 ToolExecutor
    tool_executor = ToolExecutor(
        local_executor=local_executor,
        memory_store=None,
    )
    
    config = {
        "memory": {"storage_path": str(temp_dir / "tent_memory")},
        "tools": {"profile": "full", "max_result_chars": 4000},
        "stream": {
            "block_streaming": True,
            "min_chunk_chars": 40,
            "max_chunk_chars": 300,
            "coalesce_ms": 80,
        },
        "brain_v2": {"enabled": False},  # 测试中禁用 brain v2
        "governance": {
            "approval_threshold": 0.5,
            "enable_evaluator": False,
            "enable_procedural_memory": False,
        },
    }
    
    worker = GovernanceWorker(
        bus=bus,
        llm=real_llm,
        state_store=state_store,
        tool_executor=tool_executor,
        skill_manager=None,
        config=config,
    )
    
    yield worker
    
    # 清理
    if hasattr(local_executor, 'shutdown'):
        await local_executor.shutdown()
    if hasattr(local_executor, 'close'):
        await local_executor.close()
