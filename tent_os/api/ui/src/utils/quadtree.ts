/**
 * QuadTree — 二维空间分割树（Barnes-Hut 简化版）
 * 用于力导向图的近似斥力计算，将 O(n²) 降为 O(n log n)
 */

interface Point {
  x: number;
  y: number;
  mass?: number;
}

interface Boundary {
  x: number; // 中心 x
  y: number; // 中心 y
  w: number; // 半宽
  h: number; // 半高
}

export interface QuadTreeNode {
  boundary: Boundary;
  points: Point[];
  divided: boolean;
  northeast?: QuadTreeNode;
  northwest?: QuadTreeNode;
  southeast?: QuadTreeNode;
  southwest?: QuadTreeNode;
  centerOfMass: { x: number; y: number };
  totalMass: number;
}

const CAPACITY = 4; // 每个象限最大节点数，超过则分裂

function contains(boundary: Boundary, point: Point): boolean {
  return (
    point.x >= boundary.x - boundary.w &&
    point.x < boundary.x + boundary.w &&
    point.y >= boundary.y - boundary.h &&
    point.y < boundary.y + boundary.h
  );
}

function createBoundary(x: number, y: number, w: number, h: number): Boundary {
  return { x, y, w, h };
}

export function createQuadTree(boundary: Boundary): QuadTreeNode {
  return {
    boundary,
    points: [],
    divided: false,
    centerOfMass: { x: 0, y: 0 },
    totalMass: 0,
  };
}

function subdivide(node: QuadTreeNode): void {
  const { x, y, w, h } = node.boundary;
  node.northeast = createQuadTree(createBoundary(x + w / 2, y - h / 2, w / 2, h / 2));
  node.northwest = createQuadTree(createBoundary(x - w / 2, y - h / 2, w / 2, h / 2));
  node.southeast = createQuadTree(createBoundary(x + w / 2, y + h / 2, w / 2, h / 2));
  node.southwest = createQuadTree(createBoundary(x - w / 2, y + h / 2, w / 2, h / 2));
  node.divided = true;
}

export function quadTreeInsert(node: QuadTreeNode, point: Point): boolean {
  if (!contains(node.boundary, point)) return false;

  if (node.points.length < CAPACITY && !node.divided) {
    node.points.push(point);
    // 更新质心
    const m = point.mass ?? 1;
    node.centerOfMass.x = (node.centerOfMass.x * node.totalMass + point.x * m) / (node.totalMass + m);
    node.centerOfMass.y = (node.centerOfMass.y * node.totalMass + point.y * m) / (node.totalMass + m);
    node.totalMass += m;
    return true;
  }

  if (!node.divided) {
    subdivide(node);
    // 将已有节点迁移到子象限
    for (const p of node.points) {
      if (quadTreeInsert(node.northeast!, p)) continue;
      if (quadTreeInsert(node.northwest!, p)) continue;
      if (quadTreeInsert(node.southeast!, p)) continue;
      quadTreeInsert(node.southwest!, p);
    }
    node.points = []; // 清空当前层，只保留在叶子节点
  }

  let inserted = false;
  if (quadTreeInsert(node.northeast!, point)) inserted = true;
  else if (quadTreeInsert(node.northwest!, point)) inserted = true;
  else if (quadTreeInsert(node.southeast!, point)) inserted = true;
  else if (quadTreeInsert(node.southwest!, point)) inserted = true;

  if (inserted) {
    const m = point.mass ?? 1;
    node.centerOfMass.x = (node.centerOfMass.x * node.totalMass + point.x * m) / (node.totalMass + m);
    node.centerOfMass.y = (node.centerOfMass.y * node.totalMass + point.y * m) / (node.totalMass + m);
    node.totalMass += m;
  }

  return inserted;
}

/**
 * 计算近似斥力
 * @param node QuadTree 节点
 * @param point 目标点
 * @param theta 近似阈值（0-1，越大越近似、越快）
 * @param repulsion 斥力系数
 * @returns { fx, fy } 力的分量
 */
export function quadTreeRepulsion(
  node: QuadTreeNode,
  point: Point,
  theta: number,
  repulsion: number,
): { fx: number; fy: number } {
  let fx = 0;
  let fy = 0;

  // 计算节点边界到目标点的距离
  const dx = node.centerOfMass.x - point.x;
  const dy = node.centerOfMass.y - point.y;
  const distSq = dx * dx + dy * dy;
  const dist = Math.sqrt(distSq) || 0.001;

  // 边界宽度（用半宽+半高的平均作为直径估计）
  const s = (node.boundary.w + node.boundary.h);

  // Barnes-Hut 条件：如果 s/d < theta，且不是叶子节点，用质心近似
  if ((s / dist < theta || !node.divided) && node.totalMass > 0) {
    // 排除自身（如果当前节点只包含一个点且就是目标点）
    if (node.points.length === 1 && node.points[0] === point) {
      return { fx: 0, fy: 0 };
    }
    // 质心近似斥力
    const force = (repulsion * node.totalMass) / distSq;
    fx -= (dx / dist) * force;
    fy -= (dy / dist) * force;
    return { fx, fy };
  }

  // 不满足近似条件，递归到子象限
  if (node.divided) {
    const ne = quadTreeRepulsion(node.northeast!, point, theta, repulsion);
    const nw = quadTreeRepulsion(node.northwest!, point, theta, repulsion);
    const se = quadTreeRepulsion(node.southeast!, point, theta, repulsion);
    const sw = quadTreeRepulsion(node.southwest!, point, theta, repulsion);
    fx += ne.fx + nw.fx + se.fx + sw.fx;
    fy += ne.fy + nw.fy + se.fy + sw.fy;
  } else {
    // 叶子节点：精确计算每个点的斥力
    for (const p of node.points) {
      if (p === point) continue;
      const pdx = p.x - point.x;
      const pdy = p.y - point.y;
      const pDistSq = pdx * pdx + pdy * pdy || 0.001;
      const pDist = Math.sqrt(pDistSq);
      const force = repulsion / pDistSq;
      fx -= (pdx / pDist) * force;
      fy -= (pdy / pDist) * force;
    }
  }

  return { fx, fy };
}

/**
 * 从节点数组快速构建 QuadTree
 */
export function buildQuadTree(
  nodes: Array<{ x: number; y: number }>,
  width: number,
  height: number,
): QuadTreeNode {
  const boundary = createBoundary(width / 2, height / 2, width / 2, height / 2);
  const tree = createQuadTree(boundary);
  for (const n of nodes) {
    quadTreeInsert(tree, { x: n.x, y: n.y, mass: 1 });
  }
  return tree;
}
