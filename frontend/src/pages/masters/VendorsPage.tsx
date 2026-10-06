import { Building2, Plus, ReceiptIndianRupee, Warehouse } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

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
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type {
  GoodsCategory,
  RateCard,
  Vendor,
  VendorDivision,
  Warehouse as Wh,
} from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function VendorsPage() {
  const [selected, setSelected] = useState<Vendor | null>(null)
  const [open, setOpen] = useState<'vendor' | 'division' | 'warehouse' | null>(null)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen('vendor'), []))

  const vendors = useList<Vendor>('/vendors')
  const divisions = useList<VendorDivision>('/vendor-divisions')
  const warehouses = useList<Wh>('/warehouses')

  const rateCards = useList<RateCard>('/rate-cards')

  const vendorDivisions = divisions.data?.filter((d) => d.vendor_id === selected?.id) ?? []
  const vendorWarehouses = warehouses.data?.filter((w) => w.vendor_id === selected?.id) ?? []

  const divisionIds = new Set(vendorDivisions.map((d) => d.id))
  const vendorRateCards =
    rateCards.data?.filter((c) => divisionIds.has(c.vendor_division_id)) ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        description="Rate cards attach to a division, not to the vendor — Godrej OCP and Godrej Appliance Spare price differently."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen('vendor')}>
            New vendor
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {vendors.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={vendors.data ?? []}
            rowKey={(v) => v.id}
            onRowClick={setSelected}
            empty={
              <EmptyState
                icon={<Building2 className="size-7" />}
                title="No vendors yet"
                description="Create the vendor first, then add its divisions — that is where rates live."
                action={<Button onClick={() => setOpen('vendor')}>New vendor</Button>}
              />
            }
            columns={[
              { key: 'name', header: 'Vendor', render: (v) => <span className="font-medium">{v.name}</span> },
              { key: 'gstin', header: 'GSTIN', render: (v) => v.gstin ?? '—' },
              { key: 'contact', header: 'Contact', render: (v) => v.contact_phone ?? '—' },
              {
                key: 'divisions',
                header: 'Divisions',
                align: 'right',
                render: (v) => divisions.data?.filter((d) => d.vendor_id === v.id).length ?? 0,
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/vendors'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Vendor"
                    fields={[
                      { name: 'name', label: 'Vendor name', required: true },
                      { name: 'gstin', label: 'GSTIN' },
                      { name: 'contact_person', label: 'Contact person' },
                      { name: 'contact_phone', label: 'Contact phone', kind: 'tel' as const },
                      { name: 'payment_terms_days', label: 'Payment terms (days)', kind: 'number' as const },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      {selected ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3.5">
              <div>
                <h2 className="text-sm font-semibold">Divisions</h2>
                <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  {selected.name}
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => setOpen('division')}>
                Add
              </Button>
            </div>
            <Table
              rows={vendorDivisions}
              rowKey={(d) => d.id}
              empty={
                <EmptyState
                  title="No divisions"
                  description="A freight is billed against a division, so at least one is needed."
                />
              }
              columns={[
                { key: 'name', header: 'Name', render: (d) => d.name },
                { key: 'code', header: 'Code', render: (d) => <span className="tnum">{d.code}</span> },
                { key: 'gst', header: 'GST', align: 'right', render: (d) => `${d.gst_rate_percent}%` },
              ]}
            />
          </Card>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3.5">
              <div>
                <h2 className="text-sm font-semibold">Warehouses</h2>
                <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  Freights start and finish here
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => setOpen('warehouse')}>
                Add
              </Button>
            </div>
            <Table
              rows={vendorWarehouses}
              rowKey={(w) => w.id}
              empty={
                <EmptyState
                  icon={<Warehouse className="size-7" />}
                  title="No warehouses"
                  description="A freight needs an origin, and returning to it is what closes the odometer loop."
                />
              }
              columns={[
                { key: 'name', header: 'Name', render: (w) => w.name },
                { key: 'code', header: 'Code', render: (w) => w.code },
              ]}
            />
          </Card>

          {/* Rates live on the division, but they belong in the vendor's own
              view - otherwise you have to remember which division carries
              which price. */}
          <Card className="overflow-hidden lg:col-span-2">
            <div className="flex items-center justify-between px-4 py-3.5">
              <div>
                <h2 className="text-sm font-semibold">Rate cards</h2>
                <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  What {selected.name} is charged, per division and per date
                </p>
              </div>
              <Link to="/rate-cards">
                <Button size="sm" variant="secondary">
                  Manage
                </Button>
              </Link>
            </div>
            <Table
              rows={vendorRateCards}
              rowKey={(c) => c.id}
              empty={
                <EmptyState
                  icon={<ReceiptIndianRupee className="size-7" />}
                  title="No rate cards"
                  description="A freight cannot be priced until its division has a card covering the freight's date."
                />
              }
              columns={[
                {
                  key: 'division',
                  header: 'Division',
                  render: (c) => (
                    <span className="font-medium">
                      {vendorDivisions.find((d) => d.id === c.vendor_division_id)?.name ?? '—'}
                    </span>
                  ),
                },
                {
                  key: 'effective',
                  header: 'Effective',
                  render: (c) => (
                    <span className="tnum">
                      {c.effective_from} → {c.effective_to ?? 'open'}
                    </span>
                  ),
                },
                {
                  key: 'base',
                  header: 'Base freight',
                  align: 'right',
                  render: (c) => rupees(c.base_trip_amount),
                },
                {
                  key: 'km',
                  header: 'Distance',
                  align: 'right',
                  render: (c) => (
                    <span className="tnum">
                      {c.included_km} km free, then {rupees(c.extra_km_rate)}/km
                    </span>
                  ),
                },
                {
                  key: 'points',
                  header: 'Points',
                  align: 'right',
                  render: (c) => (
                    <span className="tnum">
                      {Number(c.base_point_charge) > 0
                        ? `${rupees(c.base_point_charge)} covers `
                        : ''}
                      {c.included_points}, then {rupees(c.extra_point_rate)}/pt
                    </span>
                  ),
                },
                {
                  key: 'unloading',
                  header: 'Unloading',
                  render: (c) => (
                    <Badge tone={c.unloading_basis === 'NOT_APPLICABLE' ? 'neutral' : 'info'}>
                      {c.unloading_basis === 'NOT_APPLICABLE'
                        ? 'not billed'
                        : c.unloading_basis.replaceAll('_', ' ').toLowerCase()}
                    </Badge>
                  ),
                },
              ]}
            />
          </Card>
        </div>
      ) : vendors.data?.length ? (
        <p className="px-1 text-[13px]" style={{ color: 'var(--text-faint)' }}>
          Select a vendor to see its divisions, warehouses and rate cards.
        </p>
      ) : null}

      <VendorForm open={open === 'vendor'} onClose={() => setOpen(null)} />
      {selected ? (
        <>
          <DivisionForm
            open={open === 'division'}
            onClose={() => setOpen(null)}
            vendor={selected}
          />
          <WarehouseForm
            open={open === 'warehouse'}
            onClose={() => setOpen(null)}
            vendor={selected}
          />
        </>
      ) : null}
    </div>
  )
}

function VendorForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState({ name: '', gstin: '', contact_person: '', contact_phone: '' })
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<typeof form>('/vendors', {
    onSuccess: () => {
      setForm({ name: '', gstin: '', contact_person: '', contact_phone: '' })
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New vendor">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(form, { onError: (err) => setError(apiErrorMessage(err)) })
        }}
      >
        <Field label="Vendor name">
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Godrej"
            required
          />
        </Field>
        <Field label="GSTIN" hint="Optional — needed before invoices are issued">
          <Input
            value={form.gstin}
            onChange={(e) => setForm({ ...form, gstin: e.target.value })}
            placeholder="32AAACG0000A1Z5"
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Contact person">
            <Input
              value={form.contact_person}
              onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
            />
          </Field>
          <Field label="Contact phone">
            <Input
              value={form.contact_phone}
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            />
          </Field>
        </div>
        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create vendor
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function DivisionForm({
  open,
  onClose,
  vendor,
}: {
  open: boolean
  onClose: () => void
  vendor: Vendor
}) {
  const categories = useList<GoodsCategory>('/goods-categories')
  const [form, setForm] = useState({
    name: '',
    code: '',
    goods_category_id: '',
    gst_rate_percent: '12',
    invoice_series: '191',
  })
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/vendor-divisions', {
    onSuccess: () => {
      setForm({ name: '', code: '', goods_category_id: '', gst_rate_percent: '12', invoice_series: '191' })
      onClose()
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New division"
      description={`Under ${vendor.name}. Rate cards attach to the division.`}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              vendor_id: vendor.id,
              name: form.name,
              code: form.code.toUpperCase(),
              goods_category_id: form.goods_category_id || null,
              gst_rate_percent: form.gst_rate_percent,
              invoice_series: form.invoice_series,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Division name">
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Godrej Appliance Spare"
            required
          />
        </Field>
        <Field label="Code" hint="Short identifier, used on invoices">
          <Input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="GODREJ-APPLIANCE-SPARE"
            required
          />
        </Field>
        <Field label="Goods category" hint="Drives whether unloading is billed">
          <Select
            value={form.goods_category_id}
            onChange={(e) => setForm({ ...form, goods_category_id: e.target.value })}
          >
            <option value="">Not set</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Invoice series">
            <Input
              value={form.invoice_series}
              onChange={(e) => setForm({ ...form, invoice_series: e.target.value })}
            />
          </Field>
          <Field label="GST rate %">
            <Input
              type="number"
              step="0.01"
              value={form.gst_rate_percent}
              onChange={(e) => setForm({ ...form, gst_rate_percent: e.target.value })}
            />
          </Field>
        </div>
        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create division
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function WarehouseForm({
  open,
  onClose,
  vendor,
}: {
  open: boolean
  onClose: () => void
  vendor: Vendor
}) {
  const [form, setForm] = useState({ name: '', code: '', address: '', latitude: '', longitude: '' })
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/warehouses', {
    onSuccess: () => {
      setForm({ name: '', code: '', address: '', latitude: '', longitude: '' })
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New warehouse" description={vendor.name}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              vendor_id: vendor.id,
              name: form.name,
              code: form.code.toUpperCase(),
              address: form.address || null,
              latitude: form.latitude || null,
              longitude: form.longitude || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Warehouse name">
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Godrej Warehouse, Ernakulam"
            required
          />
        </Field>
        <Field label="Code">
          <Input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="GODREJ-EKM"
            required
          />
        </Field>
        <Field label="Address">
          <Input
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Latitude" hint="Optional">
            <Input
              className="tnum"
              value={form.latitude}
              onChange={(e) => setForm({ ...form, latitude: e.target.value })}
              placeholder="10.0159"
            />
          </Field>
          <Field label="Longitude">
            <Input
              className="tnum"
              value={form.longitude}
              onChange={(e) => setForm({ ...form, longitude: e.target.value })}
              placeholder="76.3419"
            />
          </Field>
        </div>
        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create warehouse
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function GoodsCategoryBadge({ name }: { name: string | null }) {
  return name ? <Badge>{name}</Badge> : <span style={{ color: 'var(--text-faint)' }}>—</span>
}
