import { useRef, useCallback, useState, useEffect } from 'react';
import { CanvasAvatar } from './CanvasAvatar';
import { useAvatarHome, type AvatarHomeSource } from '@/contexts/AvatarHomeContext';
import { useAIState } from '@/contexts/AIStateContext';

interface AvatarHomeButtonProps {
  source: AvatarHomeSource;
  size?: number;
  showLevelRing?: boolean;
  showParticles?: boolean;
  className?: string;
  onClick?: () => void;
  onLongPress?: () => void;
  onDoubleClick?: () => void;
  onPet?: () => void;
  title?: string;
}

export function AvatarHomeButton({
  source,
  size = 36,
  showLevelRing = false,
  showParticles = false,
  className = '',
  onClick,
  onLongPress,
  onDoubleClick,
  onPet,
  title = '按住拖拽解放我！',
}: AvatarHomeButtonProps) {
  const { state: homeState, summon, returnHome } = useAvatarHome();
  const { state: aiState } = useAIState();
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragData = useRef({ startX: 0, startY: 0, hasMoved: false });
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPressed = useRef(false);

  const isAway = homeState.mode === 'free' && homeState.homeSource === source;

  // 拖拽逻辑：用原生 DOM 事件，可靠
  const startDrag = useCallback((clientX: number, clientY: number) => {
    dragData.current = { startX: clientX, startY: clientY, hasMoved: false };
    isLongPressed.current = false;
    setIsDragging(true);

    longPressTimer.current = setTimeout(() => {
      isLongPressed.current = true;
      onLongPress?.();
    }, 600);
  }, [onLongPress]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    startDrag(e.clientX, e.clientY);
  }, [startDrag]);

  // 全局事件监听用 useEffect 管理，可靠
  useEffect(() => {
    if (!isDragging) return;

    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - dragData.current.startX;
      const dy = e.clientY - dragData.current.startY;
      if (Math.sqrt(dx * dx + dy * dy) > 6) {
        dragData.current.hasMoved = true;
        if (longPressTimer.current) {
          clearTimeout(longPressTimer.current);
          longPressTimer.current = null;
        }
      }
    };

    const onUp = () => {
      setIsDragging(false);
      if (longPressTimer.current) {
        clearTimeout(longPressTimer.current);
        longPressTimer.current = null;
      }
      if (dragData.current.hasMoved) {
        const rect = containerRef.current?.getBoundingClientRect();
        if (rect) summon(source, rect);
      }
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isDragging, summon, source]);

  const handleClick = useCallback(() => {
    if (!dragData.current.hasMoved && !isLongPressed.current && onClick) {
      onClick();
    }
  }, [onClick]);

  if (isAway) {
    return (
      <div
        ref={containerRef}
        className={`relative cursor-pointer ${className}`}
        onClick={returnHome}
        title="点击召回 Avatar"
      >
        <div
          className="rounded-full bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center"
          style={{ width: size, height: size }}
        >
          <span className="text-gray-400 text-xs">💤</span>
        </div>
        <div className="absolute -top-1 -right-1 w-3 h-3 bg-tent-500 rounded-full animate-pulse" />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative inline-block ${isDragging ? 'cursor-grabbing' : 'cursor-grab'} ${className}`}
      onMouseDown={onMouseDown}
      onClick={handleClick}
      onDoubleClick={onDoubleClick}
      title={title}
    >
      <CanvasAvatar
        emotion={aiState.emotion}
        persona={aiState.persona}
        size={size}
        level={1}
        isThinking={aiState.isThinking}
        isSpeaking={aiState.isSpeaking}
        vitals={size >= 120 ? aiState.vitals : undefined}
        isBeingPetted={aiState.isBeingPetted}
        currentSentence={aiState.currentSentence}
        showLevelRing={showLevelRing}
        showParticles={showParticles}
        onPet={onPet}
        animated={size >= 80} // Sidebar Logo (36px) 静态渲染，省 RAF/GPU
      />
      {isDragging && (
        <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] text-tent-500 whitespace-nowrap pointer-events-none bg-white/80 px-1.5 py-0.5 rounded-full shadow-sm">
          释放召唤！
        </div>
      )}
    </div>
  );
}
