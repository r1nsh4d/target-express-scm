import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Printer,
  CheckCircle2,
  MapPin,
  Package,
  PackageCheck,
  Phone,
  Truck,
} from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { createPortal } from 'react-dom'
import { useParams } from 'react-router-dom'

import { ConsignmentNote } from '@/components/ConsignmentNote'
import { BRAND } from '@/lib/brand'
import { Button, Card, ErrorNote, Spinner, Textarea } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

const TrackMap = lazy(() =>
  import('@/components/TrackMap').then((m) => ({ default: m.TrackMap })),
)

const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

/* The customer's page. No login, no app — the token in the link is the whole
   credential. It shows this delivery and nothing else: no vendor, no other
   customers on the run, no prices. */

interface TrackedBox {
  bill_no: string
  item_no: number
  of_total: number
  item_name: string | null
  delivered: boolean
}

interface Tracking {
  consignee_name: string
  address: string | null
  status: string
  stop_number: number
  stops_before: number
  box_count: number
  boxes: TrackedBox[]
  dispatched: boolean
  planned_eta: string | null
  arrived_at: string | null
  delivered_at: string | null
  latitude: number | null
  longitude: number | null
  can_update_location: boolean
  vehicle_position: { latitude: number; longitude: number; recorded_at: string } | null
  distance_km: number | null
  eta_minutes: number | null
  lr_no: string | null
  trip_no: string | null
  trip_date: string | null
  vendor_name: string | null
  from_warehouse: string | null
  from_address: string | null
  vehicle_no: string | null
  driver_name: string | null
  consignee_phone: string | null
  customer_rating: number | null
  customer_remarks: string | null
  driver_phone: string | null
  delivery_photo_url: string | null
  receiver_name: string | null
}

