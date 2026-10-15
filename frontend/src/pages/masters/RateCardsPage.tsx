import { useMutation, useQueryClient } from '@tanstack/react-query'
import { IndianRupee, Plus, Sofa, Trash2, Truck } from 'lucide-react'
import { useState } from 'react'
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
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import type { VendorDivision } from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'

/* What each vendor is charged, as one card you can read at a glance.
 *
 * This was a table of nine narrow columns, which is the wrong shape for the
 * thing it holds: a rate card is not a row of numbers, it is one commercial
 * agreement with a vendor, and the question somebody actually has is "what
 * are we on with Godrej?" — not "what is in column six".
 *
 * So one tile per card, laid out the way the money is worked out: the base
 * covers so many kilometres and so many points, then extras, then unloading.
 * The worked example at the bottom is the whole card in one sentence, because
 * a rate card nobody can check is a rate card nobody trusts.
 *
 * Rates are never edited — that is why there is no edit button. To change
 * one, add a card dated from the change, so freights before it keep their
 * original price and old invoices re-print unchanged.
 */

interface RateCard {
  id: string
  vendor_division_id: string
  vehicle_type_id: string | null
  effective_from: string
  effective_to: string | null
  base_trip_amount: string
  included_km: number
  extra_km_rate: string
  base_point_charge: string
  included_points: number
  extra_point_rate: string
  unloading_basis: string
  unloading_rate: string
  notes: string | null
  is_active: boolean
}

interface VehicleType {
  id: string
  name: string
}

