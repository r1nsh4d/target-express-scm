/* The whole cycle, as a chart.
 *
 * The question this answers is the one people actually ask on day one: "when
 * does a consignment get created, and what has to exist before it can?" A list
 * of numbered steps does not answer that, because the real shape is not a list —
 * it is a one-time setup that feeds a loop you run every day.
 *
 * Built from CSS boxes, not SVG.
 *
 * The first version was SVG on a hand-computed grid, and it broke in exactly
 * the ways that approach breaks: the viewBox was 1000 units wide while the six
 * boxes needed 1010, so the last one was cut off; the captions were drawn as
 * single-line <text>, so anything longer than its box ran out over the
 * neighbours; and the connector paths were routed by arithmetic that no longer
 * matched once the boxes moved.
 *
 * None of that is fixable by nudging numbers — it comes from laying out text by
 * hand. Flexbox already wraps text inside a box, already wraps the boxes onto
 * the next line, and already tells you the true width of the row. So the arrows
 * became chevrons between items rather than lines that have to find them.
 */

import { ArrowDown, ChevronRight, RotateCcw } from 'lucide-react'

interface Node {
  label: string
  detail: string
  /** The step this whole chart exists to locate. */
  accent?: boolean
}

const SETUP: Node[] = [
  { label: 'Goods category', detail: 'Spare parts / furniture' },
  { label: 'Vendor', detail: 'Then its divisions' },
  { label: 'Warehouse', detail: 'Where runs start and end' },
  { label: 'Rate card', detail: 'What the vendor is charged' },
  { label: 'Vehicle + driver', detail: 'Owned or hired in' },
  { label: 'Customers', detail: 'The delivery points' },
]

const RUN: Node[] = [
  { label: 'Freight', detail: 'Division, warehouse, date, points' },
  { label: 'Consignment', detail: 'One vendor bill, on one point', accent: true },
  { label: 'Boxes', detail: 'Created under the bill' },
  { label: 'Labels', detail: 'One QR sticker per box' },
  { label: 'Dispatch', detail: 'LR issued, opening odometer' },
  { label: 'Deliver', detail: 'Scan each box at the point' },
  { label: 'Return', detail: 'Closing odometer, freight completes' },
  { label: 'Invoice + settle', detail: 'Vendor billed, driver paid' },
]

function Box({ node }: { node: Node }) {
  return (
    <div
      className="flex min-h-[64px] w-[164px] shrink-0 flex-col justify-center rounded-[10px] px-3 py-2.5"
      style={{
        background: node.accent ? 'var(--accent-dim)' : 'var(--surface)',
        border: `1px solid ${node.accent ? 'var(--accent)' : 'var(--border-strong)'}`,
      }}
    >
      <p
        className="text-[13px] leading-tight font-semibold"
        style={{ color: node.accent ? 'var(--accent)' : 'var(--text)' }}
      >
        {node.label}
      </p>
      {/* Wraps. That is the entire reason this is not SVG. */}
      <p className="mt-1 text-[11px] leading-[1.3]" style={{ color: 'var(--text-faint)' }}>
        {node.detail}
      </p>
    </div>
  )
}

function Row({ nodes }: { nodes: Node[] }) {
  return (
    <div className="flex flex-wrap items-stretch gap-x-1 gap-y-2.5">
      {nodes.map((node, i) => (
        <div key={node.label} className="flex items-stretch">
          <Box node={node} />
          {i < nodes.length - 1 ? (
            <div className="flex w-5 items-center justify-center" aria-hidden>
              <ChevronRight className="size-4" style={{ color: 'var(--text-faint)' }} />
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

export function WorkflowChart() {
  return (
    <div className="space-y-4">
      <section>
        <p className="eyebrow mb-2.5">Set up once per vendor</p>
        <Row nodes={SETUP} />
      </section>

      <div className="flex items-center gap-2 pl-1" aria-hidden>
        <ArrowDown className="size-4" style={{ color: 'var(--text-faint)' }} />
        <span className="h-px flex-1" style={{ background: 'var(--border)' }} />
      </div>

      <section>
        <p className="eyebrow mb-2.5" style={{ color: 'var(--accent)' }}>
          Every run
        </p>
        <Row nodes={RUN} />
      </section>

      <p
        className="flex items-center gap-2 text-[11.5px]"
        style={{ color: 'var(--text-faint)' }}
      >
        <RotateCcw className="size-3.5 shrink-0" aria-hidden />
        The next run starts again at Freight. The setup above is not repeated.
      </p>
    </div>
  )
}
