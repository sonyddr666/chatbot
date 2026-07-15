import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, ExternalLink, Loader2, Wrench, XCircle } from 'lucide-react'
import type { SkillActivity } from '../lib/api'

interface Props {
  activities: SkillActivity[]
}

const stateStyle = (status: SkillActivity['status']) => {
  if (status === 'running') return {
    color: '#f97316',
    background: 'rgba(249, 115, 22, 0.08)',
    border: 'rgba(249, 115, 22, 0.45)',
    label: 'Em execucao',
  }
  if (status === 'failed') return {
    color: '#ef4444',
    background: 'rgba(239, 68, 68, 0.08)',
    border: 'rgba(239, 68, 68, 0.45)',
    label: 'Falhou',
  }
  return {
    color: '#16a34a',
    background: 'rgba(22, 163, 74, 0.08)',
    border: 'rgba(22, 163, 74, 0.45)',
    label: 'Concluida',
  }
}

export function SkillActivityBlock({ activities }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const overallStatus: SkillActivity['status'] = activities.some(item => item.status === 'running')
    ? 'running'
    : activities.some(item => item.status === 'failed') ? 'failed' : 'completed'
  const overall = stateStyle(overallStatus)

  return (
    <div className="mb-3 overflow-hidden rounded-xl border" style={{ borderColor: overall.border, background: overall.background }}>
      <button
        type="button"
        onClick={() => setCollapsed(value => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-semibold transition-opacity hover:opacity-80"
        style={{ color: overall.color }}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <Wrench size={14} />
        <span>Ferramentas e Skills</span>
        <span className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-black uppercase" style={{ color: overall.color, background: overall.background }}>
          {activities.length} usada{activities.length === 1 ? '' : 's'}
        </span>
      </button>

      {!collapsed && (
        <div className="space-y-2 border-t px-3 py-3" style={{ borderColor: overall.border }}>
          {activities.map((activity, index) => {
            const state = stateStyle(activity.status)
            const isImage = activity.name === 'image_generate' || activity.name === 'image_edit'
            return (
              <div
                key={activity.call_id || `${activity.name}-${index}`}
                className="rounded-lg border px-3 py-2"
                style={{ borderColor: state.border, background: state.background }}
              >
                <div className="flex items-center gap-2">
                  {activity.status === 'running'
                    ? <Loader2 size={15} className="animate-spin" style={{ color: state.color }} />
                    : activity.status === 'failed'
                      ? <XCircle size={15} style={{ color: state.color }} />
                      : <CheckCircle2 size={15} style={{ color: state.color }} />}
                  <span className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>{activity.label}</span>
                  <span className="ml-auto text-[10px] font-black uppercase" style={{ color: state.color }}>{state.label}</span>
                </div>
                <p className="mt-1 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {isImage ? `Ferramenta: ${activity.name}` : `Skill: ${activity.name}`}
                  {activity.provider ? ` · ${activity.provider}` : ''}
                  {activity.source_count > 0 ? ` · ${activity.source_count} fontes verificadas` : ''}
                </p>
                {activity.query ? (
                  <p className="mt-1 break-words rounded-md bg-black/10 px-2 py-1 font-mono text-[10px] dark:bg-black/20" style={{ color: 'var(--text-secondary)' }}>
                    {isImage ? 'Prompt usado' : 'Consulta usada'}: {activity.query}
                  </p>
                ) : null}
                {activity.sources.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {activity.sources.map(source => (
                      <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold" style={{ borderColor: state.border, color: state.color }}>
                        {source.label}<ExternalLink size={10} />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
