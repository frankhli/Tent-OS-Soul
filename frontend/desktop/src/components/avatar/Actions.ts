/**
 * 关键帧动作系统 + 步态循环 v3
 * 核心升级：
 * 1. 动画12原则——预备动作、跟随动作、挤压拉伸、弧线运动
 * 2. 丰富的idle微动作——呼吸、眨眼、歪头、抖耳朵、张望、搓手、伸懒腰
 * 3. 走路有重量感——落地反弹、重心转移、头部滞后
 * 4. 表情姿态叠加——思考托腮、生气叉腰、难过抱膝
 */

import type { BoneDef } from './Bone';

export type AvatarAction =
  | 'idle' | 'walk' | 'run' | 'sleep' | 'sit' | 'lie' | 'wave' | 'jump' | 'dance'
  // P0: 新增系统角色动作
  | 'monitor' | 'operate' | 'think_deep' | 'recall' | 'alert'
  | 'scan' | 'commune' | 'report' | 'console' | 'reach_out'
  // 机制一-3: 道具交互
  | 'drink_coffee' | 'water_plant' | 'check_time';

export type PosePatch = Partial<Pick<BoneDef, 'x' | 'y' | 'rotation' | 'scaleX' | 'scaleY'>>;

export interface ActionDef {
  name: AvatarAction;
  basePose: Record<string, PosePatch>;
  cycleSpeed?: number;
  cycleFn?: (time: number) => Record<string, PosePatch>;
  transitionTime: number;
}

// ========== 基础姿态 ==========

const POSE_IDLE: Record<string, PosePatch> = {
  root: { rotation: 0, y: 0, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: 0 },
  torso: { rotation: 0, y: -30, scaleX: 1, scaleY: 1 },
  neck: { rotation: 0, y: -40 },
  head: { rotation: 0, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: 0.05 },
  forearm_L: { rotation: -0.05 },
  hand_L: { rotation: 0 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -0.05 },
  forearm_R: { rotation: 0.05 },
  hand_R: { rotation: 0 },
  thigh_L: { rotation: 0 },
  leg_L: { rotation: 0 },
  foot_L: { rotation: 0 },
  thigh_R: { rotation: 0 },
  leg_R: { rotation: 0 },
  foot_R: { rotation: 0 },
  antenna_L_base: { rotation: -0.2 },
  antenna_R_base: { rotation: 0.2 },
};

const POSE_SLEEP: Record<string, PosePatch> = {
  root: { rotation: Math.PI / 2.3, y: 30, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: 0.1 },
  torso: { rotation: -0.1, y: -25 },
  neck: { rotation: 0.2, y: -35 },
  head: { rotation: 0.25, y: -12 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: 0.7 },
  forearm_L: { rotation: 0.5 },
  hand_L: { rotation: 0.1 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -0.7 },
  forearm_R: { rotation: -0.5 },
  hand_R: { rotation: -0.1 },
  thigh_L: { rotation: 0.3 },
  leg_L: { rotation: -0.5 },
  foot_L: { rotation: 0.1 },
  thigh_R: { rotation: -0.3 },
  leg_R: { rotation: -0.5 },
  foot_R: { rotation: -0.1 },
  antenna_L_base: { rotation: -0.05 },
  antenna_R_base: { rotation: 0.05 },
};

const POSE_SIT: Record<string, PosePatch> = {
  root: { rotation: 0, y: 20, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: -0.5 },
  torso: { rotation: 0.15, y: -25, scaleX: 1.02, scaleY: 0.95 },
  neck: { rotation: 0.05, y: -38 },
  head: { rotation: 0, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: 0.25 },
  forearm_L: { rotation: -0.5 },
  hand_L: { rotation: 0 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -0.25 },
  forearm_R: { rotation: 0.5 },
  hand_R: { rotation: 0 },
  thigh_L: { rotation: -1.1 },
  leg_L: { rotation: 1.3 },
  foot_L: { rotation: -0.3 },
  thigh_R: { rotation: -1.1 },
  leg_R: { rotation: 1.3 },
  foot_R: { rotation: -0.3 },
  antenna_L_base: { rotation: -0.15 },
  antenna_R_base: { rotation: 0.15 },
};

