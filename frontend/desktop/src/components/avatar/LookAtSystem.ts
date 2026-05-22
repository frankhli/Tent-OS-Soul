/**
 * LookAtSystem — 注视链系统
 * 头先转 → 身体再转 → 最后启动移动
 * 让 Avatar 的行为更有生命感和目的性
 */

export interface LookAtState {
  // 头部朝向目标
  headTargetAngle: number;
  headCurrentAngle: number;
  headSpeed: number;

  // 身体朝向目标
  bodyTargetAngle: number;
  bodyCurrentAngle: number;
  bodySpeed: number;

  // 当前注视目标
  targetX: number;
  targetY: number;
  targetPriority: number;

  // 是否已完成注视链（可以移动）
  isAligned: boolean;
  alignmentProgress: number;
}

export function createLookAtState(): LookAtState {
  return {
    headTargetAngle: 0,
    headCurrentAngle: 0,
    headSpeed: 0,
    bodyTargetAngle: 0,
    bodyCurrentAngle: 0,
    bodySpeed: 0,
    targetX: 0,
    targetY: 0,
    targetPriority: 0,
    isAligned: false,
    alignmentProgress: 0,
  };
}

/** 设置注视目标 */
export function setLookTarget(
  state: LookAtState,
  x: number,
  y: number,
  avatarX: number,
  avatarY: number,
  priority: number = 1
): void {
  // 高优先级目标可以覆盖低优先级
  if (priority < state.targetPriority) return;

  state.targetX = x;
  state.targetY = y;
  state.targetPriority = priority;

  // 计算目标角度
  const dx = x - avatarX;
  const dy = y - avatarY;
  state.headTargetAngle = Math.atan2(dy, dx);
  state.bodyTargetAngle = Math.atan2(dy, dx);
}

/** 更新注视链 */
export function updateLookAt(
  state: LookAtState,
  dt: number,
  isMoving: boolean
): void {
  const HEAD_ALIGN_TIME = 0.2;  // 头部对齐用时
  const BODY_ALIGN_TIME = 0.4;  // 身体对齐用时
  const ALIGN_THRESHOLD = 0.15; // 弧度阈值（约 8.5 度）

  // 头部转向目标
  const headDiff = shortestAngleDiff(state.headCurrentAngle, state.headTargetAngle);
  state.headCurrentAngle += headDiff * Math.min(1, dt / HEAD_ALIGN_TIME);

  // 身体跟随头部（有延迟）
  const bodyDiff = shortestAngleDiff(state.bodyCurrentAngle, state.headCurrentAngle);
  state.bodyCurrentAngle += bodyDiff * Math.min(1, dt / BODY_ALIGN_TIME);

  // 对齐进度
  const headAligned = Math.abs(headDiff) < ALIGN_THRESHOLD;
  const bodyAligned = Math.abs(bodyDiff) < ALIGN_THRESHOLD;

  if (headAligned && bodyAligned) {
    state.alignmentProgress = Math.min(1, state.alignmentProgress + dt * 3);
  } else {
    state.alignmentProgress = Math.max(0, state.alignmentProgress - dt * 2);
  }

  // 当对齐进度 > 0.8 且正在移动时，认为已完成注视链
  state.isAligned = state.alignmentProgress > 0.8 && isMoving;

  // 目标优先级衰减
  state.targetPriority *= 0.999;
}

/** 获取骨骼旋转偏移（用于驱动骨骼系统） */
export function getBoneRotations(state: LookAtState): {
  headRot: number;
  torsoRot: number;
} {
  return {
    headRot: state.headCurrentAngle * 0.3,
    torsoRot: state.bodyCurrentAngle * 0.15,
  };
}

/** 环顾行为（到达后左右看） */
export function lookAround(
  state: LookAtState,
  _dt: number,
  baseAngle: number
): boolean {
  const cycle = (performance.now() / 1000) % 3;
  if (cycle < 0.5) {
    state.headTargetAngle = baseAngle - 0.4;
  } else if (cycle < 1.0) {
    state.headTargetAngle = baseAngle + 0.4;
  } else if (cycle < 1.5) {
    state.headTargetAngle = baseAngle;
  } else {
    return true; // 环顾完成
  }
  return false;
}

/** 最短角度差（处理 -PI ~ PI 环绕） */
function shortestAngleDiff(current: number, target: number): number {
  let diff = target - current;
  while (diff > Math.PI) diff -= Math.PI * 2;
  while (diff < -Math.PI) diff += Math.PI * 2;
  return diff;
}

/** 获取注视目标描述 */
export function getLookTargetDescription(state: LookAtState): string {
  if (state.targetPriority < 0.1) return '漫无目的';
  const angle = state.headTargetAngle;
  if (Math.abs(angle) < 0.3) return '看向右方';
  if (Math.abs(angle - Math.PI) < 0.3 || Math.abs(angle + Math.PI) < 0.3) return '看向左方';
  if (angle > 0) return '看向右下方';
  return '看向左下方';
}
