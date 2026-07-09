import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { X } from 'lucide-react'
import { api, type SkillInfo, type SkillRunInfo } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

export function SkillsPanel({ open, onClose }: Props) {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [runs, setRuns] = useState<SkillRunInfo[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [nextSkills, nextRuns] = await Promise.all([
        api.listSkills(),
        api.listSkillRuns(10),
      ])
      setSkills(nextSkills)
      setRuns(nextRuns.runs)
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

        <div className="mt-5 max-h-[calc(100vh-105px)] space-y-5 overflow-y-auto pr-1">
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-black" style={{ color: 'var(--text-primary)' }}>Skills disponiveis</h3>
              <button
                onClick={load}
                className="rounded-lg px-2 py-1 text-xs font-semibold"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
              >
                Atualizar
              </button>
            </div>
          {loading ? (
            <p style={{ color: 'var(--text-secondary)' }}>Carregando...</p>
          ) : skills.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>Nenhuma skill cadastrada.</p>
          ) : skills.map(skill => {
            const command = typeof skill.definition.command === 'string' ? skill.definition.command : ''
            const examples = Array.isArray(skill.definition.examples)
              ? skill.definition.examples.filter((example): example is string => typeof example === 'string')
              : []

            return (
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
              {command && (
                <div className="mt-3 rounded-lg px-3 py-2 text-xs" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                  <p className="mb-1 font-semibold">Comando</p>
                  <code className="whitespace-pre-wrap break-all">{command}</code>
                </div>
              )}
              {examples.length > 0 && (
                <p className="mt-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  Exemplo: <span style={{ color: 'var(--text-secondary)' }}>{examples[0]}</span>
                </p>
              )}
            </div>
            )
          })}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-black" style={{ color: 'var(--text-primary)' }}>Execucoes recentes</h3>
            {runs.length === 0 ? (
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Nenhuma skill executada ainda.</p>
            ) : (
              <div className="space-y-2">
                {runs.map(run => (
                  <div
                    key={run.id}
                    className="rounded-2xl border p-3"
                    style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-bold" style={{ color: 'var(--text-primary)' }}>{run.skill_name}</p>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase"
                        style={{
                          background: run.status === 'completed' ? '#dcfce7' : '#fee2e2',
                          color: run.status === 'completed' ? '#16a34a' : '#dc2626',
                        }}
                      >
                        {run.status}
                      </span>
                    </div>
                    {run.output_summary && (
                      <p className="mt-2 line-clamp-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {run.output_summary}
                      </p>
                    )}
                    {run.error_message && (
                      <p className="mt-2 text-xs" style={{ color: '#dc2626' }}>{run.error_message}</p>
                    )}
                    <p className="mt-2 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                      {run.started_at ? new Date(run.started_at).toLocaleString() : 'sem data'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  )
}
