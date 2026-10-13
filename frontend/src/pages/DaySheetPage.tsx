import { useMutation } from '@tanstack/react-query'
import {
  ArrowDown,
  ArrowUp,
  Check,
  CircleAlert,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button, Card, ErrorNote, Input, Select, Spinner, Textarea } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import type { Consignee, VendorDivision, Warehouse } from '@/lib/resources'
import { useCountUp, stagger } from '@/lib/motion'
import { useList } from '@/lib/resources'

/* The whole morning on one screen.
 *
 * Entering a day used to be a dialog per bill, then a separate screen to build
 * the freight, then a third pass attaching each bill to its stop. Here it is
 * one textarea, one review, one button.
 *
 * The layout earns its keep as much as the parsing does. The first version
 * stacked each understood bill as its own card with its own set of field
 * labels, so three bills filled the screen and the Create button sat below the
 * fold — which, on a screen whose whole promise is "enter thirty bills
 * quickly", is the wrong shape. Now: what you type on the left, what was
 * understood on the right, labels written once, one line per bill, and the
 * action pinned to the bottom where it can always be reached.
 */

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

/* A person's corrections, kept apart from the parse result so that retyping a
   line does not throw away a customer somebody has already confirmed. */
interface Override {
  consignee_id?: string | null
  newCustomerName?: string
  box_count?: number
  vendor_bill_no?: string
  dropped?: boolean
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

  // Only one warehouse for this vendor? Then there is nothing to choose, and
  // asking is one more thing standing between a stack of bills and a freight.
  useEffect(() => {
    const only = warehouses.data
    if (only?.length === 1 && !warehouseId) setWarehouseId(only[0].id)
  }, [warehouses.data, warehouseId])

  const doParse = useMutation({
    mutationFn: async (body: { text: string; vendor_division_id: string | null }) =>
      (await api.post<ParseOut>('/daysheet/parse', body)).data,
    onSuccess: setParsed,
  })

  /* Read as you type, but not on every keystroke. 400ms is long enough that a
     half-typed line is not parsed and short enough to feel immediate. */
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

  const rows = useMemo(() => {
    if (!parsed) return []
    return parsed.lines
      .map((line) => {
        const o = overrides[line.line_no] ?? {}
        const consigneeId =
          o.consignee_id !== undefined ? o.consignee_id : (line.match?.consignee_id ?? null)
        const name = consigneeId
          ? (consignees.data?.find((c) => c.id === consigneeId)?.name ??
            line.match?.name ??
            '')
          : (o.newCustomerName ?? line.customer_text)

        const billNo = o.vendor_bill_no ?? line.vendor_bill_no ?? ''
        const boxes = o.box_count ?? line.box_count ?? 0

        const blockers: string[] = []
        if (!billNo) blockers.push('a bill number')
        if (!boxes || boxes < 1) blockers.push('a box count')
        // A customer nobody has entered yet is not a problem — it is the
        // ordinary case of a new dealer, and the name read off the line is
        // enough to create one. The only real blocker is having no name at
        // all. (This used to require the dropdown to be actively changed,
        // which meant a row that displayed "+ New customer: Vadakara Furniture
        // House" as its selected option still refused to be created, with
        // nothing on screen explaining why.)
        if (!consigneeId && name.trim().length < 2) blockers.push('a customer name')

        return { line, consigneeId, name, billNo, boxes, blockers, o }
      })
      .filter((r) => !r.o.dropped)
  }, [parsed, overrides, consignees.data])

  const ready = rows.length > 0 && rows.every((r) => r.blockers.length === 0)
  const totalBoxes = rows.reduce((sum, r) => sum + r.boxes, 0)
  const needLook = rows.filter((r) => r.blockers.length).length

