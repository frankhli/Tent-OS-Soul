import { useRef, useCallback, useEffect } from 'react';
import { useAIState } from '@/contexts/AIStateContext';

export function useVoiceProsody() {
  const { sendWs } = useAIState();
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number>(0);
  const historyRef = useRef<number[]>([]); // 能量历史
  const lastSendRef = useRef(0);
  const isActiveRef = useRef(false);

  const start = useCallback(async () => {
    if (isActiveRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
          sampleRate: 16000,
        },
      });
      streamRef.current = stream;

      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      isActiveRef.current = true;
      historyRef.current = [];

      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      const timeArray = new Uint8Array(bufferLength);

      const analyze = () => {
        if (!isActiveRef.current) return;

        analyser.getByteFrequencyData(dataArray);
        analyser.getByteTimeDomainData(timeArray);

        // 1. 计算整体能量（音量）
        let energy = 0;
        for (let i = 0; i < bufferLength; i++) {
          energy += dataArray[i];
        }
        energy = energy / bufferLength / 255;

        // 2. 音调变化（频谱重心偏移）
        let weightedSum = 0;
        let total = 0;
        for (let i = 0; i < bufferLength; i++) {
          weightedSum += dataArray[i] * i;
          total += dataArray[i];
        }
        const centroid = total > 0 ? weightedSum / total : 0;
        const normalizedCentroid = centroid / bufferLength;

        // 3. 音量变化（时域标准差）
        let sum = 0;
        let sumSq = 0;
        for (let i = 0; i < bufferLength; i++) {
          const v = (timeArray[i] - 128) / 128;
          sum += v;
          sumSq += v * v;
        }
        const mean = sum / bufferLength;
        const variance = sumSq / bufferLength - mean * mean;
        const volumeVar = Math.min(1.0, Math.sqrt(Math.max(0, variance)) * 4);

        // 存储能量历史用于计算语速
        historyRef.current.push(energy);
        if (historyRef.current.length > 100) {
          historyRef.current.shift();
        }

        // 4. 语速估算（通过检测语音活动段）
        let speechRate = 1.0;
        if (historyRef.current.length >= 50) {
          const recent = historyRef.current.slice(-50);
          const threshold = 0.05;
          let activeFrames = 0;
          for (const e of recent) {
            if (e > threshold) activeFrames++;
          }
          // activeFrames / 50 ≈ 语音活动比例
          // 正常语速 ≈ 0.3-0.5 的活动比例
          const ratio = activeFrames / 50;
          speechRate = Math.max(0.5, Math.min(2.0, ratio * 2.5));
        }

        // 计算音调变化（最近 10 帧的 centroid 标准差）
        // 简化：用当前帧和平均值的差异
        const pitchVar = Math.min(1.0, normalizedCentroid * 2);

        // 每 2 秒发送一次
        const now = Date.now();
        if (now - lastSendRef.current > 2000 && sendWs) {
          lastSendRef.current = now;
          try {
            sendWs('voice.prosody', {
              user_id: 'web_user',
              prosody: {
                pitch_variation: Math.round(pitchVar * 100) / 100,
                speech_rate: Math.round(speechRate * 100) / 100,
                volume_variation: Math.round(volumeVar * 100) / 100,
                energy: Math.round(energy * 100) / 100,
              },
              timestamp: now,
            });
          } catch {
            // ignore
          }
        }

        // 节流到 ~10fps，语音韵律不需要帧率精度
        rafRef.current = window.setTimeout(analyze, 100);
      };

      rafRef.current = window.setTimeout(analyze, 100);
    } catch {
      // 用户拒绝麦克风权限或设备不支持
    }
  }, [sendWs]);

  const stop = useCallback(() => {
    isActiveRef.current = false;
    if (rafRef.current) {
      clearTimeout(rafRef.current);
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    audioCtxRef.current = null;
    analyserRef.current = null;
    streamRef.current = null;
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return { start, stop };
}
