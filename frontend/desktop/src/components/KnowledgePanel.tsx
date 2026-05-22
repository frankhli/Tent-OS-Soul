import { useState, useEffect, useRef } from 'react';
import { MessageCircle, Pin, Heart, User, Calendar, Repeat, Brain, BookOpen, RefreshCw, Plus, X, Tag, Pencil, Trash2 } from 'lucide-react';
import { USER_ID } from '../api/soulApi';

interface KItem {
 id: string;
 title: string;
 summary: string;
 memory_type: string;
 created_at: string;
}

const typeConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
 conversation: { icon: <MessageCircle className="w-3.5 h-3.5" />, label: '对话记忆', color: 'bg-blue-50 text-blue-600 border-blue-100' },
 fact: { icon: <Pin className="w-3.5 h-3.5" />, label: '事实知识', color: 'bg-amber-50 text-amber-600 border-amber-100' },
 preference: { icon: <Heart className="w-3.5 h-3.5" />, label: '个人偏好', color: 'bg-rose-50 text-rose-600 border-rose-100' },
 entity: { icon: <User className="w-3.5 h-3.5" />, label: '人物实体', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
 event: { icon: <Calendar className="w-3.5 h-3.5" />, label: '事件记录', color: 'bg-purple-50 text-purple-600 border-purple-100' },
 pattern: { icon: <Repeat className="w-3.5 h-3.5" />, label: '行为模式', color: 'bg-cyan-50 text-cyan-600 border-cyan-100' },
 belief: { icon: <Brain className="w-3.5 h-3.5" />, label: '信念观点', color: 'bg-indigo-50 text-indigo-600 border-indigo-100' },
 note: { icon: <BookOpen className="w-3.5 h-3.5" />, label: '手动笔记', color: 'bg-violet-50 text-violet-600 border-accent-border' },
};

