import type { ReactNode } from 'react'

import { Card, EmptyState } from '@/components/ui'
import { stagger } from '@/lib/motion'

/* Records as cards rather than rows.
 *
 * A table is the right shape when the question is "compare these forty on one
 * column" — which is what Reports and Money in are for. It is the wrong shape
 * for a list of eleven lorries, where the question is "tell me about this
 * lorry" and the answer is spread across six narrow columns the eye has to
 * reassemble.
 *
 * It is also the shape that fails worst on a phone and for somebody who has
 * not used software like this before: a row offers no obvious place to press,
 * and a header that has scrolled out of view leaves the values unlabelled.
 *
 * So: one card per record, its name large, its facts labelled where they sit,
 * and the actions on the card rather than in a column of icons at the far
 * right of a horizontal scroll.
 */

export function TileGrid<T>({
  rows,
  rowKey,
  render,
  empty,
  columns = 3,
  onRowClick,
  selected,
}: {
  rows: T[]
  rowKey: (row: T) => string
  render: (row: T) => ReactNode
  empty: ReactNode
  /** Widest breakpoint column count. Two for denser cards, three for simple. */
  columns?: 2 | 3
  /** Makes the whole tile pick the record. The actions on it still win. */
  onRowClick?: (row: T) => void
  selected?: (row: T) => boolean
}) {
  if (!rows.length) return <Card>{empty}</Card>

  return (
    <div className={`grid gap-3 sm:grid-cols-2 ${columns === 3 ? 'xl:grid-cols-3' : ''}`}>
      {rows.map((row, i) => {
        const isSelected = selected?.(row) ?? false

        return (
          <Card
            key={rowKey(row)}
            className="tx-in hoverable p-4"
            style={{
              ...stagger(i, 30, 240),
              ...(isSelected ? { borderColor: 'var(--accent)', boxShadow: 'var(--glow)' } : {}),
              ...(onRowClick ? { cursor: 'pointer' } : {}),
            }}
            onClick={
              onRowClick
                ? (e) => {
                    // A tile carries its own edit and retire buttons. Clicking
                    // one of those must not also select the record behind it.
                    if ((e.target as HTMLElement).closest('button,a,input,select')) return
                    onRowClick(row)
                  }
                : undefined
            }
          >
            {render(row)}
          </Card>
        )
      })}
    </div>
  )
}

/** A labelled fact on a tile. The label sits with the value, so it is still
 *  there when a table header would have scrolled away. */
export function Fact({
  label,
  value,
  tone,
}: {
  label: string
  value: ReactNode
  tone?: 'muted' | 'warning' | 'danger' | 'success'
}) {
  const colour =
    tone === 'warning'
      ? 'var(--warning)'
      : tone === 'danger'
        ? 'var(--danger)'
        : tone === 'success'
          ? 'var(--success)'
          : tone === 'muted'
            ? 'var(--text-muted)'
            : undefined

  return (
    <div>
      <p className="text-[10.5px] tracking-[0.1em] uppercase" style={{ color: 'var(--text-faint)' }}>
        {label}
      </p>
      <p className="mt-0.5 text-[13px] font-medium" style={colour ? { color: colour } : undefined}>
        {value}
      </p>
    </div>
  )
}

/** The head of a tile: a name, something beside it, and the row's actions. */
export function TileHead({
  title,
  sub,
  badge,
  actions,
}: {
  title: ReactNode
  sub?: ReactNode
  badge?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate text-[15px] font-semibold">{title}</h3>
          {badge}
        </div>
        {sub ? (
          <p className="mt-0.5 truncate text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
            {sub}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
    </div>
  )
}

/** The grid of facts under the head. */
export function Facts({ children }: { children: ReactNode }) {
  return <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">{children}</div>
}

export { EmptyState }
