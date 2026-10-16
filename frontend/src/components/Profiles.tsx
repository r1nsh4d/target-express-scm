/* One lorry, or one driver, opened from its tile.
 *
 * The list answers "which vehicles do we have", which is not a question
 * anybody has. They ask about one of them: how much has it run, what did it
 * earn against what it cost, who drives it, are its papers in date. Or about
 * one driver: what has he run, what is he owed right now, what has already
 * been settled, what is outstanding against him in advances.
 *
 * All of that existed, spread across a period report, the settlements screen
 * and the advances screen, and the answer came out differently depending on
 * which one you looked at. Here it is assembled from the same documents the
 * reports use, so it cannot disagree with them.
 *
 * The runs stay a TABLE. Everything else on these screens became tiles
 * because the question was "tell me about this one"; a list of forty trips is
 * the other kind of question — scan one column down the page — and that is
 * what a table is for.
 */

import { useQuery } from '@tanstack/react-query'
import { IndianRupee, Route, TriangleAlert, Wallet } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge, Card, EmptyState, Modal, Spinner, Table } from '@/components/ui'
import { api } from '@/lib/api'
import { STATUS_TONE, rupees } from '@/lib/resources'

interface RunRow {
  freight_id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  destination_text: string | null
  point_count: number
  km: number
  counterpart: string | null
  invoiced: string | null
  paid: string
}

interface VehicleProfile {
  id: string
  registration_no: string
  vehicle_type_name: string | null
  ownership: string
  owner_name: string | null
  is_active: boolean
  lr_prefix: string | null
  lr_next_number: number
  last_closing_km: number | null
  insurance_expiry: string | null
  fitness_expiry: string | null
  permit_expiry: string | null
  puc_expiry: string | null
  expired_papers: string[]
  hire_rate_basis: string | null
  hire_rate_value: string | null
  hire_minimum_km: number
  hire_includes_unloading: boolean
  trips: number
  km: number
  invoiced: string
  cost: string
  margin: string
  margin_per_km: string
  first_trip: string | null
  last_trip: string | null
  drivers: string[]
  runs: RunRow[]
}

interface SettlementRow {
  id: string
  settlement_no: string
  settlement_date: string
  period_from: string
  period_to: string
  trip_count: number
  gross_amount: string
  advance_recovered: string
  net_payable: string
  status: string
}

interface AdvanceRow {
  id: string
  advance_date: string
  amount: string
  recovered_amount: string
  outstanding: string
  reason: string | null
  status: string
}

interface DriverProfile {
  id: string
  name: string
  phone: string
  engagement: string
  licence_no: string | null
  is_active: boolean
  has_login: boolean
  trips: number
  km: number
  points: number
  earned: string
  settled: string
  unsettled: string
  transportation: string
  unloading: string
  point_incentive: string
  other: string
  advances_outstanding: string
  first_trip: string | null
  last_trip: string | null
  vehicles: string[]
  runs: RunRow[]
  settlements: SettlementRow[]
  advances: AdvanceRow[]
}

/** A headline figure. Four of these say more than a paragraph. */
function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: ReactNode
  sub?: string
  tone?: 'success' | 'danger' | 'warning'
}) {
  const colour =
    tone === 'success'
      ? 'var(--success)'
      : tone === 'danger'
        ? 'var(--danger)'
        : tone === 'warning'
          ? 'var(--warning)'
          : undefined

  return (
    <div className="inset px-3.5 py-3">
      <p className="text-[10.5px] tracking-[0.1em] uppercase" style={{ color: 'var(--text-faint)' }}>
        {label}
      </p>
      <p
        className="tnum mt-1 text-[18px] font-semibold"
        style={colour ? { color: colour } : undefined}
      >
        {value}
      </p>
      {sub ? (
        <p className="mt-0.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
          {sub}
        </p>
      ) : null}
    </div>
  )
}

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13.5px] font-semibold">{title}</h3>
        {aside}
      </div>
      {children}
    </div>
  )
}

