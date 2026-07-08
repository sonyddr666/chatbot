import { Check, X } from 'lucide-react'
import type { WorkspacePatchPreview } from '../lib/api'

interface Props {
  preview: WorkspacePatchPreview
  applying: boolean
  onApply: () => void
  onCancel: () => void
}

export function DiffViewer({ preview, applying, onApply, onCancel }: Props) {
  const lines = preview.diff.split('\n')

  return (
    <div
      className="mt-3 overflow-hidden rounded-2xl border"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-primary)' }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b p-3" style={{ borderColor: 'var(--border)' }}>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: 'var(--accent)' }}>
            Preview de alteracao
          </p>
          <p className="truncate text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            {preview.path}
          </p>
          <p className="mt-1 font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
            expected_checksum: {preview.expected_checksum.slice(0, 12)}...
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold"
            style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
          >
            <X size={14} />
            Cancelar
          </button>
          <button
            onClick={onApply}
            disabled={applying}
            className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-60"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            <Check size={14} />
            {applying ? 'Aplicando...' : 'Aplicar patch aprovado'}
          </button>
        </div>
      </div>

      <pre className="max-h-64 overflow-auto p-3 text-xs leading-relaxed">
        {lines.map((line, index) => {
          const color = line.startsWith('+') ? '#16a34a' : line.startsWith('-') ? '#dc2626' : 'var(--text-secondary)'
          const background = line.startsWith('+')
            ? 'rgba(22, 163, 74, 0.08)'
            : line.startsWith('-')
              ? 'rgba(220, 38, 38, 0.08)'
              : 'transparent'
          return (
            <div key={`${index}-${line}`} className="px-2 font-mono" style={{ color, background }}>
              {line || ' '}
            </div>
          )
        })}
      </pre>
    </div>
  )
}
