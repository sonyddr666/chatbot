import { useEffect, useState } from 'react'
import {
  MessageSquare, Plus, Trash2, Upload, BarChart3,
  FileText, X, Download, Search, Pencil,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useChatStore } from '../hooks/useChatStore'
import { api, parseApiTimestamp } from '../lib/api'

export function Sidebar() {
  const {
    conversations, documents, stats, showSidebar,
    sessionId, setSession, clearMessages, loadConversations,
    loadDocuments, loadStats, toggleSidebar,
  } = useChatStore()

  const [tab, setTab] = useState<'chats' | 'docs' | 'stats'>('chats')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    loadConversations()
    loadDocuments()
    loadStats()
  }, [loadConversations, loadDocuments, loadStats])

  useEffect(() => {
    const refreshDocuments = () => void loadDocuments()
    window.addEventListener('documents-changed', refreshDocuments)
    return () => window.removeEventListener('documents-changed', refreshDocuments)
  }, [loadDocuments])

  useEffect(() => {
    if (tab === 'docs') void loadDocuments()
  }, [loadDocuments, tab])

  useEffect(() => {
    if (tab !== 'chats') return
    const refresh = () => {
      if (!document.hidden) void loadConversations()
    }
    refresh()
    const interval = window.setInterval(refresh, 2000)
    return () => window.clearInterval(interval)
  }, [loadConversations, tab])

  useEffect(() => {
    if (tab !== 'stats') return
    void loadStats()
    const refresh = window.setInterval(() => {
      if (!document.hidden) void loadStats()
    }, 5000)
    return () => window.clearInterval(refresh)
  }, [loadStats, tab])

  const filteredConvs = conversations.filter(c =>
    c.title.toLowerCase().includes(search.toLowerCase()),
  )

  const closeOnMobile = () => {
    if (window.innerWidth < 768) toggleSidebar()
  }

  const handleNew = async () => {
    const newId = `chat-${Date.now()}`
    await setSession(newId)
    clearMessages()
    closeOnMobile()
  }

  const handleSelect = async (id: string) => {
    await setSession(id)
    closeOnMobile()
  }

  const handleRename = async (id: string) => {
    if (editTitle.trim()) {
      try {
        await api.renameConversation(id, editTitle.trim())
        loadConversations()
        toast.success('Conversa renomeada')
      } catch {
        toast.error('Erro ao renomear')
      }
    }
    setEditingId(null)
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteConversation(id)
      await Promise.all([loadConversations(), loadStats()])
      if (sessionId === id) {
        await setSession('default')
        clearMessages()
      }
      toast.success('Conversa excluída')
    } catch {
      toast.error('Erro ao excluir')
    }
  }

  const handleExport = async () => {
    try {
      const text = await api.exportConversation(sessionId)
      const blob = new Blob([text], { type: 'text/plain' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `chat-${sessionId}.txt`
      a.click()
      URL.revokeObjectURL(a.href)
      toast.success('Conversa exportada')
    } catch {
      toast.error('Erro ao exportar')
    }
  }

  return (
    <>
      {showSidebar && (
        <div className="fixed inset-0 bg-black/60 z-30 md:hidden" onClick={toggleSidebar} />
      )}

      <aside
        className={`
          fixed md:relative z-40 h-full flex flex-col overflow-hidden
          transition-[width,transform] duration-300 ease-out
          ${showSidebar ? 'translate-x-0 w-80 md:w-80' : '-translate-x-full w-80 md:w-0 md:translate-x-0'}
          flex-shrink-0
        `}
        style={{
          background: 'var(--bg-secondary)',
          borderRight: showSidebar ? '1px solid var(--border)' : '0',
        }}
        aria-hidden={!showSidebar}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>🤖 Chatbot</h1>
          <button
            onClick={toggleSidebar}
            className="md:hidden p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <X size={18} style={{ color: 'var(--text-secondary)' }} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
          {[
            { id: 'chats', icon: MessageSquare, label: 'Conversas' },
            { id: 'docs', icon: FileText, label: 'Docs' },
            { id: 'stats', icon: BarChart3, label: 'Stats' },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as any)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors"
              style={{
                color: tab === t.id ? 'var(--accent)' : 'var(--text-tertiary)',
                borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {tab === 'chats' && (
            <>
              <button
                onClick={handleNew}
                className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-2"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                <Plus size={16} /> Nova conversa
              </button>
              <div className="relative mb-2">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--text-tertiary)' }}
                />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar conversas..."
                  className="w-full pl-8 pr-3 py-2 rounded-lg text-sm outline-none"
                  style={{
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                />
              </div>
              {filteredConvs.length === 0 ? (
                <p className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
                  {search ? 'Nenhuma conversa encontrada' : 'Nenhuma conversa ainda'}
                </p>
              ) : (
                filteredConvs.map(c => {
                  const isResponding = c.job_status === 'queued' || c.job_status === 'running'
                  const hasUnreadResponse = !!c.has_unread_response && c.session_id !== sessionId
                  return <div
                    key={c.session_id}
                    onClick={() => handleSelect(c.session_id)}
                    className="group flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-all"
                    style={{
                      background: sessionId === c.session_id ? 'var(--accent-light)' : 'transparent',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <span className="relative flex h-4 w-4 flex-shrink-0 items-center justify-center">
                      {isResponding ? (
                        <>
                          <span className="absolute h-3 w-3 rounded-full bg-blue-400/60 animate-ping" />
                          <span className="relative h-2 w-2 rounded-full bg-blue-500" title="Respondendo em segundo plano" />
                        </>
                      ) : hasUnreadResponse ? (
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" title="Resposta concluída" />
                      ) : (
                        <MessageSquare size={14} style={{ color: 'var(--text-tertiary)' }} />
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      {editingId === c.session_id ? (
                        <input
                          value={editTitle}
                          onChange={e => setEditTitle(e.target.value)}
                          onBlur={() => handleRename(c.session_id)}
                          onKeyDown={e => e.key === 'Enter' && handleRename(c.session_id)}
                          className="w-full text-sm px-1 py-0.5 rounded outline-none"
                          style={{ background: 'var(--bg-primary)', border: '1px solid var(--accent)' }}
                          autoFocus
                          onClick={e => e.stopPropagation()}
                        />
                      ) : (
                        <p className="truncate font-medium">{c.title}</p>
                      )}
                      <p
                        className="text-xs"
                        style={{ color: isResponding ? '#3b82f6' : hasUnreadResponse ? '#10b981' : 'var(--text-tertiary)' }}
                      >
                        {isResponding
                          ? (c.job_status === 'queued' ? 'Na fila…' : 'Respondendo em segundo plano…')
                          : hasUnreadResponse
                            ? 'Resposta concluída'
                            : `${c.message_count} msgs · ${parseApiTimestamp(c.updated_at).toLocaleDateString()}`}
                      </p>
                    </div>
                    <div className="hidden group-hover:flex items-center gap-1">
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          setEditingId(c.session_id)
                          setEditTitle(c.title)
                        }}
                        className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                      >
                        <Pencil size={12} style={{ color: 'var(--text-tertiary)' }} />
                      </button>
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          handleDelete(c.session_id)
                        }}
                        className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                      >
                        <Trash2 size={12} style={{ color: 'var(--danger)' }} />
                      </button>
                    </div>
                  </div>
                })
              )}
            </>
          )}

          {tab === 'docs' && (
            <div className="space-y-2">
              <UploadZone onUpload={() => loadDocuments()} />
              {documents.length === 0 ? (
                <p className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
                  Nenhum documento. Arraste arquivos acima.
                </p>
              ) : (
                documents.map(d => (
                  <div
                    key={d.id}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-primary)' }}
                  >
                    <FileText size={14} style={{ color: 'var(--accent)' }} />
                    <div className="flex-1 min-w-0">
                      <p className="truncate">{d.filename}</p>
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {d.chunks} chunks · {(d.size / 1024).toFixed(1)}KB
                      </p>
                    </div>
                    <button
                      onClick={() =>
                        api.deleteDocument(d.id).then(() => {
                          loadDocuments()
                          toast.success('Documento excluído')
                        }).catch(() => toast.error('Erro ao excluir'))
                      }
                      className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                    >
                      <Trash2 size={12} style={{ color: 'var(--danger)' }} />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'stats' && (
            <div className="space-y-3">
              {stats ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: 'Mensagens', value: stats.total_messages, color: 'var(--accent)' },
                      { label: 'Conversas', value: stats.total_conversations, color: 'var(--success)' },
                      { label: 'Likes', value: stats.likes, color: '#16a34a' },
                      { label: 'Dislikes', value: stats.dislikes, color: '#dc2626' },
                    ].map(s => (
                      <div key={s.label} className="p-3 rounded-lg text-center" style={{ background: 'var(--bg-primary)' }}>
                        <p className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>{s.label}</p>
                      </div>
                    ))}
                  </div>
                  <div className="p-3 rounded-lg" style={{ background: 'var(--bg-primary)' }}>
                    <div className="flex justify-between text-sm mb-1.5">
                      <span style={{ color: 'var(--text-secondary)' }}>Satisfação</span>
                      <span
                        className="font-bold"
                        style={{ color: stats.satisfaction_rate >= 70 ? '#16a34a' : '#dc2626' }}
                      >
                        {stats.satisfaction_rate}%
                      </span>
                    </div>
                    <div className="w-full h-2.5 rounded-full" style={{ background: 'var(--border)' }}>
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${stats.satisfaction_rate}%`,
                          background: stats.satisfaction_rate >= 70 ? '#16a34a' : '#dc2626',
                        }}
                      />
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
                  Carregando...
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t" style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={handleExport}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium transition-colors"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <Download size={14} /> Exportar conversa
          </button>
        </div>
      </aside>
    </>
  )
}

// ─── Componente UploadZone ───
function UploadZone({ onUpload }: { onUpload: () => void }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  const handleUpload = async (file: File) => {
    if (!file) return
    setUploading(true)
    try {
      await api.uploadOriginalDocument(file)
      onUpload()
      toast.success(`"${file.name}" salvo. Confirme a ingestao em Documentos RAG.`)
    } catch (err: any) {
      toast.error(err.message || 'Erro ao enviar')
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    await handleUpload(file)
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={e => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onClick={() => document.getElementById('file-input')?.click()}
      className="flex flex-col items-center justify-center p-4 rounded-lg border-2 border-dashed cursor-pointer transition-all text-center"
      style={{
        borderColor: dragging ? 'var(--accent)' : 'var(--border)',
        background: dragging ? 'var(--accent-light)' : 'var(--bg-primary)',
      }}
    >
      <input
        id="file-input"
        type="file"
        className="hidden"
        accept=".txt,.md,.pdf,.csv,.json"
        onChange={async e => {
          const file = e.target.files?.[0]
          if (file) await handleUpload(file)
          e.target.value = ''
        }}
      />
      {uploading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--accent)' }}>
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          Enviando...
        </div>
      ) : (
        <>
          <Upload size={20} style={{ color: 'var(--text-tertiary)' }} />
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
            {dragging ? 'Solte aqui' : 'Clique ou arraste arquivos'}
          </p>
        </>
      )}
    </div>
  )
}
