/* Edit and retire, for any master list.
 *
 * Every master screen was create-only. A driver's name typed wrong stayed wrong,
 * a customer who moved could not be corrected, a lorry sold last month still
 * appeared in the assign list. People work around that by keeping the real list
 * in a spreadsheet, and then the application is decoration.
 *
 * One component rather than eight, driven by a field spec, because the edit form
 * for a driver and the edit form for a warehouse differ only in their fields.
 *
 * RETIRE, NOT DELETE. Everything here is referenced by a freight, a point or a
 * settlement. The row stops appearing in pickers and keeps answering for the
 * history it is part of. The confirmation says that in words, because "delete"
 * and "this will be hidden from new trips" are different promises.
 */

import { useQueryClient } from '@tanstack/react-query'
import { Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'

import {
  Button,
  Checkbox,
  ErrorNote,
  Field,
  Input,
  Modal,
  Select,
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

export type FieldSpec =
  | {
      name: string
      label: string
      kind?: 'text' | 'number' | 'tel' | 'email' | 'date'
      hint?: string
      required?: boolean
    }
  | { name: string; label: string; kind: 'checkbox'; hint?: string }
  | { name: string; label: string; kind: 'textarea'; hint?: string }
  | {
      name: string
      label: string
      kind: 'select'
      hint?: string
      options: { value: string; label: string }[]
    }

interface Row {
  id: string
  is_active?: boolean
  [key: string]: unknown
}

export function RowActions({
  path,
  row,
  label,
  fields,
  queryKey,
  canRetire = true,
}: {
  /** Collection path, e.g. "/drivers". Edits PATCH `${path}/${id}`. */
  path: string
  row: Row
  /** What this record is called, for the confirmation wording. */
  label: string
  /** Empty means no edit button — used for rate cards, which are immutable. */
  fields: FieldSpec[]
  /** The list to refresh. Defaults to `path`. */
  queryKey?: string
  canRetire?: boolean
}) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: [queryKey ?? path] })

  const retired = row.is_active === false

  async function setRetired(next: boolean) {
    setBusy(true)
    setError(null)
    try {
      if (next) await api.delete(`${path}/${row.id}`)
      else await api.post(`${path}/${row.id}/restore`)
      refresh()
      setConfirming(false)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not change this record'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex justify-end gap-1">
      {fields.length ? (
        <button
          onClick={() => setEditing(true)}
          className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-muted)' }}
          title={`Edit this ${label.toLowerCase()}`}
          aria-label={`Edit ${label}`}
        >
          <Pencil className="size-3.5" />
        </button>
      ) : null}

      {canRetire ? (
        retired ? (
          <button
            onClick={() => setRetired(false)}
            disabled={busy}
            className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
            style={{ color: 'var(--accent)' }}
            title="Bring it back"
            aria-label={`Restore ${label}`}
          >
            <RotateCcw className="size-3.5" />
          </button>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
            style={{ color: 'var(--text-faint)' }}
            title="Retire — hidden from new trips, history kept"
            aria-label={`Retire ${label}`}
          >
            <Trash2 className="size-3.5" />
          </button>
        )
      ) : null}

      <EditModal
        open={editing}
        onClose={() => setEditing(false)}
        path={path}
        row={row}
        label={label}
        fields={fields}
        onSaved={refresh}
      />

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title={`Retire this ${label.toLowerCase()}?`}
        description="It will stop appearing when you build new trips. Everything it is already attached to — freights, invoices, settlements — is untouched and still readable."
      >
        <div className="space-y-4">
          <p className="text-[13.5px]">
            <span className="font-medium">
              {String(row.name ?? row.registration_no ?? row.contact_name ?? '')}
            </span>
          </p>
          <p className="text-[12.5px]" style={{ color: 'var(--text-faint)' }}>
            Nothing is deleted. You can bring it back from the same list by
            ticking “show retired”.
          </p>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button type="button" loading={busy} onClick={() => setRetired(true)}>
              Retire it
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function EditModal({
  open,
  onClose,
  path,
  row,
  label,
  fields,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  path: string
  row: Row
  label: string
  fields: FieldSpec[]
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  if (open && loadedFor !== row.id) {
    setLoadedFor(row.id)
    const initial: Record<string, unknown> = {}
    for (const f of fields) {
      const value = row[f.name]
      initial[f.name] =
        f.kind === 'checkbox' ? !!value : value === null || value === undefined ? '' : String(value)
    }
    setDraft(initial)
    setError(null)
  }
  if (!open && loadedFor !== null) setLoadedFor(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)

    /* Only what actually changed goes up.
       The API treats an omitted field as "leave it alone", so sending the whole
       form would make every edit rewrite every column — and a field the form
       renders as an empty string would blank a value the user never touched. */
    const body: Record<string, unknown> = {}
    for (const f of fields) {
      const before = row[f.name]
      const now = draft[f.name]

      if (f.kind === 'checkbox') {
        if (!!before !== !!now) body[f.name] = !!now
        continue
      }
      const beforeText = before === null || before === undefined ? '' : String(before)
      if (String(now ?? '') === beforeText) continue

      if (f.kind === 'number') {
        body[f.name] = now === '' ? null : Number(now)
      } else {
        body[f.name] = now === '' ? null : now
      }
    }

    if (Object.keys(body).length === 0) {
      onClose()
      setBusy(false)
      return
    }

    try {
      await api.patch(`${path}/${row.id}`, body)
      onSaved()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save this change'))
    } finally {
      setBusy(false)
    }
  }

  const set = (name: string, value: unknown) => setDraft({ ...draft, [name]: value })

  return (
    <Modal open={open} onClose={onClose} wide title={`Edit ${label.toLowerCase()}`}>
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2">
          {fields.map((f) => {
            const value = draft[f.name]

            if (f.kind === 'checkbox') {
              return (
                <div key={f.name} className="flex items-end pb-2">
                  <Checkbox
                    label={f.label}
                    checked={!!value}
                    onChange={(e) => set(f.name, e.target.checked)}
                  />
                </div>
              )
            }

            if (f.kind === 'select') {
              return (
                <Field key={f.name} label={f.label} hint={f.hint}>
                  <Select
                    value={String(value ?? '')}
                    onChange={(e) => set(f.name, e.target.value)}
                  >
                    <option value="">Not set</option>
                    {f.options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )
            }

            if (f.kind === 'textarea') {
              return (
                <div key={f.name} className="sm:col-span-2">
                  <Field label={f.label} hint={f.hint}>
                    <Textarea
                      rows={2}
                      value={String(value ?? '')}
                      onChange={(e) => set(f.name, e.target.value)}
                    />
                  </Field>
                </div>
              )
            }

            return (
              <Field key={f.name} label={f.label} hint={f.hint}>
                <Input
                  type={f.kind ?? 'text'}
                  value={String(value ?? '')}
                  onChange={(e) => set(f.name, e.target.value)}
                  required={f.required}
                />
              </Field>
            )
          })}
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Save changes
          </Button>
        </div>
      </form>
    </Modal>
  )
}
