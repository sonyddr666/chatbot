import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent, type ReactNode } from 'react'
import toast from 'react-hot-toast'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  GripVertical,
  Image as ImageIcon,
  Maximize2,
  MoveRight,
  Pencil,
  RefreshCw,
  Save,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react'
import { api, type WorkspaceNode, type WorkspacePatchPreview } from '../lib/api'
import { DiffViewer } from './DiffViewer'

interface Props {
  open: boolean
  onClose: () => void
}

interface WorkspaceTreeNode extends WorkspaceNode {
  children: WorkspaceTreeNode[]
}

type PendingTransfer =
  | { kind: 'move'; source: string; target: string }
  | { kind: 'import'; file: File; target: string }

interface PendingDelete {
  path: string
  kind: 'file' | 'folder'
}

const MAX_TREE_DEPTH = 12
const MAX_IMPORT_BYTES = 1024 * 1024
const IMAGE_EXTENSIONS = new Set([
  '.apng', '.avif', '.bmp', '.gif', '.heic', '.heif', '.ico', '.jfif',
  '.jpeg', '.jpg', '.pjp', '.pjpeg', '.png', '.svg', '.tif', '.tiff', '.webp',
])

function isImagePath(path: string) {
  const filename = path.split('/').pop() || ''
  const dot = filename.lastIndexOf('.')
  return dot >= 0 && IMAGE_EXTENSIONS.has(filename.slice(dot).toLowerCase())
}

