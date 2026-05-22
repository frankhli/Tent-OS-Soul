# Tent OS V2 记忆系统升级路线图

> 基于 RESEARCH_SYNTHESIS.md 的综合研究，制定分阶段实施计划
> 原则：先做底层修复（避免 OpenViking 的结构性缺陷），再做上层增强

---

## Phase 2A: 记忆基础设施升级（底层修复）

**目标**：修复当前 L0/L1 "名存实亡" 问题，建立真正可用的分层检索体系

### 2A.1 索引指针层（L0 Index）—— 对标 Claude Code memory.md

**问题**：当前 `inject_on_session_start()` 直接组装三段内容塞入 Prompt，没有路由层。随着记忆增长，这个注入内容会失控膨胀。

**方案**：
```
┌─────────────────────────────────────────────────────────────┐
│  当前: 直接注入三段内容（用户画像 + 近期摘要 + 待办）          │
│  未来: L0 索引 → 按需加载具体文件                              │
├─────────────────────────────────────────────────────────────┤
│  tent://memory/index.md (始终加载, ~200 tokens)              │
│  ├── user: tent://memory/user/profile.md                     │
│  ├── recent: tent://memory/session/2026-04-22.md            │
│  ├── decisions: tent://memory/decisions/                     │
│  └── tasks: tent://memory/tasks/active.md                    │
└─────────────────────────────────────────────────────────────┘
```

**实现**：
- 新增 `MemoryIndex` 类：维护轻量级索引文件
- `inject_on_session_start()` 改为：加载索引 → 根据 task_query 决定加载哪些文件
- 索引支持 `hot`（常加载）/ `warm`（按需加载）/ `cold`（仅检索）三级

### 2A.2 L0/L1 保证可达 —— 修复 OpenViking #1549

**问题**：OpenViking 的 DIRECTORY_DOMINANCE_RATIO=1.2 导致密集的 L2 候选永远压倒 L0/L1，100% 注入的是 L2 原始对话。

**方案**：**强制分层检索协议**
```python
async def hierarchical_search(query_vector, limit=5):
    """强制分层：先搜 L0，确认相关后再考虑 L1，绝不直接跳到 L2"""
    # Step 1: L0 检索（轻量，全部候选）
    l0_candidates = await search_l0(query_vector, limit=limit*3)
    
    # Step 2: 相关性确认（L0 分数 > 阈值才进 L1）
    relevant_l0 = [c for c in l0_candidates if c.score > 0.6]
    if not relevant_l0:
        return []  # L0 不相关，不浪费时间加载 L1/L2
    
    # Step 3: L1 加载（只为确认的 L0 候选加载）
    results = []
    for l0 in relevant_l0[:limit]:
        l1 = await load_l1(l0.uri)  # L1 是 LLM 生成的摘要，不是原始截断
        results.append({
            "uri": l0.uri,
            "l0_abstract": l0.abstract,
            "l1_overview": l1.overview,  # ~500-1000 tokens 的 LLM 摘要
            "score": l0.score,
        })
    
    # Step 4: L2 绝不自动注入 Prompt
    # L2 只通过 tool_call memory_read(uri) 按需读取
    return results
```

**关键规则**：
1. **L2 绝不自动注入 Prompt** — 只存文件，只通过工具调用读取
2. **L1 必须 LLM 生成** — 不是原始文本截断，是结构化摘要
3. **L0 是唯一的向量搜索目标** — 不直接向量搜 L1/L2

### 2A.3 L1 LLM 生成 —— 替代当前"截断"方案

**当前**：`l1 = chunk[:2000] + "..."` — 这是假 L1，真截断

**目标**：用 LLM 生成真正的 L1 概览
```python
async def generate_l1_overview(chunk: str, uri: str) -> str:
    """调用 LLM 生成结构化概览"""
    prompt = f"""总结以下内容的结构和核心要点：
    
{chunk[:3000]}

格式：
- 一句话摘要（50字内）
- 核心要点（3-5条 bullet）
- 涉及的关键实体（人/项目/系统）
- 时间线（如有）
- 与哪些主题相关（用于检索标签）
"""
    return await llm.generate(prompt)
```

