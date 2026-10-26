/* What each kind of login is for.
 *
 * The commonest question after "whose job is this step" is "why can I not see
 * that screen". Both have the same answer and it was nowhere in the guide.
 *
 * Written as what a role is FOR rather than as a list of permissions. Somebody
 * reading this wants to know whether they are holding the right login for the
 * job in front of them; a table of ticks tells them what is switched on, which
 * is a different and much less useful fact.
 *
 * THE MISSING HALF MATTERS AS MUCH AS THE PRESENT HALF. Somebody who knows the
 * earnings are deliberately not on their screen stops hunting for them and
 * asks the right person instead. The reason is always the same — the figure
 * belongs to a different job — and saying so is what stops it reading as
 * distrust.
 */

import { Check, ChevronDown, Monitor, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Card } from '@/components/ui'
import { ROLE_LABELS, useAuth } from '@/lib/auth'
import type { UserRole } from '@/lib/auth'

interface RoleGuide {
  role: UserRole
  what: string
  does: string[]
  /** What is deliberately absent, and why. */
  not: string
  /** Where the day starts. */
  start: { label: string; to: string }
}

const ROLE_GUIDES: RoleGuide[] = [
  {
    role: 'WAREHOUSE_ADMIN',
    what: 'Runs the day. The bills in, the freights out, and the lists both depend on.',
    does: [
      'Enters the day’s vendor bills — fastest through the Day sheet, which does the bills, the boxes, the freight and the stops in one go',
      'Builds the freight, puts the stops in delivery order, attaches each bill to its stop',
      'Prints the stickers, confirms what went on the vehicle, then dispatches',
      'Adds customers, drivers, vehicles and loading crew as they turn up',
      'Sends a new customer a link to fill in their own address and drop their own pin',
      'Scans the returns when the lorry is back',
      'Hands a driver an advance when he asks at the counter',
    ],
    not: 'No rate cards, no invoices, no settlements and no company earnings. This login builds freights; it does not price them, and those figures belong to the people who do.',
    start: { label: 'Day sheet', to: '/day-sheet' },
  },
  {
    role: 'ACCOUNTS',
    what: 'Turns finished work into money, in both directions.',
    does: [
      'Invoices the vendor for completed freights, ticking which ones go on the bill',
      'Prints the invoice with its unloading charge sheets behind it, one per delivery point',
      'Records what the bank actually credited — not the invoice total, because TDS at source makes them differ',
      'Settles drivers and vehicle owners, with any advances recovered against them',
      'Approves or refuses the expenses drivers claimed on the road',
      'Reads the reports',
    ],
    not: 'Cannot build a freight or dispatch one. That is deliberate: whoever decides what a run was worth should not also be the person who recorded what it did.',
    start: { label: 'Vendor invoices', to: '/invoices' },
  },
  {
    role: 'OPS_ADMIN',
    what: 'Everything the warehouse does, plus the terms it runs on.',
    does: [
      'All of the warehouse admin’s work, across every warehouse',
      'Sets the rate cards — what each vendor division is charged for a trip, its kilometres and its points',
      'Sets the unloading rates per article and per floor, on both sides: what the vendor pays and what the driver earns',
      'Adds vendors, their divisions and their godowns',
      'Creates logins and decides what each role may reach',
      'Reads the reports',
    ],
    not: 'No invoices, no money in, no settlements. Setting what a trip is worth and collecting for it are kept in different hands.',
    start: { label: 'Dashboard', to: '/dashboard' },
  },
  {
    role: 'SUPER_ADMIN',
    what: 'Holds every key. One or two people, not a department.',
    does: [
      'Everything above, with nothing withheld',
      'The first set-up, in order: goods categories, vendors, divisions, warehouses, rate cards',
      'Creates the other logins and the roles behind them',
      'Can cancel an issued invoice, and override a freight’s status with a written reason',
    ],
    not: 'Nothing is hidden from this login, which is the reason to have as few of them as the work allows.',
    start: { label: 'Dashboard', to: '/dashboard' },
  },
  {
    role: 'STAKEHOLDER',
    what: 'Reads how the business is doing, and changes nothing.',
    does: [
      'The dashboard and the reports: invoiced, received, outstanding and kept',
      'Margin by month, by vendor division, by driver and by lorry',
      'Which invoices are overdue, and by how long',
      'Every freight and what it did',
    ],
    not: 'Every button that changes something is absent. This login can be handed to an owner or a partner without a second thought.',
    start: { label: 'Reports', to: '/reports' },
  },
  {
    role: 'DRIVER',
    what: 'The phone, on the road. Nothing else in the system exists for this login.',
    does: [
      'Signs in at /driver with his own mobile number',
      'Enters the opening odometer before leaving the godown — the trip will not start without it',
      'Scans the cartons at each stop; one belonging to another customer is refused before it is handed over',
      'Records who received them and a photo, then what he carried in, article by article and to which floor',
      'Records porter cash separately from unloading, because the vendor is reimbursing that rather than paying for our work',
      'Claims tolls and other road expenses with a photo of the receipt',
      'Scans anything coming back before the lorry is unloaded at the godown',
      'Enters the closing odometer on return, which completes the freight',
      'Sees what each run pays him, line by line, and what he has earned this month',
    ],
    not: 'Nothing about rates, other drivers, other customers, or what the vendor is charged. One trip and one stop at a time.',
    start: { label: 'The driver app', to: '/driver' },
  },
  /* The three outside logins.
   *
   * They were built and then left out of the guide, which is the worst of both:
   * the office cannot tell somebody what the login they just made is for.
   *
   * THE DRIVER OF AN OUTSIDE LORRY IS THE ONE WORTH READING TWICE. He holds a
   * plain Driver login with the earnings switched off, and that is not a
   * demotion — Target Express does not pay him, so it has no figure to show
   * him. What he is paid is his owner's arrangement, and the owner reads his
   * own half on the login below. */
  {
    role: 'VEHICLE_OWNER',
    what: 'A man whose lorries Target Express hires. His money, and nothing else.',
    does: [
      'Signs in at /owner with his own mobile number',
      'Sees every run his lorries did and what each one pays him — run by run, not one monthly figure',
      'Reads his settlements and what each was made up of, less any advance recovered',
      'Reads the advances he has drawn and what is left to come off a settlement',
      'Sees his own drivers and which of them has a login',
    ],
    not: 'Nothing about what the vendor was charged. The gap between what Godrej pays and what he is paid is Target Express’s margin, and he cannot create or change anything — ask the office. One owner may have several lorries; he sees all of his and none of anybody else’s.',
    start: { label: 'The owner portal', to: '/owner' },
  },
  {
    role: 'OWNER_DRIVER',
    what: 'One man, one lorry, one login: he owns it and he drives it himself.',
    does: [
      'Signs in at /driver and runs the trip exactly as any driver does',
      'Reads his owner’s earnings, settlements and advances on a tab inside the same app',
      'Draws an advance against what his own lorry has earned',
    ],
    not: 'He is not two logins. Give this to a man who owns the lorry he drives — if he employs somebody else to drive it, that man gets a plain Driver login instead, because anyone holding this one sees the owner’s money.',
    start: { label: 'The driver app', to: '/driver' },
  },
  {
    role: 'VENDOR',
    what: 'A customer’s own login — Godrej, Dost, Ace — into their own work and no one else’s.',
    does: [
      'Signs in at /vendor',
      'Raises a freight themselves instead of ringing it through',
      'Reads the rate card they are on, as agreed and not editable',
      'Reads their freights, the charges on each and the attachments and photos from every point',
      'Reads the invoices raised against them, with the unloading charge sheets behind each one',
    ],
    not: 'Another vendor’s freight does not exist for this login — not refused, not found. Nothing about drivers’ pay, hire or what a run cost Target Express.',
    start: { label: 'The vendor portal', to: '/vendor' },
  },
]

