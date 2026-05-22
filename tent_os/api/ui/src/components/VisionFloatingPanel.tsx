import { useRef, useState, useEffect, useCallback } from 'react';
import { CameraOff, Eye, Move, Maximize2, Minimize2, Smile, Frown, Angry, AlertCircle, Meh, Camera, Aperture, Scan, Radio } from 'lucide-react';

interface YoloDetection {
  label: string;
  confidence: number;
  normalized: { x: number; y: number; width: number; height: number };
  isHighInterest: boolean;
}

interface VisionFloatingPanelProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  detectedObjects: YoloDetection[];
  lastEmotion: string;
  emotionConfidence: number;
  cameraActive: boolean;
  cameraMirror: boolean;
  devices?: Array<{ deviceId: string; label: string; facing?: string }>;
  selectedDeviceId?: string | null;
  onStart: () => void;
  onStop: () => void;
  onToggleMirror: () => void;
  onSwitchCamera?: (deviceId: string) => void;
  onCapture?: () => void;
}

const EMOTION_DISPLAY: Record<string, { label: string; icon: React.ReactNode; color: string; bg: string }> = {
  happy: { label: '开心', icon: <Smile className="w-3 h-3" />, color: 'text-amber-600', bg: 'bg-amber-50' },
  sad: { label: '难过', icon: <Frown className="w-3 h-3" />, color: 'text-blue-600', bg: 'bg-blue-50' },
  angry: { label: '生气', icon: <Angry className="w-3 h-3" />, color: 'text-red-600', bg: 'bg-red-50' },
  surprised: { label: '惊讶', icon: <AlertCircle className="w-3 h-3" />, color: 'text-purple-600', bg: 'bg-purple-50' },
  neutral: { label: '平静', icon: <Meh className="w-3 h-3" />, color: 'text-gray-600', bg: 'bg-gray-50' },
};

const LS_VISION_POS = 'tent_os_vision_pos';
const LS_VISION_MODE = 'tent_os_vision_mode';

