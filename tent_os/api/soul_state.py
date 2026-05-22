"""Tent OS Soul Intercom — 精简版 API Server

移除了：World API、Skills API、MCP Server、AI社区、社交、物理执行器、IoT、2D庄园
保留了：对话、任务、健康检查、灵魂层接口、WebSocket、前端静态文件
"""

import asyncio
import json
import os
import sqlite3
import uuid
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
import uvicorn
import yaml

from tent_os.bootstrap import load_config, create_message_bus, create_state_store, create_llm
from tent_os.logging_config import get_logger
import random
import re

# ========== 旧硬编码追问生成器已删除（Phase 1）==========
# 追问交由 LLM 自主生成，或通过 Skills 系统实现。
# 保留空列表作为兼容回退。
def generate_follow_ups(ai_response: str, user_message: str = "") -> List[str]:
    """追问生成（已废弃，返回空列表）

    Phase 1: 删除硬编码关键词匹配追问。
    追问功能后续通过 Skills 系统或 LLM 自治实现。
    """
    return []
from tent_os.soul import (
    ThoughtExtractor, VoiceModeler, AppearanceModeler,
    StyleFinetuner, TTSSynthesizer, AuthorizationEngine,
    PersonaProfiler, PersonaProfile,
)
from tent_os.soul.encryption import SoulEncryption
from tent_os.soul.dependency_guardian import DependencyGuardian
from tent_os.governance.mode_router import get_mode_router
from tent_os.tools.definitions import get_tools_by_mode

logger = get_logger()


# ========== Pydantic 模型 ==========

class TaskSubmitRequest(BaseModel):
    task: str = Field(..., description="用户任务描述")
    tools: list = Field(default=[], description="可用工具列表")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class FeedbackRequest(BaseModel):
    type: str = Field(..., description="反馈类型: like / dislike / correct")
    correction: Optional[str] = Field(default=None, description="纠正内容")
    message_index: Optional[int] = Field(default=None, description="消息索引")


class ApprovalRequest(BaseModel):
    approved: bool = Field(..., description="是否批准执行")


class WillRequest(BaseModel):
    heirs: list = []
    topic_whitelist: list = []
    topic_blacklist: list = []
    activation_condition: str = "after_death"
    activation_date: Optional[str] = None
    farewell_letter: Optional[str] = None
    access_code: Optional[str] = None


class TTSRequest(BaseModel):
    text: str = Field(..., description="要合成的文本")
    emotion: Optional[str] = Field(default="neutral", description="情绪标签")
    voice_key: Optional[str] = Field(default=None, description="声音选择键")


# ========== WebSocket 管理器 ==========

