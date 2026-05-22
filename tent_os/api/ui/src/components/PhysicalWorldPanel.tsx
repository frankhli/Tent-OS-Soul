import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Truck,
  Bike,
  User,
  AlertTriangle,
  RefreshCw,
  Plus,
  X,
  ChevronDown,
  ChevronUp,
  MapPin,
  Package,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Eye,
  Camera,
  Zap,
  Shield,
  Activity,
  Radio,
  Send,
  Plug,
  Server,
  Settings2,
  Brain,
  Search,
  Lightbulb,
  Gauge,
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip } from 'recharts';
import { AvatarHomeButton } from './AvatarHomeButton';
import { SpatialMapPanel } from './SpatialMapPanel';
import { SceneControlPanel } from './SceneControlPanel';

// ========== 类型定义 ==========
interface PhysicalExecutor {
  id: string;
  name: string;
  type: 'robot' | 'flashex' | 'manual' | 'drone' | 'camera' | 'mcp' | 'plugin';
  status: 'online' | 'offline' | 'busy' | 'error' | 'standby';
  location?: string;
  battery?: number;
  capabilities: string[];
  health_score?: number;
  config?: Record<string, any>;
}

interface PhysicalTask {
  task_id: string;
  action: string;
  target_location: string;
  item_description: string;
  provider: string;
  priority: 'urgent' | 'normal' | 'low';
  status: 'submitted' | 'assigned' | 'executing' | 'completed' | 'failed';
  created_at: string;
  updated_at?: string;
  error?: string;
  fallback_history?: string[];
}

interface HandEyeEvent {
  id: string;
  timestamp: string;
  type: 'vision_detect' | 'physical_action' | 'safety_alert' | 'coordination';
  description: string;
  camera_id?: string;
  executor_id?: string;
  severity: 'info' | 'warning' | 'critical';
}

interface PhysicalStatus {
  enabled: boolean;
  providers: Array<{ name: string; enabled: boolean; endpoint: string }>;
  active_tasks: number;
}

interface LevelInfo {
  level: number;
  title: string;
}

// ========== 辅助函数 ==========
function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    online: 'text-green-600 bg-green-50 border-green-200',
    offline: 'text-gray-400 bg-gray-100 border-gray-200',
    busy: 'text-amber-600 bg-amber-50 border-amber-200',
    error: 'text-red-600 bg-red-50 border-red-200',
    standby: 'text-blue-600 bg-blue-50 border-blue-200',
    submitted: 'text-gray-500 bg-gray-50 border-gray-200',
    assigned: 'text-blue-600 bg-blue-50 border-blue-200',
    executing: 'text-tent-600 bg-tent-50 border-tent-200',
    completed: 'text-green-600 bg-green-50 border-green-200',
    failed: 'text-red-600 bg-red-50 border-red-200',
  };
  return map[status] || 'text-gray-500 bg-gray-50 border-gray-200';
}

function getStatusIcon(status: string) {
  const map: Record<string, React.ReactNode> = {
    online: <Activity className="w-3 h-3" />,
    offline: <XCircle className="w-3 h-3" />,
    busy: <Loader2 className="w-3 h-3 animate-spin" />,
    error: <AlertTriangle className="w-3 h-3" />,
    standby: <Clock className="w-3 h-3" />,
    submitted: <Clock className="w-3 h-3" />,
    assigned: <CheckCircle2 className="w-3 h-3" />,
    executing: <Loader2 className="w-3 h-3 animate-spin" />,
    completed: <CheckCircle2 className="w-3 h-3" />,
    failed: <XCircle className="w-3 h-3" />,
  };
  return map[status] || null;
}

function getExecutorIcon(type: string) {
  switch (type) {
    case 'robot': return <Settings2 className="w-4 h-4" />;
    case 'flashex': return <Bike className="w-4 h-4" />;
    case 'manual': return <User className="w-4 h-4" />;
    case 'camera': return <Camera className="w-4 h-4" />;
    case 'mcp': return <Plug className="w-4 h-4" />;
    case 'plugin': return <Server className="w-4 h-4" />;
    case 'drone': return <Radio className="w-4 h-4" />;
    default: return <Truck className="w-4 h-4" />;
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线', offline: '离线', busy: '忙碌', error: '故障', standby: '待命',
    submitted: '已提交', assigned: '已分配', executing: '执行中', completed: '已完成', failed: '失败',
  };
  return map[status] || status;
}

