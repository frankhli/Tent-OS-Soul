import { useState, useEffect, useRef, useCallback } from 'react';
import { Users, User, X } from 'lucide-react';
import { USER_ID } from '../api/soulApi';

interface GraphNode {
 id: string;
 name: string;
 type: string;
 confidence: number;
 x?: number;
 y?: number;
}

interface GraphEdge {
 source: string;
 target: string;
 relation_type: string;
 strength: number;
 evidence?: string;
}

const RELATION_COLORS: Record<string, string> = {
 family: '#ef4444', // red
 friend: '#22c55e', // green
 colleague: '#3b82f6', // blue
 partner: '#d946ef', // fuchsia
 acquaintance: '#f59e0b', // amber
 related: '#94a3b8', // slate
};

const RELATION_LABELS: Record<string, string> = {
 family: '家人',
 friend: '朋友',
 colleague: '同事',
 partner: '伴侣',
 acquaintance: '熟人',
 related: '关联',
};

export default function RelationGalaxy() {
 const [nodes, setNodes] = useState<GraphNode[]>([]);
 const [edges, setEdges] = useState<GraphEdge[]>([]);
 const [loading, setLoading] = useState(true);
 const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
 const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);
 const containerRef = useRef<HTMLDivElement>(null);
 const [size, setSize] = useState({ width: 400, height: 400 });
 const isDark = typeof window !== 'undefined' && document.documentElement.classList.contains('dark');

 useEffect(() => {
 loadRelations();
 const iv = setInterval(loadRelations, 30000);
 return () => clearInterval(iv);
 }, []);

 useEffect(() => {
 const handleResize = () => {
 if (containerRef.current) {
 setSize({
 width: containerRef.current.clientWidth,
 height: containerRef.current.clientHeight,
 });
 }
 };
 handleResize();
 window.addEventListener('resize', handleResize);
 return () => window.removeEventListener('resize', handleResize);
 }, []);

 const loadRelations = async () => {
 setLoading(true);
 try {
 const res = await fetch(`/api/v1/soul/relations/${USER_ID}`);
 if (!res.ok) throw new Error();
 const data = await res.json();
 setNodes(layoutNodes(data.nodes || [], size.width, size.height));
 setEdges(data.edges || []);
 } catch {
 setNodes([]);
 setEdges([]);
 } finally {
 setLoading(false);
 }
 };

 // 简单的力导向布局（固定中心 + 环绕分布）
 const layoutNodes = useCallback((rawNodes: GraphNode[], w: number, h: number): GraphNode[] => {
 const centerX = w / 2;
 const centerY = h / 2;
 const radius = Math.min(w, h) * 0.35;

 // 找到用户节点
 const userNode = rawNodes.find((n) => n.id === 'entity://user/self');
 const others = rawNodes.filter((n) => n.id !== 'entity://user/self');

 const positioned: GraphNode[] = [];

 if (userNode) {
 positioned.push({ ...userNode, x: centerX, y: centerY });
 }

 // 其他节点围绕中心均匀分布
 others.forEach((node, i) => {
 const angle = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
 // 根据置信度调整距离（置信度越高越近）
 const dist = radius * (0.6 + 0.4 * (1 - node.confidence));
 positioned.push({
 ...node,
 x: centerX + Math.cos(angle) * dist,
 y: centerY + Math.sin(angle) * dist,
 });
 });

 return positioned;
 }, []);

 // 当 size 变化时重新布局
 useEffect(() => {
 if (nodes.length > 0) {
 setNodes((prev) => layoutNodes(prev.map((n) => ({ ...n, x: undefined, y: undefined })), size.width, size.height));
 }
 }, [size.width, size.height]);

 const getConnectedEdges = (nodeId: string) => edges.filter((e) => e.source === nodeId || e.target === nodeId);

 const getNodeById = (id: string) => nodes.find((n) => n.id === id);

 const nodeRadius = (n: GraphNode) => n.id === 'entity://user/self' ? 28 : 18 + n.confidence * 8;

 if (loading && nodes.length === 0) {
 return (
 <div className="flex items-center justify-center h-64">
 <div className="text-content-muted text-sm animate-pulse">绘制关系星系中...</div>
 </div>
 );
 }

 if (nodes.length === 0) {
 return (
 <div className="flex flex-col items-center justify-center h-64 text-center">
 <Users className="w-8 h-8 text-content-muted mb-2" />
 <div className="text-sm text-content-muted">关系星系还是空的</div>
 <div className="text-xs text-content-secondary mt-1">在对话中提及"我儿子张三"、"我同事李四"，<br />系统会自动识别并绘制关系网络</div>
 </div>
 );
 }

 return (
 <div className="relative w-full h-full" ref={containerRef}>
 <svg width={size.width} height={size.height} className="absolute inset-0">
 {/* 边 */}
 {edges.map((edge, i) => {
 const src = getNodeById(edge.source);
 const tgt = getNodeById(edge.target);
 if (!src || !tgt || src.x === undefined || src.y === undefined || tgt.x === undefined || tgt.y === undefined) return null;
 const color = RELATION_COLORS[edge.relation_type] || RELATION_COLORS.related;
 const isHovered = hoveredEdge === edge;
 const isSelected = selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
 return (
 <g key={i}>
 <line
 x1={src.x} y1={src.y}
 x2={tgt.x} y2={tgt.y}
 stroke={color}
 strokeWidth={isHovered || isSelected ? 3 : 1 + edge.strength * 2}
 strokeOpacity={isHovered || isSelected ? 0.9 : 0.4}
 className="transition-all"
 onMouseEnter={() => setHoveredEdge(edge)}
 onMouseLeave={() => setHoveredEdge(null)}
 />
 {/* 关系标签（只在悬停或选中时显示） */}
 {(isHovered || isSelected) && (
 <text
 x={(src.x + tgt.x) / 2}
 y={(src.y + tgt.y) / 2 - 6}
 textAnchor="middle"
 className="text-[10px]"
 fill={color}
 style={{ fontSize: 10, pointerEvents: 'none' }}
 >
 {RELATION_LABELS[edge.relation_type] || edge.relation_type}
 </text>
 )}
 </g>
 );
 })}

 {/* 节点 */}
 {nodes.map((node) => {
 if (node.x === undefined || node.y === undefined) return null;
 const r = nodeRadius(node);
 const isUser = node.id === 'entity://user/self';
 const isSelected = selectedNode?.id === node.id;
 const connected = selectedNode ? getConnectedEdges(node.id).length > 0 : true;
 const opacity = selectedNode && !isSelected && !connected ? 0.3 : 1;

 return (
 <g
 key={node.id}
 transform={`translate(${node.x}, ${node.y})`}
 style={{ cursor: 'pointer', opacity, transition: 'opacity 0.3s' }}
 onClick={() => setSelectedNode(isSelected ? null : node)}
 >
 {/* 光晕（用户节点） */}
 {isUser && (
 <circle r={r + 8} fill="none" stroke="#8b5cf6" strokeWidth={1} strokeOpacity={0.3}>
 <animate attributeName="r" values={`${r+6};${r+12};${r+6}`} dur="3s" repeatCount="indefinite" />
 <animate attributeName="stroke-opacity" values="0.3;0.1;0.3" dur="3s" repeatCount="indefinite" />
 </circle>
 )}
 {/* 主圆 */}
 <circle
 r={r}
 fill={isUser ? '#8b5cf6' : (isDark ? '#1e293b' : '#e2e8f0')}
 stroke={isSelected ? '#d946ef' : isUser ? '#a78bfa' : (isDark ? '#475569' : '#94a3b8')}
 strokeWidth={isSelected ? 3 : 2}
 />
 {/* 文字 */}
 <text
 textAnchor="middle"
 dominantBaseline="middle"
 fill={isUser ? '#fff' : (isDark ? '#cbd5e1' : '#334155')}
 style={{ fontSize: isUser ? 12 : 10, fontWeight: isUser ? 600 : 400, pointerEvents: 'none' }}
 >
 {node.name.length > 3 ? node.name.slice(0, 2) + '…' : node.name}
 </text>
 {/* 置信度指示器 */}
 {!isUser && (
 <circle
 r={3}
 cx={r - 4}
 cy={-r + 4}
 fill={node.confidence > 0.7 ? '#22c55e' : node.confidence > 0.4 ? '#f59e0b' : '#ef4444'}
 />
 )}
 </g>
 );
 })}
 </svg>

 {/* 选中节点的详情面板 */}
 {selectedNode && (
 <div className="absolute bottom-3 left-3 right-3 p-3 rounded-xl bg-surface-panel/90 border border-line-subtle backdrop-blur-sm shadow-lg">
 <div className="flex items-center justify-between mb-2">
 <div className="flex items-center gap-2">
 {selectedNode.id === 'entity://user/self' ? <User className="w-5 h-5 text-accent" /> : <Users className="w-5 h-5 text-content-muted" />}
 <span className="text-content-primary font-medium text-sm">{selectedNode.name}</span>
 </div>
 <button onClick={() => setSelectedNode(null)} className="text-content-muted hover:text-content-primary transition"><X className="w-4 h-4" /></button>
 </div>
 <div className="space-y-1">
 {getConnectedEdges(selectedNode.id).map((edge, i) => {
 const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
 const other = getNodeById(otherId);
 const color = RELATION_COLORS[edge.relation_type] || RELATION_COLORS.related;
 return (
 <div key={i} className="flex items-center gap-2 text-xs">
 <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
 <span className="text-content-secondary">
 {edge.source === selectedNode.id ? '→' : '←'}
 {' '}{RELATION_LABELS[edge.relation_type] || edge.relation_type}
 {' '}→ {other?.name || '未知'}
 </span>
 <span className="text-content-muted ml-auto">{Math.round(edge.strength * 100)}%</span>
 </div>
 );
 })}
 </div>
 </div>
 )}

 {/* 图例 */}
 <div className="absolute top-2 right-2 p-2 rounded-lg bg-surface-panel/80 border border-line-subtle/50 text-[10px] shadow-sm">
 {Object.entries(RELATION_LABELS).map(([type, label]) => (
 <div key={type} className="flex items-center gap-1.5 mb-0.5">
 <span className="w-2 h-2 rounded-full" style={{ backgroundColor: RELATION_COLORS[type] }} />
 <span className="text-content-muted">{label}</span>
 </div>
 ))}
 </div>
 </div>
 );
}
