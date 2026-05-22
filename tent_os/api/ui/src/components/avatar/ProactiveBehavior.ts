/**
 * ProactiveBehavior — 主动行为库
 * Avatar 不再只是被动响应，而是主动做自己的事、主动找用户
 */

export type ProactiveAction =
  // P0: 删除宠物行为，替换为系统角色行为
  | 'system_scan'        // 系统扫描：目光扫视，检查状态
  | 'sensor_check'       // 传感器检查
  | 'memory_organize'    // 记忆整理：沉思姿态
  | 'predictive_check'   // 预测性检查
  | 'self_diagnostic'    // 自检
  | 'learn_observation'  // 观察学习
  | 'optimize_idle'      // 空闲优化
  | 'report_status'      // 主动汇报系统状态
  | 'suggest_help'       // 主动提供帮助
  | 'celebrate'          // 庆祝（保留）
  | 'comfort_user'       // 安慰用户（保留）
  | 'report_task'        // 汇报任务完成（保留）
  | 'alert_urgent';      // 紧急提醒（保留）

export interface ProactiveState {
  lastActionTime: number;
  cooldown: number;
  currentAction: ProactiveAction | null;
  actionTimer: number;
  actionDuration: number;
  boredomLevel: number;  // 0~100，越高越无聊
}

export function createProactiveState(): ProactiveState {
  return {
    lastActionTime: 0,
    cooldown: 5,
    currentAction: null,
    actionTimer: 0,
    actionDuration: 0,
    boredomLevel: 0,
  };
}

/** 更新主动行为状态 */
export function updateProactive(
  state: ProactiveState,
  dt: number,
  params: {
    userIdleMs: number;
    isUserWorking: boolean;
    isNight: boolean;
    bond: number;
    energy: number;
    mood: number;
    curiosity: number;
    hasTaskCompleted: boolean;
    hasTaskFailed: boolean;
    // P0: 新增系统感知参数
    systemLoad: number;
    physicalTasks: number;
    lastAlert: string | null;
    userDetected: boolean;
  }
): ProactiveAction | null {
  state.actionTimer += dt;
  state.cooldown -= dt;

  // 无聊度增长（用户无操作时增长）
  if (params.userIdleMs > 3000) {
    state.boredomLevel += dt * 2;
  } else {
    state.boredomLevel -= dt * 5;
  }
  state.boredomLevel = Math.max(0, Math.min(100, state.boredomLevel));

  // 当前动作进行中
  if (state.currentAction && state.actionTimer < state.actionDuration) {
    return state.currentAction;
  }

  // 动作结束
  if (state.currentAction && state.actionTimer >= state.actionDuration) {
    state.currentAction = null;
    state.cooldown = 3 + Math.random() * 5;
  }

  // cooldown 期间不触发新动作
  if (state.cooldown > 0) return null;

  // 能量太低时不主动行为
  if (params.energy < 20) return null;

  // P0: 系统告警 → 紧急提醒（最高优先级）
  if (params.lastAlert) {
    return trigger(state, 'alert_urgent', 3);
  }

  // 任务完成 → 庆祝
  if (params.hasTaskCompleted) {
    return trigger(state, 'celebrate', 2);
  }

  // 任务失败 → 安慰
  if (params.hasTaskFailed && params.bond > 30) {
    return trigger(state, 'comfort_user', 2);
  }

  // P0: 物理任务执行中 → 不主动行为（专注工作）
  if (params.physicalTasks > 0) {
    return null;
  }

  // P0: 系统负载低时 → 执行自检/优化
  if (params.systemLoad < 0.2 && params.energy > 50 && Math.random() < 0.3) {
    return trigger(state, 'self_diagnostic', 3);
  }

  // P0: 深夜低负载 → 记忆整理（类似 REM）
  if (params.isNight && params.systemLoad < 0.1 && params.energy > 40) {
    return trigger(state, 'memory_organize', 5);
  }

  // P0: 系统负载中等 → 系统扫描
  if (params.systemLoad > 0.3 && params.systemLoad < 0.7 && Math.random() < 0.2) {
    return trigger(state, 'system_scan', 4);
  }

  // P0: 检测到用户 → 主动交流
  if (params.userDetected && params.bond > 40 && Math.random() < 0.3) {
    return trigger(state, 'report_status', 2);
  }

  // P0: 长时间空闲 → 预测性检查
  if (params.userIdleMs > 120000 && params.energy > 40 && Math.random() < 0.2) { // 2分钟
    return trigger(state, 'predictive_check', 3);
  }

  // P0: 高好奇心 + 低负载 → 观察学习
  if (params.curiosity > 60 && params.systemLoad < 0.3 && Math.random() < 0.15) {
    return trigger(state, 'learn_observation', 3);
  }

  return null;
}

/** 触发一个主动动作 */
function trigger(state: ProactiveState, action: ProactiveAction, duration: number): ProactiveAction {
  state.currentAction = action;
  state.actionTimer = 0;
  state.actionDuration = duration;
  state.lastActionTime = performance.now();
  state.boredomLevel = Math.max(0, state.boredomLevel - 30);
  return action;
}

/** 获取主动动作描述 */
export function getProactiveDescription(action: ProactiveAction): string {
  const map: Record<ProactiveAction, string> = {
    system_scan: '系统扫描中',
    sensor_check: '检查传感器',
    memory_organize: '整理记忆',
    predictive_check: '预测性检查',
    self_diagnostic: '自检优化',
    learn_observation: '观察学习',
    optimize_idle: '空闲优化',
    report_status: '汇报系统状态',
    suggest_help: '提供帮助',
    celebrate: '开心地庆祝',
    comfort_user: '安慰你',
    report_task: '跑来汇报任务',
    alert_urgent: '紧急提醒',
  };
  return map[action] || '';
}

/** 主动动作 → 目标位置偏移（相对于当前位置） */
export function getProactiveTargetOffset(action: ProactiveAction): { dx: number; dy: number } | null {
  switch (action) {
    case 'system_scan': return { dx: (Math.random() - 0.5) * 60, dy: (Math.random() - 0.5) * 30 }; // 小范围移动
    case 'sensor_check': return { dx: 0, dy: 0 }; // 原地
    case 'memory_organize': return { dx: 0, dy: 0 }; // 原地沉思
    case 'predictive_check': return { dx: (Math.random() - 0.5) * 40, dy: (Math.random() - 0.5) * 20 };
    case 'self_diagnostic': return { dx: 0, dy: 0 }; // 原地
    case 'learn_observation': return { dx: (Math.random() - 0.5) * 80, dy: (Math.random() - 0.5) * 40 };
    case 'optimize_idle': return { dx: 0, dy: 0 }; // 原地
    case 'report_status': return { dx: -30, dy: -20 }; // 靠近用户
    case 'suggest_help': return { dx: -40, dy: -30 }; // 靠近用户
    case 'celebrate': return { dx: (Math.random() - 0.5) * 100, dy: (Math.random() - 0.5) * 50 };
    case 'comfort_user': return { dx: -20, dy: -10 }; // 靠近用户
    case 'report_task': return { dx: -40, dy: -30 }; // 靠近用户
    case 'alert_urgent': return { dx: -30, dy: -20 }; // 靠近用户
    default: return null;
  }
}
