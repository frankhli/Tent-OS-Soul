/**
 * HomeSystem — 家园系统
 * 家的物理位置、视觉标识、磁吸吸附、召唤/回家动画
 */

export interface HomeState {
  // 家的位置（自由模式下的"家"）
  x: number;
  y: number;
  radius: number;      // 势力范围
  isVisible: boolean;  // 是否显示家标识
  glowIntensity: number;

  // 召唤/回家动画
  animPhase: 'idle' | 'summoning' | 'summoned' | 'returning' | 'returned';
  animTimer: number;
  animProgress: number;
}

export function createHomeState(x: number, y: number): HomeState {
  return {
    x, y,
    radius: 80,
    isVisible: true,
    glowIntensity: 0.3,
    animPhase: 'idle',
    animTimer: 0,
    animProgress: 0,
  };
}

/** 更新家的视觉状态 */
export function updateHome(home: HomeState, dt: number, avatarX: number, avatarY: number): void {
  home.animTimer += dt;

  //  glow 呼吸效果
  home.glowIntensity = 0.2 + Math.sin(home.animTimer * 1.5) * 0.1;

  // 召唤动画
  if (home.animPhase === 'summoning') {
    home.animProgress += dt * 3;
    if (home.animProgress >= 1) {
      home.animProgress = 1;
      home.animPhase = 'summoned';
    }
  }

  // 回家动画
  if (home.animPhase === 'returning') {
    home.animProgress += dt * 2;
    if (home.animProgress >= 1) {
      home.animProgress = 1;
      home.animPhase = 'returned';
    }
  }

  // 检查 Avatar 是否在家的势力范围内
  const dist = Math.hypot(avatarX - home.x, avatarY - home.y);
  if (dist < home.radius && home.animPhase === 'idle') {
    home.glowIntensity = 0.5 + Math.sin(home.animTimer * 5) * 0.2;
  }
}

/** 开始召唤动画 */
export function startSummon(home: HomeState): void {
  home.animPhase = 'summoning';
  home.animTimer = 0;
  home.animProgress = 0;
}

/** 开始回家动画 */
export function startReturn(home: HomeState): void {
  home.animPhase = 'returning';
  home.animTimer = 0;
  home.animProgress = 0;
}

/** 检查是否在家的势力范围内 */
export function isInHomeRange(home: HomeState, x: number, y: number): boolean {
  const dist = Math.hypot(x - home.x, y - home.y);
  return dist < home.radius;
}

/** 计算磁吸目标位置（家的中心） */
export function getHomeSnapTarget(home: HomeState): { x: number; y: number } {
  return { x: home.x, y: home.y };
}

/** 绘制家的视觉标识 */
export function drawHome(
  ctx: CanvasRenderingContext2D,
  home: HomeState,
  avatarInRange: boolean
) {
  if (!home.isVisible) return;

  ctx.save();

  const { x, y, radius, glowIntensity } = home;

  // 底座光晕
  const glowR = radius * (0.8 + glowIntensity * 0.4);
  const grad = ctx.createRadialGradient(x, y + 20, 5, x, y + 20, glowR);
  grad.addColorStop(0, `rgba(148, 163, 184, ${glowIntensity * 0.3})`);
  grad.addColorStop(0.5, `rgba(148, 163, 184, ${glowIntensity * 0.15})`);
  grad.addColorStop(1, 'rgba(148, 163, 184, 0)');
  ctx.fillStyle = grad;
  ctx.fillRect(x - glowR, y - glowR, glowR * 2, glowR * 2);

  // 小窝底座（半圆）
  ctx.beginPath();
  ctx.ellipse(x, y + 15, radius * 0.4, radius * 0.15, 0, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(148, 163, 184, ${0.15 + glowIntensity * 0.1})`;
  ctx.fill();
  ctx.strokeStyle = `rgba(148, 163, 184, ${0.2 + glowIntensity * 0.15})`;
  ctx.lineWidth = 1;
  ctx.stroke();

  // Avatar 在家范围内时，家发光提示
  if (avatarInRange) {
    ctx.beginPath();
    ctx.arc(x, y + 10, radius * 0.5, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(96, 165, 250, ${0.3 + Math.sin(home.animTimer * 4) * 0.2})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // 召唤动画效果
  if (home.animPhase === 'summoning') {
    const p = home.animProgress;
    const scale = 0.5 + p * 0.5;
    ctx.beginPath();
    ctx.arc(x, y + 10, radius * scale, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(96, 165, 250, ${1 - p})`;
    ctx.lineWidth = 2 * (1 - p);
    ctx.stroke();
  }

  ctx.restore();
}

/** 绘制召唤/回家动画特效 */
export function drawHomeTransition(
  ctx: CanvasRenderingContext2D,
  home: HomeState,
  _avatarX: number,
  _avatarY: number
) {
  if (home.animPhase === 'returning') {
    const p = home.animProgress;
    // Avatar 逐渐变小消失
    const alpha = 1 - p;
    ctx.globalAlpha = alpha;
  }
}

/** 获取家的动画状态描述 */
export function getHomeDescription(home: HomeState): string {
  switch (home.animPhase) {
    case 'summoning': return '正在出来...';
    case 'summoned': return '已出来';
    case 'returning': return '正在回家...';
    case 'returned': return '已到家';
    default: return '';
  }
}
