/**
 * WorldAvatarRenderer — 在世界 Canvas 上渲染完整 Avatar
 *
 * 复用 CanvasAvatar 的核心渲染管线：
 * - Skeleton（骨骼系统）
 * - PartSystem（部件绘制）
 * - Live2DPhysics（弹簧物理）
 * - Actions（动作姿态）
 * - FaceDeformation（面部表情）
 *
 * 不依赖 React，纯状态机驱动渲染。
 */

import { Skeleton, createDefaultSkeleton } from '@/components/avatar/Bone';
import { PartSystem } from '@/components/avatar/PartSystem';
import { createAvatarParts } from '@/components/avatar/PartDefs';
import { Live2DPhysics } from '@/components/avatar/Physics';
import { computeActionPose, applyEmotionToPose } from '@/components/avatar/Actions';
import { getFaceForEmotion, type FaceParams } from '@/components/avatar/FaceDeformation';
import { worldToScreen } from './WorldState';
import type { Camera, WorldAvatarState } from './WorldTypes';

export class WorldAvatarRenderer {
  skeleton: Skeleton;
  physics: Live2DPhysics;
  partSystem: PartSystem;

  // 动作状态
  actionTime = 0;
  lastAction = 'idle';
  globalTime = 0;

  // 面部状态
  face: FaceParams;
  faceVel: Partial<Record<keyof FaceParams, number>> = {};
  blink = 0;
  isBlinking = false;
  blinkPhase = 0;
  blinkSpeed = 15;
  lastBlinkTime = 0;
  breathPhase = 0;

  // 行走步态相位
  gaitPhase = 0;

  // 当前情绪（用于面部插值）
  currentEmotion = 'neutral';

  constructor() {
    this.skeleton = new Skeleton(createDefaultSkeleton());
    this.physics = new Live2DPhysics();
    this.partSystem = new PartSystem(createAvatarParts());
    this.face = getFaceForEmotion('neutral');
    this.lastBlinkTime = performance.now();
  }