export default function TrackPage() {
  const { token } = useParams<{ token: string }>()
  const queryClient = useQueryClient()
  const [fixing, setFixing] = useState(false)
  const [showNote, setShowNote] = useState(false)
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: ['track', token],
    queryFn: async () => (await api.get<Tracking>(`/track/${token}`)).data,
    retry: false,
    // The vehicle moves; this page should not need a reload to show it.
    refetchInterval: 45_000,
  })

  const submitLocation = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ message: string }>(`/track/${token}/location`, {
          latitude: pin!.lat,
          longitude: pin!.lng,
        })
      ).data,
    onSuccess: (res) => {
      setNote(res.message)
      setFixing(false)
      setPin(null)
      queryClient.invalidateQueries({ queryKey: ['track', token] })
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  if (isLoading) {
    return (
      <Shell>
        <div className="flex justify-center py-24">
          <Spinner className="size-6" />
        </div>
      </Shell>
    )
  }

  if (isError || !data) {
    return (
      <Shell>
        <Card className="p-8 text-center">
          <p className="text-[15px] font-medium">
            {apiErrorMessage(loadError, 'This tracking link is no longer active.')}
          </p>
          <p className="mt-2 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            If your delivery is still expected, please contact the sender for a new link.
          </p>
        </Card>
      </Shell>
    )
  }

  const delivered = data.status === 'DELIVERED' || data.status === 'PART_DELIVERED'

  /* The one line the customer opened the link for, said in the largest type
     on the page. It was a 13.5px grey line under a name, which is the size of
     an afterthought — somebody standing in a shop doorway holding a phone
     should get the answer without reading. */
  const headline = delivered
    ? 'Delivered'
    : !data.dispatched
      ? 'Being loaded'
      : data.eta_minutes !== null
        ? `About ${humanMinutes(data.eta_minutes)} away`
        : data.stops_before === 0
          ? 'Yours is next'
          : `${data.stops_before} ${data.stops_before === 1 ? 'stop' : 'stops'} to go`

  const subline = delivered
    ? data.receiver_name
      ? `Received by ${data.receiver_name}`
      : 'The goods are in'
    : !data.dispatched
      ? 'Still at the warehouse. This page will move once the lorry sets off.'
      : data.stops_before === 0
        ? 'The lorry is on its way to you now'
        : `${data.stops_before} ${data.stops_before === 1 ? 'delivery' : 'deliveries'} before yours`

  // Booked, loaded, on the way, delivered.
  const step = delivered ? 3 : data.dispatched ? 2 : 1

  return (
    <Shell>
      <div className="space-y-4">
        <Card className="tx-in p-5">
          <div className="flex items-start gap-3">
            <span
              className="grid size-11 shrink-0 place-items-center rounded-[13px]"
              style={
                delivered
                  ? {
                      background: 'color-mix(in oklab, var(--success) 16%, transparent)',
                      color: 'var(--success)',
                    }
                  : { background: 'var(--accent-dim)', color: 'var(--accent)' }
              }
            >
              {delivered ? <PackageCheck className="size-5" /> : <Truck className="size-5" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {!delivered && data.dispatched ? (
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10.5px] font-medium"
                    style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                  >
                    <span className="live-dot" />
                    On the road
                  </span>
                ) : null}
                {data.lr_no ? (
                  <span
                    className="tnum text-[10px] tracking-[0.14em] uppercase"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    LR {data.lr_no}
                    {data.trip_no ? ` · ${data.trip_no}` : ''}
                  </span>
                ) : null}
              </div>

              <h1 className="mt-1.5 text-[26px] leading-[1.1] font-semibold tracking-tight">
                {headline}
              </h1>
              <p className="mt-1 text-[13.5px]" style={{ color: 'var(--text-muted)' }}>
                {subline}
              </p>
            </div>
          </div>

          <Journey step={step} />

          <div className="groove my-4" />

          <p className="text-[13px] font-medium">{data.consignee_name}</p>
          {data.address ? (
            <p
              className="mt-1 flex gap-2 text-[12.5px] leading-relaxed"
              style={{ color: 'var(--text-muted)' }}
            >
              <MapPin className="mt-0.5 size-3.5 shrink-0" />
              {data.address}
            </p>
          ) : null}

          {delivered && data.delivered_at ? (
            <p
              className="mt-3 flex items-center gap-2 text-[12.5px]"
              style={{ color: 'var(--success)' }}
            >
              <CheckCircle2 className="size-4 shrink-0" />
              Signed for on {new Date(data.delivered_at).toLocaleString('en-IN', {
                day: '2-digit',
                month: 'short',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </p>
          ) : null}

          {/* Where it is, and roughly how long.
              Shown together because neither is much use alone: a lorry on a map
              with no sense of when, or a time with no sense of where, both
              leave the customer asking the same question they opened the link
              to answer. */}
          {/* Dispatched, but the lorry has not reported yet.
              Hiding the map in silence is how the feature looks missing
              rather than idle — and the customer is left wondering whether
              the page is broken or the lorry simply has not set off. */}
          {!delivered && data.dispatched && !data.vehicle_position ? (
            <div
              className="mt-4 flex items-start gap-2.5 rounded-[var(--radius-control)] px-3.5 py-3"
              style={{ background: 'var(--bg-elevated)' }}
            >
              <MapPin className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--text-faint)' }} />
              <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                The lorry has not reported its position yet. Live tracking appears here once the
                driver is on the road.
              </p>
            </div>
          ) : null}

          {!delivered && data.vehicle_position ? (
            <div className="mt-4">
              <Suspense fallback={<div className="skeleton" style={{ height: 220 }} />}>
                <TrackMap
                  vehicle={data.vehicle_position}
                  destination={
                    data.latitude !== null && data.longitude !== null
                      ? { latitude: data.latitude, longitude: data.longitude }
                      : null
                  }
                />
              </Suspense>

              {/* The headline above already carries the time, so this line
                  carries what it cannot: how far, and how fresh the marker
                  is. A lorry that last reported forty minutes ago is in a
                  dead spot, and a customer watching a dot that has not moved
                  deserves to know that rather than conclude it is parked. */}
              <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12.5px]">
                {data.distance_km !== null ? (
                  <span className="tnum font-medium">{data.distance_km} km away</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Still some way off</span>
                )}
                <span style={{ color: 'var(--text-faint)' }}>
                  position updated {sinceText(data.vehicle_position.recorded_at)}
                </span>
              </div>

              {/* Said plainly. Every delivery company's "arriving at 14:37" is
                  wrong often enough to be resented, and a customer deciding
                  whether to go out is better served by an honest rough answer
                  than a precise-looking one. */}
              {data.eta_minutes !== null ? (
                <p className="mt-1 text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  An estimate from the lorry's position
                  {data.stops_before > 0
                    ? ` and the ${data.stops_before} ${data.stops_before === 1 ? 'stop' : 'stops'} before yours`
                    : ''}
                  . Traffic and the road will change it.
                </p>
              ) : null}
            </div>
          ) : null}

          {/* Who is bringing it, and on what.
              A name and a number plate is what turns "a lorry is coming" into
              something a person can look out for, and it is the first thing
              every delivery app shows. */}
          {!delivered && (data.driver_name || data.vehicle_no) ? (
            <div
              className="mt-4 flex items-center gap-3 rounded-[var(--radius-control)] px-3.5 py-3"
              style={{ background: 'var(--bg-elevated)' }}
            >
              <span
                className="grid size-9 shrink-0 place-items-center rounded-full text-[13px] font-semibold"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
              >
                {(data.driver_name ?? '?').slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium">{data.driver_name ?? 'Driver'}</p>
                {data.vehicle_no ? (
                  <p className="tnum text-[12px]" style={{ color: 'var(--text-muted)' }}>
                    {data.vehicle_no}
                  </p>
                ) : null}
              </div>
              {data.driver_phone ? (
                <a
                  href={`tel:${data.driver_phone}`}
                  className="grid size-9 shrink-0 place-items-center rounded-full no-underline"
                  style={{ background: 'var(--accent)', color: '#04121a' }}
                  aria-label="Call the driver"
                >
                  <Phone className="size-4" />
                </a>
              ) : null}
            </div>
          ) : null}
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-start justify-between gap-3 px-5 py-4">
            <div>
              <h2 className="text-[14px] font-semibold">
                Your {data.box_count} {data.box_count === 1 ? 'box' : 'boxes'}
              </h2>
              <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                Listed against the bill numbers on the cartons.
              </p>
            </div>
            {/* How many are actually in. On a part delivery this is the whole
                question, and it was readable only by counting the colour of
                four identical icons. */}
            {data.boxes.some((b) => b.delivered) ? (
              <span
                className="tnum shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-medium"
                style={{
                  background: 'color-mix(in oklab, var(--success) 14%, transparent)',
                  color: 'var(--success)',
                }}
              >
                {data.boxes.filter((b) => b.delivered).length} of {data.boxes.length} in
              </span>
            ) : null}
          </div>
          {data.boxes.length ? (
            <ul>
              {data.boxes.map((b) => (
                <li
                  key={`${b.bill_no}-${b.item_no}`}
                  className="flex items-center gap-3 px-5 py-2.5"
                  style={{ borderTop: '1px solid var(--border)' }}
                >
                  {b.delivered ? (
                    <CheckCircle2 className="size-4 shrink-0" style={{ color: 'var(--success)' }} />
                  ) : (
                    <Package className="size-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
                  )}
                  <span className="min-w-0 flex-1 text-[13px]">
                    <span className="tnum">
                      Bill {b.bill_no} · box {b.item_no} of {b.of_total}
                    </span>
                    {b.item_name ? (
                      <span className="block text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                        {b.item_name}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 pb-5 text-[13px]" style={{ color: 'var(--text-muted)' }}>
              {data.box_count} boxes are on their way.
            </p>
          )}
        </Card>

        {/* Only once the goods are in.
            Rating a delivery that has not happened is either a mistake or
            somebody rating the wait, and neither is what this measures. */}
        {delivered ? <RateDelivery token={token!} data={data} /> : null}

        {/* The consignment note.
            The LR is the document that travels with the goods, and until now
            the customer had no way to get their part of it — they had a page
            that disappears after three days and nothing to keep. A dealer
            asked by their own accounts what arrived, when and on whose lorry
            had nothing to show. */}
        <Card className="px-5 py-4 print:hidden">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-[14px] font-semibold">Consignment note</h2>
              <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                Your copy of the LR, to keep or forward.
              </p>
            </div>
            <Button
              variant="secondary"
              icon={<FileText className="size-4" />}
              onClick={() => setShowNote(true)}
            >
              View &amp; save
            </Button>
          </div>
        </Card>

        {delivered && data.delivery_photo_url ? (
          <Card className="overflow-hidden">
            <div className="px-5 py-4">
              <h2 className="text-[14px] font-semibold">Proof of delivery</h2>
            </div>
            <img src={data.delivery_photo_url} alt="Proof of delivery" className="w-full" />
          </Card>
        ) : null}

        {note ? (
          <Card
            className="px-5 py-4 text-[13px]"
            style={{ background: 'color-mix(in oklab, var(--success) 10%, var(--surface))' }}
          >
            {note}
          </Card>
        ) : null}

        {data.can_update_location ? (
          <Card className="p-5">
            <h2 className="text-[14px] font-semibold">Is the location right?</h2>
            <p className="mt-1 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              If the pin is wrong, move it and the driver will use the corrected one.
            </p>

            {fixing ? (
              <div className="mt-4 space-y-3">
                <Suspense fallback={<div className="inset h-[240px] animate-pulse" />}>
                  <LocationPicker
                    value={
                      pin ??
                      (data.latitude != null && data.longitude != null
                        ? { lat: data.latitude, lng: data.longitude }
                        : null)
                    }
                    onChange={setPin}
                    height={240}
                  />
                </Suspense>
                <ErrorNote>{error}</ErrorNote>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setFixing(false)} className="flex-1">
                    Cancel
                  </Button>
                  <Button
                    className="flex-1"
                    disabled={!pin}
                    loading={submitLocation.isPending}
                    onClick={() => {
                      setError(null)
                      submitLocation.mutate()
                    }}
                  >
                    Use this location
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                className="mt-4 w-full"
                icon={<MapPin className="size-4" />}
                onClick={() => setFixing(true)}
              >
                Correct the location
              </Button>
            )}
          </Card>
        ) : null}
      </div>

      {/* Shown over the page rather than on it. A consignment note is a
          document, and a document competing for space with a live tracking
          card is neither. Printing from here gives the note alone — the
          browser's own "Save as PDF" is the download, which needs no library
          and produces a file every accounts department already knows. */}
      {/* On document.body, not here.
          The print stylesheet hides `main` in order to print a sheet's
          contents alone, and this overlay sits inside `main` — left where it
          is written, printing it would give a blank page. */}
      {showNote
        ? createPortal(
        <div
          className="tx-print-sheet fixed inset-0 z-50 overflow-y-auto"
          style={{ background: 'rgba(2,4,8,0.85)' }}
        >
          <div className="mx-auto w-full max-w-[760px] px-4 py-6">
            <div className="tx-modal-head mb-3 flex items-center justify-between gap-3">
              <Button variant="secondary" onClick={() => setShowNote(false)}>
                Close
              </Button>
              <Button icon={<Printer className="size-4" />} onClick={() => window.print()}>
                Print / Save as PDF
              </Button>
            </div>
            <div className="tx-modal-body">
              <ConsignmentNote
                note={{
                  lr_no: data.lr_no,
                  trip_no: data.trip_no,
                  trip_date: data.trip_date,
                  vendor_name: data.vendor_name,
                  from_warehouse: data.from_warehouse,
                  from_address: data.from_address,
                  vehicle_no: data.vehicle_no,
                  driver_name: data.driver_name,
                  consignee_name: data.consignee_name,
                  consignee_phone: data.consignee_phone,
                  address: data.address,
                  box_count: data.box_count,
                  boxes: data.boxes,
                  status: data.status,
                  delivered_at: data.delivered_at,
                  receiver_name: data.receiver_name,
                }}
                trackUrl={window.location.href}
              />
            </div>
          </div>
        </div>,
            document.body,
          )
        : null}
    </Shell>
  )
}

/* The same field the tracking form stands on.
 *
 * The form was given a hero, a glow and a grid, and the page it leads to — the
 * one the customer actually came for and the only page of ours most of them
 * will ever see — was a grey bar and a stack of flat boxes. Somebody who
 * follows a link from an SMS should not feel they have left the company
 * halfway through.
 */
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="relative flex min-h-dvh flex-col overflow-hidden"
      style={{ background: 'var(--bg)' }}
    >
      <div className="aurora" aria-hidden />
      <div className="grid-field" aria-hidden />

      <header className="relative z-10 px-5 py-5">
        <div className="mx-auto flex max-w-lg items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-9 place-items-center rounded-[10px] text-[13px] font-bold italic"
            style={{ background: 'var(--accent-grad)', color: '#04121a' }}
          >
            TE
          </span>
          <div className="leading-none">
            <p className="text-[12.5px] font-semibold italic tracking-[0.08em] uppercase">
              {BRAND.name}
            </p>
            <p
              className="mt-[3px] text-[9px] tracking-[0.2em] uppercase"
              style={{ color: 'var(--text-faint)' }}
            >
              {BRAND.tagline}
            </p>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-lg flex-1 px-4 pt-1 pb-10">
        {children}
      </main>
    </div>
  )
}

/* Where the delivery has got to, as four steps.
 *
 * A customer opening this link is answering one question, and a line of grey
 * 13px text saying "2 stops before yours" is not an answer they can see from
 * arm's length. The rail says where the goods are in their journey before any
 * reading happens, and the headline above it says the rest.
 */
function Journey({ step }: { step: number }) {
  const steps = ['Booked', 'Loaded', 'On the way', 'Delivered']

  return (
    <div className="mt-5 flex items-start">
      {steps.map((label, i) => {
        const done = i <= step
        return (
          <div key={label} className="flex min-w-0 flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              {/* The joining line, half each side, so the dots sit on one rail
                  rather than each in its own cell. */}
              <span
                className="h-[2px] flex-1"
                style={{ background: i === 0 ? 'transparent' : done ? 'var(--accent)' : 'var(--border)' }}
              />
              <span
                className="grid size-3 shrink-0 place-items-center rounded-full"
                style={{
                  background: done ? 'var(--accent)' : 'var(--border-strong)',
                  boxShadow: i === step ? '0 0 0 4px var(--accent-dim)' : undefined,
                }}
              />
              <span
                className="h-[2px] flex-1"
                style={{
                  background:
                    i === steps.length - 1
                      ? 'transparent'
                      : i < step
                        ? 'var(--accent)'
                        : 'var(--border)',
                }}
              />
            </div>
            <span
              className="mt-2 text-center text-[10.5px] leading-tight"
              style={{ color: done ? 'var(--text)' : 'var(--text-faint)' }}
            >
              {label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/* "about 2 hours", not "127 minutes".
 *
 * The estimate is rough, so the wording is rounded to match it. Reporting 127
 * minutes claims a precision the calculation does not have, and a customer
 * reads the odd number as a promise. */
function humanMinutes(total: number): string {
  if (total < 10) return 'a few minutes'
  if (total < 60) return `${Math.round(total / 5) * 5} minutes`

  const hours = Math.floor(total / 60)
  const minutes = Math.round((total % 60) / 15) * 15

  if (hours >= 6) return `${hours} hours`
  if (minutes === 0 || minutes === 60) {
    const h = minutes === 60 ? hours + 1 : hours
    return h === 1 ? 'an hour' : `${h} hours`
  }
  if (minutes === 30) return hours === 1 ? 'an hour and a half' : `${hours}½ hours`
  return `${hours} hour${hours === 1 ? '' : 's'} ${minutes} minutes`
}

/* How stale the position is.
 *
 * Worth saying. A lorry that last reported forty minutes ago is in a dead spot,
 * and a customer watching a marker that has not moved deserves to know that
 * rather than conclude the lorry is parked. */
function sinceText(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 120) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} minutes ago`
  const hours = Math.round(minutes / 60)
  return hours === 1 ? 'an hour ago' : `${hours} hours ago`
}

/* How the delivery went, in the customer's own words.
 *
 * The only account of a delivery that does not come from the people who made
 * it — a driver who is quick and careful and one who leaves cartons in the
 * rain look identical in a box count.
 *
 * Stars are tappable at 44px because this is a phone held at a doorway, and
 * the remark box is offered without being insisted on: "they carried it up
 * without being asked" is worth more to the office than any number, and
 * demanding a score first is how you lose it.
 */
function RateDelivery({
  token,
  data,
}: {
  token: string
  data: { customer_rating: number | null; customer_remarks: string | null }
}) {
  const [rating, setRating] = useState<number | null>(data.customer_rating)
  const [remarks, setRemarks] = useState(data.customer_remarks ?? '')
  const [done, setDone] = useState(!!data.customer_rating || !!data.customer_remarks)
  const [error, setError] = useState<string | null>(null)

  const send = useMutation({
    mutationFn: async () =>
      (await api.post(`/track/${token}/rating`, { rating, remarks: remarks || null })).data,
    onSuccess: () => {
      setDone(true)
      setError(null)
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  return (
    <Card className="px-5 py-4">
      <h2 className="text-[14px] font-semibold">
        {done ? 'Thank you' : 'How was the delivery?'}
      </h2>
      <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
        {done
          ? 'This goes straight to the office.'
          : 'It goes straight to the office, and nobody at the door sees it.'}
      </p>

      <div className="mt-3 flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => {
              setRating(n)
              setDone(false)
            }}
            className="grid size-11 place-items-center rounded-full text-[20px]"
            style={{
              background: (rating ?? 0) >= n ? 'var(--accent-dim)' : 'var(--bg-elevated)',
              color: (rating ?? 0) >= n ? 'var(--accent)' : 'var(--text-faint)',
            }}
            aria-label={`${n} out of 5`}
          >
            {(rating ?? 0) >= n ? '★' : '☆'}
          </button>
        ))}
      </div>

      <div className="mt-3">
        <Textarea
          rows={2}
          placeholder="Anything worth telling the office? (optional)"
          value={remarks}
          onChange={(e) => {
            setRemarks(e.target.value)
            setDone(false)
          }}
        />
      </div>

      <ErrorNote>{error}</ErrorNote>

      <Button
        className="mt-3 w-full"
        variant={done ? 'secondary' : 'primary'}
        disabled={done || (rating === null && !remarks.trim())}
        loading={send.isPending}
        onClick={() => send.mutate()}
      >
        {done ? 'Sent' : 'Send'}
      </Button>
    </Card>
  )
}
