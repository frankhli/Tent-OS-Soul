# Tent OS 运行时验证报告：文档声明 vs 代码实际 vs 用户体验

**验证日期**: 2026-04-24  
**验证方法**: 代码静态分析 + 运行时端到端测试 + 日志审计  
**基准文档**: `CLAUDE_CODE_INTEGRATION_BLUEPRINT.md` (2026-04-23 更新)

---

## 一、核心结论（先说结论）

> **文档说"Phase 1-3 全部完成，进入运行时验证阶段"。**
> **实际情况是：骨架全在，血肉参差不齐，约 40% 的"已完成"功能在对话流程中从未触发。**

**最危险的发现**：
1. **3 个关键模块从未在对话中被调用**（Permission Mode、Auto-Classifier、Subagent）
2. **File Memory 有 458 行代码，但 `tent_memory/files/` 目录为空**——没有 .md 文件 = 零效果
3. **Speculative Execution 有 287 行代码，但意图检测逻辑与蓝图描述不符**
4. **Slot Manager 没有蓝图里描述的 `default_max_tokens` / `extended_max_tokens` 参数**
5. **Control UI 有 11 个面板，但多个面板没有后端数据支撑**

---

## 二、13 个"已完成"模块逐一验证

### 🟢 真正在工作（有实际效果）

| 模块 | 代码行数 | 实际效果 | 与蓝图差距 |
|------|---------|---------|-----------|
| **JSONL Logger** | 467 | ✅ 写入日志文件 | 无差距 |
| **7层安全架构** | 408 | ✅ 每次工具调用都评估 | L4 Auto-Classifier 默认关闭 |
| **5层上下文压缩** | 514 | ✅ 超过 token 限制时触发 | 触发条件罕见（需 >6000 tokens） |
| **Hook Engine** | 459 | ✅ 17 事件点注册完整 | Hook 实际注册数 = 0（无插件加载） |
| **Telemetry** | 248 | ✅ 记录安全/压缩/LLM 调用 | 前端无可视化面板 |
| **Tool Pool Assembler** | 368 | ✅ 5 步组装逻辑完整 | MCP 集成是 stub |

### 🟡 代码存在但效果打折

| 模块 | 代码行数 | 问题 | 用户体验影响 |
|------|---------|------|-------------|
| **Speculative Execution** | 287 | 有 `detect_intent` 但蓝图描述的是 `_detect_tool_intent`；意图检测基于关键词而非流式 AST 解析 | 推测执行几乎不触发 |
| **Slot Manager** | 289 | 没有 `default_max_tokens` 参数，只有 `_was_truncated` | 无法主动管理输出长度 |
| **Prompt Cache v2** | 244 | 与 `build_system_prompt` 是并行系统，未完全替换旧缓存 | 缓存命中率未知 |
| **File Memory** | 457 | `tent_memory/files/` 为空，没有 .md 文件 | 有代码无数据，召回永远为空 |

### 🔴 从未在对话流程中触发

| 模块 | 代码行数 | 未触发原因 | 修复难度 |
|------|---------|-----------|---------|
| **Permission Mode** | 307 | `LayeredSecurity._l1_prefilter()` 调用 `mode_manager.is_tool_allowed()`，但 `mode_manager` 初始化后从未在 worker 中被主动引用 | 低 |
| **Auto-Classifier** | 287 | `LayeredSecurity.layers_enabled["L4_classifier"]` 默认 `False`（`config.security.auto_classifier=False`） | 低（需配轻量 LLM） |
| **Subagent Spawner** | 585 | 有 `spawn` 方法但无 `run` 方法；`_on_memory_injected` 和 `_handle_tool_loop` 中无调用点 | 中（需接入 Tool Loop） |

---

## 三、用户体验完整链路审计

### 链路 1：Control UI → 发起对话

```
用户打开 http://localhost:8002/ui/
  → WebSocket 连接 ✅
  → 显示历史会话列表 ✅（从 localStorage 读取）
  → 用户输入消息
```

**问题**：
- 没有显示当前 **Permission Mode**（strict/standard/auto/unrestricted）
- 没有显示 **WorkingMemory** 当前加载的记忆内容
- 没有显示 **Skill** 激活状态（虽然后端有日志，但前端不显示）
- 没有显示 **安全层决策**（LayeredSecurity 评估结果不暴露给前端）

### 链路 2：消息 → 治理进程处理

```
WebSocket 消息 → _handle_chat_message()
  → 情绪检测（关键词匹配）✅
  → 发布 memory.inject → 记忆进程消费 ✅
  → 记忆进程注入上下文 → _on_memory_injected() ✅
```

