import { useState, useEffect, useRef, useCallback } from 'react';
import { ScrollText, Pause, Play, Trash2, Download } from 'lucide-react';

interface LogLine {
  type: 'history' | 'live';
  line: string;
  id: number;
}

export function LogsPanel() {
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [filter, setFilter] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const idCounter = useRef(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const bufferRef = useRef<LogLine[]>([]);

  const flushBuffer = useCallback(() => {
    if (bufferRef.current.length === 0) return;
    setLogs((prev) => {
      const next = [...prev, ...bufferRef.current];
      bufferRef.current = [];
      // 限制最大行数，避免内存溢出
      if (next.length > 5000) {
        return next.slice(next.length - 5000);
      }
      return next;
    });
  }, []);

  // SSE 自动重连（指数退避）
  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    const maxReconnectDelay = 30000; // 最大30秒

    const connect = () => {
      if (es) {
        try { es.close(); } catch {}
      }
      es = new EventSource('/api/v1/logs/stream?lines=200');
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
        reconnectAttempt = 0;
      };

      es.onerror = () => {
        setIsConnected(false);
        if (es) {
          try { es.close(); } catch {}
          es = null;
        }
        // 指数退避重连
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), maxReconnectDelay);
        reconnectAttempt++;
        reconnectTimer = setTimeout(connect, delay);
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'history' || data.type === 'live') {
            bufferRef.current.push({
              type: data.type,
              line: data.line,
              id: idCounter.current++,
            });
          }
        } catch {
          bufferRef.current.push({
            type: 'live',
            line: event.data,
            id: idCounter.current++,
          });
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (es) {
        try { es.close(); } catch {}
      }
    };
  }, []);

  // 定期刷新缓冲区（降低渲染频率）
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isPaused) {
        flushBuffer();
      }
    }, 200);
    return () => clearInterval(interval);
  }, [isPaused, flushBuffer]);

  // 自动滚动到底部
  useEffect(() => {
    if (!isPaused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isPaused]);

  const filteredLogs = filter
    ? logs.filter((l) => l.line.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  const clearLogs = () => setLogs([]);

  const downloadLogs = () => {
    const text = logs.map((l) => l.line).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tent-os-logs-${new Date().toISOString().slice(0, 19)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // 解析日志级别颜色
  const getLineColor = (line: string): string => {
    if (line.includes('ERROR')) return 'text-red-600';
    if (line.includes('WARNING')) return 'text-amber-600';
    if (line.includes('INFO')) return 'text-blue-600';
    if (line.includes('DEBUG')) return 'text-gray-500';
    return 'text-gray-800';
  };

  return (
    <div className="h-full flex flex-col bg-gray-50" ref={containerRef}>
      {/* Header */}
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ScrollText className="w-5 h-5 text-tent-600" />
          <h2 className="text-sm font-semibold text-gray-900">实时日志</h2>
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
              isConnected
                ? 'bg-green-50 text-green-700 border border-green-200'
                : 'bg-red-50 text-red-700 border border-red-200'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            {isConnected ? '实时推送中' : '已断开'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="过滤日志..."
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-gray-50 focus:border-tent-400 focus:outline-none focus:ring-1 focus:ring-tent-100 w-48"
          />
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              isPaused
                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200 border border-transparent'
            }`}
          >
            {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            {isPaused ? '继续' : '暂停'}
          </button>
          <button
            onClick={clearLogs}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            清空
          </button>
          <button
            onClick={downloadLogs}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
          >
            <Download className="w-3 h-3" />
            下载
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="px-5 py-2 bg-gray-50 border-b border-gray-200 flex items-center gap-6 text-xs text-gray-500">
        <span>总行数: <strong className="text-gray-700">{logs.length}</strong></span>
        <span>显示: <strong className="text-gray-700">{filteredLogs.length}</strong></span>
        {isPaused && <span className="text-amber-600 font-medium">⏸ 已暂停接收新日志</span>}
      </div>

      {/* Log lines */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-2 font-mono text-xs leading-relaxed"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <ScrollText className="w-8 h-8 mb-2" />
            <p>等待日志...</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {filteredLogs.map((log) => (
              <div
                key={log.id}
                className={`${getLineColor(log.line)} hover:bg-gray-100 px-2 py-0.5 rounded transition-colors whitespace-pre-wrap break-all`}
              >
                {log.line}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
