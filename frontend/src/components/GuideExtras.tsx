/* The things added after the guide was written.
 *
 * A guide that stops at "invoice the vendor" describes the system as it was
 * six weeks ago, and the gap is invisible to the person reading it — they
 * conclude the feature does not exist and go back to doing it on paper. These
 * are the pieces that arrived later and are easiest to miss, each one said in
 * the terms of the problem it solves rather than the screen it lives on.
 */

import {
  BadgeIndianRupee,
  FileSpreadsheet,
  HandCoins,
  PackageX,
  Scale,
  Send,
  Sofa,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Card } from '@/components/ui'

interface Extra {
  icon: ReactNode
  title: string
  to?: string
  who: string
  body: string
  todo?: string[]
}

const EXTRAS: Extra[] = [
  {
    icon: <FileSpreadsheet className="size-4" />,
    title: 'The vendor’s own Excel, dropped straight in',
    to: '/day-sheet',
    who: 'Warehouse',
    body: 'Most vendors send the day’s bills as a spreadsheet. Drop that file on the Day sheet and it finds the columns itself — bill number, customer, boxes — whatever they happen to be called and wherever they start. Nothing is created until you have looked at what it read.',
  },
  {
    icon: <Send className="size-4" />,
    title: 'Ask a customer for their own address',
    to: '/consignees',
    who: 'Warehouse',
    body: 'A customer entered while the morning’s bills are being typed is a name, a mobile and a town, which is all anybody has time for. The door, the landmark and the pin belong to the person who lives there.',
    todo: [
      'On the customer, press “Ask them for their address”.',
      'Copy the message, or open WhatsApp with it already written.',
      'They get one screen: a map to drop a pin on, their address, a landmark, and who the driver should ask for.',
      'A pin they drop is marked verified, because they were standing at the door. One set from the office counts as approximate.',
    ],
  },
  {
    icon: <Sofa className="size-4" />,
    title: 'The unloading charge sheet',
    to: '/invoices',
    who: 'Driver, then Accounts',
    body: 'The small printed form the dealer signs, built from what the driver counted at the door rather than from what the bill said was sent. It prints behind the invoice, one page per delivery point, so the unloading line on the bill has its working attached instead of being a number the vendor has to take on trust.',
    todo: [
      'The driver ticks the articles he carried in, and the floor, on his phone.',
      'The sheet prices each one and totals the point.',
      'When the invoice is generated, the sheets for exactly the freights you ticked come with it.',
      'Anything carried that has no rate on file is called out in red before the bill goes out — it was billed as nothing.',
    ],
  },
  {
    icon: <Scale className="size-4" />,
    title: 'What a freight earned and what it cost',
    to: '/freights',
    who: 'Office',
    body: 'At the bottom of every freight: what the vendor pays on the left, what the driver or vehicle owner is paid on the right, and the gap underneath with the rupees per kilometre. Every line carries its own working — “40 km over 60 × ₹17.00”, not just ₹680 — and a line of zero stays with its reason, because “1 stop, within the 3 included” is what explains why a one-stop run bills the same as a three-stop one.',
  },
  {
    icon: <BadgeIndianRupee className="size-4" />,
    title: 'A fixed fare for one run',
    to: '/freights',
    who: 'Office',
    body: 'Per-kilometre pay is right for the ordinary run and wrong for the ones people ring about — a Kasaragod round trip settled at twelve hundred before the lorry leaves. On the freight’s leg, press “Set a fixed fare”.',
    todo: [
      'An agreed figure replaces the distance calculation rather than adding to it.',
      'There is a second box for the unloading, for vendors who price it by neither article nor share.',
      'Leave a box empty to go back to his usual rate. Zero is a different answer and is kept apart from empty.',
      'Write why. An amount nobody can explain six weeks later is the one that gets queried.',
      'A run already covered by a settlement cannot be changed — somebody has been paid against those lines.',
    ],
  },
  {
    icon: <HandCoins className="size-4" />,
    title: 'Advances, and getting them back',
    to: '/advances',
    who: 'Warehouse or Accounts',
    body: 'Cash handed to a driver or a vehicle owner before the work is settled. It is recorded against them and comes off their next settlement automatically, so nobody has to remember it — on a rented lorry the advance is recovered from whoever the hire is paid to.',
  },
  {
    icon: <PackageX className="size-4" />,
    title: 'Returns, scanned at the godown',
    to: '/returns',
    who: 'Driver, then Warehouse',
    body: 'Cartons that came back. The driver scans them before the lorry is unloaded, which is the only moment anybody can say with certainty what returned and what did not. The reason is recorded against each one, so “refused at the door” and “nobody there” stay different facts when the vendor asks.',
  },
]

export function GuideExtras() {
  return (
    <section>
      <h2 className="eyebrow mb-3">Worth knowing, and easy to miss</h2>
      <div className="space-y-3">
        {EXTRAS.map((e) => (
          <Card key={e.title} className="p-5">
            <div className="flex flex-wrap items-start gap-4">
              <span
                className="grid size-9 shrink-0 place-items-center rounded-[10px]"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
              >
                {e.icon}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[15px] font-semibold">{e.title}</h3>
                  <span
                    className="rounded-full px-2 py-0.5 text-[10.5px] font-medium"
                    style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
                  >
                    {e.who}
                  </span>
                </div>

                <p
                  className="mt-1.5 text-[13px] leading-relaxed"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {e.body}
                </p>

                {e.todo ? (
                  <ol className="mt-2.5 space-y-1">
                    {e.todo.map((t, i) => (
                      <li key={t} className="flex gap-2.5 text-[13px] leading-relaxed">
                        <span
                          className="tnum mt-[2px] shrink-0 text-[11px]"
                          style={{ color: 'var(--text-faint)' }}
                        >
                          {i + 1}.
                        </span>
                        <span>{t}</span>
                      </li>
                    ))}
                  </ol>
                ) : null}

                {e.to ? (
                  <Link
                    to={e.to}
                    className="mt-2.5 inline-block text-[12.5px] no-underline"
                    style={{ color: 'var(--accent)' }}
                  >
                    Open it &rarr;
                  </Link>
                ) : null}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </section>
  )
}
