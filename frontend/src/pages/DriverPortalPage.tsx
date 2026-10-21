import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  Gauge,
  IndianRupee,
  LayoutDashboard,
  LogOut,
  Navigation,
  Package,
  Phone,
  ScanLine,
  Route as RouteIcon,
  Wallet,
} from 'lucide-react'
import { Suspense, lazy, useEffect, useState } from 'react'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Logo,
  Spinner,
} from '@/components/ui'
import { PhotoInput } from '@/components/PhotoInput'
import { ReturnedBoxes } from '@/components/ReturnedBoxes'
import { UnloadingSheet } from '@/components/UnloadingSheet'
import { ScanBoxesSheet } from '@/components/ScanBoxesSheet'
import { multiStopMapsUrl, singleStopMapsUrl } from '@/lib/maps'
import { api, apiErrorMessage } from '@/lib/api'
import { trackLeg } from '@/lib/pings'
import { useAuth } from '@/lib/auth'
import { STATUS_TONE, rupees } from '@/lib/resources'

interface Point {
  id: string
  sequence: number
  consignee_name: string
  address: string | null
  phone: string | null
  latitude: number | null
  longitude: number | null
  floor_number: number
  has_lift: boolean
  loaded_box_count: number
  delivered_box_count: number
  status: string
  unloading_paid: string
}

interface Freight {
  id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  destination_text: string | null
  vehicle_no: string
  leg_id: string
  start_odometer: number | null
  end_odometer: number | null
  total_km: number | null
  origin_name: string | null
  origin_latitude: number | null
  origin_longitude: number | null
  points: Point[]
}

interface FreightRow {
  id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  destination_text: string | null
  vehicle_no: string
  point_count: number
  delivered_point_count: number
  total_km: number | null
  is_open: boolean
}

interface Earnings {
  period_from: string
  period_to: string
  trip_count: number
  by_head: Record<string, string>
  gross: string
  advance_outstanding: string
  net: string
  /* The runs behind the total, newest first. A month's figure is not
     something a driver can check; a run he remembers is. */
  freights: {
    freight_id: string
    trip_no: string
    trip_date: string
    vehicle_no: string | null
    km: number
    amount: string
  }[]
}

type Tab = 'home' | 'freights' | 'earnings'

const RouteMap = lazy(() =>
  import('@/components/RouteMap').then((m) => ({ default: m.RouteMap })),
)

