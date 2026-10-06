import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Wallet } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Spinner,
  Table,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { STATUS_TONE, rupees, useList } from '@/lib/resources'

interface Pending {
  payee_type: 'DRIVER' | 'VEHICLE_OWNER'
  payee_id: string
  payee_name: string
  freight_count: number
  by_head: Record<string, string>
  gross: string
  advance_outstanding: string
  net_payable: string
}

interface SettlementRow {
  id: string
  settlement_no: string
  settlement_date: string
  period_from: string
  period_to: string
  payee_type: string
  payee_name: string | null
  trip_count: number
  transportation_amount: string
  loading_unloading_amount: string
  point_incentive_amount: string
  gross_amount: string
  advance_recovered: string
  net_payable: string
  status: string
}

export default function SettlementsPage() {
  const queryClient = useQueryClient()
  const today = new Date()
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)

  const [period, setPeriod] = useState({
    period_from: firstOfMonth.toISOString().slice(0, 10),
    period_to: today.toISOString().slice(0, 10),
  })
  const [error, setError] = useState<string | null>(null)

  const pending = useList<Pending>('/settlements/pending', period)
  const settlements = useList<SettlementRow>('/settlements')

  const settle = useMutation({
    mutationFn: async (p: Pending) =>
      (
        await api.post('/settlements', {
          payee_type: p.payee_type,
          payee_id: p.payee_id,
          ...period,
        })
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/settlements/pending'] })
      queryClient.invalidateQueries({ queryKey: ['/settlements'] })
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  return (
    <div className="space-y-6">
      <PageHeader description="A settlement is a payment run for one party, not for one freight. An owned vehicle's work pays its driver; a rented one pays the vehicle's owner — and any advance already drawn is deducted here." />

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="From">
            <Input
              type="date"
              value={period.period_from}
              onChange={(e) => setPeriod({ ...period, period_from: e.target.value })}
            />
          </Field>
        </div>
        <div className="w-44">
          <Field label="To">
            <Input
              type="date"
              value={period.period_to}
              onChange={(e) => setPeriod({ ...period, period_to: e.target.value })}
            />
          </Field>
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      <section>
        <h2 className="eyebrow mb-2">Outstanding</h2>
        {pending.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner className="size-5" />
          </div>
        ) : !pending.data?.length ? (
          <Card>
            <EmptyState
              icon={<Wallet className="size-7" />}
              title="Everyone is settled"
              description="No unsettled work in this period."
            />
          </Card>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {pending.data.map((p) => (
              <Card key={`${p.payee_type}-${p.payee_id}`} className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[15px] font-semibold">{p.payee_name}</p>
                    <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {p.payee_type === 'VEHICLE_OWNER' ? 'Vehicle owner' : 'Driver'} ·{' '}
                      {p.freight_count} freight{p.freight_count === 1 ? '' : 's'}
                    </p>
                  </div>
                  <Badge tone={p.payee_type === 'VEHICLE_OWNER' ? 'info' : 'accent'}>
                    {p.payee_type === 'VEHICLE_OWNER' ? 'Owner' : 'Driver'}
                  </Badge>
                </div>

                <div className="mt-4 space-y-1.5">
                  {Object.entries(p.by_head)
                    .filter(([, v]) => Number(v) !== 0)
                    .map(([head, value]) => (
                      <div key={head} className="flex items-baseline justify-between text-[13px]">
                        <span style={{ color: 'var(--text-muted)' }}>
                          {head.replaceAll('_', ' ').toLowerCase()}
                        </span>
                        <span className="tnum">{rupees(value)}</span>
                      </div>
                    ))}

                  {Number(p.advance_outstanding) > 0 ? (
                    <div className="flex items-baseline justify-between text-[13px]">
                      <span style={{ color: 'var(--warning)' }}>advance to recover</span>
                      <span className="tnum" style={{ color: 'var(--warning)' }}>
                        −{rupees(p.advance_outstanding)}
                      </span>
                    </div>
                  ) : null}
                </div>

                <div className="groove my-3" />

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                      Net payable
                    </p>
                    <p className="tnum text-[20px] font-semibold">{rupees(p.net_payable)}</p>
                  </div>
                  <Button
                    loading={settle.isPending && settle.variables?.payee_id === p.payee_id}
                    onClick={() => {
                      setError(null)
                      settle.mutate(p)
                    }}
                  >
                    Settle
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="eyebrow mb-2">Settled</h2>
        <Card className="overflow-hidden">
          <Table
            rows={settlements.data ?? []}
            rowKey={(s) => s.id}
            empty={<EmptyState title="Nothing settled yet" />}
            columns={[
              {
                key: 'no',
                header: 'Settlement',
                render: (s) => <span className="font-medium">{s.settlement_no}</span>,
              },
              { key: 'payee', header: 'Paid to', render: (s) => s.payee_name ?? '—' },
              {
                key: 'type',
                header: 'Type',
                render: (s) => (
                  <Badge tone={s.payee_type === 'VEHICLE_OWNER' ? 'info' : 'accent'}>
                    {s.payee_type === 'VEHICLE_OWNER' ? 'Owner' : 'Driver'}
                  </Badge>
                ),
              },
              {
                key: 'period',
                header: 'Period',
                render: (s) => (
                  <span className="tnum">
                    {s.period_from} → {s.period_to}
                  </span>
                ),
              },
              {
                key: 'trips',
                header: 'Freights',
                align: 'right',
                render: (s) => <span className="tnum">{s.trip_count}</span>,
              },
              {
                key: 'gross',
                header: 'Gross',
                align: 'right',
                render: (s) => <span className="tnum">{rupees(s.gross_amount)}</span>,
              },
              {
                key: 'adv',
                header: 'Advance',
                align: 'right',
                render: (s) => <span className="tnum">{rupees(s.advance_recovered)}</span>,
              },
              {
                key: 'net',
                header: 'Net',
                align: 'right',
                render: (s) => (
                  <span className="tnum font-semibold">{rupees(s.net_payable)}</span>
                ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (s) => (
                  <Badge tone={STATUS_TONE[s.status] ?? 'neutral'}>{s.status}</Badge>
                ),
              },
            ]}
          />
        </Card>
      </section>
    </div>
  )
}
