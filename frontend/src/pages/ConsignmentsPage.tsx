import { Package, Plus, Printer, ScanBarcode } from 'lucide-react'
import { useCallback, useState } from 'react'

import type { Label } from '@/components/LabelCard'
import { LabelCard } from '@/components/LabelCard'
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
import { apiErrorMessage } from '@/lib/api'
import type { Consignee, VendorDivision, Warehouse } from '@/lib/resources'
import { STATUS_TONE, useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

interface Consignment {
  id: string
  vendor_division_id: string
  consignee_id: string
  consignee_name: string | null
  vendor_bill_no: string
  bill_date: string
  declared_box_count: number
  status: string
  freight_point_id: string | null
}

interface Box {
  id: string
  item_no: number
  barcode: string
  item_code: string | null
  item_name: string | null
  status: string
}

export default function ConsignmentsPage() {
  const [open, setOpen] = useState(false)
  // The bill whose stickers are being looked at. Clicking a row opens them,
  // because "which cartons are on this bill, and what is pasted on them" is
  // the question the row itself cannot answer.
  const [showing, setShowing] = useState<Consignment | null>(null)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen(true), []))
  const [division, setDivision] = useState('')
  const [unassignedOnly, setUnassignedOnly] = useState(false)

  const divisions = useList<VendorDivision>('/vendor-divisions')
  const consignments = useList<Consignment>('/consignments', {
    ...(division ? { vendor_division_id: division } : {}),
    ...(unassignedOnly ? { unassigned: true } : {}),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        description="One vendor bill, for one delivery point, covering a number of boxes. Creating a bill generates a box per carton — those are what get labelled and counted at both ends. Click a bill to see its stickers and reprint one."
        action={
          <Button
            icon={<Plus className="size-4" />}
            onClick={() => setOpen(true)}
            disabled={!divisions.data?.length}
          >
            New consignment
          </Button>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[16rem]">
          <Field label="Vendor division">
            <Select value={division} onChange={(e) => setDivision(e.target.value)}>
              <option value="">All divisions</option>
              {divisions.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button
          variant={unassignedOnly ? 'primary' : 'secondary'}
          onClick={() => setUnassignedOnly((v) => !v)}
        >
          Not yet on a freight
        </Button>
      </div>

      <Card className="overflow-hidden">
        {consignments.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={consignments.data ?? []}
            rowKey={(c) => c.id}
            onRowClick={(c) => setShowing(c)}
            empty={
              <EmptyState
                icon={<Package className="size-7" />}
                title="No consignments"
                description={
                  divisions.data?.length
                    ? "Enter the day's bills here, then group them onto a freight."
                    : 'Create a vendor and a division first.'
                }
              />
            }
            columns={[
              {
                key: 'bill',
                header: 'Bill no',
                render: (c) => <span className="font-medium">{c.vendor_bill_no}</span>,
              },
              { key: 'date', header: 'Date', render: (c) => <span className="tnum">{c.bill_date}</span> },
              { key: 'to', header: 'Customer', render: (c) => c.consignee_name ?? '—' },
              {
                key: 'boxes',
                header: 'Boxes',
                align: 'right',
                render: (c) => <span className="tnum">{c.declared_box_count}</span>,
              },
              {
                key: 'assigned',
                header: 'On a freight',
                render: (c) =>
                  c.freight_point_id ? (
                    <Badge tone="success">Yes</Badge>
                  ) : (
                    <Badge tone="warning">Waiting</Badge>
                  ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (c) => (
                  <Badge tone={STATUS_TONE[c.status] ?? 'neutral'}>
                    {c.status.replace('_', ' ')}
                  </Badge>
                ),
              },
            ]}
          />
        )}
      </Card>

      <ConsignmentForm
        open={open}
        onClose={() => setOpen(false)}
        divisions={divisions.data ?? []}
      />

      <StickerSheet consignment={showing} onClose={() => setShowing(null)} />
    </div>
  )
}

/* The stickers on one bill.
   Two jobs. The first is simply to answer "what is pasted on these cartons" —
   the row says four boxes, this says which four and what each one reads. The
   second is the reprint: a label torn off in the lorry, or a bill that turned
   up after the freight was labelled. Reprinting the whole freight to recover
   one sticker wastes a sheet and puts duplicates in the godown. */
function StickerSheet({
  consignment,
  onClose,
}: {
  consignment: Consignment | null
  onClose: () => void
}) {
  const id = consignment?.id
  const labels = useList<Label>(`/consignments/${id}/labels`, undefined, !!id)
  // The sticker does not carry a status — a printed label cannot change. The
  // box rows do, which is how you see what has actually been scanned off the
  // vehicle without leaving this screen.
  const boxes = useList<Box>(`/consignments/${id}/boxes`, undefined, !!id)

  const rows = labels.data ?? []
  const statusOf = new Map((boxes.data ?? []).map((b) => [b.barcode, b.status]))
  const onAFreight = rows.length > 0 && rows[0].point_sequence > 0

  return (
    <Modal
      open={!!consignment}
      onClose={onClose}
      wide
      printable
      title={consignment ? `Bill ${consignment.vendor_bill_no}` : ''}
      description={
        consignment
          ? `${consignment.consignee_name ?? 'Customer not named'} · ${
              rows.length || consignment.declared_box_count
            } boxes${onAFreight ? ` · point ${rows[0].point_sequence} on ${rows[0].trip_no}` : ''}`
          : undefined
      }
    >
      {labels.isLoading || boxes.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner className="size-5" />
        </div>
      ) : !rows.length ? (
        <EmptyState
          icon={<ScanBarcode className="size-7" />}
          title="No boxes on this bill"
          description="A bill normally generates one box per carton when it is created. This one has none, so there is nothing to label."
        />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
            <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              {onAFreight
                ? 'These are the same stickers the freight print produces — a reprint is identical, so it cannot be confused with the original.'
                : 'This bill is not on a freight yet, so the point number and trip are blank. Put it on a freight before labelling, or the carton sorts to nowhere.'}
            </p>
            <Button
              variant="secondary"
              icon={<Printer className="size-4" />}
              onClick={() => window.print()}
            >
              Print {rows.length === 1 ? 'the sticker' : `${rows.length} stickers`}
            </Button>
          </div>

          <div className="label-sheet grid grid-cols-1 gap-3 lg:grid-cols-2">
            {rows.map((label) => (
              <div key={label.barcode} className="space-y-1">
                <LabelCard label={label} />
                {/* Screen only. A status printed on a sticker would be a lie
                    the moment the carton moves. */}
                <p
                  className="px-1 text-[11px] print:hidden"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {(statusOf.get(label.barcode) ?? '—').replace(/_/g, ' ').toLowerCase()}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}

function ConsignmentForm({
  open,
  onClose,
  divisions,
}: {
  open: boolean
  onClose: () => void
  divisions: VendorDivision[]
}) {
  const blank = {
    vendor_division_id: '',
    warehouse_id: '',
    consignee_id: '',
    vendor_bill_no: '',
    bill_date: new Date().toISOString().slice(0, 10),
    box_count: '1',
    item_name: '',
    eway_bill_no: '',
    remarks: '',
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const vendorId = divisions.find((d) => d.id === form.vendor_division_id)?.vendor_id
  const warehouses = useList<Warehouse>(
    '/warehouses',
    vendorId ? { vendor_id: vendorId } : undefined,
    !!vendorId,
  )
  const consignees = useList<Consignee>('/consignees')

  const create = useCreate<Record<string, unknown>>('/consignments', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="New consignment"
      description="One bill, one customer. A box row is generated for every carton, with its own label code."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              vendor_division_id: form.vendor_division_id,
              warehouse_id: form.warehouse_id,
              consignee_id: form.consignee_id,
              vendor_bill_no: form.vendor_bill_no,
              bill_date: form.bill_date,
              box_count: Number(form.box_count) || 1,
              item_name: form.item_name || null,
              item_code: form.item_name ? form.item_name.toUpperCase().replace(/\s+/g, '_') : null,
              eway_bill_no: form.eway_bill_no || null,
              remarks: form.remarks || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Vendor division">
            <Select
              value={form.vendor_division_id}
              onChange={(e) =>
                setForm({ ...form, vendor_division_id: e.target.value, warehouse_id: '' })
              }
              required
            >
              <option value="">Select</option>
              {divisions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Loading warehouse">
            <Select
              value={form.warehouse_id}
              onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}
              required
              disabled={!vendorId}
            >
              <option value="">Select</option>
              {warehouses.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Customer" hint="This bill's delivery point">
          <Select
            value={form.consignee_id}
            onChange={(e) => setForm({ ...form, consignee_id: e.target.value })}
            required
          >
            <option value="">Select</option>
            {consignees.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.city ? ` · ${c.city}` : ''}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Vendor bill number">
            <Input
              value={form.vendor_bill_no}
              onChange={(e) => setForm({ ...form, vendor_bill_no: e.target.value })}
              placeholder="4521"
              required
            />
          </Field>
          <Field label="Bill date">
            <Input
              type="date"
              value={form.bill_date}
              onChange={(e) => setForm({ ...form, bill_date: e.target.value })}
              required
            />
          </Field>
          <Field label="Number of boxes" hint="One label per box">
            <Input
              className="tnum"
              type="number"
              min={1}
              max={999}
              value={form.box_count}
              onChange={(e) => setForm({ ...form, box_count: e.target.value })}
              required
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Article" hint="Furniture only — priced per article at unloading">
            <Input
              value={form.item_name}
              onChange={(e) => setForm({ ...form, item_name: e.target.value })}
              placeholder="Chair"
            />
          </Field>
          <Field label="E-way bill number">
            <Input
              value={form.eway_bill_no}
              onChange={(e) => setForm({ ...form, eway_bill_no: e.target.value })}
            />
          </Field>
        </div>

        <Field label="Remarks">
          <Textarea
            value={form.remarks}
            onChange={(e) => setForm({ ...form, remarks: e.target.value })}
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create consignment
          </Button>
        </div>
      </form>
    </Modal>
  )
}
