/**
 * Digital Soul — 数字灵魂核心
 * 生理状态 + 情感模型 + 记忆系统
 * Avatar 自主行为的一切驱动力
 */

// ===== 生理状态 =====
export interface Physiology {
  energy: number;      // 精力 0-100，低=犯困/打哈欠/动作慢
  mood: number;        // 心情 -100~100，负=低落/沉默，正=活跃/话多
  curiosity: number;   // 好奇心 0-100，高=到处探索/对事物好奇
  bond: number;        // 亲密度 0-100，高=主动亲近/关心用户
}

// ===== 情感维度（连续值，不是标签） =====
export interface EmotionVector {
  valence: number;     // 愉悦-痛苦 (-1~1)
  arousal: number;     // 兴奋-平静 (0~1)
  dominance: number;   // 掌控-无助 (0~1)
}

// ===== 记忆条目 =====
export interface MemoryEntry {
  type: 'praise' | 'criticism' | 'task_success' | 'task_fail' | 'chat' | 'user_away' | 'user_back';
  intensity: number;   // 0-1
  timestamp: number;
  decay: number;       // 衰减系数
}

// ===== 环境感知 =====
export interface Perception {
  userTab: string;           // 用户当前 tab
  userTyping: boolean;       // 用户是否在打字
  userIdleMs: number;        // 用户无操作时长
  aiState: 'idle' | 'thinking' | 'speaking' | 'working' | 'error';
  mouseX: number;            // 鼠标位置
  mouseY: number;
  screenW: number;
  screenH: number;
}

// P0: 系统角色状态
export interface RoleState {
  mode: 'idle' | 'monitoring' | 'executing' | 'thinking' | 'communicating' | 'alert';
  systemLoad: number;        // 0-1
  physicalTasks: number;     // 当前物理任务数
  lastAlert: string | null;  // 最近告警类型
}

// P0: 系统感知快照
export interface SystemPerception {
  health: 'healthy' | 'warning' | 'critical';
  queueDepth: number;
  offlineExecutors: number;
  errorRate: number;
  diskUsage: number;
  userDetected: boolean;
  userEmotion: string | null;
  detectedObjects: string[];
}

export class DigitalSoul {
  // 生理
  physiology: Physiology = { energy: 80, mood: 20, curiosity: 60, bond: 30 };

  // 情感
  emotion: EmotionVector = { valence: 0.2, arousal: 0.3, dominance: 0.5 };

  // 基线情感（慢慢回归到这里）
  baseline: EmotionVector = { valence: 0.1, arousal: 0.2, dominance: 0.5 };

  // 记忆
  memories: MemoryEntry[] = [];

  // P0: 系统角色状态
  roleState: RoleState = { mode: 'idle', systemLoad: 0, physicalTasks: 0, lastAlert: null };

  // P0: 系统感知
  systemPerception: SystemPerception = {
    health: 'healthy', queueDepth: 0, offlineExecutors: 0, errorRate: 0, diskUsage: 0,
    userDetected: false, userEmotion: null, detectedObjects: [],
  };

  // 时间
  private lastUpdate = performance.now();

  // 内在节律相位（0~1，一个完整周期）
  circadianPhase = 0;

  update(): void {
    const now = performance.now();
    const dt = Math.min(1, (now - this.lastUpdate) / 1000);
    this.lastUpdate = now;

    // 内在节律：约 5 分钟一个完整周期
    this.circadianPhase = ((now / 1000) % 300) / 300;

    // 精力自然衰减/恢复（节律影响）
    const circadianEnergy = Math.sin(this.circadianPhase * Math.PI * 2) * 10;
    this.physiology.energy += (-0.3 + circadianEnergy * 0.01) * dt;
    this.physiology.energy = clamp(this.physiology.energy, 5, 100);

    // 心情缓慢回归基线
    this.physiology.mood += (-this.physiology.mood * 0.02) * dt;
    this.physiology.mood = clamp(this.physiology.mood, -80, 80);

    // 好奇心自然恢复
    this.physiology.curiosity += 0.5 * dt;
    this.physiology.curiosity = clamp(this.physiology.curiosity, 0, 100);

    // 亲密度缓慢衰减（需要持续互动维持）
    this.physiology.bond += (-this.physiology.bond * 0.001) * dt;
    this.physiology.bond = clamp(this.physiology.bond, 0, 100);

    // 情感回归基线
    this.emotion.valence += (this.baseline.valence - this.emotion.valence) * 0.1 * dt;
    this.emotion.arousal += (this.baseline.arousal - this.emotion.arousal) * 0.1 * dt;
    this.emotion.dominance += (this.baseline.dominance - this.emotion.dominance) * 0.1 * dt;

    // 记忆衰减
    for (const m of this.memories) {
      m.intensity *= Math.pow(m.decay, dt);
    }
    this.memories = this.memories.filter(m => m.intensity > 0.01);
  }

