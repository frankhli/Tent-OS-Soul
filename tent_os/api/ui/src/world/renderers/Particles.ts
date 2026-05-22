import type { Camera } from '../WorldTypes';
import { worldToScreen } from '../WorldState';
import type { Room } from '../WorldTypes';


interface Particle {
  x: number; y: number;
  vx: number; vy: number;
  life: number; maxLife: number;
  size: number;
  color: string;
  type: 'dust' | 'glow' | 'firefly' | 'spark';
}

export class ParticleSystem {
  particles: Particle[] = [];
  private _time = 0;

  update(dt: number, time: number, rooms: Room[], timeOfDay: string): void {
    this._time = time;
    // 更新现有粒子
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt;
      if (p.life <= 0) this.particles.splice(i, 1);
    }
    // 补充环境粒子（减少数量以提升性能）
    const isNight = timeOfDay === 'night';
    const targetCount = isNight ? 15 : 8;
    while (this.particles.length < targetCount) {
      this.spawnAmbient(rooms, timeOfDay);
    }
  }

  private spawnAmbient(rooms: Room[], timeOfDay: string): void {
    const isNight = timeOfDay === 'night';
    // 优先在解锁房间内生成
    const unlocked = rooms.filter(r => r.unlocked);
    if (unlocked.length === 0) return;
    const room = unlocked[Math.floor(Math.random() * unlocked.length)];
    const x = room.bounds.x + 20 + Math.random() * (room.bounds.w - 40);
    const y = room.bounds.y + 20 + Math.random() * (room.bounds.h - 40);

    if (isNight && Math.random() < 0.3) {
      // 萤火虫
      this.particles.push({
        x, y, vx: (Math.random() - 0.5) * 15, vy: (Math.random() - 0.5) * 15,
        life: 2 + Math.random() * 3, maxLife: 5,
        size: 1.5 + Math.random(), color: `rgba(255,235,100,${0.6 + Math.random() * 0.4})`,
        type: 'firefly',
      });
    } else {
      // 灰尘/光尘
      this.particles.push({
        x, y, vx: (Math.random() - 0.5) * 8, vy: -5 - Math.random() * 10,
        life: 3 + Math.random() * 4, maxLife: 7,
        size: 0.8 + Math.random() * 1.2,
        color: isNight ? `rgba(200,220,255,${0.2 + Math.random() * 0.3})` : `rgba(180,160,120,${0.15 + Math.random() * 0.2})`,
        type: 'dust',
      });
    }
  }

  spawnBurst(x: number, y: number, count: number, color: string): void {
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
      const speed = 30 + Math.random() * 60;
      this.particles.push({
        x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 0.5 + Math.random() * 1, maxLife: 1.5,
        size: 1.5 + Math.random() * 2, color,
        type: 'spark',
      });
    }
  }

  render(ctx: CanvasRenderingContext2D, camera: Camera): void {
    for (const p of this.particles) {
      const s = worldToScreen(p.x, p.y, camera);
      const alpha = Math.min(1, p.life / p.maxLife * 2);
      const size = p.size * camera.zoom;
      if (p.type === 'firefly') {
        const pulse = 0.5 + 0.5 * Math.sin(this._time * 3 + p.x);
        // 避免正则，直接构造颜色字符串
        ctx.fillStyle = `rgba(255,235,100,${alpha * pulse})`;
      } else if (p.type === 'spark') {
        ctx.fillStyle = p.color;
        ctx.globalAlpha = alpha;
      } else {
        ctx.fillStyle = p.color;
        ctx.globalAlpha = alpha * 0.6;
      }
      ctx.beginPath();
      ctx.arc(s.x, s.y, size, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
}

// 全局粒子系统实例（由 WorldMapPanel 管理生命周期）

// 全局粒子系统实例
export const worldParticles = new ParticleSystem();
