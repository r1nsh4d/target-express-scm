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
        description="Furniture is not unloaded by the box. A chair, a wardrobe and a mattress are different work — and carrying any of them up four floors is different work again. Each article gets a ground-floor rate plus a charge for every floor above it."
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
                key: 'example',
                header: '4th floor',
                align: 'right',
                render: (r) => (
                  <span className="tnum font-medium">
                    {rupees(Number(r.base_rate) + 4 * Number(r.per_floor_rate))}
                  </span>
                ),
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

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New article rate"
      description="What unloading one of these costs, on the ground and per floor above it."
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

        {base > 0 ? (
          <p className="inset px-3.5 py-2.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            One to the 4th floor bills{' '}
            <span className="tnum font-medium" style={{ color: 'var(--text)' }}>
              {rupees(base)} + 4 × {rupees(perFloor)} = {rupees(base + 4 * perFloor)}
            </span>
          </p>
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
