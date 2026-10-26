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
} from '@/components/ui'
import { byName, useFilters } from '@/components/Filters'
import { Fact, Facts, TileGrid, TileHead } from '@/components/TileGrid'
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

  const all = vendors.data ?? []
  const view = useFilters<Vendor>({
    rows: all,
    placeholder: 'Search vendors',
    search: (v) => [v.name, v.gstin, v.contact_person, v.contact_phone],
    filters: [
      {
        // A vendor with no GSTIN cannot be invoiced, which is worth being
        // able to see on its own rather than reading down a column.
        key: 'gstin',
        label: 'GSTIN',
        choices: [
          { value: 'missing', label: 'not on file' },
          { value: 'present', label: 'on file' },
        ],
        matches: (v, value) => (value === 'present' ? !!v.gstin : !v.gstin),
      },
    ],
    sorts: [{ key: 'name', label: 'A to Z', compare: byName<Vendor>((v) => v.name) }],
  })

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

      {view.controls}

      {vendors.isLoading ? (
        <Card>
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        </Card>
      ) : (
        <TileGrid
          rows={view.rows}
          rowKey={(v) => v.id}
          onRowClick={(v) => setSelected(selected?.id === v.id ? null : v)}
          selected={(v) => v.id === selected?.id}
          empty={
            <EmptyState
              icon={<Building2 className="size-7" />}
              title="No vendors yet"
              description="Create the vendor first, then add its divisions — that is where rates live."
              action={<Button onClick={() => setOpen('vendor')}>New vendor</Button>}
            />
          }
          render={(v) => {
            const count = divisions.data?.filter((d) => d.vendor_id === v.id).length ?? 0

            return (
              <>
                <TileHead
                  title={v.name}
                  sub={v.contact_person ?? 'No contact on file'}
                  actions={
                    <RowActions
                      path={'/vendors'}
                      row={v as unknown as Record<string, unknown> & { id: string }}
                      label="Vendor"
                      fields={[
                        { name: 'name', label: 'Vendor name', required: true },
                        { name: 'gstin', label: 'GSTIN' },
                        { name: 'contact_person', label: 'Contact person' },
                        { name: 'contact_phone', label: 'Contact phone', kind: 'tel' as const },
                        {
                          name: 'payment_terms_days',
                          label: 'Payment terms (days)',
                          kind: 'number' as const,
                        },
                      ]}
                    />
                  }
                />
                <Facts>
                  <Fact
                    label="GSTIN"
                    value={<span className="tnum">{v.gstin ?? 'Not on file'}</span>}
                    // An invoice cannot be issued without it, so a blank one
                    // is a thing to fix rather than a blank cell.
                    tone={v.gstin ? undefined : 'warning'}
                  />
                  <Fact label="Phone" value={<span className="tnum">{v.contact_phone ?? '—'}</span>} />
                  <Fact
                    label="Divisions"
                    value={<span className="tnum">{count}</span>}
                    tone={count ? undefined : 'warning'}
                  />
                </Facts>
              </>
            )
          }}
        />
      )}

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
            {vendorDivisions.length ? (
              <div className="grid gap-2 px-4 pb-4 sm:grid-cols-2">
                {vendorDivisions.map((d) => (
                  <div
                    key={d.id}
                    className="rounded-[11px] border p-3"
                    style={{ background: 'var(--bg-elevated)' }}
                  >
                    <p className="truncate text-[13.5px] font-medium">{d.name}</p>
                    <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {d.code} · GST {d.gst_rate_percent}%
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                compact
                title="No divisions"
                description="A freight is billed against a division, so at least one is needed."
              />
            )}
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
            {vendorWarehouses.length ? (
              <div className="grid gap-2 px-4 pb-4 sm:grid-cols-2">
                {vendorWarehouses.map((w) => (
                  <div
                    key={w.id}
                    className="flex items-center gap-2.5 rounded-[11px] border p-3"
                    style={{ background: 'var(--bg-elevated)' }}
                  >
                    <Warehouse className="size-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
                    <div className="min-w-0">
                      <p className="truncate text-[13.5px] font-medium">{w.name}</p>
                      <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                        {w.code}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                compact
                icon={<Warehouse className="size-7" />}
                title="No warehouses"
                description="A freight needs an origin, and returning to it is what closes the odometer loop."
              />
            )}
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
            {vendorRateCards.length ? (
              <div className="grid gap-3 px-4 pb-4 lg:grid-cols-2">
                {vendorRateCards.map((c) => (
                  <div
                    key={c.id}
                    className="rounded-[12px] border p-3.5"
                    style={{ background: 'var(--bg-elevated)' }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-[13.5px] font-medium">
                          {vendorDivisions.find((d) => d.id === c.vendor_division_id)?.name ?? '—'}
                        </p>
                        <p className="tnum mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                          {c.effective_from} → {c.effective_to ?? 'open'}
                        </p>
                      </div>
                      <Badge tone={c.unloading_basis === 'NOT_APPLICABLE' ? 'neutral' : 'info'}>
                        {c.unloading_basis === 'NOT_APPLICABLE'
                          ? 'unloading not billed'
                          : c.unloading_basis.replaceAll('_', ' ').toLowerCase()}
                      </Badge>
                    </div>

                    {/* The three numbers that price a trip, in the order the
                        calculation uses them. */}
                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <Fact label="Base" value={rupees(c.base_trip_amount)} />
                      <Fact
                        label="Distance"
                        value={
                          <span className="tnum">
                            {c.included_km} km, then {rupees(c.extra_km_rate)}/km
                          </span>
                        }
                      />
                      <Fact
                        label="Points"
                        value={
                          <span className="tnum">
                            {c.included_points}, then {rupees(c.extra_point_rate)}/pt
                          </span>
                        }
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                compact
                icon={<ReceiptIndianRupee className="size-7" />}
                title="No rate cards"
                description="A freight cannot be priced until its division has a card covering the freight's date."
              />
            )}
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
