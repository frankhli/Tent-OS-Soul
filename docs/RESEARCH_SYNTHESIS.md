# Tent OS 记忆系统升级：综合研究报告

> 研究对象：OpenClaw / OpenViking / Claude Code(泄露源码) / Harness(Anthropic) / Second Me / 社区插件生态
> 研究日期：2026-04-22
> 核心目标：取精华去其糟粕，让 Tent OS 的记忆系统向"人类大脑"更进一步

---

## 一、各项目核心机制解剖

### 1. OpenClaw —— 文件优先的认知架构

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 价值 |
|------|------|------|
| **SOUL.md** | <500 tokens，定义人格、价值观、边界、沟通风格 | 身份一致性，跨会话稳定 |
| **USER.md** | 用户画像（姓名、公司、偏好、工作习惯） | 个性化服务基础 |
| **AGENTS.md** | 安全规则、业务上下文、技能映射 | 多层规则体系 |
| **Heartbeat** | 每30分钟自动唤醒，检查任务清单 | 从被动响应到主动代理 |
| **Cron** | 精确时间调度（如早8点简报） | 定时任务能力 |
| **Skills** | 模块化能力，可配置规则和安全 | 能力可插拔 |
| **MEMORY.md 分层** | Daily Logs(60%) + SOUL(25%) + Curated Memory(15%) | 结构性记忆分配 |
| **自动 Skills 触发** | 关键词→Skill 路由，文件类型自动识别 | 零配置能力激活 |

**糟粕（Tent OS 应避免）：**

- ❌ **Token Crusher**: 启动时全量读取 soul + daily log，200K 上下文一次塞入
- ❌ **纯文本安全漏洞**: ClawHavoc 攻击泄露 9000+ 安装的 API 密钥
- ❌ **没有真正分层加载**: 只有"读全部"和"不读"两种模式
- ❌ **L0/L1/L2 名存实亡**: 用户的 OpenClaw MEMORY.md 实际只有一层索引+扁平存储

---

### 2. OpenViking —— 字节跳动的上下文数据库

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 价值 |
|------|------|------|
| **viking:// 文件系统范式** | 统一记忆/资源/技能为虚拟文件系统 | 结构化、可导航、确定性定位 |
| **L0/L1/L2 渐进加载** | L0摘要→L1概览→L2详情，按需升级 | Token 消耗降低 83%（4.3M vs 24.6M） |
| **目录递归检索** | 目录定位 + 语义搜索结合 | 全局观 + 精确性 |
| **Session.commit() 自动压缩** | 会话结束自动提取长期记忆 | 零维护记忆积累 |
| **可视化检索轨迹** | 可观察上下文获取路径 | 可调试、可优化 |
| **Bottom-up L0/L1 生成** | 子目录 L0 聚合为父目录 L1 | 层次化摘要自动化 |

**糟粕（Tent OS 应避免）：**

- ❌ **L0/L1 结构性不可达**（GitHub #1549）：`DIRECTORY_DOMINANCE_RATIO=1.2` 导致密集 L2 候选永远压倒 L0/L1
- ❌ **auto-recall 直接读 L2**: 100% 注入的记忆是 L2 原始对话，L0/L1 生成后永远不进 Prompt
- ❌ **events 类型存储原始对话**: L2 应该存 LLM 摘要，不是原始文本
- ❌ **Token 预算管理缺失**: 没有硬上限，只靠"建议"控制 L2 加载率

**关键教训**：OpenViking 的理论设计极好，但工程实现有严重缺陷——**分层结构必须保证每层都可到达**，不能只靠文档说"应该"这样用。

---

