import { memo, useState, useEffect, useCallback, useDeferredValue, useMemo, useRef } from 'react'
import {
  X, Plus, Trash2, Check,
  Server, Globe, Eye, EyeOff, Power, PowerOff,
  Pencil, Save, AlertTriangle, Loader2, Upload, Download, RefreshCw, User, ArrowLeft, Gauge, ExternalLink,
  GripVertical, Search,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, formatApiError, getAuthToken, type UserProviderInfo } from '../lib/api'
import { AIProviderIcon } from './AIProviderIcon'

// ─── Tipos ──────────────────────────────────────────────────────────

interface ModelInfo {
  id: string
  name: string
  alias?: string
  usage?: string
  status?: string
  validation_status?: 'working' | 'failed'
  validation_error?: string
  validated_at?: string
  context_length: number
  enabled: boolean
  active?: boolean
  supports_images?: boolean
  supports_thinking?: boolean
  thinking_stream?: boolean
  recommended?: boolean
}

interface ProviderInfo {
  id: string
  name: string
  base_url: string
  endpoint?: string
  api_key?: string
  api_format: string
  auth_type?: string
  provider_type: 'builtin' | 'custom'
  enabled: boolean
  active: boolean
  active_model_id?: string | null
  api_key_url?: string
  docs_url?: string
  catalog_provider_id?: string
  models: ModelInfo[]
  has_key?: boolean
  key_source?: string
}

interface CloudflareAccountInfo {
  id: string
  name: string
}

interface BenchmarkResult {
  ok: boolean
  model: string
  model_name: string
  ttft_ms?: number
  total_ms?: number
  output_chars?: number
  chars_per_second?: number
  had_reasoning?: boolean
  message?: string
}

interface Props {
  open: boolean
  onClose: () => void
  isAdmin?: boolean
}

interface CatalogProviderInfo {
  id: string
  name: string
  model_count: number
  doc?: string
  env?: string[]
  model_search_index?: string
  api?: string
  api_format?: string
  endpoint?: string
  endpoint_verified?: boolean
  connection_catalogued?: boolean
  connection_confidence?: string
  quick_setup?: boolean
  setup_mode?: string
  auth_type?: string
  required_fields?: string[]
  docs_url?: string
  connection_notes?: string
}

interface CatalogModelInfo extends ModelInfo {
  catalog_provider_id: string
  family?: string
  output_length?: number
  release_date?: string
  last_updated?: string
  supports_tools?: boolean
  supports_pdf?: boolean
}

// ─── API helpers ────────────────────────────────────────────────────

const API = '/api/v1'

async function apiReq<T>(url: string, opts?: RequestInit): Promise<T> {
  const token = getAuthToken()
  const res = await fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(formatApiError(err, 'Erro na requisicao'))
  }
  return res.json()
}

// ─── Componente principal ──────────────────────────────────────────

