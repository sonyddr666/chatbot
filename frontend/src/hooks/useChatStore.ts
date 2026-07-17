import { create } from 'zustand'
import type { ChatAttachmentInfo, ChatMessage, Conversation, Profile, AppConfig, DocumentInfo, Stats, ReasoningEffort, ResponseMode } from '../lib/api'
import { api, getAuthToken, parseApiTimestamp, upsertSkillActivity } from '../lib/api'

let activeStreamController: AbortController | null = null
let activeJobId: string | null = null
let sessionLoadSequence = 0
let conversationsLoadSequence = 0
let configLoadSequence = 0
let profilesLoadSequence = 0
let documentsLoadSequence = 0
let statsLoadSequence = 0
const resumeJobRuns = new Map<string, Promise<void>>()

const PENDING_JOBS_KEY = 'chatbot_pending_jobs_v1'
const PENDING_JOB_TTL_MS = 24 * 60 * 60 * 1000
const STREAM_RENDER_INTERVAL_MS = 40
const STREAM_RENDER_MAX_CHARS = 2048

export function detachActiveChatStreams() {
  sessionLoadSequence += 1
  activeStreamController?.abort()
  activeStreamController = null
  activeJobId = null
  resumeJobRuns.clear()
}

interface PendingChatJob {
  clientRequestId: string
  owner: string
  sessionId: string
  message: string
  useRag: boolean
  responseMode: ResponseMode
  reasoningEffort: ReasoningEffort
  attachments: ChatAttachmentInfo[]
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
    return parsed
      .filter(item => item?.clientRequestId && item?.createdAt >= cutoff)
      .map(item => ({
        ...item,
        attachments: Array.isArray(item.attachments) ? item.attachments : [],
      }))
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
        (pending.attachments || []).map(attachment => attachment.id),
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
  return ['auto', 'none', 'default', 'low', 'medium', 'high', 'xhigh', 'max'].includes(saved || '')
    ? saved as ReasoningEffort
    : 'auto'
}

function loadUseRag(): boolean {
  const saved = localStorage.getItem('chatbot_use_rag')
  return saved === null ? true : saved === 'true'
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
    files?: File[],
  ) => Promise<boolean>
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

function createUserMsg(content: string, attachments: ChatAttachmentInfo[] = []): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: new Date(),
    attachments,
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

