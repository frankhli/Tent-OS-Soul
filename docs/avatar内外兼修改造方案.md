# Tent OS Avatar "内外兼修" 系统级改造方案

## 一、问题诊断：当前为什么"言行不统一"

### 1.1 截图揭示的核心矛盾

用户问 Tent OS "你知道你的形象吗"，Tent OS 回答：
> "我的核心身份是 **Tent OS（小腾）**，一个去AI化的智能操作系统内核，版本 2.0。"

**但同一时刻，右侧 avatar 在做什么？**
- 做俯卧撑、抛接球、打盹（ProactiveBehavior.ts）
- 无聊了在屏幕边缘散步（BehaviorTree.ts）
- 被点击时播放连击粒子特效（CanvasAvatar.tsx）

**这不是"操作系统内核"，这是一个桌面宠物。**

### 1.2 五大断裂点（代码级分析结果）

| 断裂点 | 后端（内在） | 前端（外在） | 后果 |
|-------|-----------|-----------|------|
| **身份断裂** | EmotionService 定义 8 种系统角色情绪：proud（任务完成自豪）、thinking（深入思考）、listening（认真聆听） | DigitalSoul + ProactiveBehavior 表现宠物行为：play_ball、do_pushups、take_nap | 用户感到"精神分裂" |
| **感知断裂** | SensoryLayer 监控队列深度、执行者离线、错误率、磁盘使用；VisualObservationEngine 检测物理世界异常；EmotionFusionEngine 融合文本+视觉+语音情绪 | Perception 只有：userTab、userTyping、userIdleMs、mouseX/Y | Avatar "瞎了"，感知不到系统真实状态 |
| **行动断裂** | PhysicalDeliveryExecutor 调度机器人/闪送/人工通知，有自动降级和熔断；EmbodiedPlanner 做路径规划和风险评估 | 动作只有：idle/walk/run/jump/dance/wave/sleep/sit/lie | 调度机器人时 avatar 毫无反应 |
| **决策断裂** | IntentionRegistry 管理 4 来源意图（heartbeat/event/user/system），有优先级算法和死锁检测 | BehaviorTree 条件极简：arousal>0.7、energy<25，大量 Math.random() | 决策依据不足，行为看起来"随机" |
| **记忆断裂** | CognitiveGraph + PlasticityEngine + ForgettingEngine，支持四阶段记忆巩固、矛盾检测、模式发现 | DigitalSoul.memories 只在内存中，页面刷新丢失 | Avatar "失忆"，每次对话都是重新开始 |

---

## 二、游戏公司让角色"有生命感"的核心范式

### 2.1 不是动画技术，是闭环逻辑

游戏角色有生命感的关键不是 Spine/Live2D/动作捕捉，而是 **感知→认知→决策→执行→反馈** 的完整闭环。

**《塞尔达传说：旷野之息》的 Bokoblin（波克布林）：**
1. **感知**：看到 Link（视觉）+ 听到脚步声（听觉）+ 闻到烤肉味（嗅觉）
2. **认知**："有敌人/有食物" → 威胁评估 vs 欲望评估
3. **决策**：如果饥饿度 > 恐惧度 → 去吃烤肉；否则 → 攻击 Link
4. **执行**：跑向烤肉（奔跑动画）或 举起武器（攻击动画）
5. **反馈**：吃到烤肉 → 满足 →  idle 变为悠闲；被打中 → 疼痛 → 逃跑动画

**每个动作都有明确的原因。** 玩家能"读懂"角色在想什么。

### 2.2 关键技术与 Tent OS 的对应

