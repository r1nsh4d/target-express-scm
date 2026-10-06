import clsx from 'clsx'
import { ChevronDown, X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { forwardRef, useEffect, useState } from 'react'

import { stagger } from '@/lib/motion'
import { useTheme } from '@/lib/theme'

/* -------------------------------------------------------------------------- */
/* Button                                                                      */
/* -------------------------------------------------------------------------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
}

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] font-medium ' +
  'transition-[box-shadow,transform,filter] duration-150 select-none whitespace-nowrap ' +
  'disabled:opacity-45 disabled:pointer-events-none disabled:hover:translate-y-0'

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3.5 text-[13px]',
  md: 'h-10 px-4 text-[13.5px]',
  // Driver-facing controls use lg: tapped in a lorry cab, often one-handed.
  lg: 'h-12 px-5 text-[15px]',
}

/** The primary action carries the accent gradient and a soft bloom.
 *
 *  It is the one place the gradient appears inside the workspace. On any screen
 *  there is exactly one primary button, so it reads as "the thing to do here"
 *  rather than as colour for its own sake. Everything else is quiet. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, icon, className, children, disabled, ...rest },
  ref,
) {
  const inline: Record<ButtonVariant, React.CSSProperties> = {
    primary: {
      background: 'var(--accent-grad)',
      color: 'var(--accent-fg)',
      boxShadow: 'var(--glow)',
    },
    secondary: {
      background: 'var(--surface)',
      color: 'var(--text)',
      border: '1px solid var(--border-strong)',
      boxShadow: 'var(--lift-sm)',
    },
    ghost: { color: 'var(--text-muted)' },
    danger: {
      background: 'var(--danger)',
      color: '#fff',
      boxShadow: 'var(--lift-sm)',
    },
  }

  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        BUTTON_BASE,
        BUTTON_SIZES[size],
        variant === 'ghost'
          ? 'hover:bg-[var(--surface-hover)]'
          : 'hover:-translate-y-px hover:brightness-110 active:translate-y-0',
        className,
      )}
      style={inline[variant]}
      {...rest}
    >
      {loading ? <Spinner className="size-4" /> : icon}
      {children}
    </button>
  )
})

/* -------------------------------------------------------------------------- */
/* Input + Field                                                               */
/* -------------------------------------------------------------------------- */

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

/** Pressed into the canvas, so a field reads as somewhere to put something —
 *  and lit while you are in it, so there is never a question about where your
 *  typing is going. The accent means live, and the field you are editing is the
 *  most live thing on the screen. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={clsx(
        'h-11 w-full rounded-[var(--radius-control)] px-3.5 text-[13.5px] outline-none',
        'transition-[border-color,box-shadow] duration-150',
        'placeholder:text-[var(--text-faint)]',
        'focus:border-[var(--accent)] focus:shadow-[var(--glow)]',
        className,
      )}
      style={{
        background: 'var(--bg)',
        color: 'var(--text)',
        border: `1px solid ${invalid ? 'var(--danger)' : 'var(--border)'}`,
        boxShadow: 'var(--well)',
      }}
      {...rest}
    />
  )
})

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-[12px]" style={{ color: 'var(--danger)' }}>
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1.5 block text-[12px]" style={{ color: 'var(--text-faint)' }}>
          {hint}
        </span>
      ) : null}
    </label>
  )
}

/* -------------------------------------------------------------------------- */
/* Surfaces                                                                    */
/* -------------------------------------------------------------------------- */

export function Card({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx('surface', className)} {...rest}>
      {children}
    </div>
  )
}

/* A coloured dot plus a label in normal ink.
   The label carries the meaning, the dot only speeds up scanning a long table.
   Keeping the text in ink rather than the status colour is what lets amber and
   red stay far enough apart in light mode while both remain fully readable. */
