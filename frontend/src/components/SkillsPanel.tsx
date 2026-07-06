import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { X } from 'lucide-react'
import { api, type SkillInfo } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

export function SkillsPanel({ open, onClose }: Props) {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setSkills(await api.listSkills())
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar skills')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) load()
  }, [open])

  const toggle = async (skill: SkillInfo) => {
    try {
      await api.toggleSkill(skill.name, !skill.enabled)
      setSkills(items => items.map(item => item.name === skill.name ? { ...item, enabled: !skill.enabled } : item))
      toast.success(`${skill.name} ${skill.enabled ? 'desativada' : 'ativada'}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao atualizar skill')
    }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l p-4 shadow-xl"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--accent)' }}>Skills</p>
            <h2 className="text-xl font-black" style={{ color: 'var(--text-primary)' }}>Habilidades do usuario</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {loading ? (
            <p style={{ color: 'var(--text-secondary)' }}>Carregando...</p>
          ) : skills.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>Nenhuma skill cadastrada.</p>
          ) : skills.map(skill => (
            <div
              key={skill.name}
              className="rounded-2xl border p-4"
              style={{ background: 'var(--bg-secondary)', borderColor: skill.enabled ? 'var(--accent)' : 'var(--border)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>{skill.name}</h3>
                  <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>{skill.description}</p>
                  <p className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {skill.kind} · risco {skill.risk_level}
                    {skill.requires_network ? ' · rede' : ''}
                    {skill.requires_shell ? ' · shell' : ''}
                  </p>
                </div>
                <button
                  onClick={() => toggle(skill)}
                  className="rounded-full px-3 py-1 text-xs font-bold"
                  style={{
                    background: skill.enabled ? 'var(--accent)' : 'var(--bg-tertiary)',
                    color: skill.enabled ? '#fff' : 'var(--text-secondary)',
                  }}
                >
                  {skill.enabled ? 'ON' : 'OFF'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}
