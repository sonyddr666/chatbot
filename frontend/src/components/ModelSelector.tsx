import { useState, useEffect, useRef, useCallback } from 'react'
import { ChevronDown, Cpu, Server, Settings, AlertCircle } from 'lucide-react'
import { useChatStore } from '../hooks/useChatStore'

// ─── Tipos ──────────────────────────────────────────────────────────

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
  base_url: string
  api_format: string
  provider_type: 'builtin' | 'custom'
  enabled: boolean
  active: boolean
  active_model_id?: string | null
  models: ModelInfo[]
}

const API = '/api/v1'

// ─── Helpers ────────────────────────────────────────────────────────

function fmtCtx(n: number): string {
  return n >= 1000000
    ? `${(n / 1000000).toFixed(0)}M`
    : n >= 1000
      ? `${(n / 1000).toFixed(0)}K`
      : String(n)
}

// ─── Componente ─────────────────────────────────────────────────────

export function ModelSelector() {
  const { loadConfig } = useChatStore()
  const [open, setOpen] = useState(false)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fecha ao clicar fora
  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // Busca providers ao abrir (sempre dados frescos)
  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    fetch(`${API}/providers/manage`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setProviders(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [open])

  // Também recarrega quando algum evento de mudança externa acontece
  // (ex: usuário fecha o provider manager)
  useEffect(() => {
    const refresh = () => {
      if (!open) {
        fetch(`${API}/providers/manage`)
          .then(r => r.json())
          .then(data => setProviders(data))
          .catch(() => {})
      }
    }
    window.addEventListener('provider-changed', refresh)
    return () => window.removeEventListener('provider-changed', refresh)
  }, [open])

  // Selecionar modelo — com optimistic update
  const handleSelect = useCallback(async (providerId: string, modelId: string) => {
    // Optimistic: já atualiza local pra feedback instantâneo
    setProviders(prev => prev.map(p => ({
      ...p,
      active: p.id === providerId,
      active_model_id: p.id === providerId ? modelId : null,
      models: p.models.map(m => ({
        ...m,
        active: p.id === providerId && m.id === modelId,
      })),
    })))
    setOpen(false)

    // Se for outro provider, ativa primeiro
    const provider = providers.find(p => p.id === providerId)
    if (!provider?.active) {
      try {
        const r = await fetch(`${API}/providers/manage/${providerId}/activate`, { method: 'POST' })
        if (!r.ok) throw new Error('Falha ao ativar provider')
      } catch {
        // Reverte optimistic update? Não por enquanto
        return
      }
    }

    // Ativa o modelo
    try {
      const r = await fetch(`${API}/providers/activate-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
      })
      if (!r.ok) throw new Error('Falha ao ativar modelo')
      loadConfig()
      // Dispara evento pra outros componentes saberem
      window.dispatchEvent(new CustomEvent('provider-changed'))
    } catch {
      // silent
    }
  }, [providers, loadConfig])

  // Provider ativo + modelo ativo
  const selectableProviders = providers
    .filter(p => p.enabled)
    .map(p => ({ ...p, models: p.models.filter(m => m.enabled) }))
    .filter(p => p.models.length > 0)

  const activeProvider = selectableProviders.find(p => p.active)
  const activeModel = activeProvider?.models.find(m => m.active) || activeProvider?.models[0]

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Botão do seletor */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm font-medium transition-all hover:opacity-90"
        style={{
          background: 'var(--accent-light)',
          color: 'var(--accent)',
          border: '1px solid transparent',
        }}
        title={
          activeProvider && activeModel
            ? `${activeProvider.name} › ${activeModel.name}`
            : 'Selecionar modelo'
        }
      >
        <Cpu size={14} />
        <span className="max-w-[160px] truncate flex items-center gap-1">
          {activeProvider && activeModel ? (
            <>
              <span className="opacity-60 font-normal text-xs">
                {activeProvider.name.replace('OpenCode ', '')}
              </span>
              <span>{activeModel.name}</span>
            </>
          ) : (
            'Selecionar modelo'
          )}
        </span>
        <ChevronDown size={14} className={`transition-transform flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute top-full right-0 mt-1 w-80 max-h-96 overflow-y-auto rounded-xl border shadow-lg z-50"
          style={{
            background: 'var(--bg-primary)',
            borderColor: 'var(--border)',
          }}
        >
          {/* Loading / Error */}
          {loading && (
            <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
              Carregando...
            </div>
          )}
          {error && !loading && (
            <div className="px-4 py-8 text-center text-sm flex items-center justify-center gap-2" style={{ color: '#dc2626' }}>
              <AlertCircle size={14} />
              Erro ao carregar
            </div>
          )}

          {/* Lista de providers */}
          {!loading && !error && selectableProviders.length === 0 && (
            <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
              Nenhum provider disponível
            </div>
          )}

          {!loading && !error && selectableProviders
            .map(provider => (
              <div key={provider.id}>
                {/* ─── Header do Provedor ─── */}
                <div
                  className="flex items-center gap-2 px-4 py-2.5 border-b sticky top-0"
                  style={{
                    background: 'var(--bg-secondary)',
                    borderColor: 'var(--border)',
                  }}
                >
                  <Server size={14} style={{ color: provider.active ? 'var(--accent)' : 'var(--text-tertiary)' }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-sm font-semibold truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {provider.name}
                      </span>
                      {provider.active && (
                        <span
                          className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                          style={{ background: '#dcfce7', color: '#16a34a' }}
                        >
                          ATIVO
                        </span>
                      )}
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      {provider.models.length} modelo{provider.models.length !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>

                {/* Modelos */}
                {provider.models
                    .map(model => (
                      <button
                        key={model.id}
                        onClick={() => handleSelect(provider.id, model.id)}
                        className="flex items-center gap-3 w-full px-4 py-2.5 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5"
                        style={{
                          background: model.active ? 'var(--accent-light)' : 'transparent',
                          borderLeft: model.active ? '3px solid var(--accent)' : '3px solid transparent',
                        }}
                      >
                        <Cpu size={16} style={{ color: model.active ? 'var(--accent)' : 'var(--text-tertiary)' }} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p
                              className="text-sm font-medium truncate"
                              style={{ color: model.active ? 'var(--accent)' : 'var(--text-primary)' }}
                            >
                              {model.name}
                            </p>
                            {model.active && (
                              <span
                                className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                                style={{ background: '#dcfce7', color: '#16a34a' }}
                              >
                                ATIVO
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-mono truncate" style={{ color: 'var(--text-tertiary)' }}>
                            {model.id}
                          </p>
                        </div>
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded font-mono flex-shrink-0"
                          style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
                        >
                          {fmtCtx(model.context_length)}
                        </span>
                      </button>
                    ))}
              </div>
            ))}

          {/* Link para gerenciar */}
          <div
            className="sticky bottom-0 border-t px-4 py-2"
            style={{
              background: 'var(--bg-primary)',
              borderColor: 'var(--border)',
            }}
          >
            <button
              onClick={() => {
                setOpen(false)
                window.dispatchEvent(new CustomEvent('open-provider-manager'))
              }}
              className="flex items-center gap-2 w-full px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-90"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
            >
              <Settings size={12} />
              Gerenciar providers
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
