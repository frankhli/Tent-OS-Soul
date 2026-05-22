import {useState, useEffect, useRef, useCallback} from 'react';
import {useWebSocket} from '../hooks/useWebSocket';
import * as api from '../api/soulApi';
import {useVoiceRecorder} from '../hooks/useVoiceRecorder';
import {useSystemSettings} from './SystemSettings';
import MarkdownMessage from './MarkdownMessage';
import {Sparkles, Lightbulb, AlertTriangle, ThumbsUp, ThumbsDown, Mic, Paperclip, FileText, BookOpen, Brain, RefreshCw, Phone, Search, Globe, Laptop, History, ChevronUp, ChevronDown} from 'lucide-react';
import VoiceCallPanel from './VoiceCallPanel';
import {EmotionAvatar} from './EmotionAvatar';

interface Msg {
 id: string;
 role: 'user' | 'assistant' | 'system';
 content: string;
 reasoning?: string;
 audioUrl?: string;
 isStreaming?: boolean;
 timestamp?: number;
 toolCalls?: {tool: string; arguments: string}[];
 toolResults?: {tool: string; result: string}[];
}

interface ChatInterfaceProps {
 sessionId: string | null;
 onSessionCreated?: (sessionId: string) => void;
 onNewSession?: () => void;
 onOpenHistory?: () => void;
}