export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'
  children: ReactNode
}) {
  const colors: Record<string, string> = {
    neutral: 'var(--text-faint)',
    accent: 'var(--accent)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    danger: 'var(--danger)',
    info: 'var(--info)',
  }
  const color = colors[tone]

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-wide whitespace-nowrap uppercase"
      style={{
        color: 'var(--text-muted)',
        borderColor: 'var(--border-strong)',
        background: 'var(--bg-elevated)',
      }}
    >
      <span
        aria-hidden
        className="size-1.5 shrink-0 rounded-full"
        style={{ background: color }}
      />
      {children}
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/* Select + Textarea                                                          */
/* -------------------------------------------------------------------------- */

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={clsx(
            'h-11 w-full appearance-none rounded-[var(--radius-control)] pr-9 pl-3.5',
            'text-[13.5px] outline-none transition-[border-color,box-shadow] duration-150',
            'focus:border-[var(--accent)] focus:shadow-[var(--glow)]',
            className,
          )}
          style={{
            background: 'var(--bg)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            boxShadow: 'var(--well)',
          }}
          {...rest}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2"
          style={{ color: 'var(--text-faint)' }}
        />
      </div>
    )
  },
)

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...rest }, ref) {
  return (
    <textarea
      ref={ref}
      rows={3}
      className={clsx(
        'w-full rounded-[var(--radius-control)] px-3.5 py-2.5 text-[13.5px] outline-none',
        'transition-[border-color,box-shadow] duration-150',
        'placeholder:text-[var(--text-faint)]',
        'focus:border-[var(--accent)] focus:shadow-[var(--glow)]',
        className,
      )}
      style={{
        background: 'var(--bg)',
        color: 'var(--text)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--well)',
      }}
      {...rest}
    />
  )
})

export function Checkbox({
  label,
  ...rest
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-[13px]">
      <input
        type="checkbox"
        className="size-4 rounded accent-[var(--accent)]"
        style={{ accentColor: 'var(--accent)' }}
        {...rest}
      />
      {label}
    </label>
  )
}

