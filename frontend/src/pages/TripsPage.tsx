import { Bookmark, BookmarkPlus, MapPin, Plus, Route, Trash2 } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
import type {
  Consignee,
  Freight,
  FreightRow,
  RoutePreset,
  VendorDivision,
  Warehouse,
} from '@/lib/resources'
import { STATUS_TONE, useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function TripsPage() {
  const [open, setOpen] = useState(false)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen(true), []))
  const [statusFilter, setStatusFilter] = useState('')
  const navigate = useNavigate()

  const trips = useList<FreightRow>('/freights', statusFilter ? { status: statusFilter } : undefined)

  return (
    <div className="space-y-6">
      <PageHeader
        description="A freight runs out from one warehouse, serves its points, and is finished when the vehicle is back at that warehouse."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New trip
          </Button>
        }
      />

      <div className="max-w-xs">
        <Field label="Status">
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All</option>
            {['DRAFT', 'PLANNED', 'LOADING', 'DISPATCHED', 'IN_TRANSIT', 'COMPLETED', 'BILLED'].map(
              (s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ),
            )}
          </Select>
        </Field>
      </div>

      <Card className="overflow-hidden">
        {trips.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={trips.data ?? []}
            rowKey={(t) => t.id}
            onRowClick={(t) => navigate(`/freights/${t.id}`)}
            empty={
              <EmptyState
                icon={<Route className="size-7" />}
                title="No trips yet"
                description="Build one from a vendor division, a warehouse and the points it will serve."
                action={<Button onClick={() => setOpen(true)}>New trip</Button>}
              />
            }
            columns={[
              {
                key: 'trip',
                header: 'Trip',
                render: (t) => (
                  <div>
                    <div className="font-medium">{t.trip_no}</div>
                    {t.lr_no ? (
                      <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                        LR {t.lr_no}
                      </div>
                    ) : null}
                  </div>
                ),
              },
              { key: 'date', header: 'Date', render: (t) => <span className="tnum">{t.trip_date}</span> },
              {
                key: 'dest',
                header: 'Destination',
                render: (t) => (
                  <span className="block max-w-[20rem] truncate">{t.destination_text ?? '—'}</span>
                ),
              },
              {
                key: 'vehicle',
                header: 'Vehicle',
                render: (t) => (
                  <div>
                    <div>{t.vehicle_no ?? '—'}</div>
                    {t.driver_name ? (
                      <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                        {t.driver_name}
                      </div>
                    ) : null}
                  </div>
                ),
              },
              {
                key: 'km',
                header: 'KM',
                align: 'right',
                render: (t) => <span className="tnum">{t.total_km ?? '—'}</span>,
              },
              {
                key: 'status',
                header: 'Status',
                render: (t) => (
                  <Badge tone={STATUS_TONE[t.status] ?? 'neutral'}>{t.status.replace('_', ' ')}</Badge>
                ),
              },
            ]}
          />
        )}
      </Card>

      <TripForm open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

interface DraftPoint {
  consignee_id: string
  floor_number: string
  has_lift: boolean
  planned_box_count: string
}

function TripForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const divisions = useList<VendorDivision>('/vendor-divisions')
  const consignees = useList<Consignee>('/consignees')

  const [divisionId, setDivisionId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [tripDate, setTripDate] = useState(new Date().toISOString().slice(0, 10))
  const [points, setPoints] = useState<DraftPoint[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const vendorId = divisions.data?.find((d) => d.id === divisionId)?.vendor_id
  const warehouses = useList<Warehouse>('/warehouses', vendorId ? { vendor_id: vendorId } : undefined, !!vendorId)

  const create = useCreate<Record<string, unknown>, Freight>('/freights', {
    onSuccess: (trip) => {
      reset()
      onClose()
      navigate(`/freights/${trip.id}`)
    },
  })

  function reset() {
    setDivisionId('')
    setWarehouseId('')
    setPoints([])
    setError(null)
  }

  const addPoint = () =>
    setPoints([...points, { consignee_id: '', floor_number: '0', has_lift: false, planned_box_count: '0' }])

  const update = (i: number, patch: Partial<DraftPoint>) =>
    setPoints(points.map((p, idx) => (idx === i ? { ...p, ...patch } : p)))

  /* Load a saved round.
   *
   * The stops are COPIED in, and the preset is then forgotten. Editing "No. 11"
   * next month must not reach back and alter a freight that has already run and
   * been invoiced — so this freight keeps no reference to where it came from.
   *
   * The existing points are replaced rather than appended. Picking a round is
   * "start from this", and silently merging two rounds would produce a route
   * nobody asked for with duplicate stops in it. */
  function loadPreset(preset: RoutePreset) {
    setPoints(
      preset.points.map((p) => ({
        consignee_id: p.consignee_id,
        floor_number: String(p.default_floor_number ?? 0),
        has_lift: !!p.default_has_lift,
        planned_box_count: '0',
      })),
    )
    if (preset.warehouse_id) setWarehouseId(preset.warehouse_id)
    // Only the office's own count of how often the round earns its keep. It is
    // what puts the weekly rounds at the top of the list instead of alphabetical
    // order, and a failure here must never block creating the freight.
    api.post(`/route-presets/${preset.id}/used`).catch(() => {})
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="New trip"
      description="Points are delivered in the order listed. Drag order comes later — for now, add them in sequence."
    >
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          if (!points.length || points.some((p) => !p.consignee_id)) {
            setError('Every point needs a customer selected')
            return
          }
          create.mutate(
            {
              vendor_division_id: divisionId,
              warehouse_id: warehouseId,
              trip_date: tripDate,
              points: points.map((p) => ({
                consignee_id: p.consignee_id,
                floor_number: Number(p.floor_number) || 0,
                has_lift: p.has_lift,
                planned_box_count: Number(p.planned_box_count) || 0,
              })),
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Vendor division">
            <Select
              value={divisionId}
              onChange={(e) => {
                setDivisionId(e.target.value)
                setWarehouseId('')
              }}
              required
            >
              <option value="">Select</option>
              {divisions.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Origin warehouse" hint="The trip returns here">
            <Select
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              required
              disabled={!divisionId}
            >
              <option value="">Select</option>
              {warehouses.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Trip date">
            <Input type="date" value={tripDate} onChange={(e) => setTripDate(e.target.value)} required />
          </Field>
        </div>

        <PresetPicker divisionId={divisionId} onPick={loadPreset} />

        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] font-semibold tracking-[0.14em] uppercase" style={{ color: 'var(--text-faint)' }}>
              Delivery points ({points.length})
            </p>
            <div className="flex gap-2">
              {points.filter((p) => p.consignee_id).length > 1 ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  icon={<Bookmark className="size-3.5" />}
                  onClick={() => setSaving(true)}
                >
                  Save as route
                </Button>
              ) : null}
              <Button type="button" size="sm" variant="secondary" onClick={addPoint}>
                Add point
              </Button>
            </div>
          </div>

          {points.length === 0 ? (
            <div
              className="rounded-lg border border-dashed px-4 py-8 text-center text-[13px]"
              style={{ borderColor: 'var(--border-strong)', color: 'var(--text-faint)' }}
            >
              <MapPin className="mx-auto mb-2 size-5" />
              Add at least one delivery point.
            </div>
          ) : (
            <div className="space-y-2">
              {points.map((point, i) => (
                <div
                  key={i}
                  className="grid items-end gap-3 rounded-lg border p-3 sm:grid-cols-[2rem_1fr_6rem_6rem_auto]"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
                >
                  <div
                    className="tnum flex size-7 items-center justify-center rounded-lg text-[12px] font-semibold"
                    style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                  >
                    {i + 1}
                  </div>
                  <Select
                    value={point.consignee_id}
                    onChange={(e) => update(i, { consignee_id: e.target.value })}
                    required
                  >
                    <option value="">Select customer</option>
                    {consignees.data?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                        {c.city ? ` · ${c.city}` : ''}
                      </option>
                    ))}
                  </Select>
                  <Input
                    className="tnum"
                    type="number"
                    min={0}
                    value={point.floor_number}
                    onChange={(e) => update(i, { floor_number: e.target.value })}
                    placeholder="Floor"
                    title="Floor — billable on furniture work"
                  />
                  <Input
                    className="tnum"
                    type="number"
                    min={0}
                    value={point.planned_box_count}
                    onChange={(e) => update(i, { planned_box_count: e.target.value })}
                    placeholder="Boxes"
                    title="Planned box count"
                  />
                  <div className="flex items-center gap-3">
                    <Checkbox
                      label="Lift"
                      checked={point.has_lift}
                      onChange={(e) => update(i, { has_lift: e.target.checked })}
                    />
                    <button
                      type="button"
                      onClick={() => setPoints(points.filter((_, idx) => idx !== i))}
                      className="rounded-lg p-1.5 hover:bg-[var(--surface-hover)]"
                      style={{ color: 'var(--text-faint)' }}
                      aria-label={`Remove point ${i + 1}`}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create trip
          </Button>
        </div>
      </form>

      <SaveAsPresetModal
        open={saving}
        onClose={() => setSaving(false)}
        divisionId={divisionId}
        warehouseId={warehouseId}
        points={points}
        consignees={consignees.data ?? []}
      />
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Saved rounds                                                               */
/* -------------------------------------------------------------------------- */

/** Pick a saved round to start from.
 *
 *  This is the screen's reason for existing. The vendor's requirement arrives
 *  on WhatsApp, and the round is almost always one the office already runs —
 *  "No. 11", with the same dozen customers in the same order. Twenty minutes of
 *  typing becomes one tap, then dropping whoever has nothing this week.
 *
 *  Shown only once a division is chosen, because the list is filtered by it and
 *  an unfiltered list of every round the company runs is not a shortcut. */
function PresetPicker({
  divisionId,
  onPick,
}: {
  divisionId: string
  onPick: (preset: RoutePreset) => void
}) {
  const presets = useList<RoutePreset>(
    '/route-presets',
    divisionId ? { vendor_division_id: divisionId } : undefined,
    !!divisionId,
  )

  if (!divisionId) return null
  if (presets.isLoading) return <div className="skeleton h-16" />
  if (!presets.data?.length) return null

  return (
    <div
      className="rounded-[var(--radius-control)] p-3"
      style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
    >
      <p className="eyebrow mb-2.5">Start from a saved route</p>
      <div className="flex flex-wrap gap-2">
        {presets.data.map((preset) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => onPick(preset)}
            className="group flex items-center gap-2 rounded-full px-3 py-1.5 text-[12.5px] transition-colors"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border-strong)',
              color: 'var(--text)',
            }}
          >
            <Bookmark className="size-3.5" style={{ color: 'var(--accent)' }} />
            <span className="font-medium">{preset.name}</span>
            <span style={{ color: 'var(--text-faint)' }}>
              {preset.points.length} {preset.points.length === 1 ? 'stop' : 'stops'}
            </span>
          </button>
        ))}
      </div>
      <p className="mt-2.5 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
        Picking a route replaces the points below. Add or remove whoever differs this week —
        the saved route is not changed.
      </p>
    </div>
  )
}

/** Save the route just built, so next week is one tap.
 *
 *  Offered at the point the knowledge exists — the admin has just sequenced a
 *  round and knows what it is called. Asking them to go to another screen and
 *  retype it is how this feature would end up unused. */
function SaveAsPresetModal({
  open,
  onClose,
  divisionId,
  warehouseId,
  points,
  consignees,
}: {
  open: boolean
  onClose: () => void
  divisionId: string
  warehouseId: string
  points: DraftPoint[]
  consignees: Consignee[]
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const stops = points.filter((p) => p.consignee_id)

  const create = useCreate<Record<string, unknown>, RoutePreset>('/route-presets', {
    onSuccess: () => {
      setDone(true)
      setTimeout(() => {
        setDone(false)
        setName('')
        onClose()
      }, 1300)
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Save as a route"
      description="Give it the name the office already uses. Next time it is one tap instead of retyping every stop."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              name: name.trim(),
              vendor_division_id: divisionId || null,
              warehouse_id: warehouseId || null,
              points: stops.map((p) => ({
                consignee_id: p.consignee_id,
                default_floor_number: Number(p.floor_number) || 0,
                default_has_lift: p.has_lift,
              })),
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Route name" hint="Whatever it is called on the phone — “No. 11”, “Kasaragod Tuesday”">
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </Field>

        <div
          className="rounded-[var(--radius-control)] p-3"
          style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
        >
          <p className="eyebrow mb-2">
            {stops.length} {stops.length === 1 ? 'stop' : 'stops'}, in this order
          </p>
          <ol className="space-y-1 text-[12.5px]">
            {stops.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="tnum w-5 shrink-0 text-right" style={{ color: 'var(--text-faint)' }}>
                  {i + 1}.
                </span>
                <span className="truncate">
                  {consignees.find((c) => c.id === p.consignee_id)?.name ?? '—'}
                </span>
              </li>
            ))}
          </ol>
        </div>

        <ErrorNote>{error}</ErrorNote>
        {done ? (
          <p className="text-[13px]" style={{ color: 'var(--success)' }}>
            Saved. It will appear above next time you build a trip.
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            loading={create.isPending}
            icon={<BookmarkPlus className="size-4" />}
          >
            Save route
          </Button>
        </div>
      </form>
    </Modal>
  )
}
