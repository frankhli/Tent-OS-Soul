import asyncio
import json
import re
from pathlib import Path
from typing import List, Dict

from tent_os.memory.tiered_store import TieredMemoryStore
from tent_os.memory.index import MemoryIndex
from tent_os.memory.vector_search import PurePythonVectorSearch
from tent_os.logging_config import get_logger

# Tent OS 2.0 大脑模块（可选）
try:
    from tent_os.memory.plasticity import PlasticityEngine
    _PLASTICITY_AVAILABLE = True
except ImportError:
    _PLASTICITY_AVAILABLE = False

logger = get_logger()


def _sync_build_injected_context(storage_path: str, user_id: str,
                                  heartbeat_md: str, task_query: str,
                                  embedding_model=None, persona: str = None) -> str:
    """在线程池中同步构建记忆注入上下文
    
    关键设计：在线程中创建独立的 SQLite 连接，避免阻塞主事件循环。
    优先语义向量搜索，回退到时间和关键词匹配。
    """
    try:
        store = TieredMemoryStore(storage_path)
        index = MemoryIndex(storage_path)
    except Exception as e:
        logger.warning(f"记忆存储初始化失败: {e}")
        return ""
    
    sections = []
    
    # 1. 用户画像（HOT 记忆 + 动态风格参数）
    profile_parts = []
    for ptr in index.get_pointers("hot", persona=persona):
        if ptr.memory_type in ("profile", "preference"):
            content = index.read_content(ptr.uri)
            if content:
                profile_parts.append(content[:400])
    
    # 加载动态用户画像（基于反馈的风格参数）
    try:
        from tent_os.memory.user_profile import UserProfileStore
        from pathlib import Path
        profile_db = Path(storage_path) / "memory.db" if Path(storage_path).is_dir() else storage_path
        profile_store = UserProfileStore(str(profile_db))
        dynamic_profile = profile_store.get_profile_for_prompt(user_id)
        if dynamic_profile:
            profile_parts.append(dynamic_profile)
    except Exception as e:
        logger.debug(f"加载动态用户画像失败: {e}")
    
    if profile_parts:
        sections.append(("👤 用户画像", "\n\n".join(profile_parts), 0))
    
    # 1.5 空间记忆注入：AI 的物理世界观察
    # 只在用户询问与空间/物理世界相关的问题时注入，避免每次对话都带
    SPATIAL_KEYWORDS = [
        "工厂", "设备", "监控", "摄像头", "现场", "办公室", "房间",
        "哪里", "位置", "异常", "今天", "最近", "现在", "怎么样",
        "发生", "看到", "观察", "物理", "空间", "环境", "状况",
    ]
    task_query_lower = (task_query or "").lower()
    if any(kw in task_query_lower for kw in SPATIAL_KEYWORDS):
        try:
            from tent_os.services.visual_memory_service import get_visual_memory_service
            vm = get_visual_memory_service()
            
            # 获取最近空间观察 + 异常检测
            spatial_memories = vm.get_spatial_summary(user_id, hours=24)
            anomalies = vm.detect_anomalies(user_id, window_hours=24)
            
            lines = []
            # 最多取 5 条最近观察
            for mem in spatial_memories[:5]:
                desc = mem.get("description", "")
                scene = mem.get("scene_type", "")
                created = mem.get("created_at", "")
                time_label = created[11:16] if len(created) >= 16 else created
                prefix = f"[{time_label}]"
                if scene:
                    prefix += f" [{scene}]"
                lines.append(f"- {prefix} {desc[:60]}")
            
            # 添加异常项
            for anomaly in anomalies[:3]:
                obj = anomaly.get("object", "")
                expected = anomaly.get("expected", "")
                actual = anomaly.get("actual", "")
                severity = anomaly.get("severity", "info")
                icon = "⚠️" if severity == "warning" else "❗" if severity == "critical" else "ℹ️"
                lines.append(f"- {icon} [异常] {obj}: {expected}，但实际{actual}")
            
            if lines:
                # 限制总长度不超过 300 字符
                content = "\n".join(lines)
                if len(content) > 300:
                    content = content[:297] + "..."
                sections.append(("🌍 空间观察（最近24小时）", content, 0))
        except Exception as e:
            logger.debug(f"空间记忆注入失败: {e}")
    
    # 1.6 空间认知层注入：足迹 + 场景 + 地点记忆
    # 触发关键词扩展：位置、附近、距离、路线、去过、家、办公室、在路上
    SPATIAL_COGNITION_KEYWORDS = [
        "在哪里", "位置", "附近", "距离", "路线", "去过", "家", "办公室",
        "在路上", "出门", "回家", "到达", "离开", "周边", "导航",
        "地方", "地点", "地址", "坐标", "地图",
    ]
    if any(kw in task_query_lower for kw in SPATIAL_COGNITION_KEYWORDS):
        try:
            from tent_os.services.spatial_footprint_service import get_spatial_footprint_service
            from tent_os.memory.user_profile import UserProfileStore
            sf = get_spatial_footprint_service()
            profile_store = UserProfileStore()
            profile = profile_store.get_or_create(user_id)
            
            lines = []
            
            # 当前位置
            recent_loc = sf.get_recent_location(user_id)
            if recent_loc:
                lat = recent_loc.get("lat", 0)
                lng = recent_loc.get("lng", 0)
                hint = recent_loc.get("scene_hint", "")
                lines.append(f"- 当前坐标: 纬度{lat:.4f}, 经度{lng:.4f}")
                if hint:
                    lines.append(f"- 场景推测: {hint}")
            
            # 当前场景
            if profile.active_scene:
                lines.append(f"- 当前场景: {profile.active_scene}")
            
            # 地点记忆（取最近3个）
            loc_memories = sf.get_all_location_memories(user_id)[:3]
            for loc_mem in loc_memories:
                if loc_mem and loc_mem.get("location_name"):
                    lines.append(f"- 地点记忆: {loc_mem['location_name']} — 来过{loc_mem.get('visit_count', 0)}次，累计停留{loc_mem.get('total_duration_minutes', 0)}分钟")
            
            # 最近足迹摘要
            path = sf.get_footprint_path(user_id, hours=24)
            if len(path) >= 2:
                first = path[0]
                last = path[-1]
                lines.append(f"- 今天足迹: 从 ({first['lat']:.4f}, {first['lng']:.4f}) 到 ({last['lat']:.4f}, {last['lng']:.4f})，共{len(path)}个记录点")
            
            if lines:
                content = "\n".join(lines)
                if len(content) > 300:
                    content = content[:297] + "..."
                sections.append(("🗺️ 空间足迹与场景", content, 0))
        except Exception as e:
            logger.debug(f"空间认知注入失败: {e}")
    
    # 2. FIX v3.2: 工作记忆——像人类"刚才聊到哪了"（只取最近3条，更短摘要）
    try:
        recent = store.get_recent(limit=3, user_id=user_id, hours=24, persona=persona)
        
        if recent:
            lines = []
            from datetime import datetime
            now = datetime.now()
            for r in recent[:3]:
                abstract = r.get("abstract", "")
                created_str = r.get("created_at", "")
                time_label = ""
                try:
                    created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                    delta = now - created_dt.replace(tzinfo=None)
                    if delta.days == 0:
                        time_label = f"{delta.seconds // 60}分钟前" if delta.seconds < 3600 else f"{delta.seconds // 3600}小时前"
                    elif delta.days == 1:
                        time_label = "昨天"
                    else:
                        time_label = f"{delta.days}天前"
                except Exception:
                    time_label = created_str[:10] if created_str else ""
                
                lines.append(f"- [{time_label}] {abstract[:80]}")
            
            sections.append(("💬 刚才聊到", "\n".join(lines), 1))
    except Exception as e:
        logger.debug(f"读取近期记忆失败: {e}")
    
    # 3. 语义向量搜索（如果 embedding_model 可用）
    semantic_results = []
    if embedding_model and task_query:
        try:
            query_vec = embedding_model(task_query)
            # 处理 async embedding（在线程中需要新建事件循环执行）
            import asyncio
            if hasattr(query_vec, '__await__'):
                loop = asyncio.new_event_loop()
                try:
                    query_vec = loop.run_until_complete(query_vec)
                finally:
                    loop.close()
            searcher = PurePythonVectorSearch(store.db)
            semantic_results = searcher.search(query_vec, limit=5, persona=persona)
            # FIX v3: 动态排序替代质量门控
            # 旧逻辑：如果结果太少或相似度<0.5就清空——这会导致单条高质量记忆被丢弃
            # 新逻辑：按相似度排序取前5条，不再清空。记忆检索是"注意力排序"不是"阈值过滤"。
            if semantic_results:
                # 按相似度排序（已经排好，但再确认一下）
                semantic_results.sort(key=lambda r: r.get("score", 0), reverse=True)
                # FIX v3.2: 从5条降到2条——人类的联想是"这让我想起一件事"，不是列出所有相关的事
                top_results = semantic_results[:2]
                if top_results:
                    max_score = top_results[0].get("score", 0)
                    logger.debug(f"语义搜索保留 {len(top_results)} 条（最高相似度 {max_score:.2f}）")
                    lines = []
                    for r in top_results:
                        abstract = r.get("abstract", "")
                        lines.append(f"- {abstract[:80]}...")
                    sections.append(("🔍 相关记忆", "\n".join(lines), 1))
        except Exception as e:
            logger.debug(f"语义搜索失败: {e}")
    
    # 4. 兜底：直接 SQL 关键词搜索 l0_index（不依赖 MemoryIndex，修复跨会话丢失）
    if not semantic_results:
        try:
            task_lower = task_query.lower()
            keywords = set(re.findall(r'[a-zA-Z_]{3,}', task_lower))
            keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', task_query))
            
            matched = []
            if keywords:
                # 构建 LIKE 条件（参数化查询，防止 SQL 注入）
                like_conditions = []
                params = []
                for kw in keywords:
                    like_conditions.append("abstract LIKE ?")
                    params.append(f"%{kw}%")
                
                # 优先检索该用户的记忆，如果没有则检索所有
                where_clause = " OR ".join(like_conditions)
                if user_id:
                    if persona:
                        sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) AND user_id = ? AND (persona = ? OR persona = '__shared__' OR persona IS NULL) ORDER BY created_at DESC LIMIT 8"
                        rows = store.db.execute(sql, (*params, user_id, persona)).fetchall()
                    else:
                        sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) AND user_id = ? ORDER BY created_at DESC LIMIT 8"
                        rows = store.db.execute(sql, (*params, user_id)).fetchall()
                    # 如果该用户没有匹配，放宽到所有用户
                    if not rows:
                        if persona:
                            sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) AND (persona = ? OR persona = '__shared__' OR persona IS NULL) ORDER BY created_at DESC LIMIT 8"
                            rows = store.db.execute(sql, (*params, persona)).fetchall()
                        else:
                            sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) ORDER BY created_at DESC LIMIT 8"
                            rows = store.db.execute(sql, params).fetchall()
                else:
                    if persona:
                        sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) AND (persona = ? OR persona = '__shared__' OR persona IS NULL) ORDER BY created_at DESC LIMIT 8"
                        rows = store.db.execute(sql, (*params, persona)).fetchall()
                    else:
                        sql = f"SELECT uri, abstract, memory_type, created_at FROM l0_index WHERE ({where_clause}) ORDER BY created_at DESC LIMIT 8"
                        rows = store.db.execute(sql, params).fetchall()
                
                for row in rows:
                    matched.append({
                        "uri": row[0],
                        "abstract": row[1],
                        "type": row[2],
                        "created_at": row[3],
                    })
            
            if matched:
                lines = []
                for m in matched[:5]:
                    abstract = m.get("abstract", "")
                    lines.append(f"- {abstract[:150]}")
                sections.append(("💡 相关记忆（关键词匹配）", "\n".join(lines), 2))
        except Exception as e:
            logger.debug(f"关键词搜索兜底失败: {e}")
    
    # 5. FIX v6: 用户历史项目摘要——跨session记忆的核心修复
    # 问题：考试/回顾类query的关键词与历史记忆abstract不匹配，导致跨session失忆
    # 解决：主动聚合该用户的所有历史session，按session分组展示摘要
    try:
        if user_id:
            # 按 session 分组聚合记忆：从 uri 中提取 session_id
            if persona:
                rows = store.db.execute(
                    "SELECT uri, abstract, created_at FROM l0_index WHERE user_id = ? AND (persona = ? OR persona = '__shared__' OR persona IS NULL) ORDER BY created_at DESC LIMIT 100",
                    (user_id, persona)
                ).fetchall()
            else:
                rows = store.db.execute(
                    "SELECT uri, abstract, created_at FROM l0_index WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
                    (user_id,)
                ).fetchall()
            
            session_map = {}
            for row in rows:
                uri = row[0]
                abstract = row[1] or ""
                created = row[2] or ""
                # 从 uri 中提取 session_id，如 "session/proj_a_bp#chunk0"
                m = re.match(r'session/([^#]+)', uri)
                if m:
                    sid = m.group(1)
                    if sid not in session_map:
                        session_map[sid] = {"abstracts": [], "created_at": created}
                    # 只取非代码片段的有意义摘要
                    if len(abstract) > 10 and not abstract.startswith('<') and not abstract.startswith('```'):
                        session_map[sid]["abstracts"].append(abstract[:120])
            
            if session_map:
                lines = []
                # 最多展示5个历史session
                for sid, info in list(session_map.items())[:5]:
                    # 取每个session的前2条有意义摘要
                    meaningful = info["abstracts"][:2]
                    if meaningful:
                        summary = " | ".join(meaningful)
                        lines.append(f"- [{sid}] {summary[:150]}")
                
                if lines:
                    sections.append(("📁 用户历史项目", "\n".join(lines), 1))
    except Exception as e:
        logger.debug(f"用户历史项目聚合失败: {e}")
    
    # 5.1 FIX v6: UserProfileStore 事件——显式跨session事实
    try:
        if user_id:
            from tent_os.memory.user_profile import UserProfileStore
            profile_db = Path(storage_path) / "memory.db" if Path(storage_path).is_dir() else storage_path
            profile_store = UserProfileStore(str(profile_db))
            profile = profile_store.get_or_create(user_id)
            events = profile.get_events()
            if events:
                lines = []
                for ev in events[-10:]:  # 最近10条事件
                    event_text = ev.get("event", "")
                    if event_text:
                        lines.append(f"- {event_text[:120]}")
                if lines:
                    sections.append(("📝 重要事件记录", "\n".join(lines), 0))
    except Exception as e:
        logger.debug(f"加载用户事件失败: {e}")
    
    # 6. WARM 经验记忆（通过 MemoryIndex，向后兼容）
    try:
        warm = index.get_pointers("warm", persona=persona)
        task_lower = task_query.lower()
        matched = []
        for ptr in warm:
            if ptr.memory_type in ("decision", "learning"):
                score = 0
                if ptr.title.lower() in task_lower or any(w in ptr.title.lower() for w in task_lower.split()):
                    score += 2
                for kw in ptr.keywords:
                    if kw.lower() in task_lower:
                        score += 1
                if score > 0:
                    content = index.read_content(ptr.uri)
                    if content:
                        matched.append((score, ptr.title, content[:300]))
        if matched:
            matched.sort(key=lambda x: x[0], reverse=True)
            lines = [f"- {title}: {content[:200]}..." for _, title, content in matched[:3]]
            sections.append(("📚 经验规则", "\n".join(lines), 2))
    except Exception as e:
        logger.debug(f"读取经验记忆失败: {e}")
    
    # 5. 待办任务
    if heartbeat_md and heartbeat_md.strip():
        sections.append(("📌 待办任务", heartbeat_md[:600], 0))
    
    if not sections:
        return ""
    
    # 组装结果，限制总长度
    result_parts = [
        "【系统注入】以下是你应该知道的背景信息：",
        "",
        "🧠 对话连续性提示：",
        "- 用户可能继续上一次的对话话题，请主动关联。",
        "- 如果用户的问题明显是新话题，不需要强行关联旧记忆。",
        "- 你看到的'最近对话'是按时间排序的，越靠前越新鲜。",
        "",
    ]
    total_len = len("".join(result_parts))
    max_total = 2000  # 字符数限制（约 600-800 tokens）
    
    for title, content, _ in sections:
        section_text = f"{'=' * 30}\n{title}\n{'=' * 30}\n{content}\n\n"
        if total_len + len(section_text) > max_total and total_len > 0:
            remaining = max_total - total_len - len(f"{'=' * 30}\n{title}\n{'=' * 30}\n\n")
            if remaining > 50:
                truncated = content[:remaining]
                section_text = f"{'=' * 30}\n{title}\n{'=' * 30}\n{truncated}\n\n"
                result_parts.append(section_text)
            break
        result_parts.append(section_text)
        total_len += len(section_text)
    
    # 提示 LLM 可以通过工具读取完整内容
    result_parts.append(
        "💡 记忆提示：如需查看完整历史内容，请使用 memory_search(query) 和 memory_get(uri) 工具。"
    )
    
    return "\n".join(result_parts)


