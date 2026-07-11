const API = '/api/v1'

const TOKEN_KEY = 'chatbot_auth_token'

export function getAuthToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setAuthToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getAuthToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

export interface Profile {
  id: string; name: string; model: string; provider: string; active: boolean
}
export interface SkillSource {
  label: string
  url: string
}
export interface SkillActivity {
  name: string
  status: 'completed' | 'failed' | 'running'
  label: string
  source_count: number
  sources: SkillSource[]
}
export interface ChatMessage {
  id: string; role: 'user' | 'assistant'; content: string; timestamp: Date
  messageId?: number; feedbackScore?: number | null; tokens?: number
  reasoning?: string // pensamento interno do modelo
  providerId?: string | null
  providerName?: string | null
  modelId?: string | null
  modelName?: string | null
  workspacePlan?: WorkspaceActionPlan
  skillActivities?: SkillActivity[]
}
export interface Conversation {
  id: number; session_id: string; title: string; language: string
  message_count: number; created_at: string; updated_at: string
}

export function parseApiTimestamp(value: string | Date) {
  if (value instanceof Date) return value
  const raw = String(value || '').trim()
  if (!raw) return new Date(Number.NaN)
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)
  return new Date(hasTimezone ? raw : `${raw}Z`)
}
export interface DocumentInfo {
  id: number
  filename: string
  source: string
  chunks: number
  size: number
  upload_path?: string | null
  extracted_path?: string | null
  checksum?: string | null
  status?: string
  parser?: string | null
  error_message?: string | null
  manifest_path?: string | null
  created_at: string
}
export interface Stats {
  total_messages: number; total_conversations: number
  likes: number; dislikes: number; satisfaction_rate: number
}
export interface AppConfig {
  provider: string; profile: string; model: string
  model_id?: string; provider_id?: string
  moderation: boolean; multilang: boolean; rag: boolean; max_upload_mb: number
}