/** The trips, as a table. The one place on these screens a table is right. */
function Runs({ runs, counterpartLabel }: { runs: RunRow[]; counterpartLabel: string }) {
  return (
    <Card className="overflow-hidden">
      <Table
        rows={runs}
        rowKey={(r) => `${r.freight_id}-${r.trip_no}`}
        empty={
          <EmptyState
            compact
            icon={<Route className="size-7" />}
            title="No trips yet"
            description="Runs appear here once a freight has been dispatched."
          />
        }
        columns={[
          { key: 'date', header: 'Date', render: (r) => <span className="tnum">{r.trip_date}</span> },
          {
            key: 'trip',
            header: 'Trip / LR',
            render: (r) => (
              <span className="tnum">
                {r.trip_no}
                {r.lr_no ? (
                  <span className="block text-[11px]" style={{ color: 'var(--text-faint)' }}>
                    LR {r.lr_no}
                  </span>
                ) : null}
              </span>
            ),
          },
          { key: 'who', header: counterpartLabel, render: (r) => r.counterpart ?? '—' },
          {
            key: 'dest',
            header: 'Destination',
            render: (r) => (
              <span className="block max-w-[14rem] truncate">{r.destination_text ?? '—'}</span>
            ),
          },
          { key: 'pts', header: 'Pts', align: 'right', render: (r) => <span className="tnum">{r.point_count}</span> },
          { key: 'km', header: 'KM', align: 'right', render: (r) => <span className="tnum">{r.km}</span> },
          {
            key: 'invoiced',
            header: 'Invoiced',
            align: 'right',
            render: (r) =>
              r.invoiced ? (
                <span className="tnum">{rupees(r.invoiced)}</span>
              ) : (
                <span className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  not billed
                </span>
              ),
          },
          {
            key: 'paid',
            header: 'Paid out',
            align: 'right',
            render: (r) => <span className="tnum">{rupees(r.paid)}</span>,
          },
          {
            key: 'status',
            header: 'Status',
            render: (r) => <Badge tone={STATUS_TONE[r.status] ?? 'neutral'}>{r.status}</Badge>,
          },
        ]}
      />
    </Card>
  )
}

export function VehicleDetail({
  vehicleId,
  open,
  onClose,
}: {
  vehicleId: string | null
  open: boolean
  onClose: () => void
}) {
  const profile = useQuery({
    queryKey: [`/vehicles/${vehicleId}/profile`],
    queryFn: async () => (await api.get<VehicleProfile>(`/vehicles/${vehicleId}/profile`)).data,
    enabled: open && !!vehicleId,
  })

  const v = profile.data

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={v?.registration_no ?? 'Vehicle'}
      description={
        v
          ? `${v.vehicle_type_name ?? 'Type not set'} · ${
              v.ownership === 'OWNED' ? 'Owned by Target Express' : `Rented from ${v.owner_name ?? 'an owner'}`
            }`
          : undefined
      }
    >
      {profile.isLoading || !v ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : (
        <div className="space-y-5">
          {v.expired_papers.length ? (
            <p
              className="flex items-start gap-2 rounded-[var(--radius-control)] px-3.5 py-2.5 text-[12.5px]"
              style={{ background: 'color-mix(in oklab, var(--danger) 12%, transparent)' }}
            >
              <TriangleAlert className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--danger)' }} />
              <span>
                <strong>{v.expired_papers.join(', ')}</strong> expired. This lorry should not be
                assigned to a freight until it is renewed.
              </span>
            </p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Trips"
              value={v.trips}
              sub={v.first_trip ? `since ${v.first_trip}` : 'never run'}
            />
            <Stat label="Distance" value={`${v.km.toLocaleString('en-IN')} km`} />
            <Stat label="Invoiced" value={rupees(v.invoiced)} sub="what vendors were billed" />
            <Stat
              label="Contributed"
              value={rupees(v.margin)}
              sub={`${rupees(v.margin_per_km)} a kilometre`}
              tone={Number(v.margin) >= 0 ? 'success' : 'danger'}
            />
          </div>

          <Section title="The lorry">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Odometer"
                value={
                  v.last_closing_km != null
                    ? `${v.last_closing_km.toLocaleString('en-IN')} km`
                    : '—'
                }
                sub="last closing reading"
              />
              <Stat
                label="Next LR"
                value={`${v.lr_prefix ?? ''}${v.lr_next_number}`}
                sub="issued at dispatch"
              />
              <Stat label="Paid out" value={rupees(v.cost)} sub="drivers, owner and expenses" />
              <Stat
                label="Driven by"
                value={v.drivers.length ? v.drivers[0] : '—'}
                sub={
                  v.drivers.length > 1
                    ? `and ${v.drivers.length - 1} other${v.drivers.length === 2 ? '' : 's'}`
                    : undefined
                }
              />
            </div>
          </Section>

          {/* Rented lorries only. An owned one pays its driver instead, and a
              hire block full of zeroes would read as a rate of nothing. */}
          {v.ownership !== 'OWNED' ? (
            <Section title="What the owner is paid">
              <div className="inset px-3.5 py-3 text-[13px]">
                {v.hire_rate_value ? (
                  <p className="tnum">
                    {rupees(v.hire_rate_value)}{' '}
                    {v.hire_rate_basis === 'PER_KM' ? 'per kilometre' : 'per trip'}
                    {v.hire_minimum_km > 0 ? `, minimum ${v.hire_minimum_km} km a trip` : ''}
                    {v.hire_includes_unloading ? ' · rent covers unloading' : ''}
                  </p>
                ) : (
                  <p style={{ color: 'var(--warning)' }}>
                    No hire terms in force. A trip on this lorry cannot be settled to its owner
                    until a rate is set.
                  </p>
                )}
              </div>
            </Section>
          ) : null}

          <Section
            title="Its runs"
            aside={
              <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                Kilometres are this lorry's own legs — a trip it finished on a replacement counts
                only its share.
              </span>
            }
          >
            <Runs runs={v.runs} counterpartLabel="Driver" />
          </Section>
        </div>
      )}
    </Modal>
  )
}