class MemoryWorker:
    def __init__(self, bus, store: TieredMemoryStore, embedding_model: callable,
                 config: Dict = None, llm=None):
        self.bus = bus
        self.store = store
        self.embedding_model = embedding_model
        self.storage_path = str(store.storage_path)
        self.config = config or {}
        
        # Tent OS 2.0：初始化神经可塑性引擎（可选）
        self.plasticity = None
        if _PLASTICITY_AVAILABLE and self.config.get("brain_v2", {}).get("enabled", False):
            self.plasticity = PlasticityEngine(
                bus=bus,
                config=self.config.get("brain_v2", {}),
                llm=llm,
                graph_db_path=f"{self.storage_path}/graph.db",
                memory_db_path=f"{self.storage_path}/memory.db",
            )
    
    async def start(self):
        await self.bus.subscribe("memory.inject", "memory-inject", self._handle_inject)
        await self.bus.subscribe("memory.ingest", "memory-ingest", self._handle_ingest)
        
        # 启动神经可塑性引擎
        if self.plasticity:
            await self.plasticity.start()
    
    async def _handle_inject(self, msg):
        """处理记忆注入请求 —— 线程池执行，不阻塞事件循环"""
        data = json.loads(msg.data)
        session_id = data.get("session_id", "")
        user_id = data.get("user_id", "anonymous")
        task_query = data.get("current_task", "")
        persona = data.get("persona", None)  # Phase 2: 人格记忆隔离
        
        heartbeat_md = self._read_heartbeat_md()
        
        try:
            # 在线程池中执行同步 SQLite 查询，避免阻塞事件循环
            context = await asyncio.to_thread(
                _sync_build_injected_context,
                self.storage_path,
                user_id,
                heartbeat_md,
                task_query,
                self.embedding_model,
                persona,
            )
            logger.info(f"[MEM] 记忆注入完成 [{session_id}]: {len(context)} chars")
        except Exception as e:
            logger.error(f"[MEM] 记忆注入失败 [{session_id}]: {e}")
            context = ""
        
        await self.bus.publish(data["reply_to"], json.dumps({
            "session_id": session_id,
            "type": "memory_injected",
            "injected_context": context
        }).encode())
    
    async def _handle_ingest(self, msg):
        data = json.loads(msg.data)
        content = self._format_messages(data["messages"])
        session_id = data.get("session_id", "")
        user_id = data.get("user_id", "")
        persona = data.get("persona", "work")  # Phase 2: 人格记忆隔离
        
        # FIX v3.2: 记忆摄入改为后台任务，不阻塞主流程和事件循环
        asyncio.create_task(self._background_ingest(content, session_id, user_id, persona))
    
    async def _background_ingest(self, content: str, session_id: str, user_id: str, persona: str = "work"):
        """后台记忆摄入——不阻塞主流程"""
        try:
            # 1. 标准记忆摄入（Phase 2: 传递 persona）
            await self.store.ingest(
                content, f"session/{session_id}", "conversation",
                user_id=user_id, embedding_model=self.embedding_model, persona=persona
            )
            logger.debug(f"[MEM] 后台记忆摄入完成 [{session_id}]")
        except Exception as e:
            logger.error(f"[MEM] 后台记忆摄入失败 [{session_id}]: {e}")
        
        # 2. Tent OS 2.0：触发神经可塑性 Light 阶段
        if self.plasticity:
            try:
                await self.plasticity.on_memory_ingest(
                    content=content,
                    uri=f"session/{session_id}",
                    memory_type="conversation",
                    user_id=user_id,
                    source_session=session_id,
                    persona=persona,
                )
            except Exception as e:
                logger.debug(f"[MEM] 可塑性 Light 阶段失败: {e}")
    
    def _read_heartbeat_md(self) -> str:
        path = Path("./HEARTBEAT.md")
        return path.read_text() if path.exists() else ""
    
    def _format_messages(self, messages: List[Dict]) -> str:
        lines = []
        for m in messages:
            role = m.get('role', 'unknown')
            content = m.get('content', '')
            # FIX: 过滤掉系统内部污染标记（SelfValidator的alert等）
            if self._is_system_pollution(content):
                logger.debug(f"[MEM] 过滤污染消息: {content[:80]}...")
                continue
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)
    
    def _is_system_pollution(self, content: str) -> bool:
        """检测内容是否为系统内部污染标记，不应存入记忆"""
        if not content:
            return False
        pollution_markers = [
            "⚠️ 任务可能未完成",
            "判断理由:",
            "未完成的方面:",
            "💡 建议:",
            "【任务执行完成】",
            "✅ 任务执行完成",
            "❌ 任务执行失败",
            "[VALIDATOR]",
            "[GOV] 规则反馈",
            "[GOV] 规则闭环",
            "[PROMISE]",
        ]
        content_str = str(content)
        return any(marker in content_str for marker in pollution_markers)
