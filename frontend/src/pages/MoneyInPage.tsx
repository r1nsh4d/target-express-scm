import { Landmark } from 'lucide-react'
import { useState } from 'react'

import { Card, EmptyState, Field, Input, PageHeader, Spinner, Table } from '@/components/ui'
import { rupees, useList } from '@/lib/resources'

/* Payments received, as a bank statement would be read against them.

   The other side of Settlements, which is money going out. It reads from the
   invoices themselves rather than from a separate ledger, so a receipt can
   never disagree with the document it was paid against — there is only one
   number, not two that have to be kept in step.

   The column that earns its place is the shortfall. A 92,478.40 invoice
   settled by 91,553.62 is not a short payment to chase; it is TDS deducted at
   source, and the balance arrives later as a credit. Showing it means the
   difference is accounted for on the day rather than discovered at year end as
   a gap nobody can explain. */

interface MoneyInRow {
  invoice_id: string
  invoice_no: string
  vendor_division_name: string | null
  invoice_date: string
  paid_on: string
  invoiced: string
  received: string
  shortfall: string
  payment_mode: string | null
  payment_reference: string | null
}

export default function MoneyInPage() {
  const today = new Date()
  const firstOfYear = new Date(today.getFullYear(), today.getMonth() - 3, 1)

  const [from, setFrom] = useState(firstOfYear.toISOString().slice(0, 10))
  const [to, setTo] = useState(today.toISOString().slice(0, 10))

  const rows = useList<MoneyInRow>('/money-in', { period_from: from, period_to: to })
  const data = rows.data ?? []

  const received = data.reduce((sum, r) => sum + Number(r.received), 0)
  const invoiced = data.reduce((sum, r) => sum + Number(r.invoiced), 0)
  const shortfall = invoiced - received

  return (
    <div className="space-y-6">
      <PageHeader description="What vendors have actually paid, and against which invoice. A receipt smaller than the invoice is normally TDS deducted at source — the difference is shown rather than left to be worked out." />

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

      {rows.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : (
        <>
          {data.length ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <Figure label="Received" value={received} strong />
              <Figure label="Invoiced" value={invoiced} />
              <Figure label="Shortfall (TDS and short payments)" value={shortfall} warn={shortfall > 0} />
            </div>
          ) : null}

          <Card className="overflow-hidden">
            <Table
              rows={data}
              rowKey={(r) => r.invoice_id}
              empty={
                <EmptyState
                  icon={<Landmark className="size-7" />}
                  title="No payments in this period"
                  description="A payment appears here once it is recorded against an invoice, under Vendor invoices."
                />
              }
              columns={[
                {
                  key: 'paid',
                  header: 'Received on',
                  render: (r) => <span className="tnum font-medium">{r.paid_on}</span>,
                },
                { key: 'inv', header: 'Invoice', render: (r) => r.invoice_no },
                {
                  key: 'div',
                  header: 'Division',
                  render: (r) => r.vendor_division_name ?? '—',
                },
                {
                  key: 'mode',
                  header: 'Mode',
                  render: (r) => (
                    <span>
                      {r.payment_mode ?? '—'}
                      {r.payment_reference ? (
                        <span className="block text-[11px]" style={{ color: 'var(--text-faint)' }}>
                          {r.payment_reference}
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  key: 'invoiced',
                  header: 'Invoiced',
                  align: 'right',
                  render: (r) => (
                    <span className="tnum" style={{ color: 'var(--text-muted)' }}>
                      {rupees(r.invoiced)}
                    </span>
                  ),
                },
                {
                  key: 'short',
                  header: 'Shortfall',
                  align: 'right',
                  render: (r) =>
                    Number(r.shortfall) > 0 ? (
                      <span className="tnum" style={{ color: 'var(--warning)' }}>
                        {rupees(r.shortfall)}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-faint)' }}>—</span>
                    ),
                },
                {
                  key: 'received',
                  header: 'Received',
                  align: 'right',
                  render: (r) => <span className="tnum font-semibold">{rupees(r.received)}</span>,
                },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  )
}

function Figure({
  label,
  value,
  strong,
  warn,
}: {
  label: string
  value: number
  strong?: boolean
  warn?: boolean
}) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </p>
      <p
        className={`tnum mt-1 ${strong ? 'text-[22px] font-semibold' : 'text-[18px] font-medium'}`}
        style={warn && value > 0 ? { color: 'var(--warning)' } : undefined}
      >
        {rupees(value.toFixed(2))}
      </p>
    </Card>
  )
}
