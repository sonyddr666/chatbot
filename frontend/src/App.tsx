import { useEffect, useState, useCallback, useRef } from 'react'
import { Toaster } from 'react-hot-toast'
import { Menu, Settings, Wifi, WifiOff, Server, ArrowDown } from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { ChatMessageBubble } from './components/ChatMessage'
import { ChatInput } from './components/ChatInput'
import { SettingsPanel } from './components/SettingsPanel'
import { ProviderManager } from './components/ProviderManager'
import { ModelSelector } from './components/ModelSelector'
import { useChatStore } from './hooks/useChatStore'
import type { ChatMessage } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'

export default function App() {
  const {
    messages, isLoading, error, route,
    sendMessage, regenerate, stopGeneration, loadConfig, loadProfiles,
    toggleSidebar, setError, sessionId,
    useThinking, useRag,
    setWsConnected, lastMetrics,
  } = useChatStore()

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 140
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior })
    autoScrollRef.current = true
    setShowScrollBottom(false)
  }, [])

  const handleMessagesScroll = useCallback(() => {
    const near = isNearBottom()
    autoScrollRef.current = near
    setShowScrollBottom(!near)
  }, [isNearBottom])

  // Só auto-desce quando entra uma nova bolha de mensagem.
  // Não acompanha cada chunk/token da resposta, pra não "grudar" no scroll.
  useEffect(() => {
    if (!autoScrollRef.current) return
    requestAnimationFrame(() => scrollToBottom('auto'))
  }, [messages.length, scrollToBottom])

  // Quando a resposta cresce e empurra o fim pra baixo, apenas mostra o botão.
  // Não move o scroll sozinho.
  useEffect(() => {
    requestAnimationFrame(() => setShowScrollBottom(!isNearBottom()))
  }, [messages, isNearBottom])

  // Evento para abrir gerenciador pelo ModelSelector
  useEffect(() => {
    const handler = () => setProviderManagerOpen(true)
    window.addEventListener('open-provider-manager', handler)
    return () => window.removeEventListener('open-provider-manager', handler)
  }, [])

  // ── WebSocket ──
  const handleChunk = useCallback((chunk: any) => {
    const set = useChatStore.setState
    const get = useChatStore.getState
    const s = get()

    if (chunk.type === 'reasoning') {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, reasoning: (last.reasoning || '') + (chunk.text || '') }
        set({ messages: msgs })
      }
    } else if (chunk.type === 'content') {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + (chunk.text || '') }
        set({ messages: msgs })
      }
    } else if (chunk.type === 'done') {
      const msgs = [...get().messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = {
          ...last,
          messageId: chunk.messageId,
          providerId: chunk.providerId,
          providerName: chunk.providerName,
          modelId: chunk.modelId,
          modelName: chunk.modelName,
        }
      }
      set({ messages: msgs, isLoading: false, route: chunk.hasReasoning ? 'full' : 'fast', lastMetrics: chunk.metrics || null })
      get().loadConversations()
    } else if (chunk.type === 'start') {
      set({ route: chunk.route || null })
    }
  }, [])

  const handleStatus = useCallback((_status: string) => {
    // Poderia mostrar status na UI
  }, [])

  const handleWsError = useCallback((err: string) => {
    setError(err)
    useChatStore.setState({ isLoading: false })
  }, [setError])

  const { connected: wsConnected, sendMessage: wsSend } = useWebSocket({
    onChunk: handleChunk,
    onStatus: handleStatus,
    onError: handleWsError,
  })

  // Sincroniza estado de conexão
  useEffect(() => {
    setWsConnected(wsConnected)
  }, [wsConnected, setWsConnected])

  // ── Load inicial ──
  useEffect(() => {
    loadConfig()
    loadProfiles()
    // Carrega o histórico da sessão atual apenas uma vez ao abrir.
    useChatStore.getState().setSession(useChatStore.getState().sessionId)
  }, [loadConfig, loadProfiles])

  // ── Send via WebSocket ou HTTP ──
  const handleSend = useCallback((content: string) => {
    if (wsConnected) {
      useChatStore.setState({ isLoading: true, error: null })
      const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content, timestamp: new Date() }
      const asstMsg: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', timestamp: new Date(), reasoning: '' }
      useChatStore.setState(s => ({ messages: [...s.messages, userMsg, asstMsg] }))
      wsSend(content, sessionId, useRag, useThinking)
    } else {
      sendMessage(content)
    }
  }, [wsConnected, wsSend, sessionId, useRag, useThinking, sendMessage])

  const isLastAssistant = messages.length > 0 && messages[messages.length - 1]?.role === 'assistant'

  return (
    <div className="h-screen flex overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            fontSize: '14px',
          },
        }}
      />

      <Sidebar />
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <ProviderManager open={providerManagerOpen} onClose={() => setProviderManagerOpen(false)} />

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header
          className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center gap-3">
            <button onClick={toggleSidebar} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors">
              <Menu size={20} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>🤖 Chatbot</h1>
            {route && (
              <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{
                background: route === 'fast' ? '#dcfce7' : '#dbeafe',
                color: route === 'fast' ? '#16a34a' : 'var(--accent)',
              }}>
                {route === 'fast' ? '⚡ Rápida' : '🔬 Completa'}
              </span>
            )}
            {lastMetrics?.total_s && (
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>
                {lastMetrics.total_s.toFixed(1)}s
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Conexão */}
            <span title={wsConnected ? 'WebSocket' : 'HTTP'}>
              {wsConnected ? (
                <Wifi size={14} style={{ color: '#16a34a' }} />
              ) : (
                <WifiOff size={14} style={{ color: 'var(--text-tertiary)' }} />
              )}
            </span>

            <ModelSelector />
            <button
              onClick={() => setProviderManagerOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Gerenciar Providers"
            >
              <Server size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button onClick={() => setSettingsOpen(true)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors">
              <Settings size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
          </div>
        </header>

        {/* Error banner */}
        {error && (
          <div className="flex items-center justify-between px-4 py-2 text-sm"
            style={{ background: '#fef2f2', color: '#dc2626', borderBottom: '1px solid #fecaca' }}>
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)} className="font-bold hover:opacity-70">×</button>
          </div>
        )}

        {/* Messages */}
        <div className="relative flex-1 min-h-0">
          <div
            ref={scrollRef}
            onScroll={handleMessagesScroll}
            className="h-full overflow-y-auto px-4 py-6"
          >
            <div className="max-w-4xl mx-auto">
              {messages.length === 0 ? (
                <div className="flex items-center justify-center h-full min-h-[60vh]">
                  <div className="text-center max-w-md animate-fade-in">
                    <div className="text-7xl mb-6">🤖</div>
                    <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                      Olá! Como posso ajudar?
                    </h2>
                    <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
                      Sou um assistente AI com suporte a RAG, multilíngue e muito mais.
                    </p>
                    <div className="grid grid-cols-2 gap-3 text-left">
                      {[
                        { icon: '💬', title: 'Conversas', desc: 'Histórico completo com busca' },
                        { icon: '📄', title: 'Documentos', desc: 'Upload e RAG automático' },
                        { icon: '🌍', title: 'Multilíngue', desc: 'Detecta seu idioma' },
                        { icon: '🎨', title: 'Temas', desc: 'Claro e escuro' },
                      ].map(s => (
                        <div key={s.title} className="p-3 rounded-xl"
                          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                          <p className="text-lg mb-1">{s.icon}</p>
                          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{s.title}</p>
                          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{s.desc}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {messages.map(msg => (
                    <ChatMessageBubble
                      key={msg.id}
                      message={msg}
                      isLoading={isLoading && msg.role === 'assistant' && (msg.content === '' || !!msg.reasoning)}
                      onRegenerate={
                        msg.role === 'assistant' && isLastAssistant && msg.id === messages[messages.length - 1]?.id
                          ? regenerate
                          : undefined
                      }
                    />
                  ))}
                  <div className="h-2" />
                </>
              )}
            </div>
          </div>

          {showScrollBottom && (
            <button
              type="button"
              onClick={() => scrollToBottom('smooth')}
              className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 px-3 py-2 rounded-full text-xs font-medium shadow-lg border transition-all hover:scale-105"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                borderColor: 'var(--border)',
              }}
              title="Descer até o final"
            >
              <ArrowDown size={14} />
              Final
            </button>
          )}
        </div>

        {/* Input */}
        <ChatInput onSend={handleSend} disabled={isLoading} onStop={stopGeneration} />
      </div>
    </div>
  )
}