### 3. Claude Code（泄露源码分析）—— 生产级记忆架构

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 价值 |
|------|------|------|
| **memory.md 是指针索引** | ~150 字符/行，不存数据只存位置 | 轻量路由，O(1) 定位 |
| **Self-Healing Memory** | Agent 自己重写记忆文件 | 零人工维护 |
| **Strict Write Discipline** | 文件写入成功后才更新索引 | 防止失败操作污染记忆 |
| **Skeptical Memory** | 记忆视为"提示"而非事实，需验证 | 降低幻觉风险 |
| **KAIROS / autoDream** | 空闲时记忆整合：合并、消矛盾、转事实 | 背景维护，不占用主进程 |
| **子 Agent Fork** | 维护任务用独立子进程执行 | 不污染主 Agent 思维流 |
| **14 Prompt Cache Break Vectors** | 精确追踪导致 cache 失效的因素 | 可预测的成本控制 |
| **Auto-Compact Circuit Breaker** | 3 次失败后停止（曾浪费 250K API 调用/天） | 防止级联失败 |
| **23 层 Bash 安全检查** | 每个检查有编号，对应真实攻击事件 | 防御深度 |
| **Multi-Agent in Prompt** | 协调逻辑全在 system prompt 中 | 零框架依赖，模型即协议 |
| **QueryEngine (46K 行)** | 流式响应、Tool Loop、Token 计数、权限拦截 | 生产级鲁棒性 |
| **Frustration Detection** | 正则检测用户愤怒，触发安抚逻辑 | 用户体验 |

**糟粕（Tent OS 应避免）：**

- ❌ **React + Ink 终端渲染过于复杂**: Tent OS 是后端系统，不需要终端 UI
- ❌ **Bun 依赖**: 生态锁定，Tent OS 用 Python 更通用
- ❌ **Undercover Mode**: 伦理风险，不需要
- ❌ **BUDDY Tamagotchi**: 娱乐功能，与内核无关

---

### 4. Harness（Anthropic 三代理架构）—— 质量革命

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 价值 |
|------|------|------|
| **Planner/Generator/Evaluator 分离** | 规划→生成→评估，三个独立 Agent | 解决自评估偏见 |
| **Sprint Contracts** | 执行前协商 JSON 完成标准 | 可测试的验收条件 |
| **Shared State File** | 所有 Agent 通过同一文件通信 | 零协议复杂度 |
| **Context Reset + 状态传递** | 长任务拆 Sprint，重置上下文 | 避免上下文焦虑 |
| **Evaluator 怀疑者调优** | 独立评估，偏严格而非宽松 | 质量守门员 |
| **GAN-style 反馈循环** | 生成器-评估器对抗，迭代收敛 | 质量持续改进 |

**关键数据**：同任务对比
- 单 Agent：20 分钟，$9，核心功能损坏
- 三 Agent Harness：6 小时，$200，功能完整、 polished

**糟粕（Tent OS 应避免）：**

- ❌ **共享文件通信的并发风险**: 多 Agent 同时写可能冲突（Tent OS 用 NATS 消息总线更好）
- ❌ **成本 40x 差异**: 需要智能决策何时用 Harness、何时用单 Agent

---

### 5. Second Me（论文）—— 记忆参数化

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 价值 |
|------|------|------|
| **LLM-based Parameterization** | 记忆不仅是文本，是参数化的知识表示 | 更高效的压缩和检索 |
| **L0→L1→L2 丰富化** | 层层递进，L0/L1 为 L2 提供上下文支撑 | 非独立分层，是协同分层 |
| **L2 编排器角色** | L2 不执行，而是协调外部专家模型 | 从执行到智能调度 |
| **Inner/Outer Loop** | 内循环层间集成 + 外循环资源协调 | 双层架构清晰 |

**糟粕（Tent OS 应避免）：**

- ❌ **过于学术化**: 自动化训练管线（SFT/DPO）落地成本极高
- ❌ **假设有专用模型**: 需要微调后的个人模型，不现实

---

### 6. 社区插件生态（Claude-Recall / Nemp / Memory-LanceDB-Pro）

**精华（Tent OS 应借鉴）：**

| 机制 | 说明 | 来源 |
|------|------|------|
| **Auto-Capture 六分类** | fact/preference/entity/decision/pattern/error | Claude-Memory |
| **Two-Stage Deduplication** | 向量预过滤(≥0.7) + LLM 决策(CREATE/MERGE/SKIP) | Memory-LanceDB-Pro |
| **Weibull Decay 生命周期** | Core(β=0.8)/Working(β=1.0)/Peripheral(β=1.3) | Memory-LanceDB-Pro |
| **Composite Score** | Recency 40% + Frequency 30% + Intrinsic 30% | Memory-LanceDB-Pro |
| **Self-Improvement Governance** | LEARNINGS.md / ERRORS.md，经验→技能 | Memory-LanceDB-Pro |
| **Hierarchical Directory** | index.yaml → entities/people/systems/decisions | Claude-Recall |
| **Temporal Organization** | 日→周→月→归档，自动压缩 | Claude-Recall |
| **Progressive Disclosure** | Skill 分级加载：metadata → body → reference | Memory-LanceDB-Pro |

