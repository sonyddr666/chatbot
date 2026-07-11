import { create } from 'zustand'
import type { ChatMessage, Conversation, Profile, AppConfig, DocumentInfo, Stats, ReasoningEffort, ResponseMode } from '../lib/api'
import { api, getAuthToken, parseApiTimestamp } from '../lib/api'

let activeStreamController: AbortController | null = null
let activeJobId: string | null = null

const PENDING_JOBS_KEY = 'chatbot_pending_jobs_v1'
const PENDING_JOB_TTL_MS = 24 * 60 * 60 * 1000

interface PendingChatJob {
  clientRequestId: string
  owner: string
  sessionId: string
  message: string
  useRag: boolean
  responseMode: ResponseMode
  reasoningEffort: ReasoningEffort
  createdAt: number
}

function pendingOwner(): string {
  const token = getAuthToken()
  if (!token) return ''
  try {
    const encoded = token.split('.')[1]
    const payload = JSON.parse(atob(encoded.replace(/-/g, '+').replace(/_/g, '/')))
    if (payload?.sub) return String(payload.sub)
  } catch {
    // A token opaco ainda recebe um escopo estavel sem ser salvo novamente.
  }
  return token.slice(-24)
}

function loadPendingJobs(): PendingChatJob[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(PENDING_JOBS_KEY) || '[]')
    if (!Array.isArray(parsed)) return []
    const cutoff = Date.now() - PENDING_JOB_TTL_MS
    return parsed.filter(item => item?.clientRequestId && item?.createdAt >= cutoff)
  } catch {
    return []
  }
}

function savePendingJobs(items: PendingChatJob[]) {
  localStorage.setItem(PENDING_JOBS_KEY, JSON.stringify(items.slice(-20)))
}

function rememberPendingJob(item: PendingChatJob) {
  savePendingJobs([
    ...loadPendingJobs().filter(current => current.clientRequestId !== item.clientRequestId),
    item,
  ])
}

function forgetPendingJob(clientRequestId: string) {
  savePendingJobs(loadPendingJobs().filter(item => item.clientRequestId !== clientRequestId))
}

function pendingJobsForSession(sessionId: string): PendingChatJob[] {
  const owner = pendingOwner()
  return loadPendingJobs().filter(item => item.owner === owner && item.sessionId === sessionId)
}

async function recoverPendingJobs(sessionId: string) {
  for (const pending of pendingJobsForSession(sessionId)) {
    try {
      await api.createChatJob(
        pending.message,
        pending.sessionId,
        pending.useRag,
        pending.responseMode,
        pending.reasoningEffort,
        pending.clientRequestId,
      )
      forgetPendingJob(pending.clientRequestId)
    } catch {
      // Mantem o pedido para uma proxima retomada se a rede ou o servidor ainda estiver indisponivel.
    }
  }
}

function loadResponseMode(): ResponseMode {
  const saved = localStorage.getItem('chatbot_response_mode')
  return saved === 'thinking' || saved === 'live' ? saved : 'normal'
}

function loadReasoningEffort(): ReasoningEffort {
  const saved = localStorage.getItem('chatbot_reasoning_effort')
  return saved === 'medium' || saved === 'high' || saved === 'xhigh' || saved === 'max' ? saved : 'low'
}

// ─── Tipos locais ───
export interface ChatMetrics {
  ttft_s?: number
  total_s?: number
  route?: 'fast' | 'full'
  classify_ms?: number
  moderation_ms?: number
}

interface ChatState {
  // Messages
  messages: ChatMessage[]
  isLoading: boolean
  error: string | null
  lastMetrics: ChatMetrics | null
  route: 'fast' | 'full' | null
  streamStatus: string | null

  // Session
  sessionId: string
  conversations: Conversation[]
  showSidebar: boolean

  // Config
  config: AppConfig | null
  profiles: Profile[]
  selectedProfile: string

  // Toggles
  responseMode: ResponseMode
  reasoningEffort: ReasoningEffort
  useRag: boolean

  // WebSocket
  wsConnected: boolean
  wsReconnecting: boolean

  // Documents
  documents: DocumentInfo[]

  // Stats
  stats: Stats | null

