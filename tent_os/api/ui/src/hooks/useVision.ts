import { useState, useRef, useCallback, useEffect } from 'react';
import { FilesetResolver, FaceLandmarker, ObjectDetector } from '@mediapipe/tasks-vision';
import { useCamera } from './useCamera';
import { useYolo, type YoloDetection } from './useYolo';

interface VisionState {
  // 情绪
  lastEmotion: string;
  emotionConfidence: number;
  blendshapes: Record<string, number> | null;

  // 物体检测（YOLOv8）
  detectedObjects: YoloDetection[];

  // 注意力 / 注视
  gazeX: number; // -1 ~ 1, 画面左侧到右侧
  gazeY: number; // -1 ~ 1, 画面上方到下方

  // 场景分析
  lastSceneDescription: string | null;
  sceneAnalyzing: boolean;

  // 错误
  error: string | null;
}

// =================== 情绪特征签名（竞争评分系统）====================
const EMOTION_SIGNATURES = [
  {
    name: 'happy',
    weights: {
      mouthSmileLeft: 2.0, mouthSmileRight: 2.0,
      cheekPuff: 0.8, jawOpen: 0.4,
      eyeBlinkLeft: 0.2, eyeBlinkRight: 0.2,
      mouthFrownLeft: -1.0, mouthFrownRight: -1.0,
      browDownLeft: -0.5, browDownRight: -0.5,
    },
  },
  {
    name: 'sad',
    weights: {
      mouthFrownLeft: 2.0, mouthFrownRight: 2.0,
      browInnerUp: 1.2, browOuterUpLeft: 0.6, browOuterUpRight: 0.6,
      mouthPucker: 0.8,
      mouthSmileLeft: -1.5, mouthSmileRight: -1.5,
      jawOpen: -0.3,
    },
  },
  {
    name: 'angry',
    weights: {
      browDownLeft: 2.0, browDownRight: 2.0,
      mouthFrownLeft: 1.5, mouthFrownRight: 1.5,
      noseSneerLeft: 1.0, noseSneerRight: 1.0,
      jawOpen: 0.3,
      mouthSmileLeft: -1.5, mouthSmileRight: -1.5,
      browInnerUp: -0.5,
    },
  },
  {
    name: 'surprised',
    weights: {
      eyeWideLeft: 1.8, eyeWideRight: 1.8,
      browInnerUp: 1.2, browOuterUpLeft: 0.8, browOuterUpRight: 0.8,
      jawOpen: 1.2,
      mouthSmileLeft: -0.5, mouthSmileRight: -0.5,
      browDownLeft: -0.8, browDownRight: -0.8,
    },
  },
  {
    name: 'fearful',
    weights: {
      eyeWideLeft: 1.8, eyeWideRight: 1.8,
      browInnerUp: 1.0, browOuterUpLeft: 0.8, browOuterUpRight: 0.8,
      mouthStretchLeft: 0.8, mouthStretchRight: 0.8,
      jawOpen: -0.5,
      mouthSmileLeft: -0.5, mouthSmileRight: -0.5,
    },
  },
  {
    name: 'disgusted',
    weights: {
      noseSneerLeft: 2.0, noseSneerRight: 2.0,
      mouthFrownLeft: 1.2, mouthFrownRight: 1.2,
      browDownLeft: 0.6, browDownRight: 0.6,
      mouthSmileLeft: -1.0, mouthSmileRight: -1.0,
      jawOpen: -0.3,
    },
  },
];

// 收集所有与情绪签名相关的 blendshape 名称（用于计算 signalEnergy）
const RELEVANT_BLENDSHAPES = new Set<string>();
for (const sig of EMOTION_SIGNATURES) {
  for (const bs of Object.keys(sig.weights)) {
    RELEVANT_BLENDSHAPES.add(bs);
  }
}