const POSE_LIE: Record<string, PosePatch> = {
  root: { rotation: Math.PI / 2, y: 25, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: 0 },
  torso: { rotation: 0, y: -28 },
  neck: { rotation: -0.1, y: -38 },
  head: { rotation: 0.1, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: 0.8 },
  forearm_L: { rotation: 0.4 },
  hand_L: { rotation: 0 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -0.8 },
  forearm_R: { rotation: -0.4 },
  hand_R: { rotation: 0 },
  thigh_L: { rotation: 0.2 },
  leg_L: { rotation: -0.3 },
  foot_L: { rotation: 0 },
  thigh_R: { rotation: -0.2 },
  leg_R: { rotation: -0.3 },
  foot_R: { rotation: 0 },
  antenna_L_base: { rotation: -0.02 },
  antenna_R_base: { rotation: 0.02 },
};

const POSE_WAVE: Record<string, PosePatch> = {
  root: { rotation: 0, y: 0, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: 0 },
  torso: { rotation: -0.05, y: -30 },
  neck: { rotation: 0.05, y: -40 },
  head: { rotation: 0.1, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: -0.05 },
  forearm_L: { rotation: 0.05 },
  hand_L: { rotation: 0 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -2.0 },
  forearm_R: { rotation: -0.2 },
  hand_R: { rotation: 0.15 },
  thigh_L: { rotation: 0 },
  leg_L: { rotation: 0 },
  foot_L: { rotation: 0 },
  thigh_R: { rotation: 0.05 },
  leg_R: { rotation: 0 },
  foot_R: { rotation: 0 },
  antenna_L_base: { rotation: -0.2 },
  antenna_R_base: { rotation: 0.35 },
};

const POSE_JUMP: Record<string, PosePatch> = {
  root: { rotation: 0, y: -20, scaleX: 0.92, scaleY: 1.08 },
  pelvis: { rotation: -0.15 },
  torso: { rotation: 0.1, y: -30, scaleX: 0.95, scaleY: 1.05 },
  neck: { rotation: 0, y: -40 },
  head: { rotation: 0, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: -0.9 },
  forearm_L: { rotation: -0.4 },
  hand_L: { rotation: 0 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: 0.9 },
  forearm_R: { rotation: 0.4 },
  hand_R: { rotation: 0 },
  thigh_L: { rotation: -0.7 },
  leg_L: { rotation: 0.9 },
  foot_L: { rotation: -0.25 },
  thigh_R: { rotation: -0.7 },
  leg_R: { rotation: 0.9 },
  foot_R: { rotation: -0.25 },
  antenna_L_base: { rotation: -0.5 },
  antenna_R_base: { rotation: 0.5 },
};

const POSE_DANCE: Record<string, PosePatch> = {
  root: { rotation: 0, y: 0, scaleX: 1, scaleY: 1 },
  pelvis: { rotation: 0.05 },
  torso: { rotation: -0.05, y: -30 },
  neck: { rotation: 0, y: -40 },
  head: { rotation: 0, y: -14 },
  shoulder_L: { rotation: 0 },
  arm_L: { rotation: 0.7 },
  forearm_L: { rotation: -0.4 },
  hand_L: { rotation: 0.15 },
  shoulder_R: { rotation: 0 },
  arm_R: { rotation: -0.7 },
  forearm_R: { rotation: 0.4 },
  hand_R: { rotation: -0.15 },
  thigh_L: { rotation: -0.25 },
  leg_L: { rotation: 0.35 },
  foot_L: { rotation: -0.1 },
  thigh_R: { rotation: 0.25 },
  leg_R: { rotation: 0.35 },
  foot_R: { rotation: 0.1 },
  antenna_L_base: { rotation: -0.45 },
  antenna_R_base: { rotation: 0.45 },
};

// ========== 步态循环 ==========

