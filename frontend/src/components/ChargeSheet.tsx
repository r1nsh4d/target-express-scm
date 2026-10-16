/* The unloading charge sheet, as the document the dealer signs.
 *
 * Target Express already issues this on paper — a small form filled in at the
 * door with the customer, the bill number, how many items, which floor, what
 * was carried, the amount and a signature. The vendor's accounts team checks
 * the unloading line of an invoice against it, and without it that line is a
 * number with nothing behind it.
 *
 * So this is printed, not displayed: the same fields in the same order as the
 * paper form they already recognise, one per page behind the tax invoice.
 *
 * Three things are deliberate.
 *
 * THE TOTAL IS WHAT THE VENDOR WAS CHARGED, not a fresh sum of the lines. If
 * the office corrected the figure after the driver saved his sheet the two
 * differ, and that is shown on screen rather than silently printing a third
 * number — but what prints is always the invoice's figure, because a sheet
 * that disagrees with the bill it backs is worse than no sheet.
 *
 * COOLIE IS BELOW THE TOTAL, NEVER INSIDE IT. A porter gang at a market gate
 * is a cash demand the driver settled and the vendor reimburses; folding it in
 * makes "why has unloading gone up?" unanswerable.
 *
 * THE SIGNATURE LINE IS ALWAYS THERE. Even where the receiver's name was
 * captured on the phone, the printed copy carries a line for the dealer to
 * sign, because that is what makes it the document they already accept.
 */

export interface ChargeSheetLine {
  item_code: string
  item_name: string
  quantity: number
  base_rate: string
  floors_charged: number
  per_floor_rate: string
  unit_charge: string
  amount: string
}

export interface ChargeSheetData {
  point_id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  vehicle_no: string
  customer_name: string
  location: string | null
  vendor_bill_nos: string[]
  bill_date: string | null
  floor_number: number
  has_lift: boolean
  lines: ChargeSheetLine[]
  item_count: number
  billed_total: string
  rebuilt_total: string
  agrees_with_invoice: boolean
  unpriced_item_codes: string[]
  coolie_billed: string
  coolie_note: string | null
  receiver_name: string | null
  delivered_on: string | null
}

