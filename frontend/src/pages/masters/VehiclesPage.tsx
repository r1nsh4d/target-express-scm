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
  Table,
} from '@/components/ui'
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { Vehicle, VehicleOwner, VehicleType } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function VehiclesPage() {
  const [open, setOpen] = useState<'vehicle' | 'type' | 'owner' | null>(null)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen('vehicle'), []))
  const vehicles = useList<Vehicle>('/vehicles')
  const types = useList<VehicleType>('/vehicle-types')
  const owners = useList<VehicleOwner>('/vehicle-owners')

  return (
    <div className="space-y-6">
      <PageHeader
        description="An owned vehicle pays its driver. A rented one pays the vehicle's owner, so a rented vehicle needs an owner on file first."
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

      <Card className="overflow-hidden">
        {vehicles.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={vehicles.data ?? []}
            rowKey={(v) => v.id}
            empty={
              <EmptyState
                icon={<Truck className="size-7" />}
                title="No vehicles yet"
                description="A freight needs a vehicle before it can be dispatched."
                action={<Button onClick={() => setOpen('vehicle')}>New vehicle</Button>}
              />
            }
            columns={[
              {
                key: 'reg',
                header: 'Registration',
                render: (v) => <span className="font-medium">{v.registration_no}</span>,
              },
              { key: 'type', header: 'Type', render: (v) => v.vehicle_type_name ?? '—' },
              {
                key: 'own',
                header: 'Ownership',
                render: (v) => (
                  <Badge tone={v.ownership === 'OWNED' ? 'success' : 'info'}>
                    {v.ownership === 'OWNED' ? 'Owned' : 'Rented'}
                  </Badge>
                ),
              },
              { key: 'owner', header: 'Paid to', render: (v) => v.owner_name ?? 'Driver' },
              {
                key: 'km',
                header: 'Last closing km',
                align: 'right',
                render: (v) => (
                  <span className="tnum">
                    {v.last_closing_km?.toLocaleString('en-IN') ?? '—'}
                  </span>
                ),
              },
              {
                key: 'lr',
                header: 'Next LR',
                align: 'right',
                render: (v) => <span className="tnum">{v.lr_next_number}</span>,
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/vehicles'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Vehicle"
                    fields={[
                      { name: 'registration_no', label: 'Registration', required: true },
                      { name: 'make_model', label: 'Make and model' },
                      { name: 'lr_prefix', label: 'LR prefix', hint: 'The odometer and LR counter are not editable here' },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

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