---

## 二、Tent OS 当前状态评估

### 已实现的（✅）

| 能力 | 实现程度 | 对标项目 |
|------|---------|---------|
| 三层存储 L0/L1/L2 | 结构有，但 L1 只是截断、L2 是原始文件 | OpenViking |
| 纯 Python 向量检索 | 完整替代 sqlite-vec，功能无损 | — |
| 1500 token 工作记忆上限 | 硬截断 + 优先级排序 | OpenClaw |
| 六层 Prompt Cache | L1-L6 完整，但无 L0 索引层 | Claude Code |
| 话题切换检测 | 余弦相似度阈值检测 | — |
| 语义搜索降级 | 向量失败→时间排序 | — |

### 缺失的（❌）

| 能力 | 重要性 | 来源 |
|------|--------|------|
| 文件系统范式 | 🔴 高 | OpenViking |
| L0/L1 保证可达 | 🔴 高 | OpenViking #1549 教训 |
| 索引指针模式 | 🔴 高 | Claude Code memory.md |
| Self-Healing 记忆 | 🟡 中 | Claude Code |
| Heartbeat 自主机制 | 🟡 中 | OpenClaw |
| Evaluator 独立评估 | 🟡 中 | Harness |
| Sprint Contracts | 🟡 中 | Harness |
| 记忆生命周期（衰减） | 🟡 中 | Memory-LanceDB-Pro |
| Auto-Capture 六分类 | 🟡 中 | Claude-Memory |
| Two-Stage 去重 | 🟢 低 | Memory-LanceDB-Pro |
| KAIROS 记忆整合 | 🟢 低 | Claude Code |
| 子 Agent Fork | 🟢 低 | Claude Code |
| Prompt Cache Break Vectors | 🟢 低 | Claude Code |

---

## 三、精华去糟粕的综合判断

### 必须借鉴的（无争议）

1. **Claude Code 的索引指针模式** — memory.md 不是存储文件而是路由表，这是解决"Token Crusher"的关键
2. **OpenViking 的渐进加载** — 但必须修复 L0/L1 不可达的工程缺陷
3. **Harness 的 Evaluator 分离** — 解决自评估偏见，提升输出质量
4. **OpenClaw 的 Heartbeat** — 从被动响应到主动代理的质变

### 选择性借鉴的（需权衡）

5. **Weibull 衰减生命周期** — 好概念，但初期可以简化实现
6. **Auto-Capture 六分类** — 好概念，但可用规则提取替代 LLM 分类降低成本
7. **KAIROS 记忆整合** — 好概念，但可用定时任务替代复杂守护进程

### 不应借鉴的（明确排除）

8. ❌ OpenClaw 的启动时全量读取 — 这是 Token Crusher 根源
9. ❌ OpenViking 的 DIRECTORY_DOMINANCE_RATIO — 导致 L0/L1 结构性不可达
10. ❌ Second Me 的自动化训练管线 — 学术化，落地成本太高
11. ❌ Claude Code 的终端 UI 渲染 — Tent OS 是后端系统
12. ❌ Harness 的共享文件通信 — Tent OS 已有 NATS 消息总线，更优

---

## 四、"人类大脑"愿景的具象化

当前 Tent OS 的记忆系统 ≈ **"一个有笔记本的人"** — 能记、能搜、有上限。

目标记忆系统 ≈ **"一个真正的大脑"**：

| 大脑功能 | Tent OS 映射 | 当前状态 | 目标状态 |
|---------|-------------|---------|---------|
| 海马体（短期记忆）| 工作记忆 1500 tokens | ✅ 有 | 动态加载/卸载 |
| 颞叶（长期记忆检索）| L0/L1/L2 向量检索 | ⚠️ 有结构但缺深度 | 渐进式+保证可达 |
| 前额叶（执行控制）| Governance Worker | ✅ 有 | + Evaluator |
| 小脑（技能自动化）| Executor Plugin | ✅ 有 | + 从经验生成技能 |
| 自主神经系统 | Heartbeat/Cron | ❌ 无 | 主动代理 |
| 睡眠中的记忆巩固 | KAIROS / autoDream | ❌ 无 | 定时整合任务 |
| 自我意识 | SOUL.md / IDENTITY | ⚠️ 有文件但无系统 | 系统化身份管理 |
| 社交认知 | USER.md 用户画像 | ⚠️ 简单读取 | 持续学习更新 |


