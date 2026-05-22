import type { WorldState } from '../WorldTypes';
import { roundRect } from './Utils';

export function renderWorldUI(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  viewportW: number,
  _viewportH: number,
  _time: number
): void {
  const timeLabels: Record<string, string> = {
    morning: '🌅 早晨', afternoon: '☀️ 下午', evening: '🌆 傍晚', night: '🌙 深夜',
  };

  // 时间指示器（带背景 pill）
  const timeText = timeLabels[state.timeOfDay] || '';
  ctx.font = 'bold 12px Inter, sans-serif';
  const textW = ctx.measureText(timeText).width;
  const pillW = textW + 24;
  const pillH = 26;
  const pillX = viewportW - 16 - pillW;
  const pillY = 10;

  ctx.fillStyle = state.timeOfDay === 'night' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)';
  roundRect(ctx, pillX, pillY, pillW, pillH, 13);
  ctx.fill();

  ctx.fillStyle = state.timeOfDay === 'night' ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.4)';
  ctx.textAlign = 'right';
  ctx.fillText(timeText, viewportW - 28, 28);

  // 缩放指示器
  ctx.fillStyle = state.timeOfDay === 'night' ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)';
  ctx.font = '11px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(`${Math.round(state.camera.zoom * 100)}%`, 16, 28);


}

// ===== 工具函数 =====

