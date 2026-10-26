import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Check,
  Copy,
  FileWarning,
  HandCoins,
  Package2,
  Replace,
  ReceiptIndianRupee,
  Gauge,
  Link2,
  GitBranch,
  Package,
  Pencil,
  Printer,
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
import type { ChargeSheetData } from '@/components/ChargeSheet'
import { ChargeSheet } from '@/components/ChargeSheet'
import { FreightMoney } from '@/components/FreightMoney'
import { EditTripModal, OverrideStatusModal } from '@/components/TripEditModals'
import { api, apiErrorMessage } from '@/lib/api'
import { BRAND } from '@/lib/brand'
import type { Driver, Freight, FreightLeg, FreightPoint, Vehicle } from '@/lib/resources'
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
  const [pricing, setPricing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: [path] })
    queryClient.invalidateQueries({ queryKey: [`${path}/quote`] })
    queryClient.invalidateQueries({ queryKey: ['/freights'] })
  }

  const dispatch = useAction<undefined>(`${path}/dispatch`, { onSuccess: refresh })

  const reissue = useMutation({
    mutationFn: async (pointId: string) =>
      (await api.post(`${path}/points/${pointId}/tracking-link`, {})).data,
    onSuccess: refresh,
    onError: (err) => setError(apiErrorMessage(err)),
  })

  /* Raise an invoice for this freight alone, then open it.
     The freight becomes BILLED as a consequence of the invoice existing, which
     is the rule everywhere else — this only saves the trip to Invoices and the
     date-range fiddling that billing one freight used to need. */
  const bill = useMutation({
    mutationFn: async () => (await api.post(`${path}/bill`, {})).data as { id: string },
    onSuccess: (invoice) => {
      refresh()
      queryClient.invalidateQueries({ queryKey: ['/invoices'] })
      navigate(`/invoices?open=${invoice.id}`)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

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
          {/* Cancelled is the end of the line — nothing follows it, so there is
              nothing to offer. The replacement is a new trip. */}
          {!['BILLED', 'SETTLED', 'CANCELLED'].includes(t.status) ? (
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
          {/* A completed freight is billed from here, not by going to Invoices
              and narrowing a date range until it happens to contain this one
              trip. BILLED still follows from issuing an invoice — this raises
              the invoice, it does not set the flag. */}
          {t.status === 'COMPLETED' ? (
            <Button
              icon={<ReceiptIndianRupee className="size-4" />}
              loading={bill.isPending}
              onClick={() => {
                setError(null)
                bill.mutate()
              }}
            >
              Bill this freight
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
                    {p.bill_count} bill{p.bill_count === 1 ? '' : 's'} · {p.box_count} boxes ·{' '}
                    {p.loaded_box_count} loaded · {p.delivered_box_count} delivered
                    {!p.phone ? ' · no phone, no tracking link' : ''}
                  </p>
                  {/* The stop nobody put a bill on.
                      A point with no bills produces no boxes, so it produces no
                      labels — and the only place that showed up was an empty
                      sorting sheet with nothing saying what to do about it. It
                      is said here instead, beside the button that fixes it. */}
                  {/* The advice has to match the buttons actually on screen.
                      Bills can only be attached before dispatch, so on a trip
                      that has already left, "press Bills" points at a button
                      that is not there — which reads as the screen being
                      broken rather than the trip being past the point of
                      changing. */}
                  {p.bill_count === 0 && !['BILLED', 'SETTLED', 'CANCELLED'].includes(t.status) ? (
                    <p className="mt-1 text-[12px]" style={{ color: 'var(--warning)' }}>
                      {['DRAFT', 'PLANNED', 'LOADING'].includes(t.status) ? (
                        <>
                          No bills on this stop yet — press <strong>Bills</strong> to attach them.
                          Until then there is nothing to label and nothing to deliver here.
                        </>
                      ) : (
                        <>
                          No bills were attached to this stop before the trip left
                          {p.loaded_box_count > 0
                            ? `, though ${p.loaded_box_count} boxes were counted onto the vehicle`
                            : ''}
                          . Bills cannot be added once a trip is dispatched — the driver can still
                          record the delivery, and the stop still counts for billing.
                        </>
                      )}
                    </p>
                  ) : null}
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
                  {p.tracking_url ? (
                    <>
                      <TrackingLink
                        url={p.tracking_url}
                        phone={p.phone}
                        consignee={p.consignee_name}
                        tripNo={t.trip_no}
                      />
                      {p.tracking_expires_at ? (
                        <p className="mt-0.5 text-[11px]" style={{ color: 'var(--text-faint)' }}>
                          Works until {p.tracking_expires_at.slice(0, 10)}
                        </p>
                      ) : null}
                    </>
                  ) : null}
                  {/* The link ran out. The customer's page tells them to ask
                      the sender for a new one — this is the sender's end of
                      that conversation, which previously did not exist. */}
                  {/* No usable link, on a trip that has already left.
                      Expired is one way to arrive here; never issued is the
                      other — a stop whose links were cleared, or a trip whose
                      status was moved by hand rather than through Dispatch.
                      Both left the stop with no link AND no way to make one,
                      which is a dead end on the single screen that can fix
                      it. */}
                  {!p.tracking_url &&
                  ['DISPATCHED', 'IN_TRANSIT', 'COMPLETED'].includes(t.status) ? (
                    <div className="mt-1">
                      <p className="text-[12px]" style={{ color: 'var(--warning)' }}>
                        {p.tracking_expired
                          ? 'The tracking link for this stop has expired.'
                          : 'This stop has no tracking link yet.'}
                      </p>
                      <button
                        type="button"
                        className="mt-0.5 text-[12px] underline underline-offset-2"
                        style={{ color: 'var(--accent)' }}
                        disabled={reissue.isPending}
                        onClick={() => {
                          setError(null)
                          reissue.mutate(p.id)
                        }}
                      >
                        {p.tracking_expired ? 'Issue a new link' : 'Create a tracking link'}
                      </button>
                    </div>
                  ) : null}
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
          {/* What it bills used to live here on its own, with what it pays
              out further down the page, so "was this trip worth running"
              was a subtraction somebody did in their head between two cards.
              Both sides and the gap are now one block below the grid. */}
          <UnloadingSheets freightId={t.id} />

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

                    {/* What was settled for this run, where anything was.
                        Shown on the leg rather than tucked in a dialog,
                        because an agreed figure that is not visible beside
                        the kilometres is one somebody re-derives from the
                        rate and then queries. */}
                    {l.agreed_fare !== null || l.agreed_unloading !== null ? (
                      <p className="tnum mt-1 text-[12px]" style={{ color: 'var(--accent)' }}>
                        Agreed for this run:
                        {l.agreed_fare !== null ? ` ${rupees(l.agreed_fare)} driving` : ''}
                        {l.agreed_fare !== null && l.agreed_unloading !== null ? ' ·' : ''}
                        {l.agreed_unloading !== null
                          ? ` ${rupees(l.agreed_unloading)} unloading`
                          : ''}
                        {l.fare_note ? (
                          <span className="block" style={{ color: 'var(--text-faint)' }}>
                            {l.fare_note}
                          </span>
                        ) : null}
                      </p>
                    ) : null}

                    <div className="mt-1 flex flex-wrap gap-x-3">
                      <button
                        type="button"
                        onClick={() => setPricing(l.id)}
                        className="text-[11.5px] underline underline-offset-2"
                        style={{ color: 'var(--info)' }}
                      >
                        {l.agreed_fare !== null || l.agreed_unloading !== null
                          ? 'Change what was agreed'
                          : 'Set a fixed fare'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setCorrecting(l.id)}
                        className="text-[11.5px] underline underline-offset-2"
                        style={{ color: 'var(--info)' }}
                      >
                        Correct a reading
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </Card>
          ) : null}
        </div>
      </div>

      {/* In, out, and what is left. Full width because the whole point is
          that the two sides sit beside each other. */}
      <FreightMoney freightId={t.id} />

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

      <AgreedFareModal
        leg={t.legs.find((l) => l.id === pricing) ?? null}
        onClose={() => setPricing(null)}
        path={path}
        onDone={refresh}
      />
    </div>
  )
}

/* The figure settled for one run, rather than worked out from a rate.
 *
 * Per-kilometre pay is right for the ordinary case and wrong for the ones
 * people ring about: a Kasaragod round trip agreed as "twelve hundred for the
 * run" before the lorry leaves, or a short town job at a flat two fifty.
 * Without somewhere to put that, the real number lives in a notebook — and
 * once the real number is in a notebook, the settlement screen is decoration.
 *
 * The unloading box is here for the same reason and a sharper one. Where a
 * division prices unloading by neither article nor percentage, a driver was
 * being paid NOTHING for carrying goods in, with no screen anywhere to say
 * what he should get instead.
 *
 * BLANK AND ZERO ARE DIFFERENT. Blank means "work it out from his rate";
 * zero means somebody decided this run pays nothing for driving, which
 * happens on a day a driver is squared up another way. The form keeps them
 * apart rather than treating an empty box as a nil.
 */
function AgreedFareModal({
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
  const [fare, setFare] = useState('')
  const [unloading, setUnloading] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [openedFor, setOpenedFor] = useState<string | null>(null)

  if (leg && openedFor !== leg.id) {
    setOpenedFor(leg.id)
    setFare(leg.agreed_fare ?? '')
    setUnloading(leg.agreed_unloading ?? '')
    setNote(leg.fare_note ?? '')
    setError(null)
  }

  const save = useAction<Record<string, unknown>>(`${path}/legs/${leg?.id}/fare`, {
    onSuccess: () => {
      onDone()
      onClose()
    },
  })

  const km = leg?.leg_distance_km ?? 0

  return (
    <Modal
      open={!!leg}
      onClose={onClose}
      title="What was agreed for this run"
      description={
        leg
          ? `${leg.vehicle_no} · ${leg.driver_name}${km ? ` · ${km} km` : ''}. Leave a box empty to go back to his usual rate.`
          : undefined
      }
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          save.mutate(
            {
              // An empty box is "work it out", which is null — not zero. The
              // server takes the two as different answers, so the form has to
              // as well.
              fare: fare.trim() === '' ? null : fare,
              unloading: unloading.trim() === '' ? null : unloading,
              note: note,
              set_fare: true,
              set_unloading: true,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field
          label="Fare for the run"
          hint="Replaces the per-kilometre figure. Empty means use his usual rate."
        >
          <Input
            className="tnum"
            type="number"
            step="0.01"
            min={0}
            value={fare}
            placeholder="e.g. 1200"
            onChange={(e) => setFare(e.target.value)}
          />
        </Field>

        <Field
          label="Unloading for the run"
          hint="For vendors that price unloading by neither article nor share. He is still never paid less than he handed over at the points."
        >
          <Input
            className="tnum"
            type="number"
            step="0.01"
            min={0}
            value={unloading}
            placeholder="e.g. 300"
            onChange={(e) => setUnloading(e.target.value)}
          />
        </Field>

        <Field label="Why" hint="So the figure can be explained six weeks later">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Agreed with Anil — lorry was going back empty anyway"
          />
        </Field>

        <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
          This rewrites what the run pays straight away, so the trip screen and his phone both
          show it. A run already covered by a settlement cannot be changed.
        </p>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save what was agreed
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* The unloading charge sheets this trip produced.
 *
 * Here rather than only on the invoice, because the query a driver or a
 * dealer raises is about one run — "what did you charge us at Kottayam on the
 * 8th" — and reaching that through the invoice it was later folded into is
 * the long way round. Printing from here gives the dealer their copy without
 * sending the whole month's bill with it.
 */
function UnloadingSheets({ freightId }: { freightId: string }) {
  const company = useItem<{ name: string }>('/company')
  const sheets = useList<ChargeSheetData>(`/freights/${freightId}/unloading-sheets`)
  const [showing, setShowing] = useState(false)

  if (!sheets.data?.length) return null

  const total = sheets.data.reduce((sum, s) => sum + Number(s.billed_total), 0)

  return (
    <>
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-[13.5px] font-semibold">Unloading charge sheets</h3>
            <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
              {sheets.data.length} {sheets.data.length === 1 ? 'point' : 'points'} ·{' '}
              {rupees(total.toFixed(2))} billed
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => setShowing(true)}>
            View &amp; print
          </Button>
        </div>
      </Card>

      <Modal
        open={showing}
        onClose={() => setShowing(false)}
        wide
        printable
        title="Unloading charge sheets"
        description="One per delivery point, as the dealer signed it."
      >
        <div className="space-y-5">
          {sheets.data.map((sheet) => (
            <div key={sheet.point_id} className="tx-sheet-page">
              <ChargeSheet sheet={sheet} companyName={company.data?.name ?? ''} />
            </div>
          ))}
          <div className="flex justify-end gap-2 print:hidden">
            <Button variant="secondary" onClick={() => setShowing(false)}>
              Close
            </Button>
            <Button icon={<Printer className="size-4" />} onClick={() => window.print()}>
              Print
            </Button>
          </div>
        </div>
      </Modal>
    </>
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

/* Getting the tracking link to the customer.
 *
 * Copying it was the only option, which meant somebody then had to open
 * WhatsApp, find the customer and paste it — and in practice that is the step
 * that does not happen, so the link sits unused and the customer rings the
 * office instead.
 *
 * Send opens WhatsApp with the message already written and the customer's
 * number already filled in. No gateway, no API key, no per-message cost and
 * nothing to configure: it is a URL. For an operator this size that is the
 * right trade — a Business API account costs money and takes weeks of
 * verification to do a job a tap can do today.
 *
 * Without a mobile number there is nobody to send to, so it offers the copy
 * alone and says why. */
function TrackingLink({
  url,
  phone,
  consignee,
  tripNo,
}: {
  url: string
  phone?: string | null
  consignee?: string
  tripNo?: string
}) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard?.writeText(url).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      },
      () => undefined,
    )
  }

  // wa.me wants digits only, with the country code. Indian mobiles are stored
  // as ten digits here, so 91 is prefixed when it is not already there.
  const digits = (phone ?? '').replace(/\D/g, '')
  const waNumber = digits.length === 10 ? `91${digits}` : digits
  // Built from explicit line breaks rather than a multi-line template: a
  // reformat would fold this file's indentation into the message the
  // customer receives.
  const message = encodeURIComponent(
    [
      BRAND.name,
      '',
      `Your delivery${tripNo ? ` (${tripNo})` : ''} is on the way. You can follow it here:`,
      url,
      '',
      'This link works for three days.',
    ].join('\n'),
  )

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1">
      {waNumber.length >= 11 ? (
        <a
          href={`https://wa.me/${waNumber}?text=${message}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] no-underline transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--success)' }}
        >
          <Send className="size-3" />
          Send on WhatsApp
        </a>
      ) : null}

      <button
        type="button"
        onClick={copy}
        className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] transition-colors hover:bg-[var(--surface-hover)]"
        style={{ color: 'var(--accent)' }}
      >
        {copied ? <Copy className="size-3" /> : <Link2 className="size-3" />}
        {copied ? 'Link copied' : 'Copy link'}
      </button>

      {waNumber.length < 11 ? (
        <span className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
          · no mobile number on file for {consignee ?? 'this customer'}
        </span>
      ) : null}
    </div>
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
  /* The man chosen IS the lorry's owner. Then "the hire goes to the owner
     and the unloading to the driver" describes one person twice. */
  const ownerIsDriving =
    !!vehicle?.owner_id &&
    drivers.find((d) => d.id === driverId)?.vehicle_owner_id === vehicle.owner_id

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

        <Field label="Driver">
          <Select value={driverId} onChange={(e) => setDriverId(e.target.value)} required>
            <option value="">Select a driver</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.phone}
                {/* Said in the list as well as under it, because by the time
                    the note appears the choice has already been made. */}
                {vehicle && d.vehicle_owner_id === vehicle.owner_id
                  ? ' · owns this lorry'
                  : ''}
              </option>
            ))}
          </Select>
        </Field>

        {/* Where the money goes.

            A hired lorry is paid for as a lorry: one amount to its owner
            covering the run and what was carried in. Who drives it, and what
            that man is paid, is the owner's arrangement.

            This said the hire went to the owner and the unloading to the
            driver, which was the old split and made the screen describe two
            settlements where there is now one. */}
        {vehicle?.ownership === 'HIRED' ? (
          <p
            className="rounded-lg border px-3.5 py-2.5 text-[12.5px]"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            This is a hired lorry, so the whole run — the hire and the unloading — settles to{' '}
            {vehicle.owner_name ?? 'its owner'} as one amount.
            {ownerIsDriving
              ? ' He is driving it himself, so that is all of it.'
              : ` Whatever ${vehicle.owner_name ?? 'he'} pays the driver is between the two of
                 them, and Target Express does not record it.`}
          </p>
        ) : null}

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
      // Editing a point that already exists, so PATCH. The default POST was
      // landing on no route at all and coming back as "Method Not Allowed".
      method: 'patch',
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

  /* Two lists, not one.
   *
   * This asked only for UNASSIGNED bills, so a stop that already had its bill
   * attached showed "No unassigned bills for this customer" — which reads as
   * "the bill has gone", on a screen that says "1 bill · 6 boxes" two inches
   * above it. What is already here has to be visible before what could be
   * added to it. */
  const bills = useList<BillRow>('/consignments', undefined, !!point)
  const forCustomer = (bills.data ?? []).filter((b) => b.consignee_id === point?.consignee_id)
  const attached = forCustomer.filter((b) => b.freight_point_id === point?.id)
  const available = forCustomer.filter((b) => b.freight_point_id === null)

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
        {attached.length ? (
          <div>
            <p className="eyebrow mb-1.5">Already on this stop</p>
            <div className="space-y-2">
              {attached.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center gap-3 px-3.5 py-2.5"
                  style={{
                    background: 'var(--accent-dim)',
                    borderRadius: 'var(--radius-control)',
                  }}
                >
                  <Check className="size-4 shrink-0" style={{ color: 'var(--accent)' }} />
                  <span className="flex-1 text-[13px]">
                    Bill <span className="font-medium">{b.vendor_bill_no}</span>
                    <span className="tnum ml-2" style={{ color: 'var(--text-faint)' }}>
                      {b.bill_date}
                    </span>
                  </span>
                  <span className="tnum text-[13px]">{b.declared_box_count} boxes</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {available.length === 0 ? (
          attached.length ? (
            <p className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
              Nothing else of this customer's is waiting to be put on a trip. Another bill for
              them would be created under Consignments, or typed into the day sheet.
            </p>
          ) : (
            <EmptyState
              icon={<Package2 className="size-7" />}
              title="No bills for this customer yet"
              description="Create the consignment first, under Consignments — or type the day's bills into the day sheet and it will do both at once."
            />
          )
        ) : (
          <div>
            {attached.length ? <p className="eyebrow mb-1.5">Waiting to be attached</p> : null}
            <div className="space-y-2">
              {available.map((b) => (
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
