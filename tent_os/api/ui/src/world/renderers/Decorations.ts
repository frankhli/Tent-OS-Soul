import type { Room } from '../WorldTypes';
import type { WorldAvatarState, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';
import { roundRect } from './Utils';

// ===== Layer 8.9: 梦境思想泡泡 =====

const DREAM_KEYWORDS = [
  '记忆碎片', '知识图谱', '情感印记', '时空回溯',
  '任务轨迹', '对话回声', '认知节点', '灵感火花',
  '经验结晶', '模式识别', '联想跳跃', '潜意识',
];

export function _renderDreamBubbles(
  ctx: CanvasRenderingContext2D,
  avatar: WorldAvatarState,
  camera: Camera,
  time: number,
  currentActivity?: { type: string; target: string; progress: number } | null,
  dreamEntries?: string[],
): void {
  const pos = worldToScreen(avatar.position.x, avatar.position.y - 35, camera);
  const bubbleCount = 3;
  const entries = dreamEntries && dreamEntries.length > 0 ? dreamEntries : DREAM_KEYWORDS;

  for (let i = 0; i < bubbleCount; i++) {
    const phase = (time * 0.5 + i * 2.1) % 6; // 6 秒一个周期
    const floatY = Math.sin(phase * Math.PI / 3) * 20 * camera.zoom;
    const alpha = phase < 1 ? phase : (phase > 4 ? 5 - phase : 1); // 淡入淡出
    const bx = pos.x + (i - 1) * 45 * camera.zoom;
    const by = pos.y - 30 * camera.zoom - floatY;

    // 泡泡大小
    const bw = (50 + Math.sin(time + i) * 5) * camera.zoom;
    const bh = 22 * camera.zoom;

    ctx.save();
    ctx.globalAlpha = alpha * 0.85;

    // 泡泡背景
    ctx.fillStyle = 'rgba(230, 220, 255, 0.9)';
    roundRect(ctx, bx - bw / 2, by - bh / 2, bw, bh, bh / 2);
    ctx.fill();

    // 泡泡边框
    ctx.strokeStyle = 'rgba(180, 160, 220, 0.5)';
    ctx.lineWidth = 1 * camera.zoom;
    roundRect(ctx, bx - bw / 2, by - bh / 2, bw, bh, bh / 2);
    ctx.stroke();

    // 小尾巴
    ctx.fillStyle = 'rgba(230, 220, 255, 0.9)';
    ctx.beginPath();
    ctx.moveTo(bx - 4 * camera.zoom, by + bh / 2);
    ctx.lineTo(bx + 4 * camera.zoom, by + bh / 2);
    ctx.lineTo(bx, by + bh / 2 + 6 * camera.zoom);
    ctx.closePath();
    ctx.fill();

    // 文字
    ctx.fillStyle = 'rgba(100, 80, 150, 0.9)';
    ctx.font = `${7 * camera.zoom}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const keyword = currentActivity?.target
      ? currentActivity.target.slice(0, 6)
      : entries[Math.floor((time * 0.3 + i * 3.7) % entries.length)];
    ctx.fillText(keyword, bx, by);

    ctx.restore();
  }
}

// ===== 收集品渲染 =====

export function _renderCollectible(
  ctx: CanvasRenderingContext2D,
  obj: { name: string; visualForm: string; placedPosition: { x: number; y: number } },
  room: Room,
  camera: Camera,
  time: number,
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const cx = roomScreen.x + obj.placedPosition.x * camera.zoom;
  const cy = roomScreen.y + obj.placedPosition.y * camera.zoom;
  const size = 16 * camera.zoom;

  ctx.save();

  if (obj.visualForm === 'sticker') {
    // 墙上贴纸：轻微摆动
    const wobble = Math.sin(time * 2 + obj.placedPosition.x) * 0.05;
    ctx.translate(cx + size / 2, cy + size / 2);
    ctx.rotate(wobble);
    ctx.translate(-(cx + size / 2), -(cy + size / 2));

    // 贴纸背景
    ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
    roundRect(ctx, cx, cy, size, size, 3 * camera.zoom);
    ctx.fill();
    ctx.strokeStyle = 'rgba(200, 200, 200, 0.5)';
    ctx.lineWidth = 0.5 * camera.zoom;
    roundRect(ctx, cx, cy, size, size, 3 * camera.zoom);
    ctx.stroke();
  } else {
    // 桌面摆件：底座阴影
    ctx.shadowColor = 'rgba(0,0,0,0.15)';
    ctx.shadowOffsetY = 2 * camera.zoom;
    ctx.shadowBlur = 4 * camera.zoom;
  }

  // 根据物体名称绘制简笔画
  const name = obj.name.toLowerCase();
  if (name.includes('cat') || name.includes('猫')) {
    // 猫脸
    ctx.fillStyle = '#FFAB91';
    ctx.beginPath();
    ctx.arc(cx + size / 2, cy + size / 2, size * 0.35, 0, Math.PI * 2);
    ctx.fill();
    // 耳朵
    ctx.beginPath();
    ctx.moveTo(cx + size * 0.25, cy + size * 0.25);
    ctx.lineTo(cx + size * 0.2, cy + size * 0.1);
    ctx.lineTo(cx + size * 0.35, cy + size * 0.2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(cx + size * 0.75, cy + size * 0.25);
    ctx.lineTo(cx + size * 0.8, cy + size * 0.1);
    ctx.lineTo(cx + size * 0.65, cy + size * 0.2);
    ctx.fill();
    // 眼睛
    ctx.fillStyle = '#5D4037';
    ctx.beginPath();
    ctx.arc(cx + size * 0.4, cy + size * 0.45, size * 0.06, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + size * 0.6, cy + size * 0.45, size * 0.06, 0, Math.PI * 2);
    ctx.fill();
  } else if (name.includes('plant') || name.includes('flower') || name.includes('植物')) {
    // 小盆栽
    ctx.fillStyle = '#8D6E63';
    ctx.beginPath();
    ctx.ellipse(cx + size / 2, cy + size * 0.75, size * 0.25, size * 0.15, 0, 0, Math.PI * 2);
    ctx.fill();
    // 叶子
    ctx.fillStyle = '#66BB6A';
    for (let i = 0; i < 3; i++) {
      const angle = -Math.PI / 2 + (i - 1) * 0.6;
      ctx.beginPath();
      ctx.ellipse(
        cx + size / 2 + Math.cos(angle) * size * 0.15,
        cy + size * 0.5 + Math.sin(angle) * size * 0.2,
        size * 0.08, size * 0.2, angle, 0, Math.PI * 2
      );
      ctx.fill();
    }
  } else if (name.includes('coffee') || name.includes('cup') || name.includes('咖啡')) {
    // 咖啡杯
    ctx.fillStyle = '#D7CCC8';
    ctx.beginPath();
    ctx.arc(cx + size / 2, cy + size * 0.55, size * 0.25, 0, Math.PI, false);
    ctx.fill();
    ctx.fillRect(cx + size * 0.25, cy + size * 0.3, size * 0.5, size * 0.25);
    // 把手
    ctx.strokeStyle = '#D7CCC8';
    ctx.lineWidth = 2 * camera.zoom;
    ctx.beginPath();
    ctx.arc(cx + size * 0.75, cy + size * 0.45, size * 0.1, -Math.PI / 2, Math.PI / 2);
    ctx.stroke();
    // 热气
    ctx.strokeStyle = 'rgba(150, 150, 150, 0.4)';
    ctx.lineWidth = 1 * camera.zoom;
    for (let i = 0; i < 2; i++) {
      ctx.beginPath();
      ctx.moveTo(cx + size * (0.4 + i * 0.2), cy + size * 0.25);
      ctx.quadraticCurveTo(
        cx + size * (0.35 + i * 0.2), cy + size * 0.1,
        cx + size * (0.45 + i * 0.2), cy + size * 0.05
      );
      ctx.stroke();
    }
  } else if (name.includes('book') || name.includes('notebook') || name.includes('书') || name.includes('笔记')) {
    // 书本
    ctx.fillStyle = '#5C6BC0';
    ctx.fillRect(cx + size * 0.15, cy + size * 0.2, size * 0.7, size * 0.55);
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(cx + size * 0.2, cy + size * 0.25, size * 0.55, size * 0.45);
    // 书签
    ctx.fillStyle = '#FF5252';
    ctx.beginPath();
    ctx.moveTo(cx + size * 0.6, cy + size * 0.15);
    ctx.lineTo(cx + size * 0.65, cy + size * 0.3);
    ctx.lineTo(cx + size * 0.55, cy + size * 0.3);
    ctx.fill();
  } else if (name.includes('guitar') || name.includes('instrument') || name.includes('乐器') || name.includes('吉他')) {
    // 吉他
    ctx.fillStyle = '#D4A574';
    ctx.beginPath();
    ctx.ellipse(cx + size / 2, cy + size * 0.55, size * 0.18, size * 0.25, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillRect(cx + size * 0.47, cy + size * 0.15, size * 0.06, size * 0.4);
    // 音孔
    ctx.fillStyle = '#3E2723';
    ctx.beginPath();
    ctx.arc(cx + size / 2, cy + size * 0.55, size * 0.06, 0, Math.PI * 2);
    ctx.fill();
  } else if (name.includes('game') || name.includes('console') || name.includes('游戏') || name.includes('switch')) {
    // 游戏机
    ctx.fillStyle = '#E53935';
    ctx.fillRect(cx + size * 0.2, cy + size * 0.35, size * 0.6, size * 0.35);
    ctx.fillStyle = '#1A1A1A';
    ctx.fillRect(cx + size * 0.25, cy + size * 0.4, size * 0.5, size * 0.25);
    // 摇杆
    ctx.fillStyle = '#424242';
    ctx.beginPath();
    ctx.arc(cx + size * 0.35, cy + size * 0.52, size * 0.06, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + size * 0.65, cy + size * 0.52, size * 0.06, 0, Math.PI * 2);
    ctx.fill();
  } else if (name.includes('pillow') || name.includes('plush') || name.includes('玩偶') || name.includes('抱枕')) {
    // 抱枕/玩偶
    ctx.fillStyle = '#F48FB1';
    ctx.beginPath();
    ctx.roundRect(cx + size * 0.15, cy + size * 0.25, size * 0.7, size * 0.5, size * 0.15);
    ctx.fill();
    // 笑脸
    ctx.fillStyle = '#880E4F';
    ctx.beginPath();
    ctx.arc(cx + size * 0.38, cy + size * 0.45, size * 0.04, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + size * 0.62, cy + size * 0.45, size * 0.04, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + size * 0.5, cy + size * 0.55, size * 0.08, 0, Math.PI);
    ctx.stroke();
  } else if (name.includes('ball') || name.includes('sport') || name.includes('运动') || name.includes('球')) {
    // 运动球
    ctx.fillStyle = '#FF7043';
    ctx.beginPath();
    ctx.arc(cx + size / 2, cy + size / 2, size * 0.3, 0, Math.PI * 2);
    ctx.fill();
    // 球纹
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5 * camera.zoom;
    ctx.beginPath();
    ctx.arc(cx + size / 2, cy + size / 2, size * 0.2, -Math.PI * 0.3, Math.PI * 0.8);
    ctx.stroke();
  } else {
    // 默认：星星
    ctx.fillStyle = '#FFD54F';
    const starX = cx + size / 2;
    const starY = cy + size / 2;
    const starR = size * 0.3;
    ctx.beginPath();
    for (let i = 0; i < 5; i++) {
      const angle = (i * 4 * Math.PI) / 5 - Math.PI / 2;
      const x = starX + Math.cos(angle) * starR;
      const y = starY + Math.sin(angle) * starR;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();
  }

  ctx.restore();
}

// ===== 认知地图标签 =====
export interface CognitiveLabel {
  x: number;
  y: number;
  label: string;
  type: 'rest' | 'energy' | 'work' | 'social' | 'unknown';
  confidence: number; // 0-1
  discoveredAt: number; // timestamp
}

export function renderCognitiveLabels(
  ctx: CanvasRenderingContext2D,
  labels: CognitiveLabel[],
  camera: Camera,
  viewportW: number,
  viewportH: number,
  time: number,
  showAll: boolean = false
): void {
  for (const lb of labels) {
    if (!showAll && lb.confidence < 0.5) continue;

    const sx = (lb.x - camera.x) * camera.zoom + viewportW / 2;
    const sy = (lb.y - camera.y) * camera.zoom + viewportH / 2;

    const colors: Record<string, string> = {
      rest: '#8E24AA',   // 紫色 - 休息区
      energy: '#FF9800', // 橙色 - 能量补给
      work: '#1976D2',   // 蓝色 - 工作区
      social: '#43A047', // 绿色 - 社交区
      unknown: '#757575',
    };
    const color = colors[lb.type] || colors.unknown;

    const pulse = Math.sin(time * 0.002 + lb.x) * 0.15 + 0.85;
    const radius = 24 * camera.zoom * pulse;

    ctx.save();
    ctx.globalAlpha = 0.7 * lb.confidence;

    // 外圈波纹
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(sx, sy, radius * (1.2 + Math.sin(time * 0.003) * 0.2), 0, Math.PI * 2);
    ctx.stroke();

    // 内圈实心
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(sx, sy, radius * 0.5, 0, Math.PI * 2);
    ctx.fill();

    // 图标
    ctx.fillStyle = '#FFFFFF';
    ctx.font = `bold ${12 * camera.zoom}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const icons: Record<string, string> = {
      rest: '💤', energy: '⚡', work: '💻', social: '💬', unknown: '?',
    };
    ctx.fillText(icons[lb.type] || '?', sx, sy);

    // 标签文字
    if (lb.confidence > 0.6 || showAll) {
      ctx.font = `${10 * camera.zoom}px sans-serif`;
      ctx.fillStyle = '#333';
      ctx.fillText(lb.label, sx, sy - radius - 6);
    }

    ctx.restore();
  }
}

// ===== Layer 8.97: 思维导图节点生长 =====

export function _renderThinkingMap(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  camera: Camera,
  time: number,
  reasoningNodes: string[]
): void {
  // 找到 study 房间中的 desk，或任意 desk
  let deskRoom: Room | null = null;
  let deskFurniture: import('../WorldTypes').Furniture | null = null;
  for (const room of rooms) {
    if (!room.unlocked) continue;
    const desk = room.furniture.find(f => f.type === 'desk');
    if (desk) {
      deskRoom = room;
      deskFurniture = desk;
      break;
    }
  }
  if (!deskRoom || !deskFurniture) return;

  const roomScreen = worldToScreen(deskRoom.bounds.x, deskRoom.bounds.y, camera);
  const dx = roomScreen.x + deskFurniture.position.x * camera.zoom;
  const dy = roomScreen.y + deskFurniture.position.y * camera.zoom;
  const dw = deskFurniture.size.w * camera.zoom;
  const dh = deskFurniture.size.h * camera.zoom;

  // 以笔记本电脑屏幕中心为思维导图原点
  const originX = dx + dw * 0.275; // laptopX + laptopW/2
  const originY = dy + dh * 0.12;

  const nodes = reasoningNodes.slice(-8);
  const nodeCount = nodes.length;
  if (nodeCount === 0) return;

  ctx.save();

  // 节点布局：从原点向上呈扇形展开
  const spreadAngle = Math.min(Math.PI * 0.8, nodeCount * 0.35);
  const startAngle = -Math.PI / 2 - spreadAngle / 2;
  const radiusBase = 45 * camera.zoom;

  const nodePositions: { x: number; y: number; text: string; age: number }[] = [];

  for (let i = 0; i < nodeCount; i++) {
    const age = nodeCount - 1 - i; // 0 = 最新
    const angle = startAngle + (spreadAngle / Math.max(1, nodeCount - 1)) * i;
    const r = radiusBase * (1 + age * 0.15);
    const nx = originX + Math.cos(angle) * r;
    const ny = originY + Math.sin(angle) * r;
    const rawText = nodes[i].replace(/\s+/g, ' ').trim();
    const chars = Array.from(rawText);
    const text = chars.slice(0, 6).join('') + (chars.length > 6 ? '..' : '');
    nodePositions.push({ x: nx, y: ny, text, age });
  }

  // 绘制连线（从原点 → 每个节点，以及节点之间）
  ctx.strokeStyle = 'rgba(100, 180, 150, 0.25)';
  ctx.lineWidth = 1 * camera.zoom;
  ctx.setLineDash([3 * camera.zoom, 3 * camera.zoom]);
  ctx.lineDashOffset = -time * 0.02;

  // 原点 → 节点
  for (const np of nodePositions) {
    ctx.beginPath();
    ctx.moveTo(originX, originY);
    ctx.lineTo(np.x, np.y);
    ctx.stroke();
  }

  // 节点之间
  ctx.strokeStyle = 'rgba(100, 180, 150, 0.15)';
  ctx.lineWidth = 0.6 * camera.zoom;
  for (let i = 0; i < nodePositions.length - 1; i++) {
    ctx.beginPath();
    ctx.moveTo(nodePositions[i].x, nodePositions[i].y);
    ctx.lineTo(nodePositions[i + 1].x, nodePositions[i + 1].y);
    ctx.stroke();
  }

  ctx.setLineDash([]);

  // 绘制节点
  for (const np of nodePositions) {
    const isNewest = np.age === 0;
    const nodeW = Math.min(60 * camera.zoom, 12 * camera.zoom + np.text.length * 7 * camera.zoom);
    const nodeH = 18 * camera.zoom;

    // 最新节点脉冲
    if (isNewest) {
      const pulse = Math.sin(time * 0.005) * 0.15 + 0.85;
      ctx.fillStyle = 'rgba(100, 200, 150, 0.12)';
      ctx.beginPath();
      ctx.arc(np.x, np.y, (nodeW / 2 + 6) * pulse, 0, Math.PI * 2);
      ctx.fill();
    }

    // 节点背景
    ctx.fillStyle = isNewest ? 'rgba(240, 255, 245, 0.92)' : 'rgba(245, 250, 248, 0.78)';
    ctx.strokeStyle = isNewest ? 'rgba(80, 180, 120, 0.6)' : 'rgba(100, 160, 130, 0.35)';
    ctx.lineWidth = isNewest ? 1.2 * camera.zoom : 0.8 * camera.zoom;
    roundRect(ctx, np.x - nodeW / 2, np.y - nodeH / 2, nodeW, nodeH, 4 * camera.zoom);
    ctx.fill();
    ctx.stroke();

    // 节点文字
    ctx.fillStyle = isNewest ? '#1a5c3a' : '#4a7c5c';
    ctx.font = `${isNewest ? 8 : 7}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(np.text, np.x, np.y);

    // 最新节点闪烁点
    if (isNewest) {
      ctx.fillStyle = 'rgba(80, 200, 120, 0.8)';
      ctx.beginPath();
      ctx.arc(np.x + nodeW / 2 + 3 * camera.zoom, np.y, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 原点发光（笔记本电脑屏幕）
  const screenGlow = Math.sin(time * 0.003) * 0.1 + 0.15;
  ctx.fillStyle = `rgba(100, 200, 150, ${screenGlow})`;
  ctx.beginPath();
  ctx.arc(originX, originY, 5 * camera.zoom, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

// ===== Layer 8.98: 空间记忆标记 =====

export function _renderSpatialMemory(
  ctx: CanvasRenderingContext2D,
  rooms: Room[],
  camera: Camera,
  time: number,
  memories: Array<{
    roomId: string;
    x: number;
    y: number;
    label: string;
    memoryType: string;
    emotionalTag: string | null;
  }>
): void {
  for (const mem of memories) {
    const room = rooms.find(r => r.id === mem.roomId);
    if (!room || !room.unlocked) continue;

    const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
    const mx = roomScreen.x + mem.x * camera.zoom;
    const my = roomScreen.y + mem.y * camera.zoom;

    ctx.save();

    // 情绪颜色
    const emotionColors: Record<string, string> = {
      happy: '#FBBF24',
      sad: '#94A3B8',
      angry: '#F87171',
      calm: '#34D399',
      excited: '#A78BFA',
      focused: '#60A5FA',
      nostalgic: '#F472B6',
    };
    const color = emotionColors[mem.emotionalTag || ''] || '#60A5FA';

    // 脉冲波纹
    const pulse = 0.6 + 0.4 * Math.sin(time * 0.002 + mem.x);
    ctx.strokeStyle = color + '40';
    ctx.lineWidth = 1.5 * camera.zoom;
    ctx.beginPath();
    ctx.arc(mx, my, 16 * camera.zoom * pulse, 0, Math.PI * 2);
    ctx.stroke();

    // 记忆点
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(mx, my, 5 * camera.zoom, 0, Math.PI * 2);
    ctx.fill();

    // 内芯
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.arc(mx, my, 2 * camera.zoom, 0, Math.PI * 2);
    ctx.fill();

    // 标签
    ctx.fillStyle = '#4B5563';
    ctx.font = `${8 * camera.zoom}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(mem.label, mx, my - 10 * camera.zoom);

    // 类型小标签
    ctx.fillStyle = color + 'CC';
    ctx.font = `${6 * camera.zoom}px sans-serif`;
    ctx.fillText(mem.memoryType, mx, my + 14 * camera.zoom);

    ctx.restore();
  }
}

// ===== Layer 0: 世界背景 =====

