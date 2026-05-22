import type { Room, Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';
import { shadeColor } from './Utils';

export function renderMapView(
  ctx: CanvasRenderingContext2D,
  state: import('../WorldTypes').WorldState,
  viewportW: number,
  viewportH: number,
  _time: number,
): void {
  const { rooms, communityBuildings, avatar, camera } = state;

  ctx.clearRect(0, 0, viewportW, viewportH);

  // 背景：分区地面纹理
  renderMapGround(ctx, viewportW, viewportH, camera);

  // 按 Y 坐标分组房间（自动识别上排/下排，不再硬编码数组索引）
  const sortedByY = [...rooms].sort((a, b) => a.bounds.y - b.bounds.y);
  const rowYs = [...new Set(sortedByY.map(r => r.bounds.y))];
  const rows: typeof rooms[] = [];
  for (const y of rowYs) {
    const row = rooms.filter(r => r.bounds.y === y).sort((a, b) => a.bounds.x - b.bounds.x);
    if (row.length > 0) rows.push(row);
  }

  // 计算内容边界（包含标签底部）
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const r of rooms) {
    minX = Math.min(minX, r.bounds.x);
    minY = Math.min(minY, r.bounds.y);
    maxX = Math.max(maxX, r.bounds.x + r.bounds.w);
    maxY = Math.max(maxY, r.bounds.y + r.bounds.h);
  }
  for (const b of communityBuildings) {
    minX = Math.min(minX, b.bounds.x);
    minY = Math.min(minY, b.bounds.y);
    maxX = Math.max(maxX, b.bounds.x + b.bounds.w);
    maxY = Math.max(maxY, b.bounds.y + b.bounds.h);
  }
  // 家园与社区虚线分隔
  const dividerX = worldToScreen(2050, 0, camera).x;
  ctx.strokeStyle = 'rgba(180, 160, 140, 0.12)';
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 8]);
  ctx.beginPath();
  ctx.moveTo(dividerX, 0);
  ctx.lineTo(dividerX, viewportH);
  ctx.stroke();
  ctx.setLineDash([]);

  // 石板路（按实际相邻关系连接）
  renderMapRoads(ctx, rows, rooms, communityBuildings, camera);

  // 区域标题
  renderMapZoneLabels(ctx, viewportW);

  // 渲染建筑
  for (const room of rooms) {
    renderMapBuilding(ctx, room, camera, _time);
  }
  for (const building of communityBuildings) {
    renderMapCommunityBuilding(ctx, building, camera, _time);
  }
  renderMapAvatar(ctx, avatar, camera, _time);
}

