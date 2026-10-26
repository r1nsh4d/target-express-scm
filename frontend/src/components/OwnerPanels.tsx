/* What a hired lorry earned, for the man who owns it.
 *
 * A rented vehicle settles to its OWNER, who pays his own driver. So the
 * money question is his, and until now he answered it by ringing the office
 * at the end of the month.
 *
 * These are panels rather than a page because they are read in two places by
 * two different people who are often the same person. A man who only owns
 * lorries opens them on their own; a man who owns one and drives it himself
 * opens them as a tab inside the driver app, between runs, on the same phone
 * he just closed the odometer on.
 *
 * NOTHING HERE SAYS WHAT THE VENDOR WAS CHARGED. The gap between what Godrej
 * pays and what he is paid is Target Express's margin, and handing a
 * contractor both halves of it is handing him a negotiation.
 */

import { useQuery } from '@tanstack/react-query'
import { HandCoins, Route, Truck, UserRound, Wallet } from 'lucide-react'

import { Badge, Card, EmptyState, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { STATUS_TONE, rupees } from '@/lib/resources'

interface OwnerHome {
  owner_name: string
  vehicles: { id: string; registration_no: string; last_closing_km: number | null; is_active: boolean }[]
  /* His own men. One owner with four lorries and three drivers is an
     ordinary arrangement, and until a driver knew whose he was there was no
     way to ask the question. */
  drivers: { id: string; name: string; phone: string; has_login: boolean }[]
  trips_this_month: number
  km_this_month: number
  earned_this_month: string
  unsettled: string
  advances_outstanding: string
}

interface OwnerRun {
  freight_id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  vehicle_no: string
  driver_name: string | null
  destination_text: string | null
  points: number
  km: number
  earned: string
  settlement_no: string | null
}

interface OwnerSettlement {
  id: string
  settlement_no: string
  settlement_date: string
  period_from: string
  period_to: string
  trip_count: number
  total_km: number
  gross_amount: string
  advance_recovered: string
  net_payable: string
  status: string
}

interface OwnerAdvance {
  id: string
  advance_date: string
  amount: string
  recovered_amount: string
  outstanding: string
  reason: string | null
  status: string
}

export function OwnerPanels() {
  const home = useQuery({
    queryKey: ['owner-home'],
    queryFn: async () => (await api.get<OwnerHome>('/owner/home')).data,
    retry: false,
  })
  const runs = useQuery({
    queryKey: ['owner-runs'],
    queryFn: async () => (await api.get<OwnerRun[]>('/owner/runs')).data,
    retry: false,
  })
  const settlements = useQuery({
    queryKey: ['owner-settlements'],
    queryFn: async () => (await api.get<OwnerSettlement[]>('/owner/settlements')).data,
    retry: false,
  })
  const advances = useQuery({
    queryKey: ['owner-advances'],
    queryFn: async () => (await api.get<OwnerAdvance[]>('/owner/advances')).data,
    retry: false,
  })

  if (home.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="size-5" />
      </div>
    )
  }
  if (!home.data) return null

  const h = home.data

  return (
    <div className="space-y-4">
      {/* The figure he is actually ringing about, first and largest. A
          month's earnings is history; what has not been settled is the
          conversation. */}
      <Card className="p-5">
        <p className="eyebrow">Not settled yet</p>
        <p
          className="tnum mt-2 text-[30px] leading-none font-semibold"
          style={{ color: Number(h.unsettled) > 0 ? 'var(--accent)' : undefined }}
        >
          {rupees(h.unsettled)}
        </p>
        <p className="mt-2 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
          {rupees(h.earned_this_month)} earned this month over {h.trips_this_month}{' '}
          {h.trips_this_month === 1 ? 'run' : 'runs'} · {h.km_this_month.toLocaleString('en-IN')} km
        </p>
        {Number(h.advances_outstanding) > 0 ? (
          <p className="mt-2 text-[12.5px]" style={{ color: 'var(--warning)' }}>
            {rupees(h.advances_outstanding)} of advances still to come off a settlement.
          </p>
        ) : null}
      </Card>

      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold">
            <Truck className="size-4" style={{ color: 'var(--text-faint)' }} />
            {h.vehicles.length === 1 ? 'Your lorry' : 'Your lorries'}
          </h3>
        </div>
        {h.vehicles.map((v) => (
          <div
            key={v.id}
            className="flex items-center justify-between gap-3 border-t px-4 py-2.5"
            style={{ borderColor: 'var(--border)' }}
          >
            <span className="tnum text-[13.5px] font-medium">{v.registration_no}</span>
            <span className="tnum text-[12px]" style={{ color: 'var(--text-faint)' }}>
              {v.last_closing_km != null
                ? `${v.last_closing_km.toLocaleString('en-IN')} km`
                : 'no reading yet'}
            </span>
          </div>
        ))}
      </Card>

      {/* His men.
          He pays them himself out of what Target Express pays for the lorry,
          so there are no amounts here — the one thing he can act on is
          whether a man can run a trip from his own phone, which is a
          question for the office and not something to fix on this screen. */}
      {h.drivers.length ? (
        <Card className="overflow-hidden">
          <div className="px-4 py-3.5">
            <h3 className="flex items-center gap-2 text-[14px] font-semibold">
              <UserRound className="size-4" style={{ color: 'var(--text-faint)' }} />
              {h.drivers.length === 1 ? 'Your driver' : 'Your drivers'}
            </h3>
          </div>
          {h.drivers.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between gap-3 border-t px-4 py-2.5"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0">
                <p className="truncate text-[13.5px] font-medium">{d.name}</p>
                <p className="tnum text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  {d.phone}
                </p>
              </div>
              <Badge tone={d.has_login ? 'success' : 'warning'}>
                {d.has_login ? 'has a login' : 'no login yet'}
              </Badge>
            </div>
          ))}
          <p
            className="border-t px-4 py-2.5 text-[11.5px]"
            style={{ borderColor: 'var(--border)', color: 'var(--text-faint)' }}
          >
            A driver with a login runs the trip and updates the deliveries from his own
            phone. He is shown no money — what you pay him is between the two of you. Ask
            Target Express to add or remove one.
          </p>
        </Card>
      ) : null}

      {/* Run by run, for the same reason the driver's screen is: a total is
          something to accept or argue with, and a run he remembers is
          something he can check. */}
      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold">
            <Route className="size-4" style={{ color: 'var(--text-faint)' }} />
            Run by run
          </h3>
        </div>
        {runs.data?.length ? (
          runs.data.map((r) => (
            <div
              key={r.freight_id}
              className="flex items-start justify-between gap-3 border-t px-4 py-3"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0">
                <p className="tnum text-[13.5px] font-medium">
                  {r.trip_no}
                  {r.lr_no ? ` · LR ${r.lr_no}` : ''}
                </p>
                <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  {new Date(r.trip_date).toLocaleDateString('en-IN')} · {r.vehicle_no}
                  {r.km ? ` · ${r.km} km` : ''}
                  {r.driver_name ? ` · ${r.driver_name}` : ''}
                </p>
                {r.destination_text ? (
                  <p className="mt-0.5 truncate text-[12px]" style={{ color: 'var(--text-muted)' }}>
                    {r.destination_text}
                  </p>
                ) : null}
              </div>
              <div className="shrink-0 text-right">
                <p className="tnum text-[14px] font-semibold">{rupees(r.earned)}</p>
                {/* Paid or not, in a word. It is the only thing he wants to
                    know about a run that is already finished. */}
                <p className="mt-0.5 text-[11px]" style={{ color: 'var(--text-faint)' }}>
                  {r.settlement_no ? `paid · ${r.settlement_no}` : 'not settled'}
                </p>
              </div>
            </div>
          ))
        ) : (
          <EmptyState
            compact
            icon={<Route className="size-7" />}
            title="No runs yet"
            description="Trips your lorries do will appear here with what each one pays."
          />
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold">
            <Wallet className="size-4" style={{ color: 'var(--text-faint)' }} />
            Settlements
          </h3>
        </div>
        {settlements.data?.length ? (
          settlements.data.map((s) => (
            <div
              key={s.id}
              className="border-t px-4 py-3"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium">{s.settlement_no}</p>
                  <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
                    {s.period_from} → {s.period_to} · {s.trip_count}{' '}
                    {s.trip_count === 1 ? 'run' : 'runs'}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[s.status] ?? 'neutral'}>{s.status}</Badge>
              </div>
              <div className="tnum mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
                <span style={{ color: 'var(--text-muted)' }}>
                  Gross {rupees(s.gross_amount)}
                </span>
                {Number(s.advance_recovered) > 0 ? (
                  <span style={{ color: 'var(--warning)' }}>
                    Advance −{rupees(s.advance_recovered)}
                  </span>
                ) : null}
                <span className="font-semibold">Paid {rupees(s.net_payable)}</span>
              </div>
            </div>
          ))
        ) : (
          <EmptyState
            compact
            icon={<Wallet className="size-7" />}
            title="Nothing settled yet"
            description="A settlement gathers the runs over a period, less any advance."
          />
        )}
      </Card>

      {/* Both sides reading one ledger is most of the answer to the
          commonest dispute a contractor has with an office: whether an
          advance was recovered twice. */}
      <Card className="overflow-hidden">
        <div className="px-4 py-3.5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold">
            <HandCoins className="size-4" style={{ color: 'var(--text-faint)' }} />
            Advances
          </h3>
        </div>
        {advances.data?.length ? (
          advances.data.map((a) => (
            <div
              key={a.id}
              className="flex items-start justify-between gap-3 border-t px-4 py-2.5"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0">
                <p className="tnum text-[13px]">
                  {new Date(a.advance_date).toLocaleDateString('en-IN')}
                </p>
                {a.reason ? (
                  <p className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
                    {a.reason}
                  </p>
                ) : null}
              </div>
              <div className="shrink-0 text-right">
                <p className="tnum text-[13px]">{rupees(a.amount)}</p>
                <p
                  className="tnum mt-0.5 text-[11.5px]"
                  style={{
                    color:
                      Number(a.outstanding) > 0 ? 'var(--warning)' : 'var(--text-faint)',
                  }}
                >
                  {Number(a.outstanding) > 0
                    ? `${rupees(a.outstanding)} still to recover`
                    : 'recovered'}
                </p>
              </div>
            </div>
          ))
        ) : (
          <EmptyState
            compact
            icon={<HandCoins className="size-7" />}
            title="No advances"
            description="Cash drawn before a settlement would show here, with what is left to recover."
          />
        )}
      </Card>
    </div>
  )
}
