# Tent OS E2E 天气工具测试 —— 完整问题报告

> 测试时间: 2026-05-01 09:04 - 09:10
> 测试场景: 3阶段自主开发（商业模式讨论 → PRD撰写 → 代码开发）
> 原则: 全部记录，不简化，测试完成后统一分析

---

## 一、测试执行摘要

| 阶段 | 测试判定 | 实际系统行为 | 延迟 | 关键问题 |
|------|---------|------------|------|---------|
| Phase 1 Round 1 (初始请求) | ✅ 通过 | 创建目录+发起商业模式讨论 | 24s | reasoning消息淹没 |
| Phase 1 Round 2 (用户回复) | ✅ 通过 | 确认商业模式要素 | 21s | reasoning消息淹没 |
| Phase 1 Round 3 (保存文档) | ❌ 超时 | **实际已完成**：生成Business_Model.html | 120s+ | **completed消息未到达客户端** |
| Phase 2 (PRD撰写) | ❌ 失败 | 返回空响应"✅ 文档生成 任务执行完成" | 35s | 无实际PRD内容输出 |
| Phase 3 (代码开发) | ❌ 超时 | 触发approval.request要求人工确认 | 123s+ | **approval机制阻塞自动化** |

**系统实际能力评估**: Phase 1 核心任务（目录创建+商业模式文档生成）**实际已完成**，但消息协议和客户端同步存在严重问题。

---

## 二、问题清单（共18项，按严重性排序）

### 🔴 Critical (0项)
无系统崩溃或数据丢失。

### 🟠 High (9项)

#### H1: API Key前缀泄露到日志 [SECURITY]
- **位置**: `tent_os/llm/kimi_coding.py`
- **现象**: 每次LLM调用记录 `api_key length: 72, prefix: sk-kimi-qoFIKrn...`
- **影响**: API key前缀暴露于无访问控制的日志文件
- **修复**: 删除或降级该debug日志为trace级别，或使用哈希代替前缀

#### H2: chat.completed消息未到达测试客户端 [PROTOCOL]
- **位置**: API Server WebSocket转发 / NATS消息订阅
- **现象**: 
  - 系统日志显示 `[PROMISE] 承诺完成` (09:06:39)
  - 但测试脚本的WebSocket在120s内未收到 `chat.completed`
  - 测试脚本最终因超时退出
- **根因推测**: 
  - `MessageBus.subscribe()` 使用 `DeliverPolicy.BY_START_TIME` + `opt_start_time=now()`，可能丢弃了未消费的消息
  - 或 `_on_task_completed` 在处理中抛异常未转发
- **影响**: 客户端无法感知任务完成，导致重复请求或超时

