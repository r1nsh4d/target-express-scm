import clsx from 'clsx'
import {
  KeyRound,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sun,
  X,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import CommandPalette, { openCommandPalette } from '@/components/CommandPalette'
import { Button, ErrorNote, Field, Input, Logo, Modal } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { ROLE_LABELS, useAuth } from '@/lib/auth'
import type { NavItem } from '@/lib/nav'
import { currentNav, navFor } from '@/lib/nav'
import { toggleTheme, useTheme } from '@/lib/theme'

const COLLAPSE_KEY = 'tx.rail.collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

/* -------------------------------------------------------------------------- */
/* The rail — black in both themes, and sized to never scroll                  */
/* -------------------------------------------------------------------------- */

/* A navigation row that does NOT carry an href.
 *
 * An <a href> makes every browser print the destination in its own status strip
 * at the bottom-left of the window. No site can suppress that — it is a built-in
 * anti-phishing cue. The only way to not show it is to not be a link, so these
 * rows navigate in code instead.
 *
 * What that would normally cost is handled here rather than lost:
 *   role="link" + tabIndex   keyboard focus and screen-reader announcement
 *   Enter / Space            activation
 *   aria-current="page"      the active row, announced
 *   ctrl / cmd / shift click open in a new tab or window
 *   middle click             open in a new tab
 *
 * What is genuinely gone is the right-click menu — "open link in new tab" and
 * "copy link address" are not offered on a non-link. The modifier clicks above
 * cover the common case. */
function RailLink({
  item,
  collapsed,
  active,
  badge = 0,
  onNavigate,
}: {
  item: NavItem
  collapsed: boolean
  active: boolean
  /** Something is waiting here. Zero draws nothing at all. */
  badge?: number
  onNavigate?: () => void
}) {
  const navigate = useNavigate()

  function activate(e: ReactMouseEvent) {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) {
      window.open(item.to, '_blank', 'noopener')
      return
    }
    navigate(item.to)
    onNavigate?.()
  }

  function onKeyDown(e: ReactKeyboardEvent) {
    if (e.key !== 'Enter' && e.key !== ' ') return
    e.preventDefault()
    navigate(item.to)
    onNavigate?.()
  }

  return (
    <span
      role="link"
      tabIndex={0}
      aria-current={active ? 'page' : undefined}
      onClick={activate}
      onAuxClick={(e) => {
        // Middle click. preventDefault stops the autoscroll cursor appearing.
        if (e.button === 1) {
          e.preventDefault()
          activate(e)
        }
      }}
      onKeyDown={onKeyDown}
      // A tooltip is only useful when the label itself is hidden.
      title={collapsed ? item.label : undefined}
      className={clsx(
        'group relative flex cursor-pointer items-center rounded-lg text-[12.5px] leading-4 select-none',
        'transition-[background-color,color] duration-150 outline-none',
        'hover:bg-[var(--rail-hover)] focus-visible:ring-1 focus-visible:ring-[var(--accent)]',
        collapsed ? 'justify-center p-1.5' : 'gap-2.5 px-2.5 py-1',
      )}
      style={
        active
          ? { background: 'var(--rail-active)', color: 'var(--rail-text)', fontWeight: 500 }
          : { color: 'var(--rail-muted)' }
      }
    >
      {/* The icon carries the accent on the active row. One cue, in colour, in
          the place the eye already is — no indicator bar needed. */}
      <span
        className="transition-colors duration-150"
        style={{ color: active ? 'var(--accent)' : 'inherit' }}
      >
        {item.icon}
      </span>
      {collapsed ? null : <span className="truncate">{item.label}</span>}

      {/* On a collapsed rail there is no room for a number, so it becomes a dot
          — still says "something is here", which is the whole job. */}
      {badge > 0 ? (
        collapsed ? (
          <span
            className="absolute top-1 right-1 size-1.5 rounded-full"
            style={{ background: 'var(--accent)' }}
            aria-label={`${badge} waiting`}
          />
        ) : (
          <span
            className="tnum ml-auto rounded-full px-1.5 py-px text-[10.5px] font-semibold"
            style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
          >
            {badge > 99 ? '99+' : badge}
          </span>
        )
      ) : null}
    </span>
  )
}

