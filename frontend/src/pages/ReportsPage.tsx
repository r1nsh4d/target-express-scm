import { BarChart3 } from 'lucide-react'
import { useState } from 'react'

import { Card, EmptyState, Field, Input, PageHeader, Spinner, Table } from '@/components/ui'
import { rupees, useItem } from '@/lib/resources'

/* What the business did, over a period.
 *
 * The dashboard answers "what is happening today". This answers the questions
 * asked at the end of a month: did we make anything, where did it come from,
 * who is slow to pay, and what came back.
 *
 * Every figure is built from the invoices and payouts themselves rather than a
 * separate ledger, so a report can never disagree with the documents it
 * summarises — which is the usual reason nobody trusts a reports screen.
 */

interface Report {
  period_from: string
  period_to: string
  money: {
    invoiced: string
    received: string
    outstanding: string
    paid_to_drivers_and_owners: string
    expenses: string
    margin: string
    margin_percent: string
  }
  work: {
    trips: number
    points: number
    km: number
    boxes_delivered: number
    boxes_returned: number
    return_rate_percent: string
  }
  by_month: { month: string; trips: number; invoiced: string; margin: string }[]
  by_division: { name: string; trips: number; amount: string }[]
  top_customers: { name: string; trips: number }[]
  drivers: { name: string; trips: number; km: number; earned: string }[]
  vehicles: {
    registration_no: string
    owned: boolean
    trips: number
    km: number
    invoiced: string
    cost: string
    margin: string
    margin_per_km: string
  }[]
  overdue: {
    invoice_no: string
    vendor_division_name: string | null
    invoice_date: string
    total: string
    days_outstanding: number
  }[]
}

const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

function monthLabel(ym: string) {
  const [year, month] = ym.split('-')
  return `${MONTH_NAMES[Number(month) - 1] ?? month} ${year}`
}

