import { useMutation } from '@tanstack/react-query'
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Mail,
  MapPin,
  MessageCircle,
  PackageSearch,
  Phone,
} from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, apiErrorMessage } from '@/lib/api'
import { useRevealOnScroll } from '@/lib/motion'

/* The public face. Fixed dark editorial styling — it does not follow the app's
   theme, because a landing page is brand, not workspace.

   Display type is Anton, everything else Inter. Greys are neutral rather than
   blue-tinted: a blue-grey caption on a near-black ground reads as a link.

   One container width and one gutter, used by every section, so edges line up
   down the whole page.

   The accent gradient is used exactly three times on this page — the live
   badge, one word of the headline, and the enquiry button. A gradient used a
   fourth time stops meaning anything. */

const PAPER = '#0a0b0d'
const PANEL = '#121317'
const NAVY = '#1c2478'
const INK = '#ffffff'
const MUTED = '#a2a2a8'
const FAINT = '#6e6e76'
const LINE = 'rgba(255,255,255,0.10)'
const CYAN = '#22d3ee'
const GRAD = 'linear-gradient(135deg, #22d3ee 0%, #a78bfa 100%)'

/* ---------------------------------------------------------------------------
   CONTACT DETAILS — REPLACE THESE WITH THE CLIENT'S REAL ONES.

   These are placeholders. I do not know Target Express's actual phone, email or
   office address, and a landing page that publishes a wrong number is worse
   than one that publishes none. Everything the public sees is in this one
   object: change it here and it changes in the nav, the connect section and the
   footer together.
--------------------------------------------------------------------------- */
const CONTACT = {
  phone: '+91 00000 00000',
  phoneHref: 'tel:+910000000000',
  whatsapp: 'https://wa.me/910000000000',
  email: 'ops@targetexpress.in',
  city: 'Kerala, India',
}

const SHELL = 'mx-auto w-full max-w-[1200px] px-6 sm:px-10'

const DISPLAY: React.CSSProperties = {
  fontFamily: "'Anton', 'Inter', sans-serif",
  fontWeight: 400,
  letterSpacing: '-0.005em',
  lineHeight: 0.9,
  textTransform: 'uppercase',
}

