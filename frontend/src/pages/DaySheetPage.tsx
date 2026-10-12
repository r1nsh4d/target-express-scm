import { useMutation } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Check, CircleAlert, Sparkles, Wand2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import type { Consignee, VendorDivision, Warehouse } from '@/lib/resources'
import { useList } from '@/lib/resources'

/* The whole morning on one screen.

   Entering a day used to be: a dialog per bill, then a separate screen to
   build the freight, then a third pass attaching each bill to its stop. Thirty
   bills is thirty round trips and the attaching step is the one people miss —
   which is how a sorting sheet ends up full of zeroes with nothing to print.

   Here it is one textarea, one review, one button. The reading is done on the
   server by rules and fuzzy matching: no API key, no cost per line, no
   internet needed, and no customer's name leaves the machine. It is not a
   language model and does not pretend to be. What it will not do is guess
   quietly — every line says what it understood, and anything doubtful waits
   for a person, because a wrong customer on a bill is a carton delivered to
   the wrong town. */

interface Match {
  consignee_id: string | null
  name: string
  score: number
  alternatives: { id: string; name: string; city: string | null; score: number }[]
}

interface ParsedLine {
  line_no: number
  raw: string
  vendor_bill_no: string | null
  customer_text: string
  match: Match | null
  box_count: number | null
  item_name: string | null
  problems: string[]
}

interface ParseOut {
  lines: ParsedLine[]
  bill_count: number
  box_count: number
  stop_count: number
  needs_attention: number
}

/* A person's corrections to what was read. Kept apart from the parse result so
   that retyping a line does not silently throw away a customer somebody has
   already confirmed. */
interface Override {
  consignee_id?: string | null
  newCustomerName?: string
  box_count?: number
  vendor_bill_no?: string
}

const EXAMPLE = `GDJ/8870 Rinshad Km 6
GDJ/8871 Kannur DC 4 chairs
gdj 8872 kozikode srvce 2`

