/**
 * ArrivalBehavior — 到达行为系统
 * 提前减速 → 停下 → 环顾左右 → 进入 idle
 */

export type ArrivalPhase = 'approaching' | 'decelerating' | 'arrived' | 'looking_around' | 'settled';

export interface ArrivalState {
  phase: ArrivalPhase;
  phaseTimer: number;
  lookCount: number;
  maxLooks: number;
  arrivalX: number;
  arrivalY: number;
  baseHeadAngle: number;
}

export function createArrivalState(): ArrivalState {
  return {
    phase: 'approaching',
    phaseTimer: 0,
    lookCount: 0,
    maxLooks: 3,
    arrivalX: 0,
    arrivalY: 0,
    baseHeadAngle: 0,
  };
}

/** 开始到达行为 */
export function startArrival(
  state: ArrivalState,
  x: number,
  y: number,
  headAngle: number
): void {
  state.phase = 'approaching';
  state.phaseTimer = 0;
  state.lookCount = 0;
  state.arrivalX = x;
  state.arrivalY = y;
  state.baseHeadAngle = headAngle;
}

/** 更新到达行为 */
export function updateArrival(
  state: ArrivalState,
  dt: number,
  distToTarget: number
): { headLookAngle: number; isComplete: boolean } {
  state.phaseTimer += dt;

  switch (state.phase) {
    case 'approaching':
      // 距离目标 50px 内开始减速
      if (distToTarget < 50) {
        state.phase = 'decelerating';
        state.phaseTimer = 0;
      }
      return { headLookAngle: 0, isComplete: false };

    case 'decelerating':
      // 减速持续 0.5s 或距离 < 5px
      if (state.phaseTimer > 0.5 || distToTarget < 5) {
        state.phase = 'arrived';
        state.phaseTimer = 0;
      }
      return { headLookAngle: 0, isComplete: false };

    case 'arrived':
      // 到达后停顿 0.3s，然后开始环顾
      if (state.phaseTimer > 0.3) {
        state.phase = 'looking_around';
        state.phaseTimer = 0;
        state.lookCount = 0;
      }
      return { headLookAngle: 0, isComplete: false };

    case 'looking_around': {
      // 环顾：左右转头 2-3 次
      const lookCycle = 0.6; // 每次转头用时
      const progress = state.phaseTimer / lookCycle;

      let lookAngle = 0;
      if (state.lookCount < state.maxLooks) {
        // 左右交替看
        const dir = state.lookCount % 2 === 0 ? -1 : 1;
        if (progress < 0.5) {
          // 转头过去
          lookAngle = dir * 0.5 * (progress * 2);
        } else {
          // 转回来
          lookAngle = dir * 0.5 * ((1 - progress) * 2);
        }

        if (progress >= 1) {
          state.lookCount++;
          state.phaseTimer = 0;
        }
      } else {
        state.phase = 'settled';
        state.phaseTimer = 0;
      }

      return { headLookAngle: lookAngle, isComplete: false };
    }

    case 'settled':
      //  settled 状态持续一段时间后自动重置
      if (state.phaseTimer > 2) {
        return { headLookAngle: 0, isComplete: true };
      }
      return { headLookAngle: 0, isComplete: false };

    default:
      return { headLookAngle: 0, isComplete: true };
  }
}

/** 获取到达状态描述 */
export function getArrivalDescription(state: ArrivalState): string {
  switch (state.phase) {
    case 'approaching': return '正在接近';
    case 'decelerating': return '开始减速';
    case 'arrived': return '停下了';
    case 'looking_around': return '左右看看';
    case 'settled': return '待在这里';
    default: return '';
  }
}

/** 检查是否正在到达过程中 */
export function isArriving(state: ArrivalState): boolean {
  return state.phase !== 'approaching' && state.phase !== 'settled';
}