/* Their own card, opened; the rest collapsed.
 *
 * Nine roles down a page is a page nobody reads. Knowing what the other logins
 * are for is useful once and in the way every day after that. */
export function YourRole() {
  const { user } = useAuth()
  const mine = user?.role

  const ordered = [
    ...ROLE_GUIDES.filter((g) => g.role === mine),
    ...ROLE_GUIDES.filter((g) => g.role !== mine),
  ]

  return (
    <section>
      <h2 className="eyebrow mb-3">What each login is for</h2>
      <p className="mb-3 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        A screen missing from your rail is not broken and not an oversight — it belongs to
        somebody else’s job. Yours is open below.
      </p>
      <div className="space-y-3">
        {ordered.map((g) => (
          <RoleCard key={g.role} guide={g} isMine={g.role === mine} />
        ))}
      </div>
    </section>
  )
}

function RoleCard({ guide, isMine }: { guide: RoleGuide; isMine: boolean }) {
  const [open, setOpen] = useState(isMine)

  return (
    <Card
      className="overflow-hidden"
      style={isMine ? { borderColor: 'var(--accent)' } : undefined}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-start gap-4 px-5 py-4 text-left"
      >
        <span
          className="grid size-9 shrink-0 place-items-center rounded-[10px]"
          style={
            isMine
              ? { background: 'var(--accent)', color: '#04121a' }
              : { background: 'var(--bg-elevated)', color: 'var(--text-muted)' }
          }
        >
          {guide.role === 'DRIVER' || guide.role === 'OWNER_DRIVER' ? (
            <Smartphone className="size-4" />
          ) : (
            <Monitor className="size-4" />
          )}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold">{ROLE_LABELS[guide.role]}</span>
            {isMine ? (
              <span
                className="rounded-full px-2 py-0.5 text-[10.5px] font-medium"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
              >
                This is you
              </span>
            ) : null}
          </span>
          <span className="mt-0.5 block text-[13px]" style={{ color: 'var(--text-muted)' }}>
            {guide.what}
          </span>
        </span>

        <ChevronDown
          className="mt-1 size-4 shrink-0 transition-transform"
          style={{ color: 'var(--text-faint)', transform: open ? 'rotate(180deg)' : undefined }}
          aria-hidden
        />
      </button>

      {open ? (
        <div className="border-t px-5 py-4" style={{ borderColor: 'var(--border)' }}>
          <ul className="space-y-1.5">
            {guide.does.map((t) => (
              <li key={t} className="flex gap-2.5 text-[13px] leading-relaxed">
                <Check className="mt-[3px] size-3.5 shrink-0" style={{ color: 'var(--success)' }} />
                <span>{t}</span>
              </li>
            ))}
          </ul>

          <p
            className="mt-3 rounded-[10px] px-3.5 py-2.5 text-[12.5px] leading-relaxed"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
          >
            <span className="font-medium" style={{ color: 'var(--text)' }}>
              What you will not see.{' '}
            </span>
            {guide.not}
          </p>

          <Link
            to={guide.start.to}
            className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] no-underline"
            style={{ color: 'var(--accent)' }}
          >
            Start here: {guide.start.label} &rarr;
          </Link>
        </div>
      ) : null}
    </Card>
  )
}