---

## 五、竞争格局补充研究

### 1. Mem0 —— 48K Stars，AWS 独家记忆提供商

**核心架构**：
- **两阶段流水线**：提取（从对话中提取事实）→ 更新（ADD/UPDATE/DELETE/NOOP）
- **不是简单追加**：用户说"我搬到班加罗尔了"，Mem0 会删除旧地址、添加新地址，不是并存
- **自我编辑记忆**：消除重复条目，无需手动去重
- **向量+图混合存储**：语义搜索 + 关系图谱

**关键数据**：
- LOCOMO 67.13%（LLM-as-Judge），p95 搜索延迟 0.200 秒
- 每对话仅 ~1,764 tokens vs 全上下文 26,031 tokens（93% 节省）
- Mem0g（图增强版）：时间敏感问题 58.13% vs OpenAI 21.71%

**糟粕**：
- ❌ 无原生时间模型（只有创建时间戳，没有事实有效期）
- ❌ 图记忆在 Pro 付费墙后（$249/月）
- ❌ 大规模下索引可靠性问题

**对 Tent OS 的启示**：
- ✅ 借鉴两阶段去重（提取+LLM决策），但 Tent OS 的审批机制天然提供更强的约束
- ✅ 记忆的自我编辑是关键能力，Agent 应该能修正自己的错误记忆

---

### 2. Zep / Graphiti —— 24K Stars，时间知识图谱

**核心架构**：
- **时间是第一等维度**：每条边携带 `valid_from`, `valid_to`, `invalid_at`
- **Temporal Knowledge Graph**：不是"用户住在哪里"，而是"用户在什么时间住在什么地方"
- **事实生命周期原生建模**

**关键数据**：
- LongMemEval 63.8% vs Mem0 49.0%（15 分差距来自时间推理）
- 能回答："用户搬家前的地址是什么？""团队什么时候从 Slack 切换到 Teams？"

**糟粕**：
- ❌ CE 版已废弃，自托管需管理 Neo4j
- ❌ 图数据库运维负担重

**对 Tent OS 的启示**：
- ✅ 时间维度是记忆的天然属性，Tent OS 的 L0 表已有 `created_at`，但需要扩展到事实有效期
- ✅ 不需要完整的图数据库，SQLite + 时间字段即可实现 Zep 80% 的时间推理能力

---

### 3. LangMem —— LangChain 官方记忆库

**核心架构**：
- **三种记忆类型**：
  - Semantic（事实和偏好）
  - Episodic（过去交互的少样本示例）
  - Procedural（自我更新的系统指令）—— **独有**
- **背景记忆管理器**：自动提取、整合、更新，Agent 不主动决定记住什么

**关键数据**：
- p95 搜索延迟 **59.82 秒** — 不适合实时交互
- LOCOMO 58.10% vs Mem0 67.13%

**糟粕**：
- ❌ 59.82 秒延迟是致命的
- ❌ LangGraph 锁定
- ❌ 无知识图谱

**对 Tent OS 的启示**：
- ✅ **程序记忆（Procedural Memory）** 是关键差异化：Agent 基于经验更新自己的行为规则
- ✅ 背景自动提取逻辑可以借鉴，但要保证性能

---

### 4. 微软 AGT（Agent Governance Toolkit）—— 治理/安全标杆

**核心架构（7 个包）**：

| 包 | 功能 | 对 Tent OS 的启示 |
|-----|------|------------------|
| **Agent OS** | 状态机策略引擎，<0.1ms 确定性执行 | 审批机制可升级为此模式 |
| **Agent Mesh** | Ed25519 + ML-DSA-65 身份，信任评分 0-1000 | Executor 身份认证可借鉴 |
| **Agent Runtime** | 4 层特权环（类似 CPU），Saga 编排，Kill Switch | 执行者分级权限 |
| **Agent SRE** | SLO、错误预算、熔断器、混沌工程 | 已有熔断器，可扩展 SLO |
| **Agent Compliance** | OWASP Top 10 全覆盖，EU AI Act 映射 | 治理合规框架 |
| **Agent Marketplace** | 插件签名验证，供应链安全 | Skill 插件签名机制 |
| **Agent Lightning** | RL 训练治理 | 暂不相关 |

