import { useState, useRef, useCallback, useEffect } from 'react';

// Web Speech API types
declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: any) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export interface VoiceRecorderState {
  isRecording: boolean;
  recordingTime: number; // seconds
  transcript: string;
  interimTranscript: string;
  visualizerData: number[];
  error: string | null;
  audioBlob: Blob | null;
  supportsSpeechRecognition: boolean;
}

export function useVoiceRecorder() {
  const [state, setState] = useState<VoiceRecorderState>({
    isRecording: false,
    recordingTime: 0,
    transcript: '',
    interimTranscript: '',
    visualizerData: new Array(32).fill(0),
    error: null,
    audioBlob: null,
    supportsSpeechRecognition: false,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number>(0);
  const timerRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  // Detect speech recognition support on mount
  useEffect(() => {
    const supported = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    setState((s) => ({ ...s, supportsSpeechRecognition: supported }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecording();
    };
  }, []);

  const startRecording = useCallback(async () => {
    try {
      // Reset state
      setState((s) => ({
        ...s,
        isRecording: true,
        recordingTime: 0,
        transcript: '',
        interimTranscript: '',
        visualizerData: new Array(32).fill(0),
        error: null,
        audioBlob: null,
      }));
      audioChunksRef.current = [];

      // Get microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Set up Web Audio API for visualization
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      // Set up MediaRecorder for audio blob
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setState((s) => ({ ...s, audioBlob: blob }));
      };
      recorder.start(100); // Collect data every 100ms

      // Set up Speech Recognition
      const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognitionCtor) {
        const recognition = new SpeechRecognitionCtor();
        recognition.lang = 'zh-CN';
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
          let finalTranscript = '';
          let interimTranscript = '';
          for (let i = event.results.length - 1; i >= 0; i--) {
            const result = event.results[i];
            if (result.isFinal) {
              finalTranscript = result[0].transcript + finalTranscript;
            } else if (!interimTranscript) {
              interimTranscript = result[0].transcript;
            }
          }
          setState((s) => ({
            ...s,
            transcript: finalTranscript || s.transcript,
            interimTranscript: interimTranscript,
          }));
        };

        recognition.onerror = (event: any) => {
          if (event.error !== 'aborted' && event.error !== 'no-speech') {
            setState((s) => ({ ...s, error: `语音识别: ${event.error}` }));
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
      }

      // Start timer
      startTimeRef.current = Date.now();
      timerRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setState((s) => ({ ...s, recordingTime: elapsed }));
      }, 1000);

      // Start visualization loop
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateVisualizer = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        const normalized = Array.from(dataArray.slice(0, 32)).map((v) => v / 255);
        setState((s) => ({ ...s, visualizerData: normalized }));
        rafRef.current = requestAnimationFrame(updateVisualizer);
      };
      rafRef.current = requestAnimationFrame(updateVisualizer);
    } catch (err: any) {
      setState((s) => ({
        ...s,
        isRecording: false,
        error: `无法开始录制: ${err.message || '请检查麦克风权限'}`,
      }));
    }
  }, []);

  const stopRecording = useCallback(() => {
    // Stop recognition
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }

    // Stop media recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
    }
    mediaRecorderRef.current = null;

    // Stop stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    // Stop audio context
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }

    // Cancel animation frame
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }

    // Clear timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = 0;
    }

    setState((s) => ({
      ...s,
      isRecording: false,
      interimTranscript: '',
      visualizerData: new Array(32).fill(0),
    }));
  }, []);

  return {
    ...state,
    startRecording,
    stopRecording,
    stateRef,
  };
}
