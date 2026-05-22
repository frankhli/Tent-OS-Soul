import { useState, useRef, useCallback } from 'react';
import * as ort from 'onnxruntime-web';

// COCO 80 类标签（YOLOv8 预训练模型使用的）
export const COCO_LABELS = [
  'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
  'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog',
  'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella',
  'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
  'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 'bottle',
  'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich',
  'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
  'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard',
  'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock',
  'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush',
];

// 室内常见物体高亮（用于注意力机制）
export const HIGH_INTEREST_CLASSES = new Set([
  'person', 'cell phone', 'laptop', 'cup', 'mouse', 'remote', 'keyboard',
  'book', 'bottle', 'clock', 'chair', 'couch', 'tv', 'potted plant',
]);

export interface YoloDetection {
  label: string;
  confidence: number;
  bbox: [number, number, number, number]; // [x, y, width, height] 原始图像坐标
  normalized: { x: number; y: number; width: number; height: number };
  isHighInterest: boolean;
}

interface YoloState {
  isLoading: boolean;
  isReady: boolean;
  error: string | null;
  detections: YoloDetection[];
}

const INPUT_SIZE = 640;
const CONFIDENCE_THRESHOLD = 0.25;
const IOU_THRESHOLD = 0.45;

/**
 * YOLOv8n ONNX 前端推理 Hook
 *
 * 流程：
 * 1. 加载 ONNX 模型（ONNX Runtime Web）
 * 2. 输入图像 → letterbox resize → normalize → tensor
 * 3. session.run() 推理
 * 4. 解析输出 [1, 84, 8400] → 候选框 → NMS → 结果
 */
