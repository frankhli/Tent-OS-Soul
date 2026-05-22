# Tent OS Multi-Agent System (MAS) — 完整架构设计

## 一、愿景与定位

> 从一个"灵魂对讲机"进化为一个"AI 团队协作平台"。用户不再只和一个 AI 对话，而是组建一支由多个专业 AI Agent 组成的团队，它们各有专长、各有记忆、可以开会协作、可以独立完成任务。

## 二、核心概念

### 2.1 Agent 的生命周期

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   创建      │ →  │   配置      │ →  │   激活      │ →  │   运行      │
│  (Create)   │    │  (Config)   │    │ (Activate)  │    │  (Runtime)  │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                                  │
                              ┌───────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │   会议/协作      │
                    │  (Collaborate)  │
                    └─────────────────┘
```

### 2.2 Agent 的完整属性

每个 Agent 是一个独立的"灵魂"，拥有：

| 维度 | 说明 | 示例（产品经理 Agent） | 示例（财务顾问 Agent） |
|------|------|----------------------|----------------------|
| **Identity** | 名字、角色、头像、声音 | "小明"，产品经理，年轻活力 | "老张"，财务顾问，稳重严谨 |
| **Soul** | 人格画像、思维方式 | 发散思维、用户导向、快速迭代 | 逻辑思维、风险控制、数据驱动 |
| **Memory** | 独立记忆库（L0/L1/L2） | 产品需求文档、用户反馈、竞品分析 | 财务报表、投资组合、税务政策 |
| **Tools** | 可用工具集 | 原型设计、用户调研、数据分析 | 财务计算、风险评估、报表生成 |
| **Skills** | 专长领域 | 需求分析、竞品分析、PRD 撰写 | 预算规划、投资建议、税务优化 |
| **State** | 运行状态、疲劳度、任务负载 | 当前处理3个需求评审 | 刚完成一份年度预算报告 |

### 2.3 Agent 类型

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent 类型体系                           │
├─────────────────┬─────────────────┬─────────────────────────┤
│   主 Agent       │   子 Agent      │   系统 Agent            │
│  (Primary)      │  (Sub-Agent)   │  (System)              │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • 用户直接对话   │ • 用户自定义    │ • 调度器 Agent         │
│ • 负责调度      │ • 各有专长      │ • 会议室主持人 Agent    │
│ • 整合结果      │ • 可被主 Agent  │ • 纪要生成 Agent       │
│ • 唯一入口      │   调用          │ • 心跳监控 Agent       │
└─────────────────┴─────────────────┴─────────────────────────┘
```

## 三、数据模型

### 3.1 Agent 定义表 (`agents`)

```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,              -- agent_xxx
    name TEXT NOT NULL,               -- 显示名称
    role TEXT NOT NULL,               -- 角色标签
    avatar_config TEXT,               -- JSON: 外观配置
    voice_config TEXT,                -- JSON: 声纹配置
    system_prompt TEXT,               -- 核心 system prompt
    identity JSON,                    -- {name, age, gender, personality...}
    skills JSON,                      -- [{name, level, description}]
    tools_allowed JSON,               -- ["web_search", "file_read", "calculator"]
    memory_isolation BOOLEAN DEFAULT TRUE,  -- 是否独立记忆
    parent_agent_id TEXT,             -- 上级 Agent（层级关系）
    created_by TEXT,                  -- 创建者 user_id
    is_active BOOLEAN DEFAULT TRUE,
    created_at TEXT,
    updated_at TEXT
);
```

### 3.2 Agent 记忆表 (`agent_memories`)

每个 Agent 有独立的记忆库，结构同 L0/L1/L2：

```sql
CREATE TABLE agent_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    uri TEXT NOT NULL,
    content TEXT,                     -- 原始内容
    abstract TEXT,                    -- L0 摘要
    embedding BLOB,                   -- 向量
    memory_type TEXT DEFAULT 'conversation',
    created_at TEXT,
    UNIQUE(agent_id, uri)
);
```

