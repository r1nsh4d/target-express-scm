import { QrCode } from '@/components/QrCode'

/* The sticker, in one place.
   Two screens print these — the whole freight before loading, and one bill on
   its own when a label is torn off in the lorry. The backend returns identical
   fields to both for a reason: two different stickers for the same carton is
   worse than a missing one, because the godown sorts by whichever it reads
   first and nobody knows which that was. Copying this markup into the second
   screen would reintroduce that by the back door, so it lives here. */

export interface Label {
  barcode: string
  point_sequence: number
  point_colour: string
  consignee_name: string
  city: string | null
  vendor_bill_no: string
  item_no: number
  of_total: number
  item_name: string | null
  trip_no: string
  lr_no: string | null
  floor_number: number
}

/* Ordered by what a loader actually uses: the colour band and point number
   first, the customer second, the bill and box number third, the code last. */
export function LabelCard({ label }: { label: Label }) {
  // A bill not yet on a freight has no stop number and no trip. Those are the
  // two biggest things on the sticker, so the label says they are missing
  // rather than printing a 0 that looks like a real point and sorts nowhere.
  const onAFreight = label.point_sequence > 0

  return (
    <div
      className="label-card relative overflow-hidden bg-white text-black"
      style={{ border: '1px solid #111', borderRadius: 6 }}
    >
      <div className="flex items-stretch">
        <div
          className="flex w-[74px] shrink-0 flex-col items-center justify-center py-3 text-white"
          style={{ background: label.point_colour }}
        >
          <span className="text-[9px] tracking-[0.18em] uppercase opacity-90">Point</span>
          {onAFreight ? (
            <span className="text-[40px] leading-none font-extrabold">
              {label.point_sequence}
            </span>
          ) : (
            <span className="px-1 text-center text-[10px] leading-tight font-bold">
              NOT ON A FREIGHT
            </span>
          )}
          {label.floor_number > 0 ? (
            <span className="mt-1 text-[9px] tracking-wider uppercase opacity-90">
              Floor {label.floor_number}
            </span>
          ) : null}
        </div>

        <div className="min-w-0 flex-1 px-3 py-2.5">
          <p className="truncate text-[15px] leading-tight font-bold uppercase">
            {label.consignee_name}
          </p>
          {label.city ? (
            <p className="truncate text-[11px] text-neutral-600 uppercase">{label.city}</p>
          ) : null}

          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className="text-[12px] font-semibold">Bill {label.vendor_bill_no}</span>
            <span className="text-[17px] leading-none font-extrabold">
              {label.item_no}
              <span className="text-[11px] font-medium text-neutral-500"> of {label.of_total}</span>
            </span>
          </div>

          {label.item_name ? (
            <p className="mt-1 truncate text-[11px] text-neutral-700">{label.item_name}</p>
          ) : null}

          <div className="mt-2 flex items-center justify-between border-t border-neutral-300 pt-1.5">
            <span className="font-mono text-[10px] tracking-tight">{label.barcode}</span>
            <span className="text-[9px] text-neutral-500">
              {label.trip_no || '—'}
              {label.lr_no ? ` · LR ${label.lr_no}` : ''}
            </span>
          </div>
        </div>

        {/* The scannable code, at the open edge of the sticker so a driver can
            reach it with a phone without lifting the carton. The same value is
            printed as text beside it: when a camera will not focus in a dark
            lorry, somebody still has to be able to read it out. */}
        <div className="flex shrink-0 items-center justify-center bg-white px-2 py-2">
          <QrCode value={label.barcode} size={58} />
        </div>
      </div>
    </div>
  )
}
