import { useState, useRef, useCallback } from 'react';

interface SpeechRecognitionState {
  transcript: string;
  interimTranscript: string;
  isListening: boolean;
  error: string | null;
  supported: boolean;
}

/**
 * 浏览器原生语音识别（Web Speech API）
 * 
 * 用于通话模式：接通后自动监听，用户说完自动触发回调。
 * 不需要按住按钮，全程自然对话。
 */
export function useSpeechRecognition() {
  const [state, setState] = useState<SpeechRecognitionState>({
    transcript: '',
    interimTranscript: '',
    isListening: false,
    error: null,
    supported: typeof window !== 'undefined' && 
      !!(window as any).webkitSpeechRecognition || !!(window as any).SpeechRecognition,
  });

  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<number | null>(null);
  const onResultCallback = useRef<((text: string) => void) | null>(null);
  const transcriptBuffer = useRef('');

  const start = useCallback((onResult?: (text: string) => void) => {
    if (!state.supported) {
      setState(s => ({ ...s, error: '浏览器不支持语音识别，请使用 Chrome/Edge/Safari' }));
      return;
    }

    // 停止之前的
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    onResultCallback.current = onResult || null;
    transcriptBuffer.current = '';

    recognition.onstart = () => {
      setState(s => ({ ...s, isListening: true, error: null }));
    };

    recognition.onresult = (event: any) => {
      let finalPart = '';
      let interimPart = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalPart += t;
        } else {
          interimPart += t;
        }
      }

      if (finalPart) {
        transcriptBuffer.current += finalPart;
        setState(s => ({ ...s, transcript: transcriptBuffer.current }));

        // 检测到完整句子，启动沉默计时器（2秒后认为说完了）
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = window.setTimeout(() => {
          const fullText = transcriptBuffer.current.trim();
          if (fullText && onResultCallback.current) {
            onResultCallback.current(fullText);
          }
          transcriptBuffer.current = '';
          setState(s => ({ ...s, transcript: '', interimTranscript: '' }));
        }, 1800);
      }

      setState(s => ({ ...s, interimTranscript: interimPart }));
    };

    recognition.onerror = (event: any) => {
      if (event.error === 'no-speech') {
        // 没检测到语音，静默重启监听
        return;
      }
      if (event.error === 'aborted') {
        // 手动停止，不算错误
        return;
      }
      console.warn('[SpeechRecognition] error:', event.error);
      setState(s => ({ ...s, error: event.error }));
    };

    recognition.onend = () => {
      setState(s => ({ ...s, isListening: false }));
      // 如果还有未发送的内容，发送
      const fullText = transcriptBuffer.current.trim();
      if (fullText && onResultCallback.current) {
        onResultCallback.current(fullText);
        transcriptBuffer.current = '';
        setState(s => ({ ...s, transcript: '', interimTranscript: '' }));
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
  }, [state.supported]);

  const stop = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
      recognitionRef.current = null;
    }
    transcriptBuffer.current = '';
    setState(s => ({ ...s, isListening: false, transcript: '', interimTranscript: '', error: null }));
  }, []);

  return {
    ...state,
    start,
    stop,
  };
}
