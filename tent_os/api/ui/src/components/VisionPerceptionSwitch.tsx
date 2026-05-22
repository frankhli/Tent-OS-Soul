/**
 * VisionPerceptionSwitch — 视觉感知开关
 *
 * 功能:
 * 1. 一键开启/关闭摄像头 VLM 感知
 * 2. 显示当前感知状态（场景、人数、物体）
 * 3. 将 VLM 结果写入 SpacetimeContext
 *
 * 补齐 PRD 缺口: 摄像头 → VLM → 空间记忆的感知闭环
 */
import { useCallback } from 'react';
import { useCamera } from '@/hooks/useVisionCamera';
import { useSpacetime } from '@/contexts/SpacetimeContext';
import { Camera, CameraOff, Eye, Users, Lightbulb, Sparkles, Loader2 } from 'lucide-react';

export function VisionPerceptionSwitch() {
  const { setVisionPerception, state: spacetime } = useSpacetime();

  const handlePerception = useCallback((result: unknown) => {
    const r = result as Record<string, unknown> | undefined;
    if (!r) return;
    setVisionPerception({
      roomId: 'living_room',
      sceneType: String(r.scene_type || 'unknown'),
      sceneDescription: String(r.scene_description || ''),
      objects: Array.isArray(r.objects)
        ? r.objects.map((o: unknown) => {
            const obj = o as Record<string, unknown>;
            return {
              name: String(obj.name || ''),
              location: String(obj.location || ''),
              confidence: typeof obj.confidence === 'number' ? obj.confidence : 0,
            };
          })
        : [],
      peopleCount: typeof r.people_count === 'number' ? r.people_count : 0,
      lighting: String(r.lighting || 'unknown'),
      mood: String(r.mood || 'neutral'),
      timestamp: new Date().toISOString(),
    });
  }, [setVisionPerception]);

  const { state: camState, toggle } = useCamera(handlePerception);
  const perception = spacetime.visionPerception;

  return (
    <div className="flex flex-col gap-2">
      {/* 开关按钮 */}
      <button
        onClick={toggle}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
          camState.enabled
            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30'
            : 'bg-slate-700/50 text-slate-400 border border-slate-600/30 hover:bg-slate-600/50'
        }`}
        title={camState.enabled ? '关闭视觉感知' : '开启视觉感知'}
      >
        {camState.capturing ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : camState.enabled ? (
          <Camera className="w-3.5 h-3.5" />
        ) : (
          <CameraOff className="w-3.5 h-3.5" />
        )}
        <span>
          {camState.capturing ? '分析中…' : camState.enabled ? '视觉感知开启' : '视觉感知关闭'}
        </span>
        {camState.enabled && (
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        )}
      </button>

      {/* 错误提示 */}
      {camState.error && (
        <div className="text-[10px] text-red-400 bg-red-500/10 px-2 py-1 rounded">
          {camState.error}
        </div>
      )}

      {/* 感知结果卡片 */}
      {perception && camState.enabled && (
        <div className="bg-slate-800/60 rounded-lg p-2.5 border border-slate-700/30 space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-300">
            <Eye className="w-3 h-3 text-emerald-400" />
            <span className="font-medium">{perception.sceneType}</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-relaxed">{perception.sceneDescription}</p>

          <div className="flex flex-wrap gap-1.5">
            <span className="inline-flex items-center gap-0.5 text-[10px] bg-slate-700/50 px-1.5 py-0.5 rounded text-slate-300">
              <Users className="w-2.5 h-2.5" />
              {perception.peopleCount} 人
            </span>
            <span className="inline-flex items-center gap-0.5 text-[10px] bg-slate-700/50 px-1.5 py-0.5 rounded text-slate-300">
              <Lightbulb className="w-2.5 h-2.5" />
              {perception.lighting}
            </span>
            <span className="inline-flex items-center gap-0.5 text-[10px] bg-slate-700/50 px-1.5 py-0.5 rounded text-slate-300">
              <Sparkles className="w-2.5 h-2.5" />
              {perception.mood}
            </span>
          </div>

          {perception.objects.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {perception.objects.slice(0, 4).map((obj, i) => (
                <span
                  key={i}
                  className="text-[9px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/20"
                >
                  {obj.name}
                </span>
              ))}
              {perception.objects.length > 4 && (
                <span className="text-[9px] text-slate-500">+{perception.objects.length - 4}</span>
              )}
            </div>
          )}

          <div className="text-[9px] text-slate-600">
            {new Date(perception.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </div>
        </div>
      )}
    </div>
  );
}
