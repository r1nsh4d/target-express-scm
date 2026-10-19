/* What this trip earned, what it cost, and what is left.
 *
 * The trip screen had "What this bills" and, separately and further down,
 * what it pays out. Nothing put the two beside each other, so the question
 * anybody actually has about a freight — was it worth running — was a
 * subtraction done in somebody's head between two cards.
 *
 * Here it is one block: in on the left, out on the right, the gap underneath.
 *
 * EVERY LINE CARRIES ITS WORKING, in the small grey line beneath it. "₹680"
 * is a number you either believe or ring somebody about; "40 km over 60 ×
 * ₹17.00" is one you can check. The unloading goes further and lists the
 * stops, the articles and the floors, because "why is unloading 340 on this
 * trip" is the question this exists to answer without a phone call.
 *
 * A LINE OF ZERO IS STILL A LINE. "Extra points ₹0.00 — 1 stop, within the 3
 * included" is the sentence that explains why a one-stop run bills the same
 * as a three-stop one. Dropping it is how that becomes a query.
 */

import { TrendingDown, TrendingUp } from 'lucide-react'

import { Card, Spinner } from '@/components/ui'
import { rupees, useItem } from '@/lib/resources'

interface MoneyLine {
  label: string
  amount: string
  working: string
}

interface UnloadingArticle {
  item_name: string
  quantity: number
  charged_each: string
  charged: string
  driver_each: string
  driver_pay: string
  floors_charged: number
}

interface UnloadingPoint {
  point_id: string
  sequence: number
  customer_name: string
  floor_number: number
  has_lift: boolean
  articles: UnloadingArticle[]
  charged: string
  driver_pay: string
  margin: string
}

export interface Economics {
  trip_no: string
  trip_date: string
  status: string
  vehicle_no: string | null
  vehicle_type_name: string | null
  driver_name: string | null
  km: number
  points: number
  revenue: MoneyLine[]
  revenue_total: string
  revenue_problem: string | null
  cost: MoneyLine[]
  cost_total: string
  paid_to: string
  is_settled: boolean
  unloading_points: UnloadingPoint[]
  margin: string
  margin_percent: string
  margin_per_km: string
}

function Line({ line }: { line: MoneyLine }) {
  return (
    <div
      className="flex items-start justify-between gap-3 border-t px-4 py-2.5"
      style={{ borderColor: 'var(--border)' }}
    >
      <div className="min-w-0">
        <p className="text-[13px]">{line.label}</p>
        {line.working ? (
          <p className="mt-0.5 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
            {line.working}
          </p>
        ) : null}
      </div>
      <span
        className="tnum shrink-0 text-[13px] font-medium"
        style={Number(line.amount) === 0 ? { color: 'var(--text-faint)' } : undefined}
      >
        {rupees(line.amount)}
      </span>
    </div>
  )
}

function Column({
  title,
  note,
  lines,
  total,
  totalLabel,
  problem,
}: {
  title: string
  note: string
  lines: MoneyLine[]
  total: string
  totalLabel: string
  problem?: string | null
}) {
  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3.5">
        <h3 className="text-[13.5px] font-semibold">{title}</h3>
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
          {note}
        </p>
      </div>

      {problem ? (
        <div
          className="border-t px-4 py-3 text-[12.5px]"
          style={{
            borderColor: 'var(--border)',
            background: 'color-mix(in oklab, var(--warning) 12%, transparent)',
          }}
        >
          {problem}
        </div>
      ) : (
        lines.map((line, i) => <Line key={`${line.label}-${i}`} line={line} />)
      )}

      <div
        className="flex items-baseline justify-between border-t px-4 py-3"
        style={{ borderColor: 'var(--border-strong)' }}
      >
        <span className="text-[13px] font-semibold">{totalLabel}</span>
        <span className="tnum text-[15px] font-semibold">{rupees(total)}</span>
      </div>
    </Card>
  )
}

