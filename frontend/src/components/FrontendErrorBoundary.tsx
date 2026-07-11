import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { detachActiveChatStreams } from '../hooks/useChatStore'

const LAST_FRONTEND_ERROR_KEY = 'chatbot_last_frontend_error_v1'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class FrontendErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The persistent server job continues; only the broken browser reader is detached.
    detachActiveChatStreams()
    const diagnostic = {
      occurred_at: new Date().toISOString(),
      message: error.message,
      stack: error.stack || '',
      component_stack: info.componentStack || '',
      page: `${window.location.origin}${window.location.pathname}`,
      user_agent: navigator.userAgent,
    }
    try {
      localStorage.setItem(LAST_FRONTEND_ERROR_KEY, JSON.stringify(diagnostic))
    } catch {
      // Recovery UI must remain available even when browser storage is blocked.
    }
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <main
        className="grid min-h-[100dvh] place-items-center p-5"
        style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
      >
        <section
          className="w-full max-w-lg rounded-3xl border p-6 shadow-2xl"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
          role="alert"
        >
          <div
            className="mb-4 grid h-12 w-12 place-items-center rounded-2xl"
            style={{ background: '#fef2f2', color: '#dc2626' }}
          >
            <AlertTriangle size={24} />
          </div>
          <h1 className="text-xl font-black">A interface foi interrompida</h1>
          <p className="mt-2 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            A resposta continua salva no servidor. Recarregue para recuperar a conversa sem reenviar sua pergunta.
          </p>
          <p
            className="mt-4 max-h-28 overflow-auto rounded-xl p-3 font-mono text-xs"
            style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}
          >
            {this.state.error.message}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-sm font-bold text-white"
            style={{ background: 'var(--accent)' }}
          >
            <RefreshCw size={17} />
            Recarregar e recuperar conversa
          </button>
          <p className="mt-3 text-center text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
            O diagnostico tecnico foi preservado somente neste navegador.
          </p>
        </section>
      </main>
    )
  }
}
