import { useState, useRef, useEffect, useCallback } from 'react';
import { PhoneOff, Mic } from 'lucide-react';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import * as api from '../api/soulApi';

interface Props {
 onSendVoice: (text: string) => void;
 onExit: () => void;
 aiLoading: boolean;
 lastAiReply: string | null;
 onPlayTTS: (text: string) => void;
}

type CallState = 'idle' | 'listening' | 'thinking' | 'speaking';

export default function VoiceCallPanel({ onSendVoice, onExit, aiLoading, lastAiReply, onPlayTTS }: Props) {
 const [callState, setCallState] = useState<CallState>('idle');
 const voiceRecorder = useVoiceRecorder();
 const micPressTimerRef = useRef<number | null>(null);
 const isLongPressRef = useRef(false);
 const hasPlayedRef = useRef(false);

 // Auto-play TTS when AI reply arrives
 useEffect(() => {
 if (lastAiReply && callState === 'thinking' && !hasPlayedRef.current) {
 hasPlayedRef.current = true;
 setCallState('speaking');
 onPlayTTS(lastAiReply);
 }
 }, [lastAiReply, callState, onPlayTTS]);

 // Reset state when AI finishes loading
 useEffect(() => {
 if (!aiLoading && callState === 'thinking') {
 // Will be handled by lastAiReply effect
 }
 if (!aiLoading && callState === 'speaking') {
 // After speaking, reset to idle after a delay
 const timer = setTimeout(() => {
 setCallState('idle');
 hasPlayedRef.current = false;
 }, 1500);
 return () => clearTimeout(timer);
 }
 }, [aiLoading, callState]);

 const handlePointerDown = useCallback(() => {
 if (callState !== 'idle') return;
 micPressTimerRef.current = window.setTimeout(() => {
 isLongPressRef.current = true;
 voiceRecorder.startRecording();
 setCallState('listening');
 }, 300);
 }, [callState, voiceRecorder]);

 const handlePointerUp = useCallback(async () => {
 if (micPressTimerRef.current) clearTimeout(micPressTimerRef.current);
 if (!isLongPressRef.current) return;
 isLongPressRef.current = false;
 voiceRecorder.stopRecording();

 setTimeout(async () => {
 const latest = voiceRecorder.stateRef.current;
 const browserText = latest.transcript || latest.interimTranscript;
 const blob = latest.audioBlob;

 let finalText = browserText;
 if (blob && blob.size > 1000) {
 try {
 const asrRes = await api.transcribeAudio(blob, `call_${Date.now()}.webm`);
 if (asrRes.text && asrRes.text.trim() && !asrRes.fallback) {
 finalText = asrRes.text.trim();
 }
 } catch (e) {}
 }

 if (finalText && finalText.trim()) {
 setCallState('thinking');
 hasPlayedRef.current = false;
 onSendVoice(finalText.trim());
 } else {
 setCallState('idle');
 }
 }, 200);
 }, [voiceRecorder, onSendVoice]);

 const statusText = {
 idle: '按住说话',
 listening: '聆听中...',
 thinking: '思考中...',
 speaking: '说话中...',
 }[callState];

 const statusColor = {
 idle: 'bg-slate-700',
 listening: 'bg-red-500',
 thinking: 'bg-amber-500',
 speaking: 'bg-emerald-500',
 }[callState];

 return (
 <div className="flex flex-col items-center justify-center h-full gap-8 py-8">
 {/* Status */}
 <div className="text-center">
 <div className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm text-white ${statusColor} transition-colors duration-300`}>
 {callState === 'listening' && (
 <span className="relative flex h-2 w-2">
 <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-surface-elevated opacity-75" />
 <span className="relative inline-flex rounded-full h-2 w-2 bg-surface-elevated" />
 </span>
 )}
 {statusText}
 </div>
 </div>

 {/* Waveform */}
 <div className="h-16 flex items-center justify-center gap-0.5">
 {callState === 'listening' ? (
 voiceRecorder.visualizerData.slice(0, 32).map((v, i) => (
 <div
 key={i}
 className="w-1 bg-accent-subtle rounded-full transition-all duration-75"
 style={{ height: `${Math.max(4, v * 40)}px` }}
 />
 ))
 ) : callState === 'thinking' ? (
 <div className="flex gap-1">
 {[0, 150, 300].map((delay) => (
 <span key={delay} className="w-2.5 h-2.5 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: `${delay}ms` }} />
 ))}
 </div>
 ) : callState === 'speaking' ? (
 <div className="flex gap-1">
 {[0, 150, 300, 450].map((delay) => (
 <span key={delay} className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" style={{ animationDelay: `${delay}ms` }} />
 ))}
 </div>
 ) : (
 <div className="text-content-muted text-sm">等待中...</div>
 )}
 </div>

 {/* Big Mic Button */}
 <button
 onPointerDown={handlePointerDown}
 onPointerUp={handlePointerUp}
 onPointerLeave={() => {
 if (micPressTimerRef.current) clearTimeout(micPressTimerRef.current);
 if (isLongPressRef.current) {
 isLongPressRef.current = false;
 voiceRecorder.stopRecording();
 setCallState('idle');
 }
 }}
 disabled={callState === 'thinking' || callState === 'speaking'}
 className={`w-24 h-24 rounded-full flex items-center justify-center transition-all shadow-lg ${
 callState === 'listening'
 ? 'bg-red-500/100 scale-110 shadow-red-500/30'
 : callState === 'thinking'
 ? 'bg-amber-500/100 shadow-amber-500/30'
 : callState === 'speaking'
 ? 'bg-emerald-500/100 shadow-emerald-500/30'
 : 'bg-violet-600 hover:bg-violet-700 hover:scale-105 shadow-violet-500/30'
 }`}
 >
 <Mic className="w-10 h-10 text-white" />
 </button>

 {/* Exit */}
 <button
 onClick={onExit}
 className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-surface-panel hover:bg-surface-overlay text-content-muted hover:text-content-primary transition text-sm"
 >
 <PhoneOff className="w-4 h-4" />
 结束通话
 </button>
 </div>
 );
}