export function FreightMoney({ freightId }: { freightId: string }) {
  const money = useItem<Economics>(`/freights/${freightId}/economics`)

  if (money.isLoading) {
    return (
      <Card className="flex justify-center py-12">
        <Spinner className="size-5" />
      </Card>
    )
  }
  if (!money.data) return null

  const e = money.data
  const up = Number(e.margin) >= 0

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Column
          title="What the vendor pays"
          note={`On the card in force on ${e.trip_date}${
            e.vehicle_type_name ? `, for a ${e.vehicle_type_name}` : ''
          }.`}
          lines={e.revenue}
          total={e.revenue_total}
          totalLabel="Billed"
          problem={e.revenue_problem}
        />

        <Column
          title={e.paid_to === 'VEHICLE_OWNER' ? "What goes to the owner" : 'What the driver is paid'}
          note={
            e.is_settled
              ? 'What this trip actually paid out, from its settled rows.'
              : 'On the terms in force. These become firm when the trip closes.'
          }
          lines={e.cost}
          total={e.cost_total}
          totalLabel="Paid out"
        />
      </div>

      {/* The answer to "was it worth running". */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              className="grid size-10 shrink-0 place-items-center rounded-[11px]"
              style={{
                background: up
                  ? 'color-mix(in oklab, var(--success) 16%, transparent)'
                  : 'color-mix(in oklab, var(--danger) 16%, transparent)',
                color: up ? 'var(--success)' : 'var(--danger)',
              }}
            >
              {up ? <TrendingUp className="size-5" /> : <TrendingDown className="size-5" />}
            </span>
            <div>
              <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                {up ? 'Target Express keeps' : 'This trip lost'}
              </p>
              <p
                className="tnum text-[22px] font-semibold"
                style={{ color: up ? 'var(--success)' : 'var(--danger)' }}
              >
                {rupees(e.margin)}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-x-8 gap-y-2">
            <div>
              <p className="text-[11px] tracking-[0.1em] uppercase" style={{ color: 'var(--text-faint)' }}>
                Of what was billed
              </p>
              <p className="tnum mt-0.5 text-[14px] font-medium">{e.margin_percent}%</p>
            </div>
            <div>
              <p className="text-[11px] tracking-[0.1em] uppercase" style={{ color: 'var(--text-faint)' }}>
                Per kilometre
              </p>
              <p className="tnum mt-0.5 text-[14px] font-medium">{rupees(e.margin_per_km)}</p>
            </div>
            <div>
              <p className="text-[11px] tracking-[0.1em] uppercase" style={{ color: 'var(--text-faint)' }}>
                Distance
              </p>
              <p className="tnum mt-0.5 text-[14px] font-medium">{e.km} km</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Unloading, stop by stop. The one head where the margin is made a
          chair at a time, so it is the one worth opening up. */}
      {e.unloading_points.length ? (
        <Card className="overflow-hidden">
          <div className="px-4 py-3.5">
            <h3 className="text-[13.5px] font-semibold">Unloading, stop by stop</h3>
            <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
              What the vendor is charged per article against what the driver is paid for
              carrying it. Both off the same count, at the same floor.
            </p>
          </div>

          {e.unloading_points.map((p) => (
            <div
              key={p.point_id}
              className="border-t px-4 py-3"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-[13px] font-medium">
                  {p.sequence}. {p.customer_name}
                  <span className="ml-2 font-normal" style={{ color: 'var(--text-muted)' }}>
                    {p.floor_number === 0
                      ? 'ground floor'
                      : `floor ${p.floor_number}${p.has_lift ? ', lift' : ''}`}
                  </span>
                </p>
                <p className="tnum text-[12.5px]">
                  <span style={{ color: 'var(--text-muted)' }}>{rupees(p.charged)} in</span>
                  <span className="mx-1.5" style={{ color: 'var(--text-faint)' }}>
                    −
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>{rupees(p.driver_pay)} out</span>
                  <span className="mx-1.5" style={{ color: 'var(--text-faint)' }}>
                    =
                  </span>
                  <span
                    className="font-semibold"
                    style={{
                      color: Number(p.margin) >= 0 ? 'var(--success)' : 'var(--danger)',
                    }}
                  >
                    {rupees(p.margin)}
                  </span>
                </p>
              </div>

              <div className="mt-2 space-y-1">
                {p.articles.map((a) => (
                  <div
                    key={a.item_name}
                    className="tnum flex flex-wrap items-baseline justify-between gap-2 text-[12px]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <span>
                      {a.quantity} × {a.item_name}
                      {a.floors_charged > 0 ? ` up ${a.floors_charged}` : ''}
                    </span>
                    <span>
                      {rupees(a.charged_each)} each charged · {rupees(a.driver_each)} each paid
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>
      ) : null}
    </div>
  )
}