function quickEmotionFromBlendshapes(blendshapes: Record<string, number>): { emotion: string; confidence: number } {
  const s = (name: string) => blendshapes[name] || 0;
  const scores: Record<string, number> = {};

  for (const sig of EMOTION_SIGNATURES) {
    let score = 0;
    let totalWeight = 0;
    for (const [bs, w] of Object.entries(sig.weights)) {
      score += s(bs) * w;
      totalWeight += Math.abs(w);
    }
    scores[sig.name] = totalWeight > 0 ? score / totalWeight : 0;
  }

  // Layer 3: 只计算与情绪签名相关的 blendshapes 的 signalEnergy
  const relevantValues = Object.entries(blendshapes)
    .filter(([k]) => RELEVANT_BLENDSHAPES.has(k))
    .map(([, v]) => v);
  const signalEnergy = relevantValues.length > 0
    ? relevantValues.reduce((sum, v) => sum + v * v, 0) / relevantValues.length
    : 0;

  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const [bestEmotion, bestScore] = sorted[0] || ['neutral', 0];
  const secondScore = sorted[1]?.[1] ?? 0;
  const margin = bestScore - secondScore;

  // Layer 3: 阈值平衡——既远离噪声，又不漏掉真实表情
  if (signalEnergy < 0.006) return { emotion: 'neutral', confidence: 0.2 };
  if (bestScore < 0.04) return { emotion: 'neutral', confidence: Math.min(0.5, 0.2 + signalEnergy * 3) };
  if (margin < 0.04) return { emotion: 'neutral', confidence: Math.min(0.6, 0.3 + margin * 5) };

  return { emotion: bestEmotion, confidence: Math.min(0.95, 0.4 + margin * 3 + signalEnergy * 4) };
}

// =================== 显著性计算（注意力机制）====================
interface SaliencyRegion {
  x: number; // 画面中心 x (0~1)
  y: number; // 画面中心 y (0~1)
  weight: number;
}

function computeAttentionGaze(
  faceLandmarks: any[],
  detectedObjects: YoloDetection[],
): { x: number; y: number } {
  const regions: SaliencyRegion[] = [];

  // 1. 人脸中心（最高显著性）
  if (faceLandmarks && faceLandmarks.length > 0) {
    const lm = faceLandmarks[0];
    let sumX = 0, sumY = 0;
    for (const pt of lm) {
      sumX += pt.x;
      sumY += pt.y;
    }
    regions.push({ x: sumX / lm.length, y: sumY / lm.length, weight: 10 });
  }

  // 2. 新出现的 / 移动的物体
  for (const obj of detectedObjects) {
    const cx = obj.normalized.x + obj.normalized.width / 2;
    const cy = obj.normalized.y + obj.normalized.height / 2;
    regions.push({ x: cx, y: cy, weight: obj.isHighInterest ? 5 : 2 });
  }

  if (regions.length === 0) {
    // 没有显著区域：看向画面中心偏上（模拟"看用户"）
    return { x: 0.5, y: 0.4 };
  }

  let totalWeight = 0;
  let wx = 0, wy = 0;
  for (const r of regions) {
    totalWeight += r.weight;
    wx += r.x * r.weight;
    wy += r.y * r.weight;
  }

  // 映射到 -1~1（Live2D 坐标系）
  // 注意：前置摄像头镜像，x 需要翻转
  const rawX = wx / totalWeight;
  const rawY = wy / totalWeight;
  return {
    x: -(rawX * 2 - 1), // 镜像翻转
    y: -(rawY * 2 - 1), // y 也翻转（画面坐标系 vs Live2D）
  };
}

