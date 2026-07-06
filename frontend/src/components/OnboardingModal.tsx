import { useState, type ChangeEvent, type FormEvent } from 'react'
import toast from 'react-hot-toast'
import { api, type UserInfo } from '../lib/api'

interface Props {
  user: UserInfo
  onDone: () => void
}

export function OnboardingModal({ user, onDone }: Props) {
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    display_name: user.display_name || user.username,
    role: '',
    technical_level: '',
    preferred_tone: 'direto e pratico',
    goals: '',
    avoid: '',
  })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await api.onboarding({
        display_name: form.display_name,
        language: 'pt',
        timezone: 'America/Sao_Paulo',
        role: form.role,
        technical_level: form.technical_level,
        preferred_tone: form.preferred_tone,
        goals: splitList(form.goals),
        avoid: splitList(form.avoid),
        memory_policy: 'ask',
      })
      localStorage.setItem(`chatbot_onboarding_done_${user.id}`, '1')
      toast.success('Perfil inicial salvo no seu RAG')
      onDone()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha no onboarding')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/70 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-2xl rounded-3xl border p-6 shadow-2xl"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
      >
        <p className="text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--accent)' }}>
          Onboarding inicial
        </p>
        <h2 className="mt-2 text-2xl font-black" style={{ color: 'var(--text-primary)' }}>
          Vamos personalizar seu chatbot
        </h2>
        <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
          Isso cria um documento inicial no seu RAG pessoal para o chat ja nascer com contexto.
        </p>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <Field label="Como quer ser chamado?" value={form.display_name} onChange={display_name => setForm(s => ({ ...s, display_name }))} />
          <Field label="Area/projeto principal" value={form.role} onChange={role => setForm(s => ({ ...s, role }))} />
          <Field label="Nivel tecnico" value={form.technical_level} onChange={technical_level => setForm(s => ({ ...s, technical_level }))} />
          <Field label="Tom preferido" value={form.preferred_tone} onChange={preferred_tone => setForm(s => ({ ...s, preferred_tone }))} />
          <Field label="Objetivos, separados por virgula" value={form.goals} onChange={goals => setForm(s => ({ ...s, goals }))} textarea />
          <Field label="Evitar/nao fazer, separado por virgula" value={form.avoid} onChange={avoid => setForm(s => ({ ...s, avoid }))} textarea />
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onDone}
            className="rounded-xl px-4 py-2 text-sm font-semibold"
            style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
          >
            Pular
          </button>
          <button
            disabled={loading}
            className="rounded-xl px-4 py-2 text-sm font-bold disabled:opacity-60"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {loading ? 'Salvando...' : 'Salvar perfil inicial'}
          </button>
        </div>
      </form>
    </div>
  )
}

function splitList(value: string): string[] {
  return value.split(',').map(item => item.trim()).filter(Boolean)
}

function Field({
  label,
  value,
  onChange,
  textarea = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  textarea?: boolean
}) {
  const props = {
    value,
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value),
    className: 'mt-1 w-full rounded-xl border px-3 py-2 outline-none',
    style: { background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' },
  }
  return (
    <label className={textarea ? 'md:col-span-2 block' : 'block'}>
      <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      {textarea ? <textarea rows={3} {...props} /> : <input {...props} />}
    </label>
  )
}