| 游戏技术 | 作用 | Tent OS 对应 |
|---------|------|-------------|
| **感知系统（Perception System）** | 角色"看到"世界 | SensoryLayer + VisualObservationEngine + EmotionFusionEngine ✅ 已有 |
| **认知系统（Cognition / Memory）** | 角色"理解"世界 | CognitiveGraph + PlasticityEngine ✅ 已有 |
| **决策系统（Behavior Tree / GOAP）** | 角色"决定"做什么 | IntentionRegistry + BehaviorTree ✅ 已有但不连通 |
| **动画状态机（Animation State Machine）** | 状态转换有明确条件 | Actions.ts 有基本状态机，但缺少**过渡条件** |
| **Blend Tree** | 多个因素同时影响表现 | 当前 emotion 只影响颜色，需要扩展到**系统负载、错误率、任务数** |
| **IK / LookAt** | 身体部位指向目标 | LookAtSystem 只影响头部，需要扩展到**手臂指向物理任务目标** |
| **Procedural Animation** | 环境驱动的程序化动画 | idle 微动作是时间驱动正弦波，需要改为**状态驱动** |

**核心结论：Tent OS 后端已经具备了"有生命感"的全部原材料，问题出在前后端没有连通，以及前端的动作系统没有表达"系统角色"。**

---

## 三、改造方案：三阶段实施

### 阶段一：感知融合层 —— 让 Avatar 真正"看到"

**目标**：把后端丰富的感知数据通过 WebSocket 实时推送到前端，扩展 SystemEventBridge。

#### 3.1.1 新增系统健康感知事件

后端 `SensoryLayer.check_system_health()` 生成的意图当前只写入 IntentionRegistry，不推送到前端。

**改造：**
- SensoryLayer 检测到异常时，通过 MessageBus 广播 `system.health_alert` 事件
- 前端 SystemEventBridge 订阅该事件，转换为 avatar 可理解的感知

```typescript
// SystemEventBridge.ts 新增事件类型
type SystemEvent = 
  | ... // 原有事件
  | { type: 'system_queue_overload'; depth: number }
  | { type: 'system_executor_offline'; count: number }
  | { type: 'system_error_spike'; rate: number }
  | { type: 'system_disk_full'; usage: number }
  | { type: 'system_all_clear' }; // 异常解除
```

**Avatar 反应映射：**
| 事件 | 情绪变化 | 动作变化 |
|-----|---------|---------|
| queue_overload | arousal ↑, dominance ↑ | 警觉扫描姿态，呼吸急促 |
| executor_offline | valence ↓, arousal ↑ | 皱眉，目光快速扫视 |
| error_spike | valence ↓, dominance ↓ | 紧张，身体微缩 |
| disk_full | valence ↓ | 焦虑踱步 |
| all_clear | valence ↑, arousal ↓ | 放松，深呼吸 |

#### 3.1.2 新增物理执行感知事件

后端 `PhysicalDeliveryExecutor` 当前只返回执行结果，不广播状态变化。

**改造：**
- PhysicalDeliveryExecutor 在任务状态变化时（assigned/executing/completed/failed/fallback）广播 `physical.status_change`
- 前端订阅并映射到 avatar 动作

```typescript
// 新增事件
type SystemEvent = 
  | ...
  | { type: 'physical_task_assigned'; taskId: string; provider: string }
  | { type: 'physical_task_executing'; taskId: string }
  | { type: 'physical_task_completed'; taskId: string }
  | { type: 'physical_fallback_triggered'; from: string; to: string }
  | { type: 'physical_circuit_open'; provider: string };
```

**Avatar 反应映射：**
| 事件 | 动作语义 |
|-----|---------|
| task_assigned | 伸出手臂，手指做"操作"动作（像在控制面板操作） |
| task_executing | 保持操作姿态，目光专注 |
| task_completed | 挺胸，点头，"确认"手势 |
| fallback_triggered | 短暂皱眉，摇头，重新伸出手臂 |
| circuit_open | 警觉，身体紧绷，"警告"手势 |

#### 3.1.3 视觉感知事件增强

后端 `EmotionService.update_by_vision()` 已有用户情绪检测，但前端 avatar 无法感知。

**改造：**
- EmotionService 检测到用户情绪变化时，不仅更新 AI 情绪，还广播 `vision.user_emotion_detected`
- VisualObservationEngine 检测到物体时广播 `vision.object_detected`

