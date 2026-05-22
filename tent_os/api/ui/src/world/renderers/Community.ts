import type { WorldState, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';

export function renderCommunityZone(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  camera: Camera,
  time: number
): void {
  const { communityBuildings, neighborAvatars, hoveredBuildingId } = state;
  if (!communityBuildings || communityBuildings.length === 0) return;

  // 1. 家和社区之间的过渡带（大门 + 道路）
  renderCommunityTransition(ctx, camera, time);

  // 2. 社区建筑
  for (const building of communityBuildings) {
    renderCommunityBuilding(ctx, building, camera, hoveredBuildingId === building.id, time);
  }

  // 3. 邻居 AI Avatar（简化版）
  for (const neighbor of neighborAvatars || []) {
    renderNeighborAvatar(ctx, neighbor, camera, time);
  }

  // 4. 社区道路网络
  renderCommunityRoads(ctx, communityBuildings, camera);
}

export function renderCommunityTransition(
  ctx: CanvasRenderingContext2D,
  camera: Camera,
  _time: number
): void {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const gateX = 2000;
  const s = worldToScreen(gateX, 0, camera);

  // 只在相机能看到大门时渲染
  if (s.x < -100 || s.x > vw + 100) return;

  ctx.save();

  // 过渡带草地
  const grassS = worldToScreen(gateX - 40, 0, camera);
  const grassE = worldToScreen(gateX + 40, 0, camera);
  const grassWidth = grassE.x - grassS.x;
  ctx.fillStyle = '#E8F5E9';
  ctx.fillRect(grassS.x, 0, grassWidth, vh);

  // 大门立柱
  const pillarW = 8 * camera.zoom;
  const pillarH = 120 * camera.zoom;
  const pillarY = vh / 2 - pillarH / 2;

  ctx.fillStyle = '#8D6E63';
  ctx.fillRect(s.x - pillarW / 2 - 30 * camera.zoom, pillarY, pillarW, pillarH);
  ctx.fillRect(s.x - pillarW / 2 + 30 * camera.zoom, pillarY, pillarW, pillarH);

  // 门楣
  ctx.fillStyle = '#6D4C41';
  ctx.fillRect(s.x - 60 * camera.zoom, pillarY - 12 * camera.zoom, 120 * camera.zoom, 14 * camera.zoom);

  // 门楣文字
  ctx.fillStyle = '#FFF';
  ctx.font = `bold ${10 * camera.zoom}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('AI 社区', s.x, pillarY - 5 * camera.zoom);

  // 道路（从大门延伸进社区）
  const roadS = worldToScreen(gateX, 500, camera);
  const roadE = worldToScreen(gateX + 100, 500, camera);
  ctx.strokeStyle = 'rgba(180,160,130,0.3)';
  ctx.lineWidth = 20 * camera.zoom;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(roadS.x, roadS.y);
  ctx.lineTo(roadE.x + 200 * camera.zoom, roadE.y);
  ctx.stroke();

  ctx.restore();
}

export function renderCommunityBuilding(
  ctx: CanvasRenderingContext2D,
  building: import('../WorldTypes').CommunityBuilding,
  camera: Camera,
  isHovered: boolean,
  time: number
): void {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const { bounds, bgColor, accentColor, nameZh, type } = building;
  const s = worldToScreen(bounds.x, bounds.y, camera);
  const sw = bounds.w * camera.zoom;
  const sh = bounds.h * camera.zoom;

  // 裁剪检测
  if (s.x + sw < -100 || s.x > vw + 100 || s.y + sh < -100 || s.y > vh + 100) return;

  ctx.save();

  // 建筑主体背景（简洁几何风格，无阴影）
  ctx.fillStyle = bgColor;
  const r = 20 * camera.zoom;
  ctx.beginPath();
  ctx.roundRect(s.x, s.y, sw, sh, r);
  ctx.fill();

  // 边框
  ctx.strokeStyle = isHovered ? accentColor : 'rgba(0,0,0,0.08)';
  ctx.lineWidth = isHovered ? 2.5 * camera.zoom : 1.5 * camera.zoom;
  ctx.beginPath();
  ctx.roundRect(s.x, s.y, sw, sh, r);
  ctx.stroke();

  // 悬停高亮
  if (isHovered) {
    ctx.fillStyle = accentColor + '12';
    ctx.beginPath();
    ctx.roundRect(s.x, s.y, sw, sh, r);
    ctx.fill();
    ctx.strokeStyle = accentColor;
    ctx.lineWidth = 2 * camera.zoom;
    ctx.beginPath();
    ctx.roundRect(s.x - 4 * camera.zoom, s.y - 4 * camera.zoom, sw + 8 * camera.zoom, sh + 8 * camera.zoom, r + 4 * camera.zoom);
    ctx.stroke();
  }

  // === 根据建筑类型渲染精美细节 ===
  switch (type) {
    case 'plaza': renderPlazaDetail(ctx, s.x, s.y, sw, sh, camera, time, accentColor); break;
    case 'market': renderMarketDetail(ctx, s.x, s.y, sw, sh, camera, time, accentColor); break;
    case 'temple': renderTempleDetail(ctx, s.x, s.y, sw, sh, camera, time, accentColor); break;
    case 'friend_home': renderFriendHomeDetail(ctx, s.x, s.y, sw, sh, camera, time, accentColor); break;
  }

  // 名称标签（底部居中）
  const labelH = 28 * camera.zoom;
  const labelY = s.y + sh - labelH / 2;
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(s.x + sw * 0.2, labelY - labelH / 2, sw * 0.6, labelH, 14 * camera.zoom);
  ctx.fill();

  ctx.fillStyle = '#1e293b';
  ctx.font = `bold ${12 * camera.zoom}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(nameZh, s.x + sw / 2, labelY);

  ctx.restore();
}

// ===== 社区广场：简洁几何风格 =====
export function renderPlazaDetail(
  ctx: CanvasRenderingContext2D,
  bx: number, by: number, bw: number, bh: number,
  _camera: Camera, _time: number, accent: string
) {
  const cx = bx + bw / 2;
  const cy = by + bh / 2;
  const z = _camera.zoom;

  // 1. 中心圆形水池外圈
  ctx.strokeStyle = accent + '40';
  ctx.lineWidth = 2 * z;
  ctx.beginPath();
  ctx.ellipse(cx, cy, bw * 0.18, bh * 0.18, 0, 0, Math.PI * 2);
  ctx.stroke();

  // 2. 中心圆形水池
  ctx.fillStyle = accent + '18';
  ctx.beginPath();
  ctx.ellipse(cx, cy, bw * 0.18, bh * 0.18, 0, 0, Math.PI * 2);
  ctx.fill();

  // 3. 水面
  ctx.fillStyle = accent + '30';
  ctx.beginPath();
  ctx.ellipse(cx, cy, bw * 0.1, bh * 0.1, 0, 0, Math.PI * 2);
  ctx.fill();

  // 4. 十字石板路（垂直）
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.fillRect(cx - 6 * z, by + bh * 0.18, 12 * z, bh * 0.64);

  // 5. 十字石板路（水平）
  ctx.fillRect(bx + bw * 0.18, cy - 6 * z, bw * 0.64, 12 * z);

  // 6. 左侧长椅
  ctx.fillStyle = '#8D6E63';
  ctx.beginPath();
  ctx.roundRect(bx + bw * 0.06, cy - 6 * z, bw * 0.12, 12 * z, 3 * z);
  ctx.fill();

  // 7. 右侧长椅
  ctx.beginPath();
  ctx.roundRect(bx + bw * 0.82, cy - 6 * z, bw * 0.12, 12 * z, 3 * z);
  ctx.fill();

  // 8. 顶部装饰线
  ctx.strokeStyle = accent + '25';
  ctx.lineWidth = 1.5 * z;
  ctx.beginPath();
  ctx.ellipse(cx, cy, bw * 0.38, bh * 0.38, 0, 0, Math.PI * 2);
  ctx.stroke();
}

// ===== 技能集市：简洁几何风格 =====
export function renderMarketDetail(
  ctx: CanvasRenderingContext2D,
  bx: number, by: number, bw: number, bh: number,
  _camera: Camera, _time: number, accent: string
) {
  const z = _camera.zoom;
  const cx = bx + bw / 2;

  // 1. 大型顶棚
  ctx.fillStyle = accent + '25';
  ctx.beginPath();
  ctx.roundRect(bx + bw * 0.08, by + bh * 0.1, bw * 0.84, bh * 0.25, 6 * z);
  ctx.fill();
  ctx.strokeStyle = accent + '50';
  ctx.lineWidth = 1.5 * z;
  ctx.stroke();

  // 2. 三根支柱
  ctx.fillStyle = '#8D6E63';
  const pillarW = 6 * z;
  const pillarH = bh * 0.45;
  const pillarY = by + bh * 0.35;
  ctx.fillRect(bx + bw * 0.2 - pillarW / 2, pillarY, pillarW, pillarH);
  ctx.fillRect(cx - pillarW / 2, pillarY, pillarW, pillarH);
  ctx.fillRect(bx + bw * 0.8 - pillarW / 2, pillarY, pillarW, pillarH);

  // 3. 货柜1
  ctx.fillStyle = '#EF5350';
  ctx.beginPath();
  ctx.roundRect(bx + bw * 0.15, by + bh * 0.55, bw * 0.18, bh * 0.18, 3 * z);
  ctx.fill();

  // 4. 货柜2
  ctx.fillStyle = '#FF9800';
  ctx.beginPath();
  ctx.roundRect(cx - bw * 0.09, by + bh * 0.55, bw * 0.18, bh * 0.18, 3 * z);
  ctx.fill();

  // 5. 货柜3
  ctx.fillStyle = '#FBC02D';
  ctx.beginPath();
  ctx.roundRect(bx + bw * 0.67, by + bh * 0.55, bw * 0.18, bh * 0.18, 3 * z);
  ctx.fill();

  // 6. 中央招牌
  ctx.fillStyle = '#5D4037';
  ctx.fillRect(cx - 4 * z, by + bh * 0.08, 8 * z, 18 * z);
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.roundRect(cx - 18 * z, by + bh * 0.02, 36 * z, 14 * z, 4 * z);
  ctx.fill();
}

// ===== 任务神庙：简洁几何风格 =====
export function renderTempleDetail(
  ctx: CanvasRenderingContext2D,
  bx: number, by: number, bw: number, bh: number,
  _camera: Camera, _time: number, accent: string
) {
  const z = _camera.zoom;
  const cx = bx + bw / 2;
  const bodyW = bw * 0.6;
  const bodyH = bh * 0.35;
  const bodyY = by + bh * 0.35;

  // 1. 主体建筑
  ctx.fillStyle = '#FAFAFA';
  ctx.fillRect(cx - bodyW / 2, bodyY, bodyW, bodyH);
  ctx.strokeStyle = '#BDBDBD';
  ctx.lineWidth = 1.5 * z;
  ctx.strokeRect(cx - bodyW / 2, bodyY, bodyW, bodyH);

  // 2. 三角形屋顶
  const roofH = bh * 0.22;
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.moveTo(cx - bodyW / 2 - 8 * z, bodyY);
  ctx.lineTo(cx, bodyY - roofH);
  ctx.lineTo(cx + bodyW / 2 + 8 * z, bodyY);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = accent + '80';
  ctx.lineWidth = 2 * z;
  ctx.stroke();

  // 3. 门（中央）
  ctx.fillStyle = '#5D4037';
  ctx.beginPath();
  ctx.roundRect(cx - 12 * z, bodyY + bodyH - 28 * z, 24 * z, 28 * z, 4 * z);
  ctx.fill();

  // 4. 圆形窗户（门上）
  ctx.fillStyle = accent + '30';
  ctx.beginPath();
  ctx.arc(cx, bodyY + 18 * z, 10 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = accent + '50';
  ctx.lineWidth = 1.5 * z;
  ctx.stroke();

  // 5. 祭坛
  ctx.fillStyle = '#8D6E63';
  ctx.fillRect(cx - 20 * z, bodyY + bodyH, 40 * z, 10 * z);
  ctx.fillStyle = '#5D4037';
  ctx.fillRect(cx - 14 * z, bodyY + bodyH - 6 * z, 28 * z, 10 * z);

  // 6. 两侧小柱子
  ctx.fillStyle = '#E0E0E0';
  ctx.fillRect(cx - bodyW / 2 - 6 * z, bodyY, 6 * z, bodyH);
  ctx.fillRect(cx + bodyW / 2, bodyY, 6 * z, bodyH);
}

// ===== 朋友的家：简洁几何风格 =====
export function renderFriendHomeDetail(
  ctx: CanvasRenderingContext2D,
  bx: number, by: number, bw: number, bh: number,
  _camera: Camera, _time: number, accent: string
) {
  const z = _camera.zoom;
  const cx = bx + bw / 2;
  const houseW = bw * 0.45;
  const houseH = bh * 0.35;
  const houseY = by + bh * 0.35;

  // 1. 房屋主体
  ctx.fillStyle = '#FFF3E0';
  ctx.fillRect(cx - houseW / 2, houseY, houseW, houseH);
  ctx.strokeStyle = '#D7CCC8';
  ctx.lineWidth = 1.5 * z;
  ctx.strokeRect(cx - houseW / 2, houseY, houseW, houseH);

  // 2. 三角形屋顶
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.moveTo(cx - houseW / 2 - 8 * z, houseY);
  ctx.lineTo(cx, houseY - houseH * 0.5);
  ctx.lineTo(cx + houseW / 2 + 8 * z, houseY);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = accent + '80';
  ctx.lineWidth = 2 * z;
  ctx.stroke();

  // 3. 门
  ctx.fillStyle = '#5D4037';
  ctx.beginPath();
  ctx.roundRect(cx - 10 * z, houseY + houseH - 28 * z, 20 * z, 28 * z, 3 * z);
  ctx.fill();
  // 门把手
  ctx.fillStyle = '#FFD54F';
  ctx.beginPath();
  ctx.arc(cx + 6 * z, houseY + houseH - 14 * z, 2.5 * z, 0, Math.PI * 2);
  ctx.fill();

  // 4. 圆形窗户（门上）
  ctx.fillStyle = accent + '20';
  ctx.beginPath();
  ctx.arc(cx, houseY + 16 * z, 10 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = accent + '50';
  ctx.lineWidth = 1.5 * z;
  ctx.stroke();

  // 5. 两侧窗户
  [-1, 1].forEach((dir) => {
    const wx = cx + dir * houseW * 0.28;
    const wy = houseY + houseH * 0.28;
    ctx.fillStyle = '#E3F2FD';
    ctx.fillRect(wx - 10 * z, wy - 8 * z, 20 * z, 16 * z);
    ctx.strokeStyle = '#90CAF9';
    ctx.lineWidth = 1.5 * z;
    ctx.strokeRect(wx - 10 * z, wy - 8 * z, 20 * z, 16 * z);
    // 窗框十字
    ctx.beginPath();
    ctx.moveTo(wx, wy - 8 * z);
    ctx.lineTo(wx, wy + 8 * z);
    ctx.moveTo(wx - 10 * z, wy);
    ctx.lineTo(wx + 10 * z, wy);
    ctx.stroke();
  });

  // 6. 烟囱
  ctx.fillStyle = '#8D6E63';
  ctx.fillRect(cx + houseW * 0.22, houseY - houseH * 0.35, 10 * z, 18 * z);

  // 7. 门前小路
  ctx.fillStyle = '#D7CCC8';
  ctx.beginPath();
  ctx.roundRect(cx - 10 * z, houseY + houseH, 20 * z, bh * 0.2, 4 * z);
  ctx.fill();
}

export function renderNeighborAvatar(
  ctx: CanvasRenderingContext2D,
  neighbor: import('../WorldTypes').NeighborAvatar,
  camera: Camera,
  _time: number
): void {
  const s = worldToScreen(neighbor.position.x, neighbor.position.y, camera);
  const z = camera.zoom;
  const sy = s.y;

  ctx.save();

  // 根据情绪选择颜色
  const emotionColors: Record<string, { body: string; accent: string }> = {
    happy: { body: '#FFB74D', accent: '#F57C00' },
    calm: { body: '#4DD0E1', accent: '#0097A7' },
    creative: { body: '#CE93D8', accent: '#8E24AA' },
    focused: { body: '#7986CB', accent: '#303F9F' },
    welcoming: { body: '#A5D6A7', accent: '#388E3C' },
  };
  const colors = emotionColors[neighbor.emotion] || { body: '#90A4AE', accent: '#546E7A' };

  // === 身体 ===
  ctx.fillStyle = colors.body;
  ctx.beginPath();
  ctx.ellipse(s.x, sy + 4 * z, 9 * z, 8 * z, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 1 * z;
  ctx.stroke();

  // === 头部 ===
  ctx.fillStyle = colors.body;
  ctx.beginPath();
  ctx.arc(s.x, sy - 6 * z, 8 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = colors.accent;
  ctx.stroke();

  // === 眼睛（简化为圆点） ===
  ctx.fillStyle = '#37474F';
  ctx.beginPath();
  ctx.arc(s.x - 3 * z, sy - 7 * z, 2 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(s.x + 3 * z, sy - 7 * z, 2 * z, 0, Math.PI * 2);
  ctx.fill();

  // === 嘴巴 ===
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 1 * z;
  ctx.lineCap = 'round';
  ctx.beginPath();
  if (neighbor.emotion === 'happy' || neighbor.emotion === 'welcoming') {
    ctx.arc(s.x, sy - 4 * z, 3 * z, 0.2, Math.PI - 0.2);
  } else if (neighbor.emotion === 'sad') {
    ctx.arc(s.x, sy - 2 * z, 3 * z, Math.PI + 0.2, -0.2);
  } else {
    ctx.moveTo(s.x - 2 * z, sy - 4 * z);
    ctx.lineTo(s.x + 2 * z, sy - 4 * z);
  }
  ctx.stroke();

  // === 天线（静态） ===
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 1.5 * z;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(s.x - 3 * z, sy - 13 * z);
  ctx.quadraticCurveTo(s.x - 6 * z, sy - 20 * z, s.x - 8 * z, sy - 22 * z);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(s.x + 3 * z, sy - 13 * z);
  ctx.quadraticCurveTo(s.x + 6 * z, sy - 20 * z, s.x + 8 * z, sy - 22 * z);
  ctx.stroke();
  // 天线球
  ctx.fillStyle = colors.accent;
  ctx.beginPath();
  ctx.arc(s.x - 8 * z, sy - 22 * z, 2 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(s.x + 8 * z, sy - 22 * z, 2 * z, 0, Math.PI * 2);
  ctx.fill();

  // === 名字标签（无阴影） ===
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  const labelW = (neighbor.name.length * 10 + 10) * z;
  const labelH = 16 * z;
  const labelY = sy + 16 * z;
  ctx.beginPath();
  ctx.roundRect(s.x - labelW / 2, labelY - labelH / 2, labelW, labelH, 8 * z);
  ctx.fill();

  ctx.fillStyle = '#1e293b';
  ctx.font = `bold ${9 * z}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(neighbor.name, s.x, labelY);

  // 在线指示器（无发光）
  ctx.fillStyle = '#10B981';
  ctx.beginPath();
  ctx.arc(s.x + 7 * z, sy + 8 * z, 3 * z, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

export function renderCommunityRoads(
  ctx: CanvasRenderingContext2D,
  buildings: import('../WorldTypes').CommunityBuilding[],
  camera: Camera
): void {
  if (buildings.length < 2) return;

  ctx.save();
  ctx.strokeStyle = 'rgba(180,160,130,0.2)';
  ctx.lineWidth = 16 * camera.zoom;
  ctx.lineCap = 'round';

  // 连接各建筑中心
  for (let i = 0; i < buildings.length; i++) {
    for (let j = i + 1; j < buildings.length; j++) {
      const a = buildings[i];
      const b = buildings[j];
      const acx = a.bounds.x + a.bounds.w / 2;
      const acy = a.bounds.y + a.bounds.h / 2;
      const bcx = b.bounds.x + b.bounds.w / 2;
      const bcy = b.bounds.y + b.bounds.h / 2;

      const sa = worldToScreen(acx, acy, camera);
      const sb = worldToScreen(bcx, bcy, camera);

      ctx.beginPath();
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
      ctx.stroke();
    }
  }
  ctx.restore();
}

// ===== 地图俯瞰视图（简化建筑 + 道路 + Avatar）=====

