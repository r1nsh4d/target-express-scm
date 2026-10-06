import {
  Building2,
  Command,
  Check,
  Package,
  ReceiptIndianRupee,
  Route,
  Smartphone,
  Truck,
  UserRound,
  Users,
  Warehouse,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { openCommandPalette } from '@/components/CommandPalette'
import { WorkflowChart } from '@/components/WorkflowChart'
import { Card, PageHeader } from '@/components/ui'

/* The guide is a page rather than a document because the order matters: a
   freight cannot exist until a vendor, a division, a warehouse, a rate card,
   customers, a vehicle and a driver all do. Walking it once makes the
   dependencies obvious. */

interface Step {
  n: string
  icon: ReactNode
  title: string
  to?: string
  why: string
  todo: string[]
  watch?: string
}

const SETUP: Step[] = [
  {
    n: '01',
    icon: <Package className="size-4" />,
    title: 'Goods categories',
    to: '/categories',
    why: 'A category decides whether unloading is billed. Spare parts are not charged for unloading; furniture is, per article plus a charge for every floor climbed.',
    todo: ['Add “Spare Parts”, “Furniture” and anything else the vendor ships.'],
  },
  {
    n: '02',
    icon: <Building2 className="size-4" />,
    title: 'Vendor, then its divisions',
    to: '/vendors',
    why: 'Rates belong to a division, not a vendor. Godrej OCP and Godrej Appliance Spare use the same lorries but price differently, so each is its own division.',
    todo: [
      'Create the vendor — name, GSTIN, a contact.',
      'Select it, then add one division per business line, pointing each at a goods category.',
    ],
    watch: 'Getting divisions wrong here means every invoice is wrong later. Split anything that prices differently.',
  },
  {
    n: '03',
    icon: <Warehouse className="size-4" />,
    title: 'Warehouses',
    to: '/vendors',
    why: 'A freight leaves a warehouse and is finished when the vehicle is back at that same warehouse. That return is what closes the kilometre loop.',
    todo: ['With the vendor selected, add each godown you load from.'],
  },
  {
    n: '04',
    icon: <ReceiptIndianRupee className="size-4" />,
    title: 'Rate cards',
    to: '/rate-cards',
    why: 'What the vendor is charged: a base freight charge covering some kilometres and some points, then a rate for each extra kilometre and each extra point.',
    todo: [
      'Pick the division and an effective-from date.',
      'Set the base amount, included kilometres and rate per extra kilometre.',
      'Set the point slab: how many points the base covers, and the rate beyond.',
    ],
    watch: 'Rates are never edited. To change one, add a new card dated from the change — older freights keep pricing on the old card, so past invoices re-print unchanged.',
  },
  {
    n: '05',
    icon: <Truck className="size-4" />,
    title: 'Vehicles',
    to: '/vehicles',
    why: 'Ownership decides who gets paid. An owned vehicle pays its driver; a rented one pays the vehicle’s owner, who settles with his own driver.',
    todo: [
      'Add the vehicle type first if it is new, and the owner if the vehicle is rented.',
      'Add the vehicle with its current odometer reading and its LR book number.',
    ],
    watch: 'The opening odometer matters — the continuity check compares each freight’s closing reading against the next one’s opening reading.',
  },
  {
    n: '06',
    icon: <UserRound className="size-4" />,
    title: 'Drivers',
    to: '/drivers',
    why: 'Drivers are paid on distance, plus the unloading cash they hand to labourers at each point.',
    todo: [
      'Add the driver with his phone number — that is also his login.',
      'Set the rate per kilometre and his unloading share.',
      'Leave the password blank to use the last six digits of his phone.',
    ],
    watch: 'A driver who comes with a rented vehicle earns nothing from Target Express for driving, so his earnings screen is switched off automatically.',
  },
  {
    n: '07',
    icon: <Users className="size-4" />,
    title: 'Customers',
    to: '/consignees',
    why: 'The delivery points. A mobile number is required — without it the customer gets no tracking link.',
    todo: [
      'Add each customer or distribution centre.',
      'Drop a pin on the map, or paste coordinates straight out of Google Maps.',
    ],
    watch: 'A pin the customer corrects from their tracking link is saved back here, so the next delivery to that address is already right.',
  },
]

const RUN: Step[] = [
  {
    n: '08',
    icon: <Route className="size-4" />,
    title: 'Build the freight',
    to: '/freights',
    why: 'A freight is one run: out from a warehouse, round its points, back again.',
    todo: [
      'Pick the vendor division, the origin warehouse and the date.',
      'Add the points in delivery order, with the floor and planned box count for each.',
      'Assign the vehicle and driver.',
    ],
  },
  {
    n: '09',
    icon: <Package className="size-4" />,
    title: 'Load and dispatch',
    to: '/freights',
    why: 'The count into the vehicle is the number the delivery count is checked against. This is the whole missing-box story.',
    todo: [
      'Confirm the box count for each point as it is loaded.',
      'Press Dispatch — the LR number is issued from the vehicle’s book and a tracking link opens for every customer.',
    ],
  },
  {
    n: '10',
    icon: <Smartphone className="size-4" />,
    title: 'The driver runs it',
    why: 'From his phone, at /driver. He sees only what he needs, one point at a time.',
    todo: [
      'Enters the opening odometer before leaving.',
      'Navigates to each point — one stop at a time, or the whole route in Google Maps.',
      'Records boxes handed over, the receiver and the unloading paid.',
      'Enters the closing odometer on return, which completes the freight.',
    ],
  },
  {
    n: '11',
    icon: <ReceiptIndianRupee className="size-4" />,
    title: 'Bill and settle',
    why: 'The completed freight prices itself on the rate card in force on its date, and produces what the driver or vehicle owner is owed.',
    todo: [
      'Check the freight’s billing panel — every line shows the working behind it.',
      'Raise the vendor invoice for a period, and settle the driver or owner.',
    ],
  },
]

export default function GuidePage() {
  return (
    <div className="space-y-7">
      <PageHeader description="The order matters: a freight cannot exist until the vendor, its rates, a vehicle, a driver and the customers all do. Walk it once and the rest is repetition." />

      {/* First, because it is the thing that saves the most time and the thing
          nobody discovers on their own. */}
      <Card className="lit p-5">
        <div className="flex flex-wrap items-start gap-4">
          <span
            className="grid size-9 shrink-0 place-items-center rounded-[10px]"
            style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
          >
            <Command className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px] font-semibold">
              You never have to hunt through the menu
            </h2>
            <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Press{' '}
              <kbd
                className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                style={{ background: 'var(--surface-hover)' }}
              >
                Ctrl
              </kbd>{' '}
              +{' '}
              <kbd
                className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                style={{ background: 'var(--surface-hover)' }}
              >
                K
              </kbd>{' '}
              anywhere in the application and start typing what you want. “New freight”, “Godrej”,
              “floor”, “diesel” — it finds the screen and takes you there. You do not need to
              remember which menu anything lives under.
            </p>
            <button
              onClick={openCommandPalette}
              className="mt-3 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors"
              style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
            >
              Try it now
            </button>
          </div>
        </div>
      </Card>

      {/* The chart first. The commonest question on day one is "when does a
          consignment get created, and what has to exist before it can" — and a
          numbered list cannot answer that, because the real shape is a one-time
          setup feeding a loop. */}
      <Card className="overflow-hidden p-5">
        <h2 className="text-[15px] font-semibold">The whole cycle</h2>
        <p className="mt-1 max-w-[72ch] text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          Everything on the top row is done once per vendor and then left alone. Everything on
          the bottom two rows happens on every run.
        </p>
        {/* No forced width and no horizontal scroll: the chart wraps onto as
            many lines as the column gives it. */}
        <div className="mt-4">
          <WorkflowChart />
        </div>
      </Card>

      {/* Two questions that come up constantly and are not obvious from the
          step list, because both sit between other steps. */}
      <Card className="p-5">
        <h2 className="text-[15px] font-semibold">When is a consignment created?</h2>
        <div className="mt-3 space-y-3 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          <p>
            <span className="font-medium" style={{ color: 'var(--text)' }}>
              After the freight exists, and against one of its points.
            </span>{' '}
            A consignment is one vendor bill going to one customer. It cannot be created
            before the freight, because it has to attach to a delivery point — and the points
            only exist once the freight does.
          </p>
          <p>The order, in full:</p>
          <ol className="ml-4 list-decimal space-y-1.5">
            <li>
              Build the freight with its points, in delivery order.{' '}
              <Link to="/freights" style={{ color: 'var(--accent)' }}>Freights</Link>
            </li>
            <li>
              Open the freight, find the point, and press <strong>Bills</strong>. That is where
              a consignment is attached to that stop.
            </li>
            <li>
              Enter the vendor&rsquo;s bill number, its date, and how many boxes are on it.
              The boxes are created automatically — one row per carton, each with its own code.
            </li>
            <li>
              Repeat for every bill going to that point. One point can carry several bills, and
              several customers&rsquo; goods, which is why the bill number is on every label.
            </li>
          </ol>
          <p>
            A freight with no consignments can still be dispatched — the driver carries a
            counted number of boxes. But nothing can be labelled or scanned until the bills are
            in, because a label is printed per box and the boxes come from the bill.
          </p>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-[15px] font-semibold">How to print the sorting labels</h2>
        <div className="mt-3 space-y-3 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          <ol className="ml-4 list-decimal space-y-1.5">
            <li>
              The freight must have its points, and each point must have its bills attached —
              see above. Labels are generated from the boxes, and boxes come from the bills.
            </li>
            <li>
              Go to{' '}
              <Link to="/labels" style={{ color: 'var(--accent)' }}>Sorting &amp; labels</Link>{' '}
              and pick the freight.
            </li>
            <li>
              You will see how many boxes go to each point, in delivery order. Check that
              against what is on the floor before printing.
            </li>
            <li>
              Press <strong>Print</strong>. Stickers come out three to a row and a label is never
              split across a page.
            </li>
            <li>
              Paste one on every carton. The big number and the colour band are the point; the
              loaders sort by those long before anyone reads a code.
            </li>
          </ol>
          <p>
            Each sticker carries a <strong>QR code</strong>. At the delivery point the driver
            opens the stop and presses <strong>Scan boxes</strong> — if a carton belongs to a
            different customer, the phone says so before it is handed over.
          </p>
          <p style={{ color: 'var(--text-faint)' }}>
            Nothing is forced. Some vendors&rsquo; cartons cannot take a sticker, so a point can
            always be delivered with a typed count instead.
          </p>
        </div>
      </Card>

      <Section title="Set up, once per vendor" steps={SETUP} />
      <Section title="Every working day" steps={RUN} />

      <Card className="p-6">
        <h2 className="text-[15px] font-semibold">Words used here</h2>
        <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {[
            ['Freight', 'One delivery run. Out from a warehouse, round its points, back to the same warehouse.'],
            ['Point', 'One stop on a freight — a customer or a distribution centre.'],
            ['Consignment', 'One vendor bill, for one point, covering a number of boxes.'],
            ['LR number', 'The consignment note. Issued from the vehicle’s own book when the freight is dispatched.'],
            ['Division', 'A vendor’s business line. Rates attach here, not to the vendor.'],
            ['Leg', 'One vehicle-and-driver stretch of a freight. A breakdown makes a second leg.'],
            ['Enquiry', 'A business that filled in the form on the website asking to work with us. They appear under Enquiries within seconds.'],
            ['Tracking link', 'What a customer uses to watch their own delivery. Sent on dispatch, and findable again from the website with the LR number and their phone.'],
          ].map(([term, meaning]) => (
            <div key={term}>
              <dt className="text-[13px] font-medium">{term}</dt>
              <dd className="mt-1 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                {meaning}
              </dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  )
}

function Section({ title, steps }: { title: string; steps: Step[] }) {
  return (
    <section>
      <h2 className="eyebrow mb-3">{title}</h2>
      <div className="space-y-3">
        {steps.map((s) => (
          <Card key={s.n} className="p-5">
            <div className="flex flex-wrap items-start gap-4">
              <span
                className="tnum grid size-9 shrink-0 place-items-center rounded-[10px] text-[12px] font-semibold"
                style={{ background: 'var(--rail)', color: 'var(--rail-text)' }}
              >
                {s.n}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[15px] font-semibold">{s.title}</h3>
                  {s.to ? (
                    <Link
                      to={s.to}
                      className="text-[12px] underline underline-offset-2"
                      style={{ color: 'var(--info)' }}
                    >
                      Open
                    </Link>
                  ) : null}
                </div>

                <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  {s.why}
                </p>

                <ul className="mt-3 space-y-1.5">
                  {s.todo.map((t) => (
                    <li key={t} className="flex gap-2.5 text-[13px] leading-relaxed">
                      <Check className="mt-[3px] size-3.5 shrink-0" style={{ color: 'var(--success)' }} />
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>

                {s.watch ? (
                  <p
                    className="mt-3 rounded-[var(--radius-control)] px-3.5 py-2.5 text-[12.5px] leading-relaxed"
                    style={{ background: 'var(--bg)', color: 'var(--text-muted)', boxShadow: 'var(--neu-inset)' }}
                  >
                    <span className="font-medium" style={{ color: 'var(--text)' }}>
                      Worth knowing.{' '}
                    </span>
                    {s.watch}
                  </p>
                ) : null}
              </div>

              <span className="mt-1 hidden shrink-0 sm:block" style={{ color: 'var(--text-faint)' }}>
                {s.icon}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </section>
  )
}