export default function ReportsPage() {
  const today = new Date()
  const threeMonthsAgo = new Date(today.getFullYear(), today.getMonth() - 3, 1)

  const [from, setFrom] = useState(threeMonthsAgo.toISOString().slice(0, 10))
  const [to, setTo] = useState(today.toISOString().slice(0, 10))

  const report = useItem<Report>(
    `/reports?period_from=${from}&period_to=${to}`,
  )
  const r = report.data

  return (
    <div className="space-y-6">
      <PageHeader description="Built from the invoices and payouts themselves, so these figures can never disagree with the documents behind them. Revenue is what was invoiced; what has actually been received is shown beside it." />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[10rem]">
          <Field label="From">
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
        </div>
        <div className="min-w-[10rem]">
          <Field label="To">
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      </div>

      {report.isLoading || !r ? (
        <div className="flex justify-center py-20">
          <Spinner className="size-5" />
        </div>
      ) : !r.work.trips && !r.by_division.length ? (
        <Card>
          <EmptyState
            icon={<BarChart3 className="size-7" />}
            title="Nothing in this period"
            description="Widen the dates, or run some trips first."
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Figure label="Invoiced" value={rupees(r.money.invoiced)} strong />
            <Figure label="Received" value={rupees(r.money.received)} tone="success" />
            <Figure
              label="Still owed"
              value={rupees(r.money.outstanding)}
              tone={Number(r.money.outstanding) > 0 ? 'warning' : undefined}
            />
            <Figure
              label={`Margin · ${r.money.margin_percent}%`}
              value={rupees(r.money.margin)}
              tone={Number(r.money.margin) >= 0 ? 'success' : 'danger'}
              strong
            />
          </div>

          {/* The working, so the margin is a sum anybody can check rather than
              a number to be taken on trust. */}
          <Card className="p-4">
            <h3 className="text-[14px] font-semibold">How the margin is made</h3>
            <div className="mt-3 space-y-1.5 text-[13px]">
              <Line label="Invoiced to vendors" value={r.money.invoiced} />
              <Line label="Paid to drivers and vehicle owners" value={`-${r.money.paid_to_drivers_and_owners}`} negative />
              <Line label="Approved road expenses" value={`-${r.money.expenses}`} negative />
              <div className="groove my-1.5" />
              <Line label="Margin" value={r.money.margin} bold />
            </div>
          </Card>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Figure label="Trips" value={String(r.work.trips)} />
            <Figure label="Stops served" value={String(r.work.points)} />
            <Figure label="Kilometres" value={r.work.km.toLocaleString('en-IN')} />
            <Figure
              label={`Returns · ${r.work.return_rate_percent}%`}
              value={`${r.work.boxes_returned} of ${r.work.boxes_delivered + r.work.boxes_returned}`}
              tone={Number(r.work.return_rate_percent) > 2 ? 'warning' : undefined}
            />
          </div>

          {r.by_month.length > 1 ? (
            <Card className="p-4">
              <h3 className="text-[14px] font-semibold">Month by month</h3>
              <div className="mt-3 space-y-2">
                {r.by_month.map((m) => {
                  const peak = Math.max(...r.by_month.map((x) => Number(x.invoiced)), 1)
                  return (
                    <div key={m.month} className="flex items-center gap-3">
                      <span className="w-20 shrink-0 text-[12.5px]">{monthLabel(m.month)}</span>
                      <div
                        className="h-5 flex-1 overflow-hidden rounded"
                        style={{ background: 'var(--surface)' }}
                      >
                        <div
                          className="h-full rounded"
                          style={{
                            width: `${(Number(m.invoiced) / peak) * 100}%`,
                            background: 'var(--accent-grad)',
                          }}
                        />
                      </div>
                      <span className="tnum w-28 shrink-0 text-right text-[12.5px]">
                        {rupees(m.invoiced)}
                      </span>
                      <span
                        className="tnum w-24 shrink-0 text-right text-[12px]"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {m.trips} trips
                      </span>
                    </div>
                  )
                })}
              </div>
            </Card>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-2">
            <Card className="overflow-hidden">
              <div className="px-4 py-3.5">
                <h3 className="text-[14px] font-semibold">By vendor division</h3>
              </div>
              <Table
                rows={r.by_division}
                rowKey={(d) => d.name}
                empty={<EmptyState title="Nothing invoiced yet" />}
                columns={[
                  { key: 'n', header: 'Division', render: (d) => d.name },
                  {
                    key: 't',
                    header: 'Trips',
                    align: 'right',
                    render: (d) => <span className="tnum">{d.trips}</span>,
                  },
                  {
                    key: 'a',
                    header: 'Invoiced',
                    align: 'right',
                    render: (d) => <span className="tnum font-medium">{rupees(d.amount)}</span>,
                  },
                ]}
              />
            </Card>

            <Card className="overflow-hidden">
              <div className="px-4 py-3.5">
                <h3 className="text-[14px] font-semibold">Busiest customers</h3>
              </div>
              <Table
                rows={r.top_customers}
                rowKey={(c) => c.name}
                empty={<EmptyState title="No stops yet" />}
                columns={[
                  { key: 'n', header: 'Customer', render: (c) => c.name },
                  {
                    key: 's',
                    header: 'Stops',
                    align: 'right',
                    render: (c) => <span className="tnum font-medium">{c.trips}</span>,
                  },
                ]}
              />
            </Card>
          </div>

          <Card className="overflow-hidden">
            <div className="px-4 py-3.5">
              <h3 className="text-[14px] font-semibold">Drivers</h3>
              <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                Legs driven in the period, and what they earned for them.
              </p>
            </div>
            <Table
              rows={r.drivers}
              rowKey={(d) => d.name}
              empty={<EmptyState title="No completed legs in this period" />}
              columns={[
                { key: 'n', header: 'Driver', render: (d) => d.name },
                {
                  key: 't',
                  header: 'Legs',
                  align: 'right',
                  render: (d) => <span className="tnum">{d.trips}</span>,
                },
                {
                  key: 'k',
                  header: 'KM',
                  align: 'right',
                  render: (d) => <span className="tnum">{d.km.toLocaleString('en-IN')}</span>,
                },
                {
                  key: 'e',
                  header: 'Earned',
                  align: 'right',
                  render: (d) => <span className="tnum font-medium">{rupees(d.earned)}</span>,
                },
              ]}
            />
          </Card>

          <Card className="overflow-hidden">
            <div className="px-4 py-3.5">
              <h3 className="text-[14px] font-semibold">Vehicles</h3>
              <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                Attributed by leg, so a trip that broke down and finished on a hired lorry is
                split between the two. Rupees per kilometre is the only fair comparison between a
                DOST doing town runs and a lorry doing Kasaragod and back.
              </p>
            </div>
            <Table
              rows={r.vehicles}
              rowKey={(v) => v.registration_no}
              empty={<EmptyState title="No completed legs in this period" />}
              columns={[
                {
                  key: 'reg',
                  header: 'Vehicle',
                  render: (v) => (
                    <div>
                      <div className="font-medium">{v.registration_no}</div>
                      <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                        {v.owned ? 'Owned' : 'Hired'}
                      </div>
                    </div>
                  ),
                },
                {
                  key: 't',
                  header: 'Legs',
                  align: 'right',
                  render: (v) => <span className="tnum">{v.trips}</span>,
                },
                {
                  key: 'k',
                  header: 'KM',
                  align: 'right',
                  render: (v) => <span className="tnum">{v.km.toLocaleString('en-IN')}</span>,
                },
                {
                  key: 'i',
                  header: 'Invoiced',
                  align: 'right',
                  render: (v) => <span className="tnum">{rupees(v.invoiced)}</span>,
                },
                {
                  key: 'c',
                  header: 'Cost',
                  align: 'right',
                  render: (v) => (
                    <span className="tnum" style={{ color: 'var(--text-muted)' }}>
                      {rupees(v.cost)}
                    </span>
                  ),
                },
                {
                  key: 'm',
                  header: 'Margin',
                  align: 'right',
                  render: (v) => (
                    <span
                      className="tnum font-medium"
                      style={{ color: Number(v.margin) >= 0 ? 'var(--success)' : 'var(--danger)' }}
                    >
                      {rupees(v.margin)}
                    </span>
                  ),
                },
                {
                  key: 'pk',
                  header: 'Per km',
                  align: 'right',
                  render: (v) => (
                    <span className="tnum" style={{ color: 'var(--text-muted)' }}>
                      {rupees(v.margin_per_km)}
                    </span>
                  ),
                },
              ]}
            />
          </Card>

          {r.overdue.length ? (
            <Card className="overflow-hidden">
              <div className="px-4 py-3.5">
                <h3 className="text-[14px] font-semibold">Issued and not yet paid</h3>
                <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  Oldest first. These are the calls to make.
                </p>
              </div>
              <Table
                rows={r.overdue}
                rowKey={(o) => o.invoice_no}
                columns={[
                  { key: 'i', header: 'Invoice', render: (o) => o.invoice_no },
                  {
                    key: 'd',
                    header: 'Division',
                    render: (o) => o.vendor_division_name ?? '—',
                  },
                  {
                    key: 'dt',
                    header: 'Raised',
                    render: (o) => <span className="tnum">{o.invoice_date}</span>,
                  },
                  {
                    key: 'age',
                    header: 'Waiting',
                    align: 'right',
                    render: (o) => (
                      <span
                        className="tnum"
                        style={o.days_outstanding > 30 ? { color: 'var(--warning)' } : undefined}
                      >
                        {o.days_outstanding} days
                      </span>
                    ),
                  },
                  {
                    key: 't',
                    header: 'Amount',
                    align: 'right',
                    render: (o) => <span className="tnum font-medium">{rupees(o.total)}</span>,
                  },
                ]}
              />
            </Card>
          ) : null}
        </>
      )}
    </div>
  )
}

function Figure({
  label,
  value,
  strong,
  tone,
}: {
  label: string
  value: string
  strong?: boolean
  tone?: 'success' | 'warning' | 'danger'
}) {
  const colour =
    tone === 'success'
      ? 'var(--success)'
      : tone === 'warning'
        ? 'var(--warning)'
        : tone === 'danger'
          ? 'var(--danger)'
          : undefined
  return (
    <Card className="px-4 py-3.5">
      <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </p>
      <p
        className={`tnum mt-1 ${strong ? 'text-[20px] font-semibold' : 'text-[17px] font-medium'}`}
        style={colour ? { color: colour } : undefined}
      >
        {value}
      </p>
    </Card>
  )
}

function Line({
  label,
  value,
  negative,
  bold,
}: {
  label: string
  value: string
  negative?: boolean
  bold?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between">
      <span style={{ color: bold ? 'var(--text)' : 'var(--text-muted)' }} className={bold ? 'font-medium' : ''}>
        {label}
      </span>
      <span
        className={`tnum ${bold ? 'text-[15px] font-semibold' : ''}`}
        style={negative ? { color: 'var(--text-muted)' } : undefined}
      >
        {value.startsWith('-') ? `- ${rupees(value.slice(1))}` : rupees(value)}
      </span>
    </div>
  )
}