function walkCycle(time: number): Record<string, PosePatch> {
  const t = time * 3.5;
  const sway = Math.sin(t * 0.5) * 0.035;
  const bob = Math.abs(Math.sin(t)) * -2.5;
  const headBob = Math.abs(Math.sin(t - 0.3)) * -1.5;
  const headSway = Math.sin(t * 0.5 - 0.4) * 0.018;

  const thighL = Math.sin(t) * 0.3;
  const thighR = Math.sin(t + Math.PI) * 0.3;
  const legL = Math.max(0, Math.sin(t + 0.3)) * 0.4;
  const legR = Math.max(0, Math.sin(t + Math.PI + 0.3)) * 0.4;
  const footL = Math.sin(t + 0.6) * 0.08;
  const footR = Math.sin(t + Math.PI + 0.6) * 0.08;

  const armSwingL = Math.sin(t + Math.PI) * 0.18 + Math.sin(t * 2 + Math.PI) * 0.025;
  const armSwingR = Math.sin(t) * 0.18 + Math.sin(t * 2) * 0.025;
  const forearmL = -0.08 + Math.sin(t + Math.PI + 0.5) * 0.06;
  const forearmR = 0.08 + Math.sin(t + 0.5) * 0.06;

  return {
    root: { rotation: sway, y: bob },
    torso: { rotation: -sway * 0.6 },
    head: { rotation: headSway, y: -14 + headBob },
    thigh_L: { rotation: thighL },
    leg_L: { rotation: legL },
    foot_L: { rotation: footL },
    thigh_R: { rotation: thighR },
    leg_R: { rotation: legR },
    foot_R: { rotation: footR },
    arm_L: { rotation: armSwingL + 0.05 },
    forearm_L: { rotation: forearmL },
    arm_R: { rotation: armSwingR - 0.05 },
    forearm_R: { rotation: forearmR },
  };
}

function runCycle(time: number): Record<string, PosePatch> {
  const t = time * 6;
  const bob = Math.abs(Math.sin(t)) * -4;
  const lean = 0.25;

  const thighL = Math.sin(t) * 0.7;
  const thighR = Math.sin(t + Math.PI) * 0.7;
  const legL = Math.max(0.05, Math.sin(t + 0.4)) * 0.85;
  const legR = Math.max(0.05, Math.sin(t + Math.PI + 0.4)) * 0.85;
  const footL = Math.sin(t + 0.8) * 0.22;
  const footR = Math.sin(t + Math.PI + 0.8) * 0.22;

  const armL = Math.sin(t + Math.PI) * 0.5 + 0.05;
  const armR = Math.sin(t) * 0.5 - 0.05;
  const forearmL = -0.25 + Math.sin(t + Math.PI + 0.3) * 0.12;
  const forearmR = 0.25 + Math.sin(t + 0.3) * 0.12;
  const antennaWind = Math.sin(t * 1.5) * 0.18;

  return {
    root: { rotation: lean + Math.sin(t * 0.5) * 0.02, y: bob },
    torso: { rotation: lean * 0.3 },
    head: { rotation: -lean * 0.2, y: -14 + bob * 0.5 },
    thigh_L: { rotation: thighL },
    leg_L: { rotation: legL },
    foot_L: { rotation: footL },
    thigh_R: { rotation: thighR },
    leg_R: { rotation: legR },
    foot_R: { rotation: footR },
    arm_L: { rotation: armL },
    forearm_L: { rotation: forearmL },
    arm_R: { rotation: armR },
    forearm_R: { rotation: forearmR },
    antenna_L_base: { rotation: -0.3 + antennaWind },
    antenna_R_base: { rotation: 0.3 - antennaWind },
  };
}

// ========== Idle 微动作系统 v3 ==========

