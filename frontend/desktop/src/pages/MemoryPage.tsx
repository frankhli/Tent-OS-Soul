import { useState, useEffect, useRef, useCallback } from 'react';
import {
 BookOpen, MessageCircle, Pin, User, Calendar, Repeat, Brain, Search, RefreshCw,
 LayoutGrid, GitCommit, Network, BarChart3, Zap, Database, Layers, Clock, Play,
} from 'lucide-react';
import { USER_ID } from '../api/soulApi';

interface KItem {
 id: string;
 title: string;
 summary: string;
 memory_type: string;
 created_at: string;
}

interface GraphNode {
 id: string;
 content: string;
 type: string;
 confidence: number;
 created_at: string;
}

interface GraphEdge {
 source: string;
 target: string;
 relation: string;
 strength: number;
}

interface MemoryStats {
 graph: { node_count: number; edge_count: number; type_distribution?: Record<string, number>; relation_distribution?: Record<string, number>; avg_confidence?: number };
 tiered: { l0_count: number; l1_count: number };
 sessions: number;
}

const typeConfig: Record<string, { icon: React.ReactNode; name: string; color: string }> = {
 conversation: { icon: <MessageCircle className="w-5 h-5" />, name: '对话记忆', color: '#8b5cf6' },
 fact: { icon: <Pin className="w-5 h-5" />, name: '事实知识', color: '#10b981' },
 preference: { icon: <BookOpen className="w-5 h-5" />, name: '个人偏好', color: '#f59e0b' },
 entity: { icon: <User className="w-5 h-5" />, name: '人物实体', color: '#3b82f6' },
 event: { icon: <Calendar className="w-5 h-5" />, name: '事件记录', color: '#ef4444' },
 pattern: { icon: <Repeat className="w-5 h-5" />, name: '行为模式', color: '#ec4899' },
 belief: { icon: <Brain className="w-5 h-5" />, name: '信念观点', color: '#06b6d4' },
};

