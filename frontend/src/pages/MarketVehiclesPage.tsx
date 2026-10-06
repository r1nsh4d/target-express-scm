/* The market vehicle phonebook.
 *
 * When a vendor sends a requirement on WhatsApp, the first thing the admin does
 * is find a lorry. Today that means scrolling a phone's contacts for a name he
 * half remembers, and guessing what was paid last time.
 *
 * This is that phonebook with the two facts a phone cannot hold: what we paid
 * this supplier last time, and whether they turned up. It is deliberately not
 * the fleet — a row here is somebody who might send a lorry; a Vehicle is a
 * lorry that actually ran a freight and has an odometer and an LR book.
 *
 * The ordering is the product: reliable first, then most recently hired. At 7am
 * with a load waiting, the person who turned up last time is the right call.
 */

import { useQueryClient } from '@tanstack/react-query'
import {
  Check,
  IndianRupee,
  MapPin,
  MessageCircle,
  Pencil,
  Phone,
  Plus,
  Search,

  Trash2,
  Truck,
} from 'lucide-react'
import { useCallback, useState } from 'react'

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
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { stagger, useOpenOnNewParam } from '@/lib/motion'
import type { MarketVehicle, VehicleType } from '@/lib/resources'
import { rupees, useList } from '@/lib/resources'

type Standing = MarketVehicle['standing']

const STANDING_LABEL: Record<Standing, string> = {
  RELIABLE: 'Reliable',
  UNTRIED: 'Not used yet',
  AVOID: 'Avoid',
}

const STANDING_TONE: Record<Standing, 'success' | 'neutral' | 'danger'> = {
  RELIABLE: 'success',
  UNTRIED: 'neutral',
  AVOID: 'danger',
}

