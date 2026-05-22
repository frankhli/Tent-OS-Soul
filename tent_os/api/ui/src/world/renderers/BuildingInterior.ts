import { shadeColor } from './Utils';

export function renderBuildingInterior(
  ctx: CanvasRenderingContext2D,
  building: import('../WorldTypes').CommunityBuilding,
  vw: number,
  vh: number,
  time: number,
): void {
  const topH = 48;
  const botH = 36;
  const roomTop = topH;
  const roomBot = vh - botH;
  const roomH = roomBot - roomTop;

  // ── 室内透视参数 ──
  const backW = vw * 0.55;
  const backH = roomH * 0.55;
  const backX = (vw - backW) / 2;
  const backY = roomTop + (roomH - backH) / 2;

  const wallL = shadeColor(building.bgColor, -15);
  const wallR = shadeColor(building.bgColor, -22);
  const wallBack = shadeColor(building.bgColor, -5);
  const floor = shadeColor(building.bgColor, -30);
  const ceiling = shadeColor(building.bgColor, 8);

  // ── 地板（梯形透视） ──
  ctx.fillStyle = floor;
  ctx.beginPath();
  ctx.moveTo(0, roomBot);
  ctx.lineTo(vw, roomBot);
  ctx.lineTo(backX + backW, backY + backH);
  ctx.lineTo(backX, backY + backH);
  ctx.closePath();
  ctx.fill();
  // 地板网格线（增加透视感）
  ctx.strokeStyle = 'rgba(0,0,0,0.04)';
  ctx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) {
    const t = i / 5;
    const y = backY + backH + (roomBot - backY - backH) * t;
    const x1 = backX * (1 - t);
    const x2 = backX + backW + (vw - backX - backW) * t;
    ctx.beginPath();
    ctx.moveTo(x1, y);
    ctx.lineTo(x2, y);
    ctx.stroke();
  }

  // ── 天花板 ──
  ctx.fillStyle = ceiling;
  ctx.beginPath();
  ctx.moveTo(0, roomTop);
  ctx.lineTo(vw, roomTop);
  ctx.lineTo(backX + backW, backY);
  ctx.lineTo(backX, backY);
  ctx.closePath();
  ctx.fill();

  // ── 左墙 ──
  ctx.fillStyle = wallL;
  ctx.beginPath();
  ctx.moveTo(0, roomTop);
  ctx.lineTo(backX, backY);
  ctx.lineTo(backX, backY + backH);
  ctx.lineTo(0, roomBot);
  ctx.closePath();
  ctx.fill();

  // ── 右墙 ──
  ctx.fillStyle = wallR;
  ctx.beginPath();
  ctx.moveTo(vw, roomTop);
  ctx.lineTo(backX + backW, backY);
  ctx.lineTo(backX + backW, backY + backH);
  ctx.lineTo(vw, roomBot);
  ctx.closePath();
  ctx.fill();

  // ── 后墙 ──
  ctx.fillStyle = wallBack;
  ctx.fillRect(backX, backY, backW, backH);
  // 后墙边框
  ctx.strokeStyle = shadeColor(building.accentColor, -10);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(backX, backY, backW, backH);

  // ── 后墙内部装饰（根据建筑类型） ──
  ctx.save();
  ctx.beginPath();
  ctx.rect(backX + 2, backY + 2, backW - 4, backH - 4);
  ctx.clip();
  _renderBuildingInteriorContent(ctx, building, backX, backY, backW, backH, time);
  ctx.restore();

  // ── 门口光影（左右下角的暗角） ──
  const gradL = ctx.createLinearGradient(0, roomTop, vw * 0.25, roomBot);
  gradL.addColorStop(0, 'rgba(0,0,0,0.12)');
  gradL.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gradL;
  ctx.fillRect(0, roomTop, vw * 0.25, roomH);

  const gradR = ctx.createLinearGradient(vw, roomTop, vw * 0.75, roomBot);
  gradR.addColorStop(0, 'rgba(0,0,0,0.12)');
  gradR.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gradR;
  ctx.fillRect(vw * 0.75, roomTop, vw * 0.25, roomH);

  // ── 顶部标题栏 ──
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.fillRect(0, 0, vw, topH);
  ctx.fillStyle = building.accentColor;
  ctx.font = 'bold 18px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(`${building.icon} ${building.nameZh}`, vw / 2, topH / 2);

  // ── 底部描述 ──
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.fillRect(0, vh - botH, vw, botH);
  ctx.fillStyle = '#64748b';
  ctx.font = '13px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(building.description, vw / 2, vh - botH / 2);
}