export interface UserInfo {
  id: number
  email: string
  username: string
  display_name: string
  is_admin: boolean
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface RegistrationResponse {
  status: 'pending'
  message: string
}

export interface RegistrationStatus {
  enabled: boolean
  approval_required: boolean
}

export interface AdminUserInfo {
  id: number
  email: string
  username: string
  display_name: string
  is_admin: boolean
  is_active: boolean
  registration_status: 'pending' | 'approved' | 'rejected'
  created_at: string
  approved_at?: string | null
  approved_by?: number | null
}

export interface SkillInfo {
  id: number
  name: string
  description: string
  kind: string
  definition: Record<string, unknown>
  requires_network: boolean
  requires_shell: boolean
  risk_level: number
  enabled: boolean
  config?: Record<string, unknown>
}

export interface SkillRunInfo {
  id: number
  user_id: number
  skill_name: string
  status: string
  input_json: string
  output_summary: string
  error_message: string
  started_at: string | null
  finished_at: string | null
}

export interface PerplexoStatus {
  skill: string
  configured: boolean
  base_url: string
  timeout_seconds: number
  online?: boolean
  status_code?: number
}

export interface InworldVoice {
  voice_id: string
  display_name: string
  language: string
  description: string
  source: string
  is_cloned: boolean
  is_custom: boolean
  tags: string[]
}

export interface InworldVoicesResponse {
  configured: boolean
  provider: 'inworld'
  model: string
  default_voice: string
  voices: InworldVoice[]
  cloned_count: number
}

export interface InworldTtsStatus {
  configured: boolean
  provider: 'inworld'
  model: string
  default_voice: string
}

export interface UserPreferenceInfo {
  value: unknown
  source: string
  confidence: number
  updated_at: string | null
}

export interface PreferenceSuggestionInfo {
  id: number
  user_id: number
  suggestion_type: string
  current_value: unknown
  suggested_value: unknown
  reason: string
  confidence: number
  status: string
  created_at: string | null
  resolved_at: string | null
}

export interface UserProviderInfo {
  id: number
  user_id: number
  provider_id: string
  display_name: string
  base_url: string
  model: string
  api_format: string
  is_enabled: boolean
  is_default: boolean
  has_key: boolean
  key_masked: string
  created_at: string | null
  updated_at: string | null
}

export interface WorkspaceNode {
  name: string
  path: string
  kind: 'file' | 'folder'
  size: number
}

export interface WorkspaceTree {
  path: string
  nodes: WorkspaceNode[]
}

export interface WorkspaceFile {
  path: string
  content: string
}

export interface WorkspaceInfo {
  name: string
  path: string
  kind: 'file' | 'folder'
  size: number
}

export interface WorkspacePatchPreview {
  path: string
  expected_checksum: string
  new_checksum: string
  diff: string
}

export interface WorkspacePatchApplyResult {
  path: string
  applied: boolean
  checksum: string
  snapshot_path: string
}

export type WorkspaceActionOperation = 'mkdir' | 'write_file' | 'move' | 'delete'

export interface WorkspaceAction {
  operation: WorkspaceActionOperation
  path?: string
  source?: string
  target?: string
  mode?: 'create' | 'edit'
  recursive?: boolean
  diff?: string
  content?: string
  exists?: boolean
}

export interface WorkspaceActionPlan {
  id: string
  instruction: string
  summary: string
  status: 'pending' | 'applied' | 'cancelled' | 'failed' | 'expired'
  actions: WorkspaceAction[]
  created_at: string
  expires_at: string
  applied_at?: string
  cancelled_at?: string
  error?: string
}

/** Chunk do streaming SSE */
export interface StreamChunk {
  type: 'content' | 'reasoning' | 'done' | 'start' | 'status' | 'workspace_plan' | 'skill_activity'
  text?: string
  messageId?: number
  hasReasoning?: boolean
  route?: 'fast' | 'full'
  sessionId?: string
  providerId?: string
  providerName?: string
  modelId?: string
  modelName?: string
  workspacePlan?: WorkspaceActionPlan
  skillActivity?: SkillActivity
  metrics?: {
    ttft_s?: number
    total_s?: number
    route?: 'fast' | 'full'
    classify_ms?: number
    moderation_ms?: number
  }
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(API + url, {
    headers: authHeaders({ 'Content-Type': 'application/json', ...opts?.headers }),
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(err.detail || err.message || `Erro ${res.status}`)
  }
  return res.json()
}

export const api = {
  setToken: setAuthToken,
  getToken: getAuthToken,

  // Auth
  registrationStatus: () => req<RegistrationStatus>('/auth/registration-status'),
  register: (body: { email: string; username: string; password: string; display_name?: string }) =>
    req<RegistrationResponse>('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: { login: string; password: string }) =>
    req<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => req<UserInfo>('/auth/me'),
  logout: () => setAuthToken(''),
  adminListUsers: (status: 'all' | 'pending' | 'approved' | 'rejected' = 'all') =>
    req<AdminUserInfo[]>(`/admin/users?status=${status}`),
  adminApproveUser: (userId: number) =>
    req<AdminUserInfo>(`/admin/users/${userId}/approve`, { method: 'POST' }),
  adminRejectUser: (userId: number) =>
    req<AdminUserInfo>(`/admin/users/${userId}/reject`, { method: 'POST' }),
  adminDeleteRegistration: (userId: number) =>
    req<{ status: string; user_id: number }>(`/admin/users/${userId}`, { method: 'DELETE' }),
  onboarding: (body: {
    display_name?: string
    language?: string
    timezone?: string
    role?: string
    technical_level?: string
    preferred_tone?: string
    goals?: string[]
    avoid?: string[]
    memory_policy?: string
    extra?: Record<string, unknown>
  }) => req<any>('/onboarding', { method: 'POST', body: JSON.stringify(body) }),
  listSkills: () => req<SkillInfo[]>('/skills'),
  listSkillRuns: (limit = 10) =>
    req<{ runs: SkillRunInfo[] }>(`/skills/runs?limit=${limit}`),
  toggleSkill: (name: string, enabled: boolean, config?: Record<string, unknown>) =>
    req<any>(`/skills/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled, config }),
    }),
  getPerplexoStatus: () => req<PerplexoStatus>('/skills/perplexo/status'),
  testPerplexo: () => req<PerplexoStatus>('/skills/perplexo/test', { method: 'POST' }),
  listPreferences: () =>
    req<{ preferences: Record<string, UserPreferenceInfo> }>('/preferences'),
  setPreference: (key: string, value: unknown, source = 'manual', confidence = 1) =>
    req<any>(`/preferences/${encodeURIComponent(key)}`, {
      method: 'PUT',
      body: JSON.stringify({ value, source, confidence }),
    }),
  listPreferenceSuggestions: () =>
    req<{ suggestions: PreferenceSuggestionInfo[] }>('/preference-suggestions'),
  resolvePreferenceSuggestion: (id: number, accept: boolean) =>
    req<{ status: string; suggestion_id: number }>(`/preference-suggestions/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ accept }),
    }),