export default function MarketVehiclesPage() {
  const queryClient = useQueryClient()
  const [q, setQ] = useState('')
  const [typeId, setTypeId] = useState('')
  const [editing, setEditing] = useState<MarketVehicle | null>(null)
  const [creating, setCreating] = useState(false)
  const [hiring, setHiring] = useState<MarketVehicle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useOpenOnNewParam(useCallback(() => setCreating(true), []))

  const params: Record<string, string> = {}
  if (q.trim()) params.q = q.trim()
  if (typeId) params.vehicle_type_id = typeId

  const rows = useList<MarketVehicle>(
    '/market-vehicles',
    Object.keys(params).length ? params : undefined,
  )
  const types = useList<VehicleType>('/vehicle-types')

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['/market-vehicles'] })

  async function remove(row: MarketVehicle) {
    try {
      await api.delete(`/market-vehicles/${row.id}`)
      refresh()
    } catch (e) {
      setError(apiErrorMessage(e))
    }
  }

  const list = rows.data ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        description="Lorries and suppliers you can hire in. Reliable ones first, then whoever was hired most recently — and what we paid them, so the same supplier cannot quote a different number every month."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
            Add contact
          </Button>
        }
      />

      <ErrorNote>{error}</ErrorNote>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
            style={{ color: 'var(--text-faint)' }}
          />
          <Input
            className="pl-10"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Name, phone, city or registration…"
            aria-label="Search the phonebook"
          />
        </div>
        <div className="w-full sm:w-52">
          <Select value={typeId} onChange={(e) => setTypeId(e.target.value)} aria-label="Vehicle type">
            <option value="">Any vehicle type</option>
            {types.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {rows.isLoading ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-40" style={stagger(i)} />
          ))}
        </div>
      ) : list.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Truck className="size-7" />}
            title={q || typeId ? 'Nobody matches that' : 'The phonebook is empty'}
            description={
              q || typeId
                ? 'Try a different name, city or vehicle type.'
                : 'Add the lorry owners and brokers you already call. Next time a load needs a vehicle, they are one tap away with last month’s rate beside them.'
            }
            action={
              <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                Add contact
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {list.map((row, i) => (
            <Card key={row.id} className="hoverable overflow-hidden" style={stagger(i)}>
              <div className="flex items-start justify-between gap-3 p-4 pb-2.5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-[14.5px] font-semibold">{row.contact_name}</h3>
                    <Badge tone={STANDING_TONE[row.standing]}>{STANDING_LABEL[row.standing]}</Badge>
                  </div>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                    {row.registration_no ? (
                      <span className="font-medium tracking-wide">{row.registration_no}</span>
                    ) : null}
                    {row.vehicle_type_name ? <span>{row.vehicle_type_name}</span> : null}
                    {row.base_city ? (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="size-3" />
                        {row.base_city}
                      </span>
                    ) : null}
                  </p>
                </div>

                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => setEditing(row)}
                    className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                    style={{ color: 'var(--text-muted)' }}
                    title="Edit"
                    aria-label={`Edit ${row.contact_name}`}
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  <button
                    onClick={() => remove(row)}
                    className="rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)]"
                    style={{ color: 'var(--text-faint)' }}
                    title="Remove from the phonebook"
                    aria-label={`Remove ${row.contact_name}`}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>

              {/* Calling is the whole point of the screen, so it is a control,
                  not a line of text to copy out. */}
              <div className="flex flex-wrap gap-2 px-4 pb-3">
                <a
                  href={`tel:${row.phone.replace(/\s/g, '')}`}
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                >
                  <Phone className="size-3.5" />
                  {row.phone}
                </a>
                <a
                  href={`https://wa.me/${row.phone.replace(/\D/g, '')}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px]"
                  style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
                >
                  <MessageCircle className="size-3.5" />
                  WhatsApp
                </a>
                {row.alternate_phone ? (
                  <a
                    href={`tel:${row.alternate_phone.replace(/\s/g, '')}`}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px]"
                    style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
                  >
                    <Phone className="size-3.5" />
                    {row.alternate_phone}
                  </a>
                ) : null}
              </div>

              <div className="groove mx-4" />

              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 p-4 text-[12.5px]">
                <div>
                  <span className="eyebrow block">Last rate</span>
                  <span className="tnum font-medium">
                    {row.last_hired_rate ? rupees(row.last_hired_rate) : '—'}
                  </span>
                </div>
                <div>
                  <span className="eyebrow block">Last hired</span>
                  <span className="font-medium">
                    {row.last_hired_on
                      ? new Date(row.last_hired_on).toLocaleDateString('en-IN')
                      : 'Never'}
                  </span>
                </div>
                <div>
                  <span className="eyebrow block">Times hired</span>
                  <span className="tnum font-medium">{row.times_hired}</span>
                </div>

                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="ml-auto"
                  icon={<IndianRupee className="size-3.5" />}
                  onClick={() => setHiring(row)}
                >
                  Record a hire
                </Button>
              </div>

              {row.capacity_note || row.notes ? (
                <p
                  className="mx-4 mb-4 rounded-[10px] px-3 py-2.5 text-[12.5px] leading-relaxed"
                  style={{ background: 'var(--bg)', color: 'var(--text-muted)' }}
                >
                  {[row.capacity_note, row.notes].filter(Boolean).join(' · ')}
                </p>
              ) : null}
            </Card>
          ))}
        </div>
      )}

      <ContactForm
        open={creating || !!editing}
        row={editing}
        types={types.data ?? []}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        onSaved={refresh}
      />

      <RecordHireModal row={hiring} onClose={() => setHiring(null)} onSaved={refresh} />
    </div>
  )
}

/* -------------------------------------------------------------------------- */

/** What we paid, and when. This is the memory the phone does not have — without
 *  it the same supplier quotes a different number every month and nobody
 *  notices. Recording a hire also promotes an untried contact to reliable: they
 *  turned up, which is the only evidence that matters. */
function RecordHireModal({
  row,
  onClose,
  onSaved,
}: {
  row: MarketVehicle | null
  onClose: () => void
  onSaved: () => void
}) {
  const [rate, setRate] = useState('')
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!row) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/market-vehicles/${row.id}/hired`, { rate: Number(rate), hired_on: on })
      onSaved()
      setRate('')
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={!!row}
      onClose={onClose}
      title={row ? `Hired ${row.contact_name}` : 'Record a hire'}
      description="What was agreed, so next time the number is on the screen instead of in somebody's memory."
    >
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Rate agreed" hint="The whole hire, as settled with the owner">
          <Input
            type="number"
            min={0}
            step="0.01"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            required
            autoFocus
          />
        </Field>
        <Field label="Date">
          <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </Field>

        {row?.last_hired_rate ? (
          <p className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            Last time: <span className="tnum font-medium">{rupees(row.last_hired_rate)}</span>
            {row.last_hired_on
              ? ` on ${new Date(row.last_hired_on).toLocaleDateString('en-IN')}`
              : ''}
          </p>
        ) : null}

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Record
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */

function ContactForm({
  open,
  row,
  types,
  onClose,
  onSaved,
}: {
  open: boolean
  row: MarketVehicle | null
  types: VehicleType[]
  onClose: () => void
  onSaved: () => void
}) {
  const blank = {
    contact_name: '',
    phone: '',
    alternate_phone: '',
    registration_no: '',
    vehicle_type_id: '',
    capacity_note: '',
    base_city: '',
    operating_area: '',
    standing: 'UNTRIED' as Standing,
    notes: '',
    pan: '',
    bank_account: '',
    ifsc: '',
  }

  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  const key = open ? (row?.id ?? 'new') : null
  if (key && key !== loadedFor) {
    setLoadedFor(key)
    setForm(
      row
        ? {
            contact_name: row.contact_name,
            phone: row.phone,
            alternate_phone: row.alternate_phone ?? '',
            registration_no: row.registration_no ?? '',
            vehicle_type_id: row.vehicle_type_id ?? '',
            capacity_note: row.capacity_note ?? '',
            base_city: row.base_city ?? '',
            operating_area: row.operating_area ?? '',
            standing: row.standing,
            notes: row.notes ?? '',
            pan: row.pan ?? '',
            bank_account: row.bank_account ?? '',
            ifsc: row.ifsc ?? '',
          }
        : blank,
    )
    setError(null)
  }
  if (!open && loadedFor !== null) setLoadedFor(null)

  const set = (k: keyof typeof blank) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value })

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const body = {
      ...form,
      vehicle_type_id: form.vehicle_type_id || null,
      alternate_phone: form.alternate_phone || null,
      registration_no: form.registration_no || null,
      capacity_note: form.capacity_note || null,
      base_city: form.base_city || null,
      operating_area: form.operating_area || null,
      notes: form.notes || null,
      pan: form.pan || null,
      bank_account: form.bank_account || null,
      ifsc: form.ifsc || null,
    }
    try {
      if (row) await api.put(`/market-vehicles/${row.id}`, body)
      else await api.post('/market-vehicles', body)
      onSaved()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save this contact'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={row ? `Edit ${row.contact_name}` : 'Add a market vehicle'}
      description="Only the name and a phone number are needed. A broker often has no particular lorry until the morning of the load."
    >
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Contact name">
            <Input value={form.contact_name} onChange={set('contact_name')} required autoFocus />
          </Field>
          <Field label="Phone">
            <Input type="tel" value={form.phone} onChange={set('phone')} required />
          </Field>
          <Field label="Alternate phone">
            <Input type="tel" value={form.alternate_phone} onChange={set('alternate_phone')} />
          </Field>
          <Field label="Registration" hint="If they have one particular lorry">
            <Input
              value={form.registration_no}
              onChange={set('registration_no')}
              placeholder="KL 07 AA 1234"
            />
          </Field>
          <Field label="Vehicle type">
            <Select value={form.vehicle_type_id} onChange={set('vehicle_type_id')}>
              <option value="">Not set</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Based at" hint="Decides whether calling them is worth it at all">
            <Input value={form.base_city} onChange={set('base_city')} placeholder="Kochi" />
          </Field>
        </div>

        <Field label="What they can supply" hint="“Two DOSTs at a day’s notice”, “407 only”">
          <Textarea rows={2} value={form.capacity_note} onChange={set('capacity_note')} />
        </Field>

        <Field label="Standing" hint="Can you rely on them? That is the only question at 7am.">
          <Select value={form.standing} onChange={set('standing')}>
            <option value="UNTRIED">Not used yet</option>
            <option value="RELIABLE">Reliable — would call again</option>
            <option value="AVOID">Avoid — did not turn up, or caused trouble</option>
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="PAN">
            <Input value={form.pan} onChange={set('pan')} />
          </Field>
          <Field label="Bank account">
            <Input value={form.bank_account} onChange={set('bank_account')} />
          </Field>
          <Field label="IFSC">
            <Input value={form.ifsc} onChange={set('ifsc')} />
          </Field>
        </div>

        <Field label="Notes">
          <Textarea rows={2} value={form.notes} onChange={set('notes')} />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy} icon={row ? <Check className="size-4" /> : undefined}>
            {row ? 'Save changes' : 'Add to phonebook'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