### 3.3 Agent 间消息表 (`agent_messages`)

```sql
CREATE TABLE agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,            -- 房间/会议 ID
    from_agent_id TEXT NOT NULL,
    to_agent_id TEXT,                 -- NULL = 广播
    message_type TEXT,                -- text | tool_call | tool_result | thought | emotion
    content TEXT,
    metadata JSON,                    -- {emotion, confidence, tools_used}
    created_at TEXT
);
```

### 3.4 会议室表 (`agent_rooms`)

```sql
CREATE TABLE agent_rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    topic TEXT,                       -- 会议主题
    participants JSON,                -- [agent_id1, agent_id2, ...]
    host_agent_id TEXT,               -- 主持人
    status TEXT,                      -- idle | active | paused | closed
    summary TEXT,                     -- 会议纪要
    created_by TEXT,
    created_at TEXT,
    closed_at TEXT
);
```

## 四、运行时架构

### 4.1 Agent 运行时 (AgentRuntime)

```python
class AgentRuntime:
    """每个 Agent 的独立运行时"""
    
    def __init__(self, agent_config: AgentConfig):
        self.config = agent_config
        self.memory = AgentMemoryStore(agent_config.id)  # 独立记忆
        self.emotion = EmotionDetector()                 # 独立情绪
        self.tool_executor = ToolExecutor(
            allowed_tools=agent_config.tools_allowed
        )
        self.state = AgentState()  # 运行状态
        self.cognitive_graph = AgentCognitiveGraph(agent_config.id)
    
    async def run(self, task: str, context: Dict) -> AgentResult:
        """执行一次任务"""
        # 1. 加载该 Agent 的 system prompt + 人格画像
        # 2. 从独立记忆中检索相关上下文
        # 3. 调用 LLM（带 tool calling）
        # 4. 执行工具
        # 5. 保存结果到记忆
        # 6. 返回结果给调用方
        pass
```

### 4.2 主 Agent 调度器 (AgentOrchestrator)

```python
class AgentOrchestrator:
    """主 Agent 的调度中枢"""
    
    async def handle_user_message(self, user_msg: str) -> str:
        # Step 1: 分析用户需求
        intent = await self._analyze_intent(user_msg)
        
        # Step 2: 判断是否需要子 Agent
        if intent.requires_sub_agent:
            # 选择合适的子 Agent
            agent = self._select_agent(intent)
            # 委派任务
            result = await self.runtime_pool.run_agent(
                agent_id=agent.id,
                task=user_msg,
                context={"user_intent": intent}
            )
            # 整合结果
            return await self._synthesize(result, user_msg)
        else:
            # 自己处理
            return await self.primary_agent.run(user_msg)
    
    async def _analyze_intent(self, msg: str) -> Intent:
        """判断需要什么类型的 Agent"""
        # 用 LLM 做意图分类
        # 返回：{domain: "finance", confidence: 0.92, requires_sub_agent: True}
        pass
```

### 4.3 Agent 运行时池 (AgentRuntimePool)

```python
class AgentRuntimePool:
    """管理所有 Agent 的运行时实例"""
    
    def __init__(self):
        self.runtimes: Dict[str, AgentRuntime] = {}
    
    def get_or_create(self, agent_id: str) -> AgentRuntime:
        if agent_id not in self.runtimes:
            config = load_agent_config(agent_id)
            self.runtimes[agent_id] = AgentRuntime(config)
        return self.runtimes[agent_id]
    
    async def run_agent(self, agent_id: str, task: str, context: Dict) -> AgentResult:
        runtime = self.get_or_create(agent_id)
        return await runtime.run(task, context)
```

## 五、Agent 间协作机制

### 5.1 1:1 委派 (Delegation)

```
用户: "帮我分析一下这个季度的财务状况"
  ↓
主 Agent (分析意图 → 需要财务专家)
  ↓
调用 delegate 工具
  {
    "target_agent": "finance_advisor",
    "task": "分析用户Q3财务状况，给出投资建议",
    "context": {用户提供的财务数据}
  }
  ↓
财务 Agent 独立执行
  ↓
返回结果给主 Agent
  ↓
主 Agent 整合并回复用户
```

