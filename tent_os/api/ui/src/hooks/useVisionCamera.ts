/**
 * useCamera — 摄像头采集 + VLM 感知闭环 Hook
 *
 * 功能:
 * 1. 申请摄像头权限，创建 video 元素
 * 2. 定期从 video 帧截图 (base64 JPEG)
 * 3. 调用后端 /ui/api/vision/analyze 进行 VLM 分析
 * 4. 通过 onPerception 回调返回分析结果
 *
 * 补齐 PRD 缺口: 摄像头 → VLM → 空间记忆的感知闭环
 */
import { useState, useRef, useCallback, useEffect } from 'react';
const API_BASE = '';  // 同项目其他 API 文件

export interface CameraState {
  enabled: boolean;
  capturing: boolean;
  lastCaptureAt: number | null;
  error: string | null;
  peopleCount: number;
}

export function useCamera(onPerception?: (result: unknown) => void) {
  const [state, setState] = useState<CameraState>({
    enabled: false,
    capturing: false,
    lastCaptureAt: null,
    error: null,
    peopleCount: 0,
  });

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // 初始化 canvas（离屏，用于截图）
  useEffect(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    canvasRef.current = canvas;
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      stopStream();
    };
  }, []);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current = null;
    }
  }, []);

  const captureFrame = useCallback(async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7);

    setState(prev => ({ ...prev, capturing: true, lastCaptureAt: Date.now() }));

    try {
      const res = await fetch(`${API_BASE}/ui/api/vision/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: dataUrl,
          room_id: 'living_room',
        }),
      });
      const json = await res.json();

      if (json.status === 'analyzed') {
        setState(prev => ({
          ...prev,
          capturing: false,
          peopleCount: json.result?.people_count ?? 0,
          error: null,
        }));
        onPerception?.(json.result);
      } else {
        setState(prev => ({
          ...prev,
          capturing: false,
          error: json.status === 'parse_failed' ? 'VLM 输出解析失败' : '分析失败',
        }));
      }
    } catch (e) {
      setState(prev => ({
        ...prev,
        capturing: false,
        error: e instanceof Error ? e.message : '网络错误',
      }));
    }
  }, [onPerception]);

  const start = useCallback(async () => {
    if (streamRef.current) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;

      const video = document.createElement('video');
      video.autoplay = true;
      video.playsInline = true;
      video.srcObject = stream;
      video.muted = true;
      await video.play();
      videoRef.current = video;

      setState(prev => ({ ...prev, enabled: true, error: null }));

      // 每 15 秒截一帧分析（避免过于频繁调用 VLM）
      intervalRef.current = setInterval(captureFrame, 15000);

      // 首次立即分析
      setTimeout(captureFrame, 2000);
    } catch (e) {
      setState(prev => ({
        ...prev,
        enabled: false,
        error: e instanceof Error ? e.message : '摄像头启动失败',
      }));
    }
  }, [captureFrame]);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    stopStream();
    setState(prev => ({ ...prev, enabled: false, capturing: false }));
  }, [stopStream]);

  const toggle = useCallback(() => {
    if (state.enabled) stop();
    else start();
  }, [state.enabled, start, stop]);

  return { state, start, stop, toggle, captureFrame };
}
