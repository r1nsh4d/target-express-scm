import { Plus, Truck } from 'lucide-react'
import { useCallback, useState } from 'react'

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
} from '@/components/ui'
import { Fact, Facts, TileGrid, TileHead } from '@/components/TileGrid'
import { VehicleDetail } from '@/components/Profiles'
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { Vehicle, VehicleOwner, VehicleType } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function VehiclesPage() {
  const [open, setOpen] = useState<'vehicle' | 'type' | 'owner' | null>(null)
  const [viewing, setViewing] = useState<string | null>(null)

  /* Filtering by type, because the type is what the rate card is written
     against: a DOST and a 17-footer are different base charges for the same
     run. "Which of our lorries can take this Godrej OCP job" is a question
     about the type, and scanning eleven tiles for the word DOST is not how
     anybody should answer it. */
  const [type, setType] = useState('')

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen('vehicle'), []))
  const vehicles = useList<Vehicle>('/vehicles')
  const types = useList<VehicleType>('/vehicle-types')
  const owners = useList<VehicleOwner>('/vehicle-owners')

  const shown = (vehicles.data ?? []).filter((v) =>
    !type ? true : type === 'none' ? !v.vehicle_type_id : v.vehicle_type_id === type,
  )

  // Only the types that something is actually on. A chip for a type with no
  // lorries behind it is a dead end.
  const counts = new Map<string, number>()
  for (const v of vehicles.data ?? []) {
    const key = v.vehicle_type_id ?? 'none'
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        description="An owned vehicle pays its driver. A rented one pays the vehicle's owner, so a rented vehicle needs an owner on file first. The type decides which rate card prices a trip."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setOpen('type')}>
              Vehicle type
            </Button>
            <Button variant="secondary" onClick={() => setOpen('owner')}>
              Owner
            </Button>
            <Button icon={<Plus className="size-4" />} onClick={() => setOpen('vehicle')}>
              New vehicle
            </Button>
          </div>
        }
      />

      {counts.size > 1 ? (
        <div className="flex flex-wrap gap-2">
          <TypeChip label="All" count={vehicles.data?.length ?? 0} on={!type} onClick={() => setType('')} />
          {types.data
            ?.filter((t) => counts.has(t.id))
            .map((t) => (
              <TypeChip
                key={t.id}
                label={t.name}
                count={counts.get(t.id) ?? 0}
                on={type === t.id}
                onClick={() => setType(type === t.id ? '' : t.id)}
              />
            ))}
          {counts.has('none') ? (
            <TypeChip
              label="Type not set"
              count={counts.get('none') ?? 0}
              on={type === 'none'}
              onClick={() => setType(type === 'none' ? '' : 'none')}
            />
          ) : null}
        </div>
      ) : null}

      {vehicles.isLoading ? (
        <Card>
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        </Card>
      ) : (
        <TileGrid
          rows={shown}
          rowKey={(v) => v.id}
          onRowClick={(v) => setViewing(v.id)}
          empty={
            <EmptyState
              icon={<Truck className="size-7" />}
              title={type ? 'None of this type' : 'No vehicles yet'}
              description={
                type
                  ? 'Every lorry of this type has been retired, or there were never any.'
                  : 'A freight needs a vehicle before it can be dispatched.'
              }
              action={
                type ? (
                  <Button variant="secondary" onClick={() => setType('')}>
                    Show all
                  </Button>
                ) : (
                  <Button onClick={() => setOpen('vehicle')}>New vehicle</Button>
                )
              }
            />
          }
          render={(v) => (
            <>
              <TileHead
                title={<span className="tnum">{v.registration_no}</span>}
                sub={v.vehicle_type_name ?? 'Type not set'}
                badge={
                  <Badge tone={v.ownership === 'OWNED' ? 'success' : 'info'}>
                    {v.ownership === 'OWNED' ? 'Owned' : 'Rented'}
                  </Badge>
                }
                actions={
                  <RowActions
                    path={'/vehicles'}
                    row={v as unknown as Record<string, unknown> & { id: string }}
                    label="Vehicle"
                    fields={[
                      { name: 'registration_no', label: 'Registration', required: true },
                      { name: 'make_model', label: 'Make and model' },
                      {
                        name: 'lr_prefix',
                        label: 'LR prefix',
                        hint: 'The odometer and LR counter are not editable here',
                      },
                    ]}
                  />
                }
              />
              <Facts>
                <Fact label="Paid to" value={v.owner_name ?? 'Driver'} />
                <Fact
                  label="Odometer"
                  value={
                    <span className="tnum">
                      {v.last_closing_km != null
                        ? `${v.last_closing_km.toLocaleString('en-IN')} km`
                        : '—'}
                    </span>
                  }
                  tone={v.last_closing_km == null ? 'muted' : undefined}
                />
                <Fact label="Next LR" value={<span className="tnum">{v.lr_next_number}</span>} />
              </Facts>
              <p className="mt-2.5 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
                Open for its runs, earnings and papers
              </p>
            </>
          )}
        />
      )}

      <VehicleDetail
        vehicleId={viewing}
        open={viewing !== null}
        onClose={() => setViewing(null)}
      />

      <VehicleForm
        open={open === 'vehicle'}
        onClose={() => setOpen(null)}
        types={types.data ?? []}
        owners={owners.data ?? []}
      />
      <SimpleForm
        open={open === 'type'}
        onClose={() => setOpen(null)}
        title="New vehicle type"
        path="/vehicle-types"
        fields={[
          { key: 'name', label: 'Name', placeholder: 'DOST', required: true },
          { key: 'capacity_kg', label: 'Capacity (kg)', type: 'number' },
        ]}
      />
      <SimpleForm
        open={open === 'owner'}
        onClose={() => setOpen(null)}
        title="New vehicle owner"
        description="Who gets paid for a rented vehicle's trips."
        path="/vehicle-owners"
        fields={[
          { key: 'name', label: 'Name', required: true },
          { key: 'phone', label: 'Phone', required: true },
          { key: 'pan', label: 'PAN' },
          { key: 'bank_account', label: 'Bank account' },
          { key: 'ifsc', label: 'IFSC' },
        ]}
      />
    </div>
  )
}

