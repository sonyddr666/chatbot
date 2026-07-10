import { useState } from 'react'
import toast from 'react-hot-toast'
import { Check, CheckCircle2, Database, FileEdit, FilePlus2, FolderPlus, MoveRight, RefreshCw, Trash2, X } from 'lucide-react'
import { api, type WorkspaceAction, type WorkspaceActionPlan } from '../lib/api'

interface Props {
  plan: WorkspaceActionPlan
}

function actionDetails(action: WorkspaceAction) {
  if (action.operation === 'mkdir') return { icon: FolderPlus, title: 'Criar pasta', path: action.path || '' }
  if (action.operation === 'write_file') {
    return {
      icon: action.mode === 'edit' ? FileEdit : FilePlus2,
      title: action.mode === 'edit' ? 'Editar arquivo' : 'Criar arquivo',
      path: action.path || '',
    }
  }
  if (action.operation === 'move') {
    return { icon: MoveRight, title: 'Mover ou renomear', path: `${action.source} -> ${action.target}` }
  }
  return {
    icon: Trash2,
    title: action.recursive ? 'Apagar pasta e conteudo' : 'Apagar',
    path: action.path || '',
  }
}

export function WorkspacePlanCard({ plan }: Props) {
  const [current, setCurrent] = useState(plan)
  const [busy, setBusy] = useState(false)
  const [ragPaths, setRagPaths] = useState<string[]>([])
  const [ragDone, setRagDone] = useState<string[]>([])
  const [ragProgress, setRagProgress] = useState('')
  const pending = current.status === 'pending'
  const applied = current.status === 'applied'
  const statusLabel = applied ? 'Concluido' : current.status === 'cancelled' ? 'Cancelado' : current.status
  const eligibleRagPaths = current.actions
    .filter(action => action.operation === 'write_file' && action.path)
    .map(action => action.path as string)

  const applyPlan = async () => {
    setBusy(true)
    try {
      const applied = await api.workspaceAiApplyPlan(current.id)
      setCurrent(applied)
      window.dispatchEvent(new CustomEvent('workspace-changed'))
      toast.success('Plano aplicado no Workspace')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao aplicar plano')
    } finally {
      setBusy(false)
    }
  }

  const cancelPlan = async () => {
    setBusy(true)
    try {
      const cancelled = await api.workspaceAiCancelPlan(current.id)
      setCurrent(cancelled)
      toast.success('Plano cancelado sem alterar arquivos')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao cancelar plano')
    } finally {
      setBusy(false)
    }
  }

  const addSelectedToRag = async () => {
    if (ragPaths.length === 0) return
    setBusy(true)
    setRagProgress('Preparando arquivos selecionados...')
    const completed: string[] = []
    try {
      for (const [index, path] of ragPaths.entries()) {
        setRagProgress(`Processando ${index + 1} de ${ragPaths.length}: ${path}`)
        await api.workspaceRagIngest(path)
        completed.push(path)
      }
      setRagDone(previous => [...new Set([...previous, ...completed])])
      setRagPaths([])
      window.dispatchEvent(new CustomEvent('documents-changed'))
      toast.success(`${completed.length} arquivo(s) selecionado(s) adicionados ao RAG`)
    } catch (error) {
      setRagDone(previous => [...new Set([...previous, ...completed])])
      toast.error(error instanceof Error ? error.message : 'Falha ao adicionar ao RAG')
    } finally {
      setBusy(false)
      setRagProgress('')
    }
  }

  return (
    <div
      className="mt-3 overflow-hidden rounded-2xl border"
      style={{ borderColor: applied ? '#16a34a' : 'var(--border)', background: 'var(--bg-secondary)' }}
    >
      <div className="border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.18em]" style={{ color: 'var(--accent)' }}>
              Plano da IA para o Workspace
            </p>
            <p className="mt-1 text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{current.summary}</p>
          </div>
          <span
            className="rounded-full px-2 py-1 text-[10px] font-bold uppercase"
            style={{
              background: pending ? 'rgba(234,179,8,.16)' : applied ? 'rgba(22,163,74,.16)' : 'var(--bg-tertiary)',
              color: pending ? '#a16207' : applied ? '#16a34a' : 'var(--text-secondary)',
            }}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="space-y-2 p-3">
        {current.actions.map((action, index) => {
          const details = actionDetails(action)
          const Icon = details.icon
          return (
            <details
              key={`${action.operation}-${index}`}
              className="rounded-xl border px-3 py-2"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-primary)' }}
            >
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm">
                <Icon size={15} style={{ color: action.operation === 'delete' ? 'var(--danger)' : 'var(--accent)' }} />
                <span className="font-bold">{details.title}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {details.path}
                </span>
              </summary>
              {action.diff ? (
                <pre
                  className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded-lg p-2 text-[11px]"
                  style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
                >
                  {action.diff}
                </pre>
              ) : null}
            </details>
          )
        })}
      </div>

      {pending ? (
        <div className="grid grid-cols-2 gap-2 border-t p-3" style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={cancelPlan}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
          >
            <X size={14} /> Cancelar
          </button>
          <button
            onClick={applyPlan}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            <Check size={14} /> {busy ? 'Executando...' : 'Confirmar e executar'}
          </button>
        </div>
      ) : null}

      {applied ? (
        <div className="border-t p-3" style={{ borderColor: 'rgba(22,163,74,.35)', background: 'rgba(22,163,74,.12)' }}>
          <div className="flex items-start gap-2" style={{ color: '#16a34a' }}>
            <CheckCircle2 className="mt-0.5 shrink-0" size={18} />
            <div>
              <p className="text-sm font-black">Tudo concluido</p>
              <p className="mt-0.5 text-xs font-medium">
                Criei e organizei tudo que voce pediu. O Workspace ja esta atualizado.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {current.status === 'applied' && eligibleRagPaths.length > 0 ? (
        <div className="border-t p-3" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2 text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
            <Database size={14} style={{ color: 'var(--accent)' }} />
            RAG opcional: selecione somente o que deve virar conhecimento
          </div>
          <div className="mt-2 space-y-1">
            {eligibleRagPaths.map(path => (
              <label key={path} className="flex cursor-pointer items-center gap-2 rounded-lg border border-transparent px-2 py-1.5 text-xs transition-all hover:border-green-600 hover:brightness-125" style={{ background: 'var(--bg-primary)' }}>
                <input
                  type="checkbox"
                  checked={ragPaths.includes(path) || ragDone.includes(path)}
                  disabled={busy || ragDone.includes(path)}
                  onChange={event => setRagPaths(previous => event.target.checked ? [...previous, path] : previous.filter(item => item !== path))}
                />
                <span className="min-w-0 flex-1 truncate font-mono">{path}</span>
                {ragDone.includes(path) ? <span style={{ color: '#16a34a' }}>no RAG</span> : null}
              </label>
            ))}
          </div>
          {busy && ragProgress ? (
            <div className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold" style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>
              <RefreshCw className="animate-spin" size={14} /> {ragProgress}
            </div>
          ) : null}
          {!busy && ragPaths.length === 0 && eligibleRagPaths.some(path => !ragDone.includes(path)) ? (
            <p className="mt-2 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Marque um arquivo acima para ativar o botao.</p>
          ) : null}
          <button
            onClick={addSelectedToRag}
            disabled={busy || ragPaths.length === 0}
            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold transition-all enabled:cursor-pointer enabled:hover:brightness-150 enabled:hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: 'var(--accent-light)', borderColor: 'var(--accent)', color: 'var(--accent)' }}
          >
            {busy ? <RefreshCw className="animate-spin" size={14} /> : <Database size={14} />}
            {busy ? 'Adicionando ao RAG...' : 'Adicionar selecionados ao RAG'}
          </button>
        </div>
      ) : null}
    </div>
  )
}
