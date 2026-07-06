import { create } from 'zustand'
import type { ChatMessage, Conversation, Profile, AppConfig, DocumentInfo, Stats } from '../lib/api'
import { api } from '../lib/api'

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

  // Session
  sessionId: string
  conversations: Conversation[]
  showSidebar: boolean

  // Config
  config: AppConfig | null
  profiles: Profile[]
  selectedProfile: string

  // Toggles
  useThinking: boolean
  useRag: boolean

  // WebSocket
  wsConnected: boolean
  wsReconnecting: boolean

  // Documents
  documents: DocumentInfo[]

  // Stats
  stats: Stats | null

  // Actions
  sendMessage: (content: string) => Promise<void>
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
  setUseThinking: (v: boolean) => void
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

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  lastMetrics: null,
  route: null,
  sessionId: 'default',
  conversations: [],
  showSidebar: false,
  config: null,
  profiles: [],
  selectedProfile: 'zen-free',
  useThinking: true,
  useRag: true,
  wsConnected: false,
  wsReconnecting: false,
  documents: [],
  stats: null,

  setWsConnected: (v) => set({ wsConnected: v }),
  setWsReconnecting: (v) => set({ wsReconnecting: v }),
  setUseThinking: (v) => set({ useThinking: v }),
  setUseRag: (v) => set({ useRag: v }),

  sendMessage: async (content: string) => {
    const { isLoading, sessionId, useThinking, useRag, wsConnected } = get()
    if (!content.trim() || isLoading) return

    const userMsg = createUserMsg(content)
    const assistantMsg = createAssistantMsg()

    set(s => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isLoading: true,
      error: null,
      lastMetrics: null,
      route: null,
    }))

    try {
      // Tenta via WebSocket primeiro
      if (wsConnected) {
        // O WebSocket vai chamar os handlers que atualizam o estado
        // Isso é gerenciado pelo App.tsx via WebSocketProvider
        // Por enquanto, fallback para HTTP SSE
        await httpStream(content, sessionId, useRag, useThinking)
      } else {
        await httpStream(content, sessionId, useRag, useThinking)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro desconhecido'
      set(s => ({
        messages: s.messages.map((m, i) =>
          i === s.messages.length - 1 && m.role === 'assistant'
            ? { ...m, content: m.content || `❌ **Erro:** ${msg}` }
            : m,
        ),
        error: msg,
      }))
    } finally {
      set({ isLoading: false })
    }
  },

  regenerate: async () => {
    const { messages, sessionId, isLoading } = get()
    if (messages.length < 2 || isLoading) return

    const lastUser = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUser) return
    if (messages[messages.length - 1]?.role !== 'assistant') return

    const withoutLast = messages.slice(0, -1)
    const newAssistant = createAssistantMsg()
    set({ messages: [...withoutLast, newAssistant], isLoading: true, lastMetrics: null })

    try {
      await httpStream(lastUser.content, sessionId)
    } catch {
      set({ isLoading: false, error: 'Falha ao regenerar' })
    } finally {
      set({ isLoading: false })
    }
  },

  stopGeneration: () => {
    set({ isLoading: false })
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

  clearMessages: () => set({ messages: [], error: null }),

  setSession: async (id: string) => {
    set({ sessionId: id, messages: [], isLoading: true })
    try {
      const conv = await api.getConversation(id)
      if (conv?.messages) {
        const msgs: ChatMessage[] = conv.messages.map((m: any) => ({
          id: `msg-${m.id}`,
          role: m.role,
          content: m.content,
          timestamp: new Date(m.created_at),
          messageId: m.id,
          feedbackScore: m.feedback_score,
          reasoning: m.reasoning || '',
          providerId: m.provider_id,
          providerName: m.provider_name,
          modelId: m.model_id,
          modelName: m.model_name,
        }))
        set({ messages: msgs })
      }
    } catch {
      // ok
    } finally {
      set({ isLoading: false })
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

// ─── HTTP SSE Streaming (fallback / principal) ───
async function httpStream(
  content: string,
  sessionId: string,
  useRag = false,
  _useThinking = true,
) {
  for await (const chunk of api.stream(content, sessionId, useRag)) {
    if (chunk.type === 'reasoning') {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, reasoning: (last.reasoning || '') + (chunk.text || '') }
        useChatStore.setState({ messages: msgs })
      }
    } else if (chunk.type === 'content') {
      const s = useChatStore.getState()
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + (chunk.text || '') }
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
      if (route) useChatStore.setState({ route })
    } else if (chunk.type === 'status') {
      // status updates could be shown in UI
    }
  }
}
