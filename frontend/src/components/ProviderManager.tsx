import { memo, useState, useEffect, useCallback, useRef } from 'react'
import {
  X, Plus, Trash2, Check,
  Server, Globe, Cpu, Eye, EyeOff, Power, PowerOff,
  Pencil, Save, AlertTriangle, Loader2, Upload, Download, RefreshCw, User,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, getAuthToken, type UserProviderInfo } from '../lib/api'

// ─── Tipos ──────────────────────────────────────────────────────────

interface ModelInfo {
  id: string
  name: string
  alias?: string
  usage?: string
  status?: string
  context_length: number
  enabled: boolean
  active?: boolean
}

interface ProviderInfo {
  id: string
  name: string
  base_url: string
  endpoint?: string
  api_key?: string
  api_format: string
  provider_type: 'builtin' | 'custom'
  enabled: boolean
  active: boolean
  active_model_id?: string | null
  models: ModelInfo[]
  has_key?: boolean
  key_source?: string
}

interface Props {
  open: boolean
  onClose: () => void
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
    throw new Error(err.detail || 'Erro na requisição')
  }
  return res.json()
}

// ─── Componente principal ──────────────────────────────────────────

export const ProviderManager = memo(function ProviderManager({ open, onClose }: Props) {
  // Importante: não assinar a store inteira aqui.
  // Durante streaming, messages muda a cada chunk; se este modal assinar tudo, o Codex Pool fica travando.
  const loadConfig = useChatStore(s => s.loadConfig)

  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [userProviders, setUserProviders] = useState<UserProviderInfo[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
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
  const [formBaseUrl, setFormBaseUrl] = useState('')
  const [formEndpoint, setFormEndpoint] = useState('')
  const [formApiKey, setFormApiKey] = useState('')
  const [formApiFormat, setFormApiFormat] = useState('chat_completions')
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
    setLoading(true)
    try {
      const [data, personal] = await Promise.all([
        apiReq<ProviderInfo[]>(`${API}/providers/manage`),
        api.listUserProviders(),
      ])
      setProviders(data)
      setUserProviders(personal.providers)
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      loadProviders()
      setShowAddForm(false)
      setShowPersonalForm(false)
      setEditing(false)
    }
  }, [open, loadProviders])

  const selected = providers.find(p => p.id === selectedId) || null
  const builtinProviders = providers.filter(p => p.provider_type === 'builtin')
  const customProviders = providers.filter(p => p.provider_type === 'custom')

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
        loadConfig()
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
      loadConfig()
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

  const handleImportProviders = async (event: any) => {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    setImportingProviders(true)
    try {
      const parsed = JSON.parse(await file.text())
      const hasApiKeys = JSON.stringify(parsed).includes('"api_key"')
      const accepted = confirm(
        `Importar providers de "${file.name}"?\n\n`
        + 'Providers pessoais existentes com a mesma configuracao serao atualizados. '
        + 'Para usuarios comuns, providers customizados serao adicionados como providers pessoais.'
        + (hasApiKeys ? '\n\nO arquivo contem API keys.' : ''),
      )
      if (!accepted) return

      const result = await apiReq<any>(`${API}/providers/import`, {
        method: 'POST',
        body: JSON.stringify(parsed),
      })
      await loadProviders()
      loadConfig()
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

  // ─── Testar provider ───────────────────────────────────────────

  const handleTestProvider = async () => {
    if (!selectedId) return
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

  // ─── Ativar provider ───────────────────────────────────────────

  const handleActivate = async (id: string) => {
    try {
      await apiReq(`${API}/providers/manage/${id}/activate`, { method: 'POST' })
      setProviders(prev => prev.map(p => ({ ...p, active: p.id === id })))
      toast.success(`Provider ativado`)
      loadConfig() // Recarrega para o chat usar o novo provider
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
    try {
      await apiReq(`${API}/providers/manage/${id}`, { method: 'DELETE' })
      setProviders(prev => prev.filter(p => p.id !== id))
      if (selectedId === id) {
        setSelectedId(null)
        setShowAddForm(false)
        setEditing(false)
      }
      toast.success('Provider excluído')
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
    setFormBaseUrl('')
    setFormEndpoint('')
    setFormApiKey('')
    setFormApiFormat('chat_completions')
    setFormModelId('')
    setFormModelName('')
    setFormModelCtx('128000')
    setShowKey(false)
    setEditing(false)
    setShowAddForm(false)
    setShowPersonalForm(false)
  }

  const handleEditProvider = (p: ProviderInfo) => {
    if (p.provider_type === 'builtin') {
      toast('Providers built-in não podem ser editados')
      return
    }
    setFormName(p.name)
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
    setSaving(true)
    try {
      if (editing && selectedId) {
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
      } else {
        // Cria o modelo inicial se o usuário preencheu
        const models: any[] = []
        if (formModelId.trim()) {
          models.push({
            id: formModelId.trim().toLowerCase().replace(/\s+/g, '-'),
            name: formModelName.trim() || formModelId.trim(),
            context_length: parseInt(formModelCtx) || 128000,
            enabled: true,
          })
        }
        const body = {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          endpoint: formEndpoint.trim(),
          api_key: formApiKey.trim(),
          api_format: formApiFormat,
          models,
        }
        const created = await apiReq<ProviderInfo>(`${API}/providers/manage`, {
          method: 'POST', body: JSON.stringify(body),
        })
        setProviders(prev => [...prev, created])
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
        await apiReq(`${API}/providers/manage/${selectedId}/models/${editingModelId}`, {
          method: 'PUT', body: JSON.stringify(body),
        })
        setProviders(prev => prev.map(p =>
          p.id === selectedId ? {
            ...p,
            models: p.models.map(m => m.id === editingModelId ? { ...m, ...body } : m),
          } : p
        ))
        toast.success('Modelo atualizado')
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
    try {
      await apiReq(`${API}/providers/manage/${selectedId}/models/${modelId}`, { method: 'DELETE' })
      setProviders(prev => prev.map(p =>
        p.id === selectedId ? { ...p, models: p.models.filter(m => m.id !== modelId) } : p
      ))
      toast.success('Modelo excluído')
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

  // ─── Selecionar modelo ativo (1 clique: ativa provider + modelo) ─

  const handleSelectModel = async (modelId: string, providerId?: string) => {
    const targetProviderId = providerId || selectedId
    if (!targetProviderId) return
    try {
      const provider = providers.find(p => p.id === targetProviderId)
      // Se provider não estiver ativo, ativa primeiro
      if (!provider?.active) {
        await apiReq(`${API}/providers/manage/${targetProviderId}/activate`, { method: 'POST' })
      }
      // Agora ativa o modelo
      await apiReq(`${API}/providers/activate-model`, {
        method: 'POST',
        body: JSON.stringify({ model_id: modelId }),
      })
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
      setSelectedId(targetProviderId)
      toast.success(`✅ Usando: ${provider?.name || targetProviderId} › ${modelId}`)
      loadConfig()
    } catch (err: any) {
      toast.error(err.message)
    }
  }

  // ─── Renderiza formato da API ──────────────────────────────────

  const formatLabels: Record<string, string> = {
    chat_completions: 'Chat Completions',
    anthropic_messages: 'Anthropic Messages',
    responses: 'Responses API',
    openai: 'OpenAI Compatible',
  }

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
        className="flex w-[95vw] max-w-6xl h-[85vh] rounded-2xl overflow-hidden shadow-2xl"
        style={{ background: 'var(--bg-primary)' }}
      >
        {/* ─── Sidebar ─── */}
        <div
          className="w-72 flex-shrink-0 flex flex-col border-r overflow-hidden"
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
          </div>

          {/* Lista */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading && providers.length === 0 ? (
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
                    onClick={() => { setSelectedId(p.id); setShowAddForm(false); setShowPersonalForm(false); setEditing(false) }}
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
                        onClick={() => { setSelectedId(p.id); setShowAddForm(false); setShowPersonalForm(false); setEditing(false) }}
                        onEdit={() => handleEditProvider(p)}
                        onDelete={() => handleDelete(p.id)}
                      />
                    ))}
                  </>
                )}

                <div className="px-2 py-1.5 mt-3">
                  <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                    Providers pessoais
                  </p>
                </div>
                <div className="space-y-1">
                  {userProviders.length === 0 ? (
                    <p className="px-3 py-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      Nenhum provider pessoal ainda.
                    </p>
                  ) : (
                    userProviders.map(provider => (
                      <div
                        key={provider.id}
                        className="px-3 py-2 rounded-xl border"
                        style={{
                          background: provider.is_default ? 'var(--accent-light)' : 'transparent',
                          borderColor: provider.is_default ? 'var(--accent)' : 'var(--border)',
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                              {provider.display_name}
                            </p>
                            <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                              {provider.model}
                            </p>
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
              onClick={() => { resetForm(); setShowAddForm(true); setShowPersonalForm(false); setSelectedId(null) }}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-medium text-sm transition-all hover:opacity-90"
              style={{ background: 'var(--accent)', color: '#fff' }}
            >
              <Plus size={16} />
              Add Provider
            </button>
            <button
              onClick={() => { resetForm(); resetPersonalForm(); setShowPersonalForm(true); setShowAddForm(false); setSelectedId(null) }}
              className="mt-2 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-medium text-sm transition-all hover:opacity-90 border"
              style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
            >
              <User size={16} />
              Criar provider pessoal
            </button>
          </div>
        </div>

        {/* ─── Main Area ─── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {showPersonalForm ? (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-xl mx-auto">
                <h3 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                  Criar provider pessoal
                </h3>
                <p className="text-sm mb-6" style={{ color: 'var(--text-tertiary)' }}>
                  Este provider fica ligado somente ao usuario logado e pode virar o padrao do chat dele.
                </p>

                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
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

                  <div className="grid grid-cols-2 gap-3">
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
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-xl mx-auto">
                <h3 className="text-xl font-bold mb-6" style={{ color: 'var(--text-primary)' }}>
                  {editing ? 'Edit Provider' : 'Add New Provider'}
                </h3>

                <div className="space-y-4">
                  {/* Nome */}
                  <div>
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
                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Base URL</label>
                    <input
                      type="url"
                      value={formBaseUrl}
                      onChange={e => setFormBaseUrl(e.target.value)}
                      placeholder="https://api.example.com/v1"
                      className="w-full px-3 py-2 rounded-xl border text-sm font-mono"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                    />
                  </div>

                  {/* API Key */}
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
                  <div>
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
                  {!editing && (
                    <>
                      <div className="border-t pt-4 mt-2" style={{ borderColor: 'var(--border)' }}>
                        <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-secondary)' }}>
                          🧩 Modelo inicial <span className="text-xs font-normal" style={{ color: 'var(--text-tertiary)' }}>(opcional — adicione mais depois)</span>
                        </p>
                        <div className="grid grid-cols-3 gap-3">
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
                      {editing ? 'Save Changes' : 'Create Provider'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : selected ? (
            /* ─── Detalhes do Provider ─── */
            <div className="flex-1 overflow-y-auto p-6">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <div className="flex items-center gap-3">
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

                <div className="flex items-center gap-2">
                  {!selected.active && (
                    <button
                      onClick={() => handleActivate(selected.id)}
                      className="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all hover:opacity-90"
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
              <div className="grid grid-cols-2 gap-4 mb-6">
                <InfoCard label="API Format" value={formatLabels[selected.api_format] || selected.api_format} icon={<Globe size={16} />} />
                <InfoCard label="Provider Type" value={selected.provider_type === 'builtin' ? 'Built-in' : 'Custom'} icon={<Server size={16} />} />
                <InfoCard label="Endpoint" value={selected.endpoint || 'Padrao do formato'} icon={<Globe size={16} />} />
                <InfoCard
                  label="API Key"
                  value={selected.id === 'codex-chatgpt' && selected.has_key ? 'OAuth conectado' : (selected.has_key ? `${(selected.api_key || '').substring(0, 12)}...` : 'Não configurada')}
                  icon={<Eye size={16} />}
                  className="cursor-pointer hover:opacity-80"
                  onClick={() => {
                    setLocalApiKey('')
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
                    <input
                      type="password"
                      value={localApiKey}
                      onChange={e => setLocalApiKey(e.target.value)}
                      placeholder={selected?.has_key ? 'Digite uma nova chave para substituir' : 'sk-...'}
                      className="w-full px-3 py-2 rounded-xl text-sm mb-4 outline-none transition-all border"
                      style={{
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        borderColor: 'var(--border)',
                      }}
                      autoFocus
                    />
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
                        onClick={handleSaveApiKey}
                        disabled={savingKey || !localApiKey.trim()}
                        className="flex-1 px-3 py-2 rounded-xl text-sm font-medium text-white transition-all"
                        style={{
                          background: savingKey || !localApiKey.trim() ? 'var(--border)' : 'var(--accent)',
                        }}
                      >
                        {savingKey ? 'Salvando...' : 'Salvar'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ─── Botão Testar Provider ─── */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={handleTestProvider}
                  disabled={testingProvider}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-all hover:opacity-90"
                  style={{
                    background: selected.has_key ? 'var(--accent)' : 'var(--border)',
                    color: selected.has_key ? '#fff' : 'var(--text-tertiary)',
                    cursor: selected.has_key ? 'pointer' : 'not-allowed',
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
                  <h4 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                    Models ({selected.models.length})
                  </h4>
                  <button
                    onClick={() => { setShowAddModel(true); setEditingModelId(null); setModelFormName(''); setModelFormId(''); setModelFormCtx('128000') }}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
                    style={{ background: 'var(--accent)', color: '#fff' }}
                  >
                    <Plus size={12} />
                    Add Model
                  </button>
                </div>

                <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
                  {selected.models.length === 0 ? (
                    <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
                      No models configured. Click "Add Model" to add one.
                    </div>
                  ) : (
                    selected.models.map(model => (
                      <ModelRow
                        key={model.id}
                        model={model}
                        isBuiltin={selected.provider_type === 'builtin'}
                        onToggle={() => handleToggleModel(model.id, model.enabled)}
                        onSelect={() => handleSelectModel(model.id, selected.id)}
                        onEdit={() => handleEditModel(model)}
                        onDelete={() => handleDeleteModel(model.id)}
                      />
                    ))
                  )}
                </div>
              </div>

              {/* ─── Codex ChatGPT: Pool de Contas ─── */}
              {selected.id === 'codex-chatgpt' && <CodexAccountPanel providerId={selected.id} />}

              {/* Add Model Form */}
              {showAddModel && (
                <div
                  className="mt-4 p-4 rounded-xl border"
                  style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                >
                  <h5 className="font-medium text-sm mb-3" style={{ color: 'var(--text-primary)' }}>
                    {editingModelId ? 'Edit Model' : 'Add Model'}
                  </h5>
                  <div className="grid grid-cols-3 gap-3 mb-3">
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

function ProviderItem({
  provider, selected, onClick, onEdit, onDelete,
}: {
  provider: ProviderInfo
  selected: boolean
  onClick: () => void
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <div
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer transition-colors group"
      style={{
        background: selected ? 'var(--accent-light)' : 'transparent',
        color: selected ? 'var(--accent)' : 'var(--text-primary)',
      }}
      onMouseEnter={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)' }}
      onMouseLeave={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    >
      {/* Status dot */}
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ background: provider.enabled ? '#16a34a' : '#a1a1aa' }}
      />

      {/* Active indicator */}
      {provider.active && (
        <span className="text-[10px] font-bold flex-shrink-0" style={{ color: '#16a34a' }}>ACTIVE</span>
      )}

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
  model, isBuiltin, onToggle, onSelect, onEdit, onDelete,
}: {
  model: ModelInfo
  isBuiltin: boolean
  onToggle: () => void
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
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
    <div className="flex items-center justify-between px-4 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
      style={{
        background: isActive ? 'var(--accent-light)' : 'transparent',
        borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
      }}>
      <div className="flex items-center gap-3">
        <Cpu size={16} style={{ color: isActive ? 'var(--accent)' : model.enabled ? 'var(--text-secondary)' : 'var(--text-tertiary)' }} />
        <div>
          <div className="flex items-center gap-2">
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
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            <span className="font-mono">{model.id}</span>
            {model.alias && <span>alias: {model.alias}</span>}
          </div>
          {model.usage && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {model.usage}
            </p>
          )}
        </div>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-mono"
          style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
        >
          {ctxLabel}
        </span>
      </div>
      <div className="flex items-center gap-1">
        {model.enabled && (
          <button
            onClick={onSelect}
            className="px-2 py-1 rounded-lg text-xs font-medium transition-all hover:opacity-90"
            style={{
              background: isActive ? '#16a34a' : 'var(--accent)',
              color: '#fff',
              opacity: isActive ? 0.6 : 1,
            }}
            title={isActive ? 'Já está ativo' : 'Usar este modelo'}
            disabled={isActive}
          >
            {isActive ? '✓ Ativo' : 'Usar'}
          </button>
        )}
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
          <User size={16} style={{ color: 'var(--accent)' }} />
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
