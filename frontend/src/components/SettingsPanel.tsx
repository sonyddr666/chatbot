import { useState, useEffect, useCallback } from 'react'
import { X, Sun, Moon, Brain, Zap, BarChart3, Server, Cpu, Radio, MessageCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, getAuthToken, type PreferenceSuggestionInfo, type ReasoningEffort } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

const API = '/api/v1'

function authHeaders(): HeadersInit {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

interface ModelInfo {
  id: string
  name: string
  context_length: number
  enabled: boolean
  active?: boolean
}

interface ProviderInfo {
  id: string
  name: string
  provider_type: string
  enabled: boolean
  active: boolean
  active_model_id?: string | null
  models: ModelInfo[]
}

export function SettingsPanel({ open, onClose }: Props) {
  const {
    config, loadConfig,
    responseMode, setResponseMode, reasoningEffort, setReasoningEffort, useRag, setUseRag,
    lastMetrics, route, wsConnected,
  } = useChatStore()

  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved) return saved === 'dark'
    return document.documentElement.classList.contains('dark')
  })
  const [activeProvider, setActiveProvider] = useState<ProviderInfo | null>(null)
  const [activeModel, setActiveModel] = useState<ModelInfo | null>(null)
  const [answerTone, setAnswerTone] = useState('direto')
  const [answerDetail, setAnswerDetail] = useState('pratico')
  const [ragAggressiveness, setRagAggressiveness] = useState('balanced')
  const [preferenceSuggestions, setPreferenceSuggestions] = useState<PreferenceSuggestionInfo[]>([])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme)
    localStorage.setItem('theme', theme ? 'dark' : 'light')
  }, [theme])

  useEffect(() => {
    if (config) {
      setUseRag(config.rag)
    }
  }, [config, setUseRag])

  useEffect(() => {
    if (open) loadConfig()
  }, [open, loadConfig])

  const loadPreferences = useCallback(async () => {
    try {
      const data = await api.listPreferences()
      const answerStyle = data.preferences.answer_style?.value
      if (isAnswerStyle(answerStyle)) {
        setAnswerTone(String(answerStyle.tone || 'direto'))
        setAnswerDetail(String(answerStyle.detail || 'pratico'))
      }
      const rag = data.preferences.rag_aggressiveness?.value
      if (typeof rag === 'string') setRagAggressiveness(rag)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar preferencias')
    }
  }, [])

  const loadPreferenceSuggestions = useCallback(async () => {
    try {
      const data = await api.listPreferenceSuggestions()
      setPreferenceSuggestions(data.suggestions)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar sugestoes')
    }
  }, [])

  const savePreferences = async () => {
    try {
      await Promise.all([
        api.setPreference('answer_style', { tone: answerTone, detail: answerDetail }),
        api.setPreference('rag_aggressiveness', ragAggressiveness),
      ])
      toast.success('Preferencias salvas')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao salvar preferencias')
    }
  }

  const resolvePreferenceSuggestion = async (suggestion: PreferenceSuggestionInfo, accept: boolean) => {
    try {
      await api.resolvePreferenceSuggestion(suggestion.id, accept)
      toast.success(accept ? 'Sugestao aceita' : 'Sugestao rejeitada')
      await loadPreferenceSuggestions()
      if (accept) await loadPreferences()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao resolver sugestao')
    }
  }

  // Busca provider ativo
  const fetchActiveProvider = useCallback(async () => {
    try {
      const r = await fetch(`${API}/providers/manage`, { headers: authHeaders() })
      const data: ProviderInfo[] = await r.json()
      const active = data.find(p => p.active) || null
      setActiveProvider(active)
      setActiveModel(active?.models.find(m => m.active) || null)
    } catch {}
  }, [])

  useEffect(() => {
    if (open) {
      fetchActiveProvider()
      loadPreferences()
      loadPreferenceSuggestions()
    }
  }, [open, fetchActiveProvider, loadPreferences, loadPreferenceSuggestions])

  // Escuta mudanças externas
  useEffect(() => {
    const refresh = () => fetchActiveProvider()
    window.addEventListener('provider-changed', refresh)
    return () => window.removeEventListener('provider-changed', refresh)
  }, [fetchActiveProvider])

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-50" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-50 h-full w-full shadow-lg animate-slide-in sm:w-80"
        style={{ background: 'var(--bg-primary)', borderLeft: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            Configurações
          </h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors">
            <X size={18} style={{ color: 'var(--text-secondary)' }} />
          </button>
        </div>

        <div className="p-4 space-y-5 overflow-y-auto h-[calc(100%-60px)]">
          {/* Modelo Ativo (via Provider Manager) */}
          <div>
            <label className="text-sm font-medium mb-1.5 block" style={{ color: 'var(--text-primary)' }}>
              Modelo Ativo
            </label>
            <div
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
              }}
            >
              <Cpu size={18} style={{ color: 'var(--accent)' }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                  {activeModel?.name || activeProvider?.name || 'Nenhum'}
                </p>
                <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                  {activeProvider?.name || ''}
                  {activeModel?.context_length ? ` · ${fmtCtx(activeModel.context_length)}` : ''}
                </p>
              </div>
              {activeModel && (
                <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>
                  {activeModel.id}
                </span>
              )}
            </div>
            <button
              onClick={() => {
                onClose()
                window.dispatchEvent(new CustomEvent('open-provider-manager'))
              }}
              className="w-full mt-2 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all hover:opacity-90"
              style={{ background: 'var(--accent)', color: '#fff' }}
            >
              <Server size={12} />
              Abrir gerenciador de providers
            </button>
          </div>

          {/* Tema */}
          <div>
            <label className="text-sm font-medium mb-1.5 block" style={{ color: 'var(--text-primary)' }}>Tema</label>
            <div className="flex gap-2">
              {[
                { id: false as const, label: 'Claro', icon: Sun },
                { id: true as const, label: 'Escuro', icon: Moon },
              ].map(t => (
                <button
                  key={String(t.id)}
                  onClick={() => setTheme(t.id)}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm transition-all"
                  style={{
                    background: theme === t.id ? 'var(--accent)' : 'var(--bg-secondary)',
                    color: theme === t.id ? '#fff' : 'var(--text-primary)',
                    border: theme === t.id ? 'none' : '1px solid var(--border)',
                  }}
                >
                  <t.icon size={16} /> {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Preferencias pessoais */}
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: 'var(--text-primary)' }}>
              Preferencias pessoais
            </label>
            <div className="space-y-2">
              <input
                value={answerTone}
                onChange={event => setAnswerTone(event.target.value)}
                placeholder="Tom: direto, professor, criativo..."
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              />
              <input
                value={answerDetail}
                onChange={event => setAnswerDetail(event.target.value)}
                placeholder="Detalhe: pratico, detalhado..."
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              />
              <select
                value={ragAggressiveness}
                onChange={event => setRagAggressiveness(event.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="low">RAG leve</option>
                <option value="balanced">RAG equilibrado</option>
                <option value="high">RAG forte</option>
              </select>
              <button
                onClick={savePreferences}
                className="w-full rounded-lg px-3 py-2 text-xs font-bold"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                Salvar preferencias
              </button>
            </div>
          </div>

          {preferenceSuggestions.length > 0 && (
            <div>
              <label className="text-sm font-medium mb-2 block" style={{ color: 'var(--text-primary)' }}>
                Sugestoes inteligentes
              </label>
              <div className="space-y-2">
                {preferenceSuggestions.map(suggestion => (
                  <div
                    key={suggestion.id}
                    className="rounded-xl border p-3"
                    style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--accent)' }}>
                        {preferenceLabel(suggestion.suggestion_type)}
                      </p>
                      <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                        {Math.round(suggestion.confidence * 100)}%
                      </span>
                    </div>
                    <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {suggestion.reason}
                    </p>
                    <p className="mt-2 rounded-lg px-2 py-1 text-[11px]" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                      {formatSuggestionValue(suggestion.suggested_value)}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => resolvePreferenceSuggestion(suggestion, true)}
                        className="flex-1 rounded-lg px-2 py-1.5 text-xs font-bold"
                        style={{ background: 'var(--accent)', color: '#fff' }}
                      >
                        Aceitar
                      </button>
                      <button
                        onClick={() => resolvePreferenceSuggestion(suggestion, false)}
                        className="flex-1 rounded-lg border px-2 py-1.5 text-xs font-bold"
                        style={{ background: 'transparent', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                      >
                        Rejeitar
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ─── TOGGLES: Thinking + RAG ─── */}
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: 'var(--text-primary)' }}>
              Otimização
            </label>
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: 'normal', label: 'Normal', detail: 'Equilibrado', icon: MessageCircle },
                  { id: 'thinking', label: 'Pensando', detail: 'Mais analise', icon: Brain },
                  { id: 'live', label: 'Live', detail: 'Baixa latencia', icon: Radio },
                ] as const).map(mode => {
                  const Icon = mode.icon
                  const selected = responseMode === mode.id
                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => {
                        setResponseMode(mode.id)
                        toast.success(`Modo ${mode.label} selecionado`)
                      }}
                      className="rounded-xl border px-2 py-3 text-center transition-all"
                      style={{
                        background: selected ? 'var(--accent-light)' : 'var(--bg-secondary)',
                        borderColor: selected ? 'var(--accent)' : 'var(--border)',
                      }}
                    >
                      <Icon size={18} className="mx-auto mb-1.5" style={{ color: selected ? 'var(--accent)' : 'var(--text-tertiary)' }} />
                      <span className="block text-xs font-bold" style={{ color: 'var(--text-primary)' }}>{mode.label}</span>
                      <span className="mt-0.5 block text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{mode.detail}</span>
                    </button>
                  )
                })}
              </div>

              <div className="rounded-xl border p-3" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Esforco do modelo</p>
                    <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Mais esforco aumenta qualidade, latencia e consumo.</p>
                  </div>
                  <Brain size={18} style={{ color: 'var(--accent)' }} />
                </div>
                <select
                  value={reasoningEffort}
                  onChange={event => setReasoningEffort(event.target.value as ReasoningEffort)}
                  className="w-full rounded-lg border px-3 py-2 text-sm font-semibold outline-none"
                  style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                >
                  <option value="low">Leve</option>
                  <option value="medium">Medio</option>
                  <option value="high">Alto</option>
                  <option value="xhigh">Extra alto</option>
                  <option value="max">Maximo (usa o teto xhigh do Codex)</option>
                </select>
              </div>

              {/* RAG toggle */}
              <button
                onClick={() => {
                  setUseRag(!useRag)
                  toast.success(`RAG ${useRag ? 'desligado' : 'ligado'}`)
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
                style={{
                  background: useRag ? 'var(--accent-light)' : 'var(--bg-secondary)',
                  border: `1px solid ${useRag ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                <Zap size={18} style={{ color: useRag ? 'var(--accent)' : 'var(--text-tertiary)' }} />
                <div className="text-left flex-1">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    RAG (Base de Conhecimento)
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {useRag ? 'Ligado — consulta documentos' : 'Desligado — apenas conhecimento do modelo'}
                  </p>
                </div>
                <div
                  className="w-10 h-5 rounded-full transition-colors relative"
                  style={{ background: useRag ? 'var(--accent)' : 'var(--border)' }}
                >
                  <div
                    className="w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all shadow-sm"
                    style={{ left: useRag ? '22px' : '2px' }}
                  />
                </div>
              </button>
            </div>
          </div>

          {/* ─── MÉTRICAS DE LATÊNCIA ─── */}
          <div>
            <label className="text-sm font-medium mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-primary)' }}>
              <BarChart3 size={14} /> Métricas da Última Resposta
            </label>
            {lastMetrics ? (
              <div className="space-y-1.5">
                <MetricRow label="Rota" value={route === 'fast' ? '⚡ Rápida' : '🔬 Completa'} color={route === 'fast' ? '#16a34a' : 'var(--accent)'} />
                <MetricRow label="TTFT (primeiro token)" value={`${lastMetrics.ttft_s?.toFixed(2) || '?'}s`} />
                <MetricRow label="Total" value={`${lastMetrics.total_s?.toFixed(2) || '?'}s`} />
                <MetricRow label="Classificação" value={`${lastMetrics.classify_ms || '?'}ms`} />
                <MetricRow label="Moderação" value={`${lastMetrics.moderation_ms || '?'}ms`} />
              </div>
            ) : (
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Envie uma mensagem para ver as métricas.
              </p>
            )}
          </div>

          {/* Status da conexão */}
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-gray-400'}`} />
            {wsConnected ? 'WebSocket conectado' : 'HTTP (fallback)'}
          </div>

          {/* Info */}
          <div className="p-3 rounded-lg text-xs space-y-1" style={{ background: 'var(--bg-secondary)', color: 'var(--text-tertiary)' }}>
            <p>🤖 Chatbot v0.3.0</p>
            <p>⚡ Provider: {activeProvider?.name || config?.provider || '—'}</p>
            <p>🧠 Modelo: {activeModel?.name || config?.model || '—'}</p>
            <p>📦 Vector DB: ChromaDB</p>
            <p>🧠 Modo: {responseMode}</p>
            <p>⚙ Esforco: {reasoningEffort}</p>
            <p>📄 RAG: {useRag ? 'ON' : 'OFF'}</p>
          </div>
        </div>
      </div>
    </>
  )
}

function fmtCtx(n: number): string {
  return n >= 1000000
    ? `${(n / 1000000).toFixed(0)}M`
    : n >= 1000
      ? `${(n / 1000).toFixed(0)}K`
      : String(n)
}

function isAnswerStyle(value: unknown): value is { tone?: unknown; detail?: unknown } {
  return typeof value === 'object' && value !== null
}

function preferenceLabel(type: string): string {
  const labels: Record<string, string> = {
    answer_style: 'Estilo de resposta',
    default_language: 'Idioma padrao',
    rag_aggressiveness: 'Uso do RAG',
  }
  return labels[type] || type
}

function formatSuggestionValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return 'Valor sugerido'
  }
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between px-2 py-1 rounded text-xs" style={{ background: 'var(--bg-secondary)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className="font-mono font-medium" style={{ color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}
