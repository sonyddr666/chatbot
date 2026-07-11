import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ClipboardEvent, type KeyboardEvent } from 'react'
import { FileText, Paperclip, Send, StopCircle, UploadCloud, X } from 'lucide-react'

const MAX_FILES = 5
const CLIPBOARD_IMAGE_EXTENSIONS: Record<string, string> = {
  'image/avif': 'avif',
  'image/bmp': 'bmp',
  'image/gif': 'gif',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/svg+xml': 'svg',
  'image/webp': 'webp',
}
interface Props {
  onSend: (message: string, files: File[]) => Promise<boolean | void> | boolean | void
  busy?: boolean
  onStop?: () => void
  maxUploadMb?: number
  status?: string | null
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function clipboardImageFile(file: File, index: number) {
  const extension = CLIPBOARD_IMAGE_EXTENSIONS[file.type] || 'png'
  const timestamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, '')
  return new File(
    [file],
    `clipboard-${timestamp}${index ? `-${index + 1}` : ''}.${extension}`,
    { type: file.type || `image/${extension}`, lastModified: Date.now() + index },
  )
}

function PendingImageThumbnail({ file }: { file: File }) {
  const [source, setSource] = useState('')

  useEffect(() => {
    const nextSource = URL.createObjectURL(file)
    setSource(nextSource)
    return () => URL.revokeObjectURL(nextSource)
  }, [file])

  return (
    <img
      src={source}
      alt={`Preview de ${file.name}`}
      className="h-10 w-10 shrink-0 rounded-lg object-cover"
    />
  )
}

