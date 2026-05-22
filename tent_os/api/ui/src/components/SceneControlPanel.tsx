import { useState, useEffect, useCallback } from 'react';
import {
  Home,
  Briefcase,
  AlertTriangle,
  Zap,
  Settings,
  ChevronRight,
  Power,
  Lightbulb,
  Thermometer,
  Lock,
  Wifi,
  Smartphone,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

// ========== 类型定义 ==========
interface Scene {
  scene_id: string;
  name: string;
  type: string;
  location: { lat: number; lng: number };
  geofence_radius: number;
  persona: string;
  devices: string[];
  auto_actions: {
    enter?: string[];
    leave?: string[];
  };
}

interface CurrentScene {
  scene_id: string;
  name: string;
  persona: string;
  entered_at: string;
}

interface Device {
  id: string;
  name: string;
  type: string;
  status: 'online' | 'offline' | 'busy' | 'error';
  protocol: string;
  last_heartbeat: string;
  capabilities: string[];
}

// ========== 场景图标映射 ==========
function getSceneIcon(type: string) {
  switch (type) {
    case 'home': return <Home className="w-5 h-5" />;
    case 'office': return <Briefcase className="w-5 h-5" />;
    case 'emergency': return <AlertTriangle className="w-5 h-5" />;
    default: return <Settings className="w-5 h-5" />;
  }
}

function getSceneColor(type: string) {
  switch (type) {
    case 'home': return 'bg-green-50 text-green-600 border-green-200';
    case 'office': return 'bg-blue-50 text-blue-600 border-blue-200';
    case 'emergency': return 'bg-red-50 text-red-600 border-red-200';
    default: return 'bg-gray-50 text-gray-600 border-gray-200';
  }
}

function getPersonaLabel(persona: string) {
  const map: Record<string, string> = {
    casual: '管家模式（轻松）',
    work: '秘书模式（高效）',
    emergency: '应急模式（严肃）',
  };
  return map[persona] || persona;
}

function getDeviceIcon(type: string) {
  switch (type) {
    case 'light': return <Lightbulb className="w-4 h-4" />;
    case 'thermostat': return <Thermometer className="w-4 h-4" />;
    case 'lock': return <Lock className="w-4 h-4" />;
    case 'camera': return <Wifi className="w-4 h-4" />;
    default: return <Smartphone className="w-4 h-4" />;
  }
}

// ========== 组件 ==========
export function SceneControlPanel() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [currentScene, setCurrentScene] = useState<CurrentScene | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedScene, setSelectedScene] = useState<string | null>(null);
  const [actionLogs, setActionLogs] = useState<Array<{ time: string; action: string; status: string }>>([]);
  const { showToast } = useToast();

  // ========== 加载数据 ==========
  const loadData = useCallback(async () => {
    try {
      const [scenesRes, sceneRes, devicesRes] = await Promise.all([
        fetch('/ui/api/scenes').then((r) => r.json()).catch(() => ({ scenes: [] })),
        fetch('/ui/api/scenes/current').then((r) => r.json()).catch(() => ({ scene: null })),
        fetch('/ui/api/devices').then((r) => r.json()).catch(() => ({ devices: [] })),
      ]);
      setScenes(scenesRes.scenes || []);
      setCurrentScene(sceneRes.scene || null);
      setDevices(devicesRes.devices || []);
    } catch {
      // 静默失败
    } finally {
      // loading done
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // ========== 手动切换场景 ==========
  const handleSwitchScene = async (sceneId: string) => {
    try {
      const resp = await fetch('/ui/api/scene/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'frank', scene_id: sceneId }),
      });
      if (resp.ok) {
        showToast('场景已切换', 'success');
        await loadData();
        // 添加日志
        setActionLogs((prev) => [
          { time: new Date().toLocaleTimeString('zh-CN'), action: `切换到场景: ${sceneId}`, status: 'success' },
          ...prev.slice(0, 19),
        ]);
      } else {
        showToast('切换失败', 'error');
      }
    } catch {
      showToast('后端未连接', 'error');
    }
  };

  // ========== 发送设备控制命令 ==========
  const handleDeviceAction = async (deviceId: string, action: string) => {
    try {
      const resp = await fetch('/ui/api/physical/tasks/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'device_control',
          target_location: deviceId,
          item_description: action,
          provider: 'auto',
          priority: 'normal',
        }),
      });
      if (resp.ok) {
        showToast(`已发送: ${action}`, 'success');
        setActionLogs((prev) => [
          { time: new Date().toLocaleTimeString('zh-CN'), action: `${deviceId}: ${action}`, status: 'success' },
          ...prev.slice(0, 19),
        ]);
      }
    } catch {
      showToast('发送失败', 'error');
    }
  };

  // ========== 获取场景下的设备 ==========
  const selectedSceneConfig = scenes.find((s) => s.scene_id === selectedScene);

  return (
    <div className="space-y-4">
      {/* 顶部信息栏 */}
      <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-xl border border-amber-100 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <Settings className="w-4 h-4 text-amber-600" />
              🎭 场景自适应引擎
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              AI 根据你所在的位置自动切换人格和行为模式。在家是管家，在办公室是秘书。
            </p>
          </div>
          <div className="text-center">
            <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
              currentScene
                ? getSceneColor(scenes.find((s) => s.scene_id === currentScene.scene_id)?.type || 'other')
                : 'bg-gray-100 text-gray-400'
            }`}>
              {currentScene ? getSceneIcon(scenes.find((s) => s.scene_id === currentScene.scene_id)?.type || 'other') : <Settings className="w-3 h-3" />}
              {currentScene ? currentScene.name : '未进入任何场景'}
            </div>
            {currentScene && (
              <div className="text-[10px] text-gray-400 mt-1">
                {getPersonaLabel(currentScene.persona)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 场景卡片 */}
      <div className="grid grid-cols-3 gap-3">
        {scenes.map((scene) => {
          const isActive = currentScene?.scene_id === scene.scene_id;
          return (
            <button
              key={scene.scene_id}
              onClick={() => setSelectedScene(selectedScene === scene.scene_id ? null : scene.scene_id)}
              className={`text-left rounded-xl border p-4 transition-all ${
                isActive
                  ? 'bg-white border-amber-300 shadow-md ring-1 ring-amber-200'
                  : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${getSceneColor(scene.type)}`}>
                  {getSceneIcon(scene.type)}
                </div>
                {isActive && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-200 font-medium">
                    当前场景
                  </span>
                )}
              </div>
              <h4 className="text-sm font-semibold text-gray-800">{scene.name}</h4>
              <p className="text-[11px] text-gray-500 mt-0.5">{getPersonaLabel(scene.persona)}</p>
              <div className="flex items-center gap-1 mt-2 text-[10px] text-gray-400">
                <Zap className="w-3 h-3" />
                <span>{(scene.auto_actions?.enter?.length || 0) + (scene.auto_actions?.leave?.length || 0)} 个自动动作</span>
              </div>
              <div className="flex items-center gap-1 mt-1 text-[10px] text-gray-400">
                <Settings className="w-3 h-3" />
                <span>{scene.devices?.length || 0} 个设备</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* 选中场景的详情 */}
      {selectedSceneConfig && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              {getSceneIcon(selectedSceneConfig.type)}
              {selectedSceneConfig.name} 详情
            </h4>
            <button
              onClick={() => handleSwitchScene(selectedSceneConfig.scene_id)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                currentScene?.scene_id === selectedSceneConfig.scene_id
                  ? 'bg-gray-100 text-gray-400 cursor-default'
                  : 'bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200'
              }`}
              disabled={currentScene?.scene_id === selectedSceneConfig.scene_id}
            >
              <Power className="w-3 h-3" />
              {currentScene?.scene_id === selectedSceneConfig.scene_id ? '当前场景' : '切换到此场景'}
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* 自动动作 */}
            <div>
              <h5 className="text-xs font-medium text-gray-500 mb-2">进入时自动执行</h5>
              {selectedSceneConfig.auto_actions?.enter?.length ? (
                <div className="space-y-1">
                  {selectedSceneConfig.auto_actions.enter.map((action, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-700 bg-green-50 rounded-lg px-3 py-2">
                      <CheckCircle2 className="w-3 h-3 text-green-500" />
                      {action}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-gray-400">无自动动作</p>
              )}

              <h5 className="text-xs font-medium text-gray-500 mb-2 mt-3">离开时自动执行</h5>
              {selectedSceneConfig.auto_actions?.leave?.length ? (
                <div className="space-y-1">
                  {selectedSceneConfig.auto_actions.leave.map((action, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-700 bg-gray-50 rounded-lg px-3 py-2">
                      <XCircle className="w-3 h-3 text-gray-400" />
                      {action}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-gray-400">无自动动作</p>
              )}
            </div>

            {/* 位置信息 */}
            <div>
              <h5 className="text-xs font-medium text-gray-500 mb-2">位置信息</h5>
              <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">坐标</span>
                  <span className="text-gray-700 font-mono">
                    {selectedSceneConfig.location?.lat?.toFixed(5)}, {selectedSceneConfig.location?.lng?.toFixed(5)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">围栏半径</span>
                  <span className="text-gray-700">{selectedSceneConfig.geofence_radius} 米</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">人格模式</span>
                  <span className="text-gray-700">{getPersonaLabel(selectedSceneConfig.persona)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 设备列表 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-semibold text-gray-700 flex items-center gap-1">
            <Smartphone className="w-3 h-3" />
            已连接的智能设备
          </h4>
          <span className="text-[10px] text-gray-400">{devices.length} 个设备</span>
        </div>
        {devices.length === 0 ? (
          <div className="text-center py-6 text-gray-400 text-xs bg-gray-50 rounded-xl border border-dashed border-gray-200">
            <Wifi className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p>暂无连接的设备</p>
            <p className="mt-0.5">设备连接后会显示在这里，支持灯控、温控、门锁等</p>
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-2">
            {devices.map((device) => (
              <div
                key={device.id}
                className={`bg-gray-50 rounded-lg border p-3 ${
                  device.status === 'online' ? 'border-green-200' : 'border-gray-200'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-2 h-2 rounded-full ${device.status === 'online' ? 'bg-green-400' : 'bg-gray-300'}`} />
                  {getDeviceIcon(device.type)}
                  <span className="text-xs font-medium text-gray-700 truncate">{device.name}</span>
                </div>
                <div className="text-[10px] text-gray-400 mb-2">
                  {device.protocol} · {device.status === 'online' ? '在线' : '离线'}
                </div>
                <div className="flex gap-1">
                  {device.capabilities.slice(0, 3).map((cap) => (
                    <button
                      key={cap}
                      onClick={() => handleDeviceAction(device.id, cap)}
                      className="text-[9px] px-2 py-1 rounded bg-white border border-gray-200 text-gray-600 hover:bg-gray-100 transition-colors"
                    >
                      {cap}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 动作日志 */}
      {actionLogs.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            场景动作日志
          </h4>
          <div className="space-y-1 max-h-[200px] overflow-y-auto">
            {actionLogs.map((log, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-gray-400 font-mono">{log.time}</span>
                <ChevronRight className="w-3 h-3 text-gray-300" />
                <span className="text-gray-700">{log.action}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  log.status === 'success' ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'
                }`}>
                  {log.status === 'success' ? '成功' : '失败'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
