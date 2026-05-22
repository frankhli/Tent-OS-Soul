import { useState, useEffect, useRef } from 'react';
import { Mic, MessageCircle, ScrollText, Camera, Sparkles, Plus, X, CheckCircle2, Circle, ArrowRight } from 'lucide-react';
import { USER_ID } from '../api/soulApi';

interface Suggestion {
 id: string;
 title: string;
 subtitle: string;
 icon: React.ReactNode;
 action: string;
 priority: 'high' | 'medium' | 'low';
}

interface Todo {
 id: number;
 title: string;
 description: string;
 status: string;
 priority: string;
 created_at: string;
}

const priorityConfig: Record<string, { label: string; dot: string; border: string }> = {
 high: { label: '高', dot: 'bg-amber-500', border: 'border-amber-200' },
 medium: { label: '中', dot: 'bg-blue-400', border: 'border-blue-200' },
 low: { label: '低', dot: 'bg-slate-300', border: 'border-slate-200' },
};

export default function TodoPanel() {
 const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
 const [todos, setTodos] = useState<Todo[]>([]);
 const [loading, setLoading] = useState(true);
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [newTitle, setNewTitle] = useState('');
 const [newPriority, setNewPriority] = useState('medium');
 const [showInput, setShowInput] = useState(false);
 const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('pending');

 useEffect(() => {
 loadAll();
 const iv = setInterval(loadAll, 30000);
 return () => clearInterval(iv);
 }, []);

 const loadAll = async () => {
 setLoading(true);
 try {
 await Promise.all([loadSuggestions(), loadTodos()]);
 } finally {
 if (mountedRef.current) setLoading(false);
 }
 };

 const loadSuggestions = async () => {
 try {
 const res = await fetch(`/api/v1/soul/completeness/${USER_ID}`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 if (!mountedRef.current) return;
 const comps = {
 thought: data.thought ?? 0,
 voice: data.voice ?? 0,
 appearance: data.appearance ?? 0,
 overall: data.overall ?? 0,
 };

 const items: Suggestion[] = [];
 if (comps.thought < 0.3) {
 items.push({ id: 'thought', title: '开启首次对话', subtitle: '让 AI 了解你的思维方式', icon: <MessageCircle className="w-4 h-4" />, action: 'chat', priority: 'high' });
 }
 if (comps.voice < 0.3) {
 items.push({ id: 'voice', title: '录制语音样本', subtitle: '收集声音数据用于未来克隆', icon: <Mic className="w-4 h-4" />, action: 'voice', priority: 'high' });
 }
 if (comps.appearance < 0.3) {
 items.push({ id: 'appearance', title: '上传参考照片', subtitle: '上传正面照帮助构建数字形象', icon: <Camera className="w-4 h-4" />, action: 'photo', priority: 'high' });
 }
 if (comps.overall >= 0.3 && comps.overall < 0.7) {
 items.push({ id: 'continue', title: '继续深度对话', subtitle: `当前完成度 ${Math.round(comps.overall * 100)}%`, icon: <Sparkles className="w-4 h-4" />, action: 'chat', priority: 'medium' });
 }
 if (comps.voice >= 0.3 && comps.voice < 0.8) {
 items.push({ id: 'more_voice', title: '补充更多语音', subtitle: `已有 ${Math.round(comps.voice * 100)}%`, icon: <Mic className="w-4 h-4" />, action: 'voice', priority: 'medium' });
 }
 if (comps.overall >= 0.7) {
 items.push({ id: 'will', title: '配置数字遗嘱', subtitle: '指定继承人与激活条件', icon: <ScrollText className="w-4 h-4" />, action: 'will', priority: 'low' });
 }
 const order = { high: 0, medium: 1, low: 2 };
 items.sort((a, b) => order[a.priority] - order[b.priority]);
 if (mountedRef.current) setSuggestions(items.slice(0, 5));
 } catch {
 if (mountedRef.current) setSuggestions([
 { id: 's1', title: '与 AI 对话', subtitle: '积累思维数据', icon: <MessageCircle className="w-4 h-4" />, action: 'chat', priority: 'high' },
 { id: 's2', title: '录制语音样本', subtitle: '收集声纹数据', icon: <Mic className="w-4 h-4" />, action: 'voice', priority: 'high' },
 ]);
 }
 };

 const loadTodos = async () => {
 try {
 const res = await fetch(`/api/v1/todos?user_id=${USER_ID}&limit=10`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 if (mountedRef.current) setTodos(data.todos || []);
 } catch {
 if (mountedRef.current) setTodos([]);
 }
 };

 const createTodo = async () => {
 if (!newTitle.trim()) return;
 try {
 await fetch('/api/v1/todos', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ user_id: USER_ID, title: newTitle.trim(), priority: newPriority }),
 });
 setNewTitle('');
 setNewPriority('medium');
 setShowInput(false);
 loadTodos();
 } catch {
 // ignore
 }
 };

 const toggleTodo = async (id: number, currentStatus: string) => {
 const next = currentStatus === 'completed' ? 'pending' : 'completed';
 try {
 await fetch(`/api/v1/todos/${id}`, {
 method: 'PATCH',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ status: next }),
 });
 loadTodos();
 } catch {
 // ignore
 }
 };

 const deleteTodo = async (id: number) => {
 try {
 await fetch(`/api/v1/todos/${id}`, { method: 'DELETE' });
 loadTodos();
 } catch {
 // ignore
 }
 };

 const handleClick = (action: string) => {
 if (action === 'chat') {
 document.querySelector('textarea')?.focus();
 } else if (action === 'voice' || action === 'photo' || action === 'will') {
 window.dispatchEvent(new CustomEvent('soul-action', { detail: { action } }));
 }
 };

 const filteredTodos = todos.filter((t) => {
 if (filter === 'all') return true;
 return t.status === filter;
 });

 const pendingCount = todos.filter((t) => t.status === 'pending').length;
 const completedCount = todos.filter((t) => t.status === 'completed').length;

 return (
 <div className="space-y-5">
 {/* Todos */}
 <div>
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider">待办事项</h4>
 <div className="flex items-center gap-1">
 <button onClick={() => setShowInput(!showInput)} className="text-xs text-accent hover:text-accent font-medium flex items-center gap-0.5 p-1 rounded hover:bg-accent-subtle transition">
 <Plus className="w-3 h-3" />
 </button>
 <a href="/tasks" className="text-xs text-content-muted hover:text-accent p-1 rounded hover:bg-surface-overlay transition" title="打开任务管理">
 <ArrowRight className="w-3 h-3" />
 </a>
 </div>
 </div>

 {/* Filter Tabs */}
 <div className="flex gap-1 mb-2">
 {(['pending', 'completed', 'all'] as const).map((f) => (
 <button
 key={f}
 onClick={() => setFilter(f)}
 className={`text-[10px] px-2 py-0.5 rounded-full transition ${
 filter === f
 ? 'bg-surface-overlay text-content-primary'
 : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
 }`}
 >
 {f === 'pending' ? `待办 ${pendingCount}` : f === 'completed' ? `已完成 ${completedCount}` : `全部 ${todos.length}`}
 </button>
 ))}
 </div>

 {showInput && (
 <div className="flex gap-2 mb-2">
 <input
 type="text"
 value={newTitle}
 onChange={(e) => setNewTitle(e.target.value)}
 onKeyDown={(e) => e.key === 'Enter' && createTodo()}
 placeholder="输入待办内容..."
 className="flex-1 bg-surface-elevated border border-line-subtle rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-violet-400"
 autoFocus
 />
 <select
 value={newPriority}
 onChange={(e) => setNewPriority(e.target.value)}
 className="text-xs border border-line-subtle rounded-lg px-2 py-1.5 bg-surface-elevated focus:outline-none focus:border-violet-400"
 >
 <option value="high">高优</option>
 <option value="medium">中优</option>
 <option value="low">低优</option>
 </select>
 <button onClick={createTodo} className="px-3 py-1.5 bg-violet-600 text-white rounded-lg text-sm hover:bg-violet-700 transition">添加</button>
 </div>
 )}

 {filteredTodos.length === 0 ? (
 <div className="flex flex-col items-center justify-center py-8 text-center">
 <CheckCircle2 className="w-8 h-8 text-line-active mb-2" />
 <div className="text-sm text-content-muted font-medium">
 {filter === 'pending' ? '暂无待办事项' : filter === 'completed' ? '暂无已完成任务' : '暂无任务'}
 </div>
 <div className="text-xs text-content-disabled mt-1">
 {filter === 'pending' ? '对话中 AI 会自动创建待办' : '继续对话以生成更多任务'}
 </div>
 </div>
 ) : (
 <div className="space-y-1.5">
 {filteredTodos.map((t) => {
 const pc = priorityConfig[t.priority] || priorityConfig.medium;
 return (
 <div
 key={t.id}
 className={`flex items-center gap-2 p-2 rounded-lg bg-surface-elevated border transition group ${
 t.status === 'completed' ? 'border-line-subtle opacity-60' : pc.border
 }`}
 >
 <button
 onClick={() => toggleTodo(t.id, t.status)}
 className="shrink-0 text-content-muted hover:text-accent transition"
 >
 {t.status === 'completed' ? (
 <CheckCircle2 className="w-4 h-4 text-accent" />
 ) : (
 <Circle className="w-4 h-4" />
 )}
 </button>
 <div className="flex-1 min-w-0">
 <div className={`text-sm truncate ${t.status === 'completed' ? 'text-content-muted line-through' : 'text-content-secondary'}`}>
 {t.title}
 </div>
 {t.description && (
 <div className="text-[10px] text-content-muted truncate">{t.description}</div>
 )}
 </div>
 <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${pc.dot}`} title={pc.label} />
 <button onClick={() => deleteTodo(t.id)} className="shrink-0 opacity-0 group-hover:opacity-100 text-content-secondary hover:text-red-400 transition">
 <X className="w-3.5 h-3.5" />
 </button>
 </div>
 );
 })}
 </div>
 )}
 </div>

 {/* Suggestions */}
 <div>
 <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider mb-3">成长建议</h4>
 {loading ? (
 <div className="space-y-2">
 {[1, 2].map((i) => (
 <div key={i} className="p-3 rounded-lg bg-surface-base animate-pulse">
 <div className="h-3 bg-surface-overlay rounded w-3/4 mb-1" />
 <div className="h-2 bg-surface-overlay rounded w-1/2" />
 </div>
 ))}
 </div>
 ) : suggestions.length === 0 ? (
 <div className="flex flex-col items-center justify-center py-6 text-center">
 <Sparkles className="w-8 h-8 text-line-active mb-2" />
 <div className="text-sm text-content-muted font-medium">数字灵魂已成型</div>
 <div className="text-xs text-content-disabled mt-1">继续对话以精化细节</div>
 </div>
 ) : (
 <div className="space-y-2">
 {suggestions.map((s) => (
 <button
 key={s.id}
 onClick={() => handleClick(s.action)}
 className="w-full text-left p-3 rounded-xl bg-surface-base hover:bg-surface-elevated hover:shadow-sm border border-transparent hover:border-line-subtle transition group"
 >
 <div className="flex items-start gap-2.5">
 <span className="shrink-0 mt-0.5 text-content-muted">{s.icon}</span>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-1.5">
 <span className="text-sm font-medium text-content-secondary group-hover:text-accent transition">{s.title}</span>
 <span className={`w-1.5 h-1.5 rounded-full ${priorityConfig[s.priority]?.dot || 'bg-slate-300'}`} />
 </div>
 <div className="text-xs text-content-muted mt-0.5 truncate">{s.subtitle}</div>
 </div>
 <svg className="w-4 h-4 text-content-secondary group-hover:text-accent mt-1 transition shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
 </svg>
 </div>
 </button>
 ))}
 </div>
 )}
 </div>
 </div>
 );
}