export function VisionFloatingPanel({
  videoRef,
  detectedObjects,
  lastEmotion,
  emotionConfidence,
  cameraActive,
  cameraMirror,
  devices = [],
  selectedDeviceId,
  onStart,
  onStop,
  onToggleMirror,
  onSwitchCamera,
  onCapture,
}: VisionFloatingPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previewVideoRef = useRef<HTMLVideoElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const [showCameraSelect, setShowCameraSelect] = useState(false);
  const [showObjectList, setShowObjectList] = useState(false);
  const [lastCapture, setLastCapture] = useState<string | null>(null);
  const [showCapturePreview, setShowCapturePreview] = useState(false);

  const [mode, setMode] = useState<'expanded' | 'minimized'>(() => {
    try { return (localStorage.getItem(LS_VISION_MODE) as 'expanded' | 'minimized') || 'expanded'; }
    catch { return 'expanded'; }
  });
  const [position, setPosition] = useState(() => {
    try {
      const saved = localStorage.getItem(LS_VISION_POS);
      if (saved) return JSON.parse(saved);
    } catch {}
    return { x: window.innerWidth - 280, y: window.innerHeight - 240 };
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  const emotionInfo = EMOTION_DISPLAY[lastEmotion] || EMOTION_DISPLAY.neutral;

  // 同步 hidden video stream 到 visible preview video
  useEffect(() => {
    const hiddenVideo = videoRef.current;
    const previewVideo = previewVideoRef.current;
    if (!hiddenVideo || !previewVideo) return;

    const syncStream = () => {
      if (hiddenVideo.srcObject && previewVideo.srcObject !== hiddenVideo.srcObject) {
        previewVideo.srcObject = hiddenVideo.srcObject;
        previewVideo.play().catch(() => {});
      }
    };

    syncStream();
    hiddenVideo.addEventListener('loadedmetadata', syncStream);
    return () => {
      hiddenVideo.removeEventListener('loadedmetadata', syncStream);
    };
  }, [cameraActive, videoRef]);

  // YOLO 检测框绘制
  useEffect(() => {
    const canvas = overlayCanvasRef.current;
    const video = previewVideoRef.current;
    if (!canvas || !video || !cameraActive) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const obj of detectedObjects) {
      let x = obj.normalized.x * canvas.width;
      const y = obj.normalized.y * canvas.height;
      const ow = obj.normalized.width * canvas.width;
      const oh = obj.normalized.height * canvas.height;

      if (cameraMirror) {
        x = canvas.width - x - ow;
      }

      const color = obj.isHighInterest ? '#ef4444' : '#22c55e';
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, ow, oh);

      const label = `${obj.label} ${(obj.confidence * 100).toFixed(0)}%`;
      ctx.font = 'bold 11px sans-serif';
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = color;
      ctx.fillRect(x, y - 14, tw + 6, 14);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, x + 3, y - 3);
    }
  }, [detectedObjects, cameraActive, cameraMirror]);

  // 拖拽逻辑
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!panelRef.current) return;
    setIsDragging(true);
    dragOffset.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
  }, [position]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (e: MouseEvent) => {
      const newX = Math.max(0, Math.min(window.innerWidth - 100, e.clientX - dragOffset.current.x));
      const newY = Math.max(0, Math.min(window.innerHeight - 40, e.clientY - dragOffset.current.y));
      setPosition({ x: newX, y: newY });
    };
    const handleUp = () => {
      setIsDragging(false);
      try { localStorage.setItem(LS_VISION_POS, JSON.stringify(position)); }
      catch {}
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [isDragging, position]);

  const toggleMode = () => {
    const next = mode === 'expanded' ? 'minimized' : 'expanded';
    setMode(next);
    try { localStorage.setItem(LS_VISION_MODE, next); }
    catch {}
  };

  // 截图功能
  const handleCapture = useCallback(() => {
    const video = previewVideoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    if (cameraMirror) {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
    setLastCapture(dataUrl);
    setShowCapturePreview(true);
    setTimeout(() => setShowCapturePreview(false), 3000);
    onCapture?.();
  }, [cameraMirror, onCapture]);

  // 最小化态：药丸形态
  if (mode === 'minimized') {
    return (
      <div
        ref={panelRef}
        className="fixed z-50 select-none"
        style={{ left: position.x, top: position.y, cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full shadow-lg border transition-all ${
            cameraActive ? 'bg-white border-gray-200' : 'bg-gray-100 border-gray-200 opacity-60'
          }`}
          onMouseDown={handleMouseDown}
        >
          {cameraActive ? (
            <>
              <div className={`w-2 h-2 rounded-full ${emotionInfo.bg.replace('bg-', 'bg-').replace('50', '400')} animate-pulse`} />
              <span className={`text-[10px] font-medium ${emotionInfo.color}`}>
                {emotionInfo.label} {(emotionConfidence * 100).toFixed(0)}%
              </span>
              {detectedObjects.length > 0 && (
                <span className="text-[10px] text-gray-400">· {detectedObjects.length}物体</span>
              )}
              <button onClick={(e) => { e.stopPropagation(); toggleMode(); }} className="ml-1 text-gray-400 hover:text-gray-600">
                <Maximize2 className="w-3 h-3" />
              </button>
            </>
          ) : (
            <>
              <CameraOff className="w-3 h-3 text-gray-400" />
              <span className="text-[10px] text-gray-500">视觉关闭</span>
              <button onClick={(e) => { e.stopPropagation(); onStart(); }} className="ml-1 text-tent-500 hover:text-tent-600">
                <Eye className="w-3 h-3" />
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  // 展开态
  return (
    <div
      ref={panelRef}
      className="fixed z-50 select-none"
      style={{
        left: position.x,
        top: position.y,
        cursor: isDragging ? 'grabbing' : 'default',
      }}
    >
      <div className="bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden w-[280px]">
        {/* 标题栏 */}
        <div
          className="flex items-center justify-between px-2.5 py-1.5 bg-gray-50 border-b border-gray-100"
          onMouseDown={handleMouseDown}
          style={{ cursor: 'grab' }}
        >
          <div className="flex items-center gap-1.5">
            <Move className="w-3 h-3 text-gray-400" />
            <span className="text-[11px] font-medium text-gray-600">视觉感知</span>
            {cameraActive && (
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            )}
          </div>
          <div className="flex items-center gap-0.5">
            <button onClick={toggleMode} className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600" title="最小化">
              <Minimize2 className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* 视频区域 */}
        <div className="relative bg-black" style={{ height: 180 }}>
          {cameraActive ? (
            <>
              <video
                ref={previewVideoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
                style={{ transform: cameraMirror ? 'scaleX(-1)' : 'none' }}
              />
              <canvas
                ref={overlayCanvasRef}
                className="absolute inset-0 w-full h-full pointer-events-none"
              />
              {/* 扫描线 */}
              <div className="absolute inset-0 pointer-events-none overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-green-400/40 animate-scan" />
              </div>
              {/* 情绪浮层 */}
              <div className="absolute top-2 left-2">
                <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium ${emotionInfo.bg} ${emotionInfo.color} border border-white/30 backdrop-blur-sm`}>
                  {emotionInfo.icon}
                  <span>{emotionInfo.label} {(emotionConfidence * 100).toFixed(0)}%</span>
                </div>
              </div>
              {/* 物体数量 */}
              {detectedObjects.length > 0 && (
                <div className="absolute top-2 right-2">
                  <div className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-black/50 text-white backdrop-blur-sm">
                    {detectedObjects.length} 个物体
                  </div>
                </div>
              )}
              {/* 截图预览 */}
              {showCapturePreview && lastCapture && (
                <div className="absolute bottom-2 right-2 animate-in fade-in zoom-in-95 duration-300">
                  <div className="w-16 h-12 rounded border-2 border-white shadow-lg overflow-hidden">
                    <img src={lastCapture} alt="capture" className="w-full h-full object-cover" />
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <CameraOff className="w-8 h-8 text-gray-600" />
              <span className="text-xs text-gray-500">摄像头未开启</span>
              <button
                onClick={onStart}
                className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-medium text-white bg-tent-500 hover:bg-tent-600 transition-colors"
              >
                <Eye className="w-3 h-3" />
                开启视觉感知
              </button>
            </div>
          )}
        </div>

        {/* 底部控制栏 */}
        {cameraActive && (
          <div className="px-2.5 py-1.5 bg-gray-50 border-t border-gray-100 space-y-1.5">
            {/* 第一行控制 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button
                  onClick={onToggleMirror}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors ${
                    cameraMirror
                      ? 'bg-tent-50 text-tent-600 border-tent-200'
                      : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  镜像{cameraMirror ? '开' : '关'}
                </button>
                {/* 截图按钮 */}
                <button
                  onClick={handleCapture}
                  className="flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-medium border bg-white text-gray-500 border-gray-200 hover:bg-gray-100 transition-colors"
                  title="截图"
                >
                  <Camera className="w-2.5 h-2.5" />
                  截图
                </button>
                {/* 物体列表按钮 */}
                <button
                  onClick={() => setShowObjectList(!showObjectList)}
                  className={`flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-medium border transition-colors ${
                    showObjectList ? 'bg-tent-50 text-tent-600 border-tent-200' : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  <Scan className="w-2.5 h-2.5" />
                  物体
                </button>
              </div>
              <button
                onClick={onStop}
                className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors"
              >
                <CameraOff className="w-3 h-3" />
                关闭
              </button>
            </div>

            {/* 摄像头选择 */}
            {devices.length > 1 && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowCameraSelect(!showCameraSelect)}
                  className="flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-medium border bg-white text-gray-500 border-gray-200 hover:bg-gray-100 transition-colors"
                >
                  <Aperture className="w-2.5 h-2.5" />
                  {showCameraSelect ? '隐藏' : '切换摄像头'}
                </button>
                {showCameraSelect && (
                  <div className="flex-1 flex items-center gap-1 overflow-x-auto">
                    {devices.map((device) => (
                      <button
                        key={device.deviceId}
                        onClick={() => {
                          onSwitchCamera?.(device.deviceId);
                          setShowCameraSelect(false);
                        }}
                        className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-medium border transition-colors ${
                          selectedDeviceId === device.deviceId
                            ? 'bg-tent-50 text-tent-600 border-tent-200'
                            : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-100'
                        }`}
                        title={device.label}
                      >
                        {device.facing === 'environment' ? '📷' : '🤳'}
                        {device.label.length > 8 ? device.label.slice(0, 8) + '...' : device.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 物体列表 */}
            {showObjectList && detectedObjects.length > 0 && (
              <div className="bg-white rounded border border-gray-200 p-1.5 max-h-24 overflow-y-auto">
                <div className="flex flex-wrap gap-1">
                  {detectedObjects.map((obj, idx) => (
                    <span
                      key={`${obj.label}-${idx}`}
                      className={`text-[9px] px-1.5 py-0.5 rounded border font-medium ${
                        obj.isHighInterest
                          ? 'bg-red-50 text-red-600 border-red-200'
                          : 'bg-green-50 text-green-600 border-green-200'
                      }`}
                    >
                      {obj.label} {(obj.confidence * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 远程摄像头提示 */}
            <div className="flex items-center gap-1 text-[9px] text-gray-400">
              <Radio className="w-2.5 h-2.5" />
              <span>支持本机/网络/手机摄像头</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