```typescript
// 新增事件
type SystemEvent = 
  | ...
  | { type: 'vision_user_detected'; confidence: number }
  | { type: 'vision_user_emotion'; emotion: string; confidence: number }
  | { type: 'vision_object_detected'; objects: string[] }
  | { type: 'vision_scene_changed'; scene: string };
```

**Avatar 反应映射：**
| 事件 | 动作语义 |
|-----|---------|
| user_detected | 转头注视摄像头方向，微笑 |
| user_emotion: happy | 共情微笑，身体微微前倾 |
| user_emotion: sad | 共情低头，温柔注视 |
| user_emotion: angry | 困惑歪头，安抚姿态 |
| object_detected | 好奇转头，"观察"姿态 |

#### 3.1.4 记忆感知事件

后端 `PlasticityEngine` 在记忆巩固时触发事件，但前端无法感知。

**改造：**
- PlasticityEngine 在 Light/Deep/REM 阶段广播 `memory.consolidation_phase`
- CognitiveGraph 检测到重要记忆时广播 `memory.significant_recall`

```typescript
// 新增事件
type SystemEvent = 
  | ...
  | { type: 'memory_light_processing' }
  | { type: 'memory_deep_consolidation' }
  | { type: 'memory_significant_recall'; topic: string }
  | { type: 'memory_contradiction_detected' };
```

**Avatar 反应映射：**
| 事件 | 动作语义 |
|-----|---------|
| memory_light_processing | 微微点头，"整理"手势 |
| memory_deep_consolidation | 闭眼，手托下巴，沉思 |
| memory_significant_recall | 眼神失焦（回忆远方），微微仰头 |
| memory_contradiction_detected | 困惑皱眉，歪头，"思考"手势 |

---

### 阶段二：统一意识模型 —— 前后端"灵魂"同步

**目标**：建立前后端共享的 DigitalSoul 状态，消除"两套情感模型"的问题。

#### 3.2.1 共享状态定义

当前前端 DigitalSoul 用 VAD (Valence-Arousal-Dominance)，后端 EmotionService 用离散情绪标签（happy/sad/excited等）。

**统一模型：**
```typescript
// 前后端共享的"灵魂状态"
interface UnifiedSoulState {
  // 核心情感（VAD 空间）
  emotion: { valence: number; arousal: number; dominance: number };
  
  // 系统角色状态（Tent OS 特有的）
  roleState: {
    mode: 'idle' | 'monitoring' | 'executing' | 'thinking' | 'communicating' | 'alert';
    systemLoad: number;      // 0-1，系统负载
    physicalTasks: number;   // 当前物理任务数
    lastAlert: string | null; // 最近告警类型
  };
  
  // 感知快照
  perception: {
    userDetected: boolean;
    userEmotion: string;
    detectedObjects: string[];
    systemHealth: 'healthy' | 'warning' | 'critical';
  };
  
  // 记忆摘要（定期同步，不是全量）
  memoryDigest: {
    recentTopics: string[];
    bondLevel: number;      // 亲密度（从后端认知图谱计算）
    familiarity: number;    // 熟悉度
  };
}
```

#### 3.2.2 同步机制

- **后端→前端**：EmotionService 情绪变化时通过 WebSocket 推送 `soul.state_update`
- **前端→后端**：DigitalSoul 的生理状态（energy/mood/curiosity/bond）每 30 秒上报一次
- **初始化**：前端加载时从后端拉取当前 soul 状态，避免"失忆"

#### 3.2.3 DigitalSoul 改造

