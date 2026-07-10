import { useCallback, useEffect, useRef, useState } from 'react'
import { Toaster } from 'react-hot-toast'
import { ArrowDown, FileText, FolderOpen, LogOut, Menu, Server, Settings, Sparkles, Wifi, WifiOff } from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { ChatMessageBubble } from './components/ChatMessage'
import { ChatInput } from './components/ChatInput'
import { SettingsPanel } from './components/SettingsPanel'
import { ProviderManager } from './components/ProviderManager'
import { ModelSelector } from './components/ModelSelector'
import { AuthPanel } from './components/AuthPanel'
import { OnboardingModal } from './components/OnboardingModal'
import { SkillsPanel } from './components/SkillsPanel'
import { WorkspacePanel } from './components/WorkspacePanel'
import { DocumentsPanel } from './components/DocumentsPanel'
import { useChatStore } from './hooks/useChatStore'
import { api, getAuthToken, setAuthToken, type ChatMessage, type StreamChunk, type UserInfo } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'

export default function App() {
  const {
    messages, isLoading, error, route, streamStatus,
    sendMessage, regenerate, stopGeneration, loadConfig, loadProfiles,
    toggleSidebar, setError, sessionId,
    useThinking, useRag,
    setWsConnected, lastMetrics,
  } = useChatStore()

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)
  const [skillsOpen, setSkillsOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [documentsOpen, setDocumentsOpen] = useState(false)
  const [user, setUser] = useState<UserInfo | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)

  const handleStreamChunk = useCallback((chunk: StreamChunk) => {
    if (chunk.type === 'start') {
      useChatStore.setState({
        ...(chunk.route ? { route: chunk.route } : {}),
        streamStatus: 'Conectando ao modelo...',
      })
      return
    }

    if (chunk.type === 'reasoning' || chunk.type === 'content') {
      useChatStore.setState(state => {
        const nextMessages = [...state.messages]
        const last = nextMessages[nextMessages.length - 1]
        if (last?.role === 'assistant') {
          nextMessages[nextMessages.length - 1] = chunk.type === 'reasoning'
            ? { ...last, reasoning: `${last.reasoning || ''}${chunk.text || ''}` }
            : { ...last, content: `${last.content || ''}${chunk.text || ''}` }
        }
        return { messages: nextMessages, streamStatus: null }
      })
      return
    }

    if (chunk.type === 'workspace_plan' && chunk.workspacePlan) {
      useChatStore.setState(state => {
        const nextMessages = [...state.messages]
        const last = nextMessages[nextMessages.length - 1]
        if (last?.role === 'assistant') {
          nextMessages[nextMessages.length - 1] = { ...last, workspacePlan: chunk.workspacePlan }
        }
        return { messages: nextMessages }
      })
      return
    }

    if (chunk.type === 'skill_activity' && chunk.skillActivity) {
      useChatStore.setState(state => {
        const nextMessages = [...state.messages]
        const last = nextMessages[nextMessages.length - 1]
        if (last?.role === 'assistant') {
          nextMessages[nextMessages.length - 1] = {
            ...last,
            skillActivities: [...(last.skillActivities || []), chunk.skillActivity!],
          }
        }
        return { messages: nextMessages }
      })
      return
    }

    if (chunk.type === 'done') {
      useChatStore.setState(state => {
        const nextMessages = [...state.messages]
        const last = nextMessages[nextMessages.length - 1]
        if (last?.role === 'assistant') {
          nextMessages[nextMessages.length - 1] = {
            ...last,
            messageId: chunk.messageId,
            providerId: chunk.providerId,
            providerName: chunk.providerName,
            modelId: chunk.modelId,
            modelName: chunk.modelName,
          }
        }
        return {
          messages: nextMessages,
          isLoading: false,
          streamStatus: null,
          route: chunk.hasReasoning === undefined ? state.route : chunk.hasReasoning ? 'full' : 'fast',
          lastMetrics: chunk.metrics || state.lastMetrics,
        }
      })
      useChatStore.getState().loadConversations()
    }
  }, [])

  const {
    connected: wsConnected,
    sendMessage: wsSend,
    reconnect: reconnectWs,
    disconnect: disconnectWs,
  } = useWebSocket({
    enabled: !!user,
    onChunk: handleStreamChunk,
    onStatus: status => useChatStore.setState({ streamStatus: status }),
    onError: errorMessage => {
      useChatStore.setState({ error: errorMessage, isLoading: false, streamStatus: null })
    },
  })

  useEffect(() => {
    setWsConnected(wsConnected)
  }, [setWsConnected, wsConnected])

  useEffect(() => {
    let cancelled = false

    async function loadUser() {
      const token = getAuthToken()
      if (!token) {
        setAuthChecked(true)
        return
      }

      try {
        const me = await api.me()
        if (cancelled) return
        setUser(me)
        setShowOnboarding(localStorage.getItem(`chatbot_onboarding_done_${me.id}`) !== '1')
      } catch {
        setAuthToken('')
      } finally {
        if (!cancelled) setAuthChecked(true)
      }
    }

    loadUser()
    return () => {
      cancelled = true
    }
  }, [])

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

  useEffect(() => {
    if (!autoScrollRef.current) return
    scrollToBottom('auto')
  }, [messages, scrollToBottom])

  useEffect(() => {
    const handler = () => setProviderManagerOpen(true)
    window.addEventListener('open-provider-manager', handler)
    return () => window.removeEventListener('open-provider-manager', handler)
  }, [])

  useEffect(() => {
    if (!user) return
    loadConfig()
    loadProfiles()
    useChatStore.getState().setSession(useChatStore.getState().sessionId)
  }, [loadConfig, loadProfiles, user])

  const handleAuthenticated = useCallback((nextUser: UserInfo) => {
    setUser(nextUser)
    setShowOnboarding(localStorage.getItem(`chatbot_onboarding_done_${nextUser.id}`) !== '1')
    setTimeout(() => reconnectWs(), 50)
  }, [reconnectWs])

  const handleLogout = useCallback(() => {
    disconnectWs()
    api.logout()
    setUser(null)
    setShowOnboarding(false)
    useChatStore.setState({
      messages: [],
      conversations: [],
      documents: [],
      stats: null,
      sessionId: 'default',
      isLoading: false,
      error: null,
      streamStatus: null,
    })
  }, [disconnectWs])

  const handleOnboardingDone = useCallback(() => {
    if (user) localStorage.setItem(`chatbot_onboarding_done_${user.id}`, '1')
    setShowOnboarding(false)
  }, [user])

  const handleSend = useCallback((content: string) => {
    if (wsConnected) {
      useChatStore.setState({ isLoading: true, error: null, streamStatus: 'Preparando resposta...' })
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date(),
      }
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        reasoning: '',
      }
      useChatStore.setState(state => ({ messages: [...state.messages, userMsg, assistantMsg] }))
      wsSend(content, sessionId, useRag, useThinking)
      return
    }

    sendMessage(content)
  }, [sendMessage, sessionId, useRag, useThinking, wsConnected, wsSend])

  const isLastAssistant = messages.length > 0 && messages[messages.length - 1]?.role === 'assistant'

  if (!authChecked) {
    return (
      <div className="min-h-screen grid place-items-center" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 rounded-full border-4 border-current border-t-transparent animate-spin opacity-70" />
          <p className="text-sm font-medium">Carregando sessao...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <>
        <Toaster position="top-center" />
        <AuthPanel onAuthenticated={handleAuthenticated} />
      </>
    )
  }

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
      <SkillsPanel open={skillsOpen} onClose={() => setSkillsOpen(false)} />
      <WorkspacePanel open={workspaceOpen} onClose={() => setWorkspaceOpen(false)} />
      <DocumentsPanel open={documentsOpen} onClose={() => setDocumentsOpen(false)} />
      {showOnboarding && <OnboardingModal user={user} onDone={handleOnboardingDone} />}

      <div className="flex-1 flex flex-col min-w-0">
        <header
          className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Menu"
            >
              <Menu size={20} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <h1 className="text-lg font-bold truncate" style={{ color: 'var(--text-primary)' }}>Chatbot</h1>
            {route && (
              <span
                className="hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  background: route === 'fast' ? '#dcfce7' : '#dbeafe',
                  color: route === 'fast' ? '#16a34a' : 'var(--accent)',
                }}
              >
                {route === 'fast' ? 'Rapida' : 'Completa'}
              </span>
            )}
            {lastMetrics?.total_s && (
              <span
                className="hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
              >
                {lastMetrics.total_s.toFixed(1)}s
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden md:inline text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
              {user.display_name || user.username}
            </span>
            <span title={wsConnected ? 'WebSocket conectado' : 'Modo HTTP'}>
              {wsConnected ? (
                <Wifi size={14} style={{ color: '#16a34a' }} />
              ) : (
                <WifiOff size={14} style={{ color: 'var(--text-tertiary)' }} />
              )}
            </span>
            <ModelSelector />
            <button
              onClick={() => setWorkspaceOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Workspace"
            >
              <FolderOpen size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setDocumentsOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Documentos RAG"
            >
              <FileText size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setSkillsOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Skills"
            >
              <Sparkles size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setProviderManagerOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Gerenciar providers"
            >
              <Server size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Configuracoes"
            >
              <Settings size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Sair"
            >
              <LogOut size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
          </div>
        </header>

        {error && (
          <div
            className="flex items-center justify-between px-4 py-2 text-sm"
            style={{ background: '#fef2f2', color: '#dc2626', borderBottom: '1px solid #fecaca' }}
          >
            <span>{error}</span>
            <button onClick={() => setError(null)} className="font-bold hover:opacity-70">x</button>
          </div>
        )}

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
                    <div className="mx-auto mb-6 grid h-20 w-20 place-items-center rounded-3xl" style={{ background: 'var(--accent-light)' }}>
                      <Sparkles size={38} style={{ color: 'var(--accent)' }} />
                    </div>
                    <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                      Ola, {user.display_name || user.username}.
                    </h2>
                    <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
                      Seu chat agora tem login, memoria/RAG por usuario, onboarding inicial e skills configuraveis.
                    </p>
                    <div className="grid grid-cols-2 gap-3 text-left">
                      {[
                        { title: 'Multiusuario', desc: 'Dados isolados por conta' },
                        { title: 'RAG pessoal', desc: 'Documentos por usuario' },
                        { title: 'Onboarding', desc: 'Perfil salvo como memoria' },
                        { title: 'Skills', desc: 'Habilidades ativaveis' },
                      ].map(item => (
                        <div
                          key={item.title}
                          className="p-3 rounded-xl"
                          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
                        >
                          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{item.title}</p>
                          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{item.desc}</p>
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
                      isLoading={isLoading && msg.role === 'assistant' && msg.id === messages[messages.length - 1]?.id}
                      status={isLoading && msg.id === messages[messages.length - 1]?.id ? streamStatus : null}
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
              title="Descer ate o final"
            >
              <ArrowDown size={14} />
              Final
            </button>
          )}
        </div>

        <ChatInput onSend={handleSend} busy={isLoading} onStop={stopGeneration} />
      </div>
    </div>
  )
}
