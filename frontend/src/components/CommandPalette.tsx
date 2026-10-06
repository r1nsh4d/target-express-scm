/* Ctrl+K — go anywhere, do anything, by typing.
 *
 * This is the single feature that makes the product learnable without training.
 * A warehouse admin who cannot remember which menu "unloading rates" lives under
 * types "floor" and gets there. Nobody has to memorise the information
 * architecture, which means the architecture can be as deep as the business
 * actually is instead of being flattened for the sake of discoverability.
 *
 * Everything it offers is already permitted: it searches the same role-filtered
 * navigation the rail renders, so it can never be a way around a role.
 */

import clsx from 'clsx'
import {
  ArrowRight,
  CornerDownLeft,
  LogOut,
  Moon,
  Plus,
  Search,
  Sun,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/lib/auth'
import { navFor } from '@/lib/nav'
import { setTheme, useTheme } from '@/lib/theme'

/** Open the palette from anywhere — the top bar's search button, an empty
 *  state, a guide step. A custom event rather than a context, so a caller does
 *  not have to sit inside a provider to use it. */
export const PALETTE_EVENT = 'tx:palette'

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(PALETTE_EVENT))
}

interface Command {
  id: string
  label: string
  hint?: string
  icon: ReactNode
  section: string
  keywords: string
  run: () => void
}

/* Subsequence match, the same thing editors do: "unlrt" finds "Unloading
   rates". Scored so that a prefix beats a word-start, which beats a scattered
   match — otherwise short queries rank nonsense first. */