export default function DriverPortalPage() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('home')
  const [openId, setOpenId] = useState<string | null>(null)

  return (
    <div className="min-h-dvh pb-16">
      <header
        className="sticky top-0 z-20 flex items-center justify-between px-4 py-3 backdrop-blur-md"
        style={{ background: 'var(--rail)' }}
      >
        <Logo onDark size={26} />
        <button
          onClick={logout}
          className="rounded-lg p-2"
          style={{ color: 'var(--rail-muted)' }}
          aria-label="Sign out"
        >
          <LogOut className="size-4" />
        </button>
      </header>

      <main className="mx-auto max-w-xl px-4 py-5">
        {openId ? (
          <FreightDetail id={openId} onBack={() => setOpenId(null)} />
        ) : (
          <>
            {/* Two kinds of driver, and only one of them is paid by us.

                A man on a rented lorry runs the trip and is paid by the
                vehicle's owner, so there is no figure of ours to show him.
                The tab is left out entirely rather than opened onto a
                refusal: a locked door he can see is still a question he
                asks, and the answer is always "ask your owner". */}
            <div className="flex gap-1.5">
              {(
                [
                  ['home', 'Home', <LayoutDashboard key="h" className="size-4" />],
                  ['freights', 'Freights', <RouteIcon key="r" className="size-4" />],
                  ...(user?.can_view_earnings
                    ? ([['earnings', 'Earnings', <Wallet key="w" className="size-4" />]] as [
                        Tab,
                        string,
                        React.ReactNode,
                      ][])
                    : []),
                ] as [Tab, string, React.ReactNode][]
              ).map(([key, label, icon]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-control)] py-2.5 text-[13px] font-medium transition-colors"
                  style={
                    tab === key
                      ? { background: 'var(--accent-grad)', color: 'var(--accent-fg)' }
                      : {
                          background: 'var(--surface)',
                          color: 'var(--text-muted)',
                          border: '1px solid var(--border)',
                        }
                  }
                >
                  {icon}
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-5">
              {tab === 'home' ? (
                <DriverHome
                  name={user?.full_name}
                  onOpen={setOpenId}
                  onSeeAll={() => setTab('freights')}
                />
              ) : tab === 'freights' || !user?.can_view_earnings ? (
                /* A tab that is not drawn can still be the one in state —
                   a login whose earnings were switched off while it was
                   open would otherwise sit on a panel with no way back. */
                <FreightList onOpen={setOpenId} />
              ) : (
                <EarningsPanel />
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function FreightList({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['driver-freights'],
    queryFn: async () => (await api.get<FreightRow[]>('/driver/freights')).data,
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="size-5" />
      </div>
    )
  }

  const rows = data ?? []
  const open = rows.filter((r) => r.is_open)
  const past = rows.filter((r) => !r.is_open)

  if (!rows.length) {
    return (
      <Card>
        <EmptyState
          icon={<Package className="size-7" />}
          title="No freights assigned"
          description="When the office puts you on a freight it will appear here."
        />
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {open.length ? (
        <section>
          <h2 className="eyebrow mb-2 px-1">Running now</h2>
          <div className="space-y-2.5">
            {open.map((r) => (
              <FreightRowCard key={r.id} row={r} onOpen={onOpen} highlight />
            ))}
          </div>
        </section>
      ) : null}

      {past.length ? (
        <section>
          <h2 className="eyebrow mb-2 px-1">Previous runs</h2>
          <div className="space-y-2.5">
            {past.map((r) => (
              <FreightRowCard key={r.id} row={r} onOpen={onOpen} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

function FreightRowCard({
  row,
  onOpen,
  highlight,
}: {
  row: FreightRow
  onOpen: (id: string) => void
  highlight?: boolean
}) {
  return (
    <button onClick={() => onOpen(row.id)} className="w-full text-left">
      <Card
        className="flex items-center gap-3 p-4"
        style={highlight ? { outline: '1.5px solid var(--accent)' } : undefined}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-semibold">{row.trip_no}</span>
            <Badge tone={STATUS_TONE[row.status] ?? 'neutral'}>
              {row.status.replace('_', ' ')}
            </Badge>
          </div>
          <p className="mt-1 truncate text-[13px]" style={{ color: 'var(--text-muted)' }}>
            {row.destination_text ?? '—'}
          </p>
          <p className="tnum mt-1 text-[12px]" style={{ color: 'var(--text-faint)' }}>
            {row.trip_date} · {row.vehicle_no} · {row.delivered_point_count}/{row.point_count} points
            {row.total_km ? ` · ${row.total_km} km` : ''}
          </p>
        </div>
        <ChevronRight className="size-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
      </Card>
    </button>
  )
}

/* -------------------------------------------------------------------------- */

function FreightDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const { data: trip, isLoading } = useQuery({
    queryKey: ['driver-freight', id],
    queryFn: async () => (await api.get<Freight>(`/driver/freights/${id}`)).data,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['driver-freight', id] })
    queryClient.invalidateQueries({ queryKey: ['driver-freights'] })
  }

  /* Send the lorry's position while the trip is open.
     Starts when the opening odometer is in and stops at the closing one, so a
     phone left on in a yard overnight is not still reporting. The fixes are
     buffered on the phone and flushed when there is a signal — a lorry on the
     Kasaragod road loses it for twenty minutes at a time, and those are the
     interesting minutes. */
  const legId = trip?.leg_id
  const running = !!legId && trip?.start_odometer !== null && trip?.end_odometer === null
  useEffect(() => {
    if (!running || !legId) return
    return trackLeg(legId)
  }, [running, legId])

  const start = useMutation({
    mutationFn: ({ reading, photo }: { reading: number; photo: string | null }) =>
      api.post(`/driver/legs/${trip!.leg_id}/start`, { reading, photo_url: photo }),
    onSuccess: refresh,
    onError: (e) => setError(apiErrorMessage(e)),
  })
  const close = useMutation({
    mutationFn: ({ reading, photo }: { reading: number; photo: string | null }) =>
      api.post(`/driver/legs/${trip!.leg_id}/close`, { reading, photo_url: photo }),
    onSuccess: refresh,
    onError: (e) => setError(apiErrorMessage(e)),
  })
  const deliver = useMutation({
    mutationFn: ({
      pointId,
      boxes,
      unloading,
      photo,
      receiver,
    }: {
      pointId: string
      boxes: number
      unloading: string
      photo: string | null
      receiver: string
    }) =>
      api.post(`/driver/points/${pointId}/deliver`, {
        delivered_box_count: boxes,
        unloading_paid: unloading || '0',
        delivery_photo_url: photo,
        receiver_name: receiver || null,
      }),
    onSuccess: refresh,
    onError: (e) => setError(apiErrorMessage(e)),
  })

  if (isLoading || !trip) {
    return (
      <div className="flex justify-center py-20">
        <Spinner className="size-6" />
      </div>
    )
  }

  const pending = trip.points.filter((p) => p.status !== 'DELIVERED' && p.status !== 'PART_DELIVERED')
  const routeUrl = multiStopMapsUrl(
    pending.length ? pending : trip.points,
    trip.origin_latitude != null
      ? { latitude: trip.origin_latitude, longitude: trip.origin_longitude }
      : null,
  )

  return (
    <div className="space-y-4">
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-[13px]"
        style={{ color: 'var(--text-muted)' }}
      >
        <ArrowLeft className="size-4" />
        All freights
      </button>

      <Card className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[17px] font-semibold">{trip.trip_no}</p>
            <p className="mt-0.5 text-[13px]" style={{ color: 'var(--text-muted)' }}>
              {trip.vehicle_no}
              {trip.lr_no ? ` · LR ${trip.lr_no}` : ''} · {trip.trip_date}
            </p>
          </div>
          <Badge tone={STATUS_TONE[trip.status] ?? 'neutral'}>
            {trip.status.replace('_', ' ')}
          </Badge>
        </div>

        {trip.destination_text ? (
          <p className="mt-3 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            {trip.destination_text}
          </p>
        ) : null}

        {/* The shape of the day.
            Google Maps is still the right thing for actually driving — it
            knows the roads and this does not. What was missing is how many
            stops, in what order, how far apart and which are done: a list of
            six towns does not tell a driver he is about to double back. The
            numbers are the delivery order and the grey ones are finished. */}
        <div className="mt-4">
          <Suspense fallback={<div className="skeleton" style={{ height: 240 }} />}>
            <RouteMap
              stops={trip.points}
              origin={
                trip.origin_latitude != null
                  ? { latitude: trip.origin_latitude, longitude: trip.origin_longitude }
                  : null
              }
            />
          </Suspense>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-3 text-center">
          {[
            [String(trip.points.length), 'points'],
            [
              String(trip.points.reduce((n, p) => n + p.loaded_box_count, 0)),
              'boxes loaded',
            ],
            [trip.total_km ? `${trip.total_km}` : '—', 'km'],
          ].map(([v, l]) => (
            <div key={l} className="inset px-2 py-3">
              <p className="tnum text-[17px] font-semibold">{v}</p>
              <p className="mt-0.5 text-[11px]" style={{ color: 'var(--text-faint)' }}>
                {l}
              </p>
            </div>
          ))}
        </div>

        {routeUrl ? (
          <a href={routeUrl} target="_blank" rel="noreferrer" className="mt-4 block">
            <Button size="lg" className="w-full" icon={<Navigation className="size-4" />}>
              Open the whole route
            </Button>
          </a>
        ) : null}
        <p className="mt-2 text-center text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
          Every remaining stop, in order, as one Google Maps route.
        </p>
      </Card>

      <TripEarnings freightId={id} />

      <ErrorNote>{error}</ErrorNote>

      {trip.start_odometer === null ? (
        <OdometerCard
          title="Start the freight"
          hint="Enter the meter reading before leaving the godown."
          cta="Start freight"
          busy={start.isPending}
          onSubmit={(r, photo) => start.mutate({ reading: r, photo })}
        />
      ) : (
        <Card className="flex items-center gap-3 px-4 py-3">
          <Gauge className="size-4" style={{ color: 'var(--text-muted)' }} />
          <span className="text-[13px]">
            Opening reading{' '}
            <span className="tnum font-semibold">
              {trip.start_odometer.toLocaleString('en-IN')}
            </span>
          </span>
        </Card>
      )}

      <div className="space-y-2.5">
        <h2 className="eyebrow px-1">{trip.points.length} delivery points</h2>
        {trip.points.map((p) => (
          <PointCard
            key={p.id}
            point={p}
            disabled={trip.start_odometer === null}
            busy={deliver.isPending}
            onDeliver={(boxes, unloading, photo, receiver) =>
              deliver.mutate({ pointId: p.id, boxes, unloading, photo, receiver })
            }
          />
        ))}
      </div>

      {/* Before the odometer, deliberately. Closing the trip is the last
          action, and anything still on the vehicle has to be accounted for
          before it — otherwise it is counted the next morning, by which time
          it has had a night to be misremembered. */}
      {trip.start_odometer !== null && trip.end_odometer === null ? (
        <ReturnedBoxes freightId={trip.id} />
      ) : null}

      {trip.start_odometer !== null && trip.end_odometer === null ? (
        <OdometerCard
          title="Close the freight"
          hint="Enter the meter reading after returning to the godown."
          cta="Close freight"
          busy={close.isPending}
          onSubmit={(r, photo) => close.mutate({ reading: r, photo })}
        />
      ) : null}

      {trip.end_odometer !== null ? (
        <Card className="flex items-center gap-3 px-4 py-3">
          <CheckCircle2 className="size-4" style={{ color: 'var(--success)' }} />
          <span className="text-[13px]">
            Closed at{' '}
            <span className="tnum font-semibold">
              {trip.end_odometer.toLocaleString('en-IN')}
            </span>
          </span>
        </Card>
      ) : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */

/* What this run pays him, and how it was worked out.
 *
 * A month's total tells a driver nothing he can check, and "₹475 earned this
 * month" on the home screen is exactly the figure that starts an argument
 * nobody can settle. This is the one he can check: his rate, the distance he
 * actually drove, what the unloading came to, and the sum. If it is wrong he
 * can say which line is wrong.
 *
 * His side only. Nothing here says what the vendor was charged — that is not
 * his business, and putting it in front of him invites the one conversation
 * a lorry bay does not need.
 *
 * It says plainly whether the figures are firm. Before the trip closes they
 * move with the odometer, and a driver who sees ₹250 on Tuesday and ₹410 on
 * Wednesday needs to have been told why.
 */
function TripEarnings({ freightId }: { freightId: string }) {
  const { data, isError } = useQuery({
    queryKey: ['driver-trip-earnings', freightId],
    queryFn: async () =>
      (
        await api.get<{
          km: number
          points: number
          lines: { label: string; amount: string; working: string }[]
          total: string
          is_final: boolean
        }>(`/driver/freights/${freightId}/earnings`)
      ).data,
    // A 403 is the honest answer for a driver on a rented lorry: he is paid
    // by the vehicle's owner, not by Target Express. Nothing is shown, rather
    // than a zero that reads as a missing payment.
    retry: false,
  })

  if (isError || !data || !data.lines.length) return null

  return (
    <Card className="p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[14px] font-semibold">What you earn on this run</h3>
        <span className="text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
          {data.is_final ? 'final' : 'so far'}
        </span>
      </div>

      <div className="mt-3 space-y-2">
        {data.lines.map((line, i) => (
          <div key={`${line.label}-${i}`} className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13.5px]">{line.label}</p>
              {line.working ? (
                <p className="tnum mt-0.5 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
                  {line.working}
                </p>
              ) : null}
            </div>
            <span className="tnum shrink-0 text-[14px] font-medium">{rupees(line.amount)}</span>
          </div>
        ))}
      </div>

      <div
        className="mt-3 flex items-baseline justify-between border-t pt-3"
        style={{ borderColor: 'var(--border)' }}
      >
        <span className="text-[14px] font-semibold">
          Total for this freight
          <span className="ml-2 text-[12px] font-normal" style={{ color: 'var(--text-muted)' }}>
            {data.km} km
          </span>
        </span>
        <span className="tnum text-[20px] font-semibold" style={{ color: 'var(--success)' }}>
          {rupees(data.total)}
        </span>
      </div>

      {!data.is_final ? (
        <p className="mt-2 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
          This moves until the trip is closed — the distance is not final until you put in the
          closing meter reading.
        </p>
      ) : null}
    </Card>
  )
}

function PointCard({
  point,
  disabled,
  busy,
  onDeliver,
}: {
  point: Point
  disabled: boolean
  busy: boolean
  onDeliver: (boxes: number, unloading: string, photo: string | null, receiver: string) => void
}) {
  const done = point.status === 'DELIVERED' || point.status === 'PART_DELIVERED'
  const [boxes, setBoxes] = useState(String(point.loaded_box_count))
  const [unloading, setUnloading] = useState('')
  const [photo, setPhoto] = useState<string | null>(null)
  const [receiver, setReceiver] = useState('')
  const [open, setOpen] = useState(false)
  const [scanning, setScanning] = useState(false)

  const mapsHref = singleStopMapsUrl(point)

  return (
    <Card className="overflow-hidden">
      <div className="flex gap-3 p-4">
        <div
          className="tnum grid size-8 shrink-0 place-items-center rounded-[10px] text-[13px] font-semibold"
          style={
            done
              ? { background: 'color-mix(in oklab, var(--success) 18%, transparent)', color: 'var(--success)' }
              : { background: 'var(--rail)', color: 'var(--rail-text)' }
          }
        >
          {point.sequence}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[14px] font-medium">{point.consignee_name}</p>
            {done ? <Badge tone="success">Delivered</Badge> : null}
            {point.floor_number > 0 ? (
              <Badge tone="info">
                Floor {point.floor_number}
                {point.has_lift ? ' · lift' : ''}
              </Badge>
            ) : null}
          </div>

          {point.address ? (
            <p className="mt-1 text-[12.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              {point.address}
            </p>
          ) : null}

          <p className="tnum mt-1.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
            <Package className="mr-1 inline size-3" />
            {done
              ? `${point.delivered_box_count} of ${point.loaded_box_count} boxes handed over`
              : `${point.loaded_box_count} boxes`}
            {Number(point.unloading_paid) > 0 ? ` · ${rupees(point.unloading_paid)} unloading` : ''}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {mapsHref ? (
              <a href={mapsHref} target="_blank" rel="noreferrer">
                <Button variant="secondary" size="sm" icon={<Navigation className="size-3.5" />}>
                  Navigate
                </Button>
              </a>
            ) : (
              <Button variant="secondary" size="sm" disabled>
                No location
              </Button>
            )}
            {point.phone ? (
              <a href={`tel:${point.phone}`}>
                <Button variant="secondary" size="sm" icon={<Phone className="size-3.5" />}>
                  Call
                </Button>
              </a>
            ) : null}
            {!done ? (
              <>
                {/* Scan first, then confirm. Deliberately the primary action:
                    the count the driver types is a claim, the scans are proof,
                    and the one that catches a wrong carton is the scan. */}
                <Button
                  size="sm"
                  disabled={disabled}
                  icon={<ScanLine className="size-3.5" />}
                  onClick={() => setScanning(true)}
                >
                  Scan boxes
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={disabled}
                  onClick={() => setOpen((o) => !o)}
                >
                  Mark delivered
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </div>

      <ScanBoxesSheet
        open={scanning}
        point={point}
        onClose={() => setScanning(false)}
        onAllScanned={(count) => {
          // Every carton accounted for, so the count is already known. Open the
          // delivery form with it filled in rather than asking him to retype a
          // number the phone just proved.
          setBoxes(String(count))
          setScanning(false)
          setOpen(true)
        }}
      />

      {open && !done ? (
        <form
          className="space-y-3 px-4 pb-4"
          onSubmit={(e) => {
            e.preventDefault()
            onDeliver(Number(boxes), unloading, photo, receiver)
            setOpen(false)
          }}
        >
          <div className="groove" />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Boxes handed over">
              <Input
                className="tnum"
                type="number"
                inputMode="numeric"
                min={0}
                max={point.loaded_box_count}
                value={boxes}
                onChange={(e) => setBoxes(e.target.value)}
              />
            </Field>
            <Field label="Unloading cash paid out" hint="What you handed the labourers">
              <div className="relative">
                <IndianRupee
                  className="pointer-events-none absolute top-1/2 left-3.5 size-3.5 -translate-y-1/2"
                  style={{ color: 'var(--text-faint)' }}
                />
                <Input
                  className="tnum pl-9"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  placeholder="0"
                  value={unloading}
                  onChange={(e) => setUnloading(e.target.value)}
                />
              </div>
            </Field>
          </div>

          {/* The unloading charge sheet, for vendors who pay per article.
              Separate from the cash box above, and both are real: the cash is
              what left his pocket, this is what the work was worth. On a
              spare-parts run the component renders nothing at all, because
              nothing is charged and a list of articles would be a question
              with no answer. */}
          <div className="groove my-1" />
          <UnloadingSheet pointId={point.id} />
          <div className="groove my-1" />
          <Field label="Received by" hint="Name of the person who took the goods">
            <Input value={receiver} onChange={(e) => setReceiver(e.target.value)} />
          </Field>

          <div>
            <p className="mb-2 text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
              Photo of the unloaded goods
            </p>
            <PhotoInput kind="delivery" value={photo} onChange={setPhoto} label="Take photo" />
          </div>

          <Button type="submit" size="lg" className="w-full" loading={busy}>
            Confirm delivery
          </Button>
        </form>
      ) : null}
    </Card>
  )
}

/* -------------------------------------------------------------------------- */

function OdometerCard({
  title,
  hint,
  cta,
  busy,
  onSubmit,
}: {
  title: string
  hint: string
  cta: string
  busy: boolean
  onSubmit: (reading: number, photo: string | null) => void
}) {
  const [value, setValue] = useState('')
  const [photo, setPhoto] = useState<string | null>(null)
  return (
    <Card className="p-4">
      <h3 className="text-[14px] font-semibold">{title}</h3>
      <form
        className="mt-3 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          const reading = Number(value)
          if (Number.isFinite(reading) && reading > 0) onSubmit(reading, photo)
        }}
      >
        <Field label="Odometer reading" hint={hint}>
          <Input
            type="number"
            inputMode="numeric"
            placeholder="e.g. 189143"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="tnum h-12 text-[16px]"
            required
          />
        </Field>
        <div>
          <p className="mb-2 text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
            Photo of the meter
          </p>
          <PhotoInput kind="odometer" value={photo} onChange={setPhoto} label="Photograph the meter" />
        </div>

        <Button type="submit" size="lg" className="w-full" loading={busy}>
          {cta}
        </Button>
      </form>
    </Card>
  )
}

/* -------------------------------------------------------------------------- */

function EarningsPanel() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['driver-earnings'],
    queryFn: async () => (await api.get<Earnings>('/driver/earnings')).data,
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="size-5" />
      </div>
    )
  }

  if (isError) {
    return (
      <Card>
        <EmptyState
          icon={<Wallet className="size-7" />}
          title="Earnings are not shown on this login"
          description={apiErrorMessage(
            error,
            'Your account does not show earnings. Ask the office if you think that is wrong.',
          )}
        />
      </Card>
    )
  }

  const heads = Object.entries(data?.by_head ?? {}).filter(([, v]) => Number(v) !== 0)

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <p className="eyebrow">This month</p>
        <p className="tnum mt-2 text-[30px] leading-none font-semibold">{rupees(data?.net)}</p>
        <p className="mt-2 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
          {data?.trip_count ?? 0} freight{(data?.trip_count ?? 0) === 1 ? '' : 's'} ·{' '}
          {data?.period_from} to {data?.period_to}
        </p>
      </Card>

      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h3 className="text-[14px] font-semibold">How it adds up</h3>
        </div>
        {heads.length ? (
          heads.map(([head, value]) => (
            <div key={head} className="flex items-center justify-between px-4 py-2.5">
              <span className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
                {head.replaceAll('_', ' ').toLowerCase()}
              </span>
              <span className="tnum text-[13.5px]">{rupees(value)}</span>
            </div>
          ))
        ) : (
          <EmptyState title="Nothing yet this month" description="Completed freights show up here." />
        )}

        <div className="px-4">
          <div className="groove" />
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
            Gross
          </span>
          <span className="tnum text-[13.5px]">{rupees(data?.gross)}</span>
        </div>
        {Number(data?.advance_outstanding ?? 0) > 0 ? (
          <div className="flex items-center justify-between px-4 pb-3">
            <span className="text-[13px]" style={{ color: 'var(--warning)' }}>
              Advance to recover
            </span>
            <span className="tnum text-[13.5px]" style={{ color: 'var(--warning)' }}>
              −{rupees(data?.advance_outstanding)}
            </span>
          </div>
        ) : null}
      </Card>

      {/* The runs behind the total.

          A month's figure and a split by head are both true and neither is
          checkable: he cannot tell whether ₹2,975 is right, only whether it
          feels low. What he CAN check is "the Kasaragod run on the 12th paid
          420", because he remembers that run. Without this the number is
          something to accept or argue with, and there is no third option. */}
      {data?.freights?.length ? (
        <Card className="overflow-hidden">
          <div className="px-4 py-3.5">
            <h3 className="text-[14px] font-semibold">Run by run</h3>
            <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
              Tap one to see how it was worked out.
            </p>
          </div>
          {data.freights.map((f) => (
            <div
              key={f.freight_id}
              className="flex items-center justify-between gap-3 border-t px-4 py-3"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0">
                <p className="tnum text-[13.5px] font-medium">{f.trip_no}</p>
                <p className="tnum text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  {new Date(f.trip_date).toLocaleDateString('en-IN')}
                  {f.vehicle_no ? ` · ${f.vehicle_no}` : ''}
                  {f.km ? ` · ${f.km} km` : ''}
                </p>
              </div>
              <span className="tnum shrink-0 text-[14px] font-semibold">
                {rupees(f.amount)}
              </span>
            </div>
          ))}
        </Card>
      ) : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* The driver's home screen                                                   */
/* -------------------------------------------------------------------------- */

/** What a driver opens the app to find out.
 *
 * Built for a phone held one-handed in a cab, often before dawn. The order is
 * the order the questions are actually asked:
 *
 *   1. Am I on a run right now, and where am I in it?   — the live card
 *   2. What have I earned this month?                   — the number
 *   3. How much have I run?                             — trips and kilometres
 *
 * Earnings are shown only when the office has allowed it on this login. A
 * driver on a rented vehicle runs trips but is not paid by Target Express, and
 * showing him a zero would be worse than showing him nothing — so that whole
 * block disappears rather than reading empty.
 */
function DriverHome({
  name,
  onOpen,
  onSeeAll,
}: {
  name: string | undefined
  onOpen: (id: string) => void
  onSeeAll: () => void
}) {
  const freights = useQuery({
    queryKey: ['driver-freights', 'all'],
    queryFn: async () => (await api.get<FreightRow[]>('/driver/freights')).data,
  })

  const earnings = useQuery({
    queryKey: ['driver-earnings'],
    queryFn: async () => (await api.get<Earnings>('/driver/earnings')).data,
    retry: false,
  })

  const all = freights.data ?? []
  const running = all.filter((f) => f.is_open)
  const done = all.filter((f) => !f.is_open)

  // Lifetime, from what the server already returns. Not a new endpoint for a
  // number this screen can add up itself.
  const totalKm = done.reduce((sum, f) => sum + (f.total_km ?? 0), 0)
  const totalPoints = done.reduce((sum, f) => sum + f.delivered_point_count, 0)

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[13px]" style={{ color: 'var(--text-faint)' }}>
          {greeting}
        </p>
        <h1 className="text-[22px] leading-tight font-semibold">{name ?? 'Driver'}</h1>
      </div>

      {/* The live run, if there is one. Biggest thing on the screen, because at
          5am it is the only thing he needs. */}
      {freights.isLoading ? (
        <div className="skeleton h-28" />
      ) : running.length ? (
        running.map((f) => (
          <button
            key={f.id}
            onClick={() => onOpen(f.id)}
            className="lit w-full overflow-hidden rounded-[var(--radius-card)] p-4 text-left"
            style={{ background: 'var(--surface)', boxShadow: 'var(--lift)' }}
          >
            <div className="flex items-center gap-2">
              <span className="live-dot" />
              <span className="eyebrow" style={{ color: 'var(--accent)' }}>
                Running now
              </span>
            </div>
            <p className="mt-2.5 text-[17px] font-semibold">
              {f.destination_text ?? f.trip_no}
            </p>
            <p className="mt-1 text-[13px]" style={{ color: 'var(--text-muted)' }}>
              {f.vehicle_no} · {f.delivered_point_count} of {f.point_count} points delivered
            </p>

            {/* A bar, because a fraction read at a glance beats two numbers. */}
            <div
              className="mt-3 h-1.5 overflow-hidden rounded-full"
              style={{ background: 'var(--surface-hover)' }}
              aria-hidden
            >
              <div
                className="h-full rounded-full transition-[width] duration-700"
                style={{
                  width: `${f.point_count ? (f.delivered_point_count / f.point_count) * 100 : 0}%`,
                  background: 'var(--accent-grad)',
                }}
              />
            </div>

            <span
              className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium"
              style={{ color: 'var(--accent)' }}
            >
              Open the run
              <ChevronRight className="size-3.5" />
            </span>
          </button>
        ))
      ) : (
        <Card className="p-5 text-center">
          <p className="text-[14px] font-medium">No run assigned</p>
          <p className="mt-1 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            The office will assign your next freight here.
          </p>
        </Card>
      )}

      {/* Earnings, only if this login is allowed to see them. */}
      {earnings.isSuccess ? (
        <Card className="p-5">
          <p className="eyebrow">Earned this month</p>
          <p className="tnum mt-2 text-[32px] leading-none font-semibold">
            {rupees(earnings.data?.net)}
          </p>
          <p className="mt-2 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            {earnings.data?.trip_count ?? 0} freight
            {(earnings.data?.trip_count ?? 0) === 1 ? '' : 's'} this month
          </p>
          {Number(earnings.data?.advance_outstanding ?? 0) > 0 ? (
            <p className="mt-2 text-[12.5px]" style={{ color: 'var(--warning)' }}>
              {rupees(earnings.data?.advance_outstanding)} advance still to recover
            </p>
          ) : null}
        </Card>
      ) : null}

      <div className="grid grid-cols-3 gap-2.5">
        <MiniStat label="Runs done" value={String(done.length)} />
        <MiniStat label="Points" value={String(totalPoints)} />
        <MiniStat label="Kilometres" value={totalKm.toLocaleString('en-IN')} />
      </div>

      {done.length ? (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3.5">
            <h2 className="text-[14px] font-semibold">Recent runs</h2>
            <button
              onClick={onSeeAll}
              className="text-[12.5px] font-medium"
              style={{ color: 'var(--accent)' }}
            >
              See all
            </button>
          </div>
          {done.slice(0, 3).map((f) => (
            <button
              key={f.id}
              onClick={() => onOpen(f.id)}
              className="flex w-full items-center gap-3 border-t px-4 py-3 text-left"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium">
                  {f.destination_text ?? f.trip_no}
                </p>
                <p className="tnum text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  {new Date(f.trip_date).toLocaleDateString('en-IN')} · {f.vehicle_no}
                  {f.total_km ? ` · ${f.total_km} km` : ''}
                </p>
              </div>
              <ChevronRight className="size-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
            </button>
          ))}
        </Card>
      ) : null}

      <DriverHelp />
    </div>
  )
}

/* How the run works, on the phone that runs it.
 *
 * The written guide is an office screen and a driver cannot open it — he is
 * not on those routes — so every word of guidance aimed at him reached
 * everybody except him. He was taught once, standing in a godown, by somebody
 * with their own phone out.
 *
 * Closed by default, because a man who has done forty runs does not need it
 * and should not have to scroll past it. Eight lines when opened, in the order
 * he does them, with the two things that catch people out said plainly:
 * nothing starts without the opening meter reading, and nothing is ever
 * forced — a carton that will not scan is still delivered.
 */
function DriverHelp() {
  const [open, setOpen] = useState(false)

  const steps = [
    'Before you leave: enter the meter reading and take a photo of it. The run will not start without it.',
    'At each stop: scan the cartons. If one belongs to a different customer the phone stops you and tells you whose it is.',
    'Hand them over, type who received them, and take a photo.',
    'Tick what you carried inside — how many chairs, which floor. That is what you are paid for and what the shop signs for.',
    'Porter money is a separate box from unloading. Keep them apart or the amounts cannot be explained later.',
    'Paid a toll or bought diesel? Add it with a photo of the receipt before you forget.',
    'Anything coming back: scan it at the godown before the lorry is emptied.',
    'Last thing: the closing meter reading and its photo. That finishes the run.',
  ]

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left"
      >
        <span
          className="grid size-8 shrink-0 place-items-center rounded-full"
          style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
        >
          <HelpCircle className="size-4" />
        </span>
        <span className="flex-1 text-[14px] font-medium">How a run works</span>
        <ChevronRight
          className="size-4 shrink-0 transition-transform"
          style={{
            color: 'var(--text-faint)',
            transform: open ? 'rotate(90deg)' : undefined,
          }}
          aria-hidden
        />
      </button>

      {open ? (
        <div className="border-t px-4 py-3.5" style={{ borderColor: 'var(--border)' }}>
          <ol className="space-y-2.5">
            {steps.map((t, i) => (
              <li key={t} className="flex gap-3 text-[13.5px] leading-relaxed">
                <span
                  className="tnum grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                >
                  {i + 1}
                </span>
                <span>{t}</span>
              </li>
            ))}
          </ol>

          <p
            className="mt-3 rounded-[10px] px-3 py-2.5 text-[12.5px] leading-relaxed"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
          >
            Nothing here is forced. If a carton will not scan, type the count instead — the
            delivery still goes through. If you are out of signal, carry on: the phone keeps
            what you entered and sends it when the signal comes back.
          </p>
        </div>
      ) : null}
    </Card>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-3 text-center">
      <p className="tnum text-[19px] leading-none font-semibold">{value}</p>
      <p className="eyebrow mt-1.5">{label}</p>
    </Card>
  )
}
