/**
 * MiniViewRenderer — AI 的家的独立渲染器
 * 完全不依赖 renderWorld()，只加载必要的渲染模块
 */

import type { WorldState } from '../WorldTypes';
import type { WorldRenderEffects } from './WorldRenderEffects';
import { worldToScreen } from '../WorldState';
import { worldAvatarRenderer } from '../WorldAvatarRenderer';
import { renderRoom } from './Room';
import { renderFurniture } from './Furniture';

const PHASE_BG: Record<string, string> = {
  morning: '#fefce8',
  afternoon: '#fff7ed',
  evening: '#fdf2f8',
  night: '#1e1b4b',
};

/**
 * 极简渲染：只画当前房间 + 家具 + Avatar
 * 不画：其他房间、过道、社区、粒子、UI 层、完整特效
 */
export function renderMiniWorld(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  viewportW: number,
  viewportH: number,
  time: number,
  effects?: WorldRenderEffects,
): void {
  const { camera, avatar, rooms, timeOfDay } = state;
  const fx = effects || {};

  // 简化背景（纯色，根据时间变化）
  ctx.fillStyle = PHASE_BG[timeOfDay] || PHASE_BG.morning;
  ctx.fillRect(0, 0, viewportW, viewportH);

  // 只画当前房间
  const room = rooms.find(r => r.id === avatar.roomId);
  if (room && room.unlocked) {
    renderRoom(ctx, room, camera, true, time);

    // 只画当前房间的家具
    for (const furniture of room.furniture) {
      renderFurniture(ctx, furniture, room, camera, false, time, fx.environment, fx.currentActivity);
    }
  }

  // Avatar（使用完整 Avatar 渲染器）
  worldAvatarRenderer.render(ctx, avatar, camera);

  // 极简思考光环（如果 AI 在思考）
  if (fx.isThinking) {
    const as = worldToScreen(avatar.position.x, avatar.position.y, camera);
    ctx.strokeStyle = 'rgba(167,139,250,0.3)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(as.x, as.y, 18 + Math.sin(time * 3) * 3, 0, Math.PI * 2);
    ctx.stroke();
  }
}
