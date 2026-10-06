import { HandCoins, Plus } from 'lucide-react'
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
import { apiErrorMessage } from '@/lib/api'
import type { Driver, FreightRow, VehicleOwner } from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'

interface Advance {
  id: string
  payee_type: 'DRIVER' | 'VEHICLE_OWNER'
  driver_id: string | null
  vehicle_owner_id: string | null
  freight_id: string | null
  advance_date: string
  amount: string
  recovered_amount: string
  outstanding: string
  status: string
  mode: string | null
  reference: string | null
}

const STATUS_TONE: Record<string, 'warning' | 'info' | 'success' | 'neutral'> = {
  OUTSTANDING: 'warning',
  PART_RECOVERED: 'info',
  RECOVERED: 'success',
  WRITTEN_OFF: 'neutral',
}

export default function AdvancesPage() {
  const [open, setOpen] = useState(false)
  const [outstandingOnly, setOutstandingOnly] = useState(false)

  const advances = useList<Advance>(
    '/advances',
    outstandingOnly ? { outstanding_only: true } : undefined,
  )
  const drivers = useList<Driver>('/drivers')
  const owners = useList<VehicleOwner>('/vehicle-owners')

  const nameOf = (a: Advance) =>
    a.payee_type === 'VEHICLE_OWNER'
      ? (owners.data?.find((o) => o.id === a.vehicle_owner_id)?.name ?? '—')
      : (drivers.data?.find((d) => d.id === a.driver_id)?.name ?? '—')

  return (
    <div className="space-y-6">
      <PageHeader
        description="Money handed over before a settlement. A rented vehicle's owner normally draws one when the lorry leaves, and it is set against what that freight earns when the vehicle returns. An advance larger than the run earned is not an error — the excess carries to his next one."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            Record advance
          </Button>
        }
      />

      <Button
        variant={outstandingOnly ? 'primary' : 'secondary'}
        onClick={() => setOutstandingOnly((v) => !v)}
      >
        Outstanding only
      </Button>

      <Card className="overflow-hidden">
        {advances.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={advances.data ?? []}
            rowKey={(a) => a.id}
            empty={
              <EmptyState
                icon={<HandCoins className="size-7" />}
                title="No advances"
                description="Record one when cash is handed over before a settlement."
              />
            }
            columns={[
              { key: 'date', header: 'Date', render: (a) => <span className="tnum">{a.advance_date}</span> },
              { key: 'payee', header: 'Paid to', render: (a) => <span className="font-medium">{nameOf(a)}</span> },
              {
                key: 'type',
                header: 'Type',
                render: (a) => (
                  <Badge tone={a.payee_type === 'VEHICLE_OWNER' ? 'info' : 'accent'}>
                    {a.payee_type === 'VEHICLE_OWNER' ? 'Owner' : 'Driver'}
                  </Badge>
                ),
              },
              {
                key: 'amount',
                header: 'Advance',
                align: 'right',
                render: (a) => <span className="tnum">{rupees(a.amount)}</span>,
              },
              {
                key: 'recovered',
                header: 'Recovered',
                align: 'right',
                render: (a) => <span className="tnum">{rupees(a.recovered_amount)}</span>,
              },
              {
                key: 'out',
                header: 'Outstanding',
                align: 'right',
                render: (a) => (
                  <span className="tnum font-medium">{rupees(a.outstanding)}</span>
                ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (a) => (
                  <Badge tone={STATUS_TONE[a.status] ?? 'neutral'}>
                    {a.status.replaceAll('_', ' ').toLowerCase()}
                  </Badge>
                ),
              },
            ]}
          />
        )}
      </Card>

      <AdvanceForm
        open={open}
        onClose={() => setOpen(false)}
        drivers={drivers.data ?? []}
        owners={owners.data ?? []}
      />
    </div>
  )
}

function AdvanceForm({
  open,
  onClose,
  drivers,
  owners,
}: {
  open: boolean
  onClose: () => void
  drivers: Driver[]
  owners: VehicleOwner[]
}) {
  const blank = {
    payee_type: 'VEHICLE_OWNER',
    payee_id: '',
    freight_id: '',
    advance_date: new Date().toISOString().slice(0, 10),
    amount: '',
    mode: 'CASH',
    reference: '',
    reason: '',
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const freights = useList<FreightRow>('/freights', { limit: 60 })

  const create = useCreate<Record<string, unknown>>('/advances', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  const toOwner = form.payee_type === 'VEHICLE_OWNER'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Record an advance"
      description="It is recovered from whoever drew it — never from the other party on the same freight."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              payee_type: form.payee_type,
              driver_id: toOwner ? null : form.payee_id,
              vehicle_owner_id: toOwner ? form.payee_id : null,
              freight_id: form.freight_id || null,
              advance_date: form.advance_date,
              amount: form.amount,
              mode: form.mode,
              reference: form.reference || null,
              reason: form.reason || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Paid to">
          <Select
            value={form.payee_type}
            onChange={(e) => setForm({ ...form, payee_type: e.target.value, payee_id: '' })}
          >
            <option value="VEHICLE_OWNER">A vehicle owner</option>
            <option value="DRIVER">A driver</option>
          </Select>
        </Field>

        <Field label={toOwner ? 'Vehicle owner' : 'Driver'}>
          <Select
            value={form.payee_id}
            onChange={(e) => setForm({ ...form, payee_id: e.target.value })}
            required
          >
            <option value="">Select</option>
            {(toOwner ? owners : drivers).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.phone}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Against which freight"
          hint="Optional. Linking it recovers the advance automatically when that freight closes."
        >
          <Select
            value={form.freight_id}
            onChange={(e) => setForm({ ...form, freight_id: e.target.value })}
          >
            <option value="">Not linked to a freight</option>
            {freights.data?.map((f) => (
              <option key={f.id} value={f.id}>
                {f.trip_no} · {f.trip_date} · {f.destination_text ?? '—'}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Amount">
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min={1}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              required
            />
          </Field>
          <Field label="Date">
            <Input
              type="date"
              value={form.advance_date}
              onChange={(e) => setForm({ ...form, advance_date: e.target.value })}
              required
            />
          </Field>
          <Field label="Mode">
            <Select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
              <option value="CASH">Cash</option>
              <option value="UPI">UPI</option>
              <option value="BANK">Bank transfer</option>
            </Select>
          </Field>
        </div>

        <Field label="Reference" hint="UPI reference, cheque number, whatever there is">
          <Input
            value={form.reference}
            onChange={(e) => setForm({ ...form, reference: e.target.value })}
          />
        </Field>

        <Field label="Reason">
          <Textarea
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Record advance
          </Button>
        </div>
      </form>
    </Modal>
  )
}