function idleMicro(time: number): Record<string, PosePatch> {
  const cycle = Math.floor(time / 3.5) % 7;
  const t = time % 3.5;
  const breath = Math.sin(time * 2.5) * 0.015;

  // 所有 idle 都有呼吸基础
  const base = {
    torso: { rotation: breath, scaleY: 1 + breath * 0.5 },
    head: { rotation: breath * 0.3, y: -14 + breath * 2 },
  };

  switch (cycle) {
    case 0: // 左右张望
      return {
        ...base,
        head: { rotation: Math.sin(t * 1.8) * 0.12 + breath * 0.3, y: -14 + breath * 2 },
        neck: { rotation: Math.sin(t * 1.8) * 0.08 },
        antenna_L_base: { rotation: -0.2 + Math.sin(t * 2.5) * 0.08 },
        antenna_R_base: { rotation: 0.2 + Math.sin(t * 2.5) * 0.08 },
      };
    case 1: { // 挠头
      if (t < 1.2) {
        const st = Math.min(1, t / 0.25);
        const sp = t > 0.25 ? Math.sin((t - 0.25) * 12) * 0.25 : 0;
        return {
          ...base,
          arm_R: { rotation: (-1.6 * st) + sp },
          forearm_R: { rotation: (-0.7 * st) },
          head: { rotation: (-0.05 * st) + breath * 0.3, y: -14 + breath * 2 },
        };
      }
      return base;
    }
    case 2: { // 搓手/期待
      if (t < 1.8) {
        const f = Math.sin(t * 7) * 0.06;
        return {
          ...base,
          arm_L: { rotation: 0.25 + f },
          forearm_L: { rotation: -0.35 + f },
          arm_R: { rotation: -0.25 - f },
          forearm_R: { rotation: 0.35 - f },
          hand_L: { rotation: f * 1.5 },
          hand_R: { rotation: -f * 1.5 },
        };
      }
      return base;
    }
    case 3: { // 踮脚
      if (t < 1.0) {
        const tip = Math.sin(t * 3) * 0.12;
        return {
          ...base,
          root: { y: tip * -3, rotation: breath },
          foot_L: { rotation: -tip },
          foot_R: { rotation: -tip },
          thigh_L: { rotation: tip * 0.25 },
          thigh_R: { rotation: tip * 0.25 },
        };
      }
      return base;
    }
    case 4: { // 伸懒腰
      if (t < 2.2) {
        const st = Math.sin(Math.min(1, t / 0.4) * Math.PI * 0.5) * Math.sin(Math.max(0, (2.2 - t) / 1.8) * Math.PI * 0.5);
        return {
          ...base,
          root: { y: st * -4 + breath, scaleY: 1 + st * 0.04 },
          torso: { scaleY: 1 + st * 0.03 + breath * 0.5, rotation: breath },
          arm_L: { rotation: st * 0.55 },
          arm_R: { rotation: -st * 0.55 },
          head: { rotation: -st * 0.08 + breath * 0.3, y: -14 + breath * 2 },
          antenna_L_base: { rotation: -0.2 - st * 0.15 },
          antenna_R_base: { rotation: 0.2 + st * 0.15 },
        };
      }
      return base;
    }
    case 5: { // 抖耳朵
      if (t < 1.5) {
        const earShake = Math.sin(t * 10) * 0.12;
        return {
          ...base,
          head: { rotation: earShake * 0.3 + breath * 0.3, y: -14 + breath * 2 },
          antenna_L_base: { rotation: -0.2 + earShake },
          antenna_R_base: { rotation: 0.2 - earShake },
        };
      }
      return base;
    }
    case 6: { // 探头好奇
      if (t < 1.5) {
        const probe = Math.sin(Math.min(1, t / 0.5) * Math.PI * 0.5) * Math.sin(Math.max(0, (1.5 - t) / 1) * Math.PI * 0.5);
        return {
          ...base,
          neck: { rotation: probe * 0.15 },
          head: { rotation: probe * 0.25 + breath * 0.3, y: -14 + breath * 2 },
          torso: { rotation: -probe * 0.05 + breath, scaleY: 1 + breath * 0.5 },
        };
      }
      return base;
    }
    default:
      return base;
  }
}

// ========== 动作定义表 ==========

// P0: 新增系统角色姿态定义
const POSE_MONITOR: Record<string, PosePatch> = {
  ...POSE_IDLE,
  torso: { rotation: 0.05, y: -30 },
  head: { rotation: 0, y: -14 },
  arm_L: { rotation: -0.3 },
  arm_R: { rotation: 0.3 },
  antenna_L_base: { rotation: -0.3 },
  antenna_R_base: { rotation: 0.3 },
};

const POSE_OPERATE: Record<string, PosePatch> = {
  // 坐姿面对电脑
  ...POSE_SIT,
  head: { rotation: 0.05, y: -14 },  // 微微低头看屏幕
  neck: { rotation: 0.1, y: -38 },
  // 左手在键盘上
  arm_L: { rotation: 0.4 },
  forearm_L: { rotation: -1.0 },
  hand_L: { rotation: 0.15 },
  // 右手在键盘上
  arm_R: { rotation: -0.4 },
  forearm_R: { rotation: 1.0 },
  hand_R: { rotation: -0.15 },
  torso: { rotation: 0.08, y: -25, scaleX: 1.02, scaleY: 0.95 },
};

