# Tent OS Soul — 核心对话引擎重构计划

## 架构诊断结论

**不是代码少，是代码连不起来。**

Tent OS 已拥有生产级基础设施：5层压缩管道、L0/L1/L2分层记忆、完整MCP协议栈、认知图、工作记忆、Skills路由、Redis+SQLite混合存储。但 `_handle_fast_chat` 绕过了所有这些，使用硬编码关键词路由 + 伪流式 + 非向量记忆搜索。

---

## 实施原则

1. **连接，不是重写** — 已有的 `compression.py`, `tiered_store.py`, `mcp_gateway.py`, `working_memory.py` 都是精良组件，只需正确接入
2. **删除硬编码** — 所有关键词匹配、正则路由、[[DELEGATE:...]] 标记全部删除，委托给LLM自治
3. **参考主流参数** — token上限、上下文窗口、压缩阈值参考Claude Code/Kimi K2.6实际值，不凭空想象
4. **安全不过度** — System 1直觉拦截极端危险，System 2分类器降级模式，用户确认的approval workflow放行
5. **真流式** — KimiCodingLLM已实现`chat_stream_with_tools`，直接调用，删除伪流式

---

## Phase 1: P0 — 核心路径重构（当前对话重点）

### 1.1 创建 `tent_os/agent/context_assembly.py`
**目标**：整合System Prompt + WorkingMemory + 相关记忆 + 对话历史 + 5层压缩

**接口设计**：
```python
class ContextAssemblyPipeline:
    async def assemble(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        persona_profile: Optional[PersonaProfile] = None,
        working_memory_slots: Optional[str] = None,
        relevant_memories: Optional[List[Dict]] = None,
        tool_schemas: Optional[List[Dict]] = None,
        max_context_tokens: int = 120000,  # Kimi K2.6: 256K窗口，留136K给回复
    ) -> List[Dict]:
        """组装LLM上下文
        
        组装顺序（与Claude Code一致）：
        1. System Prompt（人格 + 规则 + 工作记忆）
        2. CLAUDE.md层级指令（如果有）
        3. 相关记忆（向量搜索召回）
        4. 对话历史（经5层压缩）
        5. 当前用户消息
        """
```

**关键参数（参考主流）**：
- `max_context_tokens = 120000` — Kimi K2.6 窗口256K，给回复留136K（Claude Code同样策略）
- `ContextCompressionPipeline` 默认 `max_tokens = 120000`（当前6000太低）
- `l2_keep_recent = 32`（当前16，参考Claude Code保留最近足够多消息）
- `l1_max_content_tokens = 8000`（当前4000，中文需要更多）

### 1.2 创建 `tent_os/agent/loop.py` — 真流式Agent Loop
**目标**：替换 `_handle_fast_chat` 的混乱逻辑

**核心循环**：
```python
class AgentLoop:
    async def run(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        websocket: WebSocket,
        capabilities: Dict,
        deep_thinking: bool = False,
    ):
        # 1. 组装上下文
        messages = await self.context_assembler.assemble(...)
        
        # 2. 获取工具列表（从MCP Gateway + 本地工具）
        tools = await self._get_tools(capabilities)
        
        # 3. 流式LLM调用（真流式）
        # 使用 chat_stream_with_tools，实时推送chunk到前端
        
        # 4. Tool Loop（如果需要）
        # max_rounds = 50（高安全上限，让LLM自终止）
        # 认知预算：3600秒，预算耗尽转入后台续跑
        
        # 5. 后台记忆入库（非阻塞队列）
```

**关键改动**：
- 删除 `max_tool_rounds = 5 if deep_thinking else 2` → 改为 `max_rounds = 50`
- 删除伪流式 `for i in range(0, len(reply), chunk_size)` → 使用 `chat_stream_with_tools` 的 `on_chunk` 回调
- 删除 `FOLLOW_UP_KEYWORDS` → 追问让LLM自己生成（或通过Skills系统）
- 删除 `[[DELEGATE:...]]` → Agent委派通过tool_call实现（`delegate_to_agent` 工具）

### 1.3 修复 `_execute_memory` — 向量搜索替换关键词匹配
**文件**：`tent_os/tools/executor.py`

当前 `memory_search` 使用关键词匹配（`query_words = set(query_lower.split())`）。
改为：
1. 调用 `EmbeddingClient.embed(query)` 生成查询向量
2. 调用 `TieredMemoryStore.search(query_vector, limit=limit)`
3. 返回 L0 摘要 + L1 概览

### 1.4 连接 MCP Gateway 到工具列表
**文件**：`tent_os/agent/loop.py`

当前工具列表来自 `get_tools_by_mode("deep")` 硬编码。
改为：
1. 从 `MCPGatewayRegistry.list_all_tools()` 获取动态工具
2. 合并本地工具（shell, file_read等）
3. 根据 `capabilities` 过滤（用户开关）

### 1.5 初始化 WorkingMemoryManager
**文件**：`tent_os/api/soul_state.py` 的 `APIServerState.setup()`

当前 `setup()` 没有初始化 `WorkingMemoryManager`。
需要：
1. 创建 `WorkingMemoryManager(graph=self.cognitive_graph)`
2. 在每次对话前调用 `working_memory.update(user_query)`
3. 将 `working_memory.get_context_text()` 注入 system prompt

---

## Phase 2: P1 — 生产级模式移植

### 2.1 安全管道（从worker.py移植）
**文件**：新建 `tent_os/agent/security.py`

移植内容：
- `_security_intuition()` — System 1: 0ms正则拦截极端危险（rm -rf, drop table等）
- `_assess_security()` — System 2: LLM分类器（仅在直觉不确定时调用）
- `ModeManager` — strict/standard/auto/unrestricted 四种模式

