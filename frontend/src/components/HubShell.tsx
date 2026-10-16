import type { ReactNode } from 'react'

import { Hub } from '@/components/Hub'
import { HUBS } from '@/lib/hubs'

/* Wraps a hub's own screen with its tiles.
 *
 * A thin thing on purpose: the routes stay readable as a list, and a hub with
 * no children renders its page untouched rather than growing an empty strip
 * of tiles above it. */
export function HubShell({ to, children }: { to: string; children: ReactNode }) {
  const hub = HUBS.find((h) => h.to === to)
  if (!hub) return <>{children}</>
  return <Hub hub={hub}>{children}</Hub>
}