export default function LandingPage() {
  // One observer for the page. Anything carrying .tx-reveal below is picked up.
  const ref = useRevealOnScroll<HTMLDivElement>()

  return (
    <div
      ref={ref}
      style={{ background: PAPER, color: INK }}
      className="min-h-dvh overflow-x-clip"
    >
      <Nav />
      <Hero />
      <TrackStrip />
      <Statement />
      <Services />
      <Billing />
      <Connect />
      <Footer />
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function Wordmark({ size = 16 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-3">
      <span
        aria-hidden
        className="grid place-items-center rounded-[7px] font-bold italic"
        style={{
          width: size * 1.7,
          height: size * 1.7,
          background: INK,
          color: PAPER,
          fontSize: size * 0.76,
          letterSpacing: '-0.04em',
        }}
      >
        TE
      </span>
      <span className="flex flex-col leading-none">
        <span className="text-[13px] font-semibold italic tracking-[0.1em]">TARGET EXPRESS</span>
        <span className="mt-1 text-[8.5px] tracking-[0.22em]" style={{ color: FAINT }}>
          LOGISTICS TO CONNECT WORLD
        </span>
      </span>
    </span>
  )
}

function Nav() {
  return (
    <header
      className="sticky top-0 z-40 border-b backdrop-blur-md"
      style={{ borderColor: LINE, background: 'rgba(10,11,13,0.82)' }}
    >
      <div className={`${SHELL} flex h-[72px] items-center justify-between gap-4`}>
        <Wordmark />

        <nav className="flex items-center gap-2 sm:gap-3">
          {/* Tracking before sign-in. Far more people arriving here want to find
              a parcel than want to log in to the console. */}
          <Link
            to="/track"
            className="inline-flex h-10 items-center gap-2 px-4 text-[11.5px] font-semibold tracking-[0.12em] uppercase transition-colors hover:bg-white/5 sm:px-5"
            style={{ border: `1px solid ${LINE}`, color: INK }}
          >
            <PackageSearch className="size-3.5" />
            <span className="hidden sm:inline">Track delivery</span>
            <span className="sm:hidden">Track</span>
          </Link>

          <a
            href="#connect"
            className="hidden h-10 items-center px-5 text-[11.5px] font-semibold tracking-[0.12em] uppercase transition-colors hover:bg-white/5 md:inline-flex"
            style={{ border: `1px solid ${LINE}`, color: INK }}
          >
            Work with us
          </a>

          <Link
            to="/login"
            className="inline-flex h-10 items-center gap-2 px-5 text-[11.5px] font-semibold tracking-[0.12em] uppercase transition-transform hover:scale-[1.03] sm:px-6"
            style={{ background: INK, color: PAPER }}
          >
            Sign in
            <ArrowRight className="size-3.5" />
          </Link>
        </nav>
      </div>
    </header>
  )
}

/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* ------------------------------------------------------------------ *
       * The photograph, with the wordmark set over it.
       *
       * The image is 1199px wide, so it is given a bounded height rather than
       * a viewport-filling one — stretched past its own resolution it goes
       * soft, and a blurry hero is worse than no hero.
       *
       * Two scrims sit between the photo and the type. Neither is decoration:
       * white Anton over a dusk sky fails contrast outright, and the loading
       * bay in this picture runs from a bright horizon on the left to lit
       * doorways on the right, so one flat overlay cannot hold the whole
       * width. The vertical gradient darkens the lower half where the words
       * sit; the horizontal one keeps the left edge readable without crushing
       * the sky.
       * ------------------------------------------------------------------ */}
      {/* A minimum height, so the photograph has room to be a photograph. The
          content is pushed to the bottom of it: sky and loading bay above, the
          wordmark across the darkest band at the foot of the frame. */}
      <div className="relative flex min-h-[520px] flex-col justify-end sm:min-h-[600px] lg:min-h-[680px]">
        <div className="absolute inset-0 overflow-hidden" aria-hidden>
          <img
            src="/hero.jpg"
            alt=""
            /* Above the fold, so it is fetched eagerly and at high priority —
               this is the first thing anyone sees of Target Express.
               object-position favours the lower half: the trucks and the lit
               dock are the subject, the sky is only the backdrop. */
            fetchPriority="high"
            decoding="async"
            className="h-full w-full object-cover"
            style={{ objectPosition: 'center 58%' }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: `linear-gradient(to bottom,
                rgba(10,11,13,0.55) 0%,
                rgba(10,11,13,0.18) 30%,
                rgba(10,11,13,0.72) 72%,
                ${PAPER} 100%)`,
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: `linear-gradient(to right,
                rgba(10,11,13,0.72) 0%,
                rgba(10,11,13,0.26) 48%,
                rgba(10,11,13,0.06) 100%)`,
            }}
          />
        </div>

        <div className={`${SHELL} relative pt-20 pb-12 sm:pb-16`}>
          <span
            className="tx-in inline-flex items-center gap-2 rounded-full px-3 py-1 text-[10.5px] font-semibold tracking-[0.14em] uppercase backdrop-blur-sm"
            style={{ background: 'rgba(34,211,238,0.16)', color: CYAN }}
          >
            <span className="live-dot" />
            Live tracking on every run
          </span>

          {/* Wordmark at full width. `clamp` keeps it on one line at every
              size, so it never wraps into a ragged second row. The text shadow
              is the last line of defence where the photo is brightest. */}
          <h1
            className="tx-in mt-6 text-[clamp(2.7rem,11.1vw,10rem)] whitespace-nowrap"
            style={{
              ...DISPLAY,
              ['--d' as string]: '60ms',
              textShadow: '0 2px 40px rgba(0,0,0,0.55)',
            }}
          >
            Target&nbsp;Express
          </h1>

          <div
            className="tx-in mt-6 flex flex-wrap items-baseline gap-x-5 gap-y-2 border-t pt-5 text-[10.5px] tracking-[0.2em] uppercase"
            style={{
              borderColor: 'rgba(255,255,255,0.22)',
              color: MUTED,
              ['--d' as string]: '120ms',
            }}
          >
            <span style={{ color: INK }}>Logistics to connect world</span>
            <span aria-hidden>·</span>
            <span>Kerala</span>
            <span aria-hidden>·</span>
            <span>Vendor godown to customer door</span>
          </div>
        </div>
      </div>

      <div className={`${SHELL} relative pt-14 pb-16 sm:pt-20 sm:pb-24`}>
        <div className="grid gap-14 lg:grid-cols-[1.35fr_1fr] lg:items-start">
          <div className="tx-in" style={{ ['--d' as string]: '180ms' }}>
            <p className="text-[clamp(1.7rem,4vw,3.4rem)]" style={DISPLAY}>
              We deliver more
              <br />
              than cargo.
              <br />
              We deliver{' '}
              <span
                style={{
                  background: GRAD,
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  color: 'transparent',
                }}
              >
                proof.
              </span>
            </p>

            <p className="mt-8 max-w-[54ch] text-[15px] leading-[1.75]" style={{ color: MUTED }}>
              Anyone can move a box from A to B. The hard part is being able to say, six weeks
              later, exactly which box went on which lorry, who signed for it, and what that
              journey cost. That is what we built.
            </p>

            <div className="mt-10 flex flex-wrap gap-3">
              <a
                href="#connect"
                className="inline-flex items-center gap-2 px-8 py-4 text-[12px] font-semibold tracking-[0.14em] uppercase transition-transform hover:scale-[1.02]"
                style={{ background: INK, color: PAPER }}
              >
                Move goods with us
                <ArrowRight className="size-4" />
              </a>
              <a
                href="#services"
                className="inline-flex items-center border px-8 py-4 text-[12px] font-semibold tracking-[0.14em] uppercase transition-colors hover:bg-white/5"
                style={{ borderColor: LINE, color: INK }}
              >
                What we do
              </a>
            </div>
          </div>

          <div
            className="tx-in relative overflow-hidden p-8 sm:p-9"
            style={{ background: NAVY, ['--d' as string]: '260ms' }}
          >
            <p className="text-[10px] tracking-[0.22em] uppercase" style={{ color: '#aeb5ec' }}>
              One run, start to finish
            </p>
            <p className="mt-6 text-[1.75rem]" style={DISPLAY}>
              Sorted.
              <br />
              Sealed.
              <br />
              Signed for.
            </p>

            <dl className="mt-8 border-t pt-6" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
              {[
                ['Every box labelled', 'Before it leaves the godown'],
                ['Every stop tracked', 'A live link per customer'],
                ['Every handover proved', 'Photo, receiver, count'],
                ['Every rupee explained', 'On the invoice line itself'],
              ].map(([term, detail], i) => (
                <div
                  key={term}
                  className="tx-in flex flex-col gap-0.5 py-2.5"
                  style={{ ['--d' as string]: `${380 + i * 90}ms` }}
                >
                  <dt className="text-[13px] font-medium">{term}</dt>
                  <dd className="text-[12px]" style={{ color: '#aeb5ec' }}>
                    {detail}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

/** The customer's way in, at the top of the page where they will look for it.
 *  Submitting hands off to /track, which does the real lookup — one form, one
 *  place where the rules live. */
function TrackStrip() {
  const [reference, setReference] = useState('')
  const navigate = useNavigate()

  return (
    <section className="border-y" style={{ borderColor: LINE, background: PANEL }}>
      <div className={`${SHELL} tx-reveal flex flex-wrap items-center gap-6 py-10`}>
        <div className="min-w-[260px] flex-1">
          <p className="text-[1.5rem]" style={DISPLAY}>
            Expecting a delivery?
          </p>
          <p className="mt-2 text-[13.5px]" style={{ color: MUTED }}>
            Enter the LR number from your paperwork. No app, no login, no password.
          </p>
        </div>

        <form
          className="flex w-full flex-wrap gap-2 sm:w-auto"
          onSubmit={(e) => {
            e.preventDefault()
            // Carried through so the tracking page opens with it already filled.
            navigate(`/track?ref=${encodeURIComponent(reference.trim())}`)
          }}
        >
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="LR OR BILL NUMBER"
            aria-label="LR or bill number"
            autoCapitalize="characters"
            className="h-[52px] min-w-[220px] flex-1 px-5 text-[13.5px] tracking-[0.1em] uppercase outline-none transition-colors focus:border-[#22d3ee]"
            style={{ background: PAPER, border: `1px solid ${LINE}`, color: INK }}
          />
          <button
            type="submit"
            className="inline-flex h-[52px] items-center gap-2 px-7 text-[12px] font-semibold tracking-[0.14em] uppercase transition-transform hover:scale-[1.02]"
            style={{ background: INK, color: PAPER }}
          >
            Track
            <ArrowRight className="size-4" />
          </button>
        </form>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

function Statement() {
  return (
    <section className="border-b" style={{ borderColor: LINE }}>
      <div className={`${SHELL} grid gap-10 py-20 sm:py-28 lg:grid-cols-[1fr_1fr] lg:gap-16`}>
        <p className="tx-reveal text-[clamp(1.8rem,4.4vw,3.4rem)]" style={DISPLAY}>
          A missing box
          <br />
          is never really
          <br />
          missing. The
          <br />
          record is.
        </p>
        <p
          className="tx-reveal max-w-[58ch] self-end text-[15px] leading-[1.75]"
          style={{ color: MUTED, ['--d' as string]: '120ms' }}
        >
          Somebody always knows what happened — the loader, the driver, the man at the gate. The
          problem is that nobody wrote it down. So we made writing it down the only way to finish
          the job: a freight cannot be closed until the boxes loaded equal the boxes delivered
          plus the boxes brought back. No override, no exception. That one rule turns an argument
          into an arithmetic.
        </p>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

const SERVICES: [string, string, string[]][] = [
  [
    '01',
    'Sorting & labelling',
    [
      'Our own admin and helper work inside the vendor’s godown, so their loading crew is freed entirely.',
      'Each box is sorted to its point and labelled with the point number, the bill number and which box of how many it is.',
      'Loaders sort by colour and number. Nothing depends on anyone remembering.',
    ],
  ],
  [
    '02',
    'Multi-point delivery',
    [
      'One run leaves a warehouse, serves up to thirty points, and is not finished until it is back.',
      'The route is sequenced in the office and opens as a single multi-stop route on the driver’s phone.',
      'A breakdown splits the run in two. Two vehicles get paid; the vendor still sees one freight.',
    ],
  ],
  [
    '03',
    'Live customer tracking',
    [
      'Every customer gets their own link the moment the lorry leaves. No app, no login, no password.',
      'They see their own cartons listed by bill number — not a status word, the actual boxes.',
      'Wrong address? They move the pin themselves, and it is right for every delivery after.',
    ],
  ],
  [
    '04',
    'Billing & settlement',
    [
      'A finished freight prices itself on the vendor’s own rate card, the one in force that day.',
      'Drivers are paid on distance. Rented lorries settle to their owner, with the advance already deducted.',
      'Every line shows its own arithmetic, so a vendor query takes thirty seconds, not a week.',
    ],
  ],
]

function Services() {
  return (
    <section id="services" className="scroll-mt-20">
      <div className={`${SHELL} py-20 sm:py-28`}>
        <h2 className="tx-reveal text-[clamp(2rem,6vw,4.2rem)]" style={DISPLAY}>
          What we do
        </h2>

        <div className="mt-14 grid gap-px sm:grid-cols-2" style={{ background: LINE }}>
          {SERVICES.map(([num, title, lines], i) => (
            <article
              key={num}
              className="group tx-reveal flex flex-col p-8 transition-colors sm:p-10"
              style={{ background: i === 1 ? NAVY : PANEL, ['--d' as string]: `${i * 90}ms` }}
            >
              <div className="flex items-start justify-between">
                <span className="text-[2.4rem] leading-none" style={DISPLAY}>
                  {num}
                </span>
                <ArrowUpRight
                  className="size-5 opacity-30 transition-all group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100"
                  aria-hidden
                />
              </div>

              <h3 className="mt-8 text-[1.4rem]" style={DISPLAY}>
                {title}
              </h3>

              <ul className="mt-5 space-y-3">
                {lines.map((l) => (
                  <li
                    key={l}
                    className="text-[13.5px] leading-[1.65]"
                    style={{ color: i === 1 ? '#c2c7ef' : MUTED }}
                  >
                    {l}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

function Billing() {
  const rows: [string, string][] = [
    ['Base freight charge', '₹1,867.00'],
    ['900 km − 60 included = 840 × ₹17', '₹14,280.00'],
    ['7 points − 3 included = 4 × ₹175', '₹700.00'],
    ['Toll, at actuals', '₹290.00'],
  ]

  return (
    <section className="border-t" style={{ borderColor: LINE }}>
      <div className={`${SHELL} grid gap-14 py-20 sm:py-28 lg:grid-cols-2 lg:items-center`}>
        <div className="tx-reveal">
          <h2 className="text-[clamp(1.9rem,5vw,3.6rem)]" style={DISPLAY}>
            Invoices that
            <br />
            explain themselves
          </h2>

          <p className="mt-8 max-w-[54ch] text-[15px] leading-[1.75]" style={{ color: MUTED }}>
            A rate agreed in April should still price an April freight in December. So rates are
            held per vendor division and per date, and are never edited — a change is a new card
            from the day it starts. Every line then carries its own working, in plain arithmetic.
          </p>

          <ul className="mt-9 flex flex-wrap gap-2">
            {['Per-vendor rate cards', 'Dated, never edited', 'Toll at actuals', 'GST ready'].map(
              (chip) => (
                <li
                  key={chip}
                  className="border px-4 py-2 text-[11px] tracking-[0.1em] uppercase"
                  style={{ borderColor: LINE, color: MUTED }}
                >
                  {chip}
                </li>
              ),
            )}
          </ul>
        </div>

        <div
          className="tx-reveal p-8 sm:p-10"
          style={{ background: PANEL, border: `1px solid ${LINE}`, ['--d' as string]: '120ms' }}
        >
          <p className="text-[10px] tracking-[0.2em] uppercase" style={{ color: FAINT }}>
            Freight Y26005892 · Kasaragod · 7 points · 900 km
          </p>

          <dl className="mt-8 space-y-3.5 font-mono text-[12.5px]">
            {rows.map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-6">
                <dt style={{ color: MUTED }}>{label}</dt>
                <dd className="tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          <div
            className="mt-8 flex items-baseline justify-between border-t pt-6"
            style={{ borderColor: LINE }}
          >
            <span className="text-[11px] tracking-[0.18em] uppercase" style={{ color: MUTED }}>
              Line total
            </span>
            <span className="font-mono text-[1.85rem] font-bold tabular-nums">₹17,137.00</span>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

/** Where a vendor turns into a conversation.
 *
 *  The fields asked for are the ones that let the office quote without a second
 *  call: what you move, where from, and roughly how much. Everything beyond
 *  company, name and phone is optional — an enquiry form that interrogates
 *  people gets abandoned. */
function Connect() {
  const [form, setForm] = useState({
    company_name: '',
    contact_name: '',
    phone: '',
    email: '',
    goods_type: '',
    origin_city: '',
    monthly_volume: '',
    message: '',
    website: '', // honeypot: hidden from people, filled by bots
  })

  const submit = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ message: string }>('/public/enquiries', form)
      return data.message
    },
  })

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const ready =
    form.company_name.trim().length >= 2 &&
    form.contact_name.trim().length >= 2 &&
    form.phone.replace(/\D/g, '').length >= 6

  const fieldStyle: React.CSSProperties = {
    background: PAPER,
    border: `1px solid ${LINE}`,
    color: INK,
  }

  return (
    <section id="connect" className="scroll-mt-20 border-t" style={{ borderColor: LINE }}>
      <div className={`${SHELL} grid gap-14 py-20 sm:py-28 lg:grid-cols-[1fr_1.1fr] lg:gap-20`}>
        <div className="tx-reveal">
          <h2 className="text-[clamp(1.9rem,5vw,3.6rem)]" style={DISPLAY}>
            Move your
            <br />
            goods with us
          </h2>

          <p className="mt-8 max-w-[48ch] text-[15px] leading-[1.75]" style={{ color: MUTED }}>
            Tell us what you move and where it goes. We will come back with a rate card for your
            division — the same dated, itemised card our existing vendors are billed on. No
            lock-in, and no charge for the first survey of your godown.
          </p>

          <div className="mt-10 space-y-px" style={{ background: LINE }}>
            {[
              { icon: <Phone className="size-4" />, label: 'Call the operations desk', value: CONTACT.phone, href: CONTACT.phoneHref },
              { icon: <MessageCircle className="size-4" />, label: 'WhatsApp', value: 'Send us a message', href: CONTACT.whatsapp },
              { icon: <Mail className="size-4" />, label: 'Email', value: CONTACT.email, href: `mailto:${CONTACT.email}` },
              { icon: <MapPin className="size-4" />, label: 'Operating from', value: CONTACT.city },
            ].map((row) => {
              const inner = (
                <div
                  className="flex items-center gap-4 p-5 transition-colors hover:bg-white/[0.04]"
                  style={{ background: PANEL }}
                >
                  <span style={{ color: CYAN }}>{row.icon}</span>
                  <span className="min-w-0">
                    <span
                      className="block text-[10px] tracking-[0.18em] uppercase"
                      style={{ color: FAINT }}
                    >
                      {row.label}
                    </span>
                    <span className="block truncate text-[14px] font-medium">{row.value}</span>
                  </span>
                </div>
              )
              return row.href ? (
                <a
                  key={row.label}
                  href={row.href}
                  target={row.href.startsWith('http') ? '_blank' : undefined}
                  rel="noreferrer"
                  className="block"
                >
                  {inner}
                </a>
              ) : (
                <div key={row.label}>{inner}</div>
              )
            })}
          </div>
        </div>

        <div
          className="tx-reveal p-7 sm:p-10"
          style={{ background: PANEL, border: `1px solid ${LINE}`, ['--d' as string]: '120ms' }}
        >
          {submit.isSuccess ? (
            <div className="tx-in-scale flex min-h-[380px] flex-col items-center justify-center text-center">
              <span
                className="grid size-14 place-items-center rounded-full"
                style={{ background: 'rgba(34,211,238,0.12)', color: CYAN }}
              >
                <Check className="size-6" />
              </span>
              <p className="mt-6 text-[1.5rem]" style={DISPLAY}>
                Enquiry received
              </p>
              <p className="mt-3 max-w-[38ch] text-[14px] leading-relaxed" style={{ color: MUTED }}>
                {submit.data}
              </p>
            </div>
          ) : (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                if (ready) submit.mutate()
              }}
            >
              <p className="text-[10px] tracking-[0.2em] uppercase" style={{ color: FAINT }}>
                Business enquiry
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                <Input label="Company name" required value={form.company_name} onChange={set('company_name')} style={fieldStyle} />
                <Input label="Your name" required value={form.contact_name} onChange={set('contact_name')} style={fieldStyle} />
                <Input label="Phone" required type="tel" value={form.phone} onChange={set('phone')} style={fieldStyle} />
                <Input label="Email" type="email" value={form.email} onChange={set('email')} style={fieldStyle} />
                <Input label="What do you move?" placeholder="Spare parts, furniture…" value={form.goods_type} onChange={set('goods_type')} style={fieldStyle} />
                <Input label="Dispatching from" placeholder="City or godown" value={form.origin_city} onChange={set('origin_city')} style={fieldStyle} />
              </div>

              <Input
                label="Roughly how much, per month?"
                placeholder="e.g. 400 boxes, or 20 runs"
                value={form.monthly_volume}
                onChange={set('monthly_volume')}
                style={fieldStyle}
              />

              <label className="block">
                <span className="text-[10px] tracking-[0.18em] uppercase" style={{ color: FAINT }}>
                  Anything else
                </span>
                <textarea
                  rows={3}
                  value={form.message}
                  onChange={set('message')}
                  className="mt-2 w-full resize-none px-4 py-3 text-[14px] outline-none transition-colors focus:border-[#22d3ee]"
                  style={fieldStyle}
                />
              </label>

              {/* Honeypot. Hidden from people, invisible to screen readers,
                  irresistible to form-filling bots. */}
              <input
                type="text"
                name="website"
                value={form.website}
                onChange={set('website')}
                tabIndex={-1}
                autoComplete="off"
                aria-hidden="true"
                className="absolute left-[-9999px] h-px w-px opacity-0"
              />

              {submit.isError ? (
                <p className="text-[13px]" style={{ color: '#fb7185' }} role="alert">
                  {apiErrorMessage(submit.error, 'Could not send that. Please call us instead.')}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={!ready || submit.isPending}
                className="group inline-flex h-[52px] w-full items-center justify-center gap-2 text-[12px] font-semibold tracking-[0.14em] uppercase transition-transform hover:scale-[1.01] disabled:scale-100 disabled:opacity-40"
                style={{ background: GRAD, color: PAPER }}
              >
                {submit.isPending ? 'Sending…' : 'Send enquiry'}
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </button>

              <p className="text-[11.5px] leading-relaxed" style={{ color: FAINT }}>
                We use your number to call you back about this enquiry, and for nothing else.
              </p>
            </form>
          )}
        </div>
      </div>
    </section>
  )
}

function Input({
  label,
  style,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="text-[10px] tracking-[0.18em] uppercase" style={{ color: FAINT }}>
        {label}
        {props.required ? <span style={{ color: CYAN }}> *</span> : null}
      </span>
      <input
        {...props}
        className="mt-2 h-[46px] w-full px-4 text-[14px] outline-none transition-colors focus:border-[#22d3ee]"
        style={style}
      />
    </label>
  )
}

/* -------------------------------------------------------------------------- */

function Footer(): ReactNode {
  return (
    <footer className="border-t" style={{ borderColor: LINE }}>
      <div className={`${SHELL} pt-20 pb-10`}>
        <p className="text-[clamp(2.3rem,10.4vw,9.2rem)] whitespace-nowrap" style={DISPLAY}>
          Target&nbsp;Express
        </p>

        <div
          className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 border-t pt-7 text-[11px]"
          style={{ borderColor: LINE, color: FAINT }}
        >
          <Link to="/track" className="transition-colors hover:text-white">
            Track a delivery
          </Link>
          <a href="#connect" className="transition-colors hover:text-white">
            Work with us
          </a>
          <Link to="/login" className="transition-colors hover:text-white">
            Staff sign in
          </Link>
          <a href={CONTACT.phoneHref} className="transition-colors hover:text-white">
            {CONTACT.phone}
          </a>
        </div>

        <div
          className="mt-6 flex flex-wrap items-center justify-between gap-4 text-[10.5px] tracking-[0.2em] uppercase"
          style={{ color: FAINT }}
        >
          <span>Logistics to connect world</span>
          <span>© {new Date().getFullYear()} Target Express Logistics</span>
        </div>
      </div>
    </footer>
  )
}