**成本优化**：
- 批量生成（一次处理多个 chunks）
- 缓存已生成的 L1（hash 去重）
- 非阻塞：L1 生成异步后台进行，不影响主流程

---

## Phase 2B: 自主神经系统（主动代理）

**目标**：让 Tent OS 从"等待指令"进化为"主动服务"

### 2B.1 Heartbeat 机制 —— 对标 OpenClaw Heartbeat

**设计**：
```
┌────────────────────────────────────────┐
│  Heartbeat Scheduler                   │
│  ├── 定时触发（默认 30 分钟）           │
│  ├── 读取 HEARTBEAT.md 任务清单         │
│  ├── 检查每个任务的触发条件             │
│  ├── 条件满足 → 生成 governance.request │
│  └── 条件不满足 → HEARTBEAT_OK         │
└────────────────────────────────────────┘
```

**HEARTBEAT.md 格式**：
```markdown
# Heartbeat 任务清单

## 高频检查（每次心跳）
- [ ] 检查是否有待审批的任务（governance.approval.request 状态）
- [ ] 检查 OFFLINE 执行者是否需要恢复

## 中频检查（每 2 次心跳 = 1小时）
- [ ] 检查任务队列深度是否异常
- [ ] 生成系统健康简报

## 低频检查（每 48 次心跳 = 24小时）
- [ ] 记忆压缩：将过期 L0/L1 归档
- [ ] 生成日报/周报
```

**实现**：
- 新增 `tent_os/autonomy/heartbeat.py`
- 复用现有 NATS 消息总线发布 governance.request
- 轻量级：每次心跳只读 HEARTBEAT.md，不加载全部记忆

### 2B.2 Cron 精确调度

**设计**：标准 Cron 语法，支持到秒级
```python
# config/heartbeat.yaml
cron_jobs:
  - name: "morning_briefing"
    cron: "0 8 * * *"  # 每天早8点
    task: "生成系统健康简报并通知用户"
  
  - name: "weekly_report"
    cron: "0 9 * * 1"  # 每周一早9点
    task: "汇总上周任务完成情况"
```

### 2B.3 记忆整合任务（简化版 KAIROS）

**设计**：非实时守护进程，而是心跳触发的后台任务
```python
async def memory_consolidation_task():
    """空闲时执行的记忆整合"""
    # 1. 读取最近 N 天的 L0 摘要
    recent = store.get_recent(days=7, limit=50)
    
    # 2. 检测矛盾（同一实体的不一致描述）
    contradictions = detect_contradictions(recent)
    
    # 3. 合并零散观察（同一主题的多个碎片）
    merged = merge_fragments(recent)
    
    # 4. 将高频出现的临时记忆提升为长期记忆
    promoted = promote_frequently_accessed(recent)
    
    # 5. 更新索引
    update_memory_index()
```

---

## Phase 2C: 治理系统升级（质量革命）

**目标**：引入 Harness 的 Planner/Generator/Evaluator 分离

### 2C.1 Evaluator 代理

**当前流程**：
```
governance.request → Plan生成 → 审批 → Execute → 返回结果
```

**升级流程**：
```
governance.request → Plan生成 → 审批 → Execute → Evaluate → 结果
                                   ↑___________________↓
                                    (评估不通过则重试)
```