export function ChatInput({ onSend, busy = false, onStop, maxUploadMb = 10, status }: Props) {
  const [input, setInput] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const filesRef = useRef<File[]>([])

  useEffect(() => {
    if (!busy && !isSubmitting && textareaRef.current) textareaRef.current.focus()
  }, [busy, isSubmitting])

  useEffect(() => {
    if (busy) setIsSubmitting(false)
  }, [busy])

  const replaceFiles = useCallback((next: File[]) => {
    filesRef.current = next
    setFiles(next)
  }, [])

  const addFiles = useCallback((incoming: File[]) => {
    const next = [...filesRef.current]
    let nextError: string | null = null
    for (const file of incoming) {
      if (next.length >= MAX_FILES) {
        nextError = `Maximo de ${MAX_FILES} arquivos por mensagem.`
        break
      }
      if (file.size > maxUploadMb * 1024 * 1024) {
        nextError = `${file.name} ultrapassa o limite de ${maxUploadMb}MB.`
        continue
      }
      const duplicate = next.some(item => (
        item.name === file.name && item.size === file.size && item.lastModified === file.lastModified
      ))
      if (!duplicate) next.push(file)
    }
    replaceFiles(next)
    setFileError(nextError)
  }, [maxUploadMb, replaceFiles])

  useEffect(() => {
    const containsFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types || []).includes('Files')
    const handleDragOver = (event: DragEvent) => {
      if (!containsFiles(event)) return
      event.preventDefault()
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
      setIsDragging(true)
    }
    const handleDrop = (event: DragEvent) => {
      if (!containsFiles(event)) return
      event.preventDefault()
      setIsDragging(false)
      addFiles(Array.from(event.dataTransfer?.files || []))
    }
    const handleDragLeave = (event: DragEvent) => {
      if (!event.relatedTarget) setIsDragging(false)
    }
    window.addEventListener('dragover', handleDragOver)
    window.addEventListener('drop', handleDrop)
    window.addEventListener('dragleave', handleDragLeave)
    return () => {
      window.removeEventListener('dragover', handleDragOver)
      window.removeEventListener('drop', handleDrop)
      window.removeEventListener('dragleave', handleDragLeave)
    }
  }, [addFiles])

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files || []))
    event.target.value = ''
  }

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const pastedImages: File[] = []
    for (const item of Array.from(event.clipboardData.items || [])) {
      if (item.kind !== 'file' || !item.type.startsWith('image/')) continue
      const file = item.getAsFile()
      if (file) pastedImages.push(clipboardImageFile(file, pastedImages.length))
    }
    if (!pastedImages.length) return

    event.preventDefault()
    addFiles(pastedImages)
  }

  const handleSend = async () => {
    if ((!input.trim() && files.length === 0) || busy || isSubmitting) return
    const submittedText = input.trim()
    const submittedFiles = files
    setInput('')
    replaceFiles([])
    setFileError(null)
    setIsSubmitting(true)
    try {
      const sent = await onSend(submittedText, submittedFiles)
      if (sent === false) {
        setInput(current => current || submittedText)
        if (filesRef.current.length === 0) replaceFiles(submittedFiles)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleKey = (event: KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!busy && !isSubmitting) void handleSend()
    }
  }

  useEffect(() => {
    const element = textareaRef.current
    if (element) {
      element.style.height = 'auto'
      element.style.height = `${Math.min(element.scrollHeight, 200)}px`
    }
  }, [input])

  const canSend = (!!input.trim() || files.length > 0) && !busy && !isSubmitting

  return (
    <div className="border-t px-4 py-3" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}>
      {isDragging && (
        <div
          className="fixed inset-0 z-[100] grid place-items-center p-6"
          style={{ background: 'rgba(5, 12, 20, 0.82)', backdropFilter: 'blur(8px)' }}
        >
          <div
            className="w-full max-w-xl rounded-3xl border-2 border-dashed p-10 text-center shadow-2xl"
            style={{ background: 'var(--bg-secondary)', borderColor: 'var(--accent)', color: 'var(--text-primary)' }}
          >
            <UploadCloud size={42} className="mx-auto mb-4" style={{ color: 'var(--accent)' }} />
            <p className="text-lg font-bold">Solte os arquivos na conversa</p>
            <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              Eles serao salvos em Workspace/chat/uploads e enviados ao modelo, sem entrar no RAG.
            </p>
          </div>
        </div>
      )}

      <div className="mx-auto max-w-4xl">
        {busy && status && (
          <div
            className="mb-2 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold"
            style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: 'var(--accent)' }} />
            {status}
          </div>
        )}
        {!!files.length && (
          <div className="mb-2 flex flex-wrap gap-2">
            {files.map((file, index) => {
              const isImage = file.type.startsWith('image/')
              return (
                <div
                  key={`${file.name}-${file.size}-${file.lastModified}`}
                  className="flex min-w-0 max-w-full items-center gap-2 rounded-xl border px-3 py-2"
                  style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                >
                  {isImage
                    ? <PendingImageThumbnail file={file} />
                    : <FileText size={16} style={{ color: 'var(--accent)' }} />}
                  <div className="min-w-0">
                    <p className="max-w-48 truncate text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{file.name}</p>
                    <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{formatFileSize(file.size)}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => replaceFiles(files.filter((_, currentIndex) => currentIndex !== index))}
                    className="rounded-md p-1 transition-colors hover:bg-black/10 dark:hover:bg-white/10"
                    title="Remover anexo"
                  >
                    <X size={14} />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {fileError && <p className="mb-2 text-xs font-medium" style={{ color: 'var(--danger)' }}>{fileError}</p>}

        <div
          className="flex items-end gap-1.5 rounded-xl p-1.5 transition-all focus-within:shadow-md"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileInput}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isSubmitting || files.length >= MAX_FILES}
            className="mb-0.5 rounded-lg p-2.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            style={{ color: files.length ? 'var(--accent)' : 'var(--text-secondary)' }}
            title="Anexar arquivos ao chat"
          >
            <Paperclip size={18} />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={event => setInput(event.target.value)}
            onKeyDown={handleKey}
            onPaste={handlePaste}
            placeholder={busy
              ? 'Continue digitando... o envio libera quando a resposta terminar'
              : files.length
                ? 'Escreva o que o modelo deve fazer com os arquivos...'
                : 'Digite, cole uma imagem ou arraste arquivos...'}
            rows={1}
            className="flex-1 resize-none rounded-lg bg-transparent px-2 py-2.5 text-[15px] outline-none sm:px-3"
            style={{ color: 'var(--text-primary)', maxHeight: '200px' }}
          />
          <div className="flex items-center gap-1">
            {busy && onStop ? (
              <button
                type="button"
                onClick={onStop}
                className="rounded-lg p-2.5 transition-colors"
                style={{ background: 'var(--danger)', color: '#fff' }}
                title="Parar"
              >
                <StopCircle size={18} />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleSend()}
                disabled={!canSend}
                className="rounded-lg p-2.5 transition-all disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: canSend ? 'var(--accent)' : 'var(--border)', color: canSend ? '#fff' : 'var(--text-tertiary)' }}
                title={files.length ? 'Enviar mensagem e arquivos' : 'Enviar'}
              >
                <Send size={18} />
              </button>
            )}
          </div>
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-3 px-1 text-[10px] sm:text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          <span>Cole imagens com Ctrl+V. Arquivos vao ao Workspace; RAG so quando voce escolher.</span>
          <span className="shrink-0">{files.length}/{MAX_FILES}</span>
        </div>
      </div>
    </div>
  )
}