  const stops = useMemo(() => {
    const byCustomer = new Map<string, { name: string; bills: number; boxes: number }>()
    for (const r of rows) {
      const key = r.consigneeId ?? `new:${r.name.toLowerCase()}`
      const current = byCustomer.get(key) ?? { name: r.name, bills: 0, boxes: 0 }
      current.bills += 1
      current.boxes += r.boxes
      byCustomer.set(key, current)
    }
    const ids = [...byCustomer.keys()]
    const ordered = [
      ...order.filter((id) => ids.includes(id)),
      ...ids.filter((id) => !order.includes(id)),
    ]
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
        await api.post<{ freight_id: string | null }>('/daysheet/commit', {
          vendor_division_id: divisionId,
          warehouse_id: warehouseId,
          trip_date: tripDate,
          create_freight: makeFreight,
          stop_order: stops.map((s) => s.id).filter((id) => !id.startsWith('new:')),
          rows: rows.map((r) => ({
            vendor_bill_no: r.billNo,
            box_count: r.boxes,
            item_name: r.line.item_name,
            consignee_id: r.consigneeId,
            new_customer: r.consigneeId
              ? null
              : { name: r.o.newCustomerName ?? r.line.customer_text },
          })),
        })
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

  /* Counted up rather than snapping. The numbers change as a sheet is typed,
     and a figure that climbs is read as a figure that is being worked out —
     which it is. */
  const billsUp = useCountUp(rows.length)
  const boxesUp = useCountUp(totalBoxes)
  const stopsUp = useCountUp(stops.length)

  const missingSetup = !divisionId || !warehouseId
  const canCommit = ready && !missingSetup

  return (
    /* Room at the bottom for the pinned action bar, so the last row is never
       hidden behind it. */
    <div className="space-y-5">
      {/* A line that says what the screen is doing.
          The parse is debounced and then takes a moment, and without a sign
          that anything is happening people type, wait, and type the line
          again. */}
      <div className="flex flex-wrap items-center gap-2.5">
        {doParse.isPending ? (
          <>
            <span className="live-dot" aria-hidden />
            <span className="text-[13px]" style={{ color: 'var(--accent)' }}>
              Reading the sheet&hellip;
            </span>
          </>
        ) : rows.length ? (
          <>
            <Check className="size-4" style={{ color: ready ? 'var(--success)' : 'var(--warning)' }} />
            <span className="tnum text-[13px]" style={{ color: 'var(--text-muted)' }}>
              <strong style={{ color: 'var(--text)' }}>{billsUp}</strong> bills ·{' '}
              <strong style={{ color: 'var(--text)' }}>{boxesUp}</strong> boxes ·{' '}
              <strong style={{ color: 'var(--text)' }}>{stopsUp}</strong> stops
            </span>
          </>
        ) : (
          <span className="text-[13px]" style={{ color: 'var(--text-faint)' }}>
            Type the day&rsquo;s bills below and they are read as you go.
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Compact label="Vendor division">
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
        </Compact>
        <Compact label="Loading warehouse">
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
        </Compact>
        <Compact label="Date">
          <Input type="date" value={tripDate} onChange={(e) => setTripDate(e.target.value)} />
        </Compact>
      </div>

      {/* What you type, and what it became, side by side — so the translation
          is visible rather than something that happens further down a page. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-4 lg:self-start">
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <span className="text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
              Type the day&rsquo;s bills
            </span>
            {!text ? (
              <button
                type="button"
                className="text-[12px] underline underline-offset-2"
                style={{ color: 'var(--accent)' }}
                onClick={() => setText(EXAMPLE)}
              >
                Show an example
              </button>
            ) : null}
          </div>
          <div className={doParse.isPending ? 'tx-scan rounded-[var(--radius-control)]' : ''}>
          <Textarea
            rows={14}
            className="font-mono text-[13px] leading-relaxed"
            placeholder={`One bill per line:\n\n${EXAMPLE}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
          />
          </div>
          <p className="mt-2 text-[12px] leading-relaxed" style={{ color: 'var(--text-faint)' }}>
            <Wand2 className="mr-1 inline size-3" />
            Bill number, customer and box count, in any order. Misspelt names are matched to the
            list, and a paste out of a spreadsheet works.
          </p>
        </div>

        <div className="min-w-0">
          {doParse.isPending && !parsed ? (
            <div className="flex justify-center py-12">
              <Spinner className="size-5" />
            </div>
          ) : !parsed || !rows.length ? (
            <Card className="relative flex min-h-[14rem] items-center justify-center overflow-hidden p-6 text-center">
              <span className="grid-field" aria-hidden />
              <div className="relative">
                <Wand2 className="mx-auto mb-2 size-6" style={{ color: 'var(--accent)' }} />
                <p className="text-[13.5px] font-medium">Nothing read yet</p>
                <p className="mt-1 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                  What you type on the left appears here, bill by bill, before anything is
                  created.
                </p>
              </div>
            </Card>
          ) : (
            <div className="space-y-2">
              {/* Labels once, not on every row. */}
              <div
                className="grid items-center gap-2 px-2 text-[11px] tracking-[0.1em] uppercase sm:grid-cols-[7.5rem_minmax(0,1fr)_4rem_2rem]"
                style={{ color: 'var(--text-faint)' }}
              >
                <span>Bill no</span>
                <span className="hidden sm:block">Customer</span>
                <span className="hidden text-right sm:block">Boxes</span>
                <span />
              </div>

              {rows.map((r, i) => (
                <LineRow
                  key={r.line.line_no}
                  row={r}
                  index={i}
                  customers={consignees.data ?? []}
                  onSet={(patch) => set(r.line.line_no, patch)}
                />
              ))}

              {makeFreight && stops.length ? (
                <Card className="mt-4 p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-[13.5px] font-semibold">Stops, in delivery order</h3>
                    <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      One per customer — the vendor is charged per stop, not per bill
                    </p>
                  </div>
                  <div className="mt-2.5 space-y-1.5">
                    {stops.map((s, i) => (
                      <div
                        key={s.id}
                        className="flex items-center gap-3 rounded-lg px-3 py-1.5"
                        style={{ background: 'var(--bg-elevated)' }}
                      >
                        <span
                          className="tnum grid size-5 shrink-0 place-items-center rounded text-[11px] font-semibold"
                          style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                        >
                          {i + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[13px]">{s.name}</span>
                        <span className="tnum text-[12px]" style={{ color: 'var(--text-muted)' }}>
                          {s.bills}&nbsp;bill{s.bills === 1 ? '' : 's'} · {s.boxes}&nbsp;boxes
                        </span>
                        <div className="flex shrink-0">
                          <IconBtn
                            label={`Move ${s.name} earlier`}
                            disabled={i === 0}
                            onClick={() => move(i, -1)}
                          >
                            <ArrowUp className="size-3.5" />
                          </IconBtn>
                          <IconBtn
                            label={`Move ${s.name} later`}
                            disabled={i === stops.length - 1}
                            onClick={() => move(i, 1)}
                          >
                            <ArrowDown className="size-3.5" />
                          </IconBtn>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Pinned, so the count and the button are reachable from anywhere in a
          sheet of forty lines without scrolling to the end to find out what it
          adds up to. */}
      {rows.length ? (
        /* Sticky, not fixed. The content area is scaled by the text-size
           setting, and a `fixed` box inside a scaled ancestor is laid out in
           the scaled coordinate space — at the largest setting it would stop
           short of the right-hand edge. Sticky stays in normal flow and is
           unaffected. */
        <div
          /* Lit when the sheet is ready, so the moment it becomes committable
             is visible without reading the count. */
          className={`sticky bottom-0 z-20 -mx-1 rounded-t-[var(--radius-card)] border-t backdrop-blur-md${
            canCommit ? ' lit' : ''
          }`}
          style={{
            borderColor: canCommit
              ? 'color-mix(in oklab, var(--accent) 30%, transparent)'
              : 'var(--border)',
            background: 'color-mix(in oklab, var(--surface-solid) 92%, transparent)',
          }}
        >
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
            <div className="flex items-center gap-2.5">
              {ready ? (
                <Check className="size-4 shrink-0" style={{ color: 'var(--success)' }} />
              ) : (
                <CircleAlert className="size-4 shrink-0" style={{ color: 'var(--warning)' }} />
              )}
              <span className="tnum text-[13.5px] font-medium">
                {billsUp} bill{rows.length === 1 ? '' : 's'} · {boxesUp} boxes
                {makeFreight ? ` · ${stopsUp} stop${stops.length === 1 ? '' : 's'}` : ''}
              </span>
            </div>

            <label className="flex items-center gap-2 text-[12.5px]">
              <input
                type="checkbox"
                className="size-4 accent-[var(--accent)]"
                checked={makeFreight}
                onChange={(e) => setMakeFreight(e.target.checked)}
              />
              Build the freight too
            </label>

            <div className="ms-auto flex items-center gap-3">
              <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                {missingSetup
                  ? 'Pick the division and warehouse above'
                  : needLook
                    ? `${needLook} line${needLook === 1 ? '' : 's'} need a look`
                    : 'Nothing is created until you press this'}
              </span>
              <Button
                icon={<Sparkles className="size-4" />}
                disabled={!canCommit}
                loading={commit.isPending}
                onClick={() => {
                  setError(null)
                  commit.mutate()
                }}
              >
                {makeFreight ? 'Create bills + freight' : 'Create bills'}
              </Button>
            </div>
          </div>
          {error ? (
            <div className="px-4 pb-3">
              <ErrorNote>{error}</ErrorNote>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function Compact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      {children}
    </label>
  )
}

function IconBtn({
  children,
  label,
  disabled,
  onClick,
}: {
  children: React.ReactNode
  label: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="rounded p-1 hover:bg-[var(--surface-hover)] disabled:opacity-25"
      style={{ color: 'var(--text-muted)' }}
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
    >
      {children}
    </button>
  )
}

/* One bill, on one line.
 *
 * Everything is editable in place, with no labels repeated — the header above
 * says what the columns are, once. The raw text and the match confidence only
 * appear when the match was not certain: on a clean sheet of thirty bills,
 * thirty copies of "matched 100%" is noise that hides the one line that needs
 * a person. */
function LineRow({
  row,
  index,
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
  index: number
  customers: Consignee[]
  onSet: (patch: Override) => void
}) {
  const { line, consigneeId, billNo, boxes, blockers } = row
  const score = line.match?.score ?? 0
  const unsure = !!line.match?.consignee_id && score < 0.86
  const isNew = !consigneeId
  const needsLook = blockers.length > 0

  /* The leading edge, coloured by how the line was read.
     Thin and on the left, so thirty rows become one column of confidence that
     can be scanned down in a second — the one amber line in a page of cyan is
     found without reading a word. Its strength follows the match score, so a
     94% match is visibly firmer than a 71% one without a number being read. */
  const edge = needsLook
    ? { colour: 'var(--warning)', strength: 1 }
    : isNew
      ? { colour: 'var(--accent-2)', strength: 0.9 }
      : unsure
        ? { colour: 'var(--warning)', strength: 0.85 }
        : { colour: 'var(--success)', strength: Math.max(0.45, score) }

  return (
    <div
      className="tx-edge tx-in hoverable rounded-[10px] border py-2 pr-2 pl-3.5"
      style={{
        ...stagger(index, 35, 240),
        ['--tx-edge-colour' as string]: edge.colour,
        ['--tx-edge-strength' as string]: String(edge.strength),
        borderColor: needsLook
          ? 'color-mix(in oklab, var(--warning) 45%, transparent)'
          : 'var(--border)',
        background: needsLook
          ? 'color-mix(in oklab, var(--warning) 6%, var(--surface))'
          : 'var(--surface)',
      }}
    >
      <div className="grid items-center gap-2 sm:grid-cols-[7.5rem_minmax(0,1fr)_4rem_2rem]">
        <Input
          value={billNo}
          placeholder="GDJ/8870"
          className="font-mono text-[12.5px]"
          onChange={(e) => onSet({ vendor_bill_no: e.target.value })}
        />

        {/* A new dealer gets a text box, not a dropdown.
            The parser's guess at a name it has never seen is exactly where it
            is least reliable — "kozikode srvce" is a fine thing to MATCH
            against an existing branch and a poor thing to create a customer
            called. So the name is editable before it becomes a record, and the
            dropdown beside it is the way back to the existing list. */}
        {isNew ? (
          <div className="flex min-w-0 gap-2">
            <Input
              value={row.o.newCustomerName ?? line.customer_text}
              placeholder="New customer's name"
              onChange={(e) => onSet({ newCustomerName: e.target.value })}
              aria-label="New customer name"
            />
            <Select
              className="w-[11rem] shrink-0"
              value="__new__"
              onChange={(e) => onSet({ consignee_id: e.target.value })}
            >
              <option value="__new__">New customer</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.city ? ` · ${c.city}` : ''}
                </option>
              ))}
            </Select>
          </div>
        ) : (
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
            <option value="__new__">+ New customer</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.city ? ` · ${c.city}` : ''}
              </option>
            ))}
          </Select>
        )}

        <Input
          className="tnum text-center"
          type="number"
          min={1}
          value={boxes || ''}
          onChange={(e) => onSet({ box_count: Number(e.target.value) || 0 })}
          aria-label="Boxes"
        />

        <IconBtn label={`Remove ${billNo || 'this line'}`} onClick={() => onSet({ dropped: true })}>
          <Trash2 className="size-3.5" />
        </IconBtn>
      </div>

      {/* Only when it is worth saying. */}
      {needsLook || unsure || isNew || line.item_name ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11.5px]">
          {needsLook ? (
            <span style={{ color: 'var(--warning)' }}>
              Needs {blockers.join(' and ')} — typed “{line.raw}”
            </span>
          ) : null}
          {isNew && !needsLook ? (
            <span style={{ color: 'var(--accent)' }}>
              Nobody on file matches “{line.customer_text}” — this will be created as a new
              customer. Add their address and phone later under Customers.
            </span>
          ) : null}
          {unsure && !needsLook ? (
            <span style={{ color: 'var(--warning)' }}>
              Matched {Math.round((line.match?.score ?? 0) * 100)}% — check this
            </span>
          ) : null}
          {line.item_name ? (
            <span style={{ color: 'var(--text-faint)' }}>{line.item_name}</span>
          ) : null}
          {unsure
            ? line.match?.alternatives.map((alt) => (
                <button
                  key={alt.id}
                  type="button"
                  className="underline underline-offset-2"
                  style={{ color: 'var(--accent)' }}
                  onClick={() => onSet({ consignee_id: alt.id })}
                >
                  {alt.name}?
                </button>
              ))
            : null}
        </div>
      ) : null}
    </div>
  )
}