**关键数据**：
- 覆盖全部 **10 个 OWASP Agentic 风险**
- **9,500+ 测试**
- 基于 prompt 的安全策略违规率 26.67% vs AGT 确定性执行 **0.00%**

**对 Tent OS 的启示**：
- ✅ **确定性策略执行** 是 Tent OS 治理的核心升级方向：当前审批是人工的，未来可以是策略自动判定
- ✅ **4 层特权环** 直接映射到 Tent OS 的执行者三维特征（标准化/社交/危险）
- ✅ **Kill Switch** 是物理执行者的刚需：机器人失控时必须能立即停止
- ✅ **Saga 编排**：多步骤任务的事务一致性（Tent OS 的 Plan/Execute 天然支持）

---

### 5. Galileo —— 评估→防护生命周期

**核心架构**：
- **Eval-to-Guardrail**：离线评估自动转化为在线防护规则
- **Luna-2 SLM**：专用评估模型，152ms 延迟，比 GPT-4 成本低 97%
- **三层防护**：输入防护（prompt injection）→ 输出防护（幻觉）→ 动作防护（越权）

**对 Tent OS 的启示**：
- ✅ Tent OS 的 Evaluator（Harness 模式）+ 审批机制，天然就是简化的 Eval-to-Guardrail
- ✅ Luna-2 思路：不需要 GPT-4 做评估，小模型即可，大幅降低成本
- ✅ 三层防护映射：输入→任务提交验证，输出→执行结果评估，动作→执行者权限检查

---

### 6. 物理世界调度 —— 几乎空白的蓝海

**现有方案（碎片化）**：

| 方案 | 类型 | 规模 | 局限 |
|------|------|------|------|
| **M4 (SEER)** | 机器人调度 | 100+/区域 | 仅仓储场景，封闭生态 |
| **LocusONE** | 机器人调度 | 1000+/设施 | 仅 Locus 品牌机器人 |
| **InOrbit** | 统一指挥 | 多品牌 | 仅机器人，不调度人类 |
| **VDA 5050** | 通信协议 | 行业标准 | 仅协议，无智能调度 |
| **ROS** | 机器人框架 | 开源 | 单机/局域网，无云端调度 |
| **车队管理** | 车辆调度 | 百级 | 仅车辆，不混合机器人 |
| **众包API** | 人力调度 | 千级 | 仅人类，无机器人 |

**关键洞察**：
- **没有统一调度人类+机器人的系统**：要么只管机器人，要么只管人类
- **Tent OS 的 SchedulerRouter（三维决策）恰好填补这个空白**：标准化程度 + 社交需求 + 危险程度
- **VDA 5050 标准**值得参考：状态机通信（IDLE→ACTIVE→ERROR），订单状态流转

**对 Tent OS 的启示**：
- ✅ SchedulerRouter 的三维决策模型（标准化×社交×危险）是差异化核心
- ✅ 执行者状态机可借鉴 VDA 5050：IDLE → ASSIGNED → EXECUTING → COMPLETED/FAILED
- ✅ Saga 编排（微软 AGT）对混合调度至关重要：机器人+人类的复合任务需要事务一致性

---

### 7. 新加坡 Model AI Governance Framework for Agentic AI

**四大治理维度**：
1. **评估和限定风险**：知道风险，通过设计限制影响范围
2. **人类问责**：明确责任分配，设计有效的人类监督
3. **技术控制和流程**：设计时控制、部署前测试、部署后持续监控
4. **终端用户责任**：透明告知、用户教育

**对 Tent OS 的启示**：
- ✅ 当前审批机制对应"人类问责"，但需要更系统的治理框架
- ✅ 技术控制（微软 AGT 的确定性策略执行）是下一阶段重点
- ✅ 透明告知：Tent OS 的日志系统已为此打下基础

---

## 六、Tent OS 竞争定位分析

### 当前格局

| 层级 | 竞争状态 | 代表 | Tent OS 定位 |
|------|---------|------|-------------|
| Agent 框架 | 🔴 红海 | LangChain, CrewAI, AutoGen, OpenClaw | ❌ 不竞争，Tent OS 是"内核"不是框架 |
| Agent 记忆 | 🔴 红海 | Mem0, Zep, LangMem | ⚠️ 差异化：物理世界+记忆结合 |
| Agent 治理/安全 | 🟡 刚变红 | 微软AGT, Galileo, Permiscope | ✅ 核心差异化：确定性策略执行 |
| 物理世界统一调度 | 🟢 几乎空白 | ROS, M4, 车队管理, 众包 | ✅ **核心蓝海**：机器人+人类统一调度 |