export function useYolo() {
  const [state, setState] = useState<YoloState>({
    isLoading: false,
    isReady: false,
    error: null,
    detections: [],
  });

  const sessionRef = useRef<ort.InferenceSession | null>(null);

  // 加载模型
  const loadModel = useCallback(async () => {
    if (sessionRef.current) return;
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      // WASM 从 CDN 加载（避免 Vite hash 文件名问题）
      ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.25.1/dist/';
      ort.env.wasm.numThreads = 2;
      const session = await ort.InferenceSession.create('/ui/models/yolov8n.onnx', {
        executionProviders: ['wasm'],
        graphOptimizationLevel: 'all',
      });
      sessionRef.current = session;
      console.log('[YOLO] 模型加载成功');
      setState((s) => ({ ...s, isLoading: false, isReady: true }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'YOLO 模型加载失败';
      console.error('[YOLO] 加载失败:', msg);
      setState((s) => ({ ...s, isLoading: false, error: msg }));
    }
  }, []);

  // 前处理：letterbox resize + normalize
  function preprocess(imageData: ImageData, srcWidth: number, srcHeight: number) {
    const canvas = document.createElement('canvas');
    canvas.width = INPUT_SIZE;
    canvas.height = INPUT_SIZE;
    const ctx = canvas.getContext('2d')!;

    // 计算 letterbox 缩放比例
    const scale = Math.min(INPUT_SIZE / srcWidth, INPUT_SIZE / srcHeight);
    const newW = Math.round(srcWidth * scale);
    const newH = Math.round(srcHeight * scale);
    const padX = (INPUT_SIZE - newW) / 2;
    const padY = (INPUT_SIZE - newH) / 2;

    // 灰色背景填充
    ctx.fillStyle = '#808080';
    ctx.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE);
    // 从 ImageData 绘制到临时 canvas 再缩放
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = srcWidth;
    tempCanvas.height = srcHeight;
    tempCanvas.getContext('2d')!.putImageData(imageData, 0, 0);
    ctx.drawImage(tempCanvas, padX, padY, newW, newH);

    // 提取像素并归一化
    const imgData = ctx.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE);
    const data = imgData.data;
    const floatData = new Float32Array(3 * INPUT_SIZE * INPUT_SIZE);

    // RGB 归一化 /255
    for (let i = 0; i < INPUT_SIZE * INPUT_SIZE; i++) {
      floatData[i] = data[i * 4] / 255.0;                    // R
      floatData[i + INPUT_SIZE * INPUT_SIZE] = data[i * 4 + 1] / 255.0;  // G
      floatData[i + 2 * INPUT_SIZE * INPUT_SIZE] = data[i * 4 + 2] / 255.0; // B
    }

    return { tensorData: floatData, scale, padX, padY };
  }

  // 后处理：解析输出 → NMS
  function postprocess(
    output: Float32Array,
    scale: number,
    padX: number,
    padY: number,
    srcWidth: number,
    srcHeight: number,
  ): YoloDetection[] {
    // output shape: [1, 84, 8400] → flatten 后是 float32 array
    // 实际从 ONNX 输出获取
    const numAnchors = 8400;
    const numClasses = 80;

    const candidates: Array<{
      x: number; y: number; w: number; h: number;
      score: number; classId: number;
    }> = [];

    for (let i = 0; i < numAnchors; i++) {
      // 每个 anchor 的 84 个值
      const cx = output[i];
      const cy = output[numAnchors + i];
      const w = output[numAnchors * 2 + i];
      const h = output[numAnchors * 3 + i];

      // 找最高分类分数
      let bestScore = 0;
      let bestClass = -1;
      for (let c = 0; c < numClasses; c++) {
        const score = output[numAnchors * (4 + c) + i];
        if (score > bestScore) {
          bestScore = score;
          bestClass = c;
        }
      }

      if (bestScore > CONFIDENCE_THRESHOLD) {
        candidates.push({ x: cx, y: cy, w, h, score: bestScore, classId: bestClass });
      }
    }

    // 将 center-x/y/width/height 转换为左上角坐标
    const boxes = candidates.map((c) => ({
      x1: c.x - c.w / 2,
      y1: c.y - c.h / 2,
      x2: c.x + c.w / 2,
      y2: c.y + c.h / 2,
      score: c.score,
      classId: c.classId,
    }));

    // NMS（按类别分组做）
    const keep: typeof boxes = [];
    const classGroups = new Map<number, typeof boxes>();
    for (const b of boxes) {
      const arr = classGroups.get(b.classId) || [];
      arr.push(b);
      classGroups.set(b.classId, arr);
    }

    for (const [, group] of classGroups) {
      // 按分数降序
      group.sort((a, b) => b.score - a.score);
      const suppressed = new Set<number>();

      for (let i = 0; i < group.length; i++) {
        if (suppressed.has(i)) continue;
        keep.push(group[i]);

        for (let j = i + 1; j < group.length; j++) {
          if (suppressed.has(j)) continue;
          const iou = computeIoU(group[i], group[j]);
          if (iou > IOU_THRESHOLD) {
            suppressed.add(j);
          }
        }
      }
    }

    // 映射回原始图像坐标
    return keep.map((b) => {
      // 先移除 padding
      const nx1 = (b.x1 - padX) / scale;
      const ny1 = (b.y1 - padY) / scale;
      const nx2 = (b.x2 - padX) / scale;
      const ny2 = (b.y2 - padY) / scale;

      const x = Math.max(0, Math.min(nx1, srcWidth));
      const y = Math.max(0, Math.min(ny1, srcHeight));
      const w = Math.max(0, Math.min(nx2 - nx1, srcWidth - x));
      const h = Math.max(0, Math.min(ny2 - ny1, srcHeight - y));

      const label = COCO_LABELS[b.classId] || `class_${b.classId}`;

      return {
        label,
        confidence: Math.round(b.score * 1000) / 1000,
        bbox: [x, y, w, h] as [number, number, number, number],
        normalized: {
          x: x / srcWidth,
          y: y / srcHeight,
          width: w / srcWidth,
          height: h / srcHeight,
        },
        isHighInterest: HIGH_INTEREST_CLASSES.has(label),
      };
    });
  }

  function computeIoU(
    a: { x1: number; y1: number; x2: number; y2: number },
    b: { x1: number; y1: number; x2: number; y2: number },
  ) {
    const xi1 = Math.max(a.x1, b.x1);
    const yi1 = Math.max(a.y1, b.y1);
    const xi2 = Math.min(a.x2, b.x2);
    const yi2 = Math.min(a.y2, b.y2);
    const interW = Math.max(0, xi2 - xi1);
    const interH = Math.max(0, yi2 - yi1);
    const interArea = interW * interH;
    const unionArea = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - interArea;
    return unionArea > 0 ? interArea / unionArea : 0;
  }

  // 推理一帧
  const detect = useCallback(async (
    imageSource: HTMLVideoElement | HTMLCanvasElement | HTMLImageElement,
    srcWidth: number,
    srcHeight: number,
  ): Promise<YoloDetection[]> => {
    const session = sessionRef.current;
    if (!session) return [];

    try {
      // 从视频/画布提取 ImageData
      const canvas = document.createElement('canvas');
      canvas.width = srcWidth;
      canvas.height = srcHeight;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(imageSource, 0, 0, srcWidth, srcHeight);
      const imageData = ctx.getImageData(0, 0, srcWidth, srcHeight);

      // 前处理
      const { tensorData, scale, padX, padY } = preprocess(imageData, srcWidth, srcHeight);

      // 创建输入 tensor [1, 3, 640, 640]
      const inputTensor = new ort.Tensor('float32', tensorData, [1, 3, INPUT_SIZE, INPUT_SIZE]);

      // 推理
      const feeds: Record<string, ort.Tensor> = {};
      const inputName = session.inputNames[0];
      feeds[inputName] = inputTensor;
      const results = await session.run(feeds);

      // 获取输出
      const outputName = session.outputNames[0];
      const outputTensor = results[outputName];
      const outputData = outputTensor.data as Float32Array;

      // 后处理
      const detections = postprocess(outputData, scale, padX, padY, srcWidth, srcHeight);
      setState((s) => ({ ...s, detections }));
      return detections;
    } catch (err) {
      console.error('[YOLO] 推理失败:', err);
      return [];
    }
  }, []);

  return {
    ...state,
    loadModel,
    detect,
  };
}
