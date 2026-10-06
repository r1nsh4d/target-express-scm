import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  MapPin,
  Package,
  PackageCheck,
  Phone,
  Truck,
} from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { useParams } from 'react-router-dom'

import { Button, Card, ErrorNote, Spinner } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

const LocationPicker = lazy(() =>
  import('@/components/LocationPicker').then((m) => ({ default: m.LocationPicker })),
)

/* The customer's page. No login, no app — the token in the link is the whole
   credential. It shows this delivery and nothing else: no vendor, no other
   customers on the run, no prices. */

interface TrackedBox {
  bill_no: string
  item_no: number
  of_total: number
  item_name: string | null
  delivered: boolean
}

interface Tracking {
  consignee_name: string
  address: string | null
  status: string
  stop_number: number
  stops_before: number
  box_count: number
  boxes: TrackedBox[]
  dispatched: boolean
  planned_eta: string | null
  arrived_at: string | null
  delivered_at: string | null
  latitude: number | null
  longitude: number | null
  can_update_location: boolean
  vehicle_position: { latitude: number; longitude: number; recorded_at: string } | null
  driver_phone: string | null
  delivery_photo_url: string | null
  receiver_name: string | null
}

export default function TrackPage() {
  const { token } = useParams<{ token: string }>()
  const queryClient = useQueryClient()
  const [fixing, setFixing] = useState(false)
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: ['track', token],
    queryFn: async () => (await api.get<Tracking>(`/track/${token}`)).data,
    retry: false,
    // The vehicle moves; this page should not need a reload to show it.
    refetchInterval: 45_000,
  })

  const submitLocation = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ message: string }>(`/track/${token}/location`, {
          latitude: pin!.lat,
          longitude: pin!.lng,
        })
      ).data,
    onSuccess: (res) => {
      setNote(res.message)
      setFixing(false)
      setPin(null)
      queryClient.invalidateQueries({ queryKey: ['track', token] })
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
            {apiErrorMessage(loadError, 'This tracking link is no longer active.')}
          </p>
          <p className="mt-2 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            If your delivery is still expected, please contact the sender for a new link.
          </p>
        </Card>
      </Shell>
    )
  }

  const delivered = data.status === 'DELIVERED' || data.status === 'PART_DELIVERED'

  return (
    <Shell>
      <div className="space-y-4">
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <span
              className="grid size-10 shrink-0 place-items-center rounded-full"
              style={
                delivered
                  ? { background: 'color-mix(in oklab, var(--success) 16%, transparent)', color: 'var(--success)' }
                  : { background: 'var(--rail)', color: 'var(--rail-text)' }
              }
            >
              {delivered ? <PackageCheck className="size-5" /> : <Truck className="size-5" />}
            </span>
            <div className="min-w-0">
              <p className="text-[17px] font-semibold">{data.consignee_name}</p>
              <p className="mt-0.5 text-[13.5px]" style={{ color: 'var(--text-muted)' }}>
                {delivered
                  ? 'Delivered'
                  : data.dispatched
                    ? data.stops_before === 0
                      ? 'Your delivery is next'
                      : `${data.stops_before} ${data.stops_before === 1 ? 'stop' : 'stops'} before yours`
                    : 'Being prepared at the warehouse'}
              </p>
            </div>
          </div>

          {data.address ? (
            <p
              className="mt-4 flex gap-2 text-[13px] leading-relaxed"
              style={{ color: 'var(--text-muted)' }}
            >
              <MapPin className="mt-0.5 size-3.5 shrink-0" />
              {data.address}
            </p>
          ) : null}

          {delivered && data.receiver_name ? (
            <p className="mt-3 flex items-center gap-2 text-[13px]" style={{ color: 'var(--success)' }}>
              <CheckCircle2 className="size-4" />
              Received by {data.receiver_name}
            </p>
          ) : null}

          {data.driver_phone && !delivered ? (
            <a href={`tel:${data.driver_phone}`} className="mt-4 block">
              <Button variant="secondary" className="w-full" icon={<Phone className="size-4" />}>
                Call the driver
              </Button>
            </a>
          ) : null}
        </Card>

        <Card className="overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="text-[14px] font-semibold">
              Your {data.box_count} {data.box_count === 1 ? 'box' : 'boxes'}
            </h2>
            <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
              Listed against the bill numbers on the cartons.
            </p>
          </div>
          {data.boxes.length ? (
            <ul>
              {data.boxes.map((b) => (
                <li
                  key={`${b.bill_no}-${b.item_no}`}
                  className="flex items-center gap-3 px-5 py-2.5"
                  style={{ borderTop: '1px solid var(--border)' }}
                >
                  <Package
                    className="size-4 shrink-0"
                    style={{ color: b.delivered ? 'var(--success)' : 'var(--text-faint)' }}
                  />
                  <span className="tnum flex-1 text-[13px]">
                    Bill {b.bill_no} · box {b.item_no} of {b.of_total}
                    {b.item_name ? ` · ${b.item_name}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 pb-5 text-[13px]" style={{ color: 'var(--text-muted)' }}>
              {data.box_count} boxes are on their way.
            </p>
          )}
        </Card>

        {delivered && data.delivery_photo_url ? (
          <Card className="overflow-hidden">
            <div className="px-5 py-4">
              <h2 className="text-[14px] font-semibold">Proof of delivery</h2>
            </div>
            <img src={data.delivery_photo_url} alt="Proof of delivery" className="w-full" />
          </Card>
        ) : null}

        {note ? (
          <Card
            className="px-5 py-4 text-[13px]"
            style={{ background: 'color-mix(in oklab, var(--success) 10%, var(--surface))' }}
          >
            {note}
          </Card>
        ) : null}

        {data.can_update_location ? (
          <Card className="p-5">
            <h2 className="text-[14px] font-semibold">Is the location right?</h2>
            <p className="mt-1 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              If the pin is wrong, move it and the driver will use the corrected one.
            </p>

            {fixing ? (
              <div className="mt-4 space-y-3">
                <Suspense fallback={<div className="inset h-[240px] animate-pulse" />}>
                  <LocationPicker
                    value={
                      pin ??
                      (data.latitude != null && data.longitude != null
                        ? { lat: data.latitude, lng: data.longitude }
                        : null)
                    }
                    onChange={setPin}
                    height={240}
                  />
                </Suspense>
                <ErrorNote>{error}</ErrorNote>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setFixing(false)} className="flex-1">
                    Cancel
                  </Button>
                  <Button
                    className="flex-1"
                    disabled={!pin}
                    loading={submitLocation.isPending}
                    onClick={() => {
                      setError(null)
                      submitLocation.mutate()
                    }}
                  >
                    Use this location
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                className="mt-4 w-full"
                icon={<MapPin className="size-4" />}
                onClick={() => setFixing(true)}
              >
                Correct the location
              </Button>
            )}
          </Card>
        ) : null}
      </div>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="px-5 py-4" style={{ background: 'var(--rail)' }}>
        <div className="mx-auto flex max-w-lg items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-8 place-items-center rounded-[8px] text-[13px] font-bold italic"
            style={{ background: 'var(--rail-text)', color: 'var(--rail)' }}
          >
            TE
          </span>
          <div className="leading-none">
            <p
              className="text-[12.5px] font-semibold italic tracking-[0.08em] uppercase"
              style={{ color: 'var(--rail-text)' }}
            >
              Target Express
            </p>
            <p
              className="mt-[3px] text-[9px] tracking-[0.2em] uppercase"
              style={{ color: 'var(--rail-faint)' }}
            >
              Logistics to connect world
            </p>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-5">{children}</main>
    </div>
  )
}