  // Actions
  sendMessage: (
    content: string,
    responseModeOverride?: ResponseMode,
    reasoningEffortOverride?: ReasoningEffort,
  ) => Promise<void>
  regenerate: () => Promise<void>
  stopGeneration: () => void
  clearMessages: () => void
  setSession: (id: string) => Promise<void>
  loadConversations: () => Promise<void>
  loadConfig: () => Promise<void>
  loadProfiles: () => Promise<void>
  loadDocuments: () => Promise<void>
  loadStats: () => Promise<void>
  toggleSidebar: () => void
  setError: (err: string | null) => void
  setSelectedProfile: (id: string) => void
  setResponseMode: (mode: ResponseMode) => void
  setReasoningEffort: (effort: ReasoningEffort) => void
  setUseRag: (v: boolean) => void
  setWsConnected: (v: boolean) => void
  setWsReconnecting: (v: boolean) => void
}

function createAssistantMsg(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    timestamp: new Date(),
    reasoning: '',
  }
}

function createUserMsg(content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: new Date(),
  }
}

function updateAssistantForJob(jobId: string, updater: (message: ChatMessage) => ChatMessage) {
  useChatStore.setState(state => {
    const messages = [...state.messages]
    let index = -1
    for (let current = messages.length - 1; current >= 0; current -= 1) {
      if (messages[current].role === 'assistant' && messages[current].jobId === jobId) {
        index = current
        break
      }
    }
    if (index < 0) return state
    messages[index] = updater(messages[index])
    return { messages }
  })
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  lastMetrics: null,
  route: null,
  streamStatus: null,
  sessionId: 'default',
  conversations: [],
  showSidebar: false,
  config: null,
  profiles: [],
  selectedProfile: 'zen-free',
  responseMode: loadResponseMode(),
  reasoningEffort: loadReasoningEffort(),
  useRag: true,
  wsConnected: false,
  wsReconnecting: false,
  documents: [],
  stats: null,

  setWsConnected: (v) => set({ wsConnected: v }),
  setWsReconnecting: (v) => set({ wsReconnecting: v }),
  setResponseMode: (mode) => {
    localStorage.setItem('chatbot_response_mode', mode)
    if (mode === 'thinking') {
      localStorage.setItem('chatbot_reasoning_effort', 'high')
      set({ responseMode: mode, reasoningEffort: 'high' })
    } else if (mode === 'live') {
      localStorage.setItem('chatbot_reasoning_effort', 'low')
      set({ responseMode: mode, reasoningEffort: 'low' })
    } else {
      set({ responseMode: mode })
    }
  },
  setReasoningEffort: (effort) => {
    localStorage.setItem('chatbot_reasoning_effort', effort)
    set({ reasoningEffort: effort })
  },
  setUseRag: (v) => set({ useRag: v }),

  sendMessage: async (content: string, responseModeOverride?: ResponseMode, reasoningEffortOverride?: ReasoningEffort) => {
    const { isLoading, sessionId, responseMode, reasoningEffort, useRag } = get()
    if (!content.trim() || isLoading) return

    const userMsg = createUserMsg(content)
    const assistantMsg = createAssistantMsg()
    const selectedMode = responseModeOverride || responseMode
    const selectedEffort = reasoningEffortOverride || reasoningEffort
    const clientRequestId = crypto.randomUUID()
    rememberPendingJob({
      clientRequestId,
      owner: pendingOwner(),
      sessionId,
      message: content.trim(),
      useRag,
      responseMode: selectedMode,
      reasoningEffort: selectedEffort,
      createdAt: Date.now(),
    })

    set(s => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isLoading: true,
      error: null,
      lastMetrics: null,
      route: null,
      streamStatus: 'Preparando resposta...',
    }))

    let controller: AbortController | null = null
    let startedJobId: string | null = null
    try {
      activeStreamController?.abort()
      controller = new AbortController()
      activeStreamController = controller
      const job = await api.createChatJob(
        content,
        sessionId,
        useRag,
        selectedMode,
        selectedEffort,
        clientRequestId,
      )
      forgetPendingJob(clientRequestId)
      startedJobId = job.id
      if (get().sessionId !== sessionId) {
        void get().loadConversations()
        return
      }
      activeJobId = job.id
      set(state => {
        const next = [...state.messages]
        const last = next[next.length - 1]
        if (last?.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            messageId: job.assistant_message_id,
            jobId: job.id,
            jobStatus: job.status,
            providerId: job.provider_id,
            providerName: job.provider_name,
            modelId: job.model_id,
            modelName: job.model_name,
          }
        }
        return { messages: next }
      })
      await jobStream(job.id, 0, controller.signal)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (!(err instanceof TypeError)) forgetPendingJob(clientRequestId)
      if (get().sessionId !== sessionId) return
      const msg = err instanceof Error ? err.message : 'Erro desconhecido'
      set(s => ({
        messages: s.messages.map((m, i) =>
          i === s.messages.length - 1 && m.role === 'assistant'
            ? { ...m, content: m.content || `❌ **Erro:** ${msg}` }
            : m,
        ),
        error: msg,
        streamStatus: null,
      }))
    } finally {
      if (activeStreamController === controller) activeStreamController = null
      if (activeJobId === startedJobId) activeJobId = null
      if (get().sessionId === sessionId) set({ isLoading: false, streamStatus: null })
    }
  },

  regenerate: async () => {
    const { messages, sessionId, isLoading, responseMode, reasoningEffort } = get()
    if (messages.length < 2 || isLoading) return

    const lastUser = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUser) return
    if (messages[messages.length - 1]?.role !== 'assistant') return

    const withoutLast = messages.slice(0, -1)
    const newAssistant = createAssistantMsg()
    set({
      messages: [...withoutLast, newAssistant],
      isLoading: true,
      lastMetrics: null,
      streamStatus: 'Preparando resposta...',
    })

    let controller: AbortController | null = null
    try {
      activeStreamController?.abort()
      controller = new AbortController()
      activeStreamController = controller
      await httpStream(lastUser.content, sessionId, false, responseMode, reasoningEffort, controller.signal)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      set({ isLoading: false, error: 'Falha ao regenerar', streamStatus: null })
    } finally {
      if (activeStreamController === controller) activeStreamController = null
      set({ isLoading: false, streamStatus: null })
    }
  },

  stopGeneration: () => {
    const jobId = activeJobId
    if (jobId) void api.cancelChatJob(jobId).catch(() => undefined)
    activeStreamController?.abort()
    activeStreamController = null
    activeJobId = null
    set({ isLoading: false, streamStatus: null })
    // Se o usuário interrompeu, marca a última mensagem como interrompida
    const { messages } = get()
    const last = messages[messages.length - 1]
    if (last?.role === 'assistant' && last.content === '') {
      useChatStore.setState(s => ({
        messages: s.messages.map((m, i) =>
          i === s.messages.length - 1 ? { ...m, content: '*(interrompido)*' } : m
        ),
      }))
    }
  },

  clearMessages: () => set({ messages: [], error: null, streamStatus: null }),

  setSession: async (id: string) => {
    activeStreamController?.abort()
    activeStreamController = null
    activeJobId = null
    let isResuming = false
    set({ sessionId: id, messages: [], isLoading: true, streamStatus: null })
    try {
      const localPending = pendingJobsForSession(id)
      if (localPending.length) {
        const pending = localPending[localPending.length - 1]
        set({
          messages: [
            { ...createUserMsg(pending.message), id: `pending-user-${pending.clientRequestId}` },
            {
              ...createAssistantMsg(),
              id: `pending-assistant-${pending.clientRequestId}`,
              jobStatus: 'queued',
            },
          ],
          streamStatus: 'Retomando resposta...',
        })
      }
      await recoverPendingJobs(id)
      const conv = await api.getConversation(id)
      if (conv?.messages) {
        const msgs: ChatMessage[] = conv.messages.map((m: any) => ({
          id: `msg-${m.id}`,
          role: m.role,
          content: m.content,
          timestamp: parseApiTimestamp(m.created_at),
          messageId: m.id,
          feedbackScore: m.feedback_score,
          reasoning: m.reasoning || '',
          skillActivities: Array.isArray(m.skill_activities) ? m.skill_activities : [],
          providerId: m.provider_id,
          providerName: m.provider_name,
          modelId: m.model_id,
          modelName: m.model_name,
          jobId: m.job_id,
          jobStatus: m.status || 'completed',
          readAt: m.read_at,
        }))
        const restored = await Promise.all(msgs.map(async message => {
          if (message.role !== 'assistant') return message
          const match = message.content.match(/<!-- workspace-plan:([a-f0-9]{32}) -->/i)
          if (!match) return message
          try {
            const workspacePlan = await api.workspaceAiGetPlan(match[1])
            return { ...message, workspacePlan }
          } catch {
            return message
          }
        }))
        set({ messages: restored })
        const unreadIds = restored
          .filter(message => message.role === 'assistant' && message.jobId && message.jobStatus === 'completed' && !message.readAt && message.messageId)
          .map(message => message.messageId as number)
        if (unreadIds.length) {
          window.setTimeout(() => {
            void Promise.all(unreadIds.map(messageId => api.markMessageRead(messageId).catch(() => null))).then(() => {
              const readAt = new Date().toISOString()
              useChatStore.setState(state => ({
                messages: state.messages.map(message => message.messageId && unreadIds.includes(message.messageId)
                  ? { ...message, readAt }
                  : message),
              }))
            })
          }, 1500)
        }
        const pending = [...restored].reverse().find(
          message => message.role === 'assistant'
            && !!message.jobId
            && (message.jobStatus === 'queued' || message.jobStatus === 'running'),
        )
        if (pending?.jobId) {
          isResuming = true
          void resumePersistedJob(pending.jobId)
        }
      }
    } catch {
      // ok
    } finally {
      if (!isResuming) set({ isLoading: false })
    }
  },

  loadConversations: async () => {
    try {
      const convs = await api.listConversations()
      set({ conversations: convs })
    } catch { /* silêncio */ }
  },

  loadConfig: async () => {
    try {
      const config = await api.getConfig()
      set({ config, selectedProfile: config.profile })
    } catch { /* silêncio */ }
  },

  loadProfiles: async () => {
    try {
      const profiles = await api.getProfiles()
      set({ profiles })
    } catch { /* silêncio */ }
  },

  loadDocuments: async () => {
    try {
      const docs = await api.listDocuments()
      set({ documents: docs })
    } catch { /* silêncio */ }
  },

  loadStats: async () => {
    try {
      const stats = await api.getStats()
      set({ stats })
    } catch { /* silêncio */ }
  },

  toggleSidebar: () => set(s => ({ showSidebar: !s.showSidebar })),
  setError: err => set({ error: err }),
  setSelectedProfile: id => set({ selectedProfile: id }),
}))

