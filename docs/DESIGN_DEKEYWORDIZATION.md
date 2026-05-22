# 去关键词化设计方案 v1.0 —— 从"背字典"到"语义理解"

## 背景：为什么关键词是毒药

Tent OS 的设计愿景是 **"不限制用户表达，不用关键词匹配触发功能"**。但当前系统中仍有 4 个核心模块依赖静态关键词列表：

| 模块 | 关键词 | 影响 |
|------|--------|------|
| plan_executor | "先"/"步骤"/"分步" | 复杂任务不走 Plan 模式 |
| multi_persona | "工作"/"紧急"/"创意" | 人格系统被锁死 |
| skills/router | triggers 倒排索引 | "生成幻灯片"≠"做PPT" |
| emotion_detector | 情绪关键词映射 | 误检/漏检 |

**竞品对比**：
- OpenClaw: AGENTS.md + Channel 语义路由，零关键词依赖
- Harness: Knowledge Graph + HQL 语义查询
- Claude Code: 27 事件 Hook + LLM 全权决策

---

## 设计原则：化学反应式联动

不孤立修复单个模块，而是让修复后的模块之间形成**数据流动链**：

```
AutoClassifier(语义评估) 
    ↓ 输出: complexity_score + urgency_level + safety_level
    ↓
PlanExecutor(接收 complexity_score 替代关键词)
MultiPersona(接收 urgency_level + 图谱数据 替代关键词)
SkillRouter(接收语义相似度 替代关键词)
EmotionDetector(接收 LLM 情绪分析 替代关键词)
    ↓
所有结果 → CognitiveGraph 沉淀 → 越用越准
```

---

## 模块一：PlanExecutor —— 用 AutoClassifier 替代关键词 ✅ 已完成

### 当前问题（已修复）
```python
# BEFORE: 关键词匹配
keywords = ["先", "再", "步骤", "plan", "execute", "执行计划", "分步", "一步一步"]
return any(k in task.lower() for k in keywords) or len(task) > 300
```

### 修复后实现

**Step 1: AutoClassifier 扩展复杂度评估** ✅

```python
class AutoModeClassifier:
    async def evaluate_complexity(self, task, context=None) -> ComplexityResult:
        """评估任务复杂度 —— 替代 plan_executor 的关键词匹配"""
        # 1. 启发式预筛（零成本）—— 任务长度/动词密度/时序词密度
        heuristic = self._heuristic_complexity(task)
        if heuristic and heuristic.confidence > 0.85:
            return heuristic  # 零成本快速路径
        
        # 2. LLM 评估（复用 chat 方法，单次调用 ~2-3s）
        return await self._llm_complexity(task, context)
```

启发式指标（不依赖关键词字典）：
- **任务长度** > 500 字 → 复杂
- **动词密度** ≥ 4 个动作词 → 复杂（中文/英文通用）
- **时序连接词密度** ≥ 3 个 → 复杂（"先/再/然后"等统计密度）
- **简单判定**：< 20 字 + 无动词 → 简单（高置信度）
- **中间地带** → 返回 None，降级到 LLM

**Step 2: PlanExecutor 接收 complexity_score** ✅

```python
class PlanExecuteExecutor:
    async def needs_plan(self, task, tools, classifier=None) -> bool:
        """De-keywordization: 不再用关键词匹配"""
        # 方案 1: 有 classifier → 用 complexity_score（优先）
        if classifier:
            result = await classifier.evaluate_complexity(task)
            return result.is_complex and result.confidence > 0.7
        
        # 方案 2: 无 classifier → 启发式评估（零成本，仍不依赖关键词）
        return self._heuristic_needs_plan(task)
```

**Step 3: GovernanceWorker 联动** ✅

```python
# worker.py _on_memory_injected()
if await self.executor.needs_plan(
    last_user_msg, plan_tools, classifier=self.auto_classifier
):
    await self._handle_complex_task(...)
```

### 测试结果

| 测试场景 | 输入 | 结果 | 路径 |
|---------|------|------|------|
| 简单问候 | "你好" | is_complex=False, conf=0.90 | 启发式（零成本） |
| 单动作 | "列出当前目录" | is_complex=False, conf=0.90 | 启发式（零成本） |
| 时序依赖 | "先读取配置，然后修改端口，最后重启" | is_complex=True, conf=0.88 | 启发式（零成本） |
| 语义复杂（无关键词） | "整理桌面文件，图片移到相册，文档移到工作" | is_complex=True, score=0.65 | LLM（~24s） |
| PlanExecutor 集成 | "部署代码到生产环境并验证" | needs_plan=True | complexity_score |

**化学反应点**：AutoClassifier 一次 LLM 评估三重驱动 —— `safety_level`→LayeredSecurity、`complexity_score`→PlanExecutor、`urgency_level`→MultiPersona（待实现），成本不变，信息翻倍。

---

## 模块二：MultiPersona —— 用 CognitiveGraph + SoulEvolution 替代关键词

### 当前问题
```python
trigger_keywords={
    "work": ["工作", "project", "meeting"],
    "emergency": ["紧急", "urgent", "asap"],
    ...
}
```
用户说"帮我处理一个 deadline 很紧的事"→ 不包含"紧急"关键词 → 不触发 emergency 模式。