**Evaluator 设计**：
```python
class Evaluator:
    """独立评估代理 — 被调为"怀疑者"模式"""
    
    async def evaluate(self, task_result: TaskResult, plan: Plan) -> Evaluation:
        # 1. 检查输出是否符合 plan 的预期
        completeness = check_completeness(task_result, plan)
        
        # 2. 检查是否有明显错误（如空结果、异常堆栈）
        correctness = check_correctness(task_result)
        
        # 3. 检查是否满足 Sprint Contract（如果有）
        contract_compliance = check_contract(task_result, plan.contract)
        
        # 4. 综合评分
        score = weighted_score(completeness, correctness, contract_compliance)
        
        # 5. 严格阈值：任何维度低于阈值即失败
        if score < self.threshold:
            return Evaluation(
                pass_=False,
                score=score,
                feedback=generate_actionable_feedback(task_result),
                retry_recommended=True
            )
```

**与现有架构集成**：
- Evaluator 是 Governance Worker 内部的一个步骤（不是独立进程）
- 利用现有 NATS 总线传递评估结果
- 可配置：简单任务跳过评估（节省成本）

### 2C.2 Sprint Contracts（可选增强）

**设计**：Plan 阶段生成 JSON 格式的"完成标准"
```json
{
  "contract_id": "task-123",
  "criteria": [
    {"name": "功能完整性", "weight": 0.4, "min_score": 0.7},
    {"name": "安全性", "weight": 0.3, "min_score": 0.9},
    {"name": "性能", "weight": 0.3, "min_score": 0.6}
  ],
  "acceptance_tests": [
    "API 返回 HTTP 200",
    "响应时间 < 500ms",
    "无异常堆栈"
  ]
}
```

---

## Phase 2D: 记忆生命周期与自动捕获

**目标**：记忆不仅是存储，还要会"遗忘"和"进化"

### 2D.1 Weibull 衰减（简化版）

**三层分级**：
```python
@dataclass
class MemoryTier:
    name: str           # core / working / peripheral
    beta: float         # 衰减系数
    floor: float        # 最低保留分数
    promotion_threshold: float  # 升级阈值
    demotion_threshold: float   # 降级阈值

TIERS = {
    "core": MemoryTier("core", beta=0.8, floor=0.9, promotion_threshold=999, demotion_threshold=0.7),
    "working": MemoryTier("working", beta=1.0, floor=0.7, promotion_threshold=0.85, demotion_threshold=0.5),
    "peripheral": MemoryTier("peripheral", beta=1.3, floor=0.5, promotion_threshold=0.7, demotion_threshold=0),
}
```

**Composite Score 计算**：
```python
def compute_memory_score(memory, now):
    age_days = (now - memory.created_at).days
    recency_score = exp(-0.1 * age_days)  # 40%
    frequency_score = min(memory.access_count / 10, 1.0)  # 30%
    intrinsic_score = memory.importance  # 30%（LLM 评估或规则标记）
    return 0.4 * recency_score + 0.3 * frequency_score + 0.3 * intrinsic_score
```

**简化实现**：
- Phase 2D 只实现衰减计算和分层标记
- 自动升降级放在 Phase 2E

### 2D.2 Auto-Capture（规则版）

**不调用 LLM，用规则检测六类记忆**：
```python
AUTO_CAPTURE_PATTERNS = {
    "decision": r"(决定|决策|选用|选择).{0,30}(使用|采用|定为|确定)",
    "preference": r"(我?(喜欢|偏好|习惯|总是|从不)).{0,50}",
    "error": r"(错误|bug|异常|失败|问题).{0,30}(因为|由于|修复|解决)",
    "entity": r"(项目|系统|服务|API|数据库).{0,20}(叫|名为|是)",
    "pattern": r"(我们?通常|一般|总是|规范).{0,50}",
    "fact": r"(.{0,30}(是|位于|属于|有).{0,30})",
}
```

**触发时机**：
- 任务完成后，自动扫描对话记录
- 匹配到的内容 → 提取 → 存入 L0（标记 auto_captured=True）
- 不阻塞主流程，后台异步执行

---

## Phase 2E: 高级功能（可选）