/* A type, and how many lorries are on it.
 *
 * Chips rather than a dropdown: there are four or five types and the counts
 * are half the answer — "we have three DOSTs free" is read off the filter
 * itself, without opening anything. */
function TypeChip({
  label,
  count,
  on,
  onClick,
}: {
  label: string
  count: number
  on: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className="hoverable rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium"
      style={
        on
          ? { background: 'var(--accent)', borderColor: 'var(--accent)', color: '#04121a' }
          : { background: 'var(--bg-elevated)', color: 'var(--text-muted)' }
      }
    >
      {label}
      <span className="tnum ml-1.5" style={{ opacity: 0.7 }}>
        {count}
      </span>
    </button>
  )
}

function VehicleForm({
  open,
  onClose,
  types,
  owners,
}: {
  open: boolean
  onClose: () => void
  types: VehicleType[]
  owners: VehicleOwner[]
}) {
  const blank = {
    registration_no: '',
    vehicle_type_id: '',
    ownership: 'OWNED',
    owner_id: '',
    lr_prefix: '',
    lr_next_number: '1',
    last_closing_km: '',
    hire_rate_value: '',
    hire_minimum_km: '0',
    hire_includes_unloading: false,
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)
  const rented = form.ownership === 'HIRED'

  const create = useCreate<Record<string, unknown>>('/vehicles', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New vehicle">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              registration_no: form.registration_no.toUpperCase().replace(/\s/g, ''),
              vehicle_type_id: form.vehicle_type_id || null,
              ownership: form.ownership,
              owner_id: rented ? form.owner_id || null : null,
              lr_prefix: form.lr_prefix,
              lr_next_number: Number(form.lr_next_number) || 1,
              last_closing_km: form.last_closing_km ? Number(form.last_closing_km) : null,
              hire_rate_basis: rented && form.hire_rate_value ? 'PER_KM' : null,
              hire_rate_value: rented && form.hire_rate_value ? form.hire_rate_value : null,
              hire_minimum_km: Number(form.hire_minimum_km) || 0,
              hire_includes_unloading: form.hire_includes_unloading,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Registration number">
            <Input
              value={form.registration_no}
              onChange={(e) => setForm({ ...form, registration_no: e.target.value })}
              placeholder="KL07AA1234"
              required
            />
          </Field>
          <Field label="Vehicle type">
            <Select
              value={form.vehicle_type_id}
              onChange={(e) => setForm({ ...form, vehicle_type_id: e.target.value })}
            >
              <option value="">Not set</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Ownership" hint="Decides who is paid for this vehicle's trips">
          <Select
            value={form.ownership}
            onChange={(e) => setForm({ ...form, ownership: e.target.value })}
          >
            <option value="OWNED">Owned by Target Express — pays the driver</option>
            <option value="HIRED">Rented — pays the vehicle owner</option>
          </Select>
        </Field>

        {rented ? (
          <div
            className="space-y-4 rounded-lg border p-4"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
          >
            <Field label="Vehicle owner" hint="Required for a rented vehicle">
              <Select
                value={form.owner_id}
                onChange={(e) => setForm({ ...form, owner_id: e.target.value })}
                required
              >
                <option value="">Select an owner</option>
                {owners.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name} · {o.phone}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Hire rate per km">
                <Input
                  className="tnum"
                  type="number"
                  step="0.01"
                  value={form.hire_rate_value}
                  onChange={(e) => setForm({ ...form, hire_rate_value: e.target.value })}
                  placeholder="13.00"
                />
              </Field>
              <Field label="Minimum km per trip" hint="A short trip still bills this floor">
                <Input
                  className="tnum"
                  type="number"
                  value={form.hire_minimum_km}
                  onChange={(e) => setForm({ ...form, hire_minimum_km: e.target.value })}
                />
              </Field>
            </div>
            <Checkbox
              label="The rent already covers unloading"
              checked={form.hire_includes_unloading}
              onChange={(e) => setForm({ ...form, hire_includes_unloading: e.target.checked })}
            />
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="LR prefix" hint="Optional">
            <Input
              value={form.lr_prefix}
              onChange={(e) => setForm({ ...form, lr_prefix: e.target.value })}
            />
          </Field>
          <Field label="Next LR number">
            <Input
              className="tnum"
              type="number"
              value={form.lr_next_number}
              onChange={(e) => setForm({ ...form, lr_next_number: e.target.value })}
            />
          </Field>
          <Field label="Current odometer">
            <Input
              className="tnum"
              type="number"
              value={form.last_closing_km}
              onChange={(e) => setForm({ ...form, last_closing_km: e.target.value })}
            />
          </Field>
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create vehicle
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** A small form for masters that are just a handful of text fields. */
export function SimpleForm({
  open,
  onClose,
  title,
  description,
  path,
  fields,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  path: string
  fields: { key: string; label: string; placeholder?: string; type?: string; required?: boolean }[]
}) {
  const [form, setForm] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>(path, {
    onSuccess: () => {
      setForm({})
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title={title} description={description}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          const body: Record<string, unknown> = {}
          fields.forEach((f) => {
            const value = form[f.key]
            if (value === undefined || value === '') return
            body[f.key] = f.type === 'number' ? Number(value) : value
          })
          create.mutate(body, { onError: (err) => setError(apiErrorMessage(err)) })
        }}
      >
        {fields.map((f) => (
          <Field key={f.key} label={f.label}>
            <Input
              type={f.type ?? 'text'}
              value={form[f.key] ?? ''}
              placeholder={f.placeholder}
              required={f.required}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            />
          </Field>
        ))}
        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Modal>
  )
}
