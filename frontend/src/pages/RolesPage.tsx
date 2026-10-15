import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Spinner,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { useItem, useList } from '@/lib/resources'

/* Roles somebody can make, instead of six compiled into the application.
 *
 * The six built-ins are here as rows now, holding exactly the permissions
 * they always had. What they gain is company: a branch manager in Kannur who
 * sees freights and invoices but not settlements used to need a developer.
 *
 * Two lists on a role, and the screen says plainly that they are different
 * kinds of thing. PERMISSIONS are enforced by the server. SCREENS decide what
 * appears in the rail and are tidiness, not security — implying otherwise
 * with an identical-looking tick box would be a lie the UI told.
 */

interface Role {
  id: string
  name: string
  description: string | null
  is_system: boolean
  is_active: boolean
  base_role: string | null
  capabilities: string[]
  screens: string[]
  user_count: number
}

interface Catalogue {
  capabilities: { key: string; label: string }[]
  screens: { key: string; label: string; needs: string }[]
}

export default function RolesPage() {
  const [editing, setEditing] = useState<Role | null>(null)
  const [creating, setCreating] = useState(false)

  const roles = useList<Role>('/roles')
  const catalogue = useItem<Catalogue>('/capabilities')

  return (
    <div className="space-y-6">
      <PageHeader
        description="A role is a set of permissions, and a user is created against one. The six built-in roles hold exactly what they always did and cannot be edited — make a new one instead, which is safer than changing the role you would need to undo it."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
            New role
          </Button>
        }
      />

      {roles.isLoading || !catalogue.data ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {(roles.data ?? []).map((role) => (
            <Card key={role.id} className="hoverable p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-[15px] font-semibold">{role.name}</h3>
                    {role.is_system ? (
                      <Badge tone="neutral">
                        <Lock className="mr-1 inline size-3" />
                        built in
                      </Badge>
                    ) : null}
                  </div>
                  {role.description ? (
                    <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                      {role.description}
                    </p>
                  ) : null}
                </div>
                <span className="tnum shrink-0 text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  {role.user_count} {role.user_count === 1 ? 'user' : 'users'}
                </span>
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {role.capabilities.map((c) => (
                  <Badge key={c} tone="accent">
                    {catalogue.data!.capabilities.find((x) => x.key === c)?.label ?? c}
                  </Badge>
                ))}
              </div>

              <p className="mt-2 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
                {role.screens.length} screen{role.screens.length === 1 ? '' : 's'} in the menu
              </p>

              <div className="mt-3 flex justify-end">
                <Button size="sm" variant="secondary" onClick={() => setEditing(role)}>
                  {role.is_system ? 'View' : 'Edit'}
                </Button>
              </div>
            </Card>
          ))}

          {!roles.data?.length ? (
            <Card>
              <EmptyState
                icon={<ShieldCheck className="size-7" />}
                title="No roles yet"
                description="The built-in ones appear here the first time this screen loads."
              />
            </Card>
          ) : null}
        </div>
      )}

      {catalogue.data ? (
        <RoleForm
          role={editing}
          open={creating || !!editing}
          catalogue={catalogue.data}
          onClose={() => {
            setCreating(false)
            setEditing(null)
          }}
        />
      ) : null}
    </div>
  )
}

function RoleForm({
  role,
  open,
  catalogue,
  onClose,
}: {
  role: Role | null
  open: boolean
  catalogue: Catalogue
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [caps, setCaps] = useState<string[]>(role?.capabilities ?? [])
  const [screens, setScreens] = useState<string[]>(role?.screens ?? [])
  const [error, setError] = useState<string | null>(null)

  // Reset when a different role is opened.
  const [seeded, setSeeded] = useState<string | null>(null)
  const key = role?.id ?? 'new'
  if (seeded !== key) {
    setSeeded(key)
    setName(role?.name ?? '')
    setDescription(role?.description ?? '')
    setCaps(role?.capabilities ?? [])
    setScreens(role?.screens ?? [])
    setError(null)
  }

  const locked = !!role?.is_system

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, description: description || null, capabilities: caps, screens }
      return role
        ? (await api.patch(`/roles/${role.id}`, body)).data
        : (await api.post('/roles', body)).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/roles'] })
      onClose()
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const remove = useMutation({
    mutationFn: async () => (await api.delete(`/roles/${role!.id}`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/roles'] })
      onClose()
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  /* A screen whose permission is missing is not offered. An item in the rail
     with a 403 behind it is worse than no item, so the list shrinks as the
     permissions do rather than letting somebody tick a dead one. */
  const reachable = catalogue.screens.filter((s) => caps.includes(s.needs))

  function toggle(list: string[], value: string, set: (v: string[]) => void) {
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={role ? role.name : 'New role'}
      description={
        locked
          ? 'Built in. Its permissions are part of the application, so they cannot be changed — but the name and the menu can be.'
          : 'Permissions are enforced by the server. The menu list only decides what appears in the sidebar.'
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Branch Manager · Kannur" />
          </Field>
          <Field label="What is it for?">
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Sees the work and the invoices, not the settlements"
            />
          </Field>
        </div>

        <div>
          <p className="text-[13px] font-medium">Permissions</p>
          <p className="mt-0.5 mb-2 text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Enforced by the server. Anything not ticked is refused however it is reached.
          </p>
          <div className="space-y-1.5">
            {catalogue.capabilities.map((c) => (
              <label
                key={c.key}
                className="flex items-center gap-2.5 rounded-[var(--radius-control)] px-3 py-2 text-[13px]"
                style={{
                  background: caps.includes(c.key) ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                  opacity: locked ? 0.7 : 1,
                }}
              >
                <input
                  type="checkbox"
                  className="size-4 accent-[var(--accent)]"
                  disabled={locked}
                  checked={caps.includes(c.key)}
                  onChange={() => {
                    toggle(caps, c.key, setCaps)
                    // Drop screens that just lost their permission, rather
                    // than silently keeping a tick that no longer applies.
                    setScreens((s) =>
                      s.filter((key) => {
                        const screen = catalogue.screens.find((x) => x.key === key)
                        if (!screen) return false
                        const next = caps.includes(c.key)
                          ? caps.filter((v) => v !== c.key)
                          : [...caps, c.key]
                        return next.includes(screen.needs)
                      }),
                    )
                  }}
                />
                <span>{c.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[13px] font-medium">Menu</p>
          <p className="mt-0.5 mb-2 text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Which screens appear in the sidebar. Tidiness rather than security — the permissions
            above are what actually stop anything.
          </p>
          {reachable.length ? (
            <div className="flex flex-wrap gap-1.5">
              {reachable.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => toggle(screens, s.key, setScreens)}
                  className="rounded-full px-2.5 py-1 text-[12px]"
                  style={
                    screens.includes(s.key)
                      ? { background: 'var(--accent)', color: '#04121a' }
                      : { background: 'var(--bg-elevated)', color: 'var(--text-muted)' }
                  }
                >
                  {s.label}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[12.5px]" style={{ color: 'var(--text-faint)' }}>
              Tick a permission first — a screen without one would be a menu item that refuses to
              open.
            </p>
          )}
        </div>

        <ErrorNote>{error}</ErrorNote>

        <div className="flex flex-wrap justify-end gap-2">
          {role && !role.is_system ? (
            <Button
              variant="ghost"
              icon={<Trash2 className="size-4" />}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Delete
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={name.trim().length < 2 || !caps.length}
            loading={save.isPending}
            onClick={() => {
              setError(null)
              save.mutate()
            }}
          >
            {role ? 'Save' : 'Create role'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