| 功能 | 复杂度 | 价值 | 建议 |
|------|--------|------|------|
| 子 Agent Fork（维护任务隔离） | 高 | 中 | Phase 3 |
| Prompt Cache Break Vectors 追踪 | 中 | 中 | Phase 3 |
| Two-Stage Deduplication（LLM 去重） | 高 | 低 | 延后 |
| 从经验生成 Skills | 高 | 高 | Phase 3 |
| 真实 Embedding API 接入 | 低 | 高 | **立即做** |

---

## 实施优先级建议

### 立即做（本周）
1. ✅ 接入真实 Embedding API（解决 mock_embed 固定向量问题）
2. ✅ L1 LLM 生成（替换当前的 chunk[:2000] 截断）
3. ✅ L2 不自动注入 Prompt（修复 OpenViking 式污染）

### 短期（2-3周）
4. ✅ Memory Index 指针层（Claude Code 模式）
5. ✅ Heartbeat 机制（OpenClaw 模式）
6. ✅ Evaluator 代理（Harness 模式）

### 中期（1-2月）
7. ✅ 记忆生命周期（Weibull 衰减）
8. ✅ Auto-Capture 六分类
9. ✅ 记忆整合任务（简化 KAIROS）

### 长期（3月+）
10. ✅ 子 Agent Fork
11. ✅ 从经验生成 Skills
12. ✅ 完整的 Prompt Cache Break Vectors 追踪

---

## 成本预估

| 升级项 | 额外 Token 成本 | 开发工作量 | 运行成本 |
|--------|----------------|-----------|---------|
| L1 LLM 生成 | 一次性（摄入时） | 中 | 低 |
| Heartbeat | 每30分钟触发 | 低 | 极低 |
| Evaluator | 每个任务 +1 LLM 调用 | 中 | 中 |
| 记忆整合 | 每日1次 | 中 | 低 |
| Auto-Capture | 规则检测，零 LLM | 低 | 零 |

**总体判断**：升级后的 Tent OS 运行成本增加约 20-30%，但质量提升和幻觉降低的收益远大于成本。


---

## Phase 2F: 竞争格局驱动的关键升级（新增）

基于 Mem0/Zep/LangMem/微软AGT/Galileo/物理调度研究，以下升级具有最高优先级：

### 2F.1 记忆自我编辑（Mem0 精华）

**问题**：当前记忆是追加式的，同一事实变化后旧版本仍然存在。

**方案**：
```python
async def memory_update_decision(new_fact: str, existing_memories: List) -> str:
    """
    LLM 决策：
    - ADD: 全新事实
    - UPDATE: 替换旧事实（如地址变更）
    - DELETE: 删除过时事实
    - NOOP: 无变化
    - CONTRADICT: 标记矛盾，待人工确认
    """
```

### 2F.2 时间维度（Zep 精华）

**问题**：当前 `created_at` 只是记录创建时间，不代表事实有效期。

**方案**：
```sql
ALTER TABLE l0_index ADD COLUMN valid_from TEXT;
ALTER TABLE l0_index ADD COLUMN valid_to TEXT;
ALTER TABLE l0_index ADD COLUMN superseded_by TEXT;  -- 指向新版本的 URI
```

查询时支持时间切片：
```python
store.search_at_time(query, timestamp="2026-03-01")  # 查询3月1日时的记忆状态
```

### 2F.3 程序记忆（LangMem 精华）

**问题**：Agent 的行为规则是静态的（SOUL.md 人工维护），不会从经验中学习。

**方案**：
```
tent://memory/procedural/
├── behavior_rules.md       # 当前生效的行为规则
├── learned_patterns.md     # 从经验中学到的模式
└── deprecated_rules.md     # 已淘汰的规则
```

自动更新触发条件：
- 同一类任务成功 5 次以上 → 提取成功模式 → 更新行为规则
- 同一类任务失败 3 次以上 → 提取失败教训 → 添加约束规则

### 2F.4 确定性策略执行（微软 AGT 精华）