#### H3: approval.request阻塞自动化流程 [AUTOMATION]
- **位置**: `governance/worker.py` 权限系统
- **现象**: Phase 3中系统发送 `approval.request` 要求确认文件覆盖操作，测试脚本无法自动处理
- **证据**: `⏸️ 检测到文件覆盖操作，需要确认: python3 -c "content = '''# Weather CLI - 产品需求文档..."
- **影响**: 任何涉及文件覆盖/修改的自动化任务都会被阻塞，需要人工干预
- **建议**: 提供自动化模式配置，或让测试脚本能自动批准低风险操作

#### H4: 文件格式不匹配 [UX]
- **位置**: 工具选择 / Skill路由
- **现象**: 用户要求 `business_model.md`，系统生成 `Business_Model.html`
- **根因**: 系统激活了 `render_document` Skill（输出HTML），而非 `file_write` 工具（输出纯文本/md）
- **影响**: 用户明确要求markdown格式，系统输出HTML格式，不符合预期

#### H5: Phase 3文件缺失 [OUTPUT]
- **现象**: `weather.py` 和 `readme.md` 未生成
- **根因**: Phase 3因approval阻塞而超时，代码生成未完成

#### H6: Phase 2 PRD文件缺失 [OUTPUT]
- **现象**: `prd.md` 未生成（或测试脚本未检测到）
- **根因**: Phase 2返回的响应为空（仅15字符"✅ 文档生成 任务执行完成"），未实际写入文件

#### H7: Phase 1文件格式错误 [OUTPUT]
- **现象**: 预期 `business_model.md`，实际 `Business_Model.html`
- **根因**: 同H4

#### H8: 工具使用纠正逻辑错误 [LOGIC]
- **位置**: Tool Loop工具选择纠正
- **现象**: shell成功执行 `mkdir` 后，系统"纠正"为 `render_webpage (创建网页目录)`
- **证据**: `[GOV] 工具使用纠正: shell → render_webpage`
- **影响**: LLM的工具选择被系统错误覆盖，导致后续迭代使用错误工具

#### H9: LLM对工具执行结果的认知偏差 [COGNITION]
- **现象**: LLM认为"mkdir不在白名单内"被拦截，但实际上shell工具成功执行了
- **证据**: reasoning消息中显示"shell命令被拦截了，mkdir不在白名单内"
- **影响**: LLM基于错误前提进行后续推理，可能导致错误的工具链选择

### 🟡 Medium (7项)

#### M1: chat.stream_reasoning消息未被客户端识别 [PROTOCOL]
- **现象**: 系统发送大量 `chat.stream_reasoning` 消息，客户端标记为 `UNKNOWN_MSG`
- **影响**: 客户端无法展示AI的思考过程，用户体验受损
- **建议**: 在API文档中明确 `chat.stream_reasoning` 消息类型，或合并到 `chat.stream_chunk`

#### M2: Reasoning流式输出粒度极细 [PERFORMANCE]
- **现象**: 每个中文字符单独一个WebSocket消息，一轮产生500+条消息
- **影响**: WebSocket消息量爆炸，网络开销大，客户端处理压力高
- **数据**: Round 1 reasoning消息约300条，Round 2约400条
- **建议**: 按句子或语义单元批量发送，减少消息数量

#### M3: Tool Loop迭代延迟高 [LATENCY]
- **数据**: 
  - Round 1: 2次迭代，24s
  - Round 2: 1次迭代，21s
  - Round 3: 3次迭代，系统实际耗时54.5s+自验证97s=151s
- **根因**: 每次迭代 = LLM调用(8-15s) + 工具执行 + 结果回传 + LLM再推理
- **影响**: 多轮迭代累积延迟高，用户体验差

#### M4: 自验证机制增加额外延迟 [LATENCY]
- **现象**: `[VALIDATOR] 自验证触发: many_iterations`，LLM评估耗时97s
- **证据**: 09:06:39触发，09:08:16完成
- **影响**: 在已有延迟基础上额外增加1-2分钟
- **建议**: 自验证应异步执行，不阻塞主响应流程

#### M5: 同一会话Skills激活不一致 [SKILL_ROUTING]
- **数据**:
  - Round 1: `['software-engineer', 'project-management']`
  - Round 2: `['copywriting', 'shell_expert']`
  - Round 3: `['canvas-design', 'document-skills']`
- **影响**: 同一上下文下Skills频繁切换，系统行为不一致

#### M6: 话题切换记录显示跨会话上下文泄漏 [CONTEXT]
- **现象**: `话题切换: 帮我写一段Python快速排序代码 → 帮我开发...`
- **影响**: 当前会话日志混入其他会话内容，干扰调试

#### M7: sqlite-vec持续失败 [DEGRADATION]
- **现象**: 每次消息都触发 `sqlite-vec vec0虚拟表创建失败`
- **影响**: 语义搜索降级为关键词匹配（已知问题，已列在active issues中）

### 🟢 Low (2项)

#### L1: 经验提取每次对话后触发 [PERFORMANCE]
- **现象**: 每次对话结束后触发 `[GOV] 经验提取触发: error_lesson` + 规则反馈
- **影响**: 每次额外消耗1次LLM调用

#### L2: API缺少/health端点标准路径 [DEVEX]
- **现象**: `GET /health` 返回404，实际是 `/api/v1/health`
- **影响**: 监控和健康检查脚本需要硬编码非标准路径

---

## 三、根因分析

### 核心问题1: 消息协议设计与客户端期望不匹配

```
系统发送的消息类型:
  - chat.message_accepted ✅
  - chat.stream_reasoning ⚠️ (客户端不认识)
  - chat.stream_chunk ❓ (测试脚本未收到，可能未发送)
  - chat.completed ❌ (经常丢失或延迟)
  - approval.request ❌ (客户端不认识，阻塞自动化)