  /**
   * 更新 Avatar 状态（每帧调用）
   * @param dt 时间步长（秒）
   * @param avatar 世界 Avatar 状态
   * @param time 全局时间（秒）
   * @param emotion 当前情绪标签
   */
  update(dt: number, avatar: WorldAvatarState, time: number, emotion: string): void {
    this.globalTime = time;
    this.currentEmotion = emotion;

    // 动作切换重置
    if (avatar.currentAction !== this.lastAction) {
      this.lastAction = avatar.currentAction;
      this.actionTime = 0;
    }
    this.actionTime += dt;

    // === 1. 计算目标姿态 ===
    let targetPose = computeActionPose(avatar.currentAction as any, this.actionTime);
    targetPose = applyEmotionToPose(targetPose, emotion);

    // === 2. 呼吸叠加 ===
    const breath = this.physics.breathe(1);
    if (targetPose.torso) {
      targetPose.torso.y = (targetPose.torso.y ?? -30) + breath.torsoY;
      targetPose.torso.scaleX = (targetPose.torso.scaleX ?? 1) * breath.chestScale;
    }

    // === 3. 应用到骨骼（带弹簧过渡） ===
    for (const [boneId, patch] of Object.entries(targetPose)) {
      const current = this.skeleton.getLocal(boneId);
      if (!current) continue;

      if (patch.rotation !== undefined) {
        const val = this.physics.lerp(`bone_${boneId}_rot`, patch.rotation, 4);
        this.skeleton.setLocal(boneId, { rotation: val });
      }
      if (patch.x !== undefined) {
        const val = this.physics.lerp(`bone_${boneId}_x`, patch.x, 4);
        this.skeleton.setLocal(boneId, { x: val });
      }
      if (patch.y !== undefined) {
        const val = this.physics.lerp(`bone_${boneId}_y`, patch.y, 4);
        this.skeleton.setLocal(boneId, { y: val });
      }
      if (patch.scaleX !== undefined) {
        const val = this.physics.lerp(`bone_${boneId}_sx`, patch.scaleX, 4);
        this.skeleton.setLocal(boneId, { scaleX: val });
      }
      if (patch.scaleY !== undefined) {
        const val = this.physics.lerp(`bone_${boneId}_sy`, patch.scaleY, 4);
        this.skeleton.setLocal(boneId, { scaleY: val });
      }
    }

    // === 4. 天线物理 ===
    const antBaseL = this.skeleton.getLocal('antenna_L_base')?.rotation ?? -0.3;
    const antBaseR = this.skeleton.getLocal('antenna_R_base')?.rotation ?? 0.3;
    const movementInt = avatar.currentAction === 'run' ? 1 : avatar.currentAction === 'walk' ? 0.5 : 0;
    const ant = this.physics.antennaPhysics(antBaseL, antBaseR, movementInt);
    this.skeleton.setLocal('antenna_L_base', { rotation: ant.antL });
    this.skeleton.setLocal('antenna_R_base', { rotation: ant.antR });

    // === 5. 行走步态 ===
    if (avatar.isMoving) {
      this.gaitPhase += dt * 8;
      const gait = Math.sin(this.gaitPhase) * 0.2;
      this.skeleton.setLocal('arm_L', { rotation: gait });
      this.skeleton.setLocal('arm_R', { rotation: -gait });
      this.skeleton.setLocal('thigh_L', { rotation: -gait * 0.6 });
      this.skeleton.setLocal('thigh_R', { rotation: gait * 0.6 });
      // 身体轻微上下 bounce
      this.skeleton.setLocal('root', { y: Math.abs(Math.sin(this.gaitPhase)) * -3 });
    } else {
      // 恢复 idle 姿态
      this.physics.lerp('gait_arm_L', 0, 3);
      this.physics.lerp('gait_arm_R', 0, 3);
      this.physics.lerp('gait_thigh_L', 0, 3);
      this.physics.lerp('gait_thigh_R', 0, 3);
      this.skeleton.setLocal('root', { y: 0 });
    }

    // === 6. 计算世界变换 ===
    this.skeleton.invalidate();

    // === 7. 物理步进 ===
    this.physics.step(dt);

    // === 8. 面部更新 ===
    this.updateFace(dt, emotion);

    // === 9. 眨眼更新 ===
    this.updateBlink(dt);

    // === 10. 呼吸相位 ===
    this.breathPhase += dt * 1.5;
  }

  private updateFace(dt: number, emotion: string): void {
    const baseFace = getFaceForEmotion(emotion);
    const targetFace = { ...baseFace };

    const STIFFNESS = 8;
    const DAMPING = 0.7;

    for (const k of Object.keys(targetFace) as (keyof FaceParams)[]) {
      const target = targetFace[k];
      const current = (this.face as any)[k] ?? 0;
      const vel = (this.faceVel as any)[k] ?? 0;
      const force = ((target as number) - current) * STIFFNESS;
      const newVel = (vel + force * dt) * DAMPING;
      (this.faceVel as any)[k] = newVel;
      (this.face as any)[k] = current + newVel * dt;
    }

    // 呼吸影响面部
    const breathOffset = Math.sin(this.breathPhase) * 0.02;
    (this.face as FaceParams).browLHeight = ((this.face as FaceParams).browLHeight ?? 0) + breathOffset * 0.5;
    (this.face as FaceParams).browRHeight = ((this.face as FaceParams).browRHeight ?? 0) + breathOffset * 0.5;
  }

  private updateBlink(dt: number): void {
    const now = performance.now();
    if (!this.isBlinking && now - this.lastBlinkTime > 2000 + Math.random() * 3000) {
      this.isBlinking = true;
      this.blinkPhase = 0;
      this.blinkSpeed = 15;
      this.lastBlinkTime = now;
    }
    if (this.isBlinking) {
      this.blinkPhase += this.blinkSpeed * dt;
      if (this.blinkPhase >= Math.PI) {
        this.blinkPhase = 0;
        this.isBlinking = false;
        this.blink = 0;
      } else {
        if (this.blinkPhase < 1.5) {
          this.blink = Math.sin((this.blinkPhase / 1.5) * Math.PI * 0.5);
        } else if (this.blinkPhase < 1.8) {
          this.blink = 1;
        } else {
          this.blink = Math.cos(((this.blinkPhase - 1.8) / (Math.PI - 1.8)) * Math.PI * 0.5);
        }
      }
    } else {
      this.blink = 0;
    }
  }

