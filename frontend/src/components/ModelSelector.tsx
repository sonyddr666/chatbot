import { useState, useEffect, useRef, useCallback } from 'react'
import { ChevronDown, Settings, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, getAuthToken } from '../lib/api'
import { AIProviderIcon } from './AIProviderIcon'

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
const PROVIDERS_CACHE_KEY = 'chatbot_selectable_providers_v1'
let providersMemoryCache: { owner: string; providers: ProviderInfo[] } | null = null

function providerCacheOwner(): string {
  return (getAuthToken() || 'anonymous').slice(-24)
}

function readProvidersCache(): ProviderInfo[] {
  const owner = providerCacheOwner()
  if (providersMemoryCache?.owner === owner) return providersMemoryCache.providers
  try {
    const parsed = JSON.parse(sessionStorage.getItem(`${PROVIDERS_CACHE_KEY}:${owner}`) || '[]')
    providersMemoryCache = { owner, providers: Array.isArray(parsed) ? parsed : [] }
  } catch {
    providersMemoryCache = { owner, providers: [] }
  }
  return providersMemoryCache.providers
}

function writeProvidersCache(providers: ProviderInfo[]) {
  const owner = providerCacheOwner()
  providersMemoryCache = { owner, providers }
  try { sessionStorage.setItem(`${PROVIDERS_CACHE_KEY}:${owner}`, JSON.stringify(providers)) } catch { /* optional */ }
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getAuthToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function apiFetch(url: string, opts?: RequestInit) {
  return fetch(url, {
    ...opts,
    headers: authHeaders(opts?.headers),
  })
}

// ─── Helpers ────────────────────────────────────────────────────────

function fmtCtx(n: number): string {
  return n >= 1000000
    ? `${(n / 1000000).toFixed(0)}M`
    : n >= 1000
      ? `${(n / 1000).toFixed(0)}K`
      : String(n)
}

// ─── Componente ─────────────────────────────────────────────────────

export function ModelSelector({ canManageGlobal = false }: { canManageGlobal?: boolean }) {
  const config = useChatStore(state => state.config)
  const loadConfig = useChatStore(state => state.loadConfig)
  const [open, setOpen] = useState(false)
  const [providers, setProviders] = useState<ProviderInfo[]>(readProvidersCache)
  const [loading, setLoading] = useState(() => readProvidersCache().length === 0)
  const [error, setError] = useState<string | null>(null)
  const [optimisticSelection, setOptimisticSelection] = useState<{ provider: string; model: string } | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const providersRequestRef = useRef(0)

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

  // A lista e pre-carregada; abrir o menu nunca dispara uma consulta.
  // Também recarrega quando algum evento de mudança externa acontece
  // (ex: usuário fecha o provider manager)
  useEffect(() => {
    const refresh = () => {
      const requestId = ++providersRequestRef.current
      apiFetch(`${API}/providers/manage?compact=true`)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.json()
          })
          .then(data => {
            if (requestId === providersRequestRef.current) {
              writeProvidersCache(data)
              setProviders(data)
              setLoading(false)
              setError(null)
            }
          })
          .catch(err => {
            if (requestId === providersRequestRef.current && !readProvidersCache().length) {
              setError(err instanceof Error ? err.message : 'Falha ao carregar')
              setLoading(false)
            }
          })
    }
    refresh()
    window.addEventListener('provider-changed', refresh)
    return () => window.removeEventListener('provider-changed', refresh)
  }, [])

  // Selecionar modelo — com optimistic update
  const handleSelect = useCallback(async (providerId: string, modelId: string) => {
    // Invalida a busca iniciada ao abrir o menu. Sem isso, uma resposta antiga
    // pode chegar depois do clique e recolocar visualmente o provider anterior.
    providersRequestRef.current += 1
    const provider = providers.find(p => p.id === providerId)
    const model = provider?.models.find(item => item.id === modelId)
    setOptimisticSelection({
      provider: provider?.name || providerId,
      model: model?.name || modelId,
    })
    // Optimistic: já atualiza local pra feedback instantâneo
    const optimisticProviders = providers.map(p => ({
      ...p,
      active: p.id === providerId,
      active_model_id: p.id === providerId ? modelId : null,
      models: p.models.map(m => ({
        ...m,
        active: p.id === providerId && m.id === modelId,
      })),
    }))
    writeProvidersCache(optimisticProviders)
    setProviders(optimisticProviders)
    setOpen(false)

    // Se for outro provider, ativa primeiro
    if (!provider?.active) {
      try {
        const r = await apiFetch(`${API}/providers/manage/${providerId}/activate`, { method: 'POST' })
        if (!r.ok) throw new Error('Falha ao ativar provider')
      } catch (selectionError) {
        setOptimisticSelection(null)
        toast.error(selectionError instanceof Error ? selectionError.message : 'Falha ao ativar provider')
        await loadConfig()
        window.dispatchEvent(new CustomEvent('provider-changed'))
        return
      }
    }

    // Ativa o modelo
    try {
      const r = await apiFetch(`${API}/providers/activate-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
      })
      if (!r.ok) throw new Error('Falha ao ativar modelo')
      // A selecao deste menu e global. Remove o override pessoal apenas depois
      // que provider e modelo globais foram salvos com sucesso.
      await api.useGlobalProvider()
      await loadConfig()
      setOptimisticSelection(null)
      // Dispara evento pra outros componentes saberem
      window.dispatchEvent(new CustomEvent('provider-changed'))
    } catch (selectionError) {
      setOptimisticSelection(null)
      toast.error(selectionError instanceof Error ? selectionError.message : 'Falha ao ativar modelo')
      await loadConfig()
      window.dispatchEvent(new CustomEvent('provider-changed'))
    }
  }, [providers, loadConfig])

  // Provider ativo + modelo ativo
  const selectableProviders = providers
    .filter(p => p.enabled)
    .map(p => ({ ...p, models: p.models.filter(m => m.enabled) }))
    .filter(p => p.models.length > 0)

  const activeProvider = selectableProviders.find(p => p.active)
  const activeModel = activeProvider?.models.find(m => m.active) || activeProvider?.models[0]
  const providerMatchesConfig = !!activeProvider && activeProvider.id === config?.provider_id
  const modelMatchesConfig = !!activeModel && activeModel.id === config?.model_id
  const displayedProviderName = optimisticSelection?.provider || (providerMatchesConfig && modelMatchesConfig
    ? activeProvider.name
    : config?.profile || activeProvider?.name)
  const displayedModelName = optimisticSelection?.model || (providerMatchesConfig && modelMatchesConfig
    ? activeModel.name
    : config?.model || activeModel?.name)

  return (
    <div className="relative min-w-0" ref={dropdownRef}>
      {/* Botão do seletor */}
      <button
        onClick={() => {
          if (!canManageGlobal) {
            window.dispatchEvent(new CustomEvent('open-provider-manager'))
            return
          }
          setOpen(!open)
        }}
        className="flex min-w-0 items-center gap-1.5 rounded-xl px-2 py-1.5 text-sm font-medium transition-all hover:opacity-90 sm:gap-2 sm:px-3"
        style={{
          background: 'var(--accent-light)',
          color: 'var(--accent)',
          border: '1px solid transparent',
        }}
        title={
          displayedProviderName && displayedModelName
            ? `${displayedProviderName} › ${displayedModelName}`
            : 'Selecionar modelo'
        }
      >
        <AIProviderIcon provider={displayedProviderName} model={displayedModelName} size={16} className="flex-shrink-0" />
        <span className="max-w-[96px] min-w-0 truncate sm:max-w-[132px]">
          {displayedProviderName && displayedModelName ? (
            displayedModelName
          ) : (
            'Selecionar modelo'
          )}
        </span>
        <ChevronDown size={14} className={`transition-transform flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="fixed inset-x-2 top-14 z-50 max-h-[70dvh] overflow-y-auto rounded-xl border shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-1 sm:w-80 sm:max-h-96"
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
                  <AIProviderIcon provider={provider.name || provider.id} size={17} className="flex-shrink-0" />
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
                        <AIProviderIcon provider={`${provider.name} ${provider.id}`} model={`${model.name} ${model.id}`} size={18} className="flex-shrink-0" />
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