**问题**：当前审批阈值是单一数字（0.5），不够精细。

**方案**：YAML 策略规则，<1ms 执行：
```yaml
# config/policies.yaml
policies:
  - name: "高危操作双人审批"
    condition: "action.danger_level > 0.7"
    action: "require_approval"
    approvers: 2
  
  - name: "物理执行者熔断保护"
    condition: "executor.consecutive_failures >= 3"
    action: "circuit_break"
    cooldown: "300s"
  
  - name: "夜间限制物理操作"
    condition: "time.hour >= 22 OR time.hour <= 6"
    action: "deny"
    except: "emergency_override"
```

### 2F.5 执行者状态机（VDA 5050 精华）

**问题**：当前执行者状态简单（ONLINE/OFFLINE），没有任务生命周期状态。

**方案**：
```
IDLE → ASSIGNED → EXECUTING → COMPLETED
  ↓       ↓           ↓           ↓
ERROR ← CANCELLED ← TIMEOUT ← FAILED
```

每个状态转换都通过 NATS 发布事件，支持 Saga 事务回滚。

### 2F.6 Kill Switch（微软 AGT + 物理安全）

**问题**：物理执行者（机器人）失控时没有紧急停止机制。

**方案**：
```python
class EmergencyStop:
    """紧急停止 — 秒级响应"""
    
    async def kill_all_physical(self):
        """停止所有物理执行者"""
        for executor in physical_executors:
            await bus.publish(f"executor.{executor.id}.emergency_stop", {})
    
    async def kill_by_zone(self, zone_id: str):
        """按区域停止"""
        ...
```

### 2F.7 SLO 与错误预算（Galileo + 微软 AGT SRE）

**问题**：当前没有量化的服务质量目标。

**方案**：
```yaml
# config/slo.yaml
slos:
  - name: "任务完成率"
    target: 0.99
    window: "7d"
  
  - name: "Plan 生成延迟"
    target: 0.95  # 95% 在 5 秒内
    threshold: "5s"
  
  - name: "执行者可用率"
    target: 0.999
    window: "30d"
```

错误预算耗尽时自动触发保护模式（降低并发、增加审批）。

---

## 更新后的实施优先级

### 🔴 P0：立即做（本周）
1. 真实 Embedding API（解决 mock_embed）
2. L1 LLM 生成（替换 chunk 截断）
3. L2 不自动注入 Prompt（修复 OpenViking 污染）
4. **执行者状态机（VDA 5050 风格）**
5. **Kill Switch 紧急停止**

### 🟡 P1：短期（2-3周）
6. Memory Index 指针层
7. Heartbeat 机制
8. Evaluator 代理
9. **确定性策略执行（YAML 规则）**
10. **时间维度（valid_from/valid_to）**

### 🟢 P2：中期（1-2月）
11. 记忆生命周期（Weibull 衰减）
12. Auto-Capture 六分类
13. 记忆自我编辑（ADD/UPDATE/DELETE）
14. **程序记忆（经验→行为规则）**
15. **SLO 与错误预算**

### 🔵 P3：长期（3月+）
16. 子 Agent Fork
17. 从经验生成 Skills
18. Prompt Cache Break Vectors
19. **混沌工程（随机故障注入测试）**

---

## 终极判断

研究完所有竞品后，Tent OS 的核心竞争力变得更加清晰：

> **别人在做"AI Agent 的记忆/框架/治理"，Tent OS 在做"物理世界的操作系统"。**

这不是降维打击，是**维度错位竞争**：
- Mem0/Zep/LangMem 是纯数字记忆 → Tent OS 是物理+数字混合记忆
- 微软 AGT/Galileo 是纯软件治理 → Tent OS 是物理执行者的安全治理
- M4/LocusONE 是纯机器人调度 → Tent OS 是机器人+人类混合调度

**Tent OS 不应该在红海竞争，应该强化蓝海的独特性。**