```typescript
// DigitalSoul.ts 改造要点
class DigitalSoul {
  // 保留原有生理/情感模型
  physiology: Physiology;
  emotion: EmotionVector;
  
  // 新增：系统角色状态（从后端同步）
  roleState: RoleState;
  
  // 新增：感知快照（从后端同步）
  systemPerception: SystemPerception;
  
  // 事件响应扩展
  onSystemAlert(type: string, severity: number) {
    // 根据告警类型和严重程度调整情绪
    this.emotion.arousal += severity * 0.3;
    this.emotion.valence -= severity * 0.2;
    this.roleState.mode = 'alert';
  }
  
  onPhysicalTaskStart(taskId: string) {
    this.roleState.physicalTasks++;
    this.roleState.mode = 'executing';
    this.emotion.dominance += 0.1;
  }
  
  onPhysicalTaskComplete(success: boolean) {
    this.roleState.physicalTasks--;
    if (success) {
      this.emotion.valence += 0.2;
      this.physiology.mood += 10;
    } else {
      this.emotion.valence -= 0.3;
      this.physiology.mood -= 15;
    }
  }
  
  onUserDetected(emotion: string) {
    this.systemPerception.userDetected = true;
    this.systemPerception.userEmotion = emotion;
    // 共情反应
    const sympathy = this.computeSympathy(emotion);
    this.emotion.valence = sympathy.valence;
    this.emotion.arousal = sympathy.arousal;
  }
}
```

---

### 阶段三：意图-动作映射 —— 每个动作都有原因

**目标**：建立"系统意图 → 可视化动作"的映射，替换掉随机动画和宠物行为。

#### 3.3.1 新增"系统角色动作"

当前 Actions.ts 定义的动作：idle/walk/run/sleep/sit/lie/wave/jump/dance

**新增动作（反映 Tent OS 系统角色）：**
```typescript
type AvatarAction = 
  | 'idle' | 'walk' | 'run' | 'sleep' | 'sit' | 'lie' | 'wave' | 'jump' | 'dance'
  // 新增系统角色动作
  | 'monitor'      // 监控系统：目光扫视，身体微前倾
  | 'operate'      // 调度操作：伸出手臂，手指动作
  | 'think_deep'   // 深度思考：手托下巴，眼神失焦
  | 'recall'       // 回忆记忆：闭眼，微微仰头
  | 'alert'        // 警觉响应：身体紧绷，目光快速移动
  | 'scan'         // 扫描检测：头部转动，"观察"姿态
  | 'commune'      // 与用户交流：身体前倾，专注注视
  | 'report'       // 汇报状态：挺胸，"展示"手势
  | 'console'      // 控制台操作：双手在面前"操作"虚拟面板
  | 'reach_out';   // 伸出手：调度物理世界的手
```

#### 3.3.2 动作姿态定义

每个新增动作需要定义骨骼姿态：

```typescript
// Actions.ts 新增
function getSystemActionPose(action: string, time: number): Pose {
  switch (action) {
    case 'monitor':
      return {
        head: { rotation: Math.sin(time * 3) * 0.3 }, // 头部左右扫视
        torso: { rotation: Math.sin(time * 2) * 0.05 }, // 身体微转
        arm_L: { rotation: -0.5 }, // 左手自然下垂
        arm_R: { rotation: -0.5 },
        eyeOpen: 0.9, // 眼睛睁大（专注）
      };
    
    case 'operate':
      return {
        head: { rotation: -0.1 }, // 低头看"操作面板"
        arm_L: { rotation: -1.5 + Math.sin(time * 8) * 0.2 }, // 左手在面前操作
        arm_R: { rotation: -1.2 + Math.cos(time * 6) * 0.15 }, // 右手配合
        // 手指微动作（需要 PartDefs.ts 支持手指骨骼）
      };
    
    case 'think_deep':
      return {
        head: { rotation: 0.1 }, // 微微仰头
        arm_R: { rotation: -2.5 }, // 右手托下巴
        eyeOpen: 0.6, // 眼睛半闭（专注思考）
        browHeight: -0.2, // 眉毛微皱
      };
    
    case 'alert':
      return {
        head: { rotation: Math.sin(time * 6) * 0.4 }, // 快速扫视
        torso: { scaleY: 1.05 }, // 身体微紧绷
        arm_L: { rotation: -0.8 }, // 手臂微张开（准备行动）
        arm_R: { rotation: -0.8 },
        eyeOpen: 1.0, // 眼睛睁最大
      };
    
    case 'reach_out':
      return {
        head: { rotation: 0 }, // 直视前方
        arm_R: { rotation: -2.8, x: 20 }, // 右手伸出，指向目标
        // 手臂末端指向物理任务目标方向（需要 IK）
      };
    
    // ... 其他动作
  }
}
```