/** 地图模式下渲染单个房间建筑（外部轮廓） */
export function renderMapBuilding(
  ctx: CanvasRenderingContext2D,
  room: import('../WorldTypes').Room,
  camera: import('../WorldTypes').Camera,
  _time: number,
) {
  const z = camera.zoom;
  const s = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const sw = room.bounds.w * z;
  const sh = room.bounds.h * z;

  ctx.save();

  // 建筑底部阴影
  ctx.fillStyle = 'rgba(0,0,0,0.06)';
  ctx.beginPath();
  ctx.ellipse(s.x + sw / 2, s.y + sh + 4 * z, sw * 0.55, 6 * z, 0, 0, Math.PI * 2);
  ctx.fill();

  // 建筑主体（带立体感）
  const bodyY = s.y + sh * 0.18;
  const bodyH = sh * 0.82;

  // 主体阴影面（右侧）
  ctx.fillStyle = shadeColor(room.bgColor, -8);
  ctx.beginPath();
  ctx.roundRect(s.x + 2 * z, bodyY, sw, bodyH, 6 * z);
  ctx.fill();

  // 主体亮面（左侧）
  ctx.fillStyle = room.bgColor;
  ctx.beginPath();
  ctx.roundRect(s.x, bodyY, sw - 2 * z, bodyH, 6 * z);
  ctx.fill();

  // 主体边框
  ctx.strokeStyle = shadeColor(room.wallColor, 10);
  ctx.lineWidth = 1.5 * z;
  ctx.beginPath();
  ctx.roundRect(s.x, bodyY, sw, bodyH, 6 * z);
  ctx.stroke();

  // 屋顶（梯形 + 顶部脊线）
  const roofY = bodyY;
  const roofH = sh * 0.22;
  const overhang = 10 * z;

  // 屋顶阴影面
  ctx.fillStyle = shadeColor(room.wallColor, -15);
  ctx.beginPath();
  ctx.moveTo(s.x - overhang + 2 * z, roofY);
  ctx.lineTo(s.x + sw / 2 + 2 * z, roofY - roofH);
  ctx.lineTo(s.x + sw + overhang + 2 * z, roofY);
  ctx.closePath();
  ctx.fill();

  // 屋顶亮面
  ctx.fillStyle = room.wallColor;
  ctx.beginPath();
  ctx.moveTo(s.x - overhang, roofY);
  ctx.lineTo(s.x + sw / 2, roofY - roofH);
  ctx.lineTo(s.x + sw + overhang, roofY);
  ctx.closePath();
  ctx.fill();

  // 屋顶边框
  ctx.strokeStyle = shadeColor(room.wallColor, -25);
  ctx.lineWidth = 1.2 * z;
  ctx.stroke();

  // 屋顶脊线
  ctx.strokeStyle = 'rgba(255,255,255,0.25)';
  ctx.lineWidth = 1 * z;
  ctx.beginPath();
  ctx.moveTo(s.x + sw / 2 - 8 * z, roofY - roofH * 0.6);
  ctx.lineTo(s.x + sw / 2 + 8 * z, roofY - roofH * 0.6);
  ctx.stroke();

  // 窗户（带窗框和玻璃反光）
  const winW = sw * 0.14;
  const winH = sh * 0.11;
  const winY = bodyY + sh * 0.12;
  [
    s.x + sw * 0.13,
    s.x + sw * 0.71,
  ].forEach((winX) => {
    // 窗框阴影
    ctx.fillStyle = 'rgba(0,0,0,0.06)';
    ctx.fillRect(winX + 1 * z, winY + 1 * z, winW, winH);
    // 窗框
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(winX, winY, winW, winH);
    // 玻璃
    ctx.fillStyle = '#a8d0f0';
    ctx.fillRect(winX + 2 * z, winY + 2 * z, winW - 4 * z, winH - 4 * z);
    // 玻璃高光（对角线）
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 1 * z;
    ctx.beginPath();
    ctx.moveTo(winX + 3 * z, winY + winH - 3 * z);
    ctx.lineTo(winX + winW - 3 * z, winY + 3 * z);
    ctx.stroke();
    // 窗框十字
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 1.5 * z;
    ctx.beginPath();
    ctx.moveTo(winX + winW / 2, winY + 2 * z);
    ctx.lineTo(winX + winW / 2, winY + winH - 2 * z);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(winX + 2 * z, winY + winH / 2);
    ctx.lineTo(winX + winW - 2 * z, winY + winH / 2);
    ctx.stroke();
  });

  // 门（带门框和门把手）
  const doorW = sw * 0.2;
  const doorH = sh * 0.32;
  const doorX = s.x + sw * 0.4;
  const doorY = bodyY + bodyH - doorH;

  // 门框
  ctx.fillStyle = '#4a3528';
  ctx.fillRect(doorX - 2 * z, doorY - 2 * z, doorW + 4 * z, doorH + 2 * z);
  // 门板
  ctx.fillStyle = '#5D4037';
  ctx.fillRect(doorX, doorY, doorW, doorH);
  // 门板纹理（竖线）
  ctx.strokeStyle = 'rgba(0,0,0,0.15)';
  ctx.lineWidth = 1 * z;
  ctx.beginPath();
  ctx.moveTo(doorX + doorW / 2, doorY + 3 * z);
  ctx.lineTo(doorX + doorW / 2, doorY + doorH - 3 * z);
  ctx.stroke();
  // 门把手
  ctx.fillStyle = '#FFD54F';
  ctx.beginPath();
  ctx.arc(doorX + doorW * 0.75, doorY + doorH * 0.55, 2.5 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.2)';
  ctx.lineWidth = 0.5 * z;
  ctx.stroke();

  // 名称标签（建筑外部下方，带背景卡片）
  const labelText = room.nameZh;
  ctx.font = `bold 12px sans-serif`;
  const labelW = ctx.measureText(labelText).width + 16 * z;
  const labelH = 22 * z;
  const labelX = s.x + sw / 2 - labelW / 2;
  const labelY = s.y + sh + 8 * z;

  // 标签阴影
  ctx.fillStyle = 'rgba(0,0,0,0.04)';
  ctx.beginPath();
  ctx.roundRect(labelX + 1 * z, labelY + 1 * z, labelW, labelH, 11 * z);
  ctx.fill();
  // 标签背景
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(labelX, labelY, labelW, labelH, 11 * z);
  ctx.fill();
  // 标签文字
  ctx.fillStyle = '#3d4f3a';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(labelText, s.x + sw / 2, labelY + labelH / 2);

  ctx.restore();
}

