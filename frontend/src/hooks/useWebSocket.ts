import { useEffect, useRef, useCallback, useState } from 'react'
import { getAuthToken, type StreamChunk } from '../lib/api'

type ChunkHandler = (chunk: StreamChunk) => void
type StatusHandler = (status: string) => void

interface UseWebSocketOptions {
  onChunk?: ChunkHandler
  onStatus?: StatusHandler
  onError?: (error: string) => void
}

// Usa caminho relativo (proxy do Vite em dev, ou mesmo domínio em prod)
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

export function useWebSocket(options: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const handlersRef = useRef(options)
  handlersRef.current = options

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const token = getAuthToken()
    const url = token ? `${WS_BASE}?token=${encodeURIComponent(token)}` : WS_BASE
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      setReconnecting(false)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const { onChunk, onStatus, onError } = handlersRef.current

        switch (data.type) {
          case 'start':
            onChunk?.({
              type: 'start',
              route: data.route,
              sessionId: data.session_id,
              providerId: data.provider_id,
              providerName: data.provider_name,
              modelId: data.model_id,
              modelName: data.model_name,
            } as any)
            break

          case 'status':
            onStatus?.(data.text)
            break

          case 'reasoning':
            onChunk?.({ type: 'reasoning', text: data.text })
            break

          case 'token':
            onChunk?.({ type: 'content', text: data.text })
            break

          case 'done':
            onChunk?.({
              type: 'done',
              messageId: data.message_id,
              hasReasoning: data.has_reasoning,
              providerId: data.provider_id,
              providerName: data.provider_name,
              modelId: data.model_id,
              modelName: data.model_name,
              metrics: data.metrics,
            })
            break

          case 'error':
            onError?.(data.text)
            onChunk?.({ type: 'done' })
            break

          case 'pong':
            break
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setConnected(false)
      // Reconecta automaticamente após 3s
      reconnectTimerRef.current = setTimeout(() => {
        setReconnecting(true)
        connect()
      }, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
    }
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
    setReconnecting(false)
  }, [])

  const send = useCallback(
    (data: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(data))
        return true
      }
      return false
    },
    [],
  )

  const sendMessage = useCallback(
    (message: string, sessionId: string, useRag = false, useThinking = true) => {
      return send({
        type: 'chat',
        message,
        session_id: sessionId,
        use_rag: useRag,
        use_thinking: useThinking,
      })
    },
    [send],
  )

  const ping = useCallback(() => {
    send({ type: 'ping' })
  }, [send])

  // Ping a cada 30s para manter conexão viva
  useEffect(() => {
    if (!connected) return
    const interval = setInterval(ping, 30000)
    return () => clearInterval(interval)
  }, [connected, ping])

  // Conecta automaticamente
  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    connected,
    reconnecting,
    sendMessage,
    send,
    disconnect,
    reconnect: connect,
  }
}