**问题**：
- `_on_memory_injected()` 中 **6 个 brain v2 模块串行执行**，没有并行化
- `PersonaCompressor.compress()` 调用耗时（300 token 的 LLM 生成）
- `ReasoningChain.answer_complex_question()` 在几乎所有中文问题上触发（条件太宽），但空图谱时返回空结果
- `FileMemory.recall()` 因为 `files/` 目录为空，永远返回空
- **system prompt 膨胀到 5000-8000 字符**，但 `CompressionPipeline` 只在 >6000 tokens 时触发

### 链路 3：Tool Loop → 工具执行

```
_handle_tool_loop()
  → _get_available_tools() → ToolPoolAssembler.assemble() ✅
  → chat_with_tools() → LLM 判断是否需要工具 ✅
  → LayeredSecurity.evaluate_tool_call() ✅（但 L4 跳过）
  → ToolExecutor.execute() → LocalExecutor ✅
  → 结果返回给 LLM → 下一轮
```

**问题**：
- **每轮工具调用都伴随一次 LLM 请求**，这是最大延迟来源
- `chat_with_tools()` 非流式，用户看不到 LLM "思考"过程
- Speculative Execution 不触发（意图检测不工作）
- 没有 **循环检测**——如果 LLM 反复调用同一个错误工具，不会自动停止
- 没有 **自验证**——工具执行后不会自动检查结果是否合理

### 链路 4：结果返回 → 用户看到

```
LLM 回复 → _simulate_stream() 分块发送 ✅
  → WebSocket stream chunk → 前端显示 ✅
  → 异步 _extract_experience_after_chat() → 经验提取（后台）
  → 异步 _evaluate_rule_compliance() → 规则反馈（后台）
```

**问题**：
- `_simulate_stream()` 是**假流式**——LLM 已经生成完整回复后才分块发送
- 真正的 `chat_stream()` 只在 `_handle_chat_reply()` 中使用（纯聊天无工具时）
- 经验提取和规则反馈对用户不可见（没有前端面板显示）
- **没有"任务完成"的明确状态**——用户不知道 Agent 是否还在后台执行

---

## 四、模块间冲突与副作用

### 冲突 1：System Prompt 膨胀 vs 压缩管道的矛盾

- **注入源**: injected_context (~2000 chars) + brain_context (~500-1500 chars) + skill_prompt (~500-2000 chars) + file_memory (0) + procedural_rules (~200-500 chars) + boundary_text (~300 chars) + self_state (~100 chars)
- **典型总长度**: 5000-8000 chars
- **压缩触发条件**: >6000 tokens (~18000-24000 chars)
- **结果**: 大多数对话 system prompt 在 2000-4000 tokens，**压缩管道几乎不触发**
- **副作用**: 长 system prompt 增加 LLM 生成时间 + 成本

### 冲突 2：ReasoningChain 空触发

- 触发条件: `len(task) > 20 and any(kw in task.lower() for kw in [...])`
- 几乎所有中文查询都 >20 字，且常含"怎么"/"为什么"/"推荐"
- **结果**: 每次对话都触发 reasoning，但空图谱时返回 `"confidence": 0, "answer": ""`
- **副作用**: 浪费 2-3 次 graph 查询 + 注入空内容到 prompt

### 冲突 3：ExperienceExtractor 后台 LLM 调用

- 每次对话结束后，异步调用 LLM 提取经验规则
- 如果用户快速连续发送消息，后台任务堆积
- **副作用**: 增加 API 成本，但提取的规则质量未经验证

### 冲突 4：SkillRouter 增加工具数量 → LLM 决策更困难

- Skill 激活后，可用工具从 10 个增加到 14 个
- LLM 需要在这些工具中选择，增加决策时间
- **副作用**: 工具越多，LLM 越可能选错或反复尝试

### 冲突 5：Evaluator LLM 评估的额外开销

- 计划执行完成后，Evaluator 调用 LLM 做深度评估
- 但 `_rule_based_evaluate()` 已经给了 0.97 分
- **副作用**: 额外一次 LLM 调用，增加 15-25s 延迟

---

## 五、与三巨头的差距（诚实对比）

### Tent OS 已有的（差异化壁垒）

| 能力 | 状态 |
|------|------|
| 三大进程物理隔离 | ✅ 真正在工作 |
| 状态完全外存（Redis TTL） | ✅ 真正在工作 |
| 物理执行者（机器人/闪送） | ✅ 骨架完整，待真实场景验证 |
| 办公渲染（PPT/Excel/Word） | ✅ 真正在工作 |
| 全异步消息驱动（NATS） | ✅ 真正在工作 |
| Webhook Gateway | ✅ 真正在工作 |

### Tent OS 缺失的（对标三巨头）

