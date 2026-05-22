/**
 * 行为树系统 — 游戏级 AI 决策
 * Selector: 选择第一个成功的子节点
 * Sequence: 顺序执行所有子节点，一个失败就返回失败
 * Action: 具体动作，返回 Success/Running/Failure
 */

import type { DigitalSoul, Perception } from './DigitalSoul';
import type { RoamingState } from './RoamingEngine';

export type BTStatus = 'success' | 'running' | 'failure';

export interface BTContext {
  soul: DigitalSoul;
  perception: Perception;
  roaming: RoamingState;
  time: number;        // 当前行为持续时间
  currentAction?: string;  // 当前执行的动作名称（输出）
}

export interface BTNode {
  tick(ctx: BTContext): BTStatus;
  reset?(): void;
}

// ===== 组合节点 =====

/** Selector: 顺序执行子节点，遇到第一个成功就返回 */
export class Selector implements BTNode {
  children: BTNode[];
  private runningIndex = -1;

  constructor(children: BTNode[]) { this.children = children; }

  tick(ctx: BTContext): BTStatus {
    const start = this.runningIndex >= 0 ? this.runningIndex : 0;
    for (let i = start; i < this.children.length; i++) {
      const status = this.children[i].tick(ctx);
      if (status === 'running') {
        this.runningIndex = i;
        return 'running';
      }
      this.runningIndex = -1;
      if (status === 'success') return 'success';
    }
    return 'failure';
  }

  reset() {
    this.runningIndex = -1;
    for (const c of this.children) c.reset?.();
  }
}

/** Sequence: 顺序执行子节点，全部成功才返回成功 */
export class Sequence implements BTNode {
  children: BTNode[];
  private runningIndex = -1;

  constructor(children: BTNode[]) { this.children = children; }

  tick(ctx: BTContext): BTStatus {
    const start = this.runningIndex >= 0 ? this.runningIndex : 0;
    for (let i = start; i < this.children.length; i++) {
      const status = this.children[i].tick(ctx);
      if (status === 'running') {
        this.runningIndex = i;
        return 'running';
      }
      this.runningIndex = -1;
      if (status === 'failure') return 'failure';
    }
    return 'success';
  }

  reset() {
    this.runningIndex = -1;
    for (const c of this.children) c.reset?.();
  }
}

// ===== 条件节点 =====

export class Condition implements BTNode {
  private fn: (ctx: BTContext) => boolean;

  constructor(fn: (ctx: BTContext) => boolean) { this.fn = fn; }

  tick(ctx: BTContext): BTStatus {
    return this.fn(ctx) ? 'success' : 'failure';
  }
}

// ===== 动作节点 =====

export class Action implements BTNode {
  name: string;
  private fn: (ctx: BTContext) => BTStatus;

  constructor(name: string, fn: (ctx: BTContext) => BTStatus) {
    this.name = name;
    this.fn = fn;
  }

  tick(ctx: BTContext): BTStatus {
    ctx.currentAction = this.name;
    return this.fn(ctx);
  }
}

/** 持续一段时间的动作 */
export class WaitAction implements BTNode {
  name: string;
  duration: number;
  private elapsed = 0;

  constructor(name: string, duration: number) {
    this.name = name;
    this.duration = duration;
  }

  tick(_ctx: BTContext): BTStatus {
    this.elapsed += 0.016;
    if (this.elapsed >= this.duration) {
      this.elapsed = 0;
      return 'success';
    }
    return 'running';
  }

  reset() { this.elapsed = 0; }
}

// ===== Avatar 具体行为节点 =====

export function createAvatarBehaviorTree(): BTNode {
  return new Selector([
    // 优先级 1: 用户需要我（在聊天且 AI 收到消息）
    new Sequence([
      new Condition(ctx => ctx.perception.userTab === 'chat' && ctx.perception.aiState !== 'idle'),
      new Action('approach_user', ctx => {
        ctx.roaming.targetX = ctx.perception.mouseX - 100;
        ctx.roaming.targetY = ctx.perception.mouseY - 150;
        return 'success';
      }),
    ]),

    // 优先级 2: 用户回来了（长时间离开后）
    new Sequence([
      new Condition(ctx => ctx.soul.hasRecentMemoryOfType('user_back', 5000)),
      new Action('welcome_user', ctx => {
        ctx.roaming.targetX = ctx.perception.mouseX - 80;
        ctx.roaming.targetY = ctx.perception.mouseY - 120;
        return 'success';
      }),
    ]),

    // 优先级 3: 我很兴奋（高唤醒）
    new Sequence([
      new Condition(ctx => ctx.soul.emotion.arousal > 0.7 && ctx.soul.emotion.valence > 0.3),
      new Selector([
        new Sequence([
          new Condition(ctx => ctx.soul.physiology.energy > 40),
          new Action('express_joy', ctx => {
            // 随机选择：跳、跑、转圈
            ctx.roaming.targetX = ctx.roaming.x + (Math.random() - 0.5) * 200;
            ctx.roaming.targetY = ctx.roaming.y + (Math.random() - 0.5) * 200;
            return 'running';
          }),
        ]),
        new Action('calm_down', () => 'success'),
      ]),
    ]),

    // 优先级 4: 我很累
    new Sequence([
      new Condition(ctx => ctx.soul.physiology.energy < 25),
      new Selector([
        new Sequence([
          new Condition(ctx => ctx.time > 3),
          new Action('fall_asleep', () => 'success'),
        ]),
        new Action('yawn_and_rest', () => 'running'),
      ]),
    ]),

    // 优先级 5: 用户长时间不理我
    new Sequence([
      new Condition(ctx => ctx.perception.userIdleMs > 20000 && ctx.soul.physiology.curiosity > 40),
      new Selector([
        new Sequence([
          new Condition(ctx => ctx.soul.physiology.bond > 50),
          new Action('seek_attention', ctx => {
            ctx.roaming.targetX = ctx.perception.mouseX - 60;
            ctx.roaming.targetY = ctx.perception.mouseY - 100;
            return 'running';
          }),
        ]),
        new Action('explore_bored', ctx => {
          ctx.roaming.targetX = Math.random() * ctx.perception.screenW;
          ctx.roaming.targetY = Math.random() * ctx.perception.screenH;
          return 'running';
        }),
      ]),
    ]),

    // 优先级 6: 好奇心驱动探索
    new Sequence([
      new Condition(ctx => ctx.soul.physiology.curiosity > 60),
      new Action('explore', ctx => {
        if (Math.random() < 0.02) {
          ctx.roaming.targetX = 50 + Math.random() * (ctx.perception.screenW - 250);
          ctx.roaming.targetY = 50 + Math.random() * (ctx.perception.screenH - 300);
        }
        return 'running';
      }),
    ]),

    // 默认: 待机
    new Action('idle', () => 'running'),
  ]);
}

// 扩展 DigitalSoul 类型以支持 hasRecentMemoryOfType
declare module './DigitalSoul' {
  interface DigitalSoul {
    hasRecentMemoryOfType(type: string, withinMs: number): boolean;
  }
}

// 实际实现
import { DigitalSoul as DS } from './DigitalSoul';
(DS.prototype as any).hasRecentMemoryOfType = function(type: string, withinMs: number): boolean {
  const now = Date.now();
  return this.memories.some((m: { type: string; timestamp: number; intensity: number }) => m.type === type && (now - m.timestamp) < withinMs && m.intensity > 0.2);
};
