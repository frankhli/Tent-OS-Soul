/**
 * BondSystem — 亲密度系统
 * 亲密度影响互动频率、距离偏好、表情丰富度、主动行为类型
 */

export interface BondState {
  level: number;        // 0-100
  label: string;        // 陌生人/熟悉/亲密/伴侣
  interactionFreq: number;  // 互动频率倍率
  preferredDistance: number; // 偏好的距离（px）
  expressionRichness: number; // 表情丰富度 0-1
  unlockedBehaviors: string[]; // 已解锁的行为
  lastInteraction: number;   // 上次互动时间戳
  interactionCount: number;  // 总互动次数
  nickname: string | null;   // 专属昵称
}

export function createBondState(): BondState {
  return {
    level: 10,
    label: '陌生人',
    interactionFreq: 0.3,
    preferredDistance: 120,
    expressionRichness: 0.3,
    unlockedBehaviors: ['report_task'],
    lastInteraction: 0,
    interactionCount: 0,
    nickname: null,
  };
}

/** 增加亲密度 */
export function addBond(state: BondState, amount: number, _reason: string): void {
  const oldLevel = state.level;
  state.level = Math.min(100, Math.max(0, state.level + amount));
  state.interactionCount++;
  state.lastInteraction = Date.now();

  // 等级变化时更新属性
  if (Math.floor(state.level / 10) !== Math.floor(oldLevel / 10)) {
    recalcBondState(state);
  }
}

/** 重新计算亲密度状态 */
export function recalcBondState(state: BondState): void {
  const level = state.level;

  if (level < 10) {
    state.label = '陌生人';
    state.interactionFreq = 0.2;
    state.preferredDistance = 150;
    state.expressionRichness = 0.2;
    state.unlockedBehaviors = ['report_task'];
  } else if (level < 30) {
    state.label = '认识';
    state.interactionFreq = 0.4;
    state.preferredDistance = 120;
    state.expressionRichness = 0.4;
    state.unlockedBehaviors = ['report_task', 'watch_mouse'];
  } else if (level < 60) {
    state.label = '熟悉';
    state.interactionFreq = 0.6;
    state.preferredDistance = 90;
    state.expressionRichness = 0.6;
    state.unlockedBehaviors = ['report_task', 'watch_mouse', 'wave_hello', 'bring_coffee'];
  } else if (level < 90) {
    state.label = '亲密';
    state.interactionFreq = 0.8;
    state.preferredDistance = 60;
    state.expressionRichness = 0.8;
    state.unlockedBehaviors = ['report_task', 'watch_mouse', 'wave_hello', 'bring_coffee', 'remind_rest', 'comfort_user'];
    if (!state.nickname) state.nickname = '小伙伴';
  } else {
    state.label = '伴侣';
    state.interactionFreq = 1.0;
    state.preferredDistance = 40;
    state.expressionRichness = 1.0;
    state.unlockedBehaviors = ['report_task', 'watch_mouse', 'wave_hello', 'bring_coffee', 'remind_rest', 'comfort_user', 'play_ball', 'celebrate'];
    if (!state.nickname) state.nickname = '亲爱的';
  }
}

/** 检查行为是否已解锁 */
export function isBehaviorUnlocked(state: BondState, behavior: string): boolean {
  return state.unlockedBehaviors.includes(behavior);
}

/** 亲密度自然衰减（长时间不互动） */
export function decayBond(state: BondState): void {
  const hoursSinceLastInteraction = (Date.now() - state.lastInteraction) / 3600000;
  if (hoursSinceLastInteraction > 24) {
    state.level = Math.max(0, state.level - 0.5);
    recalcBondState(state);
  }
}

/** 获取亲密度描述 */
export function getBondDescription(state: BondState): string {
  return `${state.label} (亲密度 ${Math.round(state.level)}/100)`;
}
