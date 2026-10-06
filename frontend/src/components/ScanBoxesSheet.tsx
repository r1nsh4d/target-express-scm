/* Scanning the cartons off the vehicle at one stop.
 *
 * The screen is a checklist with a camera attached, not a camera with a list
 * attached — and that ordering is deliberate. The list is what a driver falls
 * back to when the camera will not focus in a dark lorry, and it is what he
 * shows the customer. The scanner is the fast path, not the only path.
 *
 * The verdict after each scan is the product. Three outcomes matter:
 *
 *   OK           counted, shown green, the phone buzzes
 *   ALREADY      a slip, not an error — the camera sees the same sticker on
 *                many frames and a driver re-scans out of habit
 *   WRONG_POINT  the whole reason this exists. Loud, red, names the customer
 *                it actually belongs to, and does not count.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, CircleCheck, ScanLine, X } from 'lucide-react'
import { useState } from 'react'

import { BoxScanner } from '@/components/BoxScanner'
import { Button, Spinner } from '@/components/ui'
import { api } from '@/lib/api'

interface PointBox {
  id: string
  barcode: string
  item_no: number
  item_name: string | null
  bill_no: string
  scanned: boolean
}

interface ScanResult {
  result: 'OK' | 'ALREADY' | 'WRONG_POINT' | 'UNKNOWN'
  message: string
  barcode: string | null
  item_name: string | null
  bill_no: string | null
  belongs_to_point: number | null
  belongs_to_consignee: string | null
  scanned_count: number
  expected_count: number
  all_scanned: boolean
}

export function ScanBoxesSheet({
  open,
  point,
  onClose,
  onAllScanned,
}: {
  open: boolean
  point: { id: string; consignee_name: string; sequence: number }
  onClose: () => void
  onAllScanned: (count: number) => void
}) {
  const queryClient = useQueryClient()
  const [camera, setCamera] = useState(false)
  const [last, setLast] = useState<ScanResult | null>(null)

  const key = ['driver-point-boxes', point.id]

  const boxes = useQuery({
    queryKey: key,
    queryFn: async () =>
      (await api.get<PointBox[]>(`/driver/points/${point.id}/boxes`)).data,
    enabled: open,
  })

  const scan = useMutation({
    mutationFn: async (code: string) =>
      (await api.post<ScanResult>(`/driver/points/${point.id}/scan`, { code })).data,
    onSuccess: (result) => {
      setLast(result)
      queryClient.invalidateQueries({ queryKey: key })
    },
  })

  if (!open) return null

  const rows = boxes.data ?? []
  const scanned = rows.filter((b) => b.scanned).length
  const complete = rows.length > 0 && scanned === rows.length

  return (
    <div className="px-4 pb-4">
      <div className="groove mb-3" />

      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[13.5px] font-medium">Boxes for this stop</p>
          <p className="tnum text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            {scanned} of {rows.length} confirmed
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-2"
          style={{ color: 'var(--text-faint)' }}
          aria-label="Close"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Progress as a bar. A driver glances at this between cartons. */}
      <div
        className="mt-2.5 h-1.5 overflow-hidden rounded-full"
        style={{ background: 'var(--surface-hover)' }}
        aria-hidden
      >
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${rows.length ? (scanned / rows.length) * 100 : 0}%`,
            background: complete ? 'var(--success)' : 'var(--accent-grad)',
          }}
        />
      </div>

      {/* The verdict from the last scan. Held on screen until the next one, so
          a driver who looked away still sees what happened. */}
      {last ? <Verdict result={last} onDismiss={() => setLast(null)} /> : null}

      {boxes.isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner className="size-5" />
        </div>
      ) : rows.length === 0 ? (
        <p className="py-6 text-center text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
          No boxes were assigned to this stop in the office, so there is nothing to scan.
          Use “Mark delivered” and enter the count by hand.
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {rows.map((box) => (
            <li
              key={box.id}
              className="flex items-center gap-2.5 rounded-[10px] px-3 py-2"
              style={{
                background: box.scanned
                  ? 'color-mix(in oklab, var(--success) 10%, transparent)'
                  : 'var(--bg)',
                border: '1px solid var(--border)',
              }}
            >
              <span
                className="grid size-5 shrink-0 place-items-center rounded-full"
                style={{
                  background: box.scanned ? 'var(--success)' : 'var(--surface-hover)',
                  color: box.scanned ? '#fff' : 'var(--text-faint)',
                }}
              >
                {box.scanned ? <Check className="size-3" /> : null}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">
                  {box.item_name ?? `Box ${box.item_no}`}
                </span>
                <span className="block truncate text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
                  Bill {box.bill_no} · {box.barcode}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex gap-2">
        <Button
          size="lg"
          className="flex-1"
          icon={<ScanLine className="size-4" />}
          onClick={() => setCamera(true)}
          disabled={rows.length === 0}
        >
          {scanned ? 'Scan the next box' : 'Open the camera'}
        </Button>
        {complete ? (
          <Button
            size="lg"
            variant="secondary"
            icon={<CircleCheck className="size-4" />}
            onClick={() => onAllScanned(rows.length)}
          >
            Done
          </Button>
        ) : null}
      </div>

      {complete ? (
        <p className="mt-2.5 text-center text-[12.5px]" style={{ color: 'var(--success)' }}>
          Every box confirmed. Tap Done to record the delivery.
        </p>
      ) : null}

      <BoxScanner
        open={camera}
        onClose={() => setCamera(false)}
        onCode={(code) => scan.mutate(code)}
        title={`Stop ${point.sequence} · ${point.consignee_name}`}
        subtitle={`${scanned} of ${rows.length} confirmed`}
      />
    </div>
  )
}

/** The verdict after one scan.
 *
 *  Colour and an icon carry it, but the words carry the instruction — a wrong
 *  carton says "do not hand it over" rather than relying on red meaning that. */
function Verdict({ result, onDismiss }: { result: ScanResult; onDismiss: () => void }) {
  const tone =
    result.result === 'OK'
      ? { bg: 'var(--success)', icon: <Check className="size-4" /> }
      : result.result === 'ALREADY'
        ? { bg: 'var(--text-faint)', icon: <Check className="size-4" /> }
        : { bg: 'var(--danger)', icon: <AlertTriangle className="size-4" /> }

  return (
    <div
      className="tx-in-scale mt-3 flex items-start gap-2.5 rounded-[10px] px-3 py-2.5"
      style={{ background: `color-mix(in oklab, ${tone.bg} 14%, transparent)` }}
      role="status"
      aria-live="assertive"
    >
      <span className="mt-px shrink-0" style={{ color: tone.bg }}>
        {tone.icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium" style={{ color: tone.bg }}>
          {result.message}
        </p>
        {result.belongs_to_consignee ? (
          <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            It belongs to stop {result.belongs_to_point} — {result.belongs_to_consignee}. Put it
            back on the vehicle.
          </p>
        ) : null}
        {result.item_name ? (
          <p className="mt-0.5 truncate text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
            {result.item_name}
            {result.bill_no ? ` · Bill ${result.bill_no}` : ''}
          </p>
        ) : null}
      </div>
      <button onClick={onDismiss} aria-label="Dismiss" style={{ color: 'var(--text-faint)' }}>
        <X className="size-3.5" />
      </button>
    </div>
  )
}