export function DriverDetail({
  driverId,
  open,
  onClose,
}: {
  driverId: string | null
  open: boolean
  onClose: () => void
}) {
  const profile = useQuery({
    queryKey: [`/drivers/${driverId}/profile`],
    queryFn: async () => (await api.get<DriverProfile>(`/drivers/${driverId}/profile`)).data,
    enabled: open && !!driverId,
  })

  const d = profile.data

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={d?.name ?? 'Driver'}
      description={
        d
          ? `${d.phone} · ${
              d.engagement === 'OWN_STAFF' ? 'Target Express staff' : 'comes with a rented vehicle'
            }`
          : undefined
      }
    >
      {profile.isLoading || !d ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Trips"
              value={d.trips}
              sub={d.first_trip ? `since ${d.first_trip}` : 'never run'}
            />
            <Stat label="Distance" value={`${d.km.toLocaleString('en-IN')} km`} sub={`${d.points} points`} />
            <Stat label="Earned" value={rupees(d.earned)} sub="all time" />
            {/* The figure anybody acts on. Earned is history; this is what he
                is owed right now. */}
            <Stat
              label="Owed now"
              value={rupees(d.unsettled)}
              sub="not yet settled"
              tone={Number(d.unsettled) > 0 ? 'warning' : undefined}
            />
          </div>

          <Section title="What he has earned, by head">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Driving" value={rupees(d.transportation)} />
              <Stat label="Unloading" value={rupees(d.unloading)} />
              <Stat label="Point incentive" value={rupees(d.point_incentive)} />
              <Stat
                label="Advances against him"
                value={rupees(d.advances_outstanding)}
                tone={Number(d.advances_outstanding) > 0 ? 'danger' : undefined}
                sub="recovered from his next settlement"
              />
            </div>
          </Section>

          <Section title="His runs">
            <Runs runs={d.runs} counterpartLabel="Vehicle" />
          </Section>

          <Section
            title="Settlements"
            aside={
              <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                {rupees(d.settled)} already settled
              </span>
            }
          >
            <Card className="overflow-hidden">
              <Table
                rows={d.settlements}
                rowKey={(s) => s.id}
                empty={
                  <EmptyState
                    compact
                    icon={<Wallet className="size-7" />}
                    title="Nothing settled yet"
                    description="A settlement gathers his payouts over a period, less any advances."
                  />
                }
                columns={[
                  { key: 'no', header: 'Settlement', render: (s) => s.settlement_no },
                  {
                    key: 'period',
                    header: 'Period',
                    render: (s) => (
                      <span className="tnum">
                        {s.period_from} → {s.period_to}
                      </span>
                    ),
                  },
                  { key: 'trips', header: 'Trips', align: 'right', render: (s) => <span className="tnum">{s.trip_count}</span> },
                  { key: 'gross', header: 'Gross', align: 'right', render: (s) => <span className="tnum">{rupees(s.gross_amount)}</span> },
                  {
                    key: 'adv',
                    header: 'Advance recovered',
                    align: 'right',
                    render: (s) => <span className="tnum">{rupees(s.advance_recovered)}</span>,
                  },
                  {
                    key: 'net',
                    header: 'Net paid',
                    align: 'right',
                    render: (s) => <span className="tnum font-medium">{rupees(s.net_payable)}</span>,
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (s) => <Badge tone={STATUS_TONE[s.status] ?? 'neutral'}>{s.status}</Badge>,
                  },
                ]}
              />
            </Card>
          </Section>

          <Section title="Advances">
            <Card className="overflow-hidden">
              <Table
                rows={d.advances}
                rowKey={(a) => a.id}
                empty={
                  <EmptyState
                    compact
                    icon={<IndianRupee className="size-7" />}
                    title="No advances"
                    description="Cash handed over before a settlement would show here, with what is left to recover."
                  />
                }
                columns={[
                  { key: 'date', header: 'Date', render: (a) => <span className="tnum">{a.advance_date}</span> },
                  { key: 'why', header: 'Reason', render: (a) => a.reason ?? '—' },
                  { key: 'amt', header: 'Given', align: 'right', render: (a) => <span className="tnum">{rupees(a.amount)}</span> },
                  {
                    key: 'rec',
                    header: 'Recovered',
                    align: 'right',
                    render: (a) => <span className="tnum">{rupees(a.recovered_amount)}</span>,
                  },
                  {
                    key: 'out',
                    header: 'Still owed',
                    align: 'right',
                    render: (a) => (
                      <span
                        className="tnum font-medium"
                        style={Number(a.outstanding) > 0 ? { color: 'var(--warning)' } : undefined}
                      >
                        {rupees(a.outstanding)}
                      </span>
                    ),
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (a) => <Badge tone={STATUS_TONE[a.status] ?? 'neutral'}>{a.status}</Badge>,
                  },
                ]}
              />
            </Card>
          </Section>
        </div>
      )}
    </Modal>
  )
}