function score(query: string, text: string): number {
  if (!query) return 1
  const q = query.toLowerCase()
  const t = text.toLowerCase()

  if (t.startsWith(q)) return 1000
  const wordStart = t.split(/[\s&/-]+/).some((w) => w.startsWith(q))
  if (wordStart) return 800
  if (t.includes(q)) return 600

  let qi = 0
  let gaps = 0
  let last = -1
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] !== q[qi]) continue
    if (last >= 0) gaps += ti - last - 1
    last = ti
    qi++
  }
  if (qi < q.length) return 0
  return Math.max(1, 400 - gaps)
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const theme = useTheme()

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setCursor(0)
  }, [])

  const go = useCallback(
    (to: string) => {
      close()
      navigate(to)
    },
    [close, navigate],
  )

  const commands = useMemo<Command[]>(() => {
    const pages = navFor(user?.role).map<Command>((item) => ({
      id: `go:${item.to}`,
      label: item.label,
      hint: item.blurb,
      icon: item.icon,
      section: 'Go to',
      keywords: `${item.label} ${item.blurb} ${item.keywords ?? ''}`,
      run: () => go(item.to),
    }))

    /* Creation shortcuts. Each lands on the list screen with ?new, which the
       screen reads to open its own create form — so there is one form, not two
       that can drift apart. */
    const creatable: { to: string; label: string; roles: string[] }[] = [
      { to: '/freights?new=1', label: 'New freight', roles: ['SUPER_ADMIN', 'OPS_ADMIN', 'WAREHOUSE_ADMIN'] },
      { to: '/consignments?new=1', label: 'New consignment', roles: ['SUPER_ADMIN', 'OPS_ADMIN', 'WAREHOUSE_ADMIN'] },
      { to: '/vendors?new=1', label: 'New vendor', roles: ['SUPER_ADMIN', 'OPS_ADMIN'] },
      { to: '/consignees?new=1', label: 'New customer', roles: ['SUPER_ADMIN', 'OPS_ADMIN', 'WAREHOUSE_ADMIN'] },
      { to: '/vehicles?new=1', label: 'New vehicle', roles: ['SUPER_ADMIN', 'OPS_ADMIN'] },
      { to: '/drivers?new=1', label: 'New driver', roles: ['SUPER_ADMIN', 'OPS_ADMIN'] },
      { to: '/invoices?new=1', label: 'New invoice', roles: ['SUPER_ADMIN', 'ACCOUNTS'] },
    ]

    const actions = creatable
      .filter((c) => user && c.roles.includes(user.role))
      .map<Command>((c) => ({
        id: `new:${c.to}`,
        label: c.label,
        icon: <Plus className="size-4 shrink-0" />,
        section: 'Create',
        keywords: `${c.label} add create`,
        run: () => go(c.to),
      }))

    const system: Command[] = [
      {
        id: 'theme',
        label: theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
        icon: theme === 'dark' ? <Sun className="size-4 shrink-0" /> : <Moon className="size-4 shrink-0" />,
        section: 'System',
        keywords: 'theme dark light appearance contrast',
        run: () => {
          setTheme(theme === 'dark' ? 'light' : 'dark')
          close()
        },
      },
      {
        id: 'logout',
        label: 'Sign out',
        icon: <LogOut className="size-4 shrink-0" />,
        section: 'System',
        keywords: 'logout sign out exit leave',
        run: () => {
          close()
          logout()
        },
      },
    ]

    return [...actions, ...pages, ...system]
  }, [user, theme, go, close, logout])

  const results = useMemo(() => {
    if (!query.trim()) return commands
    return commands
      .map((c) => ({ c, s: score(query.trim(), c.keywords) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .map((r) => r.c)
  }, [commands, query])

  /* Open with Ctrl+K / Cmd+K, and with "/" the way search boxes everywhere
     work — but not while the person is typing into a field. */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      const typing =
        !!target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        return
      }
      if (e.key === '/' && !typing && !open) {
        e.preventDefault()
        setOpen(true)
      }
    }
    const onAsk = () => setOpen(true)

    window.addEventListener('keydown', onKey)
    window.addEventListener(PALETTE_EVENT, onAsk)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener(PALETTE_EVENT, onAsk)
    }
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => setCursor(0), [query])

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[data-cursor="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  if (!open) return null

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault()
      close()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (results.length ? (c + 1) % results.length : 0))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (results.length ? (c - 1 + results.length) % results.length : 0))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      results[cursor]?.run()
    }
  }

  let lastSection = ''

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center px-4 pt-[12vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="tx-in-fade absolute inset-0"
        style={{ background: 'rgba(2,4,8,0.72)', backdropFilter: 'blur(6px)' }}
        onClick={close}
      />

      <div
        className="tx-in-scale lit relative w-full max-w-[600px] overflow-hidden"
        style={{
          background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--lift-lg)',
        }}
        onKeyDown={onKeyDown}
      >
        <div
          className="flex items-center gap-3 px-4"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <Search className="size-4 shrink-0" style={{ color: 'var(--accent)' }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for a screen, or type what you want to do…"
            className="h-14 flex-1 bg-transparent text-[14.5px] outline-none placeholder:text-[var(--text-faint)]"
            autoComplete="off"
            spellCheck={false}
            aria-label="Search commands"
          />
          <kbd
            className="hidden rounded px-1.5 py-0.5 text-[10px] font-medium sm:block"
            style={{ background: 'var(--surface-hover)', color: 'var(--text-faint)' }}
          >
            ESC
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
          {results.length === 0 ? (
            <p className="px-3 py-10 text-center text-[13px]" style={{ color: 'var(--text-muted)' }}>
              Nothing matches “{query}”.
            </p>
          ) : (
            results.map((cmd, i) => {
              const header = cmd.section !== lastSection ? cmd.section : null
              lastSection = cmd.section
              const active = i === cursor

              return (
                <div key={cmd.id}>
                  {header ? (
                    <p className="eyebrow px-3 pt-3 pb-1.5">{header}</p>
                  ) : null}
                  <button
                    data-cursor={active}
                    onMouseMove={() => setCursor(i)}
                    onClick={cmd.run}
                    className={clsx(
                      'flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-left',
                      'transition-colors duration-100',
                    )}
                    style={{
                      background: active ? 'var(--accent-dim)' : 'transparent',
                      color: active ? 'var(--text)' : 'var(--text-muted)',
                    }}
                  >
                    <span style={{ color: active ? 'var(--accent)' : 'var(--text-faint)' }}>
                      {cmd.icon}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium">{cmd.label}</span>
                      {cmd.hint ? (
                        <span
                          className="block truncate text-[11.5px]"
                          style={{ color: 'var(--text-faint)' }}
                        >
                          {cmd.hint}
                        </span>
                      ) : null}
                    </span>
                    {active ? (
                      <ArrowRight className="size-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
                    ) : null}
                  </button>
                </div>
              )
            })
          )}
        </div>

        <div
          className="flex items-center gap-4 px-4 py-2.5 text-[11px]"
          style={{ borderTop: '1px solid var(--border)', color: 'var(--text-faint)' }}
        >
          <span className="flex items-center gap-1.5">
            <CornerDownLeft className="size-3" /> open
          </span>
          <span>↑↓ move</span>
          <span className="ml-auto hidden sm:block">
            {results.length} {results.length === 1 ? 'result' : 'results'}
          </span>
        </div>
      </div>
    </div>
  )
}
