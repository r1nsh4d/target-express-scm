/* A tax invoice, laid out as the document a vendor actually receives.
 *
 * Not a screen with the numbers on it. This is what comes out of the printer
 * and goes to Godrej's accounts team, so it is built to the shape of the paper
 * invoice Target Express already issues:
 *
 *   supplier block | invoice number, date, period
 *   billed to      | GSTIN, state and its code
 *   the lines      | one freight per row, with its own working
 *   tax summary    | taxable value, CGST+SGST or IGST, total
 *   total in words | which the accounts team reads to check the figure
 *   bank details   | so they can pay without asking
 *
 * Two things are deliberate:
 *
 * CGST+SGST OR IGST, NEVER BOTH. Same-state supply is split into central and
 * state halves; different-state is one integrated amount. Printing all three
 * rows with zeros in two of them is how a vendor's team ends up claiming the
 * wrong credit. Which applies is decided by the state codes, not by a setting
 * somebody has to remember.
 *
 * MISSING DETAILS ARE PRINTED AS MISSING. An invoice without the supplier's
 * GSTIN cannot be claimed against and comes straight back, so a gap is called
 * out in red on the document rather than left as a blank line. A gap you can
 * see is recoverable.
 */

import type { ReactNode } from 'react'

export interface Company {
  name: string
  address: string
  gstin: string
  pan: string
  phone: string
  email: string
  state: string
  state_code: string
  bank_name: string
  bank_account: string
  bank_ifsc: string
  sac_code: string
  missing: string[]
}

export interface InvoiceLine {
  sl_no: number
  trip_date: string
  trip_no: string
  lr_no: string | null
  vehicle_no: string
  /* "Dost", "Ace". The freight charge is billed per type, because that is
     how the rate is agreed and how the vendor checks it. */
  vehicle_type?: string | null
  destination_text: string
  point_count: number
  km: number
  base_amount: string
  extra_km: number
  extra_km_rate: string
  extra_km_amount: string
  extra_points: number
  extra_point_rate: string
  extra_point_amount: string
  toll: string
  unloading: string
  unloading_additional: string
  detention: string
  coolie: string
  line_total: string
}

export interface Invoice {
  invoice_no: string
  invoice_date: string
  period_from: string
  period_to: string
  vendor_division_name: string | null
  vendor_name: string | null
  vendor_gstin: string | null
  vendor_billing_address: string | null
  place_of_supply_state_code: string | null
  taxable_value: string
  /* Toll, recharged at cost. Nil-rated, as their own summary has it. */
  zero_rated_value?: string
  /* The rate this invoice was raised at, not whatever the division says now. */
  gst_rate_percent?: string
  cgst: string
  sgst: string
  igst: string
  total: string
  total_in_words: string
  status: string
  lines: InvoiceLine[]
}

