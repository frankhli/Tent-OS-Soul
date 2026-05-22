import type { Room } from '../WorldTypes';
import type { WorldAvatarState, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';

export function renderPathPreview(
  ctx: CanvasRenderingContext2D,
  path: import('../WorldTypes').Point[],
  camera: Camera,
  time: number
): void {
  if (path.length < 2) return;

  ctx.save();

  // 虚线路径
  ctx.strokeStyle = '#0D9488';
  ctx.lineWidth = 2 * camera.zoom;
  ctx.setLineDash([8 * camera.zoom, 6 * camera.zoom]);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // 路径发光
  ctx.shadowColor = 'rgba(13,148,136,0.4)';
  ctx.shadowBlur = 8 * camera.zoom;

  ctx.beginPath();
  const start = worldToScreen(path[0].x, path[0].y, camera);
  ctx.moveTo(start.x, start.y);
  for (let i = 1; i < path.length; i++) {
    const p = worldToScreen(path[i].x, path[i].y, camera);
    ctx.lineTo(p.x, p.y);
  }
  ctx.stroke();

  ctx.shadowBlur = 0;
  ctx.setLineDash([]);

  // 目标点脉冲光环
  const target = path[path.length - 1];
  const ts = worldToScreen(target.x, target.y, camera);
  const pulseR = (6 + 3 * Math.sin(time * 4)) * camera.zoom;

  ctx.fillStyle = 'rgba(13,148,136,0.2)';
  ctx.beginPath();
  ctx.arc(ts.x, ts.y, pulseR, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = '#0D9488';
  ctx.lineWidth = 2 * camera.zoom;
  ctx.beginPath();
  ctx.arc(ts.x, ts.y, 4 * camera.zoom, 0, Math.PI * 2);
  ctx.stroke();

  // 流动箭头（沿路径）
  const arrowOffset = (time * 30) % 40;
  for (let i = 0; i < path.length - 1; i++) {
    const a = worldToScreen(path[i].x, path[i].y, camera);
    const b = worldToScreen(path[i + 1].x, path[i + 1].y, camera);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 20 * camera.zoom) continue;

    const segCount = Math.floor(dist / 40);
    for (let j = 0; j < segCount; j++) {
      const t = (j * 40 + arrowOffset) / dist;
      if (t > 1) continue;
      const ax = a.x + dx * t;
      const ay = a.y + dy * t;
      const angle = Math.atan2(dy, dx);

      ctx.save();
      ctx.translate(ax, ay);
      ctx.rotate(angle);
      ctx.fillStyle = 'rgba(13,148,136,0.6)';
      ctx.beginPath();
      ctx.moveTo(4 * camera.zoom, 0);
      ctx.lineTo(-2 * camera.zoom, -2.5 * camera.zoom);
      ctx.lineTo(-2 * camera.zoom, 2.5 * camera.zoom);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
  }

  ctx.restore();
}

// ===== 情绪-世界联动特效 =====

export function renderAlertVignette(
  ctx: CanvasRenderingContext2D,
  w: number, h: number,
  time: number
): void {
  const pulse = 0.15 + 0.1 * Math.sin(time * 6);
  const grad = ctx.createRadialGradient(w / 2, h / 2, h * 0.3, w / 2, h / 2, h * 0.8);
  grad.addColorStop(0, 'transparent');
  grad.addColorStop(1, `rgba(220,50,50,${pulse})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}

export function renderThinkingAura(
  ctx: CanvasRenderingContext2D,
  avatar: import('../WorldTypes').WorldAvatarState,
  camera: Camera,
  time: number
): void {
  const s = worldToScreen(avatar.position.x, avatar.position.y, camera);
  const r = 80 * camera.zoom;
  const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r);
  grad.addColorStop(0, 'rgba(150,100,255,0.15)');
  grad.addColorStop(0.5, 'rgba(150,100,255,0.05)');
  grad.addColorStop(1, 'transparent');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
  ctx.fill();

  // 思考粒子（小圆点环绕）
  for (let i = 0; i < 3; i++) {
    const angle = time * 1.5 + (i / 3) * Math.PI * 2;
    const px = s.x + Math.cos(angle) * r * 0.5;
    const py = s.y + Math.sin(angle) * r * 0.3;
    ctx.fillStyle = `rgba(180,150,255,${0.4 + 0.3 * Math.sin(time * 3 + i)})`;
    ctx.beginPath();
    ctx.arc(px, py, 2.5 * camera.zoom, 0, Math.PI * 2);
    ctx.fill();
  }
}

export function renderUserPresenceGlow(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  camera: Camera,
  time: number
): void {
  const livingRoom = rooms.find(r => r.id === 'living_room' && r.unlocked);
  if (!livingRoom) return;

  // 在客厅沙发区域产生温暖光尘
  const sofa = livingRoom.furniture.find(f => f.type === 'sofa');
  if (!sofa) return;

  const roomScreen = worldToScreen(livingRoom.bounds.x, livingRoom.bounds.y, camera);
  const sx = roomScreen.x + (sofa.position.x + sofa.size.w / 2) * camera.zoom;
  const sy = roomScreen.y + (sofa.position.y + sofa.size.h / 2) * camera.zoom;

  const r = 60 * camera.zoom;
  const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, r);
  grad.addColorStop(0, 'rgba(255,200,100,0.12)');
  grad.addColorStop(1, 'transparent');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(sx, sy, r, 0, Math.PI * 2);
  ctx.fill();

  // 金色光尘粒子
  for (let i = 0; i < 4; i++) {
    const angle = time * 0.8 + (i / 4) * Math.PI * 2 + livingRoom.bounds.x;
    const px = sx + Math.cos(angle) * r * 0.6;
    const py = sy + Math.sin(angle) * r * 0.4 - 10 * camera.zoom;
    const pulse = 0.5 + 0.5 * Math.sin(time * 2 + i);
    ctx.fillStyle = `rgba(255,220,150,${pulse * 0.5})`;
    ctx.beginPath();
    ctx.arc(px, py, 1.5 * camera.zoom, 0, Math.PI * 2);
    ctx.fill();
  }
}

export function renderLevelUpFlash(
  ctx: CanvasRenderingContext2D,
  avatar: import('../WorldTypes').WorldAvatarState,
  camera: Camera,
  intensity: number
): void {
  const s = worldToScreen(avatar.position.x, avatar.position.y, camera);

  // 金色粒子爆发
  const particleCount = 20;
  for (let i = 0; i < particleCount; i++) {
    const angle = (i / particleCount) * Math.PI * 2;
    const dist = 30 + 80 * intensity;
    const px = s.x + Math.cos(angle) * dist;
    const py = s.y + Math.sin(angle) * dist - 20 * camera.zoom;
    const size = (2 + 3 * intensity) * camera.zoom;
    ctx.fillStyle = `rgba(255,215,50,${intensity * 0.8})`;
    ctx.beginPath();
    ctx.arc(px, py, size, 0, Math.PI * 2);
    ctx.fill();
  }

  // 光环
  ctx.strokeStyle = `rgba(255,215,50,${intensity * 0.5})`;
  ctx.lineWidth = 3 * camera.zoom;
  ctx.beginPath();
  ctx.arc(s.x, s.y - 20 * camera.zoom, 40 * camera.zoom * (1 + intensity), 0, Math.PI * 2);
  ctx.stroke();

  // 文字
  ctx.fillStyle = `rgba(255,215,50,${intensity})`;
  ctx.font = `bold ${16 * camera.zoom}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText('Level Up!', s.x, s.y - 60 * camera.zoom);
}

export function renderRoomUnlockFlash(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  camera: Camera,
  flash: { roomId: string; intensity: number }
): void {
  const room = rooms.find(r => r.id === flash.roomId);
  if (!room) return;

  const s = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const sw = room.bounds.w * camera.zoom;
  const sh = room.bounds.h * camera.zoom;
  const cx = s.x + sw / 2;
  const cy = s.y + sh / 2;
  const maxR = Math.max(sw, sh) * 0.8;

  // 光芒扩散
  const r = maxR * flash.intensity;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  grad.addColorStop(0, `rgba(255,255,255,${flash.intensity * 0.4})`);
  grad.addColorStop(0.5, `rgba(255,220,100,${flash.intensity * 0.2})`);
  grad.addColorStop(1, 'transparent');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();

  // 文字
  ctx.fillStyle = `rgba(255,255,255,${flash.intensity})`;
  ctx.font = `bold ${14 * camera.zoom}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(`新区域解锁：${room.nameZh}`, cx, cy);
}

// ===== Layer 8.8: 情绪外化特效 =====

export function renderEmotionEffects(
  ctx: CanvasRenderingContext2D,
  avatar: WorldAvatarState,
  camera: Camera,
  time: number,
  emotion: string
): void {
  const s = worldToScreen(avatar.position.x, avatar.position.y, camera);

  if (emotion === 'sad' || emotion === 'depressed') {
    // 低落：头顶灰色小雨滴
    ctx.save();
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = '#94a3b8';
    const dropCount = 3;
    for (let i = 0; i < dropCount; i++) {
      const dx = s.x + (i - 1) * 8 * camera.zoom;
      const dy = s.y - 35 * camera.zoom + Math.sin(time * 0.003 + i * 2) * 4 * camera.zoom;
      const dropLen = 3 * camera.zoom + Math.sin(time * 0.005 + i) * 1.5 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(dx, dy);
      ctx.lineTo(dx - 1 * camera.zoom, dy + dropLen);
      ctx.lineTo(dx + 1 * camera.zoom, dy + dropLen);
      ctx.fill();
    }
    ctx.restore();
  }

  if (emotion === 'excited' || emotion === 'happy' || emotion === 'celebrating') {
    // 兴奋：头顶彩带
    ctx.save();
    const colors = ['#f87171', '#fbbf24', '#34d399', '#60a5fa', '#a78bfa'];
    for (let i = 0; i < 5; i++) {
      const t = (time * 0.002 + i * 1.3) % 1; // 0-1 循环
      const startX = s.x + (Math.sin(i * 2.5) * 10 * camera.zoom);
      const startY = s.y - 30 * camera.zoom;
      const endX = startX + Math.sin(time * 0.003 + i * 3) * 20 * camera.zoom * t;
      const endY = startY - 15 * camera.zoom * t - 5 * camera.zoom * Math.sin(t * Math.PI);
      ctx.strokeStyle = colors[i % colors.length];
      ctx.lineWidth = 2 * camera.zoom;
      ctx.globalAlpha = 1 - t;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.quadraticCurveTo(
        startX + Math.sin(time * 0.004 + i) * 8 * camera.zoom,
        startY - 8 * camera.zoom,
        endX, endY
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  if (emotion === 'waiting' || emotion === 'bored') {
    // 等待：头顶时钟图标 + 叹气气泡
    ctx.save();
    ctx.globalAlpha = 0.5 + Math.sin(time * 0.003) * 0.2;
    const cx = s.x + 20 * camera.zoom;
    const cy = s.y - 38 * camera.zoom;
    const r = 5 * camera.zoom;
    // 时钟外圈
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1.2 * camera.zoom;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
    // 时钟指针
    const angle = (time * 0.001) % (Math.PI * 2);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle - Math.PI / 2) * r * 0.6, cy + Math.sin(angle - Math.PI / 2) * r * 0.6);
    ctx.stroke();
    // 叹气 "..."
    ctx.fillStyle = '#64748b';
    ctx.font = `${7 * camera.zoom}px sans-serif`;
    ctx.textAlign = 'center';
    const dotsAlpha = (Math.sin(time * 0.002) + 1) / 2;
    ctx.globalAlpha = dotsAlpha * 0.6;
    ctx.fillText('...', s.x - 18 * camera.zoom, cy - 2 * camera.zoom);
    ctx.restore();
  }
}

// ===== Layer 10.5: 社区层（AI 社会）=====