/** 地图模式下渲染社区建筑（外部轮廓）——与家园统一为小房子风格 */
export function renderMapCommunityBuilding(
  ctx: CanvasRenderingContext2D,
  building: import('../WorldTypes').CommunityBuilding,
  camera: import('../WorldTypes').Camera,
  _time: number,
) {
  const z = camera.zoom;
  const s = worldToScreen(building.bounds.x, building.bounds.y, camera);
  const sw = building.bounds.w * z;
  const sh = building.bounds.h * z;

  ctx.save();

  // 建筑底部阴影
  ctx.fillStyle = 'rgba(0,0,0,0.06)';
  ctx.beginPath();
  ctx.ellipse(s.x + sw / 2, s.y + sh + 4 * z, sw * 0.55, 6 * z, 0, 0, Math.PI * 2);
  ctx.fill();

  // 建筑主体（带立体感）
  const bodyY = s.y + sh * 0.18;
  const bodyH = sh * 0.82;

  // 主体阴影面
  ctx.fillStyle = shadeColor(building.bgColor, -8);
  ctx.beginPath();
  ctx.roundRect(s.x + 2 * z, bodyY, sw, bodyH, 6 * z);
  ctx.fill();

  // 主体亮面
  ctx.fillStyle = building.bgColor;
  ctx.beginPath();
  ctx.roundRect(s.x, bodyY, sw - 2 * z, bodyH, 6 * z);
  ctx.fill();

  // 主体边框
  ctx.strokeStyle = shadeColor(building.accentColor, 10);
  ctx.lineWidth = 1.5 * z;
  ctx.beginPath();
  ctx.roundRect(s.x, bodyY, sw, bodyH, 6 * z);
  ctx.stroke();

  // 屋顶（梯形 + 脊线）
  const roofY = bodyY;
  const roofH = sh * 0.22;
  const overhang = 10 * z;

  ctx.fillStyle = shadeColor(building.accentColor, -15);
  ctx.beginPath();
  ctx.moveTo(s.x - overhang + 2 * z, roofY);
  ctx.lineTo(s.x + sw / 2 + 2 * z, roofY - roofH);
  ctx.lineTo(s.x + sw + overhang + 2 * z, roofY);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = building.accentColor;
  ctx.beginPath();
  ctx.moveTo(s.x - overhang, roofY);
  ctx.lineTo(s.x + sw / 2, roofY - roofH);
  ctx.lineTo(s.x + sw + overhang, roofY);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = shadeColor(building.accentColor, -25);
  ctx.lineWidth = 1.2 * z;
  ctx.stroke();

  // 屋顶脊线
  ctx.strokeStyle = 'rgba(255,255,255,0.25)';
  ctx.lineWidth = 1 * z;
  ctx.beginPath();
  ctx.moveTo(s.x + sw / 2 - 8 * z, roofY - roofH * 0.6);
  ctx.lineTo(s.x + sw / 2 + 8 * z, roofY - roofH * 0.6);
  ctx.stroke();

  // 窗户（三扇，带窗框和玻璃反光）
  const winW = sw * 0.11;
  const winH = sh * 0.11;
  const winY = bodyY + sh * 0.12;
  [
    s.x + sw * 0.11,
    s.x + sw * 0.445,
    s.x + sw * 0.78,
  ].forEach((winX) => {
    ctx.fillStyle = 'rgba(0,0,0,0.06)';
    ctx.fillRect(winX + 1 * z, winY + 1 * z, winW, winH);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(winX, winY, winW, winH);
    ctx.fillStyle = '#a8d0f0';
    ctx.fillRect(winX + 2 * z, winY + 2 * z, winW - 4 * z, winH - 4 * z);
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 1 * z;
    ctx.beginPath();
    ctx.moveTo(winX + 3 * z, winY + winH - 3 * z);
    ctx.lineTo(winX + winW - 3 * z, winY + 3 * z);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 1.5 * z;
    ctx.beginPath();
    ctx.moveTo(winX + winW / 2, winY + 2 * z);
    ctx.lineTo(winX + winW / 2, winY + winH - 2 * z);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(winX + 2 * z, winY + winH / 2);
    ctx.lineTo(winX + winW - 2 * z, winY + winH / 2);
    ctx.stroke();
  });

  // 门（更宽）
  const doorW = sw * 0.28;
  const doorH = sh * 0.32;
  const doorX = s.x + sw * 0.36;
  const doorY = bodyY + bodyH - doorH;

  ctx.fillStyle = '#4a3528';
  ctx.fillRect(doorX - 2 * z, doorY - 2 * z, doorW + 4 * z, doorH + 2 * z);
  ctx.fillStyle = '#5D4037';
  ctx.fillRect(doorX, doorY, doorW, doorH);
  ctx.strokeStyle = 'rgba(0,0,0,0.15)';
  ctx.lineWidth = 1 * z;
  ctx.beginPath();
  ctx.moveTo(doorX + doorW / 2, doorY + 3 * z);
  ctx.lineTo(doorX + doorW / 2, doorY + doorH - 3 * z);
  ctx.stroke();
  ctx.fillStyle = '#FFD54F';
  ctx.beginPath();
  ctx.arc(doorX + doorW * 0.75, doorY + doorH * 0.55, 2.5 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.2)';
  ctx.lineWidth = 0.5 * z;
  ctx.stroke();

  // 图标
  ctx.fillStyle = building.accentColor;
  ctx.font = `${Math.max(10, 14 * z)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(building.icon, s.x + sw / 2, bodyY + sh * 0.42);

  // 名称标签（外部下方卡片）
  const labelText = building.nameZh;
  ctx.font = `bold 12px sans-serif`;
  const labelW = ctx.measureText(labelText).width + 16 * z;
  const labelH = 22 * z;
  const labelX = s.x + sw / 2 - labelW / 2;
  const labelY = s.y + sh + 8 * z;

  ctx.fillStyle = 'rgba(0,0,0,0.04)';
  ctx.beginPath();
  ctx.roundRect(labelX + 1 * z, labelY + 1 * z, labelW, labelH, 11 * z);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(labelX, labelY, labelW, labelH, 11 * z);
  ctx.fill();
  ctx.fillStyle = '#5a4a3a';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(labelText, s.x + sw / 2, labelY + labelH / 2);

  ctx.restore();
}

/** 地图模式下渲染简化 Avatar */
export function renderMapAvatar(
  ctx: CanvasRenderingContext2D,
  avatar: import('../WorldTypes').WorldAvatarState,
  camera: import('../WorldTypes').Camera,
  _time: number,
) {
  const z = camera.zoom;
  const s = worldToScreen(avatar.position.x, avatar.position.y, camera);

  ctx.save();

  // 地面阴影
  ctx.fillStyle = 'rgba(0,0,0,0.1)';
  ctx.beginPath();
  ctx.ellipse(s.x, s.y + 8 * z, 10 * z, 3 * z, 0, 0, Math.PI * 2);
  ctx.fill();

  // 身体
  ctx.fillStyle = '#FFB74D';
  ctx.beginPath();
  ctx.ellipse(s.x, s.y + 2 * z, 8 * z, 7 * z, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#F57C00';
  ctx.lineWidth = 1 * z;
  ctx.stroke();

  // 头部
  ctx.fillStyle = '#FFB74D';
  ctx.beginPath();
  ctx.arc(s.x, s.y - 6 * z, 7 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#F57C00';
  ctx.stroke();

  // 眼睛
  ctx.fillStyle = '#37474F';
  ctx.beginPath();
  ctx.arc(s.x - 2.5 * z, s.y - 7 * z, 1.8 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(s.x + 2.5 * z, s.y - 7 * z, 1.8 * z, 0, Math.PI * 2);
  ctx.fill();

  // 天线
  ctx.strokeStyle = '#F57C00';
  ctx.lineWidth = 1.2 * z;
  ctx.beginPath();
  ctx.moveTo(s.x - 2 * z, s.y - 12 * z);
  ctx.lineTo(s.x - 5 * z, s.y - 18 * z);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(s.x + 2 * z, s.y - 12 * z);
  ctx.lineTo(s.x + 5 * z, s.y - 18 * z);
  ctx.stroke();
  ctx.fillStyle = '#F57C00';
  ctx.beginPath();
  ctx.arc(s.x - 5 * z, s.y - 18 * z, 1.5 * z, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(s.x + 5 * z, s.y - 18 * z, 1.5 * z, 0, Math.PI * 2);
  ctx.fill();

  // 名字标签
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(s.x - 18 * z, s.y + 12 * z, 36 * z, 14 * z, 7 * z);
  ctx.fill();
  ctx.fillStyle = '#1e293b';
  ctx.font = `bold ${8 * z}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('小腾', s.x, s.y + 19 * z);

  ctx.restore();
}