  // Config
  getConfig: () => req<AppConfig>('/config'),
  getProfiles: () => req<Profile[]>('/profiles'),
  listUserProviders: () =>
    req<{ providers: UserProviderInfo[] }>('/providers/user'),
  createUserProvider: (body: {
    provider_id: string
    display_name?: string
    base_url?: string
    model: string
    api_key?: string
    api_format?: string
    is_default?: boolean
    is_enabled?: boolean
  }) => req<UserProviderInfo>('/providers/user', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  activateUserProvider: (id: number) =>
    req<{ status: string; active_config_id: number }>(`/providers/user/${id}/activate`, {
      method: 'POST',
    }),

  // Chat
  chat: (message: string, sessionId = 'default', useRag = false) =>
    req<{ response: string; reasoning?: string; skill_activities?: SkillActivity[]; session_id: string; message_id?: number; provider_id?: string; provider_name?: string; model_id?: string; model_name?: string; workspace_plan?: WorkspaceActionPlan }>('/chat', {
      method: 'POST', body: JSON.stringify({ message, session_id: sessionId, use_rag: useRag }),
    }),

  /**
   * Streaming SSE — lê o stream do backend e yield chunks com tipo.
   * O backend envia SSE events:
   *   event: reasoning\n data: <text>\n\n
   *   event: token\n data: <text>\n\n
   *   event: done\n data: {"message_id":..., "has_reasoning":...}\n\n
   */
  async *stream(
    message: string,
    sessionId = 'default',
    useRag = false,
    useThinking = true,
    signal?: AbortSignal,
  ): AsyncGenerator<StreamChunk> {
    const res = await fetch(`${API}/chat/stream`, {
      method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ message, session_id: sessionId, use_rag: useRag, use_thinking: useThinking }),
      signal,
    })
    if (!res.ok) throw new Error('Falha no streaming')

    const reader = res.body?.getReader()
    if (!reader) throw new Error('Sem stream')