const money = (v: string | number | null | undefined) => {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const shortDate = (iso: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

function Entry({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-28 shrink-0 text-[10.5px]" style={{ color: 'var(--text-faint)' }}>
        {label}
      </span>
      <span
        className="min-w-0 flex-1 border-b pb-0.5 text-[11.5px] font-medium"
        style={{ borderColor: 'var(--border)' }}
      >
        {value}
      </span>
    </div>
  )
}

export function ChargeSheet({
  sheet,
  companyName,
}: {
  sheet: ChargeSheetData
  companyName: string
}) {
  const floor =
    sheet.floor_number === 0
      ? 'Ground floor'
      : `Floor ${sheet.floor_number}${sheet.has_lift ? ' (lift available)' : ' (carried up)'}`

  return (
    <div
      className="tx-charge-sheet"
      style={{ background: 'var(--surface-solid)', border: '1px solid var(--border-strong)' }}
    >
      <div
        className="px-5 py-2.5 text-center"
        style={{ borderBottom: '1px solid var(--border-strong)' }}
      >
        <p className="text-[12px] font-bold tracking-[0.25em] uppercase">
          Unloading charge sheet
        </p>
        <p className="mt-0.5 text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
          Placement charges, per delivery point
        </p>
      </div>

      {/* The form's head: ours on the left, theirs on the right. */}
      <div
        className="grid gap-x-8 gap-y-2 px-5 py-3.5 sm:grid-cols-2"
        style={{ borderBottom: '1px solid var(--border-strong)' }}
      >
        <Entry label="Transporter" value={companyName || 'Target Express'} />
        <Entry label="Customer" value={sheet.customer_name} />
        <Entry
          label="Trip / LR"
          value={
            <span className="tnum">
              {sheet.trip_no}
              {sheet.lr_no ? ` · LR ${sheet.lr_no}` : ''}
            </span>
          }
        />
        <Entry label="Location" value={sheet.location ?? '—'} />
        <Entry label="Vehicle" value={<span className="tnum">{sheet.vehicle_no}</span>} />
        <Entry
          label="Bill no"
          value={
            <span className="tnum">
              {sheet.vendor_bill_nos.length ? sheet.vendor_bill_nos.join(', ') : '—'}
            </span>
          }
        />
        <Entry label="Date" value={<span className="tnum">{shortDate(sheet.trip_date)}</span>} />
        <Entry label="Delivered" value={<span className="tnum">{shortDate(sheet.delivered_on)}</span>} />
      </div>

      {/* What was carried in, and the arithmetic behind each line. */}
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {['Article', 'Qty', 'Rate', 'Floors', 'Each', 'Amount'].map((h, i) => (
              <th
                key={h}
                className="border px-2 py-1.5 text-[9.5px] tracking-[0.05em] uppercase"
                style={{
                  borderColor: 'var(--border-strong)',
                  color: 'var(--text-muted)',
                  textAlign: i === 0 ? 'left' : 'right',
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tnum">
          {sheet.lines.map((line) => (
            <tr key={line.item_code}>
              <td
                className="border px-2 py-1.5 text-[11px]"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {line.item_name}
              </td>
              <td
                className="border px-2 py-1.5 text-right text-[11px]"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {line.quantity}
              </td>
              <td
                className="border px-2 py-1.5 text-right text-[11px]"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {money(line.base_rate)}
              </td>
              <td
                className="border px-2 py-1.5 text-right text-[11px]"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {line.floors_charged > 0
                  ? `${line.floors_charged} × ${money(line.per_floor_rate)}`
                  : '—'}
              </td>
              <td
                className="border px-2 py-1.5 text-right text-[11px]"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {money(line.unit_charge)}
              </td>
              <td
                className="border px-2 py-1.5 text-right text-[11px] font-semibold"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                {money(line.amount)}
              </td>
            </tr>
          ))}

          {!sheet.lines.length ? (
            <tr>
              <td
                colSpan={6}
                className="border px-2 py-3 text-center text-[11px]"
                style={{ borderColor: 'var(--border-strong)', color: 'var(--text-muted)' }}
              >
                No articles recorded at this point.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>

      <div className="grid sm:grid-cols-[1.3fr_1fr]">
        <div className="px-5 py-3" style={{ borderRight: '1px solid var(--border-strong)' }}>
          <Entry label="No. of items" value={<span className="tnum">{sheet.item_count}</span>} />
          <div className="mt-2">
            <Entry label="Floor details" value={floor} />
          </div>

          {sheet.coolie_note ? (
            <p className="mt-3 text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Remarks </span>
              {sheet.coolie_note}
            </p>
          ) : null}
        </div>

        <div className="px-5 py-3">
          <dl className="tnum space-y-1 text-[11.5px]">
            <div className="flex justify-between gap-4">
              <dt style={{ color: 'var(--text-muted)' }}>Unloading</dt>
              <dd className="font-semibold">₹{money(sheet.billed_total)}</dd>
            </div>

            {/* Separate, always. The vendor is reimbursing a local demand, not
                paying for unloading work. */}
            {Number(sheet.coolie_billed) > 0 ? (
              <div className="flex justify-between gap-4">
                <dt style={{ color: 'var(--text-muted)' }}>Coolie (reimbursement)</dt>
                <dd>₹{money(sheet.coolie_billed)}</dd>
              </div>
            ) : null}

            <div className="groove my-1" />
            <div className="flex justify-between gap-4 text-[13px]">
              <dt className="font-semibold">Total</dt>
              <dd className="font-bold">
                ₹{money(Number(sheet.billed_total) + Number(sheet.coolie_billed))}
              </dd>
            </div>
          </dl>

          <div className="mt-8">
            <div className="border-b" style={{ borderColor: 'var(--border-strong)' }} />
            <p className="mt-1 text-[10px]" style={{ color: 'var(--text-faint)' }}>
              Received by{sheet.receiver_name ? ` — ${sheet.receiver_name}` : ''}
            </p>
          </div>
        </div>
      </div>

      {/* Screen only. Neither of these belongs on the copy the vendor gets:
          one is our bookkeeping, the other is a gap to close before sending. */}
      {!sheet.agrees_with_invoice ? (
        <div
          className="px-5 py-2 text-[11px] print:hidden"
          style={{
            borderTop: '1px solid var(--border-strong)',
            background: 'color-mix(in oklab, var(--warning) 12%, transparent)',
          }}
        >
          The articles above price at ₹{money(sheet.rebuilt_total)}, and ₹
          {money(sheet.billed_total)} was charged. The charged figure is what prints, because it
          is what is on the invoice — but one of the two is wrong.
        </div>
      ) : null}

      {sheet.unpriced_item_codes.length ? (
        <div
          className="px-5 py-2 text-[11px] print:hidden"
          style={{
            borderTop: '1px solid var(--border-strong)',
            background: 'color-mix(in oklab, var(--danger) 10%, transparent)',
            color: 'var(--danger)',
          }}
        >
          Carried but not priced: {sheet.unpriced_item_codes.join(', ')}. These were billed as
          nothing — add them under Unloading rates for this division.
        </div>
      ) : null}
    </div>
  )
}