async function resumePersistedJob(jobId: string) {
  let controller: AbortController | null = null
  try {
    const job = await api.getChatJob(jobId)
    useChatStore.setState(state => ({
      messages: state.messages.map(message => message.jobId === jobId ? {
        ...message,
        content: job.content,
        reasoning: job.reasoning,
        jobStatus: job.status,
        messageId: job.assistant_message_id,
      } : message),
      isLoading: job.status === 'queued' || job.status === 'running',
    }))
    if (job.status !== 'queued' && job.status !== 'running') return

    activeStreamController?.abort()
    controller = new AbortController()
    activeStreamController = controller
    activeJobId = jobId
    await jobStream(jobId, job.last_event_id, controller.signal)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    useChatStore.setState({
      error: error instanceof Error ? error.message : 'Falha ao reconectar ao job',
      isLoading: false,
    })
  } finally {
    if (activeJobId === jobId) activeJobId = null
    if (activeStreamController === controller) activeStreamController = null
  }
}

async function jobStream(jobId: string, afterId: number, signal?: AbortSignal) {
  for await (const chunk of api.streamChatJob(jobId, afterId, signal)) {
    if (chunk.type === 'reasoning' || chunk.type === 'content') {
      updateAssistantForJob(jobId, message => chunk.type === 'reasoning'
        ? { ...message, reasoning: `${message.reasoning || ''}${chunk.text || ''}`, jobStatus: 'running' }
        : { ...message, content: `${message.content || ''}${chunk.text || ''}`, jobStatus: 'running' })
      if (activeJobId === jobId) useChatStore.setState({ streamStatus: null })
    } else if (chunk.type === 'status') {
      if (activeJobId === jobId) useChatStore.setState({ streamStatus: chunk.text || 'Processando...' })
    } else if (chunk.type === 'skill_activity' && chunk.skillActivity) {
      updateAssistantForJob(jobId, message => ({
        ...message,
        skillActivities: [...(message.skillActivities || []), chunk.skillActivity!],
      }))
    } else if (chunk.type === 'workspace_plan' && chunk.workspacePlan) {
      updateAssistantForJob(jobId, message => ({ ...message, workspacePlan: chunk.workspacePlan }))
    } else if (chunk.type === 'start') {
      updateAssistantForJob(jobId, message => ({
        ...message,
        messageId: chunk.messageId || message.messageId,
        providerId: chunk.providerId,
        providerName: chunk.providerName,
        modelId: chunk.modelId,
        modelName: chunk.modelName,
        jobId,
        jobStatus: 'running',
      }))
      if (activeJobId === jobId) useChatStore.setState({ streamStatus: 'Conectando ao job...' })
    } else if (chunk.type === 'done') {
      const readAt = new Date().toISOString()
      updateAssistantForJob(jobId, message => ({
        ...message,
        messageId: chunk.messageId || message.messageId,
        jobStatus: 'completed',
        readAt,
      }))
      if (activeJobId === jobId) useChatStore.setState({ isLoading: false, streamStatus: null })
      const messageId = chunk.messageId
      if (messageId) void api.markMessageRead(messageId).catch(() => undefined)
      void useChatStore.getState().loadConversations()
    } else if (chunk.type === 'job_state') {
      updateAssistantForJob(jobId, message => ({
        ...message,
        jobStatus: (chunk.jobStatus as ChatMessage['jobStatus']) || 'failed',
      }))
      if (activeJobId === jobId) {
        useChatStore.setState({ error: chunk.text || null, isLoading: false, streamStatus: null })
      }
    }
  }
}