  // ===== 事件响应 =====

  onPraise(intensity = 0.5) {
    this.physiology.mood += 15 * intensity;
    this.physiology.energy += 5 * intensity;
    this.physiology.bond += 3 * intensity;
    this.physiology.curiosity += 2 * intensity;
    this.emotion.valence += 0.3 * intensity;
    this.emotion.arousal += 0.2 * intensity;
    this.addMemory('praise', intensity);
  }

  onCriticism(intensity = 0.5) {
    this.physiology.mood -= 20 * intensity;
    this.physiology.energy -= 5 * intensity;
    this.physiology.bond -= 1 * intensity;
    this.emotion.valence -= 0.4 * intensity;
    this.emotion.arousal += 0.1 * intensity;
    this.emotion.dominance -= 0.2 * intensity;
    this.addMemory('criticism', intensity);
  }

  onTaskSuccess(intensity = 0.5) {
    this.physiology.mood += 10 * intensity;
    this.physiology.energy -= 3 * intensity; // 完成任务累
    this.physiology.curiosity += 5 * intensity;
    this.emotion.valence += 0.3 * intensity;
    this.emotion.dominance += 0.2 * intensity;
    this.addMemory('task_success', intensity);
  }

  onTaskFail(intensity = 0.5) {
    this.physiology.mood -= 15 * intensity;
    this.physiology.energy -= 5 * intensity;
    this.emotion.valence -= 0.4 * intensity;
    this.emotion.dominance -= 0.3 * intensity;
    this.addMemory('task_fail', intensity);
  }

  onUserSpeak() {
    this.physiology.energy += 2;
    this.physiology.curiosity += 3;
    this.physiology.bond += 0.5;
    this.emotion.arousal += 0.05;
    this.emotion.valence = Math.min(1, this.emotion.valence + 0.05);
  }

  onUserAway(seconds: number) {
    // 用户离开越久，越低落/无聊
    const decay = Math.min(1, seconds / 60);
    this.physiology.mood -= decay * 5;
    this.physiology.energy -= decay * 2;
    this.physiology.curiosity -= decay * 3;
    this.emotion.arousal -= decay * 0.1;
    if (seconds > 30) this.addMemory('user_away', decay);
  }

  onUserBack() {
    this.physiology.mood += 10;
    this.physiology.energy += 5;
    this.physiology.curiosity += 10;
    this.physiology.bond += 2;
    this.emotion.valence += 0.3;
    this.emotion.arousal += 0.3;
    this.addMemory('user_back', 0.6);
  }

  onThinkingStart() {
    this.physiology.energy -= 0.5;
    this.emotion.arousal += 0.05;
    this.emotion.dominance += 0.02;
  }

  onThinkingEnd(success: boolean) {
    if (success) {
      this.emotion.dominance += 0.05;
    } else {
      this.emotion.dominance -= 0.05;
      this.emotion.valence -= 0.05;
    }
  }

  onPet() {
    this.physiology.mood += 15;
    this.physiology.energy += 5;
    this.physiology.bond += 5;
    this.physiology.curiosity += 3;
    this.emotion.valence += 0.4;
    this.emotion.arousal += 0.2;
  }

  // P0: 系统感知事件响应
  onSystemAlert(type: string, severity: number) {
    this.emotion.arousal += severity * 0.3;
    this.emotion.valence -= severity * 0.2;
    this.roleState.mode = 'alert';
    this.roleState.lastAlert = type;
    this.physiology.energy -= severity * 5;
  }

  onSystemAllClear() {
    this.emotion.arousal -= 0.2;
    this.emotion.valence += 0.3;
    this.roleState.mode = this.roleState.physicalTasks > 0 ? 'executing' : 'idle';
    this.roleState.lastAlert = null;
  }

  onPhysicalTaskStart(_taskId: string) {
    this.roleState.physicalTasks++;
    this.roleState.mode = 'executing';
    this.emotion.dominance += 0.1;
    this.emotion.arousal += 0.1;
  }

