import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { ArrowDown, Brain, Check, ChevronDown, FileText, FolderOpen, LogOut, Menu, MoreHorizontal, Server, Settings, Sparkles, UserRound, Users, Wifi, WifiOff } from 'lucide-react'
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
import { LiveVoiceButton, LiveVoiceDock } from './components/LiveVoiceControl'
import { AdminUsersPanel } from './components/AdminUsersPanel'
import { detachActiveChatStreams, useChatStore } from './hooks/useChatStore'
import { api, getAuthToken, setAuthToken, upsertSkillActivity, type ReasoningEffort, type ResponseMode, type StreamChunk, type UserInfo } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'
import { useLiveVoice } from './voice/useLiveVoice'

interface HeaderSelectOption<T extends string> {
  value: T
  label: string
}

interface HeaderSelectProps<T extends string> {
  value: T
  options: HeaderSelectOption<T>[]
  onChange: (value: T) => void
  icon: ReactNode
  label: string
  className: string
  disabled?: boolean
  title?: string
}

function HeaderSelect<T extends string>({
  value,
  options,
  onChange,
  icon,
  label,
  className,
  disabled = false,
  title,
}: HeaderSelectProps<T>) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const selected = options.find(option => option.value === value) || options[0]

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [open])

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(current => !current)}
        onKeyDown={event => {
          if (event.key === 'Escape') setOpen(false)
        }}
        className="flex h-9 items-center gap-2 rounded-full border px-3 text-xs font-semibold shadow-sm transition-all hover:-translate-y-px hover:shadow-md focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-60"
        style={{
          background: open ? 'var(--bg-primary)' : 'var(--bg-tertiary)',
          borderColor: open ? 'var(--accent)' : 'var(--border)',
          color: 'var(--text-secondary)',
        }}
        title={title || label}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="flex-shrink-0" style={{ color: open ? 'var(--accent)' : 'var(--text-tertiary)' }}>
          {icon}
        </span>
        <span className="whitespace-nowrap">{selected.label}</span>
        <ChevronDown
          size={13}
          className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute right-0 top-[calc(100%+8px)] z-[80] min-w-44 overflow-hidden rounded-2xl border p-1.5 shadow-2xl"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
        >
          {options.map(option => {
            const isSelected = option.value === value
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange(option.value)
                  setOpen(false)
                }}
                className="flex w-full items-center justify-between gap-4 rounded-xl px-3 py-2 text-left text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/10"
                style={{
                  background: isSelected ? 'var(--accent-light)' : 'transparent',
                  color: isSelected ? 'var(--accent)' : 'var(--text-secondary)',
                }}
              >
                <span>{option.label}</span>
                {isSelected && <Check size={14} aria-hidden="true" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MobileToolButton({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
  danger?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition-colors hover:bg-black/5 dark:hover:bg-white/10"
      style={{ color: danger ? 'var(--danger)' : 'var(--text-primary)' }}
    >
      <span className="shrink-0" style={{ color: danger ? 'var(--danger)' : 'var(--text-tertiary)' }}>{icon}</span>
      {label}
    </button>
  )
}

const RESPONSE_MODE_OPTIONS: HeaderSelectOption<ResponseMode>[] = [
  { value: 'normal', label: 'Normal' },
  { value: 'thinking', label: 'Pensando' },
  { value: 'live', label: 'Live' },
]

const ALL_REASONING_EFFORT_OPTIONS: HeaderSelectOption<ReasoningEffort>[] = [
  { value: 'auto', label: 'Automatico' },
  { value: 'none', label: 'Sem raciocinio' },
  { value: 'default', label: 'Padrao' },
  { value: 'low', label: 'Leve' },
  { value: 'medium', label: 'Medio' },
  { value: 'high', label: 'Alto' },
  { value: 'xhigh', label: 'Extra alto' },
  { value: 'max', label: 'Maximo' },
]

export default function App() {
  const {
    messages, isLoading, error, route, streamStatus,
    sendMessage, retryFailedJob, regenerate, stopGeneration, loadConfig, loadProfiles,
    toggleSidebar, setError,
    responseMode, setResponseMode, reasoningEffort, setReasoningEffort,
    setWsConnected, lastMetrics, config,
  } = useChatStore()

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)
  const [skillsOpen, setSkillsOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [documentsOpen, setDocumentsOpen] = useState(false)
  const [adminUsersOpen, setAdminUsersOpen] = useState(false)
  const allowedReasoningEfforts = config?.reasoning_efforts?.length
    ? config.reasoning_efforts
    : ['auto' as ReasoningEffort]
  const reasoningEffortOptions = ALL_REASONING_EFFORT_OPTIONS.filter(option => (
    allowedReasoningEfforts.includes(option.value)
  ))
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false)
  const [user, setUser] = useState<UserInfo | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const liveEnabledRef = useRef(false)
  const initializedChatUserRef = useRef<number | null>(null)

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
            skillActivities: upsertSkillActivity(last.skillActivities || [], chunk.skillActivity!),
          }
        }
        return { messages: nextMessages }
      })
      return
    }

    if (chunk.type === 'attachment' && chunk.attachment) {
      useChatStore.setState(state => {
        const nextMessages = [...state.messages]
        const last = nextMessages[nextMessages.length - 1]
        if (last?.role === 'assistant') {
          nextMessages[nextMessages.length - 1] = {
            ...last,
            attachments: (last.attachments || []).some(item => item.id === chunk.attachment!.id)
              ? last.attachments
              : [...(last.attachments || []), chunk.attachment!],
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
      const store = useChatStore.getState()
      void Promise.all([store.loadConversations(), store.loadStats()])
    }
  }, [])

  const {
    connected: wsConnected,
    reconnect: reconnectWs,
    disconnect: disconnectWs,
    restart: restartWs,
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
    if (initializedChatUserRef.current === user.id) return
    initializedChatUserRef.current = user.id
    detachActiveChatStreams()
    useChatStore.setState({
      sessionId: `chat-${Date.now()}`,
      messages: [],
      isLoading: false,
      error: null,
      streamStatus: null,
      route: null,
      lastMetrics: null,
    })
  }, [loadConfig, loadProfiles, user])

  const handleAuthenticated = useCallback((nextUser: UserInfo) => {
    setUser(nextUser)
    setShowOnboarding(localStorage.getItem(`chatbot_onboarding_done_${nextUser.id}`) !== '1')
    setTimeout(() => reconnectWs(), 50)
  }, [reconnectWs])

  const handleLogout = useCallback(() => {
    disconnectWs()
    detachActiveChatStreams()
    initializedChatUserRef.current = null
    api.logout()
    setUser(null)
    setShowOnboarding(false)
    useChatStore.setState({
      messages: [],
      conversations: [],
      documents: [],
      stats: null,
      config: null,
      profiles: [],
      selectedProfile: 'zen-free',
      sessionId: 'default',
      isLoading: false,
      error: null,
      streamStatus: null,
      route: null,
      lastMetrics: null,
    })
  }, [disconnectWs])

  const handleOnboardingDone = useCallback(() => {
    if (user) localStorage.setItem(`chatbot_onboarding_done_${user.id}`, '1')
    setShowOnboarding(false)
  }, [user])

  const handleSend = useCallback((content: string, files: File[] = []) => {
    const effectiveMode: ResponseMode = liveEnabledRef.current ? 'live' : responseMode
    return sendMessage(content, effectiveMode, reasoningEffort, files)
  }, [reasoningEffort, responseMode, sendMessage])

  const handleStop = useCallback(() => {
    stopGeneration()
    if (wsConnected) restartWs()
  }, [restartWs, stopGeneration, wsConnected])

  const lastAssistantMessage = [...messages].reverse().find(message => message.role === 'assistant')
  const liveVoice = useLiveVoice({
    userId: user?.id,
    isGenerating: isLoading,
    assistantMessageId: lastAssistantMessage?.id,
    assistantText: lastAssistantMessage?.content || '',
    onSend: handleSend,
    onInterruptGeneration: handleStop,
  })
  liveEnabledRef.current = liveVoice.enabled

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
      <ProviderManager open={providerManagerOpen} onClose={() => setProviderManagerOpen(false)} isAdmin={!!user?.is_admin} />
      <SkillsPanel open={skillsOpen} onClose={() => setSkillsOpen(false)} />
      <WorkspacePanel open={workspaceOpen} onClose={() => setWorkspaceOpen(false)} />
      <DocumentsPanel open={documentsOpen} onClose={() => setDocumentsOpen(false)} />
      {user.is_admin && <AdminUsersPanel open={adminUsersOpen} onClose={() => setAdminUsersOpen(false)} />}
      {showOnboarding && <OnboardingModal user={user} onDone={handleOnboardingDone} />}

      <div className="flex-1 flex flex-col min-w-0">
        <header
          className="relative flex items-center justify-between gap-2 border-b px-2 py-2.5 sm:px-4 sm:py-3 flex-shrink-0"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
        >
          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              title="Menu"
            >
              <Menu size={20} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <h1 className="hidden text-lg font-bold truncate sm:block" style={{ color: 'var(--text-primary)' }}>Chatbot</h1>
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

          <div className="flex min-w-0 flex-1 items-center justify-end gap-1 sm:gap-2">
            <span className="hidden md:inline text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
              {user.display_name || user.username}
            </span>
            <span className="hidden sm:inline" title={wsConnected ? 'WebSocket conectado' : 'Modo HTTP'}>
              {wsConnected ? (
                <Wifi size={14} style={{ color: '#16a34a' }} />
              ) : (
                <WifiOff size={14} style={{ color: 'var(--text-tertiary)' }} />
              )}
            </span>
            <ModelSelector canManageGlobal={user.is_admin} />
            <HeaderSelect
              value={liveVoice.enabled ? 'live' : responseMode}
              options={RESPONSE_MODE_OPTIONS}
              onChange={setResponseMode}
              disabled={liveVoice.enabled}
              icon={<UserRound size={14} aria-hidden="true" />}
              label="Modo do agente"
              className="hidden sm:block"
              title={liveVoice.enabled ? 'O modo Live esta ativo enquanto o microfone estiver ligado' : 'Modo do agente'}
            />
            <HeaderSelect
              value={reasoningEffort}
              options={reasoningEffortOptions}
              onChange={setReasoningEffort}
              icon={<Brain size={14} aria-hidden="true" />}
              label="Esforco de raciocinio do modelo"
              className="hidden md:block"
              title="Esforco de raciocinio enviado ao modelo"
            />
            <LiveVoiceButton controller={liveVoice} />
            <button
              type="button"
              onClick={() => setMobileToolsOpen(open => !open)}
              className="rounded-lg p-1.5 transition-colors hover:bg-black/5 dark:hover:bg-white/10 sm:hidden"
              title="Mais ferramentas"
              aria-label="Mais ferramentas"
              aria-expanded={mobileToolsOpen}
            >
              <MoreHorizontal size={20} style={{ color: 'var(--text-secondary)' }} />
            </button>
            {user.is_admin && (
              <button
                onClick={() => setAdminUsersOpen(true)}
                className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
                title="Usuarios e aprovacoes"
              >
                <Users size={18} style={{ color: 'var(--text-secondary)' }} />
              </button>
            )}
            <button
              onClick={() => setWorkspaceOpen(true)}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Workspace"
            >
              <FolderOpen size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setDocumentsOpen(true)}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Documentos RAG"
            >
              <FileText size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setSkillsOpen(true)}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Skills"
            >
              <Sparkles size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setProviderManagerOpen(true)}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Gerenciar providers"
            >
              <Server size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Configuracoes"
            >
              <Settings size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            <button
              onClick={handleLogout}
              className="hidden p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors sm:block"
              title="Sair"
            >
              <LogOut size={18} style={{ color: 'var(--text-secondary)' }} />
            </button>
            {mobileToolsOpen && (
              <>
                <button
                  type="button"
                  className="fixed inset-0 z-[69] sm:hidden"
                  aria-label="Fechar ferramentas"
                  onClick={() => setMobileToolsOpen(false)}
                />
                <div
                  className="absolute right-2 top-[calc(100%+8px)] z-[70] grid w-64 gap-1 rounded-2xl border p-2 shadow-2xl sm:hidden"
                  style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                >
                  {user.is_admin && (
                    <MobileToolButton icon={<Users size={17} />} label="Usuarios e aprovacoes" onClick={() => { setMobileToolsOpen(false); setAdminUsersOpen(true) }} />
                  )}
                  <MobileToolButton icon={<FolderOpen size={17} />} label="Workspace" onClick={() => { setMobileToolsOpen(false); setWorkspaceOpen(true) }} />
                  <MobileToolButton icon={<FileText size={17} />} label="Documentos RAG" onClick={() => { setMobileToolsOpen(false); setDocumentsOpen(true) }} />
                  <MobileToolButton icon={<Sparkles size={17} />} label="Skills" onClick={() => { setMobileToolsOpen(false); setSkillsOpen(true) }} />
                  <MobileToolButton icon={<Server size={17} />} label="Gerenciar providers" onClick={() => { setMobileToolsOpen(false); setProviderManagerOpen(true) }} />
                  <MobileToolButton icon={<Settings size={17} />} label="Configuracoes" onClick={() => { setMobileToolsOpen(false); setSettingsOpen(true) }} />
                  <MobileToolButton icon={<LogOut size={17} />} label="Sair" onClick={() => { setMobileToolsOpen(false); handleLogout() }} danger />
                </div>
              </>
            )}
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
            className="h-full overflow-y-auto px-2.5 py-4 sm:px-4 sm:py-6"
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
                      onRetry={msg.jobId && msg.jobStatus === 'failed' ? () => retryFailedJob(msg.jobId!) : undefined}
                      onSpeak={liveVoice.speakText}
                      onStopSpeaking={liveVoice.stopSpeaking}
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

        <LiveVoiceDock controller={liveVoice} />
        <ChatInput
          onSend={handleSend}
          busy={isLoading}
          onStop={handleStop}
          maxUploadMb={config?.max_upload_mb || 10}
          status={streamStatus}
        />
      </div>
    </div>
  )
}
