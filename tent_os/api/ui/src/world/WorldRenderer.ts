/**
 * WorldRenderer v3 — 模块化 2D 世界 Canvas 渲染引擎
 * 物理拆分为 renderers/ 子模块，本文件为组合层（barrel）
 */

import type { WorldState } from './WorldTypes';
import type { WorldRenderEffects } from './renderers/WorldRenderEffects';
import { worldAvatarRenderer } from './WorldAvatarRenderer';
import { worldParticles } from './renderers/Particles';
export { worldParticles };
import { renderWorldBackground, renderCorridors } from './renderers/Background';
import { renderRoom, renderLockedRoom } from './renderers/Room';
import { renderFurniture, renderArtifact, renderVisualMemoryProp, renderProp, renderUserDecoration } from './renderers/Furniture';
import { renderPathPreview, renderAlertVignette, renderThinkingAura, renderUserPresenceGlow, renderLevelUpFlash, renderRoomUnlockFlash, renderEmotionEffects } from './renderers/Effects';
import { renderCommunityZone } from './renderers/Community';
import { renderWorldUI } from './renderers/UI';

// Re-export 公共 API（兼容旧代码）
export type { WorldRenderEffects } from './renderers/WorldRenderEffects';
export { renderMapView } from './renderers/Map';
export { renderBuildingInterior } from './renderers/BuildingInterior';
export { renderCognitiveLabels, _renderDreamBubbles, _renderCollectible, _renderThinkingMap, _renderSpatialMemory } from './renderers/Decorations';

/**
 * 渲染静态层（Layer 0-7）：背景、过道、房间、家具、藏品、道具、锁定覆盖层
 * 这些层变化频率低，适合缓存到 offscreen canvas
 */
export function renderWorldStaticLayers(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  viewportW: number,
  viewportH: number,
  time = 0,
  effects?: WorldRenderEffects,
): void {
  const { camera, rooms, timeOfDay } = state;
  const fx = effects || {};

  ctx.clearRect(0, 0, viewportW, viewportH);

  // Layer 0: 世界背景
  renderWorldBackground(ctx, viewportW, viewportH, timeOfDay);

  // Layer 1: 过道连接
  renderCorridors(ctx, rooms, camera);

  // Layer 2-3: 房间地板和墙壁
  for (const room of rooms) {
    if (!room.unlocked) continue;
    renderRoom(ctx, room, camera, state.selectedRoomId === room.id, time);
  }

  // Layer 4: 家具
  for (const room of rooms) {
    if (!room.unlocked) continue;
    for (const furniture of room.furniture) {
      if (furniture.type !== 'rug') {
        renderFurniture(ctx, furniture, room, camera, state.hoveredFurnitureId === furniture.id, time, fx.environment, fx.currentActivity);
      }
    }
  }

  // Layer 5: 地毯
  for (const room of rooms) {
    if (!room.unlocked) continue;
    for (const furniture of room.furniture) {
      if (furniture.type === 'rug') {
        renderFurniture(ctx, furniture, room, camera, false, time, fx.environment, fx.currentActivity);
      }
    }
  }

  // Layer 6: 智慧藏品
  for (const room of rooms) {
    if (!room.unlocked) continue;
    for (const artifact of room.artifacts) {
      renderArtifact(ctx, artifact, room, camera, state.hoveredArtifactId === artifact.id, time);
    }
  }

  // Layer 6.5: 可交互道具
  if (state.props) {
    for (const prop of state.props) {
      const room = rooms.find(r => r.id === prop.roomId);
      if (room && room.unlocked) {
        renderProp(ctx, prop, room, camera, state.hoveredPropId === prop.id, time);
      }
    }
  }

  // Layer 6.6: 用户改造
  if (fx.userDecorations && fx.userDecorations.length > 0) {
    for (const dec of fx.userDecorations) {
      const room = rooms.find(r => r.id === dec.roomId);
      if (room && room.unlocked) {
        renderUserDecoration(ctx, dec, room, camera, time);
      }
    }
  }

  // Layer 6.7: 视觉记忆映射的虚实道具
  if (state.visualMemoryProps && state.visualMemoryProps.length > 0) {
    for (const vmp of state.visualMemoryProps) {
      const room = rooms.find(r => r.id === vmp.roomId);
      if (room && room.unlocked) {
        renderVisualMemoryProp(ctx, vmp, room, camera, time);
      }
    }
  }

  // Layer 7: 锁定房间覆盖层
  for (const room of rooms) {
    if (room.unlocked) continue;
    renderLockedRoom(ctx, room, camera, time);
  }
}

/**
 * 渲染完整世界（静态层 + 动态层）
 * @param skipStaticLayers 为 true 时跳过 Layer 0-7（用于 offscreen 缓存场景）
 */
export function renderWorld(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  viewportW: number,
  viewportH: number,
  time = 0,
  path?: import('./WorldTypes').Point[],
  effects?: WorldRenderEffects,
  avatarState?: string,
  skipStaticLayers = false,
): void {
  const { camera, avatar, rooms } = state;
  const fx = effects || {};

  // 绘制静态层
  if (!skipStaticLayers) {
    renderWorldStaticLayers(ctx, state, viewportW, viewportH, time, effects);
  }

  // Layer 8: Avatar
  worldAvatarRenderer.render(ctx, avatar, camera, avatarState);

  // Layer 8.5: 路径预览
  if (path && path.length > 1) {
    renderPathPreview(ctx, path, camera, time);
  }

  // Layer 8.8: 情绪-世界联动特效
  if (fx.alertSeverity === 'critical' || fx.alertSeverity === 'high') {
    renderAlertVignette(ctx, viewportW, viewportH, time);
  }
  if (fx.isThinking) {
    renderThinkingAura(ctx, avatar, camera, time);
  }
  if (fx.userDetected) {
    renderUserPresenceGlow(ctx, rooms, camera, time);
  }
  if (fx.levelUpFlash && fx.levelUpFlash > 0.01) {
    renderLevelUpFlash(ctx, avatar, camera, fx.levelUpFlash);
  }
  if (fx.roomUnlockFlash && fx.roomUnlockFlash.intensity > 0.01) {
    renderRoomUnlockFlash(ctx, rooms, camera, fx.roomUnlockFlash);
  }
  if (fx.emotion) {
    renderEmotionEffects(ctx, avatar, camera, time, fx.emotion);
  }

  // Layer 9: 粒子
  worldParticles.render(ctx, camera);

  // Layer 10.5: 社区层
  renderCommunityZone(ctx, state, camera, time);

  // Layer 11: UI 覆盖层
  renderWorldUI(ctx, state, viewportW, viewportH, time);
}
