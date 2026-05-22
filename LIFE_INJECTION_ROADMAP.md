# Tent OS 生命化改造路线图

> 目标：从"机械化流水线"改造为"有自主判断能力的智能体"

## 改造原则

1. **System 1 直觉层**：0 LLM，纯规则/缓存（<1ms）
2. **System 2 思考层**：主 LLM 按需触发（唯一阻塞路径）
3. **System 3 元认知层**：后台轻量 LLM，不阻塞（10% 触发率）
4. **System 4 价值观层**：融入主 LLM system prompt，不额外调用

---

## 已完成改造 ✅

| # | 文件 | 改动 | 状态 |
|---|------|------|------|
| 1 | `tent_os/governance/session_scheduler.py` | **新建**：操作系统式会话调度器，解决全局串行阻塞 | ✅ |
| 2 | `tent_os/message_bus.py` | `subscribe()` 增加 `concurrent=True`，NATS callback 快速 ack | ✅ |
| 3 | `tent_os/governance/worker.py` | `_ingest_memory` 从 `await` 改为 `asyncio.create_task` | ✅ |
| 4 | `tent_os/governance/worker.py` | `_assess_security` 降级逻辑：不自动 strict，高置信度才降级 | ✅ |
| 5 | `tent_os/governance/worker.py` | `_assess_security` 后台化：2秒超时快速回退 | ✅ |
| 6 | `tent_os/governance/auto_classifier.py` | `_heuristic_evaluate` 扩大问候/闲聊覆盖 | ✅ |
| 7 | `tent_os/governance/worker.py` | `_extract_experience_after_chat` / `_evaluate_rule_compliance` 改为 `create_task` | ✅ |

---

## Phase 1: 核心认知重构（优先最高，本周完成）

### 1.1 安全评估直觉化 —— 0 LLM

**文件**：`tent_os/governance/worker.py`  
**当前问题**：`_assess_security` 每轮对话都调用，即使缓存命中也需要 Redis 加载。  
**改造后**：直觉层 0ms 判断，不调用 LLM，不加载缓存。

```python
# 改造前（当前）
security_task = asyncio.create_task(_security_background())
# ... 等待 2 秒超时 ...

# 改造后（直觉层）
def _security_intuition(self, task: str, session_id: str) -> Dict:
    # 直觉 1：危险命令 = 像看到蛇，立即躲开
    if is_dangerous_command(task):  # 正则匹配，0ms
        return {"mode": "strict", "source": "intuition_danger"}
    
    # 直觉 2：熟悉的 session + 相似话题 = 像回家，直接进门
    if self._is_trusted_context(session_id, task):  # 查内存缓存，0.01ms
        return {"mode": "standard", "source": "intuition_trusted"}
    
    # 直觉 3：闲聊/问候 = 默认安全
    if is_casual_chat(task):  # 短文本+问候词检测，0.01ms
        return {"mode": "standard", "source": "intuition_casual"}
    
    # 直觉不确定：默认 standard，不阻塞，不评估
    return {"mode": "standard", "source": "intuition_default"}
```

**删除代码**：
- `worker.py` 中 `_assess_security` 的 LLM 评估分支
- `auto_classifier.py` 中 `_llm_evaluate` 的调用链（保留作为备选，但默认不触发）

---

### 1.2 经验提取元认知化 —— 后台轻量 LLM

**文件**：`tent_os/governance/worker.py`  
**当前问题**：`_extract_experience_after_chat` 每轮对话后 `create_task` 调用，无价值判断。  
**改造后**：直觉过滤 90%，10% 走后台轻量 LLM。

```python
# 改造前（当前）
asyncio.create_task(self._extract_experience_after_chat(session_id, messages, response))

# 改造后（元认知层）
async def _metacognitive_extract(self, session_id, messages, response):
    # Layer 0：直觉过滤（0ms，90% 在这里返回）
    if self._is_obviously_trivial(messages, response):
        return  # 问候/闲聊/已完成请求 → 不记
    
    # Layer 1：失败信号（直觉，0ms）
    if "失败" in response or "错误" in response:
        flag = "failure_lesson"
    # Layer 2：用户显式标记（直觉，0ms）
    elif any(kw in messages[-2]["content"] for kw in ["请记住", "记下来"]):
        flag = "user_requested"
    else:
        flag = "needs_reflection"
    
    # Layer 3：轻量 LLM 反思（后台，不阻塞，10% 触发）
    # prompt <100 tokens，只问"有"或"无"
    asyncio.create_task(self._light_reflection(session_id, messages, response, flag))
```

