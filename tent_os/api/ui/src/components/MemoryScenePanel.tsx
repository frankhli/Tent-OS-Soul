/**
 * MemoryScenePanel — 回忆场景（时空回溯）
 * 将某段对话/任务的完整时空封装并可视化重现
 */

import { useState, useEffect, useCallback } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { useSpacetime } from '@/contexts/SpacetimeContext';
import {
  ArrowLeft, Clock, MapPin, Cloud, Sun, Moon, Brain,
  MessageSquare, Sparkles, RotateCcw, CalendarDays,
} from 'lucide-react';
import type { MemorySceneDto } from '@/world/spacetimeApi';
import { loadMemoryScene } from '@/world/spacetimeApi';

interface MemoryScenePanelProps {
  sessionId?: string;
  onBack?: () => void;
  onContinueChat?: (sessionId: string) => void;
}

export function MemoryScenePanel({ sessionId, onBack, onContinueChat }: MemoryScenePanelProps) {
  const [scene, setScene] = useState<MemorySceneDto | null>(null);
  const [loading, setLoading] = useState(true);
  const { showToast: _showToast } = useToast();
  const { state: _spacetime } = useSpacetime();

  const fetchScene = useCallback(async () => {
    if (!sessionId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await loadMemoryScene(sessionId);
      if (data) {
        setScene(data);
      } else {
        // 如果后端未实现，生成模拟回忆场景
        setScene(generateMockScene(sessionId));
      }
    } catch {
      setScene(generateMockScene(sessionId));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchScene();
  }, [fetchScene]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <RotateCcw className="w-8 h-8 animate-spin" />
          <p className="text-sm">正在回溯时空...</p>
        </div>
      </div>
    );
  }

  if (!scene) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <Brain className="w-12 h-12" />
          <p className="text-sm">暂无回忆场景</p>
          <button
            onClick={onBack}
            className="mt-2 px-4 py-2 rounded-lg text-sm bg-white border border-gray-200 hover:bg-gray-50"
          >
            ← 返回
          </button>
        </div>
      </div>
    );
  }

  const date = new Date(scene.timestamp);
  const weatherIcon =
    scene.environment.weather === 'rain' ? <Cloud className="w-4 h-4" /> :
    scene.environment.weather === 'clear' ? <Sun className="w-4 h-4" /> :
    <Moon className="w-4 h-4" />;

  const phaseLabel =
    scene.environment.day_phase === 'morning' ? '🌅 早晨' :
    scene.environment.day_phase === 'afternoon' ? '☀️ 下午' :
    scene.environment.day_phase === 'evening' ? '🌆 傍晚' :
    '🌃 夜晚';

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-b from-purple-50 to-gray-50">
      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* 头部 */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={onBack}
            className="p-2 rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            <ArrowLeft className="w-4 h-4 text-gray-600" />
          </button>
          <div>
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-purple-500" />
              回忆空间
            </h2>
            <p className="text-xs text-gray-500">
              <CalendarDays className="w-3 h-3 inline mr-1" />
              {date.toLocaleString('zh-CN')}
            </p>
          </div>
        </div>

        {/* 时空信息卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="bg-white rounded-xl border border-purple-100 p-3">
            <div className="flex items-center gap-1.5 text-purple-600 mb-1">
              <Clock className="w-3.5 h-3.5" />
              <span className="text-[10px] font-medium">时间相位</span>
            </div>
            <p className="text-sm font-semibold text-gray-800">{phaseLabel}</p>
          </div>
          <div className="bg-white rounded-xl border border-purple-100 p-3">
            <div className="flex items-center gap-1.5 text-purple-600 mb-1">
              {weatherIcon}
              <span className="text-[10px] font-medium">天气</span>
            </div>
            <p className="text-sm font-semibold text-gray-800">
              {scene.environment.weather === 'rain' && '下雨'}
              {scene.environment.weather === 'clear' && '晴朗'}
              {scene.environment.weather === 'cloudy' && '多云'}
              {scene.environment.weather === 'snow' && '下雪'}
              {!scene.environment.weather && '未知'}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-purple-100 p-3">
            <div className="flex items-center gap-1.5 text-purple-600 mb-1">
              <MapPin className="w-3.5 h-3.5" />
              <span className="text-[10px] font-medium">AI 位置</span>
            </div>
            <p className="text-sm font-semibold text-gray-800">{scene.ai_state.location}</p>
          </div>
          <div className="bg-white rounded-xl border border-purple-100 p-3">
            <div className="flex items-center gap-1.5 text-purple-600 mb-1">
              <Brain className="w-3.5 h-3.5" />
              <span className="text-[10px] font-medium">当时情绪</span>
            </div>
            <p className="text-sm font-semibold text-gray-800">{scene.ai_state.emotion}</p>
          </div>
        </div>

        {/* 世界快照 */}
        <div className="bg-white rounded-xl border border-purple-100 p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
            <MapPin className="w-4 h-4 text-purple-500" />
            AI 的家 · 当时的样子
          </h3>
          <div className="relative h-48 bg-gradient-to-b from-gray-100 to-gray-200 rounded-lg overflow-hidden">
            {/* 简化的世界快照：用 CSS 模拟房间布局 */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative w-64 h-36 bg-purple-50 rounded-lg border-2 border-purple-200">
                {/* 房间名称 */}
                <span className="absolute top-2 left-2 text-[10px] text-purple-400 font-medium">
                  {scene.ai_state.location}
                </span>
                {/* 窗户 */}
                <div className={`absolute top-3 right-4 w-12 h-8 rounded border-2 ${
                  scene.environment.day_phase === 'night' ? 'bg-indigo-900 border-indigo-700' :
                  scene.environment.weather === 'rain' ? 'bg-blue-200 border-blue-300' :
                  'bg-sky-200 border-sky-300'
                }`}>
                  {scene.environment.weather === 'rain' && (
                    <div className="absolute inset-0 flex flex-col justify-around px-0.5">
                      {[1,2,3].map(i => (
                        <div key={i} className="h-px bg-blue-400/40" />
                      ))}
                    </div>
                  )}
                  {scene.environment.day_phase === 'night' && (
                    <div className="absolute top-1 right-1 w-1 h-1 bg-yellow-200 rounded-full" />
                  )}
                </div>
                {/* Avatar（简化） */}
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex flex-col items-center">
                  <div className="w-6 h-6 rounded-full bg-teal-500 shadow-sm" />
                  <div className="mt-1 px-2 py-0.5 bg-teal-500/90 rounded-full text-[8px] text-white">
                    {scene.ai_state.activity}
                  </div>
                </div>
                {/* 家具 */}
                <div className="absolute bottom-4 left-4 w-10 h-6 bg-amber-700/80 rounded" />
                <div className="absolute bottom-4 right-4 w-8 h-8 bg-indigo-300/50 rounded-full" />
              </div>
            </div>
          </div>
        </div>

        {/* 对话摘要 */}
        <div className="bg-white rounded-xl border border-purple-100 p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
            <MessageSquare className="w-4 h-4 text-purple-500" />
            对话摘要
          </h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {scene.messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-[80%] px-3 py-2 rounded-xl text-xs ${
                  m.role === 'user'
                    ? 'bg-teal-50 text-teal-900 rounded-br-sm'
                    : 'bg-purple-50 text-purple-900 rounded-bl-sm'
                }`}>
                  <p className="whitespace-pre-wrap">{m.content.slice(0, 120)}{m.content.length > 120 ? '...' : ''}</p>
                  <span className="text-[10px] text-gray-400 mt-1 block">
                    {new Date(m.timestamp).toLocaleTimeString('zh-CN')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 任务成果 */}
        {scene.artifacts.length > 0 && (
          <div className="bg-white rounded-xl border border-purple-100 p-4 mb-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-amber-500" />
              当时的智慧藏品
            </h3>
            <div className="flex flex-wrap gap-2">
              {scene.artifacts.map(a => (
                <div
                  key={a.id}
                  className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg"
                >
                  <span className="text-lg">
                    {a.visual_type === 'book' ? '📚' :
                     a.visual_type === 'crystal' ? '💎' :
                     a.visual_type === 'scroll' ? '📜' :
                     a.visual_type === 'gear' ? '⚙️' :
                     a.visual_type === 'plant' ? '🌿' : '🎨'}
                  </span>
                  <div>
                    <p className="text-xs font-medium text-gray-700">{a.name}</p>
                    <p className="text-[10px] text-gray-400">{a.rarity}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 认知图谱快照 */}
        {scene.graph_snapshot.key_nodes.length > 0 && (
          <div className="bg-white rounded-xl border border-purple-100 p-4 mb-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
              <Brain className="w-4 h-4 text-indigo-500" />
              当时的认知图谱
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {scene.graph_snapshot.key_nodes.map((node, i) => (
                <span
                  key={i}
                  className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full border border-indigo-100"
                >
                  {node}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 底部操作 */}
        <div className="flex items-center gap-3 sticky bottom-4 bg-white/80 backdrop-blur rounded-xl border border-gray-200 p-3">
          <button
            onClick={() => onContinueChat?.(scene.session_id)}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
          >
            <MessageSquare className="w-4 h-4" />
            基于这段回忆继续对话
          </button>
          <button
            onClick={onBack}
            className="px-4 py-2.5 bg-white text-gray-600 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 transition-colors"
          >
            返回
          </button>
        </div>
      </div>
    </div>
  );
}

// ===== 模拟回忆场景生成器（后端未实现时的 fallback）=====
function generateMockScene(sessionId: string): MemorySceneDto {
  const now = Date.now();
  const past = now - 7 * 24 * 60 * 60 * 1000; // 一周前
  return {
    session_id: sessionId,
    timestamp: past,
    messages: [
      { role: 'user', content: '帮我分析一下上个月的销售数据', timestamp: past },
      { role: 'assistant', content: '好的，我来为你分析销售数据。从数据来看，上个月销售额环比增长了 15%，主要增长点在...', timestamp: past + 5000 },
    ],
    artifacts: [
      { id: 'a1', name: '销售分析报告', visual_type: 'book', rarity: 'rare' },
    ],
    ai_state: {
      emotion: 'focused',
      location: '书房·书桌',
      activity: '深度分析',
    },
    environment: {
      day_phase: 'afternoon',
      weather: 'clear',
      brightness: 0.8,
    },
    graph_snapshot: {
      key_nodes: ['销售数据', '增长趋势', '客户画像'],
      connections: ['销售数据 → 增长趋势', '客户画像 → 销售策略'],
    },
  };
}