更严重的是：**SoulEvolution 的 dimensions 被 multi_persona 覆盖**（worker.py 1560-1563行）：
```python
detected_mode = self.multi_persona.detect_mode(user_query)
self.soul.dimensions = self.multi_persona.get_current_dimensions()  # 学习的人格被丢弃！
```

### 修复方案

**Step 1: 从 CognitiveGraph 推断用户偏好**

```python
class MultiPersonaManager:
    def detect_mode(self, user_input: str, 
                    user_id: str = "",
                    cognitive_graph = None,
                    emotion_state: Dict = None,
                    security_assessment: Dict = None) -> str:
        # 1. AutoClassifier 的 urgency 信号（最可靠）
        if security_assessment and security_assessment.get("safety_level") == "critical":
            return "emergency"
        
        # 2. 情绪状态推断
        if emotion_state:
            emotion = emotion_state.get("emotion", "neutral")
            if emotion in ("angry", "frustrated", "urgent"):
                return "emergency"
            if emotion == "happy":
                return "casual"
        
        # 3. CognitiveGraph 用户偏好（数据驱动）
        if cognitive_graph and user_id:
            user_model = UserModelBuilder(cognitive_graph).build(user_id)
            if user_model and user_model.preferences:
                # 从图谱中的 preference 节点推断
                return self._infer_from_preferences(user_model.preferences)
        
        # 4. SoulEvolution 学习的人格（长期演化）
        if self.soul:
            dimensions = self.soul.dimensions
            if dimensions.formality > 0.8:
                return "work"
            if dimensions.creativity > 0.8:
                return "creative"
        
        # 5. 回退：基于时间窗口（已有逻辑）
        return self._time_based_fallback()
```

**Step 2: SoulEvolution 不再被覆盖**

```python
# 修复 worker.py 1560-1563 行
detected_mode = self.multi_persona.detect_mode(
    user_query,
    user_id=user_id,
    cognitive_graph=self.cognitive_graph,
    emotion_state=emotion_state,
    security_assessment=security_assessment,
)
# 不再覆盖 soul.dimensions，而是让 soul 演化自然生效
# multi_persona 只提供"当前场景建议"，soul 提供"长期人格底色"
self.soul.record_interaction(detected_mode, user_query)  # 记录交互用于演化
```

**化学反应点**：AutoClassifier(safety) + EmotionDetector(emotion) + CognitiveGraph(preferences) + SoulEvolution(dimensions) 四个模块的数据汇聚到 MultiPersona，形成**人格推断的共识机制**。

---

## 模块三：SkillRouter —— 用 Embedding 语义匹配替代关键词倒排

### 当前问题
```python
def _index_skill(self, skill):
    # 从 triggers 提取关键词
    for trigger in skill.triggers:
        for token in self._tokenize(trigger):
            self._index[token].add(skill.name)
```
"生成幻灯片"和"做PPT"在关键词空间中完全不相关。

### 修复方案

**Step 1: Skill 描述语义向量化**

```python
class SkillRouter:
    def __init__(self, skills_dir: str, embedding_model=None):
        self.skills = self._load_skills(skills_dir)
        self.embedding_model = embedding_model
        self._skill_embeddings: Dict[str, List[float]] = {}
        
        if embedding_model:
            self._precompute_skill_embeddings()
    
    def _precompute_skill_embeddings(self):
        """预计算所有 skill 的描述 embedding"""
        for skill in self.skills:
            # 用 name + description + triggers + prompt 的拼接做语义表示
            text = f"{skill.name}\n{skill.description}\n{' '.join(skill.triggers)}\n{skill.prompt[:200]}"
            self._skill_embeddings[skill.name] = self.embedding_model(text)
```

**Step 2: 用户查询语义匹配**

```python
    def route_semantic(self, text: str, top_k: int = 2) -> List[Skill]:
        """语义路由：用 embedding 相似度替代关键词匹配"""
        if not self.embedding_model or not self._skill_embeddings:
            # 回退到关键词路由
            return self.route(text)
        
        query_embedding = self.embedding_model(text)
        
        similarities = []
        for skill_name, skill_emb in self._skill_embeddings.items():
            sim = self._cosine_similarity(query_embedding, skill_emb)
            similarities.append((skill_name, sim))
        
        similarities.sort(key=lambda x: -x[1])
        
        # 阈值过滤 + 返回 top-k
        results = []
        for name, sim in similarities[:top_k]:
            if sim > 0.5:  # 语义相似度阈值
                results.append(self._skill_map[name])
        return results
```

**Step 3: GovernanceWorker 中无缝切换**

```python
# _on_memory_injected 中
if self.skill_manager:
    # 优先语义路由，回退关键词路由
    skills = self.skill_manager.route_semantic(state.get("task", ""))
    if not skills:
        skills = self.skill_manager.route(state.get("task", ""))
```

**化学反应点**：SkillRouter 的语义匹配 + FileMemoryStore 的语义召回形成**双层语义检索**：skills 提供"能力匹配"，file memories 提供"上下文匹配"。

