import { useState, useMemo } from 'react';
import { Waves } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';

interface EmotionRecord {
 id: string;
 timestamp: number;
 source: 'user' | 'ai';
 emotion: string;
 valence: number;
 arousal: number;
 intensity: number;
 authenticity: number;
 evidence: string;
}

interface Props {
 records: EmotionRecord[];
 onClear?: () => void;
}

const EMOTION_COLORS: Record<string, string> = {
 joy: '#fbbf24', happiness: '#fbbf24', excited: '#f59e0b',
 sadness: '#60a5fa', sad: '#60a5fa', melancholy: '#3b82f6',
 anger: '#f87171', angry: '#f87171', rage: '#ef4444',
 fear: '#a78bfa', scared: '#a78bfa', anxious: '#8b5cf6',
 surprise: '#34d399', shocked: '#34d399', amazed: '#10b981',
 disgust: '#a3a3a3', contempt: '#737373',
 calm: '#22d3ee', peaceful: '#06b6d4', serene: '#0891b2',
 thinking: '#818cf8', curious: '#6366f1', confused: '#4f46e5',
 listening: '#c084fc', neutral: '#94a3b8',
};

const AUTHENTICITY_LABELS = [
 { max: 0.4, label: '强撑', color: '#ef4444' },
 { max: 0.7, label: '存疑', color: '#f59e0b' },
 { max: 1.0, label: '真实', color: '#22c55e' },
];

