import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export interface FusedEmotion {
  primary: string;
  intensity: number;
  valence: number;
  mixed: Record<string, number>;
  trend: string;
  authenticity: number;
}

export interface Vitals {
  heartRate: number;
  breathRate: number;
  intensity: number;
}

// P0: 系统感知状态
export interface SystemPerception {
  health: SystemHealth | null;
  physicalTasks: Array<{
    taskId: string;
    status: string;
    provider: string;
    action: string;
    targetLocation: string;
  }>;
  taskLoad: {
    totalRecent: number;
    completedRecent: number;
    failedRecent: number;
  };
  lastAlert: string | null;
  alertSeverity: 'warning' | 'critical' | null;
  userDetected: boolean;
  userEmotion: string | null;
  detectedObjects: string[];
}

export interface SystemHealth {
  status: string;
  natsConnected: boolean;
  redisConnected: boolean;
  workers: Record<string, boolean>;
}

export interface AIState {
  emotion: string;
  persona: string;
  isThinking: boolean;
  isSpeaking: boolean;
  userEmotion: string | null;
  visualObservation: string | null;
  fusedEmotion: FusedEmotion | null;
  vitals: Vitals;
  currentSentence: string | null;
  isBeingPetted: boolean;
  systemPerception: SystemPerception;
}

interface AIStateContextValue {
  state: AIState;
  setEmotion: (emotion: string) => void;
  setPersona: (persona: string) => void;
  setThinking: (thinking: boolean) => void;
  setSpeaking: (speaking: boolean) => void;
  setUserEmotion: (emotion: string | null) => void;
  setVisualObservation: (obs: string | null) => void;
  setFusedEmotion: (fused: FusedEmotion | null) => void;
  setVitals: (vitals: Vitals) => void;
  setCurrentSentence: (sentence: string | null) => void;
  setIsBeingPetted: (v: boolean) => void;
  setSystemPerception: (perception: SystemPerception) => void;
  sendWs: ((type: string, payload: unknown) => void) | null;
  setSendWs: (send: ((type: string, payload: unknown) => void) | null) => void;
}

const defaultState: AIState = {
  emotion: 'listening',
  persona: 'work',
  isThinking: false,
  isSpeaking: false,
  userEmotion: null,
  visualObservation: null,
  fusedEmotion: null,
  vitals: { heartRate: 72, breathRate: 16, intensity: 0 },
  currentSentence: null,
  isBeingPetted: false,
  systemPerception: {
    health: null,
    physicalTasks: [],
    taskLoad: { totalRecent: 0, completedRecent: 0, failedRecent: 0 },
    lastAlert: null,
    alertSeverity: null,
    userDetected: false,
    userEmotion: null,
    detectedObjects: [],
  },
};

const AIStateContext = createContext<AIStateContextValue>({
  state: defaultState,
  setEmotion: () => {},
  setPersona: () => {},
  setThinking: () => {},
  setSpeaking: () => {},
  setUserEmotion: () => {},
  setVisualObservation: () => {},
  setFusedEmotion: () => {},
  setVitals: () => {},
  setCurrentSentence: () => {},
  setIsBeingPetted: () => {},
  setSystemPerception: () => {},
  sendWs: null,
  setSendWs: () => {},
});

export function AIStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AIState>(defaultState);
  const [sendWs, setSendWsState] = useState<((type: string, payload: unknown) => void) | null>(null);

  const setEmotion = useCallback((emotion: string) => {
    setState((s) => s.emotion === emotion ? s : { ...s, emotion });
  }, []);

  const setPersona = useCallback((persona: string) => {
    setState((s) => s.persona === persona ? s : { ...s, persona });
  }, []);

  const setThinking = useCallback((isThinking: boolean) => {
    setState((s) => s.isThinking === isThinking ? s : { ...s, isThinking });
  }, []);

  const setSpeaking = useCallback((isSpeaking: boolean) => {
    setState((s) => s.isSpeaking === isSpeaking ? s : { ...s, isSpeaking });
  }, []);

  const setUserEmotion = useCallback((userEmotion: string | null) => {
    setState((s) => s.userEmotion === userEmotion ? s : { ...s, userEmotion });
  }, []);

  const setVisualObservation = useCallback((visualObservation: string | null) => {
    setState((s) => s.visualObservation === visualObservation ? s : { ...s, visualObservation });
  }, []);

  const setFusedEmotion = useCallback((fusedEmotion: FusedEmotion | null) => {
    setState((s) => {
      if (s.fusedEmotion === fusedEmotion) return s;
      if (s.fusedEmotion && fusedEmotion &&
          s.fusedEmotion.primary === fusedEmotion.primary &&
          s.fusedEmotion.intensity === fusedEmotion.intensity &&
          s.fusedEmotion.valence === fusedEmotion.valence &&
          s.fusedEmotion.trend === fusedEmotion.trend &&
          s.fusedEmotion.authenticity === fusedEmotion.authenticity) {
        return s;
      }
      return { ...s, fusedEmotion };
    });
  }, []);

  const setVitals = useCallback((vitals: Vitals) => {
    setState((s) => {
      if (s.vitals.heartRate === vitals.heartRate &&
          s.vitals.breathRate === vitals.breathRate &&
          s.vitals.intensity === vitals.intensity) {
        return s;
      }
      return { ...s, vitals };
    });
  }, []);

  const setCurrentSentence = useCallback((currentSentence: string | null) => {
    setState((s) => s.currentSentence === currentSentence ? s : { ...s, currentSentence });
  }, []);

  const setIsBeingPetted = useCallback((isBeingPetted: boolean) => {
    setState((s) => s.isBeingPetted === isBeingPetted ? s : { ...s, isBeingPetted });
  }, []);

  const setSystemPerception = useCallback((systemPerception: SystemPerception) => {
    setState((s) => {
      const prev = s.systemPerception;
      if (prev === systemPerception) return s;
      if (prev.health === systemPerception.health &&
          prev.lastAlert === systemPerception.lastAlert &&
          prev.alertSeverity === systemPerception.alertSeverity &&
          prev.userDetected === systemPerception.userDetected &&
          prev.userEmotion === systemPerception.userEmotion &&
          prev.physicalTasks.length === systemPerception.physicalTasks.length &&
          prev.detectedObjects.length === systemPerception.detectedObjects.length &&
          prev.taskLoad.totalRecent === systemPerception.taskLoad.totalRecent &&
          prev.taskLoad.completedRecent === systemPerception.taskLoad.completedRecent &&
          prev.taskLoad.failedRecent === systemPerception.taskLoad.failedRecent) {
        return s;
      }
      return { ...s, systemPerception };
    });
  }, []);

  const setSendWs = useCallback((send: ((type: string, payload: unknown) => void) | null) => {
    setSendWsState(() => send);
  }, []);

  return (
    <AIStateContext.Provider
      value={{
        state,
        setEmotion,
        setPersona,
        setThinking,
        setSpeaking,
        setUserEmotion,
        setVisualObservation,
        setFusedEmotion,
        setVitals,
        setCurrentSentence,
        setIsBeingPetted,
        setSystemPerception,
        sendWs,
        setSendWs,
      }}
    >
      {children}
    </AIStateContext.Provider>
  );
}

export function useAIState() {
  return useContext(AIStateContext);
}
