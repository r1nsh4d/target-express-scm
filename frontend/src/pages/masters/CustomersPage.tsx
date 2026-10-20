import { useMutation } from '@tanstack/react-query'
import { Plus, Search, Send, Users } from 'lucide-react'
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
  Textarea,
} from '@/components/ui'
import { Fact, Facts, TileGrid, TileHead } from '@/components/TileGrid'
import { RowActions } from '@/components/RowActions'
import { api, apiErrorMessage } from '@/lib/api'
import type { Consignee } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

// Leaflet is ~200 kB, so the map arrives only when a form that needs it opens.
const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

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

      {consignees.isLoading ? (
        <Card>
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        </Card>
      ) : (
        <TileGrid
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
              action={
                search ? undefined : <Button onClick={() => setOpen(true)}>New customer</Button>
              }
            />
          }
          render={(c) => (
            <>
              <TileHead
                title={c.name}
                sub={c.address ?? c.city ?? 'No address on file'}
                badge={
                  <Badge tone={c.type === 'DISTRIBUTION_CENTER' ? 'info' : 'neutral'}>
                    {c.type === 'DISTRIBUTION_CENTER' ? 'Distribution centre' : 'Customer'}
                  </Badge>
                }
                actions={
                  <RowActions
                    path={'/consignees'}
                    row={c as unknown as Record<string, unknown> & { id: string }}
                    label="Customer"
                    fields={[
                      { name: 'name', label: 'Name', required: true },
                      {
                        name: 'phone',
                        label: 'Phone',
                        kind: 'tel' as const,
                        hint: 'Their tracking link is sent here',
                      },
                      { name: 'alternate_phone', label: 'Alternate phone', kind: 'tel' as const },
                      {
                        name: 'contact_person',
                        label: 'Who to ask for',
                        hint: 'The manager at a shop, the purchase contact at a distributor',
                      },
                      { name: 'city', label: 'City' },
                      { name: 'pincode', label: 'Pincode' },
                      { name: 'address', label: 'Address', kind: 'textarea' as const },
                      { name: 'landmark', label: 'Landmark', kind: 'textarea' as const },
                      {
                        name: 'delivery_notes',
                        label: 'Delivery notes',
                        kind: 'textarea' as const,
                        hint: 'Shown to the driver at the point',
                      },
                      {
                        name: 'location' as const,
                        label: 'Delivery location',
                        kind: 'location' as const,
                        hint: 'What the driver navigates to. A pin set here counts as approximate — the customer’s own, dropped at their door, is the one marked verified.',
                      },
                    ]}
                  />
                }
              />
              <Facts>
                <Fact label="City" value={c.city ?? '—'} />
                {/* No phone means no tracking link, which is the one gap on
                    this screen that costs somebody a call. */}
                <Fact
                  label="Phone"
                  value={<span className="tnum">{c.phone ?? 'Missing'}</span>}
                  tone={c.phone ? undefined : 'warning'}
                />
                <Fact
                  label="Pin"
                  value={c.geo_confidence.toLowerCase()}
                  tone={
                    c.geo_confidence === 'VERIFIED'
                      ? 'success'
                      : c.geo_confidence === 'APPROXIMATE'
                        ? 'warning'
                        : 'muted'
                  }
                />
              </Facts>

              {/* The gap worth closing, and the one way to close it that does
                  not involve somebody guessing. A record entered during a
                  morning's bills is a name and a town; the door and the pin
                  belong to the customer, so they are asked. */}
              {!c.address || c.geo_confidence !== 'VERIFIED' ? (
                <AskCustomer customer={c} />
              ) : null}
            </>
          )}
        />
      )}

      <CustomerForm open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

/* Ask the customer to finish their own record.
 *
 * A record entered while a morning's bills were being typed is a name, a
 * mobile and a town — which is what the warehouse has and all it has time
 * for. The door, the landmark and the pin belong to the person who lives
 * there, and asking them is both faster and more accurate than guessing.
 *
 * The message comes back ready to send, because somebody doing this forty
 * times in a morning should not be composing a sentence each time. Until the
 * WhatsApp number is configured it is copied and pasted by hand: a worse
 * experience and a working one, which is the right order to build them in.
 */
function AskCustomer({ customer }: { customer: Consignee }) {
  const [link, setLink] = useState<{ url: string; whatsapp_text: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ask = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ url: string; whatsapp_text: string }>(
          `/consignees/${customer.id}/details-link`,
        )
      ).data,
    onSuccess: setLink,
    onError: (e) => setError(apiErrorMessage(e)),
  })

  if (link) {
    return (
      <div
        className="mt-3 rounded-[11px] px-3 py-2.5"
        style={{ background: 'var(--accent-dim)' }}
      >
        <p className="text-[12px] leading-relaxed">
          Send this to {customer.phone ?? 'them'} and they can fill in their own address and
          drop a pin.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={() => {
              navigator.clipboard
                ?.writeText(link.whatsapp_text)
                .then(() => {
                  setCopied(true)
                  setTimeout(() => setCopied(false), 2000)
                })
                .catch(() => setError('Could not copy — select the link and copy it by hand'))
            }}
          >
            {copied ? 'Copied' : 'Copy the message'}
          </Button>
          {customer.phone ? (
            <a
              href={`https://wa.me/91${customer.phone.replace(/\D/g, '').slice(-10)}?text=${encodeURIComponent(link.whatsapp_text)}`}
              target="_blank"
              rel="noreferrer"
              className="no-underline"
            >
              <Button size="sm" variant="secondary">
                Open WhatsApp
              </Button>
            </a>
          ) : null}
        </div>
        <p className="mt-2 break-all text-[11px]" style={{ color: 'var(--text-faint)' }}>
          {link.url}
        </p>
        <ErrorNote>{error}</ErrorNote>
      </div>
    )
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => {
          setError(null)
          ask.mutate()
        }}
        disabled={ask.isPending}
        className="inline-flex items-center gap-1.5 text-[12px] underline underline-offset-2"
        style={{ color: 'var(--accent)' }}
      >
        <Send className="size-3.5" />
        {ask.isPending ? 'Making a link…' : 'Ask them for their address'}
      </button>
      <ErrorNote>{error}</ErrorNote>
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

  // Wide: this form carries a map as well as the address fields, and at the
  // narrow width the map was a 260px strip you could not aim a pin in.
  return (
    <Modal open={open} onClose={onClose} wide title="New customer">
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