/* ========== 知识图谱可视化组件 ========== */
function GraphVisualization({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
 const svgRef = useRef<SVGSVGElement>(null);
 const posRef = useRef<Map<string, { x: number; y: number }>>(new Map());
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [, forceUpdate] = useState(0);
 const draggingRef = useRef<string | null>(null);
 const [hoverNode, setHoverNode] = useState<string | null>(null);
 const containerRef = useRef<HTMLDivElement>(null);
 const dimsRef = useRef({ w: 800, h: 500 });
 const rafRef = useRef<number>(0);

 // 初始化节点位置（环形分布）
 useEffect(() => {
 const dims = dimsRef.current;
 const newPos = new Map<string, { x: number; y: number }>();
 const cx = dims.w / 2;
 const cy = dims.h / 2;
 const radius = Math.min(dims.w, dims.h) * 0.35;
 nodes.forEach((n, i) => {
 const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
 newPos.set(n.id, {
 x: cx + Math.cos(angle) * radius + (Math.random() - 0.5) * 40,
 y: cy + Math.sin(angle) * radius + (Math.random() - 0.5) * 40,
 });
 });
 posRef.current = newPos;
 forceUpdate((v) => v + 1);
 }, [nodes.length]);

 // 力导向模拟（直接操作 DOM，不触发 React 重渲染）
 useEffect(() => {
 if (posRef.current.size === 0) return;
 let running = true;
 const dims = dimsRef.current;
 const tick = () => {
 if (!running) return;
 const next = posRef.current;
 const cx = dims.w / 2;
 const cy = dims.h / 2;

 // 斥力
 nodes.forEach((n1) => {
 const p1 = next.get(n1.id);
 if (!p1) return;
 let fx = 0, fy = 0;
 nodes.forEach((n2) => {
 if (n1.id === n2.id) return;
 const p2 = next.get(n2.id);
 if (!p2) return;
 const dx = p1.x - p2.x;
 const dy = p1.y - p2.y;
 const dist = Math.sqrt(dx * dx + dy * dy) || 1;
 const force = 8000 / (dist * dist);
 fx += (dx / dist) * force;
 fy += (dy / dist) * force;
 });
 p1.x += fx * 0.05;
 p1.y += fy * 0.05;
 });

 // 引力
 edges.forEach((e) => {
 const p1 = next.get(e.source);
 const p2 = next.get(e.target);
 if (!p1 || !p2) return;
 const dx = p2.x - p1.x;
 const dy = p2.y - p1.y;
 const dist = Math.sqrt(dx * dx + dy * dy) || 1;
 const force = (dist - 100) * 0.003 * e.strength;
 p1.x += dx * force;
 p1.y += dy * force;
 p2.x -= dx * force;
 p2.y -= dy * force;
 });

 // 中心引力
 nodes.forEach((n) => {
 const p = next.get(n.id);
 if (!p) return;
 p.x += (cx - p.x) * 0.01;
 p.y += (cy - p.y) * 0.01;
 });

 // 直接更新 DOM 属性（每 2 帧更新一次视觉）
 if (svgRef.current) {
 nodes.forEach((n) => {
 const p = next.get(n.id);
 if (!p) return;
 const g = svgRef.current!.querySelector(`[data-node-id="${n.id}"]`) as SVGGElement | null;
 if (g) g.setAttribute('transform', `translate(${p.x}, ${p.y})`);
 });
 edges.forEach((e, i) => {
 const p1 = next.get(e.source);
 const p2 = next.get(e.target);
 if (!p1 || !p2) return;
 const line = svgRef.current!.querySelector(`[data-edge-idx="${i}"]`) as SVGLineElement | null;
 if (line) {
 line.setAttribute('x1', String(p1.x));
 line.setAttribute('y1', String(p1.y));
 line.setAttribute('x2', String(p2.x));
 line.setAttribute('y2', String(p2.y));
 }
 });
 }

 rafRef.current = requestAnimationFrame(tick);
 };
 rafRef.current = requestAnimationFrame(tick);
 return () => {
 running = false;
 cancelAnimationFrame(rafRef.current);
 };
 }, [nodes, edges]);

 // 容器尺寸监听
 useEffect(() => {
 const el = containerRef.current;
 if (!el) return;
 const ro = new ResizeObserver((entries) => {
 for (const entry of entries) {
 dimsRef.current = { w: entry.contentRect.width, h: entry.contentRect.height };
 forceUpdate((v) => v + 1);
 }
 });
 ro.observe(el);
 return () => ro.disconnect();
 }, []);

 const handleMouseDown = (id: string) => { draggingRef.current = id; };
 const handleMouseUp = () => { draggingRef.current = null; };
 const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
 if (!draggingRef.current || !svgRef.current) return;
 const rect = svgRef.current.getBoundingClientRect();
 const pos = posRef.current;
 const p = pos.get(draggingRef.current);
 if (p) {
 p.x = e.clientX - rect.left;
 p.y = e.clientY - rect.top;
 }
 }, []);

 const relatedEdges = hoverNode
 ? edges.filter((e) => e.source === hoverNode || e.target === hoverNode)
 : [];

 const dims = dimsRef.current;
 const positions = posRef.current;

 return (
 <div ref={containerRef} className="w-full h-full relative">
 <svg
 ref={svgRef}
 width={dims.w}
 height={dims.h}
 onMouseMove={handleMouseMove}
 onMouseUp={handleMouseUp}
 onMouseLeave={handleMouseUp}
 className="cursor-grab active:cursor-grabbing"
 >
 {/* 边 */}
 {edges.map((e, i) => {
 const s = positions.get(e.source);
 const t = positions.get(e.target);
 if (!s || !t) return null;
 const isHighlighted = hoverNode && (e.source === hoverNode || e.target === hoverNode);
 const isDimmed = hoverNode && !isHighlighted;
 return (
 <line
 key={i}
 data-edge-idx={i}
 x1={s.x} y1={s.y} x2={t.x} y2={t.y}
 stroke={isHighlighted ? '#8b5cf6' : '#cbd5e1'}
 strokeWidth={isHighlighted ? 2.5 : 1}
 opacity={isDimmed ? 0.15 : isHighlighted ? 1 : 0.5}
 />
 );
 })}
 {/* 节点 */}
 {nodes.map((n) => {
 const p = positions.get(n.id);
 if (!p) return null;
 const isHovered = hoverNode === n.id;
 const isRelated = hoverNode ? relatedEdges.some((e) => e.source === n.id || e.target === n.id) : true;
 const color = typeConfig[n.type]?.color || '#94a3b8';
 return (
 <g
 key={n.id}
 data-node-id={n.id}
 transform={`translate(${p.x}, ${p.y})`}
 onMouseEnter={() => setHoverNode(n.id)}
 onMouseLeave={() => setHoverNode(null)}
 onMouseDown={() => handleMouseDown(n.id)}
 style={{ cursor: 'pointer', opacity: isRelated ? 1 : 0.2 }}
 >
 <circle
 r={isHovered ? 22 : 16}
 fill={color}
 opacity={isHovered ? 0.9 : 0.7}
 stroke="white"
 strokeWidth={isHovered ? 3 : 2}
 />
 <text
 textAnchor="middle"
 dy={isHovered ? -28 : -22}
 className="text-[10px] select-none"
 fill="currentColor"
 style={{ fontSize: 10, fontWeight: isHovered ? 600 : 400 }}
 >
 {n.content.slice(0, 8)}
 </text>
 </g>
 );
 })}
 </svg>
 {/* 图例 */}
 <div className="absolute bottom-3 left-3 bg-surface-panel/90 backdrop-blur rounded-lg border border-line-subtle px-3 py-2 text-[10px] space-y-1">
 <div className="text-content-muted font-medium mb-1">图谱节点类型</div>
 {Object.entries(typeConfig).slice(0, 5).map(([key, cfg]) => (
 <div key={key} className="flex items-center gap-1.5">
 <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: cfg.color }} />
 <span className="text-content-secondary">{cfg.name}</span>
 </div>
 ))}
 </div>
 {/* 悬浮提示 */}
 {hoverNode && (() => {
 const n = nodes.find((x) => x.id === hoverNode);
 if (!n) return null;
 return (
 <div className="absolute top-3 right-3 bg-surface-panel/95 backdrop-blur rounded-lg border border-line-subtle px-3 py-2 max-w-[200px]">
 <div className="text-xs font-medium text-content-primary">{n.content}</div>
 <div className="text-[10px] text-content-muted mt-0.5">
 类型: {typeConfig[n.type]?.name || n.type} · 置信度: {(n.confidence * 100).toFixed(0)}%
 </div>
 {relatedEdges.length > 0 && (
 <div className="text-[10px] text-accent mt-1">
 {relatedEdges.length} 条关联
 </div>
 )}
 </div>
 );
 })()}
 </div>
 );
}