const POSE_THINK_DEEP: Record<string, PosePatch> = {
  // 坐在沙发上思考
  ...POSE_SIT,
  head: { rotation: 0.15, y: -14 },  // 头微微后仰
  neck: { rotation: 0.05, y: -38 },
  // 右手托腮/摸下巴
  arm_R: { rotation: -0.6 },
  forearm_R: { rotation: 0.8 },
  hand_R: { rotation: 0.3 },
  // 左手放腿上
  arm_L: { rotation: 0.2 },
  forearm_L: { rotation: -0.3 },
  hand_L: { rotation: 0 },
  torso: { rotation: -0.05, y: -25, scaleX: 1.02, scaleY: 0.95 },
  antenna_L_base: { rotation: -0.1 },
  antenna_R_base: { rotation: 0.1 },
};

const POSE_ALERT: Record<string, PosePatch> = {
  ...POSE_IDLE,
  torso: { rotation: 0, y: -30, scaleY: 1.02 },
  head: { rotation: 0, y: -14 },
  arm_L: { rotation: -0.7 },
  arm_R: { rotation: 0.7 },
  antenna_L_base: { rotation: -0.5 },
  antenna_R_base: { rotation: 0.5 },
};

const POSE_COMMUNE: Record<string, PosePatch> = {
  // 坐在沙发上交流
  ...POSE_SIT,
  torso: { rotation: 0.05, y: -25, scaleX: 1.02, scaleY: 0.95 },
  head: { rotation: 0.08, y: -14 },
  neck: { rotation: 0.05, y: -38 },
  // 左手自然张开（说话手势）
  arm_L: { rotation: 0.3 },
  forearm_L: { rotation: -0.6 },
  hand_L: { rotation: 0.2 },
  // 右手自然放腿上
  arm_R: { rotation: -0.15 },
  forearm_R: { rotation: 0.4 },
  hand_R: { rotation: 0 },
};

// 机制一-3: 道具交互姿态
const POSE_DRINK_COFFEE: Record<string, PosePatch> = {
  // 坐姿，双手捧杯
  ...POSE_SIT,
  head: { rotation: 0.12, y: -14 }, // 低头看杯
  neck: { rotation: 0.08, y: -38 },
  // 双手在身前捧杯
  arm_L: { rotation: -0.4, y: 5 },
  forearm_L: { rotation: -0.9 },
  hand_L: { rotation: 0.3, x: 2 },
  arm_R: { rotation: -0.5, y: 5 },
  forearm_R: { rotation: -0.7 },
  hand_R: { rotation: -0.2, x: -2 },
  // 微微前倾
  torso: { rotation: 0.06, y: -28, scaleX: 1, scaleY: 1 },
};

const POSE_WATER_PLANT: Record<string, PosePatch> = {
  // 站姿，右手前伸拿壶
  ...POSE_IDLE,
  head: { rotation: 0.1, y: -14 }, // 低头看植物
  neck: { rotation: 0.05, y: -40 },
  // 右手前伸（拿浇水壶）
  arm_R: { rotation: -0.6, y: 2 },
  forearm_R: { rotation: -0.4 },
  hand_R: { rotation: -0.3 },
  // 左手自然下垂
  arm_L: { rotation: 0.1 },
  forearm_L: { rotation: -0.1 },
  hand_L: { rotation: 0 },
  // 微微前倾
  torso: { rotation: 0.08, y: -30 },
};

const POSE_CHECK_TIME: Record<string, PosePatch> = {
  // 站姿，左手抬起到胸前（看表）
  ...POSE_IDLE,
  head: { rotation: -0.1, y: -14 }, // 低头看手腕
  neck: { rotation: -0.05, y: -40 },
  // 左手抬起到胸前
  arm_L: { rotation: -0.7, y: 3 },
  forearm_L: { rotation: -1.2 },
  hand_L: { rotation: 0.2 },
  // 右手自然下垂
  arm_R: { rotation: 0.05 },
  forearm_R: { rotation: -0.05 },
  hand_R: { rotation: 0 },
};

