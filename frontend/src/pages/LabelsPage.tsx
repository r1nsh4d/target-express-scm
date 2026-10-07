import { Printer, ScanBarcode } from 'lucide-react'

import type { Label } from '@/components/LabelCard'
import { LabelCard } from '@/components/LabelCard'
import { useState } from 'react'

import {
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Select,
  Spinner,
  Table,
} from '@/components/ui'
import type { FreightRow } from '@/lib/resources'
import { useList } from '@/lib/resources'

interface SortingRow {
  point_sequence: number
  point_colour: string
  consignee_name: string
  bill_count: number
  box_count: number
}

export default function LabelsPage() {
  const [freightId, setFreightId] = useState('')

  const freights = useList<FreightRow>('/freights', { limit: 60 })
  const sorting = useList<SortingRow>(`/freights/${freightId}/sorting`, undefined, !!freightId)
  const labels = useList<Label>(`/freights/${freightId}/labels`, undefined, !!freightId)

  const rows = labels.data ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        description="Sort the day's boxes by point, then print one sticker per box. Loaders sort by the colour band and the point number long before anyone reads a code — that is why those are the biggest things on the label."
        action={
          rows.length ? (
            <Button icon={<Printer className="size-4" />} onClick={() => window.print()}>
              Print {rows.length} labels
            </Button>
          ) : undefined
        }
      />

      <div className="max-w-md print:hidden">
        <Field label="Freight">
          <Select value={freightId} onChange={(e) => setFreightId(e.target.value)}>
            <option value="">Select a freight</option>
            {freights.data?.map((f) => (
              <option key={f.id} value={f.id}>
                {f.trip_no} · {f.trip_date} · {f.destination_text ?? '—'}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {!freightId ? (
        <Card className="print:hidden">
          <EmptyState
            icon={<ScanBarcode className="size-7" />}
            title="Pick a freight"
            description="Choose the run you are loading and the sorting sheet and labels appear."
          />
        </Card>
      ) : sorting.isLoading || labels.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : (
        <>
          <Card className="overflow-hidden print:hidden">
            <div className="px-4 py-3.5">
              <h2 className="text-sm font-semibold">Sorting sheet</h2>
              <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                How many boxes go to each point, in delivery order.
              </p>
            </div>
            <Table
              rows={sorting.data ?? []}
              rowKey={(r) => String(r.point_sequence)}
              empty={
                <EmptyState
                  title="No consignments on this freight yet"
                  description="Assign bills to each point first — labels are generated from the boxes under them."
                />
              }
              columns={[
                {
                  key: 'point',
                  header: 'Point',
                  render: (r) => (
                    <span className="inline-flex items-center gap-2">
                      <span
                        className="size-3 rounded-full"
                        style={{ background: r.point_colour }}
                        aria-hidden
                      />
                      <span className="tnum font-medium">{r.point_sequence}</span>
                    </span>
                  ),
                },
                { key: 'to', header: 'Customer', render: (r) => r.consignee_name },
                {
                  key: 'bills',
                  header: 'Bills',
                  align: 'right',
                  render: (r) => <span className="tnum">{r.bill_count}</span>,
                },
                {
                  key: 'boxes',
                  header: 'Boxes',
                  align: 'right',
                  render: (r) => <span className="tnum font-medium">{r.box_count}</span>,
                },
              ]}
            />
          </Card>

          {rows.length ? (
            <div>
              <h2 className="eyebrow mb-3 print:hidden">{rows.length} labels</h2>
              <div className="label-sheet grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {rows.map((l) => (
                  <LabelCard key={l.barcode} label={l} />
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
