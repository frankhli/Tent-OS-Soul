/**
 * useCamera — 摄像头管理 Hook（兼容版）
 *
 * 功能:
 * 1. 申请摄像头权限，管理 video 元素
 * 2. 设备枚举与切换
 * 3. 截图（Blob / DataURL）
 * 4. 镜像切换
 *
 * 被 useVision.ts 依赖，提供完整的摄像头控制能力。
 */
import { useState, useRef, useCallback } from 'react';

export interface CameraResolution {
  width: number;
  height: number;
}

export function useCamera() {
  const [isActive, setIsActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [mirror, setMirror] = useState(true);
  const [currentResolution, setCurrentResolution] = useState<CameraResolution | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const enumerateCameras = useCallback(async () => {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      const cams = devs.filter(d => d.kind === 'videoinput');
      setDevices(cams);
      return cams;
    } catch {
      return [];
    }
  }, []);

  const startCamera = useCallback(async (deviceId?: string) => {
    if (streamRef.current) return;
    setIsLoading(true);

    try {
      const constraints: MediaStreamConstraints = {
        video: deviceId
          ? { deviceId: { exact: deviceId }, width: 640, height: 480 }
          : { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      const video = document.createElement('video');
      video.autoplay = true;
      video.playsInline = true;
      video.srcObject = stream;
      video.muted = true;
      await video.play();
      videoRef.current = video;

      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings();
      setCurrentResolution({
        width: settings.width || 640,
        height: settings.height || 480,
      });

      if (deviceId) setSelectedDeviceId(deviceId);
      setIsActive(true);
    } catch (e) {
      console.error('Camera start failed:', e);
      throw e;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current = null;
    }
    setIsActive(false);
    setCurrentResolution(null);
  }, []);

  const switchCamera = useCallback(async (deviceId: string) => {
    stopCamera();
    await startCamera(deviceId);
  }, [stopCamera, startCamera]);

  const toggleMirror = useCallback(() => {
    setMirror(prev => !prev);
  }, []);

  const captureBlob = useCallback(async (opts?: { maxWidth?: number; maxHeight?: number; quality?: number }): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return null;

    const canvas = document.createElement('canvas');
    let w = video.videoWidth || 640;
    let h = video.videoHeight || 480;

    if (opts?.maxWidth && w > opts.maxWidth) {
      h = Math.round(h * (opts.maxWidth / w));
      w = opts.maxWidth;
    }
    if (opts?.maxHeight && h > opts.maxHeight) {
      w = Math.round(w * (opts.maxHeight / h));
      h = opts.maxHeight;
    }

    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    if (mirror) {
      ctx.translate(w, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0, w, h);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', opts?.quality ?? 0.85);
    });
  }, [mirror]);

  return {
    isActive,
    isLoading,
    devices,
    selectedDeviceId,
    mirror,
    currentResolution,
    videoRef,
    startCamera,
    stopCamera,
    switchCamera,
    toggleMirror,
    enumerateCameras,
    captureBlob,
  };
}