export default function EmotionTimeline({ records, onClear }: Props) {
 const [timeWindow, setTimeWindow] = useState<number>(24);
 const [selectedSource, setSelectedSource] = useState<'all' | 'user' | 'ai'>('all');
 const isDark = typeof window !== 'undefined' && document.documentElement.classList.contains('dark');
 const gridStroke = isDark ? '#1e293b' : '#e2e8f0';
 const tooltipBg = isDark ? '#0f172a' : '#fff';
 const tooltipBorder = isDark ? '1px solid #334155' : '1px solid #e2e8f0';

 const filtered = useMemo(() => {
 const cutoff = Date.now() - timeWindow * 60 * 60 * 1000;
 return records
 .filter((r) => r.timestamp >= cutoff)
 .filter((r) => selectedSource === 'all' || r.source === selectedSource)
 .sort((a, b) => a.timestamp - b.timestamp);
 }, [records, timeWindow, selectedSource]);

 const vaData = useMemo(() => {
 return filtered.map((r) => ({
 time: new Date(r.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
 valence: r.valence,
 arousal: r.arousal,
 emotion: r.emotion,
 source: r.source,
 }));
 }, [filtered]);

 const distribution = useMemo(() => {
 const counts: Record<string, number> = {};
 filtered.forEach((r) => {
 counts[r.emotion] = (counts[r.emotion] || 0) + 1;
 });
 return Object.entries(counts)
 .map(([emotion, count]) => ({ emotion, count, color: EMOTION_COLORS[emotion] || '#94a3b8' }))
 .sort((a, b) => b.count - a.count)
 .slice(0, 8);
 }, [filtered]);

 const stats = useMemo(() => {
 if (filtered.length === 0) return null;
 const avgValence = filtered.reduce((s, r) => s + r.valence, 0) / filtered.length;
 const avgArousal = filtered.reduce((s, r) => s + r.arousal, 0) / filtered.length;
 const avgAuthenticity = filtered.reduce((s, r) => s + r.authenticity, 0) / filtered.length;
 const dominant = distribution[0]?.emotion || 'neutral';
 const trend = filtered.length >= 2
 ? (filtered[filtered.length - 1].valence > filtered[0].valence ? '↗ 改善' : '↘ 低落')
 : '→ 平稳';
 return { avgValence, avgArousal, avgAuthenticity, dominant, trend, count: filtered.length };
 }, [filtered, distribution]);

 const authenticityBadge = (score: number) => {
 const item = AUTHENTICITY_LABELS.find((a) => score <= a.max) || AUTHENTICITY_LABELS[2];
 return <span className="text-[10px] px-1.5 py-0.5 rounded-full text-white" style={{ backgroundColor: item.color }}>{item.label}</span>;
 };

 if (records.length === 0) {
 return (
 <div className="flex flex-col items-center justify-center h-64 text-center px-6">
 <Waves className="w-10 h-10 text-content-muted mb-3" />
 <div className="text-sm text-content-muted font-medium">情绪时光轴</div>
 <div className="text-xs text-content-secondary mt-1 max-w-sm">
 每次对话时，系统会自动分析你和 AI 的情绪状态（开心、悲伤、焦虑、平静等），生成这条时间线。
 </div>
 <div className="mt-4 p-3 rounded-lg bg-surface-panel/60 border border-line-subtle/50 text-left max-w-sm">
 <div className="text-[10px] text-content-muted font-medium mb-1.5">例如：</div>
 <div className="flex items-center gap-2 text-[11px] text-content-muted">
 <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
 你说"今天工作好累" → 检测到<span className="text-amber-400">疲惫</span>
 </div>
 <div className="flex items-center gap-2 text-[11px] text-content-muted mt-1">
 <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
 你说"太好了！" → 检测到<span className="text-emerald-400">开心</span>
 </div>
 </div>
 <div className="text-[10px] text-content-secondary mt-3">
 去「对讲机」页面对话，情绪记录会自动出现在这里
 </div>
 </div>
 );
 }

 return (
 <div className="h-full flex flex-col bg-surface-panel rounded-2xl border border-line-subtle overflow-hidden">
 {/* Header */}
 <div className="shrink-0 p-4 border-b border-line-subtle">
 <div className="flex items-center justify-between mb-3">
 <h3 className="text-sm font-medium text-content-primary flex items-center gap-2">
 <Waves className="w-4 h-4" /> 情绪时间线
 </h3>
 {onClear && (
 <button onClick={onClear} className="text-[10px] text-content-muted hover:text-content-secondary transition">清空记录</button>
 )}
 </div>

 {/* Filters */}
 <div className="flex items-center gap-2 mb-3">
 {[{ label: '1小时', v: 1 }, { label: '6小时', v: 6 }, { label: '24小时', v: 24 }, { label: '7天', v: 168 }].map((t) => (
 <button
 key={t.v}
 onClick={() => setTimeWindow(t.v)}
 className={`text-[10px] px-2 py-1 rounded-full transition ${
 timeWindow === t.v ? 'bg-violet-600 text-white' : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
 }`}
 >
 {t.label}
 </button>
 ))}
 </div>

 <div className="flex items-center gap-2">
 {[{ label: '全部', v: 'all' }, { label: '用户', v: 'user' }, { label: 'AI', v: 'ai' }].map((s) => (
 <button
 key={s.v}
 onClick={() => setSelectedSource(s.v as any)}
 className={`text-[10px] px-2 py-1 rounded-full transition ${
 selectedSource === s.v ? 'bg-indigo-600 text-white' : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
 }`}
 >
 {s.label}
 </button>
 ))}
 </div>
 </div>

 {/* Stats Cards */}
 {stats && (
 <div className="shrink-0 grid grid-cols-3 gap-2 p-4 border-b border-line-subtle">
 <div className="p-2.5 rounded-lg bg-surface-overlay/60 border border-line-active/40">
 <div className="text-[10px] text-content-muted mb-1">主导情绪</div>
 <div className="text-sm font-medium" style={{ color: EMOTION_COLORS[stats.dominant] || '#94a3b8' }}>
 {stats.dominant}
 </div>
 </div>
 <div className="p-2.5 rounded-lg bg-surface-overlay/60 border border-line-active/40">
 <div className="text-[10px] text-content-muted mb-1">真实性</div>
 <div className="flex items-center gap-1.5">
 {authenticityBadge(stats.avgAuthenticity)}
 <span className="text-xs text-content-muted">{Math.round(stats.avgAuthenticity * 100)}%</span>
 </div>
 </div>
 <div className="p-2.5 rounded-lg bg-surface-overlay/60 border border-line-active/40">
 <div className="text-[10px] text-content-muted mb-1">趋势</div>
 <div className="text-sm font-medium text-content-secondary">{stats.trend}</div>
 </div>
 </div>
 )}

 {/* Charts */}
 <div className="flex-1 overflow-y-auto p-4 space-y-4">
 {/* VA Chart */}
 {vaData.length > 1 && (
 <div>
 <div className="text-xs text-content-muted mb-2">愉悦度 × 唤醒度</div>
 <div className="h-32 min-h-[80px]">
 <ResponsiveContainer width="100%" height="100%" minWidth={200} minHeight={60}>
 <AreaChart data={vaData}>
 <defs>
 <linearGradient id="valenceGrad" x1="0" y1="0" x2="0" y2="1">
 <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
 <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
 </linearGradient>
 </defs>
 <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
 <XAxis dataKey="time" tick={{ fill: '#475569', fontSize: 9 }} interval={Math.floor(vaData.length / 4)} />
 <YAxis domain={[-1, 1]} tick={{ fill: '#475569', fontSize: 9 }} />
 <Tooltip
 contentStyle={{ backgroundColor: tooltipBg, border: tooltipBorder, borderRadius: 8, fontSize: 11 }}
 labelStyle={{ color: '#94a3b8' }}
 />
 <Area type="monotone" dataKey="valence" stroke="#8b5cf6" fill="url(#valenceGrad)" strokeWidth={1.5} name="愉悦度" />
 </AreaChart>
 </ResponsiveContainer>
 </div>
 </div>
 )}

 {/* Distribution */}
 {distribution.length > 0 && (
 <div>
 <div className="text-xs text-content-muted mb-2">情绪分布</div>
 <div className="h-32 min-h-[80px]">
 <ResponsiveContainer width="100%" height="100%" minWidth={200} minHeight={60}>
 <BarChart data={distribution} layout="vertical">
 <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} horizontal={false} />
 <XAxis type="number" tick={{ fill: '#475569', fontSize: 9 }} />
 <YAxis dataKey="emotion" type="category" tick={{ fill: '#94a3b8', fontSize: 10 }} width={60} />
 <Tooltip
 contentStyle={{ backgroundColor: tooltipBg, border: tooltipBorder, borderRadius: 8, fontSize: 11 }}
 />
 <Bar dataKey="count" radius={[0, 4, 4, 0]}>
 {distribution.map((entry, index) => (
 <Cell key={index} fill={entry.color} />
 ))}
 </Bar>
 </BarChart>
 </ResponsiveContainer>
 </div>
 </div>
 )}

 {/* Recent Records */}
 <div>
 <div className="text-xs text-content-muted mb-2">最近记录 ({filtered.length}条)</div>
 <div className="space-y-1.5">
 {filtered.slice(-10).reverse().map((r) => (
 <div key={r.id} className="flex items-center gap-2 p-2 rounded-lg bg-surface-overlay/40 border border-line-active/30">
 <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-surface-overlay bg-slate-600 text-content-secondary shrink-0">
 {r.source === 'user' ? '你' : 'AI'}
 </span>
 <span className="text-xs" style={{ color: EMOTION_COLORS[r.emotion] || '#94a3b8' }}>{r.emotion}</span>
 <span className="text-[10px] text-content-muted ml-auto">
 {new Date(r.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
 </span>
 </div>
 ))}
 </div>
 </div>
 </div>
 </div>
 );
}
