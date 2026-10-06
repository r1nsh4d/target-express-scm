import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Copy,
  FileWarning,
  HandCoins,
  Package2,
  Replace,
  Gauge,
  Link2,
  GitBranch,
  Package,
  Pencil,
  Send,
  Truck,
} from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

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
  Select,
  Spinner,
  Textarea,
} from '@/components/ui'
import { EditTripModal, OverrideStatusModal } from '@/components/TripEditModals'
import { api, apiErrorMessage } from '@/lib/api'
import type { Driver, Freight, FreightLeg, FreightPoint, Quote, Vehicle } from '@/lib/resources'
import { STATUS_TONE, rupees, useAction, useItem, useList } from '@/lib/resources'

// The map only loads when a point's location is actually being edited.
const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

export default function TripDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const path = `/freights/${id}`

  const trip = useItem<Freight>(path, !!id)
  const quote = useItem<Quote>(`${path}/quote`, !!id)
  const vehicles = useList<Vehicle>('/vehicles')
  const drivers = useList<Driver>('/drivers')

  const [assignOpen, setAssignOpen] = useState(false)
  const [loadPoint, setLoadPoint] = useState<string | null>(null)
  const [locationPoint, setLocationPoint] = useState<string | null>(null)
  const [billsPoint, setBillsPoint] = useState<string | null>(null)
  const [chargesPoint, setChargesPoint] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [overriding, setOverriding] = useState(false)
  const [swapping, setSwapping] = useState(false)
  const [correcting, setCorrecting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: [path] })
    queryClient.invalidateQueries({ queryKey: [`${path}/quote`] })
    queryClient.invalidateQueries({ queryKey: ['/freights'] })
  }

  const dispatch = useAction<undefined>(`${path}/dispatch`, { onSuccess: refresh })

  if (trip.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="size-6" />
      </div>
    )
  }

  if (trip.isError || !trip.data) {
    return (
      <Card>
        <EmptyState title="Trip not found" description="It may have been cancelled or removed." />
      </Card>
    )
  }

  const t = trip.data
  const leg = t.legs[0]
  const canDispatch = ['PLANNED', 'LOADING'].includes(t.status) && t.legs.length > 0
  const loadedPoints = t.points.filter((p) => p.status !== 'PENDING').length

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate('/freights')}
        className="flex items-center gap-2 text-[13px] transition-colors hover:text-[var(--text)]"
        style={{ color: 'var(--text-muted)' }}
      >
        <ArrowLeft className="size-4" />
        All trips
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight">{t.trip_no}</h1>
            <Badge tone={STATUS_TONE[t.status] ?? 'neutral'}>{t.status.replace('_', ' ')}</Badge>
          </div>
          <p className="mt-1 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            {t.vendor_division_name} · {t.warehouse_name} · {t.trip_date}
            {t.lr_no ? ` · LR ${t.lr_no}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {['DRAFT', 'PLANNED', 'LOADING'].includes(t.status) ? (
            <Button
              variant="secondary"
              icon={<Pencil className="size-4" />}
              onClick={() => setEditing(true)}
            >
              Edit trip
            </Button>
          ) : null}
          {/* The hand override. Last in the row and quiet, because it is the
              exception: the normal path through these states records evidence
              at each step and this one records only a sentence. */}
          {!['BILLED', 'SETTLED'].includes(t.status) ? (
            <Button
              variant="ghost"
              icon={<GitBranch className="size-4" />}
              onClick={() => setOverriding(true)}
            >
              Set status
            </Button>
          ) : null}
          {['DRAFT', 'PLANNED'].includes(t.status) ? (
            <Button variant="secondary" icon={<Truck className="size-4" />} onClick={() => setAssignOpen(true)}>
              {t.legs.length ? 'Change vehicle' : 'Assign vehicle'}
            </Button>
          ) : null}
          {['DISPATCHED', 'IN_TRANSIT'].includes(t.status) ? (
            <Button
              variant="secondary"
              icon={<Replace className="size-4" />}
              onClick={() => setSwapping(true)}
            >
              Swap vehicle
            </Button>
          ) : null}
          {canDispatch ? (
            <Button
              icon={<Send className="size-4" />}
              loading={dispatch.isPending}
              onClick={() =>
                dispatch.mutate(undefined, { onError: (err) => setError(apiErrorMessage(err)) })
              }
            >
              Dispatch
            </Button>
          ) : null}
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {t.status === 'DRAFT' && !t.legs.length ? (
        <Card
          className="px-4 py-3 text-[13px]"
          style={{
            borderColor: 'color-mix(in oklab, var(--info) 30%, transparent)',
            background: 'color-mix(in oklab, var(--info) 8%, var(--surface))',
          }}
        >
          Assign a vehicle and driver, confirm the loading for each point, then dispatch. The LR
          number is issued at dispatch from that vehicle's book.
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Points" value={`${t.delivered_point_count}/${t.billable_point_count}`} sub="delivered / billable" />
        <Stat label="Distance" value={t.total_km ? `${t.total_km} km` : '—'} sub="round trip" />
        <Stat
          label="Vehicle"
          value={leg?.vehicle_no ?? '—'}
          sub={leg?.driver_name ?? 'not assigned'}
        />
        <Stat
          label="Loading"
          value={`${loadedPoints}/${t.points.length}`}
          sub="points confirmed"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <Card className="overflow-hidden">
          <div className="px-4 py-3.5">
            <h2 className="text-sm font-semibold">Delivery points</h2>
            <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
              Confirm the box count into the vehicle for each point before dispatch.
            </p>
          </div>
          <ul>
            {t.points.map((p) => (
              <li
                key={p.id}
                className="flex flex-wrap items-start gap-3 border-t px-4 py-3"
                style={{ borderColor: 'var(--border)' }}
              >
                <div
                  className="tnum flex size-7 shrink-0 items-center justify-center rounded-lg text-[12px] font-semibold"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                >
                  {p.sequence}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13.5px] font-medium">{p.consignee_name}</span>
                    <Badge tone={STATUS_TONE[p.status] ?? 'neutral'}>
                      {p.status.replace('_', ' ')}
                    </Badge>
                    {p.floor_number > 0 ? (
                      <Badge tone="info">
                        Floor {p.floor_number}
                        {p.has_lift ? ' · lift' : ''}
                      </Badge>
                    ) : null}
                  </div>
                  {p.address ? (
                    <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                      {p.address}
                    </p>
                  ) : null}
                  <p className="tnum mt-1 text-[12px]" style={{ color: 'var(--text-faint)' }}>
                    <Package className="mr-1 inline size-3" />
                    {p.loaded_box_count} loaded · {p.delivered_box_count} delivered
                    {!p.phone ? ' · no phone, no tracking link' : ''}
                  </p>
                  {/* Unloading and coolie are shown apart, always. Folding them
                      into one figure is precisely what makes "why has unloading
                      gone up?" unanswerable three weeks later. */}
                  {Number(p.unloading_billed) > 0 || Number(p.coolie_billed) > 0 ? (
                    <p className="tnum mt-1 flex flex-wrap gap-x-3 text-[12px]">
                      {Number(p.unloading_billed) > 0 ? (
                        <span style={{ color: 'var(--text-muted)' }}>
                          Unloading {rupees(p.unloading_billed)}
                          {Number(p.unloading_paid) !== Number(p.unloading_billed)
                            ? ` (paid ${rupees(p.unloading_paid)})`
                            : ''}
                        </span>
                      ) : null}
                      {Number(p.coolie_billed) > 0 ? (
                        <span style={{ color: 'var(--warning)' }} title={p.coolie_note ?? undefined}>
                          Coolie {rupees(p.coolie_billed)}
                          {Number(p.coolie_paid) !== Number(p.coolie_billed)
                            ? ` (paid ${rupees(p.coolie_paid)})`
                            : ''}
                        </span>
                      ) : null}
                    </p>
                  ) : null}
                  {p.tracking_url ? <TrackingLink url={p.tracking_url} /> : null}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {['DRAFT', 'PLANNED', 'LOADING'].includes(t.status) ? (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => setBillsPoint(p.id)}>
                        Bills
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setLocationPoint(p.id)}>
                        Location
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setLoadPoint(p.id)}>
                        Confirm loading
                      </Button>
                    </>
                  ) : null}
                  {/* Unloading is settled at the point, so this stays available
                      after loading closes - and shuts once the freight has been
                      invoiced, because changing a charge then would make the
                      invoice disagree with the trip it was built from. */}
                  {!['BILLED', 'SETTLED', 'CANCELLED'].includes(t.status) ? (
                    <Button size="sm" variant="secondary" onClick={() => setChargesPoint(p.id)}>
                      Charges
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-5">
          <Card className="overflow-hidden">
            <div className="px-4 py-3.5">
              <h2 className="text-sm font-semibold">What this bills</h2>
              <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                On the rate card in force on {t.trip_date}.
              </p>
            </div>
            {quote.isError ? (
              <div className="px-4 pb-4">
                <ErrorNote>
                  {apiErrorMessage(quote.error, 'No rate card covers this trip date')}
                </ErrorNote>
              </div>
            ) : quote.data ? (
              <div className="hairline">
                <QuoteRow label="Base trip" value={quote.data.base_amount} />
                <QuoteRow
                  label={`Extra distance (${quote.data.extra_km} km)`}
                  value={quote.data.extra_km_amount}
                />
                <QuoteRow
                  label={`Points (${quote.data.extra_points} extra)`}
                  value={quote.data.extra_point_amount}
                />
                <QuoteRow label="Unloading" value={quote.data.unloading} />
                <QuoteRow label="Toll" value={quote.data.toll} />
                <div
                  className="flex items-center justify-between border-t px-4 py-3"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <span className="text-[13px] font-semibold">Total</span>
                  <span className="tnum text-[15px] font-semibold">
                    {rupees(quote.data.line_total)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex justify-center py-8">
                <Spinner className="size-5" />
              </div>
            )}
          </Card>

          {quote.data?.trace?.length ? (
            <Card className="p-4">
              <h3 className="text-[11px] font-semibold tracking-[0.14em] uppercase" style={{ color: 'var(--text-faint)' }}>
                How it was worked out
              </h3>
              <ul className="mt-2 space-y-1">
                {quote.data.trace.map((line, i) => (
                  <li key={i} className="tnum text-[12px]" style={{ color: 'var(--text-muted)' }}>
                    {line}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <TripAccount path={path} />

          {t.legs.length ? (
            <Card className="overflow-hidden">
              <div className="px-4 py-3.5">
                <h2 className="text-sm font-semibold">Legs</h2>
              </div>
              {t.legs.map((l) => (
                <div
                  key={l.id}
                  className="flex items-start gap-3 border-t px-4 py-3"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <Gauge className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium">
                      {l.vehicle_no} · {l.driver_name}
                    </p>
                    <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {l.start_odometer?.toLocaleString('en-IN') ?? '—'} →{' '}
                      {l.end_odometer?.toLocaleString('en-IN') ?? 'open'}
                      {l.leg_distance_km ? ` · ${l.leg_distance_km} km` : ''}
                    </p>
                    {l.change_reason !== 'INITIAL' ? (
                      <Badge tone="warning">{l.change_reason.replace('_', ' ')}</Badge>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setCorrecting(l.id)}
                      className="mt-1 block text-[11.5px] underline underline-offset-2"
                      style={{ color: 'var(--info)' }}
                    >
                      Correct a reading
                    </button>
                  </div>
                </div>
              ))}
            </Card>
          ) : null}
        </div>
      </div>

      <AssignModal
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        path={path}
        vehicles={vehicles.data ?? []}
        drivers={drivers.data ?? []}
        onDone={refresh}
      />
      <LoadModal
        pointId={loadPoint}
        onClose={() => setLoadPoint(null)}
        path={path}
        defaultCount={t.points.find((p) => p.id === loadPoint)?.loaded_box_count ?? 0}
        onDone={refresh}
      />
      <LocationModal
        point={t.points.find((p) => p.id === locationPoint) ?? null}
        onClose={() => setLocationPoint(null)}
        path={path}
        onDone={refresh}
      />
      <BillsModal
        point={t.points.find((p) => p.id === billsPoint) ?? null}
        onClose={() => setBillsPoint(null)}
        path={path}
        onDone={refresh}
      />
      <ChargesModal
        point={t.points.find((p) => p.id === chargesPoint) ?? null}
        onClose={() => setChargesPoint(null)}
        path={path}
        onDone={refresh}
      />
      <EditTripModal
        open={editing}
        trip={t}
        onClose={() => setEditing(false)}
        path={path}
        onDone={refresh}
      />
      <OverrideStatusModal
        open={overriding}
        trip={t}
        onClose={() => setOverriding(false)}
        path={path}
        onDone={refresh}
      />
      <SwapVehicleModal
        open={swapping}
        onClose={() => setSwapping(false)}
        path={path}
        vehicles={vehicles.data ?? []}
        drivers={drivers.data ?? []}
        onDone={refresh}
      />
      <CorrectOdometerModal
        leg={t.legs.find((l) => l.id === correcting) ?? null}
        onClose={() => setCorrecting(null)}
        path={path}
        onDone={refresh}
      />
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="text-[11px] font-medium tracking-wide uppercase" style={{ color: 'var(--text-faint)' }}>
        {label}
      </p>
      <p className="tnum mt-1.5 text-lg font-semibold tracking-tight">{value}</p>
      {sub ? (
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
          {sub}
        </p>
      ) : null}
    </Card>
  )
}

function QuoteRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="flex items-center justify-between border-t px-4 py-2"
      style={{ borderColor: 'var(--border)' }}
    >
      <span className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span className="tnum text-[13px]">{rupees(value)}</span>
    </div>
  )
}

function TrackingLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(url).then(
          () => {
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          },
          () => undefined,
        )
      }}
      className="mt-1.5 inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] transition-colors hover:bg-[var(--surface-hover)]"
      style={{ color: 'var(--accent)' }}
    >
      {copied ? <Copy className="size-3" /> : <Link2 className="size-3" />}
      {copied ? 'Link copied' : 'Copy tracking link'}
    </button>
  )
}

function AssignModal({
  open,
  onClose,
  path,
  vehicles,
  drivers,
  onDone,
}: {
  open: boolean
  onClose: () => void
  path: string
  vehicles: Vehicle[]
  drivers: Driver[]
  onDone: () => void
}) {
  const [vehicleId, setVehicleId] = useState('')
  const [driverId, setDriverId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const assign = useAction<{ vehicle_id: string; driver_id: string }>(`${path}/assign`, {
    onSuccess: () => {
      onDone()
      onClose()
    },
  })

  const vehicle = vehicles.find((v) => v.id === vehicleId)

  return (
    <Modal open={open} onClose={onClose} title="Assign vehicle and driver">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          assign.mutate(
            { vehicle_id: vehicleId, driver_id: driverId },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Vehicle">
          <Select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} required>
            <option value="">Select a vehicle</option>
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {v.registration_no} · {v.ownership === 'OWNED' ? 'owned' : 'rented'}
              </option>
            ))}
          </Select>
        </Field>

        {vehicle?.ownership === 'HIRED' ? (
          <p
            className="rounded-lg border px-3.5 py-2.5 text-[12.5px]"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            This is a rented vehicle, so the hire settles to {vehicle.owner_name ?? 'its owner'}.
            The unloading cash still goes to the driver.
          </p>
        ) : null}

        <Field label="Driver">
          <Select value={driverId} onChange={(e) => setDriverId(e.target.value)} required>
            <option value="">Select a driver</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.phone}
              </option>
            ))}
          </Select>
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={assign.isPending}>
            Assign
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function LoadModal({
  pointId,
  onClose,
  path,
  defaultCount,
  onDone,
}: {
  pointId: string | null
  onClose: () => void
  path: string
  defaultCount: number
  onDone: () => void
}) {
  const [count, setCount] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const confirm = useAction<Record<string, unknown>>(
    `${path}/points/${pointId}/load`,
    {
      onSuccess: () => {
        setCount('')
        setReason('')
        onDone()
        onClose()
      },
    },
  )

  return (
    <Modal
      open={!!pointId}
      onClose={onClose}
      title="Confirm loading"
      description="The count going into the vehicle. This is the number the delivery count is checked against."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          confirm.mutate(
            {
              loaded_box_count: Number(count || defaultCount) || 0,
              short_reason: reason || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Boxes loaded">
          <Input
            className="tnum"
            type="number"
            min={0}
            value={count}
            placeholder={String(defaultCount)}
            onChange={(e) => setCount(e.target.value)}
            autoFocus
          />
        </Field>
        <Field label="Reason, if short" hint="Only needed when the count is below what was planned">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={confirm.isPending}>
            Confirm
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* A one-off location for this stop only.
 *
 * Deliveries go to odd places — a site office, a back gate, a relative's shop.
 * Correcting the point should not silently rewrite the customer's permanent
 * address, so keeping it is an explicit choice. */
function LocationModal({
  point,
  onClose,
  path,
  onDone,
}: {
  point: FreightPoint | null
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [floor, setFloor] = useState('0')
  const [lift, setLift] = useState(false)
  const [keep, setKeep] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openedFor, setOpenedFor] = useState<string | null>(null)

  // Seed the form the first time a given point is opened.
  if (point && openedFor !== point.id) {
    setOpenedFor(point.id)
    setPin(null)
    setFloor(String(point.floor_number ?? 0))
    setLift(!!point.has_lift)
    setKeep(false)
    setError(null)
  }

  const save = useAction<Record<string, unknown>>(
    `${path}/points/${point?.id}`,
    {
      onSuccess: () => {
        onDone()
        onClose()
      },
    },
  )

  return (
    <Modal
      open={!!point}
      onClose={onClose}
      wide
      title="Delivery location"
      description={point ? `Point ${point.sequence} · ${point.consignee_name}` : undefined}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          save.mutate(
            {
              ...(pin ? { latitude: String(pin.lat), longitude: String(pin.lng) } : {}),
              floor_number: Number(floor) || 0,
              has_lift: lift,
              save_to_customer: keep,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Suspense fallback={<div className="inset h-[260px] animate-pulse" />}>
          <LocationPicker
            value={
              pin ??
              (point?.latitude != null && point?.longitude != null
                ? { lat: Number(point.latitude), lng: Number(point.longitude) }
                : null)
            }
            onChange={setPin}
          />
        </Suspense>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Floor" hint="Ground is 0. Billable on furniture work.">
            <Input
              className="tnum"
              type="number"
              min={0}
              value={floor}
              onChange={(e) => setFloor(e.target.value)}
            />
          </Field>
          <div className="flex items-end pb-3">
            <Checkbox
              label="There is a lift"
              checked={lift}
              onChange={(e) => setLift(e.target.checked)}
            />
          </div>
        </div>

        <Checkbox
          label="Also save this location on the customer, for future deliveries"
          checked={keep}
          onChange={(e) => setKeep(e.target.checked)}
        />

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save location
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* What this freight pays out, after any advance                              */
/* -------------------------------------------------------------------------- */

interface Account {
  payee_type: 'DRIVER' | 'VEHICLE_OWNER'
  payee_name: string | null
  driver_names: string[]
  by_head: Record<string, string>
  gross: string
  advance_drawn: string
  advance_recovered: string
  balance_payable: string
  advance_carried_forward: string
  is_closed: boolean
}

function TripAccount({ path }: { path: string }) {
  const account = useItem<Account[]>(`${path}/account`)
  const rows = account.data ?? []
  if (!rows.length) return null

  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3.5">
        <h2 className="text-sm font-semibold">What this freight pays out</h2>
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
          A swapped vehicle produces two accounts, each covering the legs that party ran.
        </p>
      </div>

      {rows.map((a, i) => (
        <div key={i} className="border-t px-4 py-3.5" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium">{a.payee_name ?? '—'}</p>
              <p className="mt-0.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                {a.payee_type === 'VEHICLE_OWNER' ? 'Vehicle owner' : 'Driver'}
                {a.driver_names.length ? ` · driven by ${a.driver_names.join(', ')}` : ''}
              </p>
            </div>
            {a.is_closed ? <Badge tone="success">Closed</Badge> : null}
          </div>

          <div className="mt-3 space-y-1.5">
            {Object.entries(a.by_head)
              .filter(([, v]) => Number(v) !== 0)
              .map(([head, value]) => (
                <div key={head} className="flex items-baseline justify-between text-[12.5px]">
                  <span style={{ color: 'var(--text-muted)' }}>
                    {head.replaceAll('_', ' ').toLowerCase()}
                  </span>
                  <span className="tnum">{rupees(value)}</span>
                </div>
              ))}
            {Number(a.advance_recovered) > 0 ? (
              <div className="flex items-baseline justify-between text-[12.5px]">
                <span style={{ color: 'var(--warning)' }}>advance recovered</span>
                <span className="tnum" style={{ color: 'var(--warning)' }}>
                  −{rupees(a.advance_recovered)}
                </span>
              </div>
            ) : null}
          </div>

          <div className="groove my-2.5" />
          <div className="flex items-baseline justify-between">
            <span className="text-[12.5px] font-medium">Balance payable</span>
            <span className="tnum text-[15px] font-semibold">{rupees(a.balance_payable)}</span>
          </div>
          {Number(a.advance_carried_forward) > 0 ? (
            <p className="mt-1.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
              <HandCoins className="mr-1 inline size-3" />
              {rupees(a.advance_carried_forward)} of advance carries to the next freight.
            </p>
          ) : null}
        </div>
      ))}
    </Card>
  )
}

/* -------------------------------------------------------------------------- */
/* Attach vendor bills to a stop                                              */
/* -------------------------------------------------------------------------- */

interface BillRow {
  id: string
  vendor_bill_no: string
  bill_date: string
  consignee_id: string
  declared_box_count: number
  freight_point_id: string | null
}

function BillsModal({
  point,
  onClose,
  path,
  onDone,
}: {
  point: FreightPoint | null
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  // Only this customer's unassigned bills can go on this stop.
  const bills = useList<BillRow>('/consignments', { unassigned: true }, !!point)
  const mine = (bills.data ?? []).filter((b) => b.consignee_id === point?.consignee_id)

  const assign = useAction<{ consignment_ids: string[] }>(
    `${path}/points/${point?.id}/consignments`,
    {
      onSuccess: () => {
        setPicked([])
        onDone()
        onClose()
      },
    },
  )

  return (
    <Modal
      open={!!point}
      onClose={onClose}
      title="Attach bills to this stop"
      description={
        point
          ? `Point ${point.sequence} · ${point.consignee_name}. The box count comes from the bills, and the labels are printed from their boxes.`
          : undefined
      }
    >
      <div className="space-y-4">
        {mine.length === 0 ? (
          <EmptyState
            icon={<Package2 className="size-7" />}
            title="No unassigned bills for this customer"
            description="Create the consignment first, under Consignments."
          />
        ) : (
          <div className="space-y-2">
            {mine.map((b) => (
              <label
                key={b.id}
                className="flex cursor-pointer items-center gap-3 px-3.5 py-2.5"
                style={{
                  background: 'var(--bg)',
                  borderRadius: 'var(--radius-control)',
                  boxShadow: 'var(--neu-inset)',
                }}
              >
                <input
                  type="checkbox"
                  className="size-4"
                  style={{ accentColor: 'var(--accent)' }}
                  checked={picked.includes(b.id)}
                  onChange={(e) =>
                    setPicked(
                      e.target.checked ? [...picked, b.id] : picked.filter((id) => id !== b.id),
                    )
                  }
                />
                <span className="flex-1 text-[13px]">
                  Bill <span className="font-medium">{b.vendor_bill_no}</span>
                  <span className="tnum ml-2" style={{ color: 'var(--text-faint)' }}>
                    {b.bill_date}
                  </span>
                </span>
                <span className="tnum text-[13px]">{b.declared_box_count} boxes</span>
              </label>
            ))}
          </div>
        )}

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!picked.length}
            loading={assign.isPending}
            onClick={() => {
              setError(null)
              assign.mutate(
                { consignment_ids: picked },
                { onError: (err) => setError(apiErrorMessage(err)) },
              )
            }}
          >
            Attach {picked.length || ''} {picked.length === 1 ? 'bill' : 'bills'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Breakdown: close this leg, open the next                                   */
/* -------------------------------------------------------------------------- */

function SwapVehicleModal({
  open,
  onClose,
  path,
  vehicles,
  drivers,
  onDone,
}: {
  open: boolean
  onClose: () => void
  path: string
  vehicles: Vehicle[]
  drivers: Driver[]
  onDone: () => void
}) {
  const [form, setForm] = useState({
    vehicle_id: '',
    driver_id: '',
    start_odometer: '',
    reason: 'BREAKDOWN',
    notes: '',
  })
  const [error, setError] = useState<string | null>(null)

  const swap = useAction<Record<string, unknown>>(`${path}/swap-vehicle`, {
    onSuccess: () => {
      onDone()
      onClose()
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Swap the vehicle"
      description="Closes the current leg and opens a second one. The vendor still sees one freight; hire and driver pay divide across the two."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          swap.mutate(
            { ...form, start_odometer: Number(form.start_odometer) || 0 },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <p className="inset px-3.5 py-2.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
          <FileWarning className="mr-1.5 inline size-3.5" />
          Close the current leg&apos;s odometer first — that reading is what splits the kilometres.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Replacement vehicle">
            <Select
              value={form.vehicle_id}
              onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}
              required
            >
              <option value="">Select</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.registration_no} · {v.ownership === 'OWNED' ? 'owned' : 'rented'}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Driver">
            <Select
              value={form.driver_id}
              onChange={(e) => setForm({ ...form, driver_id: e.target.value })}
              required
            >
              <option value="">Select</option>
              {drivers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Its opening odometer">
            <Input
              className="tnum"
              type="number"
              min={0}
              value={form.start_odometer}
              onChange={(e) => setForm({ ...form, start_odometer: e.target.value })}
              required
            />
          </Field>
          <Field label="Why">
            <Select
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            >
              <option value="BREAKDOWN">Breakdown</option>
              <option value="ACCIDENT">Accident</option>
              <option value="DRIVER_UNAVAILABLE">Driver unavailable</option>
              <option value="OTHER">Other</option>
            </Select>
          </Field>
        </div>

        <Field label="Notes">
          <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={swap.isPending}>
            Swap vehicle
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Correct a meter reading, on the record                                     */
/* -------------------------------------------------------------------------- */

function CorrectOdometerModal({
  leg,
  onClose,
  path,
  onDone,
}: {
  leg: FreightLeg | null
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const [field, setField] = useState<'start_odometer' | 'end_odometer'>('start_odometer')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const correct = useAction<Record<string, unknown>>(`${path}/legs/${leg?.id}/correct-odometer`, {
    onSuccess: () => {
      setValue('')
      setReason('')
      onDone()
      onClose()
    },
  })

  const current = leg
    ? field === 'start_odometer'
      ? leg.start_odometer
      : leg.end_odometer
    : null

  return (
    <Modal
      open={!!leg}
      onClose={onClose}
      title="Correct a meter reading"
      description="The driver's original entry is kept. The correction is recorded with its reason and author, because billing is computed from these numbers."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          correct.mutate(
            { field, corrected_value: Number(value), reason },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Which reading">
          <Select
            value={field}
            onChange={(e) => setField(e.target.value as 'start_odometer' | 'end_odometer')}
          >
            <option value="start_odometer">Opening</option>
            <option value="end_odometer">Closing</option>
          </Select>
        </Field>

        <p className="inset px-3.5 py-2.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
          Currently recorded:{' '}
          <span className="tnum font-medium" style={{ color: 'var(--text)' }}>
            {current?.toLocaleString('en-IN') ?? 'not entered'}
          </span>
        </p>

        <Field label="Corrected reading">
          <Input
            className="tnum"
            type="number"
            min={0}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </Field>

        <Field label="Reason" hint="Kept on the audit trail">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Digits transposed when entered"
            required
            minLength={3}
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={correct.isPending}>
            Save correction
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Unloading and coolie, recorded at the stop they happened at                 */
/* -------------------------------------------------------------------------- */

/** Four numbers, kept deliberately apart.
 *
 * UNLOADING is work Target Express is responsible for. The vendor is billed for
 * it on the rate sheet, cash goes out to the labourers, and the driver takes an
 * agreed share of it — that share is set on his pay terms, not here.
 *
 * COOLIE is not that. At some markets a local porter gang controls who may
 * unload and demands cash before the lorry is touched. They are not our crew,
 * they are not on the rate sheet, and the money is reimbursed in full to
 * whoever handed it over rather than shared.
 *
 * Mixing the two into one figure is what makes "why has unloading gone up this
 * month?" unanswerable three weeks later, which is when a vendor asks.
 *
 * Paid and billed are separate for the same kind of reason: a spare-parts run
 * bills the vendor nothing for unloading while cash still leaves the driver's
 * pocket, and what a driver handed to a porter gang at an unfamiliar market is
 * not automatically what the vendor agreed to cover.
 */
function ChargesModal({
  point,
  onClose,
  path,
  onDone,
}: {
  point: FreightPoint | null
  onClose: () => void
  path: string
  onDone: () => void
}) {
  const [unloadingPaid, setUnloadingPaid] = useState('')
  const [unloadingBilled, setUnloadingBilled] = useState('')
  const [cooliePaid, setCooliePaid] = useState('')
  const [coolieBilled, setCoolieBilled] = useState('')
  const [coolieNote, setCoolieNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  const num = (v: string | number) => String(v ?? '') === '0' ? '' : String(v ?? '')

  if (point && point.id !== loadedFor) {
    setLoadedFor(point.id)
    setUnloadingPaid(num(point.unloading_paid))
    setUnloadingBilled(num(point.unloading_billed))
    setCooliePaid(num(point.coolie_paid))
    setCoolieBilled(num(point.coolie_billed))
    setCoolieNote(point.coolie_note ?? '')
    setError(null)
  }
  if (!point && loadedFor !== null) setLoadedFor(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!point) return

    const coolie = Number(coolieBilled) || 0
    if (coolie > 0 && !coolieNote.trim()) {
      // An unexplained cash line is the one a vendor refuses to pay. Making the
      // reason mandatory is what turns this from a number into a collectable
      // charge — and the moment it is collectable is now, not in three weeks.
      setError('Say who demanded the coolie money and why. A vendor will not reimburse a bare number.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await api.patch(`${path}/points/${point.id}`, {
        unloading_paid: Number(unloadingPaid) || 0,
        unloading_billed: Number(unloadingBilled) || 0,
        coolie_paid: Number(cooliePaid) || 0,
        coolie_billed: coolie,
        coolie_note: coolieNote.trim() || null,
      })
      onDone()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save these charges'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={!!point}
      onClose={onClose}
      wide
      title={point ? `Charges at stop ${point.sequence}` : 'Charges'}
      description={point?.consignee_name}
    >
      <form className="space-y-5" onSubmit={submit}>
        <section>
          <p className="eyebrow mb-2">Unloading</p>
          <p className="mb-3 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            Our own unloading, on the vendor's rate sheet. The driver's share of this is
            set on his pay terms — it is not entered here.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Paid out here" hint="Cash to the labourers at this stop">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={unloadingPaid}
                onChange={(e) => setUnloadingPaid(e.target.value)}
                placeholder="0.00"
              />
            </Field>
            <Field label="Billed to the vendor" hint="Zero on spare parts — they are not charged">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={unloadingBilled}
                onChange={(e) => setUnloadingBilled(e.target.value)}
                placeholder="0.00"
              />
            </Field>
          </div>
        </section>

        <div className="groove" />

        <section>
          <p className="eyebrow mb-2">Coolie</p>
          <p className="mb-3 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            Local porters who control unloading at this market. Not our crew and not on the
            rate sheet — reimbursed in full to whoever paid, never shared. Kept apart from
            unloading so a vendor querying the unloading figure can be answered.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Paid out here" hint="What the driver actually handed over">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={cooliePaid}
                onChange={(e) => setCooliePaid(e.target.value)}
                placeholder="0.00"
              />
            </Field>
            <Field label="Billed to the vendor" hint="What they agreed to reimburse">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={coolieBilled}
                onChange={(e) => setCoolieBilled(e.target.value)}
                placeholder="0.00"
              />
            </Field>
          </div>

          <div className="mt-4">
            <Field
              label="Who demanded it, and why"
              hint="Required when anything is billed. This is the sentence that gets it paid."
            >
              <Textarea
                rows={2}
                value={coolieNote}
                onChange={(e) => setCoolieNote(e.target.value)}
                placeholder="Porter gang at Kasaragod market, demanded before they would let us unload"
              />
            </Field>
          </div>
        </section>

        <ErrorNote>{error}</ErrorNote>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Save charges
          </Button>
        </div>
      </form>
    </Modal>
  )
}
