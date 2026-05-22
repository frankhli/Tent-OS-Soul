/**
 * Live2D 物理引擎 — 弹簧阻尼系统
 * 驱动：呼吸、视线追踪、天线摆动、动作过渡
 */

export interface Spring {
  target: number;
  current: number;
  velocity: number;
  stiffness: number;
  damping: number;
}

export class Live2DPhysics {
  springs: Map<string, Spring> = new Map();
  time = 0;

  /** 创建或获取弹簧 */
  ensure(id: string, initial: number, stiffness = 120, damping = 8): Spring {
    if (!this.springs.has(id)) {
      this.springs.set(id, { target: initial, current: initial, velocity: 0, stiffness, damping });
    }
    return this.springs.get(id)!;
  }

  /** 设置目标值 */
  setTarget(id: string, target: number) {
    const s = this.springs.get(id);
    if (s) s.target = target;
  }

  /** 单步物理模拟（dt 单位为秒） */
  step(dt: number) {
    this.time += dt;
    for (const s of this.springs.values()) {
      const force = (s.target - s.current) * s.stiffness;
      s.velocity += force * dt;
      s.velocity *= Math.max(0, 1 - s.damping * dt);
      s.current += s.velocity * dt;
    }
  }

  /** 获取当前值 */
  get(id: string): number {
    return this.springs.get(id)?.current ?? 0;
  }

  /** 获取目标值 */
  getTarget(id: string): number {
    return this.springs.get(id)?.target ?? 0;
  }

  /** 视线追踪：头部追踪鼠标位置（阻尼弹簧） */
  trackLookAt(mouseX: number, mouseY: number, centerX: number, centerY: number) {
    const dx = mouseX - centerX;
    const dy = mouseY - centerY;
    const targetAngle = Math.atan2(dy, dx);
    const dist = Math.sqrt(dx * dx + dy * dy);
    const strength = Math.min(1, dist / 300); // 距离越远跟随越强，上限1

    // 水平转头
    const springH = this.ensure('look_h', 0, 80, 6);
    springH.target = targetAngle * strength * 0.4;

    // 垂直点头
    const springV = this.ensure('look_v', 0, 60, 5);
    springV.target = (dy / 300) * strength * 0.3;

    // 眼睛偏移（比头部更灵敏）
    const springEyeX = this.ensure('eye_x', 0, 150, 10);
    springEyeX.target = (dx / 300) * strength * 6;
    const springEyeY = this.ensure('eye_y', 0, 150, 10);
    springEyeY.target = (dy / 300) * strength * 4;

    return {
      headRot: this.get('look_h'),
      headTilt: this.get('look_v'),
      eyeX: this.get('eye_x'),
      eyeY: this.get('eye_y'),
    };
  }

  /** 呼吸：多频叠加 + 弹簧阻尼 */
  breathe(baseIntensity = 1) {
    const t = this.time;
    // 主呼吸频率
    const main = Math.sin(t * 2.5) * 0.5 + 0.5;
    // 次呼吸频率（细微抖动）
    const sub = Math.sin(t * 4.3 + 1.2) * 0.15;
    // 微小颤动
    const micro = Math.sin(t * 7.1 + 0.7) * 0.05;

    const springBreath = this.ensure('breath', 0, 60, 4);
    springBreath.target = (main + sub + micro) * baseIntensity;

    const v = this.get('breath');
    return {
      chestScale: 1 + v * 0.04,
      torsoY: v * -2,
      shoulderY: v * -1.5,
    };
  }

  /** 天线/头发物理：摆动惯性和阻尼 */
  antennaPhysics(baseAngleL: number, baseAngleR: number, movementIntensity = 0) {
    const t = this.time;

    // 天线有自己的弹簧
    const antL = this.ensure('antenna_L', 0, 40, 3);
    const antR = this.ensure('antenna_R', 0, 40, 3);

    // 基础摆动 + 运动惯性
    const windL = Math.sin(t * 3.2) * 0.15 + Math.sin(t * 5.7 + 1) * 0.08;
    const windR = Math.sin(t * 2.8 + 0.5) * 0.15 + Math.sin(t * 6.1) * 0.08;

    antL.target = windL + movementIntensity * 0.3;
    antR.target = windR - movementIntensity * 0.3;

    return {
      antL: baseAngleL + this.get('antenna_L'),
      antR: baseAngleR + this.get('antenna_R'),
    };
  }

  /** 全身动作过渡：所有骨骼同时平滑过渡 */
  transitionPose(current: Record<string, number>, target: Record<string, number>, speed = 4) {
    const result: Record<string, number> = {};
    for (const [id, tVal] of Object.entries(target)) {
      const cVal = current[id] ?? tVal;
      const spring = this.ensure(`pose_${id}`, cVal, speed * 20, speed * 1.2);
      spring.target = tVal;
      result[id] = this.get(`pose_${id}`);
    }
    // 清理不再使用的弹簧
    for (const key of this.springs.keys()) {
      if (key.startsWith('pose_') && !target[key.replace('pose_', '')]) {
        // 保留但不更新，自然衰减到 0
      }
    }
    return result;
  }

  /** 单值弹簧过渡 */
  lerp(id: string, target: number, speed = 5): number {
    const s = this.ensure(id, target, speed * 20, speed);
    s.target = target;
    return this.get(id);
  }
}
