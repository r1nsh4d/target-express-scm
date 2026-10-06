import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CircleSlash,
  Gauge,
  MapPin,
  Route,
  TriangleAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Badge, Card, EmptyState } from '@/components/ui'
import { api } from '@/lib/api'
import { stagger, useCountUp } from '@/lib/motion'

interface OdometerGap {
  registration_no: string
  previous_trip_no: string
  previous_end_km: number
  next_trip_no: string
  next_start_km: number
  gap_km: number
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
}

interface TripRow {
  id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  destination_text: string | null
  point_count: number
  points_delivered: number
  vehicle_no: string | null
  driver_name: string | null
  total_km: number | null
}

interface Summary {
  as_of: string
  trips_today: number
  trips_active: number
  points_delivered_today: number
  points_pending_today: number
  boxes_loaded_today: number
  boxes_delivered_today: number
  uninvoiced_trip_count: number
  uninvoiced_since: string | null
  new_enquiry_count: number
  oldest_new_enquiry_at: string | null
  odometer_gaps: OdometerGap[]
  recent_trips: TripRow[]
}

/* A stat tile, not a chart: these are single headline numbers with no shape to
   plot. Charts arrive with the reports module, where there is a time axis.

   The number counts up when it changes. That is not decoration — a figure that
   MOVED looks different from one that was always there, so a count ticking
   under you while you read is noticed rather than missed. */
function Stat({
  icon,
  label,
  value,
  sub,
  tone,
  live,
  index = 0,
}: {
  icon: ReactNode
  label: string
  value: number
  /** When the headline figure is a pair, like boxes out over boxes in. */
  display?: string
  sub?: string
  tone?: 'accent' | 'warning'
  /** Draws the pulsing dot: something is happening right now. */
  live?: boolean
  index?: number
}) {
  const shown = useCountUp(value)
  const color =
    tone === 'warning' ? 'var(--warning)' : tone === 'accent' ? 'var(--accent)' : 'var(--text)'

  return (
    <Card
      className={clsx('hoverable p-4', live && 'lit')}
      style={stagger(index)}
      data-tx-in
    >
      <div className="flex items-center gap-2" style={{ color: 'var(--text-faint)' }}>
        {icon}
        <span className="text-[11px] font-medium tracking-wide uppercase">{label}</span>
        {live ? <span className="live-dot ml-auto" title="Live" /> : null}
      </div>
      <p className="tnum mt-2.5 text-[26px] leading-none font-semibold tracking-tight" style={{ color }}>
        {shown}
      </p>
      {sub ? (
        <p className="mt-1.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
          {sub}
        </p>
      ) : null}
    </Card>
  )
}

/** Two counts over one another — boxes out of boxes in. Kept separate from Stat
 *  because the comparison IS the information: a single number here would hide
 *  the thing worth seeing. */
function PairStat({
  icon,
  label,
  left,
  right,
  sub,
  tone,
  index = 0,
}: {
  icon: ReactNode
  label: string
  left: number
  right: number
  sub?: string
  tone?: 'warning'
  index?: number
}) {
  const a = useCountUp(left)
  const b = useCountUp(right)
  const color = tone === 'warning' ? 'var(--warning)' : 'var(--text)'

  return (
    <Card className="hoverable p-4" style={stagger(index)}>
      <div className="flex items-center gap-2" style={{ color: 'var(--text-faint)' }}>
        {icon}
        <span className="text-[11px] font-medium tracking-wide uppercase">{label}</span>
      </div>
      <p className="tnum mt-2.5 text-[26px] leading-none font-semibold tracking-tight" style={{ color }}>
        {a}
        <span style={{ color: 'var(--text-faint)' }}> / {b}</span>
      </p>
      {sub ? (
        <p className="mt-1.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
          {sub}
        </p>
      ) : null}
      {/* The bar is the same two numbers again, as a shape. A ratio is read
          faster than a fraction. */}
      <div
        className="mt-3 h-1 overflow-hidden rounded-full"
        style={{ background: 'var(--surface-hover)' }}
        aria-hidden
      >
        <div
          className="h-full rounded-full transition-[width] duration-700"
          style={{
            width: `${b > 0 ? Math.min(100, (a / b) * 100) : 0}%`,
            background: tone === 'warning' ? 'var(--warning)' : 'var(--accent-grad)',
          }}
        />
      </div>
    </Card>
  )
}

