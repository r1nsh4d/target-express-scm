/* The customer filling in their own delivery details.
 *
 * The warehouse types a name, a mobile and a town, because that is what it
 * has at seven in the morning with thirty bills to enter. Everything that
 * makes a delivery findable — the door, the landmark, the floor, the pin —
 * belongs to the person who lives there, and the only practical way to ask is
 * to send them a link.
 *
 * So this is built for the person at the other end of a WhatsApp message: no
 * login, no app, one screen, and a map they can drag. The token in the link
 * is the whole credential and it reaches exactly one record.
 *
 * WHAT IT DOES NOT ASK. Their name is fixed, because it has to keep matching
 * the vendor's bill. Their number is fixed, because the link was sent to it.
 * Neither is editable here and neither is a field they have to skip past.
 *
 * THE PIN IS THE POINT. Everything else saves a phone call; the pin saves the
 * driver forty minutes. It is the largest thing on the page for that reason.
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, MapPin } from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { useParams } from 'react-router-dom'

import { Button, Card, ErrorNote, Field, Input, Spinner, Textarea } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { BRAND } from '@/lib/brand'

const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

interface MyDetails {
  name: string
  type: string
  phone: string | null
  contact_person: string | null
  address: string | null
  city: string | null
  pincode: string | null
  landmark: string | null
  delivery_notes: string | null
  latitude: number | null
  longitude: number | null
  already_completed: boolean
  company_name: string
}

export default function MyDetailsPage() {
  const { token } = useParams<{ token: string }>()
  const [form, setForm] = useState<Partial<MyDetails> | null>(null)
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: ['my-details', token],
    queryFn: async () => (await api.get<MyDetails>(`/my-details/${token}`)).data,
    retry: false,
  })

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<MyDetails>(`/my-details/${token}`, {
          ...form,
          ...(pin ? { latitude: pin.lat, longitude: pin.lng } : {}),
        })
      ).data,
    onSuccess: () => {
      setSaved(true)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  if (isLoading) {
    return (
      <Shell>
        <div className="flex justify-center py-24">
          <Spinner className="size-6" />
        </div>
      </Shell>
    )
  }

  if (isError || !data) {
    return (
      <Shell>
        <Card className="p-8 text-center">
          <p className="text-[15px] font-medium">
            {apiErrorMessage(loadError, 'This link is no longer active.')}
          </p>
          <p className="mt-2 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            Ask us to send you a new one and it will work straight away.
          </p>
        </Card>
      </Shell>
    )
  }

  // Seeded once, from what is already on file, so somebody correcting one
  // line does not have to retype the other five.
  const current = form ?? data
  const set = (patch: Partial<MyDetails>) => {
    setForm({ ...current, ...patch })
    setSaved(false)
  }

  const current_pin =
    pin ??
    (data.latitude != null && data.longitude != null
      ? { lat: data.latitude, lng: data.longitude }
      : null)

  return (
    <Shell>
      <div className="space-y-4">
        <Card className="tx-in p-5">
          <p className="text-[11px] tracking-[0.14em] uppercase" style={{ color: 'var(--text-faint)' }}>
            {data.company_name}
          </p>
          <h1 className="mt-1 text-[22px] leading-tight font-semibold">
            Where should we deliver to you?
          </h1>
          <p className="mt-1.5 text-[13.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            We have you as <strong style={{ color: 'var(--text)' }}>{data.name}</strong>
            {data.phone ? ` on ${data.phone}` : ''}. Fill this in once and every delivery after
            it goes to the right door.
          </p>
        </Card>

        {saved ? (
          <Card
            className="flex items-start gap-2.5 px-5 py-4"
            style={{ background: 'color-mix(in oklab, var(--success) 12%, var(--surface))' }}
          >
            <Check className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--success)' }} />
            <p className="text-[13px] leading-relaxed">
              Saved, thank you. You can change any of it later from this same link.
            </p>
          </Card>
        ) : null}

        {/* The pin first. Everything else on this page saves a phone call;
            this saves the driver forty minutes of asking in the street. */}
        <Card className="p-5">
          <h2 className="flex items-center gap-2 text-[14px] font-semibold">
            <MapPin className="size-4" style={{ color: 'var(--accent)' }} />
            Drop a pin on your door
          </h2>
          <p className="mt-1 text-[12.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Press the button for your current location if you are standing there now, or drag
            the map. This is what the driver navigates to.
          </p>
          <div className="mt-3">
            <Suspense fallback={<div className="inset h-[260px] animate-pulse" />}>
              <LocationPicker
                value={current_pin}
                onChange={(p) => {
                  setPin(p)
                  setSaved(false)
                }}
                height={260}
              />
            </Suspense>
          </div>
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="text-[14px] font-semibold">Your address</h2>

          <Field label="Full address">
            <Textarea
              rows={3}
              value={current.address ?? ''}
              placeholder="Shop or house number, street, area"
              onChange={(e) => set({ address: e.target.value })}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Town or city">
              <Input value={current.city ?? ''} onChange={(e) => set({ city: e.target.value })} />
            </Field>
            <Field label="Pincode">
              <Input
                className="tnum"
                inputMode="numeric"
                value={current.pincode ?? ''}
                onChange={(e) => set({ pincode: e.target.value })}
              />
            </Field>
          </div>

          <Field label="Landmark" hint="What the driver should look for from the road">
            <Input
              value={current.landmark ?? ''}
              placeholder="Opposite the bus stand"
              onChange={(e) => set({ landmark: e.target.value })}
            />
          </Field>

          {/* A shop has somebody who signs for goods; a household does not.
              Asked of everyone, insisted on by nobody. */}
          <Field
            label="Who should the driver ask for?"
            hint={data.type === 'DISTRIBUTION_CENTER' ? 'The person at the gate' : 'Optional'}
          >
            <Input
              value={current.contact_person ?? ''}
              onChange={(e) => set({ contact_person: e.target.value })}
            />
          </Field>

          <Field
            label="Anything else the driver should know?"
            hint="A floor, a narrow lane, a time the shutter is open"
          >
            <Textarea
              rows={2}
              value={current.delivery_notes ?? ''}
              placeholder="First floor, no lift. Side shutter after 6pm."
              onChange={(e) => set({ delivery_notes: e.target.value })}
            />
          </Field>

          <ErrorNote>{error}</ErrorNote>

          <Button
            size="lg"
            className="w-full"
            loading={save.isPending}
            onClick={() => {
              setError(null)
              save.mutate()
            }}
          >
            Save my details
          </Button>

          <p className="text-center text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
            Only {data.company_name} sees this, and only to deliver to you.
          </p>
        </Card>
      </div>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="relative flex min-h-dvh flex-col overflow-hidden"
      style={{ background: 'var(--bg)' }}
    >
      <div className="aurora" aria-hidden />
      <div className="grid-field" aria-hidden />

      <header className="relative z-10 px-5 py-5">
        <div className="mx-auto flex max-w-lg items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-9 place-items-center rounded-[10px] text-[13px] font-bold italic"
            style={{ background: 'var(--accent-grad)', color: '#04121a' }}
          >
            TE
          </span>
          <div className="leading-none">
            <p className="text-[12.5px] font-semibold italic tracking-[0.08em] uppercase">
              {BRAND.name}
            </p>
            <p
              className="mt-[3px] text-[9px] tracking-[0.2em] uppercase"
              style={{ color: 'var(--text-faint)' }}
            >
              {BRAND.tagline}
            </p>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-lg flex-1 px-4 pt-1 pb-10">
        {children}
      </main>
    </div>
  )
}
