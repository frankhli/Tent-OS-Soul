import { useState, useEffect, useRef, useCallback } from 'react';
import { Bot, ChevronDown, Sparkles, Volume2 } from 'lucide-react';
import { Live2DAvatar } from './Live2DAvatar';
import { startTtsLipSync } from '@/utils/lipsync';

interface AIAvatarFloatingProps {
  emotion?: string;
  characterName?: string;
  avatarType?: string;
  onToggleExpand?: (expanded: boolean) => void;
}

const EMOTION_CONFIG: Record<string, { label: string; emoji: string; color: string; bgColor: string; animation: string; speakText: string }> = {
  happy: { label: '开心', emoji: '😊', color: 'text-amber-600', bgColor: 'bg-amber-50', animation: 'animate-bounce', speakText: '很高兴见到你！' },
  sad: { label: '难过', emoji: '😢', color: 'text-blue-600', bgColor: 'bg-blue-50', animation: 'opacity-70', speakText: '别难过，我在呢。' },
  excited: { label: '兴奋', emoji: '🤩', color: 'text-pink-600', bgColor: 'bg-pink-50', animation: 'animate-pulse', speakText: '太棒了！' },
  confused: { label: '困惑', emoji: '😕', color: 'text-purple-600', bgColor: 'bg-purple-50', animation: 'animate-spin-slow', speakText: '让我再想想...' },
  proud: { label: '自豪', emoji: '😌', color: 'text-tent-600', bgColor: 'bg-tent-50', animation: 'shadow-glow', speakText: '任务完成得很漂亮！' },
  sleepy: { label: '困倦', emoji: '😴', color: 'text-gray-600', bgColor: 'bg-gray-50', animation: 'opacity-60', speakText: '有点困了...' },
  listening: { label: '聆听', emoji: '👂', color: 'text-green-600', bgColor: 'bg-green-50', animation: '', speakText: '我在听，请说。' },
};

export function AIAvatarFloating({ emotion = 'listening', characterName = 'AI助理', avatarType = 'live2d' }: AIAvatarFloatingProps) {
  const [expanded, setExpanded] = useState(false);
  const [prevEmotion, setPrevEmotion] = useState(emotion);
  const [animating, setAnimating] = useState(false);
  const [mouthOpen, setMouthOpen] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const stopSpeakRef = useRef<(() => void) | null>(null);

  const config = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.listening;

  // 情绪变化时触发动画 + 自动说话
  useEffect(() => {
    if (emotion !== prevEmotion) {
      setAnimating(true);
      setPrevEmotion(emotion);
      const timer = setTimeout(() => setAnimating(false), 1000);
      
      // 情绪变化时自动TTS（Web Speech API）
      if (window.speechSynthesis && !isSpeaking) {
        handleSpeak();
      }
      
      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emotion]);

  const handleSpeak = useCallback(() => {
    if (isSpeaking) {
      // 停止当前说话
      if (stopSpeakRef.current) {
        stopSpeakRef.current();
        stopSpeakRef.current = null;
      }
      setIsSpeaking(false);
      setMouthOpen(0);
      return;
    }
    
    setIsSpeaking(true);
    const stop = startTtsLipSync(
      config.speakText,
      (open) => setMouthOpen(open),
      () => {
        setIsSpeaking(false);
        setMouthOpen(0);
        stopSpeakRef.current = null;
      }
    );
    stopSpeakRef.current = stop;
  }, [config.speakText, isSpeaking]);

  // 清理
  useEffect(() => {
    return () => {
      if (stopSpeakRef.current) {
        stopSpeakRef.current();
      }
    };
  }, []);

  if (!expanded) {
    // 收起状态：小圆点头像 + 情绪徽章
    return (
      <div className="fixed bottom-20 right-4 z-50 flex flex-col items-end gap-2">
        <button
          onClick={() => setExpanded(true)}
          className={`relative w-12 h-12 rounded-full bg-gradient-to-br from-tent-500 to-tent-700 flex items-center justify-center shadow-lg hover:scale-110 transition-transform ${animating ? config.animation : ''}`}
          title={`${characterName} - ${config.label}`}
        >
          <Bot className="w-6 h-6 text-white" />
          {/* 情绪徽章 */}
          <span className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center text-xs bg-white rounded-full shadow border border-gray-100">
            {config.emoji}
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-20 right-4 z-50 w-72 bg-white rounded-2xl border border-gray-200 shadow-xl overflow-hidden">
      {/* 头部 */}
      <div className="relative bg-gradient-to-br from-tent-500 to-tent-700 p-4 text-white">
        <button
          onClick={() => setExpanded(false)}
          className="absolute top-2 right-2 p-1 rounded-full hover:bg-white/20 transition-colors"
        >
          <ChevronDown className="w-4 h-4 text-white" />
        </button>
        
        {/* Live2D 或 CSS 占位 */}
        <div className="flex justify-center mb-2">
          {avatarType === 'live2d' ? (
            <Live2DAvatar
              emotion={emotion}
              mouthOpen={mouthOpen}
              width={260}
              height={300}
              scale={0.28}
            />
          ) : (
            <div className={`w-16 h-16 rounded-full bg-white/20 flex items-center justify-center mb-2 ${animating ? config.animation : ''}`}>
              <span className="text-3xl">{config.emoji}</span>
            </div>
          )}
        </div>
        
        <h4 className="text-center text-sm font-semibold">{characterName}</h4>
        <p className="text-center text-[10px] text-white/80 mt-0.5">
          当前状态: {config.label}
        </p>
      </div>

      {/* 快捷操作 */}
      <div className="p-3 space-y-2">
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${config.bgColor}`}>
          <Sparkles className={`w-3.5 h-3.5 ${config.color}`} />
          <span className={`text-xs ${config.color}`}>
            {emotion === 'proud' ? '任务完成，感到自豪' :
             emotion === 'happy' ? '很高兴为你服务' :
             emotion === 'sad' ? '有点难过，但会努力' :
             emotion === 'excited' ? '太棒了，继续加油！' :
             emotion === 'confused' ? '让我再想想...' :
             emotion === 'sleepy' ? '有点困了...' :
             '正在认真聆听'}
          </span>
        </div>
        
        {/* TTS 说话按钮 */}
        <button
          onClick={handleSpeak}
          className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
            isSpeaking
              ? 'bg-red-50 text-red-600 border border-red-200'
              : 'bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100'
          }`}
        >
          <Volume2 className="w-3 h-3" />
          {isSpeaking ? '停止说话' : '让我说句话'}
        </button>
        
        <div className="text-[10px] text-gray-400 text-center">
          情绪会随任务和用户状态变化
        </div>
      </div>
    </div>
  );
}
