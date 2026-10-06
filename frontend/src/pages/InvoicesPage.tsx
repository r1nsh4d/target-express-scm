import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, Printer, Sparkles } from 'lucide-react'
import { useState } from 'react'

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

  const doPreview = useMutation({
    mutationFn: async () => (await api.post<Preview>('/invoices/preview', form)).data,
    onSuccess: setPreview,
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const doGenerate = useMutation({
    mutationFn: async () => (await api.post<Invoice>('/invoices', form)).data,
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

            <Card className="overflow-hidden">
              <Table
                rows={preview.lines}
                rowKey={(l) => l.trip_no}
                empty={
                  <EmptyState
                    title="Nothing to bill"
                    description="No completed, uninvoiced freights in that period."
                  />
                }
                columns={[
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
                    render: (l) => <span className="tnum">{rupees(l.line_total)}</span>,
                  },
                ]}
              />
            </Card>

            <div className="inset space-y-1.5 p-4">
              <Row label={`Taxable value (${preview.freight_count} freights)`} value={preview.taxable_value} />
              <Row label={`GST at ${preview.gst_rate_percent}%`} value={preview.gst_amount} />
              <div className="groove my-1.5" />
              <div className="flex items-baseline justify-between">
                <span className="text-[13px] font-semibold">Invoice total</span>
                <span className="tnum text-[18px] font-semibold">{rupees(preview.total)}</span>
              </div>
            </div>
          </div>
        ) : null}

        <ErrorNote>{error}</ErrorNote>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!preview || !preview.freight_count}
            loading={doGenerate.isPending}
            onClick={() => {
              setError(null)
              doGenerate.mutate()
            }}
          >
            Create invoice
          </Button>
        </div>
      </div>
    </Modal>
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

function InvoiceDetail({ id, onBack }: { id: string; onBack: () => void }) {
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
        <Button
          variant="secondary"
          icon={<Printer className="size-4" />}
          onClick={() => window.print()}
          className="print:hidden"
        >
          Print
        </Button>
      </div>

      <Card className="overflow-hidden">
        <Table
          rows={inv.lines}
          rowKey={(l) => l.id}
          empty={<EmptyState title="No lines" />}
          columns={[
            { key: 'sl', header: '#', render: (l) => <span className="tnum">{l.sl_no}</span> },
            { key: 'date', header: 'Date', render: (l) => <span className="tnum">{l.trip_date}</span> },
            { key: 'trip', header: 'Freight', render: (l) => l.trip_no },
            { key: 'lr', header: 'LR', render: (l) => l.lr_no ?? '—' },
            { key: 'veh', header: 'Vehicle', render: (l) => l.vehicle_no },
            {
              key: 'dest',
              header: 'Destination',
              render: (l) => (
                <span className="block max-w-[15rem] truncate">{l.destination_text}</span>
              ),
            },
            { key: 'km', header: 'KM', align: 'right', render: (l) => <span className="tnum">{l.km}</span> },
            {
              key: 'base',
              header: 'Base',
              align: 'right',
              render: (l) => <span className="tnum">{rupees(l.base_amount)}</span>,
            },
            {
              key: 'xkm',
              header: 'Extra km',
              align: 'right',
              render: (l) => <span className="tnum">{rupees(l.extra_km_amount)}</span>,
            },
            {
              key: 'xpt',
              header: 'Points',
              align: 'right',
              render: (l) => <span className="tnum">{rupees(l.extra_point_amount)}</span>,
            },
            {
              key: 'toll',
              header: 'Toll',
              align: 'right',
              render: (l) => <span className="tnum">{rupees(l.toll)}</span>,
            },
            {
              key: 'unl',
              header: 'Unloading',
              align: 'right',
              render: (l) => <span className="tnum">{rupees(l.unloading)}</span>,
            },
            {
              // Its own column, never folded into Unloading. A vendor querying
              // why unloading rose this month must be able to see the two
              // apart — one is our crew's work on the rate sheet, the other is
              // cash a local porter gang demanded at a market.
              key: 'coolie',
              header: 'Coolie',
              align: 'right',
              render: (l) =>
                Number(l.coolie) > 0 ? (
                  <span className="tnum" style={{ color: 'var(--warning)' }}>
                    {rupees(l.coolie)}
                  </span>
                ) : (
                  <span style={{ color: 'var(--text-faint)' }}>—</span>
                ),
            },
            {
              key: 'total',
              header: 'Total',
              align: 'right',
              render: (l) => <span className="tnum font-semibold">{rupees(l.line_total)}</span>,
            },
          ]}
        />
      </Card>

      <div className="flex justify-end">
        <Card className="w-full max-w-sm space-y-1.5 p-5">
          <Row label="Taxable value" value={inv.taxable_value} />
          {Number(inv.igst) > 0 ? (
            <Row label="IGST" value={inv.igst} />
          ) : (
            <>
              <Row label="CGST" value={inv.cgst} />
              <Row label="SGST" value={inv.sgst} />
            </>
          )}
          <div className="groove my-2" />
          <div className="flex items-baseline justify-between">
            <span className="text-[13px] font-semibold">Total</span>
            <span className="tnum text-[20px] font-semibold">{rupees(inv.total)}</span>
          </div>
        </Card>
      </div>
    </div>
  )
}
