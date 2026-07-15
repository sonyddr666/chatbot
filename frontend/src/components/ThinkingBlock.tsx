import { useState, useEffect, useRef } from 'react'
import { ChevronDown, ChevronRight, Brain } from 'lucide-react'

interface Props {
  /** Texto do reasoning sendo recebido ao vivo ou já completo */
  text: string
  /** Se ainda está streaming (mostra pulsando) */
  isStreaming?: boolean
  /** Se deve iniciar recolhido */
  startCollapsed?: boolean
}

export function ThinkingBlock({ text, isStreaming = false, startCollapsed = true }: Props) {
  const [collapsed, setCollapsed] = useState(startCollapsed)
  const bodyRef = useRef<HTMLDivElement>(null)
  const hasText = text.length > 0

  // Auto-expandir enquanto está streaming, recolher quando terminar
  useEffect(() => {
    if (isStreaming) {
      setCollapsed(false)
    } else if (hasText) {
      // Só recolhe automático se tiver texto e não estiver mais streaming
      // Pequeno delay pra dar tempo de ver o resultado
      const timer = setTimeout(() => setCollapsed(true), 800)
      return () => clearTimeout(timer)
    }
  }, [hasText, isStreaming])

  // Scroll automático para acompanhar o pensamento
  useEffect(() => {
    if (bodyRef.current && !collapsed && isStreaming) {
      const frame = requestAnimationFrame(() => {
        if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
      })
      return () => cancelAnimationFrame(frame)
    }
  }, [text, collapsed, isStreaming])

  // Se não tem texto e não está streaming, não mostra nada
  if (!text && !isStreaming) return null

  return (
    <div
      className="thinking-block rounded-xl border overflow-hidden transition-all duration-300 mb-3"
      style={{
        borderColor: 'var(--border)',
        background: 'var(--bg-tertiary)',
        opacity: text ? 1 : 0.7,
      }}
    >
      {/* Header clicável */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5"
        style={{ color: 'var(--text-secondary)' }}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <Brain size={14} style={{ color: 'var(--accent)' }} />

        {isStreaming ? (
          <>
            <span style={{ color: 'var(--accent)' }}>Pensando</span>
            <span className="flex gap-0.5">
              <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          </>
        ) : (
          <>
            <span>Raciocínio</span>
            <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
              · {(text.length / 4).toFixed(0)} chars
            </span>
          </>
        )}
      </button>

      {/* Body expandível */}
      <div
        className="transition-all duration-300 overflow-hidden"
        style={{
          maxHeight: collapsed ? '0px' : '400px',
          opacity: collapsed ? 0 : 1,
        }}
      >
        <div
          ref={bodyRef}
          className="px-3 pb-3 pt-1 text-xs leading-relaxed whitespace-pre-wrap max-h-[320px] overflow-y-auto"
          style={{ color: 'var(--text-secondary)', fontFamily: 'monospace' }}
        >
          {text || (isStreaming ? 'Aguardando o provider enviar o raciocínio…' : '')}
          {isStreaming && <span className="typing-cursor">▊</span>}
        </div>
      </div>
    </div>
  )
}
