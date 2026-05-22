import { useEffect, useRef, useState } from 'react';
import type { L2D } from 'l2d';

interface Live2DAvatarProps {
  modelPath?: string;
  scale?: number;
  emotion?: string;
  mouthOpen?: number; // 0-1 for lipsync
  gazeX?: number;     // -1 ~ 1, 眼球水平方向
  gazeY?: number;     // -1 ~ 1, 眼球垂直方向
  width?: number;
  height?: number;
}

// 情绪 -> 表情ID 映射（根据常见Live2D模型的表情命名约定）
const EMOTION_EXPRESSION_MAP: Record<string, string> = {
  happy: 'happy',
  sad: 'sad',
  excited: 'excited',
  confused: 'confused',
  proud: 'proud',
  sleepy: 'sleepy',
  listening: 'normal',
};

// 情绪 -> 动作组 映射（可选：情绪变化时播放配套动作）
const EMOTION_MOTION_MAP: Record<string, string> = {
  happy: 'Idle',
  sad: 'Idle',
  excited: 'Idle',
  confused: 'Idle',
  proud: 'Idle',
  sleepy: 'Idle',
  listening: 'Idle',
};

export function Live2DAvatar({
  modelPath = 'https://cdn.jsdelivr.net/gh/Live2D/CubismWebSamples@develop/Samples/Resources/Hiyori/Hiyori.model3.json', // 支持从外部传入自定义模型路径
  scale = 0.5,
  emotion = 'listening',
  mouthOpen = 0,
  gazeX = 0,
  gazeY = -0.2,
  width = 200,
  height = 250,
}: Live2DAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const l2dRef = useRef<L2D | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modelLoaded, setModelLoaded] = useState(false);

  // 初始化 l2d 并加载模型
  useEffect(() => {
    if (!canvasRef.current) return;

    let destroyed = false;

    async function setup() {
      try {
        const { init } = await import('l2d');
        const l2d = init(canvasRef.current!);
        if (destroyed) {
          l2d.destroy();
          return;
        }
        l2dRef.current = l2d;

        await l2d.load({
          path: modelPath,
          scale,
          logLevel: 'error',
        });

        if (destroyed) {
          l2d.destroy();
          return;
        }

        setModelLoaded(true);
        setLoading(false);
      } catch (err) {
        if (!destroyed) {
          const msg = err instanceof Error ? err.message : '模型加载失败';
          console.warn('[Live2D] 初始化失败:', msg);
          setError(msg);
          setLoading(false);
        }
      }
    }

    setup();

    return () => {
      destroyed = true;
      if (l2dRef.current) {
        try {
          l2dRef.current.destroy();
        } catch {}
        l2dRef.current = null;
      }
    };
  }, [modelPath, scale]);

  // 情绪变化时切换表情 + 播放动作
  useEffect(() => {
    const l2d = l2dRef.current;
    if (!l2d || !modelLoaded) return;

    const expressionId = EMOTION_EXPRESSION_MAP[emotion] || 'normal';
    try {
      l2d.setExpression(expressionId);
    } catch (e) {
      // 表情不存在时静默失败
    }

    const motionGroup = EMOTION_MOTION_MAP[emotion];
    if (motionGroup) {
      try {
        l2d.playMotion(motionGroup);
      } catch {}
    }
  }, [emotion, modelLoaded]);

  // 嘴唇同步
  useEffect(() => {
    const l2d = l2dRef.current;
    if (!l2d || !modelLoaded) return;
    try {
      l2d.setParams({
        ParamMouthOpenY: mouthOpen,
        PARAM_MOUTH_OPEN_Y: mouthOpen,
      });
    } catch {}
  }, [mouthOpen, modelLoaded]);

  // 眼球注视方向（视觉注意力）
  useEffect(() => {
    const l2d = l2dRef.current;
    if (!l2d || !modelLoaded) return;
    try {
      l2d.setParams({
        ParamEyeBallX: gazeX,
        PARAM_EYE_BALL_X: gazeX,
        ParamEyeBallY: gazeY,
        PARAM_EYE_BALL_Y: gazeY,
      });
    } catch {}
  }, [gazeX, gazeY, modelLoaded]);

  if (error) {
    // 降级：CSS Emoji 头像
    const emojiMap: Record<string, string> = {
      happy: ':)',
      sad: ':(',
      excited: ':D',
      confused: ':?',
      proud: ':]',
      sleepy: 'zZ',
      listening: '||',
    };
    const emoji = emojiMap[emotion] || 'AI';
    return (
      <div
        className="flex items-center justify-center bg-gradient-to-br from-tent-100 to-tent-200 rounded-2xl"
        style={{ width, height }}
      >
        <div className="text-center">
          <div className="w-16 h-16 mx-auto rounded-full bg-tent-500/20 flex items-center justify-center animate-pulse">
            <span className="text-3xl">{emoji}</span>
          </div>
          <p className="text-[10px] text-tent-700 mt-2">Live2D未加载</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative" style={{ width, height }}>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="rounded-2xl"
        style={{ width, height }}
      />
      {loading && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-white/80 rounded-2xl"
          style={{ width, height }}
        >
          <div className="w-8 h-8 border-2 border-tent-300 border-t-tent-600 rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
}