/** 地图模式：分区地面纹理 */
export function renderMapGround(
  ctx: CanvasRenderingContext2D,
  viewportW: number,
  viewportH: number,
  camera: Camera,
): void {
  // 家园区域（左侧）：淡绿色草坪
  const homeRight = worldToScreen(2050, 0, camera).x;
  ctx.fillStyle = '#f0f5e8';
  ctx.fillRect(0, 0, Math.max(0, homeRight), viewportH);

  // 社区区域（右侧）：浅米色广场
  if (homeRight < viewportW) {
    ctx.fillStyle = '#f5f0e8';
    ctx.fillRect(homeRight, 0, viewportW - homeRight, viewportH);
  }

  // 微妙的草坪纹理（家园区域）
  ctx.save();
  ctx.strokeStyle = 'rgba(180,200,160,0.08)';
  ctx.lineWidth = 1;
  const gridSize = 40;
  for (let x = 0; x < viewportW; x += gridSize) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, viewportH);
    ctx.stroke();
  }
  for (let y = 0; y < viewportH; y += gridSize) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(viewportW, y);
    ctx.stroke();
  }
  ctx.restore();
}

/** 地图模式：石板路 */
export function renderMapRoads(
  ctx: CanvasRenderingContext2D,
  rows: Room[][],
  rooms: Room[],
  communityBuildings: import('../WorldTypes').CommunityBuilding[],
  camera: Camera,
): void {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // 主路（深灰色路基）
  ctx.strokeStyle = '#b8a898';
  ctx.lineWidth = 10;
  ctx.beginPath();
  for (const row of rows) {
    for (let i = 0; i < row.length - 1; i++) {
      const a = row[i], b = row[i + 1];
      const sa = worldToScreen(a.bounds.x + a.bounds.w / 2, a.bounds.y + a.bounds.h / 2, camera);
      const sb = worldToScreen(b.bounds.x + b.bounds.w / 2, b.bounds.y + b.bounds.h / 2, camera);
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
    }
  }
  for (let i = 0; i < rows.length - 1; i++) {
    for (const a of rows[i]) {
      for (const b of rows[i + 1]) {
        const ax = a.bounds.x + a.bounds.w / 2;
        const bx = b.bounds.x + b.bounds.w / 2;
        if (Math.abs(ax - bx) < 250) {
          const sa = worldToScreen(ax, a.bounds.y + a.bounds.h / 2, camera);
          const sb = worldToScreen(bx, b.bounds.y + b.bounds.h / 2, camera);
          ctx.moveTo(sa.x, sa.y);
          ctx.lineTo(sb.x, sb.y);
        }
      }
    }
  }
  const homeRooms = rooms.filter(r => r.bounds.x < 2000);
  if (homeRooms.length > 0 && communityBuildings.length > 0) {
    const rightMost = homeRooms.reduce((a, b) => (a.bounds.x + a.bounds.w > b.bounds.x + b.bounds.w ? a : b));
    const leftMost = communityBuildings.reduce((a, b) => (a.bounds.x < b.bounds.x ? a : b));
    const s1 = worldToScreen(rightMost.bounds.x + rightMost.bounds.w / 2, rightMost.bounds.y + rightMost.bounds.h / 2, camera);
    const s2 = worldToScreen(leftMost.bounds.x + leftMost.bounds.w / 2, leftMost.bounds.y + leftMost.bounds.h / 2, camera);
    ctx.moveTo(s1.x, s1.y);
    ctx.lineTo(s2.x, s2.y);
  }
  ctx.stroke();

  // 石板路纹理（白色虚线）
  ctx.strokeStyle = 'rgba(255,255,255,0.35)';
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 6]);
  ctx.beginPath();
  for (const row of rows) {
    for (let i = 0; i < row.length - 1; i++) {
      const a = row[i], b = row[i + 1];
      const sa = worldToScreen(a.bounds.x + a.bounds.w / 2, a.bounds.y + a.bounds.h / 2, camera);
      const sb = worldToScreen(b.bounds.x + b.bounds.w / 2, b.bounds.y + b.bounds.h / 2, camera);
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
    }
  }
  ctx.stroke();
  ctx.setLineDash([]);

  // 道路两侧小草
  ctx.fillStyle = 'rgba(140,180,120,0.15)';
  for (const row of rows) {
    for (let i = 0; i < row.length - 1; i++) {
      const a = row[i], b = row[i + 1];
      const sa = worldToScreen(a.bounds.x + a.bounds.w / 2, a.bounds.y + a.bounds.h / 2, camera);
      const sb = worldToScreen(b.bounds.x + b.bounds.w / 2, b.bounds.y + b.bounds.h / 2, camera);
      const dx = sb.x - sa.x;
      const dy = sb.y - sa.y;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const nx = -dy / len * 6;
      const ny = dx / len * 6;
      for (let t = 0; t <= 1; t += 0.1) {
        const px = sa.x + dx * t + nx;
        const py = sa.y + dy * t + ny;
        ctx.beginPath();
        ctx.arc(px, py, 2, 0, Math.PI * 2);
        ctx.fill();
        const px2 = sa.x + dx * t - nx;
        const py2 = sa.y + dy * t - ny;
        ctx.beginPath();
        ctx.arc(px2, py2, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.restore();
}

/** 地图模式：区域标题 */
export function renderMapZoneLabels(ctx: CanvasRenderingContext2D, viewportW: number): void {
  const labelY = 32;
  const padX = 16;
  const padY = 8;
  const fontSize = 14;

  ctx.font = `bold ${fontSize}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // 家园标签
  const homeText = '🏠 家园';
  const homeW = ctx.measureText(homeText).width + padX * 2;
  const homeX = viewportW * 0.22;
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(homeX - homeW / 2, labelY - padY - fontSize / 2, homeW, padY * 2 + fontSize, 12);
  ctx.fill();
  ctx.fillStyle = '#5a6e4a';
  ctx.fillText(homeText, homeX, labelY);

  // 社区标签
  const commText = '🏘️ AI 社区';
  const commW = ctx.measureText(commText).width + padX * 2;
  const commX = viewportW * 0.72;
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.roundRect(commX - commW / 2, labelY - padY - fontSize / 2, commW, padY * 2 + fontSize, 12);
  ctx.fill();
  ctx.fillStyle = '#7a6e5a';
  ctx.fillText(commText, commX, labelY);
}

// ===== 社区建筑内部视图（点击进入后渲染）=====

