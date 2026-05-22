import { useState, useCallback, useRef, useEffect } from 'react';
import { useAIState } from '@/contexts/AIStateContext';

// Web Speech API 类型声明
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: Event) => void) | null;
  start(): void;
  stop(): void;
}

// ===== 情感语音映射 =====
const EMOTION_VOICE_MAP: Record<string, { rate: number; pitch: number; pause: number }> = {
  happy:    { rate: 1.15, pitch: 1.1, pause: 50 },
  excited:  { rate: 1.25, pitch: 1.2, pause: 30 },
  calm:     { rate: 0.95, pitch: 0.95, pause: 80 },
  thinking: { rate: 1.0, pitch: 1.0, pause: 120 },
  surprised:{ rate: 1.1, pitch: 1.15, pause: 60 },
  sad:      { rate: 0.85, pitch: 0.9, pause: 100 },
  angry:    { rate: 1.05, pitch: 0.95, pause: 40 },
  listening:{ rate: 1.0, pitch: 1.0, pause: 70 },
  neutral:  { rate: 1.05, pitch: 1.0, pause: 60 },
};

/** 将文本分割为句子数组（支持中英文标点） */
function splitSentences(text: string): string[] {
  // 按句号、问号、感叹号、分号、换行分割，保留分隔符
  const matches = text.match(/[^。！？\n;]+[。！？\n;]?/g);
  if (!matches) return [text];
  return matches.map((s) => s.trim()).filter((s) => s.length > 0);
}

// 语音指令关键词映射
const VOICE_COMMANDS: Array<{ command: string; keywords: string[]; action: string }> = [
  { command: 'stop_speaking', keywords: ['停止朗读', '别读了', '安静', '闭嘴', '停下', '不要读了'], action: '停止朗读' },
  { command: 'clear_input', keywords: ['清除', '清空', '删掉', '删除', '重写'], action: '清空输入' },
  { command: 'send_message', keywords: ['发送', '提交', '确认', '好了'], action: '发送消息' },
  { command: 'new_session', keywords: ['新会话', '新建', '重新开始', '换一个新话题'], action: '新建会话' },
];

function detectVoiceCommand(text: string): string | null {
  const lowered = text.toLowerCase().replace(/[，。！？\s]/g, '');
  for (const cmd of VOICE_COMMANDS) {
    for (const kw of cmd.keywords) {
      if (lowered.includes(kw)) {
        return cmd.command;
      }
    }
  }
  return null;
}

