import { Printer, ScanBarcode } from 'lucide-react'

import { QrCode } from '@/components/QrCode'
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

interface Label {
  barcode: string
  point_sequence: number
  point_colour: string
  consignee_name: string
  city: string | null
  vendor_bill_no: string
  item_no: number
  of_total: number
  item_name: string | null
  trip_no: string
  lr_no: string | null
  floor_number: number
}

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

/* The sticker itself. Ordered by what a loader actually uses: the colour band
   and point number first, the customer second, the bill and box number third,
   the code last. */
function LabelCard({ label }: { label: Label }) {
  return (
    <div
      className="label-card relative overflow-hidden bg-white text-black"
      style={{ border: '1px solid #111', borderRadius: 6 }}
    >
      <div className="flex items-stretch">
        <div
          className="flex w-[74px] shrink-0 flex-col items-center justify-center py-3 text-white"
          style={{ background: label.point_colour }}
        >
          <span className="text-[9px] tracking-[0.18em] uppercase opacity-90">Point</span>
          <span className="text-[40px] leading-none font-extrabold">{label.point_sequence}</span>
          {label.floor_number > 0 ? (
            <span className="mt-1 text-[9px] tracking-wider uppercase opacity-90">
              Floor {label.floor_number}
            </span>
          ) : null}
        </div>

        <div className="min-w-0 flex-1 px-3 py-2.5">
          <p className="truncate text-[15px] leading-tight font-bold uppercase">
            {label.consignee_name}
          </p>
          {label.city ? (
            <p className="truncate text-[11px] text-neutral-600 uppercase">{label.city}</p>
          ) : null}

          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className="text-[12px] font-semibold">Bill {label.vendor_bill_no}</span>
            <span className="text-[17px] leading-none font-extrabold">
              {label.item_no}
              <span className="text-[11px] font-medium text-neutral-500">
                {' '}
                of {label.of_total}
              </span>
            </span>
          </div>

          {label.item_name ? (
            <p className="mt-1 truncate text-[11px] text-neutral-700">{label.item_name}</p>
          ) : null}

          <div className="mt-2 flex items-center justify-between border-t border-neutral-300 pt-1.5">
            <span className="font-mono text-[10px] tracking-tight">{label.barcode}</span>
            <span className="text-[9px] text-neutral-500">
              {label.trip_no}
              {label.lr_no ? ` · LR ${label.lr_no}` : ''}
            </span>
          </div>
        </div>

        {/* The scannable code, at the open edge of the sticker so a driver can
            reach it with a phone without lifting the carton. The same value is
            printed as text beside it: when a camera will not focus in a dark
            lorry, somebody still has to be able to read it out. */}
        <div className="flex shrink-0 items-center justify-center bg-white px-2 py-2">
          <QrCode value={label.barcode} size={58} />
        </div>
      </div>
    </div>
  )
}