export const ACTION_DEFS: Record<AvatarAction, ActionDef> = {
  idle: { name: 'idle', basePose: POSE_IDLE, transitionTime: 0.5 },
  walk: { name: 'walk', basePose: POSE_IDLE, cycleSpeed: 1, cycleFn: walkCycle, transitionTime: 0.3 },
  run: { name: 'run', basePose: POSE_IDLE, cycleSpeed: 1, cycleFn: runCycle, transitionTime: 0.2 },
  sleep: { name: 'sleep', basePose: POSE_SLEEP, transitionTime: 1.0 },
  sit: { name: 'sit', basePose: POSE_SIT, transitionTime: 0.6 },
  lie: { name: 'lie', basePose: POSE_LIE, transitionTime: 0.8 },
  wave: { name: 'wave', basePose: POSE_WAVE, transitionTime: 0.4 },
  jump: { name: 'jump', basePose: POSE_JUMP, transitionTime: 0.2 },
  dance: { name: 'dance', basePose: POSE_DANCE, transitionTime: 0.4 },
  // P0: 新增系统角色动作
  monitor: { name: 'monitor', basePose: POSE_MONITOR, transitionTime: 0.4 },
  operate: { name: 'operate', basePose: POSE_OPERATE, transitionTime: 0.4 },
  think_deep: { name: 'think_deep', basePose: POSE_THINK_DEEP, transitionTime: 0.5 },
  recall: { name: 'recall', basePose: POSE_THINK_DEEP, transitionTime: 0.5 },
  alert: { name: 'alert', basePose: POSE_ALERT, transitionTime: 0.2 },
  scan: { name: 'scan', basePose: POSE_MONITOR, transitionTime: 0.4 },
  commune: { name: 'commune', basePose: POSE_COMMUNE, transitionTime: 0.4 },
  report: { name: 'report', basePose: POSE_WAVE, transitionTime: 0.4 },
  console: { name: 'console', basePose: POSE_OPERATE, transitionTime: 0.4 },
  reach_out: { name: 'reach_out', basePose: POSE_WAVE, transitionTime: 0.3 },
  // 机制一-3: 道具交互
  drink_coffee: { name: 'drink_coffee', basePose: POSE_DRINK_COFFEE, transitionTime: 0.4 },
  water_plant: { name: 'water_plant', basePose: POSE_WATER_PLANT, transitionTime: 0.4 },
  check_time: { name: 'check_time', basePose: POSE_CHECK_TIME, transitionTime: 0.3 },
};