export const ProviderManager = memo(function ProviderManager({ open, onClose, isAdmin = false }: Props) {
  // Importante: não assinar a store inteira aqui.
  // Durante streaming, messages muda a cada chunk; se este modal assinar tudo, o Codex Pool fica travando.
  const loadConfig = useChatStore(s => s.loadConfig)
  const providerLoadRequestRef = useRef(0)

  const syncChatProvider = useCallback(async () => {
    await loadConfig()
    window.dispatchEvent(new CustomEvent('provider-changed'))
  }, [loadConfig])

  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [userProviders, setUserProviders] = useState<UserProviderInfo[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [providerOrder, setProviderOrder] = useState<string[]>([])
  const [draggedProviderId, setDraggedProviderId] = useState<string | null>(null)
  const [providerView, setProviderView] = useState<'active' | 'hidden' | 'catalog'>('active')
  const providerViewRef = useRef<'active' | 'hidden' | 'catalog'>('active')
  const [catalogProviders, setCatalogProviders] = useState<CatalogProviderInfo[]>([])
  const [catalogUpdatedAt, setCatalogUpdatedAt] = useState<string | null>(null)
  const [catalogSearch, setCatalogSearch] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogRefreshing, setCatalogRefreshing] = useState(false)
  const [selectedCatalog, setSelectedCatalog] = useState<CatalogProviderInfo | null>(null)
  const selectedCatalogRef = useRef<CatalogProviderInfo | null>(null)
  const [catalogQuickSetup, setCatalogQuickSetup] = useState<CatalogProviderInfo | null>(null)
  const [catalogModels, setCatalogModels] = useState<CatalogModelInfo[]>([])
  const [catalogModelSearch, setCatalogModelSearch] = useState('')
  const [catalogModelsLoading, setCatalogModelsLoading] = useState(false)
  const catalogModelsCacheRef = useRef(new Map<string, CatalogModelInfo[]>())
  const catalogLoadRequestRef = useRef(0)
  const catalogModelsRequestRef = useRef(0)
  const [syncingCatalog, setSyncingCatalog] = useState(false)
  const [modelView, setModelView] = useState<'active' | 'hidden'>('active')
  const [loading, setLoading] = useState(false)
  const [showAddForm, setShowAddForm] = useState(false)
  const [showPersonalForm, setShowPersonalForm] = useState(false)
  const [editing, setEditing] = useState(false)
  const [showExportDialog, setShowExportDialog] = useState(false)
  const [exportingProviders, setExportingProviders] = useState(false)
  const [importingProviders, setImportingProviders] = useState(false)
  const importProvidersRef = useRef<HTMLInputElement | null>(null)

  // Form state
  const [formName, setFormName] = useState('')
  const [formProviderId, setFormProviderId] = useState('')
  const [formCatalogProviderId, setFormCatalogProviderId] = useState('')
  const [formBaseUrl, setFormBaseUrl] = useState('')
  const [formEndpoint, setFormEndpoint] = useState('')
  const [formApiKey, setFormApiKey] = useState('')
  const [formApiFormat, setFormApiFormat] = useState('chat_completions')
  const [formCatalogModels, setFormCatalogModels] = useState<CatalogModelInfo[]>([])
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [personalSaving, setPersonalSaving] = useState(false)
  const [personalProviderId, setPersonalProviderId] = useState('')
  const [personalDisplayName, setPersonalDisplayName] = useState('')
  const [personalBaseUrl, setPersonalBaseUrl] = useState('')
  const [personalModel, setPersonalModel] = useState('')
  const [personalApiKey, setPersonalApiKey] = useState('')
  const [personalApiFormat, setPersonalApiFormat] = useState('chat_completions')
  const [personalIsDefault, setPersonalIsDefault] = useState(true)

  // Model management
  const [showAddModel, setShowAddModel] = useState(false)
  const [modelFormName, setModelFormName] = useState('')
  const [modelFormId, setModelFormId] = useState('')
  const [modelFormCtx, setModelFormCtx] = useState('128000')
  const [editingModelId, setEditingModelId] = useState<string | null>(null)

  // ─── Carregar providers ────────────────────────────────────────

  const loadProviders = useCallback(async () => {
    const requestId = ++providerLoadRequestRef.current
    setLoading(true)
    try {
      const [data, personal, preferences] = await Promise.all([
        apiReq<ProviderInfo[]>(`${API}/providers/manage`),
        api.listUserProviders(),
        api.listPreferences(),
      ])
      if (requestId !== providerLoadRequestRef.current) return
      setProviders(data)
      setUserProviders(personal.providers)
      const savedOrder = preferences.preferences.provider_order?.value
      setProviderOrder(Array.isArray(savedOrder)
        ? savedOrder.filter((value): value is string => typeof value === 'string')
        : [])
      setSelectedId(current => {
        if (providerViewRef.current === 'catalog') return null
        if (current && data.some(provider => provider.id === current)) return current
        return data.find(provider => provider.active)?.id || data[0]?.id || null
      })
    } catch (err: any) {
      if (requestId !== providerLoadRequestRef.current) return
      toast.error(err.message)
    } finally {
      if (requestId === providerLoadRequestRef.current) setLoading(false)
    }
  }, [])

  const loadCatalog = useCallback(async (query = '') => {
    const requestId = ++catalogLoadRequestRef.current
    setCatalogLoading(true)
    try {
      const data = await apiReq<{providers: CatalogProviderInfo[]; updated_at: string | null}>(
        `${API}/providers/catalog${query ? `?q=${encodeURIComponent(query)}` : ''}`
      )
      if (requestId !== catalogLoadRequestRef.current) return
      setCatalogProviders(data.providers)
      setCatalogUpdatedAt(data.updated_at)
    } catch (err: any) {
      if (requestId !== catalogLoadRequestRef.current) return
      toast.error(err.message)
    } finally {
      if (requestId === catalogLoadRequestRef.current) setCatalogLoading(false)
    }
  }, [])

  const openCatalogProvider = useCallback(async (provider: CatalogProviderInfo, modelQuery = '') => {
    const requestId = ++catalogModelsRequestRef.current
    selectedCatalogRef.current = provider
    setSelectedCatalog(provider)
    setSelectedId(null)
    setShowAddForm(false)
    setShowPersonalForm(false)
    setEditing(false)
    setCatalogModelSearch(modelQuery)
    const cachedModels = catalogModelsCacheRef.current.get(provider.id)
    if (cachedModels) {
      if (requestId === catalogModelsRequestRef.current) {
        setCatalogModels(cachedModels)
        setCatalogModelsLoading(false)
      }
      return
    }
    setCatalogModels([])
    setCatalogModelsLoading(true)
    try {
      const data = await apiReq<{provider_id: string; models: CatalogModelInfo[]}>(`${API}/providers/catalog/${encodeURIComponent(provider.id)}/models`)
      if (requestId !== catalogModelsRequestRef.current || data.provider_id !== provider.id) return
      if (data.models.some(model => model.catalog_provider_id !== provider.id)) {
        throw new Error('O servidor retornou modelos de outro provider. A lista foi descartada por seguranca.')
      }
      catalogModelsCacheRef.current.set(provider.id, data.models)
      setCatalogModels(data.models)
    } catch (err: any) {
      if (requestId !== catalogModelsRequestRef.current) return
      toast.error(err.message)
      setCatalogModels([])
    } finally {
      if (requestId === catalogModelsRequestRef.current) setCatalogModelsLoading(false)
    }
  }, [])

  const clearCatalogSelection = useCallback(() => {
    catalogModelsRequestRef.current += 1
    selectedCatalogRef.current = null
    setSelectedCatalog(null)
    setCatalogModels([])
    setCatalogModelSearch('')
    setCatalogModelsLoading(false)
  }, [])

  const selectManagedProvider = useCallback((providerId: string | null) => {
    clearCatalogSelection()
    setSelectedId(providerId)
    setShowAddForm(false)
    setShowPersonalForm(false)
    setEditing(false)
  }, [clearCatalogSelection])

  const refreshWorldCatalog = async () => {
    setCatalogRefreshing(true)
    try {
      const result = await apiReq<{providers: number; models: number}>(`${API}/providers/catalog/refresh`, { method: 'POST' })
      catalogModelsRequestRef.current += 1
      catalogModelsCacheRef.current.clear()
      setCatalogModels([])
      setCatalogModelsLoading(false)
      await loadCatalog()
      const currentCatalogProvider = selectedCatalogRef.current
      if (currentCatalogProvider) await openCatalogProvider(currentCatalogProvider)
      toast.success(`Catalogo atualizado: ${result.providers} providers e ${result.models} modelos`)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setCatalogRefreshing(false)
    }
  }

  useEffect(() => {
    if (open) {
      setSelectedId(null)
      catalogModelsRequestRef.current += 1
      selectedCatalogRef.current = null
      setSelectedCatalog(null)
      setCatalogModels([])
      providerViewRef.current = 'active'
      setProviderView('active')
      loadProviders()
      setShowAddForm(false)
      setShowPersonalForm(false)
      setEditing(false)
    }
  }, [open, loadProviders])

  useEffect(() => {
    providerViewRef.current = providerView
  }, [providerView])

  const selected = providers.find(p => p.id === selectedId) || null
  const catalogConfiguredProvider = selectedCatalog
    ? providers.find(provider => provider.id === selectedCatalog.id) || null
    : null
  const isCloudflareSelected = !!selected && (
    selected.id.toLowerCase().includes('cloudflare')
    || selected.base_url.toLowerCase().includes('api.cloudflare.com')
  )
  const providerOrderIndex = new Map(providerOrder.map((id, index) => [id, index]))
  const sortProviders = (items: ProviderInfo[]) => items
    .map((provider, originalIndex) => ({ provider, originalIndex }))
    .sort((left, right) => {
      const leftIndex = providerOrderIndex.get(left.provider.id)
      const rightIndex = providerOrderIndex.get(right.provider.id)
      if (leftIndex === undefined && rightIndex === undefined) return left.originalIndex - right.originalIndex
      if (leftIndex === undefined) return 1
      if (rightIndex === undefined) return -1
      return leftIndex - rightIndex
    })
    .map(item => item.provider)
  const visibleProviders = providers.filter(provider => providerView === 'hidden' ? !provider.enabled : provider.enabled)
  const visibleUserProviders = userProviders.filter(provider => providerView === 'hidden' ? !provider.is_enabled : provider.is_enabled)
  const deferredCatalogSearch = useDeferredValue(catalogSearch)
  const normalizedCatalogSearch = deferredCatalogSearch.trim().toLowerCase()
  const visibleCatalogProviders = useMemo(() => catalogProviders.filter(provider => (
    !normalizedCatalogSearch
    || provider.name.toLowerCase().includes(normalizedCatalogSearch)
    || provider.id.toLowerCase().includes(normalizedCatalogSearch)
    || provider.model_search_index?.includes(normalizedCatalogSearch)
  )), [catalogProviders, normalizedCatalogSearch])
  const builtinProviders = sortProviders(visibleProviders.filter(p => p.provider_type === 'builtin'))
  const customProviders = sortProviders(visibleProviders.filter(p => p.provider_type === 'custom'))
  const displayedModels = selected?.models.filter(model => modelView === 'hidden' ? !model.enabled : model.enabled) || []

  useEffect(() => {
    if (open && providerView === 'catalog' && catalogProviders.length === 0) void loadCatalog()
  }, [open, providerView, catalogProviders.length, loadCatalog])

  useEffect(() => {
    if (providerView !== 'catalog') return
    if (!normalizedCatalogSearch) {
      setCatalogModelSearch('')
      return
    }
    const selectedStillVisible = selectedCatalog
      ? visibleCatalogProviders.find(provider => provider.id === selectedCatalog.id)
      : undefined
    const target = selectedStillVisible || visibleCatalogProviders[0]
    if (!target) {
      clearCatalogSelection()
      return
    }
    const providerItselfMatches = `${target.name} ${target.id}`.toLowerCase().includes(normalizedCatalogSearch)
    const modelQuery = providerItselfMatches ? '' : deferredCatalogSearch.trim()
    if (selectedCatalog?.id === target.id) {
      setCatalogModelSearch(modelQuery)
    } else {
      void openCatalogProvider(target, modelQuery)
    }
  }, [clearCatalogSelection, deferredCatalogSearch, normalizedCatalogSearch, openCatalogProvider, providerView, selectedCatalog, visibleCatalogProviders])

  const handleProviderDrop = async (targetId: string) => {
    const sourceId = draggedProviderId
    setDraggedProviderId(null)
    if (!sourceId || sourceId === targetId) return
    const currentIds = sortProviders(providers).map(provider => provider.id)
    const nextOrder = currentIds.filter(id => id !== sourceId)
    const targetIndex = nextOrder.indexOf(targetId)
    nextOrder.splice(targetIndex < 0 ? nextOrder.length : targetIndex, 0, sourceId)
    const previousOrder = providerOrder
    setProviderOrder(nextOrder)
    try {
      await api.setPreference('provider_order', nextOrder)
    } catch (err) {
      setProviderOrder(previousOrder)
      toast.error(err instanceof Error ? err.message : 'Falha ao salvar a ordem dos providers')
    }
  }

  const resetPersonalForm = () => {
    setPersonalProviderId('')
    setPersonalDisplayName('')
    setPersonalBaseUrl('')
    setPersonalModel('')
    setPersonalApiKey('')
    setPersonalApiFormat('chat_completions')
    setPersonalIsDefault(true)
  }

  const handleCreatePersonalProvider = async () => {
    if (!personalProviderId.trim() || !personalModel.trim()) {
      toast.error('Provider ID e modelo sao obrigatorios')
      return
    }
    setPersonalSaving(true)
    try {
      const created = await api.createUserProvider({
        provider_id: personalProviderId.trim(),
        display_name: personalDisplayName.trim() || personalProviderId.trim(),
        base_url: personalBaseUrl.trim(),
        model: personalModel.trim(),
        api_key: personalApiKey.trim(),
        api_format: personalApiFormat,
        is_default: personalIsDefault,
        is_enabled: true,
      })
      await loadProviders()
      if (created.is_default || personalIsDefault) {
        await syncChatProvider()
      }
      resetPersonalForm()
      setShowPersonalForm(false)
      toast.success('Provider pessoal criado')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setPersonalSaving(false)
    }
  }

  const handleActivatePersonalProvider = async (id: number) => {
    setPersonalSaving(true)
    try {
      await api.activateUserProvider(id)
      setUserProviders(prev => prev.map(p => ({ ...p, is_default: p.id === id })))
      toast.success('Provider pessoal ativado')
      await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setPersonalSaving(false)
    }
  }

  const handleUseGlobalProvider = async () => {
    setPersonalSaving(true)
    try {
      await api.useGlobalProvider()
      setUserProviders(prev => prev.map(provider => ({ ...provider, is_default: false })))
      toast.success('Provider global ativado para este usuario')
      await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setPersonalSaving(false)
    }
  }

  // ─── Salvar chave de API ──────────────────────────────────────

  const handleExportProviders = async (includeApiKeys: boolean) => {
    setExportingProviders(true)
    try {
      const bundle = await apiReq<Record<string, unknown>>(
        `${API}/providers/export?include_api_keys=${includeApiKeys ? 'true' : 'false'}`,
      )
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      const date = new Date().toISOString().slice(0, 10)
      link.href = url
      link.download = `chatbot-providers-${includeApiKeys ? 'com-chaves' : 'sem-chaves'}-${date}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setShowExportDialog(false)
      toast.success(includeApiKeys ? 'Providers exportados com suas chaves' : 'Providers exportados sem chaves')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setExportingProviders(false)
    }
  }

  const handleExportAdminBackup = async () => {
    const accepted = confirm(
      'Exportar o backup administrativo completo?\n\n'
      + 'O arquivo tera TODAS as API keys e tokens OAuth do Codex e Antigravity em texto legivel. '
      + 'Quem possuir esse arquivo podera usar suas contas.',
    )
    if (!accepted) return
    setExportingProviders(true)
    try {
      const bundle = await apiReq<Record<string, unknown>>(`${API}/providers/admin-backup`)
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `chatbot-backup-completo-admin-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setShowExportDialog(false)
      toast.success('Backup administrativo completo exportado')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setExportingProviders(false)
    }
  }

  const handleImportProviders = async (event: any) => {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    setImportingProviders(true)
    try {
      const parsed = JSON.parse(await file.text())
      const isAdminBackup = parsed?.format === 'chatbot-admin-complete-backup'
      const hasApiKeys = isAdminBackup || JSON.stringify(parsed).includes('"api_key"')
      const accepted = confirm(
        `${isAdminBackup ? 'Restaurar backup administrativo completo' : 'Importar providers'} de "${file.name}"?\n\n`
        + (isAdminBackup
          ? 'Providers, chaves, contas Codex e contas Antigravity serao restaurados para o administrador.'
          : 'Providers pessoais existentes com a mesma configuracao serao atualizados. Para usuarios comuns, providers customizados serao adicionados como providers pessoais.')
        + (hasApiKeys ? '\n\nO arquivo contem API keys.' : ''),
      )
      if (!accepted) return

      const result = await apiReq<any>(`${API}${isAdminBackup ? '/providers/admin-backup' : '/providers/import'}`, {
        method: 'POST',
        body: JSON.stringify(parsed),
      })
      await loadProviders()
      await syncChatProvider()
      if (isAdminBackup) {
        toast.success(`Backup restaurado: ${result.providers?.keys || 0} chave(s), ${result.codex?.accounts || 0} Codex, ${result.antigravity?.accounts || 0} Antigravity, ${result.grok?.accounts || 0} Grok`)
        return
      }
      const customChanged = (result.custom?.created?.length || 0) + (result.custom?.updated?.length || 0)
      const personalChanged = (result.personal?.created?.length || 0) + (result.personal?.updated?.length || 0)
      const customSkipped = result.custom?.skipped?.length || 0
      toast.success(`${customChanged + personalChanged} provider(s) importado(s) ou atualizado(s)`)
      if (customSkipped) {
        toast(`${customSkipped} item(ns) customizado(s) nao puderam ser importado(s)`)
      }
    } catch (err: any) {
      toast.error(err instanceof SyntaxError ? 'Arquivo JSON invalido' : err.message)
    } finally {
      input.value = ''
      setImportingProviders(false)
    }
  }

  const handleSaveApiKey = async () => {
    if (!selectedId || !localApiKey.trim()) {
      toast.error('Insira uma chave de API')
      return
    }
    setSavingKey(true)
    try {
      await apiReq(`${API}/providers/manage/${selectedId}/api-key`, {
        method: 'PUT',
        body: JSON.stringify({ api_key: localApiKey.trim() }),
      })
      setProviders(prev => prev.map(p =>
        p.id === selectedId ? { ...p, api_key: 'sk-...', has_key: true, key_source: 'ui' } : p
      ))
      toast.success('Chave de API salva!')
      setShowApiKey(false)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setSavingKey(false)
    }
  }

  const handleDetectCloudflareAccounts = async (accountId = '', manual = false) => {
    if (!selectedId || (!localApiKey.trim() && !selected?.has_key)) {
      toast.error('Insira o API Token da Cloudflare')
      return
    }
    if (manual && !accountId.trim()) {
      toast.error('Informe o Account ID da Cloudflare')
      return
    }
    setDetectingCloudflare(true)
    try {
      const result = await apiReq<{
        configured: boolean
        accounts: CloudflareAccountInfo[]
        account?: CloudflareAccountInfo
        base_url?: string
      }>(`${API}/providers/manage/${selectedId}/cloudflare/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          api_token: localApiKey.trim() || undefined,
          account_id: accountId.trim() || undefined,
          manual_account_id: manual,
        }),
      })
      setCloudflareAccounts(result.accounts || [])
      if (result.configured) {
        await loadProviders()
        await syncChatProvider()
        setShowApiKey(false)
        setLocalApiKey('')
        setCloudflareAccountId('')
        toast.success(`Cloudflare configurado: ${result.account?.name || 'conta selecionada'}`)
      } else {
        setCloudflareAccountId(result.accounts[0]?.id || '')
        toast.success(`${result.accounts.length} contas encontradas. Escolha uma para continuar.`)
      }
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setDetectingCloudflare(false)
    }
  }

  // ─── Testar provider ───────────────────────────────────────────

  const handleTestProvider = async () => {
    if (!selectedId) return
    if (!selected?.enabled) {
      toast.error('Provider desativado. Habilite-o antes de testar.')
      return
    }
    setTestingProvider(true)
    setTestResult(null)
    try {
      const res = await apiReq<any>(`${API}/providers/test`, {
        method: 'POST',
        body: JSON.stringify({ provider_id: selectedId }),
      })
      setTestResult({
        ok: res.ok,
        latency_ms: res.latency_ms,
        message: res.message,
        source: res.source,
      })
      if (res.ok) {
        toast.success(`Provider funcionando! (${res.latency_ms}ms)`)
      } else {
        toast.error(res.message || 'Falha no teste')
      }
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message })
      toast.error(err.message)
    } finally {
      setTestingProvider(false)
    }
  }

  const runModelBenchmark = async (modelId: string, notify = true) => {
    if (!selectedId) return null
    if (!selected?.enabled) {
      if (notify) toast.error('Provider desativado. Habilite-o antes de testar.')
      return null
    }
    setBenchmarkingModels(prev => ({ ...prev, [modelId]: true }))
    try {
      const result = await apiReq<BenchmarkResult>(`${API}/providers/benchmark`, {
        method: 'POST',
        body: JSON.stringify({ provider_id: selectedId, model_id: modelId }),
      })
      setBenchmarkResults(prev => ({ ...prev, [modelId]: result }))
      setProviders(prev => prev.map(provider => provider.id !== selectedId ? provider : ({
        ...provider,
        models: provider.models.map(model => model.id !== modelId ? model : ({
          ...model,
          validation_status: result.ok ? 'working' : 'failed',
          validation_error: result.ok ? '' : (result.message || 'Falha no teste'),
          validated_at: new Date().toISOString(),
        })),
      })))
      if (notify) {
        if (result.ok) toast.success(`${result.model_name}: ${result.ttft_ms}ms ate o primeiro texto`)
        else toast.error(`${result.model_name}: ${result.message || 'falhou'}`)
      }
      return result
    } catch (err: any) {
      const failed: BenchmarkResult = {
        ok: false,
        model: modelId,
        model_name: modelId,
        message: err.message,
      }
      setBenchmarkResults(prev => ({ ...prev, [modelId]: failed }))
      if (notify) toast.error(err.message)
      return failed
    } finally {
      setBenchmarkingModels(prev => ({ ...prev, [modelId]: false }))
    }
  }

  const handleBenchmarkAll = async () => {
    if (!selected) return
    if (!selected.enabled) {
      toast.error('Provider desativado. Habilite-o antes de testar.')
      return
    }
    const enabledModels = selected.models.filter(model => model.enabled)
    if (!enabledModels.length) {
      toast.error('Nenhum modelo habilitado para testar')
      return
    }
    const confirmed = window.confirm(
      `Testar ${enabledModels.length} modelo(s) de ${selected.name}?\n\n` +
      'Sera feita uma chamada real por modelo, em sequencia. Isso pode demorar e consumir creditos.'
    )
    if (!confirmed) return

    setBenchmarkResults({})
    setBenchmarkingAll(true)
    try {
      for (const model of enabledModels) {
        await runModelBenchmark(model.id, false)
      }
      toast.success('Teste de velocidade concluido')
    } finally {
      setBenchmarkingAll(false)
    }
  }

  // ─── Ativar provider ───────────────────────────────────────────

  const handleActivate = async (id: string) => {
    const provider = providers.find(item => item.id === id)
    if (provider && !provider.enabled) {
      toast.error('Provider desativado. Habilite-o antes de ativar.')
      return
    }
    try {
      await apiReq(`${API}/providers/manage/${id}/activate`, { method: 'POST' })
      if (!['grok-oauth', 'antigravity'].includes(id)) await api.useGlobalProvider()
      setProviders(prev => prev.map(p => ({ ...p, active: p.id === id })))
      toast.success(`Provider ativado`)
      await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Toggle enable/disable ─────────────────────────────────────

  const handleToggleEnable = async (id: string, current: boolean) => {
    const p = providers.find(x => x.id === id)
    if (!p) return
    if (current && p.active) {
      toast.error('Não dá para desativar o provider ativo. Ative outro provider primeiro.')
      return
    }
    try {
      const updated = await apiReq<ProviderInfo>(`${API}/providers/manage/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: !current }),
      })
      setProviders(prev => prev.map(x => x.id === id ? { ...x, ...updated } : x))
      toast.success(current ? 'Provider desativado' : 'Provider ativado')
      loadConfig()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Deletar provider custom ───────────────────────────────────

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir este provider?')) return
    const deletingActiveProvider = providers.some(provider => provider.id === id && provider.active)
    try {
      await apiReq(`${API}/providers/manage/${id}`, { method: 'DELETE' })
      setProviders(prev => prev.filter(p => p.id !== id))
      if (selectedId === id) {
        setSelectedId(null)
        setShowAddForm(false)
        setEditing(false)
      }
      toast.success('Provider excluído')
      if (deletingActiveProvider) await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Criar / Atualizar provider ────────────────────────────────

  // ─── Estado para chave de API (qualquer provider) ────────────
  const [localApiKey, setLocalApiKey] = useState('')
  const [savingKey, setSavingKey] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [testingProvider, setTestingProvider] = useState(false)
  const [testResult, setTestResult] = useState<{ok: boolean; latency_ms?: number; message?: string; source?: string} | null>(null)
  const [benchmarkResults, setBenchmarkResults] = useState<Record<string, BenchmarkResult>>({})
  const [benchmarkingModels, setBenchmarkingModels] = useState<Record<string, boolean>>({})
  const [benchmarkingAll, setBenchmarkingAll] = useState(false)
  const [cloudflareAccounts, setCloudflareAccounts] = useState<CloudflareAccountInfo[]>([])
  const [cloudflareAccountId, setCloudflareAccountId] = useState('')
  const [detectingCloudflare, setDetectingCloudflare] = useState(false)

  useEffect(() => {
    setCloudflareAccounts([])
    setCloudflareAccountId('')
    setBenchmarkResults({})
    setBenchmarkingModels({})
    setBenchmarkingAll(false)
  }, [selectedId])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (showExportDialog) {
        setShowExportDialog(false)
      } else if (showApiKey) {
        setShowApiKey(false)
      } else {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose, open, showApiKey, showExportDialog])

  // ─── Estados do formulário de criação (com modelo) ───────────
  const [formModelId, setFormModelId] = useState('')
  const [formModelName, setFormModelName] = useState('')
  const [formModelCtx, setFormModelCtx] = useState('128000')

  const resetForm = () => {
    setFormName('')
    setFormProviderId('')
    setFormCatalogProviderId('')
    setFormBaseUrl('')
    setFormEndpoint('')
    setFormApiKey('')
    setFormApiFormat('chat_completions')
    setFormCatalogModels([])
    setFormModelId('')
    setFormModelName('')
    setFormModelCtx('128000')
    setShowKey(false)
    setCatalogQuickSetup(null)
    setEditing(false)
    setShowAddForm(false)
    setShowPersonalForm(false)
  }

  const handleEditProvider = (p: ProviderInfo) => {
    if (p.provider_type === 'builtin') {
      toast('Providers built-in não podem ser editados')
      return
    }
    clearCatalogSelection()
    setCatalogQuickSetup(null)
    setFormCatalogModels([])
    setFormName(p.name)
    setFormProviderId(p.id)
    setFormCatalogProviderId(p.catalog_provider_id || '')
    setFormBaseUrl(p.base_url)
    setFormEndpoint(p.endpoint || '')
    setFormApiKey('')
    setFormApiFormat(p.api_format)
    setEditing(true)
    setShowAddForm(true)
    setSelectedId(p.id)
  }

  const handleSaveProvider = async () => {
    if (!formName.trim() || !formBaseUrl.trim()) {
      toast.error('Nome e Base URL são obrigatórios')
      return
    }
    if (catalogQuickSetup?.env?.length && !formApiKey.trim()) {
      toast.error('Informe a API key para configurar este provider')
      return
    }
    if (catalogQuickSetup && formCatalogModels.some(model => model.catalog_provider_id !== catalogQuickSetup.id)) {
      toast.error('A lista de modelos nao corresponde ao provider selecionado. Reabra o catalogo e tente novamente.')
      return
    }
    setSaving(true)
    try {
      if (editing && selectedId) {
        const editingActiveProvider = providers.some(provider => provider.id === selectedId && provider.active)
        const body: Record<string, any> = {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          endpoint: formEndpoint.trim(),
          api_format: formApiFormat,
        }
        if (formApiKey.trim()) body.api_key = formApiKey.trim()
        const updated = await apiReq<ProviderInfo>(`${API}/providers/manage/${selectedId}`, {
          method: 'PUT', body: JSON.stringify(body),
        })
        setProviders(prev => prev.map(p => p.id === selectedId ? { ...p, ...updated } : p))
        toast.success('Provider atualizado')
        if (editingActiveProvider) await syncChatProvider()
      } else {
        // Cria o modelo inicial se o usuário preencheu
        const models: any[] = catalogQuickSetup
          ? formCatalogModels.map(model => ({ ...model, enabled: false, active: false }))
          : []
        if (!catalogQuickSetup && formModelId.trim()) {
          models.push({
            id: formModelId.trim().toLowerCase().replace(/\s+/g, '-'),
            name: formModelName.trim() || formModelId.trim(),
            context_length: parseInt(formModelCtx) || 128000,
            enabled: true,
          })
        }
        const body = {
          id: formProviderId.trim(),
          catalog_provider_id: formCatalogProviderId.trim(),
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          endpoint: formEndpoint.trim(),
          api_key: formApiKey.trim(),
          api_format: formApiFormat,
          auth_type: catalogQuickSetup?.auth_type || undefined,
          models,
        }
        const created = await apiReq<ProviderInfo>(`${API}/providers/manage`, {
          method: 'POST', body: JSON.stringify(body),
        })
        setProviders(prev => [...prev, created])
        providerViewRef.current = 'active'
        setProviderView('active')
        clearCatalogSelection()
        setSelectedId(created.id)
        toast.success(models.length > 0
          ? `Provider criado com ${models.length} modelo(s)`
          : 'Provider criado! Adicione modelos agora.')
      }
      resetForm()
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ─── Gerenciar modelos ─────────────────────────────────────────

  const handleAddModel = async () => {
    if (!modelFormName.trim() || !modelFormId.trim()) {
      toast.error('Nome e ID do modelo são obrigatórios')
      return
    }
    if (!selectedId) return
    setSaving(true)
    try {
      const body = {
        id: modelFormId.trim().toLowerCase().replace(/\s+/g, '-'),
        name: modelFormName.trim(),
        context_length: parseInt(modelFormCtx) || 128000,
        enabled: true,
      }
      if (editingModelId) {
        // Atualizar modelo existente
        const updated = await apiReq<ModelInfo>(`${API}/providers/manage/${selectedId}/models/${editingModelId}`, {
          method: 'PUT', body: JSON.stringify(body),
        })
        setProviders(prev => prev.map(p =>
          p.id === selectedId ? {
            ...p,
            models: p.models.map(m => m.id === editingModelId ? { ...m, ...updated } : m),
          } : p
        ))
        toast.success('Modelo atualizado')
        const editedActiveModel = providers.some(provider => (
          provider.id === selectedId
          && provider.active
          && provider.models.some(model => model.id === editingModelId && model.active)
        ))
        if (editedActiveModel) await syncChatProvider()
      } else {
        // Criar novo modelo
        const created = await apiReq<ModelInfo>(`${API}/providers/manage/${selectedId}/models`, {
          method: 'POST', body: JSON.stringify(body),
        })
        setProviders(prev => prev.map(p =>
          p.id === selectedId ? { ...p, models: [...p.models, created] } : p
        ))
        toast.success('Modelo adicionado')
      }
      setShowAddModel(false)
      setModelFormName('')
      setModelFormId('')
      setModelFormCtx('128000')
      setEditingModelId(null)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleEditModel = (model: ModelInfo) => {
    setModelFormName(model.name)
    setModelFormId(model.id)
    setModelFormCtx(String(model.context_length))
    setEditingModelId(model.id)
    setShowAddModel(true)
  }

  const handleDeleteModel = async (modelId: string) => {
    if (!selectedId) return
    if (!confirm(`Excluir modelo "${modelId}"?`)) return
    const deletingActiveModel = providers.some(provider => (
      provider.id === selectedId
      && provider.active
      && provider.models.some(model => model.id === modelId && model.active)
    ))
    try {
      await apiReq(`${API}/providers/manage/${selectedId}/models/${modelId}`, { method: 'DELETE' })
      setProviders(prev => prev.map(p =>
        p.id === selectedId ? { ...p, models: p.models.filter(m => m.id !== modelId) } : p
      ))
      toast.success('Modelo excluído')
      if (deletingActiveModel) await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  const handleToggleModel = async (modelId: string, current: boolean) => {
    if (!selectedId) return
    const p = providers.find(x => x.id === selectedId)
    const model = p?.models.find(m => m.id === modelId)
    if (current && p?.active && model?.active) {
      toast.error('Não dá para desativar o modelo ativo. Selecione outro modelo primeiro.')
      return
    }
    try {
      const updated = await apiReq<ModelInfo>(`${API}/providers/manage/${selectedId}/models/${modelId}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: !current }),
      })
      setProviders(prev => prev.map(prov =>
        prov.id === selectedId ? {
          ...prov,
          models: prov.models.map(m => m.id === modelId ? { ...m, ...updated } : m),
        } : prov
      ))
      loadConfig()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  const handleSyncCatalog = async (providerId: string, catalogProviderId = '') => {
    setSyncingCatalog(true)
    try {
      const result = await apiReq<{total: number; added_hidden: number}>(
        `${API}/providers/manage/${encodeURIComponent(providerId)}/sync-catalog`,
        { method: 'POST', body: JSON.stringify({ catalog_provider_id: catalogProviderId }) },
      )
      await loadProviders()
      setModelView('hidden')
      toast.success(`${result.total} modelos sincronizados; ${result.added_hidden} novos em Ocultos`)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setSyncingCatalog(false)
    }
  }

  // ─── Selecionar modelo ativo (1 clique: ativa provider + modelo) ─

  const handleSelectModel = async (modelId: string, providerId?: string) => {
    const targetProviderId = providerId || selectedId
    if (!targetProviderId) return
    try {
      const provider = providers.find(p => p.id === targetProviderId)
      if (provider && !provider.enabled) {
        toast.error('Provider desativado. Habilite-o antes de usar um modelo.')
        return
      }
      // Se provider não estiver ativo, ativa primeiro
      if (!provider?.active) {
        await apiReq(`${API}/providers/manage/${targetProviderId}/activate`, { method: 'POST' })
      }
      // Agora ativa o modelo
      await apiReq(`${API}/providers/activate-model`, {
        method: 'POST',
        body: JSON.stringify({ model_id: modelId }),
      })
      await api.useGlobalProvider()
      // Atualiza a lista completa
      setProviders(prev => prev.map(prov => ({
        ...prov,
        active: prov.id === targetProviderId,
        active_model_id: prov.id === targetProviderId ? modelId : null,
        models: prov.models.map(m => ({
          ...m,
          active: prov.id === targetProviderId && m.id === modelId,
        })),
      })))
      providerViewRef.current = 'active'
      setProviderView('active')
      clearCatalogSelection()
      setSelectedId(targetProviderId)
      toast.success(`✅ Usando: ${provider?.name || targetProviderId} › ${modelId}`)
      await syncChatProvider()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Renderiza formato da API ──────────────────────────────────

  const formatLabels: Record<string, string> = {
    chat_completions: 'Chat Completions',
    anthropic_messages: 'Anthropic Messages',
    responses: 'Responses API',
    openai_responses: 'OpenAI Responses',
    openai: 'OpenAI Compatible',
  }

  const benchmarkRanking = Object.values(benchmarkResults)
    .filter(result => result.ok && typeof result.ttft_ms === 'number')
    .sort((a, b) => (a.ttft_ms || 0) - (b.ttft_ms || 0))
  const benchmarkRankByModel = new Map(
    benchmarkRanking.map((result, index) => [result.model, index + 1])
  )

  // ─── Render ─────────────────────────────────────────────────────

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.5)' }}
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="flex h-[100dvh] w-full max-w-6xl overflow-hidden shadow-2xl sm:h-[85vh] sm:w-[95vw] sm:rounded-2xl"
        style={{ background: 'var(--bg-primary)' }}
      >
        {/* ─── Sidebar ─── */}
        <div
          className={`${showPersonalForm || showAddForm || selected || selectedCatalog ? 'hidden md:flex' : 'flex'} w-full flex-shrink-0 flex-col overflow-hidden border-r md:w-72`}
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
        >
          {/* Header */}
          <div className="px-3 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-bold text-lg" style={{ color: 'var(--text-primary)' }}>Providers</h2>
              <button onClick={onClose} className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10">
                <X size={18} style={{ color: 'var(--text-secondary)' }} />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-3">
              <button
                onClick={() => setShowExportDialog(true)}
                disabled={exportingProviders}
                className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-xl border text-xs font-semibold disabled:opacity-50"
                style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
              >
                {exportingProviders ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                Exportar
              </button>
              <button
                onClick={() => importProvidersRef.current?.click()}
                disabled={importingProviders}
                className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-xl border text-xs font-semibold disabled:opacity-50"
                style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
              >
                {importingProviders ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                Importar JSON
              </button>

            </div>
            <div className="mt-3 grid grid-cols-3 gap-1 rounded-xl p-1" style={{ background: 'var(--bg-tertiary)' }}>
              {([
                ['active', 'Ativos'],
                ['hidden', 'Ocultos'],
                ['catalog', 'Mundo'],
              ] as const).map(([view, label]) => (
                <button
                  key={view}
                  onClick={() => {
                    providerViewRef.current = view
                    setProviderView(view)
                    setSelectedId(null)
                    clearCatalogSelection()
                    setShowAddForm(false)
                    setShowPersonalForm(false)
                  }}
                  className="rounded-lg px-1 py-1.5 text-[11px] font-semibold"
                  style={{
                    background: providerView === view ? 'var(--bg-primary)' : 'transparent',
                    color: providerView === view ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Lista */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {providerView === 'catalog' ? (
              <>
                <div className="sticky top-0 z-10 space-y-2 pb-2" style={{ background: 'var(--bg-secondary)' }}>
                  <div className="relative">
                    <Search size={14} className="absolute left-3 top-2.5" style={{ color: 'var(--text-tertiary)' }} />
                    <input
                      value={catalogSearch}
                      onChange={event => setCatalogSearch(event.target.value)}
                      placeholder="Buscar no mundo..."
                      className="w-full rounded-xl border py-2 pl-9 pr-3 text-xs"
                      style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
                    />
                  </div>
                  <div className="flex items-center justify-between px-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    <span>{visibleCatalogProviders.length} de {catalogProviders.length} providers</span>
                    {catalogUpdatedAt && <span>{new Date(catalogUpdatedAt).toLocaleDateString('pt-BR')}</span>}
                  </div>
                </div>
                {catalogLoading ? (
                  <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin" /></div>
                ) : visibleCatalogProviders.length === 0 ? (
                  <p className="px-3 py-8 text-center text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    Nenhum provider encontrado para “{catalogSearch}”.
                  </p>
                ) : visibleCatalogProviders.map(provider => (
                  <button
                    key={provider.id}
                    onClick={() => {
                      const providerItselfMatches = `${provider.name} ${provider.id}`.toLowerCase().includes(normalizedCatalogSearch)
                      void openCatalogProvider(provider, providerItselfMatches ? '' : deferredCatalogSearch.trim())
                    }}
                    className="flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left"
                    style={{
                      borderColor: selectedCatalog?.id === provider.id ? 'var(--accent)' : 'transparent',
                      background: selectedCatalog?.id === provider.id ? 'var(--accent-light)' : 'transparent',
                    }}
                  >
                    <ProviderVisualIcon provider={`${provider.name} ${provider.id}`} size={19} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{provider.name}</span>
                      <span className="block truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>{provider.model_count} modelos · {provider.id}</span>
                    </span>
                  </button>
                ))}
              </>
            ) : loading && providers.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />
              </div>
            ) : (
              <>
                {/* Seção Built-in */}
                <div className="px-2 py-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                    Built-in
                  </p>
                </div>
                {builtinProviders.map(p => (
                  <ProviderItem
                    key={p.id}
                    provider={p}
                    selected={selectedId === p.id}
                    dragging={draggedProviderId === p.id}
                    onDragStart={() => setDraggedProviderId(p.id)}
                    onDragEnd={() => setDraggedProviderId(null)}
                    onDrop={() => void handleProviderDrop(p.id)}
                    onClick={() => selectManagedProvider(p.id)}
                    onEdit={() => handleEditProvider(p)}
                  />
                ))}

                {/* Seção Custom */}
                {customProviders.length > 0 && (
                  <>
                    <div className="px-2 py-1.5 mt-2">
                      <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                        Custom Providers
                      </p>
                    </div>
                    {customProviders.map(p => (
                      <ProviderItem
                        key={p.id}
                        provider={p}
                        selected={selectedId === p.id}
                        dragging={draggedProviderId === p.id}
                        onDragStart={() => setDraggedProviderId(p.id)}
                        onDragEnd={() => setDraggedProviderId(null)}
                        onDrop={() => void handleProviderDrop(p.id)}
                        onClick={() => selectManagedProvider(p.id)}
                        onEdit={() => handleEditProvider(p)}
                        onDelete={() => handleDelete(p.id)}
                      />
                    ))}
                  </>
                )}

                <div className="px-2 py-1.5 mt-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                      Providers pessoais
                    </p>
                    {userProviders.some(provider => provider.is_default) && (
                      <button
                        onClick={handleUseGlobalProvider}
                        disabled={personalSaving}
                        className="rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50"
                        style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                      >
                        Usar global
                      </button>
                    )}
                  </div>
                </div>
                <div className="space-y-1">
                  {visibleUserProviders.length === 0 ? (
                    <p className="px-3 py-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      {providerView === 'hidden' ? 'Nenhum provider pessoal oculto.' : 'Nenhum provider pessoal ativo.'}
                    </p>
                  ) : (
                    visibleUserProviders.map(provider => (
                      <div
                        key={provider.id}
                        className="px-3 py-2 rounded-xl border"
                        style={{
                          background: provider.is_default ? 'var(--accent-light)' : 'transparent',
                          borderColor: provider.is_default ? 'var(--accent)' : 'var(--border)',
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex min-w-0 items-start gap-2">
                            <AIProviderIcon
                              provider={`${provider.display_name} ${provider.base_url}`}
                              model={provider.model}
                              size={18}
                              className="mt-0.5 flex-shrink-0"
                            />
                            <div className="min-w-0">
                            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                              {provider.display_name}
                            </p>
                            <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                              {provider.model}
                            </p>
                            </div>
                          </div>
                          {provider.is_default && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                              style={{ background: '#dcfce7', color: '#16a34a' }}>
                              ativo
                            </span>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-2 mt-2">
                          <span className="text-[11px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                            {provider.has_key ? provider.key_masked : 'sem chave'}
                          </span>
                          <button
                            onClick={() => handleActivatePersonalProvider(provider.id)}
                            disabled={provider.is_default || personalSaving}
                            className="px-2 py-1 rounded-lg text-[11px] font-medium transition-all disabled:opacity-50"
                            style={{ background: 'var(--accent)', color: '#fff' }}
                          >
                            Ativar pessoal
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </div>

          {/* Botão Add Provider */}
          <div className="p-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <input
              ref={importProvidersRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleImportProviders}
            />
            <div className="grid grid-cols-2 gap-2 mb-2">
              <button
                onClick={() => setShowExportDialog(true)}
                disabled={exportingProviders}
                className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-xl border text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
                style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
              >
                {exportingProviders ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                Exportar
              </button>
              <button
                onClick={() => importProvidersRef.current?.click()}
                disabled={importingProviders}
                className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-xl border text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
                style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
              >
                {importingProviders ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                Importar JSON
              </button>
            </div>
            <button
              onClick={() => { resetForm(); clearCatalogSelection(); setShowAddForm(true); setShowPersonalForm(false); setSelectedId(null) }}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-medium text-sm transition-all hover:opacity-90"
              style={{ background: 'var(--accent)', color: '#fff' }}
            >
              <Plus size={16} />
              Add Provider
            </button>
            <button
              onClick={() => { resetForm(); resetPersonalForm(); clearCatalogSelection(); setShowPersonalForm(true); setShowAddForm(false); setSelectedId(null) }}
              className="mt-2 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-medium text-sm transition-all hover:opacity-90 border"
              style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
            >
              <User size={16} />
              Criar provider pessoal
            </button>
          </div>
        </div>

        {/* ─── Main Area ─── */}
        <div className={`${showPersonalForm || showAddForm || selected || selectedCatalog ? 'flex' : 'hidden md:flex'} min-w-0 flex-1 flex-col overflow-hidden`}>
          <div className="flex items-center justify-between border-b px-3 py-3 md:hidden" style={{ borderColor: 'var(--border)' }}>
            <button
              type="button"
              onClick={() => { clearCatalogSelection(); setSelectedId(null); setShowAddForm(false); setShowPersonalForm(false); setEditing(false) }}
              className="inline-flex items-center gap-2 rounded-xl px-2 py-1.5 text-sm font-bold"
              style={{ color: 'var(--text-primary)' }}
            >
              <ArrowLeft size={18} /> Providers
            </button>
            <button onClick={onClose} className="rounded-lg p-2" title="Fechar">
              <X size={19} style={{ color: 'var(--text-secondary)' }} />
            </button>
          </div>
          {showPersonalForm ? (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
              <div className="max-w-xl mx-auto">
                <h3 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                  Criar provider pessoal
                </h3>
                <p className="text-sm mb-6" style={{ color: 'var(--text-tertiary)' }}>
                  Este provider fica ligado somente ao usuario logado e pode virar o padrao do chat dele.
                </p>

                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Provider ID</label>
                      <input
                        type="text"
                        value={personalProviderId}
                        onChange={e => setPersonalProviderId(e.target.value)}
                        placeholder="meu-openai"
                        className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Nome visivel</label>
                      <input
                        type="text"
                        value={personalDisplayName}
                        onChange={e => setPersonalDisplayName(e.target.value)}
                        placeholder="Meu OpenAI"
                        className="w-full px-3 py-2 rounded-xl border text-sm"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Base URL</label>
                    <input
                      type="url"
                      value={personalBaseUrl}
                      onChange={e => setPersonalBaseUrl(e.target.value)}
                      placeholder="https://api.openai.com/v1"
                      className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Endpoint</label>
                    <input
                      type="text"
                      value={formEndpoint}
                      onChange={e => setFormEndpoint(e.target.value)}
                      placeholder="/responses ou /chat/completions"
                      className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                    <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
                      Caminho separado da Base URL. Deixe vazio para usar o padrao do formato da API.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Modelo</label>
                      <input
                        type="text"
                        value={personalModel}
                        onChange={e => setPersonalModel(e.target.value)}
                        placeholder="gpt-4.1-mini"
                        className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Formato</label>
                      <select
                        value={personalApiFormat}
                        onChange={e => setPersonalApiFormat(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl border text-sm"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      >
                        {Object.entries(formatLabels).map(([val, label]) => (
                          <option key={val} value={val}>{label}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>API Key</label>
                    <input
                      type="password"
                      value={personalApiKey}
                      onChange={e => setPersonalApiKey(e.target.value)}
                      placeholder="sk-..."
                      className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                  </div>

                  <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                    <input
                      type="checkbox"
                      checked={personalIsDefault}
                      onChange={e => setPersonalIsDefault(e.target.checked)}
                    />
                    Usar como provider padrao deste usuario
                  </label>

                  <div className="flex gap-3 pt-4">
                    <button
                      onClick={() => { resetPersonalForm(); setShowPersonalForm(false) }}
                      className="px-4 py-2 rounded-xl border text-sm font-medium"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleCreatePersonalProvider}
                      disabled={personalSaving}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: 'var(--accent)' }}
                    >
                      {personalSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      Criar provider pessoal
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : showAddForm ? (
            /* ─── Formulário de Adição/Edição ─── */
            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
              <div className="max-w-xl mx-auto">
                <h3 className="text-xl font-bold mb-6" style={{ color: 'var(--text-primary)' }}>
                  {editing ? 'Edit Provider' : catalogQuickSetup ? `Configurar ${catalogQuickSetup.name}` : 'Add New Provider'}
                </h3>

                <div className="space-y-4">
                  {!editing && !catalogQuickSetup && (
                    <div>
                      <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Provider ID</label>
                      <input
                        type="text"
                        value={formProviderId}
                        onChange={e => setFormProviderId(e.target.value)}
                        placeholder="anthropic"
                        className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                        style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
                      />
                    </div>
                  )}
                  {/* Nome */}
                  <div className={catalogQuickSetup ? 'hidden' : ''}>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Name</label>
                    <input
                      type="text"
                      value={formName}
                      onChange={e => setFormName(e.target.value)}
                      placeholder="e.g. DeepSeek"
                      className="w-full px-3 py-2 rounded-xl border text-sm"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                  </div>

                  {/* Base URL */}
                  <div className={catalogQuickSetup ? 'hidden' : ''}>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                      {editing && isCloudflareSelected ? 'Base URL (automatica)' : 'Base URL'}
                    </label>
                    <input
                      type="url"
                      value={formBaseUrl}
                      onChange={e => setFormBaseUrl(e.target.value)}
                      disabled={editing && isCloudflareSelected}
                      placeholder="https://api.example.com/v1"
                      className="w-full px-3 py-2 rounded-xl border text-sm font-mono disabled:cursor-not-allowed disabled:opacity-60"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                    {editing && isCloudflareSelected && (
                      <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        Ao salvar uma chave nova, o Account ID e detectado e esta URL e atualizada automaticamente.
                      </p>
                    )}
                  </div>

                  {/* API Key */}
                  {catalogQuickSetup && (
                    <div className="rounded-xl border p-3 text-sm" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                      URL, formato e {formCatalogModels.length} modelos ja vieram do catalogo. Eles serao importados ocultos: teste e habilite somente os que realmente responderem.
                    </div>
                  )}
                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>API Key</label>
                    <div className="relative">
                      <input
                        type={showKey ? 'text' : 'password'}
                        value={formApiKey}
                        onChange={e => setFormApiKey(e.target.value)}
                        placeholder={editing ? 'Leave blank to keep existing' : 'sk-...'}
                        className="w-full px-3 py-2 rounded-xl border text-sm font-mono pr-10"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                      <button
                        onClick={() => setShowKey(!showKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-black/10 dark:hover:bg-white/10"
                      >
                        {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                        <span className="sr-only">{showKey ? 'Hide' : 'Show'} API Key</span>
                      </button>
                    </div>
                  </div>

                  {/* API Format */}
                  <div className={catalogQuickSetup ? 'hidden' : ''}>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>API Format</label>
                    <select
                      value={formApiFormat}
                      onChange={e => setFormApiFormat(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border text-sm"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    >
                      {Object.entries(formatLabels).map(([val, label]) => (
                        <option key={val} value={val}>{label}</option>
                      ))}
                    </select>
                  </div>

                  {/* ─── Modelo inicial (opcional) ─── */}
                  {!editing && !catalogQuickSetup && (
                    <>
                      <div className="border-t pt-4 mt-2" style={{ borderColor: 'var(--border)' }}>
                        <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-secondary)' }}>
                          🧩 Modelo inicial <span className="text-xs font-normal" style={{ color: 'var(--text-tertiary)' }}>(opcional — adicione mais depois)</span>
                        </p>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                          <div>
                            <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Model ID</label>
                            <input
                              type="text"
                              value={formModelId}
                              onChange={e => setFormModelId(e.target.value)}
                              placeholder="meu-modelo"
                              className="w-full px-2.5 py-1.5 rounded-lg border text-sm font-mono"
                              style={{
                                background: 'var(--bg-primary)',
                                color: 'var(--text-primary)',
                                borderColor: 'var(--border)',
                              }}
                            />
                          </div>
                          <div>
                            <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Display Name</label>
                            <input
                              type="text"
                              value={formModelName}
                              onChange={e => setFormModelName(e.target.value)}
                              placeholder="Meu Modelo"
                              className="w-full px-2.5 py-1.5 rounded-lg border text-sm"
                              style={{
                                background: 'var(--bg-primary)',
                                color: 'var(--text-primary)',
                                borderColor: 'var(--border)',
                              }}
                            />
                          </div>
                          <div>
                            <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Context Length</label>
                            <input
                              type="text"
                              value={formModelCtx}
                              onChange={e => setFormModelCtx(e.target.value)}
                              placeholder="128000"
                              className="w-full px-2.5 py-1.5 rounded-lg border text-sm font-mono"
                              style={{
                                background: 'var(--bg-primary)',
                                color: 'var(--text-primary)',
                                borderColor: 'var(--border)',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  {/* Actions */}
                  <div className="flex gap-3 pt-4">
                    <button
                      onClick={resetForm}
                      className="px-4 py-2 rounded-xl border text-sm font-medium"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveProvider}
                      disabled={saving}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: 'var(--accent)' }}
                    >
                      {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      {editing ? 'Save Changes' : catalogQuickSetup ? 'Salvar chave e modelos' : 'Create Provider'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : providerView === 'catalog' && selectedCatalog ? (
            <CatalogProviderPanel
              provider={selectedCatalog}
              models={catalogModels}
              loading={catalogModelsLoading}
              query={catalogModelSearch}
              onQueryChange={setCatalogModelSearch}
              configuredProvider={catalogConfiguredProvider}
              isAdmin={isAdmin}
              refreshing={catalogRefreshing}
              syncing={syncingCatalog}
              onRefresh={() => void refreshWorldCatalog()}
              onSync={() => catalogConfiguredProvider && void handleSyncCatalog(catalogConfiguredProvider.id, selectedCatalog.id)}
              onConfigure={() => {
                const catalogProvider = selectedCatalog
                const providerModels = catalogModels.filter(model => model.catalog_provider_id === catalogProvider.id)
                if (providerModels.length !== catalogModels.length) {
                  toast.error('Os modelos carregados nao correspondem ao provider selecionado. Aguarde e tente novamente.')
                  return
                }
                catalogModelsRequestRef.current += 1
                resetForm()
                setCatalogQuickSetup(catalogProvider.quick_setup ? catalogProvider : null)
                setFormCatalogModels(catalogProvider.quick_setup ? providerModels : [])
                setFormProviderId(catalogProvider.id)
                setFormCatalogProviderId(catalogProvider.id)
                setFormName(catalogProvider.name)
                setFormBaseUrl(catalogProvider.api || '')
                setFormEndpoint(catalogProvider.endpoint || '')
                setFormApiFormat(catalogProvider.api_format || 'chat_completions')
                if (!catalogProvider.quick_setup) {
                  toast(catalogProvider.endpoint_verified
                    ? 'Este provider exige configuracao adicional ou um adaptador especifico; revise os campos avancados.'
                    : 'Endpoint ainda nao validado em documentacao oficial; revise os campos avancados antes de salvar.')
                }
                const firstModel = providerModels[0]
                if (firstModel) {
                  setFormModelId(firstModel.id)
                  setFormModelName(firstModel.name)
                  setFormModelCtx(String(firstModel.context_length || 128000))
                }
                clearCatalogSelection()
                setShowAddForm(true)
              }}
            />
          ) : selected ? (
            /* ─── Detalhes do Provider ─── */
            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
              {/* Header */}
              <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                    <ProviderVisualIcon provider={`${selected.name} ${selected.id}`} size={24} className="flex-shrink-0" />
                    <h3 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{selected.name}</h3>
                    {selected.active && (
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ background: '#dcfce7', color: '#16a34a' }}>
                        Active
                      </span>
                    )}
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{
                        background: selected.enabled ? '#dcfce7' : '#fef2f2',
                        color: selected.enabled ? '#16a34a' : '#dc2626',
                      }}>
                      {selected.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {selected.provider_type === 'custom' && (
                      <span className="text-xs px-2 py-0.5 rounded-full"
                        style={{ background: '#dbeafe', color: '#2563eb' }}>
                        Custom
                      </span>
                    )}
                  </div>
                  <p className="text-sm mt-1" style={{ color: 'var(--text-tertiary)' }}>
                    {selected.base_url}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {selected.api_key_url && (
                    <a
                      href={selected.api_key_url}
                      target="_blank"
                      rel="noreferrer"
                      className="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-90"
                      style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}
                    >
                      <ExternalLink size={12} />
                      Obter chave API
                    </a>
                  )}
                  {selected.docs_url && (
                    <a
                      href={selected.docs_url}
                      target="_blank"
                      rel="noreferrer"
                      className="px-3 py-1.5 rounded-xl border text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-90"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                    >
                      <ExternalLink size={12} />
                      Documentação
                    </a>
                  )}
                  {!selected.active && (
                    <button
                      onClick={() => handleActivate(selected.id)}
                      disabled={!selected.enabled}
                      title={selected.enabled ? 'Ativar provider' : 'Habilite o provider primeiro'}
                      className="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
                      style={{ background: '#dcfce7', color: '#16a34a' }}
                    >
                      <Power size={12} />
                      Activate
                    </button>
                  )}
                  <button
                    onClick={() => handleToggleEnable(selected.id, selected.enabled)}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-90"
                    style={{
                      background: selected.enabled ? '#fef2f2' : '#dcfce7',
                      color: selected.enabled ? '#dc2626' : '#16a34a',
                    }}
                  >
                    {selected.enabled ? <PowerOff size={12} /> : <Power size={12} />}
                    {selected.enabled ? 'Disable' : 'Enable'}
                  </button>
                  {selected.provider_type === 'custom' && (
                    <button
                      onClick={() => handleEditProvider(selected)}
                      className="p-1.5 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                      title="Edit"
                    >
                      <Pencil size={16} style={{ color: 'var(--text-secondary)' }} />
                    </button>
                  )}
                  {selected.provider_type === 'custom' && (
                    <button
                      onClick={() => handleDelete(selected.id)}
                      className="p-1.5 rounded-xl hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={16} style={{ color: '#dc2626' }} />
                    </button>
                  )}
                </div>
              </div>

              {/* Info */}
              <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
                <InfoCard label="API Format" value={formatLabels[selected.api_format] || selected.api_format} icon={<Globe size={16} />} />
                <InfoCard label="Provider Type" value={selected.provider_type === 'builtin' ? 'Built-in' : 'Custom'} icon={<Server size={16} />} />
                <InfoCard label="Endpoint" value={selected.endpoint || 'Padrao do formato'} icon={<Globe size={16} />} />
                <InfoCard
                  label="API Key"
                  value={
                    ['codex-chatgpt', 'antigravity', 'grok-oauth'].includes(selected.id)
                      ? (selected.has_key ? 'OAuth conectado' : 'OAuth não conectado')
                      : (selected.has_key ? `${(selected.api_key || '').substring(0, 12)}...` : 'Não configurada')
                  }
                  icon={<Eye size={16} />}
                  className="cursor-pointer hover:opacity-80"
                  onClick={() => {
                    if (['codex-chatgpt', 'antigravity', 'grok-oauth'].includes(selected.id)) return
                    setLocalApiKey('')
                    setCloudflareAccounts([])
                    setCloudflareAccountId('')
                    setShowApiKey(true)
                  }}
                />
              </div>

              {/* ─── Modal de edição de chave ─── */}
              {showApiKey && (
                <div
                  className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
                  onClick={() => setShowApiKey(false)}
                >
                  <div
                    className="rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl"
                    style={{ background: 'var(--bg-primary)' }}
                    onClick={e => e.stopPropagation()}
                  >
                    <h3 className="text-lg font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                      Chave de API — {selected?.name}
                    </h3>
                    <p className="text-xs mb-4" style={{ color: 'var(--text-tertiary)' }}>
                      {selected?.provider_type === 'builtin'
                        ? 'Salva no arquivo de dados. Também pode vir do .env.'
                        : 'Chave do provedor customizado.'}
                    </p>
                    {selected?.api_key_url && (
                      <a
                        href={selected.api_key_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mb-4 inline-flex items-center gap-1.5 text-xs font-semibold hover:underline"
                        style={{ color: 'var(--accent)' }}
                      >
                        <ExternalLink size={12} />
                        Obter uma chave no site oficial
                      </a>
                    )}
                    <input
                      type="password"
                      value={localApiKey}
                      onChange={e => setLocalApiKey(e.target.value)}
                      placeholder={selected?.has_key
                        ? 'Digite uma nova chave para substituir'
                        : isCloudflareSelected ? 'API Token da Cloudflare' : 'sk-...'}
                      className="w-full px-3 py-2 rounded-xl text-sm mb-4 outline-none transition-all border"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                      autoFocus
                    />
                    {isCloudflareSelected && (
                      <div className="mb-4 space-y-3 rounded-xl border p-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
                        <div>
                          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Conta Cloudflare</p>
                          <p className="mt-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                            O chatbot consulta as contas permitidas pelo token e monta a Base URL do Workers AI.
                          </p>
                        </div>
                        {cloudflareAccounts.length > 1 && (
                          <select
                            value={cloudflareAccountId}
                            onChange={event => setCloudflareAccountId(event.target.value)}
                            className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                            style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                          >
                            {cloudflareAccounts.map(account => (
                              <option key={account.id} value={account.id}>{account.name} · {account.id}</option>
                            ))}
                          </select>
                        )}
                        <div>
                          <label className="mb-1 block text-[11px] font-medium" style={{ color: 'var(--text-secondary)' }}>
                            Account ID manual (fallback)
                          </label>
                          <div className="flex gap-2">
                            <input
                              value={cloudflareAccountId}
                              onChange={event => setCloudflareAccountId(event.target.value.trim())}
                              placeholder="a1b2c3d4..."
                              className="min-w-0 flex-1 rounded-lg border px-3 py-2 text-xs outline-none"
                              style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                            />
                            <button
                              type="button"
                              onClick={() => handleDetectCloudflareAccounts(cloudflareAccountId, true)}
                              disabled={detectingCloudflare || !cloudflareAccountId.trim()}
                              className="rounded-lg px-3 py-2 text-xs font-semibold"
                              style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                            >
                              Usar ID
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => setShowApiKey(false)}
                        className="flex-1 px-3 py-2 rounded-xl text-sm font-medium"
                        style={{
                          background: 'var(--bg-secondary)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--border)',
                        }}
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={() => isCloudflareSelected
                          ? handleDetectCloudflareAccounts(cloudflareAccounts.length > 1 ? cloudflareAccountId : '')
                          : handleSaveApiKey()}
                        disabled={isCloudflareSelected
                          ? detectingCloudflare || (!localApiKey.trim() && !selected?.has_key)
                          : savingKey || !localApiKey.trim()}
                        className="flex-1 px-3 py-2 rounded-xl text-sm font-medium text-white transition-all"
                        style={{
                          background: (isCloudflareSelected
                            ? detectingCloudflare || (!localApiKey.trim() && !selected?.has_key)
                            : savingKey || !localApiKey.trim()) ? 'var(--border)' : 'var(--accent)',
                        }}
                      >
                        {isCloudflareSelected
                          ? detectingCloudflare ? 'Detectando...' : cloudflareAccounts.length > 1 ? 'Usar conta' : 'Detectar contas'
                          : savingKey ? 'Salvando...' : 'Salvar'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ─── Botão Testar Provider ─── */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={handleTestProvider}
                  disabled={testingProvider || !selected.enabled || !selected.has_key}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-all hover:opacity-90"
                  style={{
                    background: selected.has_key ? 'var(--accent)' : 'var(--border)',
                    color: selected.has_key ? '#fff' : 'var(--text-tertiary)',
                    cursor: selected.enabled && selected.has_key ? 'pointer' : 'not-allowed',
                  }}
                >
                  {testingProvider ? (
                    <><Loader2 size={14} className="animate-spin" /> Testando...</>
                  ) : (
                    <><RefreshCw size={14} /> Testar Provider</>
                  )}
                </button>
              </div>

              {/* Resultado do teste */}
              {testResult && (
                <div
                  className={`mb-4 p-3 rounded-xl text-sm ${
                    testResult.ok
                      ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                      : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                  }`}
                >
                  {testResult.ok ? (
                    <div className="flex items-center gap-2" style={{ color: '#16a34a' }}>
                      <Check size={16} />
                      <span>
                        <strong>Funcionando!</strong> Latência: {testResult.latency_ms}ms
                        <span className="text-xs ml-2 opacity-70">
                          (fonte: {testResult.source})
                        </span>
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2" style={{ color: '#dc2626' }}>
                      <AlertTriangle size={16} />
                      <span>
                        <strong>Falha:</strong> {testResult.message}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* ─── Modelos ─── */}
              <div className="border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
                  <div>
                    <h4 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                      Modelos ({displayedModels.length}/{selected.models.length})
                    </h4>
                    <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                      Medicao direta, sem agente, skills, RAG ou historico
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex rounded-lg p-0.5" style={{ background: 'var(--bg-tertiary)' }}>
                      <button onClick={() => setModelView('active')} className="rounded-md px-2 py-1 text-[10px] font-semibold" style={{ background: modelView === 'active' ? 'var(--bg-primary)' : 'transparent', color: 'var(--text-primary)' }}>
                        Ativos ({selected.models.filter(model => model.enabled).length})
                      </button>
                      <button onClick={() => setModelView('hidden')} className="rounded-md px-2 py-1 text-[10px] font-semibold" style={{ background: modelView === 'hidden' ? 'var(--bg-primary)' : 'transparent', color: 'var(--text-primary)' }}>
                        Ocultos ({selected.models.filter(model => !model.enabled).length})
                      </button>
                    </div>
                    {isAdmin && !['antigravity', 'codex-chatgpt', 'grok-oauth'].includes(selected.id) && (
                      <button
                        onClick={() => void handleSyncCatalog(selected.id)}
                        disabled={syncingCatalog}
                        className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium disabled:opacity-50"
                        style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                        title="Buscar a lista atual no Models.dev; novos entram em Ocultos"
                      >
                        <RefreshCw size={12} className={syncingCatalog ? 'animate-spin' : ''} /> Sincronizar
                      </button>
                    )}
                    <button
                      onClick={handleBenchmarkAll}
                      disabled={!selected.enabled || benchmarkingAll || !selected.models.some(model => model.enabled)}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: '#f97316', color: '#fff' }}
                      title="Faz uma chamada real por modelo, em sequencia"
                    >
                      {benchmarkingAll ? <Loader2 size={12} className="animate-spin" /> : <Gauge size={12} />}
                      {benchmarkingAll ? 'Testando todos...' : 'Testar todos'}
                    </button>
                    {selected.id !== 'antigravity' && (
                      <button
                        onClick={() => { setShowAddModel(true); setEditingModelId(null); setModelFormName(''); setModelFormId(''); setModelFormCtx('128000') }}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
                        style={{ background: 'var(--accent)', color: '#fff' }}
                      >
                        <Plus size={12} />
                        Add Model
                      </button>
                    )}
                  </div>
                </div>

                {benchmarkRanking.length > 0 && (
                  <div className="border-b px-4 py-2 text-xs" style={{ borderColor: 'var(--border)', background: 'rgba(249,115,22,0.08)', color: 'var(--text-secondary)' }}>
                    <strong style={{ color: '#f97316' }}>Mais rapido:</strong>{' '}
                    {benchmarkRanking.slice(0, 3).map((result, index) => (
                      <span key={result.model} className="mr-3 inline-flex items-center gap-1">
                        <AIProviderIcon provider={`${selected.name} ${selected.id}`} model={`${result.model_name} ${result.model}`} size={13} />
                        #{index + 1} {result.model_name} ({result.ttft_ms}ms)
                      </span>
                    ))}
                  </div>
                )}

                <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
                  {displayedModels.length === 0 ? (
                    <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
                      {modelView === 'hidden' ? 'Nenhum modelo oculto.' : 'Nenhum modelo ativo. Abra Ocultos para habilitar um.'}
                    </div>
                  ) : (
                    displayedModels.map(model => (
                      <ModelRow
                        key={model.id}
                        model={model}
                        provider={`${selected.name} ${selected.id}`}
                        isBuiltin={selected.provider_type === 'builtin'}
                        readOnly={selected.id === 'antigravity'}
                        providerEnabled={selected.enabled}
                        onToggle={() => handleToggleModel(model.id, model.enabled)}
                        onSelect={() => handleSelectModel(model.id, selected.id)}
                        onEdit={() => handleEditModel(model)}
                        onDelete={() => handleDeleteModel(model.id)}
                        onBenchmark={() => runModelBenchmark(model.id)}
                        benchmarking={!!benchmarkingModels[model.id]}
                        benchmark={benchmarkResults[model.id]}
                        benchmarkRank={benchmarkRankByModel.get(model.id)}
                      />
                    ))
                  )}
                </div>
              </div>

              {/* ─── Codex ChatGPT: Pool de Contas ─── */}
              {selected.id === 'codex-chatgpt' && isAdmin && <CodexAccountPanel providerId={selected.id} />}
              {selected.id === 'antigravity' && <AntigravityAccountPanel onModelsUpdated={loadProviders} />}
              {selected.id === 'grok-oauth' && <GrokAccountPanel onModelsUpdated={loadProviders} />}

              {/* Add Model Form */}
              {showAddModel && (
                <div
                  className="mt-4 p-4 rounded-xl border"
                  style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                >
                  <h5 className="font-medium text-sm mb-3" style={{ color: 'var(--text-primary)' }}>
                    {editingModelId ? 'Edit Model' : 'Add Model'}
                  </h5>
                  <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Model ID</label>
                      <input
                        type="text"
                        value={modelFormId}
                        onChange={e => setModelFormId(e.target.value)}
                        placeholder="my-model"
                        className="w-full px-2.5 py-1.5 rounded-lg border text-sm font-mono"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Display Name</label>
                      <input
                        type="text"
                        value={modelFormName}
                        onChange={e => setModelFormName(e.target.value)}
                        placeholder="My Model"
                        className="w-full px-2.5 py-1.5 rounded-lg border text-sm"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>Context Length</label>
                      <input
                        type="text"
                        value={modelFormCtx}
                        onChange={e => setModelFormCtx(e.target.value)}
                        placeholder="128000"
                        className="w-full px-2.5 py-1.5 rounded-lg border text-sm font-mono"
                        style={{
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)',
                          borderColor: 'var(--border)',
                        }}
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setShowAddModel(false); setEditingModelId(null) }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium border"
                      style={{
                        color: 'var(--text-secondary)',
                        borderColor: 'var(--border)',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleAddModel}
                      disabled={saving}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: 'var(--accent)' }}
                    >
                      {saving ? 'Saving...' : editingModelId ? 'Update' : 'Add'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* ─── Estado vazio ─── */
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Server size={48} style={{ color: 'var(--text-tertiary)' }} />
                <h3 className="text-lg font-bold mt-4 mb-1" style={{ color: 'var(--text-primary)' }}>
                  Select a Provider
                </h3>
                <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
                  Choose a provider from the sidebar to view or edit its configuration
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
      {showExportDialog && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60"
          onClick={() => !exportingProviders && setShowExportDialog(false)}
        >
          <div
            className="w-full max-w-md mx-4 rounded-2xl border p-6 shadow-2xl"
            style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h3 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  Exportar providers
                </h3>
                <p className="text-sm mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  O arquivo inclui providers customizados e os seus providers pessoais.
                </p>
              </div>
              <button
                onClick={() => setShowExportDialog(false)}
                disabled={exportingProviders}
                className="p-1 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => handleExportProviders(false)}
                disabled={exportingProviders}
                className="w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all hover:opacity-90 disabled:opacity-50"
                style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <Download size={20} style={{ color: 'var(--accent)' }} />
                <span>
                  <span className="block text-sm font-semibold">Exportar sem API keys</span>
                  <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    Seguro para compartilhar ou versionar.
                  </span>
                </span>
              </button>

              <button
                onClick={() => handleExportProviders(true)}
                disabled={exportingProviders}
                className="w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all hover:opacity-90 disabled:opacity-50"
                style={{ borderColor: '#f59e0b', color: 'var(--text-primary)', background: '#f59e0b12' }}
              >
                {exportingProviders
                  ? <Loader2 size={20} className="animate-spin" style={{ color: '#d97706' }} />
                  : <Eye size={20} style={{ color: '#d97706' }} />}
                <span>
                  <span className="block text-sm font-semibold">Exportar com API keys</span>
                  <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    Inclui suas chaves pessoais. Chaves globais entram somente para admins.
                  </span>
                </span>
              </button>

              {isAdmin && (
                <button
                  onClick={handleExportAdminBackup}
                  disabled={exportingProviders}
                  className="w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all hover:opacity-90 disabled:opacity-50"
                  style={{ borderColor: '#dc2626', color: 'var(--text-primary)', background: '#dc262612' }}
                >
                  {exportingProviders
                    ? <Loader2 size={20} className="animate-spin" style={{ color: '#dc2626' }} />
                    : <AlertTriangle size={20} style={{ color: '#dc2626' }} />}
                  <span>
                    <span className="block text-sm font-semibold">Backup completo do administrador</span>
                    <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                      Todas as chaves e contas OAuth do Codex e Antigravity.
                    </span>
                  </span>
                </button>
              )}
            </div>

            <div className="mt-4 flex items-start gap-2 text-xs" style={{ color: '#d97706' }}>
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
              Guarde arquivos com chaves em local seguro. Eles contêm credenciais em texto legível.
            </div>
          </div>
        </div>
      )}
    </div>
  )
})

// ─── Componentes auxiliares ─────────────────────────────────────────

function ProviderVisualIcon({ provider, model, size = 18, className }: {
  provider: string
  model?: string
  size?: number
  className?: string
}) {
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${className || ''}`} style={{ width: size, height: size }}>
      <AIProviderIcon provider={provider} model={model} size={size} />
    </span>
  )
}

function CatalogProviderPanel({
  provider, models, loading, query, onQueryChange, configuredProvider, isAdmin,
  refreshing, syncing, onRefresh, onSync, onConfigure,
}: {
  provider: CatalogProviderInfo
  models: CatalogModelInfo[]
  loading: boolean
  query: string
  onQueryChange: (value: string) => void
  configuredProvider: ProviderInfo | null
  isAdmin: boolean
  refreshing: boolean
  syncing: boolean
  onRefresh: () => void
  onSync: () => void
  onConfigure: () => void
}) {
  const needle = query.trim().toLowerCase()
  const visible = models.filter(model => !needle || `${model.name} ${model.id} ${model.family || ''}`.toLowerCase().includes(needle))
  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <ProviderVisualIcon provider={`${provider.name} ${provider.id}`} size={32} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{provider.name}</h3>
              <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>CATALOGO</span>
            </div>
            <p className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{provider.id} · {provider.model_count} modelos</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {provider.doc && (
            <a href={provider.doc} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold" style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}>
              <ExternalLink size={13} /> Documentacao
            </a>
          )}
          {isAdmin && (
            <button onClick={onRefresh} disabled={refreshing} className="flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-50" style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}>
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> Atualizar catalogo
            </button>
          )}
          {isAdmin && configuredProvider && (
            <button onClick={onSync} disabled={syncing} className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>
              {syncing ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Sincronizar modelos
            </button>
          )}
          {isAdmin && !configuredProvider && (
            <button onClick={onConfigure} disabled={loading} className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>
              <Plus size={13} /> Configurar provider
            </button>
          )}
        </div>
      </div>

      <div className="mb-4 rounded-xl border p-3 text-xs" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--text-primary)' }}>Biblioteca mundial:</strong>{' '}
        estes modelos sao referencias do Models.dev. Eles nao entram no chat ate o provider estar configurado e o modelo ser habilitado.
        {!configuredProvider && <span className="mt-1 block" style={{ color: '#d97706' }}>Este provider ainda nao esta configurado neste sistema.</span>}
      </div>

      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-2.5" style={{ color: 'var(--text-tertiary)' }} />
        <input value={query} onChange={event => onQueryChange(event.target.value)} placeholder="Buscar modelo, familia ou ID..." className="w-full rounded-xl border py-2 pl-9 pr-3 text-sm" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }} />
      </div>

      <div className="overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border)' }}>
        <div className="border-b px-4 py-3 text-sm font-semibold" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}>
          Modelos no mundo ({visible.length})
        </div>
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 size={22} className="animate-spin" /></div>
        ) : visible.length === 0 ? (
          <p className="p-6 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>Nenhum modelo encontrado.</p>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {visible.map(model => (
              <div key={model.id} className="flex items-start gap-3 px-4 py-3">
                <ProviderVisualIcon provider={`${provider.name} ${provider.id}`} model={`${model.name} ${model.id}`} size={18} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{model.name}</span>
                    {model.supports_images && <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: '#f3e8ff', color: '#7e22ce' }}>Visao</span>}
                    {model.supports_thinking && <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: '#ffedd5', color: '#c2410c' }}>Thinking</span>}
                    {model.supports_tools && <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: '#dbeafe', color: '#1d4ed8' }}>Tools</span>}
                  </div>
                  <p className="break-all font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{model.id}</p>
                </div>
                <div className="shrink-0 text-right text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                  {model.context_length > 0 && <div>{Math.round(model.context_length / 1000)}K ctx</div>}
                  {model.last_updated && <div>{model.last_updated}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ProviderItem({
  provider, selected, dragging = false, onClick, onEdit, onDelete, onDragStart, onDragEnd, onDrop,
}: {
  provider: ProviderInfo
  selected: boolean
  dragging?: boolean
  onClick: () => void
  onEdit?: () => void
  onDelete?: () => void
  onDragStart?: () => void
  onDragEnd?: () => void
  onDrop?: () => void
}) {
  return (
    <div
      draggable
      onDragStart={event => {
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', provider.id)
        onDragStart?.()
      }}
      onDragOver={event => {
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
      }}
      onDrop={event => {
        event.preventDefault()
        onDrop?.()
      }}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className="group flex cursor-pointer items-center gap-1.5 rounded-xl border px-2 py-2 transition-all"
      style={{
        background: provider.active ? 'rgba(22, 163, 74, 0.10)' : selected ? 'var(--accent-light)' : 'transparent',
        borderColor: provider.active ? '#16a34a' : 'transparent',
        boxShadow: provider.active ? '0 0 0 1px rgba(22, 163, 74, 0.18)' : 'none',
        color: provider.active ? 'var(--text-primary)' : selected ? 'var(--accent)' : 'var(--text-primary)',
        opacity: dragging ? 0.45 : 1,
      }}
      onMouseEnter={e => { if (!selected && !provider.active) (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)' }}
      onMouseLeave={e => { if (!selected && !provider.active) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    >
      <GripVertical
        size={14}
        className="shrink-0 cursor-grab opacity-35 transition-opacity group-hover:opacity-80 active:cursor-grabbing"
        style={{ color: 'var(--text-tertiary)' }}
        aria-label="Arrastar para reordenar"
      />
      {/* Status dot */}
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ background: provider.enabled ? '#16a34a' : '#a1a1aa' }}
      />

      <ProviderVisualIcon provider={`${provider.name} ${provider.id}`} size={19} className="flex-shrink-0" />

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{provider.name}</p>
        <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
          {provider.models.length} models · {provider.provider_type}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
        {provider.provider_type === 'custom' && onEdit && (
          <button onClick={onEdit} className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10" title="Edit">
            <Pencil size={12} />
          </button>
        )}
        {provider.provider_type === 'custom' && onDelete && (
          <button onClick={onDelete} className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30" title="Delete">
            <Trash2 size={12} style={{ color: '#dc2626' }} />
          </button>
        )}
      </div>
    </div>
  )
}

function ModelRow({
  model, provider, isBuiltin, readOnly = false, providerEnabled = true, onToggle, onSelect, onEdit, onDelete,
  onBenchmark, benchmarking = false, benchmark, benchmarkRank,
}: {
  model: ModelInfo
  provider: string
  isBuiltin: boolean
  readOnly?: boolean
  providerEnabled?: boolean
  onToggle: () => void
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
  onBenchmark: () => void
  benchmarking?: boolean
  benchmark?: BenchmarkResult
  benchmarkRank?: number
}) {
  const ctxLabel = model.context_length >= 1000000
    ? `${(model.context_length / 1000000).toFixed(0)}M`
    : model.context_length >= 1000
      ? `${(model.context_length / 1000).toFixed(0)}K`
      : String(model.context_length)

  const isActive = model.active === true
  const statusLabels: Record<string, { label: string, background: string, color: string }> = {
    oficial: { label: 'Oficial', background: '#dcfce7', color: '#15803d' },
    'confirmar no provider': { label: 'Confirmar', background: '#fef3c7', color: '#a16207' },
    'nao confirmado na lista publica atual': { label: 'Nao confirmado', background: '#fee2e2', color: '#b91c1c' },
  }
  const status = model.status ? statusLabels[model.status] : null

  return (
    <div className="flex flex-col gap-2 px-3 py-3 transition-colors hover:bg-black/5 dark:hover:bg-white/5 sm:flex-row sm:items-center sm:justify-between sm:px-4"
      style={{
        background: isActive ? 'var(--accent-light)' : 'transparent',
        borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
      }}>
      <div className="flex min-w-0 flex-1 items-start gap-2 sm:items-center sm:gap-3">
        <ProviderVisualIcon
          provider={provider}
          model={`${model.name} ${model.id}`}
          size={18}
          className="mt-1 shrink-0 sm:mt-0"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {model.name}
            </p>
            {isActive && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                style={{ background: '#dcfce7', color: '#16a34a' }}>
                ACTIVE
              </span>
            )}
            {status && (
              <span
                className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                style={{ background: status.background, color: status.color }}
                title={model.status}
              >
                {status.label}
              </span>
            )}
            {model.validation_status === 'working' && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: '#dcfce7', color: '#15803d' }}>
                Testado
              </span>
            )}
            {model.validation_status === 'failed' && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: '#fee2e2', color: '#b91c1c' }}>
                Falhou
              </span>
            )}
            {model.recommended && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: '#dbeafe', color: '#1d4ed8' }}>
                Recomendado
              </span>
            )}
            {model.supports_images && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: '#f3e8ff', color: '#7e22ce' }}>
                Visão
              </span>
            )}
            {model.supports_thinking && model.thinking_stream !== false && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: '#ffedd5', color: '#c2410c' }}>
                Thinking
              </span>
            )}
            {model.supports_thinking && model.thinking_stream === false && (
              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                title="O modelo raciocina internamente, mas este endpoint não transmite o texto do pensamento"
              >
                Thinking interno
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            <span className="break-all font-mono">{model.id}</span>
            {model.alias && <span>alias: {model.alias}</span>}
          </div>
          {model.usage && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {model.usage}
            </p>
          )}
          {!benchmarking && !benchmark && model.validation_status === 'failed' && model.validation_error && (
            <p className="mt-1 break-words text-xs" style={{ color: '#dc2626' }}>
              Ultimo teste: {model.validation_error}
            </p>
          )}
          {benchmarking && (
            <div className="mt-1 flex items-center gap-1.5 text-xs" style={{ color: '#f97316' }}>
              <Loader2 size={12} className="animate-spin" />
              Medindo chamada direta...
            </div>
          )}
          {!benchmarking && benchmark?.ok && (
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: '#16a34a' }}>
              {benchmarkRank && <strong>#{benchmarkRank}{benchmarkRank === 1 ? ' mais rapido' : ''}</strong>}
              <span>Primeiro texto: <strong>{benchmark.ttft_ms}ms</strong></span>
              <span>Total: <strong>{benchmark.total_ms}ms</strong></span>
              <span>Saida: <strong>{benchmark.chars_per_second} chars/s</strong></span>
            </div>
          )}
          {!benchmarking && benchmark && !benchmark.ok && (
            <p className="mt-1 break-words text-xs" style={{ color: '#dc2626' }}>
              Falhou: {benchmark.message || 'erro desconhecido'}
            </p>
          )}
        </div>
        <span
          className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-mono"
          style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
        >
          {ctxLabel}
        </span>
      </div>
      <div className="flex items-center justify-end gap-1 border-t pt-2 sm:border-0 sm:pt-0" style={{ borderColor: 'var(--border)' }}>
        {model.enabled && (
          <button
            onClick={onBenchmark}
            disabled={benchmarking || !providerEnabled}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
            style={{ background: 'rgba(249,115,22,0.14)', color: '#f97316' }}
            title="Medir este modelo sem passar pelo agente"
          >
            {benchmarking ? <Loader2 size={12} className="animate-spin" /> : <Gauge size={12} />}
            Testar
          </button>
        )}
        {model.enabled && (
          <button
            onClick={onSelect}
            className="px-2 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
            style={{
              background: isActive ? '#16a34a' : 'var(--accent)',
              color: '#fff',
              opacity: isActive || !providerEnabled ? 0.45 : 1,
              cursor: !providerEnabled ? 'not-allowed' : 'pointer',
            }}
            title={isActive ? 'Já está ativo' : 'Usar este modelo'}
            disabled={isActive || !providerEnabled}
          >
            {isActive ? '✓ Ativo' : 'Usar'}
          </button>
        )}
        {!readOnly && (
          <>
            <button
              onClick={onToggle}
              className={`p-1.5 rounded-lg transition-colors ${model.enabled ? 'hover:bg-red-100 dark:hover:bg-red-900/30' : 'hover:bg-green-100 dark:hover:bg-green-900/30'}`}
              title={model.enabled ? 'Disable' : 'Enable'}
            >
              {model.enabled
                ? <Power size={14} style={{ color: '#16a34a' }} />
                : <PowerOff size={14} style={{ color: 'var(--text-tertiary)' }} />
              }
            </button>
            <button
              onClick={onEdit}
              className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
              title="Edit model"
            >
              <Pencil size={14} style={{ color: 'var(--text-secondary)' }} />
            </button>
          </>
        )}
        {!isBuiltin && (
          <button
            onClick={onDelete}
            className="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            title="Delete model"
          >
            <Trash2 size={14} style={{ color: '#dc2626' }} />
          </button>
        )}
      </div>
    </div>
  )
}

