import { Plus, ReceiptIndianRupee } from 'lucide-react'
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
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { RateCard, VehicleType, VendorDivision } from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'

export default function RateCardsPage() {
  const [open, setOpen] = useState(false)
  const [division, setDivision] = useState('')

  const divisions = useList<VendorDivision>('/vendor-divisions')
  const types = useList<VehicleType>('/vehicle-types')
  const cards = useList<RateCard>('/rate-cards', division ? { vendor_division_id: division } : undefined)

  const divisionName = (id: string) => divisions.data?.find((d) => d.id === id)?.name ?? '—'

  return (
    <div className="space-y-6">
      <PageHeader
        description="Rates are never edited — that is why there is no edit button here. To change one, add a card dated from the change: freights before it keep their original price, so old invoices re-print unchanged. Retiring a card stops it applying to new freights without touching anything it has already priced."
        action={
          <Button
            icon={<Plus className="size-4" />}
            onClick={() => setOpen(true)}
            disabled={!divisions.data?.length}
          >
            New rate card
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
        {cards.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={cards.data ?? []}
            rowKey={(c) => c.id}
            empty={
              <EmptyState
                icon={<ReceiptIndianRupee className="size-7" />}
                title="No rate cards"
                description={
                  divisions.data?.length
                    ? 'A freight cannot be priced until its division has a card covering its date.'
                    : 'Create a vendor and a division first — rates attach to the division.'
                }
              />
            }
            columns={[
              {
                key: 'division',
                header: 'Division',
                render: (c) => <span className="font-medium">{divisionName(c.vendor_division_id)}</span>,
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
              { key: 'base', header: 'Base freight', align: 'right', render: (c) => rupees(c.base_trip_amount) },
              {
                key: 'km',
                header: 'Distance',
                align: 'right',
                render: (c) => (
                  <span className="tnum">
                    {c.included_km} km + {rupees(c.extra_km_rate)}/km
                  </span>
                ),
              },
              {
                key: 'points',
                header: 'Points',
                align: 'right',
                render: (c) => (
                  <span className="tnum">
                    {Number(c.base_point_charge) > 0 ? `${rupees(c.base_point_charge)} for ` : ''}
                    {c.included_points} + {rupees(c.extra_point_rate)}/pt
                  </span>
                ),
              },
              {
                key: 'unloading',
                header: 'Unloading',
                render: (c) => (
                  <Badge tone={c.unloading_basis === 'NOT_APPLICABLE' ? 'neutral' : 'info'}>
                    {c.unloading_basis.replaceAll('_', ' ').toLowerCase()}
                  </Badge>
                ),
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/rate-cards'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Rate card"
                    fields={[]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      <RateCardForm
        open={open}
        onClose={() => setOpen(false)}
        divisions={divisions.data ?? []}
        types={types.data ?? []}
        preselected={division}
      />
    </div>
  )
}

function RateCardForm({
  open,
  onClose,
  divisions,
  types,
  preselected,
}: {
  open: boolean
  onClose: () => void
  divisions: VendorDivision[]
  types: VehicleType[]
  preselected: string
}) {
  const blank = {
    vendor_division_id: preselected,
    vehicle_type_id: '',
    effective_from: new Date().toISOString().slice(0, 10),
    effective_to: '',
    base_trip_amount: '1867',
    included_km: '60',
    extra_km_rate: '17',
    base_point_charge: '0',
    included_points: '3',
    extra_point_rate: '175',
    unloading_basis: 'NOT_APPLICABLE',
    notes: '',
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/rate-cards', {
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
      title="New rate card"
      description="Defaults shown are the verified Godrej terms. Adjust for this vendor."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            { ...form, effective_to: form.effective_to || null, vehicle_type_id: form.vehicle_type_id || null },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
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
          <Field label="Vehicle type" hint="Leave blank to apply to every type">
            <Select
              value={form.vehicle_type_id}
              onChange={(e) => setForm({ ...form, vehicle_type_id: e.target.value })}
            >
              <option value="">All vehicle types</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Effective from">
            <Input
              type="date"
              value={form.effective_from}
              onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
              required
            />
          </Field>
          <Field label="Effective to" hint="Blank means open-ended">
            <Input
              type="date"
              value={form.effective_to}
              onChange={(e) => setForm({ ...form, effective_to: e.target.value })}
            />
          </Field>
        </div>

        <div
          className="space-y-4 rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
        >
          <p className="text-[11px] font-semibold tracking-[0.14em] uppercase" style={{ color: 'var(--text-faint)' }}>
            Transportation
          </p>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Base trip amount">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                value={form.base_trip_amount}
                onChange={(e) => setForm({ ...form, base_trip_amount: e.target.value })}
                required
              />
            </Field>
            <Field label="Included km">
              <Input
                className="tnum"
                type="number"
                value={form.included_km}
                onChange={(e) => setForm({ ...form, included_km: e.target.value })}
              />
            </Field>
            <Field label="Rate per extra km">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                value={form.extra_km_rate}
                onChange={(e) => setForm({ ...form, extra_km_rate: e.target.value })}
              />
            </Field>
          </div>
        </div>

        <div
          className="space-y-4 rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
        >
          <p className="text-[11px] font-semibold tracking-[0.14em] uppercase" style={{ color: 'var(--text-faint)' }}>
            Points
          </p>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Slab charge" hint="0 if it is inside the base">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                value={form.base_point_charge}
                onChange={(e) => setForm({ ...form, base_point_charge: e.target.value })}
              />
            </Field>
            <Field label="Points included">
              <Input
                className="tnum"
                type="number"
                value={form.included_points}
                onChange={(e) => setForm({ ...form, included_points: e.target.value })}
              />
            </Field>
            <Field label="Rate per extra point">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                value={form.extra_point_rate}
                onChange={(e) => setForm({ ...form, extra_point_rate: e.target.value })}
              />
            </Field>
          </div>
          <p className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
            A 7-point trip bills {rupees(form.base_point_charge)} +{' '}
            {Math.max(0, 7 - Number(form.included_points || 0))} ×{' '}
            {rupees(form.extra_point_rate)} ={' '}
            <span className="font-medium" style={{ color: 'var(--text)' }}>
              {rupees(
                Number(form.base_point_charge || 0) +
                  Math.max(0, 7 - Number(form.included_points || 0)) *
                    Number(form.extra_point_rate || 0),
              )}
            </span>
          </p>
        </div>

        <Field label="Unloading basis">
          <Select
            value={form.unloading_basis}
            onChange={(e) => setForm({ ...form, unloading_basis: e.target.value })}
          >
            <option value="NOT_APPLICABLE">Not billed (spare parts)</option>
            <option value="PER_ITEM_FLOOR">Per article plus floors (furniture)</option>
            <option value="ACTUAL">At actuals</option>
            <option value="PER_POINT">Per point</option>
            <option value="PER_BOX">Per box</option>
          </Select>
        </Field>

        <Field label="Notes">
          <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create rate card
          </Button>
        </div>
      </form>
    </Modal>
  )
}