// =================== useVision Hook ====================
export function useVision(
  sendWs?: (type: string, payload: unknown) => void,
  userId?: string,
) {
  const camera = useCamera();
  const yolo = useYolo();
  const sendWsRef = useRef(sendWs);
  sendWsRef.current = sendWs; // 始终指向最新引用，但不触发重渲染

  const [visionState, setVisionState] = useState<VisionState>({
    lastEmotion: 'neutral',
    emotionConfidence: 0,
    blendshapes: null,
    detectedObjects: [],
    gazeX: 0,
    gazeY: -0.2,
    lastSceneDescription: null,
    sceneAnalyzing: false,
    error: null,
  });

  const faceLandmarkerRef = useRef<FaceLandmarker | null>(null);
  const objectDetectorRef = useRef<ObjectDetector | null>(null);
  const rafRef = useRef<number>(0);
  const lastSendTime = useRef<number>(0);
  const lastSceneTime = useRef<number>(0);
  const lastObjectSendTime = useRef<number>(0);
  const runningRef = useRef(false);
  // const objectsHistoryRef = useRef<Map<string, DetectedObject>>(new Map());

  // Layer 1: EMA 平滑状态
  const emaRef = useRef<Record<string, number>>({});
  const emaAlpha = 0.3;  // 约 3-4 帧达到稳定

  // Layer 2: 静止检测状态
  const prevBlendshapesRef = useRef<Record<string, number>>({});
  const stillFrameCount = useRef(0);
  const STILL_THRESHOLD = 0.015;      // RMS 变化阈值
  const STILL_FRAMES_REQUIRED = 10;   // 连续 10 帧 (@60fps ≈ 160ms)

  // ========== 启动视觉系统 ==========
  const startVision = useCallback(async () => {
    if (camera.isActive) return; // 已经启动

    try {
      setVisionState((s) => ({ ...s, error: null }));
      await camera.startCamera();
      // 同时加载 YOLO 模型
      yolo.loadModel();
    } catch (err) {
      setVisionState((s) => ({ ...s, error: '摄像头启动失败' }));
      return;
    }
  }, [camera, yolo]);

  // ========== 加载 AI 模型并启动检测循环 ==========
  useEffect(() => {
    if (!camera.isActive || !camera.videoRef.current) return;

    let destroyed = false;

    async function setup() {
      try {
        const vision = await FilesetResolver.forVisionTasks(
          'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm'
        );

        // 1. FaceLandmarker
        let faceLandmarker: FaceLandmarker;
        try {
          faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
            baseOptions: {
              modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
              delegate: 'GPU',
            },
            runningMode: 'VIDEO',
            outputFaceBlendshapes: true,
            numFaces: 1,
          });
          console.log('[Vision] FaceLandmarker GPU 加载成功');
        } catch {
          faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
            baseOptions: {
              modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
              delegate: 'CPU',
            },
            runningMode: 'VIDEO',
            outputFaceBlendshapes: true,
            numFaces: 1,
          });
          console.log('[Vision] FaceLandmarker CPU 加载成功');
        }
        if (destroyed) { faceLandmarker.close(); return; }
        faceLandmarkerRef.current = faceLandmarker;

        // 3. 检测循环（只在摄像头真正启动后才启动 RAF，避免空转耗电）
        runningRef.current = true;
        let frameCount = 0;

        const detect = async () => {
          if (!runningRef.current) return;
          // Tab 后台时完全停止 RAF，改为 setTimeout 低频检查（1秒）
          if (document.hidden) {
            if (runningRef.current) {
              rafRef.current = window.setTimeout(detect, 1000);
            }
            return;
          }
          const video = camera.videoRef.current;
          const fl = faceLandmarkerRef.current;
          if (!video || !fl || video.readyState < 2) {
            // FIX: camera 未就绪时不 RAF，改为 2 秒后检查，避免 60fps 空转
            if (runningRef.current) rafRef.current = window.setTimeout(detect, 2000);
            return;
          }

          try {
            const ts = performance.now();
            frameCount++;

            // ---- FaceLandmarker ----
            const faceResults = fl.detectForVideo(video, ts);
            let currentBlendshapes: Record<string, number> = {};
            let faceLandmarks: any[] = [];

            if (faceResults.faceBlendshapes && faceResults.faceBlendshapes.length > 0) {
              const cats = faceResults.faceBlendshapes[0].categories;
              cats.forEach((c) => { currentBlendshapes[c.categoryName] = c.score; });
              if (faceResults.faceLandmarks) {
                faceLandmarks = faceResults.faceLandmarks;
              }

              // ===== Layer 2: 静止检测（必须用原始值，不能用EMA后的）=====
              let rmsChange = 0;
              const keys = Object.keys(currentBlendshapes);
              if (keys.length > 0 && Object.keys(prevBlendshapesRef.current).length > 0) {
                let sumSq = 0;
                for (const k of keys) {
                  const diff = currentBlendshapes[k] - (prevBlendshapesRef.current[k] ?? 0);
                  sumSq += diff * diff;
                }
                rmsChange = Math.sqrt(sumSq / keys.length);
              }
              prevBlendshapesRef.current = { ...currentBlendshapes };

              // ===== Layer 1: EMA 平滑 =====
              const smoothed: Record<string, number> = {};
              for (const [k, v] of Object.entries(currentBlendshapes)) {
                const prevEma = emaRef.current[k] ?? v;
                smoothed[k] = emaAlpha * v + (1 - emaAlpha) * prevEma;
              }
              emaRef.current = smoothed;

              const isStill = rmsChange < STILL_THRESHOLD;
              if (isStill) {
                stillFrameCount.current++;
              } else {
                stillFrameCount.current = 0;
              }

              let emotion: string;
              let confidence: number;

              if (stillFrameCount.current >= STILL_FRAMES_REQUIRED) {
                // 面部静止 → 锁定 neutral，不做情绪分析
                emotion = 'neutral';
                confidence = 0.3;
              } else {
                // 面部有活动 → 用平滑后的值分析情绪
                const result = quickEmotionFromBlendshapes(smoothed);
                emotion = result.emotion;
                confidence = result.confidence;
              }

              setVisionState((s) => ({
                ...s,
                blendshapes: smoothed,
                lastEmotion: emotion,
                emotionConfidence: confidence,
              }));

              // 每 300ms 发送 blendshapes 到后端（发送平滑后的值）
              const now = Date.now();
              if (now - lastSendTime.current > 300 && sendWs) {
                lastSendTime.current = now;
                const payload: Record<string, number> = {};
                for (const k of [
                  'jawOpen','mouthSmileLeft','mouthSmileRight','mouthFrownLeft','mouthFrownRight',
                  'eyeWideLeft','eyeWideRight','eyeBlinkLeft','eyeBlinkRight',
                  'browInnerUp','browOuterUpLeft','browOuterUpRight',
                  'browDownLeft','browDownRight','noseSneerLeft','noseSneerRight',
                  'cheekPuff','mouthPucker','mouthStretchLeft','mouthStretchRight',
                ]) {
                  if (smoothed[k] !== undefined) payload[k] = smoothed[k];
                }
                sendWs('vision.blendshapes', {
                  blendshapes: payload,
                  timestamp: now,
                  user_id: userId || 'web_user',
                  is_still: stillFrameCount.current >= STILL_FRAMES_REQUIRED,
                });
              }
            }

            // ---- YOLOv8 物体检测（每 3 帧，YOLO 模型 ready 后）----
            let currentObjects: YoloDetection[] = [];
            if (yolo.isReady && frameCount % 3 === 0) {
              try {
                const detections = await yolo.detect(video, video.videoWidth, video.videoHeight);
                currentObjects = detections;
                setVisionState((s) => ({ ...s, detectedObjects: detections }));

                // 每 2 秒发送物体清单到后端
                const now = Date.now();
                if (now - lastObjectSendTime.current > 2000 && sendWsRef.current) {
                  lastObjectSendTime.current = now;
                  sendWsRef.current('vision.objects_detected', {
                    objects: detections.map((o) => ({
                      name: o.label,
                      confidence: o.confidence,
                      normalized: o.normalized,
                    })),
                    timestamp: now,
                    user_id: userId || 'web_user',
                  });
                }
              } catch (e) {
                console.warn('[Vision] YOLO 推理失败:', e);
              }
            }

            // ---- 注意力 / 注视计算 ----
            const gaze = computeAttentionGaze(faceLandmarks, currentObjects);
            // 加入轻微随机抖动（模拟人眼自然扫视）
            const jitterX = (Math.random() - 0.5) * 0.03;
            const jitterY = (Math.random() - 0.5) * 0.03;
            setVisionState((s) => ({
              ...s,
              gazeX: Math.max(-1, Math.min(1, gaze.x + jitterX)),
              gazeY: Math.max(-1, Math.min(1, gaze.y + jitterY)),
            }));

            // ---- Phase 1: 定时场景截图（每 5 秒）----
            const now = Date.now();
            if (now - lastSceneTime.current > 5000 && sendWsRef.current) {
              lastSceneTime.current = now;
              camera.captureBlob({ maxWidth: 480, maxHeight: 360, quality: 0.6 }).then((blob) => {
                if (!blob) return;
                const reader = new FileReader();
                reader.onloadend = () => {
                  const base64 = reader.result as string;
                  sendWsRef.current?.('vision.scene_frame', {
                    image_data: base64,
                    timestamp: now,
                    user_id: userId || 'web_user',
                    resolution: camera.currentResolution,
                  });
                };
                reader.readAsDataURL(blob);
              });
            }

            // ---- 调试日志（每 ~3 秒）----
            if (frameCount % 180 === 0) {
              const top = Object.entries(currentBlendshapes)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 5)
                .map(([k, v]) => `${k}:${v.toFixed(2)}`)
                .join(', ');
              console.log(`[Vision] 情绪:${visionState.lastEmotion} 物体:${currentObjects.length} 注视:(${visionState.gazeX.toFixed(2)},${visionState.gazeY.toFixed(2)}) | bs:${top}`);
            }
          } catch (err) {
            console.warn('[Vision] 检测帧失败:', err);
          }

          if (runningRef.current) {
            rafRef.current = requestAnimationFrame(detect);
          }
        };

        rafRef.current = requestAnimationFrame(detect);
      } catch (err) {
        console.error('[Vision] 初始化失败:', err);
        setVisionState((s) => ({ ...s, error: '视觉模型加载失败' }));
      }
    }

    setup();

    return () => {
      destroyed = true;
      runningRef.current = false;
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        clearTimeout(rafRef.current);
      }
      if (faceLandmarkerRef.current) {
        try { faceLandmarkerRef.current.close(); } catch {}
        faceLandmarkerRef.current = null;
      }
      if (objectDetectorRef.current) {
        try { objectDetectorRef.current.close(); } catch {}
        objectDetectorRef.current = null;
      }
    };
  // 只在 camera.isActive 变化时触发，sendWs 用 ref 避免引用变化
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.isActive, yolo.isReady]);

  // ========== 停止 ==========
  const stopVision = useCallback(() => {
    runningRef.current = false;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    camera.stopCamera();
    setVisionState((s) => ({
      ...s,
      lastEmotion: 'neutral',
      emotionConfidence: 0,
      blendshapes: null,
      detectedObjects: [],
      gazeX: 0,
      gazeY: -0.2,
      lastSceneDescription: null,
      sceneAnalyzing: false,
    }));
  }, [camera]);

  return {
    // 摄像头控制（透传 useCamera）
    isActive: camera.isActive,
    isLoading: camera.isLoading,
    devices: camera.devices,
    selectedDeviceId: camera.selectedDeviceId,
    mirror: camera.mirror,
    currentResolution: camera.currentResolution,
    videoRef: camera.videoRef,
    startCamera: startVision,
    stopCamera: stopVision,
    switchCamera: camera.switchCamera,
    toggleMirror: camera.toggleMirror,
    enumerateCameras: camera.enumerateCameras,

    // YOLO 状态
    yoloReady: yolo.isReady,
    yoloError: yolo.error,

    // 视觉状态
    ...visionState,
  };
}