class WSConnectionManager:
    """Session-aware WebSocket 连接管理器

    Phase 1 修复：从全局广播改为按 session_id 隔离发送。
    每个 session 可以有多个 WebSocket 连接（多设备/多标签页）。
    """

    def __init__(self):
        # session_id -> Set[WebSocket]
        self._sessions: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> session_id（反向索引，用于断开清理）
        self._ws_to_session: Dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str = None):
        """建立 WebSocket 连接

        Args:
            websocket: WebSocket 连接
            session_id: 可选，如果已知则直接关联到 session。
                       如果未知（如连接建立时），可后续通过 associate_session 关联。
        """
        await websocket.accept()
        if session_id:
            async with self._lock:
                if session_id not in self._sessions:
                    self._sessions[session_id] = set()
                self._sessions[session_id].add(websocket)
                self._ws_to_session[websocket] = session_id

    async def associate_session(self, websocket: WebSocket, session_id: str):
        """将已连接的 WebSocket 关联到 session"""
        async with self._lock:
            # 先移除旧的关联
            old_sid = self._ws_to_session.get(websocket)
            if old_sid and old_sid in self._sessions:
                self._sessions[old_sid].discard(websocket)
                if not self._sessions[old_sid]:
                    del self._sessions[old_sid]
            # 添加新的关联
            if session_id not in self._sessions:
                self._sessions[session_id] = set()
            self._sessions[session_id].add(websocket)
            self._ws_to_session[websocket] = session_id

    async def disconnect(self, websocket: WebSocket):
        """断开连接并清理 session 关联"""
        async with self._lock:
            session_id = self._ws_to_session.pop(websocket, None)
            if session_id and session_id in self._sessions:
                self._sessions[session_id].discard(websocket)
                if not self._sessions[session_id]:
                    del self._sessions[session_id]
            # 兼容旧代码：也从全局集合中移除（如果有）
            if hasattr(self, 'connections') and websocket in self.connections:
                self.connections.discard(websocket)

    async def broadcast(self, message: Dict):
        """全局广播（保留但限制使用，建议改用 send_to_session）"""
        # Phase 1: 广播改为只发给有 session 关联的连接
        async with self._lock:
            all_ws = set()
            for ws_set in self._sessions.values():
                all_ws.update(ws_set)
            if hasattr(self, 'connections'):
                all_ws.update(self.connections)
            connections = list(all_ws)
        if not connections:
            return
        text = json.dumps(message)
        dead = set()
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    sid = self._ws_to_session.pop(ws, None)
                    if sid and sid in self._sessions:
                        self._sessions[sid].discard(ws)
                    if hasattr(self, 'connections'):
                        self.connections.discard(ws)

    async def send_to_session(self, session_id: str, message: Dict):
        """发送消息到指定 session 的所有连接"""
        async with self._lock:
            connections = list(self._sessions.get(session_id, set()))
        if not connections:
            return
        text = json.dumps(message)
        dead = set()
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._sessions.get(session_id, set()).discard(ws)
                    self._ws_to_session.pop(ws, None)

    async def send_to(self, websocket: WebSocket, message: Dict):
        """发送消息到单个 WebSocket"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            async with self._lock:
                sid = self._ws_to_session.pop(websocket, None)
                if sid and sid in self._sessions:
                    self._sessions[sid].discard(websocket)
                if hasattr(self, 'connections'):
                    self.connections.discard(websocket)


ws_manager = WSConnectionManager()


# ========== 快速对话模式（跳过 governance 完整流程）==========
# 可从环境变量/配置文件加载的快速模式System Prompt
FAST_CHAT_SYSTEM_PROMPT = os.environ.get(
    "TENT_FAST_CHAT_PROMPT",
    "你是 Tent OS，一个陪伴用户的 AI 助手。用自然、温暖的中文回复，适当简洁。"
)


async def _handle_fast_chat(session_id: str, user_id: str, content: str, websocket: WebSocket, capabilities: dict = None, deep_thinking: bool = False):
    """统一对话 handler：Agent Loop 真流式对话引擎

    Phase 1 重构：
    - 使用 AgentLoop.run() 进行真流式对话
    - 整合 ContextAssemblyPipeline（5层压缩 + WorkingMemory + 相关记忆）
    - 删除硬编码关键词路由、伪流式、[[DELEGATE:...]] 标记
    - 工具列表从 MCP Gateway + 本地工具动态获取
    """
    capabilities = capabilities or {}
    import time
    start_ts = time.time()

    # ========== 0. 会话管理 ==========
    try:
        if state.state_store:
            try:
                s = await state.state_store.load(session_id)
            except KeyError:
                await state.state_store.create(
                    session_id=session_id,
                    task=content,
                    user_id=user_id,
                    title=content[:30] + "..." if len(content) > 30 else content
                )
            await state.state_store.append_message(session_id, "user", content)
    except Exception as e:
        logger.warning(f"[FastChat] 会话操作失败 [{session_id}]: {e}")

    # ========== 1. 使用新 Agent Loop（如果可用）==========
    if state.agent_loop and state._llm:
        try:
            await _handle_fast_chat_v2(
                session_id, user_id, content, websocket,
                capabilities, deep_thinking, start_ts
            )
            return
        except Exception as e:
            logger.error(f"[FastChat] AgentLoop 失败，回退到旧逻辑: {e}", exc_info=True)
            # 回退到旧逻辑（保留在函数末尾）

    # ========== 2. 回退逻辑（AgentLoop 未初始化时）==========
    await _handle_fast_chat_legacy(
        session_id, user_id, content, websocket,
        capabilities, deep_thinking, start_ts
    )


async def _handle_fast_chat_v2(
    session_id: str, user_id: str, content: str, websocket: WebSocket,
    capabilities: dict, deep_thinking: bool, start_ts: float
):
    import time
    """Phase 1 重构后的真流式对话处理"""
    reply = ""
    reasoning_text = ""
    conversation_for_cache = None

    # --- 1.1 构建 persona_hint ---
    persona_hint = ""
    if state.persona_profiler:
        try:
            profile = state.persona_profiler.get_profile(user_id)
            if profile:
                persona_hint = _build_persona_hint(profile)
        except Exception:
            pass

    # --- 1.2 构建 mode_fragment ---
    mode_fragment = ""
    has_tools = bool(capabilities.get("web_search") or capabilities.get("file_ops"))
    if state.mode_router:
        try:
            mode_name = "unified" if has_tools else "chat"
            mode_fragment = state.mode_router.get_system_prompt_fragment(mode_name)
        except Exception:
            pass

    # --- 1.3 更新 WorkingMemory ---
    working_memory_text = ""
    if state.working_memory_manager:
        try:
            slots = state.working_memory_manager.update(user_query=content)
            working_memory_text = state.working_memory_manager.get_context_text(max_chars=2000)
        except Exception as e:
            logger.debug(f"[FastChat] WorkingMemory 更新失败: {e}")

    # --- 1.4 召回相关记忆（向量语义搜索）---
    relevant_memories = None
    if state.embedding_client and state.memory_store:
        try:
            query_vector = await state.embedding_client.embed(content)
            if query_vector:
                relevant_memories = await state.memory_store.search(
                    query_vector=query_vector,
                    limit=5,
                )
        except Exception as e:
            logger.debug(f"[FastChat] 记忆召回失败: {e}")

    # --- 1.5 加载对话历史 ---
    conversation_history = []
    try:
        cached_hist = state._session_msg_cache.get(session_id, [])
        if cached_hist:
            conversation_history = list(cached_hist)
        elif state.state_store:
            hist = await state.state_store.get_messages(session_id, limit=100)
            conversation_history = [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in hist
                if m.get("role") and m.get("content")
            ]
    except Exception:
        pass

    # --- 1.6 定义流式回调（同步回调，内部用 create_task 发 WS）---
    # FIX: 使用 send_to_session 替代 send_to(websocket)，避免断线重连后消息丢失
    def _on_chunk(text: str, chunk_type: str = "content"):
        nonlocal reply, reasoning_text
        if chunk_type == "reasoning":
            reasoning_text += text
            try:
                asyncio.create_task(ws_manager.send_to_session(session_id, {
                    "type": "chat.reasoning_chunk",
                    "payload": {"content": text, "session_id": session_id},
                }))
            except Exception:
                pass
        else:
            reply += text
            try:
                asyncio.create_task(ws_manager.send_to_session(session_id, {
                    "type": "chat.stream_chunk",
                    "payload": {"content": text, "session_id": session_id},
                }))
            except Exception:
                pass

    def _on_tool_call(tool_info: Dict):
        try:
            asyncio.create_task(ws_manager.send_to_session(session_id, {
                "type": "chat.tool_call",
                "payload": {
                    "session_id": session_id,
                    "tool": tool_info.get("tool", ""),
                    "arguments": tool_info.get("arguments", {}),
                },
            }))
        except Exception:
            pass

    def _on_tool_result(result_info: Dict):
        try:
            asyncio.create_task(ws_manager.send_to_session(session_id, {
                "type": "chat.tool_result",
                "payload": {
                    "session_id": session_id,
                    "tool": result_info.get("tool", ""),
                    "result": result_info.get("result", ""),
                },
            }))
        except Exception:
            pass

    # --- 1.7 执行 Agent Loop（真流式）---
    try:
        result = await state.agent_loop.run(
            session_id=session_id,
            user_id=user_id,
            user_message=content,
            websocket=websocket,
            capabilities=capabilities,
            deep_thinking=deep_thinking,
            system_prompt_base=FAST_CHAT_SYSTEM_PROMPT,
            persona_hint=persona_hint,
            mode_fragment=mode_fragment,
            working_memory_text=working_memory_text,
            relevant_memories=relevant_memories,
            conversation_history=conversation_history,
            on_chunk=_on_chunk,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
        )
        reply = result.get("content", "")
        reasoning_text = result.get("reasoning", "")
        conversation_for_cache = result.get("conversation_messages", conversation_history)
    except Exception as e:
        logger.error(f"[FastChat] AgentLoop 执行失败 [{session_id}]: {e}", exc_info=True)
        reply = "抱歉，处理过程中出现了一些问题，请稍后再试。"
        try:
            await ws_manager.send_to(websocket, {
                "type": "chat.stream_chunk",
                "payload": {"content": reply, "session_id": session_id},
            })
        except Exception:
            pass

    # --- 1.8 发送完成消息 ---
    elapsed_ms = int((time.time() - start_ts) * 1000)
    completion_payload = {
        "content": reply,
        "session_id": session_id,
        "follow_up_questions": [],  # Phase 1 删除硬编码追问，后续通过 Skills 实现
        "capabilities": capabilities,
        "deep_thinking": deep_thinking,
        "reasoning": reasoning_text.strip(),
        "elapsed_ms": elapsed_ms,
    }
    try:
        await ws_manager.send_to(websocket, {
            "type": "chat.completed",
            "payload": completion_payload,
        })
    except Exception:
        pass

    # --- 1.9 保存 AI 回复 ---
    try:
        if state.state_store:
            await state.state_store.append_message(session_id, "assistant", reply)
    except Exception as e:
        logger.warning(f"[FastChat] 保存AI回复失败 [{session_id}]: {e}")

    # --- 1.10 更新会话消息缓存 ---
    try:
        if conversation_for_cache is not None:
            conversation_for_cache.append({"role": "assistant", "content": reply})
            non_system = [m for m in conversation_for_cache if m.get("role") != "system"]
            state._session_msg_cache[session_id] = non_system[-40:]
    except Exception:
        pass

    # --- 1.11 后台任务（记忆入库、关系提取等）---
    _schedule_background_tasks(session_id, user_id, content, reply)


async def _handle_fast_chat_legacy(
    session_id: str, user_id: str, content: str, websocket: WebSocket,
    capabilities: dict, deep_thinking: bool, start_ts: float
):
    import time
    """旧版对话处理（AgentLoop 初始化失败时的回退）"""
    # 保留旧逻辑的核心，但简化
    has_tools = bool(capabilities.get("web_search") or capabilities.get("file_ops"))
    reasoning_text = ""
    reply = ""
    conversation_for_cache = None

    if not state._llm:
        reply = "系统正在初始化，请稍后再试。"
    else:
        try:
            # 简化版：直接使用 chat_stream
            messages = [
                {"role": "system", "content": FAST_CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ]

            if hasattr(state._llm, "chat_stream"):
                def _legacy_on_chunk(text: str, ctype: str = "content"):
                    if ctype == "reasoning":
                        nonlocal reasoning_text
                        reasoning_text += text
                        asyncio.create_task(
                            ws_manager.send_to_session(session_id, {
                                "type": "chat.reasoning_chunk",
                                "payload": {"content": text, "session_id": session_id},
                            })
                        )
                    else:
                        asyncio.create_task(
                            ws_manager.send_to_session(session_id, {
                                "type": "chat.stream_chunk",
                                "payload": {"content": text, "session_id": session_id},
                            })
                        )
                reply = await state._llm.chat_stream(
                    messages=messages,
                    on_chunk=_legacy_on_chunk,
                    temperature=0.7,
                    max_tokens=4096,
                )
            else:
                reply = await state._llm.chat(messages, temperature=0.7, max_tokens=4096)
                await ws_manager.send_to_session(session_id, {
                    "type": "chat.stream_chunk",
                    "payload": {"content": reply, "session_id": session_id},
                })
        except Exception as e:
            logger.warning(f"[FastChat] Legacy 调用失败 [{session_id}]: {e}")
            reply = "抱歉，我暂时无法回应。请稍后再试。"

    if not reply or not reply.strip():
        reply = "我在听，请继续说。"

    # 发送完成
    elapsed_ms = int((time.time() - start_ts) * 1000)
    try:
        await ws_manager.send_to_session(session_id, {
            "type": "chat.completed",
            "payload": {
                "content": reply,
                "session_id": session_id,
                "follow_up_questions": [],
                "capabilities": capabilities,
                "deep_thinking": deep_thinking,
                "reasoning": reasoning_text.strip(),
                "elapsed_ms": elapsed_ms,
            },
        })
    except Exception:
        pass

    # 保存
    try:
        if state.state_store:
            await state.state_store.append_message(session_id, "assistant", reply)
    except Exception as e:
        logger.warning(f"[FastChat] 保存AI回复失败 [{session_id}]: {e}")

    _schedule_background_tasks(session_id, user_id, content, reply)


def _build_persona_hint(profile) -> str:
    """从 PersonaProfile 构建轻量级人格提示"""
    fragments = []
    basic_parts = []
    if getattr(profile, "name", None):
        basic_parts.append(f"姓名：{profile.name}")
    if getattr(profile, "age", None):
        basic_parts.append(f"年龄：{profile.age}")
    if getattr(profile, "gender", None):
        basic_parts.append(f"性别：{profile.gender}")
    if getattr(profile, "occupation", None):
        basic_parts.append(f"职业：{profile.occupation}")
    if getattr(profile, "location", None):
        basic_parts.append(f"现居地：{profile.location}")
    if getattr(profile, "hometown", None):
        basic_parts.append(f"故乡：{profile.hometown}")
    if getattr(profile, "education", None):
        basic_parts.append(f"教育：{profile.education}")
    if getattr(profile, "bio", None):
        basic_parts.append(f"简介：{profile.bio[:100]}")
    if basic_parts:
        fragments.append("；".join(basic_parts))

    if getattr(profile, "language_style", None):
        fragments.append(f"语言风格：{profile.language_style[:120]}")

    try:
        catchphrases = json.loads(getattr(profile, "catchphrases", "[]") or "[]")
        if catchphrases:
            fragments.append(f"常用口头禅：{', '.join(catchphrases[:3])}")
    except Exception:
        pass

    try:
        quirks = json.loads(getattr(profile, "speaking_quirks", "[]") or "[]")
        if quirks:
            fragments.append(f"说话习惯：{', '.join(quirks[:2])}")
    except Exception:
        pass

    try:
        imperfections = json.loads(getattr(profile, "imperfections", "[]") or "[]")
        if imperfections:
            fragments.append(f"不完美（保留这些特征，不要优化掉）：{', '.join(imperfections[:2])}")
    except Exception:
        pass

    if getattr(profile, "relationship_style", None):
        fragments.append(f"对待关系：{profile.relationship_style[:80]}")

    if fragments:
        return "\n\n【关于用户的轻量提示】" + "；".join(fragments)
    return ""


def _schedule_background_tasks(session_id: str, user_id: str, content: str, reply: str):
    """调度后台任务（记忆入库、关系提取、情绪检测等）"""
    # 记忆入库
    try:
        if state.memory_store:
            conversation_text = f"用户：{content}\n\nAI：{reply}"
            uri = f"session://{session_id}/turn/{int(time.time())}"
            asyncio.create_task(
                state.memory_store.ingest(
                    content=conversation_text,
                    uri=uri,
                    memory_type="conversation",
                    user_id=user_id,
                )
            )
    except Exception as e:
        logger.debug(f"[FastChat] 记忆入库失败 [{session_id}]: {e}")

    # 深度关系提取
    try:
        if state.relation_extractor and state.cognitive_graph:
            buf = state._session_context_buffer.setdefault(session_id, [])
            buf.append(f"用户: {content}\nAI: {reply}")
            if len(buf) > 5:
                buf.pop(0)
            if len(state._session_context_buffer) > 50:
                oldest = sorted(state._session_context_buffer.keys())[:10]
                for old_sid in oldest:
                    del state._session_context_buffer[old_sid]

            aggregated_text = "\n---\n".join(buf)
            asyncio.create_task(_extract_relations_background(
                aggregated_text, user_id, session_id
            ))
    except Exception as e:
        logger.debug(f"[FastChat] 关系提取调度失败 [{session_id}]: {e}")

    # 情绪检测（广播改为发送给特定 session）
    try:
        if state.emotion_detector:
            emotion = state.emotion_detector.detect_fast(content)
            asyncio.create_task(ws_manager.send_to_session(
                session_id,
                {
                    "type": "user.emotion",
                    "payload": {
                        "session_id": session_id,
                        "emotion": emotion.primary,
                        "intensity": emotion.intensity,
                        "valence": emotion.valence,
                        "arousal": emotion.arousal,
                        "confidence": emotion.confidence,
                    },
                }
            ))
    except Exception:
        pass


async def _extract_relations_background(aggregated_text: str, user_id: str, session_id: str):
    """后台关系提取任务"""
    try:
        if state.relation_extractor and state.cognitive_graph:
            deep_result = await state.relation_extractor.extract_deep(
                text=aggregated_text,
                user_id=user_id,
                session_id=session_id,
            )
            entities = deep_result.get("entities", [])
            relations = deep_result.get("relations", [])
            if entities or relations:
                state.relation_extractor.save_to_graph(
                    entities=entities,
                    relations=relations,
                    user_id=user_id,
                    session_id=session_id,
                    source_chunk=aggregated_text[:300],
                )
                logger.debug(f"[FastChat] 深度关系提取完成 [{session_id}] 实体:{len(entities)} 关系:{len(relations)}")
    except Exception as e:
        logger.debug(f"[FastChat] 深度关系提取失败 [{session_id}]: {e}")


# ========== 全局状态 ==========

class APIServerState:
    def __init__(self):
        self.bus = None
        self.state_store = None
        self.config = None
        self.pending_results: Dict[str, asyncio.Future] = {}
        self._db: Optional[sqlite3.Connection] = None
        self._results_cache: Dict[str, Dict] = {}
        self._pending_count: Dict[str, int] = {}
        self._pending_approvals: Dict[str, Dict] = {}
        self._last_vision_emotion: Dict[str, str] = {}
        self._nats_subscriptions = []
        self._dreaming = None
        self._llm = None
        self.governance_worker = None
        # 死亡事件缓存：user_id -> datetime（内存缓存，避免频繁查库）
        self._death_events: Dict[str, str] = {}
        # Eternal mode prompt cache: user_id -> {static_hash, static_prompt, timestamp}
        self._eternal_prompt_cache: Dict[str, Dict] = {}
        # Fast chat prompt cache: "user_id:mode" -> {hash, static_prompt}
        self._fast_chat_prompt_cache: Dict[str, Dict] = {}
        # 记忆压缩追踪器：user_id -> {accumulated_tokens, last_compress_time, session_tokens}
        # 基于工作量（Token累积+时间）触发压缩，而非简单消息计数
        self._compression_tracker: Dict[str, Dict] = {}
        # 会话上下文缓冲区：session_id -> 最近N个回合的文本（用于聚合关系提取）
        self._session_context_buffer: Dict[str, List[str]] = {}
        # 会话消息缓存：保存完整对话历史（含 tool_call/tool_result），供 approval 等跨轮次上下文使用
        self._session_msg_cache: Dict[str, List[Dict]] = {}
        self.soul_layer = None
        self.memory_store = None
        self.emotion_detector = None
        self.emotion_service = None
        self.soul_evolution = None
        self.cognitive_graph = None
        self.relation_extractor = None
        self.tool_executor = None
        # Multi-Agent System
        self.agent_manager = None
        self.agent_runtime_pool = None
        # Agent Core (Phase 1 refactor)
        self.context_assembler = None
        self.agent_loop = None
        self.working_memory_manager = None
        self.mcp_gateway = None
        # Phase 2 peripherals
        self.security_pipeline = None
        self.hook_engine = None
        self.speculative_executor = None

    async def setup(self, config: Dict):
        self.config = config
        self.bus = create_message_bus(config)
        await self.bus.connect()
        self.state_store = create_state_store(config)
        # 如果已由 TentOS 主进程注入，保留现有 LLM
        if self._llm is None:
            try:
                self._llm = create_llm(config)
                logger.info(f"LLM 初始化成功 (soul_server)")
            except Exception as e:
                logger.warning(f"LLM 初始化失败: {e}")
        else:
            logger.info(f"LLM 已由主进程注入，跳过重复初始化")

        # 初始化记忆存储（供前端查询）
        try:
            from tent_os.memory.tiered_store import TieredMemoryStore
            from tent_os.memory.emotion_detector import EmotionDetector
            from tent_os.llm.embedding import EmbeddingClient
            storage_path = config.get("memory", {}).get("storage_path", "./tent_memory")
            self.memory_store = TieredMemoryStore(storage_path, llm=self._llm)
            self.emotion_detector = EmotionDetector(llm=self._llm)
            from tent_os.services.emotion_service import EmotionService
            self.emotion_service = EmotionService()
            # Embedding client for semantic search in eternal chat
            openai_api_key = config.get("llm", {}).get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
            if openai_api_key and (openai_api_key.startswith("${") or openai_api_key.strip() == ""):
                openai_api_key = None
            self.embedding_client = EmbeddingClient(
                openai_api_key=openai_api_key,
                dim=1536,
            )
            logger.info(f"[SOUL] 记忆存储与情绪检测已初始化 (embedding={self.embedding_client.provider_name})")
        except Exception as e:
            logger.warning(f"[SOUL] 记忆存储初始化失败: {e}")
            self.embedding_client = None
        
        # 初始化工具执行器（供 intuition/deep 模式直接调用工具）
        try:
            from tent_os.scheduler.executors.local import LocalExecutor
            from tent_os.tools.executor import ToolExecutor
            local_executor = LocalExecutor()
            local_config = config.get("local_executor", {})
            # 调用 initialize 传入完整配置（包含安全开关）
            init_cfg = {
                "allow_write": local_config.get("allow_write", True),
                "workspace_mode": local_config.get("workspace_mode", "unrestricted"),
                "timeout_seconds": local_config.get("timeout_seconds", 30),
                "auto_approve": not local_config.get("approval_required", True),
            }
            # 如果用户配置了 blocked_patterns，传入；否则使用默认（安全拦截）
            if "blocked_patterns" in local_config:
                init_cfg["blocked_patterns"] = local_config["blocked_patterns"]
            if "allowed_commands" in local_config:
                init_cfg["allowed_commands"] = local_config["allowed_commands"]
            await local_executor.initialize(init_cfg)
            self.tool_executor = ToolExecutor(
                local_executor=local_executor,
                memory_store=self.memory_store,
                embedding_client=getattr(self, "embedding_client", None),
            )
            logger.info(f"[Tools] 工具执行器已初始化（安全拦截={len(local_executor.blocked_patterns)}条规则, allow_write={local_executor.allow_write}）")
            
            # 初始化 MCP Server 管理器（外部工具调用）
            try:
                from tent_os.tools.mcp.manager import MCPServerManager
                self.mcp_manager = MCPServerManager()
                self.tool_executor.set_mcp_manager(self.mcp_manager)
                # 异步连接所有已配置的 Server
                asyncio.create_task(self.mcp_manager.connect_all())
                logger.info("[MCP] MCP Server 管理器已初始化")
            except Exception as mcp_e:
                logger.warning(f"[MCP] MCP 管理器初始化失败: {mcp_e}")
                self.mcp_manager = None
        except Exception as e:
            logger.warning(f"[Tools] 工具执行器初始化失败: {e}")
            self.tool_executor = None
        
        # ========== 初始化 Agent Core（Phase 1 重构）==========
        try:
            from tent_os.agent.context_assembly import ContextAssemblyPipeline
            from tent_os.agent.loop import AgentLoop
            from tent_os.memory.working_memory import WorkingMemoryManager
            from tent_os.memory.predictive_preloader import PredictivePreloader

            # 1. Context Assembly Pipeline
            self.context_assembler = ContextAssemblyPipeline(
                llm=self._llm,
                config=config.get("agent", {}),
            )

            # 2. Working Memory Manager
            if self.cognitive_graph:
                preloader = PredictivePreloader(self.cognitive_graph)
                self.working_memory_manager = WorkingMemoryManager(
                    graph=self.cognitive_graph,
                    preloader=preloader,
                )

            # 3. MCP Gateway（优先使用 GatewayRegistry，回退到 ServerManager）
            try:
                from tent_os.plugins.mcp_gateway import MCPGatewayRegistry
                self.mcp_gateway = MCPGatewayRegistry(config=config.get("mcp", {}))
                await self.mcp_gateway.start()
                logger.info("[MCP] MCP Gateway 已初始化")
            except Exception as gw_e:
                logger.debug(f"[MCP] Gateway 初始化失败，使用 ServerManager: {gw_e}")
                self.mcp_gateway = getattr(self, "mcp_manager", None)

            # 4. Security Pipeline（System 1 + System 2 安全评估）
            try:
                from tent_os.agent.security import SecurityPipeline, ModeManager
                self.security_pipeline = SecurityPipeline(
                    mode_manager=ModeManager(state_store=self.state_store),
                )
                logger.info("[AGENT] Security Pipeline 已初始化")
            except Exception as sec_e:
                logger.warning(f"[AGENT] Security Pipeline 初始化失败: {sec_e}")
                self.security_pipeline = None

            # 5. Hook Engine（工具拦截与修改）
            try:
                from tent_os.agent.hooks import HookEngine
                self.hook_engine = HookEngine()
                logger.info("[AGENT] Hook Engine 已初始化")
            except Exception as hook_e:
                logger.warning(f"[AGENT] Hook Engine 初始化失败: {hook_e}")
                self.hook_engine = None

            # 6. Speculative Executor（只读工具预执行）
            try:
                from tent_os.agent.speculative import SpeculativeExecutor
                spec_cfg = config.get("agent", {}).get("speculative", {})
                self.speculative_executor = SpeculativeExecutor(
                    tool_executor=self.tool_executor,
                    max_concurrent=spec_cfg.get("max_concurrent", 3),
                    cooldown_seconds=spec_cfg.get("cooldown_seconds", 2.0),
                )
                logger.info("[AGENT] Speculative Executor 已初始化")
            except Exception as spec_e:
                logger.warning(f"[AGENT] Speculative Executor 初始化失败: {spec_e}")
                self.speculative_executor = None

            # 7. Agent Loop
            self.agent_loop = AgentLoop(
                llm=self._llm,
                context_assembler=self.context_assembler,
                tool_executor=self.tool_executor,
                mcp_gateway=self.mcp_gateway,
                state_store=self.state_store,
                security_pipeline=self.security_pipeline,
                hook_engine=self.hook_engine,
                speculative_executor=self.speculative_executor,
                config=config.get("agent", {}),
            )
            logger.info("[AGENT] Agent Core 已初始化")
        except Exception as e:
            logger.warning(f"[AGENT] Agent Core 初始化失败: {e}")
            self.agent_loop = None
        
        # 初始化人格演化引擎
        try:
            from tent_os.persona.soul_evolution import SoulEvolution
            soul_storage = config.get("soul", {}).get("storage_path", "./tent_memory/soul")
            self.soul_evolution = SoulEvolution(f"{soul_storage}/soul.json", llm=self._llm)
            logger.info("[SOUL] 人格演化引擎已初始化")
        except Exception as e:
            logger.warning(f"[SOUL] 人格演化引擎初始化失败: {e}")
        
        # 初始化认知图谱 + 关系提取器
        try:
            from tent_os.memory.graph import CognitiveGraph
            from tent_os.soul.relation_extractor import RelationExtractor
            graph_db = config.get("memory", {}).get("graph_db", "./tent_memory/graph.db")
            self.cognitive_graph = CognitiveGraph(graph_db)
            self.relation_extractor = RelationExtractor(
                graph=self.cognitive_graph,
                llm=self._llm,
            )
            logger.info("[SOUL] 认知图谱与关系提取器已初始化")
        except Exception as e:
            logger.warning(f"[SOUL] 认知图谱初始化失败: {e}")
        
        # 初始化 Multi-Agent System
        try:
            from tent_os.soul.agent_manager import AgentManager
            from tent_os.soul.agent_runtime import AgentRuntimePool
            from tent_os.soul.agent_orchestrator import AgentOrchestrator
            from tent_os.soul.skills.manager import AgentSkillManager
            agent_storage = config.get("agent", {}).get("storage_path", "./tent_memory/agents")
            self.agent_manager = AgentManager(storage_path=agent_storage)
            self.agent_runtime_pool = AgentRuntimePool()
            self.agent_runtime_pool.set_dependencies(llm=self._llm, tool_executor=self.tool_executor)
            # 初始化技能树管理器（P4: Agent成长系统）
            self.skill_manager = AgentSkillManager(f"{agent_storage}/agent_skills.db")
            self.agent_orchestrator = AgentOrchestrator(
                llm=self._llm,
                agent_manager=self.agent_manager,
                runtime_pool=self.agent_runtime_pool,
                skill_manager=self.skill_manager,
                config=config,
            )
            # 为已有Agent初始化技能树
            try:
                for agent in self.agent_manager.list_agents():
                    existing = self.skill_manager.get_agent_skills(agent.id)
                    if not existing:
                        self.skill_manager.init_agent_skills(agent.id, agent.role)
                logger.info(f"[MAS] Agent 技能树已初始化")
            except Exception as skill_e:
                logger.debug(f"[MAS] Agent技能树初始化（部分）: {skill_e}")
            logger.info(f"[MAS] Agent 管理系统已初始化 ({agent_storage})")
        except Exception as e:
            logger.warning(f"[MAS] Agent 管理系统初始化失败: {e}")
        
        # 初始化人格画像引擎
        try:
            soul_storage = config.get("soul", {}).get("storage_path", "./tent_memory/soul")
            self.persona_profiler = PersonaProfiler(llm=self._llm, storage_path=soul_storage)
            logger.info("[SOUL] 人格画像引擎已初始化")
        except Exception as e:
            logger.warning(f"[SOUL] 人格画像引擎初始化失败: {e}")
            self.persona_profiler = None
        
        # 初始化外部语料导入管道
        try:
            from tent_os.soul.ingestion.pipeline import ExternalIngestionPipeline
            self.ingestion_pipeline = ExternalIngestionPipeline(
                memory_store=self.memory_store,
                persona_profiler=self.persona_profiler,
                embedding_client=self.embedding_client,
                llm=self._llm,
            )
            logger.info("[Ingestion] 外部语料导入管道已初始化")
        except Exception as e:
            logger.warning(f"[Ingestion] 导入管道初始化失败: {e}")
            self.ingestion_pipeline = None
        
        # 初始化声音克隆路由器
        try:
            from tent_os.soul.cloning.voice_clone_engine import VoiceCloneRouter
            self.voice_clone_router = VoiceCloneRouter()
            logger.info("[VoiceClone] 声音克隆路由器已初始化")
        except Exception as e:
            logger.warning(f"[VoiceClone] 初始化失败: {e}")
            self.voice_clone_router = None
        
        # 初始化授权引擎（遗嘱管理）
        try:
            soul_storage = config.get("soul", {}).get("storage_path", "./tent_memory/soul")
            self.authorization = AuthorizationEngine(storage_path=soul_storage)
            logger.info("[SOUL] 授权引擎已初始化")
        except Exception as e:
            logger.warning(f"[SOUL] 授权引擎初始化失败: {e}")
            self.authorization = None
        
        # === 初始化灵魂积累层（兼容独立启动模式）===
        # 大量前端路由依赖 soul_layer，必须在独立启动模式下也初始化
        try:
            soul_storage = config.get("soul", {}).get("storage_path", "./tent_memory/soul")
            self.soul_layer = {
                "thought_extractor": ThoughtExtractor(soul_storage),
                "voice_modeler": VoiceModeler(soul_storage),
                "appearance_modeler": AppearanceModeler(soul_storage),
                "style_finetuner": StyleFinetuner(soul_storage),
                "tts_synthesizer": TTSSynthesizer(soul_storage),
                "authorization": self.authorization or AuthorizationEngine(soul_storage),
                "encryption": SoulEncryption(config.get("soul", {}).get("password")),
                "persona_profiler": self.persona_profiler or PersonaProfiler(llm=self._llm, storage_path=soul_storage),
            }
            logger.info("[SOUL] 灵魂积累层已初始化（独立启动模式兼容）")
        except Exception as e:
            logger.warning(f"[SOUL] 灵魂积累层初始化失败: {e}")
            self.soul_layer = None
        
        # 初始化模式路由器（P1: 直觉模式）
        try:
            self.mode_router = get_mode_router()
            logger.info("[ModeRouter] 模式路由器已初始化（支持 chat/intuition/deep 三种模式）")
        except Exception as e:
            logger.warning(f"[ModeRouter] 初始化失败: {e}")
            self.mode_router = None
        
        # 初始化 ASR 服务
        try:
            from tent_os.soul.asr_service import ASRService
            asr_config = config.get("asr", {})
            # 从环境变量或 LLM 配置中继承 API key
            if not asr_config.get("api_key"):
                asr_config["api_key"] = config.get("llm", {}).get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
            self.asr_service = ASRService(asr_config)
            logger.info(f"[ASR] 服务已初始化: provider={self.asr_service.provider}, available={self.asr_service.is_available()}")
        except Exception as e:
            logger.warning(f"[ASR] 初始化失败: {e}")
            self.asr_service = None
        
        # 初始化情感依赖守护引擎（P4: 安全层）
        try:
            self.dependency_guardian = DependencyGuardian(soul_storage)
            logger.info("[Guardian] 情感依赖守护引擎已初始化")
        except Exception as e:
            logger.warning(f"[Guardian] 初始化失败: {e}")
            self.dependency_guardian = None

        db_path = config.get("scheduler", {}).get("db_path", "./tent_scheduler.db")
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.row_factory = sqlite3.Row
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS approval_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                plan_summary TEXT,
                approved INTEGER,
                approved_by TEXT DEFAULT 'web_user',
                created_at TEXT DEFAULT (datetime('now')),
                decided_at TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'web_user',
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                due_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS message_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER,
                feedback_type TEXT NOT NULL,
                correction TEXT,
                user_id TEXT DEFAULT 'web_user',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._db.commit()

        sub1 = await self.bus.nats.subscribe("governance.response.*", cb=self._on_governance_response)
        self._nats_subscriptions.append(sub1)
        sub_stream = await self.bus.nats.subscribe("governance.stream.*", cb=self._on_stream_chunk)
        self._nats_subscriptions.append(sub_stream)
        sub_reasoning = await self.bus.nats.subscribe("governance.stream.reasoning.*", cb=self._on_reasoning_chunk)
        self._nats_subscriptions.append(sub_reasoning)
        sub_monologue = await self.bus.nats.subscribe("governance.stream.monologue.*", cb=self._on_monologue_chunk)
        self._nats_subscriptions.append(sub_monologue)
        sub2 = await self.bus.nats.subscribe("governance.plan_update.*", cb=self._on_plan_update)
        self._nats_subscriptions.append(sub2)
        sub3 = await self.bus.nats.subscribe("scheduler.step_update.*", cb=self._on_step_update)
        self._nats_subscriptions.append(sub3)
        sub_approval = await self.bus.nats.subscribe("governance.approval.request", cb=self._on_approval_request)
        self._nats_subscriptions.append(sub_approval)
        sub_emotion = await self.bus.nats.subscribe("emotion.broadcast", cb=self._on_emotion_broadcast)
        self._nats_subscriptions.append(sub_emotion)
        sub_fused = await self.bus.nats.subscribe("emotion.fused", cb=self._on_emotion_fused)
        self._nats_subscriptions.append(sub_fused)
        sub_sys_health = await self.bus.nats.subscribe("system.health_alert", cb=self._on_system_health_alert)
        self._nats_subscriptions.append(sub_sys_health)

        logger.info("API Server 已连接消息总线 —— Tent OS 灵魂对讲机模式")
        
        # === 启动记忆压缩后台任务 ===
        self._start_memory_compression_task()

    def _start_memory_compression_task(self):
        """启动后台定时记忆压缩任务（L0→L1）"""
        async def _compress_loop():
            while True:
                try:
                    await asyncio.sleep(1800)  # 每30分钟运行一次
                    if self.memory_store and self._llm:
                        logger.info("[MemoryCompression] 启动定时 L0→L1 压缩...")
                        result = await self.memory_store.auto_compress_l0_to_l1(
                            user_id=None,  # 处理所有用户
                            hours=24,
                        )
                        logger.info(
                            f"[MemoryCompression] 完成: {result.get('compressed_count', 0)} 条记录 → "
                            f"{len(result.get('generated_uris', []))} 个 L1 摘要"
                        )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"[MemoryCompression] 压缩任务出错: {e}")
        
        self._compression_task = asyncio.create_task(_compress_loop())
        logger.info("[MemoryCompression] 后台定时压缩任务已启动（每30分钟）")

    async def cleanup(self):
        if hasattr(self, '_compression_task') and self._compression_task:
            self._compression_task.cancel()
            try:
                await self._compression_task
            except asyncio.CancelledError:
                pass
        # 断开所有 MCP Server
        if hasattr(self, 'mcp_manager') and self.mcp_manager:
            try:
                await self.mcp_manager.disconnect_all()
                logger.info("[MCP] 所有 Server 已断开")
            except Exception:
                pass
        for sub in self._nats_subscriptions:
            await sub.unsubscribe()
        if self.bus:
            await self.bus.close()
        if self._db:
            self._db.close()
        logger.info("API Server 已断开消息总线")

    # ========== 死亡事件管理 ==========
    
    def set_death_event(self, user_id: str, death_time: Optional[datetime] = None) -> bool:
        """标记用户死亡事件"""
        if not self.persona_profiler:
            return False
        try:
            self.persona_profiler.set_death_event(user_id, death_time)
            self._death_events[user_id] = (death_time or datetime.now()).isoformat()
            return True
        except Exception as e:
            logger.error(f"[DeathEvent] 标记失败 [{user_id}]: {e}")
            return False
    
    def clear_death_event(self, user_id: str) -> bool:
        """清除死亡事件标记"""
        if not self.persona_profiler:
            return False
        try:
            self.persona_profiler.clear_death_event(user_id)
            self._death_events.pop(user_id, None)
            return True
        except Exception as e:
            logger.error(f"[DeathEvent] 清除失败 [{user_id}]: {e}")
            return False
    
    def get_death_event(self, user_id: str) -> Optional[str]:
        """获取用户死亡事件时间"""
        # 先查内存缓存
        if user_id in self._death_events:
            return self._death_events[user_id]
        
        # 再查数据库
        if self.persona_profiler:
            profile = self.persona_profiler.get_profile(user_id)
            if profile and profile.death_event:
                self._death_events[user_id] = profile.death_event
                return profile.death_event
        
        return None
    
    def is_post_mortem(self, user_id: str, timestamp: Optional[datetime] = None) -> bool:
        """检查给定时间是否在死亡事件之后"""
        death_event = self.get_death_event(user_id)
        if not death_event:
            return False
        
        try:
            death_time = datetime.fromisoformat(death_event)
        except (ValueError, TypeError):
            return False
        
        check_time = timestamp or datetime.now()
        return check_time > death_time

    async def _on_governance_response(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            msg_type = data.get("type", "")
            error = data.get("error")
            if msg_type == "chat.completed":
                result = data.get("content", "")
            else:
                result = data.get("result")
            if session_id:
                self._pending_count[session_id] = self._pending_count.get(session_id, 0) - 1
                if self._pending_count.get(session_id, 0) <= 0:
                    task_id = f"chat_{uuid.uuid4().hex[:16]}"
                    self._results_cache[session_id] = {"status": "completed", "result": result, "task_id": task_id, "created_at": datetime.now().isoformat()}
                if session_id in self.pending_results and not self.pending_results[session_id].done():
                    self.pending_results[session_id].set_result(result)
                if msg_type == "chat.completed":
                    ws_type = "chat.completed"
                    ai_content = data.get("content", "")
                    payload = {
                        "session_id": session_id,
                        "content": ai_content,
                        "reasoning": data.get("reasoning", ""),
                        "source": data.get("source", ""),
                        "follow_up_questions": generate_follow_ups(ai_content),
                    }
                else:
                    ws_type = "task.failed" if error else "task.completed"
                    payload = {"session_id": session_id, "result": result if not error else None, "error": error}
                await ws_manager.send_to_session(session_id, {"type": ws_type, "payload": payload, "timestamp": asyncio.get_event_loop().time()})
        except Exception as e:
            logger.warning(f"处理治理响应出错: {e}")

    async def _on_plan_update(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {"type": "task.plan", "payload": data, "timestamp": asyncio.get_event_loop().time()})
        except Exception:
            pass

    async def _on_step_update(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {"type": "task.step", "payload": data, "timestamp": asyncio.get_event_loop().time()})
        except Exception:
            pass

    async def _on_approval_request(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                self._pending_approvals[session_id] = data
                try:
                    plan = data.get("plan", {})
                    summary = plan.get("summary") or plan.get("task") or json.dumps(plan, ensure_ascii=False)[:200]
                    self._db.execute(
                        "INSERT INTO approval_history (session_id, plan_summary, approved) VALUES (?, ?, ?)",
                        (session_id, summary, None)
                    )
                    self._db.commit()
                except Exception:
                    pass
                await ws_manager.send_to_session(session_id, {
                    "type": "approval.request",
                    "payload": {"session_id": session_id, "plan": data.get("plan", {})},
                    "timestamp": asyncio.get_event_loop().time(),
                })
        except Exception as e:
            logger.warning(f"处理审批请求出错: {e}")

    async def _on_emotion_broadcast(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            user_id = data.get("user_id", "web_user")
            await ws_manager.broadcast({
                "type": "ai.emotion",
                "payload": {"user_id": user_id, "emotion": data.get("emotion", "listening"), "source": data.get("source", "broadcast")},
                "timestamp": asyncio.get_event_loop().time(),
            })
        except Exception:
            pass

    async def _on_emotion_fused(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {
                    "type": "emotion.fused",
                    "payload": {
                        "user_id": data.get("user_id", "web_user"),
                        "session_id": session_id,
                        "primary": data.get("primary"),
                        "intensity": data.get("intensity"),
                    },
                    "timestamp": asyncio.get_event_loop().time(),
                })
        except Exception:
            pass

    async def _on_stream_chunk(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {"type": "chat.stream_chunk", "payload": data, "timestamp": asyncio.get_event_loop().time()})
        except Exception:
            pass

    async def _on_reasoning_chunk(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {"type": "chat.stream_reasoning", "payload": data, "timestamp": asyncio.get_event_loop().time()})
        except Exception:
            pass

    async def _on_monologue_chunk(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            session_id = data.get("session_id")
            if session_id:
                await ws_manager.send_to_session(session_id, {"type": "ai.monologue", "payload": data, "timestamp": asyncio.get_event_loop().time()})
        except Exception:
            pass

    async def _on_system_health_alert(self, msg):
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            await ws_manager.broadcast({
                "type": "system.health_alert",
                "payload": {"alert_type": data.get("alert_type"), "severity": data.get("severity", "warning"), "message": data.get("message")},
                "timestamp": asyncio.get_event_loop().time(),
            })
        except Exception:
            pass

    async def _query_tasks_by_session(self, session_id: str) -> List[sqlite3.Row]:
        if not self._db:
            return []
        def _exec():
            cursor = self._db.execute("SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at DESC", (session_id,))
            return cursor.fetchall()
        return await asyncio.to_thread(_exec)

    async def _query_all_tasks(self, limit: int = 50) -> List[sqlite3.Row]:
        if not self._db:
            return []
        def _exec():
            cursor = self._db.execute(
                "SELECT DISTINCT session_id, status, action as task, created_at, updated_at FROM tasks WHERE session_id IS NOT NULL ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return cursor.fetchall()
        return await asyncio.to_thread(_exec)


state = APIServerState()
