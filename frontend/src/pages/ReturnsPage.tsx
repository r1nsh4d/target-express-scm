import { useMutation, useQueryClient } from '@tanstack/react-query'
import { PackageX, Undo2 } from 'lucide-react'
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
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { useList } from '@/lib/resources'

/* Cartons that came back.
 *
 * The reconciliation has always counted returns — loaded minus delivered minus
 * returned is what says whether anything is genuinely missing. With no way to
 * record one, every carton that came back counted as unaccounted, and
 * "unaccounted" should mean a box nobody can find rather than one sitting in
 * the godown with a reason attached to it.
 *
 * Recorded by sticker, because that is what the person at the godown door has
 * in their hand, and against individual cartons because that is how they come
 * back — three of a bill's six, not all or nothing.
 */

interface ReturnedBox {
  box_id: string
  barcode: string
  item_no: number
  item_name: string | null
  status: string
  reason: string | null
  returned_at: string | null
  returned_by: string | null
  vendor_bill_no: string
  consignee_name: string | null
  trip_no: string | null
  trip_date: string | null
}

interface Summary {
  returned_to_warehouse: number
  damaged: number
  not_delivered: number
  total: number
  by_customer: { name: string; count: number }[]
}

const WHAT_HAPPENED: Record<string, { label: string; tone: 'warning' | 'danger' | 'neutral' }> = {
  RETURNED_TO_WAREHOUSE: { label: 'Came back', tone: 'warning' },
  DAMAGED: { label: 'Damaged', tone: 'danger' },
  NOT_DELIVERED: { label: 'Not delivered', tone: 'neutral' },
}

