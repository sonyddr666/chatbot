import { useCallback, useEffect, useState, type ChangeEvent, type DragEvent } from 'react'
import toast from 'react-hot-toast'
import { FileText, RefreshCw, Trash2, Upload, X } from 'lucide-react'
import { api, type DocumentInfo } from '../lib/api'
import { useChatStore } from '../hooks/useChatStore'

interface Props {
  open: boolean
  onClose: () => void
}

export function DocumentsPanel({ open, onClose }: Props) {
  const loadStoreDocuments = useChatStore(s => s.loadDocuments)
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const docs = await api.listDocuments()
      setDocuments(docs)
      await loadStoreDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar documentos')
    } finally {
      setLoading(false)
    }
  }, [loadStoreDocuments])

  useEffect(() => {
    if (open) loadDocuments()
  }, [loadDocuments, open])

  const uploadFile = useCallback(async (file?: File) => {
    if (!file) return
    setUploading(true)
    try {
      await api.uploadDocument(file)
      toast.success('Arquivo salvo em uploads e ingerido no RAG')
      await loadDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao enviar arquivo')
    } finally {
      setUploading(false)
    }
  }, [loadDocuments])

  const deleteDocument = useCallback(async (documentId: number) => {
    try {
      await api.deleteDocument(documentId)
      toast.success('Documento removido')
      await loadDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao remover documento')
    }
  }, [loadDocuments])

  const handleDrop = useCallback(async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    await uploadFile(event.dataTransfer.files[0])
  }, [uploadFile])

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-2xl flex-col border-l p-4 shadow-xl"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--accent)' }}>
              Documentos RAG
            </p>
            <h2 className="text-xl font-black" style={{ color: 'var(--text-primary)' }}>
              Uploads e conhecimento pessoal
            </h2>
            <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
              Arquivos enviados ficam em uploads/original e o texto extraido entra no RAG deste usuario.
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        <div
          onDrop={handleDrop}
          onDragOver={event => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          className="mt-5 rounded-2xl border-2 border-dashed p-5 text-center transition"
          style={{
            borderColor: dragging ? 'var(--accent)' : 'var(--border)',
            background: dragging ? 'var(--accent-light)' : 'var(--bg-secondary)',
          }}
        >
          <Upload className="mx-auto mb-2" size={28} style={{ color: 'var(--accent)' }} />
          <p className="font-bold" style={{ color: 'var(--text-primary)' }}>
            Arraste arquivos ou selecione do computador
          </p>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            TXT, Markdown, PDF, CSV, JSON e DOCX sao suportados pelo backend.
          </p>
          <label
            className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {uploading ? 'Enviando...' : 'Enviar para RAG'}
            <input
              type="file"
              className="hidden"
              accept=".txt,.md,.pdf,.csv,.json,.docx"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                uploadFile(event.target.files?.[0])
                event.target.value = ''
              }}
            />
          </label>
        </div>

        <div className="mt-5 flex items-center justify-between">
          <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>
            Documentos ingeridos
          </h3>
          <button
            onClick={loadDocuments}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-60"
            style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Atualizar
          </button>
        </div>

        <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {loading && documents.length === 0 ? (
            <p className="rounded-2xl border p-4 text-sm" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              Carregando documentos...
            </p>
          ) : documents.length === 0 ? (
            <p className="rounded-2xl border p-4 text-sm" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              Nenhum documento ingerido ainda.
            </p>
          ) : documents.map(document => (
            <div
              key={document.id}
              className="flex items-center gap-3 rounded-2xl border p-3"
              style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
            >
              <div className="grid h-10 w-10 place-items-center rounded-xl" style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>
                <FileText size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  {document.filename}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {document.chunks} chunks - {(document.size / 1024).toFixed(1)}KB
                </p>
              </div>
              <button
                onClick={() => deleteDocument(document.id)}
                className="rounded-xl p-2 hover:bg-red-100 dark:hover:bg-red-900/30"
                title="Remover documento"
              >
                <Trash2 size={16} style={{ color: 'var(--danger)' }} />
              </button>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}
