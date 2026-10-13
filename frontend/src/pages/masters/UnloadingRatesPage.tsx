import { Plus, Sofa } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  Checkbox,
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
import type { VendorDivision } from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'

interface ItemRate {
  id: string
  vendor_division_id: string
  item_code: string
  item_name: string
  base_rate: string
  per_floor_rate: string
  driver_base_rate: string
  driver_per_floor_rate: string
  charge_floors_with_lift: boolean
  max_chargeable_floors: number
  effective_from: string
  effective_to: string | null
  is_active: boolean
}

export default function UnloadingRatesPage() {
  const [open, setOpen] = useState(false)
  const [division, setDivision] = useState('')

  const divisions = useList<VendorDivision>('/vendor-divisions')
  const rates = useList<ItemRate>(
    '/unloading-rates',
    division ? { vendor_division_id: division } : undefined,
  )

  const divisionName = (id: string) => divisions.data?.find((d) => d.id === id)?.name ?? '—'

  return (
    <div className="space-y-6">
      <PageHeader
        description="Two prices for the same article: what the vendor is charged, and what the driver is paid for carrying it. The difference is what Target Express keeps on unloading. Furniture is not unloaded by the box — a chair, a wardrobe and a mattress are different work, and carrying any of them up four floors is different work again — so each article has a ground-floor rate plus a charge per floor, on both sides."
        action={
          <Button
            icon={<Plus className="size-4" />}
            onClick={() => setOpen(true)}
            disabled={!divisions.data?.length}
          >
            New article rate
          </Button>
        }
      />

      <div className="max-w-sm">
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

      <Card className="overflow-hidden">
        {rates.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={rates.data ?? []}
            rowKey={(r) => r.id}
            empty={
              <EmptyState
                icon={<Sofa className="size-7" />}
                title="No article rates"
                description="A furniture division cannot bill unloading until its articles are priced here."
              />
            }
            columns={[
              {
                key: 'item',
                header: 'Article',
                render: (r) => (
                  <div>
                    <div className="font-medium">{r.item_name}</div>
                    <div className="tnum text-[11px]" style={{ color: 'var(--text-faint)' }}>
                      {r.item_code}
                    </div>
                  </div>
                ),
              },
              { key: 'div', header: 'Division', render: (r) => divisionName(r.vendor_division_id) },
              {
                key: 'base',
                header: 'Ground floor',
                align: 'right',
                render: (r) => <span className="tnum">{rupees(r.base_rate)}</span>,
              },
              {
                key: 'floor',
                header: 'Per floor',
                align: 'right',
                render: (r) => <span className="tnum">{rupees(r.per_floor_rate)}</span>,
              },
              {
                key: 'driver',
                header: 'Driver is paid',
                align: 'right',
                render: (r) =>
                  Number(r.driver_base_rate) > 0 ? (
                    <span className="tnum">{rupees(r.driver_base_rate)}</span>
                  ) : (
                    <span className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
                      on a %
                    </span>
                  ),
              },
              {
                /* The number the business actually runs on. Shown beside the
                   two it comes from, so a rate raised on one side and not the
                   other is visible on the same row rather than discovered in a
                   settlement three weeks later. */
                key: 'margin',
                header: 'Margin',
                align: 'right',
                render: (r) => {
                  if (Number(r.driver_base_rate) <= 0) return <span style={{ color: 'var(--text-faint)' }}>—</span>
                  const margin = Number(r.base_rate) - Number(r.driver_base_rate)
                  return (
                    <span
                      className="tnum font-medium"
                      style={{ color: margin > 0 ? 'var(--success)' : 'var(--danger)' }}
                    >
                      {rupees(margin)}
                    </span>
                  )
                },
              },
              {
                key: 'lift',
                header: 'With a lift',
                render: (r) =>
                  r.charge_floors_with_lift ? (
                    <Badge tone="warning">Floors still charged</Badge>
                  ) : (
                    <Badge tone="neutral">Ground rate only</Badge>
                  ),
              },
              {
                key: 'cap',
                header: 'Cap',
                align: 'right',
                render: (r) =>
                  r.max_chargeable_floors > 0 ? (
                    <span className="tnum">{r.max_chargeable_floors} floors</span>
                  ) : (
                    <span style={{ color: 'var(--text-faint)' }}>none</span>
                  ),
              },
              {
                key: 'from',
                header: 'Effective',
                render: (r) => <span className="tnum">{r.effective_from}</span>,
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/unloading-rates'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Unloading rate"
                    fields={[
                      { name: 'item_name', label: 'Article', required: true },
                      { name: 'item_code', label: 'Code' },
                      { name: 'base_rate', label: 'Base rate', kind: 'number' as const, hint: 'Ground floor, per article' },
                      { name: 'per_floor_rate', label: 'Per floor', kind: 'number' as const },
                      { name: 'max_chargeable_floors', label: 'Max floors charged', kind: 'number' as const, hint: '0 means no cap' },
                      { name: 'charge_floors_with_lift', label: 'Charge floors even with a lift', kind: 'checkbox' as const },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      <RateForm
        open={open}
        onClose={() => setOpen(false)}
        divisions={divisions.data ?? []}
        preselected={division}
      />
    </div>
  )
}

function RateForm({
  open,
  onClose,
  divisions,
  preselected,
}: {
  open: boolean
  onClose: () => void
  divisions: VendorDivision[]
  preselected: string
}) {
  const blank = {
    vendor_division_id: preselected,
    item_name: '',
    item_code: '',
    base_rate: '',
    per_floor_rate: '',
    driver_base_rate: '',
    driver_per_floor_rate: '',
    charge_floors_with_lift: false,
    max_chargeable_floors: '0',
    effective_from: new Date().toISOString().slice(0, 10),
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/unloading-rates', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  const base = Number(form.base_rate) || 0
  const perFloor = Number(form.per_floor_rate) || 0
  const driverBase = Number(form.driver_base_rate) || 0
  const driverPerFloor = Number(form.driver_per_floor_rate) || 0
  const fourthMargin = base + 4 * perFloor - (driverBase + 4 * driverPerFloor)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New article rate"
      description="Two prices for the same article: what the vendor is charged, and what the driver is paid for carrying it. The difference is what Target Express keeps."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              ...form,
              item_code:
                form.item_code.trim().toUpperCase().replace(/\s+/g, '_') ||
                form.item_name.trim().toUpperCase().replace(/\s+/g, '_'),
              max_chargeable_floors: Number(form.max_chargeable_floors) || 0,
              // Blank means "no driver rate on this article", which is 0, not
              // an empty string the server cannot read as a number.
              driver_base_rate: driverBase,
              driver_per_floor_rate: driverPerFloor,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Vendor division">
          <Select
            value={form.vendor_division_id}
            onChange={(e) => setForm({ ...form, vendor_division_id: e.target.value })}
            required
          >
            <option value="">Select a division</option>
            {divisions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Article">
            <Input
              value={form.item_name}
              onChange={(e) => setForm({ ...form, item_name: e.target.value })}
              placeholder="Chair"
              required
            />
          </Field>
          <Field label="Code" hint="Left blank, it is made from the name">
            <Input
              value={form.item_code}
              onChange={(e) => setForm({ ...form, item_code: e.target.value })}
              placeholder="CHAIR"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ground-floor rate">
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min={0}
              value={form.base_rate}
              onChange={(e) => setForm({ ...form, base_rate: e.target.value })}
              placeholder="50"
              required
            />
          </Field>
          <Field label="Per floor above ground">
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min={0}
              value={form.per_floor_rate}
              onChange={(e) => setForm({ ...form, per_floor_rate: e.target.value })}
              placeholder="10"
            />
          </Field>
        </div>

        <div>
          <p className="eyebrow mb-2">What the driver is paid</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Ground-floor pay" hint="Leave at 0 to pay a percentage instead">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                min={0}
                value={form.driver_base_rate}
                onChange={(e) => setForm({ ...form, driver_base_rate: e.target.value })}
                placeholder="30"
              />
            </Field>
            <Field label="Per floor above ground">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                min={0}
                value={form.driver_per_floor_rate}
                onChange={(e) => setForm({ ...form, driver_per_floor_rate: e.target.value })}
                placeholder="6"
              />
            </Field>
          </div>
        </div>

        {/* Both sides worked through on one example, because the margin is the
            reason the company handles unloading at all — and a rate raised on
            the vendor side without the driver side is how it quietly
            disappears. */}
        {base > 0 ? (
          <div className="inset space-y-1.5 px-3.5 py-3 text-[12.5px]">
            <div className="flex items-baseline justify-between">
              <span style={{ color: 'var(--text-muted)' }}>Vendor is charged, 4th floor</span>
              <span className="tnum" style={{ color: 'var(--text)' }}>
                {rupees(base)} + 4 × {rupees(perFloor)} = {rupees(base + 4 * perFloor)}
              </span>
            </div>
            {driverBase > 0 ? (
              <>
                <div className="flex items-baseline justify-between">
                  <span style={{ color: 'var(--text-muted)' }}>Driver is paid</span>
                  <span className="tnum" style={{ color: 'var(--text)' }}>
                    {rupees(driverBase)} + 4 × {rupees(driverPerFloor)} ={' '}
                    {rupees(driverBase + 4 * driverPerFloor)}
                  </span>
                </div>
                <div className="groove my-1" />
                <div className="flex items-baseline justify-between">
                  <span className="font-medium">Target Express keeps</span>
                  <span
                    className="tnum font-semibold"
                    style={{ color: fourthMargin > 0 ? 'var(--success)' : 'var(--danger)' }}
                  >
                    {rupees(fourthMargin)}
                  </span>
                </div>
                {fourthMargin <= 0 ? (
                  <p style={{ color: 'var(--danger)' }}>
                    The driver is paid at least what the vendor is charged. Check both figures.
                  </p>
                ) : null}
              </>
            ) : (
              <p style={{ color: 'var(--text-faint)' }}>
                No driver rate set, so this division pays its drivers the percentage share on
                their pay terms.
              </p>
            )}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Cap on chargeable floors" hint="0 means no cap">
            <Input
              className="tnum"
              type="number"
              min={0}
              value={form.max_chargeable_floors}
              onChange={(e) => setForm({ ...form, max_chargeable_floors: e.target.value })}
            />
          </Field>
          <Field label="Effective from">
            <Input
              type="date"
              value={form.effective_from}
              onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
              required
            />
          </Field>
        </div>

        <Checkbox
          label="Charge the floors even when the building has a lift"
          checked={form.charge_floors_with_lift}
          onChange={(e) => setForm({ ...form, charge_floors_with_lift: e.target.checked })}
        />

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create rate
          </Button>
        </div>
      </form>
    </Modal>
  )
}
