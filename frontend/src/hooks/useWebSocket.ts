import { useEffect, useRef, useCallback, useState } from 'react'
import { getAuthToken, type ReasoningEffort, type ResponseMode, type StreamChunk } from '../lib/api'

type ChunkHandler = (chunk: StreamChunk) => void
type StatusHandler = (status: string) => void

interface UseWebSocketOptions {
  enabled?: boolean
  onChunk?: ChunkHandler
  onStatus?: StatusHandler
  onError?: (error: string) => void
}

// Usa caminho relativo (proxy do Vite em dev, ou mesmo domínio em prod)
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

function websocketAuthProtocol(token: string) {
  const bytes = new TextEncoder().encode(token)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return `auth.${btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
}

export function useWebSocket(options: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const handlersRef = useRef(options)
  handlersRef.current = options

  const connect = useCallback(() => {
    if (handlersRef.current.enabled === false) return
    if (
      wsRef.current?.readyState === WebSocket.CONNECTING
      || wsRef.current?.readyState === WebSocket.OPEN
    ) return
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    reconnectTimerRef.current = null

    const token = getAuthToken()
    if (!token) return
    const ws = new WebSocket(WS_BASE, ['chatbot', websocketAuthProtocol(token)])
    wsRef.current = ws

    ws.onopen = () => {
      if (wsRef.current !== ws) {
        ws.close()
        return
      }
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
              responseMode: data.response_mode,
              reasoningEffort: data.reasoning_effort,
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

          case 'workspace_plan':
            onChunk?.({ type: 'workspace_plan', workspacePlan: data.plan })
            break

          case 'skill_activity':
            onChunk?.({ type: 'skill_activity', skillActivity: data.activity })
            break

          case 'done':
            onChunk?.({
              type: 'done',
              messageId: data.message_id,
              hasReasoning: data.has_reasoning,
              responseMode: data.response_mode,
              reasoningEffort: data.reasoning_effort,
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
      if (wsRef.current !== ws) return
      wsRef.current = null
      setConnected(false)
      if (handlersRef.current.enabled === false) return
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
    const current = wsRef.current
    wsRef.current = null
    if (current) {
      current.onclose = null
      current.onerror = null
      current.onmessage = null
      current.close()
    }
    setConnected(false)
    setReconnecting(false)
  }, [])

  const restart = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    const current = wsRef.current
    wsRef.current = null
    if (current) {
      current.onclose = null
      current.onerror = null
      current.onmessage = null
      current.close()
    }
    setConnected(false)
    setReconnecting(true)
    reconnectTimerRef.current = setTimeout(connect, 120)
  }, [connect])

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
    (
      message: string,
      sessionId: string,
      useRag = false,
      responseMode: ResponseMode = 'normal',
      reasoningEffort: ReasoningEffort = 'low',
    ) => {
      return send({
        type: 'chat',
        message,
        session_id: sessionId,
        use_rag: useRag,
        response_mode: responseMode,
        reasoning_effort: reasoningEffort,
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
    if (options.enabled === false) {
      disconnect()
    } else {
      connect()
    }
    return () => disconnect()
  }, [connect, disconnect, options.enabled])

  return {
    connected,
    reconnecting,
    sendMessage,
    send,
    disconnect,
    reconnect: connect,
    restart,
  }
}
