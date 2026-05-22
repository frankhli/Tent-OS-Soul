import { useState, useEffect, useMemo } from 'react';
import {
  Sparkles, Brain, Puzzle, Trophy, Clock, TrendingUp, Zap, Star, Target, BookOpen, Shield, MessageSquare, Edit2, Check, X, Eye, Search, Box, Flame, CheckCircle2, Circle, AlertTriangle, Lightbulb
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import { useAIState } from '@/contexts/AIStateContext';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';
import { AvatarHomeButton } from './AvatarHomeButton';

interface SkillInfo {
  name: string;
  description: string;
  active: boolean;
}

interface Milestone {
  date: string;
  title: string;
  description: string;
  type: 'task' | 'memory' | 'skill' | 'rule' | 'level' | 'vision';
}

interface GrowthData {
  totalCalls: number;
  totalTokens: number;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  totalMemories: number;
  graphNodes: number;
  rulesTotal: number;
  rulesHighConfidence: number;
  skillsCount: number;
  positiveFeedback: number;
  negativeFeedback: number;
  corrections: number;
  assessments: number;
  avgLatency: number;
}

interface BrainStatus {
  enabled: boolean;
  cognitive_graph?: { node_count?: number; edge_count?: number } | null;
  persona?: {
    dimensions?: Record<string, number>;
    description?: string;
    evolution_count?: number;
  } | null;
}

interface AIAssistantPanelProps {
  emotion?: string;
  persona?: string;
}

function DailyQuestRow({ persona, growth }: { persona: string; growth: GrowthData | null }) {
  const personaLabel = { work: '工作模式', emergency: '应急模式', creative: '创意模式', learning: '学习模式' }[persona] || '默认模式';
  const quests = [
    { icon: <MessageSquare className="w-3.5 h-3.5" />, label: '今日对话', target: 5, current: Math.min(growth?.totalCalls ?? 0, 5), color: 'text-blue-600 bg-blue-50 border-blue-200' },
    { icon: <Target className="w-3.5 h-3.5" />, label: '完成任务', target: 3, current: Math.min(growth?.completedTasks ?? 0, 3), color: 'text-emerald-600 bg-emerald-50 border-emerald-200' },
    { icon: <Zap className="w-3.5 h-3.5" />, label: '技能训练', target: 2, current: Math.min(growth?.skillsCount ?? 0, 2), color: 'text-amber-600 bg-amber-50 border-amber-200' },
    { icon: <Flame className="w-3.5 h-3.5" />, label: '当前模式', target: 1, current: 1, color: 'text-tent-600 bg-tent-50 border-tent-200', text: personaLabel },
  ];
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {quests.map((q, i) => {
        const done = q.current >= q.target;
        return (
          <div key={i} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs ${q.color} ${done ? 'opacity-80' : ''}`}>
            {done ? <CheckCircle2 className="w-3 h-3" /> : <Circle className="w-3 h-3" />}
            <span className="font-medium">{q.label}</span>
            {q.text ? <span>{q.text}</span> : <span>{q.current}/{q.target}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function AIAssistantPanel({ emotion: _emotion = 'listening', persona: _persona = 'work' }: AIAssistantPanelProps) {
  const { sendWs } = useAIState();
  const [personaText, setPersonaText] = useState('');
  const [, setSkills] = useState<SkillInfo[]>([]);
  const [growth, setGrowth] = useState<GrowthData | null>(null);
  const [, setBrainStatus] = useState<BrainStatus | null>(null);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [assistantName, setAssistantName] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [character, setCharacter] = useState<{ name: string; avatar_type: string; avatar_config: Record<string, unknown> } | null>(null);
  const [sixAxis, setSixAxis] = useState<Record<string, { exp: number; score: number; level: number; next_level_exp_needed: number }> | null>(null);
  const [sixAxisSummary, setSixAxisSummary] = useState<{ total_exp: number; avg_score: number; title: string; max_dimension?: string; min_dimension?: string } | null>(null);
  const [personaDimensions, setPersonaDimensions] = useState<Record<string, number> | null>(null);
  const [skillsList, setSkillsList] = useState<SkillInfo[]>([]);
  const { showToast } = useToast();

  useEffect(() => {
    const load = async () => {
      try {
        const [brainRes, skillsRes, telemetryRes, memoryRes, rulesRes, tasksRes, sixAxisRes, charRes] = await Promise.all([
          fetch('/ui/api/brain/status').then((r) => r.json()).catch(() => ({})),
          fetch('/api/v1/skills').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/telemetry').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/memory/stats').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/procedural').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/tasks?limit=100').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/six-axis').then((r) => r.json()).catch(() => ({})),
          fetch('/ui/api/ai-character').then((r) => r.json()).catch(() => ({})),
        ]);

        setBrainStatus(brainRes);
        if (brainRes.persona?.description) setPersonaText(brainRes.persona.description);
        if (brainRes.persona?.dimensions) setPersonaDimensions(brainRes.persona.dimensions);

        if (charRes.name) {
          setCharacter({
            name: charRes.name,
            avatar_type: charRes.avatar_type || 'live2d',
            avatar_config: charRes.avatar_config || {},
          });
        }

        if (sixAxisRes.radar) {
          setSixAxis(sixAxisRes.radar);
          setSixAxisSummary({
            total_exp: sixAxisRes.total_exp,
            avg_score: sixAxisRes.avg_score,
            title: sixAxisRes.title,
          });
        }

        if (skillsRes.skills) {
          const mapped = skillsRes.skills.map((s: Record<string, unknown>) => ({
            name: s.name as string,
            description: s.description as string,
            active: true,
          }));
          setSkills(mapped);
          setSkillsList(mapped);
        }

        let positiveFeedback = 0, negativeFeedback = 0, correctionsCount = 0;
        try {
          const profileRes = await fetch('/ui/api/user/profile').then((r) => r.json());
          if (profileRes.assistant_name) setAssistantName(profileRes.assistant_name);
          positiveFeedback = profileRes.feedback?.positive ?? 0;
          negativeFeedback = profileRes.feedback?.negative ?? 0;
          correctionsCount = profileRes.corrections_count ?? 0;
        } catch {}

        const chatSessions = telemetryRes.llm?.chat_sessions ?? 0;
        const tasks = tasksRes.tasks || [];
        const completed = tasks.filter((t: { status: string }) => t.status === 'completed').length;
        const failed = tasks.filter((t: { status: string }) => t.status === 'failed').length;

        setGrowth({
          totalCalls: telemetryRes.llm?.total_calls ?? 0,
          totalTokens: telemetryRes.llm?.total_tokens ?? 0,
          totalTasks: chatSessions + tasks.length,
          completedTasks: chatSessions + completed,
          failedTasks: failed,
          totalMemories: memoryRes.stats?.total ?? 0,
          graphNodes: telemetryRes.memory?.graph_nodes ?? 0,
          rulesTotal: telemetryRes.rules?.total ?? 0,
          rulesHighConfidence: telemetryRes.rules?.high_confidence ?? 0,
          skillsCount: (skillsRes.skills || []).length,
          positiveFeedback,
          negativeFeedback,
          corrections: correctionsCount,
          assessments: telemetryRes.security?.assessments ?? 0,
          avgLatency: telemetryRes.llm?.avg_latency_ms ?? 0,
        });

        const ms: Milestone[] = [];
        if (tasks.length > 0) {
          const firstTask = tasks[tasks.length - 1];
          ms.push({ date: firstTask.created_at, title: '首次任务', description: firstTask.task?.slice(0, 40) || '开始执行任务', type: 'task' });
        }
        if ((rulesRes.rules || []).length > 0) {
          ms.push({ date: rulesRes.rules[0].created_at || new Date().toISOString(), title: '学会第一条规则', description: `从经验中提取了 "${rulesRes.rules[0].pattern?.slice(0, 30)}..."`, type: 'rule' });
        }
        if (telemetryRes.memory?.graph_nodes > 0) {
          ms.push({ date: telemetryRes.memory?.graph_first_created_at || new Date().toISOString(), title: '认知图谱构建', description: `建立了 ${telemetryRes.memory.graph_nodes} 个记忆节点的认知网络`, type: 'memory' });
        }
        if ((skillsRes.skills || []).length > 0) {
          ms.push({ date: skillsRes.first_loaded_at || new Date().toISOString(), title: '技能库启动', description: `加载了 ${skillsRes.skills.length} 个专业技能`, type: 'skill' });
        }
        ms.push({
          date: new Date().toISOString(),
          title: '当前等级',
          description: sixAxisRes.title || getLevelTitle(
            (chatSessions + completed) * 20 + (telemetryRes.llm?.total_calls ?? 0) * 5 + (telemetryRes.rules?.total ?? 0) * 10 +
            (telemetryRes.memory?.graph_nodes ?? 0) * 1 + (memoryRes.stats?.total ?? 0) * 5 + (skillsRes.skills || []).length * 15
          ),
          type: 'level',
        });
        setMilestones(ms);
      } catch (e) {
        showToast('AI 助手面板加载失败', 'error');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const radarData = useMemo(() => {
    if (!sixAxis) return [];
    const dimMap: Record<string, string> = {
      knowledge: '知识储备', skill: '执行能力', social: '社交情商',
      creativity: '创造力', tool_use: '工具使用', awareness: '感知觉知',
    };
    return Object.entries(sixAxis).map(([key, data]) => ({
      subject: dimMap[key] || key,
      A: data.score,
      fullMark: 100,
    }));
  }, [sixAxis]);

  const handleSaveName = async () => {
    const trimmed = nameInput.trim();
    try {
      const [profileResp, charResp] = await Promise.all([
        fetch('/ui/api/user/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assistant_name: trimmed }) }),
        fetch('/ui/api/ai-character', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: trimmed }) }),
      ]);
      if (profileResp.ok || charResp.ok) {
        setAssistantName(trimmed);
        if (character) setCharacter({ ...character, name: trimmed });
        setEditingName(false);
        showToast('AI 名称已保存', 'success');
      } else {
        showToast('名称保存失败', 'error');
      }
    } catch {
      showToast('名称保存失败，请检查网络', 'error');
    }
  };

  const levelInfo = useMemo(() => {
    if (!sixAxisSummary) return { level: 1, title: '新手', progress: 0, nextThreshold: 100, xp: 0 };
    const avg = sixAxisSummary.avg_score;
    const thresholds = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
    let level = 1;
    for (let i = 1; i < thresholds.length; i++) { if (avg >= thresholds[i]) level = i + 1; else break; }
    const currentThreshold = thresholds[level - 1] || 0;
    const nextThreshold = thresholds[level] || 100;
    const progress = Math.min(((avg - currentThreshold) / (nextThreshold - currentThreshold)) * 100, 100);
    return { level, title: sixAxisSummary.title, xp: Math.round(sixAxisSummary.total_exp), progress, nextThreshold };
  }, [sixAxisSummary]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-gray-400">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-5xl mx-auto">
        {/* Character Hero */}
        <div className="flex items-start gap-6 mb-6 p-5 bg-gradient-to-br from-tent-50 via-white to-tent-50/50 rounded-2xl border border-tent-100 shadow-sm">
          {/* Avatar（可拖拽召唤） */}
          <div className="flex-shrink-0 relative">
            <AvatarHomeButton
              source="assistant"
              size={120}
              showLevelRing={true}
              showParticles={true}
              onPet={() => {
                if (sendWs) {
                  sendWs('avatar.pet', { user_id: 'web_user', timestamp: Date.now() });
                }
              }}
            />
            <div className="absolute -bottom-1 -right-1 bg-tent-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow-sm border-2 border-white">
              Lv.{levelInfo.level}
            </div>
          </div>
          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {editingName ? (
                <div className="flex items-center gap-2">
                  <input type="text" value={nameInput} onChange={(e) => setNameInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveName(); if (e.key === 'Escape') setEditingName(false); }}
                    placeholder="给AI起个名字..." className="px-2 py-1 text-base border border-tent-300 rounded-md focus:outline-none focus:ring-2 focus:ring-tent-400 font-bold" autoFocus maxLength={20} />
                  <button onClick={handleSaveName} className="p-1 rounded text-green-600 hover:bg-green-50"><Check className="w-4 h-4" /></button>
                  <button onClick={() => setEditingName(false)} className="p-1 rounded text-gray-400 hover:bg-gray-100"><X className="w-4 h-4" /></button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-gray-900">{assistantName || 'AI助理'}</h2>
                  <button onClick={() => { setNameInput(assistantName); setEditingName(true); }} className="p-1 rounded text-gray-400 hover:text-tent-600 hover:bg-tent-50 transition-colors"><Edit2 className="w-3.5 h-3.5" /></button>
                </div>
              )}
              <span className="text-xs font-medium px-2 py-0.5 bg-tent-100 text-tent-700 rounded-full border border-tent-200">
                {levelInfo.title}
              </span>
            </div>
            <p className="text-sm text-gray-500 mb-3">
              {assistantName ? `${assistantName} 的能力、经验与成长轨迹` : '能力、经验与成长轨迹'}
            </p>
            {/* Daily Quests mini */}
            <DailyQuestRow persona={_persona} growth={growth} />
          </div>
        </div>

        {/* Top Stats Row */}
        {growth && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            <LevelCard level={levelInfo.level} title={levelInfo.title} progress={levelInfo.progress} xp={levelInfo.xp} next={levelInfo.nextThreshold} />
            <StatCard icon={<Target className="w-4 h-4 text-blue-500" />} label="累计任务" value={String(growth.totalTasks)} sub={`${growth.completedTasks} 成功 · ${growth.failedTasks} 失败`} />
            <StatCard icon={<MessageSquare className="w-4 h-4 text-purple-500" />} label="对话次数" value={String(growth.totalCalls)} sub={`${(growth.totalTokens / 1000).toFixed(1)}k tokens`} />
            <StatCard icon={<Zap className="w-4 h-4 text-amber-500" />} label="技能掌握" value={String(growth.skillsCount)} sub={`${growth.rulesTotal} 条经验规则`} />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 mb-6">
          {/* Radar Chart */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Star className="w-4 h-4 text-amber-500" />
              <h3 className="text-sm font-semibold text-gray-800">六维能力评估</h3>
            </div>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                  <PolarGrid stroke="#e5e7eb" />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar name="能力值" dataKey="A" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.2} strokeWidth={2} />
                  <RechartsTooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const val = payload[0].value as number;
                      const label = payload[0].payload?.subject as string;
                      return (
                        <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
                          <div className="font-medium text-gray-800 mb-0.5">{label}</div>
                          <div className="text-tent-600 font-semibold">能力值: {val}</div>
                        </div>
                      );
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            {sixAxis && (
              <div className="grid grid-cols-3 gap-2 mt-3">
                {Object.entries(sixAxis).map(([key, data]) => {
                  const labels: Record<string, string> = { knowledge: '知识', skill: '技能', social: '社交', creativity: '创造', tool_use: '工具', awareness: '感知' };
                  return (
                    <div key={key} className="flex items-center justify-between px-2 py-1 rounded bg-tent-50 border border-tent-100">
                      <span className="text-[10px] text-gray-500">{labels[key]}</span>
                      <span className="text-[10px] font-semibold text-tent-600">Lv.{data.level}</span>
                    </div>
                  );
                })}
              </div>
            )}
            {/* 能力总评 */}
            {sixAxisSummary && (
              <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-600">综合评分</span>
                  <span className="text-sm font-bold text-tent-600">{sixAxisSummary.avg_score.toFixed(1)}</span>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-gray-500">
                  <span>最强: <span className="font-medium text-gray-700">{sixAxisSummary.max_dimension}</span></span>
                  <span>最弱: <span className="font-medium text-gray-700">{sixAxisSummary.min_dimension}</span></span>
                  <span>总经验: <span className="font-medium text-gray-700">{sixAxisSummary.total_exp.toFixed(0)}</span></span>
                </div>
              </div>
            )}
            <p className="text-[10px] text-gray-400 text-center mt-2">
              基于真实运行数据动态计算 · 经验值随系统演化自动增长
            </p>
          </div>

          {/* Right Column */}
          <div className="space-y-4">
            {/* Persona */}
            {personaText && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-gray-800">当前人格</h3>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-tent-50 text-tent-600 border border-tent-100">
                    {_persona}
                  </span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">{personaText}</p>
              </div>
            )}

            {/* Soul 维度 */}
            {personaDimensions && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Star className="w-4 h-4 text-purple-500" />
                  <h3 className="text-sm font-semibold text-gray-800">人格维度</h3>
                </div>
                <div className="space-y-2">
                  {Object.entries({
                    formality: '正式度', humor: '幽默度', verbosity: '详尽度',
                    proactivity: '主动度', empathy: '共情度', directness: '直接度',
                    creativity: '创意度', precision: '精确度',
                  }).map(([key, label]) => {
                    const value = (personaDimensions[key] ?? 0.5) * 100;
                    return (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[10px] text-gray-500">{label}</span>
                          <span className="text-[10px] font-medium text-gray-700">{value.toFixed(0)}%</span>
                        </div>
                        <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="absolute top-0 left-0 h-full bg-purple-400 rounded-full transition-all" style={{ width: `${value}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 成长详情 */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="w-4 h-4 text-purple-500" />
                <h3 className="text-sm font-semibold text-gray-800">成长详情</h3>
              </div>
              {sixAxis ? (
                <div className="space-y-2">
                  {Object.entries(sixAxis).map(([key, data]) => {
                    const labels: Record<string, { label: string; color: string; icon: string }> = {
                      knowledge: { label: '知识储备', color: 'bg-blue-500', icon: '📚' },
                      skill: { label: '执行能力', color: 'bg-green-500', icon: '⚡' },
                      social: { label: '社交情商', color: 'bg-pink-500', icon: '💬' },
                      creativity: { label: '创造力', color: 'bg-purple-500', icon: '✨' },
                      tool_use: { label: '工具使用', color: 'bg-amber-500', icon: '🔧' },
                      awareness: { label: '感知觉知', color: 'bg-cyan-500', icon: '👁️' },
                    };
                    const info = labels[key] || { label: key, color: 'bg-gray-500', icon: '◆' };
                    return (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-medium text-gray-700">{info.icon} {info.label}</span>
                          <span className="text-[10px] text-gray-400">{data.exp.toFixed(0)}exp · Lv.{data.level}</span>
                        </div>
                        <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className={`absolute top-0 left-0 h-full ${info.color} rounded-full transition-all`} style={{ width: `${data.score}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-gray-400">成长数据加载中...</p>
              )}
            </div>

            {/* 认知图谱快速查询 */}
            <CognitiveGraphCard />

            {/* 情绪时间线 */}
            <EmotionTimelineCard />

            {/* Phase 4: 主动关怀统计 */}
            <ProactiveCareCard />

            {/* 物体清单 —— AI的眼睛看到的一切 */}
            <VisualInventoryCard />

            {/* Skills Quick View */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Puzzle className="w-4 h-4 text-blue-500" />
                <h3 className="text-sm font-semibold text-gray-800">已加载能力</h3>
                <span className="text-[10px] text-gray-400">({skillsList.length})</span>
              </div>
              {skillsList.length === 0 ? (
                <div className="text-center py-3">
                  <Puzzle className="w-5 h-5 text-gray-300 mx-auto mb-1" />
                  <p className="text-[10px] text-gray-400">尚未解锁技能</p>
                  <p className="text-[10px] text-gray-300">完成任务即可激活能力</p>
                </div>
              ) : (
                <div className="space-y-1.5 max-h-32 overflow-y-auto">
                  {skillsList.slice(0, 8).map((s) => (
                    <div key={s.name} className="flex items-center gap-2 text-xs group cursor-default">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0 group-hover:bg-blue-500 transition-colors" />
                      <span className="text-gray-700 truncate" title={s.description}>{s.name}</span>
                    </div>
                  ))}
                  {skillsList.length > 8 && (
                    <p className="text-[10px] text-gray-400 pl-3.5">+{skillsList.length - 8} 更多...</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Milestones */}
        {milestones.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Trophy className="w-4 h-4 text-amber-500" />
              <h3 className="text-sm font-semibold text-gray-800">成长里程碑</h3>
            </div>
            <div className="relative">
              <div className="absolute left-3.5 top-0 bottom-0 w-px bg-gray-200" />
              <div className="space-y-4">
                {milestones.map((m, idx) => (
                  <div key={idx} className="flex items-start gap-3 pl-1">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 z-10 ${milestoneColor(m.type)}`}>
                      {milestoneIcon(m.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-gray-900">{m.title}</span>
                        <span className="text-[10px] text-gray-400">
                          {new Date(m.date).toLocaleDateString('zh-CN')}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{m.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Detailed Stats */}
        {growth && (
          <div className="grid grid-cols-4 gap-3">
            <MiniStat icon={<BookOpen className="w-3.5 h-3.5 text-purple-500" />} label="记忆总量" value={String(growth.totalMemories)} />
            <MiniStat icon={<Brain className="w-3.5 h-3.5 text-blue-500" />} label="图谱节点" value={String(growth.graphNodes)} />
            <MiniStat icon={<Shield className="w-3.5 h-3.5 text-green-500" />} label="高置信规则" value={String(growth.rulesHighConfidence)} />
            <MiniStat icon={<Clock className="w-3.5 h-3.5 text-gray-500" />} label="平均延迟" value={`${growth.avgLatency.toFixed(0)}ms`} />
          </div>
        )}
      </div>
    </div>
  );
}

function LevelCard({ level, title, progress, xp, next }: { level: number; title: string; progress: number; xp: number; next: number }) {
  return (
    <div className="bg-gradient-to-br from-tent-500 to-tent-700 rounded-xl p-4 text-white">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Trophy className="w-5 h-5 text-amber-300" />
          <span className="text-xs font-medium text-white/80">等级 {level}</span>
        </div>
        <span className="text-xs font-bold">{title}</span>
      </div>
      <div className="relative h-2 bg-white/20 rounded-full overflow-hidden mb-2">
        <div className="absolute left-0 top-0 h-full bg-amber-300 rounded-full transition-all" style={{ width: `${progress}%` }} />
      </div>
      <div className="flex items-center justify-between text-[10px] text-white/70">
        <span>XP: {xp}</span>
        <span>下一级: {next}</span>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-xs text-gray-500">{label}</span></div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      {sub && <div className="text-[10px] text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

function MiniStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 flex items-center gap-3">
      {icon}
      <div>
        <div className="text-[10px] text-gray-400">{label}</div>
        <div className="text-sm font-semibold text-gray-900">{value}</div>
      </div>
    </div>
  );
}

function milestoneColor(type: string) {
  switch (type) {
    case 'task': return 'bg-blue-100 text-blue-600';
    case 'memory': return 'bg-purple-100 text-purple-600';
    case 'skill': return 'bg-green-100 text-green-600';
    case 'rule': return 'bg-amber-100 text-amber-600';
    case 'level': return 'bg-tent-100 text-tent-600';
    default: return 'bg-gray-100 text-gray-600';
  }
}

function milestoneIcon(type: string) {
  switch (type) {
    case 'task': return <Target className="w-3 h-3" />;
    case 'memory': return <Brain className="w-3 h-3" />;
    case 'skill': return <Puzzle className="w-3 h-3" />;
    case 'rule': return <BookOpen className="w-3 h-3" />;
    case 'level': return <TrendingUp className="w-3 h-3" />;
    default: return <Star className="w-3 h-3" />;
  }
}

function VisualInventoryCard() {
  const [objects, setObjects] = useState<Array<{object_name: string; location: string; confidence: number; last_seen: string}>>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<{found: boolean; object_name?: string; location?: string; last_seen?: string} | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('/ui/api/vision/objects')
      .then((r) => r.json())
      .then((data) => setObjects(data.objects || []))
      .catch(() => setObjects([]));
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch(`/ui/api/vision/find?object=${encodeURIComponent(searchQuery)}`);
      const data = await resp.json();
      setSearchResult(data);
    } catch {
      setSearchResult({ found: false });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Eye className="w-4 h-4 text-purple-500" />
        <h3 className="text-sm font-semibold text-gray-800">AI 视觉记忆</h3>
        <span className="text-[10px] text-gray-400 ml-auto">{objects.length} 个已知物体</span>
      </div>

      {/* 搜索框 */}
      <div className="flex items-center gap-2 mb-3">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索物体位置，如：遥控器..."
          className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-100 focus:border-purple-300"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="shrink-0 px-3 py-1.5 bg-purple-50 text-purple-600 rounded-lg text-xs border border-purple-200 hover:bg-purple-100 disabled:opacity-50"
        >
          {loading ? <Search className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
        </button>
      </div>

      {/* 搜索结果 */}
      {searchResult && (
        <div className={`mb-3 px-3 py-2 rounded-lg text-xs ${searchResult.found ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-gray-200'}`}>
          {searchResult.found ? (
            <div className="flex items-center gap-2">
              <Box className="w-3.5 h-3.5 text-green-500" />
              <span className="text-green-700">
                <strong>{searchResult.object_name}</strong> 在 <strong>{searchResult.location || '未知位置'}</strong>
                {searchResult.last_seen && <span className="text-green-500 ml-1">({new Date(searchResult.last_seen).toLocaleDateString('zh-CN')})</span>}
              </span>
            </div>
          ) : (
            <span className="text-gray-500">暂未在视觉记忆中找到 "{searchQuery}"</span>
          )}
        </div>
      )}

      {/* 物体列表 */}
      {objects.length > 0 ? (
        <div className="space-y-1.5 max-h-40 overflow-y-auto">
          {objects.slice(0, 10).map((obj, idx) => (
            <div key={idx} className="flex items-center justify-between px-2 py-1.5 rounded bg-gray-50 text-xs">
              <div className="flex items-center gap-2">
                <Box className="w-3 h-3 text-gray-400" />
                <span className="text-gray-700">{obj.object_name}</span>
              </div>
              <span className="text-gray-400 truncate max-w-[120px]">{obj.location || '位置未知'}</span>
            </div>
          ))}
          {objects.length > 10 && (
            <div className="text-center text-[10px] text-gray-400 py-1">+{objects.length - 10} 个物体</div>
          )}
        </div>
      ) : (
        <p className="text-xs text-gray-400">AI 尚未记录任何物体。开启摄像头或上传图片开始构建空间记忆。</p>
      )}
    </div>
  );
}

function CognitiveGraphCard() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Array<{id: string; content: string; type: string; confidence: number}>>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch(`/ui/api/brain/graph/query?keyword=${encodeURIComponent(query)}&limit=8`);
      const data = await resp.json();
      setResults(data.results || []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="w-4 h-4 text-blue-500" />
        <h3 className="text-sm font-semibold text-gray-800">认知图谱</h3>
      </div>
      <div className="flex items-center gap-2 mb-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索记忆节点..."
          className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="shrink-0 px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs border border-blue-200 hover:bg-blue-100 disabled:opacity-50"
        >
          {loading ? <Search className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
        </button>
      </div>
      {results.length > 0 ? (
        <div className="space-y-1.5 max-h-40 overflow-y-auto">
          {results.map((r) => (
            <div key={r.id} className="flex items-start gap-2 px-2 py-1.5 rounded bg-gray-50 text-xs">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-gray-700 truncate">{r.content}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-gray-400">{r.type}</span>
                  <span className="text-[10px] text-blue-400">{(r.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-400">输入关键词搜索认知图谱中的记忆节点</p>
      )}
    </div>
  );
}

function EmotionTimelineCard() {
  const { state: aiState } = useAIState();
  const [history, setHistory] = useState<Array<{primary: string; intensity: number; valence: number; authenticity: number; timestamp: number; trend: string}>>([]);
  const [insights, setInsights] = useState<{dominant: string; avg_intensity: number; authenticity_avg: number; trend_direction: string; record_count: number} | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch('/ui/api/emotion/fusion/history?user_id=web_user&hours=6&limit=50').then(r => r.json()).catch(() => ({ records: [] })),
      fetch('/ui/api/emotion/fusion/insights?user_id=web_user&window_hours=6').then(r => r.json()).catch(() => null),
    ]).then(([histData, insightData]) => {
      setHistory(histData.records || []);
      setInsights(insightData);
    }).finally(() => setLoading(false));
  }, []);

  const emotionColor = (emotion: string) => {
    const map: Record<string, string> = {
      happy: 'text-green-500', joy: 'text-green-500', excited: 'text-amber-500',
      sad: 'text-blue-500', sadness: 'text-blue-500', tired: 'text-gray-500',
      angry: 'text-red-500', anger: 'text-red-500', frustrated: 'text-orange-500',
      fear: 'text-purple-500', fearful: 'text-purple-500',
      neutral: 'text-gray-400', surprise: 'text-amber-400', disgust: 'text-lime-600',
      sleepy: 'text-indigo-400', thinking: 'text-teal-500', listening: 'text-emerald-500',
    };
    return map[emotion] || 'text-gray-400';
  };

  const barColor = (emotion: string) => {
    const map: Record<string, string> = {
      happy: '#86efac', joy: '#86efac', excited: '#fcd34d',
      sad: '#93c5fd', sadness: '#93c5fd', tired: '#d1d5db',
      angry: '#fca5a5', anger: '#fca5a5', frustrated: '#fdba74',
      fear: '#d8b4fe', fearful: '#d8b4fe',
      neutral: '#e5e7eb', surprise: '#fde68a', disgust: '#bef264',
      sleepy: '#c7d2fe', thinking: '#5eead4', listening: '#6ee7b7',
    };
    return map[emotion] || '#e5e7eb';
  };

  // 显示融合情绪的实时状态
  const fused = aiState.fusedEmotion;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-pink-500" />
          <h3 className="text-sm font-semibold text-gray-800">情绪时间线</h3>
        </div>
        {fused && (
          <div className="flex items-center gap-1.5">
            <span className={`text-[10px] font-medium capitalize ${emotionColor(fused.primary)}`}>{fused.primary}</span>
            <span className="text-[10px] text-gray-400">·</span>
            <span className="text-[10px] text-gray-400">{(fused.intensity * 100).toFixed(0)}%</span>
            {fused.authenticity < 0.5 && (
              <span title="真实性低"><AlertTriangle className="w-3 h-3 text-red-400" /></span>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <p className="text-xs text-gray-400">加载中...</p>
      ) : history.length === 0 ? (
        <p className="text-xs text-gray-400">暂无情绪数据，开始对话后自动记录</p>
      ) : (
        <>
          <div className="flex items-end gap-1 h-14 mb-2">
            {history.slice(-30).map((t, i) => (
              <div
                key={i}
                className="flex-1 rounded-t-sm hover:opacity-80 transition-colors relative group"
                style={{ height: `${Math.max(4, (t.intensity || 0.3) * 100)}%`, backgroundColor: barColor(t.primary), minHeight: 3 }}
                title={`${t.primary} · 强度${(t.intensity * 100).toFixed(0)}% · ${new Date(t.timestamp * 1000).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'})}`}
              >
                <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                  <span className={`${emotionColor(t.primary)} font-medium`}>{t.primary}</span>
                </div>
              </div>
            ))}
          </div>
          {insights && (
            <div className="flex items-center gap-3 mt-2 pt-2 border-t border-gray-100">
              <span className="text-[10px] text-gray-400">主导: <span className={`font-medium ${emotionColor(insights.dominant)}`}>{insights.dominant}</span></span>
              <span className="text-[10px] text-gray-400">强度: <span className="font-medium text-gray-600">{(insights.avg_intensity * 100).toFixed(0)}%</span></span>
              <span className="text-[10px] text-gray-400">真实: <span className={`font-medium ${insights.authenticity_avg >= 0.7 ? 'text-green-600' : insights.authenticity_avg >= 0.4 ? 'text-amber-600' : 'text-red-600'}`}>{(insights.authenticity_avg * 100).toFixed(0)}%</span></span>
              <span className="text-[10px] text-gray-400 ml-auto">{insights.record_count} 条</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ProactiveCareCard() {
  const [stats, setStats] = useState({ count: 0, types: [] as string[] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 从会话历史中统计 proactive 消息
    // 实际实现可改为从后端 API 获取
    setLoading(false);
    setStats({ count: 0, types: [] });
  }, []);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-4 h-4 text-amber-500" />
        <h3 className="text-sm font-semibold text-gray-800">主动关怀</h3>
      </div>
      {loading ? (
        <p className="text-xs text-gray-400">加载中...</p>
      ) : stats.count === 0 ? (
        <p className="text-xs text-gray-400">系统正在观察你的状态，需要时会主动发起关怀。</p>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">今日主动触发</span>
            <span className="font-semibold text-amber-600">{stats.count} 次</span>
          </div>
          {stats.types.map((t, i) => (
            <div key={i} className="flex items-center gap-1.5 text-[10px] text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function getLevelTitle(xp: number): string {
  if (xp >= 10000) return '传说';
  if (xp >= 7500) return '大师';
  if (xp >= 5500) return '专家';
  if (xp >= 4000) return '资深';
  if (xp >= 3000) return '熟练';
  if (xp >= 2200) return '进阶';
  if (xp >= 1500) return '中级';
  if (xp >= 1000) return '初级';
  if (xp >= 300) return '入门';
  return '新手';
}