export function useVoice() {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [voiceCommand, setVoiceCommand] = useState<string | null>(null);
  const [ttsEnabled, setTtsEnabled] = useState(() => {
    try {
      return localStorage.getItem('tent_os_tts') !== 'false';
    } catch {
      return true;
    }
  });
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const utteranceQueueRef = useRef<SpeechSynthesisUtterance[]>([]);
  const currentSegmentRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ttsAbortRef = useRef<AbortController | null>(null);
  const { state: aiState, sendWs, setSpeaking } = useAIState();

  const isSupported = typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);
  const isTtsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  useEffect(() => {
    if (typeof window !== 'undefined') {
      synthRef.current = window.speechSynthesis;
    }
  }, []);

  // 同步 isSpeaking 到全局状态
  useEffect(() => {
    setSpeaking(isSpeaking);
  }, [isSpeaking, setSpeaking]);

  const startListening = useCallback(() => {
    if (!isSupported) return;

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = 'zh-CN';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const results = event.results;
      // 累加所有结果段，支持长句和停顿后继续说
      let fullText = '';
      for (let i = 0; i < results.length; i++) {
        fullText += results[i][0].transcript;
      }
      setTranscript(fullText);
      // C1: 实时检测语音指令
      const cmd = detectVoiceCommand(fullText);
      if (cmd) {
        setVoiceCommand(cmd);
      }
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    setTranscript('');
    setIsListening(true);
    recognition.start();
  }, [isSupported]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsListening(false);
  }, []);

  const clearVoiceCommand = useCallback(() => {
    setVoiceCommand(null);
  }, []);

  /** 根据当前 AI 情绪获取语音参数 */
  const getVoiceParams = useCallback((emotion?: string) => {
    const e = emotion || aiState.emotion || 'neutral';
    return EMOTION_VOICE_MAP[e] || EMOTION_VOICE_MAP.neutral;
  }, [aiState.emotion]);

  /** 使用后端情感 TTS API 合成语音 */
  const speakWithBackendTts = useCallback(async (
    text: string,
    emotion?: string,
    callbacks?: {
      onStart?: () => void;
      onEnd?: () => void;
      onSegmentStart?: (segment: string, index: number) => void;
    }
  ) => {
    // 清理 markdown 符号
    const cleanText = text
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/#/g, '')
      .replace(/`/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
      .slice(0, 4000);

    if (!cleanText.trim()) {
      callbacks?.onEnd?.();
      return false;
    }

    try {
      ttsAbortRef.current = new AbortController();
      const resp = await fetch('/ui/api/tts/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cleanText, emotion: emotion || aiState.emotion || 'neutral' }),
        signal: ttsAbortRef.current.signal,
      });

      if (!resp.ok) {
        throw new Error(`TTS API 错误: ${resp.status}`);
      }

      const data = await resp.json();
      if (!data.audio_base64) {
        throw new Error('TTS API 未返回音频数据');
      }

      // 停止之前的音频
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }

      // 创建音频对象并播放
      const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
      audioRef.current = audio;

      // 句子级口型同步（用定时器模拟）
      const sentences = splitSentences(cleanText);
      const segmentTimers: number[] = [];

      audio.onplay = () => {
        setIsSpeaking(true);
        callbacks?.onStart?.();
        // 估算每句话的时长，发送口型同步事件
        const estimatedDuration = audio.duration || cleanText.length * 0.25;
        const segmentDuration = estimatedDuration / Math.max(sentences.length, 1);
        sentences.forEach((sentence, idx) => {
          const timer = window.setTimeout(() => {
            callbacks?.onSegmentStart?.(sentence, idx);
            if (sendWs) {
              sendWs('ai.speech.segment', { sentence, index: idx, total: sentences.length });
            }
          }, idx * segmentDuration * 1000);
          segmentTimers.push(timer);
        });
      };

      audio.onended = () => {
        segmentTimers.forEach((t) => clearTimeout(t));
        setIsSpeaking(false);
        callbacks?.onEnd?.();
        audioRef.current = null;
      };

      audio.onerror = () => {
        segmentTimers.forEach((t) => clearTimeout(t));
        setIsSpeaking(false);
        callbacks?.onEnd?.();
        audioRef.current = null;
      };

      await audio.play();
      return true;
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setIsSpeaking(false);
        callbacks?.onEnd?.();
        return true;
      }
      console.warn('后端 TTS 失败，回退到浏览器 TTS:', err);
      return false;
    }
  }, [aiState.emotion, sendWs]);

  /** 使用浏览器原生 Web Speech API 朗读（回退方案） */
  const speakWithBrowserTts = useCallback((
    text: string,
    callbacks?: {
      onStart?: () => void;
      onEnd?: () => void;
      onSegmentStart?: (segment: string, index: number) => void;
      emotion?: string;
    }
  ) => {
    if (!isTtsSupported || !synthRef.current) {
      callbacks?.onEnd?.();
      return;
    }

    // 取消之前的朗读
    synthRef.current.cancel();
    utteranceQueueRef.current = [];
    currentSegmentRef.current = 0;

    // 清理 markdown 符号
    const cleanText = text
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/#/g, '')
      .replace(/`/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
      .slice(0, 2000);

    if (!cleanText.trim()) {
      callbacks?.onEnd?.();
      return;
    }

    if (!ttsEnabled) {
      callbacks?.onEnd?.();
      return;
    }

    const params = getVoiceParams(callbacks?.emotion);
    const sentences = splitSentences(cleanText);

    if (sentences.length === 0) {
      callbacks?.onEnd?.();
      return;
    }

    setIsSpeaking(true);
    callbacks?.onStart?.();

    let completedCount = 0;
    const total = sentences.length;

    const speakNext = (idx: number) => {
      if (idx >= total) {
        setIsSpeaking(false);
        callbacks?.onEnd?.();
        return;
      }

      currentSegmentRef.current = idx;
      const sentence = sentences[idx];
      callbacks?.onSegmentStart?.(sentence, idx);
      if (sendWs) {
        sendWs('ai.speech.segment', { sentence, index: idx, total });
      }

      const utterance = new SpeechSynthesisUtterance(sentence);
      utterance.lang = 'zh-CN';
      utterance.rate = params.rate;
      utterance.pitch = params.pitch;

      const voices = synthRef.current?.getVoices() || [];
      const zhVoice = voices.find((v) => v.lang.startsWith('zh'));
      if (zhVoice) {
        utterance.voice = zhVoice;
      }

      utterance.onend = () => {
        completedCount++;
        if (completedCount >= total) {
          setIsSpeaking(false);
          callbacks?.onEnd?.();
        } else {
          setTimeout(() => speakNext(idx + 1), params.pause);
        }
      };

      utterance.onerror = (e) => {
        if ((e as any).error === 'canceled') return;
        completedCount++;
        if (completedCount >= total) {
          setIsSpeaking(false);
          callbacks?.onEnd?.();
        } else {
          speakNext(idx + 1);
        }
      };

      utteranceQueueRef.current.push(utterance);
      synthRef.current?.speak(utterance);
    };

    speakNext(0);
  }, [isTtsSupported, ttsEnabled, getVoiceParams, sendWs]);

  const speak = useCallback(async (
    text: string,
    callbacks?: {
      onStart?: () => void;
      onEnd?: () => void;
      onSegmentStart?: (segment: string, index: number) => void;
      emotion?: string;
    }
  ) => {
    if (!ttsEnabled) {
      callbacks?.onEnd?.();
      return;
    }

    // 优先使用后端情感 TTS（OpenAI / Edge）
    const ok = await speakWithBackendTts(text, callbacks?.emotion, callbacks);
    if (!ok) {
      // 回退到浏览器原生 TTS
      speakWithBrowserTts(text, callbacks);
    }
  }, [ttsEnabled, speakWithBackendTts, speakWithBrowserTts]);

  const stopSpeaking = useCallback(() => {
    // 停止后端 TTS 音频
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    // 中止正在进行的 TTS 请求
    if (ttsAbortRef.current) {
      ttsAbortRef.current.abort();
      ttsAbortRef.current = null;
    }
    // 停止浏览器原生 TTS
    if (synthRef.current) {
      synthRef.current.cancel();
    }
    utteranceQueueRef.current = [];
    setIsSpeaking(false);
  }, []);

  const toggleTts = useCallback(() => {
    setTtsEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('tent_os_tts', String(next));
      } catch {}

      // 通知后端 TTS 状态变化
      if (sendWs) {
        try {
          sendWs('tts.status', { enabled: next, timestamp: Date.now() });
        } catch {
          // ignore
        }
      }

      return next;
    });
    if (synthRef.current) {
      synthRef.current.cancel();
    }
    setIsSpeaking(false);
  }, [sendWs]);

  // 组件卸载时取消朗读
  useEffect(() => {
    return () => {
      if (synthRef.current) {
        synthRef.current.cancel();
      }
    };
  }, []);

  return {
    isListening,
    transcript,
    voiceCommand,
    clearVoiceCommand,
    ttsEnabled,
    isSpeaking,
    isSupported,
    isTtsSupported,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    toggleTts,
  };
}
