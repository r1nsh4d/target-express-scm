/* Finding one row in a list, and sorting what is left.
 *
 * Every list screen grew its own answer to this or none at all: Customers had
 * a search box, Vehicles had type chips, Drivers and Settlements had nothing.
 * So the answer to "where is Basheer" depended on which screen you were on,
 * and on three of them it was "scroll".
 *
 * One component, because the question is the same everywhere — narrow it by
 * typing, narrow it by a property, put it in an order — and three different
 * implementations of that is three different sets of behaviour to learn.
 *
 * THE COUNT IS PART OF THE ANSWER. "11 of 34" tells somebody their filter
 * did something; a list that silently shortens looks like data going
 * missing, and the first thing anybody does is reload.
 *
 * NOTHING IS REMEMBERED ACROSS SCREENS. A filter that persists is a filter
 * somebody forgets they set, and then the record they swear they created is
 * not there. State lives with the screen and dies with it.
 */

import { Search, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'

import { Input, Select } from '@/components/ui'

export interface FilterChoice {
  value: string
  label: string
}

export interface FilterSpec<T> {
  /** Stable key, used for the control's state. */
  key: string
  label: string
  /** The options, usually derived from the rows themselves. */
  choices: FilterChoice[]
  /** Does this row match the chosen value? */
  matches: (row: T, value: string) => boolean
}

export interface SortSpec<T> {
  key: string
  label: string
  compare: (a: T, b: T) => number
}

export interface Filtered<T> {
  rows: T[]
  total: number
  /** The controls, to render above the list. */
  controls: ReactNode
  /** True when something is narrowing the list — for the empty state. */
  narrowed: boolean
  clear: () => void
}

export function useFilters<T>({
  rows,
  search,
  filters = [],
  sorts = [],
  placeholder = 'Search',
}: {
  rows: T[]
  /** The text of a row, for the search box. Joined and lower-cased. */
  search: (row: T) => (string | null | undefined)[]
  filters?: FilterSpec<T>[]
  sorts?: SortSpec<T>[]
  placeholder?: string
}): Filtered<T> {
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<Record<string, string>>({})
  const [sortKey, setSortKey] = useState(sorts[0]?.key ?? '')

  const narrowed = query.trim().length > 0 || Object.values(chosen).some(Boolean)

  const result = useMemo(() => {
    const needle = query.trim().toLowerCase()
    let out = rows

    if (needle) {
      out = out.filter((row) =>
        search(row)
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
          .includes(needle),
      )
    }

    for (const spec of filters) {
      const value = chosen[spec.key]
      if (value) out = out.filter((row) => spec.matches(row, value))
    }

    const sort = sorts.find((s) => s.key === sortKey)
    // Copied before sorting: the array handed in belongs to a query cache,
    // and sorting it in place mutates what every other reader sees.
    if (sort) out = [...out].sort(sort.compare)

    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, query, chosen, sortKey])

  const controls = (
    <div className="flex flex-wrap items-end gap-2">
      <div className="relative min-w-0 flex-1" style={{ maxWidth: '22rem' }}>
        <Search
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
          style={{ color: 'var(--text-faint)' }}
        />
        <Input
          className="pl-10"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={placeholder}
        />
      </div>

      {filters.map((spec) =>
        // A filter with one option filters nothing and is a control that
        // does not work. Drawn only when it has a choice to offer.
        spec.choices.length > 1 ? (
          <Select
            key={spec.key}
            className="w-auto"
            value={chosen[spec.key] ?? ''}
            onChange={(e) => setChosen({ ...chosen, [spec.key]: e.target.value })}
            aria-label={spec.label}
          >
            <option value="">{spec.label}: all</option>
            {spec.choices.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        ) : null,
      )}

      {sorts.length > 1 ? (
        <Select
          className="w-auto"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value)}
          aria-label="Order"
        >
          {sorts.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
      ) : null}

      {/* The count, and the way out. A list that silently shortens looks
          like data going missing. */}
      {narrowed ? (
        <button
          type="button"
          onClick={() => {
            setQuery('')
            setChosen({})
          }}
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px]"
          style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
        >
          <X className="size-3.5" />
          {result.length} of {rows.length} · clear
        </button>
      ) : rows.length ? (
        <span className="tnum self-center text-[12px]" style={{ color: 'var(--text-faint)' }}>
          {rows.length}
        </span>
      ) : null}
    </div>
  )

  return {
    rows: result,
    total: rows.length,
    controls,
    narrowed,
    clear: () => {
      setQuery('')
      setChosen({})
    },
  }
}

/** The distinct values of a field, as filter choices, in the order given. */
export function choicesFrom<T>(
  rows: T[],
  pick: (row: T) => string | null | undefined,
  label?: (value: string) => string,
): FilterChoice[] {
  const seen: string[] = []
  for (const row of rows) {
    const value = pick(row)
    if (value && !seen.includes(value)) seen.push(value)
  }
  seen.sort((a, b) => a.localeCompare(b))
  return seen.map((value) => ({ value, label: label ? label(value) : value }))
}

/** Newest first, oldest first — the two orders every dated list wants. */
export function byDate<T>(pick: (row: T) => string | null | undefined) {
  const at = (row: T) => new Date(pick(row) ?? 0).getTime()
  return {
    newest: (a: T, b: T) => at(b) - at(a),
    oldest: (a: T, b: T) => at(a) - at(b),
  }
}

/** By a name, A to Z. */
export function byName<T>(pick: (row: T) => string) {
  return (a: T, b: T) => pick(a).localeCompare(pick(b))
}