### Tent OS 的差异化壁垒

1. **统一调度层**：唯一同时调度机器人（RealMan/FlashEx）和人类（众包/员工）的系统
2. **去 AI 化内核**：不是"用 AI 管理一切"，而是"确定性规则+AI 辅助决策"
3. **物理世界原生**：从设计之初就考虑机器人的状态机、人类的响应时间、混合任务编排
4. **三层记忆+六层缓存**：比 Mem0/Zep 更精细的上下文管理，专为长会话设计
5. **审批+熔断+评估三重保险**：比单一治理工具更完整的安全体系

---

## 七、终极综合：Tent OS V2 应该是什么

基于以上全部研究，Tent OS V2 的愿景应该是：

> **"物理世界的操作系统 —— 一个确定性内核管理混合智能体（机器人+人类+AI），具备人类大脑级的记忆和治理能力。"**

### 核心架构升级

```
┌─────────────────────────────────────────────────────────────┐
│                    TENT OS V2 架构                           │
├─────────────────────────────────────────────────────────────┤
│  感知层                                                      │
│  ├── 用户输入（API/消息/语音）                                │
│  ├── 机器人状态（位置/电量/任务进度）                         │
│  └── 人类执行者状态（在线/位置/技能）                         │
├─────────────────────────────────────────────────────────────┤
│  记忆层（海马体 2.0）                                        │
│  ├── L0 索引指针（Claude Code 模式）                         │
│  ├── L1 LLM 摘要（OpenViking 模式，保证可达）                 │
│  ├── L2 详情文件（按需加载）                                  │
│  ├── 时间维度（Zep 模式）                                    │
│  ├── 生命周期（Weibull 衰减）                                │
│  └── 自动捕获（Mem0 模式）                                   │
├─────────────────────────────────────────────────────────────┤
│  治理层（前额叶 2.0）                                        │
│  ├── Planner（计划生成）                                     │
│  ├── Generator（执行调度）                                   │
│  ├── Evaluator（独立评估） ← Harness                          │
│  ├── 确定性策略执行 ← 微软 AGT                                │
│  └── 审批机制（人工+自动）                                    │
├─────────────────────────────────────────────────────────────┤
│  调度层（神经-肌肉 2.0）                                     │
│  ├── 三维决策（标准化×社交×危险）                             │
│  ├── 执行者状态机（VDA 5050 风格）                           │
│  ├── 混合任务编排（Saga 事务）                               │
│  ├── 熔断器（已有）                                          │
│  └── Kill Switch ← 微软 AGT                                  │
├─────────────────────────────────────────────────────────────┤
│  自主层（自主神经系统 2.0）                                  │
│  ├── Heartbeat（OpenClaw 模式）                              │
│  ├── Cron 精确调度                                           │
│  ├── 记忆整合（简化 KAIROS）                                 │
│  └── 程序记忆更新（LangMem 模式）                            │
├─────────────────────────────────────────────────────────────┤
│  安全层                                                      │
│  ├── 四层特权环 ← 微软 AGT                                   │
│  ├── 输入/输出/动作三层防护 ← Galileo                        │
│  ├── 身份认证（Ed25519）                                     │
│  └── 审计日志（已有）                                        │
└─────────────────────────────────────────────────────────────┘
```

### 关键差异化特性

| 特性 | 来源 | Tent OS 独特之处 |
|------|------|-----------------|
| 混合调度 | 自创 | 机器人+人类+AI，三维决策 |
| 确定性治理 | 微软 AGT | 策略执行 <0.1ms，不是概率性 |
| 渐进记忆 | OpenViking + 修复 | L0/L1 保证可达，L2 不自动注入 |
| 索引指针 | Claude Code | 轻量路由，按需加载 |
| 时间记忆 | Zep | SQLite 实现，无需 Neo4j |
| 程序记忆 | LangMem | 经验自动转化为行为规则 |
| Heartbeat | OpenClaw | 从被动到主动 |
| Evaluator | Harness | Plan/Execute/Evaluate 分离 |