export function computeActionPose(action: AvatarAction, time: number): Record<string, PosePatch> {
  const def = ACTION_DEFS[action];
  if (!def) return POSE_IDLE;

  const pose: Record<string, PosePatch> = {};
  for (const [id, patch] of Object.entries(def.basePose)) {
    pose[id] = { ...patch };
  }

  if (def.cycleFn) {
    const cycle = def.cycleFn(time);
    for (const [id, patch] of Object.entries(cycle)) {
      if (pose[id]) {
        if (patch.rotation !== undefined) pose[id].rotation = (pose[id].rotation ?? 0) + patch.rotation;
        if (patch.x !== undefined) pose[id].x = (pose[id].x ?? 0) + patch.x;
        if (patch.y !== undefined) pose[id].y = (pose[id].y ?? 0) + patch.y;
        if (patch.scaleX !== undefined) pose[id].scaleX = (pose[id].scaleX ?? 1) * patch.scaleX;
        if (patch.scaleY !== undefined) pose[id].scaleY = (pose[id].scaleY ?? 1) * patch.scaleY;
      } else {
        pose[id] = { ...patch };
      }
    }
  }

  if (action === 'wave') {
    const waveT = time * 4;
    pose.forearm_R = { rotation: -0.2 + Math.sin(waveT) * 0.35 };
    pose.hand_R = { rotation: 0.15 + Math.sin(waveT) * 0.2 };
    pose.root = { rotation: Math.sin(waveT * 0.5) * 0.025 };
    pose.head = { rotation: Math.sin(waveT * 0.3) * 0.04, y: -14 };
  }

  if (action === 'dance') {
    const danceT = time * 2.5;
    const phase = Math.floor(time / 3) % 3;
    if (phase === 0) {
      pose.root = { rotation: Math.sin(danceT) * 0.05, y: Math.abs(Math.sin(danceT * 2)) * -3 };
      pose.arm_L = { rotation: 0.7 + Math.sin(danceT + 1) * 0.3 };
      pose.arm_R = { rotation: -0.7 + Math.sin(danceT) * 0.3 };
    } else if (phase === 1) {
      pose.root = { rotation: Math.sin(danceT * 0.5) * 0.12 };
      pose.arm_L = { rotation: 1.0 + Math.sin(danceT) * 0.2 };
      pose.arm_R = { rotation: -1.0 + Math.sin(danceT) * 0.2 };
      pose.head = { rotation: Math.sin(danceT * 0.7) * 0.08, y: -14 };
    } else {
      pose.root = { y: Math.abs(Math.sin(danceT * 2)) * -5, scaleY: 1 + Math.sin(danceT * 2) * 0.03 };
      pose.arm_L = { rotation: -1.5 + Math.sin(danceT) * 0.2 };
      pose.arm_R = { rotation: 1.5 + Math.sin(danceT) * 0.2 };
    }
    pose.torso = { rotation: Math.sin(danceT * 0.5) * 0.04, y: -30 };
  }

  if (action === 'idle') {
    const micro = idleMicro(time);
    for (const [id, patch] of Object.entries(micro)) {
      if (pose[id]) {
        if (patch.rotation !== undefined) pose[id].rotation = (pose[id].rotation ?? 0) + (patch.rotation ?? 0);
        if (patch.x !== undefined) pose[id].x = (pose[id].x ?? 0) + (patch.x ?? 0);
        if (patch.y !== undefined) pose[id].y = (pose[id].y ?? 0) + (patch.y ?? 0);
        if (patch.scaleX !== undefined) pose[id].scaleX = (pose[id].scaleX ?? 1) * (patch.scaleX ?? 1);
        if (patch.scaleY !== undefined) pose[id].scaleY = (pose[id].scaleY ?? 1) * (patch.scaleY ?? 1);
      } else {
        pose[id] = { ...patch };
      }
    }
  }

  // P0: 系统角色动作的动态表现
  if (action === 'monitor') {
    const scanT = time * 3;
    pose.head = { rotation: Math.sin(scanT) * 0.3, y: -14 };
    pose.neck = { rotation: Math.sin(scanT) * 0.15, y: -40 };
  }

  if (action === 'operate') {
    const opT = time * 8;
    pose.arm_L = { rotation: -1.5 + Math.sin(opT) * 0.2 };
    pose.forearm_L = { rotation: -0.5 + Math.cos(opT * 1.3) * 0.15 };
    pose.hand_L = { rotation: Math.sin(opT * 2) * 0.1 };
    pose.arm_R = { rotation: -1.2 + Math.cos(opT * 0.8) * 0.15 };
    pose.forearm_R = { rotation: -0.3 + Math.sin(opT * 1.1) * 0.1 };
    pose.hand_R = { rotation: Math.cos(opT * 1.5) * 0.1 };
  }

  if (action === 'think_deep') {
    const thinkT = time * 0.8;
    pose.head = { rotation: 0.1 + Math.sin(thinkT) * 0.05, y: -14 };
    pose.arm_R = { rotation: -2.5 + Math.sin(thinkT * 0.5) * 0.03 };
  }

  if (action === 'alert') {
    const alertT = time * 6;
    pose.head = { rotation: Math.sin(alertT) * 0.4, y: -14 };
    pose.torso = { rotation: 0, y: -30, scaleY: 1.02 + Math.sin(alertT * 2) * 0.01 };
    pose.arm_L = { rotation: -0.7 + Math.sin(alertT * 1.5) * 0.1 };
    pose.arm_R = { rotation: 0.7 + Math.cos(alertT * 1.5) * 0.1 };
    pose.antenna_L_base = { rotation: -0.5 + Math.sin(alertT * 3) * 0.1 };
    pose.antenna_R_base = { rotation: 0.5 + Math.cos(alertT * 3) * 0.1 };
  }

  if (action === 'commune') {
    const comT = time * 1.5;
    pose.head = { rotation: 0.05 + Math.sin(comT) * 0.03, y: -14 };
    pose.torso = { rotation: 0.08 + Math.sin(comT * 0.5) * 0.02, y: -30 };
    pose.neck = { rotation: 0.05, y: -40 };
  }

  if (action === 'reach_out') {
    const reachT = time * 2;
    pose.arm_R = { rotation: -2.8 + Math.sin(reachT) * 0.1 };
    pose.forearm_R = { rotation: -0.2 + Math.sin(reachT * 1.5) * 0.1 };
    pose.hand_R = { rotation: Math.sin(reachT) * 0.15 };
  }

  return pose;
}

