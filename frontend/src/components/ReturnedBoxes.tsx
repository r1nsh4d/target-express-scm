import { useMutation, useQuery } from '@tanstack/react-query'
import { PackageX, ScanBarcode } from 'lucide-react'
import { useState } from 'react'

import { BoxScanner } from '@/components/BoxScanner'
import { Button, Card, Input, Select } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

/* What came back, scanned at the warehouse before the trip is closed.
 *
 * Everything loaded was either delivered or came back, and until both halves
 * are recorded the difference reads as "unaccounted" — which should mean a
 * box nobody can find, not one standing in the godown.
 *
 * The driver does it because he is the one unloading the vehicle. A carton
 * counted the next morning has already had a night to be misremembered.
 *
 * The count is shown as he goes, so he can see when he is finished rather
 * than counting the pile himself — and the thing he most needs the screen to
 * catch is a carton that says DELIVERED and is in his hand.
 */

interface Reconciliation {
  result: string
  message: string
  barcode: string | null
  bill_no: string | null
  item_name: string | null
  loaded: number
  delivered: number
  returned: number
  unaccounted: number
}

const TONE: Record<string, { bg: string; fg: string }> = {
  OK: { bg: 'color-mix(in oklab, var(--success) 15%, transparent)', fg: 'var(--success)' },
  ALREADY: { bg: 'var(--bg-elevated)', fg: 'var(--text-muted)' },
  UNKNOWN: { bg: 'color-mix(in oklab, var(--warning) 15%, transparent)', fg: 'var(--warning)' },
  WAS_DELIVERED: {
    bg: 'color-mix(in oklab, var(--danger) 15%, transparent)',
    fg: 'var(--danger)',
  },
}

export function ReturnedBoxes({ freightId }: { freightId: string }) {
  const [typed, setTyped] = useState('')
  const [reason, setReason] = useState('Came back on the vehicle')
  const [state, setState] = useState('RETURNED_TO_WAREHOUSE')
  const [last, setLast] = useState<Reconciliation | null>(null)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const counts = useQuery({
    queryKey: ['/driver/reconciliation', freightId],
    queryFn: async () =>
      (await api.get<Reconciliation>(`/driver/freights/${freightId}/reconciliation`)).data,
  })

  const scan = useMutation({
    mutationFn: async (code: string) =>
      (
        await api.post<Reconciliation>(`/driver/freights/${freightId}/returns`, {
          code,
          status: state,
          reason,
        })
      ).data,
    onSuccess: (data) => {
      setLast(data)
      setTyped('')
      counts.refetch()
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const now = last ?? counts.data
  const outstanding = now?.unaccounted ?? 0

  return (
    <Card className="p-4">
      <div className="flex items-start gap-2.5">
        <PackageX className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--warning)' }} />
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold">Boxes that came back</h2>
          <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            Scan anything still on the vehicle before you close the trip.
          </p>
        </div>
      </div>

      {now ? (
        <div className="mt-3 grid grid-cols-4 gap-2 text-center">
          {[
            [now.loaded, 'loaded'],
            [now.delivered, 'delivered'],
            [now.returned, 'came back'],
            [now.unaccounted, 'unaccounted'],
          ].map(([value, label], i) => (
            <div
              key={label as string}
              className="rounded-[var(--radius-control)] px-2 py-2"
              style={{
                background:
                  i === 3 && Number(value) > 0
                    ? 'color-mix(in oklab, var(--warning) 12%, transparent)'
                    : 'var(--bg-elevated)',
              }}
            >
              <p
                className="tnum text-[18px] font-semibold"
                style={
                  i === 3 && Number(value) > 0
                    ? { color: 'var(--warning)' }
                    : i === 3
                      ? { color: 'var(--success)' }
                      : undefined
                }
              >
                {value as number}
              </p>
              <p className="text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
                {label as string}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      {outstanding === 0 && now ? (
        <p className="mt-2 text-[12.5px]" style={{ color: 'var(--success)' }}>
          Everything is accounted for. You can close the trip.
        </p>
      ) : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Select value={state} onChange={(e) => setState(e.target.value)}>
          <option value="RETURNED_TO_WAREHOUSE">Came back — refused or not taken</option>
          <option value="DAMAGED">Damaged</option>
          <option value="NOT_DELIVERED">Nobody there to take it</option>
        </Select>
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why it came back"
        />
      </div>

      <div className="mt-2 flex gap-2">
        <Input
          className="font-mono text-[13px]"
          placeholder="Or type the sticker"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            // A hand scanner types the code and presses Enter.
            if (e.key === 'Enter' && typed.trim()) {
              e.preventDefault()
              scan.mutate(typed.trim())
            }
          }}
        />
        <Button
          variant="secondary"
          disabled={!typed.trim()}
          loading={scan.isPending}
          onClick={() => scan.mutate(typed.trim())}
        >
          Add
        </Button>
      </div>

      {/* The camera, for the common case. Typing is kept beside it because a
          phone that will not focus in a dark godown must not stop a trip
          being closed. */}
      <Button
        variant="secondary"
        className="mt-2 w-full"
        icon={<ScanBarcode className="size-4" />}
        onClick={() => setScanning(true)}
      >
        Scan with the camera
      </Button>

      <BoxScanner
        open={scanning}
        onClose={() => setScanning(false)}
        onCode={(code) => scan.mutate(code)}
        title="Boxes that came back"
        subtitle="Scan each carton still on the vehicle"
      />

      {/* The verdict, coloured. A carton that says delivered and is in his
          hand is the one he must not scan past — one of the two records is
          wrong and quietly flipping the box would hide it. */}
      {last && last.result !== 'COUNT' ? (
        <div
          className="mt-2 rounded-[var(--radius-control)] px-3.5 py-2.5 text-[13px]"
          style={{
            background: TONE[last.result]?.bg ?? 'var(--bg-elevated)',
            color: TONE[last.result]?.fg ?? 'var(--text)',
          }}
        >
          <p className="font-medium">{last.message}</p>
          {last.barcode ? (
            <p className="mt-0.5 font-mono text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
              {last.barcode}
              {last.bill_no ? ` · bill ${last.bill_no}` : ''}
              {last.item_name ? ` · ${last.item_name}` : ''}
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p className="mt-2 text-[12.5px]" style={{ color: 'var(--danger)' }}>
          {error}
        </p>
      ) : null}
    </Card>
  )
}
