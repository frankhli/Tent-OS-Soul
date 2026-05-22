import { useMemo } from 'react';

interface EmotionAvatarProps {
  emotion?: string;
  size?: number;
  isThinking?: boolean;
  className?: string;
}

const emotionConfig: Record<string, {
  color: string;
  bg: string;
  border: string;
  label: string;
  anim: string;
  shape: 'circle' | 'squircle' | 'sharp' | 'droplet';
  emoji: string;
}> = {
  happy: {
    color: '#f59e0b',
    bg: '#fffbeb',
    border: '#fde68a',
    label: '开心',
    anim: 'emotion-bounce',
    shape: 'squircle',
    emoji: '😊',
  },
  excited: {
    color: '#f97316',
    bg: '#fff7ed',
    border: '#fed7aa',
    label: '兴奋',
    anim: 'emotion-bounce-fast',
    shape: 'squircle',
    emoji: '🤩',
  },
  calm: {
    color: '#3b82f6',
    bg: '#eff6ff',
    border: '#bfdbfe',
    label: '平静',
    anim: 'emotion-breathe',
    shape: 'circle',
    emoji: '😌',
  },
  thinking: {
    color: '#8b5cf6',
    bg: '#f5f3ff',
    border: '#ddd6fe',
    label: '思考',
    anim: 'emotion-pulse-rotate',
    shape: 'circle',
    emoji: '🤔',
  },
  surprised: {
    color: '#ec4899',
    bg: '#fdf2f8',
    border: '#fbcfe8',
    label: '惊讶',
    anim: 'emotion-pop',
    shape: 'circle',
    emoji: '😲',
  },
  sad: {
    color: '#6b7280',
    bg: '#f3f4f6',
    border: '#e5e7eb',
    label: '难过',
    anim: 'emotion-sad-breathe',
    shape: 'droplet',
    emoji: '😢',
  },
  angry: {
    color: '#ef4444',
    bg: '#fef2f2',
    border: '#fecaca',
    label: '生气',
    anim: 'emotion-shake',
    shape: 'sharp',
    emoji: '😠',
  },
  listening: {
    color: '#10b981',
    bg: '#ecfdf5',
    border: '#a7f3d0',
    label: '聆听',
    anim: 'emotion-breathe',
    shape: 'circle',
    emoji: '👂',
  },
  neutral: {
    color: '#9ca3af',
    bg: '#f9fafb',
    border: '#e5e7eb',
    label: '中性',
    anim: 'emotion-breathe-slow',
    shape: 'circle',
    emoji: '😐',
  },
};

function getShapeClass(shape: string): string {
  switch (shape) {
    case 'squircle': return 'rounded-2xl';
    case 'sharp': return 'rounded-lg';
    case 'droplet': return 'rounded-t-2xl rounded-bl-2xl rounded-br-md';
    default: return 'rounded-full';
  }
}

export function EmotionAvatar({ emotion = 'neutral', size = 40, isThinking = false, className = '' }: EmotionAvatarProps) {
  const cfg = emotionConfig[emotion] || emotionConfig.neutral;
  const displayAnim = isThinking ? 'emotion-pulse-rotate' : cfg.anim;
  const displayShape = isThinking ? 'circle' : cfg.shape;

  const innerSize = useMemo(() => Math.round(size * 0.45), [size]);

  return (
    <div
      className={`relative flex items-center justify-center shrink-0 transition-all duration-500 ${getShapeClass(displayShape)} ${displayAnim} ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: cfg.bg,
        border: `2px solid ${cfg.border}`,
      }}
      title={isThinking ? '思考中...' : cfg.label}
    >
      {/* 内核 */}
      <div
        className={`${getShapeClass(displayShape)} transition-all duration-500 flex items-center justify-center`}
        style={{
          width: innerSize,
          height: innerSize,
          backgroundColor: cfg.color,
          boxShadow: `0 0 ${size * 0.3}px ${cfg.color}40`,
        }}
      >
        <span style={{ fontSize: Math.round(size * 0.35) }}>{cfg.emoji}</span>
      </div>
      {/* 思考时的环绕点 */}
      {isThinking && (
        <>
          <span className="absolute w-1.5 h-1.5 rounded-full bg-violet-400 emotion-orbit" style={{ animationDelay: '0ms' }} />
          <span className="absolute w-1 h-1 rounded-full bg-violet-300 emotion-orbit" style={{ animationDelay: '400ms' }} />
          <span className="absolute w-1 h-1 rounded-full bg-violet-300 emotion-orbit" style={{ animationDelay: '800ms' }} />
        </>
      )}
    </div>
  );
}
