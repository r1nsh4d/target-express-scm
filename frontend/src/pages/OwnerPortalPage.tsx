/* A vehicle owner's own screen.
 *
 * For the man who hires lorries to Target Express and does not drive them
 * himself. One page, because he has one question — what has my lorry earned
 * and when am I being paid — and a menu would be four clicks around an answer
 * that fits on a phone.
 *
 * The owner-driver reads the same panels as a tab inside the driver app
 * instead, because at six in the morning he is a man with a lorry to start.
 */

import { LogOut } from 'lucide-react'

import { OwnerPanels } from '@/components/OwnerPanels'
import { BRAND } from '@/lib/brand'
import { useAuth } from '@/lib/auth'

export default function OwnerPortalPage() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-dvh" style={{ background: 'var(--bg)' }}>
      <header
        className="flex items-center justify-between px-4 py-3"
        style={{ background: 'var(--rail)' }}
      >
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-8 place-items-center rounded-[8px] text-[13px] font-bold italic"
            style={{ background: 'var(--rail-text)', color: 'var(--rail)' }}
          >
            TE
          </span>
          <div className="leading-none">
            <p
              className="text-[12.5px] font-semibold italic tracking-[0.08em] uppercase"
              style={{ color: 'var(--rail-text)' }}
            >
              {BRAND.name}
            </p>
            <p
              className="mt-[3px] text-[9px] tracking-[0.2em] uppercase"
              style={{ color: 'var(--rail-faint)' }}
            >
              {BRAND.tagline}
            </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="rounded-lg p-2"
          style={{ color: 'var(--rail-muted)' }}
          aria-label="Sign out"
        >
          <LogOut className="size-4" />
        </button>
      </header>

      <main className="mx-auto max-w-xl px-4 py-5">
        <div className="mb-4">
          <p className="text-[13px]" style={{ color: 'var(--text-faint)' }}>
            Your lorries with Target Express
          </p>
          <h1 className="text-[22px] leading-tight font-semibold">
            {user?.full_name ?? 'Vehicle owner'}
          </h1>
        </div>

        <OwnerPanels />
      </main>
    </div>
  )
}