export function WorkspacePanel({ open, onClose }: Props) {
  const [tree, setTree] = useState<WorkspaceTreeNode[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [currentFolder, setCurrentFolder] = useState('')
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedKind, setSelectedKind] = useState<'file' | 'folder' | ''>('')
  const [selectedFile, setSelectedFile] = useState('')
  const [fileMode, setFileMode] = useState<'text' | 'image' | ''>('')
  const [content, setContent] = useState('')
  const [imagePreviewUrl, setImagePreviewUrl] = useState('')
  const [imageExpanded, setImageExpanded] = useState(false)
  const [imageLoadError, setImageLoadError] = useState(false)
  const imagePreviewUrlRef = useRef('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [patchPreview, setPatchPreview] = useState<WorkspacePatchPreview | null>(null)
  const [patching, setPatching] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [moveTarget, setMoveTarget] = useState('')
  const [dragOverPath, setDragOverPath] = useState<string | null>(null)
  const [pendingTransfer, setPendingTransfer] = useState<PendingTransfer | null>(null)
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null)
  const [ragConfirm, setRagConfirm] = useState(false)
  const [ragLoading, setRagLoading] = useState(false)

  const clearImagePreview = useCallback(() => {
    if (imagePreviewUrlRef.current) URL.revokeObjectURL(imagePreviewUrlRef.current)
    imagePreviewUrlRef.current = ''
    setImagePreviewUrl('')
    setImageExpanded(false)
    setImageLoadError(false)
  }, [])

  useEffect(() => () => {
    if (imagePreviewUrlRef.current) URL.revokeObjectURL(imagePreviewUrlRef.current)
  }, [])

  useEffect(() => {
    if (!open) clearImagePreview()
  }, [open, clearImagePreview])

  const loadBranch = useCallback(async (path: string, depth = 0): Promise<WorkspaceTreeNode[]> => {
    const branch = await api.workspaceTree(path)
    if (depth >= MAX_TREE_DEPTH) return branch.nodes.map(node => ({ ...node, children: [] }))
    return Promise.all(branch.nodes.map(async node => ({
      ...node,
      children: node.kind === 'folder' ? await loadBranch(node.path, depth + 1) : [],
    })))
  }, [])

  const refreshTree = useCallback(async () => {
    setLoading(true)
    try {
      setTree(await loadBranch(''))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao carregar workspace')
    } finally {
      setLoading(false)
    }
  }, [loadBranch])

  useEffect(() => {
    if (open) void refreshTree()
  }, [open, refreshTree])

  useEffect(() => {
    const refresh = () => {
      if (open) void refreshTree()
    }
    window.addEventListener('workspace-changed', refresh)
    return () => window.removeEventListener('workspace-changed', refresh)
  }, [open, refreshTree])

  const pathExists = useCallback((target: string, nodes = tree): boolean => {
    for (const node of nodes) {
      if (node.path === target || pathExists(target, node.children)) return true
    }
    return false
  }, [tree])

  const selectFolder = (node: WorkspaceTreeNode) => {
    clearImagePreview()
    setSelectedPath(node.path)
    setSelectedKind('folder')
    setSelectedFile('')
    setFileMode('')
    setContent('')
    setMoveTarget(node.path)
    setCurrentFolder(node.path)
    setPatchPreview(null)
    setRagConfirm(false)
    setExpanded(previous => {
      const next = new Set(previous)
      if (next.has(node.path)) next.delete(node.path)
      else next.add(node.path)
      return next
    })
  }

  const openFile = async (node: WorkspaceTreeNode) => {
    try {
      if (isImagePath(node.path)) {
        const blob = await api.workspaceReadBlob(node.path)
        clearImagePreview()
        const previewUrl = URL.createObjectURL(blob)
        imagePreviewUrlRef.current = previewUrl
        setImagePreviewUrl(previewUrl)
        setSelectedPath(node.path)
        setSelectedKind('file')
        setSelectedFile(node.path)
        setFileMode('image')
        setContent('')
        setMoveTarget(node.path)
        setPatchPreview(null)
        setRagConfirm(false)
        return
      }

      const file = await api.workspaceReadFile(node.path)
      clearImagePreview()
      setSelectedPath(file.path)
      setSelectedKind('file')
      setSelectedFile(file.path)
      setFileMode('text')
      setContent(file.content)
      setMoveTarget(file.path)
      setPatchPreview(null)
      setRagConfirm(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao abrir arquivo')
    }
  }

  const createFolder = async () => {
    const target = normalizeTarget(newPath, currentFolder)
    if (!target) return toast.error('Informe o nome da pasta')
    if (pathExists(target)) return toast.error('Esse caminho ja existe')
    try {
      await api.workspaceMkdir(target)
      setNewPath('')
      setExpanded(previous => new Set(previous).add(currentFolder))
      toast.success('Pasta criada fora do RAG')
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao criar pasta')
    }
  }

  const createFile = async () => {
    const target = normalizeTarget(newPath, currentFolder)
    if (!target) return toast.error('Informe o nome do arquivo')
    if (pathExists(target)) return toast.error('Esse caminho ja existe')
    try {
      await api.workspaceWriteFile(target, '')
      setNewPath('')
      setSelectedPath(target)
      setSelectedKind('file')
      setSelectedFile(target)
      setFileMode('text')
      clearImagePreview()
      setContent('')
      setMoveTarget(target)
      setPatchPreview(null)
      toast.success('Arquivo criado no Workspace, fora do RAG')
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao criar arquivo')
    }
  }

  const saveFile = async () => {
    if (!selectedFile) return
    setSaving(true)
    try {
      await api.workspaceWriteFile(selectedFile, content)
      toast.success('Arquivo salvo no Workspace')
      setPatchPreview(null)
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const previewPatch = async () => {
    if (!selectedFile) return
    setPatching(true)
    try {
      setPatchPreview(await api.workspacePatchPreview(selectedFile, content))
      toast.success('Preview patch gerado')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao gerar preview patch')
    } finally {
      setPatching(false)
    }
  }

  const applyApprovedPatch = async () => {
    if (!selectedFile || !patchPreview) return
    setPatching(true)
    try {
      await api.workspacePatchApply(selectedFile, content, patchPreview.expected_checksum)
      toast.success('Patch aprovado aplicado')
      setPatchPreview(null)
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao aplicar patch aprovado')
    } finally {
      setPatching(false)
    }
  }

  const prepareMove = (source: string, folder: string) => {
    const name = source.split('/').pop() || ''
    const target = folder ? `${folder}/${name}` : name
    if (!name || source === target) return
    if (pathExists(target)) return toast.error(`O destino ${target} ja existe`)
    setPendingTransfer({ kind: 'move', source, target })
  }

  const prepareImport = (file: File, folder: string) => {
    const target = folder ? `${folder}/${file.name}` : file.name
    if (pathExists(target)) return toast.error(`O destino ${target} ja existe`)
    setPendingTransfer({ kind: 'import', file, target })
  }

  const handleDrop = (event: DragEvent, folder: string) => {
    event.preventDefault()
    event.stopPropagation()
    setDragOverPath(null)
    const externalFile = event.dataTransfer.files?.[0]
    if (externalFile) {
      prepareImport(externalFile, folder)
      return
    }
    const source = event.dataTransfer.getData('application/x-workspace-path')
    if (source) prepareMove(source, folder)
  }

  const confirmTransfer = async () => {
    if (!pendingTransfer) return
    setSaving(true)
    try {
      if (pendingTransfer.kind === 'move') {
        const info = await api.workspaceMovePath(pendingTransfer.source, pendingTransfer.target)
        if (selectedPath === pendingTransfer.source) {
          setSelectedPath(info.path)
          setMoveTarget(info.path)
          if (selectedKind === 'file') setSelectedFile(info.path)
          if (selectedKind === 'folder') setCurrentFolder(info.path)
        }
        toast.success('Item movido apos confirmacao')
      } else {
        if (pendingTransfer.file.size > MAX_IMPORT_BYTES) throw new Error('Arquivo maior que 1 MB')
        const importedContent = await pendingTransfer.file.text()
        if (importedContent.includes('\0')) throw new Error('Somente arquivos de texto podem ser importados')
        await api.workspaceWriteFile(pendingTransfer.target, importedContent)
        toast.success('Arquivo importado para o Workspace, fora do RAG')
      }
      setPendingTransfer(null)
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha na operacao')
    } finally {
      setSaving(false)
    }
  }

  const moveSelected = () => {
    if (!selectedPath || !moveTarget || moveTarget === selectedPath) return
    if (pathExists(moveTarget)) return toast.error('O destino ja existe')
    setPendingTransfer({ kind: 'move', source: selectedPath, target: moveTarget })
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setSaving(true)
    try {
      await api.workspaceDeletePath(pendingDelete.path, pendingDelete.kind === 'folder')
      toast.success('Item apagado apos confirmacao')
      if (selectedPath === pendingDelete.path) {
        clearImagePreview()
        setSelectedPath('')
        setSelectedKind('')
        setSelectedFile('')
        setFileMode('')
        setContent('')
        setMoveTarget('')
      }
      setPendingDelete(null)
      await refreshTree()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao apagar')
    } finally {
      setSaving(false)
    }
  }

  const addSelectedFileToRag = async () => {
    if (!selectedFile) return
    setRagLoading(true)
    try {
      const result = await api.workspaceRagIngest(selectedFile)
      toast.success(`${result.chunks} chunks adicionados ao RAG pessoal`)
      setRagConfirm(false)
      window.dispatchEvent(new CustomEvent('documents-changed'))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao adicionar ao RAG')
    } finally {
      setRagLoading(false)
    }
  }

  const downloadSelectedImage = () => {
    if (!selectedFile || !imagePreviewUrl) return
    const anchor = document.createElement('a')
    anchor.href = imagePreviewUrl
    anchor.download = selectedFile.split('/').pop() || 'imagem'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  }

  const renderTree = (nodes: WorkspaceTreeNode[], depth = 0): ReactNode => nodes.map(node => {
    const isFolder = node.kind === 'folder'
    const isExpanded = expanded.has(node.path)
    const selected = selectedPath === node.path
    const dropTarget = isFolder && dragOverPath === node.path
    return (
      <div key={node.path}>
        <button
          type="button"
          draggable
          onDragStart={event => {
            event.dataTransfer.effectAllowed = 'move'
            event.dataTransfer.setData('application/x-workspace-path', node.path)
          }}
          onDragOver={event => {
            if (!isFolder) return
            event.preventDefault()
            event.stopPropagation()
            setDragOverPath(node.path)
          }}
          onDragLeave={() => setDragOverPath(null)}
          onDrop={event => isFolder && handleDrop(event, node.path)}
          onClick={() => isFolder ? selectFolder(node) : void openFile(node)}
          className="flex w-full items-center gap-1.5 rounded-lg border px-2 py-2 text-left text-sm transition"
          style={{
            marginLeft: depth * 12,
            width: `calc(100% - ${depth * 12}px)`,
            background: dropTarget ? 'var(--accent-light)' : selected ? 'var(--accent-light)' : 'transparent',
            borderColor: dropTarget || selected ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
          }}
        >
          <GripVertical size={12} style={{ color: 'var(--text-tertiary)' }} />
          {isFolder ? (isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <span className="w-[13px]" />}
          {isFolder
            ? (isExpanded ? <FolderOpen size={16} /> : <Folder size={16} />)
            : isImagePath(node.path) ? <ImageIcon size={16} /> : <FileText size={16} />}
          <span className="min-w-0 flex-1 truncate">{node.name}</span>
          {!isFolder ? <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{node.size}b</span> : null}
        </button>
        {isFolder && isExpanded ? renderTree(node.children, depth + 1) : null}
      </div>
    )
  })

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full flex-col border-l p-3 shadow-xl sm:p-4 md:max-w-5xl"
        style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--accent)' }}>Workspace</p>
            <h2 className="text-lg font-black sm:text-xl" style={{ color: 'var(--text-primary)' }}>Gerenciador completo de arquivos</h2>
            <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Workspace e RAG sao separados. Nada entra no RAG sem sua confirmacao.
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10"><X size={18} /></button>
        </div>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 md:grid-cols-[340px_1fr]">
          <section className={`${selectedPath ? 'hidden md:flex' : 'flex'} min-h-0 flex-col rounded-2xl border p-3`} style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
            <div
              onDragOver={event => {
                event.preventDefault()
                setDragOverPath('')
              }}
              onDragLeave={() => setDragOverPath(null)}
              onDrop={event => handleDrop(event, '')}
              className="rounded-xl border border-dashed p-3"
              style={{ borderColor: dragOverPath === '' ? 'var(--accent)' : 'var(--border)', background: dragOverPath === '' ? 'var(--accent-light)' : 'var(--bg-primary)' }}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>/workspace/{currentFolder}</p>
                  <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>Solte aqui para mover/importar na raiz</p>
                </div>
                <label className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold" style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>
                  <UploadCloud size={13} /> Importar
                  <input
                    type="file"
                    className="hidden"
                    onChange={event => {
                      const file = event.target.files?.[0]
                      if (file) prepareImport(file, currentFolder)
                      event.target.value = ''
                    }}
                  />
                </label>
              </div>
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
              <button onClick={createFile} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>Criar arquivo</button>
              <button onClick={createFolder} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                <span className="inline-flex items-center gap-1"><FolderPlus size={13} /> Criar pasta</span>
              </button>
            </div>

            <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-xl border p-1" style={{ borderColor: 'var(--border)', background: 'var(--bg-primary)' }}>
              {loading ? <p className="p-3 text-sm" style={{ color: 'var(--text-secondary)' }}>Carregando arvore...</p> : tree.length ? renderTree(tree) : <p className="p-3 text-sm" style={{ color: 'var(--text-secondary)' }}>Workspace vazio.</p>}
            </div>
          </section>

          <section className={`${selectedPath ? 'flex' : 'hidden md:flex'} min-h-0 flex-col rounded-2xl border p-3`} style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
            {selectedPath ? (
              <>
                <button
                  type="button"
                  onClick={() => { setSelectedPath(''); setSelectedFile(''); setSelectedKind('') }}
                  className="mb-3 inline-flex w-fit items-center gap-1 rounded-xl px-2 py-1.5 text-sm font-bold md:hidden"
                  style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                >
                  <ChevronLeft size={16} /> Arquivos
                </button>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold" style={{ color: 'var(--text-tertiary)' }}>{selectedKind === 'folder' ? 'Pasta selecionada' : 'Arquivo aberto'}</p>
                    <h3 className="truncate font-bold" style={{ color: 'var(--text-primary)' }}>{selectedPath}</h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedFile && fileMode === 'text' ? (
                      <>
                        <button onClick={previewPatch} disabled={patching} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-60" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                          <Pencil size={14} /> {patching ? 'Gerando...' : 'Preview patch'}
                        </button>
                        <button onClick={saveFile} disabled={saving} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-60" style={{ background: 'var(--accent)', color: '#fff' }}>
                          <Save size={14} /> {saving ? 'Salvando...' : 'Salvar'}
                        </button>
                        <button
                          onClick={() => setRagConfirm(true)}
                          className="inline-flex cursor-pointer items-center gap-1 rounded-xl border px-3 py-2 text-xs font-bold transition-all hover:-translate-y-0.5 hover:brightness-150 hover:shadow-md active:translate-y-0"
                          style={{ background: 'var(--accent-light)', borderColor: 'var(--accent)', color: 'var(--accent)' }}
                        >
                          <Database size={14} /> Selecionar para RAG
                        </button>
                      </>
                    ) : null}
                    {selectedFile && fileMode === 'image' ? (
                      <>
                        <button
                          onClick={downloadSelectedImage}
                          className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold"
                          style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                        >
                          <Download size={14} /> Baixar
                        </button>
                        <button
                          onClick={() => setImageExpanded(true)}
                          disabled={!imagePreviewUrl || imageLoadError}
                          className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50"
                          style={{ background: 'var(--accent)', color: '#fff' }}
                        >
                          <Maximize2 size={14} /> Ampliar
                        </button>
                      </>
                    ) : null}
                    <button onClick={() => setPendingDelete({ path: selectedPath, kind: selectedKind as 'file' | 'folder' })} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold" style={{ background: '#fee2e2', color: '#dc2626' }}>
                      <Trash2 size={14} /> Apagar
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex gap-2">
                  <input value={moveTarget} onChange={(event: ChangeEvent<HTMLInputElement>) => setMoveTarget(event.target.value)} className="min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm outline-none" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }} />
                  <button onClick={moveSelected} className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}>
                    <MoveRight size={14} /> Mover/renomear
                  </button>
                </div>

                {selectedFile && fileMode === 'image' ? (
                  <div
                    className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border"
                    style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)' }}
                  >
                    <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-4 md:p-8">
                      {imageLoadError ? (
                        <div className="max-w-sm text-center">
                          <ImageIcon className="mx-auto mb-3 opacity-50" size={48} />
                          <h4 className="font-bold">O navegador nao renderiza este formato</h4>
                          <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
                            O arquivo continua intacto e disponivel para download.
                          </p>
                          <button
                            onClick={downloadSelectedImage}
                            className="mt-4 inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold"
                            style={{ background: 'var(--accent)', color: '#fff' }}
                          >
                            <Download size={16} /> Baixar original
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setImageExpanded(true)}
                          className="group relative flex h-full w-full items-center justify-center"
                          title="Clique para ampliar"
                        >
                          <img
                            src={imagePreviewUrl}
                            alt={selectedFile.split('/').pop() || 'Imagem do Workspace'}
                            onError={() => setImageLoadError(true)}
                            className="max-h-full max-w-full rounded-xl object-contain shadow-2xl"
                          />
                          <span className="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded-full bg-black/70 px-3 py-1.5 text-xs font-bold text-white opacity-0 transition group-hover:opacity-100">
                            <Maximize2 size={13} /> Ampliar
                          </span>
                        </button>
                      )}
                    </div>
                    <div className="flex items-center justify-between gap-2 border-t px-4 py-2 text-xs" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                      <span>Preview visual - original preservado</span>
                      <span className="font-mono uppercase">{selectedFile.split('.').pop()}</span>
                    </div>
                  </div>
                ) : selectedFile ? (
                  <textarea
                    value={content}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                      setContent(event.target.value)
                      setPatchPreview(null)
                      setRagConfirm(false)
                    }}
                    className="mt-3 min-h-0 flex-1 resize-none rounded-2xl border p-4 font-mono text-sm outline-none"
                    style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    spellCheck={false}
                  />
                ) : (
                  <div className="mt-3 grid flex-1 place-items-center rounded-2xl border border-dashed" style={{ borderColor: 'var(--border)' }}>
                    <div className="text-center"><FolderOpen className="mx-auto mb-2 opacity-50" size={42} /><p className="text-sm">Arraste arquivos para esta pasta ou crie itens nela.</p></div>
                  </div>
                )}

                {patchPreview ? (
                  <>
                    <p className="sr-only">Aplicar patch aprovado</p>
                    <DiffViewer preview={patchPreview} applying={patching} onApply={applyApprovedPatch} onCancel={() => setPatchPreview(null)} />
                  </>
                ) : null}
              </>
            ) : (
              <div className="grid flex-1 place-items-center text-center">
                <div><FileText className="mx-auto mb-3 opacity-50" size={42} /><h3 className="font-bold">Selecione um arquivo ou pasta</h3><p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>A arvore mostra visualmente toda a estrutura interna.</p></div>
              </div>
            )}
          </section>
        </div>

        {pendingTransfer ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border p-3" style={{ borderColor: 'var(--accent)', background: 'var(--accent-light)' }}>
            <MoveRight size={18} style={{ color: 'var(--accent)' }} />
            <p className="min-w-0 flex-1 text-sm"><strong>Confirmar {pendingTransfer.kind === 'move' ? 'movimentacao' : 'importacao'}:</strong> <span className="font-mono text-xs">{pendingTransfer.target}</span></p>
            <button onClick={() => setPendingTransfer(null)} className="rounded-xl px-3 py-2 text-xs font-bold">Cancelar</button>
            <button onClick={confirmTransfer} disabled={saving} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>Confirmar</button>
          </div>
        ) : null}

        {pendingDelete ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border p-3" style={{ borderColor: 'var(--danger)', background: 'rgba(239,68,68,.1)' }}>
            <Trash2 size={18} style={{ color: 'var(--danger)' }} />
            <p className="min-w-0 flex-1 text-sm"><strong>Apagar {pendingDelete.kind}?</strong> {pendingDelete.kind === 'folder' ? 'Todo o conteudo interno tambem sera removido.' : ''} <span className="font-mono text-xs">{pendingDelete.path}</span></p>
            <button onClick={() => setPendingDelete(null)} className="rounded-xl px-3 py-2 text-xs font-bold">Cancelar</button>
            <button onClick={confirmDelete} disabled={saving} className="rounded-xl px-3 py-2 text-xs font-bold" style={{ background: 'var(--danger)', color: '#fff' }}>Confirmar exclusao</button>
          </div>
        ) : null}

        {ragConfirm && selectedFile ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border p-3" style={{ borderColor: 'var(--accent)', background: 'var(--accent-light)' }}>
            {ragLoading ? <RefreshCw className="animate-spin" size={18} style={{ color: 'var(--accent)' }} /> : <Database size={18} style={{ color: 'var(--accent)' }} />}
            <p className="min-w-0 flex-1 text-sm">
              <strong>{ragLoading ? 'Adicionando ao RAG...' : 'Adicionar somente este arquivo ao RAG?'}</strong>{' '}
              <span className="font-mono text-xs">{selectedFile}</span>
              {ragLoading ? <span className="mt-1 block text-xs">Extraindo texto, criando chunks e atualizando a lista de documentos.</span> : null}
            </p>
            <button onClick={() => setRagConfirm(false)} disabled={ragLoading} className="rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-40">Cancelar</button>
            <button onClick={addSelectedFileToRag} disabled={ragLoading} className="rounded-xl px-3 py-2 text-xs font-bold disabled:cursor-wait disabled:opacity-70" style={{ background: 'var(--accent)', color: '#fff' }}>{ragLoading ? 'Processando...' : 'Confirmar RAG'}</button>
          </div>
        ) : null}
      </aside>

      {imageExpanded && imagePreviewUrl && !imageLoadError ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 p-3 md:p-8"
          role="dialog"
          aria-modal="true"
          aria-label={`Visualizacao ampliada de ${selectedFile}`}
          onClick={() => setImageExpanded(false)}
        >
          <button
            type="button"
            onClick={() => setImageExpanded(false)}
            className="absolute right-4 top-4 rounded-full bg-black/70 p-3 text-white transition hover:bg-black"
            aria-label="Fechar imagem ampliada"
          >
            <X size={22} />
          </button>
          <img
            src={imagePreviewUrl}
            alt={selectedFile.split('/').pop() || 'Imagem ampliada do Workspace'}
            className="max-h-full max-w-full rounded-xl object-contain shadow-2xl"
            onClick={event => event.stopPropagation()}
          />
          <button
            type="button"
            onClick={event => {
              event.stopPropagation()
              downloadSelectedImage()
            }}
            className="absolute bottom-4 right-4 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-bold text-black shadow-xl"
          >
            <Download size={16} /> Baixar original
          </button>
        </div>
      ) : null}
    </>
  )
}

function normalizeTarget(value: string, currentFolder: string): string {
  const trimmed = value.trim().replace(/^\/+/, '')
  if (!trimmed) return ''
  if (!currentFolder || trimmed.includes('/')) return trimmed
  return `${currentFolder}/${trimmed}`
}
