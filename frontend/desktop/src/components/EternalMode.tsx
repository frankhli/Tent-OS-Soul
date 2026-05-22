import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Phone, PhoneOff, Video, VideoOff, ChevronLeft, MoreHorizontal,
  Mic, Keyboard, Send, Play, Pause, Volume2, VolumeX, SmilePlus,
  Flame, Sparkles, Heart, Pin, Users, MessageCircle, BookOpen,
  AlertTriangle, Shield, Check, CheckCheck, RotateCcw,
} from 'lucide-react';
import RelationGalaxy from './RelationGalaxy';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { VideoAvatar } from './VideoAvatar';

interface Props {
  userId: string;
  heirName: string;
  token: string;
  onExit: () => void;
}

interface Msg {
  id: string;
  role: 'heir' | 'soul' | 'system';
  content: string;
  emotion?: string;
  timestamp: number;
  isVoice?: boolean;
  audioDuration?: number;
  showTranscript?: boolean;
  sending?: boolean;
  sent?: boolean;
  failed?: boolean;
}

interface MemoryItem {
  id: string;
  title: string;
  summary: string;
  memory_type: string;
  created_at: string;
}

type CallType = 'none' | 'voice' | 'video';
type CallState = 'idle' | 'calling' | 'ringing' | 'connected' | 'ended';

/* ── 时间分割线 ── */
function formatTimeDivider(ts: number, prevTs?: number): string | null {
  if (prevTs && ts - prevTs < 5 * 60 * 1000) return null;
  const now = Date.now();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const msgDay = new Date(ts);
  msgDay.setHours(0, 0, 0, 0);
  const daysDiff = Math.floor((today.getTime() - msgDay.getTime()) / (24 * 60 * 60 * 1000));
  const hm = new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (daysDiff === 0) return hm;
  if (daysDiff === 1) return `昨天 ${hm}`;
  if (daysDiff === 2) return `前天 ${hm}`;
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  if (daysDiff < 7) return `${weekdays[new Date(ts).getDay()]} ${hm}`;
  return `${new Date(ts).getMonth() + 1}月${new Date(ts).getDate()}日 ${hm}`;
}

/* ── 按句子拆分文本（用于分段TTS） ── */
function splitIntoSentences(text: string): string[] {
  // 按标点分割，保留标点
  const matches = text.match(/[^。！？\n]+[。！？\n]+|[^。！？\n]+$/g);
  if (!matches) return [text];
  return matches.map((s) => s.trim()).filter(Boolean);
}

