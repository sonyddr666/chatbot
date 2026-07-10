import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Send, Sparkles, StopCircle } from 'lucide-react'

interface Props {
  onSend: (message: string) => void
  busy?: boolean
  onStop?: () => void
}

export function ChatInput({ onSend, busy = false, onStop }: Props) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!busy && textareaRef.current) textareaRef.current.focus()
  }, [busy])

  const handleSend = () => {
    if (!input.trim() || busy) return
    onSend(input.trim())
    setInput('')
  }

  const handleKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (busy) return
      e.preventDefault(); handleSend()
    }
  }

  useEffect(() => {
    const el = textareaRef.current
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px' }
  }, [input])

  return (
    <div className="border-t px-4 py-3" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}>
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-2 p-1.5 rounded-xl transition-all focus-within:shadow-md"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={busy
              ? 'Continue digitando... o envio libera quando a resposta terminar'
              : 'Digite sua mensagem... (Enter para enviar, Shift+Enter para quebrar linha)'}
            rows={1}
            className="flex-1 resize-none rounded-lg px-3 py-2.5 text-[15px] outline-none bg-transparent"
            style={{ color: 'var(--text-primary)', maxHeight: '200px' }}
          />
          <div className="flex items-center gap-1">
            {busy && onStop ? (
              <button onClick={onStop}
                className="p-2.5 rounded-lg transition-colors"
                style={{ background: 'var(--danger)', color: '#fff' }}
                title="Parar">
                <StopCircle size={18} />
              </button>
            ) : (
              <button onClick={handleSend}
                disabled={busy || !input.trim()}
                className="p-2.5 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: input.trim() ? 'var(--accent)' : 'var(--border)', color: input.trim() ? '#fff' : 'var(--text-tertiary)' }}
                title="Enviar">
                {busy ? (
                  <Sparkles size={18} className="animate-pulse" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            )}
          </div>
        </div>
        <p className="text-[11px] text-center mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
          O chatbot pode cometer erros. Verifique informações importantes.
        </p>
      </div>
    </div>
  )
}
