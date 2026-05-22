/**
 * IntentEngine — 意图驱动的移动系统
 * 三层架构：Intent → Plan → Execute
 * 告别随机漫游，每个移动都有明确目的
 */

export type MoveIntent =
  | 'idle'
  | 'goto_mouse'      // 去鼠标位置
  | 'goto_home'       // 回家
  | 'explore'         // 探索附近
  | 'rest'            // 找地方休息
  | 'follow_user'     // 跟随用户
  | 'flee'            // 逃离（害怕时）
  | 'approach_target'; // 接近某个目标点

export interface IntentState {
  intent: MoveIntent;
  targetX: number;
  targetY: number;
  intentStartTime: number;
  intentDuration: number;
  reason: string;
}

export interface MoveState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  facing: number;
  scale: number;
}

/** 意图优先级配置 */
const INTENT_PRIORITY: Record<MoveIntent, number> = {
  flee: 100,
  goto_home: 80,
  follow_user: 70,
  goto_mouse: 60,
  approach_target: 50,
  rest: 30,
  explore: 20,
  idle: 0,
};

/** 创建初始状态 */
export function createIntentState(x: number, y: number): IntentState & MoveState {
  return {
    x, y, vx: 0, vy: 0, facing: 1, scale: 1,
    intent: 'idle',
    targetX: x,
    targetY: y,
    intentStartTime: 0,
    intentDuration: 0,
    reason: '',
  };
}

/** 设置新意图 */
export function setIntent(
  state: IntentState & MoveState,
  intent: MoveIntent,
  targetX: number,
  targetY: number,
  reason: string,
  minDuration: number = 2
): boolean {
  // 已经是这个目标且足够近，不需要重新设置
  if (intent === state.intent) {
    const dist = Math.hypot(targetX - state.targetX, targetY - state.targetY);
    if (dist < 50) return false;
    state.targetX = targetX;
    state.targetY = targetY;
    return true;
  }

  // 高优先级意图可以打断低优先级
  const currentPriority = INTENT_PRIORITY[state.intent] || 0;
  const newPriority = INTENT_PRIORITY[intent] || 0;

  if (newPriority < currentPriority) {
    return false;
  }

  state.intent = intent;
  state.targetX = targetX;
  state.targetY = targetY;
  state.intentStartTime = performance.now();
  state.intentDuration = minDuration;
  state.reason = reason;
  return true;
}

/** 更新移动物理（ease-in-out 加速曲线） */
export function updateMove(
  state: IntentState & MoveState,
  dt: number,
  screenW: number,
  screenH: number,
  maxSpeed: number = 150,
  acceleration: number = 400,
  emotion: string = 'neutral'
): void {
  const dx = state.targetX - state.x;
  const dy = state.targetY - state.y;
  const dist = Math.sqrt(dx * dx + dy * dy);

  // 面向目标
  if (Math.abs(dx) > 1) {
    state.facing = dx > 0 ? 1 : -1;
  }

  if (state.intent === 'idle' || state.intent === 'rest') {
    // 减速到停止
    state.vx *= 0.85;
    state.vy *= 0.85;
    if (Math.abs(state.vx) < 0.5) state.vx = 0;
    if (Math.abs(state.vy) < 0.5) state.vy = 0;
    state.scale = 1;
    return;
  }

  // 到达检测
  if (dist < 10) {
    state.vx *= 0.9;
    state.vy *= 0.9;
    if (dist < 3) {
      state.intent = 'idle';
      state.vx = 0;
      state.vy = 0;
    }
    return;
  }

  // 方向归一化
  const dirX = dx / dist;
  const dirY = dy / dist;

  // 减速距离（提前减速）
  const decelDist = 60;
  const speedFactor = dist < decelDist ? dist / decelDist : 1;

  // 情绪影响速度
  const emotionSpeed = getEmotionSpeedMultiplier(emotion);
  const targetSpeed = maxSpeed * speedFactor * emotionSpeed;

  // 加速到目标速度（ease-in-out）
  const ax = (dirX * targetSpeed - state.vx) * acceleration * dt;
  const ay = (dirY * targetSpeed - state.vy) * acceleration * dt;
  state.vx += ax * dt;
  state.vy += ay * dt;

  // 速度限制
  const speed = Math.sqrt(state.vx * state.vx + state.vy * state.vy);
  if (speed > targetSpeed) {
    state.vx = (state.vx / speed) * targetSpeed;
    state.vy = (state.vy / speed) * targetSpeed;
  }

  // 应用速度
  state.x += state.vx * dt;
  state.y += state.vy * dt;

  // 屏幕边缘软边界（减速而不是硬撞）
  const margin = 40;
  if (state.x < margin) {
    state.vx += (margin - state.x) * 2;
    state.facing = 1;
  }
  if (state.x > screenW - margin) {
    state.vx -= (state.x - (screenW - margin)) * 2;
    state.facing = -1;
  }
  if (state.y < margin) {
    state.vy += (margin - state.y) * 2;
  }
  if (state.y > screenH - margin) {
    state.vy -= (state.y - (screenH - margin)) * 2;
  }

  // 边缘缩放效果（远小近大）
  const edgeDist = Math.min(state.x, screenW - state.x, state.y, screenH - state.y);
  state.scale = 0.9 + Math.min(1, edgeDist / 200) * 0.1;
}

/** 情绪速度倍率 */
function getEmotionSpeedMultiplier(emotion: string): number {
  switch (emotion) {
    case 'excited': return 1.5;
    case 'happy': return 1.2;
    case 'angry': return 1.3;
    case 'surprised': return 1.4;
    case 'sad': return 0.6;
    case 'tired': return 0.4;
    case 'thinking': return 0.3;
    default: return 1.0;
  }
}

/** 获取当前移动状态描述 */
export function getMoveDescription(state: IntentState & MoveState): string {
  const dx = state.targetX - state.x;
  const dy = state.targetY - state.y;
  const dist = Math.sqrt(dx * dx + dy * dy);

  if (state.intent === 'idle') return '站立中';
  if (state.intent === 'rest') return '休息中';
  if (dist < 10) return '已到达';

  // 方向判断（保留用于调试）
  // const dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? '向右' : '向左') : (dy > 0 ? '向下' : '向上');

  const speed = Math.sqrt(state.vx * state.vx + state.vy * state.vy);
  const speedLabel = speed > 100 ? '快跑' : speed > 50 ? '走路' : '慢走';

  switch (state.intent) {
    case 'goto_mouse': return `${speedLabel}去鼠标方向`;
    case 'goto_home': return `${speedLabel}回家`;
    case 'explore': return `${speedLabel}探索`;
    case 'follow_user': return `${speedLabel}跟随用户`;
    case 'flee': return '快跑逃离';
    case 'approach_target': return `${speedLabel}接近目标`;
    default: return `${speedLabel}`;
  }
}
