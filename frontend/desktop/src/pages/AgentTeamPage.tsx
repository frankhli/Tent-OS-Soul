import { useState, useEffect, useCallback, useRef } from 'react';
import {
 Users, Plus, X, MessageSquare, Zap, Trash2, Brain,
 Wrench, Activity, Sparkles, Bot, UserCircle, Send,
 Loader2, Route, GitBranch, BarChart3, Radio,
} from 'lucide-react';

interface Agent {
 id: string;
 name: string;
 role: string;
 identity: { personality?: string; avatar_emotion?: string };
 skills: { name: string; level: number; description: string }[];
 tools_allowed: string[];
 system_prompt: string;
 is_active: boolean;
}

interface AgentTemplate {
 key: string;
 name: string;
 role: string;
 description: string;
}

interface AgentRuntimeStatus {
 agent_id: string;
 name: string;
 status: string;
 fatigue: number;
 task_load: number;
 total_tasks: number;
 memory_count?: number;
 skills?: { name: string; level: number; experience: number }[];
}

interface TeamSummary {
 total: number;
 busy: number;
 idle: number;
 offline: number;
 avg_fatigue: number;
}

interface OrchestrationTrace {
 step: string;
 time?: string;
 result?: any;
 agent?: string;
 status?: string;
 agent_count?: number;
 results?: any[];
 synthesis_length?: number;
}

interface OrchestrationResult {
 type: string;
 content: string;
 intent?: {
 action: string;
 requires_sub_agent: boolean;
 agent_count: number;
 collaboration_mode: string;
 target_domains: string[];
 confidence: number;
 reasoning: string;
 task_complexity: number;
 };
 agent_outputs?: { agent_name: string; content: string; status: string }[];
 delegations?: any[];
 synthesis?: string;
 trace?: OrchestrationTrace[];
 agent_id?: string;
 agent_name?: string;
}