  /**
   * 在世界 Canvas 上渲染 Avatar
   */
  render(
    ctx: CanvasRenderingContext2D,
    avatar: WorldAvatarState,
    camera: Camera,
    avatarState?: string,
  ): void {
    const s = worldToScreen(avatar.position.x, avatar.position.y, camera);
    // Avatar 在世界中高度约 60px，原始部件以 ~100px 为基准
    const scale = 0.32 * camera.zoom;

    ctx.save();

    // PRD D2.0: 化身状态引擎 — 状态光晕（用几何圆代替 CSS filter）
    const stateColor = this.getAvatarStateColor(avatarState);
    if (stateColor) {
      ctx.fillStyle = stateColor;
      ctx.beginPath();
      ctx.ellipse(s.x, s.y + 16 * camera.zoom, 30 * camera.zoom, 12 * camera.zoom, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // 地面阴影
    ctx.fillStyle = 'rgba(0,0,0,0.1)';
    ctx.beginPath();
    ctx.ellipse(s.x, s.y + 18 * camera.zoom, 22 * camera.zoom, 6 * camera.zoom, 0, 0, Math.PI * 2);
    ctx.fill();

    // 移动到 Avatar 中心并应用朝向
    ctx.translate(s.x, s.y - 15 * camera.zoom);
    ctx.scale(scale * avatar.facing, scale);

    // 挤压拉伸（跳跃时）
    const squash = this.getSquashStretch(avatar.currentAction, this.actionTime);
    ctx.scale(squash.scaleX, squash.scaleY);

    // 计算面部参数
    const blinkOpen = Math.max(0.05, 1 - this.blink);
    const breathOffset = Math.sin(this.breathPhase) * 0.02;

    // 绘制所有部件
    this.partSystem.draw(ctx, this.skeleton, {
      emotion: this.currentEmotion,
      time: this.globalTime,
      face: this.face,
      mouthOpen: 0,
      asleep: false,
      lookX: breathOffset,
      lookY: breathOffset * 0.5,
      blinkOpen,
    });

    ctx.restore();
  }

  /** PRD D2.0: 根据化身状态返回光晕颜色 */
  private getAvatarStateColor(state?: string): string | null {
    switch (state) {
      case 'WORKING': return 'rgba(59, 130, 246, 0.5)';   // 蓝色专注
      case 'RESTING': return 'rgba(16, 185, 129, 0.4)';   // 绿色宁静
      case 'SLEEPING': return 'rgba(99, 102, 241, 0.4)';  // 靛蓝梦境
      case 'EMOTIONAL_LOW': return 'rgba(96, 165, 250, 0.5)'; // 淡蓝忧郁
      case 'EXCITED': return 'rgba(251, 191, 36, 0.6)';   // 金黄兴奋
      default: return null;
    }
  }

  /** 挤压拉伸（跳跃/冲击） */
  private getSquashStretch(action: string, actionTime: number): { scaleX: number; scaleY: number } {
    if (action === 'jump' && actionTime < 0.4) {
      const t = actionTime / 0.4;
      if (t < 0.3) return { scaleX: 0.85, scaleY: 1.15 }; // 蓄力压缩
      if (t < 0.7) return { scaleX: 1.05, scaleY: 0.95 }; // 空中拉伸
      return { scaleX: 0.9, scaleY: 1.1 }; // 落地反弹
    }
    if (action === 'celebrate') {
      const bounce = Math.sin(actionTime * 12) * 0.05;
      return { scaleX: 1 - bounce, scaleY: 1 + bounce };
    }
    return { scaleX: 1, scaleY: 1 };
  }
}

// 全局单例（由 WorldMapPanel 持有）
export const worldAvatarRenderer = new WorldAvatarRenderer();
