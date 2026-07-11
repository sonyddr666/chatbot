import { useCallback, useEffect, useState } from 'react'
import { Check, Clock3, RefreshCw, ShieldCheck, Trash2, UserRoundCheck, Users, X, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { api, parseApiTimestamp, type AdminUserInfo } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

type UserFilter = 'pending' | 'approved' | 'rejected' | 'all'

const FILTERS: Array<{ id: UserFilter; label: string }> = [
  { id: 'pending', label: 'Pendentes' },
  { id: 'approved', label: 'Aprovados' },
  { id: 'rejected', label: 'Rejeitados' },
  { id: 'all', label: 'Todos' },
]

const STATUS_LABELS = {
  pending: 'Aguardando aprovacao',
  approved: 'Aprovado',
  rejected: 'Rejeitado',
}

export function AdminUsersPanel({ open, onClose }: Props) {
  const [filter, setFilter] = useState<UserFilter>('pending')
  const [users, setUsers] = useState<AdminUserInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [actingId, setActingId] = useState<number | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      setUsers(await api.adminListUsers(filter))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao carregar usuarios')
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    if (open) void loadUsers()
  }, [loadUsers, open])

  const approve = async (user: AdminUserInfo) => {
    setActingId(user.id)
    try {
      await api.adminApproveUser(user.id)
      toast.success(`Conta de ${user.username} aprovada`)
      await loadUsers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao aprovar conta')
    } finally {
      setActingId(null)
    }
  }

  const reject = async (user: AdminUserInfo) => {
    setActingId(user.id)
    try {
      await api.adminRejectUser(user.id)
      toast.success(`Solicitacao de ${user.username} rejeitada`)
      await loadUsers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao rejeitar solicitacao')
    } finally {
      setActingId(null)
    }
  }

  const remove = async (user: AdminUserInfo) => {
    const confirmed = window.confirm(
      `Excluir a solicitacao de ${user.username}? O email e o usuario serao liberados para um novo cadastro.`,
    )
    if (!confirmed) return
    setActingId(user.id)
    try {
      await api.adminDeleteRegistration(user.id)
      toast.success('Solicitacao excluida e dados liberados')
      await loadUsers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Falha ao excluir solicitacao')
    } finally {
      setActingId(null)
    }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60" onClick={onClose} />
      <section
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-2xl flex-col shadow-2xl"
        style={{ background: 'var(--bg-primary)', borderLeft: '1px solid var(--border)' }}
      >
        <header className="flex items-center gap-3 border-b p-4" style={{ borderColor: 'var(--border)' }}>
          <div className="grid h-10 w-10 place-items-center rounded-xl" style={{ background: 'rgba(22,163,74,.14)', color: '#16a34a' }}>
            <ShieldCheck size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-black uppercase tracking-[0.18em]" style={{ color: '#16a34a' }}>Administracao</p>
            <h2 className="text-lg font-black" style={{ color: 'var(--text-primary)' }}>Usuarios e aprovacoes</h2>
          </div>
          <button onClick={() => void loadUsers()} disabled={loading} className="rounded-lg p-2 disabled:opacity-50" title="Atualizar lista">
            <RefreshCw size={17} className={loading ? 'animate-spin' : ''} style={{ color: 'var(--text-secondary)' }} />
          </button>
          <button onClick={onClose} className="rounded-lg p-2" title="Fechar">
            <X size={19} style={{ color: 'var(--text-secondary)' }} />
          </button>
        </header>

        <nav className="flex gap-2 overflow-x-auto border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
          {FILTERS.map(item => (
            <button
              key={item.id}
              onClick={() => setFilter(item.id)}
              className="shrink-0 rounded-full px-3 py-1.5 text-xs font-bold"
              style={{
                background: filter === item.id ? 'var(--accent)' : 'var(--bg-secondary)',
                color: filter === item.id ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {!loading && users.length === 0 && (
            <div className="grid min-h-48 place-items-center rounded-2xl border border-dashed p-8 text-center" style={{ borderColor: 'var(--border)' }}>
              <div>
                <Users size={30} className="mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
                <p className="font-bold" style={{ color: 'var(--text-primary)' }}>Nenhum usuario nesta lista</p>
                <p className="mt-1 text-sm" style={{ color: 'var(--text-tertiary)' }}>Novas solicitacoes aparecerao aqui automaticamente.</p>
              </div>
            </div>
          )}

          {users.map(user => {
            const pending = user.registration_status === 'pending'
            const rejected = user.registration_status === 'rejected'
            const busy = actingId === user.id
            const statusColor = pending ? '#d97706' : rejected ? '#dc2626' : '#16a34a'
            return (
              <article key={user.id} className="rounded-2xl border p-4" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl" style={{ background: `color-mix(in srgb, ${statusColor} 14%, transparent)`, color: statusColor }}>
                    {pending ? <Clock3 size={19} /> : rejected ? <XCircle size={19} /> : <UserRoundCheck size={19} />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong style={{ color: 'var(--text-primary)' }}>{user.display_name || user.username}</strong>
                      {user.is_admin && <span className="rounded-full px-2 py-0.5 text-[10px] font-black" style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>ADMIN</span>}
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: `color-mix(in srgb, ${statusColor} 14%, transparent)`, color: statusColor }}>
                        {STATUS_LABELS[user.registration_status]}
                      </span>
                    </div>
                    <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>@{user.username} · {user.email}</p>
                    <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      Solicitado em {parseApiTimestamp(user.created_at).toLocaleString('pt-BR')}
                    </p>
                  </div>
                </div>

                {!user.is_admin && (pending || rejected) && (
                  <div className="mt-4 flex flex-wrap justify-end gap-2 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
                    {pending && (
                      <>
                        <button disabled={busy} onClick={() => void reject(user)} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold disabled:opacity-50" style={{ background: 'rgba(220,38,38,.1)', color: '#dc2626' }}>
                          <XCircle size={14} /> Rejeitar
                        </button>
                        <button disabled={busy} onClick={() => void approve(user)} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold disabled:opacity-50" style={{ background: '#16a34a', color: '#fff' }}>
                          <Check size={14} /> Aprovar
                        </button>
                      </>
                    )}
                    <button disabled={busy} onClick={() => void remove(user)} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold disabled:opacity-50" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                      <Trash2 size={14} /> Excluir e liberar dados
                    </button>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </section>
    </>
  )
}
