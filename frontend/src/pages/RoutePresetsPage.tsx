/* Saved routes — the office's own numbered rounds, written down.
 *
 * Target Express does not plan a fresh route every morning. "No. 11" is a known
 * run with a known set of customers in a known order, and until now that lived
 * in one person's head and an Excel sheet.
 *
 * This screen is where a round is built and corrected. Using one is a tap on
 * the New trip form — the point of a preset is that you never have to come here
 * to use it, only to change it.
 */

import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowDown,
  ArrowUp,
  Bookmark,
  BookmarkPlus,

  MapPin,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useCallback, useState } from 'react'

import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,

  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { stagger, useOpenOnNewParam } from '@/lib/motion'
import type { Consignee, RoutePreset, VendorDivision, Warehouse } from '@/lib/resources'
import { useList } from '@/lib/resources'

interface DraftStop {
  consignee_id: string
  default_floor_number: string
  default_has_lift: boolean
  delivery_hint: string
}

export default function RoutePresetsPage() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<RoutePreset | null>(null)
  const [creating, setCreating] = useState(false)
  const [showRetired, setShowRetired] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useOpenOnNewParam(useCallback(() => setCreating(true), []))

  const presets = useList<RoutePreset>(
    '/route-presets',
    showRetired ? { include_inactive: true } : undefined,
  )

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['/route-presets'] })

  async function retire(preset: RoutePreset) {
    try {
      await api.delete(`/route-presets/${preset.id}`)
      refresh()
    } catch (e) {
      setError(apiErrorMessage(e))
    }
  }

  async function restore(preset: RoutePreset) {
    try {
      await api.post(`/route-presets/${preset.id}/restore`)
      refresh()
    } catch (e) {
      setError(apiErrorMessage(e))
    }
  }

  const rows = presets.data ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        description="The rounds you already run, saved with their stops in order. Pick one when building a trip and the whole route is filled in — then drop whoever has nothing this week."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
            New route
          </Button>
        }
      />

      <ErrorNote>{error}</ErrorNote>

      <label className="flex w-fit cursor-pointer items-center gap-2 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
        <input
          type="checkbox"
          checked={showRetired}
          onChange={(e) => setShowRetired(e.target.checked)}
        />
        Show retired routes
      </label>

      {presets.isLoading ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-44" style={stagger(i)} />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Bookmark className="size-7" />}
            title="No saved routes yet"
            description="Build a trip the long way once, then use “Save as route” on that form. After that the same round is one tap."
            action={
              <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                New route
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {rows.map((preset, i) => (
            <Card
              key={preset.id}
              className="hoverable overflow-hidden"
              style={{ ...stagger(i), opacity: preset.is_active ? 1 : 0.55 }}
            >
              <div className="flex items-start justify-between gap-3 p-4 pb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Bookmark className="size-4 shrink-0" style={{ color: 'var(--accent)' }} />
                    <h3 className="truncate text-[15px] font-semibold">{preset.name}</h3>
                    {!preset.is_active ? (
                      <span className="eyebrow" style={{ color: 'var(--warning)' }}>
                        Retired
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                    {preset.points.length} {preset.points.length === 1 ? 'stop' : 'stops'}
                    {preset.typical_round_trip_km ? ` · about ${preset.typical_round_trip_km} km` : ''}
                    {preset.times_used > 0
                      ? ` · used ${preset.times_used} ${preset.times_used === 1 ? 'time' : 'times'}`
                      : ' · never used'}
                  </p>
                </div>

                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => setEditing(preset)}
                    className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                    style={{ color: 'var(--text-muted)' }}
                    title="Edit this route"
                    aria-label={`Edit ${preset.name}`}
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  {preset.is_active ? (
                    <button
                      onClick={() => retire(preset)}
                      className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                      style={{ color: 'var(--text-faint)' }}
                      title="Retire — the stop order is kept"
                      aria-label={`Retire ${preset.name}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  ) : (
                    <button
                      onClick={() => restore(preset)}
                      className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                      style={{ color: 'var(--accent)' }}
                      title="Bring it back"
                      aria-label={`Restore ${preset.name}`}
                    >
                      <RotateCcw className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="groove mx-4" />

              {preset.points.length === 0 ? (
                <p className="px-4 py-5 text-center text-[12.5px]" style={{ color: 'var(--text-faint)' }}>
                  No stops on this route yet.
                </p>
              ) : (
                <ol className="p-4 pt-3">
                  {preset.points.map((p) => (
                    <li key={p.id} className="flex items-baseline gap-2.5 py-[3px] text-[12.5px]">
                      <span
                        className="tnum w-5 shrink-0 text-right font-medium"
                        style={{ color: 'var(--accent)' }}
                      >
                        {p.sequence}
                      </span>
                      <span className="truncate font-medium">{p.consignee_name}</span>
                      {p.consignee_city ? (
                        <span className="truncate" style={{ color: 'var(--text-faint)' }}>
                          {p.consignee_city}
                        </span>
                      ) : null}
                      {p.default_floor_number > 0 ? (
                        <span className="ml-auto shrink-0" style={{ color: 'var(--text-faint)' }}>
                          floor {p.default_floor_number}
                          {p.default_has_lift ? ' · lift' : ''}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          ))}
        </div>
      )}

      <PresetForm
        open={creating || !!editing}
        preset={editing}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        onSaved={refresh}
      />
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function PresetForm({
  open,
  preset,
  onClose,
  onSaved,
}: {
  open: boolean
  preset: RoutePreset | null
  onClose: () => void
  onSaved: () => void
}) {
  const divisions = useList<VendorDivision>('/vendor-divisions')
  const consignees = useList<Consignee>('/consignees')

  const [name, setName] = useState('')
  const [divisionId, setDivisionId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [km, setKm] = useState('')
  const [notes, setNotes] = useState('')
  const [stops, setStops] = useState<DraftStop[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  const vendorId = divisions.data?.find((d) => d.id === divisionId)?.vendor_id
  const warehouses = useList<Warehouse>(
    '/warehouses',
    vendorId ? { vendor_id: vendorId } : undefined,
    !!vendorId,
  )

  /* Fill the form from the preset being edited. Keyed on its id so reopening a
     different route reloads, but typing into the form does not get stamped on
     by a re-render. */
  const key = open ? (preset?.id ?? 'new') : null
  if (key && key !== loadedFor) {
    setLoadedFor(key)
    setName(preset?.name ?? '')
    setDivisionId(preset?.vendor_division_id ?? '')
    setWarehouseId(preset?.warehouse_id ?? '')
    setKm(preset?.typical_round_trip_km ? String(preset.typical_round_trip_km) : '')
    setNotes(preset?.notes ?? '')
    setStops(
      (preset?.points ?? []).map((p) => ({
        consignee_id: p.consignee_id,
        default_floor_number: String(p.default_floor_number),
        default_has_lift: p.default_has_lift,
        delivery_hint: p.delivery_hint ?? '',
      })),
    )
    setError(null)
  }
  if (!open && loadedFor !== null) setLoadedFor(null)

  const update = (i: number, patch: Partial<DraftStop>) =>
    setStops(stops.map((s, idx) => (idx === i ? { ...s, ...patch } : s)))

  /* Order is the route. Moving a stop is the commonest edit there is — a
     customer changes their opening time and the round reshuffles — so it is two
     arrows on the row rather than a drag that needs a library and a touch
     fallback. */
  function move(i: number, by: -1 | 1) {
    const next = [...stops]
    const target = i + by
    if (target < 0 || target >= next.length) return
    ;[next[i], next[target]] = [next[target], next[i]]
    setStops(next)
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    const filled = stops.filter((s) => s.consignee_id)
    const ids = filled.map((s) => s.consignee_id)
    if (new Set(ids).size !== ids.length) {
      setError('The same customer appears twice. A route visits each customer once.')
      return
    }

    const body = {
      name: name.trim(),
      vendor_division_id: divisionId || null,
      warehouse_id: warehouseId || null,
      typical_round_trip_km: km ? Number(km) : null,
      notes: notes.trim() || null,
      points: filled.map((s) => ({
        consignee_id: s.consignee_id,
        default_floor_number: Number(s.default_floor_number) || 0,
        default_has_lift: s.default_has_lift,
        delivery_hint: s.delivery_hint.trim() || null,
      })),
    }

    setBusy(true)
    try {
      if (preset) await api.put(`/route-presets/${preset.id}`, body)
      else await api.post('/route-presets', body)
      onSaved()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save this route'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={preset ? `Edit ${preset.name}` : 'New route'}
      description="Stops are delivered in the order listed. Editing a route never changes a trip that has already been built from it."
    >
      <form className="space-y-5" onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Route name" hint="What the office already calls it">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="No. 11"
              required
            />
          </Field>
          <Field label="Typical round trip" hint="Planning only — real km come from the odometer">
            <Input
              type="number"
              min={0}
              value={km}
              onChange={(e) => setKm(e.target.value)}
              placeholder="900"
            />
          </Field>
          <Field label="Vendor division" hint="Leave blank for a shared round">
            <Select
              value={divisionId}
              onChange={(e) => {
                setDivisionId(e.target.value)
                setWarehouseId('')
              }}
            >
              <option value="">Any</option>
              {divisions.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Starts from" hint="And returns here">
            <Select
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              disabled={!divisionId}
            >
              <option value="">Not set</option>
              {warehouses.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="eyebrow">Stops ({stops.length}), in delivery order</p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() =>
                setStops([
                  ...stops,
                  {
                    consignee_id: '',
                    default_floor_number: '0',
                    default_has_lift: false,
                    delivery_hint: '',
                  },
                ])
              }
            >
              Add stop
            </Button>
          </div>

          {stops.length === 0 ? (
            <div
              className="rounded-lg border border-dashed px-4 py-8 text-center text-[13px]"
              style={{ borderColor: 'var(--border-strong)', color: 'var(--text-faint)' }}
            >
              <MapPin className="mx-auto mb-2 size-5" />
              Add the customers this round serves, in the order the driver reaches them.
            </div>
          ) : (
            <div className="space-y-2">
              {stops.map((stop, i) => (
                <div
                  key={i}
                  className="grid items-end gap-2 rounded-[var(--radius-control)] p-2.5 sm:grid-cols-[auto_1fr_5rem_auto_auto]"
                  style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
                >
                  <span
                    className="tnum grid size-7 shrink-0 place-items-center rounded-md text-[12px] font-semibold"
                    style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                  >
                    {i + 1}
                  </span>

                  <Select
                    value={stop.consignee_id}
                    onChange={(e) => update(i, { consignee_id: e.target.value })}
                    aria-label={`Customer at stop ${i + 1}`}
                  >
                    <option value="">Select a customer</option>
                    {consignees.data?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                        {c.city ? ` — ${c.city}` : ''}
                      </option>
                    ))}
                  </Select>

                  <Input
                    type="number"
                    min={0}
                    value={stop.default_floor_number}
                    onChange={(e) => update(i, { default_floor_number: e.target.value })}
                    aria-label={`Floor at stop ${i + 1}`}
                    title="Floor — billable for furniture"
                  />

                  <label
                    className="flex h-11 cursor-pointer items-center gap-1.5 px-1 text-[12.5px] whitespace-nowrap"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <input
                      type="checkbox"
                      checked={stop.default_has_lift}
                      onChange={(e) => update(i, { default_has_lift: e.target.checked })}
                    />
                    Lift
                  </label>

                  <div className="flex gap-0.5">
                    <button
                      type="button"
                      onClick={() => move(i, -1)}
                      disabled={i === 0}
                      className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-25"
                      style={{ color: 'var(--text-muted)' }}
                      aria-label={`Move stop ${i + 1} earlier`}
                    >
                      <ArrowUp className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => move(i, 1)}
                      disabled={i === stops.length - 1}
                      className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-25"
                      style={{ color: 'var(--text-muted)' }}
                      aria-label={`Move stop ${i + 1} later`}
                    >
                      <ArrowDown className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setStops(stops.filter((_, idx) => idx !== i))}
                      className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                      style={{ color: 'var(--danger)' }}
                      aria-label={`Remove stop ${i + 1}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Field label="Notes" hint="Anything the next person planning this round should know">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>

        <ErrorNote>{error}</ErrorNote>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy} icon={<BookmarkPlus className="size-4" />}>
            {preset ? 'Save changes' : 'Create route'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