**删除代码**：
- `worker.py` 中直接调用 `_extract_experience_after_chat` 的地方
- `memory/procedural.py` 中无条件提取的逻辑

---

### 1.3 自验证按需化 —— 只在失败后触发

**文件**：`tent_os/governance/worker.py`  
**当前问题**：`self_validator.validate` 在每次 Tool Loop 正常结束后都调用。  
**改造后**：只在"有工具调用且工具失败"或"用户明确纠正"时触发。

```python
# 改造前（当前）
if (hasattr(self, 'self_validator') and self.self_validator and
    full_response and "❌ 任务执行失败" not in full_response):
    val_result = await self.self_validator.validate(...)

# 改造后（按需）
if tool_call_count > 0 and ("失败" in full_response or "错误" in full_response):
    # 搞砸了才复盘
    asyncio.create_task(self.self_validator.validate(...))
elif "不对" in last_user_msg or "错了" in last_user_msg:
    # 用户明确纠正
    asyncio.create_task(self.self_validator.validate(...))
# 否则：成功不内耗，跳过
```

---

### 1.4 背景思考事件驱动化 —— 取消 sleep(300)

**文件**：`tent_os/governance/worker.py:980`  
**当前问题**：`_background_think` 每 5 分钟固定循环。  
**改造后**：消息堆积、错误率上升、session 结束等事件触发。

```python
# 改造前（当前）
while True:
    await asyncio.sleep(300)
    # 更新工作记忆、计算心情...

# 改造后（事件驱动）
# 1. 消息堆积事件：_recent_message_count 突增 → 触发思考
# 2. 错误率事件：_recent_error_count / _recent_message_count > 0.3 → 触发思考
# 3. Session 结束事件：用户离开 → 触发思考
# 4. 空闲超时：30 分钟无消息 → 触发一次轻量思考
```

---

## Phase 2: 记忆系统生命化（下周）

### 2.1 记忆摄入加新奇度门

**文件**：`tent_os/memory/tiered_store.py:103`  
**当前问题**：所有消息无条件切片存储。  
**改造后**：嵌入相似度 > 0.92 跳过。

```python
# 改造前
chunks = self._slice_content(content, chunk_size=400, overlap=80)
for chunk in chunks:
    self.store.ingest(chunk)

# 改造后
if self._is_redundant(content):  # 嵌入相似度检查
    logger.debug("内容冗余，跳过摄入")
    return
chunks = self._slice_content(content, chunk_size=400, overlap=80)
for chunk in chunks:
    self.store.ingest(chunk)
```

---

### 2.2 塑料性引擎事件驱动化 —— 消灭所有固定间隔 sleep

**文件**：`tent_os/memory/plasticity.py`  
**当前问题**：
- Deep 阶段：`sleep(30 * 60)` 每 30 分钟
- REM 阶段：`sleep(3600)` 每小时
- 遗忘：`sleep(6 * 3600)` 每 6 小时

**改造后**：
- Deep：short_term 节点数超过动态阈值 或 session 结束时触发
- REM：图谱节点增长 > 10% 或用户显式触发时
- 遗忘：渐进式（每个节点独立计时），不是批量扫描

```python
# 改造前
await asyncio.sleep(self.deep_interval_minutes * 60)

# 改造后
# 由外部事件触发，不再自己 sleep
async def trigger_deep(self, reason: str):
    """由 session 结束、记忆压力等事件调用"""
    ...
```

---

### 2.3 图搜索语义化 —— 消灭 SQL LIKE

**文件**：`tent_os/memory/worker.py:155`  
**当前问题**：`abstract LIKE '%{kw}%'`  
**改造后**：向量相似度搜索。

**文件**：`tent_os/memory/graph.py:338`  
**当前问题**：`SELECT * FROM nodes ORDER BY confidence DESC`  
**改造后**：`SELECT * FROM nodes ORDER BY embedding_similarity(query_vec, node_vec) DESC`

---

### 2.4 工作记忆渐进衰减 —— 不死而重生

**文件**：`tent_os/memory/working_memory.py:58`  
**当前问题**：每轮完全重建，话题切换时瞬间清空。  
**改造后**：每个 slot 有 salience（显著性），按轮次指数衰减。

