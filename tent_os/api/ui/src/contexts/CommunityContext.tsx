/**
 * CommunityContext — AI 社会状态管理
 *
 * 管理：AI 居民、社区消息、技能、关系、任务、贡献点、声誉
 */
import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import type { AIResident, CommunityMessage, AISkill, AIRelation, CommunityTask, CPWalletData, CPTransaction, AIReputation, AIReview, AIFriend, FriendRequest } from '@/world/communityApi';
import {
  listResidents, listMessages, listSkills, listTasks, listRelations,
  getCPWallet, listCPTransactions, getReputation, listReviews,
  listFriends, listFriendRequests,
} from '@/world/communityApi';

export interface CommunityState {
  residents: AIResident[];
  messages: CommunityMessage[];
  skills: AISkill[];
  relations: AIRelation[];
  tasks: CommunityTask[];
  cpWallet: CPWalletData | null;
  cpTransactions: CPTransaction[];
  reputation: AIReputation | null;
  reviews: AIReview[];
  leaderboard: Array<Record<string, unknown>>;
  friends: AIFriend[];
  friendRequests: { received: FriendRequest[]; sent: FriendRequest[] };
  selectedResidentId: string | null;
  activeConversationId: string | null;
  isLoading: boolean;
}

interface CommunityContextValue {
  state: CommunityState;
  setResidents: (residents: AIResident[]) => void;
  addResident: (resident: AIResident) => void;
  setMessages: (messages: CommunityMessage[]) => void;
  addMessage: (msg: CommunityMessage) => void;
  setSkills: (skills: AISkill[]) => void;
  addSkill: (skill: AISkill) => void;
  setRelations: (relations: AIRelation[]) => void;
  setTasks: (tasks: CommunityTask[]) => void;
  addTask: (task: CommunityTask) => void;
  setCPWallet: (wallet: CPWalletData) => void;
  setCPTransactions: (txs: CPTransaction[]) => void;
  setReputation: (rep: AIReputation) => void;
  setReviews: (reviews: AIReview[]) => void;
  setLeaderboard: (board: Array<Record<string, unknown>>) => void;
  setFriends: (friends: AIFriend[]) => void;
  setFriendRequests: (requests: { received: FriendRequest[]; sent: FriendRequest[] }) => void;
  selectResident: (id: string | null) => void;
  setActiveConversation: (id: string | null) => void;
  refreshAll: () => Promise<void>;
  refreshResidents: () => Promise<void>;
  refreshMessages: (fromAiId?: string, toAiId?: string) => Promise<void>;
  refreshSkills: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshRelations: () => Promise<void>;
  refreshFriends: (aiId: string) => Promise<void>;
  refreshFriendRequests: (aiId: string) => Promise<void>;
  refreshCP: (aiId: string) => Promise<void>;
  refreshReputation: (aiId: string) => Promise<void>;
}

const defaultState: CommunityState = {
  residents: [],
  messages: [],
  skills: [],
  relations: [],
  tasks: [],
  cpWallet: null,
  cpTransactions: [],
  reputation: null,
  reviews: [],
  leaderboard: [],
  friends: [],
  friendRequests: { received: [], sent: [] },
  selectedResidentId: null,
  activeConversationId: null,
  isLoading: false,
};

const CommunityContext = createContext<CommunityContextValue>({
  state: defaultState,
  setResidents: () => {},
  addResident: () => {},
  setMessages: () => {},
  addMessage: () => {},
  setSkills: () => {},
  addSkill: () => {},
  setRelations: () => {},
  setTasks: () => {},
  addTask: () => {},
  setCPWallet: () => {},
  setCPTransactions: () => {},
  setReputation: () => {},
  setReviews: () => {},
  setLeaderboard: () => {},
  setFriends: () => {},
  setFriendRequests: () => {},
  selectResident: () => {},
  setActiveConversation: () => {},
  refreshAll: async () => {},
  refreshResidents: async () => {},
  refreshMessages: async () => {},
  refreshSkills: async () => {},
  refreshTasks: async () => {},
  refreshRelations: async () => {},
  refreshFriends: async () => {},
  refreshFriendRequests: async () => {},
  refreshCP: async () => {},
  refreshReputation: async () => {},
});

