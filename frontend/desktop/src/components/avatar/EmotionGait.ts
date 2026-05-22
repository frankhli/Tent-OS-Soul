/**
 * EmotionGait — 情绪步态系统
 * 每种情绪有独特的移动特征：速度/步频/振幅/姿态
 */

export interface GaitParams {
  speedMultiplier: number;     // 速度倍率
  stepFrequency: number;       // 步频（步/秒）
  bounceAmplitude: number;     // 弹跳振幅
  armSwing: number;            // 手臂摆动幅度
  headBob: number;             // 头部上下摆动
  shoulderTension: number;     // 肩膀紧张度
  dragFactor: number;          // 拖沓系数（高=拖沓）
}

/** 情绪步态配置 */
export const EMOTION_GAITS: Record<string, GaitParams> = {
  neutral: {
    speedMultiplier: 1.0,
    stepFrequency: 2.0,
    bounceAmplitude: 2,
    armSwing: 0.3,
    headBob: 1,
    shoulderTension: 0,
    dragFactor: 0,
  },
  happy: {
    speedMultiplier: 1.2,
    stepFrequency: 2.5,
    bounceAmplitude: 5,
    armSwing: 0.5,
    headBob: 2,
    shoulderTension: 0,
    dragFactor: 0,
  },
  excited: {
    speedMultiplier: 1.5,
    stepFrequency: 3.0,
    bounceAmplitude: 8,
    armSwing: 0.7,
    headBob: 3,
    shoulderTension: 0.1,
    dragFactor: 0,
  },
  sad: {
    speedMultiplier: 0.6,
    stepFrequency: 1.2,
    bounceAmplitude: 0,
    armSwing: 0.1,
    headBob: 0.3,
    shoulderTension: 0.2,
    dragFactor: 0.4,
  },
  angry: {
    speedMultiplier: 1.3,
    stepFrequency: 2.8,
    bounceAmplitude: 3,
    armSwing: 0.4,
    headBob: 1.5,
    shoulderTension: 0.5,
    dragFactor: 0,
  },
  surprised: {
    speedMultiplier: 0.3, // 先停住
    stepFrequency: 0,
    bounceAmplitude: 0,
    armSwing: 0,
    headBob: 0,
    shoulderTension: 0.3,
    dragFactor: 0,
  },
  tired: {
    speedMultiplier: 0.4,
    stepFrequency: 1.0,
    bounceAmplitude: 0.5,
    armSwing: 0.05,
    headBob: 0.2,
    shoulderTension: 0.1,
    dragFactor: 0.3,
  },
  thinking: {
    speedMultiplier: 0.2,
    stepFrequency: 0.8,
    bounceAmplitude: 0,
    armSwing: 0.05,
    headBob: 0.5,
    shoulderTension: 0.1,
    dragFactor: 0.1,
  },
  sleepy: {
    speedMultiplier: 0.2,
    stepFrequency: 0.5,
    bounceAmplitude: 0,
    armSwing: 0,
    headBob: 0.1,
    shoulderTension: 0,
    dragFactor: 0.5,
  },
};

/** 获取情绪的步态参数 */
export function getGait(emotion: string): GaitParams {
  return EMOTION_GAITS[emotion] || EMOTION_GAITS.neutral;
}

/** 计算步态动画相位 */
export function computeGaitPhase(
  time: number,
  speed: number,
  gait: GaitParams
): {
  walkCycle: number;      // 0~1，步态周期
  isLeftStep: boolean;    // 左脚是否着地
  bodyBounce: number;     // 身体上下弹跳
  armLAngle: number;      // 左臂摆动角度
  armRAngle: number;      // 右臂摆动角度
  headTilt: number;       // 头部倾斜
} {
  const cycle = (time * gait.stepFrequency + speed * 0.01) % 1;
  const isLeftStep = cycle < 0.5;

  // 弹跳：双脚着地时高，单脚着地时低
  const bounce = Math.sin(cycle * Math.PI * 2) * gait.bounceAmplitude * 0.5 + gait.bounceAmplitude * 0.5;
  const bodyBounce = Math.max(0, bounce);

  // 手臂摆动（与腿相反）
  const armSwing = Math.sin(cycle * Math.PI * 2) * gait.armSwing;
  const armLAngle = isLeftStep ? armSwing : -armSwing;
  const armRAngle = isLeftStep ? -armSwing : armSwing;

  // 头部上下（与弹跳同步但滞后）
  const headTilt = Math.sin((cycle - 0.1) * Math.PI * 2) * gait.headBob * 0.02;

  return {
    walkCycle: cycle,
    isLeftStep,
    bodyBounce,
    armLAngle,
    armRAngle,
    headTilt,
  };
}

/** 将步态应用到骨骼姿态 */
export function applyGaitToPose(
  basePose: Record<string, { x: number; y: number; rotation: number }>,
  gaitPhase: ReturnType<typeof computeGaitPhase>,
  gait: GaitParams
): Record<string, { x: number; y: number; rotation: number }> {
  const pose = { ...basePose };

  // 身体上下弹跳
  if (pose.torso) {
    pose.torso = {
      ...pose.torso,
      y: pose.torso.y - gaitPhase.bodyBounce,
    };
  }

  // 头部倾斜
  if (pose.head) {
    pose.head = {
      ...pose.head,
      y: pose.head.y - gaitPhase.bodyBounce * 0.7,
      rotation: pose.head.rotation + gaitPhase.headTilt,
    };
  }

  // 肩膀紧张度（肩膀抬高）
  const shoulderOffset = gait.shoulderTension * 3;
  if (pose.shoulder_L) {
    pose.shoulder_L = {
      ...pose.shoulder_L,
      y: pose.shoulder_L.y - shoulderOffset,
    };
  }
  if (pose.shoulder_R) {
    pose.shoulder_R = {
      ...pose.shoulder_R,
      y: pose.shoulder_R.y - shoulderOffset,
    };
  }

  // 手臂摆动
  if (pose.arm_L) {
    pose.arm_L = {
      ...pose.arm_L,
      rotation: pose.arm_L.rotation + gaitPhase.armLAngle,
    };
  }
  if (pose.arm_R) {
    pose.arm_R = {
      ...pose.arm_R,
      rotation: pose.arm_R.rotation + gaitPhase.armRAngle,
    };
  }

  // 拖沓：腿拖地（小腿角度减小）
  if (gait.dragFactor > 0 && pose.leg_L) {
    pose.leg_L = {
      ...pose.leg_L,
      rotation: pose.leg_L.rotation * (1 - gait.dragFactor),
    };
  }
  if (gait.dragFactor > 0 && pose.leg_R) {
    pose.leg_R = {
      ...pose.leg_R,
      rotation: pose.leg_R.rotation * (1 - gait.dragFactor),
    };
  }

  return pose;
}

/** 情绪步态描述 */
export function getGaitDescription(emotion: string): string {
  switch (emotion) {
    case 'happy': return '轻快地跳着走';
    case 'excited': return '大步流星地跑';
    case 'sad': return '低着头拖沓地走';
    case 'angry': return '重重地快步走';
    case 'surprised': return '吓得停住了';
    case 'tired': return '摇摇晃晃地走';
    case 'thinking': return '一边踱步一边想';
    case 'sleepy': return '迷迷糊糊地走';
    default: return '正常走路';
  }
}