### 5.2 多 Agent 会议 (Conference)

```
用户: "我要做一个新产品，需要产品、技术、市场一起讨论"
  ↓
主 Agent 创建会议室
  room_id = create_room(
    name="新产品方案讨论",
    participants=["product_manager", "tech_lead", "marketing"],
    host="primary_agent"
  )
  ↓
主持人 Agent 开场
  "各位，今天讨论新产品方向，先请产品经理提出方案"
  ↓
产品 Agent 发言
  "我建议做一款...理由是..."
  ↓
技术 Agent 回应
  "技术上可行，但开发周期需要..."
  ↓
市场 Agent 补充
  "竞品分析显示...市场缺口在..."
  ↓
... (多轮讨论)
  ↓
主持人 Agent 总结
  "综合各方意见，最终方案是..."
  ↓
生成会议纪要
  ↓
主 Agent 向用户汇报
```

### 5.3 会议纪要生成

```python
class MeetingSummaryAgent:
    """专门负责生成会议纪要的系统 Agent"""
    
    async def generate_summary(self, room_id: str) -> MeetingSummary:
        messages = get_room_messages(room_id)
        
        # 用 LLM 生成结构化纪要
        summary = await self.llm.chat([
            {"role": "system", "content": "你是会议纪要专家..."},
            {"role": "user", "content": f"请总结以下会议讨论：\n{messages}"}
        ])
        
        return MeetingSummary(
            decisions=extract_decisions(summary),
            action_items=extract_action_items(summary),
            disagreements=extract_disagreements(summary),
            full_text=summary
        )
```

## 六、心跳与自治机制 (Heartbeat & Autonomy)

### 6.1 设计原则

借鉴 OpenClaw 的自治理念，但针对多 Agent 场景：

| 机制 | 说明 |
|------|------|
| **个体心跳** | 每个 Agent 定期自检（疲劳度、任务积压、记忆碎片化） |
| **群体心跳** | 系统定期评估 Agent 间的协作效率 |
| **主动建议** | Agent 发现用户可能需要帮助时，主动推送建议 |
| **记忆同步** | 相关 Agent 之间选择性同步关键记忆 |

### 6.2 Agent 心跳任务

```python
async def agent_heartbeat(agent_id: str):
    runtime = pool.get(agent_id)
    
    # 1. 疲劳度检测
    if runtime.state.fatigue > 0.8:
        await notify_user(f"{agent_id} 已连续处理多个任务，建议休息")
    
    # 2. 记忆整理
    if runtime.memory.fragmentation > 0.5:
        await runtime.memory.compact()
    
    # 3. 技能成长
    new_skills = await runtime.analyze_skill_growth()
    if new_skills:
        await update_agent_skills(agent_id, new_skills)
    
    # 4. 主动建议
    if should_proactively_suggest(runtime):
        suggestion = await runtime.generate_suggestion()
        await push_to_user(suggestion)
```

### 6.3 跨 Agent 记忆同步

```
产品 Agent 记住了："用户想做一款健身 App"
  ↓
系统检测到：市场 Agent 和开发 Agent 也需要知道这个信息
  ↓
选择性同步（只同步相关记忆片段）
  ↓
市场 Agent 现在知道："用户目标市场是健身领域"
开发 Agent 现在知道："用户可能需要运动数据追踪功能"
```

## 七、前端界面设计

### 7.1 Agent 管理页面

