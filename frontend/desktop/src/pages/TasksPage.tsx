import { useState, useEffect, useRef } from 'react';
import { CheckCircle2, Circle, Plus, X, Trash2, ArrowLeft, Calendar, Flag, Filter } from 'lucide-react';
import { USER_ID } from '../api/soulApi';
import { useNavigate } from 'react-router-dom';

interface Todo {
 id: number;
 title: string;
 description: string;
 status: string;
 priority: string;
 created_at: string;
}

const priorityConfig: Record<string, { label: string; color: string; bg: string }> = {
 high: { label: '高优先级', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
 medium: { label: '中优先级', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200' },
 low: { label: '低优先级', color: 'text-slate-600', bg: 'bg-slate-50 border-slate-200' },
};

export default function TasksPage() {
 const navigate = useNavigate();
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [todos, setTodos] = useState<Todo[]>([]);
 const [loading, setLoading] = useState(true);
 const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('all');
 const [sortBy, setSortBy] = useState<'priority' | 'created'>('priority');
 const [showAdd, setShowAdd] = useState(false);
 const [newTitle, setNewTitle] = useState('');
 const [newDesc, setNewDesc] = useState('');
 const [newPriority, setNewPriority] = useState('medium');
 const [adding, setAdding] = useState(false);

 useEffect(() => {
 loadTodos();
 }, []);

 const loadTodos = async () => {
 setLoading(true);
 try {
 const res = await fetch(`/api/v1/todos?user_id=${USER_ID}&limit=100`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 setTodos(data.todos || []);
 } catch {
 setTodos([]);
 } finally {
 setLoading(false);
 }
 };

 const createTodo = async () => {
 if (!newTitle.trim()) return;
 setAdding(true);
 try {
 await fetch('/api/v1/todos', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 user_id: USER_ID,
 title: newTitle.trim(),
 description: newDesc.trim(),
 priority: newPriority,
 }),
 });
 setNewTitle('');
 setNewDesc('');
 setNewPriority('medium');
 setShowAdd(false);
 loadTodos();
 } catch {
 // ignore
 } finally {
 setAdding(false);
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

 const filtered = todos.filter((t) => {
 if (filter === 'all') return true;
 return t.status === filter;
 });

 const sorted = [...filtered].sort((a, b) => {
 if (sortBy === 'priority') {
 const pOrder = { high: 0, medium: 1, low: 2 };
 return (pOrder as any)[a.priority] - (pOrder as any)[b.priority];
 }
 return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
 });

 const pendingCount = todos.filter((t) => t.status === 'pending').length;
 const completedCount = todos.filter((t) => t.status === 'completed').length;

 return (
 <div className="h-full flex flex-col bg-surface-elevated">
 {/* Header */}
 <div className="shrink-0 px-6 py-4 border-b border-line-subtle">
 <div className="flex items-center gap-3 mb-3">
 <button onClick={() => navigate('/')} className="text-content-muted hover:text-content-primary transition">
 <ArrowLeft className="w-5 h-5" />
 </button>
 <h1 className="text-lg font-semibold text-content-primary">任务管理</h1>
 <span className="text-xs text-content-muted ml-auto">
 待办 {pendingCount} · 已完成 {completedCount}
 </span>
 </div>

 <div className="flex items-center gap-2">
 <div className="flex bg-surface-panel rounded-lg p-0.5">
 {(['all', 'pending', 'completed'] as const).map((f) => (
 <button
 key={f}
 onClick={() => setFilter(f)}
 className={`text-xs px-3 py-1.5 rounded-md transition ${
 filter === f
 ? 'bg-surface-overlay text-content-primary shadow-sm'
 : 'text-content-muted hover:text-content-secondary'
 }`}
 >
 {f === 'all' ? '全部' : f === 'pending' ? '待办' : '已完成'}
 </button>
 ))}
 </div>
 <div className="flex items-center gap-1 text-xs text-content-muted">
 <Filter className="w-3.5 h-3.5" />
 <select
 value={sortBy}
 onChange={(e) => setSortBy(e.target.value as any)}
 className="bg-transparent border-none text-xs text-content-muted focus:outline-none cursor-pointer"
 >
 <option value="priority">按优先级</option>
 <option value="created">按时间</option>
 </select>
 </div>
 <button
 onClick={() => setShowAdd(!showAdd)}
 className="ml-auto flex items-center gap-1 text-xs px-3 py-1.5 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition"
 >
 <Plus className="w-3.5 h-3.5" />
 新建任务
 </button>
 </div>
 </div>

 {/* Add Form */}
 {showAdd && (
 <div className="shrink-0 mx-6 mt-4 p-4 rounded-xl bg-accent-subtle border border-accent-border">
 <div className="flex items-center justify-between mb-2">
 <span className="text-sm font-medium text-accent">新建任务</span>
 <button onClick={() => setShowAdd(false)} className="text-content-muted hover:text-content-secondary">
 <X className="w-4 h-4" />
 </button>
 </div>
 <input
 value={newTitle}
 onChange={(e) => setNewTitle(e.target.value)}
 placeholder="任务标题..."
 className="w-full mb-2 px-3 py-2 text-sm rounded-lg border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400"
 />
 <textarea
 value={newDesc}
 onChange={(e) => setNewDesc(e.target.value)}
 placeholder="描述（可选）..."
 rows={2}
 className="w-full mb-2 px-3 py-2 text-sm rounded-lg border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400 resize-none"
 />
 <div className="flex items-center gap-2">
 <select
 value={newPriority}
 onChange={(e) => setNewPriority(e.target.value)}
 className="text-sm px-3 py-2 rounded-lg border border-accent-border bg-surface-panel focus:outline-none"
 >
 <option value="high">高优先级</option>
 <option value="medium">中优先级</option>
 <option value="low">低优先级</option>
 </select>
 <button
 onClick={createTodo}
 disabled={adding || !newTitle.trim()}
 className="px-4 py-2 bg-violet-600 text-white text-sm rounded-lg hover:bg-violet-700 transition disabled:opacity-40"
 >
 {adding ? '保存中...' : '创建'}
 </button>
 </div>
 </div>
 )}

 {/* Task List */}
 <div className="flex-1 overflow-auto px-6 py-4">
 {loading ? (
 <div className="space-y-3">
 {[1, 2, 3].map((i) => (
 <div key={i} className="p-4 rounded-xl bg-surface-panel animate-pulse h-16" />
 ))}
 </div>
 ) : sorted.length === 0 ? (
 <div className="h-full flex flex-col items-center justify-center text-content-muted">
 <CheckCircle2 className="w-12 h-12 mb-3 text-content-secondary" />
 <div className="text-sm">
 {filter === 'pending' ? '没有待办任务，享受当下吧' : filter === 'completed' ? '还没有完成的任务' : '暂无任务'}
 </div>
 <button onClick={() => setShowAdd(true)} className="mt-3 text-xs text-accent hover:text-accent">
 创建一个任务
 </button>
 </div>
 ) : (
 <div className="space-y-2">
 {sorted.map((t) => {
 const pc = priorityConfig[t.priority] || priorityConfig.medium;
 return (
 <div
 key={t.id}
 className={`group flex items-start gap-3 p-4 rounded-xl border transition hover:shadow-sm ${
 t.status === 'completed'
 ? 'bg-slate-50 dark:bg-slate-800/50 border-slate-100 dark:border-slate-700 opacity-60'
 : `bg-white dark:bg-slate-800 ${pc.bg}`
 }`}
 >
 <button
 onClick={() => toggleTodo(t.id, t.status)}
 className="shrink-0 mt-0.5 text-content-muted hover:text-accent transition"
 >
 {t.status === 'completed' ? (
 <CheckCircle2 className="w-5 h-5 text-accent" />
 ) : (
 <Circle className="w-5 h-5" />
 )}
 </button>
 <div className="flex-1 min-w-0">
 <div className={`text-sm font-medium ${t.status === 'completed' ? 'text-content-muted line-through' : 'text-content-primary'}`}>
 {t.title}
 </div>
 {t.description && (
 <div className={`text-xs mt-0.5 ${t.status === 'completed' ? 'text-content-secondary' : 'text-content-muted'}`}>
 {t.description}
 </div>
 )}
 <div className="flex items-center gap-2 mt-1.5">
 <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${pc.bg} ${pc.color}`}>
 {pc.label}
 </span>
 <span className="text-[10px] text-content-muted flex items-center gap-0.5">
 <Calendar className="w-3 h-3" />
 {new Date(t.created_at).toLocaleDateString('zh-CN')}
 </span>
 </div>
 </div>
 <button
 onClick={() => deleteTodo(t.id)}
 className="shrink-0 opacity-0 group-hover:opacity-100 text-content-secondary hover:text-red-400 transition p-1"
 >
 <Trash2 className="w-4 h-4" />
 </button>
 </div>
 );
 })}
 </div>
 )}
 </div>
 </div>
 );
}
