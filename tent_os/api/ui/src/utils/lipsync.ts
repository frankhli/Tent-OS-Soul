/**
 * 嘴唇同步工具 —— 通过音频振幅驱动Live2D模型嘴巴开合
 * 
 * 使用Web Audio API的AnalyserNode获取实时音量
 * 映射到Live2D参数 ParamMouthOpenY (值域 0-1)
 */

export interface LipSyncController {
  start: () => void;
  stop: () => void;
  getMouthOpen: () => number;
}

export function createLipSync(audioElement?: HTMLAudioElement): LipSyncController {
  let audioContext: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let source: MediaElementAudioSourceNode | null = null;
  let rafId: number = 0;
  let currentMouthOpen = 0;
  let running = false;

  function updateMouth() {
    if (!analyser || !running) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(dataArray);

    let maxSample = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const v = (dataArray[i] - 128) / 128;
      maxSample = Math.max(maxSample, Math.abs(v));
    }

    // 映射到 0-1，适当放大让口型更明显
    currentMouthOpen = Math.min(1, maxSample * 2.5);

    rafId = requestAnimationFrame(updateMouth);
  }

  return {
    start: () => {
      if (running) return;
      running = true;

      try {
        audioContext = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;

        if (audioElement) {
          source = audioContext.createMediaElementSource(audioElement);
          source.connect(analyser);
          analyser.connect(audioContext.destination);
        } else {
          // 如果没有指定audio元素，尝试获取麦克风输入（TTS场景）
          navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
            if (!audioContext || !analyser) return;
            const micSource = audioContext.createMediaStreamSource(stream);
            micSource.connect(analyser);
          }).catch(() => {
            // 麦克风获取失败静默处理
          });
        }

        updateMouth();
      } catch (e) {
        running = false;
      }
    },

    stop: () => {
      running = false;
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      if (source) {
        source.disconnect();
        source = null;
      }
      if (analyser) {
        analyser.disconnect();
        analyser = null;
      }
      if (audioContext) {
        audioContext.close();
        audioContext = null;
      }
      currentMouthOpen = 0;
    },

    getMouthOpen: () => currentMouthOpen,
  };
}

/**
 * 配合Web Speech API TTS的嘴唇同步
 */
export function startTtsLipSync(
  text: string,
  onMouthUpdate: (open: number) => void,
  onEnd?: () => void
): () => void {
  if (!window.speechSynthesis) {
    onEnd?.();
    return () => {};
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'zh-CN';
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  // 创建临时的audio元素用于lipsync分析
  // 注意：Web Speech API的输出无法直接通过AudioContext分析
  // 这里使用模拟的嘴唇动画：根据文本长度和时间估算
  const startTime = Date.now();
  const estimatedDuration = text.length * 250; // 每个字约250ms
  let rafId = 0;
  let stopped = false;

  function simulateMouth() {
    if (stopped) return;
    const elapsed = Date.now() - startTime;
    const progress = elapsed / estimatedDuration;

    if (progress >= 1) {
      onMouthUpdate(0);
      onEnd?.();
      return;
    }

    // 模拟嘴巴开合：用正弦波模拟说话节奏
    const open = Math.max(0, Math.sin(progress * Math.PI * 10) * 0.5 + 0.3);
    onMouthUpdate(open);
    rafId = requestAnimationFrame(simulateMouth);
  }

  utterance.onstart = () => {
    simulateMouth();
  };

  utterance.onend = () => {
    stopped = true;
    if (rafId) cancelAnimationFrame(rafId);
    onMouthUpdate(0);
    onEnd?.();
  };

  utterance.onerror = () => {
    stopped = true;
    if (rafId) cancelAnimationFrame(rafId);
    onMouthUpdate(0);
    onEnd?.();
  };

  window.speechSynthesis.speak(utterance);

  return () => {
    stopped = true;
    if (rafId) cancelAnimationFrame(rafId);
    window.speechSynthesis.cancel();
    onMouthUpdate(0);
  };
}