export default function DaySheetPage() {
  const navigate = useNavigate()

  const divisions = useList<VendorDivision>('/vendor-divisions')
  const consignees = useList<Consignee>('/consignees')

  const [divisionId, setDivisionId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [tripDate, setTripDate] = useState(new Date().toISOString().slice(0, 10))
  const [makeFreight, setMakeFreight] = useState(true)

  const [text, setText] = useState('')
  const [parsed, setParsed] = useState<ParseOut | null>(null)
  const [overrides, setOverrides] = useState<Record<number, Override>>({})
  const [order, setOrder] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const vendorId = divisions.data?.find((d) => d.id === divisionId)?.vendor_id
  const warehouses = useList<Warehouse>(
    '/warehouses',
    vendorId ? { vendor_id: vendorId } : undefined,
    !!vendorId,
  )

  const doParse = useMutation({
    mutationFn: async (body: { text: string; vendor_division_id: string | null }) =>
      (await api.post<ParseOut>('/daysheet/parse', body)).data,
    onSuccess: setParsed,
  })

  /* Read as you type, but not on every keystroke. 400ms is long enough that a
     line being typed is not parsed half-finished and short enough that it feels
     like the screen is keeping up. */
  useEffect(() => {
    if (!text.trim()) {
      setParsed(null)
      return
    }
    const timer = window.setTimeout(() => {
      doParse.mutate({ text, vendor_division_id: divisionId || null })
    }, 400)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, divisionId])

  /* What each line will actually create, once a person's corrections are laid
     over what was read. */
  const rows = useMemo(() => {
    if (!parsed) return []
    return parsed.lines.map((line) => {
      const o = overrides[line.line_no] ?? {}
      const consigneeId =
        o.consignee_id !== undefined ? o.consignee_id : (line.match?.consignee_id ?? null)
      const name =
        consigneeId
          ? (consignees.data?.find((c) => c.id === consigneeId)?.name ?? line.match?.name ?? '')
          : (o.newCustomerName ?? line.customer_text)

      const billNo = o.vendor_bill_no ?? line.vendor_bill_no ?? ''
      const boxes = o.box_count ?? line.box_count ?? 0

      const blockers: string[] = []
      if (!billNo) blockers.push('needs a bill number')
      if (!boxes || boxes < 1) blockers.push('needs a box count')
      if (!consigneeId && !o.newCustomerName) blockers.push('needs a customer')

      return { line, consigneeId, name, billNo, boxes, blockers, o }
    })
  }, [parsed, overrides, consignees.data])

  const ready = rows.length > 0 && rows.every((r) => r.blockers.length === 0)
  const totalBoxes = rows.reduce((sum, r) => sum + r.boxes, 0)

  /* The stops, in the order they will be delivered. One per customer however
     many bills they have — the vendor is charged per point, so splitting a
     customer's two bills into two stops would overcharge them and the invoice
     would be queried. */
  const stops = useMemo(() => {
    const byCustomer = new Map<string, { name: string; bills: number; boxes: number }>()
    for (const r of rows) {
      if (!r.consigneeId) continue
      const current = byCustomer.get(r.consigneeId) ?? { name: r.name, bills: 0, boxes: 0 }
      current.bills += 1
      current.boxes += r.boxes
      byCustomer.set(r.consigneeId, current)
    }
    const ids = [...byCustomer.keys()]
    const ordered = [...order.filter((id) => ids.includes(id)), ...ids.filter((id) => !order.includes(id))]
    return ordered.map((id) => ({ id, ...byCustomer.get(id)! }))
  }, [rows, order])

  function move(index: number, by: number) {
    const ids = stops.map((s) => s.id)
    const next = index + by
    if (next < 0 || next >= ids.length) return
    ;[ids[index], ids[next]] = [ids[next], ids[index]]
    setOrder(ids)
  }

  function set(lineNo: number, patch: Override) {
    setOverrides((current) => ({ ...current, [lineNo]: { ...current[lineNo], ...patch } }))
  }

  const commit = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ freight_id: string | null; trip_no: string | null }>(
          '/daysheet/commit',
          {
            vendor_division_id: divisionId,
            warehouse_id: warehouseId,
            trip_date: tripDate,
            create_freight: makeFreight,
            stop_order: stops.map((s) => s.id),
            rows: rows.map((r) => ({
              vendor_bill_no: r.billNo,
              box_count: r.boxes,
              item_name: r.line.item_name,
              consignee_id: r.consigneeId,
              new_customer: r.consigneeId
                ? null
                : { name: r.o.newCustomerName ?? r.line.customer_text },
            })),
          },
        )
      ).data,
    onSuccess: (result) => {
      setText('')
      setParsed(null)
      setOverrides({})
      setOrder([])
      navigate(result.freight_id ? `/freights/${result.freight_id}` : '/consignments')
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const canCommit = ready && !!divisionId && !!warehouseId

  return (
    <div className="space-y-6">
      <PageHeader description="Type or paste the day's bills, one per line. They are read here — bill number, customer, box count — and the bills, the boxes, the freight and its stops are all created in one action." />

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Vendor division">
          <Select
            value={divisionId}
            onChange={(e) => {
              setDivisionId(e.target.value)
              setWarehouseId('')
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
        <Field label="Loading warehouse">
          <Select
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            disabled={!vendorId}
          >
            <option value="">Select</option>
            {warehouses.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Date">
          <Input type="date" value={tripDate} onChange={(e) => setTripDate(e.target.value)} />
        </Field>
      </div>

      <div>
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
            The day&rsquo;s bills
          </span>
          {!text ? (
            <button
              type="button"
              className="text-[12px] underline underline-offset-2"
              style={{ color: 'var(--accent)' }}
              onClick={() => setText(EXAMPLE)}
            >
              Show me an example
            </button>
          ) : null}
        </div>
        <Textarea
          rows={8}
          className="font-mono text-[13px]"
          placeholder={`One bill per line, in any order:\n\n${EXAMPLE}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <p className="mt-1.5 text-[12px]" style={{ color: 'var(--text-faint)' }}>
          <Wand2 className="mr-1 inline size-3" />
          Bill number, customer and box count, in whatever order they come out. Misspelt customer
          names are matched to the list; a tab- or comma-separated paste out of a spreadsheet works
          too.
        </p>
      </div>

      {doParse.isPending && !parsed ? (
        <div className="flex justify-center py-8">
          <Spinner className="size-5" />
        </div>
      ) : null}

      {parsed && rows.length ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="eyebrow">
              {rows.length} bill{rows.length === 1 ? '' : 's'} · {totalBoxes} boxes ·{' '}
              {stops.length} stop{stops.length === 1 ? '' : 's'}
            </h2>
            {ready ? (
              <span
                className="inline-flex items-center gap-1 text-[12.5px]"
                style={{ color: 'var(--success)' }}
              >
                <Check className="size-3.5" /> All read
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 text-[12.5px]"
                style={{ color: 'var(--warning)' }}
              >
                <CircleAlert className="size-3.5" />
                {rows.filter((r) => r.blockers.length).length} need a look
              </span>
            )}
          </div>

          <div className="space-y-2">
            {rows.map((r) => (
              <LineRow
                key={r.line.line_no}
                row={r}
                customers={consignees.data ?? []}
                onSet={(patch) => set(r.line.line_no, patch)}
              />
            ))}
          </div>

          {makeFreight && stops.length ? (
            <Card className="p-4">
              <h3 className="text-[14px] font-semibold">Stops, in delivery order</h3>
              <p className="mt-0.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                One stop per customer, however many bills they have — the vendor is charged per
                point, not per bill.
              </p>
              <div className="mt-3 space-y-1.5">
                {stops.map((s, i) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 rounded-lg border px-3 py-2"
                    style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
                  >
                    <span
                      className="tnum grid size-6 shrink-0 place-items-center rounded-md text-[12px] font-semibold"
                      style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                    >
                      {i + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[13px]">{s.name}</span>
                    <span className="tnum text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {s.bills} bill{s.bills === 1 ? '' : 's'} · {s.boxes} boxes
                    </span>
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        className="rounded p-1 hover:bg-[var(--surface-hover)] disabled:opacity-30"
                        disabled={i === 0}
                        onClick={() => move(i, -1)}
                        aria-label={`Move ${s.name} earlier`}
                      >
                        <ArrowUp className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        className="rounded p-1 hover:bg-[var(--surface-hover)] disabled:opacity-30"
                        disabled={i === stops.length - 1}
                        onClick={() => move(i, 1)}
                        aria-label={`Move ${s.name} later`}
                      >
                        <ArrowDown className="size-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

          <label className="flex items-center gap-2.5 text-[13px]">
            <input
              type="checkbox"
              className="size-4 accent-[var(--accent)]"
              checked={makeFreight}
              onChange={(e) => setMakeFreight(e.target.checked)}
            />
            <span>
              Build the freight as well
              <span className="block text-[12px]" style={{ color: 'var(--text-faint)' }}>
                Leave this off to enter the bills now and decide the lorry later.
              </span>
            </span>
          </label>

          <ErrorNote>{error}</ErrorNote>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              {!divisionId || !warehouseId
                ? 'Pick the vendor division and warehouse above.'
                : ready
                  ? 'Nothing is created until you press this.'
                  : 'Fix the lines marked above first.'}
            </p>
            <Button
              icon={<Sparkles className="size-4" />}
              disabled={!canCommit}
              loading={commit.isPending}
              onClick={() => {
                setError(null)
                commit.mutate()
              }}
            >
              {makeFreight
                ? `Create ${rows.length} bill${rows.length === 1 ? '' : 's'} + freight`
                : `Create ${rows.length} bill${rows.length === 1 ? '' : 's'}`}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  )
}

/* One line, as it was read, with every piece correctable in place.

   The confidence is shown rather than hidden. A match at 100% needs no
   thought; one at 71% is exactly the case where somebody should look, and
   saying so is cheaper than a carton going to the wrong town. */
function LineRow({
  row,
  customers,
  onSet,
}: {
  row: {
    line: ParsedLine
    consigneeId: string | null
    name: string
    billNo: string
    boxes: number
    blockers: string[]
    o: Override
  }
  customers: Consignee[]
  onSet: (patch: Override) => void
}) {
  const { line, consigneeId, billNo, boxes, blockers } = row
  const unsure = !!line.match?.consignee_id && line.match.score < 0.86
  const needsLook = blockers.length > 0

  return (
    <div
      className="rounded-lg border p-3"
      style={{
        borderColor: needsLook
          ? 'color-mix(in oklab, var(--warning) 40%, transparent)'
          : 'var(--border)',
        background: 'var(--bg-elevated)',
      }}
    >
      <div className="grid gap-3 sm:grid-cols-[9rem_1fr_5rem]">
        <div>
          <span className="mb-1 block text-[11px]" style={{ color: 'var(--text-faint)' }}>
            Bill no
          </span>
          <Input
            value={billNo}
            placeholder="GDJ/8870"
            onChange={(e) => onSet({ vendor_bill_no: e.target.value })}
          />
        </div>

        <div>
          <span className="mb-1 block text-[11px]" style={{ color: 'var(--text-faint)' }}>
            Customer
          </span>
          <Select
            value={consigneeId ?? '__new__'}
            onChange={(e) =>
              onSet(
                e.target.value === '__new__'
                  ? { consignee_id: null, newCustomerName: row.name }
                  : { consignee_id: e.target.value },
              )
            }
          >
            <option value="__new__">
              + Create &ldquo;{row.o.newCustomerName ?? line.customer_text}&rdquo;
            </option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.city ? ` · ${c.city}` : ''}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <span className="mb-1 block text-[11px]" style={{ color: 'var(--text-faint)' }}>
            Boxes
          </span>
          <Input
            className="tnum"
            type="number"
            min={1}
            value={boxes || ''}
            onChange={(e) => onSet({ box_count: Number(e.target.value) || 0 })}
          />
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px]">
        <span className="font-mono" style={{ color: 'var(--text-faint)' }}>
          {line.raw}
        </span>
        {line.item_name ? (
          <span style={{ color: 'var(--text-muted)' }}>· {line.item_name}</span>
        ) : null}
        {consigneeId && line.match ? (
          <span
            style={{
              color: unsure ? 'var(--warning)' : 'var(--text-faint)',
            }}
          >
            · matched {Math.round(line.match.score * 100)}%
          </span>
        ) : null}
      </div>

      {/* The runners-up, offered only when the top match was not confident.
          "Did you mean" is of no use without them. */}
      {unsure && line.match?.alternatives.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px]">
          <span style={{ color: 'var(--text-muted)' }}>Or:</span>
          {line.match.alternatives.map((alt) => (
            <button
              key={alt.id}
              type="button"
              className="rounded-full px-2.5 py-0.5 underline underline-offset-2"
              style={{ color: 'var(--accent)' }}
              onClick={() => onSet({ consignee_id: alt.id })}
            >
              {alt.name}
            </button>
          ))}
        </div>
      ) : null}

      {needsLook ? (
        <p className="mt-2 text-[12px]" style={{ color: 'var(--warning)' }}>
          This line {blockers.join(', ')}.
        </p>
      ) : null}
    </div>
  )
}