function createStreamRenderBuffer(onFlush: (reasoning: string, content: string) => void) {
  let pendingReasoning = ''
  let pendingContent = ''
  let renderTimer: ReturnType<typeof setTimeout> | null = null

  const flush = () => {
    if (renderTimer) clearTimeout(renderTimer)
    renderTimer = null
    if (!pendingReasoning && !pendingContent) return
    const reasoning = pendingReasoning
    const content = pendingContent
    pendingReasoning = ''
    pendingContent = ''
    onFlush(reasoning, content)
  }

  const queue = (type: 'reasoning' | 'content', text: string) => {
    if (!text) return
    if (type === 'reasoning') pendingReasoning += text
    else pendingContent += text
    if (pendingReasoning.length + pendingContent.length >= STREAM_RENDER_MAX_CHARS) {
      flush()
    } else if (!renderTimer) {
      renderTimer = setTimeout(flush, STREAM_RENDER_INTERVAL_MS)
    }
  }

  return { flush, queue }
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
  useRag: loadUseRag(),
  wsConnected: false,
  wsReconnecting: false,
  documents: [],
  stats: null,

  setWsConnected: (v) => set({ wsConnected: v }),
  setWsReconnecting: (v) => set({ wsReconnecting: v }),
  setResponseMode: (mode) => {
    localStorage.setItem('chatbot_response_mode', mode)
    set({ responseMode: mode })
  },
  setReasoningEffort: (effort) => {
    localStorage.setItem('chatbot_reasoning_effort', effort)
    set({ reasoningEffort: effort })
  },
  setUseRag: (v) => {
    localStorage.setItem('chatbot_use_rag', String(v))
    set({ useRag: v })
  },

  sendMessage: async (
    content: string,
    responseModeOverride?: ResponseMode,
    reasoningEffortOverride?: ReasoningEffort,
    files: File[] = [],
  ) => {
    const { isLoading, sessionId, responseMode, reasoningEffort, useRag } = get()
    if ((!content.trim() && files.length === 0) || isLoading) return false

    let attachments: ChatAttachmentInfo[] = []
    if (files.length) {
      activeStreamController?.abort()
      const uploadController = new AbortController()
      activeStreamController = uploadController
      set({ isLoading: true, error: null, streamStatus: `Enviando ${files.length} arquivo(s)...` })
      try {
        const uploaded = await api.uploadChatAttachments(files, sessionId, uploadController.signal)
        attachments = uploaded.attachments
      } catch (error) {
        if (activeStreamController === uploadController) activeStreamController = null
        if (error instanceof DOMException && error.name === 'AbortError') {
          set({ isLoading: false, streamStatus: null })
          return false
        }
        const message = error instanceof Error ? error.message : 'Falha ao enviar anexos'
        set({ isLoading: false, error: message, streamStatus: null })
        return false
      }
      if (activeStreamController === uploadController) activeStreamController = null
    }

    const userMsg = createUserMsg(content.trim(), attachments)
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
      attachments,
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
    let jobAccepted = false
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
        attachments.map(attachment => attachment.id),
      )
      jobAccepted = true
      forgetPendingJob(clientRequestId)
      void get().loadStats()
      startedJobId = job.id
      if (get().sessionId !== sessionId) {
        void get().loadConversations()
        return true
      }
      activeJobId = job.id
      set(state => {
        const next = [...state.messages]
        const userIndex = next.length - 2
        if (next[userIndex]?.role === 'user') {
          next[userIndex] = {
            ...next[userIndex],
            messageId: job.user_message_id,
            attachments: job.attachments || attachments,
          }
        }
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
      return true
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return jobAccepted
      const recoverableNetworkError = err instanceof TypeError
      if (!recoverableNetworkError) {
        forgetPendingJob(clientRequestId)
        if (!jobAccepted) {
          void Promise.all(
            attachments.map(attachment => api.deletePendingChatAttachment(attachment.id).catch(() => null)),
          )
        }
      }
      if (get().sessionId !== sessionId) return jobAccepted
      const msg = err instanceof Error ? err.message : 'Erro desconhecido'
      set(s => ({
        messages: !jobAccepted && !recoverableNetworkError
          ? s.messages.slice(0, -2)
          : s.messages.map((m, i) =>
              i === s.messages.length - 1 && m.role === 'assistant'
                ? {
                    ...m,
                    content: m.content || (recoverableNetworkError
                      ? 'A conexao caiu. O pedido ficou salvo e sera retomado ao reabrir esta conversa.'
                      : `❌ **Erro:** ${msg}`),
                  }
                : m,
            ),
        error: msg,
        streamStatus: null,
      }))
      return jobAccepted || recoverableNetworkError
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
    const loadOwner = pendingOwner()
    const loadSequence = ++sessionLoadSequence
    const isCurrentLoad = () => (
      get().sessionId === id
      && sessionLoadSequence === loadSequence
      && pendingOwner() === loadOwner
    )
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
            { ...createUserMsg(pending.message, pending.attachments || []), id: `pending-user-${pending.clientRequestId}` },
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
      if (!isCurrentLoad()) return
      const conv = await api.getConversation(id)
      if (!isCurrentLoad()) return
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
          attachments: Array.isArray(m.attachments) ? m.attachments : [],
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
        if (!isCurrentLoad()) return
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
      if (isCurrentLoad() && !isResuming) set({ isLoading: false })
    }
  },

  loadConversations: async () => {
    const requestId = ++conversationsLoadSequence
    const owner = pendingOwner()
    try {
      const convs = await api.listConversations()
      if (requestId === conversationsLoadSequence && owner === pendingOwner()) {
        set({ conversations: convs })
      }
    } catch { /* silêncio */ }
  },

  loadConfig: async () => {
    const requestId = ++configLoadSequence
    const owner = pendingOwner()
    try {
      const config = await api.getConfig()
      if (requestId !== configLoadSequence || owner !== pendingOwner()) return
      const allowed = config.reasoning_efforts?.length ? config.reasoning_efforts : ['auto' as ReasoningEffort]
      const current = get().reasoningEffort
      const reasoningEffort = allowed.includes(current)
        ? current
        : allowed.includes('default') ? 'default' : allowed.includes('medium') ? 'medium' : allowed[0]
      localStorage.setItem('chatbot_reasoning_effort', reasoningEffort)
      set({ config, selectedProfile: config.profile, reasoningEffort })
    } catch { /* silêncio */ }
  },

  loadProfiles: async () => {
    const requestId = ++profilesLoadSequence
    const owner = pendingOwner()
    try {
      const profiles = await api.getProfiles()
      if (requestId === profilesLoadSequence && owner === pendingOwner()) set({ profiles })
    } catch { /* silêncio */ }
  },

  loadDocuments: async () => {
    const requestId = ++documentsLoadSequence
    const owner = pendingOwner()
    try {
      const docs = await api.listDocuments()
      if (requestId === documentsLoadSequence && owner === pendingOwner()) set({ documents: docs })
    } catch { /* silêncio */ }
  },

  loadStats: async () => {
    const requestId = ++statsLoadSequence
    const owner = pendingOwner()
    try {
      const stats = await api.getStats()
      if (requestId === statsLoadSequence && owner === pendingOwner()) set({ stats })
    } catch { /* silêncio */ }
  },

  toggleSidebar: () => set(s => ({ showSidebar: !s.showSidebar })),
  setError: err => set({ error: err }),
  setSelectedProfile: id => set({ selectedProfile: id }),
}))

