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
  const [ingestingId, setIngestingId] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const [manifestLoadingId, setManifestLoadingId] = useState<number | null>(null)
  const [manifestDocumentId, setManifestDocumentId] = useState<number | null>(null)
  const [manifestTitle, setManifestTitle] = useState('')
  const [manifest, setManifest] = useState<Record<string, unknown> | null>(null)

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

  useEffect(() => {
    const refresh = () => {
      if (open) loadDocuments()
    }
    window.addEventListener('documents-changed', refresh)
    return () => window.removeEventListener('documents-changed', refresh)
  }, [loadDocuments, open])

  const uploadFile = useCallback(async (file?: File) => {
    if (!file) return
    setUploading(true)
    try {
      await api.uploadOriginalDocument(file)
      toast.success('Arquivo salvo. Escolha quando ingerir no RAG.')
      await loadDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao enviar arquivo')
      await loadDocuments()
    } finally {
      setUploading(false)
    }
  }, [loadDocuments])

  const ingestDocument = useCallback(async (document: DocumentInfo) => {
    setIngestingId(document.id)
    try {
      await api.ingestDocument(document.id)
      toast.success('Documento ingerido no RAG pessoal')
      await loadDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao ingerir documento')
      await loadDocuments()
    } finally {
      setIngestingId(null)
    }
  }, [loadDocuments])

  const deleteDocument = useCallback(async (documentId: number) => {
    try {
      await api.deleteDocument(documentId)
      toast.success('Documento removido')
      if (manifestDocumentId === documentId) {
        setManifest(null)
        setManifestDocumentId(null)
        setManifestTitle('')
      }
      await loadDocuments()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao remover documento')
    }
  }, [loadDocuments, manifestDocumentId])

  const openManifest = useCallback(async (document: DocumentInfo) => {
    setManifestLoadingId(document.id)
    try {
      const data = await api.getDocumentManifest(document.id)
      setManifest(data)
      setManifestDocumentId(document.id)
      setManifestTitle(document.filename)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao abrir manifesto RAG')
    } finally {
      setManifestLoadingId(null)
    }
  }, [])

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
              Arquivos enviados ficam em uploads/original. A ingestao no RAG pessoal acontece somente quando voce pedir.
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
            {uploading ? 'Enviando...' : 'Enviar arquivo'}
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
            Arquivos enviados
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
              Nenhum arquivo enviado ainda.
            </p>
          ) : documents.map(document => {
            const documentStatus = document.status || 'indexed'
            const hasIngestionError = documentStatus === 'error'
            const pendingIngestion = documentStatus === 'uploaded'
            const canIngest = document.source === 'upload' && Boolean(document.upload_path) && documentStatus !== 'indexed'

            return (
              <div
                key={document.id}
                className="flex items-start gap-3 rounded-2xl border p-3"
                style={{
                  background: 'var(--bg-secondary)',
                  borderColor: hasIngestionError ? 'var(--danger)' : 'var(--border)',
                }}
              >
                <div
                  className="grid h-10 w-10 shrink-0 place-items-center rounded-xl"
                  style={{
                    background: hasIngestionError ? 'rgba(239, 68, 68, 0.14)' : pendingIngestion ? 'rgba(234, 179, 8, 0.16)' : 'var(--accent-light)',
                    color: hasIngestionError ? 'var(--danger)' : pendingIngestion ? '#a16207' : 'var(--accent)',
                  }}
                >
                  <FileText size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                      {document.filename}
                    </p>
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.16em]"
                      style={{
                        background: hasIngestionError ? 'rgba(239, 68, 68, 0.14)' : pendingIngestion ? 'rgba(234, 179, 8, 0.16)' : 'var(--accent-light)',
                        color: hasIngestionError ? 'var(--danger)' : pendingIngestion ? '#a16207' : 'var(--accent)',
                      }}
                    >
                      {hasIngestionError ? 'Erro na ingestao' : pendingIngestion ? 'Aguardando RAG' : documentStatus}
                    </span>
                  </div>
                  <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {document.chunks} chunks - {(document.size / 1024).toFixed(1)}KB
                  </p>
                  <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    Origem: {document.source || 'upload'} - Parser: {document.parser || 'nao informado'}
                  </p>
                  {document.extracted_path ? (
                    <p className="mt-1 text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>
                      Texto extraido: rag/{document.extracted_path}
                    </p>
                  ) : null}
                  {document.checksum ? (
                    <p className="mt-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                      Checksum: {document.checksum.slice(0, 12)}
                    </p>
                  ) : null}
                  {document.error_message ? (
                    <p className="mt-2 rounded-xl px-3 py-2 text-xs" style={{ background: 'rgba(239, 68, 68, 0.12)', color: 'var(--danger)' }}>
                      {document.error_message}
                    </p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {canIngest && (
                      <button
                        onClick={() => ingestDocument(document)}
                        disabled={ingestingId === document.id}
                        className="rounded-xl px-3 py-1.5 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"
                        style={{ background: 'var(--accent)', color: '#fff' }}
                      >
                        {ingestingId === document.id ? 'Ingerindo...' : hasIngestionError ? 'Tentar ingerir de novo' : 'Ingerir no RAG'}
                      </button>
                    )}
                    <button
                      onClick={() => openManifest(document)}
                      disabled={!document.manifest_path || manifestLoadingId === document.id}
                      className="rounded-xl px-3 py-1.5 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"
                      style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                    >
                      {manifestLoadingId === document.id ? 'Abrindo...' : 'Ver manifesto'}
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => deleteDocument(document.id)}
                  className="rounded-xl p-2 hover:bg-red-100 dark:hover:bg-red-900/30"
                  title="Remover documento"
                >
                  <Trash2 size={16} style={{ color: 'var(--danger)' }} />
                </button>
              </div>
            )
          })}
        </div>

        {manifest ? (
          <div
            className="mt-3 max-h-64 overflow-auto rounded-2xl border p-3"
            style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.16em]" style={{ color: 'var(--accent)' }}>
                  Manifesto RAG
                </p>
                <p className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  {manifestTitle}
                </p>
              </div>
              <button
                onClick={() => {
                  setManifest(null)
                  setManifestDocumentId(null)
                  setManifestTitle('')
                }}
                className="rounded-lg px-2 py-1 text-xs font-bold"
                style={{ background: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
              >
                Fechar
              </button>
            </div>
            <pre className="whitespace-pre-wrap break-words text-[11px]" style={{ color: 'var(--text-secondary)' }}>
              {JSON.stringify(manifest, null, 2)}
            </pre>
          </div>
        ) : null}
      </aside>
    </>
  )
}
