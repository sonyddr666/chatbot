import { useEffect, useState, type ChangeEvent } from 'react'
import toast from 'react-hot-toast'
import { ArrowLeft, FileText, Folder, FolderPlus, Pencil, Save, Trash2, X } from 'lucide-react'
import { api, type WorkspaceNode } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

export function WorkspacePanel({ open, onClose }: Props) {
  const [path, setPath] = useState('')
  const [nodes, setNodes] = useState<WorkspaceNode[]>([])
  const [selectedFile, setSelectedFile] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [moveTarget, setMoveTarget] = useState('')

  const loadTree = async (nextPath = path) => {
    setLoading(true)
    try {
      const tree = await api.workspaceTree(nextPath)
      setPath(tree.path)
      setNodes(tree.nodes)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao carregar workspace')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) loadTree('')
  }, [open])

  const openNode = async (node: WorkspaceNode) => {
    if (node.kind === 'folder') {
      setSelectedFile('')
      setContent('')
      setMoveTarget('')
      await loadTree(node.path)
      return
    }

    try {
      const file = await api.workspaceReadFile(node.path)
      setSelectedFile(file.path)
      setContent(file.content)
      setMoveTarget(file.path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao abrir arquivo')
    }
  }

  const goUp = async () => {
    if (!path) return
    const parent = path.split('/').slice(0, -1).join('/')
    setSelectedFile('')
    setContent('')
    setMoveTarget('')
    await loadTree(parent)
  }

  const createFolder = async () => {
    const target = normalizeTarget(newPath, path)
    if (!target) return toast.error('Informe o nome da pasta')
    try {
      await api.workspaceMkdir(target)
      setNewPath('')
      toast.success('Pasta criada')
      await loadTree(path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao criar pasta')
    }
  }

  const createFile = async () => {
    const target = normalizeTarget(newPath, path)
    if (!target) return toast.error('Informe o nome do arquivo')
    try {
      await api.workspaceWriteFile(target, '')
      setNewPath('')
      toast.success('Arquivo criado')
      await loadTree(path)
      const file = await api.workspaceReadFile(target)
      setSelectedFile(file.path)
      setContent(file.content)
      setMoveTarget(file.path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao criar arquivo')
    }
  }

  const saveFile = async () => {
    if (!selectedFile) return
    setSaving(true)
    try {
      await api.workspaceWriteFile(selectedFile, content)
      toast.success('Arquivo salvo')
      await loadTree(path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const moveSelected = async () => {
    if (!selectedFile || !moveTarget || moveTarget === selectedFile) return
    try {
      const info = await api.workspaceMovePath(selectedFile, moveTarget)
      toast.success('Arquivo movido')
      setSelectedFile(info.path)
      setMoveTarget(info.path)
      await loadTree(path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao mover arquivo')
    }
  }

  const deleteSelected = async () => {
    if (!selectedFile) return
    try {
      await api.workspaceDeletePath(selectedFile)
      toast.success('Arquivo removido')
      setSelectedFile('')
      setContent('')
      setMoveTarget('')
      await loadTree(path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Falha ao remover')
    }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-3xl flex-col border-l p-4 shadow-xl"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--accent)' }}>
              Workspace
            </p>
            <h2 className="text-xl font-black" style={{ color: 'var(--text-primary)' }}>
              Arquivos do usuario
            </h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 md:grid-cols-[260px_1fr]">
          <section className="min-h-0 rounded-2xl border p-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={goUp}
                disabled={!path}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold disabled:opacity-40"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
              >
                <ArrowLeft size={14} />
                Voltar
              </button>
              <span className="truncate text-xs" style={{ color: 'var(--text-tertiary)' }}>
                /{path || 'workspace'}
              </span>
            </div>

            <div className="mt-3 flex gap-2">
              <input
                value={newPath}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setNewPath(event.target.value)}
                placeholder="novo.md ou pasta"
                className="min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button onClick={createFile} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>
                Criar arquivo
              </button>
              <button onClick={createFolder} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                <span className="inline-flex items-center gap-1"><FolderPlus size={13} /> Pasta</span>
              </button>
            </div>

            <div className="mt-4 max-h-[calc(100vh-230px)] space-y-2 overflow-y-auto pr-1">
              {loading ? (
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Carregando...</p>
              ) : nodes.length === 0 ? (
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Workspace vazio.</p>
              ) : nodes.map(node => (
                <button
                  key={node.path}
                  type="button"
                  onClick={() => openNode(node)}
                  className="flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm transition hover:scale-[1.01]"
                  style={{
                    background: selectedFile === node.path ? 'var(--accent-light)' : 'var(--bg-primary)',
                    borderColor: selectedFile === node.path ? 'var(--accent)' : 'var(--border)',
                    color: 'var(--text-primary)',
                  }}
                >
                  {node.kind === 'folder' ? <Folder size={16} /> : <FileText size={16} />}
                  <span className="min-w-0 flex-1 truncate">{node.name}</span>
                  {node.kind === 'file' && (
                    <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{node.size}b</span>
                  )}
                </button>
              ))}
            </div>
          </section>

          <section className="flex min-h-0 flex-col rounded-2xl border p-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
            {selectedFile ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold" style={{ color: 'var(--text-tertiary)' }}>Arquivo aberto</p>
                    <h3 className="truncate font-bold" style={{ color: 'var(--text-primary)' }}>{selectedFile}</h3>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={saveFile} disabled={saving} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-60" style={{ background: 'var(--accent)', color: '#fff' }}>
                      <Save size={14} />
                      {saving ? 'Salvando...' : 'Salvar'}
                    </button>
                    <button onClick={deleteSelected} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold" style={{ background: '#fee2e2', color: '#dc2626' }}>
                      <Trash2 size={14} />
                      Deletar
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex gap-2">
                  <input
                    value={moveTarget}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setMoveTarget(event.target.value)}
                    className="min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm outline-none"
                    style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  />
                  <button onClick={moveSelected} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                    <Pencil size={14} />
                    Mover
                  </button>
                </div>

                <textarea
                  value={content}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setContent(event.target.value)}
                  className="mt-3 min-h-0 flex-1 resize-none rounded-2xl border p-4 font-mono text-sm outline-none"
                  style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  spellCheck={false}
                />
              </>
            ) : (
              <div className="grid flex-1 place-items-center text-center">
                <div>
                  <FileText className="mx-auto mb-3 opacity-50" size={42} />
                  <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>Nenhum arquivo aberto</h3>
                  <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
                    Selecione um arquivo ou crie um novo no painel ao lado.
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  )
}

function normalizeTarget(value: string, currentPath: string): string {
  const trimmed = value.trim().replace(/^\/+/, '')
  if (!trimmed) return ''
  if (!currentPath || trimmed.includes('/')) return trimmed
  return `${currentPath}/${trimmed}`
}
