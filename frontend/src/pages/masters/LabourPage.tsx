import { HardHat, Plus } from 'lucide-react'
import { useState } from 'react'

import {
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
import type { Warehouse } from '@/lib/resources'
import { rupees, useCreate, useList } from '@/lib/resources'

interface Labour {
  id: string
  name: string
  phone: string | null
  warehouse_id: string | null
  daily_rate: string
  per_trip_rate: string
  is_active: boolean
}

export default function LabourPage() {
  const [open, setOpen] = useState(false)
  const labour = useList<Labour>('/labour')
  const warehouses = useList<Warehouse>('/warehouses')

  const warehouseName = (id: string | null) =>
    id ? (warehouses.data?.find((w) => w.id === id)?.name ?? '—') : '—'

  return (
    <div className="space-y-6">
      <PageHeader
        description="The helpers who load the vehicle at the godown. Held as a master because it is largely the same few people every day — the admin picks a name rather than retyping it, and a month's payments to one person can be totalled. Unloading labour at the far end is not tracked here: that money goes to the driver as a lump and he splits it himself."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New helper
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {labour.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={labour.data ?? []}
            rowKey={(l) => l.id}
            empty={
              <EmptyState
                icon={<HardHat className="size-7" />}
                title="No loading crew yet"
                description="Add the regulars, then record what they were paid against each freight."
              />
            }
            columns={[
              { key: 'name', header: 'Name', render: (l) => <span className="font-medium">{l.name}</span> },
              { key: 'phone', header: 'Phone', render: (l) => <span className="tnum">{l.phone ?? '—'}</span> },
              { key: 'wh', header: 'Warehouse', render: (l) => warehouseName(l.warehouse_id) },
              {
                key: 'trip',
                header: 'Per freight',
                align: 'right',
                render: (l) => <span className="tnum">{rupees(l.per_trip_rate)}</span>,
              },
              {
                key: 'day',
                header: 'Per day',
                align: 'right',
                render: (l) => <span className="tnum">{rupees(l.daily_rate)}</span>,
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/labour'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Loading crew member"
                    fields={[
                      { name: 'name', label: 'Name', required: true },
                      { name: 'phone', label: 'Phone', kind: 'tel' as const },
                      { name: 'daily_rate', label: 'Daily rate', kind: 'number' as const },
                      { name: 'per_trip_rate', label: 'Per trip rate', kind: 'number' as const },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      <LabourForm
        open={open}
        onClose={() => setOpen(false)}
        warehouses={warehouses.data ?? []}
      />
    </div>
  )
}

function LabourForm({
  open,
  onClose,
  warehouses,
}: {
  open: boolean
  onClose: () => void
  warehouses: Warehouse[]
}) {
  const blank = { name: '', phone: '', warehouse_id: '', per_trip_rate: '300', daily_rate: '0' }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/labour', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New helper">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              ...form,
              phone: form.phone || null,
              warehouse_id: form.warehouse_id || null,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </Field>
          <Field label="Phone">
            <Input
              className="tnum"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
        </div>

        <Field label="Usual warehouse">
          <Select
            value={form.warehouse_id}
            onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}
          >
            <option value="">Not set</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Rate per freight">
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min={0}
              value={form.per_trip_rate}
              onChange={(e) => setForm({ ...form, per_trip_rate: e.target.value })}
            />
          </Field>
          <Field label="Daily rate" hint="If he is paid by the day instead">
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min={0}
              value={form.daily_rate}
              onChange={(e) => setForm({ ...form, daily_rate: e.target.value })}
            />
          </Field>
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Add helper
          </Button>
        </div>
      </form>
    </Modal>
  )
}