function resumePersistedJob(jobId: string): Promise<void> {
  const existing = resumeJobRuns.get(jobId)
  if (existing) return existing
  const run = runPersistedJobResume(jobId)
  resumeJobRuns.set(jobId, run)
  void run.finally(() => {
    if (resumeJobRuns.get(jobId) === run) resumeJobRuns.delete(jobId)
  })
  return run
}

async function runPersistedJobResume(jobId: string) {
  const controller = new AbortController()
  try {
    activeStreamController?.abort()
    activeStreamController = controller
    activeJobId = jobId
    let failures = 0
    while (!controller.signal.aborted) {
      try {
        const job = await api.getChatJob(jobId)
        useChatStore.setState(state => ({
          messages: state.messages.map(message => message.jobId === jobId ? {
            ...message,
            content: job.content,
            reasoning: job.reasoning,
            attachments: job.assistant_attachments || [],
            jobStatus: job.status,
            messageId: job.assistant_message_id,
          } : message),
          isLoading: job.status === 'queued' || job.status === 'running',
          error: null,
        }))
        if (job.status !== 'queued' && job.status !== 'running') return
        failures = 0
        const terminal = await jobStream(jobId, job.last_event_id, controller.signal)
        if (terminal || controller.signal.aborted) return
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        failures += 1
        if (failures >= 80) throw error
      }
      if (activeJobId === jobId) {
        useChatStore.setState({ streamStatus: 'Reconectando ao servidor...' })
      }
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(resolve, 750)
        controller.signal.addEventListener('abort', () => {
          window.clearTimeout(timeout)
          reject(new DOMException('Aborted', 'AbortError'))
        }, { once: true })
      })
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    useChatStore.setState({
      error: error instanceof Error ? error.message : 'Falha ao reconectar ao job',
      isLoading: false,
    })
  } finally {
    if (activeStreamController === controller) {
      activeStreamController = null
      if (activeJobId === jobId) activeJobId = null
    }
  }
}

