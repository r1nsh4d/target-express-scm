import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, ReceiptText, X } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Table,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { rupees, useList } from '@/lib/resources'

interface Expense {
  id: string
  freight_id: string
  trip_no: string | null
  trip_date: string | null
  driver_name: string | null
  type: string
  amount: string
  paid_by: string
  billable_to_vendor: boolean
  receipt_photo_url: string | null
  labour_count: number | null
  entry_mode: string
  approval_status: string
  rejection_reason: string | null
  remarks: string | null
}

const TONE: Record<string, 'warning' | 'success' | 'danger'> = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
}

export default function ExpensesPage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('PENDING')
  const [rejecting, setRejecting] = useState<Expense | null>(null)
  const [error, setError] = useState<string | null>(null)

  const expenses = useList<Expense>('/expenses', status ? { approval_status: status } : undefined)

  const decide = useMutation({
    mutationFn: async ({ id, approve, reason }: { id: string; approve: boolean; reason?: string }) =>
      (await api.patch(`/expenses/${id}`, { approve, reason })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/expenses'] })
      setRejecting(null)
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  return (
    <div className="space-y-6">
      <PageHeader description="What drivers paid or drew on the road. The driver records what happened; the office decides what is settled. Tolls and detention pass through to the vendor's invoice — the rest is our own cost." />

      <ErrorNote>{error}</ErrorNote>

      <div className="max-w-xs">
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="PENDING">Waiting for a decision</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="">All</option>
          </Select>
        </Field>
      </div>

      <Card className="overflow-hidden">
        {expenses.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={expenses.data ?? []}
            rowKey={(e) => e.id}
            empty={
              <EmptyState
                icon={<ReceiptText className="size-7" />}
                title={status === 'PENDING' ? 'Nothing waiting' : 'Nothing here'}
                description={
                  status === 'PENDING'
                    ? 'Every expense has been decided.'
                    : 'Expenses appear as drivers record them on the road.'
                }
              />
            }
            columns={[
              {
                key: 'trip',
                header: 'Freight',
                render: (e) => (
                  <div>
                    <div className="font-medium">{e.trip_no ?? '—'}</div>
                    <div className="tnum text-[11px]" style={{ color: 'var(--text-faint)' }}>
                      {e.trip_date ?? ''}
                    </div>
                  </div>
                ),
              },
              { key: 'driver', header: 'Driver', render: (e) => e.driver_name ?? '—' },
              {
                key: 'type',
                header: 'Type',
                render: (e) => (
                  <span className="capitalize">{e.type.replaceAll('_', ' ').toLowerCase()}</span>
                ),
              },
              {
                key: 'amount',
                header: 'Amount',
                align: 'right',
                render: (e) => <span className="tnum font-medium">{rupees(e.amount)}</span>,
              },
              {
                key: 'billable',
                header: 'To vendor',
                render: (e) =>
                  e.billable_to_vendor ? (
                    <Badge tone="info">Passed through</Badge>
                  ) : (
                    <span style={{ color: 'var(--text-faint)' }}>Our cost</span>
                  ),
              },
              {
                key: 'entry',
                header: 'Entered',
                render: (e) =>
                  e.entry_mode === 'ADMIN_ON_BEHALF' ? (
                    <Badge tone="neutral">By the office</Badge>
                  ) : (
                    <span style={{ color: 'var(--text-faint)' }}>By the driver</span>
                  ),
              },
              {
                key: 'receipt',
                header: 'Receipt',
                render: (e) =>
                  e.receipt_photo_url ? (
                    <a
                      href={e.receipt_photo_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[12px] underline underline-offset-2"
                      style={{ color: 'var(--info)' }}
                    >
                      View
                    </a>
                  ) : (
                    <span style={{ color: 'var(--text-faint)' }}>None</span>
                  ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (e) => (
                  <div>
                    <Badge tone={TONE[e.approval_status] ?? 'neutral'}>
                      {e.approval_status.toLowerCase()}
                    </Badge>
                    {e.rejection_reason ? (
                      <p className="mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        {e.rejection_reason}
                      </p>
                    ) : null}
                  </div>
                ),
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (e) =>
                  e.approval_status === 'PENDING' ? (
                    <div className="flex justify-end gap-1.5">
                      <Button
                        size="sm"
                        icon={<Check className="size-3.5" />}
                        loading={decide.isPending && decide.variables?.id === e.id}
                        onClick={() => {
                          setError(null)
                          decide.mutate({ id: e.id, approve: true })
                        }}
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<X className="size-3.5" />}
                        onClick={() => setRejecting(e)}
                      >
                        Reject
                      </Button>
                    </div>
                  ) : null,
              },
            ]}
          />
        )}
      </Card>

      <RejectModal
        expense={rejecting}
        onClose={() => setRejecting(null)}
        busy={decide.isPending}
        onReject={(reason) =>
          rejecting && decide.mutate({ id: rejecting.id, approve: false, reason })
        }
      />
    </div>
  )
}

function RejectModal({
  expense,
  onClose,
  busy,
  onReject,
}: {
  expense: Expense | null
  onClose: () => void
  busy: boolean
  onReject: (reason: string) => void
}) {
  const [reason, setReason] = useState('')

  return (
    <Modal
      open={!!expense}
      onClose={onClose}
      title="Reject this expense"
      description="The driver is shown the reason, so make it something he can act on."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          onReject(reason)
          setReason('')
        }}
      >
        {expense ? (
          <p className="inset px-3.5 py-2.5 text-[13px]">
            {expense.type.replaceAll('_', ' ').toLowerCase()} ·{' '}
            <span className="tnum font-medium">{rupees(expense.amount)}</span> ·{' '}
            {expense.trip_no}
          </p>
        ) : null}

        <Field label="Reason">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="No receipt attached"
            required
            minLength={3}
            autoFocus
          />
        </Field>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" loading={busy}>
            Reject
          </Button>
        </div>
      </form>
    </Modal>
  )
}
