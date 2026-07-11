import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, ExternalLink, Wrench } from 'lucide-react'
import type { SkillActivity } from '../lib/api'


interface Props {
  activities: SkillActivity[]
}


export function SkillActivityBlock({ activities }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div
      className="mb-3 overflow-hidden rounded-xl border"
      style={{ borderColor: '#16a34a', background: 'rgba(22, 163, 74, 0.08)' }}
    >
      <button
        type="button"
        onClick={() => setCollapsed(value => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-semibold transition-colors hover:bg-green-500/10"
        style={{ color: '#16a34a' }}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <Wrench size={14} />
        <span>Ferramentas e Skills</span>
        <span className="ml-auto rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-black uppercase text-green-700">
          {activities.length} usada{activities.length === 1 ? '' : 's'}
        </span>
      </button>

      {!collapsed && (
        <div className="space-y-2 border-t px-3 py-3" style={{ borderColor: 'rgba(22, 163, 74, 0.25)' }}>
          {activities.map((activity, index) => (
            <div key={`${activity.name}-${index}`} className="rounded-lg bg-black/10 px-3 py-2 dark:bg-white/5">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={15} style={{ color: '#16a34a' }} />
                <span className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                  {activity.label}
                </span>
                <span className="ml-auto text-[10px] font-black uppercase" style={{ color: '#16a34a' }}>
                  Concluida
                </span>
              </div>
              <p className="mt-1 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                Skill: {activity.name}
                {activity.source_count > 0 ? ` · ${activity.source_count} fontes verificadas` : ''}
              </p>
              {activity.query ? (
                <p className="mt-1 break-words rounded-md bg-black/10 px-2 py-1 font-mono text-[10px] dark:bg-black/20" style={{ color: 'var(--text-secondary)' }}>
                  Consulta usada: {activity.query}
                </p>
              ) : null}
              {activity.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {activity.sources.map(source => (
                    <a
                      key={source.url}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold hover:bg-green-500/10"
                      style={{ borderColor: 'rgba(22, 163, 74, 0.35)', color: '#16a34a' }}
                    >
                      {source.label}
                      <ExternalLink size={10} />
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