export default function ReturnsPage() {
  const today = new Date()
  const monthAgo = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate())

  const [from, setFrom] = useState(monthAgo.toISOString().slice(0, 10))
  const [to, setTo] = useState(today.toISOString().slice(0, 10))
  const [recording, setRecording] = useState(false)

  const params = { period_from: from, period_to: to }
  const rows = useList<ReturnedBox>('/returns', params)
  const summary = useList<Summary>('/returns/summary', params)

  const data = rows.data ?? []
  const s = summary.data as unknown as Summary | undefined

  return (
    <div className="space-y-6">
      <PageHeader
        description="Cartons that did not stay at the point — refused, damaged, or nobody there to take them. Recorded against the sticker, with the reason, so the count balances and the vendor can be told which ones."
        action={
          <Button icon={<Undo2 className="size-4" />} onClick={() => setRecording(true)}>
            Record a return
          </Button>
        }
      />

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

      {s && s.total ? (
        <div className="grid gap-3 sm:grid-cols-4">
          <Figure label="Came back" value={s.returned_to_warehouse} />
          <Figure label="Damaged" value={s.damaged} danger={s.damaged > 0} />
          <Figure label="Not delivered" value={s.not_delivered} />
          <Figure label="Total cartons" value={s.total} strong />
        </div>
      ) : null}

      {/* Where returns cluster. One customer refusing repeatedly is a
          conversation to have; the same number spread across twenty customers
          is just a month's work. The list is useless for telling those apart,
          so the top few are pulled out. */}
      {s && s.by_customer.length > 1 ? (
        <Card className="p-4">
          <h3 className="text-[14px] font-semibold">Where they came from</h3>
          <div className="mt-2.5 space-y-1.5">
            {s.by_customer.map((c) => (
              <div key={c.name} className="flex items-center gap-3">
                <span className="w-44 shrink-0 truncate text-[13px]">{c.name}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: 'var(--surface)' }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(c.count / s.by_customer[0].count) * 100}%`,
                      background: 'var(--warning)',
                    }}
                  />
                </div>
                <span className="tnum w-8 shrink-0 text-right text-[12px]">{c.count}</span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card className="overflow-hidden">
        {rows.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={data}
            rowKey={(r) => r.box_id}
            empty={
              <EmptyState
                icon={<PackageX className="size-7" />}
                title="Nothing came back in this period"
                description="When a carton is refused, damaged or cannot be delivered, record it here so it stops counting as missing."
              />
            }
            columns={[
              {
                key: 'when',
                header: 'Recorded',
                render: (r) => (
                  <span className="tnum">{r.returned_at?.slice(0, 10) ?? '—'}</span>
                ),
              },
              {
                key: 'what',
                header: 'What happened',
                render: (r) => {
                  const w = WHAT_HAPPENED[r.status] ?? { label: r.status, tone: 'neutral' as const }
                  return <Badge tone={w.tone}>{w.label}</Badge>
                },
              },
              {
                key: 'box',
                header: 'Carton',
                render: (r) => (
                  <div>
                    <div className="font-mono text-[12px]">{r.barcode}</div>
                    <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                      {r.item_name ?? '—'} · box {r.item_no}
                    </div>
                  </div>
                ),
              },
              { key: 'bill', header: 'Bill', render: (r) => r.vendor_bill_no || '—' },
              { key: 'who', header: 'Customer', render: (r) => r.consignee_name ?? '—' },
              { key: 'trip', header: 'Trip', render: (r) => r.trip_no ?? '—' },
              {
                key: 'why',
                header: 'Reason',
                render: (r) => (
                  <span className="block max-w-[18rem] text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                    {r.reason ?? '—'}
                  </span>
                ),
              },
            ]}
          />
        )}
      </Card>

      <RecordReturn open={recording} onClose={() => setRecording(false)} />
    </div>
  )
}

function Figure({
  label,
  value,
  strong,
  danger,
}: {
  label: string
  value: number
  strong?: boolean
  danger?: boolean
}) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </p>
      <p
        className={`tnum mt-1 ${strong ? 'text-[22px] font-semibold' : 'text-[18px] font-medium'}`}
        style={danger ? { color: 'var(--danger)' } : undefined}
      >
        {value}
      </p>
    </Card>
  )
}

/* Recording them.
 *
 * One sticker per line, because a scanner types a code and then Enter, so a
 * textarea with a scanner pointed at it fills itself. Nothing here needs the
 * person to find a trip or a bill first: the sticker already knows which
 * carton it is, and the screen looks the rest up. */
function RecordReturn({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [codes, setCodes] = useState('')
  const [status, setStatus] = useState('RETURNED_TO_WAREHOUSE')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{
    recorded: ReturnedBox[]
    unknown: string[]
    already: string[]
  } | null>(null)

  const barcodes = codes
    .split(/[\n,;\t]+/)
    .map((c) => c.trim())
    .filter(Boolean)

  const record = useMutation({
    mutationFn: async () =>
      (await api.post('/returns', { barcodes, status, reason })).data as {
        recorded: ReturnedBox[]
        unknown: string[]
        already: string[]
      },
    onSuccess: (r) => {
      setResult(r)
      setCodes('')
      queryClient.invalidateQueries({ queryKey: ['/returns'] })
      queryClient.invalidateQueries({ queryKey: ['/returns/summary'] })
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  function close() {
    setResult(null)
    setError(null)
    setReason('')
    setCodes('')
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={close}
      wide
      title="Record a return"
      description="Scan or type the stickers on the cartons that came back. One per line."
    >
      <div className="space-y-4">
        <Field
          label="Stickers"
          hint={barcodes.length ? `${barcodes.length} carton${barcodes.length === 1 ? '' : 's'}` : 'A scanner types the code and presses Enter, so you can simply scan them all'}
        >
          <Textarea
            rows={6}
            className="font-mono text-[13px]"
            placeholder={'TE-A3F91C-001\nTE-A3F91C-002'}
            value={codes}
            onChange={(e) => setCodes(e.target.value)}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="What happened">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="RETURNED_TO_WAREHOUSE">Came back to the warehouse</option>
              <option value="DAMAGED">Damaged</option>
              <option value="NOT_DELIVERED">Could not be delivered</option>
            </Select>
          </Field>
          <Field label="Reason" hint="What the vendor will be told">
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Refused — wrong model sent"
            />
          </Field>
        </div>

        {result ? (
          <div className="inset space-y-1.5 px-3.5 py-3 text-[13px]">
            <p style={{ color: 'var(--success)' }}>
              {result.recorded.length} carton{result.recorded.length === 1 ? '' : 's'} recorded.
            </p>
            {result.already.length ? (
              <p style={{ color: 'var(--text-muted)' }}>
                {result.already.length} already recorded earlier, left as they were:{' '}
                {result.already.join(', ')}
              </p>
            ) : null}
            {result.unknown.length ? (
              <p style={{ color: 'var(--warning)' }}>
                Not ours, or the sticker was misread: {result.unknown.join(', ')}
              </p>
            ) : null}
          </div>
        ) : null}

        <ErrorNote>{error}</ErrorNote>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close}>
            {result ? 'Done' : 'Cancel'}
          </Button>
          <Button
            disabled={!barcodes.length || reason.trim().length < 3}
            loading={record.isPending}
            onClick={() => {
              setError(null)
              setResult(null)
              record.mutate()
            }}
          >
            Record {barcodes.length || ''} return{barcodes.length === 1 ? '' : 's'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
