"""MCP 工具定义 —— 数字灵魂能力的标准化接口

每个工具对应数字灵魂的一个核心能力：
- chat: 与数字灵魂对话
- query_persona: 查询人格画像
- query_memories: 查询记忆
- query_relations: 查询关系图谱
- synthesize_tts: 语音合成
- query_avatar: 查询形象配置
"""

import json
from typing import Any, Dict, Optional

from tent_os.mcp.protocol import MCPTool
from tent_os.logging_config import get_logger

logger = get_logger()


def _get_state():
    """获取全局状态（延迟导入避免循环依赖）"""
    from tent_os.api.soul_state import state
    return state


async def _tool_chat(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """与数字灵魂对话"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    message = arguments.get("message", "")
    mode = arguments.get("mode", "chat")  # chat, intuition, deep

    if not message:
        return {"error": "message is required"}

    state = _get_state()
    if not state._llm:
        return {"error": "LLM not available"}

    # 构建 prompt（复用 eternal_chat 的逻辑简化版）
    system_parts = ["你是 Tent OS 数字灵魂。用自然、温暖的中文回复。"]

    # 注入人格
    if state.persona_profiler:
        profile = state.persona_profiler.get_profile(user_id)
        if profile:
            system_parts.append(profile.to_system_prompt_text())

    messages = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": message},
    ]

    try:
        reply = await state._llm.chat(messages, temperature=0.7, max_tokens=400)
        return {"reply": reply or "...", "speaker": "soul", "mode": mode}
    except Exception as e:
        return {"error": str(e)}


async def _tool_query_persona(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """查询人格画像"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    state = _get_state()

    if not state.persona_profiler:
        return {"error": "Persona profiler not available"}

    profile = state.persona_profiler.get_profile(user_id)
    if not profile:
        return {"status": "not_found", "user_id": user_id}

    return {
        "status": "ok",
        "user_id": user_id,
        "persona": profile.to_dict(),
    }


async def _tool_query_memories(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """查询记忆"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    query = arguments.get("query", "")
    limit = arguments.get("limit", 5)
    state = _get_state()

    if not state.memory_store:
        return {"error": "Memory store not available"}

    try:
        # 优先语义搜索
        if query and state.embedding_client:
            try:
                vec = await state.embedding_client.embed(query)
                results = await state.memory_store.search(vec, limit=limit)
                return {
                    "status": "ok",
                    "query": query,
                    "memories": results,
                }
            except Exception as e:
                logger.debug(f"[MCP] 语义搜索失败，降级: {e}")

        # 降级：最近记忆
        rows = state.memory_store.db.execute(
            "SELECT uri, abstract, created_at FROM l0_index WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        memories = [{"uri": r[0], "abstract": r[1], "created_at": r[2]} for r in rows]
        return {"status": "ok", "query": query, "memories": memories}
    except Exception as e:
        return {"error": str(e)}


async def _tool_query_relations(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """查询关系图谱"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    state = _get_state()

    if not state.cognitive_graph:
        return {"error": "Cognitive graph not available"}

    try:
        edges = state.cognitive_graph.get_edges("entity://user/self", direction="both")
        relations = []
        for e in edges[:20]:
            tgt = state.cognitive_graph.get_node(e.target_id)
            src = state.cognitive_graph.get_node(e.source_id)
            relations.append({
                "target": tgt.content if tgt else e.target_id,
                "source": src.content if src else e.source_id,
                "type": e.relation_type,
                "evidence": e.evidence,
            })
        return {"status": "ok", "user_id": user_id, "relations": relations}
    except Exception as e:
        return {"error": str(e)}


async def _tool_synthesize_tts(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """语音合成"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    text = arguments.get("text", "")
    emotion = arguments.get("emotion", "neutral")
    voice_key = arguments.get("voice_key")

    if not text:
        return {"error": "text is required"}

    state = _get_state()
    try:
        from tent_os.soul.tts_synthesizer import TTSSynthesizer
        import os
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if state.config and not openai_key:
            openai_key = state.config.get("llm", {}).get("openai_api_key", "")
        synth = TTSSynthesizer(openai_api_key=openai_key)
        result = await synth.synthesize(text, user_id=user_id, emotion=emotion, voice_key=voice_key)
        if result["status"] == "ok":
            return {
                "status": "ok",
                "audio_url": result["audio_url"],
                "voice": result.get("voice"),
                "source": result.get("source"),
            }
        return {"error": result.get("message", "TTS failed")}
    except Exception as e:
        return {"error": str(e)}


async def _tool_query_avatar(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """查询形象配置"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    state = _get_state()

    # 从 appearance_modeler 获取配置
    try:
        from tent_os.soul.appearance_modeler import AppearanceModeler
        am = AppearanceModeler()
        config = am.generate_avatar_config(user_id)
        stats = am.get_stats(user_id)
        return {
            "status": "ok",
            "user_id": user_id,
            "avatar_config": config,
            "stats": stats,
        }
    except Exception as e:
        return {"error": str(e)}


async def _tool_export_persona_packet(arguments: Dict, auth_context: Optional[Dict]) -> Dict:
    """导出完整人格数据包（用于跨设备迁移）"""
    user_id = arguments.get("user_id", auth_context.get("user_id") if auth_context else "default")
    state = _get_state()

    packet = {"version": "2.0", "user_id": user_id}

    # 人格画像
    if state.persona_profiler:
        profile = state.persona_profiler.get_profile(user_id)
        if profile:
            packet["persona"] = profile.to_dict()

    # 声音统计
    try:
        from tent_os.soul.voice_modeler import VoiceModeler
        vm = VoiceModeler()
        packet["voice"] = vm.get_stats(user_id)
    except Exception:
        pass

    # 形象统计
    try:
        from tent_os.soul.appearance_modeler import AppearanceModeler
        am = AppearanceModeler()
        packet["appearance"] = am.get_stats(user_id)
    except Exception:
        pass

    return {"status": "ok", "packet": packet}


# ======== 工具注册表 ========

ALL_TOOLS = [
    MCPTool(
        name="chat",
        description="与数字灵魂进行对话。传入用户消息，返回灵魂的自然语言回复。",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "用户输入的消息"},
                "mode": {"type": "string", "enum": ["chat", "intuition", "deep"], "description": "对话模式"},
            },
            "required": ["message"],
        },
        handler=_tool_chat,
    ),
    MCPTool(
        name="query_persona",
        description="查询用户的人格画像——包含语言风格、思维方式、情感模式等20维度分析。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
            },
            "required": [],
        },
        handler=_tool_query_persona,
    ),
    MCPTool(
        name="query_memories",
        description="查询用户的记忆库。支持语义搜索（传入query）或获取最近记忆。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
                "query": {"type": "string", "description": "搜索关键词（可选，不传则返回最近记忆）"},
                "limit": {"type": "integer", "description": "返回数量限制", "default": 5},
            },
            "required": [],
        },
        handler=_tool_query_memories,
    ),
    MCPTool(
        name="query_relations",
        description="查询用户的关系图谱——生命中重要的人及关系类型。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
            },
            "required": [],
        },
        handler=_tool_query_relations,
    ),
    MCPTool(
        name="synthesize_tts",
        description="将文本合成为语音，使用用户的声音特征（或默认声音）。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
                "text": {"type": "string", "description": "要合成的文本"},
                "emotion": {"type": "string", "description": "情绪标签", "default": "neutral"},
                "voice_key": {"type": "string", "description": "声音选择"},
            },
            "required": ["text"],
        },
        handler=_tool_synthesize_tts,
    ),
    MCPTool(
        name="query_avatar",
        description="查询用户的数字形象配置（颜色、风格等），用于3D渲染或显示。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
            },
            "required": [],
        },
        handler=_tool_query_avatar,
    ),
    MCPTool(
        name="export_persona_packet",
        description="导出完整的人格数据包，包含人格画像、声音统计、形象统计，可用于跨设备迁移。",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID"},
            },
            "required": [],
        },
        handler=_tool_export_persona_packet,
    ),
]


ALL_RESOURCES = [
    # 资源在 soul_routes.py 中注册
]


def register_all_tools(mcp_server):
    """将所有工具注册到 MCP Server"""
    for tool in ALL_TOOLS:
        mcp_server.register_tool(tool)
