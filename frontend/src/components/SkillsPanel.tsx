import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { CheckCircle2, Loader2, Save, Wifi, X } from 'lucide-react'
import { api, type PerplexoStatus, type SkillInfo, type SkillRunInfo } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

export function SkillsPanel({ open, onClose }: Props) {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [runs, setRuns] = useState<SkillRunInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [savingSkill, setSavingSkill] = useState('')
  const [testingPerplexo, setTestingPerplexo] = useState(false)
  const [perplexoStatus, setPerplexoStatus] = useState<PerplexoStatus | null>(null)
  const loadRequestRef = useRef(0)

  const load = async () => {
    const requestId = ++loadRequestRef.current
    setLoading(true)
    try {
      const [nextSkills, nextRuns, nextPerplexoStatus] = await Promise.all([
        api.listSkills(),
        api.listSkillRuns(10),
        api.getPerplexoStatus().catch(() => null),
      ])
      if (requestId !== loadRequestRef.current) return
      setSkills(nextSkills)
      setRuns(nextRuns.runs)
      setPerplexoStatus(current => nextPerplexoStatus
        ? { ...current, ...nextPerplexoStatus, online: current?.online }
        : current)
    } catch (err) {
      if (requestId !== loadRequestRef.current) return
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar skills')
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false)
    }
  }

  useEffect(() => {
    if (open) load()
  }, [open])

  const toggle = async (skill: SkillInfo) => {
    try {
      await api.toggleSkill(skill.name, !skill.enabled, skill.config)
      setSkills(items => items.map(item => item.name === skill.name ? { ...item, enabled: !skill.enabled } : item))
      toast.success(`${skill.name} ${skill.enabled ? 'desativada' : 'ativada'}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao atualizar skill')
    }
  }

  const updateSkillConfig = (name: string, key: string, value: unknown) => {
    setSkills(items => items.map(item => item.name === name
      ? { ...item, config: { ...(item.config || {}), [key]: value } }
      : item))
  }

  const saveSkillConfig = async (skill: SkillInfo) => {
    setSavingSkill(skill.name)
    try {
      await api.toggleSkill(skill.name, skill.enabled, skill.config || {})
      toast.success('Configuracao da pesquisa salva')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao salvar configuracao')
    } finally {
      setSavingSkill('')
    }
  }

  const testPerplexo = async () => {
    setTestingPerplexo(true)
    try {
      const status = await api.testPerplexo()
      setPerplexoStatus(current => ({
        ...status,
        skill: current?.skill || 'perplexo_search',
        configured: true,
        base_url: current?.base_url || '',
        timeout_seconds: current?.timeout_seconds || 25,
      }))
      toast.success('Perplexo conectado e pronto para pesquisar')
      const nextRuns = await api.listSkillRuns(10)
      setRuns(nextRuns.runs)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Perplexo indisponivel')
    } finally {
      setTestingPerplexo(false)
    }
  }

  const configString = (skill: SkillInfo, key: string, fallback: string) => {
    const value = skill.config?.[key]
    return typeof value === 'string' ? value : fallback
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 z-50 h-full w-full border-l p-4 shadow-xl sm:max-w-md"
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

        <div className="mt-5 max-h-[calc(100dvh-105px)] space-y-5 overflow-y-auto pr-1">
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
            const isPerplexo = skill.name === 'perplexo_search'

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
              {isPerplexo && (
                <div className="mt-4 space-y-3 rounded-xl border p-3" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--border)' }}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: perplexoStatus?.configured ? '#16a34a' : '#dc2626' }}>
                      {perplexoStatus?.configured ? <CheckCircle2 size={15} /> : <X size={15} />}
                      {perplexoStatus?.configured ? 'Chave configurada no servidor' : 'MCP_API_KEY nao configurada'}
                    </div>
                    {perplexoStatus?.online && (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-black uppercase text-green-700">Online</span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      Modelo
                      <select
                        value={configString(skill, 'model', 'best')}
                        onChange={event => updateSkillConfig(skill.name, 'model', event.target.value)}
                        className="mt-1 w-full rounded-lg border px-2 py-2"
                        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                      >
                        <option value="best">Automatico</option>
                        <option value="deep-research">Pesquisa profunda</option>
                      </select>
                    </label>
                    <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      Foco
                      <select
                        value={configString(skill, 'focus', 'web')}
                        onChange={event => updateSkillConfig(skill.name, 'focus', event.target.value)}
                        className="mt-1 w-full rounded-lg border px-2 py-2"
                        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                      >
                        <option value="web">Web</option>
                        <option value="academic">Academico</option>
                      </select>
                    </label>
                    <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      Periodo
                      <select
                        value={configString(skill, 'time_range', 'week')}
                        onChange={event => updateSkillConfig(skill.name, 'time_range', event.target.value)}
                        className="mt-1 w-full rounded-lg border px-2 py-2"
                        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                      >
                        <option value="day">Ultimo dia</option>
                        <option value="week">Ultima semana</option>
                        <option value="month">Ultimo mes</option>
                        <option value="year">Ultimo ano</option>
                        <option value="all">Todo periodo</option>
                      </select>
                    </label>
                    <label className="flex items-end gap-2 pb-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                      <input
                        type="checkbox"
                        checked={skill.config?.fallback_enabled !== false}
                        onChange={event => updateSkillConfig(skill.name, 'fallback_enabled', event.target.checked)}
                      />
                      Usar fallback se ficar offline
                    </label>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => saveSkillConfig(skill)}
                      disabled={savingSkill === skill.name}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold text-white disabled:opacity-60"
                      style={{ background: 'var(--accent)' }}
                    >
                      {savingSkill === skill.name ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      Salvar
                    </button>
                    <button
                      onClick={testPerplexo}
                      disabled={testingPerplexo || !perplexoStatus?.configured}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold disabled:opacity-50"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    >
                      {testingPerplexo ? <Loader2 size={14} className="animate-spin" /> : <Wifi size={14} />}
                      {testingPerplexo ? 'Testando...' : 'Testar conexao'}
                    </button>
                  </div>
                </div>
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
                      <details className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        <summary className="cursor-pointer font-semibold" style={{ color: 'var(--accent)' }}>
                          Ver resultado completo
                        </summary>
                        <div className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg p-2" style={{ background: 'var(--bg-tertiary)' }}>
                          {run.output_summary}
                        </div>
                      </details>
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