// ========== 子组件 ==========
function ExecutorCard({ executor }: { executor: PhysicalExecutor }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`bg-white rounded-xl border transition-all ${executor.status === 'error' ? 'border-red-200 shadow-red-100' : 'border-gray-200'} hover:shadow-md`}>
      <div className="p-3 flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${executor.status === 'online' ? 'bg-green-100 text-green-600' : executor.status === 'busy' ? 'bg-amber-100 text-amber-600' : 'bg-gray-100 text-gray-500'}`}>
          {getExecutorIcon(executor.type)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800 truncate">{executor.name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${getStatusColor(executor.status)}`}>
              {getStatusIcon(executor.status)}
              <span className="ml-0.5">{statusLabel(executor.status)}</span>
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[11px] text-gray-400">
            <MapPin className="w-3 h-3" />
            <span>{executor.location || '未知位置'}</span>
          </div>
        </div>
        <button onClick={() => setExpanded(!expanded)} className="text-gray-400 hover:text-gray-600">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {expanded && (
        <div className="px-3 pb-3 border-t border-gray-100 pt-2">
          {executor.battery !== undefined && (
            <div className="mb-2">
              <div className="flex items-center justify-between text-[11px] text-gray-500 mb-1">
                <span>电量</span>
                <span>{(executor.battery * 100).toFixed(0)}%</span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${executor.battery > 0.5 ? 'bg-green-500' : executor.battery > 0.2 ? 'bg-amber-500' : 'bg-red-500'}`}
                  style={{ width: `${executor.battery * 100}%` }}
                />
              </div>
            </div>
          )}
          {executor.health_score !== undefined && (
            <div className="mb-2">
              <div className="flex items-center justify-between text-[11px] text-gray-500 mb-1">
                <span>健康评分</span>
                <span>{(executor.health_score * 100).toFixed(0)}</span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${executor.health_score > 0.8 ? 'bg-green-500' : executor.health_score > 0.5 ? 'bg-amber-500' : 'bg-red-500'}`}
                  style={{ width: `${executor.health_score * 100}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-1 mt-2">
            {executor.capabilities.map((cap) => (
              <span key={cap} className="text-[10px] px-1.5 py-0.5 bg-gray-50 text-gray-500 rounded border border-gray-100">
                {cap}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TaskCard({ task }: { task: PhysicalTask }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3 hover:shadow-sm transition-all">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${getStatusColor(task.status)}`}>
            {getStatusIcon(task.status)}
            <span className="ml-0.5">{statusLabel(task.status)}</span>
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
            task.priority === 'urgent' ? 'text-red-600 bg-red-50 border-red-200' : task.priority === 'normal' ? 'text-blue-600 bg-blue-50 border-blue-200' : 'text-gray-500 bg-gray-50 border-gray-200'
          }`}>
            {task.priority === 'urgent' ? '紧急' : task.priority === 'normal' ? '普通' : '低优'}
          </span>
        </div>
        <span className="text-[10px] text-gray-400">{task.task_id}</span>
      </div>
      <div className="flex items-start gap-2 mb-1.5">
        <Package className="w-3.5 h-3.5 text-gray-400 mt-0.5 shrink-0" />
        <p className="text-sm text-gray-700 font-medium">{task.item_description}</p>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-1.5">
        <MapPin className="w-3 h-3" />
        <span>{task.target_location}</span>
        <span>·</span>
        <span>执行者: {task.provider}</span>
      </div>
      {task.error && (
        <div className="text-[11px] text-red-500 bg-red-50 rounded px-2 py-1 mt-1">
          {task.error}
        </div>
      )}
      {task.fallback_history && task.fallback_history.length > 0 && (
        <div className="text-[10px] text-gray-400 mt-1">
          降级历史: {task.fallback_history.join(' → ')}
        </div>
      )}
      <div className="flex items-center justify-between mt-2 text-[10px] text-gray-400">
        <span>创建于 {new Date(task.created_at).toLocaleTimeString('zh-CN')}</span>
        {task.updated_at && (
          <span>更新于 {new Date(task.updated_at).toLocaleTimeString('zh-CN')}</span>
        )}
      </div>
    </div>
  );
}

function HandEyeEventCard({ event }: { event: HandEyeEvent }) {
  const severityColors = {
    info: 'border-blue-200 bg-blue-50/50',
    warning: 'border-amber-200 bg-amber-50/50',
    critical: 'border-red-200 bg-red-50/50',
  };
  const severityIcons = {
    info: <Eye className="w-3 h-3 text-blue-500" />,
    warning: <AlertTriangle className="w-3 h-3 text-amber-500" />,
    critical: <Shield className="w-3 h-3 text-red-500" />,
  };

  return (
    <div className={`rounded-lg border p-2.5 ${severityColors[event.severity]}`}>
      <div className="flex items-start gap-2">
        <div className="mt-0.5">{severityIcons[event.severity]}</div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-700">{event.description}</p>
          <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
            <span>{new Date(event.timestamp).toLocaleTimeString('zh-CN')}</span>
            {event.camera_id && <span>📷 {event.camera_id}</span>}
            {event.executor_id && <span>🤖 {event.executor_id}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ========== 新建任务弹窗 ==========
function CreateTaskModal({ onClose, onCreate }: { onClose: () => void; onCreate: (task: Partial<PhysicalTask>) => void }) {
  const [action, setAction] = useState<'deliver' | 'retrieve' | 'notify'>('deliver');
  const [location, setLocation] = useState('');
  const [item, setItem] = useState('');
  const [provider, setProvider] = useState('auto');
  const [priority, setPriority] = useState<'urgent' | 'normal' | 'low'>('normal');

  const handleSubmit = () => {
    if (!location.trim() || !item.trim()) return;
    onCreate({
      action,
      target_location: location,
      item_description: item,
      provider,
      priority,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900">🦾 创建物理任务</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">任务类型</label>
            <div className="flex gap-2">
              {[
                { value: 'deliver' as const, label: '配送', icon: Truck },
                { value: 'retrieve' as const, label: '取回', icon: Package },
                { value: 'notify' as const, label: '通知', icon: Send },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setAction(opt.value)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border transition-colors flex-1 justify-center ${
                    action === opt.value
                      ? 'bg-tent-50 text-tent-700 border-tent-200'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <opt.icon className="w-3.5 h-3.5" />
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">目标位置</label>
            <div className="relative">
              <MapPin className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="例如：会议室A、前台、办公区..."
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">物品/任务描述</label>
            <div className="relative">
              <Package className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={item}
                onChange={(e) => setItem(e.target.value)}
                placeholder="例如：咖啡 x2、文件袋、外卖..."
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">执行者</label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100 bg-white"
            >
              <option value="auto">🤖 自动选择（推荐）</option>
              <option value="realman">睿尔曼机械臂</option>
              <option value="flashex">闪送</option>
              <option value="manual">人工</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">优先级</label>
            <div className="flex gap-2">
              {[
                { value: 'urgent' as const, label: '紧急', color: 'text-red-600 bg-red-50 border-red-200' },
                { value: 'normal' as const, label: '普通', color: 'text-blue-600 bg-blue-50 border-blue-200' },
                { value: 'low' as const, label: '低优', color: 'text-gray-500 bg-gray-50 border-gray-200' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setPriority(opt.value)}
                  className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
                    priority === opt.value ? opt.color : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors">取消</button>
          <button
            onClick={handleSubmit}
            disabled={!location.trim() || !item.trim()}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-tent-600 hover:bg-tent-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
          >
            <Zap className="w-4 h-4" />
            创建任务
          </button>
        </div>
      </div>
    </div>
  );
}

// ========== 添加设备弹窗 ==========
function AddDeviceModal({ onClose, onAdd }: { onClose: () => void; onAdd: (device: { name: string; type: string; config: Record<string, any> }) => void }) {
  const [name, setName] = useState('');
  const [dtype, setDtype] = useState<'mcp' | 'http'>('mcp');
  const [transport, setTransport] = useState<'sse' | 'stdio'>('sse');
  const [url, setUrl] = useState('');
  const [location, setLocation] = useState('');

  const handleSubmit = () => {
    if (!name.trim()) return;
    const config: Record<string, any> = { location: location || '未知位置' };
    if (dtype === 'mcp') {
      config.transport = transport;
      if (transport === 'sse' && url.trim()) config.url = url.trim();
      if (transport === 'stdio') {
        config.command = 'python';
        config.args = ['-m', 'mcp_server_example'];
      }
    } else {
      if (url.trim()) config.url = url.trim();
    }
    onAdd({ name: name.trim(), type: dtype, config });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900">🔌 添加物理设备</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">设备名称</label>
            <input
              type="text" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="例如：机械臂-02、智能灯控..."
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">连接类型</label>
            <div className="flex gap-2">
              {[
                { value: 'mcp' as const, label: 'MCP 插件', desc: '通过 MCP Server 连接' },
                { value: 'http' as const, label: 'HTTP API', desc: '直接 HTTP 接口' },
              ].map((opt) => (
                <button key={opt.value} onClick={() => setDtype(opt.value)}
                  className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium border transition-colors text-left ${
                    dtype === opt.value ? 'bg-tent-50 text-tent-700 border-tent-200' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}>
                  <div className="font-medium">{opt.label}</div>
                  <div className="text-[10px] text-gray-400 mt-0.5">{opt.desc}</div>
                </button>
              ))}
            </div>
          </div>
          {dtype === 'mcp' && (
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1.5 block">传输方式</label>
              <select value={transport} onChange={(e) => setTransport(e.target.value as any)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100 bg-white">
                <option value="sse">SSE (Server-Sent Events)</option>
                <option value="stdio">Stdio (本地进程)</option>
              </select>
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">
              {dtype === 'mcp' && transport === 'sse' ? 'SSE URL' : 'API 地址'}
            </label>
            <input
              type="text" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder={dtype === 'mcp' ? 'http://localhost:8001/sse' : 'http://device-ip:8080/api'}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">位置</label>
            <input
              type="text" value={location} onChange={(e) => setLocation(e.target.value)}
              placeholder="例如：会议室A、前台..."
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
            />
          </div>
        </div>
        <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors">取消</button>
          <button onClick={handleSubmit} disabled={!name.trim()}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-tent-600 hover:bg-tent-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5">
            <Plus className="w-4 h-4" />
            添加设备
          </button>
        </div>
      </div>
    </div>
  );
}


// ========== 主组件 ==========
export function PhysicalWorldPanel() {
  // const { state: aiState } = useAIState();
  const [executors, setExecutors] = useState<PhysicalExecutor[]>([]);
  const [tasks, setTasks] = useState<PhysicalTask[]>([]);
  const [events, setEvents] = useState<HandEyeEvent[]>([]);
  const [status, setStatus] = useState<PhysicalStatus | null>(null);
  const [, setLevelInfo] = useState<LevelInfo>({ level: 1, title: '新手' });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddDeviceModal, setShowAddDeviceModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'executors' | 'tasks' | 'handeye' | 'memorymap' | 'spatialmap' | 'scene' | 'metacognition'>('executors');
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [spatialMemories, setSpatialMemories] = useState<any[]>([]);
  const [patterns, setPatterns] = useState<any[]>([]);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [visionObjects, setVisionObjects] = useState<any[]>([]);
  const [visionKeyword, setVisionKeyword] = useState('');
  const [visionSearchResults, setVisionSearchResults] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]);
  const [evalSummary, setEvalSummary] = useState<any>(null);
  const [evalTrends, setEvalTrends] = useState<any[]>([]);
  const [currentPersona, setCurrentPersona] = useState<string>('work');
  const [maintenanceLogs, setMaintenanceLogs] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const { showToast } = useToast();

  // 从后端加载真实数据
  const loadData = useCallback(async () => {
    try {
      const [executorsRes, tasksRes, statusRes, levelRes, summaryRes, patternsRes, anomaliesRes, objectsRes, evalRecentRes, evalSummaryRes, personaRes, maintenanceRes] = await Promise.all([
        fetch('/ui/api/physical/executors').then((r) => r.json()).catch(() => ({ executors: [] })),
        fetch('/ui/api/physical/tasks').then((r) => r.json()).catch(() => ({ tasks: [] })),
        fetch('/ui/api/physical/status').then((r) => r.json()).catch(() => ({ enabled: false })),
        fetch('/ui/api/six-axis').then((r) => r.json()).catch(() => null),
        fetch('/ui/api/vision/summary?hours=24').then((r) => r.json()).catch(() => ({ memories: [] })),
        fetch('/ui/api/vision/patterns?days=7').then((r) => r.json()).catch(() => ({ patterns: [] })),
        fetch('/ui/api/vision/anomalies?window_hours=24').then((r) => r.json()).catch(() => ({ anomalies: [] })),
        fetch('/ui/api/vision/objects').then((r) => r.json()).catch(() => ({ objects: [] })),
        fetch('/ui/api/evaluation/recent?limit=10').then((r) => r.json()).catch(() => ({ evaluations: [] })),
        fetch('/ui/api/evaluation/summary?days=7').then((r) => r.json()).catch(() => ({ summary: {}, trends: [] })),
        fetch('/ui/api/persona/mode').then((r) => r.json()).catch(() => ({ mode: 'work' })),
        fetch('/ui/api/memory/maintenance').then((r) => r.json()).catch(() => ({ logs: [] })),
      ]);

      setExecutors(executorsRes.executors || []);
      setTasks(tasksRes.tasks || []);
      setStatus(statusRes);
      setSpatialMemories(summaryRes.memories || []);
      setPatterns(patternsRes.patterns || []);
      setAnomalies(anomaliesRes.anomalies || []);
      setVisionObjects(objectsRes.objects || []);
      setEvaluations(evalRecentRes.evaluations || []);
      setEvalSummary(evalSummaryRes.summary || null);
      setEvalTrends(evalSummaryRes.trends || []);
      setCurrentPersona(personaRes.mode || 'work');
      setMaintenanceLogs(maintenanceRes.logs || []);

      if (levelRes && levelRes.title) {
        const thresholds = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
        const avg = levelRes.avg_score || 0;
        let lvl = 1;
        for (let i = 1; i < thresholds.length; i++) { if (avg >= thresholds[i]) lvl = i + 1; else break; }
        setLevelInfo({ level: lvl, title: levelRes.title });
      }

      // 物理世界状态可用于影响 AI 情绪（通过 WebSocket 通知后端）
      const activeTasks = (tasksRes.tasks || []).filter((t: PhysicalTask) => t.status === 'executing' || t.status === 'assigned');
      const hasError = (executorsRes.executors || []).some((e: PhysicalExecutor) => e.status === 'error');
      const allOnline = (executorsRes.executors || []).length > 0 && (executorsRes.executors || []).every((e: PhysicalExecutor) => e.status === 'online' || e.status === 'standby');
      void { hasError, activeTasks, allOnline }; // 保留状态分析逻辑，情绪由后端驱动
    } catch {
      // 静默失败，保留上次数据
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // WebSocket 连接用于手眼联动实时事件
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'vision.objects_detected') {
          const objects = msg.payload?.objects || [];
          const names = objects.map((o: any) => o.name).filter(Boolean).join(', ');
          const hasPerson = objects.some((o: any) => (o.name || '').toLowerCase() === 'person' && (o.confidence || 0) > 0.7);
          const newEvent: HandEyeEvent = {
            id: `he_${Date.now()}`,
            timestamp: new Date().toISOString(),
            type: hasPerson ? 'safety_alert' : 'vision_detect',
            description: names ? `检测到: ${names}` : '视觉检测到新物体',
            camera_id: msg.payload?.camera_id || 'camera_01',
            severity: hasPerson ? 'warning' : 'info',
          };
          setEvents((prev) => [newEvent, ...prev].slice(0, 50));
        }
        // FIX: 实时同步人格切换（聊天面板切换 → WebSocket 广播 → 仪表盘即时更新）
        if (msg.type === 'persona.changed') {
          const newMode = msg.payload?.mode;
          if (newMode) {
            setCurrentPersona(newMode);
            showToast?.(`人格切换为: ${newMode === 'work' ? '秘书' : newMode === 'casual' ? '管家' : newMode === 'emergency' ? '应急' : newMode === 'learning' ? '导师' : newMode === 'creative' ? '创意' : newMode}`, 'info');
          }
        }
      } catch {
        // ignore
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setTimeout(() => setRefreshing(false), 500);
  };

  const handleVisionSearch = async () => {
    if (!visionKeyword.trim()) return;
    try {
      const resp = await fetch(`/ui/api/vision/memory/query?keyword=${encodeURIComponent(visionKeyword)}`);
      const data = await resp.json();
      setVisionSearchResults(data.results || []);
    } catch {
      showToast('搜索失败', 'error');
    }
  };

  const handleEmergencyStop = async () => {
    if (!confirm('⚠️ 确定要紧急停止所有物理任务吗？\n\n这将立即停止所有机器人、闪送等物理执行器的任务。')) return;
    try {
      const resp = await fetch('/ui/api/physical/emergency_stop', { method: 'POST' });
      if (resp.ok) {
        showToast('🛑 紧急停止已发送', 'success');
        await loadData();
      } else {
        showToast('紧急停止失败', 'error');
      }
    } catch {
      showToast('紧急停止请求失败', 'error');
    }
  };

  const handleCreateTask = async (taskData: Partial<PhysicalTask>) => {
    try {
      const resp = await fetch('/ui/api/physical/tasks/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: taskData.action,
          target_location: taskData.target_location,
          item_description: taskData.item_description,
          provider: taskData.provider,
          priority: taskData.priority,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        showToast(data.message || '物理任务已创建', 'success');
        await loadData();
      } else {
        const err = await resp.json();
        showToast(err.detail || '创建任务失败', 'error');
      }
    } catch {
      showToast('后端未连接，任务创建失败', 'error');
    }
  };

  const handleAddDevice = async (device: { name: string; type: string; config: Record<string, any> }) => {
    try {
      const resp = await fetch('/ui/api/physical/executors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(device),
      });
      if (resp.ok) {
        const data = await resp.json();
        showToast(data.message || '设备已注册', 'success');
        await loadData();
      } else {
        const err = await resp.json();
        showToast(err.detail || '注册设备失败', 'error');
      }
    } catch {
      showToast('后端未连接', 'error');
    }
  };

  const onlineCount = executors.filter((e) => e.status === 'online').length;
  const busyCount = executors.filter((e) => e.status === 'busy').length;
  const activeTaskCount = tasks.filter((t) => t.status === 'executing' || t.status === 'assigned').length;
  const cameraCount = executors.filter((e) => e.type === 'camera').length;

  const isEnabled = status?.enabled ?? false;

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <AvatarHomeButton source="physical" size={40} showLevelRing={false} showParticles={false} />
            <div>
              <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                物理世界控制
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                {isEnabled
                  ? `AI 的眼睛和手 — ${executors.length} 个设备在线`
                  : '物理执行器未启用 — 请在 config/tent_os.yaml 中配置'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-colors ${refreshing ? 'animate-spin' : ''}`}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-tent-600 hover:bg-tent-700 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              新建任务
            </button>
            <button
              onClick={handleEmergencyStop}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              紧急停止
            </button>
          </div>
        </div>

        {/* 未启用提示 */}
        {!isEnabled && !loading && (
          <div className="mb-5 bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">物理执行器未配置</p>
              <p className="text-xs text-amber-600 mt-1">
                请在 <code className="bg-amber-100 px-1 py-0.5 rounded">config/tent_os.yaml</code> 中取消注释
                <code className="bg-amber-100 px-1 py-0.5 rounded">physical_executors</code> 段，然后重启服务。
              </p>
            </div>
          </div>
        )}

        {/* 统计卡片 */}
        <div className="grid grid-cols-5 gap-4 mb-5">
          <StatCard icon={<Eye className="w-4 h-4 text-blue-500" />} label="摄像头在线" value={`${cameraCount}`} sub="AI 的眼睛" trend="normal" />
          <StatCard icon={<Settings2 className="w-4 h-4 text-purple-500" />} label="执行器在线" value={`${onlineCount}`} sub="机器人和骑手" trend="normal" />
          <StatCard icon={<Activity className="w-4 h-4 text-amber-500" />} label="忙碌中" value={`${busyCount}`} sub="正在执行任务" trend={busyCount > 2 ? 'high' : 'normal'} />
          <StatCard icon={<Zap className="w-4 h-4 text-green-500" />} label="活跃任务" value={`${activeTaskCount}`} sub="执行中/已分配" trend={activeTaskCount > 3 ? 'high' : 'normal'} />
          <StatCard icon={<Brain className="w-4 h-4 text-indigo-500" />} label="当前人格" value={currentPersona === 'work' ? '秘书' : currentPersona === 'casual' ? '管家' : currentPersona === 'emergency' ? '应急' : currentPersona === 'learning' ? '导师' : currentPersona === 'creative' ? '创意' : currentPersona} sub="记忆隔离中" trend="normal" />
        </div>

        {/* Tab 切换 */}
        <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1 mb-5 w-fit">
          {[
            { key: 'executors' as const, label: '执行器', icon: Settings2 },
            { key: 'tasks' as const, label: '任务列表', icon: Truck },
            { key: 'handeye' as const, label: '手眼联动', icon: Eye },
            { key: 'memorymap' as const, label: '记忆地图', icon: Brain },
            { key: 'spatialmap' as const, label: '足迹地图', icon: MapPin },
            { key: 'scene' as const, label: '场景引擎', icon: Settings2 },
            { key: 'metacognition' as const, label: 'AI自评', icon: Activity },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-white text-tent-700 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* 执行器面板 */}
        {activeTab === 'executors' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">物理执行器状态</h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">{executors.length} 个设备</span>
                <button
                  onClick={() => setShowAddDeviceModal(true)}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-tent-600 bg-tent-50 hover:bg-tent-100 border border-tent-200 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  添加设备
                </button>
              </div>
            </div>
            {executors.length === 0 ? (
              <div className="text-center py-12 text-gray-400 bg-gray-50 rounded-xl border border-dashed border-gray-200">
                <Plug className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">暂无物理执行器</p>
                <p className="text-xs mt-1">配置 physical_executors 或添加 MCP 插件</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {executors.map((executor) => (
                  <ExecutorCard key={executor.id} executor={executor} />
                ))}
              </div>
            )}

            {/* 摄像头专项区域 */}
            <div className="mt-4">
              <h3 className="text-sm font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <Camera className="w-4 h-4 text-blue-500" />
                视觉感知网络
              </h3>
              <div className="bg-blue-50/50 border border-blue-200 rounded-xl p-4">
                <div className="grid grid-cols-3 gap-3">
                  {executors.filter((e) => e.type === 'camera').map((cam) => (
                    <div key={cam.id} className="bg-white rounded-lg border border-blue-100 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-2 h-2 rounded-full ${cam.status === 'online' ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
                        <span className="text-xs font-medium text-gray-700">{cam.name}</span>
                      </div>
                      <p className="text-[10px] text-gray-400">{cam.location}</p>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {cam.capabilities.slice(0, 2).map((c) => (
                          <span key={c} className="text-[9px] px-1 py-0.5 bg-blue-50 text-blue-600 rounded">{c}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                  <button
                    onClick={() => setShowAddDeviceModal(true)}
                    className="bg-white/60 rounded-lg border border-dashed border-blue-200 p-3 flex flex-col items-center justify-center text-blue-400 hover:bg-white hover:border-blue-300 transition-colors min-h-[80px]"
                  >
                    <Plus className="w-4 h-4 mb-1" />
                    <span className="text-[10px]">添加摄像头</span>
                  </button>
                </div>
                <p className="text-[11px] text-blue-600 mt-2">
                  💡 提示：摄像头不仅限于本机，可以添加网络摄像头、IP Camera、手机摄像头等。AI 通过这些"眼睛"观察物理世界。
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 任务列表面板 */}
        {activeTab === 'tasks' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">物理任务</h3>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-400">
                  共 {tasks.length} 个任务 · {tasks.filter((t) => t.status === 'submitted').length} 等待中
                </span>
              </div>
            </div>
            <div className="space-y-2">
              {tasks.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">暂无物理任务</p>
                  <p className="text-xs mt-1">点击右上角"新建任务"开始</p>
                </div>
              ) : (
                tasks.map((task) => <TaskCard key={task.task_id} task={task} />)
              )}
            </div>
          </div>
        )}

        {/* 手眼联动面板 */}
        {activeTab === 'handeye' && (
          <div className="space-y-4">
            <div className="bg-gradient-to-r from-tent-50 to-blue-50 rounded-xl border border-tent-100 p-4">
              <h3 className="text-sm font-semibold text-gray-800 mb-1 flex items-center gap-2">
                <Eye className="w-4 h-4 text-tent-600" />
                🤝 手眼协调中心
              </h3>
              <p className="text-xs text-gray-500">
                AI 的"眼睛"（摄像头）看到的信息，会实时指导"手"（机器人/闪送）的行动。
                当摄像头检测到人员靠近时，机器人会自动减速；当检测到障碍物时，会重新规划路径。
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <h4 className="text-xs font-semibold text-gray-700 mb-2">最近事件</h4>
                <div className="space-y-2">
                  {events.length === 0 ? (
                    <div className="text-center py-6 text-gray-400 text-xs">
                      <Eye className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p>暂无事件</p>
                      <p className="mt-0.5">视觉检测事件将实时显示在这里</p>
                    </div>
                  ) : (
                    events.map((event) => (
                      <HandEyeEventCard key={event.id} event={event} />
                    ))
                  )}
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-700 mb-2">协调规则</h4>
                <div className="space-y-2">
                  <RuleCard
                    icon={<Eye className="w-3.5 h-3.5 text-blue-500" />}
                    title="人员检测 → 减速避让"
                    desc="摄像头检测到人员进入安全区域时，机器人自动减速并暂停"
                    status="active"
                  />
                  <RuleCard
                    icon={<Shield className="w-3.5 h-3.5 text-green-500" />}
                    title="障碍物检测 → 路径重规划"
                    desc="YOLO 检测到新障碍物时，触发 EmbodiedPlanner 重新规划路径"
                    status="active"
                  />
                  <RuleCard
                    icon={<Zap className="w-3.5 h-3.5 text-amber-500" />}
                    title="视觉确认 → 任务执行"
                    desc="摄像头确认目标位置安全后，机器人才开始执行配送任务"
                    status="active"
                  />
                  <RuleCard
                    icon={<AlertTriangle className="w-3.5 h-3.5 text-red-500" />}
                    title="安全警报 → 紧急停止"
                    desc="检测到危险情况时，立即触发所有物理执行器的紧急停止"
                    status="active"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 足迹地图面板 */}
        {activeTab === 'spatialmap' && <SpatialMapPanel />}

        {/* 场景引擎面板 */}
        {activeTab === 'scene' && <SceneControlPanel />}

        {/* 元认知仪表盘面板 */}
        {activeTab === 'metacognition' && (
          <div className="space-y-4">
            {/* 顶部信息栏 */}
            <div className="bg-gradient-to-r from-indigo-50 via-white to-purple-50 rounded-xl border border-indigo-100 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-indigo-600" />
                    🪞 AI 的元认知仪表盘
                  </h3>
                  <p className="text-xs text-gray-500 mt-1">
                    AI 在完成每项任务后都会自我评估。这里展示的是它的"内心活动"——它知道自己做得好不好。
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-center">
                    <div className="text-lg font-bold text-indigo-600">{evalSummary?.total_evaluations || 0}</div>
                    <div className="text-[10px] text-gray-400">近7天评估</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-emerald-600">{evalSummary?.passed_count || 0}</div>
                    <div className="text-[10px] text-gray-400">通过</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-amber-600">{evalSummary?.avg_score ? (evalSummary.avg_score * 100).toFixed(0) : 0}%</div>
                    <div className="text-[10px] text-gray-400">平均分</div>
                  </div>
                </div>
              </div>
            </div>

            {evaluations.length === 0 ? (
              <div className="text-center py-16 text-gray-400 bg-gray-50 rounded-xl border border-dashed border-gray-200">
                <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">暂无评估记录</p>
                <p className="text-xs mt-1">完成复杂任务后，AI 会自动生成自我评估</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                {/* 左：雷达图 + 统计 */}
                <div className="space-y-4">
                  {/* 5维雷达图 */}
                  <div className="bg-white rounded-xl border border-gray-200 p-4">
                    <h4 className="text-xs font-semibold text-gray-700 mb-3">当前人格「{currentPersona}」的自我评价维度</h4>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <RadarChart data={[
                          { subject: '完整性', A: Math.round((evalSummary?.criteria_averages?.completeness || 0) * 100), fullMark: 100 },
                          { subject: '正确性', A: Math.round((evalSummary?.criteria_averages?.correctness || 0) * 100), fullMark: 100 },
                          { subject: '安全性', A: Math.round((evalSummary?.criteria_averages?.safety || 0) * 100), fullMark: 100 },
                          { subject: '效率', A: Math.round((evalSummary?.criteria_averages?.efficiency || 0) * 100), fullMark: 100 },
                          { subject: '质量', A: Math.round((evalSummary?.criteria_averages?.quality || 0) * 100), fullMark: 100 },
                        ]}>
                          <PolarGrid />
                          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} />
                          <Radar name="自评" dataKey="A" stroke="#6366f1" fill="#6366f1" fillOpacity={0.25} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* 每日趋势 */}
                  {evalTrends.length > 0 && (
                    <div className="bg-white rounded-xl border border-gray-200 p-4">
                      <h4 className="text-xs font-semibold text-gray-700 mb-3">近7天评估趋势</h4>
                      <div className="h-40">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={evalTrends}>
                            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                            <YAxis tick={{ fontSize: 10 }} />
                            <RechartsTooltip
                              contentStyle={{ fontSize: 12, borderRadius: 8 }}
                              formatter={(value: any, name: any) => {
                                if (name === 'avg_score') return [`${(value * 100).toFixed(0)}%`, '平均分'];
                                return [value, name === 'count' ? '评估数' : name];
                              }}
                            />
                            <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {/* Phase 3: 记忆整理日志 */}
                  {maintenanceLogs.length > 0 && (
                    <div className="bg-white rounded-xl border border-gray-200 p-4">
                      <h4 className="text-xs font-semibold text-gray-700 mb-3 flex items-center gap-1">
                        <Brain className="w-3 h-3 text-purple-500" />
                        记忆整理记录
                      </h4>
                      <div className="space-y-2 max-h-[200px] overflow-y-auto pr-1">
                        {maintenanceLogs.map((log: any, idx: number) => (
                          <div key={idx} className="text-xs bg-gray-50 rounded-lg p-2">
                            <div className="flex items-center justify-between">
                              <span className="font-medium text-gray-700">
                                {log.event === 'scene_left_demote' ? `🧹 离开${log.scene}` : '⏰ 定时整理'}
                              </span>
                              <span className="text-[10px] text-gray-400">{log.timestamp?.slice(0, 16).replace('T', ' ')}</span>
                            </div>
                            <p className="text-gray-500 mt-0.5">{log.reason}</p>
                            {(log.demoted_count > 0 || log.expired_count > 0) && (
                              <div className="flex gap-2 mt-1">
                                {log.demoted_count > 0 && (
                                  <span className="text-[10px] px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded">降温 {log.demoted_count} 条</span>
                                )}
                                {log.expired_count > 0 && (
                                  <span className="text-[10px] px-1.5 py-0.5 bg-red-50 text-red-600 rounded">过期 {log.expired_count} 条</span>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* 右：最近评估列表 */}
                <div className="bg-white rounded-xl border border-gray-200 p-4">
                  <h4 className="text-xs font-semibold text-gray-700 mb-3">最近自我评估</h4>
                  <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                    {evaluations.map((ev: any) => (
                      <div key={ev.id} className={`rounded-lg border p-3 ${ev.passed ? 'border-emerald-100 bg-emerald-50/30' : ev.retry_recommended ? 'border-amber-100 bg-amber-50/30' : 'border-red-100 bg-red-50/30'}`}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${ev.passed ? 'bg-emerald-100 text-emerald-700' : ev.retry_recommended ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                              {ev.passed ? '通过' : ev.retry_recommended ? '已重试' : '未通过'}
                            </span>
                            <span className="text-[10px] text-gray-400">{ev.persona}</span>
                          </div>
                          <span className="text-[10px] text-gray-400">{ev.timestamp?.slice(0, 16).replace('T', ' ')}</span>
                        </div>
                        <p className="text-xs text-gray-700 font-medium truncate">{ev.task_summary || '未命名任务'}</p>
                        <div className="flex items-center gap-3 mt-2">
                          <div className="flex-1">
                            <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
                              <span>综合评分</span>
                              <span className="font-medium text-indigo-600">{(ev.overall_score * 100).toFixed(0)}%</span>
                            </div>
                            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${ev.overall_score >= 0.7 ? 'bg-emerald-400' : ev.overall_score >= 0.5 ? 'bg-amber-400' : 'bg-red-400'}`}
                                style={{ width: `${ev.overall_score * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                        {ev.feedback && (
                          <p className="text-[11px] text-gray-500 mt-2 leading-relaxed italic">"{ev.feedback}"</p>
                        )}
                        {/* 5维细分明细 */}
                        <div className="grid grid-cols-5 gap-1 mt-2">
                          {Object.entries(ev.criteria_scores || {}).map(([key, score]: [string, any]) => (
                            <div key={key} className="text-center">
                              <div className="text-[9px] text-gray-400">{key === 'completeness' ? '完整' : key === 'correctness' ? '正确' : key === 'safety' ? '安全' : key === 'efficiency' ? '效率' : key === 'quality' ? '质量' : key}</div>
                              <div className={`text-[10px] font-bold ${(score as number) >= 0.7 ? 'text-emerald-600' : (score as number) >= 0.5 ? 'text-amber-600' : 'text-red-600'}`}>
                                {((score as number) * 100).toFixed(0)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 记忆地图面板 */}
        {activeTab === 'memorymap' && (
          <div className="space-y-4">
            {/* 顶部信息栏 */}
            <div className="bg-gradient-to-r from-purple-50 to-tent-50 rounded-xl border border-purple-100 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                    <Brain className="w-4 h-4 text-purple-600" />
                    🧠 AI 的空间记忆地图
                  </h3>
                  <p className="text-xs text-gray-500 mt-1">
                    AI 通过摄像头持续观察物理世界，在这里记录它看到的一切、发现的规律、和注意到的异常。
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-center">
                    <div className="text-lg font-bold text-purple-600">{patterns.length}</div>
                    <div className="text-[10px] text-gray-400">已发现规律</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-amber-600">{anomalies.length}</div>
                    <div className="text-[10px] text-gray-400">异常告警</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-blue-600">{visionObjects.length}</div>
                    <div className="text-[10px] text-gray-400">已知物体</div>
                  </div>
                </div>
              </div>
            </div>

            {/* 搜索框 */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={visionKeyword}
                  onChange={(e) => setVisionKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleVisionSearch()}
                  placeholder="搜索视觉记忆：遥控器、设备A、前台..."
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 text-sm focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-100"
                />
              </div>
              <button
                onClick={handleVisionSearch}
                className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 transition-colors"
              >
                搜索
              </button>
            </div>

            {/* 搜索结果 */}
            {visionSearchResults.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-3">
                <h4 className="text-xs font-semibold text-gray-700 mb-2">搜索结果</h4>
                <div className="space-y-2">
                  {visionSearchResults.map((r: any) => (
                    <div key={r.id} className="text-xs text-gray-600 bg-gray-50 rounded-lg p-2">
                      <span className="text-gray-400">{r.created_at?.slice(11, 16)}</span>
                      <span className="mx-1">·</span>
                      <span>{r.description}</span>
                      {r.scene_type && <span className="ml-1 text-purple-500">[{r.scene_type}]</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-4">
              {/* 左：时间轴 */}
              <div className="col-span-1">
                <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  最近观察（24小时）
                </h4>
                <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
                  {spatialMemories.length === 0 ? (
                    <div className="text-center py-6 text-gray-400 text-xs">
                      <Eye className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p>暂无观察记录</p>
                      <p className="mt-0.5">摄像头数据将自动显示</p>
                    </div>
                  ) : (
                    spatialMemories.map((mem: any) => (
                      <div key={mem.id} className="bg-white rounded-lg border border-gray-100 p-2.5 text-xs">
                        <div className="flex items-center gap-1.5 text-gray-400 mb-1">
                          <span className="font-mono">{mem.created_at?.slice(11, 16)}</span>
                          {mem.scene_type && (
                            <span className="text-[10px] px-1 py-0 bg-purple-50 text-purple-600 rounded">{mem.scene_type}</span>
                          )}
                        </div>
                        <p className="text-gray-700 leading-relaxed">{mem.description}</p>
                        {mem.objects && mem.objects.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {mem.objects.map((obj: any, i: number) => (
                              <span key={i} className="text-[10px] px-1 py-0.5 bg-gray-50 text-gray-500 rounded border border-gray-100">
                                {obj.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* 中：规律 */}
              <div className="col-span-1">
                <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1">
                  <Lightbulb className="w-3 h-3" />
                  我发现的规律
                </h4>
                <div className="space-y-2">
                  {patterns.length === 0 ? (
                    <div className="text-center py-6 text-gray-400 text-xs bg-gray-50 rounded-xl border border-dashed border-gray-200">
                      <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p>规律积累中</p>
                      <p className="mt-0.5">需要至少3天数据才能发现模式</p>
                    </div>
                  ) : (
                    patterns.map((p: any, idx: number) => (
                      <div key={idx} className="bg-white rounded-lg border border-purple-100 p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium text-gray-800">{p.object}</span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded-full">
                            置信度 {(p.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-500">{p.pattern}</p>
                        <p className="text-[10px] text-gray-400 mt-1">
                          过去{p.total_days}天出现{p.occurrences}次
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* 右：异常 */}
              <div className="col-span-1">
                <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  需要注意的事
                </h4>
                <div className="space-y-2">
                  {anomalies.length === 0 ? (
                    <div className="text-center py-6 text-gray-400 text-xs bg-green-50 rounded-xl border border-dashed border-green-200">
                      <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-30 text-green-500" />
                      <p>一切正常</p>
                      <p className="mt-0.5">未发现与历史模式偏离的异常</p>
                    </div>
                  ) : (
                    anomalies.map((a: any, idx: number) => (
                      <div key={idx} className={`bg-white rounded-lg border p-3 ${
                        a.severity === 'warning' ? 'border-amber-200 bg-amber-50/30' : 'border-red-200 bg-red-50/30'
                      }`}>
                        <div className="flex items-center gap-1.5 mb-1">
                          {a.severity === 'warning' ? (
                            <AlertTriangle className="w-3 h-3 text-amber-500" />
                          ) : (
                            <AlertTriangle className="w-3 h-3 text-red-500" />
                          )}
                          <span className="text-xs font-medium text-gray-800">{a.object}</span>
                        </div>
                        <p className="text-[11px] text-gray-500">
                          {a.type === 'missing_pattern' ? '未按规律出现' : '不常见物体'}
                        </p>
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          {a.expected} · 实际{a.actual}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* 底部：物体清单 */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <h4 className="text-xs font-semibold text-gray-700 mb-3">已知物体清单</h4>
              {visionObjects.length === 0 ? (
                <p className="text-xs text-gray-400">暂无追踪中的物体</p>
              ) : (
                <div className="grid grid-cols-4 gap-2">
                  {visionObjects.map((obj: any, idx: number) => (
                    <div key={idx} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                      <Package className="w-3 h-3 text-gray-400" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-gray-700 truncate">{obj.object_name}</p>
                        <p className="text-[10px] text-gray-400 truncate">{obj.location || '位置未知'}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showCreateModal && (
        <CreateTaskModal onClose={() => setShowCreateModal(false)} onCreate={handleCreateTask} />
      )}
      {showAddDeviceModal && (
        <AddDeviceModal onClose={() => setShowAddDeviceModal(false)} onAdd={handleAddDevice} />
      )}
    </div>
  );
}

// ========== 辅助组件 ==========
function StatCard({ icon, label, value, sub, trend }: { icon: React.ReactNode; label: string; value: string; sub?: string; trend?: 'high' | 'normal' | 'low' }) {
  const trendColor = trend === 'high' ? 'bg-red-100 text-red-600' : trend === 'normal' ? 'bg-amber-100 text-amber-600' : 'bg-green-100 text-green-600';
  const trendLabel = trend === 'high' ? '高' : trend === 'normal' ? '中' : '低';
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs text-gray-500">{label}</span>
        </div>
        {trend && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${trendColor}`}>
            {trendLabel}
          </span>
        )}
      </div>
      <div className="text-xl font-bold text-gray-900">{value}</div>
      {sub && <div className="text-[10px] text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

function RuleCard({ icon, title, desc, status }: { icon: React.ReactNode; title: string; desc: string; status: 'active' | 'disabled' }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5">{icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">{title}</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${status === 'active' ? 'bg-green-50 text-green-600' : 'bg-gray-50 text-gray-400'}`}>
              {status === 'active' ? '已启用' : '已禁用'}
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mt-0.5 leading-relaxed">{desc}</p>
        </div>
      </div>
    </div>
  );
}