    const dec = new TextDecoder()
    let buf = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
          continue
        }

        if (line.startsWith('data: ')) {
          const raw = line.slice(6).trim()

          if (raw === '[DONE]') {
            yield { type: 'done' }
            return
          }

          if (currentEvent === 'reasoning') {
            yield { type: 'reasoning', text: raw }
            continue
          }

          if (currentEvent === 'token') {
            yield { type: 'content', text: raw }
            continue
          }

          if (currentEvent === 'workspace_plan') {
            try {
              yield { type: 'workspace_plan', workspacePlan: JSON.parse(raw) }
            } catch {
              throw new Error('Plano de Workspace invalido')
            }
            continue
          }

          if (currentEvent === 'skill_activity') {
            try {
              yield { type: 'skill_activity', skillActivity: JSON.parse(raw) }
            } catch {
              throw new Error('Atividade de Skill invalida')
            }
            continue
          }

          if (currentEvent === 'done') {
            try {
              const p = JSON.parse(raw)
              yield {
                type: 'done',
                messageId: p.message_id,
                hasReasoning: p.has_reasoning,
                providerId: p.provider_id,
                providerName: p.provider_name,
                modelId: p.model_id,
                modelName: p.model_name,
              }
            } catch {
              yield { type: 'done' }
            }
            return
          }

          if (currentEvent === 'start') {
            try {
              const p = JSON.parse(raw)
              yield {
                type: 'start',
                sessionId: p.session_id,
                route: p.route,
                providerId: p.provider_id,
                providerName: p.provider_name,
                modelId: p.model_id,
                modelName: p.model_name,
              }
            } catch {
              yield { type: 'start' }
            }
            continue
          }

          if (currentEvent === 'status') {
            yield { type: 'status', text: raw }
            continue
          }

          if (currentEvent === 'error') {
            throw new Error(raw)
          }

          // Fallback: tenta parsear como JSON autônomo
          try {
            const p = JSON.parse(raw)
            if (p.token) yield { type: 'content', text: p.token }
            else if (p.reasoning) yield { type: 'reasoning', text: p.reasoning }
            else if (p.content) yield { type: 'content', text: p.content }
            else if (raw) yield { type: 'content', text: raw }
          } catch {
            if (raw) yield { type: 'content', text: raw }
          }
        }
      }
    }
  },

  // Conversations
  listConversations: () => req<Conversation[]>('/conversations'),
  getConversation: (id: string) => req<any>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    req<any>(`/conversations/${id}/title?title=${encodeURIComponent(title)}`, { method: 'PUT' }),
  deleteConversation: (id: string) =>
    req<any>(`/conversations/${id}`, { method: 'DELETE' }),

  // Feedback
  feedback: (messageId: number, score: number) =>
    req<any>('/feedback', { method: 'POST', body: JSON.stringify({ message_id: messageId, score }) }),

  // Documents
  listDocuments: () => req<DocumentInfo[]>('/documents'),
  async uploadDocument(file: File): Promise<{ filename: string; chunks: number }> {
    const fd = new FormData(); fd.append('file', file)
    const res = await fetch(`${API}/upload`, { method: 'POST', headers: authHeaders(), body: fd })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed')
    return res.json()
  },
  async uploadOriginalDocument(file: File): Promise<{ document_id: number; filename: string; status: string; chunks: number }> {
    const fd = new FormData(); fd.append('file', file)
    const res = await fetch(`${API}/documents/upload`, { method: 'POST', headers: authHeaders(), body: fd })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed')
    return res.json()
  },
  ingestDocument: (id: number) =>
    req<{ document_id: number; filename: string; status: string; chunks: number }>(`/documents/${id}/ingest`, {
      method: 'POST',
    }),
  deleteDocument: (id: number) => req<any>(`/documents/${id}`, { method: 'DELETE' }),
  getDocumentManifest: (id: number) => req<Record<string, unknown>>(`/documents/${id}/manifest`),

  // Workspace
  workspaceTree: (path = '') =>
    req<WorkspaceTree>(`/workspace/tree?path=${encodeURIComponent(path)}`),
  workspaceReadFile: (path: string) =>
    req<WorkspaceFile>(`/workspace/file?path=${encodeURIComponent(path)}`),
  workspaceWriteFile: (path: string, content: string) =>
    req<WorkspaceInfo>('/workspace/file', {
      method: 'PUT',
      body: JSON.stringify({ path, content }),
    }),
  workspaceMkdir: (path: string) =>
    req<WorkspaceInfo>('/workspace/mkdir', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  workspaceDeletePath: (path: string, recursive = false) =>
    req<{ deleted: boolean; path: string }>(`/workspace/path?path=${encodeURIComponent(path)}&recursive=${recursive}`, { method: 'DELETE' }),
  workspaceMovePath: (source: string, target: string) =>
    req<WorkspaceInfo>('/workspace/move', {
      method: 'POST',
      body: JSON.stringify({ source, target }),
    }),
  workspacePatchPreview: (path: string, content: string) =>
    req<WorkspacePatchPreview>('/workspace/patch/preview', {
      method: 'POST',
      body: JSON.stringify({ path, content }),
    }),
  workspacePatchApply: (path: string, content: string, expectedChecksum: string) =>
    req<WorkspacePatchApplyResult>('/workspace/patch/apply', {
      method: 'POST',
      body: JSON.stringify({ path, content, expected_checksum: expectedChecksum }),
    }),
  workspaceAiPlan: (instruction: string) =>
    req<WorkspaceActionPlan>('/workspace/ai/plan', {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),
  workspaceAiGetPlan: (planId: string) =>
    req<WorkspaceActionPlan>(`/workspace/ai/plans/${planId}`),
  workspaceAiApplyPlan: (planId: string) =>
    req<WorkspaceActionPlan>(`/workspace/ai/plans/${planId}/apply`, { method: 'POST' }),
  workspaceAiCancelPlan: (planId: string) =>
    req<WorkspaceActionPlan>(`/workspace/ai/plans/${planId}`, { method: 'DELETE' }),
  workspaceRagIngest: (path: string) =>
    req<{ document_id: number; path: string; status: string; chunks: number }>('/workspace/rag/ingest', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),

  inworldTtsStatus: () => req<InworldTtsStatus>('/tts/inworld/status'),
  listInworldVoices: (language = 'PT_BR', includeSystem = true) =>
    req<InworldVoicesResponse>(
      `/tts/inworld/voices?language=${encodeURIComponent(language)}&include_system=${includeSystem ? 'true' : 'false'}`,
    ),
  synthesizeInworldSpeech: async (
    text: string,
    voiceId: string,
    language = 'pt-BR',
    deliveryMode = 'BALANCED',
    signal?: AbortSignal,
  ) => {
    const res = await fetch(`${API}/tts/inworld/synthesize`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        text,
        voice_id: voiceId,
        language,
        delivery_mode: deliveryMode,
      }),
      signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(err.detail || `Falha no TTS Inworld (${res.status})`)
    }
    return res.blob()
  },

  // Stats
  getStats: () => req<Stats>('/stats'),

  // Export
  exportConversation: async (sessionId: string, format = 'txt') => {
    const res = await fetch(`${API}/export/${sessionId}?format=${format}`, { headers: authHeaders() })
    if (!res.ok) throw new Error('Export failed')
    return res.text()
  },
}
