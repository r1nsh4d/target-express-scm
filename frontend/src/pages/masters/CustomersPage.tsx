import { Plus, Search, Users } from 'lucide-react'
import { Suspense, lazy, useCallback, useState } from 'react'

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
import type { Consignee } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

// Leaflet is ~200 kB, so the map arrives only when a form that needs it opens.
const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

const GEO_TONE: Record<string, 'success' | 'warning' | 'neutral'> = {
  VERIFIED: 'success',
  APPROXIMATE: 'warning',
  UNVERIFIED: 'neutral',
}

export default function CustomersPage() {
  const [open, setOpen] = useState(false)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen(true), []))
  const [search, setSearch] = useState('')
  const consignees = useList<Consignee>('/consignees', search ? { q: search } : undefined)

  return (
    <div className="space-y-6">
      <PageHeader
        description="A pin corrected by a customer is saved back here, so the next delivery to the same address is already right."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New customer
          </Button>
        }
      />

      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
          style={{ color: 'var(--text-faint)' }}
        />
        <Input
          className="pl-10"
          placeholder="Search by name, city or phone"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Card className="overflow-hidden">
        {consignees.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={consignees.data ?? []}
            rowKey={(c) => c.id}
            empty={
              <EmptyState
                icon={<Users className="size-7" />}
                title={search ? 'No matches' : 'No customers yet'}
                description={
                  search
                    ? 'Try a different name, city or phone number.'
                    : 'Add the delivery points before building a trip.'
                }
                action={search ? undefined : <Button onClick={() => setOpen(true)}>New customer</Button>}
              />
            }
            columns={[
              { key: 'name', header: 'Name', render: (c) => <span className="font-medium">{c.name}</span> },
              {
                key: 'type',
                header: 'Type',
                render: (c) => (
                  <Badge tone={c.type === 'DISTRIBUTION_CENTER' ? 'info' : 'neutral'}>
                    {c.type === 'DISTRIBUTION_CENTER' ? 'Distribution centre' : 'Customer'}
                  </Badge>
                ),
              },
              { key: 'city', header: 'City', render: (c) => c.city ?? '—' },
              {
                key: 'phone',
                header: 'Phone',
                render: (c) =>
                  c.phone ? (
                    <span className="tnum">{c.phone}</span>
                  ) : (
                    <span style={{ color: 'var(--warning)' }}>Missing</span>
                  ),
              },
              {
                key: 'geo',
                header: 'Location',
                render: (c) => (
                  <Badge tone={GEO_TONE[c.geo_confidence] ?? 'neutral'}>
                    {c.geo_confidence.toLowerCase()}
                  </Badge>
                ),
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/consignees'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Customer"
                    fields={[
                      { name: 'name', label: 'Name', required: true },
                      { name: 'phone', label: 'Phone', kind: 'tel' as const, hint: 'Their tracking link is sent here' },
                      { name: 'alternate_phone', label: 'Alternate phone', kind: 'tel' as const },
                      { name: 'city', label: 'City' },
                      { name: 'pincode', label: 'Pincode' },
                      { name: 'address', label: 'Address', kind: 'textarea' as const },
                      { name: 'landmark', label: 'Landmark', kind: 'textarea' as const },
                      { name: 'delivery_notes', label: 'Delivery notes', kind: 'textarea' as const, hint: 'Shown to the driver at the point' },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      <CustomerForm open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

function CustomerForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const blank = {
    name: '',
    type: 'RETAIL_CUSTOMER',
    phone: '',
    address: '',
    city: '',
    pincode: '',
    latitude: '',
    longitude: '',
    landmark: '',
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<Record<string, unknown>>('/consignees', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New customer">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              ...form,
              phone: form.phone || null,
              latitude: form.latitude || null,
              longitude: form.longitude || null,
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
          <Field label="Type">
            <Select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="RETAIL_CUSTOMER">Customer</option>
              <option value="DISTRIBUTION_CENTER">Distribution centre</option>
            </Select>
          </Field>
        </div>

        <Field
          label="Mobile number"
          hint="The tracking link goes here — without it the customer cannot follow the delivery"
        >
          <Input
            className="tnum"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
        </Field>

        <Field label="Address">
          <Textarea
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="City">
            <Input
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />
          </Field>
          <Field label="Pincode">
            <Input
              className="tnum"
              value={form.pincode}
              onChange={(e) => setForm({ ...form, pincode: e.target.value })}
            />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
            Delivery location
          </p>
          <Suspense fallback={<div className="inset h-[260px] animate-pulse" />}>
            <LocationPicker
              value={
              form.latitude && form.longitude
                  ? { lat: Number(form.latitude), lng: Number(form.longitude) }
                  : null
              }
              onChange={(p) =>
                setForm({
                  ...form,
                  latitude: p ? String(p.lat) : '',
                  longitude: p ? String(p.lng) : '',
                })
              }
            />
          </Suspense>
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create customer
          </Button>
        </div>
      </form>
    </Modal>
  )
}