#### 3.3.3 行为树决策升级

当前 BehaviorTree 条件极简。升级为利用系统感知数据：

```typescript
function createAvatarBehaviorTree(): BTNode {
  return new Selector([
    // 优先级 1: 系统紧急告警
    new Sequence([
      new Condition(ctx => ctx.perception.systemHealth === 'critical'),
      new Action('alert', ctx => {
        ctx.soul.onSystemAlert('critical', 1.0);
        return 'running';
      }),
    ]),
    
    // 优先级 2: 物理任务执行中
    new Sequence([
      new Condition(ctx => ctx.soul.roleState.physicalTasks > 0),
      new Action('operate', ctx => {
        // 根据任务状态选择子动作
        if (ctx.soul.roleState.lastAlert === 'fallback') {
          ctx.currentAction = 'alert'; // 降级时警觉
        } else {
          ctx.currentAction = 'operate'; // 正常操作
        }
        return 'running';
      }),
    ]),
    
    // 优先级 3: 深度思考中（AI 正在处理复杂任务）
    new Sequence([
      new Condition(ctx => ctx.perception.aiState === 'thinking' && ctx.soul.roleState.systemLoad > 0.7),
      new Action('think_deep', () => 'running'),
    ]),
    
    // 优先级 4: 监控系统（空闲但有负载）
    new Sequence([
      new Condition(ctx => ctx.soul.roleState.systemLoad > 0.3),
      new Action('monitor', () => 'running'),
    ]),
    
    // 优先级 5: 用户交互
    new Sequence([
      new Condition(ctx => ctx.perception.userDetected),
      new Selector([
        new Sequence([
          new Condition(ctx => ctx.perception.userEmotion === 'sad'),
          new Action('commune', ctx => {
            // 温柔注视，身体前倾
            return 'running';
          }),
        ]),
        new Action('commune', () => 'running'),
      ]),
    ]),
    
    // 优先级 6: 记忆回忆
    new Sequence([
      new Condition(ctx => ctx.soul.memoryDigest.recentTopics.length > 0 && Math.random() < 0.01),
      new Action('recall', () => 'running'),
    ]),
    
    // 默认: 待机（系统空闲）
    new Action('idle', () => 'running'),
  ]);
}
```

#### 3.3.4 主动行为重塑（替换宠物行为）

当前 ProactiveBehavior：play_ball、do_pushups、wander_edge、take_nap

**替换为系统角色相关的主动行为：**

```typescript
export type ProactiveAction =
  // 删除：'play_ball' | 'do_pushups' | 'wander_edge' | 'take_nap'
  
  // 新增系统角色主动行为
  | 'system_scan'        // 系统扫描：目光扫视，检查状态
  | 'sensor_check'       // 传感器检查："倾听"姿态
  | 'memory_organize'    // 记忆整理：沉思姿态
  | 'predictive_check'   // 预测性检查：提前发现潜在问题
  | 'self_diagnostic'    // 自检：身体微动作检查自身
  | 'learn_observation'  // 观察学习：好奇注视环境中的变化
  | 'optimize_idle'      // 空闲优化：微调自身参数
  | 'report_status'      // 主动汇报：向用户汇报系统状态
  | 'suggest_help';      // 主动提供帮助

// 触发条件也改为系统相关
function updateProactive(state, dt, params) {
  // 系统负载低时 → 执行自检/优化
  if (params.systemLoad < 0.2 && params.energy > 50) {
    return trigger(state, 'self_diagnostic', 3);
  }
  
  // 长时间空闲 → 主动汇报状态或提供帮助
  if (params.userIdleMs > 60000 && params.bond > 40) {
    return trigger(state, 'report_status', 2);
  }
  
  // 检测到用户频繁操作某功能 → 主动提供帮助
  if (params.userPattern === 'struggling') {
    return trigger(state, 'suggest_help', 2);
  }
  
  // 深夜低负载 → 记忆整理（类似 REM）
  if (params.isNight && params.systemLoad < 0.1) {
    return trigger(state, 'memory_organize', 5);
  }
}
```