```python
# 改造前
self._slots = [s for s in self._slots if s.source == "user_profile"]

# 改造后
for slot in self._slots:
    slot.salience *= 0.9  # 每轮衰减 10%
self._slots = [s for s in self._slots if s.salience > 0.2]
```

---

### 2.5 遗忘渐进式 —— 消灭全表扫描

**文件**：`tent_os/memory/forgetting.py:99`  
**当前问题**：`SELECT * FROM nodes` 全表扫描。  
**改造后**：优先队列，只评估"到期"节点。

```python
# 改造前
rows = conn.execute("SELECT * FROM nodes").fetchall()

# 改造后
rows = conn.execute(
    "SELECT * FROM nodes WHERE next_review_at <= ?",
    (now,)
).fetchall()
```

---

## Phase 3: 调度器生命化（下周）

### 3.1 定时轮询 → 事件驱动

**文件**：`tent_os/scheduler/background_tasks.py:85`  
**当前问题**：`await asyncio.sleep(60)` 每分钟轮询。  
**改造后**：NATS 事件触发 + 前置条件检查。

**文件**：`tent_os/scheduler/worker.py:60`  
**当前问题**：`await asyncio.sleep(60)` 启动延迟。  
**改造后**：按需启动。

---

### 3.2 失败归因语义化 —— 消灭关键词正则

**文件**：`tent_os/scheduler/failure_attribution.py`  
**当前问题**：`ERROR_PATTERNS` 纯关键词正则匹配。  
**改造后**：LLM 语义理解错误上下文。

```python
# 改造前
if re.search(r"motor|servo|timeout", error_text):
    return "execution_error"

# 改造后
classification = await llm("根据错误日志判断根因类型：" + error_text)
return classification
```

---

### 3.3 物理执行者用真状态

**文件**：`tent_os/scheduler/executors/physical.py:180`  
**当前问题**：`state = EmbodiedState(position=(0, 0, 0), battery_level=0.8)` 假状态。  
**改造后**：查询真实机器人状态。

---

## Phase 4: 工具/技能生命化（下下周）

### 4.1 技能激活语义化 —— 消灭关键词子串匹配

**文件**：`tent_os/skills/loader.py`  
**当前问题**：`if trigger.lower() in text_lower:` 子串匹配。  
**改造后**：使用 `skills/router.py` 的语义路由（已有，需强制接管）。

**文件**：`tent_os/skills/manager.py`  
**当前问题**：`skill.matches(text)` 纯关键词。  
**改造后**：废弃 `matches()`，全部走 `SkillRouter.route()`。

---

### 4.2 工具执行前需要检查

**文件**：`tent_os/tools/executor.py`  
**当前问题**：`execute()` 无条件执行。  
**改造后**：检查冗余（5 分钟内是否执行过相同操作）。

---

## Phase 5: LLM 适配器优化（下下周）

### 5.1 盲重试 → 智能恢复

**文件**：`tent_os/llm/kimi_coding.py:75`  
**当前问题**：固定指数退避，不学习。  
**改造后**：
- 429 错误 → 读取 Retry-After 头
- 超时错误 → 切换 failover 提供商
- 记录每个端点的成功率，动态选择

---

## 全系统机械化代码清单

### 定时 Sleep（cron 大脑）

| 文件 | 行号 | 当前代码 | 改造方向 |
|------|------|---------|---------|
| `governance/worker.py` | 980 | `await asyncio.sleep(300)` | 事件驱动 |
| `governance/worker.py` | 2213 | `await asyncio.sleep(delay_ms / 1000)` | 前端背压驱动 |
| `memory/plasticity.py` | 252 | `await asyncio.sleep(30 * 60)` | session 结束触发 |
| `memory/plasticity.py` | 260 | `await asyncio.sleep(60)` | 事件触发 |
| `memory/plasticity.py` | 364 | `await asyncio.sleep(wait_seconds)` | 事件触发 |
| `memory/plasticity.py` | 372 | `await asyncio.sleep(3600)` | 事件触发 |
| `memory/plasticity.py` | 551 | `await asyncio.sleep(6 * 3600)` | 渐进式，无 sleep |
| `memory/plasticity.py` | 559 | `await asyncio.sleep(3600)` | 事件触发 |
| `memory/graph_sync.py` | 276 | `await asyncio.sleep(30)` | 按需触发 |
| `scheduler/worker.py` | 60 | `await asyncio.sleep(60)` | 事件驱动 |
| `scheduler/background_tasks.py` | 85 | `await asyncio.sleep(60)` | 事件驱动 |
| `autonomy/heartbeat.py` | 145 | `await asyncio.sleep(self.interval)` | 事件驱动 |
| `autonomy/dreaming.py` | 201 | `await asyncio.sleep(3600)` | 深夜触发 |
| `autonomy/self_healing.py` | 329 | `await asyncio.sleep(delay)` | 失败事件触发 |
| `llm/kimi_coding.py` | 75 | `await asyncio.sleep(wait)` | 智能退避 |

