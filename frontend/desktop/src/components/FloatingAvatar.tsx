import { useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { CanvasAvatar } from './CanvasAvatar';
import {
 Hand, Home,
} from 'lucide-react';

interface FloatingAvatarProps {
 emotion?: string;
 isSpeaking?: boolean;
 currentSentence?: string | null;
 appearanceConfig?: any;
 initialPos?: { x: number; y: number };
 onGoHome: () => void;
}

export function FloatingAvatar({
 emotion = 'calm',
 isSpeaking = false,
 currentSentence = null,
 appearanceConfig,
 initialPos,
 onGoHome,
}: FloatingAvatarProps) {
 const [pos, setPos] = useState(initialPos || {
 x: typeof window !== 'undefined' ? window.innerWidth - 260 : 100,
 y: typeof window !== 'undefined' ? window.innerHeight - 300 : 100,
 });
 const [isDragging, setIsDragging] = useState(false);
 const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
 const [isBeingPetted, setIsBeingPetted] = useState(false);
 const [showHome, setShowHome] = useState(false);

 const SIZE = 220;

 const handleMouseDown = useCallback((e: React.MouseEvent) => {
 setIsDragging(true);
 setDragOffset({
 x: e.clientX - pos.x,
 y: e.clientY - pos.y,
 });
 }, [pos]);

 const handleMouseMove = useCallback((e: MouseEvent) => {
 if (!isDragging) return;
 setPos({
 x: Math.max(0, Math.min(window.innerWidth - SIZE, e.clientX - dragOffset.x)),
 y: Math.max(0, Math.min(window.innerHeight - SIZE, e.clientY - dragOffset.y)),
 });
 }, [isDragging, dragOffset]);

 const handleMouseUp = useCallback(() => {
 setIsDragging(false);
 }, []);

 const handlePet = () => {
 setIsBeingPetted(true);
 setTimeout(() => setIsBeingPetted(false), 1500);
 };

 const portalContent = (
 <div
 className="fixed z-[9999] select-none"
 style={{
 left: pos.x,
 top: pos.y,
 cursor: isDragging ? 'grabbing' : 'grab',
 }}
 onMouseEnter={() => setShowHome(true)}
 onMouseLeave={() => setShowHome(false)}
 >
 {/* 拖拽层 */}
 <div
 className="absolute inset-0"
 style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
 onMouseDown={handleMouseDown}
 onMouseMove={(e) => { if (isDragging) e.preventDefault(); }}
 onMouseUp={handleMouseUp}
 onMouseLeave={handleMouseUp}
 onDoubleClick={(e) => { e.stopPropagation(); onGoHome(); }}
 />

 {/* 数字人 — 无框 */}
 <div className="relative pointer-events-none">
 <CanvasAvatar
 emotion={emotion}
 isSpeaking={isSpeaking}
 isBeingPetted={isBeingPetted}
 currentSentence={currentSentence}
 size={SIZE}
 animated={true}
 scale={1}
 showParticles={true}
 appearanceConfig={appearanceConfig}
 onPet={handlePet}
 />
 </div>

 {/* 回家按钮 — 平时隐藏，hover 显示 */}
 <div
 className={`absolute -top-2 -right-2 transition-all duration-200 ${
 showHome ? 'opacity-100 scale-100' : 'opacity-0 scale-75 pointer-events-none'
 }`}
 >
 <button
 onClick={(e) => { e.stopPropagation(); onGoHome(); }}
 className="p-1.5 rounded-full bg-surface-panel/80 backdrop-blur text-content-muted hover:text-accent border border-line-subtle/50 shadow-lg transition"
 title="双击数字人也可回家"
 >
 <Home className="w-3.5 h-3.5" />
 </button>
 </div>
 </div>
 );

 return createPortal(portalContent, document.body);
}
