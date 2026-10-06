import { Package, Plus } from 'lucide-react'
import { useCallback, useState } from 'react'

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

export default function ConsignmentsPage() {
  const [open, setOpen] = useState(false)

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
        description="One vendor bill, for one delivery point, covering a number of boxes. Creating a bill generates a box per carton — those are what get labelled and counted at both ends."
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
    </div>
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