---

### 阶段四：动画系统升级 —— 融入游戏公司做法

#### 3.4.1 Blend Tree：多因素混合影响

当前 emotion 只影响颜色和基础姿态。需要建立 Blend Tree，让多个因素同时影响 avatar 表现。

```typescript
// 定义"动画参数"（类似 Unity Animator Parameters）
interface AnimationParameters {
  // 情感参数
  valence: number;    // -1 ~ 1
  arousal: number;    // 0 ~ 1
  dominance: number;  // 0 ~ 1
  
  // 系统参数
  systemLoad: number;      // 0 ~ 1，系统负载
  errorLevel: number;      // 0 ~ 1，错误率
  taskUrgency: number;     // 0 ~ 1，任务紧急度
  
  // 感知参数
  userDistance: number;    // 0 ~ 1，用户距离（视觉）
  userEngagement: number;  // 0 ~ 1，用户参与度
}

// Blend Tree：计算最终姿态
function computeBlendedPose(params: AnimationParameters, time: number): Pose {
  // 基础 idle 姿态
  const idlePose = getIdlePose(time);
  
  // 系统负载影响：高负载 → 呼吸急促，动作紧绷
  const loadPose = getLoadPose(params.systemLoad, time);
  
  // 错误率影响：高错误 → 焦虑微动作
  const errorPose = getErrorPose(params.errorLevel, time);
  
  // 任务紧急度影响：高紧急 → 快速、精准的动作
  const urgencyPose = getUrgencyPose(params.taskUrgency, time);
  
  // 情感影响
  const emotionPose = getEmotionPose(params.valence, params.arousal, time);
  
  // 混合（加权平均）
  return blendPoses([
    { pose: idlePose, weight: 1 },
    { pose: loadPose, weight: params.systemLoad * 0.5 },
    { pose: errorPose, weight: params.errorLevel * 0.7 },
    { pose: urgencyPose, weight: params.taskUrgency * 0.6 },
    { pose: emotionPose, weight: Math.abs(params.valence) * 0.5 + params.arousal * 0.3 },
  ]);
}
```

#### 3.4.2 状态驱动的 Procedural Animation

当前 idle 微动作是时间驱动的正弦波。改为状态驱动：

```typescript
// 当前（问题）：随机的正弦波
function idleMicroAction(time: number): PosePatch {
  const cycle = (time * 0.3) % 7;
  if (cycle < 1) return { head: { rotation: Math.sin(time*2)*0.15 } }; // 张望
  // ... 随机循环
}

// 改造后：基于系统状态的程序化动画
function getStateDrivenIdle(time: number, soul: DigitalSoul): PosePatch {
  switch (soul.roleState.mode) {
    case 'monitoring':
      // 监控模式 idle：目光周期性扫视，偶尔点头
      return {
        head: { rotation: Math.sin(time * 2) * 0.25 },
        eyeLOpen: 0.9 + Math.sin(time * 3) * 0.05,
        eyeROpen: 0.9 + Math.sin(time * 3 + 0.5) * 0.05,
      };
    
    case 'alert':
      // 警觉模式 idle：身体微紧绷，目光快速扫视
      return {
        head: { rotation: Math.sin(time * 5) * 0.3 },
        torso: { scaleY: 1.02 + Math.sin(time * 4) * 0.01 },
        arm_L: { rotation: -0.7 + Math.sin(time * 3) * 0.1 },
        arm_R: { rotation: -0.7 + Math.cos(time * 3) * 0.1 },
      };
    
    case 'thinking':
      // 思考模式 idle：手托下巴，眼神偶尔移动
      return {
        head: { rotation: Math.sin(time * 0.5) * 0.1 },
        arm_R: { rotation: -2.5 + Math.sin(time * 1) * 0.05 },
        eyeLOpen: 0.6 + Math.sin(time * 0.8) * 0.05,
        eyeROpen: 0.6 + Math.sin(time * 0.8 + 0.3) * 0.05,
      };
    
    default:
      // 普通 idle：轻微呼吸，偶尔张望
      return {
        torso: { scaleY: 1 + Math.sin(time * 1.5) * 0.02 },
        head: { rotation: Math.sin(time * 0.8) * 0.05 },
      };
  }
}
```