---

## 模块四：EmotionDetector —— 语义分析为主，关键词兜底

### 当前问题
```python
KEYWORD_MAP = {
    "angry": ["生气", "愤怒", "气死", "fuck", "damn"],
    "happy": ["开心", "高兴", "棒", "great", "awesome"],
    ...
}
```
用户说"我现在心情很差"→ 不包含关键词 → 检测为 neutral。

### 修复方案

**Step 1: LLM 轻量情绪分析（主路径）**

```python
class EmotionDetector:
    def __init__(self, llm=None):
        self.llm = llm
        self.keyword_detector = KeywordEmotionDetector()  # 现有逻辑保留
    
    async def detect(self, text: str, context: str = "") -> Dict:
        # 1. 先尝试 LLM 语义分析（更准确）
        if self.llm:
            try:
                return await self._llm_detect(text, context)
            except Exception:
                pass
        
        # 2. 回退：关键词检测（零成本）
        return self.keyword_detector.detect(text)
    
    async def _llm_detect(self, text: str, context: str = "") -> Dict:
        prompt = f"""分析以下文本的情绪状态，输出JSON：
文本: {text}
上下文: {context}
输出: {{"emotion": "angry|happy|sad|urgent|frustrated|confused|neutral", 
         "intensity": 0.0-1.0, "reasoning": "简要说明"}}"""
        
        response = await self.llm.chat([{"role": "user", "content": prompt}])
        return json.loads(response)
```

**Step 2: GovernanceWorker 中联动**

```python
# _handle_chat_message 中
emotion = self._detect_emotion(content)
# 如果情绪强度高，通知 MultiPersona 和 SoulEvolution
if emotion.get("intensity", 0) > 0.7:
    # emergency 模式自动触发
    if emotion["emotion"] in ("angry", "frustrated", "urgent"):
        if self.mode_manager:
            self.mode_manager.set_mode(session_id, "strict", ...)
```

**化学反应点**：EmotionDetector 的输出 → MultiPersona(人格切换) + PermissionMode(安全模式) + SoulEvolution(人格演化) 三模块联动。

---

## 实施优先级

### P0（影响最大，最快见效）
1. **PlanExecutor needs_plan()** —— 关键词匹配 → AutoClassifier 复杂度评估
   - 改动最小（扩展 AutoClassifier + 修改 PlanExecutor 参数）
   - 影响最大（所有复杂任务都经过这里）

### P1（用户体验）
2. **SkillRouter 语义路由** —— 关键词倒排 → Embedding 语义匹配
   - 需要预计算 skill embeddings
   - 影响 Skill 激活准确率

3. **MultiPersona 图谱推断** —— 关键词触发 → 数据驱动推断
   - 需要 CognitiveGraph 有数据才能工作
   - 新用户回退到时间窗口/默认模式

### P2（锦上添花）
4. **EmotionDetector LLM 路径** —— 关键词 → 语义分析
   - 每轮对话增加一次 LLM 调用（有成本）
   - 可以先用关键词，高置信度场景再调用 LLM

---

## 预期效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| "帮我做个PPT" | ❌ 不走 Plan 模式（没关键词） | ✅ AutoClassifier 评估复杂度 → 走 Plan |
| "生成幻灯片" | ❌ Skill 不匹配（没"PPT"关键词） | ✅ 语义相似度匹配 presentation skill |
| "有个 deadline 很紧的事" | ❌ 不触发 emergency 人格 | ✅ AutoClassifier urgency + 情绪检测 → emergency |
| "我现在心情很差" | ❌ 情绪 neutral（没关键词） | ✅ LLM 语义分析 → sad |
| "帮我整理项目结构" | ❌ 简单聊天处理 | ✅ 复杂度评估 → 多步骤 → Plan 模式 |

---

## 风险与回退

1. **LLM 调用成本增加**：AutoClassifier 一次调用同时评估 safety + complexity，不增加成本
2. **Embedding 计算开销**：Skill embedding 预计算一次，运行时只做余弦相似度（O(n)）
3. **新用户无图谱数据**：MultiPersona 回退到时间窗口 + 默认模式，不影响基础功能
4. **LLM 情绪分析延迟**：每轮 +50-100ms，可配置关闭

---

## 化学反应总结

修复后的数据流：

```
用户输入
    ↓
AutoClassifier ──→ safety_level + complexity_score + urgency_level
    │                    │                    │
    │                    ▼                    ▼
    │            PlanExecutor          MultiPersona
    │            (复杂度>阈值→Plan)     (urgency→emergency)
    │                    │                    │
    ▼                    ▼                    ▼
SkillRouter ←── Embedding 语义匹配 ────────┘
    │
    ▼
EmotionDetector ──→ 情绪状态 ──→ MultiPersona + PermissionMode + SoulEvolution
    │
    ▼
CognitiveGraph ←── 所有交互数据沉淀 ───→ 越用越准
```

**核心化学反应**：AutoClassifier 的一次 LLM 评估，同时驱动 Plan 模式决策 + 人格模式决策 + 安全模式决策——**一次调用，三重联动**。
