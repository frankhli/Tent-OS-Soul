import { useState, useEffect, useRef, useCallback } from 'react';
import {
  MapPin,
  Navigation,
  Radio,
  Clock,
  Plus,
  X,
  Layers,
  Footprints,
  AlertCircle,
  Info,
  RefreshCw,
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

// ========== 类型定义 ==========
interface Footprint {
  id: string;
  lat: number;
  lng: number;
  accuracy?: number;
  altitude?: number;
  scene_hint?: string;
  created_at: string;
}

interface Geofence {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius_meters: number;
  scene_id: string;
  is_active: number;
  created_at: string;
}

interface LocationMemory {
  id: string;
  location_name: string;
  lat: number;
  lng: number;
  summary?: string;
  visit_count: number;
  total_duration_minutes: number;
  last_visit: string;
}

interface CurrentScene {
  scene_id: string;
  name: string;
  persona: string;
  entered_at: string;
}

// ========== 组件 ==========
export function SpatialMapPanel() {
  const mapRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<any>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [footprints, setFootprints] = useState<Footprint[]>([]);
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [memories, setMemories] = useState<LocationMemory[]>([]);
  const [currentScene, setCurrentScene] = useState<CurrentScene | null>(null);
  const currentSceneRef = useRef<CurrentScene | null>(null);
  const [gpsEnabled, setGpsEnabled] = useState(false);
  const [gpsPosition, setGpsPosition] = useState<{ lat: number; lng: number; accuracy: number } | null>(null);
  const [showAddGeofence, setShowAddGeofence] = useState(false);
  const [gfName, setGfName] = useState('');
  const [gfRadius, setGfRadius] = useState(100);
  const [gfLat, setGfLat] = useState('');
  const [gfLng, setGfLng] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeLayer, setActiveLayer] = useState<'all' | 'footprints' | 'geofences' | 'memories'>('all');
  const geoWatchRef = useRef<number | null>(null);
  const { showToast } = useToast();

  // ========== 动态加载高德地图 ==========
  useEffect(() => {
    const loadAmap = async () => {
      try {
        // 1. 从后端获取配置
        const resp = await fetch('/ui/api/config');
        const data = await resp.json();
        const cfg = data.config || {};
        const spatial = cfg.spatial || {};
        const key = spatial.amap_js_key || '';

        if (!key) {
          setMapError('高德地图 API Key 未配置。请在 config/tent_os.yaml 的 spatial.amap_js_key 中配置有效的 Key，然后重启服务。');
          setLoading(false);
          return;
        }

        // 2. 动态加载脚本
        if (!(window as any).AMap) {
          const script = document.createElement('script');
          script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}`;
          script.async = true;
          document.head.appendChild(script);

          // 等待加载
          await new Promise<void>((resolve, reject) => {
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('高德地图脚本加载失败'));
            // 10秒超时
            setTimeout(() => reject(new Error('高德地图脚本加载超时')), 10000);
          });
        }

        // 3. 初始化地图
        if (!mapRef.current || !(window as any).AMap) {
          setMapError('地图初始化失败：DOM 或 API 不可用');
          setLoading(false);
          return;
        }
        const AMap = (window as any).AMap;
        const m = new AMap.Map(mapRef.current, {
          zoom: 14,
          center: [116.4074, 39.9042],
          viewMode: '2D',
        });
        setMap(m);
        setMapError(null);
        setLoading(false);
      } catch (e: any) {
        setMapError('地图初始化失败: ' + (e.message || '未知错误'));
        setLoading(false);
      }
    };

    loadAmap();
  }, []);

  // ========== GPS 定位 ==========
  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsEnabled(false);
      return;
    }
    setGpsEnabled(true);

    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        const accuracy = pos.coords.accuracy;
        setGpsPosition({ lat, lng, accuracy });
        // 上报到后端
        reportFootprint(lat, lng, accuracy);
        // 如果地图已加载，移动地图中心
        if (map) {
          map.setCenter([lng, lat]);
          // 添加/更新当前位置标记
          updateCurrentPositionMarker(lat, lng);
        }
      },
      (err) => {
        console.warn('GPS 错误:', err.message);
        setGpsEnabled(false);
      },
      { enableHighAccuracy: true, maximumAge: 30000, timeout: 10000 }
    );
    geoWatchRef.current = watchId;

    return () => {
      if (geoWatchRef.current !== null) {
        navigator.geolocation.clearWatch(geoWatchRef.current);
      }
    };
  }, [map]);

  // 同步 ref 与 state，避免闭包陷阱
  useEffect(() => {
    currentSceneRef.current = currentScene;
  }, [currentScene]);

  // ========== 上报足迹 ==========
  const reportFootprint = useCallback(async (lat: number, lng: number, accuracy: number) => {
    try {
      await fetch('/ui/api/location/footprint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'frank',
          lat,
          lng,
          accuracy,
          altitude: null,
          scene_hint: currentSceneRef.current?.scene_id || '',
        }),
      });
    } catch {
      // 静默失败，不打扰用户
    }
  }, []);

  // ========== 当前位置标记 ==========
  const currentMarkerRef = useRef<any>(null);
  const updateCurrentPositionMarker = (lat: number, lng: number) => {
    if (!map || !(window as any).AMap) return;
    const AMap = (window as any).AMap;
    if (currentMarkerRef.current) {
      currentMarkerRef.current.setPosition([lng, lat]);
    } else {
      const marker = new AMap.Marker({
        position: [lng, lat],
        title: '当前位置',
        icon: new AMap.Icon({
          size: new AMap.Size(24, 24),
          imageSize: new AMap.Size(24, 24),
          image: 'data:image/svg+xml;base64,' + btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" fill="#dbeafe"/><circle cx="12" cy="12" r="4" fill="#2563eb"/></svg>`),
        }),
        offset: new AMap.Pixel(-12, -12),
      });
      map.add(marker);
      currentMarkerRef.current = marker;
    }
  };

  // ========== 加载数据 ==========
  const loadData = useCallback(async () => {
    try {
      const [fpRes, gfRes, memRes, sceneRes] = await Promise.all([
        fetch('/ui/api/location/footprint?hours=24').then((r) => r.json()).catch(() => ({ path: [] })),
        fetch('/ui/api/location/geofences').then((r) => r.json()).catch(() => ({ geofences: [] })),
        fetch('/ui/api/location/memories').then((r) => r.json()).catch(() => ({ memories: [] })),
        fetch('/ui/api/scenes/current').then((r) => r.json()).catch(() => ({ scene: null })),
      ]);
      setFootprints(fpRes.path || []);
      setGeofences(gfRes.geofences || []);
      setMemories(memRes.memories || []);
      if (sceneRes.scene) setCurrentScene(sceneRes.scene);
    } catch {
      // 静默失败
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // ========== 绘制地图元素 ==========
  useEffect(() => {
    if (!map || !(window as any).AMap) return;
    const AMap = (window as any).AMap;

    // 清除旧覆盖物（保留当前位置标记）
    const allOverlays = map.getAllOverlays();
    allOverlays.forEach((o: any) => {
      if (o !== currentMarkerRef.current) {
        map.remove(o);
      }
    });

    // 绘制足迹路径
    if ((activeLayer === 'all' || activeLayer === 'footprints') && footprints.length > 1) {
      const path = footprints.map((f) => [f.lng, f.lat]);
      const polyline = new AMap.Polyline({
        path,
        strokeColor: '#8b5cf6',
        strokeWeight: 3,
        strokeOpacity: 0.7,
        strokeStyle: 'solid',
        showDir: true,
      });
      map.add(polyline);

      // 起点和终点标记
      const start = footprints[0];
      const end = footprints[footprints.length - 1];
      const startMarker = new AMap.Marker({
        position: [start.lng, start.lat],
        title: '起点',
        label: { content: '起点', direction: 'top' },
        icon: new AMap.Icon({
          size: new AMap.Size(16, 16),
          imageSize: new AMap.Size(16, 16),
          image: 'data:image/svg+xml;base64,' + btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="#22c55e" stroke="white" stroke-width="2"/></svg>`),
        }),
        offset: new AMap.Pixel(-8, -8),
      });
      const endMarker = new AMap.Marker({
        position: [end.lng, end.lat],
        title: '终点',
        label: { content: '终点', direction: 'top' },
        icon: new AMap.Icon({
          size: new AMap.Size(16, 16),
          imageSize: new AMap.Size(16, 16),
          image: 'data:image/svg+xml;base64,' + btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="#ef4444" stroke="white" stroke-width="2"/></svg>`),
        }),
        offset: new AMap.Pixel(-8, -8),
      });
      map.add([startMarker, endMarker]);
    }

    // 绘制地理围栏
    if ((activeLayer === 'all' || activeLayer === 'geofences') && geofences.length > 0) {
      geofences.forEach((gf) => {
        const circle = new AMap.Circle({
          center: [gf.lng, gf.lat],
          radius: gf.radius_meters,
          strokeColor: gf.is_active ? '#3b82f6' : '#9ca3af',
          strokeWeight: 2,
          strokeOpacity: 0.8,
          fillColor: gf.is_active ? '#3b82f6' : '#9ca3af',
          fillOpacity: 0.15,
        });
        const marker = new AMap.Marker({
          position: [gf.lng, gf.lat],
          title: gf.name,
          label: {
            content: `<div style="font-size:11px;background:#3b82f6;color:white;padding:2px 6px;border-radius:4px;">${gf.name}</div>`,
            direction: 'top',
          },
        });
        map.add([circle, marker]);
      });
    }

    // 绘制位置记忆
    if ((activeLayer === 'all' || activeLayer === 'memories') && memories.length > 0) {
      memories.forEach((mem) => {
        const marker = new AMap.Marker({
          position: [mem.lng, mem.lat],
          title: mem.location_name,
          label: {
            content: `<div style="font-size:11px;background:#8b5cf6;color:white;padding:2px 6px;border-radius:4px;">${mem.location_name} (${mem.visit_count}次)</div>`,
            direction: 'top',
          },
          icon: new AMap.Icon({
            size: new AMap.Size(20, 20),
            imageSize: new AMap.Size(20, 20),
            image: 'data:image/svg+xml;base64,' + btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><path d="M10 2C7.24 2 5 4.24 5 7c0 3.86 5 11 5 11s5-7.14 5-11c0-2.76-2.24-5-5-5z" fill="#8b5cf6" stroke="white" stroke-width="1.5"/></svg>`),
          }),
          offset: new AMap.Pixel(-10, -20),
        });
        // 点击弹出信息窗
        marker.on('click', () => {
          const infoWindow = new AMap.InfoWindow({
            content: `<div style="padding:8px;font-size:12px;">
              <strong>${mem.location_name}</strong><br/>
              访问 ${mem.visit_count} 次<br/>
              总时长 ${mem.total_duration_minutes} 分钟<br/>
              ${mem.summary ? `<span style="color:#666;">${mem.summary}</span>` : ''}
            </div>`,
            offset: new AMap.Pixel(0, -20),
          });
          infoWindow.open(map, [mem.lng, mem.lat]);
        });
        map.add(marker);
      });
    }
  }, [map, footprints, geofences, memories, activeLayer]);

  // ========== 创建地理围栏 ==========
  const handleCreateGeofence = async () => {
    if (!gfName.trim() || !gfLat || !gfLng) {
      showToast('请填写完整信息', 'error');
      return;
    }
    try {
      const resp = await fetch('/ui/api/location/geofences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'frank',
          name: gfName.trim(),
          lat: parseFloat(gfLat),
          lng: parseFloat(gfLng),
          radius_meters: gfRadius,
          scene_id: 'custom',
        }),
      });
      if (resp.ok) {
        showToast('地理围栏已创建', 'success');
        setShowAddGeofence(false);
        setGfName('');
        setGfLat('');
        setGfLng('');
        setGfRadius(100);
        await loadData();
      } else {
        showToast('创建失败', 'error');
      }
    } catch {
      showToast('后端未连接', 'error');
    }
  };

  // ========== 删除地理围栏 ==========
  const handleDeleteGeofence = async (id: string) => {
    if (!confirm('确定删除此地理围栏？')) return;
    try {
      const resp = await fetch(`/ui/api/location/geofences/${id}`, { method: 'DELETE' });
      if (resp.ok) {
        showToast('已删除', 'success');
        await loadData();
      }
    } catch {
      showToast('删除失败', 'error');
    }
  };

  // ========== 使用当前位置创建围栏 ==========
  const useCurrentLocation = () => {
    if (gpsPosition) {
      setGfLat(gpsPosition.lat.toFixed(6));
      setGfLng(gpsPosition.lng.toFixed(6));
    } else {
      showToast('无法获取当前位置', 'error');
    }
  };

  return (
    <div className="space-y-4">
      {/* 顶部信息栏 */}
      <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl border border-blue-100 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-blue-600" />
              🗺️ 空间足迹与场景地图
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              AI 记录你的位置轨迹，识别你常去的场所，自动切换场景人格。
              {gpsEnabled ? ' GPS 定位已启用' : ' GPS 定位未启用'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {currentScene ? (
              <div className="text-center">
                <div className="text-lg font-bold text-blue-600">{currentScene.name}</div>
                <div className="text-[10px] text-gray-400">当前场景</div>
              </div>
            ) : (
              <div className="text-center">
                <div className="text-lg font-bold text-gray-400">未知</div>
                <div className="text-[10px] text-gray-400">当前场景</div>
              </div>
            )}
            <div className="text-center">
              <div className="text-lg font-bold text-purple-600">{footprints.length}</div>
              <div className="text-[10px] text-gray-400">足迹点</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-amber-600">{geofences.length}</div>
              <div className="text-[10px] text-gray-400">地理围栏</div>
            </div>
          </div>
        </div>
        {gpsPosition && (
          <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-500">
            <Navigation className="w-3 h-3 text-blue-500" />
            <span>
              当前位置: {gpsPosition.lat.toFixed(5)}, {gpsPosition.lng.toFixed(5)}
              {gpsPosition.accuracy > 0 && ` (精度 ±${gpsPosition.accuracy.toFixed(0)}m)`}
            </span>
          </div>
        )}
      </div>

      {/* 地图层切换 */}
      <div className="flex items-center gap-2">
        {[
          { key: 'all' as const, label: '全部', icon: Layers },
          { key: 'footprints' as const, label: '足迹', icon: Footprints },
          { key: 'geofences' as const, label: '围栏', icon: Radio },
          { key: 'memories' as const, label: '记忆', icon: MapPin },
        ].map((layer) => (
          <button
            key={layer.key}
            onClick={() => setActiveLayer(layer.key)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activeLayer === layer.key
                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            <layer.icon className="w-3 h-3" />
            {layer.label}
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={() => setShowAddGeofence(true)}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-3 h-3" />
          添加围栏
        </button>
        <button
          onClick={loadData}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          刷新
        </button>
      </div>

      {/* 地图容器 */}
      <div className="relative bg-gray-100 rounded-xl border border-gray-200 overflow-hidden" style={{ height: 420 }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-2" />
              <p className="text-sm text-gray-500">加载地图中...</p>
            </div>
          </div>
        )}
        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="text-center max-w-md px-4">
              <AlertCircle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
              <p className="text-sm font-medium text-gray-700 mb-2">地图加载失败</p>
              <p className="text-xs text-gray-500">{mapError}</p>
              <div className="mt-3 p-3 bg-blue-50 rounded-lg text-left">
                <p className="text-xs text-blue-700 font-medium mb-1">💡 解决方法：</p>
                <ol className="text-[11px] text-blue-600 list-decimal list-inside space-y-1">
                  <li>在 <code className="bg-blue-100 px-1 rounded">config/tent_os.yaml</code> 中配置有效的高德地图 JS API Key</li>
                  <li>确保网络可以访问 <code className="bg-blue-100 px-1 rounded">webapi.amap.com</code></li>
                  <li>刷新页面重试</li>
                </ol>
              </div>
            </div>
          </div>
        )}
        <div ref={mapRef} style={{ width: '100%', height: '100%' }} />
      </div>

      {/* 地理围栏列表 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h4 className="text-xs font-semibold text-gray-700 mb-3 flex items-center gap-1">
          <Radio className="w-3 h-3" />
          已配置的地理围栏
        </h4>
        {geofences.length === 0 ? (
          <div className="text-center py-6 text-gray-400 text-xs bg-gray-50 rounded-xl border border-dashed border-gray-200">
            <MapPin className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p>暂无地理围栏</p>
            <p className="mt-0.5">添加围栏后，AI 会在你进入/离开时自动切换场景</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {geofences.map((gf) => (
              <div key={gf.id} className="bg-gray-50 rounded-lg border border-gray-100 p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-gray-700">{gf.name}</span>
                  <button
                    onClick={() => handleDeleteGeofence(gf.id)}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
                <p className="text-[10px] text-gray-400">
                  {gf.lat.toFixed(5)}, {gf.lng.toFixed(5)} · 半径 {gf.radius_meters}m
                </p>
                <div className="flex items-center gap-1 mt-1">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${gf.is_active ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'}`}>
                    {gf.is_active ? '启用中' : '已停用'}
                  </span>
                  {gf.scene_id && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-600">
                      {gf.scene_id}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 位置记忆列表 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h4 className="text-xs font-semibold text-gray-700 mb-3 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          位置记忆
        </h4>
        {memories.length === 0 ? (
          <div className="text-center py-6 text-gray-400 text-xs bg-gray-50 rounded-xl border border-dashed border-gray-200">
            <Info className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p>暂无位置记忆</p>
            <p className="mt-0.5">足迹数据积累后会自动生成位置记忆</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {memories.map((mem) => (
              <div key={mem.id} className="bg-gray-50 rounded-lg border border-gray-100 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <MapPin className="w-3 h-3 text-purple-500" />
                  <span className="text-xs font-medium text-gray-700">{mem.location_name}</span>
                </div>
                {mem.summary && (
                  <p className="text-[11px] text-gray-500 mb-1">{mem.summary}</p>
                )}
                <div className="flex items-center gap-2 text-[10px] text-gray-400">
                  <span>访问 {mem.visit_count} 次</span>
                  <span>·</span>
                  <span>{mem.total_duration_minutes} 分钟</span>
                  <span>·</span>
                  <span>{mem.last_visit?.slice(0, 10)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 添加围栏弹窗 */}
      {showAddGeofence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-base font-semibold text-gray-900">⭕ 添加地理围栏</h3>
              <button onClick={() => setShowAddGeofence(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1.5 block">名称</label>
                <input
                  type="text"
                  value={gfName}
                  onChange={(e) => setGfName(e.target.value)}
                  placeholder="例如：家、办公室、健身房..."
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 mb-1.5 block">纬度</label>
                  <input
                    type="number"
                    step="0.000001"
                    value={gfLat}
                    onChange={(e) => setGfLat(e.target.value)}
                    placeholder="39.9042"
                    className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 mb-1.5 block">经度</label>
                  <input
                    type="number"
                    step="0.000001"
                    value={gfLng}
                    onChange={(e) => setGfLng(e.target.value)}
                    placeholder="116.4074"
                    className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>
              <button
                onClick={useCurrentLocation}
                className="w-full flex items-center justify-center gap-1 px-3 py-2 rounded-lg text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors"
              >
                <Navigation className="w-3 h-3" />
                使用当前 GPS 位置
              </button>
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1.5 block">半径（米）</label>
                <input
                  type="range"
                  min={10}
                  max={1000}
                  step={10}
                  value={gfRadius}
                  onChange={(e) => setGfRadius(parseInt(e.target.value))}
                  className="w-full"
                />
                <div className="text-center text-xs text-gray-500 mt-1">{gfRadius} 米</div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowAddGeofence(false)}
                className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateGeofence}
                disabled={!gfName.trim() || !gfLat || !gfLng}
                className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                创建围栏
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