| 能力 | 来源 | 当前状态 | 影响 |
|------|------|---------|------|
| **IDE 深度集成** | Claude Code | ❌ 不是赛道 | — |
| **25+ 消息渠道** | OpenClaw | ❌ 不是赛道 | — |
| **CI/CD Pipeline-native** | Harness | ❌ 不是赛道 | — |
| **真正的循环检测** | Harness/Claude Code | ⚠️ 未实现 | LLM 可能无限重试 |
| **真正的自验证** | Harness | ⚠️ 未实现 | 工具结果不验证 |
| **故障自愈（物理层面）** | Harness | ⚠️ 骨架 | 机器人失败后不自动切换 |
| **OPA 策略引擎** | Harness | ⚠️ PolicyEngine 是简化版 | 策略表达力弱 |
| **RBAC 权限继承** | Harness | ❌ 未实现 | AI 权限 = 用户权限 |
| **MCP Gateway 注册表** | Harness | ⚠️ Tool Pool 是静态的 | 动态工具加载弱 |
| **ai_generated 标签追溯** | Harness | ❌ 未实现 | 输出不可追溯 |
| **推测执行结果注入** | Claude Code | ⚠️ 只缓存未注入 | 预执行结果浪费 |
| **子代理完整 ReAct** | Claude Code | ⚠️ 简化版 | 无法执行复杂子任务 |
| **文件记忆 LLM 召回** | Claude Code | ⚠️ 需要接入模型 | 文件记忆空转 |
| **Auto-Classifier 模型** | Claude Code | ⚠️ 默认关闭 | L4 安全层空转 |
| **Permission Mode UI** | Claude Code | ❌ 无前端 | 用户无法切换模式 |

---

## 六、Control UI 面板数据支撑审计

| 面板 | 代码行数 | 后端数据支撑 | 实际可用性 |
|------|---------|-------------|-----------|
| **ChatPanel** | 24574 | ✅ WebSocket 流 | 可用 |
| **SkillsPanel** | 13167 | ⚠️ 静态配置，无动态状态 | 可用但信息少 |
| **DreamPanel** | 12165 | ❌ DreamingEngine 未触发 | 空面板 |
| **MemoryPanel** | 5521 | ⚠️ 需要 API 端点 | 可能为空 |
| **RulesPanel** | 4686 | ⚠️ 需要 API 端点 | 可能为空 |
| **LogsPanel** | 6837 | ✅ JSONL 日志 | 可用 |
| **ConfigPanel** | 5787 | ⚠️ 静态配置 | 可用 |
| **SLOPanel** | 4039 | ❌ Telemetry 数据未暴露 | 空面板 |
| **ApprovalDialog** | 4261 | ✅ 审批请求 | 可用 |
| **TaskFlow** | 6335 | ⚠️ 需要任务状态 API | 部分可用 |
| **Sidebar** | 3950 | ✅ 基础导航 | 可用 |

---

## 七、关键修复建议（按优先级）

### P0：让"已完成"的模块真正工作

1. **激活 Permission Mode** —— 在 `_handle_tool_loop` 中启用 L1 pre-filter
2. **激活 Auto-Classifier** —— 配置轻量 LLM（如 kimi-k1.5）并启用 L4
3. **填充 File Memory** —— 创建示例 AGENTS.md / SOUL.md / TOOLS.md，或引导用户创建
4. **修复 Speculative Execution** —— 实现蓝图中的 `_detect_tool_intent` 逻辑

### P1：减少副作用和冲突

5. **并行化 brain v2 模块** —— `working_memory.update()` + `file_memory.recall()` + `persona_compressor.compress()` 可并行
6. **收紧 ReasoningChain 触发条件** —— 空图谱时不触发，避免无意义查询
7. **添加循环检测** —— Tool Loop 中检测连续同一工具失败，自动停止
8. **添加自验证** —— 工具执行后自动检查结果格式/内容是否合理

### P2：前端暴露后端状态

9. **显示 Permission Mode** —— 在 ChatPanel 显示当前模式
10. **显示安全层决策** —— 工具调用时显示 LayeredSecurity 评估结果
11. **显示 WorkingMemory 内容** —— 让用户看到注入了哪些记忆
12. **显示 Skill 激活状态** —— 让用户知道当前激活了哪些 Skill

### P3：差异化能力深化

13. **物理故障自愈** —— 机器人失败后自动切换备用执行者
14. **RBAC 权限继承** —— 用户权限决定 AI 权限
15. **ai_generated 标签** —— 所有渲染输出自动打上标签

---

## 八、诚实评分

| 维度 | PRD 愿景 | 当前实际 | 差距 |
|------|---------|---------|------|
| **架构设计** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 无差距，方向正确 |
| **功能实现** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 40% 功能未触发 |
| **代码质量** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | async/sync 混用、测试缺失 |
| **用户体验** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 假流式、无状态暴露、无循环检测 |
| **生产就绪** | ⭐⭐⭐⭐⭐ | ⭐⭐ | 无测试、无可观测性、无故障自愈 |
| **差异化壁垒** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 多进程+物理触达+办公渲染 是独有优势 |

**最核心的问题**：
> **不是缺功能，是缺"让功能 work 的细节"和"让用户感知到功能在 work 的界面"。**