/** 建筑内部后墙内容（真正的室内元素） */
export function _renderBuildingInteriorContent(
  ctx: CanvasRenderingContext2D,
  building: import('../WorldTypes').CommunityBuilding,
  bx: number, by: number, bw: number, bh: number,
  _time: number,
) {
  const cx = bx + bw / 2;
  const cy = by + bh / 2;

  switch (building.type) {
    case 'plaza': {
      // 社区广场内部：开放大厅，中央信息屏，周围长椅
      // 地面装饰圆
      ctx.strokeStyle = building.accentColor + '30';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(cx, cy + bh * 0.1, bw * 0.18, bh * 0.15, 0, 0, Math.PI * 2);
      ctx.stroke();
      // 中央信息柱
      ctx.fillStyle = '#E0E0E0';
      ctx.fillRect(cx - bw * 0.04, by + bh * 0.15, bw * 0.08, bh * 0.35);
      ctx.fillStyle = building.accentColor + '20';
      ctx.beginPath();
      ctx.roundRect(cx - bw * 0.12, by + bh * 0.08, bw * 0.24, bh * 0.1, 4);
      ctx.fill();
      ctx.strokeStyle = building.accentColor + '40';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      // 左右长椅
      ctx.fillStyle = '#8D6E63';
      ctx.beginPath();
      ctx.roundRect(bx + bw * 0.08, cy - bh * 0.06, bw * 0.12, bh * 0.08, 3);
      ctx.fill();
      ctx.beginPath();
      ctx.roundRect(bx + bw * 0.8, cy - bh * 0.06, bw * 0.12, bh * 0.08, 3);
      ctx.fill();
      // 顶部横幅
      ctx.fillStyle = building.accentColor + '15';
      ctx.fillRect(bx, by + bh * 0.02, bw, bh * 0.08);
      ctx.fillStyle = building.accentColor;
      ctx.font = `bold ${Math.max(10, bw * 0.05)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('社区公告', cx, by + bh * 0.06);
      break;
    }
    case 'market': {
      // 技能集市内部：货架/货柜
      // 后墙货架
      ctx.fillStyle = '#EFEBE9';
      ctx.fillRect(bx + bw * 0.1, by + bh * 0.15, bw * 0.8, bh * 0.35);
      ctx.strokeStyle = '#BCAAA4';
      ctx.lineWidth = 1;
      ctx.strokeRect(bx + bw * 0.1, by + bh * 0.15, bw * 0.8, bh * 0.35);
      // 货架层板
      for (let i = 1; i <= 2; i++) {
        const ly = by + bh * 0.15 + (bh * 0.35 * i) / 3;
        ctx.beginPath();
        ctx.moveTo(bx + bw * 0.1, ly);
        ctx.lineTo(bx + bw * 0.9, ly);
        ctx.stroke();
      }
      // 货柜上的"技能瓶"
      const colors = ['#EF5350', '#FF9800', '#FBC02D', '#66BB6A', '#42A5F5', '#AB47BC'];
      for (let i = 0; i < 6; i++) {
        const px = bx + bw * 0.18 + (bw * 0.64 / 5) * i;
        const py = by + bh * 0.22 + (i % 2) * bh * 0.08;
        ctx.fillStyle = colors[i];
        ctx.beginPath();
        ctx.roundRect(px - bw * 0.03, py, bw * 0.06, bh * 0.1, 2);
        ctx.fill();
      }
      // 中央柜台
      ctx.fillStyle = '#8D6E63';
      ctx.beginPath();
      ctx.roundRect(cx - bw * 0.18, by + bh * 0.58, bw * 0.36, bh * 0.18, 4);
      ctx.fill();
      ctx.fillStyle = '#A1887F';
      ctx.fillRect(cx - bw * 0.18, by + bh * 0.58, bw * 0.36, bh * 0.04);
      // 招牌
      ctx.fillStyle = building.accentColor;
      ctx.font = `bold ${Math.max(10, bw * 0.05)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('技能交换', cx, by + bh * 0.68);
      break;
    }
    case 'temple': {
      // 任务神庙内部：祭坛、蜡烛、台阶
      // 台阶
      for (let i = 0; i < 3; i++) {
        const stepW = bw * (0.35 + i * 0.08);
        const stepH = bh * 0.04;
        const stepY = by + bh * 0.55 - i * stepH;
        ctx.fillStyle = shadeColor('#E0E0E0', -i * 5);
        ctx.fillRect(cx - stepW / 2, stepY, stepW, stepH);
        ctx.strokeStyle = '#BDBDBD';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(cx - stepW / 2, stepY, stepW, stepH);
      }
      // 祭坛
      ctx.fillStyle = '#8D6E63';
      ctx.fillRect(cx - bw * 0.1, by + bh * 0.28, bw * 0.2, bh * 0.12);
      ctx.fillStyle = '#5D4037';
      ctx.fillRect(cx - bw * 0.06, by + bh * 0.22, bw * 0.12, bh * 0.08);
      // 祭坛上的发光球
      ctx.fillStyle = building.accentColor + '30';
      ctx.beginPath();
      ctx.arc(cx, by + bh * 0.2, bw * 0.04, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = building.accentColor;
      ctx.beginPath();
      ctx.arc(cx, by + bh * 0.2, bw * 0.025, 0, Math.PI * 2);
      ctx.fill();
      // 两侧蜡烛
      [-1, 1].forEach((dir) => {
        const cX = cx + dir * bw * 0.25;
        const cY = by + bh * 0.5;
        ctx.fillStyle = '#FFF';
        ctx.fillRect(cX - 2, cY, 4, bh * 0.08);
        ctx.fillStyle = '#FFD54F';
        ctx.beginPath();
        ctx.ellipse(cX, cY - 2, 3, 5, 0, 0, Math.PI * 2);
        ctx.fill();
      });
      // 顶部横幅
      ctx.fillStyle = building.accentColor + '15';
      ctx.fillRect(bx, by + bh * 0.02, bw, bh * 0.08);
      ctx.fillStyle = building.accentColor;
      ctx.font = `bold ${Math.max(10, bw * 0.05)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('任务殿堂', cx, by + bh * 0.06);
      break;
    }
    case 'friend_home': {
      // 朋友的家内部：沙发、茶几、挂画
      // 后墙窗户
      ctx.fillStyle = '#E3F2FD';
      ctx.fillRect(cx - bw * 0.12, by + bh * 0.08, bw * 0.24, bh * 0.15);
      ctx.strokeStyle = '#90CAF9';
      ctx.lineWidth = 1;
      ctx.strokeRect(cx - bw * 0.12, by + bh * 0.08, bw * 0.24, bh * 0.15);
      ctx.beginPath();
      ctx.moveTo(cx, by + bh * 0.08);
      ctx.lineTo(cx, by + bh * 0.23);
      ctx.moveTo(cx - bw * 0.12, by + bh * 0.155);
      ctx.lineTo(cx + bw * 0.12, by + bh * 0.155);
      ctx.stroke();
      // 沙发
      ctx.fillStyle = '#FFCC80';
      ctx.beginPath();
      ctx.roundRect(cx - bw * 0.2, by + bh * 0.45, bw * 0.4, bh * 0.14, 4);
      ctx.fill();
      ctx.fillStyle = '#FFB74D';
      ctx.fillRect(cx - bw * 0.2, by + bh * 0.45, bw * 0.4, bh * 0.04);
      // 茶几
      ctx.fillStyle = '#8D6E63';
      ctx.beginPath();
      ctx.roundRect(cx - bw * 0.1, by + bh * 0.62, bw * 0.2, bh * 0.08, 3);
      ctx.fill();
      // 挂画（左）
      ctx.fillStyle = '#FFF8E1';
      ctx.fillRect(bx + bw * 0.08, by + bh * 0.18, bw * 0.1, bh * 0.12);
      ctx.strokeStyle = '#8D6E63';
      ctx.lineWidth = 2;
      ctx.strokeRect(bx + bw * 0.08, by + bh * 0.18, bw * 0.1, bh * 0.12);
      // 挂画（右）
      ctx.fillStyle = '#E8F5E9';
      ctx.fillRect(bx + bw * 0.82, by + bh * 0.18, bw * 0.1, bh * 0.12);
      ctx.strokeStyle = '#8D6E63';
      ctx.lineWidth = 2;
      ctx.strokeRect(bx + bw * 0.82, by + bh * 0.18, bw * 0.1, bh * 0.12);
      break;
    }
  }
}