客户端期望:
  - chat.stream_chunk → 收集回复内容
  - chat.completed → 标记完成
  - chat.tool_progress → 跟踪工具调用
```

**结论**: API消息协议没有文档化，且 `chat.stream_reasoning` 和 `chat.stream_chunk` 分离的设计导致客户端无法正确组装最终回复。

### 核心问题2: 自动化模式缺失

系统在执行风险操作（文件覆盖、shell命令）时强制要求人工approval，但没有提供自动化/测试模式的绕过机制。这使得：
1. 自动化测试无法进行
2. 批量任务处理被阻塞
3. CI/CD集成困难

### 核心问题3: Tool Loop串行迭代瓶颈

```
迭代1: LLM推理(10s) → 工具执行(1s) → 结果回传 → LLM再推理(10s) → ...
3次迭代 = 30s+ LLM时间 + 工具时间 + 网络时间
加上自验证(97s) = 120s+ 总延迟
```

### 核心问题4: Skill路由与工具选择不一致

系统根据消息内容动态切换Skills，但Skills决定了可用工具集。这导致：
- 同一任务在不同轮次使用不同工具
- 用户要求的格式（md）和系统输出的格式（html）不匹配

---

## 四、修复优先级建议

### P0（立即修复）
1. **移除API key debug日志** — 安全风险，1行代码
2. **修复MessageBus消息丢失** — 影响所有客户端消息接收，改 `DeliverPolicy.BY_START_TIME` 为 `ALL`
3. **添加自动化测试模式** — 允许自动approval低风险操作

### P1（本周修复）
4. **统一消息协议** — 文档化所有消息类型，合并或区分 reasoning/chunk
5. **优化reasoning消息粒度** — 按句子批量发送，减少WebSocket消息量
6. **修复工具使用纠正逻辑** — 不要纠正已成功执行的工具
7. **自验证异步化** — 不阻塞主响应流程

### P2（本月修复）
8. **Tool Loop并行化** — 支持parallel_tool_calls，减少迭代次数
9. **Skills上下文一致性** — 同一会话内Skills不应频繁切换
10. **修复sqlite-vec降级** — 提供numpy/hash后备方案

---

## 五、测试脚本改进建议

1. 处理 `chat.stream_reasoning` 消息（收集reasoning内容用于质量评估）
2. 处理 `approval.request` 消息（自动批准低风险操作）
3. 增加超时时间到300s（复杂任务需要更长时间）
4. 文件检查应在系统确认完成后再执行
5. 支持检测 `.html` 文件作为 `.md` 的替代（但应记录格式不匹配问题）

---

## 六、系统能力评估

| 能力维度 | 评分 | 说明 |
|---------|------|------|
| 需求理解 | ⭐⭐⭐⭐ | 正确理解了3阶段流程和停止review要求 |
| 主动提问 | ⭐⭐⭐⭐⭐ | Round 1主动提出了5个商业模式关键问题 |
| 文件生成 | ⭐⭐⭐ | 生成了高质量HTML文档，但格式不符合要求 |
| 消息同步 | ⭐⭐ | completed消息经常丢失，客户端无法感知完成 |
| 延迟性能 | ⭐⭐ | 单轮20s+，复杂任务120s+ |
| 自动化友好 | ⭐ | approval机制阻塞所有自动化测试 |
| 安全控制 | ⭐⭐⭐⭐⭐ | 危险命令拦截有效，文件覆盖需要确认 |

---

*报告生成时间: 2026-05-01 09:15*
*日志文件: /tmp/tent_os_e2e_test.log*
*系统日志: /tmp/tent_os_launch.log*
