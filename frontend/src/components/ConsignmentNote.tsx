import { QrCode } from '@/components/QrCode'
import { BRAND, CONTACT } from '@/lib/brand'

/* The customer's copy of the consignment note.
 *
 * The LR is the document that travels with the goods, and until now the
 * customer had no way to get their part of it — they had a tracking page that
 * disappeared after three days and nothing to keep. A dealer being asked by
 * their own accounts department what arrived, when, and on whose lorry had
 * nothing to show them.
 *
 * Printed white-on-black regardless of the app's theme, because this goes on
 * paper or into a PDF, and a dark document wastes a cartridge and photocopies
 * badly. It is laid out for A4 but reads on a phone, since that is where the
 * tracking link is opened.
 *
 * Deliberately only THEIR delivery. The run's other stops, what anyone else is
 * paying and the rest of the vehicle's load are none of a consignee's
 * business, and an LR copy that leaked them would be worse than none.
 */

export interface NoteData {
  lr_no: string | null
  trip_no: string | null
  trip_date: string | null
  vendor_name: string | null
  from_warehouse: string | null
  from_address: string | null
  vehicle_no: string | null
  driver_name: string | null
  consignee_name: string
  consignee_phone: string | null
  address: string | null
  box_count: number
  boxes: { bill_no: string; item_no: number; of_total: number; item_name: string | null }[]
  status: string
  delivered_at: string | null
  receiver_name: string | null
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">{label}</p>
      <p className="mt-0.5 text-[11.5px] leading-snug font-medium text-black">{value || '—'}</p>
    </div>
  )
}

export function ConsignmentNote({ note, trackUrl }: { note: NoteData; trackUrl: string }) {
  const delivered = note.status === 'DELIVERED' || note.status === 'PART_DELIVERED'

  // One row per bill rather than per carton: a bill of forty boxes would
  // otherwise be forty identical lines, and the count is what anybody checks.
  const bills = new Map<string, { count: number; item: string | null }>()
  for (const box of note.boxes) {
    const row = bills.get(box.bill_no) ?? { count: 0, item: box.item_name }
    row.count += 1
    bills.set(box.bill_no, row)
  }

  return (
    <div
      className="tx-note mx-auto w-full max-w-[720px] bg-white text-black"
      style={{ border: '1px solid #d4d4d4' }}
    >
      <div className="flex items-start justify-between gap-4 bg-black px-5 py-4 text-white">
        <div>
          <p className="text-[17px] font-bold italic tracking-[0.06em]">{BRAND.name}</p>
          <p className="mt-0.5 text-[8px] tracking-[0.2em] text-neutral-400 uppercase">
            {BRAND.tagline}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[9px] tracking-[0.14em] text-neutral-400 uppercase">
            Consignment note
          </p>
          <p className="text-[19px] leading-tight font-bold">{note.lr_no ?? '—'}</p>
        </div>
      </div>

      <div className="border-b border-neutral-300 px-5 py-2 text-[9.5px] text-neutral-600">
        {CONTACT.address} · {CONTACT.phone} · {CONTACT.email}
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3.5 px-5 py-4 sm:grid-cols-4">
        <Field label="LR number" value={note.lr_no} />
        <Field label="Trip" value={note.trip_no} />
        <Field label="Date" value={note.trip_date} />
        <Field label="Vehicle" value={note.vehicle_no} />
      </div>

      <div className="grid gap-0 border-y border-neutral-300 sm:grid-cols-2">
        <div className="border-b border-neutral-300 px-5 py-3.5 sm:border-r sm:border-b-0">
          <p className="text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
            Consignor — from
          </p>
          <p className="mt-1 text-[12.5px] font-semibold">{note.vendor_name ?? '—'}</p>
          {note.from_warehouse ? (
            <p className="text-[11px] text-neutral-700">{note.from_warehouse}</p>
          ) : null}
          {note.from_address ? (
            <p className="mt-0.5 text-[10.5px] leading-snug text-neutral-600">
              {note.from_address}
            </p>
          ) : null}
        </div>
        <div className="px-5 py-3.5">
          <p className="text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
            Consignee — to
          </p>
          <p className="mt-1 text-[12.5px] font-semibold">{note.consignee_name}</p>
          {note.address ? (
            <p className="mt-0.5 text-[10.5px] leading-snug text-neutral-600">{note.address}</p>
          ) : null}
          {note.consignee_phone ? (
            <p className="mt-0.5 text-[10.5px] text-neutral-600">{note.consignee_phone}</p>
          ) : null}
        </div>
      </div>

      <div className="px-5 py-4">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-neutral-400 text-left">
              <th className="pb-1.5 text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
                Bill no
              </th>
              <th className="pb-1.5 text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
                Description
              </th>
              <th className="pb-1.5 text-right text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
                Boxes
              </th>
            </tr>
          </thead>
          <tbody>
            {[...bills.entries()].map(([billNo, row]) => (
              <tr key={billNo} className="border-b border-neutral-200">
                <td className="py-1.5 font-medium">{billNo}</td>
                <td className="py-1.5 text-neutral-700">{row.item ?? 'Said to contain'}</td>
                <td className="tnum py-1.5 text-right font-medium">{row.count}</td>
              </tr>
            ))}
            {!bills.size ? (
              <tr>
                <td colSpan={3} className="py-2 text-neutral-500">
                  {note.box_count} boxes
                </td>
              </tr>
            ) : null}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} className="pt-2 text-right text-[11px] font-semibold">
                Total boxes
              </td>
              <td className="tnum pt-2 text-right text-[13px] font-bold">
                {note.boxes.length || note.box_count}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-start justify-between gap-5 border-t border-neutral-300 px-5 py-4">
        <div className="min-w-0 flex-1">
          {delivered ? (
            <>
              <p className="text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
                Delivered
              </p>
              <p className="mt-0.5 text-[11.5px] font-medium">
                {note.delivered_at ? new Date(note.delivered_at).toLocaleString('en-IN') : '—'}
              </p>
              {note.receiver_name ? (
                <p className="text-[11px] text-neutral-700">Received by {note.receiver_name}</p>
              ) : null}
            </>
          ) : (
            <>
              <p className="text-[8.5px] tracking-[0.12em] text-neutral-500 uppercase">
                Driver
              </p>
              <p className="mt-0.5 text-[11.5px] font-medium">{note.driver_name ?? '—'}</p>
              <p className="mt-3 text-[9.5px] leading-relaxed text-neutral-500">
                Goods said to contain as declared by the consignor. Received in apparent good
                order and condition unless noted. Subject to the carrier&rsquo;s standard terms.
              </p>
            </>
          )}
        </div>

        {/* Scans back to this delivery's own tracking page, so a paper copy
            still leads somewhere while the link is live. */}
        <div className="shrink-0 text-center">
          <QrCode value={trackUrl} size={74} />
          <p className="mt-1 text-[8px] text-neutral-500">Scan to track</p>
        </div>
      </div>
    </div>
  )
}