function Rail({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean
  onNavigate?: () => void
}) {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const visible = navFor(user?.role)

  /* The count of uncalled website enquiries, on the rail so it is visible from
     every screen rather than only the dashboard. It rides on the summary the
     dashboard already fetches, so this costs no extra request — and it is
     refetched every two minutes, because somebody filling in the form on the
     website is waiting for a phone call now, not at the next page load. */
  const summary = useQuery({
    queryKey: ['/dashboard/summary'],
    queryFn: async () => (await api.get<{ new_enquiry_count: number }>('/dashboard/summary')).data,
    refetchInterval: 120_000,
    // A stakeholder cannot open the enquiries screen, so do not badge it.
    enabled: !!user && ['SUPER_ADMIN', 'OPS_ADMIN'].includes(user.role),
  })
  const badges: Record<string, number> = {
    '/enquiries': summary.data?.new_enquiry_count ?? 0,
  }
  const groups = [...new Set(visible.map((i) => i.group))]
  const active = currentNav(pathname)

  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--rail)' }}>
      <div
        className={clsx(
          'flex h-[54px] shrink-0 items-center border-b',
          collapsed ? 'justify-center px-2' : 'px-4',
        )}
        style={{ borderColor: 'var(--rail-border)' }}
      >
        <Logo onDark markOnly={collapsed} size={28} />
      </div>

      {/* Sized so the longest menu — eighteen rows for a super admin — fits a
          560px viewport, which is a 1366×768 laptop with the taskbar and the
          browser's own chrome taken off. overflow-y-auto is the safety net for
          anything shorter, not the normal case. */}
      <nav className={clsx('flex-1 overflow-y-auto py-2', collapsed ? 'px-2' : 'px-2.5')}>
        {groups.map((g, gi) => (
          <div key={g}>
            {gi > 0 ? (
              <div className="my-1 h-px" style={{ background: 'var(--rail-border)' }} aria-hidden />
            ) : null}

            {visible
              .filter((i) => i.group === g)
              .map((item) => (
                <RailLink
                  key={item.to}
                  item={item}
                  collapsed={collapsed}
                  active={active?.to === item.to}
                  badge={badges[item.to] ?? 0}
                  onNavigate={onNavigate}
                />
              ))}
          </div>
        ))}
      </nav>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Account menu — theme, password and sign out, top right                     */
/* -------------------------------------------------------------------------- */

function AccountMenu() {
  const { user, logout } = useAuth()
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const [changing, setChanging] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="flex items-center gap-2" ref={ref}>
      <button
        onClick={toggleTheme}
        className="grid size-9 place-items-center rounded-full transition-[box-shadow] active:[box-shadow:var(--neu-pressed)]"
        style={{
          background: 'var(--surface)',
          color: 'var(--text-muted)',
          boxShadow: 'var(--neu-raised-sm)',
        }}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>

      <div className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 rounded-full py-1 pr-3 pl-1 transition-[box-shadow] active:[box-shadow:var(--neu-pressed)]"
          style={{ background: 'var(--surface)', boxShadow: 'var(--neu-raised-sm)' }}
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <span
            className="grid size-7 place-items-center rounded-full text-[11px] font-semibold"
            style={{ background: 'var(--rail)', color: 'var(--rail-text)' }}
          >
            {user?.full_name?.[0]?.toUpperCase() ?? '?'}
          </span>
          <span className="hidden max-w-[7rem] truncate text-[13px] font-medium sm:block">
            {user?.full_name?.split(' ')[0]}
          </span>
        </button>

        {open ? (
          <div
            role="menu"
            className="absolute right-0 z-40 mt-2 w-60 overflow-hidden p-1.5"
            /* Solid, like the modal and for the same reason: this floats over
               page content, and the glass fill would let it read through. */
            style={{
              background: 'var(--surface-solid)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--lift-lg)',
            }}
          >
            <div className="px-3 py-2.5">
              <p className="truncate text-[13px] font-medium">{user?.full_name}</p>
              <p className="mt-0.5 truncate text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                {user ? ROLE_LABELS[user.role] : ''} · {user?.phone}
              </p>
            </div>
            <div className="groove my-1" />
            <button
              onClick={() => {
                setOpen(false)
                setChanging(true)
              }}
              className="flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--surface-hover)]"
              style={{ color: 'var(--text)' }}
              role="menuitem"
            >
              <KeyRound className="size-4" />
              Change password
            </button>
            <button
              onClick={() => {
                setOpen(false)
                logout()
              }}
              className="flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--surface-hover)]"
              style={{ color: 'var(--danger)' }}
              role="menuitem"
            >
              <LogOut className="size-4" />
              Sign out
            </button>
          </div>
        ) : null}
      </div>

      <ChangePasswordModal open={changing} onClose={() => setChanging(false)} />
    </div>
  )
}

/** Seeded accounts ship with a known password, so this has to be reachable
 *  without an admin. */