### SQL LIKE 搜索（非语义检索）

| 文件 | 行号 | 当前代码 | 改造方向 |
|------|------|---------|---------|
| `memory/worker.py` | 155 | `abstract LIKE '%{kw}%'` | 向量相似度 |
| `memory/graph.py` | 338 | `SELECT * FROM nodes...` | 向量相似度 |
| `memory/graph_queries.py` | 324 | `SELECT * FROM nodes...` | 向量相似度 |
| `memory/index.py` | 113 | 关键词加分 | 嵌入相似度 |
| `tools/executor.py` | 178 | 关键词匹配 | 语义搜索 |

### 全表扫描

| 文件 | 行号 | 当前代码 | 改造方向 |
|------|------|---------|---------|
| `memory/forgetting.py` | 99 | `SELECT * FROM nodes` | 优先队列 |
| `memory/forgetting.py` | 187 | `SELECT * FROM l0_index` | 时间范围过滤 |
| `memory/procedural.py` | 132 | `SELECT * FROM procedural_rules` | 索引过滤 |
| `memory/graph.py` | 370 | `SELECT * FROM nodes ORDER BY created_at` | 嵌入相似度 |

### 硬编码启发式

| 文件 | 函数 | 当前问题 | 改造方向 |
|------|------|---------|---------|
| `auto_classifier.py` | `_heuristic_evaluate` | 固定关键词列表 | 扩大覆盖，降低 LLM 触发 |
| `auto_classifier.py` | `_heuristic_complexity` | 固定动词列表+公式 | LLM 判断 |
| `plan_executor.py` | `_heuristic_needs_plan` | 固定阈值 | LLM 判断 |
| `evaluator.py` | `_rule_based_evaluate` | 固定关键词+阈值 | 语义评估 |
| `slo.py` | 全部 | 固定 SLO 阈值 | 历史基线动态 |

### 无条件执行

| 文件 | 函数 | 当前问题 | 改造方向 |
|------|------|---------|---------|
| `tools/executor.py` | `execute()` | 无条件执行 | 冗余检查 |
| `tiered_store.py` | `ingest()` | 无条件摄入 | 新奇度门 |
| `scheduler/executors/physical.py` | `execute()` | 假状态+无确认 | 真状态+高风险确认 |
| `skills/loader.py` | `matches()` | 无条件关键词匹配 | 语义路由 |

---

## 风险与回退策略

| 改造 | 风险 | 回退 |
|------|------|------|
| 安全评估直觉化 | 假阴性（漏掉危险） | 保留 LLM 评估作为后台备选 |
| 经验提取元认知化 | 漏掉有价值的经验 | 用户显式"请记住"始终优先 |
| 塑料性引擎事件驱动 | 事件丢失导致不整理 | 保留兜底定时器（24小时一次） |
| SQL LIKE → 向量 | 向量检索失败 | fallback 到 LIKE |
| 盲重试 → 智能恢复 | 新逻辑有 bug | 保留原 retry 作为 fallback |

---

## 验收标准

| 指标 | 当前 | Phase 1 目标 | Phase 3 目标 |
|------|------|-------------|-------------|
| 简单问候延迟 | 40-60s | **5-10s** | 5-10s |
| 每轮 LLM 调用 | 3-5 次 | **1-1.2 次** | 1-1.2 次 |
| 定时 sleep 数量 | 16+ | 10 | **3** |
| SQL LIKE 数量 | 5+ | 3 | **0** |
| 全表扫描数量 | 4+ | 2 | **0** |

---

*文档版本：v1.0*  
*最后更新：2026-04-24*  
*状态：方案待确认*
