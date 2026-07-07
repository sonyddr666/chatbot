import { useState, useEffect, useCallback } from 'react'
import { X, Sun, Moon, Brain, Zap, BarChart3, Server, Cpu } from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, getAuthToken } from '../lib/api'

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
    useThinking, setUseThinking, useRag, setUseRag,
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

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme)
    localStorage.setItem('theme', theme ? 'dark' : 'light')
  }, [theme])

  useEffect(() => {
    if (config) {
      setUseRag(config.rag)
      setUseThinking(true)
    }
  }, [config, setUseRag, setUseThinking])

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
    }
  }, [open, fetchActiveProvider, loadPreferences])

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
        className="fixed right-0 top-0 h-full w-80 z-50 shadow-lg animate-slide-in"
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

          {/* ─── TOGGLES: Thinking + RAG ─── */}
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: 'var(--text-primary)' }}>
              Otimização
            </label>
            <div className="space-y-2">
              {/* Thinking toggle */}
              <button
                onClick={() => {
                  setUseThinking(!useThinking)
                  toast.success(`Modo raciocínio ${useThinking ? 'desligado' : 'ligado'}`)
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
                style={{
                  background: useThinking ? 'var(--accent-light)' : 'var(--bg-secondary)',
                  border: `1px solid ${useThinking ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                <Brain size={18} style={{ color: useThinking ? 'var(--accent)' : 'var(--text-tertiary)' }} />
                <div className="text-left flex-1">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Raciocínio (Thinking)
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {useThinking ? 'Ligado — modelo pensa antes de responder' : 'Desligado — resposta mais rápida'}
                  </p>
                </div>
                <div
                  className="w-10 h-5 rounded-full transition-colors relative"
                  style={{ background: useThinking ? 'var(--accent)' : 'var(--border)' }}
                >
                  <div
                    className="w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all shadow-sm"
                    style={{ left: useThinking ? '22px' : '2px' }}
                  />
                </div>
              </button>

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
            <p>🧠 Thinking: {useThinking ? 'ON' : 'OFF'}</p>
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

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between px-2 py-1 rounded text-xs" style={{ background: 'var(--bg-secondary)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className="font-mono font-medium" style={{ color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}