export default function AgentTeamPage() {
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [agents, setAgents] = useState<Agent[]>([]);
 const [templates, setTemplates] = useState<AgentTemplate[]>([]);
 const [loading, setLoading] = useState(true);
 const [showCreate, setShowCreate] = useState(false);
 const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
 const [chatAgent, setChatAgent] = useState<Agent | null>(null);
 const [chatMessages, setChatMessages] = useState<{role: string; content: string}[]>([]);
 const [chatInput, setChatInput] = useState('');
 const [chatLoading, setChatLoading] = useState(false);
 const [toast, setToast] = useState('');

 // Team status
 const [teamStatus, setTeamStatus] = useState<{agents: AgentRuntimeStatus[]; summary: TeamSummary} | null>(null);
 
 // Agent skills (P4)
 const [agentSkills, setAgentSkills] = useState<Record<string, any>>({});
 const [showSkillModal, setShowSkillModal] = useState(false);
 const [skillModalAgent, setSkillModalAgent] = useState<Agent | null>(null);
 const [skillModalData, setSkillModalData] = useState<any>(null);
 // P5: 关系网络
 const [showRelationMatrix, setShowRelationMatrix] = useState(false);
 const [relationMatrix, setRelationMatrix] = useState<any>(null);

 // Suggestion banner
 const [teamSuggestion, setTeamSuggestion] = useState('');

 // Room panel
 const [showRooms, setShowRooms] = useState(false);
 const [rooms, setRooms] = useState<any[]>([]);
 const [roomTopic, setRoomTopic] = useState('');
 const [roomName, setRoomName] = useState('');
 const [selectedRoomAgents, setSelectedRoomAgents] = useState<string[]>([]);
 const [roomLoading, setRoomLoading] = useState(false);
 const [roomResult, setRoomResult] = useState<any>(null);

 // Orchestration panel
 const [showOrchestrate, setShowOrchestrate] = useState(false);
 const [orchInput, setOrchInput] = useState('');
 const [orchLoading, setOrchLoading] = useState(false);
 const [orchResult, setOrchResult] = useState<OrchestrationResult | null>(null);

 // Create form states
 const [createMode, setCreateMode] = useState<'template' | 'custom' | 'ai'>('template');
 const [selectedTemplate, setSelectedTemplate] = useState('');
 const [customName, setCustomName] = useState('');
 const [customRole, setCustomRole] = useState('');
 const [customPrompt, setCustomPrompt] = useState('');
 const [aiDescription, setAiDescription] = useState('');
 const [aiGenerating, setAiGenerating] = useState(false);

 const showToast = (msg: string) => {
 setToast(msg);
 setTimeout(() => setToast(''), 3000);
 };

 const loadAgents = useCallback(async () => {
 try {
 const res = await fetch('/api/v1/agents');
 const data = await res.json();
 setAgents(data.agents || []);
 // 加载每个 Agent 的技能信息（P4）
 // 优先使用 list_agents 返回的 skill_stats，避免 N+1 查询
 const skillsMap: Record<string, any> = {};
 for (const agent of (data.agents || [])) {
 if (agent.skill_stats) {
 skillsMap[agent.id] = agent.skill_stats;
 } else {
 // 回退：单独请求
 try {
 const sres = await fetch(`/api/v1/agents/${agent.id}/skills`);
 if (sres.ok) {
 const sdata = await sres.json();
 skillsMap[agent.id] = sdata.stats || {};
 }
 } catch {}
 }
 }
 setAgentSkills(skillsMap);
 } catch (e) {
 console.error('加载 Agent 失败:', e);
 }
 }, []);

 const loadTemplates = useCallback(async () => {
 try {
 const res = await fetch('/api/v1/agents/templates');
 const data = await res.json();
 setTemplates(data.templates || []);
 } catch (e) {
 console.error('加载模板失败:', e);
 }
 }, []);

 const loadTeamStatus = useCallback(async () => {
 try {
 const res = await fetch('/api/v1/agents/status');
 const data = await res.json();
 if (data.status === 'ok') {
 setTeamStatus({ agents: data.agents || [], summary: data.summary });
 }
 } catch (e) {
 console.error('加载团队状态失败:', e);
 }
 }, []);

 const loadSuggestion = useCallback(async () => {
 try {
 const res = await fetch('/api/v1/agents/suggestions');
 const data = await res.json();
 if (data.status === 'ok' && data.suggestion) {
 setTeamSuggestion(data.suggestion);
 }
 } catch (e) {
 console.error('加载建议失败:', e);
 }
 }, []);

 const loadRooms = useCallback(async () => {
 try {
 const res = await fetch('/api/v1/agents/rooms');
 const data = await res.json();
 setRooms(data.rooms || []);
 } catch (e) {
 console.error('加载会议室失败:', e);
 }
 }, []);

 useEffect(() => {
 Promise.all([loadAgents(), loadTemplates(), loadTeamStatus(), loadSuggestion()]).then(() => setLoading(false));
 }, [loadAgents, loadTemplates, loadTeamStatus, loadSuggestion]);

 const createAgent = async () => {
 try {
 const body: any = { created_by: 'web_user' };
 if (createMode === 'template' && selectedTemplate) {
 body.template_key = selectedTemplate;
 const t = templates.find(x => x.key === selectedTemplate);
 if (t) body.name = t.name;
 } else if (createMode === 'custom') {
 body.name = customName || '未命名Agent';
 body.role = customRole || 'assistant';
 body.system_prompt = customPrompt;
 } else if (createMode === 'ai') {
 setAiGenerating(true);
 const res = await fetch('/api/v1/agents/generate', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ user_id: 'web_user', description: aiDescription }),
 });
 const data = await res.json();
 setAiGenerating(false);
 if (data.status === 'ok' && data.agent?.type === 'agent_created') {
 showToast(`AI 为你设计了「${data.agent.agent.name}」`);
 setShowCreate(false);
 setAiDescription('');
 loadAgents();
 loadTeamStatus();
 return;
 } else {
 showToast('生成失败: ' + (data.agent?.message || '未知错误'));
 return;
 }
 }

 const res = await fetch('/api/v1/agents', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify(body),
 });
 const data = await res.json();
 if (data.status === 'ok') {
 showToast(`Agent「${data.agent.name}」创建成功`);
 setShowCreate(false);
 setSelectedTemplate('');
 setCustomName('');
 setCustomRole('');
 setCustomPrompt('');
 loadAgents();
 loadTeamStatus();
 } else {
 showToast('创建失败: ' + (data.error || '未知错误'));
 }
 } catch (e) {
 showToast('创建失败');
 }
 };

 const deleteAgent = async (id: string, name: string) => {
 if (!confirm(`确定要删除 Agent「${name}」吗？`)) return;
 try {
 const res = await fetch(`/api/v1/agents/${id}`, { method: 'DELETE' });
 const data = await res.json();
 if (data.status === 'ok') {
 showToast('删除成功');
 loadAgents();
 loadTeamStatus();
 if (selectedAgent?.id === id) setSelectedAgent(null);
 if (chatAgent?.id === id) setChatAgent(null);
 }
 } catch (e) {
 showToast('删除失败');
 }
 };

 const sendChat = async () => {
 if (!chatInput.trim() || !chatAgent || chatLoading) return;
 const msg = chatInput.trim();
 setChatInput('');
 setChatMessages(prev => [...prev, { role: 'user', content: msg }]);
 setChatLoading(true);

 try {
 const res = await fetch(`/api/v1/agents/${chatAgent.id}/chat`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ message: msg }),
 });
 const data = await res.json();
 if (data.status === 'ok') {
 setChatMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
 } else {
 setChatMessages(prev => [...prev, { role: 'assistant', content: '抱歉，我暂时无法回应。' }]);
 }
 } catch (e) {
 setChatMessages(prev => [...prev, { role: 'assistant', content: '网络错误，请稍后再试。' }]);
 } finally {
 setChatLoading(false);
 }
 };

 const runOrchestrate = async () => {
 if (!orchInput.trim() || orchLoading) return;
 setOrchLoading(true);
 setOrchResult(null);
 try {
 const res = await fetch('/api/v1/agents/orchestrate', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ user_id: 'web_user', message: orchInput.trim(), context: {} }),
 });
 const data = await res.json();
 if (data.status === 'ok') {
 setOrchResult(data.result);
 } else {
 showToast('调度失败: ' + (data.detail || '未知错误'));
 }
 } catch (e) {
 showToast('调度请求失败');
 } finally {
 setOrchLoading(false);
 }
 };

 const createRoom = async () => {
 if (!roomName.trim() || selectedRoomAgents.length === 0) return;
 try {
 const res = await fetch('/api/v1/agents/rooms', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 name: roomName,
 topic: roomTopic || roomName,
 participants: selectedRoomAgents,
 created_by: 'web_user',
 }),
 });
 const data = await res.json();
 if (data.status === 'ok') {
 showToast('会议室创建成功');
 setRoomName('');
 setRoomTopic('');
 setSelectedRoomAgents([]);
 loadRooms();
 }
 } catch (e) {
 showToast('创建会议室失败');
 }
 };

 const startMeeting = async (roomId: string, topic: string, participantIds: string[]) => {
 setRoomLoading(true);
 setRoomResult(null);
 try {
 const res = await fetch(`/api/v1/agents/rooms/${roomId}/start`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ topic, participant_ids: participantIds, rounds: 1 }),
 });
 const data = await res.json();
 if (data.status === 'ok') {
 setRoomResult(data.result);
 loadRooms();
 } else {
 showToast('启动会议失败: ' + (data.detail || '未知错误'));
 }
 } catch (e) {
 showToast('启动会议请求失败');
 } finally {
 setRoomLoading(false);
 }
 };

 const roleLabelMap: Record<string, string> = {
 product_manager: '产品经理',
 tech_lead: '技术顾问',
 finance_advisor: '财务顾问',
 marketing: '市场专家',
 life_coach: '生活顾问',
 assistant: '通用助手',
 };

 const roleColorMap: Record<string, string> = {
 product_manager: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
 tech_lead: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
 finance_advisor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
 marketing: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
 life_coach: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
 assistant: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
 };

 const getStatusDot = (status?: string) => {
 if (status === 'busy') return <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" title="忙碌" />;
 if (status === 'idle') return <span className="w-2 h-2 rounded-full bg-emerald-400" title="空闲" />;
 return <span className="w-2 h-2 rounded-full bg-surface-base" title="离线" />;
 };

 const getRuntimeForAgent = (agentId: string) => {
 return teamStatus?.agents.find(a => a.agent_id === agentId);
 };

 if (loading) {
 return (
 <div className="h-full flex items-center justify-center bg-surface-elevated">
 <div className="flex items-center gap-3 text-content-muted">
 <Loader2 className="w-5 h-5 animate-spin" />
 <span>加载 Agent 团队...</span>
 </div>
 </div>
 );
 }

 return (
 <div className="h-full flex flex-col bg-surface-elevated text-content-primary">
 {/* Toast */}
 {toast && (
 <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-violet-600 text-white px-4 py-2 rounded-lg text-sm z-50 shadow-lg animate-bounce">
 {toast}
 </div>
 )}

 {/* Header */}
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <Users className="w-5 h-5 text-accent" />
 <h1 className="font-bold">Agent 团队</h1>
 <span className="text-xs text-content-muted bg-surface-panel px-2 py-0.5 rounded-full">{agents.length}</span>
 </div>
 <div className="flex items-center gap-2">
 <button
 onClick={() => { setShowRooms(true); loadRooms(); }}
 className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-panel hover:bg-surface-overlay text-content-secondary hover:text-content-primary rounded-lg text-sm font-medium transition border border-line-subtle"
 >
 <MessageSquare className="w-4 h-4" /> 会议室
 </button>
 <button
 onClick={() => setShowOrchestrate(true)}
 className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-panel hover:bg-surface-overlay text-content-secondary hover:text-content-primary rounded-lg text-sm font-medium transition border border-line-subtle"
 >
 <Route className="w-4 h-4" /> 智能调度
 </button>
 <button
 onClick={async () => {
 setShowRelationMatrix(true);
 try {
 const res = await fetch('/api/v1/agents/relationship-matrix');
 if (res.ok) setRelationMatrix(await res.json());
 } catch {}
 }}
 className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-panel hover:bg-surface-overlay text-content-secondary hover:text-content-primary rounded-lg text-sm font-medium transition border border-line-subtle"
 >
 <GitBranch className="w-4 h-4" /> 协作网络
 </button>
 <button
 onClick={() => setShowCreate(true)}
 className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium transition"
 >
 <Plus className="w-4 h-4" /> 新建 Agent
 </button>
 </div>
 </div>

 {/* Team Suggestion Banner */}
 {teamSuggestion && (
 <div className="px-6 py-2 border-b border-line-subtle bg-accent-subtle/5 shrink-0">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-2 text-xs text-violet-300">
 <Sparkles className="w-3.5 h-3.5" />
 <span>{teamSuggestion}</span>
 </div>
 <button onClick={() => setTeamSuggestion('')} className="text-content-muted hover:text-content-secondary transition">
 <X className="w-3.5 h-3.5" />
 </button>
 </div>
 </div>
 )}

 {/* Team Status Bar */}
 {teamStatus && (
 <div className="px-6 py-3 border-b border-line-subtle bg-surface-elevated/50 shrink-0">
 <div className="flex items-center gap-6 text-xs">
 <div className="flex items-center gap-2 text-content-muted">
 <BarChart3 className="w-3.5 h-3.5" />
 <span>团队状态</span>
 </div>
 <div className="flex items-center gap-1.5">
 <span className="text-content-muted">总计</span>
 <span className="text-content-primary font-medium">{teamStatus.summary.total}</span>
 </div>
 <div className="flex items-center gap-1.5">
 <span className="w-2 h-2 rounded-full bg-amber-400" />
 <span className="text-content-muted">忙碌</span>
 <span className="text-amber-400 font-medium">{teamStatus.summary.busy}</span>
 </div>
 <div className="flex items-center gap-1.5">
 <span className="w-2 h-2 rounded-full bg-emerald-400" />
 <span className="text-content-muted">空闲</span>
 <span className="text-emerald-400 font-medium">{teamStatus.summary.idle}</span>
 </div>
 <div className="flex items-center gap-1.5">
 <Activity className="w-3 h-3 text-content-muted" />
 <span className="text-content-muted">平均疲劳</span>
 <span className={`font-medium ${teamStatus.summary.avg_fatigue > 0.5 ? 'text-red-400' : 'text-content-secondary'}`}>
 {Math.round(teamStatus.summary.avg_fatigue * 100)}%
 </span>
 </div>
 </div>
 </div>
 )}

 {/* Main Content */}
 <div className="flex-1 flex overflow-hidden">
 {/* Agent List */}
 <div className={`${chatAgent ? 'w-1/3' : 'w-full'} p-6 overflow-y-auto border-r border-line-subtle`}>
 {agents.length === 0 ? (
 <div className="flex flex-col items-center justify-center h-full text-center">
 <Bot className="w-16 h-16 text-content-secondary mb-4" />
 <div className="text-lg text-content-muted mb-2">还没有 Agent</div>
 <div className="text-sm text-content-muted max-w-sm mb-6">
 创建你的第一个 AI Agent 吧。你可以组建一支团队，让不同专长的 Agent 协作完成任务。
 </div>
 <button
 onClick={() => setShowCreate(true)}
 className="px-6 py-2.5 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-medium transition"
 >
 <Plus className="w-4 h-4 inline mr-1" /> 创建第一个 Agent
 </button>
 </div>
 ) : (
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
 {agents.map(agent => {
 const rt = getRuntimeForAgent(agent.id);
 return (
 <div
 key={agent.id}
 className={`group relative p-4 rounded-xl border transition cursor-pointer ${
 selectedAgent?.id === agent.id
 ? 'bg-surface-panel border-violet-500/50'
 : 'bg-surface-panel/50 border-line-subtle/50 hover:border-line-active'
 }`}
 onClick={() => setSelectedAgent(agent)}
 >
 <div className="flex items-start justify-between mb-3">
 <div className="flex items-center gap-3">
 <div className="relative">
 <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500/20 to-indigo-500/20 flex items-center justify-center ring-1 ring-violet-500/30">
 <Bot className="w-5 h-5 text-accent" />
 </div>
 <div className="absolute -bottom-0.5 -right-0.5">
 {getStatusDot(rt?.status)}
 </div>
 </div>
 <div>
 <div className="font-medium text-sm">{agent.name}</div>
 <div className={`text-[10px] px-1.5 py-0.5 rounded border inline-block mt-0.5 ${roleColorMap[agent.role] || roleColorMap.assistant}`}>
 {roleLabelMap[agent.role] || agent.role}
 </div>
 </div>
 </div>
 <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
 <button
 onClick={(e) => { e.stopPropagation(); setChatAgent(agent); setChatMessages([]); }}
 className="p-1.5 rounded-lg bg-surface-overlay hover:bg-violet-600 text-content-muted hover:text-content-primary transition"
 title="对话"
 >
 <MessageSquare className="w-3.5 h-3.5" />
 </button>
 <button
 onClick={(e) => { e.stopPropagation(); deleteAgent(agent.id, agent.name); }}
 className="p-1.5 rounded-lg bg-surface-overlay hover:bg-red-600 text-content-muted hover:text-content-primary transition"
 title="删除"
 >
 <Trash2 className="w-3.5 h-3.5" />
 </button>
 </div>
 </div>

 {agent.identity?.personality && (
 <p className="text-xs text-content-muted mb-3 line-clamp-2">{agent.identity.personality}</p>
 )}

 {/* Runtime status bar */}
 {rt && (
 <div className="flex items-center gap-2 mb-2">
 <div className="flex-1 h-1 bg-surface-overlay rounded-full overflow-hidden">
 <div
 className={`h-full rounded-full ${rt.fatigue > 0.5 ? 'bg-red-400' : rt.fatigue > 0.3 ? 'bg-amber-400' : 'bg-emerald-400'}`}
 style={{ width: `${Math.min(rt.fatigue * 100, 100)}%` }}
 />
 </div>
 <span className="text-[10px] text-content-muted">{rt.total_tasks} 任务</span>
 </div>
 )}

 {agent.skills?.length > 0 && (
 <div className="flex flex-wrap gap-1">
 {agent.skills.slice(0, 3).map((s, i) => (
 <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-surface-overlay/50 text-content-muted">
 {s.name}
 </span>
 ))}
 {agent.skills.length > 3 && (
 <span className="text-[10px] px-2 py-0.5 rounded-full bg-surface-overlay/50 text-content-muted">
 +{agent.skills.length - 3}
 </span>
 )}
 </div>
 )}
 
 {/* 技能树等级（P4） */}
 {agentSkills[agent.id] && (
 <div className="mt-2 flex items-center gap-2">
 <div className="flex-1">
 <div className="flex justify-between text-[10px] text-content-muted mb-0.5">
 <span>技能等级 Lv.{agentSkills[agent.id].avg_level || 1}</span>
 <span>{agentSkills[agent.id].total_xp || 0} XP</span>
 </div>
 <div className="h-1 bg-surface-panel rounded-full overflow-hidden">
 <div
 className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full"
 style={{ width: `${Math.min((agentSkills[agent.id].avg_level || 1) / 5 * 100, 100)}%` }}
 />
 </div>
 </div>
 <button
 onClick={async (e) => {
 e.stopPropagation();
 setSkillModalAgent(agent);
 try {
 const res = await fetch(`/api/v1/agents/${agent.id}/skills`);
 if (res.ok) {
 const data = await res.json();
 setSkillModalData(data);
 setShowSkillModal(true);
 }
 } catch {}
 }}
 className="text-[10px] px-2 py-1 rounded bg-surface-panel hover:bg-violet-900/40 text-content-muted hover:text-violet-300 transition border border-line-subtle"
 >
 技能树
 </button>
 </div>
 )}
 </div>
 );
 })}
 </div>
 )}
 </div>

 {/* Chat Panel */}
 {chatAgent && (
 <div className="w-2/3 flex flex-col bg-surface-elevated">
 {/* Chat Header */}
 <div className="h-14 flex items-center justify-between px-4 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500/20 to-indigo-500/20 flex items-center justify-center">
 <Bot className="w-4 h-4 text-accent" />
 </div>
 <div>
 <div className="text-sm font-medium">{chatAgent.name}</div>
 <div className="text-[10px] text-content-muted">{roleLabelMap[chatAgent.role] || chatAgent.role}</div>
 </div>
 </div>
 <button
 onClick={() => { setChatAgent(null); setChatMessages([]); }}
 className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition"
 >
 <X className="w-4 h-4" />
 </button>
 </div>

 {/* Messages */}
 <div className="flex-1 overflow-y-auto p-4 space-y-4">
 {chatMessages.length === 0 && (
 <div className="flex flex-col items-center justify-center h-full text-center">
 <MessageSquare className="w-10 h-10 text-content-secondary mb-3" />
 <div className="text-sm text-content-muted">和 {chatAgent.name} 开始对话</div>
 <div className="text-xs text-content-secondary mt-1 max-w-xs">
 这位 {roleLabelMap[chatAgent.role] || chatAgent.role} 已经准备好回答你的问题了
 </div>
 </div>
 )}
 {chatMessages.map((m, i) => (
 <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
 <div className={`max-w-md px-3 py-2 rounded-xl text-sm ${
 m.role === 'user'
 ? 'bg-violet-600 text-white'
 : 'bg-surface-panel text-content-primary border border-line-subtle'
 }`}>
 {m.content}
 </div>
 </div>
 ))}
 {chatLoading && (
 <div className="flex justify-start">
 <div className="bg-surface-panel border border-line-subtle px-3 py-2 rounded-xl text-sm flex items-center gap-2">
 <Loader2 className="w-4 h-4 animate-spin text-accent" />
 <span className="text-content-muted">思考中...</span>
 </div>
 </div>
 )}
 </div>

 {/* Input */}
 <div className="p-4 border-t border-line-subtle">
 <div className="flex gap-2">
 <input
 value={chatInput}
 onChange={(e) => setChatInput(e.target.value)}
 onKeyDown={(e) => e.key === 'Enter' && sendChat()}
 placeholder={`问 ${chatAgent.name} 一个问题...`}
 disabled={chatLoading}
 className="flex-1 bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500 disabled:opacity-50"
 />
 <button
 onClick={sendChat}
 disabled={chatLoading || !chatInput.trim()}
 className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm transition disabled:opacity-50"
 >
 <Send className="w-4 h-4" />
 </button>
 </div>
 </div>
 </div>
 )}
 </div>

 {/* ─── Orchestrate Modal ─── */}
 {showOrchestrate && (
 <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
 <div className="bg-surface-elevated border border-line-subtle rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden shadow-2xl flex flex-col">
 {/* Header */}
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <div className="w-8 h-8 rounded-lg bg-accent-subtle/20 flex items-center justify-center">
 <GitBranch className="w-4 h-4 text-accent" />
 </div>
 <div>
 <h2 className="font-bold text-sm">智能调度测试</h2>
 <p className="text-[10px] text-content-muted">观察主Agent如何分析意图、选择子Agent、整合结果</p>
 </div>
 </div>
 <button onClick={() => { setShowOrchestrate(false); setOrchResult(null); }} className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="flex-1 overflow-y-auto p-6 space-y-4">
 {/* Input */}
 <div className="flex gap-2">
 <input
 value={orchInput}
 onChange={(e) => setOrchInput(e.target.value)}
 onKeyDown={(e) => e.key === 'Enter' && runOrchestrate()}
 placeholder="输入一个任务，例如：帮我设计一个SaaS产品的商业方案..."
 disabled={orchLoading}
 className="flex-1 bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500 disabled:opacity-50"
 />
 <button
 onClick={runOrchestrate}
 disabled={orchLoading || !orchInput.trim()}
 className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium transition disabled:opacity-50 flex items-center gap-1.5"
 >
 {orchLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
 调度
 </button>
 </div>

 {/* Result Display */}
 {orchResult && (
 <div className="space-y-4">
 {/* Intent Analysis */}
 {orchResult.intent && (
 <div className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4">
 <div className="flex items-center gap-2 text-xs text-accent font-medium mb-3">
 <Brain className="w-3.5 h-3.5" />
 意图分析
 </div>
 <div className="grid grid-cols-2 gap-3 text-xs">
 <div className="bg-surface-panel rounded-lg p-2.5">
 <div className="text-content-muted mb-1">动作</div>
 <div className="text-content-primary">
 {orchResult.intent.action === 'delegate_task' ? '委派任务' :
 orchResult.intent.action === 'create_agent' ? '创建Agent' : '直接对话'}
 </div>
 </div>
 <div className="bg-surface-panel rounded-lg p-2.5">
 <div className="text-content-muted mb-1">需要子Agent</div>
 <div className={`font-medium ${orchResult.intent.requires_sub_agent ? 'text-amber-400' : 'text-content-muted'}`}>
 {orchResult.intent.requires_sub_agent ? `是 (${orchResult.intent.agent_count}个)` : '否'}
 </div>
 </div>
 <div className="bg-surface-panel rounded-lg p-2.5">
 <div className="text-content-muted mb-1">目标领域</div>
 <div className="text-content-primary">{orchResult.intent.target_domains?.join(', ') || '-'}</div>
 </div>
 <div className="bg-surface-panel rounded-lg p-2.5">
 <div className="text-content-muted mb-1">协作模式</div>
 <div className="text-content-primary">
 {orchResult.intent.collaboration_mode === 'single' ? '单Agent' :
 orchResult.intent.collaboration_mode === 'parallel' ? '并行协作' : '顺序协作'}
 </div>
 </div>
 <div className="bg-surface-panel rounded-lg p-2.5 col-span-2">
 <div className="text-content-muted mb-1">推理</div>
 <div className="text-content-secondary">{orchResult.intent.reasoning}</div>
 </div>
 </div>
 </div>
 )}

 {/* Delegations */}
 {orchResult.delegations && orchResult.delegations.length > 0 && (
 <div className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4">
 <div className="flex items-center gap-2 text-xs text-amber-400 font-medium mb-3">
 <Radio className="w-3.5 h-3.5" />
 委派执行 ({orchResult.delegations.length} 个Agent)
 </div>
 <div className="space-y-2">
 {orchResult.delegations.map((d, i) => (
 <div key={i} className="flex items-center gap-3 bg-surface-panel rounded-lg p-3">
 <div className={`w-2 h-2 rounded-full ${d.status === 'success' ? 'bg-emerald-400' : d.status === 'error' ? 'bg-red-400' : 'bg-amber-400'}`} />
 <div className="flex-1 min-w-0">
 <div className="text-sm text-content-primary">{d.agent_name}</div>
 <div className="text-[10px] text-content-muted truncate">{d.result || d.task}</div>
 </div>
 </div>
 ))}
 </div>
 </div>
 )}

 {/* Agent Outputs */}
 {orchResult.agent_outputs && orchResult.agent_outputs.length > 0 && (
 <div className="space-y-3">
 {orchResult.agent_outputs.map((o, i) => (
 <div key={i} className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4">
 <div className="flex items-center gap-2 text-xs text-blue-400 font-medium mb-2">
 <Bot className="w-3.5 h-3.5" />
 {o.agent_name} 的分析
 </div>
 <div className="text-sm text-content-secondary whitespace-pre-wrap leading-relaxed">{o.content}</div>
 </div>
 ))}
 </div>
 )}

 {/* Single Agent Result */}
 {orchResult.type === 'delegated' && orchResult.content && (
 <div className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4">
 <div className="flex items-center gap-2 text-xs text-blue-400 font-medium mb-2">
 <Bot className="w-3.5 h-3.5" />
 {orchResult.agent_name} 的回复
 </div>
 <div className="text-sm text-content-secondary whitespace-pre-wrap leading-relaxed">{orchResult.content}</div>
 </div>
 )}

 {/* Synthesis */}
 {orchResult.synthesis && orchResult.agent_outputs && orchResult.agent_outputs.length > 1 && (
 <div className="bg-accent-subtle/5 rounded-xl border border-violet-500/20 p-4">
 <div className="flex items-center gap-2 text-xs text-accent font-medium mb-2">
 <Sparkles className="w-3.5 h-3.5" />
 整合结果
 </div>
 <div className="text-sm text-content-primary whitespace-pre-wrap leading-relaxed">{orchResult.synthesis}</div>
 </div>
 )}

 {/* Direct */}
 {orchResult.type === 'direct' && (
 <div className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4 text-center">
 <div className="text-sm text-content-muted">这是一个普通对话请求，不需要子Agent处理</div>
 <div className="text-xs text-content-muted mt-1">主Agent将直接回复用户</div>
 </div>
 )}

 {/* Trace */}
 {orchResult.trace && orchResult.trace.length > 0 && (
 <div className="bg-surface-panel/30 rounded-xl border border-line-subtle p-3">
 <div className="text-[10px] text-content-secondary font-medium mb-2 uppercase tracking-wider">调度轨迹</div>
 <div className="space-y-1">
 {orchResult.trace.map((t, i) => (
 <div key={i} className="flex items-center gap-2 text-[10px]">
 <span className="text-content-secondary">{i + 1}.</span>
 <span className="text-content-muted">{t.step}</span>
 {t.agent && <span className="text-accent">→ {t.agent}</span>}
 {t.status && <span className={`${t.status === 'success' ? 'text-emerald-400' : 'text-amber-400'}`}>({t.status})</span>}
 </div>
 ))}
 </div>
 </div>
 )}
 </div>
 )}

 {!orchResult && !orchLoading && (
 <div className="text-center py-12">
 <Route className="w-10 h-10 text-content-secondary mx-auto mb-3" />
 <div className="text-sm text-content-muted">输入任务后点击调度，观察主-子Agent协作流程</div>
 <div className="text-xs text-content-secondary mt-2 space-y-1">
 <div>• 单Agent委派："帮我优化这段Python代码"</div>
 <div>• 多Agent协作："帮我设计一个SaaS产品的完整方案"</div>
 <div>• 创建Agent："给我创建一个擅长写小说的Agent"</div>
 </div>
 </div>
 )}
 </div>
 </div>
 </div>
 )}

 {/* ─── Create Modal ─── */}
 {showCreate && (
 <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
 <div className="bg-surface-elevated border border-line-subtle rounded-2xl w-full max-w-lg max-h-[80vh] overflow-hidden shadow-2xl">
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle">
 <h2 className="font-bold flex items-center gap-2">
 <Sparkles className="w-5 h-5 text-accent" /> 新建 Agent
 </h2>
 <button onClick={() => setShowCreate(false)} className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="p-6 overflow-y-auto">
 {/* Mode Switch */}
 <div className="flex gap-2 mb-6">
 <button
 onClick={() => setCreateMode('template')}
 className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${
 createMode === 'template' ? 'bg-violet-600 text-white' : 'bg-surface-panel text-content-muted hover:text-content-primary'
 }`}
 >
 从模板创建
 </button>
 <button
 onClick={() => setCreateMode('ai')}
 className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${
 createMode === 'ai' ? 'bg-violet-600 text-white' : 'bg-surface-panel text-content-muted hover:text-content-primary'
 }`}
 >
 🤖 AI 设计
 </button>
 <button
 onClick={() => setCreateMode('custom')}
 className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${
 createMode === 'custom' ? 'bg-violet-600 text-white' : 'bg-surface-panel text-content-muted hover:text-content-primary'
 }`}
 >
 自定义创建
 </button>
 </div>

 {createMode === 'ai' && (
 <div className="space-y-4">
 <div className="text-xs text-content-muted mb-2">
 描述你想要的 Agent，AI 会为你设计完整的角色配置：
 </div>
 <textarea
 value={aiDescription}
 onChange={(e) => setAiDescription(e.target.value)}
 placeholder={"例如：\n• 我需要一位擅长写科幻小说的创作伙伴，文风要像刘慈欣那样宏大叙事\n• 帮我设计一个懂中医养生的健康顾问，说话温和有耐心\n• 我想要一个能帮我分析股票的技术分析师，擅长 K 线形态识别"}
 rows={6}
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500 resize-none"
 />
 <div className="flex items-center gap-2 text-xs text-content-muted">
 <Sparkles className="w-3 h-3 text-accent" />
 AI 会自动生成：角色名称、性格特点、专长技能、可用工具、system prompt
 </div>
 </div>
 )}

 {createMode === 'template' ? (
 <div className="space-y-3">
 <div className="text-xs text-content-muted mb-2">选择一个预设角色：</div>
 {templates.map(t => (
 <div
 key={t.key}
 onClick={() => setSelectedTemplate(t.key)}
 className={`p-3 rounded-xl border cursor-pointer transition ${
 selectedTemplate === t.key
 ? 'bg-accent-subtle/10 border-violet-500/50'
 : 'bg-surface-panel/50 border-line-subtle/50 hover:border-line-active'
 }`}
 >
 <div className="flex items-center justify-between">
 <div className="font-medium text-sm">{t.name}</div>
 {selectedTemplate === t.key && (
 <div className="w-4 h-4 rounded-full bg-accent-subtle flex items-center justify-center">
 <div className="w-2 h-2 rounded-full bg-surface-elevated" />
 </div>
 )}
 </div>
 <div className="text-xs text-content-muted mt-1">{t.description}</div>
 </div>
 ))}
 </div>
 ) : createMode === 'custom' && (
 <div className="space-y-4">
 <div>
 <label className="text-xs text-content-muted block mb-1">名称</label>
 <input
 value={customName}
 onChange={(e) => setCustomName(e.target.value)}
 placeholder="给 Agent 起个名字"
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 />
 </div>
 <div>
 <label className="text-xs text-content-muted block mb-1">角色</label>
 <input
 value={customRole}
 onChange={(e) => setCustomRole(e.target.value)}
 placeholder="例如：产品经理、健身教练"
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 />
 </div>
 <div>
 <label className="text-xs text-content-muted block mb-1">角色定义（System Prompt）</label>
 <textarea
 value={customPrompt}
 onChange={(e) => setCustomPrompt(e.target.value)}
 placeholder="描述这个 Agent 的核心能力、性格特点、说话风格..."
 rows={5}
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500 resize-none"
 />
 </div>
 </div>
 )}
 </div>

 <div className="p-4 border-t border-line-subtle flex justify-end gap-2">
 <button
 onClick={() => setShowCreate(false)}
 className="px-4 py-2 rounded-lg text-sm text-content-muted hover:text-content-primary hover:bg-surface-panel transition"
 >
 取消
 </button>
 <button
 onClick={createAgent}
 disabled={
 createMode === 'template' ? !selectedTemplate :
 createMode === 'ai' ? !aiDescription.trim() || aiGenerating :
 !customName.trim()
 }
 className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium transition disabled:opacity-50"
 >
 {aiGenerating ? <Loader2 className="w-4 h-4 animate-spin inline" /> : '创建'}
 </button>
 </div>
 </div>
 </div>
 )}

 {/* ─── Agent Detail Panel ─── */}
 {selectedAgent && !chatAgent && (
 <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
 <div className="bg-surface-elevated border border-line-subtle rounded-2xl w-full max-w-lg max-h-[80vh] overflow-hidden shadow-2xl">
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle">
 <div className="flex items-center gap-3">
 <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500/20 to-indigo-500/20 flex items-center justify-center">
 <Bot className="w-4 h-4 text-accent" />
 </div>
 <div>
 <div className="font-bold text-sm">{selectedAgent.name}</div>
 <div className={`text-[10px] px-1.5 py-0.5 rounded border inline-block ${roleColorMap[selectedAgent.role] || roleColorMap.assistant}`}>
 {roleLabelMap[selectedAgent.role] || selectedAgent.role}
 </div>
 </div>
 </div>
 <button onClick={() => setSelectedAgent(null)} className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="p-6 overflow-y-auto space-y-4">
 {/* Runtime stats */}
 {(() => {
 const rt = getRuntimeForAgent(selectedAgent.id);
 if (!rt) return null;
 return (
 <div className="bg-surface-panel/50 rounded-lg border border-line-subtle/50 p-3">
 <div className="text-[10px] text-content-muted font-medium mb-2 uppercase tracking-wider">运行状态</div>
 <div className="grid grid-cols-4 gap-2 text-center">
 <div>
 <div className="text-xs text-content-muted">状态</div>
 <div className={`text-xs font-medium ${rt.status === 'busy' ? 'text-amber-400' : rt.status === 'idle' ? 'text-emerald-400' : 'text-content-muted'}`}>
 {rt.status === 'busy' ? '忙碌' : rt.status === 'idle' ? '空闲' : '离线'}
 </div>
 </div>
 <div>
 <div className="text-xs text-content-muted">疲劳度</div>
 <div className={`text-xs font-medium ${rt.fatigue > 0.5 ? 'text-red-400' : 'text-content-secondary'}`}>
 {Math.round(rt.fatigue * 100)}%
 </div>
 </div>
 <div>
 <div className="text-xs text-content-muted">负载</div>
 <div className="text-xs font-medium text-content-secondary">{rt.task_load}</div>
 </div>
 <div>
 <div className="text-xs text-content-muted">总任务</div>
 <div className="text-xs font-medium text-content-secondary">{rt.total_tasks}</div>
 </div>
 </div>
 </div>
 );
 })()}

 {selectedAgent.identity?.personality && (
 <div>
 <div className="text-xs text-content-muted mb-1 flex items-center gap-1">
 <UserCircle className="w-3 h-3" /> 性格
 </div>
 <p className="text-sm text-content-secondary">{selectedAgent.identity.personality}</p>
 </div>
 )}

 {selectedAgent.skills?.length > 0 && (
 <div>
 <div className="text-xs text-content-muted mb-2 flex items-center gap-1">
 <Brain className="w-3 h-3" /> 专长技能
 </div>
 <div className="space-y-2">
 {selectedAgent.skills.map((s, i) => (
 <div key={i} className="flex items-center gap-3">
 <span className="text-sm text-content-secondary flex-1">{s.name}</span>
 <div className="w-24 h-1.5 bg-surface-overlay rounded-full overflow-hidden">
 <div className="h-full bg-accent-subtle rounded-full" style={{ width: `${(s.level || 0.5) * 100}%` }} />
 </div>
 <span className="text-[10px] text-content-muted w-8 text-right">{Math.round((s.level || 0.5) * 100)}%</span>
 </div>
 ))}
 </div>
 </div>
 )}

 {selectedAgent.tools_allowed?.length > 0 && (
 <div>
 <div className="text-xs text-content-muted mb-2 flex items-center gap-1">
 <Wrench className="w-3 h-3" /> 可用工具
 </div>
 <div className="flex flex-wrap gap-1">
 {selectedAgent.tools_allowed.map((t, i) => (
 <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-surface-panel text-content-muted border border-line-subtle">
 {t}
 </span>
 ))}
 </div>
 </div>
 )}

 {selectedAgent.system_prompt && (
 <div>
 <div className="text-xs text-content-muted mb-1 flex items-center gap-1">
 <Sparkles className="w-3 h-3" /> 角色定义
 </div>
 <p className="text-xs text-content-muted leading-relaxed bg-surface-panel/50 p-3 rounded-lg border border-line-subtle/50">
 {selectedAgent.system_prompt}
 </p>
 </div>
 )}
 </div>

 <div className="p-4 border-t border-line-subtle flex gap-2">
 <button
 onClick={() => { setChatAgent(selectedAgent); setSelectedAgent(null); setChatMessages([]); }}
 className="flex-1 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium transition flex items-center justify-center gap-1.5"
 >
 <MessageSquare className="w-4 h-4" /> 开始对话
 </button>
 <button
 onClick={() => { deleteAgent(selectedAgent.id, selectedAgent.name); setSelectedAgent(null); }}
 className="px-4 py-2 bg-surface-panel hover:bg-red-900/40 text-content-muted hover:text-red-400 rounded-lg text-sm transition"
 >
 <Trash2 className="w-4 h-4" />
 </button>
 </div>
 </div>
 </div>
 )}
 {/* ─── Rooms Modal ─── */}
 {showRooms && (
 <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
 <div className="bg-surface-elevated border border-line-subtle rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden shadow-2xl flex flex-col">
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <div className="w-8 h-8 rounded-lg bg-accent-subtle/20 flex items-center justify-center">
 <MessageSquare className="w-4 h-4 text-accent" />
 </div>
 <div>
 <h2 className="font-bold text-sm">Agent 会议室</h2>
 <p className="text-[10px] text-content-muted">让多位Agent围绕主题协作讨论</p>
 </div>
 </div>
 <button onClick={() => { setShowRooms(false); setRoomResult(null); }} className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="flex-1 overflow-y-auto p-6 space-y-4">
 {/* Create Room */}
 <div className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-4 space-y-3">
 <div className="text-xs text-accent font-medium flex items-center gap-1.5">
 <Plus className="w-3.5 h-3.5" /> 创建新会议
 </div>
 <input
 value={roomName}
 onChange={(e) => setRoomName(e.target.value)}
 placeholder="会议名称"
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 />
 <input
 value={roomTopic}
 onChange={(e) => setRoomTopic(e.target.value)}
 placeholder="讨论主题"
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 />
 <div className="text-[10px] text-content-muted">选择参与者：</div>
 <div className="flex flex-wrap gap-2">
 {agents.map(agent => (
 <button
 key={agent.id}
 onClick={() => {
 setSelectedRoomAgents(prev =>
 prev.includes(agent.id) ? prev.filter(id => id !== agent.id) : [...prev, agent.id]
 );
 }}
 className={`text-xs px-2.5 py-1 rounded-full border transition ${
 selectedRoomAgents.includes(agent.id)
 ? 'bg-accent-subtle/20 border-violet-500/50 text-violet-300'
 : 'bg-surface-panel border-line-subtle text-content-muted hover:text-content-secondary'
 }`}
 >
 {agent.name}
 </button>
 ))}
 </div>
 <button
 onClick={createRoom}
 disabled={!roomName.trim() || selectedRoomAgents.length === 0}
 className="px-4 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
 >
 创建会议
 </button>
 </div>

 {/* Room List */}
 {rooms.length > 0 && (
 <div className="space-y-2">
 <div className="text-xs text-content-muted font-medium">历史会议</div>
 {rooms.map(room => (
 <div key={room.id} className="bg-surface-panel/50 rounded-xl border border-line-subtle/50 p-3">
 <div className="flex items-center justify-between">
 <div>
 <div className="text-sm text-content-primary">{room.name}</div>
 <div className="text-[10px] text-content-muted">{room.topic}</div>
 </div>
 <div className="flex items-center gap-2">
 <span className={`text-[10px] px-1.5 py-0.5 rounded ${
 room.status === 'active' ? 'bg-amber-500/10 text-amber-400' :
 room.status === 'closed' ? 'bg-emerald-500/10 text-emerald-400' :
 'bg-surface-overlay text-content-muted'
 }`}>
 {room.status === 'active' ? '进行中' : room.status === 'closed' ? '已结束' : '空闲'}
 </span>
 {room.status !== 'closed' && (
 <button
 onClick={() => startMeeting(room.id, room.topic, room.participants || [])}
 disabled={roomLoading}
 className="px-2.5 py-1 bg-violet-600 hover:bg-violet-700 text-white rounded text-xs font-medium transition disabled:opacity-50"
 >
 {roomLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : '启动'}
 </button>
 )}
 </div>
 </div>
 {room.summary && (
 <div className="mt-2 text-[11px] text-content-muted bg-surface-panel/50 p-2 rounded border border-line-subtle/30 line-clamp-3">
 {room.summary}
 </div>
 )}
 </div>
 ))}
 </div>
 )}

 {/* Meeting Result */}
 {roomResult && (
 <div className="bg-accent-subtle/5 rounded-xl border border-violet-500/20 p-4 space-y-3">
 <div className="text-xs text-accent font-medium flex items-center gap-1.5">
 <Sparkles className="w-3.5 h-3.5" /> 讨论完成
 </div>
 {roomResult.messages?.map((m: any, i: number) => (
 <div key={i} className="bg-surface-panel/50 rounded-lg p-3">
 <div className="text-[10px] text-content-muted mb-1">{m.agent}</div>
 <div className="text-xs text-content-secondary line-clamp-4">{m.content}</div>
 </div>
 ))}
 {roomResult.summary && (
 <div className="bg-surface-panel rounded-lg p-3 border border-line-subtle">
 <div className="text-[10px] text-accent mb-1">会议纪要</div>
 <div className="text-xs text-content-primary whitespace-pre-wrap">{roomResult.summary}</div>
 </div>
 )}
 </div>
 )}
 </div>
 </div>
 </div>
 )}

 {/* Skill Tree Modal (P4) */}
 {showSkillModal && skillModalAgent && skillModalData && (
 <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
 <div className="w-full max-w-lg bg-surface-elevated border border-line-subtle rounded-xl p-5 shadow-2xl max-h-[80vh] overflow-y-auto">
 <div className="flex items-center justify-between mb-4">
 <div>
 <h3 className="text-sm font-semibold text-content-primary">{skillModalAgent.name} 的技能树</h3>
 <p className="text-[10px] text-content-muted">
 已解锁 {skillModalData.stats?.unlocked_skills || 0}/{skillModalData.stats?.total_skills || 0} · 
 总XP {skillModalData.stats?.total_xp || 0} · 
 平均等级 Lv.{skillModalData.stats?.avg_level || 1}
 </p>
 </div>
 <button onClick={() => setShowSkillModal(false)} className="text-content-muted hover:text-content-secondary">✕</button>
 </div>
 
 <div className="space-y-2">
 {(skillModalData.skills || []).map((skill: any) => (
 <div
 key={skill.skill_id}
 className={`p-3 rounded-lg border ${skill.unlocked ? 'bg-surface-panel/50 border-line-subtle' : 'bg-surface-panel/20 border-line-subtle opacity-50'}`}
 >
 <div className="flex items-center justify-between mb-1">
 <div className="flex items-center gap-2">
 <span className="text-sm">{skill.icon || '🎯'}</span>
 <span className="text-sm font-medium text-content-primary">{skill.skill_name}</span>
 {!skill.unlocked && <span className="text-[10px] text-content-muted">(锁定)</span>}
 </div>
 <div className="flex items-center gap-1.5">
 <span className="text-[10px] text-content-muted">Lv.{skill.level}/{skill.max_level}</span>
 <span className="text-[10px] text-content-muted">{skill.current_xp} XP</span>
 </div>
 </div>
 <div className="h-1.5 bg-surface-panel rounded-full overflow-hidden">
 <div
 className={`h-full rounded-full ${skill.unlocked ? 'bg-gradient-to-r from-violet-500 to-indigo-500' : 'bg-surface-overlay'}`}
 style={{ width: `${Math.min((skill.level / skill.max_level) * 100, 100)}%` }}
 />
 </div>
 </div>
 ))}
 </div>
 
 <div className="mt-4 pt-3 border-t border-line-subtle text-[10px] text-content-muted">
 技能通过完成任务获得经验值升级。父技能达到 Lv.2 后解锁子技能。
 </div>
 </div>
 </div>
 )}

 {/* P5: 关系网络弹窗 */}
 {showRelationMatrix && relationMatrix && (
 <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
 <div className="bg-surface-elevated border border-line-subtle rounded-2xl w-full max-w-lg max-h-[80vh] overflow-hidden shadow-2xl flex flex-col">
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
 <GitBranch className="w-4 h-4 text-emerald-400" />
 </div>
 <div>
 <h2 className="font-bold text-sm">Agent 协作网络</h2>
 <p className="text-[10px] text-content-muted">
 总协作 {relationMatrix.total_collaborations || 0} 次 · 成功率 {(relationMatrix.success_rate || 0) * 100}%
 </p>
 </div>
 </div>
 <button onClick={() => setShowRelationMatrix(false)} className="p-1.5 rounded-lg hover:bg-surface-panel text-content-muted transition">
 <X className="w-5 h-5" />
 </button>
 </div>
 <div className="flex-1 overflow-y-auto p-6 space-y-4">
 {relationMatrix.links?.length === 0 ? (
 <div className="text-center text-sm text-content-muted py-8">
 暂无协作记录。创建会议室让 Agent 们一起工作吧！
 </div>
 ) : (
 <div className="space-y-3">
 {relationMatrix.links.map((link: any, i: number) => {
 const source = relationMatrix.agents.find((a: any) => a.id === link.source);
 const target = relationMatrix.agents.find((a: any) => a.id === link.target);
 return (
 <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-surface-panel/50 border border-line-subtle/50">
 <div className="flex items-center gap-2 flex-1">
 <span className="text-xs font-medium text-content-primary">{source?.name || link.source}</span>
 <div className="flex-1 h-px bg-surface-overlay relative">
 <div
 className="absolute top-0 left-0 h-px bg-emerald-500"
 style={{ width: `${(link.trust || 0.5) * 100}%` }}
 />
 </div>
 <span className="text-xs font-medium text-content-primary">{target?.name || link.target}</span>
 </div>
 <div className="text-right">
 <div className="text-[10px] text-content-muted">信任度 {(link.trust || 0).toFixed(2)}</div>
 <div className="text-[10px] text-content-muted">协作 {link.count || 0} 次</div>
 </div>
 </div>
 );
 })}
 </div>
 )}
 </div>
 </div>
 </div>
 )}
 </div>
 );
}