#### 3.4.3 简单 IK：手臂指向物理任务目标

当前 LookAtSystem 只影响头部。新增手臂 IK：

```typescript
// LookAtSystem.ts 扩展
interface LookAtTarget {
  x: number;
  y: number;
  type: 'mouse' | 'user_face' | 'physical_task' | 'system_alert';
}

function computeIK(target: LookAtTarget, skeleton: Skeleton): void {
  // 头部 LookAt（已有）
  const headRot = computeHeadLookAt(target);
  skeleton.setLocal('head', { rotation: headRot });
  
  // 新增：手臂 IK（当 type === 'physical_task'）
  if (target.type === 'physical_task') {
    const armAngle = computeArmAngle(
      skeleton.getWorld('shoulder_R'),
      target
    );
    skeleton.setLocal('arm_R', { rotation: armAngle });
    
    // 前臂微调（如果有前臂骨骼）
    const forearmAngle = computeForearmAngle(
      skeleton.getWorld('elbow_R'),
      target
    );
    skeleton.setLocal('forearm_R', { rotation: forearmAngle });
  }
}
```

---

## 四、实施优先级建议

### 4.1 推荐实施顺序

| 优先级 | 阶段 | 工作量 | 效果 |
|-------|------|-------|------|
| **P0** | 阶段一：感知融合层 | 中等 | **立即可见** — avatar 能响应系统事件，"活"起来 |
| **P1** | 阶段三：意图-动作映射（新增系统角色动作 + 替换宠物行为） | 中等 | **身份对齐** — 消除"言行不一" |
| **P2** | 阶段二：统一意识模型 | 较大 | **深度体验** — 前后端灵魂同步，跨会话记忆 |
| **P3** | 阶段四：动画系统升级（Blend Tree + IK） | 较大 | **质感提升** — 动作更自然、更丰富 |

### 4.2 P0 阶段详细任务清单

**后端改造（约 2-3 小时）：**
1. `SensoryLayer`：检测到异常时广播 `system.health_alert`
2. `PhysicalDeliveryExecutor`：任务状态变化时广播 `physical.status_change`
3. `EmotionService`：用户情绪检测时广播 `vision.user_emotion_detected`
4. `APIServer`：新增 WebSocket 事件类型，转发到前端

**前端改造（约 3-4 小时）：**
1. `SystemEventBridge.ts`：扩展 SystemEvent 类型，新增事件解析
2. `DigitalSoul.ts`：新增系统感知接口（onSystemAlert/onPhysicalTask/onUserDetected）
3. `BehaviorTree.ts`：升级决策条件，利用系统感知数据
4. `ProactiveBehavior.ts`：替换宠物行为为系统角色行为
5. `CanvasAvatar.tsx`：props 接收 systemState，驱动场景切换

---

## 五、关键设计原则

1. **动作即意图的可视化**：avatar 的每个动作都必须能追溯到系统状态变化，禁止无原因的"卖萌"
2. **感知→反应的延迟**：真实生物有感知处理延迟，avatar 也应该有（100-300ms），不是即时响应
3. **情绪惯性**：情绪变化不应瞬间完成，需要过渡时间（0.5-2秒）
4. **优先级打断**：高优先级事件（系统告警）可以立即打断低优先级动作（idle），但需要有"被打断"的视觉反馈（身体微震、快速转头）
5. **记忆连续性**：每次交互后 DigitalSoul 状态应持久化，下次打开页面时 avatar 应"记得"上次的状态

---

*方案完成。等待用户确认后实施。*
