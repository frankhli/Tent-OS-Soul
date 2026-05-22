import { useState } from 'react';
import { Camera, CameraOff, Smile, Frown, Angry, Meh, AlertCircle } from 'lucide-react';

interface CameraScannerProps {
  isActive: boolean;
  lastEmotion: string;
  confidence: number;
  error: string | null;
  onStart: () => void;
  onStop: () => void;
}

const EMOTION_DISPLAY: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  happy: { label: '开心', icon: <Smile className="w-4 h-4" />, color: 'text-amber-500' },
  sad: { label: '难过', icon: <Frown className="w-4 h-4" />, color: 'text-blue-500' },
  angry: { label: '生气', icon: <Angry className="w-4 h-4" />, color: 'text-red-500' },
  surprised: { label: '惊讶', icon: <AlertCircle className="w-4 h-4" />, color: 'text-purple-500' },
  neutral: { label: '平静', icon: <Meh className="w-4 h-4" />, color: 'text-gray-500' },
};

export function CameraScanner({ isActive, lastEmotion, confidence, error, onStart, onStop }: CameraScannerProps) {
  const [showPreview, setShowPreview] = useState(false);

  const emotionInfo = EMOTION_DISPLAY[lastEmotion] || EMOTION_DISPLAY.neutral;

  return (
    <div className="flex flex-col items-center gap-2">
      {/* 情绪指示器 */}
      {isActive && (
        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full bg-white border border-gray-200 shadow-sm text-xs ${emotionInfo.color}`}>
          {emotionInfo.icon}
          <span>{emotionInfo.label}</span>
          <span className="text-[10px] text-gray-400">({(confidence * 100).toFixed(0)}%)</span>
        </div>
      )}

      {/* 摄像头预览区域 */}
      {isActive && showPreview && (
        <div className="relative w-40 h-30 bg-black rounded-lg overflow-hidden border border-gray-200 shadow-sm">
          <video
            id="vision-video-preview"
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
          />
          {/* 扫描线动画 */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-green-400/60 animate-scan" />
          </div>
          <div className="absolute bottom-1 left-1 right-1 flex items-center justify-between">
            <span className="text-[10px] text-white bg-black/50 px-1.5 py-0.5 rounded">
              检测中
            </span>
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded border border-red-200 max-w-[200px] text-center">
          {error}
        </div>
      )}

      {/* 控制按钮 */}
      <div className="flex items-center gap-2">
        {isActive ? (
          <>
            <button
              onClick={() => setShowPreview((s) => !s)}
              className="text-[10px] px-2 py-1 rounded-md bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
            >
              {showPreview ? '隐藏预览' : '显示预览'}
            </button>
            <button
              onClick={onStop}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors"
            >
              <CameraOff className="w-3 h-3" />
              关闭
            </button>
          </>
        ) : (
          <button
            onClick={onStart}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-tent-600 bg-tent-50 hover:bg-tent-100 border border-tent-200 transition-colors"
          >
            <Camera className="w-3 h-3" />
            开启摄像头
          </button>
        )}
      </div>
    </div>
  );
}
