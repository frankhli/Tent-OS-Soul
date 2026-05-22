/**
 * RelationGraph — 力导向关系网络可视化
 *
 * 显示 AI 居民之间的关系网络：
 * - 节点 = AI 居民（颜色按 persona）
 * - 边 = 关系（粗细按亲密度）
 * - 力模拟：斥力 + 弹簧力 + 中心引力
 * - 交互：拖拽节点、悬停高亮
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import type { AIResident, AIRelation } from '@/world/communityApi';
import { buildQuadTree, quadTreeRepulsion } from '@/utils/quadtree';

interface Props {
  residents: AIResident[];
  relations: AIRelation[];
  width?: number;
  height?: number;
}

interface GraphNode {
  id: string;
  name: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  persona: string;
}

interface GraphEdge {
  from: string;
  to: string;
  intimacy: number;
}

const PERSONA_COLORS: Record<string, string> = {
  work: '#3B82F6',
  creative: '#A855F7',
  social: '#EC4899',
  rest: '#10B981',
};

export function RelationGraph({ residents, relations }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);
  const rafRef = useRef(0);
  const mouseRef = useRef({ x: 0, y: 0, isDown: false, draggedNode: null as GraphNode | null });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [isSimulating, setIsSimulating] = useState(true);
  const [size, setSize] = useState({ width: 600, height: 400 });

  // 自适应容器尺寸
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setSize({ width: Math.floor(width), height: Math.floor(height) });
      }
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // 初始化节点和边
  useEffect(() => {
    const { width, height } = size;
    const nodes: GraphNode[] = residents.map((r, i) => ({
      id: r.id,
      name: r.name,
      x: width / 2 + Math.cos((i / residents.length) * Math.PI * 2) * Math.min(120, width / 4),
      y: height / 2 + Math.sin((i / residents.length) * Math.PI * 2) * Math.min(120, height / 4),
      vx: 0,
      vy: 0,
      radius: Math.min(22, width / 20),
      color: PERSONA_COLORS[r.persona] || '#64748B',
      persona: r.persona,
    }));

    const edges: GraphEdge[] = relations
      .filter(rel => rel.intimacy > 0)
      .map(rel => ({
        from: rel.from_ai_id,
        to: rel.to_ai_id,
        intimacy: rel.intimacy,
      }));

    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [residents, relations, size.width, size.height]);

  // 力模拟循环
  const simulate = useCallback(() => {
    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    if (nodes.length === 0) return;

    const centerX = size.width / 2;
    const centerY = size.height / 2;

    // 1. 斥力（所有节点互相排斥）
    // 节点数 <= 15 时精确计算，> 15 时用 QuadTree 近似（Barnes-Hut）
    if (nodes.length <= 15) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 8000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }
    } else {
      const tree = buildQuadTree(nodes, size.width, size.height);
      for (const node of nodes) {
        const { fx, fy } = quadTreeRepulsion(tree, { x: node.x, y: node.y }, 0.8, 8000);
        node.vx += fx;
        node.vy += fy;
      }
    }

    // 2. 弹簧力（有关系的节点互相吸引）
    for (const edge of edges) {
      const a = nodes.find(n => n.id === edge.from);
      const b = nodes.find(n => n.id === edge.to);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetDist = 120 - (edge.intimacy / 100) * 60; // 亲密度越高，距离越近
      const force = (dist - targetDist) * 0.003;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }

    // 3. 中心引力
    for (const node of nodes) {
      const dx = centerX - node.x;
      const dy = centerY - node.y;
      node.vx += dx * 0.0005;
      node.vy += dy * 0.0005;
    }

    // 4. 阻尼 + 更新位置
    for (const node of nodes) {
      if (mouseRef.current.draggedNode?.id === node.id) continue;
      node.vx *= 0.92;
      node.vy *= 0.92;
      node.x += node.vx;
      node.y += node.vy;
      // 边界约束
      node.x = Math.max(node.radius, Math.min(size.width - node.radius, node.x));
      node.y = Math.max(node.radius, Math.min(size.height - node.radius, node.y));
    }
  }, [size.width, size.height]);

  // 渲染循环
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let isVisible = false;
    const io = new IntersectionObserver(([entry]) => {
      const wasVisible = isVisible;
      isVisible = entry.isIntersecting;
      if (isVisible && !wasVisible && !rafRef.current) {
        rafRef.current = requestAnimationFrame(draw);
      }
    }, { threshold: 0 });
    io.observe(canvas);

    const draw = () => {
      if (!isVisible) { rafRef.current = 0; return; }
      if (isSimulating) simulate();

      ctx.clearRect(0, 0, size.width, size.height);

      const nodes = nodesRef.current;
      const edges = edgesRef.current;

      // 绘制边
      for (const edge of edges) {
        const a = nodes.find(n => n.id === edge.from);
        const b = nodes.find(n => n.id === edge.to);
        if (!a || !b) continue;

        const alpha = 0.2 + (edge.intimacy / 100) * 0.6;
        ctx.strokeStyle = `rgba(236, 72, 153, ${alpha})`;
        ctx.lineWidth = 1 + (edge.intimacy / 100) * 4;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();

        // 亲密度标签
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        ctx.fillStyle = `rgba(236, 72, 153, ${alpha + 0.2})`;
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(String(edge.intimacy), mx, my - 4);
      }

      // 绘制节点
      for (const node of nodes) {
        const isHovered = hoveredNode === node.id;
        const isDragged = mouseRef.current.draggedNode?.id === node.id;

        // 光晕
        if (isHovered || isDragged) {
          ctx.fillStyle = node.color + '20';
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.radius + 8, 0, Math.PI * 2);
          ctx.fill();
        }

        // 节点圆形
        ctx.fillStyle = node.color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.fill();

        // 边框
        ctx.strokeStyle = isHovered ? '#FFF' : 'rgba(255,255,255,0.3)';
        ctx.lineWidth = isHovered ? 2.5 : 1;
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.stroke();

        // 名字首字母
        ctx.fillStyle = '#FFF';
        ctx.font = `bold 12px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(node.name[0], node.x, node.y);

        // 名字标签
        ctx.fillStyle = '#334155';
        ctx.font = '10px sans-serif';
        ctx.fillText(node.name, node.x, node.y + node.radius + 12);
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      io.disconnect();
    };
  }, [simulate, isSimulating, hoveredNode, size.width, size.height]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    mouseRef.current.x = x;
    mouseRef.current.y = y;

    if (mouseRef.current.isDown && mouseRef.current.draggedNode) {
      mouseRef.current.draggedNode.x = x;
      mouseRef.current.draggedNode.y = y;
      mouseRef.current.draggedNode.vx = 0;
      mouseRef.current.draggedNode.vy = 0;
      return;
    }

    // 检测悬停
    const node = nodesRef.current.find(n => {
      const dx = n.x - x;
      const dy = n.y - y;
      return Math.sqrt(dx * dx + dy * dy) < n.radius;
    });
    setHoveredNode(node?.id || null);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const node = nodesRef.current.find(n => {
      const dx = n.x - x;
      const dy = n.y - y;
      return Math.sqrt(dx * dx + dy * dy) < n.radius;
    });

    if (node) {
      mouseRef.current.isDown = true;
      mouseRef.current.draggedNode = node;
      setIsSimulating(false);
    }
  };

  const handleMouseUp = () => {
    mouseRef.current.isDown = false;
    mouseRef.current.draggedNode = null;
    setIsSimulating(true);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-700">关系网络</h3>
        <div className="flex items-center gap-3 text-[10px] text-slate-400">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500" />工作</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500" />创意</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-pink-500" />社交</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" />休息</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full" style={{ height: size.height }}>
        <canvas
          ref={canvasRef}
          width={size.width}
          height={size.height}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        />
      </div>
      <div className="mt-2 text-[10px] text-slate-400 text-center">
        拖拽节点调整位置 · 线条粗细表示亲密度
      </div>
    </div>
  );
}
