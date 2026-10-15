import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Minus, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button, ErrorNote, Field, Input, Spinner } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { rupees } from '@/lib/resources'

/* What the driver actually carried in.
 *
 * The vendor's unloading charge used to come from the boxes on the bill, which
 * is a guess at what happened: the bill says five chairs, four came off the
 * lorry, one was refused at the door, and the sheet charged for five anyway.
 * The man who carried them knows, and he is standing there with a phone.
 *
 * Built for that phone and that moment — one hand, in a lorry bay, often in
 * the dark. So: big plus and minus buttons rather than a number pad, the floor
 * as a row of taps rather than a field, and the rupees updating as he goes so
 * he can see it is right before he confirms. He is never asked to do the
 * arithmetic; the rates came down already priced for this door.
 */

interface Article {
  item_code: string
  item_name: string
  vendor_each: string
  driver_each: string
  quantity: number
}

interface Sheet {
  floor_number: number
  has_lift: boolean
  articles: Article[]
  vendor_total: string
  driver_total: string
  coolie_paid: string
  coolie_note: string | null
  priced_per_article: boolean
  shows_earnings: boolean
}

const FLOORS = [0, 1, 2, 3, 4, 5]

export function UnloadingSheet({
  pointId,
  onSaved,
}: {
  pointId: string
  onSaved?: () => void
}) {
  const [qty, setQty] = useState<Record<string, number>>({})
  const [floor, setFloor] = useState<number | null>(null)
  const [lift, setLift] = useState<boolean | null>(null)
  const [coolie, setCoolie] = useState('')
  const [coolieNote, setCoolieNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  /* Re-priced by the server as the floor changes, because the rates and the
     climb rules live on the rate card and a phone should not carry a copy of
     them that can drift. */
  const sheet = useQuery({
    queryKey: ['/driver/unloading', pointId, floor, lift],
    queryFn: async () =>
      (
        await api.get<Sheet>(`/driver/points/${pointId}/unloading`, {
          params: {
            ...(floor !== null ? { floor } : {}),
            ...(lift !== null ? { lift } : {}),
          },
        })
      ).data,
  })

  // Seed from whatever is already recorded, once.
  useEffect(() => {
    const data = sheet.data
    if (!data) return
    setQty((current) =>
      Object.keys(current).length
        ? current
        : Object.fromEntries(data.articles.map((a) => [a.item_code, a.quantity])),
    )
    setFloor((f) => (f === null ? data.floor_number : f))
    setLift((l) => (l === null ? data.has_lift : l))
    setCoolie((c) => (c === '' && Number(data.coolie_paid) > 0 ? data.coolie_paid : c))
    setCoolieNote((n) => (n === '' ? (data.coolie_note ?? '') : n))
  }, [sheet.data])

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<Sheet>(`/driver/points/${pointId}/unloading`, {
          articles: Object.entries(qty).map(([item_code, quantity]) => ({
            item_code,
            quantity,
          })),
          floor_number: floor,
          has_lift: lift,
          coolie_paid: coolie || '0',
          coolie_note: coolieNote || null,
        })
      ).data,
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2200)
      onSaved?.()
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  if (sheet.isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="size-5" />
      </div>
    )
  }
  if (!sheet.data) return null

  // Spare parts are carried in and nothing is charged. A list of articles
  // nobody can fill in would be worse than not asking.
  if (!sheet.data.priced_per_article) return null

  /* Decided on the server. A driver on a rented vehicle is paid by the
     vehicle's owner, not by Target Express, so his side arrives zeroed and
     is not shown — rather than being sent and hidden. */
  const canSeeEarnings = sheet.data.shows_earnings

  const articles = sheet.data.articles
  const vendorTotal = articles.reduce(
    (sum, a) => sum + Number(a.vendor_each) * (qty[a.item_code] ?? 0),
    0,
  )
  const driverTotal = articles.reduce(
    (sum, a) => sum + Number(a.driver_each) * (qty[a.item_code] ?? 0),
    0,
  )
  const carried = articles.reduce((sum, a) => sum + (qty[a.item_code] ?? 0), 0)

  function step(code: string, by: number) {
    setQty((current) => ({ ...current, [code]: Math.max(0, (current[code] ?? 0) + by) }))
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[13px] font-medium">What did you carry in?</p>
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
          Count what actually went inside, not what the bill says.
        </p>
      </div>

      <div className="space-y-2">
        {articles.map((a) => {
          const n = qty[a.item_code] ?? 0
          return (
            <div
              key={a.item_code}
              className="flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2"
              style={{
                background: n > 0 ? 'var(--accent-dim)' : 'var(--bg-elevated)',
              }}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium">{a.item_name}</p>
                <p className="tnum text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                  {rupees(a.vendor_each)} each
                  {canSeeEarnings ? ` · you earn ${rupees(a.driver_each)}` : ''}
                </p>
              </div>

              {/* Big targets. One hand, in a lorry bay, often in the dark. */}
              <button
                type="button"
                onClick={() => step(a.item_code, -1)}
                disabled={n === 0}
                className="grid size-11 shrink-0 place-items-center rounded-full disabled:opacity-25"
                style={{ background: 'var(--surface)', color: 'var(--text)' }}
                aria-label={`One less ${a.item_name}`}
              >
                <Minus className="size-5" />
              </button>
              <span className="tnum w-7 shrink-0 text-center text-[18px] font-semibold">{n}</span>
              <button
                type="button"
                onClick={() => step(a.item_code, 1)}
                className="grid size-11 shrink-0 place-items-center rounded-full"
                style={{ background: 'var(--accent)', color: '#04121a' }}
                aria-label={`One more ${a.item_name}`}
              >
                <Plus className="size-5" />
              </button>
            </div>
          )
        })}
      </div>

      <div>
        <p className="mb-1.5 text-[13px] font-medium">Which floor did you carry to?</p>
        <div className="flex flex-wrap gap-2">
          {FLOORS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFloor(f)}
              className="tnum h-11 min-w-11 rounded-[var(--radius-control)] px-3 text-[15px] font-semibold"
              style={
                floor === f
                  ? { background: 'var(--accent)', color: '#04121a' }
                  : { background: 'var(--bg-elevated)', color: 'var(--text-muted)' }
              }
            >
              {f === 0 ? 'Ground' : f}
            </button>
          ))}
        </div>
        <label className="mt-2 flex items-center gap-2.5 text-[13px]">
          <input
            type="checkbox"
            className="size-5 accent-[var(--accent)]"
            checked={!!lift}
            onChange={(e) => setLift(e.target.checked)}
          />
          There was a lift
        </label>
      </div>

      {/* Shown as it is built, so he can see it is right before confirming
          rather than discovering it on a settlement a month later. */}
      <div className="inset space-y-1.5 px-3.5 py-3">
        <div className="flex items-baseline justify-between text-[13px]">
          <span style={{ color: 'var(--text-muted)' }}>
            {carried} {carried === 1 ? 'article' : 'articles'}
            {floor ? `, floor ${floor}` : ', ground floor'}
          </span>
          <span className="tnum font-medium">{rupees(vendorTotal.toFixed(2))}</span>
        </div>
        {canSeeEarnings ? (
          <div className="flex items-baseline justify-between text-[13px]">
            <span style={{ color: 'var(--text-muted)' }}>You earn</span>
            <span className="tnum font-semibold" style={{ color: 'var(--success)' }}>
              {rupees(driverTotal.toFixed(2))}
            </span>
          </div>
        ) : null}
      </div>

      {/* Kept apart from unloading, always. A porter gang at a market gate is
          not Target Express's crew and not on the rate sheet — it is a cash
          demand the driver settles and the vendor reimburses, and folding it
          in makes "why has unloading gone up?" unanswerable. */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Coolie paid" hint="Porter cash, if any. Not unloading.">
          <Input
            className="tnum"
            type="number"
            inputMode="decimal"
            min={0}
            placeholder="0"
            value={coolie}
            onChange={(e) => setCoolie(e.target.value)}
          />
        </Field>
        <Field label="What was it for?">
          <Input
            value={coolieNote}
            onChange={(e) => setCoolieNote(e.target.value)}
            placeholder="Market gang at the gate"
          />
        </Field>
      </div>

      <ErrorNote>{error}</ErrorNote>

      <Button
        type="button"
        size="lg"
        variant={saved ? 'secondary' : 'primary'}
        className="w-full"
        icon={saved ? <Check className="size-4" /> : undefined}
        loading={save.isPending}
        onClick={() => {
          setError(null)
          save.mutate()
        }}
      >
        {saved ? 'Unloading saved' : 'Save the unloading'}
      </Button>
    </div>
  )
}
