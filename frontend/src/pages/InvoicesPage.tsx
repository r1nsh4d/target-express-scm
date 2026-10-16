import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, Printer, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Table,
} from '@/components/ui'
import type { ChargeSheetData } from '@/components/ChargeSheet'
import { ChargeSheet } from '@/components/ChargeSheet'
import type { Company } from '@/components/TaxInvoice'
import { TaxInvoice } from '@/components/TaxInvoice'
import { api, apiErrorMessage } from '@/lib/api'
import type { VendorDivision } from '@/lib/resources'
import { STATUS_TONE, rupees, useItem, useList } from '@/lib/resources'

interface InvoiceRow {
  id: string
  invoice_no: string
  invoice_date: string
  period_from: string
  period_to: string
  vendor_division_name: string | null
  taxable_value: string
  cgst: string
  sgst: string
  igst: string
  total: string
  status: string
  line_count: number
  // Set once a payment has been recorded. `amount_received` can be less than
  // `total` — a TDS deduction at source is the normal case, not an error.
  paid_on?: string | null
  amount_received?: string | null
  payment_mode?: string | null
  payment_reference?: string | null
  // Only the detail endpoint fills these; they are what the printed tax
  // invoice needs beyond what the list shows.
  vendor_name?: string | null
  vendor_gstin?: string | null
  vendor_billing_address?: string | null
  place_of_supply_state_code?: string | null
  total_in_words?: string
}

interface InvoiceLine {
  id: string
  sl_no: number
  trip_date: string
  trip_no: string
  lr_no: string | null
  vehicle_no: string
  destination_text: string
  point_count: number
  start_km: number | null
  close_km: number | null
  km: number
  base_amount: string
  included_km: number
  extra_km: number
  extra_km_rate: string
  extra_km_amount: string
  extra_points: number
  extra_point_rate: string
  extra_point_amount: string
  toll: string
  unloading: string
  coolie: string
  detention: string
  line_total: string
}

interface Invoice extends InvoiceRow {
  lines: InvoiceLine[]
}

interface Preview {
  vendor_division_name: string
  freight_count: number
  lines: {
    // What the tick boxes send back, so the invoice can be raised for some of
    // the period's freights and not others.
    freight_id: string
    trip_no: string
    trip_date: string
    vehicle_no: string
    destination_text: string | null
    point_count: number
    km: number
    line_total: string
  }[]
  taxable_value: string
  gst_rate_percent: string
  gst_amount: string
  total: string
  problems: string[]
}

export default function InvoicesPage() {
  const [openId, setOpenId] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const invoices = useList<InvoiceRow>('/invoices')

  /* Billing a freight from the trip screen lands here with ?open=<id>, so the
     invoice it just raised is on screen rather than one row in a list. The
     parameter is consumed on arrival — a back button that reopens it would be
     confusing, and a reload should not force it open again. */
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    const wanted = params.get('open')
    if (!wanted) return
    setOpenId(wanted)
    const next = new URLSearchParams(params)
    next.delete('open')
    setParams(next, { replace: true })
  }, [params, setParams])

  if (openId) return <InvoiceDetail id={openId} onBack={() => setOpenId(null)} />

  return (
    <div className="space-y-6">
      <PageHeader
        description="Pick a vendor division and a period, and every completed freight not yet billed becomes a line — priced on the rate card in force on its own date, not today's."
        action={
          <Button icon={<Sparkles className="size-4" />} onClick={() => setGenerating(true)}>
            Generate invoice
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {invoices.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={invoices.data ?? []}
            rowKey={(i) => i.id}
            onRowClick={(i) => setOpenId(i.id)}
            empty={
              <EmptyState
                icon={<FileText className="size-7" />}
                title="No invoices yet"
                description="Completed freights wait here until they are billed."
                action={<Button onClick={() => setGenerating(true)}>Generate invoice</Button>}
              />
            }
            columns={[
              {
                key: 'no',
                header: 'Invoice',
                render: (i) => <span className="font-medium">{i.invoice_no}</span>,
              },
              { key: 'div', header: 'Division', render: (i) => i.vendor_division_name ?? '—' },
              {
                key: 'period',
                header: 'Period',
                render: (i) => (
                  <span className="tnum">
                    {i.period_from} → {i.period_to}
                  </span>
                ),
              },
              {
                key: 'lines',
                header: 'Freights',
                align: 'right',
                render: (i) => <span className="tnum">{i.line_count}</span>,
              },
              {
                key: 'total',
                header: 'Total',
                align: 'right',
                render: (i) => <span className="tnum font-medium">{rupees(i.total)}</span>,
              },
              {
                key: 'status',
                header: 'Status',
                render: (i) => (
                  <Badge tone={STATUS_TONE[i.status] ?? 'neutral'}>{i.status}</Badge>
                ),
              },
            ]}
          />
        )}
      </Card>

      <GenerateModal open={generating} onClose={() => setGenerating(false)} onDone={setOpenId} />
    </div>
  )
}

function GenerateModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: (id: string) => void
}) {
  const queryClient = useQueryClient()
  const divisions = useList<VendorDivision>('/vendor-divisions')

  const today = new Date()
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)
  const [form, setForm] = useState({
    vendor_division_id: '',
    period_from: firstOfMonth.toISOString().slice(0, 10),
    period_to: today.toISOString().slice(0, 10),
  })
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)

  /* Which freights actually go on the bill.

     The period sweep is the right default — it is how a month gets billed —
     but it is the wrong thing when one trip is disputed, is waiting on a toll
     receipt, or belongs on next month's invoice. Before this, the only way to
     leave one out was to narrow the dates until the range happened to exclude
     it, and raising a bill for a Tuesday and a Friday but not the Wednesday in
     between was simply not possible.

     Everything previewed starts ticked, so the common case is still one
     button. */
  const [chosen, setChosen] = useState<Set<string>>(new Set())

  function showPreview(p: Preview) {
    setPreview(p)
    setChosen(new Set(p.lines.map((l) => l.freight_id)))
  }

  function toggle(freightId: string) {
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(freightId)) next.delete(freightId)
      else next.add(freightId)
      return next
    })
  }

  /* Totals for what is TICKED, not for the period.

     The server re-does this arithmetic and its answer is the one that gets
     stored; this is only so the figure on screen is the figure about to be
     billed. Showing the period's total next to a part-selection would be a
     number that matches neither the lines above it nor the invoice produced. */
  const picked = (preview?.lines ?? []).filter((l) => chosen.has(l.freight_id))
  const pickedTaxable = picked.reduce((sum, l) => sum + Number(l.line_total), 0)
  const pickedGst = preview
    ? (pickedTaxable * Number(preview.gst_rate_percent)) / 100
    : 0

  const doPreview = useMutation({
    mutationFn: async () => (await api.post<Preview>('/invoices/preview', form)).data,
    onSuccess: showPreview,
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const doGenerate = useMutation({
    mutationFn: async () =>
      (await api.post<Invoice>('/invoices', { ...form, freight_ids: [...chosen] })).data,
    onSuccess: (inv) => {
      queryClient.invalidateQueries({ queryKey: ['/invoices'] })
      queryClient.invalidateQueries({ queryKey: ['/freights'] })
      setPreview(null)
      onClose()
      onDone(inv.id)
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Generate a vendor invoice"
      description="Nothing is created until you confirm. Preview first."
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Vendor division">
            <Select
              value={form.vendor_division_id}
              onChange={(e) => {
                setForm({ ...form, vendor_division_id: e.target.value })
                setPreview(null)
                setChosen(new Set())
              }}
            >
              <option value="">Select</option>
              {divisions.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="From">
            <Input
              type="date"
              value={form.period_from}
              onChange={(e) => {
                setForm({ ...form, period_from: e.target.value })
                setPreview(null)
                setChosen(new Set())
              }}
            />
          </Field>
          <Field label="To">
            <Input
              type="date"
              value={form.period_to}
              onChange={(e) => {
                setForm({ ...form, period_to: e.target.value })
                setPreview(null)
                setChosen(new Set())
              }}
            />
          </Field>
        </div>

        <Button
          variant="secondary"
          disabled={!form.vendor_division_id}
          loading={doPreview.isPending}
          onClick={() => {
            setError(null)
            doPreview.mutate()
          }}
        >
          Preview
        </Button>

        {preview ? (
          <div className="space-y-3">
            {preview.problems.length ? (
              <div
                className="rounded-[var(--radius-control)] px-3.5 py-3 text-[12.5px]"
                style={{
                  background: 'color-mix(in oklab, var(--warning) 12%, transparent)',
                  color: 'var(--text)',
                }}
              >
                <p className="font-medium">
                  {preview.problems.length} freight
                  {preview.problems.length === 1 ? '' : 's'} left out — no rate card covers the
                  date:
                </p>
                <ul className="mt-1.5 space-y-0.5">
                  {preview.problems.map((p) => (
                    <li key={p}>· {p}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                {chosen.size} of {preview.lines.length} selected. Anything left unticked stays
                unbilled and comes up on the next run.
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setChosen(new Set(preview.lines.map((l) => l.freight_id)))}
                >
                  Select all
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setChosen(new Set())}
                >
                  Clear
                </Button>
              </div>
            </div>

            <Card className="overflow-hidden">
              <Table
                rows={preview.lines}
                rowKey={(l) => l.freight_id}
                onRowClick={(l) => toggle(l.freight_id)}
                empty={
                  <EmptyState
                    title="Nothing to bill"
                    description="No completed, uninvoiced freights in that period."
                  />
                }
                columns={[
                  {
                    key: 'pick',
                    header: '',
                    width: '2.5rem',
                    render: (l) => (
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--accent)]"
                        checked={chosen.has(l.freight_id)}
                        onChange={() => toggle(l.freight_id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Include ${l.trip_no}`}
                      />
                    ),
                  },
                  { key: 'trip', header: 'Freight', render: (l) => l.trip_no },
                  { key: 'date', header: 'Date', render: (l) => <span className="tnum">{l.trip_date}</span> },
                  {
                    key: 'dest',
                    header: 'Destination',
                    render: (l) => (
                      <span className="block max-w-[16rem] truncate">{l.destination_text ?? '—'}</span>
                    ),
                  },
                  { key: 'km', header: 'KM', align: 'right', render: (l) => <span className="tnum">{l.km}</span> },
                  {
                    key: 'total',
                    header: 'Amount',
                    align: 'right',
                    render: (l) => (
                      <span
                        className="tnum"
                        style={chosen.has(l.freight_id) ? undefined : { color: 'var(--text-faint)' }}
                      >
                        {rupees(l.line_total)}
                      </span>
                    ),
                  },
                ]}
              />
            </Card>

            <div className="inset space-y-1.5 p-4">
              <Row
                label={`Taxable value (${picked.length} freight${picked.length === 1 ? '' : 's'})`}
                value={pickedTaxable.toFixed(2)}
              />
              <Row label={`GST at ${preview.gst_rate_percent}%`} value={pickedGst.toFixed(2)} />
              <div className="groove my-1.5" />
              <div className="flex items-baseline justify-between">
                <span className="text-[13px] font-semibold">Invoice total</span>
                <span className="tnum text-[18px] font-semibold">
                  {rupees((pickedTaxable + pickedGst).toFixed(2))}
                </span>
              </div>
              {picked.length < preview.lines.length ? (
                <p className="pt-1 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  {preview.lines.length - picked.length} freight
                  {preview.lines.length - picked.length === 1 ? '' : 's'} left off this invoice,
                  still unbilled.
                </p>
              ) : null}
            </div>

            {/* What will be stapled behind the bill, before it exists. A sheet
                with an unpriced article on it is money being given away, and
                the moment to notice is now rather than after the invoice has
                gone to Godrej. */}
            <SheetsToAttach freightIds={[...chosen]} />
          </div>
        ) : null}

        <ErrorNote>{error}</ErrorNote>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!preview || chosen.size === 0}
            loading={doGenerate.isPending}
            onClick={() => {
              setError(null)
              doGenerate.mutate()
            }}
          >
            {chosen.size && preview && chosen.size < preview.lines.length
              ? `Bill ${chosen.size} freight${chosen.size === 1 ? '' : 's'}`
              : 'Create invoice'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* The unloading sheets that will go behind this invoice, before it is made.
 *
 * A summary rather than the forms themselves: at this point the question is
 * "is this right to send", not "what does the paper look like". One line per
 * delivery, the dealer and the bill it is against, and anything that needs a
 * second look called out — an article carried but never priced is money given
 * away, and the moment to catch it is before the bill goes to the vendor.
 */
function SheetsToAttach({ freightIds }: { freightIds: string[] }) {
  const sheets = useList<ChargeSheetData>(
    '/unloading-sheets',
    { freight_ids: freightIds },
    freightIds.length > 0,
  )

  if (!freightIds.length || sheets.isLoading || !sheets.data?.length) return null

  const total = sheets.data.reduce((sum, s) => sum + Number(s.billed_total), 0)
  const unpriced = sheets.data.filter((s) => s.unpriced_item_codes.length)
  const disagreeing = sheets.data.filter((s) => !s.agrees_with_invoice)

  return (
    <div className="inset space-y-2 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[13px] font-medium">
          {sheets.data.length} unloading{' '}
          {sheets.data.length === 1 ? 'sheet' : 'sheets'} will be attached
        </p>
        <span className="tnum text-[13px]">{rupees(total.toFixed(2))}</span>
      </div>

      <div className="space-y-1">
        {sheets.data.map((s) => (
          <div key={s.point_id} className="flex items-baseline justify-between gap-3 text-[12px]">
            <span className="min-w-0 truncate" style={{ color: 'var(--text-muted)' }}>
              {s.customer_name}
              {s.vendor_bill_nos.length ? ` · ${s.vendor_bill_nos.join(', ')}` : ''} ·{' '}
              {s.item_count} {s.item_count === 1 ? 'item' : 'items'}
              {s.floor_number > 0 ? `, floor ${s.floor_number}` : ''}
            </span>
            <span className="tnum shrink-0">{rupees(s.billed_total)}</span>
          </div>
        ))}
      </div>

      {unpriced.length ? (
        <p className="pt-1 text-[12px]" style={{ color: 'var(--danger)' }}>
          {unpriced.length} {unpriced.length === 1 ? 'sheet has' : 'sheets have'} an article with
          no rate on file, billed as nothing:{' '}
          {[...new Set(unpriced.flatMap((s) => s.unpriced_item_codes))].join(', ')}.
        </p>
      ) : null}
      {disagreeing.length ? (
        <p className="pt-1 text-[12px]" style={{ color: 'var(--warning)' }}>
          {disagreeing.length} {disagreeing.length === 1 ? 'sheet does' : 'sheets do'} not add up
          to what was charged. Worth checking before this goes out.
        </p>
      ) : null}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between text-[13px]">
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="tnum">{rupees(value)}</span>
    </div>
  )
}

/* Where an invoice goes next. DRAFT is a working copy; ISSUED is the document
   the vendor has been given; SENT records that it went; PAID stops it being
   chased. Only ever one step forward, because skipping to PAID from a draft
   nobody sent is how an unpaid invoice disappears. */
const NEXT_STATUS: Record<string, { to: string; label: string } | undefined> = {
  DRAFT: { to: 'ISSUED', label: 'Issue invoice' },
  ISSUED: { to: 'SENT', label: 'Mark as sent' },
  SENT: { to: 'PAID', label: 'Mark as paid' },
}

function InvoiceDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient()
  const company = useItem<Company>('/company')

  const setStatus = useMutation({
    mutationFn: async (status: string) =>
      (await api.patch(`/invoices/${id}`, { status })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/invoices/${id}`] })
      queryClient.invalidateQueries({ queryKey: ['/invoices'] })
    },
  })

  const discard = useMutation({
    mutationFn: async () => (await api.delete(`/invoices/${id}`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/invoices'] })
      // The freights that were on it are COMPLETED again and will show up on
      // the next invoice, so anything listing them is now stale.
      queryClient.invalidateQueries({ queryKey: ['/freights'] })
      onBack()
    },
  })
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [editing, setEditing] = useState(false)
  const [paying, setPaying] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const removeLine = useMutation({
    mutationFn: async (lineId: string) =>
      (await api.delete(`/invoices/${id}/lines/${lineId}`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/invoices/${id}`] })
      queryClient.invalidateQueries({ queryKey: ['/invoices'] })
      // The freight that came off is COMPLETED again.
      queryClient.invalidateQueries({ queryKey: ['/freights'] })
    },
    onError: (e) => setActionError(apiErrorMessage(e)),
  })

  const invoice = useItem<Invoice>(`/invoices/${id}`)

  if (invoice.isLoading || !invoice.data) {
    return (
      <div className="flex justify-center py-20">
        <Spinner className="size-6" />
      </div>
    )
  }

  const inv = invoice.data

  return (
    <div className="space-y-5">
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-[13px] print:hidden"
        style={{ color: 'var(--text-muted)' }}
      >
        <ArrowLeft className="size-4" />
        All invoices
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-semibold">{inv.invoice_no}</h1>
          <p className="mt-1 text-[13px]" style={{ color: 'var(--text-muted)' }}>
            {inv.vendor_division_name} · {inv.period_from} to {inv.period_to} · issued{' '}
            {inv.invoice_date}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 print:hidden">
          {/* An invoice does not sit at DRAFT forever. The next step in its
              life is one button, and the one after that is the one that
              matters: PAID is what stops it being chased. */}
          {/* SENT -> PAID is not a status flip. A payment is four facts —
              when, how much, how, and against what reference — and the amount
              is routinely LESS than the invoice because of TDS deducted at
              source. Flipping a flag would record the invoice total as money
              in, and the bank reconciliation would be short with nothing to
              explain it. */}
          {inv.status === 'SENT' ? (
            <Button onClick={() => setPaying(true)}>Record payment</Button>
          ) : NEXT_STATUS[inv.status] ? (
            <Button
              loading={setStatus.isPending}
              onClick={() => setStatus.mutate(NEXT_STATUS[inv.status]!.to)}
            >
              {NEXT_STATUS[inv.status]!.label}
            </Button>
          ) : null}

          {/* A draft is a working copy, so a freight that turns out to be
              disputed can come off it without discarding and re-ticking
              everything else. */}
          {inv.status === 'DRAFT' && inv.lines.length > 1 ? (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit lines
            </Button>
          ) : null}
          {/* A draft is a working copy — nobody has seen it, so it can simply
              go away and its freights become available again. Once ISSUED the
              number has left the building and the document is cancelled
              instead, because a gap in the invoice series is the first thing
              an auditor asks about. */}
          {inv.status === 'DRAFT' ? (
            <Button
              variant="ghost"
              loading={discard.isPending}
              onClick={() => setConfirmDiscard(true)}
            >
              Discard draft
            </Button>
          ) : inv.status !== 'CANCELLED' && inv.status !== 'PAID' ? (
            <Button
              variant="ghost"
              loading={setStatus.isPending}
              onClick={() => setStatus.mutate('CANCELLED')}
            >
              Cancel invoice
            </Button>
          ) : null}
          <Button
            variant="secondary"
            icon={<Printer className="size-4" />}
            onClick={() => window.print()}
          >
            Print / PDF
          </Button>
        </div>
      </div>

      {/* The document itself, not a screen with the numbers on it. This is what
          goes to the vendor's accounts team. */}
      {company.data ? (
        <TaxInvoice invoice={inv as unknown as Parameters<typeof TaxInvoice>[0]['invoice']} company={company.data} />
      ) : (
        <div className="skeleton h-96" />
      )}

      {/* The working behind the unloading line, as the forms the dealers
          signed. They print with the invoice because that is how the vendor
          receives them today — on paper, stapled behind the bill. */}
      <InvoiceSheets invoiceId={id} companyName={company.data?.name ?? ''} />


      <Modal
        open={editing}
        onClose={() => {
          setEditing(false)
          setActionError(null)
        }}
        wide
        title={`Edit ${inv.invoice_no}`}
        description="Take a freight off this draft. It goes back to Completed and comes up on the next invoice."
      >
        <div className="space-y-3">
          <Card className="overflow-hidden">
            <Table
              rows={inv.lines}
              rowKey={(l) => l.id}
              columns={[
                { key: 'sl', header: '#', render: (l) => <span className="tnum">{l.sl_no}</span> },
                { key: 'trip', header: 'Freight', render: (l) => l.trip_no },
                {
                  key: 'date',
                  header: 'Date',
                  render: (l) => <span className="tnum">{l.trip_date}</span>,
                },
                {
                  key: 'dest',
                  header: 'Destination',
                  render: (l) => (
                    <span className="block max-w-[14rem] truncate">{l.destination_text}</span>
                  ),
                },
                {
                  key: 'amount',
                  header: 'Amount',
                  align: 'right',
                  render: (l) => <span className="tnum">{rupees(l.line_total)}</span>,
                },
                {
                  key: 'remove',
                  header: '',
                  align: 'right',
                  render: (l) => (
                    <button
                      type="button"
                      className="rounded-lg p-1.5 hover:bg-[var(--surface-hover)]"
                      style={{ color: 'var(--danger)' }}
                      aria-label={`Remove ${l.trip_no}`}
                      disabled={removeLine.isPending || inv.lines.length === 1}
                      onClick={() => {
                        setActionError(null)
                        removeLine.mutate(l.id)
                      }}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  ),
                },
              ]}
            />
          </Card>

          <ErrorNote>{actionError}</ErrorNote>
          <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
            The totals and the serial numbers are re-added after every change. The last freight
            cannot be removed — discard the draft instead.
          </p>
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(false)
                setActionError(null)
              }}
            >
              Done
            </Button>
          </div>
        </div>
      </Modal>

      <PaymentModal
        invoice={inv}
        open={paying}
        onClose={() => setPaying(false)}
        onDone={() => {
          setPaying(false)
          queryClient.invalidateQueries({ queryKey: [`/invoices/${id}`] })
          queryClient.invalidateQueries({ queryKey: ['/invoices'] })
          queryClient.invalidateQueries({ queryKey: ['/money-in'] })
        }}
      />

      <Modal
        open={confirmDiscard}
        onClose={() => setConfirmDiscard(false)}
        title={`Discard ${inv.invoice_no}?`}
        description="Nothing has been sent to the vendor yet, so this draft can simply go away."
      >
        <div className="space-y-4">
          <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
            The {inv.line_count} {inv.line_count === 1 ? 'freight' : 'freights'} on it go back to{' '}
            <strong>Completed</strong> and will be picked up by the next invoice you generate.
            The draft itself is not kept.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirmDiscard(false)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              loading={discard.isPending}
              onClick={() => discard.mutate()}
            >
              Discard draft
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

/* The unloading charge sheets behind an invoice.
 *
 * The invoice says the vendor owes 4,200 for unloading across seven trips.
 * These say which dealer, which bill, which floor and which articles made up
 * every rupee of it — and they are the documents the vendor's people already
 * recognise, because Target Express hands them over on paper today.
 *
 * Printed one to a page behind the invoice, so "Print / PDF" produces the
 * whole packet rather than the covering page of it.
 */
function InvoiceSheets({ invoiceId, companyName }: { invoiceId: string; companyName: string }) {
  const sheets = useList<ChargeSheetData>(`/invoices/${invoiceId}/unloading-sheets`)

  if (sheets.isLoading) return <div className="skeleton h-32 print:hidden" />
  if (!sheets.data?.length) return null

  const total = sheets.data.reduce((sum, s) => sum + Number(s.billed_total), 0)
  const queries = sheets.data.filter((s) => !s.agrees_with_invoice || s.unpriced_item_codes.length)

  return (
    <div className="space-y-5">
      <div className="tx-sheet-page">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-semibold">
            Annexure — unloading charge sheets
          </h2>
          <p className="tnum text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            {sheets.data.length} {sheets.data.length === 1 ? 'point' : 'points'} ·{' '}
            {rupees(total.toFixed(2))}
          </p>
        </div>
        <p className="mt-1 text-[12.5px] print:hidden" style={{ color: 'var(--text-muted)' }}>
          One per delivery point, printed behind the invoice. This is the working the vendor
          checks the unloading line against.
        </p>

        {queries.length ? (
          <p
            className="mt-2 rounded-[var(--radius-control)] px-3.5 py-2.5 text-[12.5px] print:hidden"
            style={{ background: 'color-mix(in oklab, var(--warning) 12%, transparent)' }}
          >
            {queries.length} {queries.length === 1 ? 'sheet needs' : 'sheets need'} a look before
            this goes out — marked below.
          </p>
        ) : null}
      </div>

      {sheets.data.map((sheet) => (
        <div key={sheet.point_id} className="tx-sheet-page">
          <ChargeSheet sheet={sheet} companyName={companyName} />
        </div>
      ))}
    </div>
  )
}

/* Recording what the vendor actually paid.

   Deliberately not a status flip. A payment is four facts, and the one that
   matters most is the amount: transport vendors deduct TDS at source, so a
   92,478.40 invoice is settled by 91,553.62 and the balance turns up months
   later as a credit. Writing the invoice total into the receipt would overstate
   money in and leave the bank reconciliation short with nothing to explain the
   gap — so the amount is editable, and the shortfall is named on screen before
   it is saved rather than discovered at year end. */
function PaymentModal({
  invoice,
  open,
  onClose,
  onDone,
}: {
  invoice: Invoice
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10))
  const [amount, setAmount] = useState(invoice.total)
  const [mode, setMode] = useState('NEFT')
  const [reference, setReference] = useState('')
  const [error, setError] = useState<string | null>(null)

  const pay = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/invoices/${invoice.id}/payment`, {
          paid_on: paidOn,
          amount_received: amount,
          payment_mode: mode || null,
          payment_reference: reference || null,
        })
      ).data,
    onSuccess: onDone,
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const shortfall = Number(invoice.total) - Number(amount || 0)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Payment against ${invoice.invoice_no}`}
      description="This is what goes into Money in, so it should match the bank credit rather than the invoice."
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Received on">
            <Input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
          </Field>
          <Field label="Amount received" hint={`Invoice total ${rupees(invoice.total)}`}>
            <Input
              className="tnum"
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </Field>
        </div>

        {shortfall > 0 ? (
          <div
            className="rounded-[var(--radius-control)] px-3.5 py-3 text-[12.5px]"
            style={{
              background: 'color-mix(in oklab, var(--warning) 12%, transparent)',
              color: 'var(--text)',
            }}
          >
            <strong>{rupees(shortfall.toFixed(2))}</strong> short of the invoice. That is normal
            when TDS has been deducted at source — it will show as a shortfall under Money in so
            it can be set against the TDS credit later.
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Mode">
            <Select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="NEFT">NEFT / RTGS</option>
              <option value="UPI">UPI</option>
              <option value="CHEQUE">Cheque</option>
              <option value="CASH">Cash</option>
              <option value="OTHER">Other</option>
            </Select>
          </Field>
          <Field label="Reference" hint="UTR, cheque number — what to look for on the statement">
            <Input value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={pay.isPending}
            onClick={() => {
              setError(null)
              pay.mutate()
            }}
          >
            Record payment
          </Button>
        </div>
      </div>
    </Modal>
  )
}