**改动**：不过度安全
- 默认模式：`standard`（需要approval的危险操作才拦截）
- `auto_approve` 配置：用户可配置自动批准只读操作
- Approval workflow：危险操作 → 前端弹窗确认 → 用户同意后放行

### 2.2 认知预算（从worker.py移植）
**文件**：`tent_os/agent/loop.py`

移植内容：
- 总时间限制：3600秒（可配置）
- 预算耗尽时：发送"转入后台"通知，重置计时器继续执行
- 进度心跳：每30秒发送进度消息

### 2.3 推测执行（从worker.py移植）
**文件**：新建 `tent_os/agent/speculative.py`

移植 `_preexecute_readonly()`：
- 在LLM调用前，检测用户输入中的只读意图
- 预执行 `file_read`, `memory_search`, `web_search` 等
- 结果注入到messages中作为上下文
- 跳过条件：系统stressed、闲聊、短问候

### 2.4 工具结果处理（从worker.py移植）
**文件**：`tent_os/agent/loop.py`

移植内容：
- `_truncate_tool_result_object()` — 递归智能截断JSON
- 工具结果缓存 — 避免LLM重复执行相同操作
- 工具失败追踪 — 连续失败同一工具时提示LLM换策略

### 2.5 Hook系统（从worker.py移植）
**文件**：新建 `tent_os/agent/hooks.py`

移植内容：
- `tool.assemble` — 修改工具池
- `pre_tool_use` — 批准/拦截/重写工具调用
- `post_tool_use` — 修改输出或注入上下文

### 2.6 任务中止（从worker.py移植）
**文件**：`tent_os/agent/loop.py`

移植内容：
- 每轮迭代检查 `abort_requested`
- 用户点击"中止"后立即停止
- 清理状态

---

## Phase 3: P2 — 架构修复

### 3.1 SessionAwareWSManager
**文件**：替换 `tent_os/api/soul_state.py` 中的 `WSConnectionManager`

当前 `broadcast()` 发送给所有WebSocket。
改为：
```python
class SessionAwareWSManager:
    def __init__(self):
        self._sessions: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        ...
    
    async def send_to_session(self, session_id: str, message: Dict):
        # 只发送给该session的连接
        ...
```

### 3.2 后台任务队列
**文件**：新建 `tent_os/agent/background_queue.py`

当前使用 `asyncio.create_task()` 在事件循环中执行后台任务。
改为持久队列：
- 使用 `arq` 或自定义基于Redis/SQLite的队列
- 任务类型：记忆入库、关系提取、人格分析、情绪检测
- 优点：服务重启不丢失任务、可限速、可监控

### 3.3 自动记忆管道
**文件**：`tent_os/agent/background_queue.py`

会话结束后自动：
1. `tiered_store.ingest()` — 摄入对话内容
2. `graph.add_node()` / `graph.add_edge()` — 更新认知图
3. `plasticity.on_memory_ingest()` — 触发可塑性引擎
4. `auto_compress_l0_to_l1()` — 压缩记忆

### 3.4 REM模式持久化
**文件**：`tent_os/memory/plasticity.py`

当前 `_discover_patterns()` 发现模式但不持久化。
改为：将发现的模式作为结构化节点写入认知图。

---

## Phase 4: P3 — 进化

### 4.1 Subagent系统
**文件**：新建 `tent_os/agent/subagents.py`

参考Claude Code设计：
- `ExploreAgent` — 只读代码/文件搜索（独立上下文窗口）
- `PlanAgent` — 研究模式，生成执行计划
- `GeneralAgent` — 复杂多步任务

每个Subagent：
- 独立的 `messages` 数组
- 受限的工具访问
- 独立的权限模式
- 结果返回主Agent做最终回复

### 4.2 Skill运行时
**文件**：`tent_os/skills/router.py`

当前 `SkillRouter` 有4层路由但chat路径不调用。
改为：
- 在 `ContextAssemblyPipeline` 中检查是否有匹配Skill
- 如果匹配，将Skill的system prompt和工具注入上下文
- Skill通过 `SkillTool` meta-tool被LLM调用

### 4.3 Session分叉
**文件**：扩展 `tent_os/state/redis_store.py`

当前会话历史是线性的。
改为：
- `checkpoint()` — 在任意回合创建检查点
- `branch_from(checkpoint_id)` — 从检查点创建分支
- `list_branches(session_id)` — 列出所有分支

---

## 当前对话任务

本次对话完成 **Phase 1.1 - 1.5**（P0核心路径重构）。

### 具体步骤：
1. ✅ 审计完成
2. ⏳ 创建 `ContextAssemblyPipeline`
3. ⏳ 创建 `AgentLoop`（真流式）
4. ⏳ 修复 `_execute_memory` 向量搜索
5. ⏳ 初始化 `WorkingMemoryManager`
6. ⏳ 修改 `soul_state.py` 使用新AgentLoop
7. ⏳ 删除旧硬编码代码

---

## 参考值备忘录

| 参数 | 当前值 | 参考值 | 来源 |
|------|--------|--------|------|
| 上下文窗口 | 256K (Kimi K2.6) | 256K | Kimi官方 |
| max_context_tokens | 6000 | 120000 | Claude Code策略（留136K给回复） |
| max_tokens (回复) | 4096 | 8000-16000 | Claude Code使用64000+ |
| l2_keep_recent | 16 | 32 | 参考Claude Code保留量 |
| l1_max_content_tokens | 4000 | 8000 | 中文需要更多 |
| max_tool_rounds | 2-5 | 50 | 高安全上限，LLM自终止 |
| 认知预算 | 无 | 3600秒 | worker.py已有 |
| 进度心跳 | 无 | 30秒 | worker.py已有 |
| 工具结果截断 | 简单截断 | 递归智能截断 | worker.py已有 |
