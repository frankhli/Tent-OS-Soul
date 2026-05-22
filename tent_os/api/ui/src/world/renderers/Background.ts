import type { Room, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';

export function renderWorldBackground(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  timeOfDay: string
): void {
  const gradients: Record<string, [string, string]> = {
    morning: ['#FFF8F0', '#F5EDE0'],
    afternoon: ['#F0F5FF', '#E8F0F5'],
    evening: ['#F5F0EB', '#EDE6DE'],
    night: ['#1a1f2e', '#0f1419'],
  };
  const [from, to] = gradients[timeOfDay] || gradients.afternoon;

  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, from);
  grad.addColorStop(1, to);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // 微妙的网格线（比原来更淡更细）
  ctx.strokeStyle = timeOfDay === 'night' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)';
  ctx.lineWidth = 0.5;
  const gridSize = 80;
  for (let x = 0; x < w; x += gridSize) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y < h; y += gridSize) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }
}

// ===== Layer 1: 过道连接 =====

export function renderCorridors(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  camera: Camera
): void {
  const unlocked = rooms.filter(r => r.unlocked);
  if (unlocked.length < 2) return;

  ctx.save();
  for (let i = 0; i < unlocked.length; i++) {
    for (let j = i + 1; j < unlocked.length; j++) {
      const a = unlocked[i];
      const b = unlocked[j];
      // 只连接相邻房间（距离小于阈值）
      const acx = a.bounds.x + a.bounds.w / 2;
      const acy = a.bounds.y + a.bounds.h / 2;
      const bcx = b.bounds.x + b.bounds.w / 2;
      const bcy = b.bounds.y + b.bounds.h / 2;
      const dist = Math.sqrt((acx - bcx) ** 2 + (acy - bcy) ** 2);
      if (dist > 600) continue;

      const sa = worldToScreen(acx, acy, camera);
      const sb = worldToScreen(bcx, bcy, camera);

      // 地毯路径
      ctx.strokeStyle = 'rgba(180,160,130,0.25)';
      ctx.lineWidth = 24 * camera.zoom;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
      ctx.stroke();

      // 路径边缘阴影
      ctx.strokeStyle = 'rgba(0,0,0,0.04)';
      ctx.lineWidth = 26 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
      ctx.stroke();
    }
  }
  ctx.restore();
}

// ===== Layer 2-3: 房间渲染 =====

