import { useEffect, useRef, useState, useCallback } from 'react';

export interface WsMessage {
  type: string;
  payload: Record<string, any>;
  timestamp?: number;
}

interface QueuedMessage {
  type: string;
  payload: Record<string, any>;
}

const HEARTBEAT_INTERVAL = 30000; // 30s ping
const HEARTBEAT_TIMEOUT = 10000;  // 10s 内必须收到 pong
const MAX_RECONNECT_DELAY = 30000; // 最大重连延迟 30s
const MAX_RECONNECT_ATTEMPTS = 20; // 最大重试次数

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

export function useWebSocket(url: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);
  const sendQueueRef = useRef<QueuedMessage[]>([]);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isClosingRef = useRef(false);
  const urlFallbackIndexRef = useRef(0);

  // Support localhost fallback to 127.0.0.1 to bypass IPv6 resolution issues
  const getUrls = useCallback((primaryUrl: string) => {
    const urls = [primaryUrl];
    if (primaryUrl.includes('localhost')) {
      urls.push(primaryUrl.replace('localhost', '127.0.0.1'));
    }
    return urls;
  }, []);

  const flushQueue = useCallback(() => {
    while (sendQueueRef.current.length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
      const msg = sendQueueRef.current.shift();
      if (msg) {
        wsRef.current.send(JSON.stringify(msg));
      }
    }
  }, []);

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearTimeout(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
      heartbeatTimeoutRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    clearTimers();
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping', payload: {} }));
        heartbeatTimeoutRef.current = setTimeout(() => {
          console.warn('[WS] heartbeat timeout, reconnecting...');
          wsRef.current?.close();
        }, HEARTBEAT_TIMEOUT);
      }
    }, HEARTBEAT_INTERVAL);
  }, [clearTimers]);

  useEffect(() => {
    isClosingRef.current = false;
    urlFallbackIndexRef.current = 0;

    const urls = getUrls(url);

    const connect = () => {
      if (isClosingRef.current) return;
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        console.error(`[WS] max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached`);
        setConnectionStatus('disconnected');
        return;
      }

      setConnectionStatus('connecting');

      const currentUrl = urls[Math.min(urlFallbackIndexRef.current, urls.length - 1)];

      try {
        console.log(`[WS] connecting to ${currentUrl} (attempt #${reconnectAttemptsRef.current + 1})`);
        const ws = new WebSocket(currentUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          reconnectAttemptsRef.current = 0;
          urlFallbackIndexRef.current = 0;
          setConnected(true);
          setConnectionStatus('connected');
          setReconnectCount((c) => c + 1);
          console.log('[WS] connected');
          startHeartbeat();
          flushQueue();
        };

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data) as WsMessage;
            if (msg.type === 'pong') {
              if (heartbeatTimeoutRef.current) {
                clearTimeout(heartbeatTimeoutRef.current);
                heartbeatTimeoutRef.current = null;
              }
              return;
            }
            setLastMessage(msg);
          } catch {}
        };

        ws.onclose = (event) => {
          setConnected(false);
          setConnectionStatus('disconnected');
          clearTimers();
          if (isClosingRef.current) return;

          reconnectAttemptsRef.current++;

          const delay = Math.min(
            1000 * Math.pow(2, reconnectAttemptsRef.current - 1),
            MAX_RECONNECT_DELAY
          );
          const code = event.code;
          const reason = event.reason || 'unknown';

          if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            console.error(`[WS] max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached, code=${code}, reason=${reason}`);
            setConnectionStatus('disconnected');
            return;
          }

          // If current URL failed, try fallback on next attempt
          if (urlFallbackIndexRef.current < urls.length - 1) {
            urlFallbackIndexRef.current++;
            console.log(`[WS] URL ${currentUrl} failed, trying fallback ${urls[urlFallbackIndexRef.current]}`);
          }

          console.log(`[WS] disconnected (code=${code}, reason=${reason}), retry #${reconnectAttemptsRef.current} in ${delay}ms`);
          reconnectTimerRef.current = setTimeout(connect, delay);
        };

        ws.onerror = (err) => {
          console.error(`[WS] error on ${currentUrl}:`, err);
          setConnectionStatus('disconnected');
          // Ensure we trigger onclose by closing the socket ourselves if it's still connecting
          if (ws.readyState === WebSocket.CONNECTING) {
            ws.close();
          }
        };
      } catch (err) {
        console.error('[WS] connect error', err);
        setConnectionStatus('disconnected');
        reconnectAttemptsRef.current++;
        const delay = Math.min(
          1000 * Math.pow(2, reconnectAttemptsRef.current - 1),
          MAX_RECONNECT_DELAY
        );
        reconnectTimerRef.current = setTimeout(connect, delay);
      }
    };

    connect();

    return () => {
      isClosingRef.current = true;
      clearTimers();
      wsRef.current?.close(1000, 'component unmount');
      wsRef.current = null;
    };
  }, [url, startHeartbeat, flushQueue, clearTimers, getUrls]);

  const send = useCallback((type: string, payload: Record<string, any>) => {
    const msg = { type, payload };
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else {
      sendQueueRef.current.push(msg);
      console.warn('[WS] not connected, message queued');
    }
  }, []);

  return { connected, connectionStatus, lastMessage, send, reconnectCount };
}