/* -------------------------------------------------------------------------- */
/* Modal                                                                      */
/* -------------------------------------------------------------------------- */

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8">
      <div
        className="tx-in-fade fixed inset-0 backdrop-blur-sm"
        style={{ background: 'rgba(2,4,8,0.68)' }}
        onClick={onClose}
      />
      {/* Scales up from slightly small. A dialog that simply appears reads as a
          page change; one that grows reads as something opening on top. */}
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          'tx-in-scale relative z-10 w-full',
          wide ? 'max-w-3xl' : 'max-w-lg',
        )}
        /* Solid, NOT the glass `.surface`.
           A card can be 2.8% white because it sits on the canvas and the canvas
           is behind it. A dialog floats over a blurred backdrop, so the same
           fill makes the page show straight through the form — which is exactly
           what it did. Anything that floats gets --surface-solid. */
        style={{
          background: 'var(--surface-solid)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--lift-lg)',
        }}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            {description ? (
              <p className="mt-1 text-[13px]" style={{ color: 'var(--text-muted)' }}>
                {description}
              </p>
            ) : null}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 hover:bg-[var(--surface-hover)]"
            style={{ color: 'var(--text-muted)' }}
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="px-5 pb-5">{children}</div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Table                                                                      */
/* -------------------------------------------------------------------------- */

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  align?: 'left' | 'right'
  width?: string
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  empty?: ReactNode
}) {
  if (!rows.length) return <>{empty}</>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr
            className="text-left text-[11px] tracking-wide uppercase"
            style={{ color: 'var(--text-faint)' }}
          >
            {columns.map((c) => (
              <th
                key={c.key}
                className={clsx('px-4 py-2 font-medium', c.align === 'right' && 'text-right')}
                style={{ width: c.width }}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* Rows fade in one after another. The stagger is capped in
              lib/motion, so a long table is fully drawn in a third of a second
              rather than crawling down the screen. */}
          {rows.map((row, i) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={clsx(
                'tx-in-fade border-t transition-colors',
                onRowClick && 'cursor-pointer hover:bg-[var(--surface-hover)]',
              )}
              style={{ borderColor: 'var(--border)', ...stagger(i, 22, 260) }}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx('px-4 py-2.5', c.align === 'right' && 'text-right')}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The page's own header row.
 *
 *  The screen's NAME and one-line purpose live in the top bar, so they are in
 *  the same place on every screen. This carries only what is specific to the
 *  page: a note worth reading, and the actions. */
export function PageHeader({
  title,
  description,
  action,
}: {
  title?: string
  description?: string
  action?: ReactNode
}) {
  if (!title && !description && !action) return null

  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {title ? <h1 className="text-[20px] leading-tight font-semibold">{title}</h1> : null}
        {description ? (
          <p
            className={clsx(
              'max-w-[74ch] text-[13px] leading-relaxed',
              title && 'mt-1.5',
            )}
            style={{ color: 'var(--text-muted)' }}
          >
            {description}
          </p>
        ) : null}
      </div>
      {action ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>
      ) : null}
    </div>
  )
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <div
      role="alert"
      className="rounded-lg border px-3.5 py-2.5 text-[13px]"
      style={{
        color: 'var(--danger)',
        borderColor: 'color-mix(in oklab, var(--danger) 30%, transparent)',
        background: 'color-mix(in oklab, var(--danger) 10%, transparent)',
      }}
    >
      {children}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={clsx('animate-spin', className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/* Brand                                                                       */
/* -------------------------------------------------------------------------- */

/* The client's logo is dropped into public/brand/ (see the README there) and
   picked up without a code change. Until then, the placeholder mark below is
   used. Sources that 404 are remembered so the fallback does not flicker on
   every mount. */
const exhaustedLogos = new Set<string>()

function logoCandidates(theme: string, onDark: boolean, markOnly: boolean): string[] {
  // A collapsed rail is 64px wide. A wordmark squeezed into that is unreadable,
  // so only a square mark is accepted there — and if the client has not supplied
  // one, the square typographic fallback is used rather than a shrunken logo.
  if (markOnly) return ['/brand/mark.svg']

  // On the black rail the white artwork is always right, whatever the theme.
  // Elsewhere, light mode wants the dark artwork, falling through to the other
  // file if only one was supplied.
  if (onDark) return ['/brand/logo.svg']
  return theme === 'light'
    ? ['/brand/logo-dark.svg', '/brand/logo.svg']
    : ['/brand/logo.svg']
}

export function Logo({
  size = 30,
  markOnly = false,
  onDark = false,
}: {
  size?: number
  markOnly?: boolean
  /** Rendering against the black navigation rail or a dark hero. */
  onDark?: boolean
}) {
  const theme = useTheme()
  const candidates = logoCandidates(theme, onDark, markOnly)
  const key = candidates.join('|')

  const [attempt, setAttempt] = useState(0)
  const failed = exhaustedLogos.has(key) || attempt >= candidates.length

  if (!failed) {
    return (
      <img
        src={candidates[attempt]}
        alt="Target Express"
        style={{ height: size }}
        className="w-auto max-w-full object-contain"
        onError={() => {
          const next = attempt + 1
          if (next >= candidates.length) exhaustedLogos.add(key)
          setAttempt(next)
        }}
      />
    )
  }

  /* Typographic fallback until the real files land in public/brand/. Set in
     type rather than drawn, because an approximation of someone's mark is
     worse than no mark at all. */
  const ink = onDark ? 'var(--rail-text)' : 'var(--text)'
  const paper = onDark ? 'var(--rail)' : 'var(--bg)'
  const sub = onDark ? 'var(--rail-faint)' : 'var(--text-faint)'

  const mark = (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-[9px] font-bold italic"
      style={{
        width: size,
        height: size,
        background: ink,
        color: paper,
        fontSize: size * 0.42,
        letterSpacing: '-0.04em',
      }}
    >
      TE
    </span>
  )

  if (markOnly) return mark

  return (
    <span className="inline-flex min-w-0 items-center gap-2.5">
      {mark}
      <span className="flex min-w-0 flex-col leading-none">
        <span
          className="truncate text-[13px] font-semibold italic tracking-[0.055em] uppercase"
          style={{ color: ink }}
        >
          Target Express
        </span>
        {/* The full tagline. Tracking is tighter than the name above it so the
            longer line still fits the rail without truncating. */}
        <span
          className="mt-[3px] truncate text-[8px] tracking-[0.145em] uppercase"
          style={{ color: sub }}
        >
          Logistics to connect world
        </span>
      </span>
    </span>
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  /** For a side panel, where the full-page spacing leaves a hole. */
  compact?: boolean
}) {
  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center px-6 text-center',
        compact ? 'py-8' : 'py-14',
      )}
    >
      {icon ? (
        <div
          /* Normalise the icon size here so every call site does not have to
             remember it. */
          className={clsx(
            'grid place-items-center rounded-full',
            compact ? 'mb-3 size-9 [&_svg]:size-4' : 'mb-4 size-11 [&_svg]:size-[18px]',
          )}
          style={{ background: 'var(--surface-hover)', color: 'var(--text-faint)' }}
        >
          {icon}
        </div>
      ) : null}
      <p className="text-[13.5px] font-medium">{title}</p>
      {description ? (
        <p
          className="mt-1.5 max-w-[42ch] text-[13px] leading-relaxed"
          style={{ color: 'var(--text-muted)' }}
        >
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}
