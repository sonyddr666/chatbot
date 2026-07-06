import { useState, type FormEvent } from 'react'
import toast from 'react-hot-toast'
import { api, setAuthToken, type UserInfo } from '../lib/api'

interface Props {
  onAuthenticated: (user: UserInfo) => void
}

export function AuthPanel({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    email: '',
    username: '',
    display_name: '',
    login: '',
    password: '',
  })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const response = mode === 'login'
        ? await api.login({ login: form.login || form.email || form.username, password: form.password })
        : await api.register({
            email: form.email,
            username: form.username,
            display_name: form.display_name,
            password: form.password,
          })
      setAuthToken(response.access_token)
      onAuthenticated(response.user)
      toast.success(mode === 'login' ? 'Login feito' : 'Conta criada')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha na autenticacao')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4" style={{
      background: 'radial-gradient(circle at top left, var(--accent-light), transparent 34%), var(--bg-primary)',
    }}>
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-3xl border p-6 shadow-xl"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
      >
        <p className="text-xs font-semibold uppercase tracking-[0.24em]" style={{ color: 'var(--accent)' }}>
          Chatbot pessoal
        </p>
        <h1 className="mt-2 text-3xl font-black" style={{ color: 'var(--text-primary)' }}>
          {mode === 'login' ? 'Entrar' : 'Criar conta'}
        </h1>
        <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
          Cada usuario tem conversas, RAG, onboarding e skills separados.
        </p>

        <div className="mt-6 space-y-3">
          {mode === 'register' ? (
            <>
              <Input label="Email" value={form.email} onChange={email => setForm(s => ({ ...s, email }))} type="email" />
              <Input label="Usuario" value={form.username} onChange={username => setForm(s => ({ ...s, username }))} />
              <Input label="Nome" value={form.display_name} onChange={display_name => setForm(s => ({ ...s, display_name }))} />
            </>
          ) : (
            <Input label="Email ou usuario" value={form.login} onChange={login => setForm(s => ({ ...s, login }))} />
          )}
          <Input label="Senha" value={form.password} onChange={password => setForm(s => ({ ...s, password }))} type="password" />
        </div>

        <button
          disabled={loading}
          className="mt-5 w-full rounded-2xl px-4 py-3 font-bold transition hover:scale-[1.01] disabled:opacity-60"
          style={{ background: 'var(--accent)', color: '#fff' }}
        >
          {loading ? 'Aguarde...' : mode === 'login' ? 'Entrar' : 'Cadastrar'}
        </button>

        <button
          type="button"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="mt-4 w-full text-sm font-medium"
          style={{ color: 'var(--text-secondary)' }}
        >
          {mode === 'login' ? 'Nao tenho conta ainda' : 'Ja tenho conta'}
        </button>
      </form>
    </div>
  )
}

function Input({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <input
        required
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border px-3 py-2 outline-none"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
      />
    </label>
  )
}
