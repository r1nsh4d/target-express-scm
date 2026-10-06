/* Editing a trip, and moving its status by hand.
 *
 * Both exist because reality does not always reach the application. The
 * alternative to building them is an admin editing the database directly,
 * which leaves no trace at all.
 */

import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import { useState } from 'react'

import {
  Button,
  ErrorNote,
  Field,
  Input,
  Modal,
  Select,
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import type { Consignee, Freight, Warehouse } from '@/lib/resources'
import { useList } from '@/lib/resources'

interface DraftStop {
  consignee_id: string
  floor: string
  lift: boolean
}

/** Correct a trip before it leaves.
 *
 * The vendor's requirement arrives on WhatsApp and changes twice before the
 * lorry moves — a customer drops out, another is added, the date slips a day.
 * Without this the only option was to cancel and rebuild, losing the trip
 * number and everything already recorded against it.
 *
 * The vendor division is deliberately not editable here: it decides which rate
 * card prices the trip, and changing it once points and boxes exist would
 * silently reprice work already done.
 */
export function EditTripModal({
  open,
  trip,
  onClose,
  path,
  onDone,
}: {
  open: boolean
  trip: Freight
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const consignees = useList<Consignee>('/consignees')
  const warehouses = useList<Warehouse>('/warehouses')

  const [tripDate, setTripDate] = useState(trip.trip_date)
  const [warehouseId, setWarehouseId] = useState('')
  const [stops, setStops] = useState<DraftStop[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  if (open && !loaded) {
    setLoaded(true)
    setTripDate(trip.trip_date)
    setWarehouseId('')
    setStops(
      trip.points.map((p) => ({
        consignee_id: p.consignee_id,
        floor: String(p.floor_number ?? 0),
        lift: !!p.has_lift,
      })),
    )
    setError(null)
  }
  if (!open && loaded) setLoaded(false)

  /* A stop that already has boxes against it cannot be swept away by a route
     change. The server refuses it; saying so here saves the round trip and,
     more usefully, names the stops that are in the way. */
  const lockedNames = trip.points
    .filter((p) => p.loaded_box_count > 0)
    .map((p) => p.consignee_name)

  function move(index: number, by: -1 | 1) {
    const next = [...stops]
    const target = index + by
    if (target < 0 || target >= next.length) return
    const held = next[index]
    next[index] = next[target]
    next[target] = held
    setStops(next)
  }

  function patch(index: number, change: Partial<DraftStop>) {
    setStops(stops.map((s, i) => (i === index ? { ...s, ...change } : s)))
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)

    const filled = stops.filter((s) => s.consignee_id)
    const body: Record<string, unknown> = { trip_date: tripDate }
    if (warehouseId) body.warehouse_id = warehouseId

    /* Points go up only when they actually changed. Sending them unchanged
       would still delete and rebuild every row on the server for nothing. */
    const routeChanged =
      filled.length !== trip.points.length ||
      filled.some((s, i) => s.consignee_id !== trip.points[i]?.consignee_id) ||
      filled.some((s, i) => Number(s.floor) !== trip.points[i]?.floor_number) ||
      filled.some((s, i) => s.lift !== trip.points[i]?.has_lift)

    if (routeChanged) {
      body.points = filled.map((s) => ({
        consignee_id: s.consignee_id,
        floor_number: Number(s.floor) || 0,
        has_lift: s.lift,
        planned_box_count: 0,
      }))
    }

    try {
      await api.patch(path, body)
      onDone()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save this trip'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={`Edit ${trip.trip_no}`}
      description="Only a trip that has not been dispatched can be changed. The vendor division is fixed — it decides which rate card prices this trip."
    >
      <form className="space-y-5" onSubmit={submit}>
        {lockedNames.length ? (
          <p
            className="rounded-[10px] px-3 py-2.5 text-[12.5px] leading-relaxed"
            style={{
              background: 'color-mix(in oklab, var(--warning) 12%, transparent)',
              color: 'var(--text-muted)',
            }}
          >
            Boxes are already assigned at {lockedNames.join(', ')}. Clear those stops first if
            you need to change the route — otherwise loaded boxes would belong to no point.
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Trip date">
            <Input
              type="date"
              value={tripDate}
              onChange={(e) => setTripDate(e.target.value)}
              required
            />
          </Field>
          <Field label="Origin warehouse" hint="Leave as it is to keep the current one">
            <Select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              <option value="">{trip.warehouse_name} (unchanged)</option>
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
            <p className="eyebrow">Delivery points ({stops.length})</p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setStops([...stops, { consignee_id: '', floor: '0', lift: false }])}
            >
              Add point
            </Button>
          </div>

          <div className="space-y-2">
            {stops.map((stop, i) => (
              <div
                key={i}
                className="grid items-end gap-2 rounded-[var(--radius-control)] p-2.5 sm:grid-cols-[auto_1fr_5rem_auto_auto]"
                style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
              >
                <span
                  className="tnum grid size-7 place-items-center rounded-md text-[12px] font-semibold"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                >
                  {i + 1}
                </span>

                <Select
                  value={stop.consignee_id}
                  onChange={(e) => patch(i, { consignee_id: e.target.value })}
                  aria-label={`Customer at point ${i + 1}`}
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
                  value={stop.floor}
                  onChange={(e) => patch(i, { floor: e.target.value })}
                  aria-label={`Floor at point ${i + 1}`}
                  title="Floor — billable for furniture"
                />

                <label
                  className="flex h-11 cursor-pointer items-center gap-1.5 px-1 text-[12.5px] whitespace-nowrap"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <input
                    type="checkbox"
                    checked={stop.lift}
                    onChange={(e) => patch(i, { lift: e.target.checked })}
                  />
                  Lift
                </label>

                <div className="flex gap-0.5">
                  <button
                    type="button"
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    className="rounded-lg p-2 hover:bg-[var(--surface-hover)] disabled:opacity-25"
                    style={{ color: 'var(--text-muted)' }}
                    aria-label={`Move point ${i + 1} earlier`}
                  >
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(i, 1)}
                    disabled={i === stops.length - 1}
                    className="rounded-lg p-2 hover:bg-[var(--surface-hover)] disabled:opacity-25"
                    style={{ color: 'var(--text-muted)' }}
                    aria-label={`Move point ${i + 1} later`}
                  >
                    <ArrowDown className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setStops(stops.filter((_, x) => x !== i))}
                    className="rounded-lg p-2 hover:bg-[var(--surface-hover)]"
                    style={{ color: 'var(--danger)' }}
                    aria-label={`Remove point ${i + 1}`}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
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

/* -------------------------------------------------------------------------- */

/* BILLED and SETTLED are absent on purpose: those follow from an invoice and a
   settlement existing, and a trip marked BILLED with no invoice behind it is a
   hole in the accounts. */
const OVERRIDABLE_STATUSES = [
  'DRAFT',
  'PLANNED',
  'LOADING',
  'DISPATCHED',
  'IN_TRANSIT',
  'COMPLETED',
  'CANCELLED',
] as const

/** Move a trip's status by hand.
 *
 * A driver's phone dies, a run is finished on paper, somebody forgets to press
 * a button for two days. The alternative to this is an admin editing the
 * database directly.
 *
 * The reason is mandatory. The normal path through these states records
 * evidence at every step — odometer readings, photographs, box counts — and
 * jumping straight to a status records none of it. The sentence IS the
 * evidence, and it goes into the audit trail with the name of whoever typed it.
 */
export function OverrideStatusModal({
  open,
  trip,
  onClose,
  path,
  onDone,
}: {
  open: boolean
  trip: Freight
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const [status, setStatus] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.post(`${path}/status`, { status, reason: reason.trim() })
      onDone()
      setStatus('')
      setReason('')
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not change the status'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Set the status by hand"
      description="For when what happened on the road did not reach the app. Every change here is recorded against your name."
    >
      <form className="space-y-4" onSubmit={submit}>
        <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
          Currently <span className="font-medium">{trip.status.replace('_', ' ')}</span>.
        </p>

        <Field label="Move it to">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} required>
            <option value="">Select</option>
            {OVERRIDABLE_STATUSES.filter((s) => s !== trip.status).map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Why"
          hint="Recorded in the audit trail. This is the only evidence the change was legitimate."
        >
          <Textarea
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Driver's phone died at Kanhangad. Run finished on paper, odometer read at the gate."
            required
            minLength={4}
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy} disabled={!status || reason.trim().length < 4}>
            Change status
          </Button>
        </div>
      </form>
    </Modal>
  )
}