/** How long somebody has been waiting for a call, in the words an operator
 *  would use. "3 days ago" reads as a reproach, which is the intent. */
function waitingFor(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000)
  if (hours < 1) return 'just now'
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'info'> = {
  DRAFT: 'neutral',
  PLANNED: 'neutral',
  LOADING: 'info',
  DISPATCHED: 'accent',
  IN_TRANSIT: 'accent',
  COMPLETED: 'success',
  BILLED: 'success',
  SETTLED: 'success',
  CANCELLED: 'warning',
}

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: async () => (await api.get<Summary>('/dashboard/summary')).data,
  })

  /* Skeletons rather than a spinner. The page keeps its shape while the data is
     in flight, so nothing jumps when it lands — and the shapes themselves tell
     you what is coming. */
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-4 w-56" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-[104px]" style={stagger(i)} />
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
          <div className="skeleton h-[320px]" />
          <div className="skeleton h-[200px]" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <Card>
        <EmptyState
          icon={<CircleSlash className="size-7" />}
          title="Could not load the dashboard"
          description="The API is not reachable. Check that the backend is running."
        />
      </Card>
    )
  }

  const unaccounted = data.boxes_loaded_today - data.boxes_delivered_today

  return (
    <div className="space-y-4">
      {/* No page heading: the top bar already says Dashboard and what it is for,
          and two titles stacked on one screen is a title too many. The date is
          the only thing this strip needs to add. */}
      <p className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
        {new Date(data.as_of).toLocaleDateString('en-IN', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        })}
      </p>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          index={0}
          icon={<Route className="size-3.5" />}
          label="Freights today"
          value={data.trips_today}
        />
        <Stat
          index={1}
          icon={<Gauge className="size-3.5" />}
          label="On the road"
          value={data.trips_active}
          tone="accent"
          // The one tile that is about this minute rather than today.
          live={data.trips_active > 0}
          sub={data.trips_active > 0 ? 'Moving right now' : 'Nothing out'}
        />
        <Stat
          index={2}
          icon={<MapPin className="size-3.5" />}
          label="Points delivered"
          value={data.points_delivered_today}
          sub={`${data.points_pending_today} still pending`}
        />
        <PairStat
          index={3}
          icon={<Boxes className="size-3.5" />}
          label="Boxes out / in"
          left={data.boxes_delivered_today}
          right={data.boxes_loaded_today}
          sub={
            unaccounted > 0 ? `${unaccounted} unaccounted` : 'Balanced'
          }
          tone={unaccounted > 0 ? 'warning' : undefined}
        />
      </div>

      {/* Website enquiries nobody has called yet.
          Above the invoicing warning on purpose: an uninvoiced freight is money
          already earned and it will keep. A business that filled in the form on
          Friday evening is deciding today whether to use somebody else, and the
          landing page told them we would call within one working day. */}
      {data.new_enquiry_count > 0 ? (
        <Card
          className="lit flex flex-wrap items-center gap-3 px-4 py-3"
          style={{ background: 'color-mix(in oklab, var(--accent) 7%, var(--surface))' }}
        >
          <span className="live-dot" />
          <p className="text-[13px]">
            <span className="tnum font-semibold">{data.new_enquiry_count}</span>{' '}
            {data.new_enquiry_count === 1 ? 'business has' : 'businesses have'} asked to work
            with Target Express
            {data.oldest_new_enquiry_at
              ? `, the oldest ${waitingFor(data.oldest_new_enquiry_at)}`
              : ''}
            . Nobody has called them yet.
          </p>
          <Link
            to="/enquiries"
            className="ml-auto inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors"
            style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
          >
            Open enquiries
            <ArrowRight className="size-3.5" />
          </Link>
        </Card>
      ) : null}

      {data.uninvoiced_trip_count > 0 ? (
        <Card
          className="flex flex-wrap items-center gap-3 px-4 py-3"
          style={{
            borderColor: 'color-mix(in oklab, var(--warning) 32%, transparent)',
            background: 'color-mix(in oklab, var(--warning) 8%, var(--surface))',
          }}
        >
          <TriangleAlert className="size-4 shrink-0" style={{ color: 'var(--warning)' }} />
          <p className="text-[13px]">
            <span className="tnum font-semibold">{data.uninvoiced_trip_count}</span> completed{' '}
            {data.uninvoiced_trip_count === 1 ? 'freight has' : 'freights have'} not been invoiced
            {data.uninvoiced_since
              ? `, the oldest from ${new Date(data.uninvoiced_since).toLocaleDateString('en-IN')}`
              : ''}
            .
          </p>
        </Card>
      ) : null}

      {/* items-start, so a card with two exceptions in it stays the height of two
          exceptions instead of being stretched to match the table beside it. An
          empty panel full of white space reads as something failing to load. */}
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr] xl:items-start">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3.5">
            <h2 className="text-sm font-semibold">Recent freights</h2>
          </div>
          <div className="overflow-x-auto">
            {data.recent_trips.length === 0 ? (
              <EmptyState
                icon={<Route className="size-7" />}
                title="No freights yet"
                description="Freights will appear here as soon as the first one is created."
              />
            ) : (
              <table className="w-full text-[13px]">
                <thead>
                  <tr
                    className="text-left text-[11px] tracking-wide uppercase"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    <th className="px-4 py-2 font-medium">Trip</th>
                    <th className="px-4 py-2 font-medium">Destination</th>
                    <th className="px-4 py-2 font-medium">Vehicle</th>
                    <th className="px-4 py-2 text-right font-medium">Points</th>
                    <th className="px-4 py-2 text-right font-medium">KM</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_trips.map((trip) => (
                    <tr key={trip.id} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      <td className="px-4 py-2.5">
                        <div className="font-medium">{trip.trip_no}</div>
                        {trip.lr_no ? (
                          <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                            LR {trip.lr_no}
                          </div>
                        ) : null}
                      </td>
                      <td className="max-w-[18rem] truncate px-4 py-2.5">
                        {trip.destination_text ?? '—'}
                      </td>
                      <td className="px-4 py-2.5">
                        <div>{trip.vehicle_no ?? '—'}</div>
                        {trip.driver_name ? (
                          <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                            {trip.driver_name}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {trip.points_delivered}/{trip.point_count}
                      </td>
                      <td className="px-4 py-2.5 text-right">{trip.total_km ?? '—'}</td>
                      <td className="px-4 py-2.5">
                        <Badge tone={STATUS_TONE[trip.status] ?? 'neutral'}>
                          {trip.status.replace('_', ' ')}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="px-4 py-3.5">
            <h2 className="text-sm font-semibold">Odometer exceptions</h2>
            <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
              Where a vehicle's closing reading did not match its next opening reading.
            </p>
          </div>
          {data.odometer_gaps.length === 0 ? (
            <EmptyState
              compact
              title="Every meter joins up"
              description="No gaps in the last 60 days."
            />
          ) : (
            <ul>
              {data.odometer_gaps.map((gap, i) => (
                <li
                  key={`${gap.registration_no}-${i}`}
                  className="flex gap-3 border-t px-4 py-3"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <AlertTriangle
                    className="mt-0.5 size-4 shrink-0"
                    style={{
                      color: gap.severity === 'CRITICAL' ? 'var(--danger)' : 'var(--warning)',
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-medium">{gap.registration_no}</span>
                      <Badge tone={gap.severity === 'CRITICAL' ? 'danger' : 'warning'}>
                        {gap.gap_km < 0 ? 'Reading went backwards' : `${gap.gap_km} km gap`}
                      </Badge>
                    </div>
                    <p className="tnum mt-1 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {gap.previous_trip_no} closed at {gap.previous_end_km.toLocaleString('en-IN')}{' '}
                      · {gap.next_trip_no} opened at {gap.next_start_km.toLocaleString('en-IN')}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