export function applyEmotionToPose(
  pose: Record<string, PosePatch>,
  emotion: string
): Record<string, PosePatch> {
  const result: Record<string, PosePatch> = {};
  for (const [id, patch] of Object.entries(pose)) {
    result[id] = { ...patch };
  }

  switch (emotion) {
    case 'happy':
    case 'excited': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) - 0.12 };
      result.torso = { ...(result.torso ?? {}), rotation: (result.torso?.rotation ?? 0) + 0.04 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: (result.antenna_L_base?.rotation ?? -0.2) - 0.1 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: (result.antenna_R_base?.rotation ?? 0.2) + 0.1 };
      break;
    }
    case 'sad': {
      // 耷拉脑袋：更深的低头 + 肩膀下垂
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) + 0.32 };
      result.torso = { ...(result.torso ?? {}), rotation: (result.torso?.rotation ?? 0) - 0.08 };
      result.shoulder_L = { ...(result.shoulder_L ?? {}), rotation: (result.shoulder_L?.rotation ?? 0) + 0.22 };
      result.shoulder_R = { ...(result.shoulder_R ?? {}), rotation: (result.shoulder_R?.rotation ?? 0) - 0.22 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: 0.08 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: -0.08 };
      break;
    }
    case 'waiting': {
      // 等待：头部左右张望，左手抬起到胸前（看表）
      const waitSway = Math.sin(performance.now() * 0.002) * 0.1;
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) + waitSway };
      result.arm_L = { ...(result.arm_L ?? {}), rotation: -0.8 + waitSway * 0.3 };
      result.forearm_L = { ...(result.forearm_L ?? {}), rotation: -1.0 };
      result.hand_L = { ...(result.hand_L ?? {}), rotation: 0.2 };
      result.torso = { ...(result.torso ?? {}), rotation: (result.torso?.rotation ?? 0) + waitSway * 0.3 };
      break;
    }
    case 'angry': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) - 0.06 };
      result.torso = { ...(result.torso ?? {}), rotation: (result.torso?.rotation ?? 0) + 0.06, scaleX: (result.torso?.scaleX ?? 1) * 1.03 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: -0.5 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: 0.5 };
      break;
    }
    case 'surprised': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) - 0.18 };
      result.torso = { ...(result.torso ?? {}), scaleY: (result.torso?.scaleY ?? 1) * 0.97, scaleX: (result.torso?.scaleX ?? 1) * 1.02 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: -0.55 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: 0.55 };
      break;
    }
    case 'thinking': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) + 0.22 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: -0.35 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: 0.15 };
      result.arm_R = { ...(result.arm_R ?? {}), rotation: (result.arm_R?.rotation ?? 0) - 0.4 };
      result.forearm_R = { ...(result.forearm_R ?? {}), rotation: (result.forearm_R?.rotation ?? 0) + 0.3 };
      break;
    }
    case 'sleepy': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) + 0.08 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: 0.1 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: -0.1 };
      break;
    }
    case 'embarrassed': {
      result.head = { ...(result.head ?? {}), rotation: (result.head?.rotation ?? 0) - 0.08 };
      result.torso = { ...(result.torso ?? {}), rotation: (result.torso?.rotation ?? 0) + 0.03 };
      result.antenna_L_base = { ...(result.antenna_L_base ?? {}), rotation: -0.15 };
      result.antenna_R_base = { ...(result.antenna_R_base ?? {}), rotation: 0.15 };
      break;
    }
    default:
      break;
  }

  return result;
}

export function getSquashStretch(
  action: AvatarAction,
  actionTime: number,
  clickIntensity: number
): { scaleX: number; scaleY: number } {
  let sx = 1, sy = 1;

  if (action === 'jump') {
    if (actionTime < 0.15) {
      const t = actionTime / 0.15;
      sx = 1 + t * 0.1;
      sy = 1 - t * 0.08;
    } else if (actionTime < 0.4) {
      const t = (actionTime - 0.15) / 0.25;
      sx = 1.1 - t * 0.15;
      sy = 0.92 + t * 0.12;
    } else if (actionTime < 0.7) {
      sx = 0.95;
      sy = 1.04;
    } else {
      const t = (actionTime - 0.7) / 0.3;
      const bounce = Math.sin(t * Math.PI) * 0.08;
      sx = 1 + bounce;
      sy = 1 - bounce * 0.7;
    }
  }

  if (clickIntensity > 0.01) {
    sx *= 1 + clickIntensity * 0.12;
    sy *= 1 - clickIntensity * 0.08;
  }

  return { scaleX: sx, scaleY: sy };
}