const money = (v: string | number | null | undefined) => {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const shortDate = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

/** A detail that has to be on the invoice and is not configured yet. */
function Missing({ what }: { what: string }) {
  return (
    <span className="text-[10.5px] font-medium" style={{ color: 'var(--danger)' }}>
      [{what} not set]
    </span>
  )
}

function Cell({
  children,
  align = 'left',
  bold,
  head,
}: {
  children: ReactNode
  align?: 'left' | 'right' | 'center'
  bold?: boolean
  head?: boolean
}) {
  return (
    <td
      className="border px-2 py-1.5 align-top"
      style={{
        borderColor: 'var(--border-strong)',
        textAlign: align,
        fontWeight: bold || head ? 600 : 400,
        fontSize: head ? '10px' : '11px',
        letterSpacing: head ? '0.04em' : undefined,
        textTransform: head ? 'uppercase' : undefined,
        color: head ? 'var(--text-muted)' : 'var(--text)',
      }}
    >
      {children}
    </td>
  )
}

export function TaxInvoice({ invoice, company }: { invoice: Invoice; company: Company }) {
  /* Same state means the tax splits into CGST and SGST; a different state means
     one IGST amount. Decided from the codes rather than from which figures
     happen to be non-zero, so an invoice with no tax on it still prints the
     right heading. */
  const sameState =
    !invoice.place_of_supply_state_code ||
    invoice.place_of_supply_state_code === company.state_code

  const totals = invoice.lines.reduce(
    (acc, l) => ({
      km: acc.km + l.km,
      points: acc.points + l.point_count,
      extraKm: acc.extraKm + l.extra_km,
      extraPoints: acc.extraPoints + l.extra_points,
      extraKmAmount: acc.extraKmAmount + Number(l.extra_km_amount),
      extraPointAmount: acc.extraPointAmount + Number(l.extra_point_amount),
      toll: acc.toll + Number(l.toll),
      unloading: acc.unloading + Number(l.unloading) + Number(l.unloading_additional),
      coolie: acc.coolie + Number(l.coolie),
      detention: acc.detention + Number(l.detention),
    }),
    {
      km: 0,
      points: 0,
      extraKm: 0,
      extraPoints: 0,
      extraKmAmount: 0,
      extraPointAmount: 0,
      toll: 0,
      unloading: 0,
      coolie: 0,
      detention: 0,
    },
  )

  /* The freight charge, split by vehicle type.
     A Dost and an Ace are separately agreed and separately checked, so they
     are separate lines on the document their accounts team already reads. */
  const byType = new Map<string, { amount: number; trips: number }>()
  for (const l of invoice.lines) {
    const key = l.vehicle_type || 'Vehicle'
    const row = byType.get(key) ?? { amount: 0, trips: 0 }
    row.amount += Number(l.base_amount)
    row.trips += 1
    byType.set(key, row)
  }

  /* A rate is printed only where every line agrees on it. Two different
     per-kilometre rates in one month averaged into one figure would be a
     number nobody can check against their own rate card. */
  const oneRate = (pick: (l: InvoiceLine) => string, had: (l: InvoiceLine) => boolean) => {
    const used = [...new Set(invoice.lines.filter(had).map(pick).map(Number))]
    return used.length === 1 ? used[0] : null
  }

  const heads: {
    label: string
    amount: number
    quantity?: string
    rate?: number | null
    per?: string
  }[] = []

  for (const [type, row] of byType) {
    if (!row.amount) continue
    heads.push({
      label: `Freight Charges ${type}`,
      amount: row.amount,
      quantity: `${row.trips}`,
      rate: row.trips ? row.amount / row.trips : null,
      per: 'Trip',
    })
  }
  if (totals.extraKmAmount) {
    heads.push({
      label: 'Extra KM Charges',
      amount: totals.extraKmAmount,
      quantity: `${totals.extraKm}`,
      rate: oneRate((l) => l.extra_km_rate, (l) => l.extra_km > 0),
      per: 'KM',
    })
  }
  if (totals.extraPointAmount) {
    heads.push({
      label: 'Point Charges',
      amount: totals.extraPointAmount,
      quantity: `${totals.extraPoints}`,
      rate: oneRate((l) => l.extra_point_rate, (l) => l.extra_points > 0),
      per: 'Point',
    })
  }
  if (totals.unloading) heads.push({ label: 'Unloading Charges', amount: totals.unloading })
  if (totals.coolie) heads.push({ label: 'Coolie Charges', amount: totals.coolie })
  if (totals.detention) heads.push({ label: 'Detention Charges', amount: totals.detention })
  /* Last, and nil-rated. Cash handed to a booth and recharged at cost. */
  if (totals.toll) heads.push({ label: 'Toll Charges', amount: totals.toll })

  const gross = Number(invoice.taxable_value) + Number(invoice.zero_rated_value ?? 0)
  const taxTotal = sameState
    ? Number(invoice.cgst) + Number(invoice.sgst)
    : Number(invoice.igst)
  /* CGST and SGST are each half of the agreed rate. Printed from the rate the
     invoice was RAISED at, so a reprint next year does not quietly restate
     the tax at whatever the division charges by then. */
  const fullRate = Number(invoice.gst_rate_percent ?? 0)
  const halfRate = sameState ? (fullRate / 2).toFixed(2).replace(/\.00$/, '') : fullRate

  return (
    <div
      className="tax-invoice"
      style={{ background: 'var(--surface-solid)', border: '1px solid var(--border-strong)' }}
    >
      {/* ---------------- heading ---------------- */}
      <div
        className="px-5 py-3 text-center"
        style={{ borderBottom: '1px solid var(--border-strong)' }}
      >
        <p className="text-[13px] font-bold tracking-[0.3em] uppercase">Tax Invoice</p>
      </div>

      {/* ---------------- supplier / invoice meta ---------------- */}
      <div className="grid sm:grid-cols-2" style={{ borderBottom: '1px solid var(--border-strong)' }}>
        <div className="px-5 py-3.5" style={{ borderRight: '1px solid var(--border-strong)' }}>
          <p className="text-[14px] font-bold">
            {company.name || <Missing what="Company name" />}
          </p>
          <p className="mt-1 text-[11px] leading-[1.5] whitespace-pre-line" style={{ color: 'var(--text-muted)' }}>
            {company.address || <Missing what="Address" />}
          </p>
          <dl className="mt-2 space-y-0.5 text-[11px]">
            <div className="flex gap-2">
              <dt className="w-16 shrink-0" style={{ color: 'var(--text-faint)' }}>GSTIN</dt>
              <dd className="font-medium">{company.gstin || <Missing what="GSTIN" />}</dd>
            </div>
            {company.pan ? (
              <div className="flex gap-2">
                <dt className="w-16 shrink-0" style={{ color: 'var(--text-faint)' }}>PAN</dt>
                <dd>{company.pan}</dd>
              </div>
            ) : null}
            <div className="flex gap-2">
              <dt className="w-16 shrink-0" style={{ color: 'var(--text-faint)' }}>State</dt>
              <dd>
                {company.state} ({company.state_code})
              </dd>
            </div>
            {company.phone || company.email ? (
              <div className="flex gap-2">
                <dt className="w-16 shrink-0" style={{ color: 'var(--text-faint)' }}>Contact</dt>
                <dd>{[company.phone, company.email].filter(Boolean).join(' · ')}</dd>
              </div>
            ) : null}
          </dl>
        </div>

        <div className="px-5 py-3.5">
          <dl className="space-y-1 text-[11.5px]">
            {[
              ['Invoice no', invoice.invoice_no],
              ['Invoice date', shortDate(invoice.invoice_date)],
              ['Period', `${shortDate(invoice.period_from)} — ${shortDate(invoice.period_to)}`],
              ['SAC', company.sac_code],
              ['Reverse charge', 'No'],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-3">
                <dt className="w-28 shrink-0" style={{ color: 'var(--text-faint)' }}>
                  {label}
                </dt>
                <dd className="font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {/* ---------------- billed to ---------------- */}
      <div className="px-5 py-3.5" style={{ borderBottom: '1px solid var(--border-strong)' }}>
        <p className="eyebrow mb-1.5">Billed to</p>
        <p className="text-[13px] font-semibold">
          {invoice.vendor_name ?? invoice.vendor_division_name ?? '—'}
          {invoice.vendor_division_name && invoice.vendor_name ? (
            <span className="font-normal" style={{ color: 'var(--text-muted)' }}>
              {' '}· {invoice.vendor_division_name}
            </span>
          ) : null}
        </p>
        {invoice.vendor_billing_address ? (
          <p className="mt-1 text-[11px] leading-[1.5] whitespace-pre-line" style={{ color: 'var(--text-muted)' }}>
            {invoice.vendor_billing_address}
          </p>
        ) : null}
        <p className="mt-1.5 flex flex-wrap gap-x-6 gap-y-1 text-[11px]">
          <span>
            <span style={{ color: 'var(--text-faint)' }}>GSTIN </span>
            {invoice.vendor_gstin || <Missing what="Vendor GSTIN" />}
          </span>
          <span>
            <span style={{ color: 'var(--text-faint)' }}>Place of supply </span>
            {invoice.place_of_supply_state_code
              ? `${invoice.place_of_supply_state_code}`
              : `${company.state} (${company.state_code})`}
          </span>
        </p>
      </div>

      {/* ---------------- the charges, by head ----------------

          Grouped, not one row per trip.

          Target Express's own accountant issues these from Tally, and the
          document that reaches Godrej bills the month by charge head —
          "Freight Charges Dost", "Extra KM Charges", "Toll Charges" — with
          the trips behind it as a separate sheet. An accounts team checks a
          bill head by head against what they agreed; a forty-row table of
          trips makes them do the adding up themselves.

          The freight charge splits by VEHICLE TYPE because that is how the
          rate is agreed. A Dost and an Ace are separate lines on their
          document and separate conversations when one looks wrong. */}
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Cell head align="center">Sl</Cell>
            <Cell head>Particulars</Cell>
            <Cell head align="center">HSN/SAC</Cell>
            <Cell head align="right">Quantity</Cell>
            <Cell head align="right">Rate</Cell>
            <Cell head align="center">per</Cell>
            <Cell head align="right">Amount</Cell>
          </tr>
        </thead>
        <tbody className="tnum">
          {heads.map((h, i) => (
            <tr key={h.label}>
              <Cell align="center">{i + 1}</Cell>
              <Cell>{h.label}</Cell>
              <Cell align="center">{company.sac_code}</Cell>
              <Cell align="right">{h.quantity ?? ''}</Cell>
              <Cell align="right">{h.rate ? money(h.rate) : ''}</Cell>
              <Cell align="center">{h.per ?? ''}</Cell>
              <Cell align="right">{money(h.amount)}</Cell>
            </tr>
          ))}

          <tr style={{ background: 'var(--surface-hover)' }}>
            <Cell align="center">{''}</Cell>
            <Cell bold>Total</Cell>
            <Cell align="center">{''}</Cell>
            <Cell align="right">
              {invoice.lines.length} freight{invoice.lines.length === 1 ? '' : 's'}
            </Cell>
            <Cell align="right">{''}</Cell>
            <Cell align="center">{''}</Cell>
            <Cell align="right" bold>{money(gross)}</Cell>
          </tr>
        </tbody>
      </table>

      {/* The tax summary their accounts team reconciles against: the taxed
          bucket and the nil-rated one side by side, because toll is cash
          handed to a booth and passed on rather than a service supplied. */}
      <div style={{ borderTop: '1px solid var(--border-strong)' }}>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <Cell head>HSN/SAC</Cell>
              <Cell head align="right">Taxable value</Cell>
              <Cell head align="center">{sameState ? 'CGST rate' : 'IGST rate'}</Cell>
              <Cell head align="right">{sameState ? 'CGST' : 'IGST'}</Cell>
              {sameState ? <Cell head align="center">SGST rate</Cell> : null}
              {sameState ? <Cell head align="right">SGST</Cell> : null}
              <Cell head align="right">Total tax</Cell>
            </tr>
          </thead>
          <tbody className="tnum">
            <tr>
              <Cell>{company.sac_code}</Cell>
              <Cell align="right">{money(invoice.taxable_value)}</Cell>
              <Cell align="center">{halfRate}%</Cell>
              <Cell align="right">{money(sameState ? invoice.cgst : invoice.igst)}</Cell>
              {sameState ? <Cell align="center">{halfRate}%</Cell> : null}
              {sameState ? <Cell align="right">{money(invoice.sgst)}</Cell> : null}
              <Cell align="right">{money(taxTotal)}</Cell>
            </tr>

            {Number(invoice.zero_rated_value ?? 0) > 0 ? (
              <tr>
                <Cell>{company.sac_code}</Cell>
                <Cell align="right">{money(invoice.zero_rated_value)}</Cell>
                <Cell align="center">0%</Cell>
                <Cell align="right">—</Cell>
                {sameState ? <Cell align="center">0%</Cell> : null}
                {sameState ? <Cell align="right">—</Cell> : null}
                <Cell align="right">—</Cell>
              </tr>
            ) : null}

            <tr style={{ background: 'var(--surface-hover)' }}>
              <Cell bold>Total</Cell>
              <Cell align="right" bold>{money(gross)}</Cell>
              <Cell align="center">{''}</Cell>
              <Cell align="right" bold>{money(sameState ? invoice.cgst : invoice.igst)}</Cell>
              {sameState ? <Cell align="center">{''}</Cell> : null}
              {sameState ? <Cell align="right" bold>{money(invoice.sgst)}</Cell> : null}
              <Cell align="right" bold>{money(taxTotal)}</Cell>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ---------------- tax and totals ---------------- */}
      <div className="grid sm:grid-cols-[1.4fr_1fr]" style={{ borderTop: '1px solid var(--border-strong)' }}>
        <div className="px-5 py-3.5" style={{ borderRight: '1px solid var(--border-strong)' }}>
          <p className="eyebrow">Total in words</p>
          <p className="mt-1 text-[12px] font-medium">{invoice.total_in_words || '—'}</p>

          {company.bank_account ? (
            <>
              <p className="eyebrow mt-4">Payment</p>
              <dl className="mt-1 space-y-0.5 text-[11px]">
                {[
                  ['Bank', company.bank_name],
                  ['Account', company.bank_account],
                  ['IFSC', company.bank_ifsc],
                ]
                  .filter(([, v]) => v)
                  .map(([label, value]) => (
                    <div key={label} className="flex gap-2">
                      <dt className="w-16 shrink-0" style={{ color: 'var(--text-faint)' }}>
                        {label}
                      </dt>
                      <dd className="font-medium">{value}</dd>
                    </div>
                  ))}
              </dl>
            </>
          ) : null}
        </div>

        <div className="px-5 py-3.5">
          <dl className="tnum space-y-1 text-[12px]">
            <div className="flex justify-between gap-4">
              <dt style={{ color: 'var(--text-muted)' }}>Taxable value</dt>
              <dd className="font-medium">₹{money(invoice.taxable_value)}</dd>
            </div>

            {/* One or the other. Never both. */}
            {sameState ? (
              <>
                <div className="flex justify-between gap-4">
                  <dt style={{ color: 'var(--text-muted)' }}>CGST</dt>
                  <dd>₹{money(invoice.cgst)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt style={{ color: 'var(--text-muted)' }}>SGST</dt>
                  <dd>₹{money(invoice.sgst)}</dd>
                </div>
              </>
            ) : (
              <div className="flex justify-between gap-4">
                <dt style={{ color: 'var(--text-muted)' }}>IGST</dt>
                <dd>₹{money(invoice.igst)}</dd>
              </div>
            )}

            <div className="groove my-1.5" />
            <div className="flex justify-between gap-4 text-[15px]">
              <dt className="font-semibold">Total</dt>
              <dd className="font-bold">₹{money(invoice.total)}</dd>
            </div>
          </dl>

          <div className="mt-10 text-right">
            <p className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
              For {company.name || 'Target Express'}
            </p>
            <p className="mt-8 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Authorised signatory
            </p>
          </div>
        </div>
      </div>

      {company.missing.length ? (
        <div
          className="px-5 py-2.5 text-[11.5px] print:hidden"
          style={{
            borderTop: '1px solid var(--border-strong)',
            background: 'color-mix(in oklab, var(--danger) 10%, transparent)',
            color: 'var(--danger)',
          }}
        >
          Not configured: {company.missing.join(', ')}. A tax invoice without these cannot be
          claimed against — set them in <code>.env.prod</code> as COMPANY_NAME, COMPANY_ADDRESS
          and COMPANY_GSTIN, then restart the API.
        </div>
      ) : null}
    </div>
  )
}

/* The trips behind the bill.
 *
 * The invoice itself bills the month by charge head, which is how an accounts
 * team checks it: head by head against what was agreed. But "Extra KM
 * Charges ₹1,02,889" is only checkable if somebody can also see which trips
 * made it up, and that is a different document — a sheet behind the bill, not
 * forty rows in front of it.
 *
 * Every figure here carries its own working, because this page exists to
 * answer "where did that come from" without a phone call.
 */
export function FreightAnnexure({ invoice }: { invoice: Invoice }) {
  const totals = invoice.lines.reduce(
    (acc, l) => ({
      km: acc.km + l.km,
      points: acc.points + l.point_count,
      total: acc.total + Number(l.line_total),
    }),
    { km: 0, points: 0, total: 0 },
  )

  const show = {
    toll: invoice.lines.some((l) => Number(l.toll) > 0),
    unloading: invoice.lines.some(
      (l) => Number(l.unloading) + Number(l.unloading_additional) > 0,
    ),
    coolie: invoice.lines.some((l) => Number(l.coolie) > 0),
    detention: invoice.lines.some((l) => Number(l.detention) > 0),
  }

  return (
    <div
      className="tax-invoice"
      style={{ background: 'var(--surface-solid)', border: '1px solid var(--border-strong)' }}
    >
      <div
        className="px-5 py-3"
        style={{ borderBottom: '1px solid var(--border-strong)' }}
      >
        <p className="text-[12px] font-bold tracking-[0.25em] uppercase">
          Annexure — the freights on this invoice
        </p>
        <p className="mt-0.5 text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
          {invoice.invoice_no} · {invoice.lines.length}{' '}
          {invoice.lines.length === 1 ? 'freight' : 'freights'}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse" style={{ minWidth: 760 }}>
          <thead>
            <tr>
              <Cell head align="center">#</Cell>
              <Cell head>Date</Cell>
              <Cell head>Trip / LR</Cell>
              <Cell head>Vehicle</Cell>
              <Cell head>Destination</Cell>
              <Cell head align="right">Pts</Cell>
              <Cell head align="right">KM</Cell>
              <Cell head align="right">Base</Cell>
              <Cell head align="right">Extra KM</Cell>
              <Cell head align="right">Points</Cell>
              {show.toll ? <Cell head align="right">Toll</Cell> : null}
              {show.unloading ? <Cell head align="right">Unloading</Cell> : null}
              {show.coolie ? <Cell head align="right">Coolie</Cell> : null}
              {show.detention ? <Cell head align="right">Detention</Cell> : null}
              <Cell head align="right">Amount</Cell>
            </tr>
          </thead>
          <tbody className="tnum">
            {invoice.lines.map((l) => (
              <tr key={l.sl_no}>
                <Cell align="center">{l.sl_no}</Cell>
                <Cell>{shortDate(l.trip_date)}</Cell>
                <Cell>
                  {l.trip_no}
                  {l.lr_no ? (
                    <span className="block text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      LR {l.lr_no}
                    </span>
                  ) : null}
                </Cell>
                <Cell>
                  {l.vehicle_no}
                  {l.vehicle_type ? (
                    <span className="block text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      {l.vehicle_type}
                    </span>
                  ) : null}
                </Cell>
                <Cell>{l.destination_text}</Cell>
                <Cell align="right">{l.point_count}</Cell>
                <Cell align="right">{l.km}</Cell>
                <Cell align="right">{money(l.base_amount)}</Cell>
                <Cell align="right">
                  {money(l.extra_km_amount)}
                  {l.extra_km > 0 ? (
                    <span className="block text-[9.5px]" style={{ color: 'var(--text-faint)' }}>
                      {l.extra_km} × {money(l.extra_km_rate)}
                    </span>
                  ) : null}
                </Cell>
                <Cell align="right">
                  {money(l.extra_point_amount)}
                  {l.extra_points > 0 ? (
                    <span className="block text-[9.5px]" style={{ color: 'var(--text-faint)' }}>
                      {l.extra_points} × {money(l.extra_point_rate)}
                    </span>
                  ) : null}
                </Cell>
                {show.toll ? <Cell align="right">{money(l.toll)}</Cell> : null}
                {show.unloading ? (
                  <Cell align="right">
                    {money(Number(l.unloading) + Number(l.unloading_additional))}
                  </Cell>
                ) : null}
                {show.coolie ? <Cell align="right">{money(l.coolie)}</Cell> : null}
                {show.detention ? <Cell align="right">{money(l.detention)}</Cell> : null}
                <Cell align="right" bold>{money(l.line_total)}</Cell>
              </tr>
            ))}

            <tr style={{ background: 'var(--surface-hover)' }}>
              <Cell align="center" bold>—</Cell>
              <Cell bold>Total</Cell>
              <Cell>{''}</Cell>
              <Cell>{''}</Cell>
              <Cell>{''}</Cell>
              <Cell align="right" bold>{totals.points}</Cell>
              <Cell align="right" bold>{totals.km}</Cell>
              <Cell>{''}</Cell>
              <Cell>{''}</Cell>
              <Cell>{''}</Cell>
              {show.toll ? <Cell>{''}</Cell> : null}
              {show.unloading ? <Cell>{''}</Cell> : null}
              {show.coolie ? <Cell>{''}</Cell> : null}
              {show.detention ? <Cell>{''}</Cell> : null}
              <Cell align="right" bold>{money(totals.total)}</Cell>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