export default function ChatInterface({sessionId: propSessionId, onSessionCreated, onNewSession, onOpenHistory}: ChatInterfaceProps) {
 // 欢迎语从 localStorage 加载，支持用户自定义；首次使用默认欢迎语
 const DEFAULT_WELCOME = (() => {
 // 尝试从环境/配置加载个性化欢迎语（生产环境可替换）
 try {
 const custom = localStorage.getItem('tent_custom_welcome');
 if (custom) return custom;
} catch {}
 return '你好，我是 Tent OS。从今天开始，我会通过每一次对话了解你——你的思维方式、说话习惯、甚至表情。\n\n不是为了监控你，而是为了**记住你**。这样未来的你，才能以你最真实的样子，继续存在。';
})();

 const [messages, setMessages] = useState<Msg[]>([
 {
 id: 'welcome',
 role: 'assistant',
 content: DEFAULT_WELCOME,
 timestamp: Date.now(),
},
 ]);
 const [input, setInput] = useState('');
 const [sessionId, setSessionId] = useState<string | null>(propSessionId);

 // Sync sessionId from props
 useEffect(() => {
 setSessionId(propSessionId);
}, [propSessionId]);
 const [emotion, setEmotion] = useState<string>('listening');
 const [completeness, setCompleteness] = useState({thought: 0, voice: 0, appearance: 0, overall: 0});
 const [playingMsgId, setPlayingMsgId] = useState<string | null>(null);
 const [followUpQuestions, setFollowUpQuestions] = useState<string[]>([]);
 const [isComposing, setIsComposing] = useState(false);
 const [messageFeedback, setMessageFeedback] = useState<Record<string, 'like' | 'dislike' | null>>({});
 const messageFeedbackRef = useRef(messageFeedback);
 const messagesRef = useRef(messages);
 useEffect(() => { messageFeedbackRef.current = messageFeedback; }, [messageFeedback]);
 useEffect(() => { messagesRef.current = messages; }, [messages]);
 const [attachedFiles, setAttachedFiles] = useState<{name: string; content: string; type: string}[]>([]);
 const {settings} = useSystemSettings();

 // 工具能力开关（参考 Kimi/DeepSeek 设计：per-message 能力选择）
 const [enabledTools, setEnabledTools] = useState<{
 web_search: boolean;
 file_ops: boolean;
}>(() => {
 try {
 const saved = localStorage.getItem('tent_enabled_tools');
 return saved ? JSON.parse(saved) : {web_search: false, file_ops: false};
} catch {return {web_search: false, file_ops: false};}
});
 const [deepThinking, setDeepThinking] = useState(() => {
 try {return localStorage.getItem('tent_deep_thinking') === 'true';} catch {return false;}
});


 useEffect(() => {
 localStorage.setItem('tent_enabled_tools', JSON.stringify(enabledTools));
}, [enabledTools]);
 useEffect(() => {
 localStorage.setItem('tent_deep_thinking', String(deepThinking));
}, [deepThinking]);

 const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(() => {
 try {
 const saved = localStorage.getItem('tent_expanded_reasoning');
 return saved ? new Set(JSON.parse(saved)) : new Set();
} catch {return new Set();}
});
 const [messageSearch, setMessageSearch] = useState('');
 const [showMessageSearch, setShowMessageSearch] = useState(false);
 const [searchResultIndex, setSearchResultIndex] = useState(0);
 const [showAvatarThumbnail, setShowAvatarThumbnail] = useState(() => {
 try {return localStorage.getItem('tent_show_avatar') !== 'false';} catch {return true;}
});
 const [avatarConfig, setAvatarConfig] = useState<{skin?: {base?: string}; hair?: {base?: string}} | null>(null);

 // Auto-expand reasoning for new messages if setting is enabled
 useEffect(() => {
 if (!settings.show_reasoning) return;
 const newIds = messages.filter((m) => m.reasoning && !expandedReasoning.has(m.id)).map((m) => m.id);
 if (newIds.length > 0) {
 setExpandedReasoning((prev) => {
 const next = new Set(prev);
 newIds.forEach((id) => next.add(id));
 return next;
});
}
}, [messages, settings.show_reasoning]);

 useEffect(() => {
 localStorage.setItem('tent_expanded_reasoning', JSON.stringify(Array.from(expandedReasoning)));
}, [expandedReasoning]);

 // FIX: 自动持久化消息到 localStorage，防止刷新页面后消息丢失
 useEffect(() => {
 if (sessionId && messages.length > 1) {
 try {
 localStorage.setItem(`tent_messages_${sessionId}`, JSON.stringify(messages));
 } catch {}
 }
 }, [messages, sessionId]);
 const [isCamOn, setIsCamOn] = useState(false);
 const [camStream, setCamStream] = useState<MediaStream | null>(null);
 const [showCamPreview, setShowCamPreview] = useState(false);
 const [voiceCallMode, setVoiceCallMode] = useState(false);
 const [toastMsg, setToastMsg] = useState('');
 const [isDragOver, setIsDragOver] = useState(false);
 const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
 const [editDraft, setEditDraft] = useState('');
 const [audioProgress, setAudioProgress] = useState(0);
 const [approvalRequest, setApprovalRequest] = useState<{sessionId: string; plan: any} | null>(null);
 const [audioDuration, setAudioDuration] = useState(0);
 const fileInputRef = useRef<HTMLInputElement>(null);
 const videoRef = useRef<HTMLVideoElement>(null);
 const camIntervalRef = useRef<number>(0);
 const cameraStartTimeoutRef = useRef<number>(0);

 const chatEndRef = useRef<HTMLDivElement>(null);
 const isNearBottomRef = useRef(true);
 const chatScrollRef = useRef<HTMLDivElement>(null);
 const audioRef = useRef<HTMLAudioElement | null>(null);
 const ttsCacheRef = useRef<Map<string, string>>(new Map());
 const toastTimerRef = useRef<number>(0);
 const voiceRetryTimersRef = useRef<number[]>([]);

 const voiceRecorder = useVoiceRecorder();
 const micButtonRef = useRef<HTMLButtonElement>(null);
 const micPressTimerRef = useRef<number>(0);
 const isLongPressRef = useRef(false);

 const {lastMessage, send, connectionStatus, reconnectCount} = useWebSocket(`ws://${location.host}/ws`);

 const showToast = useCallback((msg: string) => {
 setToastMsg(msg);
 if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
 toastTimerRef.current = window.setTimeout(() => setToastMsg(''), 3000);
 }, []);

 // Load soul completeness on mount
 useEffect(() => {
 loadCompleteness();
 const iv = setInterval(() => {
 loadCompleteness();
}, 15000);
 return () => clearInterval(iv);
}, []);



 const loadCompleteness = async () => {
 try {
 const data = await api.getSoulCompleteness();
 setCompleteness(data);
} catch (e) {}
};

 // Draft persistence
 const draftKey = `tent_chat_draft_${sessionId || 'default'}`;
 useEffect(() => {
 const saved = localStorage.getItem(draftKey);
 if (saved) setInput(saved);
}, [draftKey]);
 useEffect(() => {
 localStorage.setItem(draftKey, input);
}, [input, draftKey]);

 // Load session messages when sessionId changes
 useEffect(() => {
 setSessionId(propSessionId);
 if (!propSessionId) {
 setMessages([{
 id: 'welcome',
 role: 'assistant',
 content: DEFAULT_WELCOME,
 timestamp: Date.now(),
}]);
 return;
}
 // FIX: 避免在对话进行中加载历史消息，覆盖用户刚发送的消息
 if (messagesRef.current.some((m) => m.isStreaming)) return;
 // 先从 localStorage 恢复（应对刷新页面时的消息丢失）
 try {
 const saved = localStorage.getItem(`tent_messages_${propSessionId}`);
 if (saved) {
 const parsed = JSON.parse(saved);
 if (Array.isArray(parsed) && parsed.length > 0) {
 setMessages(parsed);
 }
 }
 } catch {}
 // 再向后端请求历史消息（后端数据更权威，会覆盖本地）
 send('chat.session.load', {session_id: propSessionId, user_id: api.USER_ID});
}, [propSessionId]);

 // Handle WS messages
 useEffect(() => {
 if (!lastMessage) return;
 const {type, payload} = lastMessage;
 if (type === 'chat.completed') {
 let completedMsgId: string | null = null;
 const content = typeof payload.content === 'string' ? payload.content : String(payload.content ?? '');
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 completedMsgId = prev[idx].id;
 const updated = [...prev];
 updated[idx] = {
 ...updated[idx],
 content: content,
 reasoning: payload.reasoning ? payload.reasoning : (updated[idx].reasoning || ''),
 isStreaming: false,
};
 return updated;
}
 return prev;
});
 setEmotion('calm');

 loadCompleteness();

 if (payload.follow_up_questions && Array.isArray(payload.follow_up_questions)) {
 setFollowUpQuestions(payload.follow_up_questions);
}

 if (content.trim() && completedMsgId && settings.tts_auto_play) {
 const cached = ttsCacheRef.current.get(completedMsgId);
 if (cached) {
 playAudio(cached, completedMsgId);
} else {
 // Try streaming TTS first
 const streamUrl = api.getTTSStreamUrl(content.trim(), emotion, settings.tts_voice);
 const audio = new Audio(streamUrl);
 audioRef.current = audio;
 setPlayingMsgId(completedMsgId);
 let fallbackTriggered = false;
 const doFallback = () => {
 if (fallbackTriggered) return;
 fallbackTriggered = true;
 api.synthesizeTTS(content.trim(), emotion, settings.tts_voice)
 .then((res) => {
 if (res.audio_url && completedMsgId) {
 ttsCacheRef.current.set(completedMsgId, res.audio_url);
 playAudio(res.audio_url, completedMsgId);
}
})
 .catch(() => {setPlayingMsgId(null); audioRef.current = null;});
};
 audio.onended = () => {
 setPlayingMsgId(null);
 audioRef.current = null;
 if (completedMsgId) ttsCacheRef.current.set(completedMsgId, streamUrl);
};
 audio.onerror = () => doFallback();
 audio.play().catch(() => doFallback());
}
}
} else if (type === 'chat.stream_chunk') {
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 const chunkText = typeof payload.content === 'string' ? payload.content : (typeof payload.chunk === 'string' ? payload.chunk : '');
 updated[idx] = {
 ...updated[idx],
 content: updated[idx].content + chunkText,
};
 return updated;
}
 return prev;
});
} else if (type === 'chat.reasoning_chunk' || type === 'chat.stream_reasoning') {
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 const chunkText = typeof payload.content === 'string' ? payload.content : (typeof payload.chunk === 'string' ? payload.chunk : '');
 updated[idx] = {
 ...updated[idx],
 reasoning: (updated[idx].reasoning || '') + chunkText,
};
 return updated;
}
 return prev;
});
} else if (type === 'chat.message_accepted') {
 setSessionId(payload.session_id);
 // Notify parent that a new session was created
 if (onSessionCreated && !propSessionId) {
 onSessionCreated(payload.session_id);
}
} else if (type === 'chat.session.loaded') {
 const loadedMessages = payload.messages || [];
 setMessages((prev) => {
 // 如果正在流式输出，保留当前状态，避免打断生成过程
 if (prev.some((m) => m.isStreaming)) return prev;
 if (loadedMessages.length > 0) {
 const hist = loadedMessages.map((m: any, i: number) => ({
 id: `hist_${i}`,
 role: m.role as 'user' | 'assistant' | 'system',
 content: m.content,
 reasoning: m.reasoning || '',
 timestamp: Date.now(),
 }));
 // FIX: 保留当前不在历史中的最新消息，避免覆盖正在进行的对话
 const existingContents = new Set(loadedMessages.map((m: any) => m.content));
 const localExtras = prev.filter((m) => m.id !== 'welcome' && !existingContents.has(m.content));
 return [...hist, ...localExtras];
 }
 if (!payload.error) {
 return [{
 id: 'welcome',
 role: 'assistant',
 content: DEFAULT_WELCOME,
 timestamp: Date.now(),
 }];
 }
 return prev;
 });
} else if (type === 'ai.emotion') {
 setEmotion(payload.emotion || 'listening');
} else if (type === 'user.emotion') {
 const userEmotion = payload.emotion || 'neutral';
 if (userEmotion === 'sadness' || userEmotion === 'fear') {
 setEmotion('sad');
} else if (userEmotion === 'joy' || userEmotion === 'excited') {
 setEmotion('happy');
} else if (userEmotion === 'anger') {
 setEmotion('confused');
}
} else if (type === 'approval.request') {
 setApprovalRequest({
 sessionId: payload.session_id,
 plan: payload.plan || {},
 });
} else if (type === 'chat.tool_call') {
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 const toolArgs = typeof payload.arguments === 'string' ? payload.arguments : JSON.stringify(payload.arguments ?? {});
 updated[idx] = {
 ...updated[idx],
 toolCalls: [...(updated[idx].toolCalls || []), {
 tool: payload.tool || '',
 arguments: toolArgs,
 }],
 };
 return updated;
}
 return prev;
});
} else if (type === 'chat.tool_result') {
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 const toolRes = typeof payload.result === 'string' ? payload.result : JSON.stringify(payload.result ?? {});
 updated[idx] = {
 ...updated[idx],
 toolResults: [...(updated[idx].toolResults || []), {
 tool: payload.tool || '',
 result: toolRes,
 }],
 };
 return updated;
}
 return prev;
});
} else if (type === 'chat.aborted' || type === 'chat.error' || type === 'task.aborted') {
 // 中止或出错：停止动画
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 updated[idx] = {...updated[idx], isStreaming: false};
 return updated;
}
 return prev;
});
 setEmotion('calm');

}
}, [lastMessage]);

 // 滚动锁：只在用户位于底部时自动滚动
 useEffect(() => {
 const el = chatScrollRef.current;
 if (!el) return;
 const onScroll = () => {
 const threshold = 100;
 isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
};
 el.addEventListener('scroll', onScroll, {passive: true});
 return () => el.removeEventListener('scroll', onScroll);
}, []);

 // 组件卸载时停止音频播放
 useEffect(() => {
 return () => {
 if (audioRef.current) {
 audioRef.current.pause();
 audioRef.current = null;
 }
 };
 }, []);

 const scrollThrottleRef = useRef<number>(0);
 useEffect(() => {
 if (!isNearBottomRef.current) return;
 const now = Date.now();
 if (now - scrollThrottleRef.current < 200) return;
 scrollThrottleRef.current = now;
 chatEndRef.current?.scrollIntoView({behavior: 'smooth'});
}, [messages]);

 // Auto-scroll to search result
 useEffect(() => {
 if (!showMessageSearch || !messageSearch) return;
 const matches = messages.filter((m) => (m.content || '').toLowerCase().includes(messageSearch.toLowerCase()));
 const target = matches[searchResultIndex];
 if (target) {
 const el = document.querySelector(`[data-msg-id="${target.id}"]`);
 el?.scrollIntoView({behavior: 'smooth', block: 'center'});
 }
 // eslint-disable-next-line react-hooks/exhaustive-deps
}, [searchResultIndex, messageSearch, showMessageSearch]);

 const doSend = useCallback((text: string) => {
 if (messagesRef.current.some((m) => m.isStreaming)) return;
 if (!text.trim() && attachedFiles.length === 0) return;
 const sid = sessionId || `ws_${Date.now().toString(36)}`;
 setSessionId(sid);

 let fullContent = text.trim();
 if (attachedFiles.length > 0) {
 const fileContext = attachedFiles.map((f) => `\n\n[附件: ${f.name}]\n${f.content.slice(0, 3000)}`).join('\n');
 fullContent = fullContent ? fullContent + fileContext : fileContext;
}

 const newMessages: Msg[] = [
 ...messagesRef.current,
 {id: `u_${Date.now()}`, role: 'user' as const, content: text.trim() || `[附件] ${attachedFiles.map((f) => f.name).join(', ')}`, timestamp: Date.now()},
 {id: `a_${Date.now()}`, role: 'assistant' as const, content: '', isStreaming: true, timestamp: Date.now()},
 ];
 setMessages(newMessages);
 // FIX: 持久化消息到 localStorage，防止刷新页面后消息丢失
 try {
 localStorage.setItem(`tent_messages_${sid}`, JSON.stringify(newMessages));
 } catch {}

 setFollowUpQuestions([]);
 setAttachedFiles([]);
 send('chat.message', {
 session_id: sid,
 user_id: api.USER_ID,
 content: fullContent,
 tools: enabledTools,
 deep_thinking: deepThinking,
});
 setEmotion('thinking');

 // FIX: 发送成功后清除旧 draft，防止刷新页面后输入框残留旧内容
 try {
   localStorage.removeItem('tent_chat_draft_default');
   localStorage.setItem('tent_current_session', sid);
 } catch {}

 const todoPatterns = [/提醒[我]?[:：]\s*(.+)/i, /待办[:：]\s*(.+)/i, /todo[:：]\s*(.+)/i, /记住要[:：]\s*(.+)/i];
 for (const pat of todoPatterns) {
 const m = text.match(pat);
 if (m && m[1]) {
 fetch('/api/v1/todos', {
 method: 'POST',
 headers: {'Content-Type': 'application/json'},
 body: JSON.stringify({title: m[1].trim(), priority: 'medium'}),
}).catch(() => {});
 break;
}
}
}, [sessionId, send, attachedFiles, enabledTools, deepThinking]);

 const handleSend = useCallback(() => {
 if (messagesRef.current.some((m) => m.isStreaming)) return;
 doSend(input);
 setInput('');
}, [doSend, input]);

 const handleStop = useCallback(() => {
 if (sessionId) {
 send('chat.abort', {session_id: sessionId});
}
 // 本地立即标记停止动画
 setMessages((prev) => {
 const idx = prev.findIndex((m) => m.isStreaming);
 if (idx >= 0) {
 const updated = [...prev];
 updated[idx] = {...updated[idx], isStreaming: false};
 return updated;
}
 return prev;
});
 setEmotion('calm');
}, [sessionId, send]);

 // 消息反馈：同步到后端
 const handleFeedback = useCallback(async (msgId: string, type: 'like' | 'dislike') => {
 const currentFeedback = messageFeedbackRef.current;
 const newType = currentFeedback[msgId] === type ? null : type;
 setMessageFeedback((prev) => ({...prev, [msgId]: newType}));
 if (!sessionId || !newType) return;
 const msgIndex = messagesRef.current.findIndex((m) => m.id === msgId);
 try {
 await fetch(`/api/v1/feedback/${sessionId}`, {
 method: 'POST',
 headers: {'Content-Type': 'application/json'},
 body: JSON.stringify({type: newType, message_index: msgIndex >= 0 ? msgIndex : null}),
});
} catch (e) {
 // 静默失败，UI已更新
}
}, [sessionId]);

 // Voice message: long press to record, release to send
 const handleMicPointerDown = useCallback(() => {
 isLongPressRef.current = false;
 micPressTimerRef.current = window.setTimeout(() => {
 isLongPressRef.current = true;
 voiceRecorder.startRecording();
}, 300);
}, [voiceRecorder]);

 const handleMicPointerUp = useCallback(() => {
 clearTimeout(micPressTimerRef.current);
 // Clear any pending voice retry timers
 voiceRetryTimersRef.current.forEach((id) => clearTimeout(id));
 voiceRetryTimersRef.current = [];
 if (!isLongPressRef.current) return;
 voiceRecorder.stopRecording();

 const trySend = async () => {
 const latest = voiceRecorder.stateRef.current;
 const browserText = latest.transcript || latest.interimTranscript;
 const blob = latest.audioBlob;
 const userMsgId = `u_${Date.now()}`;

 // 优先调用后端 ASR，失败 fallback 到浏览器 ASR
 let finalText = browserText;
 if (blob && blob.size > 1000) {
 try {
 const asrRes = await api.transcribeAudio(blob, `asr_${Date.now()}.webm`);
 if (asrRes.text && asrRes.text.trim() && !asrRes.fallback) {
 finalText = asrRes.text.trim();
}
} catch (e) {
 // fallback to browser ASR
}
}

 if (finalText && finalText.trim()) {
 const sid = sessionId || `ws_${Date.now().toString(36)}`;
 setSessionId(sid);
 setMessages((prev) => [
 ...prev,
 {id: userMsgId, role: 'user', content: finalText.trim(), timestamp: Date.now()},
 {id: `a_${Date.now()}`, role: 'assistant', content: '', isStreaming: true, timestamp: Date.now()},
 ]);
 send('chat.message', {session_id: sid, user_id: api.USER_ID, content: finalText.trim(), tools: enabledTools, deep_thinking: deepThinking});
 setEmotion('thinking');
}

 // Upload voice message and attach audioUrl
 if (blob && blob.size > 1000) {
 try {
 // Also save as training sample
 api.uploadVoiceSample(blob, `voice_msg_${Date.now()}.webm`).catch(() => {});
 loadCompleteness();
 // Save as voice message for playback
 const vmRes = await api.uploadVoiceMessage(blob, `vm_${Date.now()}.webm`);
 if (vmRes.url) {
 setMessages((prev) =>
 prev.map((m) => (m.id === userMsgId ? {...m, audioUrl: vmRes.url} : m))
 );
}
} catch (e) {}
}
};

 const t1 = window.setTimeout(() => {
 if (voiceRecorder.stateRef.current.audioBlob) {
 trySend();
} else {
 const t2 = window.setTimeout(() => {
 if (voiceRecorder.stateRef.current.audioBlob) {
 trySend();
} else {
 const t3 = window.setTimeout(trySend, 800);
 voiceRetryTimersRef.current.push(t3);
}
}, 400);
 voiceRetryTimersRef.current.push(t2);
}
}, 200);
 voiceRetryTimersRef.current.push(t1);
}, [voiceRecorder, sessionId, send, enabledTools, deepThinking]);

 // Audio playback for TTS
 const playAudio = useCallback((url: string, msgId: string) => {
 if (audioRef.current) {
 audioRef.current.pause();
 audioRef.current = null;
}
 const audio = new Audio(url);
 audioRef.current = audio;
 setPlayingMsgId(msgId);
 setAudioProgress(0);
 setAudioDuration(0);
 audio.onloadedmetadata = () => {
 if (audio.duration && isFinite(audio.duration)) {
 setAudioDuration(audio.duration);
}
};
 audio.ontimeupdate = () => {
 if (audio.duration && isFinite(audio.duration)) {
 setAudioProgress(audio.currentTime / audio.duration);
}
};
 audio.onended = () => {
 setPlayingMsgId(null);
 setAudioProgress(0);
 audioRef.current = null;
};
 audio.onerror = () => {
 setPlayingMsgId(null);
 setAudioProgress(0);
 audioRef.current = null;
};
 audio.play().catch(() => {
 setPlayingMsgId(null);
});
}, []);

 // Camera
 const startCamera = async () => {
 try {
 const stream = await navigator.mediaDevices.getUserMedia({video: true, audio: false});
 setCamStream(stream);
 setIsCamOn(true);
 setShowCamPreview(true);
 // Delay to let video element mount, then set srcObject and play
 if (cameraStartTimeoutRef.current) clearTimeout(cameraStartTimeoutRef.current);
 cameraStartTimeoutRef.current = window.setTimeout(() => {
 if (videoRef.current) {
 videoRef.current.srcObject = stream;
 videoRef.current.play().catch(() => {});
}
}, 100);
 camIntervalRef.current = window.setInterval(() => {
 captureAndUpload();
}, 8000);
} catch (err: any) {
 alert('无法访问摄像头: ' + err.message);
}
};

 const stopCamera = () => {
 camStream?.getTracks().forEach((t) => t.stop());
 setCamStream(null);
 setIsCamOn(false);
 setShowCamPreview(false);
 clearInterval(camIntervalRef.current);
 clearTimeout(cameraStartTimeoutRef.current);
};

 const captureAndUpload = () => {
 const video = videoRef.current;
 if (!video || video.readyState < 2) return;
 const canvas = document.createElement('canvas');
 canvas.width = video.videoWidth || 640;
 canvas.height = video.videoHeight || 480;
 const ctx = canvas.getContext('2d');
 if (!ctx) return;
 ctx.drawImage(video, 0, 0);
 canvas.toBlob(async (blob) => {
 if (!blob) return;
 try {
 await api.uploadAppearancePhoto(blob, `capture_${Date.now()}.jpg`);
 loadCompleteness();
} catch (e) {}
}, 'image/jpeg', 0.8);
};

 const togglePlay = useCallback(async (msgId: string, content: string) => {
 if (playingMsgId === msgId && audioRef.current) {
 audioRef.current.pause();
 setPlayingMsgId(null);
 return;
}
 if (audioRef.current) {
 audioRef.current.pause();
 setPlayingMsgId(null);
}
 const cached = ttsCacheRef.current.get(msgId);
 if (cached) {
 playAudio(cached, msgId);
 return;
}

 // Strategy: try streaming first (low latency), fallback to non-streaming
 const streamUrl = api.getTTSStreamUrl(content, emotion, settings.tts_voice);
 const audio = new Audio(streamUrl);
 audioRef.current = audio;
 setPlayingMsgId(msgId);

 let fallbackTriggered = false;
 const doFallback = async () => {
 if (fallbackTriggered) return;
 fallbackTriggered = true;
 try {
 const res = await api.synthesizeTTS(content, emotion, settings.tts_voice);
 if (res.audio_url) {
 ttsCacheRef.current.set(msgId, res.audio_url);
 playAudio(res.audio_url, msgId);
}
} catch (e) {
 setPlayingMsgId(null);
 audioRef.current = null;
}
};

 audio.onloadedmetadata = () => {
 if (audio.duration && isFinite(audio.duration)) {
 setAudioDuration(audio.duration);
}
};
 audio.ontimeupdate = () => {
 if (audio.duration && isFinite(audio.duration)) {
 setAudioProgress(audio.currentTime / audio.duration);
}
};
 audio.onended = () => {
 setPlayingMsgId(null);
 setAudioProgress(0);
 audioRef.current = null;
 ttsCacheRef.current.set(msgId, streamUrl);
};
 audio.onerror = () => {
 setAudioProgress(0);
 doFallback();
};
 audio.play().catch(() => {
 doFallback();
});
}, [playingMsgId, playAudio, emotion, settings.tts_voice]);

 const startNewChat = () => {
 if (isCamOn) stopCamera();
 const newSid = `ws_${Date.now().toString(36)}`;
 setSessionId(newSid);
 setMessages([{
 id: 'welcome',
 role: 'assistant',
 content: DEFAULT_WELCOME,
 timestamp: Date.now(),
}]);
 setInput('');
 setAttachedFiles([]);
 setFollowUpQuestions([]);
 setEditingMessageId(null);
 setEditDraft('');

 setVoiceCallMode(false);
 onNewSession?.();
 // 清除旧会话的本地持久化
 try {
 const keys = Object.keys(localStorage).filter((k) => k.startsWith('tent_messages_'));
 keys.forEach((k) => localStorage.removeItem(k));
 } catch {}
};

 return (
 <div
 className="flex-1 flex flex-col bg-surface-base min-h-0 relative"
 onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
 onDragLeave={(e) => {
 if (!e.currentTarget.contains(e.relatedTarget as Node)) {
 setIsDragOver(false);
 }
 }}
 onDrop={(e) => {
 e.preventDefault();
 setIsDragOver(false);
 const files = Array.from(e.dataTransfer.files);
 const oversized = files.filter((f) => f.size > 10 * 1024 * 1024);
 if (oversized.length > 0) {
 showToast(`文件过大：${oversized.map((f) => f.name).join('、')}（限10MB）`);
 }
 for (const file of files) {
 if (file.size > 10 * 1024 * 1024) continue;
 const form = new FormData();
 form.append('file', file);
 fetch('/api/v1/files/upload', {method: 'POST', body: form})
 .then((res) => res.json())
 .then((data) => {
 if (data.text) {
 setAttachedFiles((prev) => [...prev, {name: file.name, content: data.text, type: file.type}]);
} else {
 showToast(`解析失败：${file.name}`);
}
})
 .catch(() => showToast(`上传失败：${file.name}`));
}
}}
 >
 {isDragOver && (
 <div className="absolute inset-0 z-40 bg-accent-subtle/50 border-2 border-dashed border-accent flex items-center justify-center pointer-events-none">
 <div className="text-accent font-medium text-sm">释放以上传文件</div>
 </div>
 )}
 {/* Top Bar */}
 <div className="h-14 bg-surface-panel border-b border-line-subtle flex items-center justify-between px-6 shrink-0 z-20">
 <div className="flex items-center gap-3">
 {onOpenHistory && (
 <button
 onClick={onOpenHistory}
 className="md:hidden p-1.5 rounded-lg hover:bg-surface-overlay text-content-muted transition"
 title="历史会话"
 >
 <History className="w-4 h-4" />
 </button>
 )}
 <h1 className="font-bold text-content-primary">Tent OS</h1>
 <span className="text-xs text-content-muted">灵魂对讲机</span>
 {sessionId && (
 <span className="text-[10px] text-content-secondary font-mono ml-2">
 {sessionId.slice(0, 8)}...
 </span>
 )}
 </div>
 <div className="flex items-center gap-3">
 {/* Avatar Thumbnail */}
 {showAvatarThumbnail && (
 <div className="relative group">
 <button
 onClick={() => window.open('/soul', '_self')}
 className="w-8 h-8 rounded-full border-2 border-accent-border overflow-hidden flex items-center justify-center transition hover:scale-105 hover:border-violet-400"
 style={{
 background: avatarConfig?.skin?.base
 ? `linear-gradient(135deg, ${avatarConfig.skin.base} 0%, ${avatarConfig.hair?.base || '#4ecdc4'} 100%)`
 : 'linear-gradient(135deg, #a78bfa 0%, #4ecdc4 100%)',
}}
 title="你的数字形象 — 点击进入灵魂预览"
 >
 <span className="text-white text-xs font-bold">我</span>
 </button>
 <div className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-white border-line-subtle" />
 {/* Tooltip */}
 <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 px-2 py-1 bg-surface-panel text-content-primary text-[10px] rounded opacity-0 group-hover:opacity-100 transition pointer-events-none whitespace-nowrap z-30">
 数字形象预览
 </div>
 </div>
 )}
 {voiceRecorder.isRecording && (
 <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-500/10 px-2.5 py-1 rounded-full">
 <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
 语音录制中
 </div>
 )}
 {/* Emotion Avatar */}
 <EmotionAvatar emotion={emotion} size={28} isThinking={emotion === 'thinking'} className="mr-1" />
 {/* WebSocket 连接状态 */}
 {connectionStatus !== 'connected' && (
 <div className={`flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full border ${
 connectionStatus === 'connecting'
 ? 'bg-amber-500/10 text-amber-600 border-amber-200'
 : 'bg-red-500/10 text-red-500 border-red-200'
 }`}>
 <span className={`w-1.5 h-1.5 rounded-full ${connectionStatus === 'connecting' ? 'bg-amber-500 animate-pulse' : 'bg-red-500'}`} />
 <span>{connectionStatus === 'connecting' ? '连接中…' : '连接断开'}</span>
 </div>
 )}

 {/* 当前能力状态指示 */}
 <div className="flex items-center gap-1.5">
 {(enabledTools.web_search || enabledTools.file_ops || deepThinking) ? (
 <div className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-full bg-accent-subtle text-accent border border-accent-border">
 {enabledTools.web_search && <span>🔍</span>}
 {enabledTools.file_ops && <span>💻</span>}
 <span className="hidden sm:inline">{deepThinking ? '深度思考' : '工具已启'}</span>
 </div>
 ) : (
 <div className="text-[10px] px-2 py-1 rounded-full bg-surface-overlay text-content-muted">
 日常对话
 </div>
 )}
 </div>

 <button
 onClick={() => setShowMessageSearch(!showMessageSearch)}
 className={`text-xs px-3 py-1.5 rounded-lg transition font-medium ${
 showMessageSearch ? 'bg-accent-subtle text-accent' : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
}`}
 title="搜索消息"
 >
 <Search className="w-3.5 h-3.5" />
 </button>
 <button
 onClick={startNewChat}
 className="text-xs px-3 py-1.5 rounded-lg bg-accent-subtle text-accent hover:bg-accent-subtle transition font-medium"
 >
 + 新对话
 </button>
 <button
 onClick={isCamOn ? stopCamera : startCamera}
 className={`text-xs px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1 ${
 isCamOn
 ? 'bg-red-500/10 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30'
 : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
}`}
 title={isCamOn ? '关闭摄像头' : '开启摄像头采集形象'}
 >
 {isCamOn ? (
 <>
 <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
 <span>采集中</span>
 </>
 ) : (
 <>
 <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
 <span>摄像头</span>
 </>
 )}
 </button>
 <button
 onClick={() => setVoiceCallMode(!voiceCallMode)}
 className={`text-xs px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1 ${
 voiceCallMode
 ? 'bg-emerald-500/10 text-emerald-600 hover:bg-emerald-100 dark:hover:bg-emerald-900/30'
 : 'bg-surface-overlay text-content-muted hover:bg-surface-overlay'
}`}
 title="语音通话模式"
 >
 <Phone className="w-3.5 h-3.5" />
 {voiceCallMode ? '通话中' : '语音'}
 </button>
 <div className="flex items-center gap-1.5 text-xs text-content-muted">
 <span className="text-[10px]">灵魂</span>
 <span className="font-medium text-accent">{Math.round(completeness.overall * 100)}%</span>
 </div>
 </div>
 </div>



 {/* Chat Area */}
 <div ref={chatScrollRef} className={`flex-1 overflow-y-auto ${settings.compact_mode ? 'p-4 space-y-3' : 'p-6 space-y-5'}`}>
 {/* Empty State -->
 {messages.length <= 1 && !messages.some((m) => m.role === 'user') && (
 <div className="flex flex-col items-center justify-center py-12 text-center">
 <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-100 to-indigo-100 flex items-center justify-center mb-4">
 <Sparkles className="w-8 h-8 text-accent" />
 </div>
 <h3 className="text-lg font-medium text-content-primary mb-1">今天想聊点什么？</h3>
 <p className="text-sm text-content-muted mb-6 max-w-sm">每一次对话都在塑造你的数字灵魂。试着聊聊你的工作、家庭，或者任何想法。</p>
 <div className="flex flex-wrap justify-center gap-2 max-w-lg">
 {[
 {icon: <FileText className="w-3.5 h-3.5" />, label: '总结今天的会议', prompt: '帮我总结一下今天的会议要点'},
 {icon: <Lightbulb className="w-3.5 h-3.5" />, label: '给我一些人生建议', prompt: '给我一些人生建议'},
 {icon: <BookOpen className="w-3.5 h-3.5" />, label: '推荐一本书', prompt: '根据我的兴趣推荐一本书'},
 {icon: <Brain className="w-3.5 h-3.5" />, label: '分析我的决策风格', prompt: '分析我的决策风格'},
 ].map((action) => (
 <button
 key={action.label}
 onClick={() => doSend(action.prompt)}
 className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-surface-panel border border-line-active text-xs text-content-secondary hover:border-accent hover:text-accent hover:bg-accent-subtle transition"
 >
 {action.icon}
 {action.label}
 </button>
 ))}
 </div>
 </div>
 )}

 {/* Message Search */}
 {showMessageSearch && (
 <div className="sticky top-0 z-10 bg-surface-panel/80 backdrop-blur-sm border border-line-subtle rounded-xl p-3 mb-4">
 <div className="flex items-center gap-2">
 <Search className="w-4 h-4 text-content-muted shrink-0" />
 <input
 type="text"
 value={messageSearch}
 onChange={(e) => { setMessageSearch(e.target.value); setSearchResultIndex(0); }}
 placeholder="搜索历史消息..."
 className="flex-1 text-sm bg-transparent border-none outline-none text-content-primary placeholder-content-muted"
 autoFocus
 />
 {messageSearch && (
 <>
 <span className="text-[10px] text-content-muted tabular-nums">
 {(() => {
 const matches = messages.filter((m) => (m.content || '').toLowerCase().includes(messageSearch.toLowerCase()));
 return matches.length > 0 ? `${Math.min(searchResultIndex + 1, matches.length)} / ${matches.length}` : '0 / 0';
 })()}
 </span>
 <button
 onClick={() => {
 const matches = messages.filter((m) => (m.content || '').toLowerCase().includes(messageSearch.toLowerCase()));
 setSearchResultIndex((prev) => (prev > 0 ? prev - 1 : matches.length - 1));
 }}
 className="p-0.5 rounded hover:bg-surface-overlay text-content-muted"
 title="上一条"
 >
 <ChevronUp className="w-3.5 h-3.5" />
 </button>
 <button
 onClick={() => {
 const matches = messages.filter((m) => (m.content || '').toLowerCase().includes(messageSearch.toLowerCase()));
 setSearchResultIndex((prev) => (prev < matches.length - 1 ? prev + 1 : 0));
 }}
 className="p-0.5 rounded hover:bg-surface-overlay text-content-muted"
 title="下一条"
 >
 <ChevronDown className="w-3.5 h-3.5" />
 </button>
 <button
 onClick={() => setMessageSearch('')}
 className="text-xs text-content-muted hover:text-content-secondary px-2"
 >
 清除
 </button>
 </>
 )}
 <button
 onClick={() => {setShowMessageSearch(false); setMessageSearch(''); setSearchResultIndex(0);}}
 className="text-xs text-content-muted hover:text-content-secondary px-2"
 >
 关闭
 </button>
 </div>
 </div>
 )}

 {/* Messages */}
 {(() => {
 const searchMatches = messageSearch
 ? messages.filter((m) => (m.content || '').toLowerCase().includes(messageSearch.toLowerCase()))
 : [];
 const activeMatchId = searchMatches[searchResultIndex]?.id;
 const lastAiMsgId = messages.filter((m) => m.role === 'assistant' && !m.isStreaming).slice(-1)[0]?.id;
 return messages.filter((msg) => !showMessageSearch || !messageSearch || (msg.content || '').toLowerCase().includes(messageSearch.toLowerCase())).map((msg) => {
 const isSearchMatch = activeMatchId === msg.id;
 const isLastAiMsg = msg.id === lastAiMsgId;
 return (
 <div key={msg.id} data-msg-id={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
 {msg.role === 'system' ? (
 <div className={`bg-amber-500/10 border rounded-xl p-3 max-w-lg text-xs text-amber-700 dark:text-amber-300 flex items-center gap-2 ${isSearchMatch ? 'ring-2 ring-accent' : 'border-amber-300/50 dark:border-amber-800'}`}>
 <AlertTriangle className="w-4 h-4 shrink-0" />
 {msg.content || ''}
 </div>
 ) : (
 <div className={`max-w-xl ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1 relative group`}>
 <div className={`${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'} text-sm shadow-sm ${settings.compact_mode ? 'p-2.5' : 'p-3.5'} ${isSearchMatch ? 'ring-2 ring-accent' : ''}`}>
 {msg.id === 'welcome' && (
 <button
 onClick={() => setMessages((prev) => prev.filter((m) => m.id !== 'welcome'))}
 className="absolute top-1 right-1 p-1 rounded-md hover:bg-surface-overlay text-content-muted opacity-0 group-hover:opacity-100 transition"
 title="关闭欢迎消息"
 >
 <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
 </button>
 )}
 {settings.show_reasoning && msg.reasoning && (
 <div className="mb-2">
 <button
 onClick={() => {
 setExpandedReasoning((prev) => {
 const next = new Set(prev);
 if (next.has(msg.id)) next.delete(msg.id);
 else next.add(msg.id);
 return next;
});
}}
 className="flex items-center gap-1 text-[10px] text-amber-600 bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-900/30 px-2 py-0.5 rounded-full transition"
 >
 <Lightbulb className="w-3 h-3" />
 {expandedReasoning.has(msg.id) ? '隐藏思考过程' : '查看思考过程'}
 </button>
 {expandedReasoning.has(msg.id) && (
 <div className="mt-1.5 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/30 text-xs text-content-muted leading-relaxed">
 <MarkdownMessage content={msg.reasoning} />
 </div>
 )}
 </div>
 )}

 {editingMessageId === msg.id && msg.role === 'user' ? (
 <div className="flex flex-col gap-2">
 <textarea
 value={editDraft}
 onChange={(e) => setEditDraft(e.target.value)}
 className="w-full resize-none rounded-lg border border-line-active px-3 py-2 text-sm bg-surface-overlay text-content-primary placeholder-content-muted focus:outline-none focus:border-accent"
 rows={3}
 autoFocus
 />
 <div className="flex items-center gap-2">
 <button
 onClick={() => {
 const idx = messages.findIndex((m) => m.id === msg.id);
 if (idx >= 0 && editDraft.trim()) {
 setMessages((prev) => prev.slice(0, idx + 1).map((m) => m.id === msg.id ? {...m, content: editDraft.trim()} : m));
 setEditingMessageId(null);
 setEditDraft('');
 doSend(editDraft.trim());
 }
 }}
 className="text-xs px-3 py-1 rounded-lg bg-accent text-white hover:bg-accent-hover transition"
 >
 保存并重新发送
 </button>
 <button
 onClick={() => { setEditingMessageId(null); setEditDraft(''); }}
 className="text-xs px-3 py-1 rounded-lg bg-surface-overlay text-content-muted hover:text-content-secondary transition"
 >
 取消
 </button>
 </div>
 </div>
 ) : msg.isStreaming && !msg.content ? (
 <div className="flex items-center gap-1.5 text-content-muted">
 <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-bounce" style={{animationDelay: '0ms'}} />
 <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-bounce" style={{animationDelay: '150ms'}} />
 <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-bounce" style={{animationDelay: '300ms'}} />
 </div>
 ) : (
 <div className="leading-relaxed">
 <MarkdownMessage content={msg.content || ''} />
 {msg.isStreaming && (
 <span className="inline-block w-0.5 h-4 ml-0.5 bg-accent animate-pulse align-middle" />
 )}
 {msg.toolCalls && msg.toolCalls.length > 0 && (
 <div className="mt-2 space-y-1">
 {msg.toolCalls.map((tc, i) => (
 <div key={i} className="text-[11px] px-2 py-1 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
 <span className="font-medium">🔧 {tc.tool}</span>
 <span className="text-content-muted truncate">{typeof tc.arguments === 'string' ? tc.arguments : JSON.stringify(tc.arguments)}</span>
 </div>
 ))}
 </div>
 )}
 {msg.toolResults && msg.toolResults.length > 0 && (
 <div className="mt-2 space-y-1">
 {msg.toolResults.map((tr, i) => (
 <div key={i} className="text-[11px] px-2 py-1 rounded bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
 <span className="font-medium">✓ {tr.tool}</span>
 <span className="text-content-muted truncate">{typeof tr.result === 'string' ? tr.result : JSON.stringify(tr.result)}</span>
 </div>
 ))}
 </div>
 )}
 </div>
 )}
 </div>
 <div className="flex items-center gap-2 px-1">
 <span className="text-[10px] text-content-muted">
 {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'}) : ''}
 </span>
 {/* User message actions */}
 {!msg.isStreaming && msg.role === 'user' && (
 <>
 {msg.audioUrl && (
 <button
 onClick={() => {
 if (playingMsgId === msg.id) {
 audioRef.current?.pause();
 setPlayingMsgId(null);
} else {
 playAudio(msg.audioUrl!, msg.id);
}
}}
 className="text-[10px] text-content-muted hover:text-accent transition flex items-center gap-0.5"
 title={playingMsgId === msg.id ? '暂停' : '播放语音'}
 >
 {playingMsgId === msg.id ? (
 <>
 <span className="w-1 h-3 bg-violet-500 rounded-sm inline-block" />
 <span className="w-1 h-3 bg-violet-500 rounded-sm inline-block" />
 </>
 ) : (
 <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
 )}
 语音
 </button>
 )}
 <button
 onClick={() => {
 setEditingMessageId(msg.id);
 setEditDraft(msg.content || '');
 }}
 className={`text-[10px] text-content-muted hover:text-accent transition ${editingMessageId !== msg.id ? 'opacity-0 group-hover:opacity-100' : ''}`}
 title="编辑"
 >
 编辑
 </button>
 </>
 )}
 {!msg.isStreaming && msg.role === 'assistant' && msg.content && msg.id !== 'welcome' && (
 <>
 {settings.tts_enabled && (
 <>
 <button
 onClick={() => togglePlay(msg.id, msg.content || '')}
 className="text-[10px] text-content-muted hover:text-accent transition flex items-center gap-0.5"
 title={playingMsgId === msg.id ? '暂停' : '朗读'}
 >
 {playingMsgId === msg.id ? (
 <>
 <span className="w-1 h-3 bg-violet-500 rounded-sm inline-block" />
 <span className="w-1 h-3 bg-violet-500 rounded-sm inline-block" />
 </>
 ) : (
 <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
 )}
 {playingMsgId === msg.id ? '暂停' : '朗读'}
 </button>
 {playingMsgId === msg.id && audioDuration > 0 && (
 <div className="flex items-center gap-1">
 <div className="w-16 h-1 bg-surface-overlay rounded-full overflow-hidden">
 <div className="h-full bg-accent rounded-full transition-all" style={{ width: `${audioProgress * 100}%` }} />
 </div>
 <span className="text-[9px] text-content-muted tabular-nums">
 {Math.floor(audioProgress * audioDuration)}s / {Math.floor(audioDuration)}s
 </span>
 </div>
 )}
 </>
 )}
 <button
 onClick={() => navigator.clipboard.writeText(msg.content || '')}
 className="text-[10px] text-content-muted hover:text-accent transition opacity-0 group-hover:opacity-100"
 title="复制"
 >
 复制
 </button>
 <button
 onClick={() => handleFeedback(msg.id, 'like')}
 className={`text-[10px] transition opacity-0 group-hover:opacity-100 ${messageFeedback[msg.id] === 'like' ? 'text-emerald-500' : 'text-content-muted hover:text-emerald-500'}`}
 title="有用"
 >
 <ThumbsUp className="w-3 h-3" />
 </button>
 <button
 onClick={() => handleFeedback(msg.id, 'dislike')}
 className={`text-[10px] transition opacity-0 group-hover:opacity-100 ${messageFeedback[msg.id] === 'dislike' ? 'text-red-500' : 'text-content-muted hover:text-red-500'}`}
 title="没用"
 >
 <ThumbsDown className="w-3 h-3" />
 </button>
 <button
 onClick={() => {
 const idx = messages.findIndex((m) => m.id === msg.id);
 if (idx > 0 && messages[idx - 1].role === 'user') {
 const userMsg = messages[idx - 1];
 setMessages((prev) => prev.slice(0, idx - 1));
 doSend(userMsg.content);
}
}}
 className="text-[10px] text-content-muted hover:text-accent transition opacity-0 group-hover:opacity-100"
 title="重新生成"
 >
 <RefreshCw className="w-3 h-3" />
 </button>
 </>
 )}
 </div>
 {/* Follow-up questions — bound to last AI message */}
 {isLastAiMsg && followUpQuestions.length > 0 && !messages.some((m) => m.isStreaming) && (
 <div className="flex flex-wrap gap-2 mt-2 px-1">
 <span className="text-[10px] text-content-muted self-center">追问:</span>
 {followUpQuestions.map((q, i) => (
 <button
 key={i}
 onClick={() => doSend(q)}
 className="text-xs px-3 py-1.5 rounded-full bg-accent-subtle text-accent border border-accent-border hover:bg-accent-subtle hover:border-accent transition"
 >
 {q}
 </button>
 ))}
 </div>
 )}
 </div>
 )}
 </div>
 );
 });
 })()}
 <div ref={chatEndRef} />
 </div>

 {/* Camera Preview */}
 {isCamOn && showCamPreview && (
 <div className="bg-surface-panel border-t border-line-subtle px-4 py-2">
 <div className="max-w-3xl mx-auto flex items-center gap-3">
 <div className="relative w-32 h-24 rounded-xl overflow-hidden border border-line-subtle bg-surface-elevated shrink-0">
 <video ref={videoRef} className="w-full h-full object-cover" autoPlay muted playsInline />
 <div className="absolute inset-0 pointer-events-none">
 <div className="absolute top-0 left-0 right-0 h-0.5 bg-green-400/60 animate-scan" />
 </div>
 <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
 <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
 <span className="text-[9px] text-content-primary/80 font-medium">采集中</span>
 </div>
 <div className="absolute bottom-1 right-1 text-[9px] text-content-primary/60">每8秒保存</div>
 </div>
 <div className="flex-1">
 <p className="text-xs text-content-muted mb-1">摄像头正在采集你的形象数据</p>
 <p className="text-[10px] text-content-muted">这些数据用于构建你的数字形象，让你的数字灵魂更真实。</p>
 <div className="flex gap-2 mt-2">
 <button
 onClick={() => setShowCamPreview(false)}
 className="text-[10px] px-2 py-1 rounded-md bg-surface-overlay text-content-muted hover:bg-surface-overlay transition"
 >
 隐藏预览
 </button>
 <button
 onClick={stopCamera}
 className="text-[10px] px-2 py-1 rounded-md bg-red-500/10 text-red-500 hover:bg-red-100 transition"
 >
 停止采集
 </button>
 </div>
 </div>
 </div>
 </div>
 )}

 {/* Input Area */}
 <div className="p-4 bg-surface-panel border-t border-line-subtle">
 <div className="max-w-3xl mx-auto">
 {voiceRecorder.isRecording ? (
 <div className="relative rounded-xl border border-accent-border bg-accent-subtle px-4 py-3">
 <div className="flex items-center gap-3">
 <button
 ref={micButtonRef}
 onPointerUp={handleMicPointerUp}
 onPointerLeave={handleMicPointerUp}
 className="p-3 rounded-xl bg-red-100 text-red-500 shrink-0 animate-pulse"
 >
 <Mic className="w-5 h-5" />
 </button>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 mb-1.5">
 <span className="text-xs font-medium text-accent">正在聆听…</span>
 <span className="text-xs text-accent font-mono">
 {Math.floor(voiceRecorder.recordingTime / 60).toString().padStart(2, '0')}:
 {(voiceRecorder.recordingTime % 60).toString().padStart(2, '0')}
 </span>
 </div>
 <div className="flex items-center gap-0.5 h-6">
 {voiceRecorder.visualizerData.map((v, i) => (
 <div
 key={i}
 className="w-1 rounded-full bg-violet-400 transition-all duration-75"
 style={{height: `${Math.max(4, v * 24)}px`}}
 />
 ))}
 </div>
 <div className="mt-1 text-sm text-violet-800 min-h-[20px]">
 {voiceRecorder.transcript}
 <span className="text-accent">{voiceRecorder.interimTranscript}</span>
 {!voiceRecorder.transcript && !voiceRecorder.interimTranscript && (
 <span className="text-violet-300 text-xs">请说话…</span>
 )}
 </div>
 </div>
 </div>
 <p className="text-center text-[10px] text-accent mt-2">松开发送，同时保存为语音样本</p>
 </div>
 ) : voiceCallMode ? (
 <VoiceCallPanel
 onSendVoice={(text) => {
 const sid = sessionId || `ws_${Date.now().toString(36)}`;
 setSessionId(sid);
 setMessages((prev) => [
 ...prev,
 {id: `u_${Date.now()}`, role: 'user', content: text, timestamp: Date.now()},
 {id: `a_${Date.now()}`, role: 'assistant', content: '', isStreaming: true, timestamp: Date.now()},
 ]);
 send('chat.message', {session_id: sid, user_id: api.USER_ID, content: text, tools: enabledTools, deep_thinking: deepThinking});
 setEmotion('thinking');
}}
 onExit={() => setVoiceCallMode(false)}
 aiLoading={messages.some((m) => m.isStreaming)}
 lastAiReply={
 messages.length > 0 && messages[messages.length - 1].role === 'assistant' && !messages[messages.length - 1].isStreaming
 ? messages[messages.length - 1].content
 : null
}
 onPlayTTS={(content) => {
 const msgId = `call_${Date.now()}`;
 const streamUrl = api.getTTSStreamUrl(content, emotion, settings.tts_voice);
 const audio = new Audio(streamUrl);
 audioRef.current = audio;
 setPlayingMsgId(msgId);
 audio.onended = () => setPlayingMsgId(null);
 audio.onerror = () => setPlayingMsgId(null);
 audio.play().catch(() => setPlayingMsgId(null));
}}
 />
 ) : (
 <div className="flex flex-col gap-2">
 {/* Capability Toggles */}
 <div className="flex items-center gap-2 px-1">
 <button
 onClick={() => setEnabledTools((prev) => ({...prev, web_search: !prev.web_search}))}
 className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border transition ${
 enabledTools.web_search
 ? 'bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800/40'
 : 'bg-transparent text-content-muted border-line-subtle hover:border-line-active'
}`}
 title="允许 AI 搜索互联网"
 >
 <Globe className="w-3 h-3" />
 <span>联网搜索</span>
 </button>
 <button
 onClick={() => setEnabledTools((prev) => ({...prev, file_ops: !prev.file_ops}))}
 className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border transition ${
 enabledTools.file_ops
 ? 'bg-emerald-500/10 text-emerald-600 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/40'
 : 'bg-transparent text-content-muted border-line-subtle hover:border-line-active'
}`}
 title="允许 AI 执行本地命令和文件操作"
 >
 <Laptop className="w-3 h-3" />
 <span>本地操作</span>
 </button>
 <button
 onClick={() => setDeepThinking((prev) => !prev)}
 className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border transition ${
 deepThinking
 ? 'bg-accent-subtle text-accent border-accent-border/40'
 : 'bg-transparent text-content-muted border-line-subtle hover:border-line hover:border-line-active'
}`}
 title="AI 会先规划再执行复杂任务"
 >
 <Brain className="w-3 h-3" />
 <span>深度思考</span>
 </button>
 </div>
 <div className="flex gap-2 items-end">
 <button
 ref={micButtonRef}
 onPointerDown={handleMicPointerDown}
 onPointerUp={handleMicPointerUp}
 onPointerLeave={handleMicPointerUp}
 className="p-3 rounded-xl transition shrink-0 bg-surface-overlay hover:bg-surface-overlay active:bg-accent-subtle select-none"
 title="长按说话"
 >
 <Mic className="w-5 h-5 text-content-secondary" />
 </button>
 <input
 ref={fileInputRef}
 type="file"
 accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.json,.py,.js,.ts,.html,.css,.yaml,.yml,image/*"
 multiple
 className="hidden"
 onChange={async (e) => {
 const files = Array.from(e.target.files || []);
 const oversized = files.filter((f) => f.size > 10 * 1024 * 1024);
 if (oversized.length > 0) {
 showToast(`文件过大：${oversized.map((f) => f.name).join('、')}（限10MB）`);
 }
 for (const file of files) {
 if (file.size > 10 * 1024 * 1024) continue;
 const form = new FormData();
 form.append('file', file);
 try {
 const res = await fetch('/api/v1/files/upload', {method: 'POST', body: form});
 const data = await res.json();
 if (data.text) {
 setAttachedFiles((prev) => [...prev, {name: file.name, content: data.text, type: file.type}]);
} else {
 showToast(`解析失败：${file.name}`);
}
} catch {
 showToast(`上传失败：${file.name}`);
}
}
 if (fileInputRef.current) fileInputRef.current.value = '';
}}
 />
 <button
 onClick={() => fileInputRef.current?.click()}
 className="p-3 rounded-xl border border-line-subtle text-content-muted hover:text-accent hover:border-accent transition shrink-0"
 title="上传文件"
 >
 <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
 </button>
 <div className="flex-1 relative">
 {attachedFiles.length > 0 && (
 <div className="flex flex-wrap gap-1.5 mb-1.5">
 {attachedFiles.map((f, i) => (
 <span key={i} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full border border-blue-200">
 <Paperclip className="w-3 h-3" /> {f.name}
 <button onClick={() => setAttachedFiles((prev) => prev.filter((_, idx) => idx !== i))} className="text-blue-400 hover:text-blue-700 ml-0.5">×</button>
 </span>
 ))}
 </div>
 )}
 <textarea
 value={input}
 onChange={(e) => setInput(e.target.value)}
 onKeyDown={(e) => {
 if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
 e.preventDefault();
 const isStreaming = messages.some((m) => m.isStreaming);
 if (!isStreaming) {
 handleSend();
}
}
}}
 onCompositionStart={() => setIsComposing(true)}
 onCompositionEnd={() => setIsComposing(false)}
 rows={1}
 placeholder={attachedFiles.length > 0 ? `已附加 ${attachedFiles.length} 个文件，输入消息…` : '输入消息，或长按麦克风说话…'}
 className="w-full resize-none rounded-xl border border-line-active px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400 dark:focus:ring-violet-800 bg-surface-overlay text-content-primary placeholder-content-muted"
 style={{minHeight: 44, maxHeight: 120}}
 onInput={(e) => {
 const target = e.target as HTMLTextAreaElement;
 target.style.height = 'auto';
 target.style.height = Math.min(target.scrollHeight, 120) + 'px';
 }}
 onPaste={(e) => {
 // FIX: 阻止 macOS 微信复制的文件路径直接粘贴到输入框
 const text = e.clipboardData.getData('text/plain');
 if (text && text.includes('/Library/Containers/com.tencent.xinWeChat/')) {
 e.preventDefault();
 showToast('请直接拖放图片到聊天区域，不要从微信复制粘贴图片');
 }
 }}
 onDrop={(e) => {
 // FIX: 阻止拖放文件到 textarea 时插入文件路径文本
 e.preventDefault();
 }}
 />
 {messages.some((m) => m.isStreaming) ? (
 <button
 onClick={handleStop}
 className="absolute right-2 bottom-2 p-1.5 rounded-lg bg-red-500 text-white hover:bg-red-600 transition"
 title="停止生成"
 >
 <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
 </button>
 ) : (
 <button
 onClick={handleSend}
 disabled={connectionStatus !== 'connected'}
 className="absolute right-2 bottom-2 p-1.5 rounded-lg bg-violet-600 text-white hover:bg-violet-700 transition disabled:opacity-40 disabled:cursor-not-allowed"
 title={connectionStatus === 'connected' ? '发送' : '等待连接…'}
 >
 <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" /></svg>
 </button>
 )}
 </div>
 </div>
 </div>
 )}
 {voiceRecorder.error && (
 <p className="text-center text-xs text-red-500 mt-2">{voiceRecorder.error}</p>
 )}
 {!voiceRecorder.isRecording && !voiceRecorder.error && (
 <p className="text-center text-xs text-content-muted mt-2">对话内容用于构建你的数字灵魂模型</p>
 )}
 </div>
 </div>

 {/* Approval Modal */}
 {approvalRequest && (
 <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
 <div className="w-full max-w-md bg-surface-panel rounded-2xl shadow-2xl border border-line-subtle p-5 space-y-4">
 <div className="flex items-center gap-2 text-amber-500">
 <AlertTriangle className="w-5 h-5" />
 <h3 className="text-base font-semibold text-content-primary">操作审批</h3>
 </div>
 <p className="text-sm text-content-secondary">AI 请求执行以下操作，请确认是否批准：</p>
 <div className="p-3 rounded-lg bg-surface-base border border-line-subtle text-sm text-content-primary font-mono whitespace-pre-wrap max-h-40 overflow-auto">
 {approvalRequest.plan.summary || approvalRequest.plan.task || JSON.stringify(approvalRequest.plan, null, 2)}
 </div>
 <div className="flex items-center gap-3 justify-end">
 <button
 onClick={() => {
 api.submitApproval(approvalRequest.sessionId, false);
 setApprovalRequest(null);
 }}
 className="px-4 py-2 rounded-lg text-sm bg-surface-overlay text-content-secondary hover:bg-surface-elevated transition"
 >
 拒绝
 </button>
 <button
 onClick={() => {
 api.submitApproval(approvalRequest.sessionId, true);
 setApprovalRequest(null);
 }}
 className="px-4 py-2 rounded-lg text-sm bg-violet-600 text-white hover:bg-violet-700 transition"
 >
 批准
 </button>
 </div>
 </div>
 </div>
 )}

 {/* Toast */}
 {toastMsg && (
 <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-surface-panel border border-line-subtle shadow-lg text-sm text-content-primary animate-in fade-in slide-in-from-bottom-2 duration-200">
 {toastMsg}
 </div>
 )}
 </div>
 );
}
