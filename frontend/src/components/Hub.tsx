import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/lib/api'
import type { Hub as HubDef } from '@/lib/hubs'
import { stagger } from '@/lib/motion'

/* The way into one part of the business.
 *
 * Eight things are in the rail and everything else lives inside them, as
 * tiles. A tile can say what is in it — eleven vehicles, four enquiries
 * nobody has rung — which a line in a menu cannot, and that is the difference
 * between a list somebody reads and a list somebody scans.
 *
 * The hub's own screen is underneath the tiles, not behind another click.
 * Freights opens onto the tiles AND the list of trips, because the list is
 * what somebody came for forty times a day and making them choose it from a
 * menu first would be slower than the rail it replaced.
 */

export function Hub({
  hub,
  children,
}: {
  hub: HubDef
  /** The hub's own screen, shown beneath its tiles. */
  children?: ReactNode
}) {
  const counts = useQuery({
    queryKey: ['/hub-counts'],
    queryFn: async () => (await api.get<Record<string, number>>('/hub-counts')).data,
    // The numbers are decoration on a menu, not figures anybody acts on, so
    // they can be a few minutes old. The screen behind each tile is the
    // authority.
    staleTime: 3 * 60_000,
  })

  if (!hub.children.length) return <>{children}</>

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {hub.children.map((child, i) => {
          const Icon = child.icon
          const n = child.count ? counts.data?.[child.count] : undefined

          return (
            <Link
              key={child.to}
              to={child.to}
              style={stagger(i, 40, 220)}
              // A tile is a target, not a line of text: big enough to hit with
              // a thumb, and obviously pressable to somebody who has not used
              // software like this before.
              className="tx-in hoverable group flex items-start gap-3 rounded-[var(--radius-card)] border p-4 no-underline"
            >
              <span
                className="grid size-10 shrink-0 place-items-center rounded-[11px]"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
              >
                <Icon className="size-5" />
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="truncate text-[14.5px] font-semibold">{child.label}</span>
                  {n !== undefined ? (
                    <span
                      className="tnum shrink-0 text-[12.5px]"
                      style={{ color: n > 0 ? 'var(--accent)' : 'var(--text-faint)' }}
                    >
                      {n}
                    </span>
                  ) : null}
                </span>
                <span
                  className="mt-0.5 block text-[12.5px] leading-relaxed"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {child.blurb}
                </span>
              </span>

              <ArrowRight
                className="mt-1 size-4 shrink-0 transition-transform group-hover:translate-x-0.5"
                style={{ color: 'var(--text-faint)' }}
                aria-hidden
              />
            </Link>
          )
        })}
      </div>

      {children ? (
        <>
          <div className="groove" />
          {children}
        </>
      ) : null}
    </div>
  )
}