// ─── HTTP SSE Streaming (fallback / principal) ───
async function httpStream(
  content: string,
  sessionId: string,
  useRag = false,
  responseMode: ResponseMode = 'normal',
  reasoningEffort: ReasoningEffort = 'low',
  signal?: AbortSignal,
) {
  for await (const chunk of api.stream(content, sessionId, useRag, responseMode, reasoningEffort, signal)) {
    if (chunk.type === 'reasoning') {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, reasoning: (last.reasoning || '') + (chunk.text || '') }
        useChatStore.setState({ messages: msgs, streamStatus: null })
      }
    } else if (chunk.type === 'content') {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + (chunk.text || '') }
        useChatStore.setState({ messages: msgs, streamStatus: null })
      }
    } else if (chunk.type === 'workspace_plan' && chunk.workspacePlan) {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, workspacePlan: chunk.workspacePlan }
        useChatStore.setState({ messages: msgs })
      }
    } else if (chunk.type === 'skill_activity' && chunk.skillActivity) {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = {
          ...last,
          skillActivities: [...(last.skillActivities || []), chunk.skillActivity],
        }
        useChatStore.setState({ messages: msgs })
      }
    } else if (chunk.type === 'done') {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
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
        useChatStore.setState({ messages: msgs })
      }
      useChatStore.setState({ streamStatus: null })
      useChatStore.getState().loadConversations()
      if (chunk.hasReasoning !== undefined) {
        useChatStore.setState({ route: chunk.hasReasoning ? 'full' : 'fast' })
      }
      if ((chunk as any).metrics) {
        useChatStore.setState({ lastMetrics: (chunk as any).metrics })
      }
      break
    } else if (chunk.type === 'start') {
      const route = (chunk as any).route
      useChatStore.setState({
        ...(route ? { route } : {}),
        streamStatus: 'Conectando ao modelo...',
      })
    } else if (chunk.type === 'status') {
      useChatStore.setState({ streamStatus: chunk.text || 'Processando...' })
    }
  }
}