export default function KnowledgePanel() {
 const [items, setItems] = useState<KItem[]>([]);
 const [loading, setLoading] = useState(true);
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [expanded, setExpanded] = useState<string | null>(null);
 const [filterType, setFilterType] = useState<string>('all');
 const [showAddNote, setShowAddNote] = useState(false);
 const [noteTitle, setNoteTitle] = useState('');
 const [noteContent, setNoteContent] = useState('');
 const [adding, setAdding] = useState(false);
 const [editingId, setEditingId] = useState<string | null>(null);
 const [editTitle, setEditTitle] = useState('');
 const [editContent, setEditContent] = useState('');
 const [deletingId, setDeletingId] = useState<string | null>(null);

 useEffect(() => {
 loadItems();
 const iv = setInterval(loadItems, 30000);
 return () => clearInterval(iv);
 }, []);

 const loadItems = async () => {
 try {
 const res = await fetch(`/api/v1/memory/knowledge?limit=20&user_id=${USER_ID}`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 if (!mountedRef.current) return;
 setItems((data.items || []).map((it: any, idx: number) => ({
 id: it.id || String(idx),
 title: it.title || '记忆片段',
 summary: it.summary || it.abstract || '',
 memory_type: it.memory_type || 'general',
 created_at: it.created_at || '',
 })));
 } catch {
 if (mountedRef.current) setItems([]);
 } finally {
 if (mountedRef.current) setLoading(false);
 }
 };

 const addNote = async () => {
 if (!noteTitle.trim() || !noteContent.trim()) return;
 setAdding(true);
 try {
 const res = await fetch('/api/v1/memory/knowledge', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 title: noteTitle.trim(),
 summary: noteContent.trim(),
 memory_type: 'note',
 user_id: USER_ID,
 }),
 });
 if (res.ok) {
 setNoteTitle('');
 setNoteContent('');
 setShowAddNote(false);
 loadItems();
 }
 } catch {
 // ignore
 } finally {
 setAdding(false);
 }
 };

 const updateNote = async (id: string) => {
 if (!editTitle.trim()) return;
 try {
 const res = await fetch(`/api/v1/memory/knowledge/${encodeURIComponent(id)}`, {
 method: 'PUT',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 title: editTitle.trim(),
 summary: editContent.trim(),
 memory_type: 'note',
 user_id: USER_ID,
 }),
 });
 if (res.ok) {
 setEditingId(null);
 setEditTitle('');
 setEditContent('');
 loadItems();
 }
 } catch {
 // ignore
 }
 };

 const deleteNote = async (id: string) => {
 try {
 const res = await fetch(`/api/v1/memory/knowledge/${encodeURIComponent(id)}`, {
 method: 'DELETE',
 });
 if (res.ok) {
 setDeletingId(null);
 loadItems();
 }
 } catch {
 // ignore
 }
 };

 const formatTime = (s: string) => {
 if (!s) return '';
 const d = new Date(s.replace(' ', 'T'));
 const now = new Date();
 const diff = now.getTime() - d.getTime();
 if (diff < 60000) return '刚刚';
 if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
 if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
 return `${d.getMonth() + 1}/${d.getDate()}`;
 };

 // 按类型统计
 const typeCounts: Record<string, number> = {};
 items.forEach((it) => {
 typeCounts[it.memory_type] = (typeCounts[it.memory_type] || 0) + 1;
 });

 const filteredItems = filterType === 'all' ? items : items.filter((it) => it.memory_type === filterType);

 return (
 <div className="h-full flex flex-col p-3">
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider">记忆之书</h4>
 <div className="flex items-center gap-1">
 <button
 onClick={() => setShowAddNote(!showAddNote)}
 className="text-xs text-accent hover:text-accent transition p-1 rounded hover:bg-accent-subtle"
 title="添加笔记"
 >
 <Plus className="w-3.5 h-3.5" />
 </button>
 <button onClick={loadItems} className="text-xs text-content-muted hover:text-accent transition p-1 rounded hover:bg-surface-overlay">
 <RefreshCw className="w-3.5 h-3.5" />
 </button>
 </div>
 </div>

 {/* Add Note Form */}
 {showAddNote && (
 <div className="mb-3 p-2.5 rounded-lg bg-accent-subtle/50 border border-accent-border bg-accent-subtle/50 border-accent-border">
 <div className="flex items-center justify-between mb-1.5">
 <span className="text-[10px] text-accent font-medium">添加笔记</span>
 <button onClick={() => setShowAddNote(false)} className="text-content-muted hover:text-content-secondary">
 <X className="w-3 h-3" />
 </button>
 </div>
 <input
 value={noteTitle}
 onChange={(e) => setNoteTitle(e.target.value)}
 placeholder="标题..."
 className="w-full mb-1.5 px-2 py-1 text-xs rounded border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400"
 />
 <textarea
 value={noteContent}
 onChange={(e) => setNoteContent(e.target.value)}
 placeholder="内容..."
 rows={2}
 className="w-full mb-1.5 px-2 py-1 text-xs rounded border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400 resize-none"
 />
 <button
 onClick={addNote}
 disabled={adding || !noteTitle.trim() || !noteContent.trim()}
 className="w-full py-1 bg-violet-600 text-white text-xs rounded hover:bg-violet-700 transition disabled:opacity-40"
 >
 {adding ? '保存中...' : '保存笔记'}
 </button>
 </div>
 )}

 {/* Type Filter Tags */}
 {items.length > 0 && (
 <div className="flex flex-wrap gap-1 mb-2">
 <button
 onClick={() => setFilterType('all')}
 className={`text-[10px] px-2 py-0.5 rounded-full border transition ${
 filterType === 'all'
 ? 'bg-surface-overlay text-content-primary border-line-subtle'
 : 'bg-surface-overlay text-content-muted border-line-subtle hover:bg-surface-overlay'
 }`}
 >
 全部 {items.length}
 </button>
 {Object.entries(typeCounts)
 .sort((a, b) => b[1] - a[1])
 .slice(0, 5)
 .map(([type, count]) => {
 const cfg = typeConfig[type];
 return (
 <button
 key={type}
 onClick={() => setFilterType(filterType === type ? 'all' : type)}
 className={`text-[10px] px-2 py-0.5 rounded-full border transition flex items-center gap-0.5 ${
 filterType === type
 ? 'bg-surface-overlay text-content-primary border-line-subtle'
 : cfg?.color || 'bg-surface-overlay text-content-muted border-line-subtle'
 }`}
 >
 {cfg?.icon || <Tag className="w-3 h-3" />}
 {cfg?.label || type} {count}
 </button>
 );
 })}
 </div>
 )}

 {/* Items List */}
 <div className="flex-1 min-h-0 overflow-auto">
 {loading ? (
 <div className="space-y-2">
 {[1, 2].map((i) => (
 <div key={i} className="p-2 rounded-lg bg-surface-base animate-pulse h-12" />
 ))}
 </div>
 ) : filteredItems.length === 0 ? (
 <div className="flex flex-col items-center justify-center py-8 text-center">
 <BookOpen className="w-8 h-8 text-line-active mb-2" />
 <div className="text-sm text-content-muted font-medium">记忆之书还是空白的</div>
 <div className="text-xs text-content-disabled mt-1">多聊几句，我会把你说的都记下来</div>
 </div>
 ) : (
 <div className="space-y-1.5">
 {filteredItems.map((it) => {
 const cfg = typeConfig[it.memory_type];
 return (
 <div key={it.id}>
 {editingId === it.id ? (
 <div className="p-2.5 rounded-xl bg-surface-base border border-accent-border">
 <input
 value={editTitle}
 onChange={(e) => setEditTitle(e.target.value)}
 className="w-full mb-1.5 px-2 py-1 text-xs rounded border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400"
 />
 <textarea
 value={editContent}
 onChange={(e) => setEditContent(e.target.value)}
 rows={2}
 className="w-full mb-1.5 px-2 py-1 text-xs rounded border border-accent-border bg-surface-panel text-content-primary focus:outline-none focus:border-violet-400 resize-none"
 />
 <div className="flex items-center gap-2">
 <button
 onClick={() => updateNote(it.id)}
 className="text-xs px-2 py-1 rounded bg-violet-600 text-white hover:bg-violet-700 transition"
 >
 保存
 </button>
 <button
 onClick={() => { setEditingId(null); setEditTitle(''); setEditContent(''); }}
 className="text-xs px-2 py-1 rounded bg-surface-overlay text-content-muted hover:text-content-secondary transition"
 >
 取消
 </button>
 </div>
 </div>
 ) : (
 <button
 onClick={() => setExpanded(expanded === it.id ? null : it.id)}
 className="w-full text-left p-2.5 rounded-xl bg-surface-base hover:bg-surface-elevated hover:shadow-sm border border-transparent hover:border-line-subtle transition group"
 >
 <div className="flex items-start gap-2">
 <span className="text-content-muted shrink-0 mt-0.5">{cfg?.icon || <BookOpen className="w-4 h-4" />}</span>
 <div className="flex-1 min-w-0">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-1.5 min-w-0">
 <div className="text-sm font-medium text-content-secondary truncate group-hover:text-accent transition">
 {it.title}
 </div>
 {cfg && (
 <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${cfg.color}`}>
 {cfg.label}
 </span>
 )}
 </div>
 <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition shrink-0 ml-1">
 <button
 onClick={(e) => { e.stopPropagation(); setEditingId(it.id); setEditTitle(it.title); setEditContent(it.summary); }}
 className="p-1 rounded hover:bg-surface-overlay text-content-muted hover:text-accent transition"
 title="编辑"
 >
 <Pencil className="w-3 h-3" />
 </button>
 <button
 onClick={(e) => { e.stopPropagation(); setDeletingId(it.id); }}
 className="p-1 rounded hover:bg-surface-overlay text-content-muted hover:text-red-500 transition"
 title="删除"
 >
 <Trash2 className="w-3 h-3" />
 </button>
 </div>
 </div>
 <div className={`text-xs text-content-muted mt-0.5 transition-all ${expanded === it.id ? '' : 'line-clamp-2'}`}>
 {it.summary}
 </div>
 <div className="text-[10px] text-content-muted mt-1">{formatTime(it.created_at)}</div>
 </div>
 </div>
 </button>
 )}
 {deletingId === it.id && (
 <div className="mt-1 p-2 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40">
 <div className="text-xs text-red-600 dark:text-red-400 mb-1.5">确定删除这条笔记？</div>
 <div className="flex items-center gap-2">
 <button
 onClick={() => deleteNote(it.id)}
 className="text-xs px-2 py-1 rounded bg-red-500 text-white hover:bg-red-600 transition"
 >
 删除
 </button>
 <button
 onClick={() => setDeletingId(null)}
 className="text-xs px-2 py-1 rounded bg-surface-overlay text-content-muted hover:text-content-secondary transition"
 >
 取消
 </button>
 </div>
 </div>
 )}
 </div>
 );
 })}
 </div>
 )}
 </div>
 </div>
 );
}