function InfoCard({ label, value, icon, className, onClick }: {
  label: string
  value: string
  icon: React.ReactNode
  className?: string
  onClick?: () => void
}) {
  return (
    <div
      className={'flex items-center gap-3 px-4 py-3 rounded-xl border ' + (className || '')}
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', cursor: onClick ? 'pointer' : undefined }}
      onClick={onClick}
    >
      <div style={{ color: 'var(--text-tertiary)' }}>{icon}</div>
      <div>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{value}</p>
      </div>
    </div>
  )
}

// ─── Type for Codex Account ─────────────────────────────────────

interface AntigravityAccountInfo {
  id: string
  email: string
  label: string
  account_type?: string
  selected: boolean
  enabled: boolean
  model_count: number
  quotas?: Array<{ remaining_fraction?: number; reset_time?: string; models?: string[] }>
}

function AntigravityAccountPanel({ onModelsUpdated }: { onModelsUpdated: () => void }) {
  const [accounts, setAccounts] = useState<AntigravityAccountInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [oauth, setOauth] = useState<{ requestId: string; authUrl: string } | null>(null)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [finishing, setFinishing] = useState(false)
  const [importing, setImporting] = useState(false)

  const loadAccounts = useCallback(async () => {
    setLoading(true)
    try {
      setAccounts(await apiReq<AntigravityAccountInfo[]>(`${API}/antigravity/accounts`))
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadAccounts() }, [loadAccounts])

  const startLogin = async () => {
    try {
      const result = await apiReq<{ request_id: string; auth_url: string }>(`${API}/antigravity/oauth/start`, { method: 'POST' })
      setOauth({ requestId: result.request_id, authUrl: result.auth_url })
      setCallbackUrl('')
      window.open(result.auth_url, '_blank', 'noopener,noreferrer')
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  const finishLogin = async () => {
    if (!oauth || !callbackUrl.trim()) return
    setFinishing(true)
    try {
      await apiReq(`${API}/antigravity/oauth/finish`, {
        method: 'POST',
        body: JSON.stringify({ request_id: oauth.requestId, callback_url: callbackUrl.trim() }),
      })
      setOauth(null)
      setCallbackUrl('')
      await loadAccounts()
      toast.success('Conta Antigravity conectada')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setFinishing(false)
    }
  }

  const importAuth = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json,application/json'
    input.onchange = async event => {
      const file = (event.target as HTMLInputElement).files?.[0]
      if (!file) return
      setImporting(true)
      try {
        await apiReq(`${API}/antigravity/import-auth`, {
          method: 'POST',
          body: JSON.stringify(JSON.parse(await file.text())),
        })
        await loadAccounts()
        toast.success('auth.json do Antigravity importado')
      } catch (err: any) {
        toast.error(err.message || 'JSON invalido')
      } finally {
        setImporting(false)
      }
    }
    input.click()
  }

  const sync = async (accountId: string) => {
    setSyncing(accountId)
    try {
      const result = await apiReq<{ models: ModelInfo[] }>(`${API}/antigravity/accounts/${accountId}/sync`, { method: 'POST' })
      await loadAccounts()
      onModelsUpdated()
      toast.success(`${result.models?.length || 0} modelos sincronizados`)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setSyncing(null)
    }
  }

  const select = async (accountId: string) => {
    try {
      await apiReq(`${API}/antigravity/accounts/${accountId}/select`, { method: 'POST' })
      await loadAccounts()
      toast.success('Conta selecionada')
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  const remove = async (accountId: string) => {
    if (!confirm('Remover esta conta Antigravity?')) return
    try {
      await apiReq(`${API}/antigravity/accounts/${accountId}`, { method: 'DELETE' })
      await loadAccounts()
      toast.success('Conta removida')
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  return (
    <div className="mt-6 overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
        <div className="flex items-center gap-2">
          <AIProviderIcon provider="Antigravity" size={18} />
          <h4 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Antigravity Accounts</h4>
          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: accounts.length ? '#dcfce7' : '#fef2f2', color: accounts.length ? '#16a34a' : '#dc2626' }}>
            {accounts.length} conta{accounts.length === 1 ? '' : 's'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={importAuth} disabled={importing} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium" style={{ background: 'var(--bg-primary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} Import auth.json
          </button>
          <button onClick={startLogin} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-white" style={{ background: '#16a34a' }}>
            <Plus size={12} /> Conectar Google
          </button>
        </div>
      </div>

      {loading && <div className="p-8 text-center"><Loader2 size={20} className="inline animate-spin" /></div>}
      {!loading && !accounts.length && (
        <div className="px-4 py-8 text-center" style={{ color: 'var(--text-tertiary)' }}>
          <User size={32} className="mx-auto mb-2" />
          <p className="text-sm">Conecte sua conta Google ou importe o auth.json do antigravity_terminal.</p>
        </div>
      )}
      {!loading && accounts.map(account => {
        const quota = account.quotas?.find(item => typeof item.remaining_fraction === 'number')
        const quotaPct = Math.round((quota?.remaining_fraction || 0) * 100)
        return (
          <div key={account.id} className="border-b px-4 py-3 last:border-b-0" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: account.selected ? '#16a34a' : 'var(--text-tertiary)' }} />
                  <span className="truncate text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{account.label || account.email}</span>
                  {account.selected && <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-bold text-green-700">ATIVA</span>}
                </div>
                <p className="mt-1 truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>{account.email}</p>
                <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>{account.account_type || 'Plano nao sincronizado'} · {account.model_count} modelos</p>
                {quota && <div className="mt-2 w-72 max-w-full"><QuotaBar label="Cota" value={quotaPct} maxValue={100} color="#3b82f6" /></div>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {!account.selected && <button onClick={() => select(account.id)} className="rounded-lg px-2 py-1 text-xs font-semibold" style={{ background: 'var(--accent)', color: '#fff' }}>Usar</button>}
                <button onClick={() => sync(account.id)} disabled={syncing === account.id} className="grid h-8 w-8 place-items-center rounded-lg hover:bg-black/10 dark:hover:bg-white/10" title="Sincronizar modelos e cota">
                  <RefreshCw size={14} className={syncing === account.id ? 'animate-spin' : ''} />
                </button>
                <button onClick={() => remove(account.id)} className="grid h-8 w-8 place-items-center rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30" title="Remover conta"><Trash2 size={14} className="text-red-600" /></button>
              </div>
            </div>
          </div>
        )
      })}

      {oauth && (
        <div className="border-t p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          <p className="mb-2 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Concluir login Google</p>
          <p className="mb-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Depois de autorizar, localhost pode nao abrir. Copie a URL completa da barra do navegador e cole abaixo.
          </p>
          <a href={oauth.authUrl} target="_blank" rel="noopener noreferrer" className="mb-3 inline-block text-xs underline" style={{ color: 'var(--accent)' }}>Abrir login novamente</a>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input value={callbackUrl} onChange={event => setCallbackUrl(event.target.value)} placeholder="http://localhost:51121/oauth-callback?code=..." className="min-w-0 flex-1 rounded-lg border px-3 py-2 text-xs" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }} />
            <button onClick={finishLogin} disabled={finishing || !callbackUrl.trim()} className="rounded-lg px-4 py-2 text-xs font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>
              {finishing ? 'Conectando...' : 'Concluir'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface GrokAccountInfo {
  id: string
  email: string
  label: string
  expires_at: number
  access_status: 'unknown' | 'confirmed' | 'blocked' | 'rate_limited' | 'error'
  last_error?: string
  selected: boolean
  enabled: boolean
  has_refresh_token: boolean
}

function GrokAccountPanel({ onModelsUpdated }: { onModelsUpdated: () => void }) {
  const [accounts, setAccounts] = useState<GrokAccountInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [device, setDevice] = useState<{
    requestId: string
    userCode: string
    verificationUri: string
    verificationUriComplete: string
    interval: number
  } | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadAccounts = useCallback(async () => {
    setLoading(true)
    try {
      setAccounts(await apiReq<GrokAccountInfo[]>(`${API}/grok/accounts`))
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAccounts()
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [loadAccounts])

  const schedulePoll = useCallback((requestId: string, delaySeconds: number) => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    pollTimerRef.current = setTimeout(async () => {
      try {
        const result = await apiReq<{ status: string; retry_after?: number; message?: string }>(`${API}/grok/oauth/device/poll/${requestId}`, { method: 'POST' })
        if (result.status === 'saved') {
          setDevice(null)
          setConnecting(false)
          await loadAccounts()
          toast.success('Conta Grok conectada. Teste o acesso aos modelos.')
          return
        }
        if (result.status === 'pending') {
          schedulePoll(requestId, result.retry_after || delaySeconds)
          return
        }
        setDevice(null)
        setConnecting(false)
        toast.error(result.message || 'Login do Grok nao concluido')
      } catch (err: any) {
        setDevice(null)
        setConnecting(false)
        toast.error(err.message)
      }
    }, Math.max(3, delaySeconds) * 1000)
  }, [loadAccounts])

  const connect = async () => {
    setConnecting(true)
    try {
      const result = await apiReq<{
        request_id: string
        user_code: string
        verification_uri: string
        verification_uri_complete?: string
        interval: number
      }>(`${API}/grok/oauth/device/start`, { method: 'POST' })
      const next = {
        requestId: result.request_id,
        userCode: result.user_code,
        verificationUri: result.verification_uri,
        verificationUriComplete: result.verification_uri_complete || '',
        interval: result.interval || 5,
      }
      setDevice(next)
      window.open(next.verificationUriComplete || next.verificationUri, '_blank', 'noopener,noreferrer')
      schedulePoll(next.requestId, next.interval)
    } catch (err: any) {
      setConnecting(false)
      toast.error(err.message)
    }
  }

  const select = async (accountId: string) => {
    setWorkingId(accountId)
    try {
      await apiReq(`${API}/grok/accounts/${accountId}/select`, { method: 'POST' })
      await loadAccounts()
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setWorkingId(null)
    }
  }

  const testAccess = async (accountId: string) => {
    setWorkingId(accountId)
    try {
      const result = await apiReq<{ models: string[]; access_status?: string; message?: string }>(`${API}/grok/accounts/${accountId}/test`, { method: 'POST' })
      await Promise.all([loadAccounts(), onModelsUpdated()])
      if (result.access_status === 'rate_limited') toast(result.message || 'Grok temporariamente sem capacidade')
      else toast.success(result.message || 'Acesso ao Grok confirmado')
    } catch (err: any) {
      await loadAccounts()
      toast.error(err.message)
    } finally {
      setWorkingId(null)
    }
  }

  const refresh = async (accountId: string) => {
    setWorkingId(accountId)
    try {
      await apiReq(`${API}/grok/accounts/${accountId}/refresh`, { method: 'POST' })
      await loadAccounts()
      toast.success('Token Grok renovado')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setWorkingId(null)
    }
  }

  const remove = async (accountId: string) => {
    if (!confirm('Remover esta conta Grok?')) return
    setWorkingId(accountId)
    try {
      await apiReq(`${API}/grok/accounts/${accountId}`, { method: 'DELETE' })
      await loadAccounts()
      toast.success('Conta Grok removida')
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setWorkingId(null)
    }
  }

  const accessLabel = (status: GrokAccountInfo['access_status']) => ({
    confirmed: ['Acesso confirmado', '#16a34a', '#dcfce7'],
    blocked: ['Bloqueado pela xAI', '#dc2626', '#fef2f2'],
    rate_limited: ['Limite temporario', '#d97706', '#ffedd5'],
    error: ['Erro de acesso', '#dc2626', '#fef2f2'],
    unknown: ['Acesso nao testado', '#64748b', '#e2e8f0'],
  }[status] || ['Acesso nao testado', '#64748b', '#e2e8f0'])

  return (
    <div className="mt-6 overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
        <div className="flex items-center gap-2">
          <AIProviderIcon provider="xAI Grok" size={19} />
          <h4 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Contas Grok OAuth</h4>
          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: accounts.length ? '#dcfce7' : '#fef2f2', color: accounts.length ? '#16a34a' : '#dc2626' }}>
            {accounts.length} conta{accounts.length === 1 ? '' : 's'}
          </span>
        </div>
        <button onClick={connect} disabled={connecting} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>
          {connecting ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Conectar conta Grok
        </button>
      </div>

      {device && (
        <div className="border-b p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Autorize sua conta na xAI</p>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>Abra a pagina e informe este codigo. O painel verifica automaticamente quando terminar.</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button onClick={() => void navigator.clipboard.writeText(device.userCode)} className="rounded-xl border px-4 py-2 font-mono text-lg font-bold tracking-[0.25em]" style={{ borderColor: 'var(--border)', color: 'var(--text-primary)', background: 'var(--bg-primary)' }} title="Copiar codigo">
              {device.userCode}
            </button>
            <a href={device.verificationUriComplete || device.verificationUri} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-white" style={{ background: 'var(--accent)' }}>
              <ExternalLink size={13} /> Abrir autorizacao
            </a>
            <span className="inline-flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-tertiary)' }}><Loader2 size={13} className="animate-spin" /> Aguardando autorizacao</span>
          </div>
        </div>
      )}

      {loading && <div className="p-8 text-center"><Loader2 size={20} className="inline animate-spin" /></div>}
      {!loading && !accounts.length && !device && (
        <div className="px-4 py-8 text-center" style={{ color: 'var(--text-tertiary)' }}>
          <User size={32} className="mx-auto mb-2" />
          <p className="text-sm">Nenhuma conta Grok conectada.</p>
          <p className="mt-1 text-xs">A autenticacao pode funcionar mesmo quando a xAI nao libera inferencia; teste o acesso depois de conectar.</p>
        </div>
      )}
      {!loading && accounts.map(account => {
        const [statusText, statusColor, statusBackground] = accessLabel(account.access_status)
        const busy = workingId === account.id
        return (
          <div key={account.id} className="border-b px-4 py-3 last:border-b-0" style={{ borderColor: 'var(--border)' }}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: account.selected ? '#16a34a' : 'var(--text-tertiary)' }} />
                  <span className="truncate text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{account.label || account.email || 'Conta Grok'}</span>
                  {account.selected && <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-bold text-green-700">ATIVA</span>}
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ color: statusColor, background: statusBackground }}>{statusText}</span>
                </div>
                {account.email && <p className="mt-1 truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>{account.email}</p>}
                <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  OAuth conectado · {account.has_refresh_token ? 'renovacao automatica' : 'sem refresh token'}
                </p>
                {account.last_error && <p className="mt-1 max-w-2xl truncate text-[11px] text-red-600" title={account.last_error}>{account.last_error}</p>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {!account.selected && <button onClick={() => select(account.id)} disabled={busy} className="rounded-lg px-2 py-1 text-xs font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>Usar</button>}
                <button onClick={() => testAccess(account.id)} disabled={busy} className="rounded-lg px-2 py-1 text-xs font-semibold disabled:opacity-50" style={{ background: '#16a34a', color: '#fff' }}>{busy ? 'Aguarde...' : 'Testar acesso'}</button>
                <button onClick={() => refresh(account.id)} disabled={busy || !account.has_refresh_token} className="grid h-8 w-8 place-items-center rounded-lg disabled:opacity-40" title="Renovar token"><RefreshCw size={14} className={busy ? 'animate-spin' : ''} /></button>
                <button onClick={() => remove(account.id)} disabled={busy} className="grid h-8 w-8 place-items-center rounded-lg text-red-600 disabled:opacity-40" title="Remover conta"><Trash2 size={14} /></button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface CodexAccountInfo {
  id: string
  label?: string
  email?: string
  access_token?: string
  refresh_token?: string
  expires_at?: number
  quota_5h?: number
  quota_weekly?: number
  quota_5h_pct?: number
  quota_weekly_pct?: number
  enabled?: boolean
}

interface PoolStats {
  total_accounts: number
  enabled_accounts: number
  expired_tokens: number
  quotas_5h: number[]
  strategy: string
}

// ─── Componente do Pool Codex ────────────────────────────────────

function CodexAccountPanel({ providerId }: { providerId: string }) {
  const [accounts, setAccounts] = useState<CodexAccountInfo[]>([])
  const [stats, setStats] = useState<PoolStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [quotaLoading, setQuotaLoading] = useState(false)
  const [showDeviceCode, setShowDeviceCode] = useState(false)
  const [deviceCode, setDeviceCode] = useState('')
  const [verificationUri, setVerificationUri] = useState('')
  const [deviceLoading, setDeviceLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const autoQuotaRef = useRef<string | null>(null)

  const loadAccounts = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [accs, st] = await Promise.all([
        apiReq<CodexAccountInfo[]>(`${API}/codex/pool/${providerId}`),
        apiReq<PoolStats>(`${API}/codex/pool/${providerId}/stats`),
      ])
      setAccounts(accs || [])
      setStats(st || null)
      return accs || []
    } catch (err: any) {
      console.error('Erro ao carregar pool:', err)
      return []
    } finally {
      if (!silent) setLoading(false)
    }
  }, [providerId])

  const refreshQuota = useCallback(async (silent = false) => {
    if (!silent) setQuotaLoading(true)
    try {
      await apiReq(`${API}/codex/pool/${providerId}/update-quota`, { method: 'POST' })
      if (!silent) toast.success('Cota atualizada!')
      await loadAccounts(true)
    } catch (err: any) {
      if (!silent) toast.error(err.message)
      console.error('Erro ao atualizar cota:', err)
    } finally {
      if (!silent) setQuotaLoading(false)
    }
  }, [providerId, loadAccounts])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const accs = await loadAccounts(false)
      // Ao abrir o painel, atualiza quota uma vez em background.
      // Não bloqueia UI e não depende do botão "Quota".
      if (!cancelled && accs.length > 0 && autoQuotaRef.current !== providerId) {
        autoQuotaRef.current = providerId
        refreshQuota(true)
      }
    })()
    const interval = setInterval(() => loadAccounts(true), 30000) // refresh leve a cada 30s
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [providerId, loadAccounts, refreshQuota])

  // ─── Device Code ───────────────────────────────────────────

  const handleDeviceCodeInit = async () => {
    setDeviceLoading(true)
    try {
      const data: any = await apiReq(`${API}/codex/device-code/request`, { method: 'POST' })
      if (data.user_code) {
        setDeviceCode(data.user_code)
        setVerificationUri(data.verification_uri || 'https://auth.openai.com/codex/device')
        setShowDeviceCode(true)
        
        const requestId = data.request_id
        let attempts = 0
        const maxAttempts = 60 // 5 minutos
        
        const pollInterval = setInterval(async () => {
          attempts++
          try {
            const status: any = await apiReq(`${API}/codex/device-code/poll/${requestId}`, { method: 'POST' })
            
            if (status.status === 'saved') {
              clearInterval(pollInterval)
              setShowDeviceCode(false)
              setDeviceCode('')
              loadAccounts()
              toast.success('Conta conectada com sucesso!')
            } else if (status.status === 'error') {
              clearInterval(pollInterval)
              setShowDeviceCode(false)
              setDeviceCode('')
              toast.error(status.message || 'Erro na autenticação')
            } else if (attempts >= maxAttempts) {
              clearInterval(pollInterval)
              setShowDeviceCode(false)
              setDeviceCode('')
              toast.error('Tempo limite excedido (5 min)')
            }
            // else: pending, continua poll
          } catch (err: any) {
            console.error('Poll error:', err)
          }
        }, 5000)
      } else {
        toast.error(data.message || 'Erro ao gerar código')
      }
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setDeviceLoading(false)
    }
  }

  // ─── Importar auth.json ────────────────────────────────────

  const handleImportAuth = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      setImporting(true)
      try {
        const text = await file.text()
        const json = JSON.parse(text)
        const data: any = await apiReq(`${API}/codex/extract-auth`, {
          method: 'POST',
          body: JSON.stringify(json),
        })
        toast.success(`Conta ${data.email || 'desconhecida'} importada!`)
        loadAccounts()
      } catch (err: any) {
        toast.error(err.message)
      } finally {
        setImporting(false)
      }
    }
    input.click()
  }

  // ─── Remover conta ─────────────────────────────────────────

  const handleRemoveAccount = async (accountId: string) => {
    if (!confirm('Remover esta conta do pool?')) return
    try {
      await apiReq(`${API}/codex/pool/${providerId}/accounts/${accountId}`, {
        method: 'DELETE',
      })
      toast.success('Conta removida')
      loadAccounts()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Atualizar cota ────────────────────────────────────────

  const handleUpdateQuota = async () => {
    await refreshQuota(false)
  }

  // ─── Render ────────────────────────────────────────────────

  const isActive = stats && stats.total_accounts > 0

  return (
    <div className="mt-6 border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}
      >
        <div className="flex items-center gap-2">
          <AIProviderIcon provider="Codex ChatGPT" size={18} />
          <h4 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            Codex Account Pool
          </h4>
          {stats && (
            <span
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{
                background: isActive ? '#dcfce7' : '#fef2f2',
                color: isActive ? '#16a34a' : '#dc2626',
              }}
            >
              {stats.total_accounts} conta{stats.total_accounts !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleUpdateQuota}
            disabled={!isActive || quotaLoading}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90 disabled:opacity-60"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            title="Atualizar cota"
          >
            {quotaLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Quota
          </button>
          <button
            onClick={handleImportAuth}
            disabled={importing}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            Import auth.json
          </button>
          <button
            onClick={handleDeviceCodeInit}
            disabled={deviceLoading}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
            style={{ background: '#16a34a', color: '#fff' }}
          >
            {deviceLoading ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            Conectar Conta
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="px-4 py-6 text-center">
          <Loader2 size={20} className="animate-spin inline-block" style={{ color: 'var(--text-tertiary)' }} />
        </div>
      )}

      {/* Empty state */}
      {!loading && accounts.length === 0 && (
        <div className="px-4 py-8 text-center">
          <User size={32} className="mx-auto mb-2" style={{ color: 'var(--text-tertiary)' }} />
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            Nenhuma conta conectada.
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
            Clique em "Conectar Conta" para fazer login via Device Code,
            ou importe um auth.json do Codex Desktop.
          </p>
        </div>
      )}

      {/* Account list */}
      {!loading && accounts.length > 0 && (
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {accounts.map((acc) => (
            <div key={acc.id} className="px-4 py-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: acc.enabled !== false ? '#16a34a' : '#dc2626',
                    }}
                  />
                  <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {acc.label || acc.email || `Conta #${acc.id.slice(-4)}`}
                  </span>
                </div>
                <button
                  onClick={() => handleRemoveAccount(acc.id)}
                  className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                  title="Remover conta"
                >
                  <Trash2 size={12} style={{ color: '#dc2626' }} />
                </button>
              </div>

              {/* Quota bars */}
              <div className="space-y-1.5">
                <QuotaBar
                  label="5h"
                  value={acc.quota_5h_pct ?? acc.quota_5h ?? 0}
                  maxValue={100}
                  color="#3b82f6"
                />
                <QuotaBar
                  label="Weekly"
                  value={acc.quota_weekly_pct ?? acc.quota_weekly ?? 0}
                  maxValue={100}
                  color="#8b5cf6"
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stats footer */}
      {stats && (
        <div
          className="px-4 py-2 border-t text-xs flex items-center gap-4"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-tertiary)' }}
        >
          <span>Estratégia: {stats.strategy}</span>
          {stats.expired_tokens > 0 && (
            <span style={{ color: '#f59e0b' }}>
              {stats.expired_tokens} token{stats.expired_tokens > 1 ? 's' : ''} expirado{stats.expired_tokens > 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      {/* Device Code Modal */}
      {showDeviceCode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => { setShowDeviceCode(false); setDeviceCode('') }}
        >
          <div
            className="rounded-2xl p-8 max-w-sm w-full mx-4 shadow-2xl"
            style={{ background: 'var(--bg-primary)' }}
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => { setShowDeviceCode(false); setDeviceCode('') }}
              className="float-right p-1 rounded-lg hover:bg-black/10 dark:hover:bg-white/10"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
              Conectar Conta ChatGPT
            </h3>
            <p className="text-sm mb-4" style={{ color: 'var(--text-tertiary)' }}>
              Abra o link abaixo e digite o código:
            </p>
            <a
              href={verificationUri}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-sm text-center mb-4 underline"
              style={{ color: 'var(--accent)' }}
            >
              {verificationUri}
            </a>
            <div
              className="text-3xl font-mono font-bold text-center py-6 rounded-xl mb-4 tracking-widest"
              style={{
                background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                border: '2px dashed var(--border)',
              }}
            >
              {deviceCode}
            </div>
            <p className="text-xs text-center" style={{ color: 'var(--text-tertiary)' }}>
              Após autenticar, a conta aparecerá automaticamente aqui.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Barra de Cota ─────────────────────────────────────────────

function QuotaBar({ label, value, maxValue, color }: {
  label: string
  value: number
  maxValue: number
  color: string
}) {
  const pct = Math.min((value / maxValue) * 100, 100)
  const barColor = pct > 60 ? color : pct > 30 ? '#f59e0b' : '#dc2626'

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium w-14" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </span>
      <div className="flex-1 h-2 rounded-full" style={{ background: 'var(--border)' }}>
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: barColor,
          }}
        />
      </div>
      <span className="text-xs font-mono w-10 text-right" style={{ color: 'var(--text-secondary)' }}>
        {Math.round(pct)}%
      </span>
    </div>
  )
}
