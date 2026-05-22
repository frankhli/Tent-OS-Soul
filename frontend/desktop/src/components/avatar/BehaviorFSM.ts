/**
 * 自主行为状态机
 * Avatar 有自己的"想法"和决策能力
 */

import type { RoamingState } from './RoamingEngine';
import { setRandomTarget, setTargetToMouse, hasArrived } from './RoamingEngine';

export type BehaviorState = 'idle' | 'wander' | 'approach' | 'rest' | 'sleep' | 'dance' | 'run_around' | 'jump_around';

interface FSMConfig {
  screenW: number;
  screenH: number;
  onActionChange?: (action: string) => void;
}

export class BehaviorFSM {
  state: BehaviorState = 'idle';
  stateTimer = 0;
  private config: FSMConfig;
  private mouseX = 0;
  private mouseY = 0;
  private lastUserActivity = Date.now();
  private emotion = 'neutral';
  private wanderTargets = 0;

  constructor(config: FSMConfig) {
    this.config = config;
  }

  setMouse(x: number, y: number) {
    this.mouseX = x;
    this.mouseY = y;
  }

  setEmotion(emotion: string) {
    if (this.emotion !== emotion) {
      this.emotion = emotion;
      this.onEmotionChange(emotion);
    }
  }

  onUserActivity() {
    this.lastUserActivity = Date.now();
    if (this.state === 'sleep') {
      this.transitionTo('idle');
    }
  }

  onUserSpeak() {
    this.onUserActivity();
    if (this.state !== 'approach') {
      this.transitionTo('approach');
    }
  }

  private onEmotionChange(emotion: string) {
    switch (emotion) {
      case 'happy':
      case 'excited':
        if (Math.random() > 0.5) this.transitionTo('dance');
        break;
      case 'sad':
        this.transitionTo('rest');
        break;
      case 'angry':
        this.transitionTo('run_around');
        break;
      case 'surprised':
        this.transitionTo('jump_around');
        break;
    }
  }

  private transitionTo(newState: BehaviorState) {
    if (this.state === newState) return;
    this.state = newState;
    this.stateTimer = 0;
    this.wanderTargets = 0;

    // 状态切换时触发动作
    const actionMap: Record<BehaviorState, string> = {
      idle: 'idle',
      wander: 'walk',
      approach: 'walk',
      rest: 'sit',
      sleep: 'sleep',
      dance: 'dance',
      run_around: 'run',
      jump_around: 'jump',
    };
    this.config.onActionChange?.(actionMap[newState] ?? 'idle');
  }

  update(roaming: RoamingState, dt: number): void {
    this.stateTimer += dt;
    const idleTime = (Date.now() - this.lastUserActivity) / 1000;

    switch (this.state) {
      case 'idle': {
        // 站立呼吸，偶尔转头
        if (idleTime > 30) {
          this.transitionTo('sleep');
        } else if (this.stateTimer > 4 + Math.random() * 4) {
          // 4-8秒后决定下一步
          const r = Math.random();
          if (r < 0.4) this.transitionTo('wander');
          else if (r < 0.6) this.transitionTo('rest');
          else this.stateTimer = 0; // 继续 idle
        }
        break;
      }

      case 'wander': {
        // 随机走到屏幕某处
        if (this.wanderTargets === 0 || hasArrived(roaming, 30)) {
          if (this.wanderTargets >= 2 + Math.floor(Math.random() * 3)) {
            this.transitionTo('idle');
          } else {
            setRandomTarget(roaming, this.config.screenW, this.config.screenH);
            this.wanderTargets++;
          }
        }
        break;
      }

      case 'approach': {
        // 走向用户（鼠标位置）
        setTargetToMouse(roaming, this.mouseX, this.mouseY);
        if (hasArrived(roaming, 40)) {
          this.transitionTo('idle');
        } else if (this.stateTimer > 8) {
          // 太久没走到，放弃
          this.transitionTo('idle');
        }
        break;
      }

      case 'rest': {
        // 坐着休息
        if (this.stateTimer > 5 + Math.random() * 5) {
          this.transitionTo('idle');
        }
        break;
      }

      case 'sleep': {
        // 长时间无操作，睡觉
        if (idleTime < 5) {
          this.transitionTo('idle');
        }
        break;
      }

      case 'dance': {
        // 跳舞持续一段时间
        if (this.stateTimer > 5 + Math.random() * 5) {
          this.transitionTo('idle');
        }
        break;
      }

      case 'run_around': {
        // 快速跑来跑去（生气时）
        if (hasArrived(roaming, 30)) {
          if (this.wanderTargets >= 4) {
            this.transitionTo('idle');
          } else {
            setRandomTarget(roaming, this.config.screenW, this.config.screenH);
            this.wanderTargets++;
          }
        }
        break;
      }

      case 'jump_around': {
        // 跳来跳去（惊讶时）
        if (this.stateTimer > 0.8) {
          if (this.wanderTargets >= 3) {
            this.transitionTo('idle');
          } else {
            setRandomTarget(roaming, this.config.screenW, this.config.screenH);
            this.wanderTargets++;
            this.stateTimer = 0;
          }
        }
        break;
      }
    }
  }
}
