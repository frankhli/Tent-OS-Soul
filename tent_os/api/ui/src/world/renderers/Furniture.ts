import type { Room, Furniture, Artifact, Camera, Prop, VisualMemoryProp } from '../WorldTypes';
import { worldToScreen } from '../WorldState';
import { roundRect, shadeColor, seededRandom } from './Utils';

export function renderFurniture(
  ctx: CanvasRenderingContext2D,
  f: Furniture,
  room: Room,
  camera: Camera,
  isHovered: boolean,
  time: number,
  environment?: { brightness: number; weather: string | null },
  currentActivity?: { type: string; target: string; progress: number } | null,
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const fx = roomScreen.x + f.position.x * camera.zoom;
  const fy = roomScreen.y + f.position.y * camera.zoom;
  const fw = f.size.w * camera.zoom;
  const fh = f.size.h * camera.zoom;

  ctx.save();

  // 底部阴影（更柔和）
  ctx.shadowColor = 'rgba(0,0,0,0.12)';
  ctx.shadowOffsetY = 4 * camera.zoom;
  ctx.shadowBlur = 10 * camera.zoom;

  // 主体
  if (f.shape === 'custom') {
    renderCustomFurniture(ctx, f, fx, fy, fw, fh, camera, time);
  } else {
    ctx.fillStyle = f.color;
    if (f.shape === 'rounded_rect') {
      roundRect(ctx, fx, fy, fw, fh, Math.min(fw, fh) * 0.15);
      ctx.fill();
    } else if (f.shape === 'ellipse') {
      ctx.beginPath();
      ctx.ellipse(fx + fw / 2, fy + fh / 2, fw / 2, fh / 2, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (f.shape === 'rect') {
      ctx.fillRect(fx, fy, fw, fh);
    }

    // 描边
    ctx.strokeStyle = f.strokeColor;
    ctx.lineWidth = 1.2 * camera.zoom;
    if (f.shape === 'rounded_rect') {
      roundRect(ctx, fx, fy, fw, fh, Math.min(fw, fh) * 0.15);
      ctx.stroke();
    } else if (f.shape === 'ellipse') {
      ctx.beginPath();
      ctx.ellipse(fx + fw / 2, fy + fh / 2, fw / 2, fh / 2, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (f.shape === 'rect') {
      ctx.strokeRect(fx, fy, fw, fh);
    }

    // 顶部高光
    ctx.shadowColor = 'transparent';
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    if (f.shape === 'rounded_rect' || f.shape === 'rect') {
      ctx.fillRect(fx + 2, fy + 1, fw - 4, Math.max(1, 2 * camera.zoom));
    }
  }

  // 家具类型特定细节（在主体之上绘制）
  renderFurnitureDetails(ctx, f, fx, fy, fw, fh, camera, time, environment, currentActivity);

  // hover 效果
  if (isHovered) {
    ctx.strokeStyle = '#0D9488';
    ctx.lineWidth = 2 * camera.zoom;
    ctx.setLineDash([4 * camera.zoom, 4 * camera.zoom]);
    ctx.shadowColor = 'rgba(13,148,136,0.3)';
    ctx.shadowBlur = 12 * camera.zoom;
    if (f.shape === 'rounded_rect') {
      roundRect(ctx, fx - 3, fy - 3, fw + 6, fh + 6, Math.min(fw, fh) * 0.15 + 3);
      ctx.stroke();
    } else if (f.shape === 'ellipse') {
      ctx.beginPath();
      ctx.ellipse(fx + fw / 2, fy + fh / 2, fw / 2 + 3, fh / 2 + 3, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.strokeRect(fx - 3, fy - 3, fw + 6, fh + 6);
    }
    ctx.setLineDash([]);
    ctx.shadowBlur = 0;
  }

  ctx.restore();
}

/** 家具类型特定细节绘制 */
export function renderFurnitureDetails(
  ctx: CanvasRenderingContext2D,
  f: Furniture,
  fx: number, fy: number,
  fw: number, fh: number,
  camera: Camera,
  time: number,
  environment?: { brightness: number; weather: string | null },
  currentActivity?: { type: string; target: string; progress: number } | null,
): void {
  switch (f.type) {
    case 'sofa': {
      // 扶手（左右圆角）
      ctx.fillStyle = shadeColor(f.color, -10);
      ctx.beginPath();
      ctx.ellipse(fx + fw * 0.12, fy + fh * 0.35, fw * 0.12, fh * 0.4, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(fx + fw * 0.88, fy + fh * 0.35, fw * 0.12, fh * 0.4, 0, 0, Math.PI * 2);
      ctx.fill();
      // 靠垫褶皱（弧线）
      ctx.strokeStyle = shadeColor(f.color, -15) + '60';
      ctx.lineWidth = 1.5 * camera.zoom;
      ctx.beginPath();
      ctx.arc(fx + fw * 0.35, fy + fh * 0.3, fw * 0.08, 0.2, Math.PI - 0.2);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(fx + fw * 0.65, fy + fh * 0.3, fw * 0.08, 0.2, Math.PI - 0.2);
      ctx.stroke();
      break;
    }
    case 'console': {
      // 屏幕区域
      const screenPad = 6 * camera.zoom;
      const screenGrad = ctx.createLinearGradient(fx + screenPad, fy + screenPad, fx + screenPad, fy + fh * 0.55);
      screenGrad.addColorStop(0, '#1e3a5f');
      screenGrad.addColorStop(1, '#0f1f35');
      ctx.fillStyle = screenGrad;
      roundRect(ctx, fx + screenPad, fy + screenPad, fw - screenPad * 2, fh * 0.45, 3 * camera.zoom);
      ctx.fill();

      // 屏幕内容：根据当前活动显示
      if (currentActivity) {
        ctx.save();
        ctx.beginPath();
        roundRect(ctx, fx + screenPad, fy + screenPad, fw - screenPad * 2, fh * 0.45, 3 * camera.zoom);
        ctx.clip();

        const act = currentActivity;
        if (act.type === 'monitoring' || act.type === 'coding') {
          // 代码/监控滚动效果
          ctx.fillStyle = 'rgba(100, 200, 150, 0.6)';
          ctx.font = `${4 * camera.zoom}px monospace`;
          for (let i = 0; i < 4; i++) {
            const lineY = fy + screenPad + 5 * camera.zoom + i * 6 * camera.zoom;
            const lineWidth = (fw - screenPad * 2) * (0.3 + Math.sin(time * 3 + i) * 0.2 + act.progress * 0.5);
            ctx.fillRect(fx + screenPad + 2, lineY, lineWidth, 3 * camera.zoom);
          }
        } else if (act.type === 'thinking') {
          // 思维节点闪烁
          ctx.fillStyle = 'rgba(200, 150, 100, 0.5)';
          for (let i = 0; i < 3; i++) {
            const nx = fx + fw * 0.3 + i * fw * 0.2;
            const ny = fy + fh * 0.15 + Math.sin(time * 2 + i) * 3 * camera.zoom;
            const nr = 2 * camera.zoom * (0.5 + 0.5 * Math.sin(time * 3 + i));
            ctx.beginPath();
            ctx.arc(nx, ny, nr, 0, Math.PI * 2);
            ctx.fill();
          }
          // 连接线
          ctx.strokeStyle = 'rgba(200, 150, 100, 0.2)';
          ctx.lineWidth = 0.5 * camera.zoom;
          ctx.beginPath();
          ctx.moveTo(fx + fw * 0.3, fy + fh * 0.15);
          ctx.lineTo(fx + fw * 0.5, fy + fh * 0.2);
          ctx.lineTo(fx + fw * 0.7, fy + fh * 0.15);
          ctx.stroke();
        }
        ctx.restore();
      } else {
        // 空闲时的屏幕微光
        ctx.fillStyle = 'rgba(100,180,255,0.15)';
        ctx.fillRect(fx + screenPad, fy + screenPad, fw - screenPad * 2, fh * 0.08);
      }

      // 按钮排
      ctx.fillStyle = '#4B5563';
      for (let i = 0; i < 4; i++) {
        ctx.beginPath();
        ctx.arc(fx + fw * 0.2 + i * fw * 0.18, fy + fh * 0.72, 3 * camera.zoom, 0, Math.PI * 2);
        ctx.fill();
      }
      // 按钮发光（呼吸效果）
      const pulse = 0.3 + 0.2 * Math.sin(time * 2);
      ctx.fillStyle = `rgba(100,200,100,${pulse})`;
      ctx.beginPath();
      ctx.arc(fx + fw * 0.2, fy + fh * 0.72, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      // 天线
      ctx.strokeStyle = '#6B7280';
      ctx.lineWidth = 1.5 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.85, fy);
      ctx.lineTo(fx + fw * 0.9, fy - fh * 0.25);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(fx + fw * 0.9, fy - fh * 0.25, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fillStyle = '#EF4444';
      ctx.fill();
      break;
    }
    case 'desk': {
      // 桌面厚度
      ctx.fillStyle = shadeColor(f.color, -20);
      ctx.fillRect(fx + 2, fy + fh * 0.25, fw - 4, fh * 0.08);

      // 笔记本电脑（书桌固有家具）
      const laptopW = fw * 0.35;
      const laptopH = fh * 0.2;
      const laptopX = fx + fw * 0.1;
      const laptopY = fy + fh * 0.02;

      // 屏幕背板
      ctx.fillStyle = '#374151';
      roundRect(ctx, laptopX, laptopY, laptopW, laptopH, 2 * camera.zoom);
      ctx.fill();

      // 屏幕内容：工作时亮屏，空闲时暗屏
      const isWorking = currentActivity && (
        currentActivity.type === 'coding' ||
        currentActivity.type === 'thinking' ||
        currentActivity.type === 'operate' ||
        currentActivity.type === 'chatting' ||
        currentActivity.type === 'monitoring'
      );
      ctx.fillStyle = isWorking ? '#0f1f35' : '#1f2937';
      roundRect(ctx, laptopX + 2, laptopY + 2, laptopW - 4, laptopH - 4, 1 * camera.zoom);
      ctx.fill();

      if (isWorking) {
        // 代码行闪烁
        ctx.fillStyle = 'rgba(100, 200, 150, 0.5)';
        for (let i = 0; i < 3; i++) {
          const lineW = (laptopW - 8) * (0.4 + Math.sin(time * 4 + i * 2) * 0.3);
          ctx.fillRect(laptopX + 4, laptopY + 5 + i * 5 * camera.zoom, lineW, 2.5 * camera.zoom);
        }
      }

      // 键盘
      ctx.fillStyle = '#4B5563';
      ctx.fillRect(laptopX + laptopW * 0.1, laptopY + laptopH, laptopW * 0.8, 2 * camera.zoom);

      // 咖啡杯（书桌固有道具——机制一-3）
      const isResting = currentActivity && currentActivity.type === 'rest';
      const cupX = fx + fw * 0.55;
      const cupY = fy + fh * 0.08;
      const cupW = fw * 0.12;
      const cupH = fh * 0.15;
      // 杯身
      ctx.fillStyle = '#e5e7eb';
      ctx.beginPath();
      ctx.moveTo(cupX, cupY);
      ctx.lineTo(cupX + cupW, cupY);
      ctx.lineTo(cupX + cupW * 0.85, cupY + cupH);
      ctx.lineTo(cupX + cupW * 0.15, cupY + cupH);
      ctx.closePath();
      ctx.fill();
      // 杯把
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1.5 * camera.zoom;
      ctx.beginPath();
      ctx.arc(cupX + cupW, cupY + cupH * 0.35, cupW * 0.25, -Math.PI * 0.4, Math.PI * 0.4);
      ctx.stroke();
      // 咖啡液面
      ctx.fillStyle = isResting ? '#92400e' : '#78350f';
      ctx.beginPath();
      ctx.ellipse(cupX + cupW * 0.5, cupY + cupH * 0.15, cupW * 0.4, cupH * 0.1, 0, 0, Math.PI * 2);
      ctx.fill();
      // 休息时冒热气
      if (isResting) {
        ctx.strokeStyle = 'rgba(200,200,200,0.4)';
        ctx.lineWidth = 1 * camera.zoom;
        for (let i = 0; i < 2; i++) {
          const hx = cupX + cupW * 0.3 + i * cupW * 0.4;
          const hy = cupY - cupH * 0.2;
          ctx.beginPath();
          ctx.moveTo(hx, hy);
          ctx.quadraticCurveTo(
            hx + Math.sin(time * 2 + i) * 3 * camera.zoom,
            hy - 6 * camera.zoom,
            hx + Math.sin(time * 1.5 + i * 2) * 2 * camera.zoom,
            hy - 12 * camera.zoom
          );
          ctx.stroke();
        }
      }

      // 空闲时书本堆叠（在右侧）
      if (!isWorking) {
        const books = ['#EF4444', '#3B82F6', '#10B981'];
        for (let i = 0; i < 3; i++) {
          ctx.fillStyle = books[i];
          ctx.fillRect(fx + fw * 0.72 + i * fw * 0.06, fy + fh * 0.12 - i * fh * 0.06, fw * 0.12, fh * 0.18);
        }
        // 书脊线条
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 0.8 * camera.zoom;
        for (let i = 0; i < 3; i++) {
          ctx.beginPath();
          ctx.moveTo(fx + fw * 0.74 + i * fw * 0.06, fy + fh * 0.14 - i * fh * 0.06);
          ctx.lineTo(fx + fw * 0.74 + i * fw * 0.06, fy + fh * 0.26 - i * fh * 0.06);
          ctx.stroke();
        }
      }
      break;
    }
    case 'bookshelf': {
      // 隔板
      ctx.fillStyle = shadeColor(f.color, -10);
      for (let i = 1; i <= 3; i++) {
        const ly = fy + (fh * i) / 4;
        ctx.fillRect(fx + 2, ly, fw - 4, 2 * camera.zoom);
      }
      // 书脊（使用确定性随机，避免每帧闪烁）
      const bookColors = ['#8B4513', '#2F4F4F', '#800000', '#556B2F', '#4682B4', '#DAA520', '#CD853F'];
      const rng = seededRandom(f.id + '_books');
      for (let shelf = 0; shelf < 3; shelf++) {
        const by = fy + (fh * (shelf + 0.2)) / 4;
        const bh = fh * 0.15;
        let bx = fx + 4;
        let bookIdx = 0;
        while (bx < fx + fw - 8 && bookIdx < 20) {
          const bw = (3 + rng() * 5) * camera.zoom;
          if (bx + bw > fx + fw - 4) break;
          const colorIdx = Math.floor(rng() * bookColors.length);
          ctx.fillStyle = bookColors[colorIdx];
          ctx.fillRect(bx, by, bw, bh);
          bx += bw + camera.zoom;
          bookIdx++;
        }
      }
      break;
    }
    case 'window': {
      const env = environment || { brightness: 0.8, weather: null };
      const isNight = env.brightness < 0.4;
      const isRain = env.weather === 'rain';

      // 外部天空背景（基于环境亮度）
      const skyColor = isNight
        ? `rgba(20, 30, 60, ${0.3 + env.brightness * 0.3})`
        : `rgba(135, 206, 235, ${0.2 + env.brightness * 0.3})`;
      ctx.fillStyle = skyColor;
      ctx.fillRect(fx + 4, fy + 4, fw - 8, fh - 8);

      // 窗框
      ctx.strokeStyle = '#8B7355';
      ctx.lineWidth = 3 * camera.zoom;
      ctx.strokeRect(fx + 2, fy + 2, fw - 4, fh - 4);
      // 十字窗框
      ctx.beginPath();
      ctx.moveTo(fx + fw / 2, fy + 2);
      ctx.lineTo(fx + fw / 2, fy + fh - 2);
      ctx.moveTo(fx + 2, fy + fh / 2);
      ctx.lineTo(fx + fw - 2, fy + fh / 2);
      ctx.stroke();

      // 玻璃反光（随亮度变化）
      ctx.fillStyle = `rgba(255,255,255,${0.1 + env.brightness * 0.2})`;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.15, fy + fh * 0.1);
      ctx.lineTo(fx + fw * 0.35, fy + fh * 0.1);
      ctx.lineTo(fx + fw * 0.2, fy + fh * 0.4);
      ctx.closePath();
      ctx.fill();

      // 夜间星光/城市灯光
      if (isNight) {
        ctx.fillStyle = 'rgba(200, 200, 255, 0.15)';
        for (let i = 0; i < 3; i++) {
          const sx = fx + 10 + i * (fw / 4);
          const sy = fy + 10 + (i % 2) * (fh / 3);
          ctx.beginPath();
          ctx.arc(sx, sy, 1.5 * camera.zoom, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 阳光射入（高亮度时）
      if (env.brightness > 0.6 && !isNight) {
        const sunGrad = ctx.createLinearGradient(fx, fy, fx + fw, fy + fh);
        sunGrad.addColorStop(0, `rgba(255, 240, 200, ${0.08 * env.brightness})`);
        sunGrad.addColorStop(1, 'rgba(255, 240, 200, 0)');
        ctx.fillStyle = sunGrad;
        ctx.fillRect(fx + 4, fy + 4, fw - 8, fh - 8);
      }

      // 雨滴效果（雨天）
      if (isRain) {
        ctx.strokeStyle = `rgba(200, 220, 255, ${0.3 + Math.sin(time * 2) * 0.1})`;
        ctx.lineWidth = 0.8 * camera.zoom;
        for (let i = 0; i < 12; i++) {
          const dropX = fx + 8 + (i * (fw - 16) / 12);
          const dropOffset = (time * 20 + i * 30) % (fh - 16);
          const dropY = fy + 8 + dropOffset;
          ctx.beginPath();
          ctx.moveTo(dropX, dropY);
          ctx.lineTo(dropX - 1 * camera.zoom, dropY + 4 * camera.zoom);
          ctx.stroke();
        }
        // 窗玻璃上的水痕
        ctx.strokeStyle = 'rgba(180, 200, 220, 0.15)';
        ctx.lineWidth = 1.5 * camera.zoom;
        for (let i = 0; i < 3; i++) {
          const wx = fx + 15 + i * (fw / 4);
          ctx.beginPath();
          ctx.moveTo(wx, fy + fh * 0.3);
          ctx.quadraticCurveTo(wx + 3, fy + fh * 0.6, wx - 1, fy + fh * 0.85);
          ctx.stroke();
        }
      }

      break;
    }
    case 'workbench': {
      // 桌面厚度
      ctx.fillStyle = shadeColor(f.color, -15);
      ctx.fillRect(fx, fy + fh * 0.2, fw, fh * 0.06);
      // 工具简笔画：锤子
      ctx.strokeStyle = shadeColor(f.color, -30);
      ctx.lineWidth = 2 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.75, fy + fh * 0.35);
      ctx.lineTo(fx + fw * 0.82, fy + fh * 0.15);
      ctx.stroke();
      ctx.fillStyle = shadeColor(f.color, -25);
      ctx.fillRect(fx + fw * 0.79, fy + fh * 0.1, fw * 0.08, fh * 0.06);
      break;
    }
    case 'fireplace': {
      // 石砖纹理
      ctx.strokeStyle = 'rgba(0,0,0,0.1)';
      ctx.lineWidth = 0.8 * camera.zoom;
      for (let row = 0; row < 4; row++) {
        const brickY = fy + (fh * row) / 4;
        ctx.beginPath();
        ctx.moveTo(fx, brickY);
        ctx.lineTo(fx + fw, brickY);
        ctx.stroke();
      }
      // 火焰
      const flameH = fh * 0.4;
      const flameBaseY = fy + fh * 0.55;
      const flicker = Math.sin(time * 8) * 3 * camera.zoom;
      const flameGrad = ctx.createRadialGradient(
        fx + fw / 2, flameBaseY - flameH / 2, 0,
        fx + fw / 2, flameBaseY - flameH / 2, fw * 0.3
      );
      flameGrad.addColorStop(0, 'rgba(255,200,50,0.9)');
      flameGrad.addColorStop(0.5, 'rgba(255,100,30,0.6)');
      flameGrad.addColorStop(1, 'rgba(255,50,20,0)');
      ctx.fillStyle = flameGrad;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.3, flameBaseY);
      ctx.quadraticCurveTo(fx + fw * 0.5 + flicker, flameBaseY - flameH * 1.2, fx + fw * 0.7, flameBaseY);
      ctx.closePath();
      ctx.fill();
      // 火星
      for (let i = 0; i < 3; i++) {
        const sparkX = fx + fw * (0.4 + Math.sin(time * 5 + i * 2) * 0.15);
        const sparkY = flameBaseY - Math.abs(Math.sin(time * 3 + i)) * flameH * 0.8;
        ctx.fillStyle = `rgba(255,180,50,${0.5 + 0.5 * Math.sin(time * 6 + i)})`;
        ctx.beginPath();
        ctx.arc(sparkX, sparkY, 1.5 * camera.zoom, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case 'reading_chair': {
      // 靠背
      ctx.fillStyle = shadeColor(f.color, -8);
      roundRect(ctx, fx + fw * 0.15, fy, fw * 0.7, fh * 0.55, 4 * camera.zoom);
      ctx.fill();
      // 坐垫
      ctx.fillStyle = shadeColor(f.color, 5);
      roundRect(ctx, fx + fw * 0.1, fy + fh * 0.5, fw * 0.8, fh * 0.35, 3 * camera.zoom);
      ctx.fill();
      break;
    }
    case 'plant_shelf': {
      // 花盆
      for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 2; col++) {
          const px = fx + fw * (0.15 + col * 0.45);
          const py = fy + fh * (0.15 + row * 0.32);
          const pw = fw * 0.25;
          const ph = fh * 0.15;
          ctx.fillStyle = '#8D6E63';
          ctx.beginPath();
          ctx.ellipse(px + pw / 2, py + ph, pw / 2, ph * 0.4, 0, 0, Math.PI * 2);
          ctx.fill();
          // 叶子
          ctx.fillStyle = '#66BB6A';
          for (let l = 0; l < 3; l++) {
            const angle = -Math.PI / 2 + (l - 1) * 0.5;
            ctx.beginPath();
            ctx.ellipse(
              px + pw / 2 + Math.cos(angle) * pw * 0.3,
              py - ph * 0.2 + Math.sin(angle) * ph * 0.5,
              pw * 0.15, ph * 0.4, angle, 0, Math.PI * 2
            );
            ctx.fill();
          }
        }
      }
      break;
    }
    case 'bed': {
      // 床头板
      ctx.fillStyle = shadeColor(f.color, -15);
      roundRect(ctx, fx + fw * 0.05, fy, fw * 0.9, fh * 0.25, 6 * camera.zoom);
      ctx.fill();
      // 床体
      ctx.fillStyle = f.color;
      roundRect(ctx, fx + fw * 0.05, fy + fh * 0.2, fw * 0.9, fh * 0.75, 8 * camera.zoom);
      ctx.fill();
      // 被子（波浪纹理）
      ctx.fillStyle = shadeColor(f.color, 10);
      roundRect(ctx, fx + fw * 0.08, fy + fh * 0.35, fw * 0.84, fh * 0.55, 6 * camera.zoom);
      ctx.fill();
      // 被子褶皱线
      ctx.strokeStyle = shadeColor(f.color, -5) + '40';
      ctx.lineWidth = 1 * camera.zoom;
      for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        ctx.moveTo(fx + fw * 0.15, fy + fh * (0.45 + i * 0.12));
        ctx.quadraticCurveTo(
          fx + fw * 0.5, fy + fh * (0.42 + i * 0.12),
          fx + fw * 0.85, fy + fh * (0.45 + i * 0.12)
        );
        ctx.stroke();
      }
      // 枕头
      ctx.fillStyle = '#F5F5F5';
      roundRect(ctx, fx + fw * 0.12, fy + fh * 0.22, fw * 0.3, fh * 0.12, 4 * camera.zoom);
      ctx.fill();
      roundRect(ctx, fx + fw * 0.58, fy + fh * 0.22, fw * 0.3, fh * 0.12, 4 * camera.zoom);
      ctx.fill();
      // 梦境模式：床体微光
      if (environment && environment.brightness < 0.4) {
        const dreamGlow = ctx.createRadialGradient(
          fx + fw / 2, fy + fh * 0.6, 0,
          fx + fw / 2, fy + fh * 0.6, fw * 0.5
        );
        dreamGlow.addColorStop(0, 'rgba(150, 130, 200, 0.15)');
        dreamGlow.addColorStop(1, 'rgba(150, 130, 200, 0)');
        ctx.fillStyle = dreamGlow;
        ctx.fillRect(fx, fy, fw, fh);
      }
      break;
    }
    case 'nightstand': {
      // 抽屉
      ctx.fillStyle = shadeColor(f.color, -10);
      ctx.fillRect(fx + fw * 0.1, fy + fh * 0.15, fw * 0.8, fh * 0.25);
      ctx.fillRect(fx + fw * 0.1, fy + fh * 0.45, fw * 0.8, fh * 0.25);
      // 把手
      ctx.fillStyle = '#B0BEC5';
      ctx.beginPath();
      ctx.arc(fx + fw / 2, fy + fh * 0.275, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(fx + fw / 2, fy + fh * 0.575, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      // 台灯（小）
      if (environment && environment.brightness < 0.4) {
        ctx.fillStyle = 'rgba(255, 240, 200, 0.4)';
        ctx.beginPath();
        ctx.arc(fx + fw / 2, fy, fw * 0.3, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case 'wardrobe': {
      // 门
      ctx.fillStyle = shadeColor(f.color, -5);
      roundRect(ctx, fx + 2, fy + 2, fw / 2 - 4, fh - 4, 3 * camera.zoom);
      ctx.fill();
      roundRect(ctx, fx + fw / 2 + 2, fy + 2, fw / 2 - 4, fh - 4, 3 * camera.zoom);
      ctx.fill();
      // 把手
      ctx.fillStyle = '#B0BEC5';
      ctx.beginPath();
      ctx.arc(fx + fw * 0.45, fy + fh / 2, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(fx + fw * 0.55, fy + fh / 2, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'memory_board': {
      // PRD D2.0: 根据家具ID渲染不同的家园物品
      if (f.id === 'fridge_board') {
        // 冰箱贴墙：白色冰箱门 + 彩色便签
        ctx.fillStyle = '#FAFAFA';
        roundRect(ctx, fx + 2, fy + 2, fw - 4, fh - 4, 4 * camera.zoom);
        ctx.fill();
        ctx.strokeStyle = '#E0E0E0';
        ctx.lineWidth = 1 * camera.zoom;
        ctx.stroke();
        // 门把手
        ctx.fillStyle = '#BDBDBD';
        ctx.fillRect(fx + fw - 8, fy + fh * 0.45, 4, 12);
        // 便签纸
        const notes = ['#FFD54F', '#81D4FA', '#A5D6A7', '#F48FB1', '#CE93D8'];
        for (let i = 0; i < 5; i++) {
          const nx = fx + 6 + (i % 2) * (fw / 2 - 4);
          const ny = fy + 10 + Math.floor(i / 2) * (fh / 3 - 2);
          const nw = fw / 2 - 10;
          const nh = fh / 3 - 8;
          ctx.fillStyle = notes[i % notes.length];
          ctx.fillRect(nx, ny, nw, nh);
          ctx.shadowColor = 'rgba(0,0,0,0.1)';
          ctx.shadowBlur = 2 * camera.zoom;
          ctx.fillRect(nx, ny, nw, nh);
          ctx.shadowBlur = 0;
        }
      } else if (f.id === 'calendar_wall') {
        // 日历墙：暖黄色背景 + 网格
        ctx.fillStyle = '#FFF8E1';
        roundRect(ctx, fx + 2, fy + 2, fw - 4, fh - 4, 4 * camera.zoom);
        ctx.fill();
        ctx.strokeStyle = '#FFD54F';
        ctx.lineWidth = 1.5 * camera.zoom;
        ctx.stroke();
        // 月份标题
        const now = new Date();
        ctx.fillStyle = '#FF8F00';
        ctx.font = `bold ${Math.max(8, 10 * camera.zoom)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.fillText(`${now.getMonth() + 1}月`, fx + fw / 2, fy + 14);
        // 网格
        ctx.strokeStyle = '#FFE082';
        ctx.lineWidth = 0.5 * camera.zoom;
        const cols = 3, rows = 4;
        const cellW = (fw - 10) / cols;
        const cellH = (fh - 22) / rows;
        for (let r = 0; r <= rows; r++) {
          ctx.beginPath();
          ctx.moveTo(fx + 5, fy + 18 + r * cellH);
          ctx.lineTo(fx + fw - 5, fy + 18 + r * cellH);
          ctx.stroke();
        }
        for (let c = 0; c <= cols; c++) {
          ctx.beginPath();
          ctx.moveTo(fx + 5 + c * cellW, fy + 18);
          ctx.lineTo(fx + 5 + c * cellW, fy + fh - 5);
          ctx.stroke();
        }
        // 高亮今日
        const day = now.getDate();
        const highlightIdx = Math.min(day - 1, cols * rows - 1);
        const hx = fx + 5 + (highlightIdx % cols) * cellW;
        const hy = fy + 18 + Math.floor(highlightIdx / cols) * cellH;
        ctx.fillStyle = 'rgba(255, 138, 101, 0.3)';
        ctx.fillRect(hx + 1, hy + 1, cellW - 2, cellH - 2);
      } else if (f.id === 'project_frame') {
        // 项目画框：金色边框 + 内部画布
        ctx.fillStyle = '#FFF3E0';
        roundRect(ctx, fx + 2, fy + 2, fw - 4, fh - 4, 3 * camera.zoom);
        ctx.fill();
        // 金色边框
        ctx.strokeStyle = '#FFB74D';
        ctx.lineWidth = 3 * camera.zoom;
        ctx.stroke();
        // 内部画板
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(fx + 10, fy + 10, fw - 20, fh - 22);
        // 画架线条
        ctx.strokeStyle = '#E0E0E0';
        ctx.lineWidth = 1 * camera.zoom;
        ctx.beginPath();
        ctx.moveTo(fx + 15, fy + fh - 20);
        ctx.lineTo(fx + fw / 2, fy + fh - 8);
        ctx.lineTo(fx + fw - 15, fy + fh - 20);
        ctx.stroke();
        // 项目徽章
        ctx.fillStyle = '#FF9800';
        ctx.beginPath();
        ctx.arc(fx + fw / 2, fy + fh / 2 - 5, 10 * camera.zoom, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#FFFFFF';
        ctx.font = `bold ${Math.max(8, 10 * camera.zoom)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.fillText('P', fx + fw / 2, fy + fh / 2 - 1);
      } else if (f.id === 'letter_rack') {
        // 信件架：多层木架 + 信封
        ctx.fillStyle = '#E8F5E9';
        roundRect(ctx, fx + 2, fy + 2, fw - 4, fh - 4, 4 * camera.zoom);
        ctx.fill();
        ctx.strokeStyle = '#A5D6A7';
        ctx.lineWidth = 1.5 * camera.zoom;
        ctx.stroke();
        // 三层架子
        ctx.strokeStyle = '#81C784';
        ctx.lineWidth = 2 * camera.zoom;
        for (let i = 1; i <= 2; i++) {
          const ly = fy + 8 + i * (fh - 16) / 3;
          ctx.beginPath();
          ctx.moveTo(fx + 4, ly);
          ctx.lineTo(fx + fw - 4, ly);
          ctx.stroke();
        }
        // 信封
        const envColors = ['#EF9A9A', '#90CAF9', '#CE93D8'];
        for (let i = 0; i < 3; i++) {
          const ex = fx + 6 + (i % 2) * (fw / 2 - 5);
          const ey = fy + 6 + Math.floor(i / 2) * ((fh - 12) / 2);
          const ew = fw / 2 - 8;
          const eh = (fh - 12) / 2 - 4;
          ctx.fillStyle = envColors[i % envColors.length];
          ctx.fillRect(ex, ey, ew, eh);
          // 信封V形
          ctx.strokeStyle = 'rgba(255,255,255,0.6)';
          ctx.lineWidth = 1 * camera.zoom;
          ctx.beginPath();
          ctx.moveTo(ex, ey);
          ctx.lineTo(ex + ew / 2, ey + eh * 0.4);
          ctx.lineTo(ex + ew, ey);
          ctx.stroke();
        }
        // 未读红点（装饰）
        ctx.fillStyle = '#F44336';
        ctx.beginPath();
        ctx.arc(fx + fw - 6, fy + 8, 3 * camera.zoom, 0, Math.PI * 2);
        ctx.fill();
      } else {
        // 默认软木板
        ctx.fillStyle = '#D4A574';
        ctx.fillRect(fx + 2, fy + 2, fw - 4, fh - 4);
        const notes = ['#FFEB3B', '#81D4FA', '#A5D6A7', '#FFCC80'];
        for (let i = 0; i < 6; i++) {
          const nx = fx + 10 + (i % 3) * (fw / 3 - 5);
          const ny = fy + 10 + Math.floor(i / 3) * (fh / 2 - 5);
          const nw = fw / 3 - 15;
          const nh = fh / 2 - 15;
          ctx.fillStyle = notes[i % notes.length];
          ctx.fillRect(nx, ny, nw, nh);
          ctx.fillStyle = '#E74C3C';
          ctx.beginPath();
          ctx.arc(nx + nw / 2, ny + 4, 2 * camera.zoom, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.strokeStyle = '#8D6E63';
        ctx.lineWidth = 2 * camera.zoom;
        ctx.strokeRect(fx, fy, fw, fh);
      }
      break;
    }
    case 'emotional_corner': {
      // 柔和光晕
      const glow = ctx.createRadialGradient(fx + fw / 2, fy + fh / 2, 0, fx + fw / 2, fy + fh / 2, fw);
      glow.addColorStop(0, 'rgba(200, 160, 200, 0.3)');
      glow.addColorStop(1, 'rgba(200, 160, 200, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.ellipse(fx + fw / 2, fy + fh / 2, fw / 2, fh / 2, 0, 0, Math.PI * 2);
      ctx.fill();
      // 坐垫
      ctx.fillStyle = '#D8BFD8';
      roundRect(ctx, fx + fw * 0.15, fy + fh * 0.15, fw * 0.7, fh * 0.7, 8 * camera.zoom);
      ctx.fill();
      // 心形
      ctx.fillStyle = '#C8A5C0';
      const hx = fx + fw / 2;
      const hy = fy + fh / 2;
      const hr = fw * 0.15;
      ctx.beginPath();
      ctx.arc(hx - hr * 0.5, hy - hr * 0.3, hr * 0.5, 0, Math.PI * 2);
      ctx.arc(hx + hr * 0.5, hy - hr * 0.3, hr * 0.5, 0, Math.PI * 2);
      ctx.moveTo(hx - hr, hy);
      ctx.lineTo(hx, hy + hr * 1.2);
      ctx.lineTo(hx + hr, hy);
      ctx.closePath();
      ctx.fill();
      break;
    }
  }
}

/** 特殊家具自定义绘制 */
export function renderCustomFurniture(
  ctx: CanvasRenderingContext2D,
  f: Furniture,
  fx: number, fy: number,
  fw: number, fh: number,
  camera: Camera,
  _time: number
): void {
  switch (f.type) {
    case 'lamp': {
      // 灯座
      ctx.fillStyle = '#4B5563';
      ctx.fillRect(fx + fw * 0.35, fy + fh * 0.65, fw * 0.3, fh * 0.35);
      // 灯杆
      ctx.fillStyle = '#6B7280';
      ctx.fillRect(fx + fw * 0.46, fy + fh * 0.2, fw * 0.08, fh * 0.5);
      // 灯罩（梯形）
      ctx.fillStyle = f.color;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.1, fy + fh * 0.25);
      ctx.lineTo(fx + fw * 0.9, fy + fh * 0.25);
      ctx.lineTo(fx + fw * 0.75, fy);
      ctx.lineTo(fx + fw * 0.25, fy);
      ctx.closePath();
      ctx.fill();
      // 灯罩内发光
      ctx.fillStyle = 'rgba(255,240,200,0.3)';
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.3, fy + fh * 0.22);
      ctx.lineTo(fx + fw * 0.7, fy + fh * 0.22);
      ctx.lineTo(fx + fw * 0.65, fy + fh * 0.05);
      ctx.lineTo(fx + fw * 0.35, fy + fh * 0.05);
      ctx.closePath();
      ctx.fill();
      // 底部光晕（径向渐变）
      const glowR = fw * 1.2;
      const glowGrad = ctx.createRadialGradient(
        fx + fw / 2, fy + fh * 0.7, 0,
        fx + fw / 2, fy + fh * 0.7, glowR
      );
      glowGrad.addColorStop(0, 'rgba(245,200,100,0.2)');
      glowGrad.addColorStop(0.5, 'rgba(245,200,100,0.08)');
      glowGrad.addColorStop(1, 'rgba(245,200,100,0)');
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(fx + fw / 2, fy + fh * 0.7, glowR, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'globe': {
      // 支架
      ctx.strokeStyle = '#6B7280';
      ctx.lineWidth = 2 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(fx + fw / 2, fy + fh);
      ctx.lineTo(fx + fw / 2, fy + fh * 0.3);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(fx + fw / 2, fy + fh * 0.35, fw * 0.45, Math.PI, 0);
      ctx.stroke();
      // 底座
      ctx.fillStyle = '#6B7280';
      ctx.fillRect(fx + fw * 0.2, fy + fh * 0.85, fw * 0.6, fh * 0.15);
      // 地球
      const earthGrad = ctx.createRadialGradient(
        fx + fw * 0.35, fy + fh * 0.25, 0,
        fx + fw / 2, fy + fh * 0.4, fw * 0.38
      );
      earthGrad.addColorStop(0, '#60A5FA');
      earthGrad.addColorStop(1, '#1E40AF');
      ctx.fillStyle = earthGrad;
      ctx.beginPath();
      ctx.arc(fx + fw / 2, fy + fh * 0.4, fw * 0.35, 0, Math.PI * 2);
      ctx.fill();
      // 陆地
      ctx.fillStyle = '#22C55E';
      ctx.beginPath();
      ctx.ellipse(fx + fw * 0.4, fy + fh * 0.35, fw * 0.15, fh * 0.12, 0.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(fx + fw * 0.6, fy + fh * 0.42, fw * 0.1, fh * 0.08, -0.2, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'watering_can': {
      // 壶身
      ctx.fillStyle = f.color;
      ctx.beginPath();
      ctx.ellipse(fx + fw / 2, fy + fh * 0.6, fw * 0.35, fh * 0.35, 0, 0, Math.PI * 2);
      ctx.fill();
      // 壶嘴
      ctx.strokeStyle = f.strokeColor;
      ctx.lineWidth = 3 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(fx + fw * 0.7, fy + fh * 0.5);
      ctx.lineTo(fx + fw * 0.95, fy + fh * 0.3);
      ctx.stroke();
      // 把手
      ctx.beginPath();
      ctx.arc(fx + fw * 0.2, fy + fh * 0.5, fw * 0.15, Math.PI * 0.5, Math.PI * 1.5);
      ctx.stroke();
      break;
    }
    default:
      ctx.fillRect(fx, fy, fw, fh);
      break;
  }
}

// ===== Layer 5-6: 智慧藏品渲染（增强版） =====

export function renderArtifact(
  ctx: CanvasRenderingContext2D,
  artifact: Artifact,
  room: Room,
  camera: Camera,
  isHovered: boolean,
  time: number
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const ax = roomScreen.x + artifact.position.x * camera.zoom;
  const ay = roomScreen.y + artifact.position.y * camera.zoom;
  const size = 18 * camera.zoom;

  ctx.save();

  // 底部阴影
  ctx.shadowColor = 'rgba(0,0,0,0.15)';
  ctx.shadowOffsetY = 3 * camera.zoom;
  ctx.shadowBlur = 6 * camera.zoom;

  // 稀有度发光
  const glowColors: Record<string, string> = {
    common: 'rgba(200,200,200,0.25)',
    rare: 'rgba(100,180,255,0.35)',
    epic: 'rgba(180,100,255,0.45)',
    legendary: 'rgba(255,200,50,0.55)',
  };
  ctx.shadowColor = glowColors[artifact.rarity] || glowColors.common;
  ctx.shadowBlur = isHovered ? 18 * camera.zoom : 10 * camera.zoom;

  switch (artifact.visualType) {
    case 'book': {
      // 书脊
      ctx.fillStyle = '#6B4C35';
      roundRect(ctx, ax - size * 0.35, ay - size * 0.5, size * 0.7, size * 1.1, 2);
      ctx.fill();
      // 封面
      ctx.fillStyle = '#8B6F47';
      roundRect(ctx, ax - size * 0.3, ay - size * 0.45, size * 0.6, size, 1);
      ctx.fill();
      // 金色标题线
      ctx.fillStyle = '#D4AF37';
      ctx.fillRect(ax - size * 0.2, ay - size * 0.2, size * 0.4, size * 0.04);
      ctx.fillRect(ax - size * 0.15, ay - size * 0.05, size * 0.3, size * 0.04);
      // 书页边缘
      ctx.fillStyle = '#F5F0E0';
      ctx.fillRect(ax + size * 0.28, ay - size * 0.4, size * 0.06, size * 0.9);
      break;
    }
    case 'crystal': {
      // 多面菱形
      const pulse = 0.6 + 0.4 * Math.sin(time * 2 + artifact.position.x);
      const crystalGrad = ctx.createLinearGradient(ax - size, ay - size, ax + size, ay + size);
      crystalGrad.addColorStop(0, `rgba(100,180,255,${pulse})`);
      crystalGrad.addColorStop(0.5, `rgba(150,200,255,${pulse * 0.8})`);
      crystalGrad.addColorStop(1, `rgba(80,150,220,${pulse})`);
      ctx.fillStyle = crystalGrad;
      ctx.beginPath();
      ctx.moveTo(ax, ay - size);
      ctx.lineTo(ax + size * 0.55, ay - size * 0.1);
      ctx.lineTo(ax + size * 0.35, ay + size * 0.7);
      ctx.lineTo(ax - size * 0.35, ay + size * 0.7);
      ctx.lineTo(ax - size * 0.55, ay - size * 0.1);
      ctx.closePath();
      ctx.fill();
      // 高光面
      ctx.fillStyle = `rgba(255,255,255,${0.25 * pulse})`;
      ctx.beginPath();
      ctx.moveTo(ax, ay - size * 0.9);
      ctx.lineTo(ax + size * 0.25, ay - size * 0.15);
      ctx.lineTo(ax, ay + size * 0.4);
      ctx.closePath();
      ctx.fill();
      // 底部发光
      ctx.fillStyle = `rgba(100,180,255,${0.15 * pulse})`;
      ctx.beginPath();
      ctx.ellipse(ax, ay + size * 0.8, size * 0.5, size * 0.15, 0, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'scroll': {
      // 卷轴两端
      ctx.fillStyle = '#8B6E47';
      ctx.fillRect(ax - size * 0.45, ay - size * 0.35, size * 0.12, size * 0.7);
      ctx.fillRect(ax + size * 0.33, ay - size * 0.35, size * 0.12, size * 0.7);
      // 纸张
      ctx.fillStyle = '#F5F0E0';
      ctx.fillRect(ax - size * 0.35, ay - size * 0.3, size * 0.7, size * 0.6);
      // 文字线
      ctx.fillStyle = 'rgba(100,80,60,0.3)';
      for (let i = 0; i < 4; i++) {
        ctx.fillRect(ax - size * 0.25, ay - size * 0.15 + i * size * 0.12, size * 0.5, size * 0.03);
      }
      break;
    }
    case 'gear': {
      const rotation = time * 0.5;
      ctx.save();
      ctx.translate(ax, ay);
      ctx.rotate(rotation);
      // 齿轮齿
      ctx.fillStyle = '#78909C';
      for (let i = 0; i < 8; i++) {
        const angle = (i / 8) * Math.PI * 2;
        ctx.save();
        ctx.rotate(angle);
        ctx.fillRect(-size * 0.07, -size * 0.5, size * 0.14, size * 0.2);
        ctx.restore();
      }
      // 外圈
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.42, 0, Math.PI * 2);
      ctx.strokeStyle = '#78909C';
      ctx.lineWidth = 3 * camera.zoom;
      ctx.stroke();
      // 内圈
      ctx.fillStyle = '#455A64';
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.2, 0, Math.PI * 2);
      ctx.fill();
      // 中心轴
      ctx.fillStyle = '#90A4AE';
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.08, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      break;
    }
    case 'plant': {
      // 花盆
      ctx.fillStyle = '#8D6E63';
      ctx.beginPath();
      ctx.moveTo(ax - size * 0.25, ay + size * 0.3);
      ctx.lineTo(ax + size * 0.25, ay + size * 0.3);
      ctx.lineTo(ax + size * 0.2, ay + size * 0.55);
      ctx.lineTo(ax - size * 0.2, ay + size * 0.55);
      ctx.closePath();
      ctx.fill();
      // 叶子
      ctx.fillStyle = '#66BB6A';
      for (let i = 0; i < 5; i++) {
        const angle = -Math.PI / 2 + (i - 2) * 0.5;
        ctx.beginPath();
        ctx.ellipse(
          ax + Math.cos(angle) * size * 0.25,
          ay - size * 0.05 + Math.sin(angle) * size * 0.25,
          size * 0.18, size * 0.3, angle, 0, Math.PI * 2
        );
        ctx.fill();
      }
      // 露水闪烁
      if (Math.sin(time * 3 + artifact.position.x) > 0.7) {
        ctx.fillStyle = 'rgba(200,230,255,0.8)';
        ctx.beginPath();
        ctx.arc(ax + size * 0.15, ay - size * 0.15, 1.5 * camera.zoom, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case 'painting': {
      // 画框
      ctx.fillStyle = '#D4AF37';
      ctx.fillRect(ax - size * 0.5, ay - size * 0.4, size, size * 0.8);
      // 画布
      const catColors: Record<string, string> = {
        code: '#3B82F6', writing: '#10B981', design: '#F59E0B',
        analysis: '#8B5CF6', creative: '#EC4899',
      };
      ctx.fillStyle = catColors[artifact.category] || '#94A3B8';
      ctx.fillRect(ax - size * 0.4, ay - size * 0.3, size * 0.8, size * 0.6);
      // 抽象图案
      ctx.fillStyle = 'rgba(255,255,255,0.2)';
      ctx.beginPath();
      ctx.arc(ax, ay, size * 0.15, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    default: {
      ctx.fillStyle = '#94A3B8';
      ctx.beginPath();
      ctx.arc(ax, ay, size * 0.35, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // hover 微光
  if (isHovered) {
    ctx.strokeStyle = '#0D9488';
    ctx.lineWidth = 1.5 * camera.zoom;
    ctx.setLineDash([3 * camera.zoom, 3 * camera.zoom]);
    ctx.beginPath();
    ctx.arc(ax, ay, size * 0.7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.restore();
}

// ===== Layer 6.7: 视觉记忆映射道具（虚实映射）=====

export function renderVisualMemoryProp(
  ctx: CanvasRenderingContext2D,
  prop: VisualMemoryProp,
  room: Room,
  camera: Camera,
  time: number
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const ax = roomScreen.x + prop.position.x * camera.zoom;
  const ay = roomScreen.y + prop.position.y * camera.zoom;
  const size = 16 * camera.zoom;

  ctx.save();
  ctx.shadowColor = 'rgba(100,200,100,0.3)';
  ctx.shadowBlur = 8 * camera.zoom;

  // 用一个简化版的 artifact 渲染
  const fakeArtifact: Artifact = {
    id: prop.id,
    name: prop.name,
    taskId: prop.id,
    category: 'creative',
    position: prop.position,
    visualType: prop.visualType,
    createdAt: prop.createdAt,
    rarity: 'common',
    description: prop.description,
  };
  renderArtifact(ctx, fakeArtifact, room, camera, false, time);

  // 额外标注："视觉感知"
  ctx.fillStyle = 'rgba(100,160,100,0.7)';
  ctx.font = `${9 * camera.zoom}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText('👁', ax, ay - size * 1.2);

  ctx.restore();
}

// ===== Layer 6.5: 可交互道具 =====

export function renderProp(
  ctx: CanvasRenderingContext2D,
  prop: Prop,
  room: Room,
  camera: Camera,
  isHovered: boolean,
  time: number
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const px = roomScreen.x + prop.position.x * camera.zoom;
  const py = roomScreen.y + prop.position.y * camera.zoom;
  const pw = prop.size.w * camera.zoom;
  const ph = prop.size.h * camera.zoom;

  ctx.save();

  // 底部阴影
  ctx.shadowColor = 'rgba(0,0,0,0.12)';
  ctx.shadowOffsetY = 2 * camera.zoom;
  ctx.shadowBlur = 4 * camera.zoom;

  switch (prop.type) {
    case 'coffee_cup': {
      // 杯身
      ctx.fillStyle = prop.color;
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(px + pw, py);
      ctx.lineTo(px + pw * 0.85, py + ph);
      ctx.lineTo(px + pw * 0.15, py + ph);
      ctx.closePath();
      ctx.fill();
      // 杯把
      ctx.strokeStyle = prop.color;
      ctx.lineWidth = 2 * camera.zoom;
      ctx.beginPath();
      ctx.arc(px + pw, py + ph * 0.35, pw * 0.25, -Math.PI * 0.4, Math.PI * 0.4);
      ctx.stroke();
      // 咖啡液面
      const isFull = prop.state !== 'used';
      ctx.fillStyle = isFull ? '#92400e' : '#d6d3d1';
      ctx.beginPath();
      ctx.ellipse(px + pw * 0.5, py + ph * 0.15, pw * 0.4, ph * 0.1, 0, 0, Math.PI * 2);
      ctx.fill();
      // 使用中冒热气
      if (prop.state === 'in_use') {
        ctx.strokeStyle = 'rgba(200,200,200,0.5)';
        ctx.lineWidth = 1 * camera.zoom;
        for (let i = 0; i < 2; i++) {
          const hx = px + pw * 0.3 + i * pw * 0.4;
          const hy = py - ph * 0.2;
          ctx.beginPath();
          ctx.moveTo(hx, hy);
          ctx.quadraticCurveTo(
            hx + Math.sin(time * 2 + i) * 3 * camera.zoom,
            hy - 6 * camera.zoom,
            hx + Math.sin(time * 1.5 + i * 2) * 2 * camera.zoom,
            hy - 12 * camera.zoom
          );
          ctx.stroke();
        }
      }
      break;
    }
    case 'watering_can': {
      // 壶身
      ctx.fillStyle = prop.color;
      ctx.beginPath();
      ctx.ellipse(px + pw * 0.5, py + ph * 0.6, pw * 0.45, ph * 0.35, 0, 0, Math.PI * 2);
      ctx.fill();
      // 壶嘴
      ctx.strokeStyle = prop.color;
      ctx.lineWidth = 3 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(px + pw * 0.85, py + ph * 0.5);
      ctx.lineTo(px + pw * 1.1, py + ph * 0.3);
      ctx.stroke();
      // 壶嘴口
      ctx.fillStyle = prop.color;
      ctx.beginPath();
      ctx.arc(px + pw * 1.1, py + ph * 0.3, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      // 手柄
      ctx.strokeStyle = prop.color;
      ctx.lineWidth = 2.5 * camera.zoom;
      ctx.beginPath();
      ctx.arc(px + pw * 0.15, py + ph * 0.5, pw * 0.25, Math.PI * 0.3, Math.PI * 0.7);
      ctx.stroke();
      // 使用中滴水
      if (prop.state === 'in_use') {
        ctx.fillStyle = 'rgba(100,180,255,0.7)';
        for (let i = 0; i < 3; i++) {
          const dropY = py + ph * 0.3 + ((time * 0.05 + i * 0.3) % 1) * ph * 0.8;
          const dropAlpha = 1 - ((time * 0.05 + i * 0.3) % 1);
          ctx.globalAlpha = dropAlpha;
          ctx.beginPath();
          ctx.arc(px + pw * 1.1 + Math.sin(time * 0.1 + i) * 2 * camera.zoom, dropY, 2 * camera.zoom, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
      break;
    }
    case 'wall_clock': {
      // 表盘外圈
      ctx.fillStyle = prop.color;
      ctx.beginPath();
      ctx.arc(px + pw * 0.5, py + ph * 0.5, pw * 0.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#9ca3af';
      ctx.lineWidth = 1.5 * camera.zoom;
      ctx.stroke();
      // 刻度
      ctx.strokeStyle = '#6b7280';
      ctx.lineWidth = 1 * camera.zoom;
      for (let i = 0; i < 12; i++) {
        const angle = (i / 12) * Math.PI * 2 - Math.PI / 2;
        const r1 = pw * 0.4;
        const r2 = i % 3 === 0 ? pw * 0.32 : pw * 0.38;
        ctx.beginPath();
        ctx.moveTo(px + pw * 0.5 + Math.cos(angle) * r1, py + ph * 0.5 + Math.sin(angle) * r1);
        ctx.lineTo(px + pw * 0.5 + Math.cos(angle) * r2, py + ph * 0.5 + Math.sin(angle) * r2);
        ctx.stroke();
      }
      // 时针（真实时间）
      const now = new Date();
      const hourAngle = ((now.getHours() % 12) / 12) * Math.PI * 2 - Math.PI / 2 + (now.getMinutes() / 60) * (Math.PI / 6);
      ctx.strokeStyle = '#374151';
      ctx.lineWidth = 2 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(px + pw * 0.5, py + ph * 0.5);
      ctx.lineTo(px + pw * 0.5 + Math.cos(hourAngle) * pw * 0.25, py + ph * 0.5 + Math.sin(hourAngle) * pw * 0.25);
      ctx.stroke();
      // 分针
      const minuteAngle = (now.getMinutes() / 60) * Math.PI * 2 - Math.PI / 2;
      ctx.strokeStyle = '#4b5563';
      ctx.lineWidth = 1.5 * camera.zoom;
      ctx.beginPath();
      ctx.moveTo(px + pw * 0.5, py + ph * 0.5);
      ctx.lineTo(px + pw * 0.5 + Math.cos(minuteAngle) * pw * 0.35, py + ph * 0.5 + Math.sin(minuteAngle) * pw * 0.35);
      ctx.stroke();
      // 中心点
      ctx.fillStyle = '#374151';
      ctx.beginPath();
      ctx.arc(px + pw * 0.5, py + ph * 0.5, 2 * camera.zoom, 0, Math.PI * 2);
      ctx.fill();
      // 交互时发光
      if (prop.state === 'in_use') {
        const glowPulse = 0.3 + 0.2 * Math.sin(time * 0.005);
        ctx.strokeStyle = `rgba(251,191,36,${glowPulse})`;
        ctx.lineWidth = 3 * camera.zoom;
        ctx.beginPath();
        ctx.arc(px + pw * 0.5, py + ph * 0.5, pw * 0.55, 0, Math.PI * 2);
        ctx.stroke();
      }
      break;
    }
  }

  // hover 效果
  if (isHovered) {
    ctx.strokeStyle = '#0D9488';
    ctx.lineWidth = 1.5 * camera.zoom;
    ctx.setLineDash([3 * camera.zoom, 3 * camera.zoom]);
    ctx.beginPath();
    ctx.rect(px - 3, py - 3, pw + 6, ph + 6);
    ctx.stroke();
    ctx.setLineDash([]);
    // 道具名称
    ctx.fillStyle = '#0D9488';
    ctx.font = `bold ${9 * camera.zoom}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(prop.name, px + pw * 0.5, py - 8 * camera.zoom);
  }

  ctx.restore();
}

// ===== Layer 6.6: 用户改造 =====

export function renderUserDecoration(
  ctx: CanvasRenderingContext2D,
  dec: { roomId: string; position: { x: number; y: number }; size: { w: number; h: number }; color: string; decorationType: string },
  room: Room,
  camera: Camera,
  time: number
): void {
  const roomScreen = worldToScreen(room.bounds.x, room.bounds.y, camera);
  const dx = roomScreen.x + dec.position.x * camera.zoom;
  const dy = roomScreen.y + dec.position.y * camera.zoom;
  const dw = dec.size.w * camera.zoom;
  const dh = dec.size.h * camera.zoom;

  ctx.save();
  ctx.globalAlpha = 0.85;

  switch (dec.decorationType) {
    case 'sticker': {
      // 贴纸：圆角矩形 + 微旋转
      const rotation = Math.sin(time * 0.001 + dec.position.x) * 0.05;
      ctx.translate(dx + dw / 2, dy + dh / 2);
      ctx.rotate(rotation);
      ctx.fillStyle = dec.color;
      roundRect(ctx, -dw / 2, -dh / 2, dw, dh, 4 * camera.zoom);
      ctx.fill();
      // 贴纸高光
      ctx.fillStyle = 'rgba(255,255,255,0.2)';
      ctx.fillRect(-dw / 2 + 2, -dh / 2 + 1, dw - 4, 2 * camera.zoom);
      break;
    }
    case 'poster': {
      // 海报：矩形 + 边框
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(dx, dy, dw, dh);
      ctx.strokeStyle = dec.color;
      ctx.lineWidth = 2 * camera.zoom;
      ctx.strokeRect(dx, dy, dw, dh);
      // 内容色块
      ctx.fillStyle = dec.color + '40';
      ctx.fillRect(dx + 4 * camera.zoom, dy + 4 * camera.zoom, dw - 8 * camera.zoom, dh * 0.6);
      break;
    }
    case 'plant': {
      // 小盆栽
      ctx.fillStyle = '#8D6E63';
      ctx.beginPath();
      ctx.moveTo(dx + dw * 0.2, dy + dh);
      ctx.lineTo(dx + dw * 0.8, dy + dh);
      ctx.lineTo(dx + dw * 0.7, dy + dh * 0.5);
      ctx.lineTo(dx + dw * 0.3, dy + dh * 0.5);
      ctx.closePath();
      ctx.fill();
      // 叶子
      ctx.fillStyle = dec.color;
      for (let i = 0; i < 3; i++) {
        const angle = -Math.PI / 2 + (i - 1) * 0.6;
        ctx.beginPath();
        ctx.ellipse(
          dx + dw * 0.5 + Math.cos(angle) * dw * 0.2,
          dy + dh * 0.4 + Math.sin(angle) * dh * 0.2,
          dw * 0.12, dh * 0.2, angle, 0, Math.PI * 2
        );
        ctx.fill();
      }
      break;
    }
    default: {
      ctx.fillStyle = dec.color;
      ctx.beginPath();
      ctx.arc(dx + dw / 2, dy + dh / 2, dw * 0.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}

// ===== Layer 7: 锁定房间（氛围感重写） =====