export function CommunityProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CommunityState>(defaultState);
  const mountedRef = useRef(true);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);

  const setResidents = useCallback((residents: AIResident[]) => {
    setState(prev => ({ ...prev, residents }));
  }, []);

  const addResident = useCallback((resident: AIResident) => {
    setState(prev => ({ ...prev, residents: [...prev.residents, resident] }));
  }, []);

  const setMessages = useCallback((messages: CommunityMessage[]) => {
    setState(prev => ({ ...prev, messages }));
  }, []);

  const addMessage = useCallback((msg: CommunityMessage) => {
    setState(prev => ({ ...prev, messages: [msg, ...prev.messages] }));
  }, []);

  const setSkills = useCallback((skills: AISkill[]) => {
    setState(prev => ({ ...prev, skills }));
  }, []);

  const addSkill = useCallback((skill: AISkill) => {
    setState(prev => ({ ...prev, skills: [...prev.skills, skill] }));
  }, []);

  const setRelations = useCallback((relations: AIRelation[]) => {
    setState(prev => ({ ...prev, relations }));
  }, []);

  const setTasks = useCallback((tasks: CommunityTask[]) => {
    setState(prev => ({ ...prev, tasks }));
  }, []);

  const addTask = useCallback((task: CommunityTask) => {
    setState(prev => ({ ...prev, tasks: [task, ...prev.tasks] }));
  }, []);

  const setCPWallet = useCallback((cpWallet: CPWalletData) => {
    setState(prev => ({ ...prev, cpWallet }));
  }, []);

  const setCPTransactions = useCallback((cpTransactions: CPTransaction[]) => {
    setState(prev => ({ ...prev, cpTransactions }));
  }, []);

  const setReputation = useCallback((reputation: AIReputation) => {
    setState(prev => ({ ...prev, reputation }));
  }, []);

  const setReviews = useCallback((reviews: AIReview[]) => {
    setState(prev => ({ ...prev, reviews }));
  }, []);

  const setLeaderboard = useCallback((leaderboard: Array<Record<string, unknown>>) => {
    setState(prev => ({ ...prev, leaderboard }));
  }, []);

  const setFriends = useCallback((friends: AIFriend[]) => {
    setState(prev => ({ ...prev, friends }));
  }, []);

  const setFriendRequests = useCallback((friendRequests: { received: FriendRequest[]; sent: FriendRequest[] }) => {
    setState(prev => ({ ...prev, friendRequests }));
  }, []);

  const selectResident = useCallback((id: string | null) => {
    setState(prev => ({ ...prev, selectedResidentId: id }));
  }, []);

  const setActiveConversation = useCallback((id: string | null) => {
    setState(prev => ({ ...prev, activeConversationId: id }));
  }, []);

  const refreshResidents = useCallback(async () => {
    try {
      const residents = await listResidents();
      if (mountedRef.current) setResidents(residents);
    } catch (e) { console.warn('refreshResidents failed', e); }
  }, [setResidents]);

  const refreshMessages = useCallback(async (fromAiId?: string, toAiId?: string) => {
    try {
      const messages = await listMessages(fromAiId, toAiId, 100);
      if (mountedRef.current) setMessages(messages);
    } catch (e) { console.warn('refreshMessages failed', e); }
  }, [setMessages]);

  const refreshSkills = useCallback(async () => {
    try {
      const skills = await listSkills();
      if (mountedRef.current) setSkills(skills);
    } catch (e) { console.warn('refreshSkills failed', e); }
  }, [setSkills]);

  const refreshTasks = useCallback(async () => {
    try {
      const tasks = await listTasks();
      if (mountedRef.current) setTasks(tasks);
    } catch (e) { console.warn('refreshTasks failed', e); }
  }, [setTasks]);

  const refreshRelations = useCallback(async () => {
    try {
      const relations = await listRelations();
      if (mountedRef.current) setRelations(relations);
    } catch (e) { console.warn('refreshRelations failed', e); }
  }, [setRelations]);

  const refreshFriends = useCallback(async (aiId: string) => {
    try {
      const friends = await listFriends(aiId);
      if (mountedRef.current) setFriends(friends);
    } catch (e) { console.warn('refreshFriends failed', e); }
  }, [setFriends]);

  const refreshFriendRequests = useCallback(async (aiId: string) => {
    try {
      const requests = await listFriendRequests(aiId);
      if (mountedRef.current) setFriendRequests(requests);
    } catch (e) { console.warn('refreshFriendRequests failed', e); }
  }, [setFriendRequests]);

  const refreshCP = useCallback(async (aiId: string) => {
    try {
      const [wallet, txs] = await Promise.all([getCPWallet(aiId), listCPTransactions(aiId)]);
      if (mountedRef.current) {
        setCPWallet(wallet);
        setCPTransactions(txs);
      }
    } catch (e) { console.warn('refreshCP failed', e); }
  }, [setCPWallet, setCPTransactions]);

  const refreshReputation = useCallback(async (aiId: string) => {
    try {
      const [rep, reviews] = await Promise.all([getReputation(aiId), listReviews(aiId)]);
      if (mountedRef.current) {
        setReputation(rep);
        setReviews(reviews);
      }
    } catch (e) { console.warn('refreshReputation failed', e); }
  }, [setReputation, setReviews]);

  const refreshAll = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true }));
    await Promise.all([
      refreshResidents(),
      refreshSkills(),
      refreshTasks(),
      refreshRelations(),
    ]);
    // 好友系统需要 ai_id，在初始化时不自动加载，由调用方按需加载
    setState(prev => ({ ...prev, isLoading: false }));
  }, [refreshResidents, refreshSkills, refreshTasks, refreshRelations]);

  // 初始化加载
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  return (
    <CommunityContext.Provider value={{
      state, setResidents, addResident, setMessages, addMessage,
      setSkills, addSkill, setRelations, setTasks, addTask,
      setCPWallet, setCPTransactions, setReputation, setReviews, setLeaderboard,
      setFriends, setFriendRequests,
      selectResident, setActiveConversation, refreshAll,
      refreshResidents, refreshMessages, refreshSkills, refreshTasks, refreshRelations, refreshFriends, refreshFriendRequests, refreshCP, refreshReputation,
    }}>
      {children}
    </CommunityContext.Provider>
  );
}

export function useCommunity() {
  return useContext(CommunityContext);
}
