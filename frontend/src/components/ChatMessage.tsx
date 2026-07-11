import { useState, useMemo, useEffect, type ComponentProps } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, Download, FileText, Image as ImageIcon, ThumbsUp, ThumbsDown, RefreshCw, Volume2, VolumeX } from 'lucide-react'
import type { ChatAttachmentInfo, ChatMessage as ChatMessageType } from '../lib/api'
import { api } from '../lib/api'
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

  return (
    <div className="mb-2 grid gap-1.5">
      {attachments.map(attachment => {
        const Icon = attachment.kind === 'image' ? ImageIcon : FileText
        return (
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
            <Icon size={17} className="shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-semibold">{attachment.filename}</span>
              <span className="block truncate text-[10px] opacity-70">
                {formatAttachmentSize(attachment.size)} · {attachment.relative_path}
              </span>
            </span>
            <Download size={14} className={downloading === attachment.id ? 'animate-pulse' : ''} />
          </button>
        )
      })}
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
