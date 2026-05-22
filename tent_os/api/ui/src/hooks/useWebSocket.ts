import { useCallback, useEffect, useRef, useState } from 'react';
import type { WSMessage, WSMessageType } from '@/types';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnectInterval = 3000,
  maxReconnectAttempts = 10,
}: UseWebSocketOptions) {
  const [readyState, setReadyState] = useState<number>(WebSocket.CONNECTING);
  const [reconnectCount, setReconnectCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const shouldReconnect = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectCountRef = useRef(0);
  const callbacksRef = useRef({ onMessage, onOpen, onClose, onError });
  const sendQueueRef = useRef<Array<{ type: WSMessageType; payload: unknown }>>([]);

  // 保持回调最新，但不触发重渲染
  callbacksRef.current = { onMessage, onOpen, onClose, onError };

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      setReadyState(WebSocket.CONNECTING);

      ws.onopen = () => {
        setReadyState(WebSocket.OPEN);
        setReconnectCount(0);
        reconnectCountRef.current = 0;
        callbacksRef.current.onOpen?.();
        // 连接成功后，发送队列中积压的消息
        flushSendQueue();
      };

      ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          callbacksRef.current.onMessage?.(msg);
        } catch (e) {
          console.warn('Failed to parse WS message:', event.data);
        }
      };

      ws.onclose = (event) => {
        setReadyState(WebSocket.CLOSED);
        wsRef.current = null;
        callbacksRef.current.onClose?.(event);

        if (shouldReconnect.current && reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          setReconnectCount(reconnectCountRef.current);
          reconnectTimerRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        setReadyState(WebSocket.CLOSED);
        callbacksRef.current.onError?.(error);
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
      setReadyState(WebSocket.CLOSED);
    }
  }, [url, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback((type: WSMessageType, payload: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type,
          payload,
          timestamp: Date.now(),
        })
      );
    } else {
      // 连接未就绪时入队，连接成功后批量发送
      sendQueueRef.current.push({ type, payload });
    }
  }, []);

  const flushSendQueue = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    while (sendQueueRef.current.length > 0) {
      const msg = sendQueueRef.current.shift();
      if (msg) {
        wsRef.current.send(
          JSON.stringify({
            type: msg.type,
            payload: msg.payload,
            timestamp: Date.now(),
          })
        );
      }
    }
  }, []);

  useEffect(() => {
    shouldReconnect.current = true;
    connect();

    // heartbeat
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        send('ping', {});
      }
    }, 30000);

    return () => {
      clearInterval(heartbeat);
      disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]); // 只在 url 变化时重新连接

  return { readyState, reconnectCount, send, connect, disconnect };
}