/* ========== 主页面 ========== */
export default function MemoryPage() {
 const [items, setItems] = useState<KItem[]>([]);
 const [loading, setLoading] = useState(true);
 const [search, setSearch] = useState('');
 const [expanded, setExpanded] = useState<string | null>(null);
 const [filterType, setFilterType] = useState<string>('all');
 const [viewMode, setViewMode] = useState<'grid' | 'timeline' | 'graph' | 'stats'>('grid');

 // 知识图谱数据
 const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
 const [graphLoading, setGraphLoading] = useState(false);

 // 统计数据
 const [stats, setStats] = useState<MemoryStats | null>(null);
 const [statsLoading, setStatsLoading] = useState(false);

 // 摘要数据
 const [summaries, setSummaries] = useState<any[]>([]);
 const [summaryLoading, setSummaryLoading] = useState(false);

 // 压缩中状态
 const [compressing, setCompressing] = useState(false);

 useEffect(() => {
 loadItems();
 const iv = setInterval(loadItems, 30000);
 return () => clearInterval(iv);
 }, []);

 // 当切换到 graph/stats 视图时加载对应数据
 useEffect(() => {
 if (viewMode === 'graph') loadGraph();
 if (viewMode === 'stats') loadStats();
 if (viewMode === 'stats') loadSummaries();
 }, [viewMode]);

 const loadItems = async () => {
 try {
 const res = await fetch(`/api/v1/memory/knowledge?limit=50&user_id=${USER_ID}`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 setItems((data.items || []).map((it: any, idx: number) => ({
 id: it.id || String(idx),
 title: it.title || '记忆片段',
 summary: it.summary || it.abstract || '',
 memory_type: it.memory_type || 'general',
 created_at: it.created_at || '',
 })));
 } catch {
 setItems([]);
 } finally {
 setLoading(false);
 }
 };

 const loadGraph = async () => {
 setGraphLoading(true);
 try {
 const res = await fetch(`/api/v1/memory/graph?user_id=${USER_ID}&limit=200`);
 if (res.ok) {
 const data = await res.json();
 setGraphData({ nodes: data.nodes || [], edges: data.edges || [] });
 }
 } catch {}
 setGraphLoading(false);
 };

 const loadStats = async () => {
 setStatsLoading(true);
 try {
 const res = await fetch(`/api/v1/memory/stats?user_id=${USER_ID}`);
 if (res.ok) {
 const data = await res.json();
 setStats(data);
 }
 } catch {}
 setStatsLoading(false);
 };

 const loadSummaries = async () => {
 setSummaryLoading(true);
 try {
 const res = await fetch(`/api/v1/memory/summary?user_id=${USER_ID}&limit=20`);
 if (res.ok) {
 const data = await res.json();
 setSummaries(data.summaries || []);
 }
 } catch {}
 setSummaryLoading(false);
 };

 const triggerCompress = async () => {
 setCompressing(true);
 try {
 const res = await fetch(`/api/v1/memory/compress?user_id=${USER_ID}`, { method: 'POST' });
 if (res.ok) {
 await loadStats();
 await loadSummaries();
 }
 } catch {}
 setCompressing(false);
 };

 const formatTime = (s: string) => {
 if (!s) return '';
 const d = new Date(s.replace(' ', 'T'));
 const now = new Date();
 const diff = now.getTime() - d.getTime();
 if (diff < 60000) return '刚刚';
 if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
 if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
 return `${d.getMonth() + 1}月${d.getDate()}日`;
 };

 const filtered = items.filter((it) => {
 const matchSearch =
 !search ||
 it.title.toLowerCase().includes(search.toLowerCase()) ||
 it.summary.toLowerCase().includes(search.toLowerCase());
 const matchType = filterType === 'all' || it.memory_type === filterType;
 return matchSearch && matchType;
 });

 const types = ['all', ...Array.from(new Set(items.map((i) => i.memory_type)))];

 return (
 <div className="h-full flex flex-col bg-surface-elevated">
 {/* Header */}
 <div className="h-14 bg-surface-panel border-b border-line-subtle flex items-center justify-between px-6 shrink-0">
 <h1 className="font-bold text-content-primary flex items-center gap-2">
 <BookOpen className="w-5 h-5" /> 记忆之书
 </h1>
 <div className="flex items-center gap-3">
 <span className="text-xs text-content-muted">
 {viewMode === 'graph'
 ? `${graphData.nodes.length} 节点 · ${graphData.edges.length} 关系`
 : viewMode === 'stats'
 ? stats
 ? `${stats.tiered.l0_count} L0 · ${stats.tiered.l1_count} L1`
 : ''
 : `${items.length} 条记忆`}
 </span>
 <div className="flex rounded-lg bg-surface-overlay p-0.5">
 {([
 { key: 'grid', icon: <LayoutGrid className="w-3.5 h-3.5" />, title: '网格' },
 { key: 'timeline', icon: <GitCommit className="w-3.5 h-3.5" />, title: '时间线' },
 { key: 'graph', icon: <Network className="w-3.5 h-3.5" />, title: '知识图谱' },
 { key: 'stats', icon: <BarChart3 className="w-3.5 h-3.5" />, title: '统计' },
 ] as const).map((v) => (
 <button
 key={v.key}
 onClick={() => setViewMode(v.key)}
 className={`text-xs px-2 py-1 rounded-md transition ${viewMode === v.key ? 'bg-surface-elevated bg-slate-600 text-content-primary shadow-sm' : 'text-content-muted hover:text-content-secondary'}`}
 title={v.title}
 >
 {v.icon}
 </button>
 ))}
 </div>
 <button
 onClick={() => {
 loadItems();
 if (viewMode === 'graph') loadGraph();
 if (viewMode === 'stats') { loadStats(); loadSummaries(); }
 }}
 className="text-xs px-3 py-1.5 rounded-lg bg-surface-overlay hover:bg-surface-overlay text-content-secondary transition flex items-center gap-1"
 >
 <RefreshCw className="w-3 h-3" /> 刷新
 </button>
 </div>
 </div>

 {/* Search & Filter — 只在 grid/timeline 显示 */}
 {viewMode === 'grid' || viewMode === 'timeline' ? (
 <div className="px-6 py-3 bg-surface-panel border-b border-line-subtle flex items-center gap-3">
 <div className="flex-1 max-w-md relative">
 <input
 type="text"
 value={search}
 onChange={(e) => setSearch(e.target.value)}
 placeholder="搜索记忆..."
 className="w-full pl-9 pr-4 py-2 rounded-lg border border-line-active text-sm focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400 bg-surface-overlay text-content-primary placeholder-content-muted"
 />
 <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
 </div>
 <div className="flex gap-1.5 flex-wrap">
 {types.map((t) => (
 <button
 key={t}
 onClick={() => setFilterType(t)}
 className={`text-xs px-2.5 py-1.5 rounded-lg transition ${
 filterType === t
 ? 'bg-accent-subtle text-accent border border-accent-border'
 : 'bg-surface-overlay text-content-muted border border-line-active hover:bg-surface-overlay'
 }`}
 >
 {t === 'all' ? '全部' : (
 <span className="flex items-center gap-1">
 {typeConfig[t]?.icon}
 {typeConfig[t]?.name || t}
 </span>
 )}
 </button>
 ))}
 </div>
 </div>
 ) : null}

 {/* Content */}
 <div className="flex-1 overflow-hidden">
 {/* === Grid View === */}
 {viewMode === 'grid' && (
 <div className="h-full overflow-y-auto p-6">
 {loading ? (
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
 {[1, 2, 3, 4, 5, 6].map((i) => (
 <div key={i} className="p-4 rounded-xl bg-surface-panel border border-line-subtle animate-pulse h-32" />
 ))}
 </div>
 ) : filtered.length === 0 ? (
 <div className="flex flex-col items-center justify-center py-20 text-center">
 <div className="w-16 h-16 rounded-2xl bg-surface-panel flex items-center justify-center mb-4">
 <BookOpen className="w-8 h-8 text-content-muted" />
 </div>
 <h3 className="text-lg font-medium text-content-secondary mb-1">
 {search ? '未找到匹配的记忆' : '记忆之书还是空白的'}
 </h3>
 <p className="text-sm text-content-muted max-w-sm">
 {search
 ? '尝试其他关键词，或清除搜索条件'
 : '多聊几句，我会把你说的都记下来。每一条对话、每一个偏好、每一段关系，都会成为记忆之书的一页。'}
 </p>
 </div>
 ) : (
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-6xl">
 {filtered.map((it) => (
 <button
 key={it.id}
 onClick={() => setExpanded(expanded === it.id ? null : it.id)}
 className="text-left p-4 rounded-xl bg-surface-panel border border-line-subtle hover:border-accent-border hover:border-violet-800 hover:shadow-sm transition group"
 >
 <div className="flex items-start gap-3">
 <span className="text-content-muted shrink-0 mt-0.5">{typeConfig[it.memory_type]?.icon || <BookOpen className="w-5 h-5" />}</span>
 <div className="flex-1 min-w-0">
 <div className="flex items-center justify-between gap-2">
 <h3 className="text-sm font-semibold text-content-primary truncate group-hover:text-accent transition">
 {it.title}
 </h3>
 <span className="text-[10px] text-content-muted shrink-0">{formatTime(it.created_at)}</span>
 </div>
 <div className={`text-xs text-content-muted mt-1.5 leading-relaxed ${expanded === it.id ? '' : 'line-clamp-3'}`}>
 {it.summary}
 </div>
 {expanded === it.id && (
 <div className="mt-2 text-[10px] text-content-muted">
 类型: {typeConfig[it.memory_type]?.name || it.memory_type}
 </div>
 )}
 </div>
 </div>
 </button>
 ))}
 </div>
 )}
 </div>
 )}

 {/* === Timeline View === */}
 {viewMode === 'timeline' && (
 <div className="h-full overflow-y-auto p-6">
 {loading ? (
 <div className="max-w-3xl mx-auto space-y-4">
 {[1, 2, 3].map((i) => (
 <div key={i} className="animate-pulse h-20 bg-surface-panel rounded-xl" />
 ))}
 </div>
 ) : filtered.length === 0 ? (
 <div className="flex flex-col items-center justify-center py-20 text-center">
 <BookOpen className="w-8 h-8 text-content-muted mb-3" />
 <p className="text-content-muted">暂无记忆记录</p>
 </div>
 ) : (
 <div className="max-w-3xl mx-auto">
 {(() => {
 const groups: Record<string, KItem[]> = {};
 filtered.forEach((it) => {
 const d = new Date(it.created_at.replace(' ', 'T'));
 const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
 if (!groups[key]) groups[key] = [];
 groups[key].push(it);
 });
 const sortedKeys = Object.keys(groups).sort((a, b) => b.localeCompare(a));
 return sortedKeys.map((dateKey) => (
 <div key={dateKey} className="relative pl-8 pb-8 last:pb-0">
 <div className="absolute left-3 top-0 bottom-0 w-px bg-surface-overlay" />
 <div className="absolute left-0 top-0 w-6 h-6 rounded-full bg-accent-subtle border-2 border-accent-border flex items-center justify-center">
 <Calendar className="w-3 h-3 text-accent" />
 </div>
 <div className="mb-3">
 <span className="text-xs font-semibold text-content-secondary">{dateKey}</span>
 <span className="text-[10px] text-content-muted ml-2">{groups[dateKey].length} 条</span>
 </div>
 <div className="space-y-2">
 {groups[dateKey].map((it) => (
 <button
 key={it.id}
 onClick={() => setExpanded(expanded === it.id ? null : it.id)}
 className="w-full text-left p-3 rounded-xl bg-surface-panel border border-line-subtle hover:border-accent-border hover:border-violet-800 hover:shadow-sm transition group"
 >
 <div className="flex items-start gap-2">
 <span className="text-content-muted shrink-0 mt-0.5">{typeConfig[it.memory_type]?.icon || <BookOpen className="w-4 h-4" />}</span>
 <div className="flex-1 min-w-0">
 <h3 className="text-sm font-medium text-content-primary group-hover:text-accent transition">{it.title}</h3>
 <div className={`text-xs text-content-muted mt-1 leading-relaxed ${expanded === it.id ? '' : 'line-clamp-2'}`}>{it.summary}</div>
 {expanded === it.id && (
 <div className="mt-1.5 text-[10px] text-content-muted">
 类型: {typeConfig[it.memory_type]?.name || it.memory_type} · {formatTime(it.created_at)}
 </div>
 )}
 </div>
 </div>
 </button>
 ))}
 </div>
 </div>
 ));
 })()}
 </div>
 )}
 </div>
 )}

 {/* === Graph View === */}
 {viewMode === 'graph' && (
 <div className="h-full flex">
 <div className="flex-1 bg-surface-elevated relative">
 {graphLoading ? (
 <div className="absolute inset-0 flex items-center justify-center">
 <div className="flex flex-col items-center gap-2">
 <div className="w-8 h-8 border-2 border-accent-border border-t-violet-600 rounded-full animate-spin" />
 <span className="text-xs text-content-muted">加载图谱...</span>
 </div>
 </div>
 ) : graphData.nodes.length === 0 ? (
 <div className="absolute inset-0 flex flex-col items-center justify-center">
 <Network className="w-12 h-12 text-content-secondary mb-3" />
 <p className="text-sm text-content-muted">知识图谱为空</p>
 <p className="text-xs text-content-muted mt-1">多聊几句，系统会自动提取实体和关系</p>
 </div>
 ) : (
 <GraphVisualization nodes={graphData.nodes} edges={graphData.edges} />
 )}
 </div>
 {/* 右侧信息面板 */}
 <div className="w-64 shrink-0 bg-surface-panel border-l border-line-subtle p-4 overflow-y-auto">
 <h3 className="text-sm font-semibold text-content-primary mb-3">图谱统计</h3>
 <div className="space-y-2">
 <div className="flex justify-between text-xs">
 <span className="text-content-muted">节点总数</span>
 <span className="font-medium text-content-primary">{graphData.nodes.length}</span>
 </div>
 <div className="flex justify-between text-xs">
 <span className="text-content-muted">关系总数</span>
 <span className="font-medium text-content-primary">{graphData.edges.length}</span>
 </div>
 </div>
 <div className="mt-4 text-[10px] text-content-muted leading-relaxed">
 每个节点代表从对话中提取的实体（人物、概念、事件等），边代表它们之间的关系。拖拽节点可以调整布局。
 </div>
 </div>
 </div>
 )}

 {/* === Stats View === */}
 {viewMode === 'stats' && (
 <div className="h-full overflow-y-auto p-6">
 {statsLoading ? (
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
 {[1, 2, 3, 4].map((i) => (
 <div key={i} className="h-28 rounded-xl bg-surface-panel border border-line-subtle animate-pulse" />
 ))}
 </div>
 ) : !stats ? (
 <div className="flex flex-col items-center justify-center py-20">
 <BarChart3 className="w-10 h-10 text-content-secondary mb-3" />
 <p className="text-content-muted">暂无统计数据</p>
 </div>
 ) : (
 <div className="max-w-5xl mx-auto space-y-6">
 {/* 统计卡片 */}
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
 <div className="p-4 rounded-xl bg-surface-panel border border-line-subtle">
 <div className="flex items-center gap-2 mb-2">
 <Database className="w-4 h-4 text-accent" />
 <span className="text-xs text-content-muted">L0 记忆</span>
 </div>
 <div className="text-2xl font-bold text-content-primary">{stats.tiered.l0_count}</div>
 <div className="text-[10px] text-content-muted mt-1">原始摘要层</div>
 </div>
 <div className="p-4 rounded-xl bg-surface-panel border border-line-subtle">
 <div className="flex items-center gap-2 mb-2">
 <Layers className="w-4 h-4 text-emerald-500" />
 <span className="text-xs text-content-muted">L1 摘要</span>
 </div>
 <div className="text-2xl font-bold text-content-primary">{stats.tiered.l1_count}</div>
 <div className="text-[10px] text-content-muted mt-1">LLM结构化压缩</div>
 </div>
 <div className="p-4 rounded-xl bg-surface-panel border border-line-subtle">
 <div className="flex items-center gap-2 mb-2">
 <Network className="w-4 h-4 text-blue-500" />
 <span className="text-xs text-content-muted">知识图谱</span>
 </div>
 <div className="text-2xl font-bold text-content-primary">{stats.graph.node_count}</div>
 <div className="text-[10px] text-content-muted mt-1">{stats.graph.edge_count} 条关系</div>
 </div>
 <div className="p-4 rounded-xl bg-surface-panel border border-line-subtle">
 <div className="flex items-center gap-2 mb-2">
 <Clock className="w-4 h-4 text-amber-500" />
 <span className="text-xs text-content-muted">会话数</span>
 </div>
 <div className="text-2xl font-bold text-content-primary">{stats.sessions}</div>
 <div className="text-[10px] text-content-muted mt-1">总对话会话</div>
 </div>
 </div>

 {/* 手动压缩 */}
 <div className="p-4 rounded-xl bg-surface-panel border border-line-subtle flex items-center justify-between">
 <div>
 <div className="text-sm font-medium text-content-primary">记忆压缩</div>
 <div className="text-xs text-content-muted mt-0.5">将 L0 层原始记忆压缩为 L1 层结构化摘要（每30分钟自动运行）</div>
 </div>
 <button
 onClick={triggerCompress}
 disabled={compressing}
 className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition"
 >
 <Zap className="w-3.5 h-3.5" />
 {compressing ? '压缩中...' : '立即压缩'}
 </button>
 </div>

 {/* L1 摘要列表 */}
 <div>
 <h3 className="text-sm font-semibold text-content-primary mb-3">近期结构化摘要 (L1)</h3>
 {summaryLoading ? (
 <div className="space-y-2">
 {[1, 2, 3].map((i) => (
 <div key={i} className="h-16 rounded-lg bg-surface-panel animate-pulse" />
 ))}
 </div>
 ) : summaries.length === 0 ? (
 <div className="p-6 text-center rounded-xl bg-surface-panel border border-line-subtle">
 <p className="text-sm text-content-muted">暂无 L1 摘要</p>
 <p className="text-xs text-content-muted mt-1">点击"立即压缩"生成第一批结构化摘要</p>
 </div>
 ) : (
 <div className="space-y-2">
 {summaries.map((s, i) => (
 <div key={i} className="p-3 rounded-lg bg-surface-panel border border-line-subtle">
 <div className="text-xs text-content-secondary leading-relaxed whitespace-pre-line">{s.overview}</div>
 <div className="text-[10px] text-content-muted mt-1.5 flex items-center gap-2">
 <span>{s.tokens} tokens</span>
 <span>·</span>
 <span>{formatTime(s.updated_at)}</span>
 </div>
 </div>
 ))}
 </div>
 )}
 </div>
 </div>
 )}
 </div>
 )}
 </div>
 </div>
 );
}
