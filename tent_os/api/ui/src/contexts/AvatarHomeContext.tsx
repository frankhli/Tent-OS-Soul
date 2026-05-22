import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type AvatarMode = 'home' | 'free' | 'hidden';
export type AvatarHomeSource = 'sidebar' | 'chat' | 'assistant' | 'dream' | 'physical' | 'none';
export type AvatarAction =
  | 'idle' | 'walk' | 'run' | 'sleep' | 'sit' | 'lie' | 'wave' | 'jump' | 'dance'
  // P0: 新增系统角色动作
  | 'monitor'      // 监控系统：目光扫视
  | 'operate'      // 调度操作：伸出手臂
  | 'think_deep'   // 深度思考：手托下巴
  | 'recall'       // 回忆记忆
  | 'alert'        // 警觉响应
  | 'scan'         // 扫描检测
  | 'commune'      // 与用户交流
  | 'report'       // 汇报状态
  | 'console'      // 控制台操作
  | 'reach_out';   // 伸出手

export interface AvatarHomeState {
  mode: AvatarMode;
  homeSource: AvatarHomeSource;
  freePosition: { x: number; y: number };
  homePosition: { x: number; y: number }; // 家的位置（自由模式下）
  isDragging: boolean;
  dragOffset: { x: number; y: number };
}

interface AvatarHomeContextValue {
  state: AvatarHomeState;
  summon: (source: AvatarHomeSource, startRect?: DOMRect) => void;
  returnHome: () => void;
  hide: () => void;
  show: () => void;
  setFreePosition: (pos: { x: number; y: number }) => void;
  setHomePosition: (pos: { x: number; y: number }) => void;
  setDragging: (dragging: boolean) => void;
  setDragOffset: (offset: { x: number; y: number }) => void;
}

const LS_KEY_POSITION = 'tent_os_avatar_free_position';
const LS_KEY_HOME = 'tent_os_avatar_home_position';

function loadSavedPosition(): { x: number; y: number } {
  try {
    const raw = localStorage.getItem(LS_KEY_POSITION);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { x: window.innerWidth - 240, y: window.innerHeight - 280 };
}

function loadSavedHome(): { x: number; y: number } {
  try {
    const raw = localStorage.getItem(LS_KEY_HOME);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { x: window.innerWidth - 240, y: window.innerHeight - 280 };
}

const defaultState: AvatarHomeState = {
  mode: 'home',
  homeSource: 'none',
  freePosition: loadSavedPosition(),
  homePosition: loadSavedHome(),
  isDragging: false,
  dragOffset: { x: 0, y: 0 },
};

const AvatarHomeContext = createContext<AvatarHomeContextValue>({
  state: defaultState,
  summon: () => {},
  returnHome: () => {},
  hide: () => {},
  show: () => {},
  setFreePosition: () => {},
  setHomePosition: () => {},
  setDragging: () => {},
  setDragOffset: () => {},
});

export function AvatarHomeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AvatarHomeState>(defaultState);

  const summon = useCallback((source: AvatarHomeSource, startRect?: DOMRect) => {
    setState((s) => {
      const newSource = source !== 'none' ? source : s.homeSource;
      let newPos = s.freePosition;
      let homePos = s.homePosition;
      if (startRect) {
        newPos = {
          x: startRect.left + startRect.width / 2 - 100,
          y: startRect.top + startRect.height / 2 - 100,
        };
        // 家的位置设为召唤位置
        homePos = { ...newPos };
        try { localStorage.setItem(LS_KEY_HOME, JSON.stringify(homePos)); } catch { /* ignore */ }
      }
      return { ...s, mode: 'free', homeSource: newSource, freePosition: newPos, homePosition: homePos };
    });
  }, []);

  const returnHome = useCallback(() => {
    setState((s) => ({ ...s, mode: 'home', isDragging: false }));
  }, []);

  const hide = useCallback(() => {
    setState((s) => ({ ...s, mode: 'hidden', isDragging: false }));
  }, []);

  const show = useCallback(() => {
    setState((s) => ({ ...s, mode: s.homeSource === 'none' ? 'free' : 'home' }));
  }, []);

  const setFreePosition = useCallback((pos: { x: number; y: number }) => {
    setState((s) => {
      const safeX = Math.max(0, Math.min(pos.x, window.innerWidth - 220));
      const safeY = Math.max(0, Math.min(pos.y, window.innerHeight - 260));
      const safePos = { x: safeX, y: safeY };
      try { localStorage.setItem(LS_KEY_POSITION, JSON.stringify(safePos)); } catch { /* ignore */ }
      return { ...s, freePosition: safePos };
    });
  }, []);

  const setHomePosition = useCallback((pos: { x: number; y: number }) => {
    setState((s) => {
      const safePos = { x: Math.max(0, pos.x), y: Math.max(0, pos.y) };
      try { localStorage.setItem(LS_KEY_HOME, JSON.stringify(safePos)); } catch { /* ignore */ }
      return { ...s, homePosition: safePos };
    });
  }, []);

  const setDragging = useCallback((isDragging: boolean) => {
    setState((s) => ({ ...s, isDragging }));
  }, []);

  const setDragOffset = useCallback((offset: { x: number; y: number }) => {
    setState((s) => ({ ...s, dragOffset: offset }));
  }, []);

  return (
    <AvatarHomeContext.Provider
      value={{ state, summon, returnHome, hide, show, setFreePosition, setHomePosition, setDragging, setDragOffset }}
    >
      {children}
    </AvatarHomeContext.Provider>
  );
}

export function useAvatarHome() {
  return useContext(AvatarHomeContext);
}
