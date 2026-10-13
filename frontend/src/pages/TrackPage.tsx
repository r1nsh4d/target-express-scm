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
import { Button, Card, ErrorNote, Spinner } from '@/components/ui'
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

  return (
    <Shell>
      <div className="space-y-4">
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <span
              className="grid size-10 shrink-0 place-items-center rounded-full"
              style={
                delivered
                  ? { background: 'color-mix(in oklab, var(--success) 16%, transparent)', color: 'var(--success)' }
                  : { background: 'var(--rail)', color: 'var(--rail-text)' }
              }
            >
              {delivered ? <PackageCheck className="size-5" /> : <Truck className="size-5" />}
            </span>
            <div className="min-w-0 flex-1">
              {data.lr_no ? (
                <p
                  className="text-[10px] tracking-[0.14em] uppercase"
                  style={{ color: 'var(--text-faint)' }}
                >
                  LR {data.lr_no}
                  {data.trip_no ? ` · ${data.trip_no}` : ''}
                </p>
              ) : null}
              <p className="text-[17px] font-semibold">{data.consignee_name}</p>
              <p className="mt-0.5 text-[13.5px]" style={{ color: 'var(--text-muted)' }}>
                {delivered
                  ? 'Delivered'
                  : data.dispatched
                    ? data.stops_before === 0
                      ? 'Your delivery is next'
                      : `${data.stops_before} ${data.stops_before === 1 ? 'stop' : 'stops'} before yours`
                    : 'Being prepared at the warehouse'}
              </p>
            </div>
          </div>

          {data.address ? (
            <p
              className="mt-4 flex gap-2 text-[13px] leading-relaxed"
              style={{ color: 'var(--text-muted)' }}
            >
              <MapPin className="mt-0.5 size-3.5 shrink-0" />
              {data.address}
            </p>
          ) : null}

          {delivered && data.receiver_name ? (
            <p className="mt-3 flex items-center gap-2 text-[13px]" style={{ color: 'var(--success)' }}>
              <CheckCircle2 className="size-4" />
              Received by {data.receiver_name}
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

              <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                {data.eta_minutes !== null ? (
                  <span className="text-[15px] font-semibold">
                    Arriving in about {humanMinutes(data.eta_minutes)}
                  </span>
                ) : data.distance_km !== null ? (
                  <span className="text-[15px] font-semibold">Still some way off</span>
                ) : null}
                {data.distance_km !== null ? (
                  <span className="tnum text-[13px]" style={{ color: 'var(--text-muted)' }}>
                    {data.distance_km} km away
                  </span>
                ) : null}
                <span className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  updated {sinceText(data.vehicle_position.recorded_at)}
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
          <div className="px-5 py-4">
            <h2 className="text-[14px] font-semibold">
              Your {data.box_count} {data.box_count === 1 ? 'box' : 'boxes'}
            </h2>
            <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
              Listed against the bill numbers on the cartons.
            </p>
          </div>
          {data.boxes.length ? (
            <ul>
              {data.boxes.map((b) => (
                <li
                  key={`${b.bill_no}-${b.item_no}`}
                  className="flex items-center gap-3 px-5 py-2.5"
                  style={{ borderTop: '1px solid var(--border)' }}
                >
                  <Package
                    className="size-4 shrink-0"
                    style={{ color: b.delivered ? 'var(--success)' : 'var(--text-faint)' }}
                  />
                  <span className="tnum flex-1 text-[13px]">
                    Bill {b.bill_no} · box {b.item_no} of {b.of_total}
                    {b.item_name ? ` · ${b.item_name}` : ''}
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

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="px-5 py-4" style={{ background: 'var(--rail)' }}>
        <div className="mx-auto flex max-w-lg items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-8 place-items-center rounded-[8px] text-[13px] font-bold italic"
            style={{ background: 'var(--rail-text)', color: 'var(--rail)' }}
          >
            TE
          </span>
          <div className="leading-none">
            <p
              className="text-[12.5px] font-semibold italic tracking-[0.08em] uppercase"
              style={{ color: 'var(--rail-text)' }}
            >
              {BRAND.name}
            </p>
            <p
              className="mt-[3px] text-[9px] tracking-[0.2em] uppercase"
              style={{ color: 'var(--rail-faint)' }}
            >
              {BRAND.tagline}
            </p>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-5">{children}</main>
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