/* ── 通话覆盖层组件 ── */
function CallOverlay({
  callType, callState, callDuration, userName, avatarUrl, heirColor, heirName,
  isSpeaking, speechText,
  onHangup, onAnswer,
}: {
  callType: CallType; callState: CallState; callDuration: number;
  userName: string; avatarUrl: string; heirColor: string; heirName: string;
  isSpeaking: boolean;
  speechText: string;
  onHangup: () => void; onAnswer: () => void;
}) {
  const mins = Math.floor(callDuration / 60).toString().padStart(2, '0');
  const secs = (callDuration % 60).toString().padStart(2, '0');
  const heirVideoRef = useRef<HTMLVideoElement>(null);

  // 视频模式：获取继承者摄像头
  useEffect(() => {
    if (callType === 'video' && callState === 'connected') {
      navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then((stream) => {
          if (heirVideoRef.current) {
            heirVideoRef.current.srcObject = stream;
            heirVideoRef.current.play();
          }
        })
        .catch((err) => {
          console.warn('[Camera] 无法获取摄像头:', err);
        });
    }
    return () => {
      if (heirVideoRef.current && heirVideoRef.current.srcObject) {
        const stream = heirVideoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
        heirVideoRef.current.srcObject = null;
      }
    };
  }, [callType, callState]);

  // Calling 状态：显示"正在呼叫"
  if (callState === 'calling') {
    return (
      <div className="fixed inset-0 bg-[#111] z-50 flex flex-col items-center text-white animate-in fade-in duration-300">
        <div className="mt-20 text-lg font-medium">{userName}</div>
        <div className="text-sm text-white/50 mt-1">正在呼叫…</div>
        <div className="flex-1 flex items-center justify-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-full border-2 border-white/20 animate-ping" />
            <div className="absolute inset-0 rounded-full border-2 border-white/10 animate-ping" style={{ animationDelay: '0.5s' }} />
            <div className="w-28 h-28 rounded-full overflow-hidden border-2 border-white/20 bg-gray-700">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-3xl text-white/40">{userName.charAt(0)}</div>
              )}
            </div>
          </div>
        </div>
        <div className="mb-16 flex gap-12">
          <div className="flex flex-col items-center gap-2">
            <button className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center">
              <Mic className="w-5 h-5 text-white" />
            </button>
            <span className="text-[10px] text-white/40">静音</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <button onClick={onHangup} className="w-16 h-16 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition shadow-lg">
              <PhoneOff className="w-7 h-7 text-white" />
            </button>
            <span className="text-[10px] text-white/40">挂断</span>
          </div>
        </div>
      </div>
    );
  }

  // Ringing 状态：显示"对方邀请你语音通话"
  if (callState === 'ringing') {
    return (
      <div className="fixed inset-0 bg-[#111] z-50 flex flex-col items-center text-white animate-in fade-in duration-300">
        <div className="mt-16 text-sm text-white/50">{userName} 邀请你{callType === 'video' ? '视频' : '语音'}通话</div>
        <div className="flex-1 flex items-center justify-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-full border-2 border-[#07c160]/30 animate-ping" />
            <div className="w-28 h-28 rounded-full overflow-hidden border-2 border-white/20 bg-gray-700">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-3xl text-white/40">{userName.charAt(0)}</div>
              )}
            </div>
          </div>
        </div>
        <div className="mb-16 flex gap-16">
          <div className="flex flex-col items-center gap-2">
            <button onClick={onHangup} className="w-14 h-14 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition shadow-lg">
              <PhoneOff className="w-6 h-6 text-white" />
            </button>
            <span className="text-[10px] text-white/40">挂断</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <button onClick={onAnswer} className="w-14 h-14 bg-[#07c160] hover:bg-[#06ad56] rounded-full flex items-center justify-center transition shadow-lg">
              <Phone className="w-6 h-6 text-white" />
            </button>
            <span className="text-[10px] text-white/40">接听</span>
          </div>
        </div>
      </div>
    );
  }

  // Connected 状态：通话中
  return (
    <div className="fixed inset-0 bg-[#111] z-50 flex flex-col items-center text-white animate-in fade-in duration-300">
      <div className="mt-12 text-lg font-medium">{userName}</div>
      <div className="text-sm text-white/50 mt-1">
        {speechText ? (
          <span className="text-[#07c160]">{speechText}</span>
        ) : isSpeaking ? (
          '对方正在说话…'
        ) : (
          `${mins}:${secs}`
        )}
      </div>

      {/* 视频通话时显示视频区域 */}
      {callType === 'video' ? (
        <div className="flex-1 w-full flex items-center justify-center relative bg-gradient-to-b from-gray-900 to-black mt-4">
          <div className="text-center">
            <div className="mx-auto mb-4">
              <VideoAvatar
                imageUrl={avatarUrl || ''}
                isSpeaking={isSpeaking}
                size={280}
              />
            </div>
            <p className="text-sm text-white/40">面对面模式</p>
          </div>
          {/* 小窗口：继承者的摄像头画面 */}
          <div className="absolute top-4 right-4 w-28 h-36 rounded-lg overflow-hidden border border-white/10 bg-gray-800">
            <video
              ref={heirVideoRef}
              className="w-full h-full object-cover"
              muted
              playsInline
            />
            {!heirVideoRef.current?.srcObject && (
              <div className="absolute inset-0 flex items-center justify-center text-white/30 text-xs" style={{ backgroundColor: heirColor }}>
                {heirName.charAt(0)}
              </div>
            )}
            <div className="absolute bottom-1 left-1 text-[10px] text-white/60 bg-black/30 px-1 rounded">{heirName}</div>
          </div>
        </div>
      ) : (
        /* 连续语音模式：大头像 */
        <div className="flex-1 flex items-center justify-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-full border-2 border-white/10 animate-pulse" />
            <div className="w-28 h-28 rounded-full overflow-hidden border-2 border-white/20 bg-gray-700">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-3xl text-white/40">{userName.charAt(0)}</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 底部控制栏 */}
      <div className="w-full p-6 flex items-center justify-center gap-8 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex flex-col items-center gap-1">
          <button className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition">
            <Mic className="w-5 h-5 text-white" />
          </button>
          <span className="text-[10px] text-white/40">静音</span>
        </div>
        {callType === 'video' && (
          <div className="flex flex-col items-center gap-1">
            <button className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition">
              <VideoOff className="w-5 h-5 text-white" />
            </button>
            <span className="text-[10px] text-white/40">摄像头</span>
          </div>
        )}
        <div className="flex flex-col items-center gap-1">
          <button onClick={onHangup} className="w-16 h-16 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition shadow-lg">
            <PhoneOff className="w-7 h-7 text-white" />
          </button>
          <span className="text-[10px] text-white/40">挂断</span>
        </div>
      </div>
    </div>
  );
}

export default function EternalMode({ userId, heirName, token, onExit }: Props) {
  const mountedRef = useRef(true);
  useEffect(() => { return () => { mountedRef.current = false; }; }, []);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'memories' | 'relations' | 'profile' | 'health'>('memories');
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [photos, setPhotos] = useState<string[]>([]);
  const [showSidebar, setShowSidebar] = useState(false);
  const [hasEntered, setHasEntered] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const [guardianAlert, setGuardianAlert] = useState<any>(null);
  const [healthReport, setHealthReport] = useState<any>(null);
  const [showIdentityNotice, setShowIdentityNotice] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [playingMsgId, setPlayingMsgId] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const voiceRecorder = useVoiceRecorder();
  const micPressTimerRef = useRef<number | null>(null);
  const isLongPressRef = useRef(false);

  // 通话状态
  const [callType, setCallType] = useState<CallType>('none');
  const [callState, setCallState] = useState<CallState>('idle');
  const [callDuration, setCallDuration] = useState(0);
  const [callStatusText, setCallStatusText] = useState('');
  const callTimerRef = useRef<number | null>(null);
  const speech = useSpeechRecognition();

  const userName = status?.user_name || profile?.user_name || userId;
  const soulAvatar = photos.length > 0
    ? (photos[0].startsWith('/') ? photos[0] : `/photos/${userId}/${photos[0].split('/').pop()}`)
    : '';

  // 继承人头像颜色
  const heirColor = useMemo(() => {
    const colors = ['#07c160', '#576b95', '#e6a23c', '#e64340', '#10aeff', '#aa7ee2'];
    let hash = 0;
    for (let i = 0; i < heirName.length; i++) hash = heirName.charCodeAt(i) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
  }, [heirName]);

  // 通话计时器
  useEffect(() => {
    if (callState === 'connected') {
      callTimerRef.current = window.setInterval(() => setCallDuration((d) => d + 1), 1000);
    } else {
      if (callTimerRef.current) clearInterval(callTimerRef.current);
      if (callState === 'idle') setCallDuration(0);
    }
    return () => { if (callTimerRef.current) clearInterval(callTimerRef.current); };
  }, [callState]);

  // 自动从 calling → ringing → connected（模拟对方接听）
  useEffect(() => {
    if (callState === 'calling') {
      setCallStatusText('正在呼叫…');
      const t1 = setTimeout(() => setCallState('ringing'), 2000);
      return () => clearTimeout(t1);
    }
    if (callState === 'ringing') {
      setCallStatusText('对方邀请你通话');
      const t2 = setTimeout(() => setCallState('connected'), 3000);
      return () => clearTimeout(t2);
    }
    if (callState === 'connected') {
      setCallStatusText('');
      // 自动开始语音识别：用户直接说话，无需按键
      if (speech.supported) {
        speech.start((text) => {
          // 识别到用户说完一段话，自动发送
          setInput(text);
          setTimeout(() => handleSendRef.current(), 100);
        });
      }
    }
    if (callState === 'idle' || callState === 'ended') {
      speech.stop();
      setCallStatusText('');
    }
  }, [callState]);

  useEffect(() => {
    loadMemories(); loadProfile(); loadPhotos(); loadStatus(); loadHealth();
  }, [userId]);

  useEffect(() => {
    if (hasEntered) {
      const t = setTimeout(() => setShowIdentityNotice(true), 2000);
      return () => clearTimeout(t);
    }
  }, [hasEntered]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadMemories = async () => {
    try {
      const res = await fetch(`/api/v1/soul/eternal/memories/${userId}?limit=20`);
      if (res.ok) { const data = await res.json(); if (mountedRef.current) setMemories(data.items || []); }
    } catch {}
  };
  const loadProfile = async () => {
    try {
      const res = await fetch(`/api/v1/soul/profile/${userId}`);
      if (res.ok) { const data = await res.json(); if (mountedRef.current) setProfile(data); }
    } catch {}
  };
  const loadPhotos = async () => {
    try {
      const res = await fetch(`/api/v1/soul/appearance/${userId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.profile?.photos && mountedRef.current) {
          setPhotos(data.profile.photos.map((p: string) => p.replace(/^\.\/tent_memory\//, '/')));
        }
      }
    } catch {}
  };
  const loadStatus = async () => {
    try {
      const res = await fetch(`/api/v1/soul/eternal/status/${userId}`);
      if (res.ok) { const data = await res.json(); if (mountedRef.current) setStatus(data); }
    } catch {}
  };
  const loadHealth = async () => {
    try {
      const res = await fetch(`/api/v1/soul/guardian/${userId}/health?heir_id=${encodeURIComponent(token)}`);
      if (res.ok) { const data = await res.json(); if (data.report && mountedRef.current) setHealthReport(data.report); }
    } catch {}
  };

  // 分段TTS播放：把长回复拆成句子，逐句合成逐句播放

  const playSegmentedTTS = useCallback(async (msgId: string, text: string, emotion?: string) => {
    const sentences = splitIntoSentences(text);
    if (sentences.length === 0) return;

    // 如果是单句，直接用原来的方式
    if (sentences.length === 1) {
      playSingleTTS(msgId, text, emotion);
      return;
    }

    // 多句：逐句预加载后连续播放
    setPlayingMsgId(msgId);
    const emotionParam = emotion || 'neutral';
    const audioUrls: string[] = [];

    // 并行预加载所有句子的音频
    await Promise.all(sentences.map(async (sentence, idx) => {
      try {
        const url = `/api/v1/soul/tts/${userId}?text=${encodeURIComponent(sentence)}&emotion=${encodeURIComponent(emotionParam)}&stream=true`;
        audioUrls[idx] = url;
      } catch {
        audioUrls[idx] = '';
      }
    }));

    // 顺序播放
    for (let i = 0; i < sentences.length; i++) {
      if (!audioUrls[i]) continue;
      const audio = new Audio(audioUrls[i]);
      audioRef.current = audio;

      await new Promise<void>((resolve) => {
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
        audio.play().catch(() => resolve());
      });

      // 播放完一句后检查是否被手动停止
      if (playingMsgId !== msgId) break;
    }

    setPlayingMsgId(null);
    audioRef.current = null;
  }, [userId, playingMsgId]);

  const playSingleTTS = (msgId: string, text: string, emotion?: string) => {
    if (playingMsgId === msgId) {
      audioRef.current?.pause();
      setPlayingMsgId(null);
      return;
    }
    const emotionParam = emotion || 'neutral';
    const url = `/api/v1/soul/tts/${userId}?text=${encodeURIComponent(text)}&emotion=${encodeURIComponent(emotionParam)}&stream=true`;
    const audio = new Audio(url);
    audioRef.current = audio;
    setPlayingMsgId(msgId);
    const stop = () => { setPlayingMsgId(null); audioRef.current = null; };
    audio.onended = stop;
    audio.onerror = stop;
    audio.play().catch((err) => { console.warn('[TTS] 播放失败:', err); stop(); });
  };

  const playTTS = (msgId: string, text: string, emotion?: string) => {
    if (callState === 'connected') {
      // 通话中自动分段播放
      playSegmentedTTS(msgId, text, emotion);
    } else {
      playSingleTTS(msgId, text, emotion);
    }
  };

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    const heirMsgId = `h_${Date.now()}`;
    setMessages((prev) => [...prev, {
      id: heirMsgId, role: 'heir', content: text, timestamp: Date.now(), sending: true,
    }]);
    setLoading(true);

    try {
      const history = messages.slice(-6).map((m) => ({
        role: m.role === 'heir' ? 'user' : 'assistant',
        content: m.content,
      }));
      const res = await fetch(`/api/v1/soul/eternal/chat/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history, heir_id: token }),
      });
      const data = await res.json();
      const soulMsgId = `s_${Date.now()}`;
      const replyText = data.reply || '……（沉默）';
      const replyEmotion = data.reply_emotion || 'neutral';

      if (data.guardian_alert) setGuardianAlert(data.guardian_alert);
      const isGuardianMessage = data.is_guardian_message;

      setMessages((prev) => prev.map((m) => m.id === heirMsgId ? { ...m, sending: false, sent: true } : m));
      setMessages((prev) => [...prev, {
        id: soulMsgId,
        role: 'soul',
        content: replyText,
        emotion: replyEmotion,
        timestamp: Date.now(),
        isVoice: data.is_voice !== false,
        audioDuration: data.audio_duration || Math.max(1, Math.ceil(replyText.length / 4)),
      }]);

      // 自动播放：聊天模式延迟400ms，通话模式立即播放
      if (!isGuardianMessage && replyText && replyText !== '……（沉默）') {
        const delay = callState === 'connected' ? 100 : 400;
        setTimeout(() => playTTS(soulMsgId, replyText, replyEmotion), delay);
      }
      loadHealth();
    } catch {
      setMessages((prev) => prev.map((m) => m.id === heirMsgId ? { ...m, sending: false, failed: true } : m));
      setMessages((prev) => [...prev, {
        id: `s_${Date.now()}`, role: 'soul', content: '……我在这里，请再说一次。',
        timestamp: Date.now(), isVoice: true, audioDuration: 3,
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, userId, token, callState, playSegmentedTTS]);

  // ref for handleSend to avoid closure issues in speech recognition callback
  const handleSendRef = useRef(handleSend);
  useEffect(() => { handleSendRef.current = handleSend; }, [handleSend]);

  const toggleTranscript = (msgId: string) => {
    setMessages((prev) => prev.map((m) =>
      m.id === msgId ? { ...m, showTranscript: !m.showTranscript } : m
    ));
  };

  const retrySend = (msgId: string) => {
    const msg = messages.find((m) => m.id === msgId);
    if (!msg || msg.role !== 'heir') return;
    setMessages((prev) => prev.filter((m) => m.id !== msgId));
    setInput(msg.content);
    setTimeout(() => handleSend(), 50);
  };

  const typeIcon = (t?: string) => {
    if (t === 'conversation') return <MessageCircle className="w-3.5 h-3.5 text-blue-400 inline-block" />;
    if (t === 'fact') return <Pin className="w-3.5 h-3.5 text-amber-400 inline-block" />;
    if (t === 'preference') return <Heart className="w-3.5 h-3.5 text-red-400 inline-block" />;
    return '🧠';
  };

  const farewell = status?.farewell_letter || '';

  // 拨打通话
  const startCall = (type: CallType) => {
    setCallType(type);
    setCallState('calling');
    setCallDuration(0);
  };

  // 接听
  const answerCall = () => {
    setCallState('connected');
  };

  // 挂断
  const hangupCall = () => {
    setCallState('ended');
    setTimeout(() => {
      setCallType('none');
      setCallState('idle');
      setCallDuration(0);
    }, 300);
  };

  /* ─────────── 欢迎界面 ─────────── */
  if (!hasEntered) {
    const defaultWelcomeText = `孩子，你来了。

虽然我已不在这个世界，但我的记忆、我的想法、我对你的关心，都还在这里。

你想聊些什么？`;

    return (
      <div className="h-screen flex flex-col bg-[#ededed] overflow-hidden">
        <div className="h-12 bg-[#ededed] flex items-center justify-between px-4 border-b border-black/5 shrink-0">
          <button onClick={onExit} className="flex items-center gap-0.5 text-[#576b95]">
            <ChevronLeft className="w-5 h-5" /><span className="text-sm">返回</span>
          </button>
          <span className="text-base font-medium text-black">{userName}</span>
          <button className="text-[#576b95]"><MoreHorizontal className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center px-6">
          <div className="w-24 h-24 rounded-full overflow-hidden border-[3px] border-white shadow-lg mb-4 bg-gray-200">
            {soulAvatar ? (
              <img src={soulAvatar} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-gray-400 text-2xl">{userName.charAt(0)}</div>
            )}
          </div>
          <h1 className="text-xl font-semibold text-black mb-1">{userName}</h1>
          <p className="text-sm text-gray-400 mb-8">{status?.user_name ? '' : '数字灵魂'}</p>
          {farewell ? (
            <div className="max-w-md w-full mb-8">
              <div className="p-4 rounded-lg bg-white shadow-sm">
                <div className="text-xs text-[#576b95] mb-2 font-medium">留给{heirName}的话</div>
                <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{farewell}</p>
              </div>
            </div>
          ) : (
            <div className="max-w-md w-full mb-8 text-center">
              <p className="text-sm text-gray-400 leading-relaxed">这里留存着TA的记忆、思维方式和对你的关心。</p>
            </div>
          )}
          <button
            onClick={() => {
              setHasEntered(true);
              setMessages([{
                id: 'welcome', role: 'soul',
                content: farewell ? `${farewell}\n\n—— 现在，我们可以聊聊了。` : defaultWelcomeText,
                timestamp: Date.now(), isVoice: true,
                audioDuration: Math.max(3, Math.ceil((farewell || defaultWelcomeText).length / 4)),
              }]);
            }}
            className="px-10 py-2.5 bg-[#07c160] hover:bg-[#06ad56] text-white rounded text-sm font-medium transition"
          >开始对话</button>
        </div>
      </div>
    );
  }

  /* ─────────── 主聊天界面 ─────────── */
  return (
    <div className="h-screen flex bg-[#ededed] text-black overflow-hidden relative">
      {/* 通话覆盖层 */}
      {callType !== 'none' && callState !== 'idle' && callState !== 'ended' && (
        <CallOverlay
          callType={callType}
          callState={callState}
          callDuration={callDuration}
          userName={userName}
          avatarUrl={soulAvatar}
          heirColor={heirColor}
          heirName={heirName}
          isSpeaking={playingMsgId !== null}
          speechText={speech.interimTranscript || speech.transcript}
          onHangup={hangupCall}
          onAnswer={answerCall}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部栏 */}
        <div className="h-12 bg-[#ededed] flex items-center justify-between px-4 border-b border-black/5 shrink-0">
          <button onClick={onExit} className="flex items-center gap-0.5 text-[#576b95]">
            <ChevronLeft className="w-5 h-5" /><span className="text-sm">返回</span>
          </button>
          <div className="flex flex-col items-center">
            <span className="text-base font-medium text-black leading-tight">{userName}</span>
            {showIdentityNotice && <span className="text-[10px] text-gray-400 leading-tight">数字灵魂</span>}
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => startCall('voice')} className="text-gray-600 hover:text-gray-800 transition" title="连续语音模式">
              <Phone className="w-5 h-5" />
            </button>
            <button onClick={() => startCall('video')} className="text-gray-600 hover:text-gray-800 transition" title="面对面模式">
              <Video className="w-5 h-5" />
            </button>
            <button onClick={() => setShowSidebar(!showSidebar)} className="text-gray-600 hover:text-gray-800 transition">
              <MoreHorizontal className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Guardian Alert */}
        {guardianAlert && (
          <div className={`shrink-0 px-4 py-2 flex items-center gap-2 text-xs ${
            guardianAlert.level === 'red' ? 'bg-red-50 text-red-600 border-b border-red-100' :
            guardianAlert.level === 'orange' ? 'bg-amber-50 text-amber-600 border-b border-amber-100' :
            'bg-yellow-50 text-yellow-600 border-b border-yellow-100'
          }`}>
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span className="flex-1">{guardianAlert.message}</span>
            <button onClick={() => setGuardianAlert(null)} className="text-gray-400 hover:text-gray-600">知道了</button>
          </div>
        )}

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {messages.map((msg, idx) => {
            const prevMsg = idx > 0 ? messages[idx - 1] : undefined;
            const timeLabel = formatTimeDivider(msg.timestamp, prevMsg?.timestamp);
            return (
              <div key={msg.id}>
                {timeLabel && (
                  <div className="flex justify-center my-4">
                    <span className="text-[11px] text-gray-400 bg-gray-200/60 px-2 py-0.5 rounded">{timeLabel}</span>
                  </div>
                )}
                <div className={`flex ${msg.role === 'heir' ? 'justify-end' : 'justify-start'} mb-3`}>
                  {msg.role === 'soul' && (
                    <div className="w-9 h-9 rounded-[4px] overflow-hidden shrink-0 mr-2.5 self-start bg-gray-200">
                      {soulAvatar ? (
                        <img src={soulAvatar} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">{userName.charAt(0)}</div>
                      )}
                    </div>
                  )}

                  <div className={`max-w-[72%] flex flex-col ${msg.role === 'heir' ? 'items-end' : 'items-start'}`}>
                    {msg.isVoice ? (
                      <div
                        onClick={() => playTTS(msg.id, msg.content, msg.emotion || 'neutral')}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer select-none ${
                          msg.role === 'heir' ? 'bg-[#95ec69]' : 'bg-white'
                        }`}
                        style={{ minWidth: `${60 + (msg.audioDuration || 3) * 8}px`, maxWidth: '220px' }}
                      >
                        {msg.role === 'soul' ? (
                          <>
                            {playingMsgId === msg.id ? (
                              <div className="flex items-center gap-[2px] h-4">
                                {[1, 0.6, 0.9, 0.5, 0.8].map((h, i) => (
                                  <div key={i} className="w-[2px] bg-[#07c160] rounded-full animate-pulse"
                                    style={{ height: `${Math.max(3, h * 12)}px`, animationDelay: `${i * 120}ms` }} />
                                ))}
                              </div>
                            ) : (
                              <Volume2 className="w-4 h-4 text-[#07c160] shrink-0" />
                            )}
                            <span className="text-xs text-gray-500 shrink-0 ml-auto">{msg.audioDuration || 3}"</span>
                          </>
                        ) : (
                          <>
                            <span className="text-xs text-gray-600 shrink-0">{msg.audioDuration || 3}"</span>
                            {playingMsgId === msg.id ? (
                              <div className="flex items-center gap-[2px] h-4 ml-auto">
                                {[1, 0.6, 0.9, 0.5, 0.8].map((h, i) => (
                                  <div key={i} className="w-[2px] bg-[#1a1a1a] rounded-full animate-pulse"
                                    style={{ height: `${Math.max(3, h * 12)}px`, animationDelay: `${i * 120}ms` }} />
                                ))}
                              </div>
                            ) : (
                              <Volume2 className="w-4 h-4 text-gray-700 shrink-0 ml-auto" />
                            )}
                          </>
                        )}
                      </div>
                    ) : (
                      <div className={`px-3.5 py-2 rounded-lg text-[15px] leading-relaxed ${
                        msg.role === 'heir' ? 'bg-[#95ec69] text-black' : 'bg-white text-black'
                      }`}>
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                      </div>
                    )}

                    <div className="flex items-center gap-2 mt-1 px-1">
                      <span className="text-[10px] text-gray-400">
                        {new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {msg.role === 'heir' && (
                        <span className="text-[10px] text-gray-400">
                          {msg.sending ? '发送中…' :
                           msg.failed ? (
                             <button onClick={() => retrySend(msg.id)} className="text-red-500 flex items-center gap-0.5">
                               <RotateCcw className="w-3 h-3" /> 失败
                             </button>
                           ) : (
                             <CheckCheck className="w-3 h-3 text-[#07c160]" />
                           )}
                        </span>
                      )}
                      {msg.role === 'soul' && msg.isVoice && (
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleTranscript(msg.id); }}
                          className="text-[10px] text-[#576b95] hover:underline"
                        >
                          {msg.showTranscript ? '收起' : '转文字'}
                        </button>
                      )}
                    </div>

                    {msg.role === 'soul' && msg.isVoice && msg.showTranscript && (
                      <div className="mt-1.5 px-2 py-1.5 bg-white/60 rounded text-[13px] text-gray-700 leading-relaxed border border-black/5">
                        {msg.content}
                      </div>
                    )}
                  </div>

                  {msg.role === 'heir' && (
                    <div
                      className="w-9 h-9 rounded-[4px] overflow-hidden shrink-0 ml-2.5 self-start flex items-center justify-center text-white text-xs font-medium"
                      style={{ backgroundColor: heirColor }}
                    >
                      {heirName.charAt(0)}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="flex justify-start mb-3">
              <div className="w-9 h-9 rounded-[4px] overflow-hidden shrink-0 mr-2.5 bg-gray-200 self-start">
                {soulAvatar ? (
                  <img src={soulAvatar} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">{userName.charAt(0)}</div>
                )}
              </div>
              <div className="bg-white px-4 py-3 rounded-lg">
                <div className="flex items-center gap-1.5 text-gray-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* 底部输入栏 */}
        <div className="shrink-0 bg-[#f7f7f7] border-t border-black/5 relative">
          <div className="flex items-center gap-2 px-3 py-2">
            <button
              onClick={() => setInputMode(inputMode === 'text' ? 'voice' : 'text')}
              className="w-8 h-8 flex items-center justify-center text-gray-600 hover:text-gray-800 transition shrink-0"
            >
              {inputMode === 'text' ? <Mic className="w-5 h-5" /> : <Keyboard className="w-5 h-5" />}
            </button>

            {inputMode === 'text' ? (
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder=""
                className="flex-1 bg-white border border-black/10 rounded text-sm px-3 py-2 text-black placeholder-gray-400 focus:outline-none focus:border-[#07c160]/50"
              />
            ) : (
              <button
                onPointerDown={() => {
                  micPressTimerRef.current = window.setTimeout(() => {
                    isLongPressRef.current = true;
                    voiceRecorder.startRecording();
                  }, 300);
                }}
                onPointerUp={() => {
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
                        const form = new FormData();
                        form.append('file', blob, `asr_${Date.now()}.webm`);
                        const res = await fetch(`/api/v1/soul/asr/${userId}`, { method: 'POST', body: form });
                        const asrRes = await res.json();
                        if (asrRes.text && asrRes.text.trim() && !asrRes.fallback) finalText = asrRes.text.trim();
                      } catch {}
                    }
                    if (finalText && finalText.trim()) {
                      setInput(finalText.trim());
                      setInputMode('text');
                      setTimeout(() => handleSend(), 50);
                    }
                  }, 200);
                }}
                onPointerLeave={() => {
                  if (micPressTimerRef.current) clearTimeout(micPressTimerRef.current);
                  if (isLongPressRef.current) { isLongPressRef.current = false; voiceRecorder.stopRecording(); }
                }}
                className={`flex-1 py-2 rounded text-sm font-medium transition ${
                  voiceRecorder.isRecording ? 'bg-gray-300 text-gray-600' : 'bg-white text-gray-700 border border-black/10'
                }`}
              >
                {voiceRecorder.isRecording ? '松开 结束' : '按住 说话'}
              </button>
            )}

            <button className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 transition shrink-0">
              <SmilePlus className="w-5 h-5" />
            </button>

            {inputMode === 'text' && (
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="px-4 py-2 bg-[#07c160] hover:bg-[#06ad56] disabled:bg-gray-300 disabled:text-gray-500 text-white rounded text-sm font-medium transition shrink-0"
              >
                {loading ? '...' : '发送'}
              </button>
            )}
          </div>

          {voiceRecorder.isRecording && (
            <div className="absolute inset-0 bg-black/30 flex items-center justify-center z-50">
              <div className="bg-[#4c4c4c] rounded-lg px-6 py-4 flex flex-col items-center gap-3">
                <div className="flex items-end gap-0.5 h-8">
                  {voiceRecorder.visualizerData.slice(0, 20).map((v: number, i: number) => (
                    <div key={i} className="w-1 bg-white rounded-full transition-all"
                      style={{ height: `${Math.max(4, v * 28)}px` }} />
                  ))}
                </div>
                <span className="text-white text-sm">{voiceRecorder.recordingTime}s</span>
                <span className="text-white/60 text-xs">手指上滑，取消发送</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 侧边栏 */}
      {showSidebar && (
        <div className="w-80 border-l border-black/5 bg-white flex flex-col shrink-0">
          <div className="flex border-b border-black/5">
            {[
              { key: 'memories', label: <><BookOpen className="w-3.5 h-3.5 inline-block mr-1" /> 记忆</> },
              { key: 'relations', label: <><Users className="w-3.5 h-3.5 inline-block mr-1" /> 关系</> },
              { key: 'profile', label: '🧬 画像' },
              { key: 'health', label: <><Shield className="w-3.5 h-3.5 inline-block mr-1" /> 健康</> },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setSidebarTab(tab.key as any)}
                className={`flex-1 py-2.5 text-xs font-medium transition ${
                  sidebarTab === tab.key ? 'text-[#07c160] border-b-2 border-[#07c160]' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {sidebarTab === 'memories' && (
              <div className="space-y-3">
                <div className="text-xs text-gray-500 mb-2">
                  {memories.length === 0 ? '记忆之书还是空的' : `共 ${memories.length} 段记忆`}
                </div>
                {memories.map((m) => (
                  <div key={m.id} className="p-3 rounded-lg bg-gray-50 border border-black/5">
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="text-sm">{typeIcon(m.memory_type)}</span>
                      <span className="text-xs text-gray-700 font-medium truncate">{m.title}</span>
                    </div>
                    {m.summary && <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-3">{m.summary}</p>}
                    <div className="text-[10px] text-gray-400 mt-1.5">{m.created_at ? new Date(m.created_at).toLocaleDateString('zh-CN') : ''}</div>
                  </div>
                ))}
              </div>
            )}
            {sidebarTab === 'relations' && <div className="h-64"><RelationGalaxy /></div>}
            {sidebarTab === 'profile' && (
              <div className="space-y-4">
                {profile?.soul_dimensions && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">人格维度</div>
                    {Object.entries(profile.soul_dimensions).map(([key, val]: [string, any]) => (
                      <div key={key} className="flex items-center gap-2 mb-1.5">
                        <span className="text-[10px] text-gray-400 w-12">{key}</span>
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-[#07c160] rounded-full" style={{ width: `${val * 100}%` }} />
                        </div>
                        <span className="text-[10px] text-gray-500 w-8 text-right">{Math.round(val * 100)}%</span>
                      </div>
                    ))}
                  </div>
                )}
                {profile?.core_values && profile.core_values.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-500 mb-2">核心价值观</div>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.core_values.map((v: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 bg-[#07c160]/10 text-[#07c160] rounded-full text-[10px] border border-[#07c160]/20">{v}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {sidebarTab === 'health' && (
              <div className="space-y-4">
                {healthReport ? (
                  <>
                    <div className={`p-3 rounded-xl border ${
                      healthReport.status === 'healthy' ? 'bg-emerald-50 border-emerald-100' :
                      healthReport.status === 'attention' ? 'bg-amber-50 border-amber-100' :
                      'bg-red-50 border-red-100'
                    }`}>
                      <div className="text-xs mb-1">
                        <span className={healthReport.status === 'healthy' ? 'text-emerald-600' :
                          healthReport.status === 'attention' ? 'text-amber-600' : 'text-red-600'}>交互健康度</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="relative w-14 h-14">
                          <svg className="w-14 h-14 -rotate-90" viewBox="0 0 36 36">
                            <path className="text-gray-200" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                            <path className={`transition-all duration-700 ${
                              healthReport.status === 'healthy' ? 'text-emerald-500' :
                              healthReport.status === 'attention' ? 'text-amber-500' : 'text-red-500'
                            }`} strokeDasharray={`${healthReport.health_score}, 100`} d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                          </svg>
                          <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-sm font-bold text-gray-800">{healthReport.health_score}</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-600">
                            {healthReport.status === 'healthy' ? '状态良好' :
                             healthReport.status === 'attention' ? '需要关注' : '建议休息'}
                          </div>
                          <div className="text-[10px] text-gray-400 mt-0.5">累计 {healthReport.total_interactions} 次交互</div>
                        </div>
                      </div>
                    </div>
                    {healthReport.daily_stats && healthReport.daily_stats.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 mb-2">最近7天</div>
                        <div className="space-y-1.5">
                          {healthReport.daily_stats.map((d: any) => (
                            <div key={d.date} className="flex items-center gap-2 text-[10px]">
                              <span className="text-gray-500 w-16">{d.date}</span>
                              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-[#07c160]/60 rounded-full" style={{ width: `${Math.min(100, d.minutes / 2)}%` }} />
                              </div>
                              <span className="text-gray-600 w-12 text-right">{d.minutes}分钟</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : <div className="text-xs text-gray-400 text-center py-8">健康数据采集中…</div>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
