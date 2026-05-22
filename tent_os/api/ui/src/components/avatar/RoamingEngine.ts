/**
 * 屏幕漫游物理引擎
 * Avatar 在自由态时在屏幕上自主移动
 */

export interface RoamingState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
  facing: number; // 1 = 右, -1 = 左
  scale: number;  // 远近感（走到边缘时缩小）
}

export function createRoamingState(startX: number, startY: number): RoamingState {
  return {
    x: startX,
    y: startY,
    vx: 0,
    vy: 0,
    targetX: startX,
    targetY: startY,
    facing: 1,
    scale: 1,
  };
}

/** 更新漫游状态（每帧调用） */
export function updateRoaming(
  state: RoamingState,
  dt: number,
  screenW: number,
  screenH: number,
  speed = 1
): void {
  const margin = 220; // Avatar 尺寸 + 边距
  const accel = 400 * speed;
  const damping = 0.92;
  const arriveDist = 15;

  // 向目标点加速
  const dx = state.targetX - state.x;
  const dy = state.targetY - state.y;
  const dist = Math.sqrt(dx * dx + dy * dy);

  if (dist > arriveDist) {
    const nx = dx / dist;
    const ny = dy / dist;
    state.vx += nx * accel * dt;
    state.vy += ny * accel * dt;
    state.facing = nx > 0 ? 1 : -1;
  } else {
    // 到达目标，减速
    state.vx *= 0.8;
    state.vy *= 0.8;
  }

  // 阻尼
  state.vx *= damping;
  state.vy *= damping;

  // 速度上限
  const maxSpeed = 300 * speed;
  const spd = Math.sqrt(state.vx * state.vx + state.vy * state.vy);
  if (spd > maxSpeed) {
    state.vx = (state.vx / spd) * maxSpeed;
    state.vy = (state.vy / spd) * maxSpeed;
  }

  // 更新位置
  state.x += state.vx * dt;
  state.y += state.vy * dt;

  // 边界限制（软边界，允许部分超出）
  const minX = -50;
  const maxX = screenW - margin + 50;
  const minY = -30;
  const maxY = screenH - margin + 30;

  if (state.x < minX) { state.x = minX; state.vx *= -0.3; }
  if (state.x > maxX) { state.x = maxX; state.vx *= -0.3; }
  if (state.y < minY) { state.y = minY; state.vy *= -0.3; }
  if (state.y > maxY) { state.y = maxY; state.vy *= -0.3; }

  // 远近感：走到边缘时略微缩小
  const edgeDistX = Math.min(state.x, screenW - state.x - margin);
  const edgeDistY = Math.min(state.y, screenH - state.y - margin);
  const edgeDist = Math.min(edgeDistX, edgeDistY);
  state.scale = 0.85 + Math.min(1, edgeDist / 100) * 0.15;
}

/** 设置随机漫游目标 */
export function setRandomTarget(state: RoamingState, screenW: number, screenH: number): void {
  const margin = 220;
  state.targetX = 50 + Math.random() * (screenW - margin - 100);
  state.targetY = 50 + Math.random() * (screenH - margin - 100);
}

/** 设置目标为鼠标附近 */
export function setTargetToMouse(state: RoamingState, mx: number, my: number): void {
  state.targetX = mx - 100;
  state.targetY = my - 150;
}

/** 检查是否到达目标 */
export function hasArrived(state: RoamingState, threshold = 20): boolean {
  const dx = state.targetX - state.x;
  const dy = state.targetY - state.y;
  return Math.sqrt(dx * dx + dy * dy) < threshold;
}
