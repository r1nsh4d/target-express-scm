import { useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus, Users as UsersIcon } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Table,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { ROLE_LABELS, useAuth } from '@/lib/auth'
import type { UserRole } from '@/lib/auth'
import { useCreate, useList } from '@/lib/resources'

interface AppUser {
  id: string
  full_name: string
  phone: string
  email: string | null
  role: UserRole
  is_active: boolean
  can_view_earnings: boolean
}

const ROLES: UserRole[] = [
  'SUPER_ADMIN',
  'OPS_ADMIN',
  'WAREHOUSE_ADMIN',
  'ACCOUNTS',
  'STAKEHOLDER',
  'DRIVER',
]

export default function UsersPage() {
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState<AppUser | null>(null)

  const users = useList<AppUser>('/auth/users')

  const patch = useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Partial<AppUser>) =>
      (await api.patch(`/auth/users/${id}`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['/auth/users'] }),
    onError: (e) => setError(apiErrorMessage(e)),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        description="One login serves every role. Earnings visibility is set per person, not derived from the vehicle — a driver moving between an owned and a rented lorry should not have it flip with the roster."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New user
          </Button>
        }
      />

      <ErrorNote>{error}</ErrorNote>

      <Card className="overflow-hidden">
        {users.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={users.data ?? []}
            rowKey={(u) => u.id}
            empty={
              <EmptyState
                icon={<UsersIcon className="size-7" />}
                title="No users"
                description="Add the people who need a login."
              />
            }
            columns={[
              {
                key: 'name',
                header: 'Name',
                render: (u) => (
                  <span className="font-medium">
                    {u.full_name}
                    {u.id === me?.id ? (
                      <span className="ml-2 text-[11px]" style={{ color: 'var(--text-faint)' }}>
                        you
                      </span>
                    ) : null}
                  </span>
                ),
              },
              { key: 'phone', header: 'Login', render: (u) => <span className="tnum">{u.phone}</span> },
              {
                key: 'role',
                header: 'Role',
                render: (u) => <Badge tone="info">{ROLE_LABELS[u.role]}</Badge>,
              },
              {
                key: 'earn',
                header: 'Sees earnings',
                render: (u) =>
                  u.role !== 'DRIVER' ? (
                    <span style={{ color: 'var(--text-faint)' }}>—</span>
                  ) : (
                    <Checkbox
                      label=""
                      checked={u.can_view_earnings}
                      onChange={(e) => {
                        setError(null)
                        patch.mutate({ id: u.id, can_view_earnings: e.target.checked })
                      }}
                    />
                  ),
              },
              {
                key: 'active',
                header: 'Status',
                render: (u) =>
                  u.is_active ? (
                    <Badge tone="success">Active</Badge>
                  ) : (
                    <Badge tone="warning">Disabled</Badge>
                  ),
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (u) =>
                  u.id === me?.id ? null : (
                    <div className="flex justify-end gap-2">
                      {/* Drivers lose phones and forget passwords, and the phone
                          number IS the username — there is no email to send a
                          reset link to. Without this the only recovery is a
                          shell on the server. */}
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<KeyRound className="size-3.5" />}
                        onClick={() => {
                          setError(null)
                          setResetting(u)
                        }}
                      >
                        Password
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setError(null)
                          patch.mutate({ id: u.id, is_active: !u.is_active })
                        }}
                      >
                        {u.is_active ? 'Disable' : 'Enable'}
                      </Button>
                    </div>
                  ),
              },
            ]}
          />
        )}
      </Card>

      <UserForm open={open} onClose={() => setOpen(false)} />
      <ResetPasswordModal user={resetting} onClose={() => setResetting(null)} />
    </div>
  )
}

function UserForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const blank = {
    full_name: '',
    phone: '',
    email: '',
    password: '',
    role: 'WAREHOUSE_ADMIN' as UserRole,
    can_view_earnings: false,
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/auth/users', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New user">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            { ...form, email: form.email || null },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Full name">
          <Input
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Mobile number" hint="This is the login">
            <Input
              className="tnum"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              required
            />
          </Field>
          <Field label="Email" hint="Optional">
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
        </div>

        <Field label="Role">
          <Select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Password" hint="At least 6 characters">
          <Input
            type="text"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            minLength={6}
            required
          />
        </Field>

        {form.role === 'DRIVER' ? (
          <Checkbox
            label="This driver can see his own earnings"
            checked={form.can_view_earnings}
            onChange={(e) => setForm({ ...form, can_view_earnings: e.target.checked })}
          />
        ) : null}

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create user
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */

/** Set somebody else's password.
 *
 *  An admin is never shown the existing one, because nobody can be — they are
 *  bcrypt hashes and that is the point. This replaces it.
 *
 *  Deliberately its own dialog rather than another field on the edit form. A
 *  password change hands someone an account; it should be impossible to do by
 *  accident while ticking "can view earnings".
 */
function ResetPasswordModal({
  user,
  onClose,
}: {
  user: AppUser | null
  onClose: () => void
}) {
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!user) return
    setError(null)

    if (next !== confirm) {
      setError('The two entries do not match')
      return
    }

    setBusy(true)
    try {
      await api.post(`/auth/users/${user.id}/reset-password`, { new_password: next })
      setDone(true)
      setNext('')
      setConfirm('')
      setTimeout(() => {
        setDone(false)
        onClose()
      }, 1600)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not set the password'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={!!user}
      onClose={onClose}
      title={user ? `New password for ${user.full_name}` : 'Set a password'}
      description={
        user
          ? `They sign in with ${user.phone}. Tell them the new password yourself — it is not sent anywhere.`
          : undefined
      }
    >
      <form className="space-y-4" onSubmit={submit}>
        <Field label="New password" hint="At least 6 characters">
          <Input
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            autoFocus
          />
        </Field>
        <Field label="Repeat it">
          <Input
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </Field>

        <p className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
          The old password cannot be shown to anyone — passwords are stored as one-way
          hashes. This replaces it.
        </p>

        <ErrorNote>{error}</ErrorNote>
        {done ? (
          <p className="text-[13px]" style={{ color: 'var(--success)' }}>
            Password set. Pass it on to them directly.
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Set password
          </Button>
        </div>
      </form>
    </Modal>
  )
}
