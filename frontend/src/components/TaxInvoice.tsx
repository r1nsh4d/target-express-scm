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
      base: acc.base + Number(l.base_amount),
      extraKm: acc.extraKm + Number(l.extra_km_amount),
      extraPoints: acc.extraPoints + Number(l.extra_point_amount),
      toll: acc.toll + Number(l.toll),
      unloading: acc.unloading + Number(l.unloading) + Number(l.unloading_additional),
      coolie: acc.coolie + Number(l.coolie),
      detention: acc.detention + Number(l.detention),
    }),
    { km: 0, points: 0, base: 0, extraKm: 0, extraPoints: 0, toll: 0, unloading: 0, coolie: 0, detention: 0 },
  )

  /* Columns that are zero on every line are dropped. A freight invoice with an
     empty Detention column down its whole length is just harder to read — and
     on spare parts, Unloading is legitimately zero every time. */
  const show = {
    toll: totals.toll > 0,
    unloading: totals.unloading > 0,
    coolie: totals.coolie > 0,
    detention: totals.detention > 0,
  }

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

      {/* ---------------- the lines ---------------- */}
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
                <Cell>{l.vehicle_no}</Cell>
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
              <Cell>{`${invoice.lines.length} freight${invoice.lines.length === 1 ? '' : 's'}`}</Cell>
              <Cell align="right" bold>{totals.points}</Cell>
              <Cell align="right" bold>{totals.km}</Cell>
              <Cell align="right" bold>{money(totals.base)}</Cell>
              <Cell align="right" bold>{money(totals.extraKm)}</Cell>
              <Cell align="right" bold>{money(totals.extraPoints)}</Cell>
              {show.toll ? <Cell align="right" bold>{money(totals.toll)}</Cell> : null}
              {show.unloading ? <Cell align="right" bold>{money(totals.unloading)}</Cell> : null}
              {show.coolie ? <Cell align="right" bold>{money(totals.coolie)}</Cell> : null}
              {show.detention ? <Cell align="right" bold>{money(totals.detention)}</Cell> : null}
              <Cell align="right" bold>{money(invoice.taxable_value)}</Cell>
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