export default function RateCardsPage() {
  const [open, setOpen] = useState(false)
  const [division, setDivision] = useState('')

  const divisions = useList<VendorDivision>('/vendor-divisions')
  const types = useList<VehicleType>('/vehicle-types')
  const cards = useList<RateCard>(
    '/rate-cards',
    division ? { vendor_division_id: division } : undefined,
  )

  const divisionName = (id: string) =>
    divisions.data?.find((d) => d.id === id)?.name ?? '—'
  const typeName = (id: string | null) =>
    id ? (types.data?.find((t) => t.id === id)?.name ?? 'A vehicle type') : 'Any vehicle'

  return (
    <div className="space-y-6">
      <PageHeader
        description="One card per agreement: what the vendor pays for a trip, the distance and the points. Rates are never edited — to change one, add a card dated from the change, so freights before it keep their original price and old invoices re-print unchanged."
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

      {cards.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner className="size-5" />
        </div>
      ) : !cards.data?.length ? (
        <Card>
          <EmptyState
            icon={<IndianRupee className="size-7" />}
            title={division ? 'No rate card for this division' : 'No rate cards yet'}
            description="Without one, a finished freight cannot be priced and cannot be invoiced."
            action={
              division ? (
                <Button variant="secondary" onClick={() => setDivision('')}>
                  Show all divisions
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {cards.data.map((card) => (
            <RateTile
              key={card.id}
              card={card}
              divisionName={divisionName(card.vendor_division_id)}
              typeName={typeName(card.vehicle_type_id)}
            />
          ))}
        </div>
      )}

      <RateCardForm
        open={open}
        onClose={() => setOpen(false)}
        divisions={divisions.data ?? []}
        types={types.data ?? []}
      />
    </div>
  )
}

function Line({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
        {label}
        {sub ? (
          <span className="block text-[11px]" style={{ color: 'var(--text-faint)' }}>
            {sub}
          </span>
        ) : null}
      </span>
      <span className="tnum shrink-0 text-[13.5px] font-medium">{value}</span>
    </div>
  )
}

function RateTile({
  card,
  divisionName,
  typeName,
}: {
  card: RateCard
  divisionName: string
  typeName: string
}) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const retire = useMutation({
    mutationFn: async () => (await api.delete(`/rate-cards/${card.id}`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/rate-cards'] })
      setConfirming(false)
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const base = Number(card.base_trip_amount)
  const perKm = Number(card.extra_km_rate)
  const perPoint = Number(card.extra_point_rate)

  // The card in one sentence. A rate card nobody can check is a rate card
  // nobody trusts, and the arithmetic is exactly what an invoice line does.
  const exampleKm = card.included_km + 40
  const examplePoints = card.included_points + 2
  const exampleTotal = base + 40 * perKm + 2 * perPoint

  return (
    <Card className="hoverable overflow-hidden">
      <div
        className="flex items-start justify-between gap-3 px-4 py-3.5"
        style={{ background: 'var(--bg-elevated)' }}
      >
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-semibold">{divisionName}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px]" style={{ color: 'var(--text-muted)' }}>
            <Truck className="inline size-3" />
            {typeName}
            <span>·</span>
            <span className="tnum">
              from {card.effective_from}
              {card.effective_to ? ` to ${card.effective_to}` : ' — still in force'}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="shrink-0 rounded p-1.5 hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-muted)' }}
          aria-label={`Retire the ${divisionName} rate card`}
        >
          <Trash2 className="size-4" />
        </button>
      </div>

      <div className="px-4 py-3">
        <p className="eyebrow mb-1">What the vendor pays</p>
        <Line
          label="Base trip charge"
          sub={`covers ${card.included_km} km and ${card.included_points} points`}
          value={rupees(card.base_trip_amount)}
        />
        <div className="groove" />
        <Line label="Each extra kilometre" value={rupees(card.extra_km_rate)} />
        <Line label="Each extra point" value={rupees(card.extra_point_rate)} />
        {Number(card.base_point_charge) > 0 ? (
          <Line label="Point charge" value={rupees(card.base_point_charge)} />
        ) : null}

        <div className="groove my-1" />
        <div className="flex items-baseline justify-between gap-3 py-1.5">
          <span className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            Unloading
          </span>
          {card.unloading_basis === 'NOT_APPLICABLE' ? (
            <Badge tone="neutral">not charged</Badge>
          ) : (
            <Link to="/unloading-rates" className="no-underline">
              <span
                className="inline-flex items-center gap-1.5 text-[12.5px]"
                style={{ color: 'var(--accent)' }}
              >
                <Sofa className="size-3.5" />
                per article and floor &rarr;
              </span>
            </Link>
          )}
        </div>

        {/* The whole card, worked through. This is the arithmetic an invoice
            line does, so anybody can check the card against a real bill. */}
        <div className="inset mt-2 px-3.5 py-2.5 text-[12px]">
          <p style={{ color: 'var(--text-muted)' }}>
            A {exampleKm} km run to {examplePoints} points bills
          </p>
          <p className="tnum mt-0.5">
            {rupees(base)} + 40 × {rupees(perKm)} + 2 × {rupees(perPoint)} ={' '}
            <span className="font-semibold">{rupees(exampleTotal.toFixed(2))}</span>
          </p>
        </div>

        {card.notes ? (
          <p className="mt-2 text-[12px]" style={{ color: 'var(--text-faint)' }}>
            {card.notes}
          </p>
        ) : null}
      </div>

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Retire this rate card?"
        description="It stops applying to new freights. Anything it has already priced is untouched."
      >
        <div className="space-y-4">
          <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
            Freights already invoiced on this card keep their prices, and those invoices re-print
            exactly as they were. What changes is that a freight entered from now on will not find
            this card — so unless another one covers the date, it cannot be priced at all.
          </p>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
            <Button variant="danger" loading={retire.isPending} onClick={() => retire.mutate()}>
              Retire it
            </Button>
          </div>
        </div>
      </Modal>
    </Card>
  )
}

function RateCardForm({
  open,
  onClose,
  divisions,
  types,
}: {
  open: boolean
  onClose: () => void
  divisions: VendorDivision[]
  types: VehicleType[]
}) {
  const blank = {
    vendor_division_id: '',
    vehicle_type_id: '',
    effective_from: new Date().toISOString().slice(0, 10),
    base_trip_amount: '1867',
    included_km: '60',
    extra_km_rate: '17',
    base_point_charge: '0',
    included_points: '3',
    extra_point_rate: '175',
    unloading_basis: 'NOT_APPLICABLE',
    unloading_rate: '0',
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

  const base = Number(form.base_trip_amount) || 0
  const perKm = Number(form.extra_km_rate) || 0
  const perPoint = Number(form.extra_point_rate) || 0
  const km = Number(form.included_km) || 0
  const points = Number(form.included_points) || 0

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="New rate card"
      description="Dated from the day it takes effect. Freights before that keep the old card, which is why rates are added rather than edited."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              ...form,
              vehicle_type_id: form.vehicle_type_id || null,
              included_km: Number(form.included_km) || 0,
              included_points: Number(form.included_points) || 0,
              notes: form.notes || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Vendor division">
            <Select
              value={form.vendor_division_id}
              onChange={(e) => setForm({ ...form, vendor_division_id: e.target.value })}
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
          <Field label="Vehicle type" hint="The base charge depends on it">
            <Select
              value={form.vehicle_type_id}
              onChange={(e) => setForm({ ...form, vehicle_type_id: e.target.value })}
            >
              <option value="">Any vehicle</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="In force from">
            <Input
              type="date"
              value={form.effective_from}
              onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
              required
            />
          </Field>
        </div>

        <div>
          <p className="eyebrow mb-2">The base, and what it covers</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Base trip charge">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                min={0}
                value={form.base_trip_amount}
                onChange={(e) => setForm({ ...form, base_trip_amount: e.target.value })}
                required
              />
            </Field>
            <Field label="Kilometres included">
              <Input
                className="tnum"
                type="number"
                min={0}
                value={form.included_km}
                onChange={(e) => setForm({ ...form, included_km: e.target.value })}
              />
            </Field>
            <Field label="Points included">
              <Input
                className="tnum"
                type="number"
                min={0}
                value={form.included_points}
                onChange={(e) => setForm({ ...form, included_points: e.target.value })}
              />
            </Field>
          </div>
        </div>

        <div>
          <p className="eyebrow mb-2">Beyond that</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Each extra kilometre">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                min={0}
                value={form.extra_km_rate}
                onChange={(e) => setForm({ ...form, extra_km_rate: e.target.value })}
              />
            </Field>
            <Field label="Each extra point">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                min={0}
                value={form.extra_point_rate}
                onChange={(e) => setForm({ ...form, extra_point_rate: e.target.value })}
              />
            </Field>
          </div>
        </div>

        <Field
          label="Unloading"
          hint="Per article means the figures live under Unloading rates, with the driver's side beside them"
        >
          <Select
            value={form.unloading_basis}
            onChange={(e) => setForm({ ...form, unloading_basis: e.target.value })}
          >
            <option value="NOT_APPLICABLE">Not charged — spare parts and the like</option>
            <option value="PER_ITEM_FLOOR">Per article and floor — furniture</option>
          </Select>
        </Field>

        {/* The card checked before it is saved, with the same arithmetic an
            invoice line uses. A wrong rate found here costs a correction; one
            found on an invoice costs a conversation with the vendor. */}
        {base > 0 ? (
          <div className="inset px-3.5 py-3 text-[12.5px]">
            <p style={{ color: 'var(--text-muted)' }}>
              A {km + 40} km run to {points + 2} points would bill
            </p>
            <p className="tnum mt-1 text-[14px]">
              {rupees(base)} + 40 × {rupees(perKm)} + 2 × {rupees(perPoint)} ={' '}
              <span className="font-semibold">
                {rupees((base + 40 * perKm + 2 * perPoint).toFixed(2))}
              </span>
            </p>
          </div>
        ) : null}

        <Field label="Notes">
          <Textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="What was agreed, and with whom"
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Add rate card
          </Button>
        </div>
      </form>
    </Modal>
  )
}
