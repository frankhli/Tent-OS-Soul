import type { Room, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';
import { roundRect, shadeColor } from './Utils';

export function renderRoom(
  ctx: CanvasRenderingContext2D,
  room: Room,
  camera: Camera,
  isSelected: boolean,
  _time: number
): void {
  const s = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const sw = room.bounds.w * camera.zoom;
  const sh = room.bounds.h * camera.zoom;
  const r = 16 * camera.zoom;
  const wallThick = 8 * camera.zoom;

  ctx.save();

  // 房间整体投影（让房间"浮"在背景上）
  ctx.shadowColor = 'rgba(0,0,0,0.12)';
  ctx.shadowOffsetX = 4 * camera.zoom;
  ctx.shadowOffsetY = 6 * camera.zoom;
  ctx.shadowBlur = 20 * camera.zoom;

  // 墙壁厚度（顶部和左侧深色偏移）
  const wallColor = shadeColor(room.wallColor, -20);
  ctx.fillStyle = wallColor;
  roundRect(ctx, s.x - wallThick, s.y - wallThick, sw + wallThick, sh + wallThick, r + wallThick);
  ctx.fill();

  ctx.shadowColor = 'transparent';

  // 地板（主色）
  ctx.fillStyle = room.bgColor;
  roundRect(ctx, s.x, s.y, sw, sh, r);
  ctx.fill();

  // 地板纹理（subtle 网格）
  renderRoomFloorTexture(ctx, s.x, s.y, sw, sh, r, room.bgColor, camera);

  // 墙壁内阴影（顶部天花板遮挡）
  ctx.save();
  roundRect(ctx, s.x, s.y, sw, sh, r);
  ctx.clip();
  const shadowGrad = ctx.createLinearGradient(s.x, s.y, s.x, s.y + 30 * camera.zoom);
  shadowGrad.addColorStop(0, 'rgba(0,0,0,0.1)');
  shadowGrad.addColorStop(0.5, 'rgba(0,0,0,0.03)');
  shadowGrad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = shadowGrad;
  ctx.fillRect(s.x, s.y, sw, 30 * camera.zoom);

  // 左侧墙壁阴影
  const leftGrad = ctx.createLinearGradient(s.x, s.y, s.x + 20 * camera.zoom, s.y);
  leftGrad.addColorStop(0, 'rgba(0,0,0,0.06)');
  leftGrad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = leftGrad;
  ctx.fillRect(s.x, s.y, 20 * camera.zoom, sh);
  ctx.restore();

  // 边框（subtle）
  ctx.strokeStyle = 'rgba(0,0,0,0.04)';
  ctx.lineWidth = 1;
  roundRect(ctx, s.x, s.y, sw, sh, r);
  ctx.stroke();

  // 选中高亮（内部 glow）
  if (isSelected) {
    ctx.save();
    roundRect(ctx, s.x, s.y, sw, sh, r);
    ctx.clip();
    const glowGrad = ctx.createRadialGradient(
      s.x + sw / 2, s.y + sh / 2, 0,
      s.x + sw / 2, s.y + sh / 2, Math.max(sw, sh) * 0.6
    );
    glowGrad.addColorStop(0, 'rgba(13,148,136,0.06)');
    glowGrad.addColorStop(1, 'rgba(13,148,136,0)');
    ctx.fillStyle = glowGrad;
    ctx.fillRect(s.x, s.y, sw, sh);
    ctx.restore();

    // 选中边框
    ctx.strokeStyle = '#0D9488';
    ctx.lineWidth = 2.5 * camera.zoom;
    roundRect(ctx, s.x - 1, s.y - 1, sw + 2, sh + 2, r + 1);
    ctx.stroke();
  }

  // 房间名称标签（带背景）
  const labelY = s.y + 18 * camera.zoom;
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.font = `bold ${12 * camera.zoom}px Inter, sans-serif`;
  ctx.textAlign = 'left';
  ctx.fillText(room.nameZh, s.x + 14 * camera.zoom, labelY);

  // 描述（更小更淡）
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.font = `${9 * camera.zoom}px Inter, sans-serif`;
  ctx.fillText(room.description, s.x + 14 * camera.zoom, labelY + 14 * camera.zoom);

  ctx.restore();
}
export function renderLockedRoom(
  ctx: CanvasRenderingContext2D,
  room: Room,
  camera: Camera,
  time: number
): void {
  const s = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const sw = room.bounds.w * camera.zoom;
  const sh = room.bounds.h * camera.zoom;
  const r = 16 * camera.zoom;
  const cx = s.x + sw / 2;
  const cy = s.y + sh / 2;

  ctx.save();

  // 房间底色（灰暗版）
  ctx.fillStyle = 'rgba(220,220,225,0.4)';
  roundRect(ctx, s.x, s.y, sw, sh, r);
  ctx.fill();

  // 半透明深色遮罩
  ctx.fillStyle = 'rgba(30,30,45,0.55)';
  roundRect(ctx, s.x, s.y, sw, sh, r);
  ctx.fill();

  // 锁链装饰（四角到中央）
  ctx.strokeStyle = 'rgba(160,150,130,0.3)';
  ctx.lineWidth = 2 * camera.zoom;
  ctx.setLineDash([6 * camera.zoom, 4 * camera.zoom]);
  const chainOffset = 15 * camera.zoom;
  ctx.beginPath();
  ctx.moveTo(s.x + chainOffset, s.y + chainOffset);
  ctx.lineTo(cx - 10 * camera.zoom, cy - 10 * camera.zoom);
  ctx.moveTo(s.x + sw - chainOffset, s.y + chainOffset);
  ctx.lineTo(cx + 10 * camera.zoom, cy - 10 * camera.zoom);
  ctx.moveTo(s.x + chainOffset, s.y + sh - chainOffset);
  ctx.lineTo(cx - 10 * camera.zoom, cy + 10 * camera.zoom);
  ctx.moveTo(s.x + sw - chainOffset, s.y + sh - chainOffset);
  ctx.lineTo(cx + 10 * camera.zoom, cy + 10 * camera.zoom);
  ctx.stroke();
  ctx.setLineDash([]);

  // 中央大锁
  const lockSize = 36 * camera.zoom;
  const lockY = cy - lockSize * 0.2;

  // 锁体（金属渐变）
  const lockGrad = ctx.createLinearGradient(
    cx - lockSize * 0.4, lockY,
    cx + lockSize * 0.4, lockY + lockSize * 0.6
  );
  lockGrad.addColorStop(0, '#9CA3AF');
  lockGrad.addColorStop(0.5, '#6B7280');
  lockGrad.addColorStop(1, '#4B5563');
  ctx.fillStyle = lockGrad;
  roundRect(ctx, cx - lockSize * 0.4, lockY, lockSize * 0.8, lockSize * 0.6, 4 * camera.zoom);
  ctx.fill();
  // 锁体描边
  ctx.strokeStyle = '#D1D5DB';
  ctx.lineWidth = 1.5 * camera.zoom;
  roundRect(ctx, cx - lockSize * 0.4, lockY, lockSize * 0.8, lockSize * 0.6, 4 * camera.zoom);
  ctx.stroke();

  // 锁钩
  ctx.strokeStyle = '#9CA3AF';
  ctx.lineWidth = 4 * camera.zoom;
  ctx.beginPath();
  ctx.arc(cx, lockY, lockSize * 0.3, Math.PI, 0);
  ctx.stroke();

  // 钥匙孔
  ctx.fillStyle = '#1F2937';
  ctx.beginPath();
  ctx.arc(cx, lockY + lockSize * 0.25, 3 * camera.zoom, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillRect(cx - 1.5 * camera.zoom, lockY + lockSize * 0.25, 3 * camera.zoom, 5 * camera.zoom);

  // 锁周围微光粒子（缓慢旋转）
  const orbitR = lockSize * 0.8;
  for (let i = 0; i < 5; i++) {
    const angle = time * 0.5 + (i / 5) * Math.PI * 2;
    const px = cx + Math.cos(angle) * orbitR;
    const py = lockY + lockSize * 0.3 + Math.sin(angle) * orbitR * 0.5;
    const pulse = 0.4 + 0.3 * Math.sin(time * 2 + i);
    ctx.fillStyle = `rgba(255,215,100,${pulse})`;
    ctx.beginPath();
    ctx.arc(px, py, 2 * camera.zoom, 0, Math.PI * 2);
    ctx.fill();
  }

  // 房间名称
  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.font = `bold ${12 * camera.zoom}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(`🔒 ${room.nameZh}`, cx, lockY + lockSize * 1.1);

  // 解锁条件
  if (room.unlockCondition) {
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.font = `${9 * camera.zoom}px Inter, sans-serif`;
    const condText = getUnlockConditionText(room.unlockCondition);
    ctx.fillText(condText, cx, lockY + lockSize * 1.35);
  }

  ctx.restore();
}

export function getUnlockConditionText(cond: { type: string; threshold: number; category?: string }): string {
  switch (cond.type) {
    case 'task_count': return `完成 ${cond.threshold} 个任务解锁`;
    case 'task_category': return `完成 ${cond.threshold} 个${cond.category || ''}任务解锁`;
    case 'level': return `达到等级 ${cond.threshold} 解锁`;
    default: return '未知条件';
  }
}

// ===== Layer 9: Hover 特效 =====

// ===== Layer 10: UI 覆盖层 =====



export function renderRoomFloorTexture(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  w: number, h: number,
  r: number,
  baseColor: string,
  camera: Camera
): void {
  ctx.save();
  roundRect(ctx, x, y, w, h, r);
  ctx.clip();

  // Subtle 交叉线纹理
  const lineColor = shadeColor(baseColor, -8);
  ctx.strokeStyle = lineColor + '20'; // 12% opacity
  ctx.lineWidth = 0.5;
  const step = 40 * camera.zoom;

  for (let ix = x; ix < x + w; ix += step) {
    ctx.beginPath();
    ctx.moveTo(ix, y);
    ctx.lineTo(ix, y + h);
    ctx.stroke();
  }
  for (let iy = y; iy < y + h; iy += step) {
    ctx.beginPath();
    ctx.moveTo(x, iy);
    ctx.lineTo(x + w, iy);
    ctx.stroke();
  }

  ctx.restore();
}