```
┌─────────────────────────────────────────────────────────────┐
│  我的 Agent 团队                                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  🧑‍💼        │  │  👨‍💻        │  │  👩‍💼        │  + 新建 │
│  │  产品经理    │  │  技术顾问    │  │  财务顾问    │         │
│  │  在线 ✓     │  │  在线 ✓     │  │  休息中     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│  产品经理 的配置                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  名称: 小明                                          │   │
│  │  角色: 产品经理                                      │   │
│  │  专长: 需求分析、竞品分析、PRD 撰写                    │   │
│  │  可用工具: 原型设计、用户调研、数据分析                 │   │
│  │  人格: 发散思维、用户导向、快速迭代                     │   │
│  │  记忆隔离: ✓                                         │   │
│  │  [编辑] [测试对话] [查看记忆]                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 会议室页面

```
┌─────────────────────────────────────────────────────────────┐
│  会议室: 新产品方案讨论      [结束会议]                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  主持人(主Agent): "各位，请产品经理先介绍方案"               │
│                                                             │
│  ┌──────────┐                                              │
│  │ 🧑‍💼 小明   │  我建议做一款结合 AI 教练的健身 App...      │
│  └──────────┘                                              │
│                                                             │
│  ┌──────────┐                                              │
│  │ 👨‍💻 老张   │  技术上用 Flutter 跨端，后端用 FastAPI...   │
│  └──────────┘                                              │
│                                                             │
│  ┌──────────┐                                              │
│  │ 👩‍💼 Lisa  │  竞品已经有 Keep 和薄荷健康，我们的差异化... │
│  └──────────┘                                              │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│  [生成会议纪要] [加入讨论] [邀请其他Agent]                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 八、实现路线图

### Phase 1: Agent 基础设施（1-2 周）
- [ ] Agent 数据模型（数据库表）
- [ ] Agent 运行时框架
- [ ] Agent 管理 API（CRUD）
- [ ] Agent 管理前端页面

### Phase 2: 主-子 Agent 调度（1-2 周）
- [ ] 主 Agent 意图分析
- [ ] `delegate` 工具实现
- [ ] 子 Agent 独立执行
- [ ] 结果整合回复

### Phase 3: Agent 间协作（2 周）
- [ ] 会议室数据模型
- [ ] 会议室主持人 Agent
- [ ] 多 Agent 对话循环
- [ ] 会议纪要生成

### Phase 4: 心跳与自治（1-2 周）
- [ ] 个体心跳任务
- [ ] 跨 Agent 记忆同步
- [ ] 主动建议推送
- [ ] 群体心跳监控

### Phase 5: 完善与优化（持续）
- [ ] Agent 技能成长系统
- [ ] Agent 间关系网络
- [ ] 可视化调试面板
- [ ] 性能优化

## 九、与现有系统的兼容性

| 现有模块 | 复用方式 |
|----------|----------|
| `memory_store` | 扩展为 `AgentMemoryStore`，每个 Agent 独立 namespace |
| `cognitive_graph` | 扩展为 `AgentCognitiveGraph`，Agent 间共享部分节点 |
| `persona_profiler` | 扩展为 `AgentIdentityEngine`，每个 Agent 独立画像 |
| `emotion_detector` | 直接复用，每个 Agent 独立情绪状态 |
| `tool_executor` | 扩展权限控制，按 Agent 配置可用工具子集 |
| `scheduler` | 复用任务调度，Agent 心跳作为周期性任务 |
| `governance` | 复用审批机制，高风险操作需用户确认 |

## 十、关键决策点

### Q1: 子 Agent 是独立 LLM 调用还是共享同一个 LLM 上下文？
**推荐**: 独立 LLM 调用。每个 Agent 有自己独立的 system prompt 和记忆上下文，更符合"不同灵魂"的设计理念。代价是多消耗 Token。

### Q2: Agent 记忆是完全隔离还是部分共享？
**推荐**: 默认隔离，选择性共享。用户作为"共同上下文"自动同步给所有 Agent。Agent 间只同步显式标记为"共享"的记忆。

### Q3: 会议室是串行发言还是并行思考？
**推荐**: 串行发言（模拟真实会议）。主持人按顺序邀请 Agent 发言，每个 Agent 可以看到前面的发言记录，然后发表自己的观点。

### Q4: 心跳频率？
**推荐**: 个体心跳 5 分钟一次，群体心跳 30 分钟一次。可配置。
