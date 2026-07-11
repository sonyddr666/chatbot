import { useState, useMemo, useEffect, useRef, type ComponentProps } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, Download, FileText, Image as ImageIcon, Maximize2, ThumbsUp, ThumbsDown, RefreshCw, Volume2, VolumeX, X } from 'lucide-react'
import type { ChatAttachmentInfo, ChatMessage as ChatMessageType } from '../lib/api'
import { api } from '../lib/api'
import { useChatStore } from '../hooks/useChatStore'
import { ThinkingBlock } from './ThinkingBlock'
import { WorkspacePlanCard } from './WorkspacePlanCard'
import { SkillActivityBlock } from './SkillActivityBlock'

interface Props {
  message: ChatMessageType
  isLoading?: boolean
  status?: string | null
  onRegenerate?: () => void
  onSpeak?: (text: string) => void
  onStopSpeaking?: () => void
}

function formatTime(d: Date) {
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// ─── CodeBlock (extraído para evitar hooks no render) ───
function CodeBlock({ className, children }: ComponentProps<'code'>) {
  const match = /language-([^\s]+)/.exec(className || '')
  const isInline = !match
  const [codeCopied, setCodeCopied] = useState(false)
  const code = String(children).replace(/\n$/, '')
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'))

  useEffect(() => {
    const root = document.documentElement
    const update = () => setIsDark(root.classList.contains('dark'))
    update()
    const observer = new MutationObserver(update)
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])
  const rawLanguage = (match?.[1] || '').toLowerCase()
  const languageAliases: Record<string, string> = {
    html: 'markup',
    xml: 'markup',
    svg: 'markup',
    js: 'javascript',
    jsx: 'jsx',
    ts: 'typescript',
    tsx: 'tsx',
    py: 'python',
    sh: 'bash',
    shell: 'bash',
  }
  const language = languageAliases[rawLanguage] || rawLanguage

  const handleCopyCode = () => {
    navigator.clipboard.writeText(code)
    setCodeCopied(true)
    setTimeout(() => setCodeCopied(false), 2000)
  }

  if (isInline) {
    return <code className={className}>{children}</code>
  }

  return (
    <div className="code-block-group" style={{ position: 'relative' }}>
      <div
        className="flex items-center justify-between px-4 py-1.5 text-xs rounded-t-lg border-b"
        style={{
          background: isDark ? '#111827' : '#f1f5f9',
          color: 'var(--text-tertiary)',
          borderColor: 'var(--border)',
        }}
      >
        <span>{rawLanguage}</span>
        <button onClick={handleCopyCode} className="flex items-center gap-1 hover:text-white transition-colors">
          {codeCopied ? <Check size={12} /> : <Copy size={12} />}
          {codeCopied ? 'Copiado!' : 'Copiar'}
        </button>
      </div>
      <SyntaxHighlighter
        style={isDark ? oneDark : oneLight}
        language={language}
        PreTag="div"
        codeTagProps={{ style: { color: 'inherit' } }}
        customStyle={{
          margin: 0,
          borderRadius: '0 0 8px 8px',
          fontSize: '0.875rem',
          background: isDark ? '#0f172a' : '#f8fafc',
          color: isDark ? '#e2e8f0' : '#0f172a',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

// ─── Typing indicator ───
function TypingIndicator({ status }: { status?: string | null }) {
  return (
    <div className="flex items-center gap-3 py-2" style={{ color: 'var(--text-secondary)' }}>
      <span className="flex gap-1.5">
        <span className="w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '300ms' }} />
      </span>
      <span className="text-xs font-medium">{status || 'Aguardando o primeiro token...'}</span>
    </div>
  )
}

// ─── Action button ───
function ActionButton({
  icon: Icon,
  active,
  activeColor,
  title,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number }>
  active?: boolean
  activeColor?: string
  title: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
      style={{ color: active ? activeColor : 'var(--text-tertiary)' }}
      title={title}
    >
      <Icon size={14} />
    </button>
  )
}

// ─── Componente principal ───
function formatAttachmentSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function ImageLightbox({
  source,
  attachment,
  downloading,
  onClose,
  onDownload,
}: {
  source: string
  attachment: ChatAttachmentInfo
  downloading: boolean
  onClose: () => void
  onDownload: () => void
}) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [onClose])

  return createPortal(
    <div
      className="fixed inset-0 z-[140] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`Visualizacao de ${attachment.filename}`}
      onMouseDown={event => {
        if (event.currentTarget === event.target) onClose()
      }}
    >
      <div
        className="flex max-h-[calc(100dvh-1.5rem)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-neutral-950 shadow-2xl sm:max-h-[calc(100dvh-3rem)]"
        onMouseDown={event => event.stopPropagation()}
      >
        <div className="flex min-h-12 items-center gap-2 border-b border-white/10 px-3 py-2 text-white sm:px-4">
          <ImageIcon size={17} className="shrink-0 text-blue-400" />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{attachment.filename}</span>
          <button
            type="button"
            onClick={onDownload}
            className="inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-xs font-semibold transition-colors hover:bg-white/10"
            title="Baixar imagem"
          >
            <Download size={16} className={downloading ? 'animate-pulse' : ''} />
            <span className="hidden sm:inline">Baixar</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            autoFocus
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl transition-colors hover:bg-white/10"
            title="Fechar imagem"
            aria-label="Fechar imagem"
          >
            <X size={20} />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-2 sm:p-4">
          <img
            src={source}
            alt={attachment.filename}
            className="max-h-full max-w-full object-contain"
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}

function AttachmentImagePreview({
  attachment,
  isUser,
  downloading,
  onDownload,
  onUnavailable,
}: {
  attachment: ChatAttachmentInfo
  isUser: boolean
  downloading: boolean
  onDownload: () => void
  onUnavailable: (message: string) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [shouldLoad, setShouldLoad] = useState(false)
  const [source, setSource] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const element = containerRef.current
    if (!element || typeof IntersectionObserver === 'undefined') {
      setShouldLoad(true)
      return
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setShouldLoad(true)
        observer.disconnect()
      }
    }, { rootMargin: '300px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!shouldLoad) return
    let active = true
    let objectUrl = ''
    setPreviewError(false)
    void api.downloadChatAttachment(attachment.id)
      .then(blob => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setSource(objectUrl)
      })
      .catch(() => {
        if (!active) return
        setPreviewError(true)
        onUnavailable('A previa nao esta disponivel; o arquivo pode ter sido movido ou apagado.')
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachment.id, onUnavailable, shouldLoad])

  return (
    <div
      ref={containerRef}
      className="min-w-0 overflow-hidden rounded-xl border"
      style={{
        background: isUser ? 'rgba(255,255,255,0.12)' : 'var(--bg-tertiary)',
        borderColor: isUser ? 'rgba(255,255,255,0.22)' : 'var(--border)',
      }}
    >
      <button
        type="button"
        onClick={() => source && setOpen(true)}
        disabled={!source}
        className="group/image relative block aspect-square w-full overflow-hidden disabled:cursor-default"
        title={source ? `Ampliar ${attachment.filename}` : 'Carregando miniatura'}
      >
        {source ? (
          <img
            src={source}
            alt={attachment.filename}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover/image:scale-[1.03]"
          />
        ) : (
          <span className="grid h-full w-full place-items-center" style={{ background: 'rgba(0,0,0,0.12)' }}>
            <span className="flex flex-col items-center gap-2 text-xs opacity-70">
              <ImageIcon size={25} className={previewError ? '' : 'animate-pulse'} />
              {previewError ? 'Previa indisponivel' : 'Carregando imagem...'}
            </span>
          </span>
        )}
        {source && (
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-lg bg-black/65 px-2 py-1 text-[10px] font-bold text-white backdrop-blur-sm">
            <Maximize2 size={12} /> Ampliar
          </span>
        )}
      </button>
      <div className="flex min-w-0 items-center gap-2 px-2.5 py-2">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-semibold">{attachment.filename}</span>
          <span className="block truncate text-[10px] opacity-70">{formatAttachmentSize(attachment.size)}</span>
        </span>
        <button
          type="button"
          onClick={onDownload}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors hover:bg-black/10 dark:hover:bg-white/10"
          title={`Baixar ${attachment.filename}`}
          aria-label={`Baixar ${attachment.filename}`}
        >
          <Download size={14} className={downloading ? 'animate-pulse' : ''} />
        </button>
      </div>
      {open && source && (
        <ImageLightbox
          source={source}
          attachment={attachment}
          downloading={downloading}
          onClose={() => setOpen(false)}
          onDownload={onDownload}
        />
      )}
    </div>
  )
}

function MessageAttachments({ attachments, isUser }: { attachments: ChatAttachmentInfo[]; isUser: boolean }) {
  const [downloading, setDownloading] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const download = async (attachment: ChatAttachmentInfo) => {
    setDownloading(attachment.id)
    setDownloadError(null)
    try {
      const blob = await api.downloadChatAttachment(attachment.id)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = attachment.filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch {
      setDownloadError('O arquivo foi movido, apagado ou nao esta disponivel.')
    } finally {
      setDownloading(null)
    }
  }

  const imageAttachments = attachments.filter(attachment => attachment.kind === 'image')
  const fileAttachments = attachments.filter(attachment => attachment.kind !== 'image')

  return (
    <div className="mb-2 grid gap-1.5">
      {!!imageAttachments.length && (
        <div className={`grid gap-2 ${imageAttachments.length === 1 ? 'max-w-72 grid-cols-1' : 'grid-cols-2'}`}>
          {imageAttachments.map(attachment => (
            <AttachmentImagePreview
              key={attachment.id}
              attachment={attachment}
              isUser={isUser}
              downloading={downloading === attachment.id}
              onDownload={() => void download(attachment)}
              onUnavailable={setDownloadError}
            />
          ))}
        </div>
      )}
      {fileAttachments.map(attachment => (
          <button
            key={attachment.id}
            type="button"
            onClick={() => void download(attachment)}
            className="flex min-w-0 items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-transform hover:-translate-y-0.5"
            style={{
              background: isUser ? 'rgba(255,255,255,0.12)' : 'var(--bg-tertiary)',
              borderColor: isUser ? 'rgba(255,255,255,0.22)' : 'var(--border)',
            }}
            title={`Baixar ${attachment.filename}`}
          >
            <FileText size={17} className="shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-semibold">{attachment.filename}</span>
              <span className="block truncate text-[10px] opacity-70">
                {formatAttachmentSize(attachment.size)} · {attachment.relative_path}
              </span>
            </span>
            <Download size={14} className={downloading === attachment.id ? 'animate-pulse' : ''} />
          </button>
      ))}
      <span className="text-[10px] font-medium opacity-70">Salvo no Workspace · direto ao modelo · fora do RAG</span>
      {downloadError && <span className="text-[10px] font-semibold" style={{ color: 'var(--danger)' }}>{downloadError}</span>}
    </div>
  )
}

export function ChatMessageBubble({ message, isLoading, status, onRegenerate, onSpeak, onStopSpeaking }: Props) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState<number | null>(message.feedbackScore ?? null)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleFeedback = async (score: number) => {
    if (!message.messageId) return
    const newScore = score === feedback ? null : score
    setFeedback(newScore)
    await api.feedback(message.messageId, newScore ?? 0)
    void useChatStore.getState().loadStats()
  }

  // Reasoning ativo (está chegando agora)
  const isReasoning = !!(isLoading && message.content === '' && message.reasoning)
  // Reasoning já finalizado
  const hasReasoning = !!message.reasoning
  const displayContent = useMemo(
    () => message.content.replace(/\s*<!-- workspace-plan:[a-f0-9]{32} -->\s*/gi, '').trim(),
    [message.content],
  )

  const memoContent = useMemo(
    () => (
      <div className="markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
          {displayContent}
        </ReactMarkdown>
      </div>
    ),
    [displayContent],
  )

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3 animate-fade-in`}>
      <div className="max-w-[85%] md:max-w-[75%] group relative">
        <div
          className="rounded-2xl px-4 py-3 shadow-sm"
          style={{
            background: isUser ? 'var(--user-bubble)' : 'var(--bot-bubble)',
            color: isUser ? 'var(--user-text)' : 'var(--bot-text)',
          }}
        >
          {!!message.attachments?.length && (
            <MessageAttachments attachments={message.attachments} isUser={isUser} />
          )}
          {isUser ? (
            message.content
              ? <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
              : null
          ) : (
            <>
              {message.jobId && message.jobStatus === 'completed' && !message.readAt && (
                <div
                  className="mb-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold"
                  style={{ background: '#f0fdf4', borderColor: '#86efac', color: '#15803d' }}
                >
                  Nao lida
                </div>
              )}
              {message.jobStatus && message.jobStatus !== 'completed' && (
                <div
                  className="mb-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold"
                  style={{
                    background: message.jobStatus === 'running' || message.jobStatus === 'queued' ? '#eff6ff' : '#fff7ed',
                    borderColor: message.jobStatus === 'running' || message.jobStatus === 'queued' ? '#93c5fd' : '#fdba74',
                    color: message.jobStatus === 'running' || message.jobStatus === 'queued' ? '#1d4ed8' : '#c2410c',
                  }}
                >
                  {message.jobStatus === 'queued' && 'Na fila'}
                  {message.jobStatus === 'running' && 'Respondendo...'}
                  {message.jobStatus === 'interrupted' && 'Interrompida'}
                  {message.jobStatus === 'failed' && 'Erro na resposta'}
                  {message.jobStatus === 'cancelled' && 'Cancelada'}
                </div>
              )}
              {!!message.skillActivities?.length && (
                <SkillActivityBlock activities={message.skillActivities} />
              )}
              {/* Thinking block — mostra reasoning se existir */}
              {(hasReasoning || isReasoning) && (
                <ThinkingBlock
                  text={message.reasoning || ''}
                  isStreaming={!!isReasoning}
                  startCollapsed={!isReasoning && hasReasoning}
                />
              )}

              {/* Badge do modelo que respondeu */}
              {(message.modelName || message.modelId || message.providerName) && (
                <div
                  className="inline-flex items-center gap-1 px-2 py-0.5 mb-2 rounded-full text-[11px] font-medium"
                  style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
                  title={`${message.providerName || message.providerId || ''} ${message.modelName || message.modelId || ''}`.trim()}
                >
                  <span>{message.providerName || message.providerId || 'Provider'}</span>
                  {(message.modelName || message.modelId) && <span>· {message.modelName || message.modelId}</span>}
                </div>
              )}

              {/* Conteúdo da resposta */}
              {memoContent}
              {message.workspacePlan && <WorkspacePlanCard plan={message.workspacePlan} />}

              {/* Loading indicator quando não tem content nem reasoning */}
              {isLoading && !message.content && !message.reasoning && <TypingIndicator status={status} />}
            </>
          )}
          <div
            className="text-[11px] mt-1.5"
            style={{ color: isUser ? 'rgba(255,255,255,0.6)' : 'var(--text-tertiary)' }}
          >
            {formatTime(message.timestamp)}
          </div>
        </div>

        {/* Ações (copy, feedback, regenerate) */}
        {!isUser && !isLoading && (
          <div className="flex items-center gap-0.5 mt-1 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <ActionButton
              icon={copied ? Check : Copy}
              active={copied}
              activeColor="#16a34a"
              title="Copiar"
              onClick={handleCopy}
            />
            {onSpeak && displayContent && (
              <ActionButton icon={Volume2} title="Ouvir resposta" onClick={() => onSpeak(displayContent)} />
            )}
            {onStopSpeaking && (
              <ActionButton icon={VolumeX} title="Parar voz" onClick={onStopSpeaking} />
            )}
            <ActionButton
              icon={ThumbsUp}
              active={feedback === 1}
              activeColor="#16a34a"
              title="Útil"
              onClick={() => handleFeedback(1)}
            />
            <ActionButton
              icon={ThumbsDown}
              active={feedback === -1}
              activeColor="#dc2626"
              title="Não útil"
              onClick={() => handleFeedback(-1)}
            />
            {onRegenerate && <ActionButton icon={RefreshCw} title="Regenerar" onClick={onRegenerate} />}
          </div>
        )}
      </div>
    </div>
  )
}