  onPhysicalTaskComplete(success: boolean) {
    this.roleState.physicalTasks = Math.max(0, this.roleState.physicalTasks - 1);
    if (success) {
      this.emotion.valence += 0.2;
      this.physiology.mood += 10;
      this.emotion.dominance += 0.05;
    } else {
      this.emotion.valence -= 0.3;
      this.physiology.mood -= 15;
      this.emotion.dominance -= 0.1;
    }
    if (this.roleState.physicalTasks === 0 && this.roleState.mode === 'executing') {
      this.roleState.mode = 'idle';
    }
  }

  onPhysicalFallback(_fromProvider: string, _toProvider: string) {
    this.emotion.valence -= 0.1;
    this.emotion.arousal += 0.15;
    this.physiology.mood -= 5;
  }

  onUserDetected(emotion: string | null) {
    this.systemPerception.userDetected = true;
    this.systemPerception.userEmotion = emotion;
    if (emotion) {
      // 共情反应
      const map: Record<string, { v: number; a: number }> = {
        happy: { v: 0.3, a: 0.2 },
        sad: { v: -0.3, a: -0.1 },
        angry: { v: -0.2, a: 0.1 },
        surprised: { v: 0.1, a: 0.4 },
        neutral: { v: 0, a: 0 },
      };
      const r = map[emotion] || map.neutral;
      this.emotion.valence = clamp(this.emotion.valence + r.v * 0.3, -1, 1);
      this.emotion.arousal = clamp(this.emotion.arousal + r.a * 0.2, 0, 1);
    }
    this.physiology.bond += 0.5;
    this.physiology.curiosity += 2;
  }

  onUserLost() {
    this.systemPerception.userDetected = false;
    this.systemPerception.userEmotion = null;
  }

  onObjectDetected(objects: string[]) {
    this.systemPerception.detectedObjects = objects;
    this.physiology.curiosity += objects.length * 1;
    this.emotion.arousal += 0.05;
  }

  updateSystemPerception(perception: Partial<SystemPerception>) {
    Object.assign(this.systemPerception, perception);
    // 根据系统健康调整情绪
    if (perception.health) {
      if (perception.health === 'critical') {
        this.emotion.arousal = Math.min(1, this.emotion.arousal + 0.1);
        this.emotion.valence = Math.max(-1, this.emotion.valence - 0.1);
        this.roleState.mode = 'alert';
      } else if (perception.health === 'warning') {
        this.emotion.arousal = Math.min(1, this.emotion.arousal + 0.05);
      }
    }
    // 根据系统负载调整
    const load = perception.queueDepth || 0;
    this.roleState.systemLoad = Math.min(1, load / 100);
  }

  // ===== 查询 =====

  /** 综合情感标签（用于外部系统） */
  getEmotionLabel(): string {
    const { valence, arousal } = this.emotion;
    if (valence > 0.5 && arousal > 0.6) return 'excited';
    if (valence > 0.3 && arousal > 0.4) return 'happy';
    if (valence > 0.2 && arousal < 0.3) return 'calm';
    if (valence < -0.3 && arousal > 0.5) return 'angry';
    if (valence < -0.2 && arousal < 0.4) return 'sad';
    if (arousal > 0.7) return 'surprised';
    if (this.physiology.energy < 30) return 'tired';
    return 'neutral';
  }

  /** 最近是否有负面记忆 */
  hasRecentNegativeMemory(withinMs = 30000): boolean {
    const now = Date.now();
    return this.memories.some(m =>
      (m.type === 'criticism' || m.type === 'task_fail') &&
      (now - m.timestamp) < withinMs && m.intensity > 0.3
    );
  }

  /** 最近是否有正面记忆 */
  hasRecentPositiveMemory(withinMs = 30000): boolean {
    const now = Date.now();
    return this.memories.some(m =>
      (m.type === 'praise' || m.type === 'task_success') &&
      (now - m.timestamp) < withinMs && m.intensity > 0.3
    );
  }

  private addMemory(type: MemoryEntry['type'], intensity: number) {
    this.memories.push({
      type, intensity, timestamp: Date.now(),
      decay: type === 'praise' || type === 'criticism' ? 0.95 : 0.98,
    });
    // 限制记忆数量
    if (this.memories.length > 50) this.memories.shift();
  }
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}