function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError('The two new passwords do not match')
      return
    }
    setBusy(true)
    try {
      await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      setDone(true)
      setCurrent('')
      setNext('')
      setConfirm('')
      setTimeout(() => {
        setDone(false)
        onClose()
      }, 1400)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not change the password'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Change password">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Current password">
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </Field>
        <Field label="New password" hint="At least 6 characters">
          <Input
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </Field>
        <Field label="Repeat the new password">
          <Input
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </Field>

        <ErrorNote>{error}</ErrorNote>
        {done ? (
          <p className="text-[13px]" style={{ color: 'var(--success)' }}>
            Password changed.
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Change password
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */

export default function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const location = useLocation()
  const nav = currentNav(location.pathname)

  useEffect(() => setMobileOpen(false), [location.pathname])

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0')
    } catch {
      /* private browsing - the preference simply will not persist */
    }
  }, [collapsed])

  /* One number drives both the rail's width and the content column's offset, so
     they cannot drift apart. `.tx-rail` / `.tx-main` in index.css read it, which
     keeps the breakpoint in CSS instead of a JS media query. */
  const railWidth = collapsed ? 64 : 236

  return (
    <div
      className="relative min-h-dvh overflow-x-clip"
      style={{ ['--tx-rail-w' as string]: `${railWidth}px` }}
    >
      <aside className="tx-rail fixed inset-y-0 left-0 z-30 hidden lg:block">
        <Rail collapsed={collapsed} />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 backdrop-blur-sm"
            style={{ background: 'rgba(0,0,0,0.55)' }}
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[264px]">
            <button
              onClick={() => setMobileOpen(false)}
              className="absolute top-4 right-3 z-10 rounded-lg p-1.5"
              style={{ color: 'var(--rail-muted)' }}
              aria-label="Close menu"
            >
              <X className="size-4" />
            </button>
            <Rail collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="tx-main relative min-w-0">
        <header
          className="sticky top-0 z-20 flex h-[54px] items-center gap-2 px-4 backdrop-blur-md sm:px-6 lg:px-8"
          style={{ background: 'color-mix(in oklab, var(--bg) 86%, transparent)' }}
        >
          <button
            onClick={() => setMobileOpen(true)}
            className="-ml-1 rounded-lg p-2 lg:hidden"
            style={{ color: 'var(--text-muted)' }}
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>

          {/* Collapse the rail. The choice is remembered, because someone who
              works on a 13" laptop wants it collapsed every day, not once. */}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="-ml-1 hidden rounded-lg p-2 transition-colors hover:bg-[var(--surface-hover)] lg:block"
            style={{ color: 'var(--text-muted)' }}
            aria-label={collapsed ? 'Show the menu' : 'Hide the menu'}
            title={collapsed ? 'Show the menu' : 'Hide the menu'}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-[18px]" />
            ) : (
              <PanelLeftClose className="size-[18px]" />
            )}
          </button>

          {/* The page name and what it is for. This is where the old per-item
              hover hints went — visible for the screen you are on, rather than
              only for whichever item the mouse happens to be over. */}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] font-semibold">
              {nav?.label ?? 'Target Express'}
            </p>
            {nav?.blurb ? (
              <p className="truncate text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                {nav.blurb}
              </p>
            ) : null}
          </div>

          {/* The way in to everything. Shown as a real control rather than left
              as a hidden shortcut, because a shortcut nobody knows about is a
              feature nobody has. */}
          <button
            onClick={openCommandPalette}
            className="hidden items-center gap-2 rounded-full py-1.5 pr-2 pl-3 transition-colors md:flex"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-faint)',
            }}
            aria-label="Search and commands"
          >
            <Search className="size-3.5" />
            <span className="text-[12.5px]">Search…</span>
            <kbd
              className="rounded px-1.5 py-0.5 text-[10px] font-medium"
              style={{ background: 'var(--surface-hover)', color: 'var(--text-faint)' }}
            >
              Ctrl K
            </kbd>
          </button>

          <button
            onClick={openCommandPalette}
            className="rounded-lg p-2 md:hidden"
            style={{ color: 'var(--text-muted)' }}
            aria-label="Search"
          >
            <Search className="size-[18px]" />
          </button>

          <AccountMenu />
        </header>

        <div className="px-4 pb-3 sm:px-6 lg:px-8">
          <div className="groove" />
        </div>

        {/* Keyed on the path, so every navigation replays the entrance. The page
            arriving is the feedback that the click worked. */}
        <main
          key={location.pathname}
          className="tx-in mx-auto w-full min-w-0 max-w-[1280px] px-4 pt-2 pb-10 sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>
      </div>

      <CommandPalette />
    </div>
  )
}