async function jobStream(jobId: string, afterId: number, signal?: AbortSignal): Promise<boolean> {
  const deltaBuffer = createStreamRenderBuffer((reasoning, content) => {
    updateAssistantForJob(jobId, message => ({
      ...message,
      reasoning: `${message.reasoning || ''}${reasoning}`,
      content: `${message.content || ''}${content}`,
      jobStatus: 'running',
    }))
    if (activeJobId === jobId && useChatStore.getState().streamStatus !== null) {
      useChatStore.setState({ streamStatus: null })
    }
  })

  try {
    for await (const chunk of api.streamChatJob(jobId, afterId, signal)) {
      if (chunk.type === 'reasoning' || chunk.type === 'content') {
        deltaBuffer.queue(chunk.type, chunk.text || '')
      } else if (chunk.type === 'status') {
        deltaBuffer.flush()
        if (activeJobId === jobId) useChatStore.setState({ streamStatus: chunk.text || 'Processando...' })
      } else if (chunk.type === 'skill_activity' && chunk.skillActivity) {
        deltaBuffer.flush()
        updateAssistantForJob(jobId, message => ({
          ...message,
          skillActivities: upsertSkillActivity(message.skillActivities || [], chunk.skillActivity!),
        }))
      } else if (chunk.type === 'attachment' && chunk.attachment) {
        deltaBuffer.flush()
        updateAssistantForJob(jobId, message => ({
          ...message,
          attachments: (message.attachments || []).some(item => item.id === chunk.attachment!.id)
            ? message.attachments
            : [...(message.attachments || []), chunk.attachment!],
        }))
      } else if (chunk.type === 'workspace_plan' && chunk.workspacePlan) {
        deltaBuffer.flush()
        updateAssistantForJob(jobId, message => ({ ...message, workspacePlan: chunk.workspacePlan }))
      } else if (chunk.type === 'reset') {
        deltaBuffer.flush()
        updateAssistantForJob(jobId, message => ({
          ...message,
          content: '',
          reasoning: '',
          attachments: [],
          skillActivities: [],
          jobStatus: 'queued',
        }))
      } else if (chunk.type === 'start') {
        deltaBuffer.flush()
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
        deltaBuffer.flush()
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
        const store = useChatStore.getState()
        void Promise.all([store.loadConversations(), store.loadStats()])
        return true
      } else if (chunk.type === 'job_state') {
        deltaBuffer.flush()
        updateAssistantForJob(jobId, message => ({
          ...message,
          jobStatus: (chunk.jobStatus as ChatMessage['jobStatus']) || 'failed',
        }))
        if (activeJobId === jobId) {
          useChatStore.setState({ error: chunk.text || null, isLoading: false, streamStatus: null })
        }
        return true
      }
    }
  } finally {
    deltaBuffer.flush()
  }
  return false
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
  const deltaBuffer = createStreamRenderBuffer((reasoning, contentDelta) => {
    if (!reasoning && !contentDelta) return
    const state = useChatStore.getState()
    const messages = [...state.messages]
    const last = messages[messages.length - 1]
    if (last?.role !== 'assistant') return
    messages[messages.length - 1] = {
      ...last,
      reasoning: `${last.reasoning || ''}${reasoning}`,
      content: `${last.content || ''}${contentDelta}`,
    }
    useChatStore.setState({ messages, streamStatus: null })
  })

  try {
    for await (const chunk of api.stream(content, sessionId, useRag, responseMode, reasoningEffort, signal)) {
      if (chunk.type === 'reasoning' || chunk.type === 'content') {
        deltaBuffer.queue(chunk.type, chunk.text || '')
        continue
      }
      deltaBuffer.flush()

      if (chunk.type === 'workspace_plan' && chunk.workspacePlan) {
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
            skillActivities: upsertSkillActivity(last.skillActivities || [], chunk.skillActivity),
          }
          useChatStore.setState({ messages: msgs })
        }
      } else if (chunk.type === 'attachment' && chunk.attachment) {
        const s = useChatStore.getState()
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (last?.role === 'assistant') {
          msgs[msgs.length - 1] = {
            ...last,
            attachments: (last.attachments || []).some(item => item.id === chunk.attachment!.id)
              ? last.attachments
              : [...(last.attachments || []), chunk.attachment],
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
        const store = useChatStore.getState()
        void Promise.all([store.loadConversations(), store.loadStats()])
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
  } finally {
    deltaBuffer.flush()
  }
}
