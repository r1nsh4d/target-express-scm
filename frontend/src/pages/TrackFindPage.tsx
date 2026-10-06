/* "Where is my delivery?" — the public front door to tracking.
 *
 * Target Express sends a tracking link by WhatsApp when a run is dispatched.
 * People delete that message, change phones, or were not the one who received
 * it. This page is the way back in: the number printed on the paperwork, plus
 * the phone the delivery was booked against.
 *
 * Two facts, not one, and that is a deliberate product decision rather than a
 * technical one. An LR number is a sequence — if it alone were enough, anyone
 * could count upward from 0001 and read out every customer Target Express has.
 * The phone is the shared secret. It costs the customer nothing: it is their
 * own number, and they are holding the invoice with the LR on it.
 */

import { useMutation } from '@tanstack/react-query'
import { ArrowRight, PackageSearch, Phone, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { Logo } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

export default function TrackFindPage() {
  // The landing page's strip passes the number through, so somebody who typed
  // it there does not type it again here.
  const [params] = useSearchParams()
  const [reference, setReference] = useState(() => params.get('ref')?.toUpperCase() ?? '')
  const [phone, setPhone] = useState('')
  const navigate = useNavigate()

  const lookup = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ token: string }>('/public/track/lookup', {
        reference: reference.trim(),
        phone: phone.trim(),
      })
      return data.token
    },
    onSuccess: (token) => navigate(`/track/${token}`),
  })

  const ready = reference.trim().length >= 3 && phone.trim().length >= 6

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="aurora" aria-hidden />
      <div className="grid-field" aria-hidden />

      <header className="relative z-10 flex items-center justify-between px-5 py-5 sm:px-10">
        <button onClick={() => navigate('/')} aria-label="Target Express home">
          <Logo size={30} />
        </button>
        <button
          onClick={() => navigate('/login')}
          className="rounded-full px-4 py-1.5 text-[12.5px] font-medium transition-colors"
          style={{ border: '1px solid var(--border-strong)', color: 'var(--text-muted)' }}
        >
          Staff sign in
        </button>
      </header>

      <main className="relative z-10 mx-auto flex w-full max-w-[520px] flex-1 flex-col justify-center px-5 pb-20">
        <div className="tx-in">
          <span
            className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-medium"
            style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
          >
            <span className="live-dot" />
            Live tracking
          </span>

          <h1 className="mt-5 text-[34px] leading-[1.08] font-semibold tracking-tight sm:text-[40px]">
            Where is my
            <br />
            <span className="ink-grad">delivery?</span>
          </h1>

          <p className="mt-4 text-[14px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Enter the LR number from your delivery paperwork, or the bill number from
            your invoice, along with the phone number the delivery was booked against.
          </p>
        </div>

        <form
          className="tx-in mt-8 space-y-4"
          style={{ ['--d' as string]: '90ms' }}
          onSubmit={(e) => {
            e.preventDefault()
            if (ready) lookup.mutate()
          }}
        >
          <label className="block">
            <span className="eyebrow">LR number or bill number</span>
            <div className="relative mt-2">
              <PackageSearch
                className="absolute top-1/2 left-4 size-4 -translate-y-1/2"
                style={{ color: 'var(--text-faint)' }}
              />
              <input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="TX-LR-0042"
                autoComplete="off"
                autoCapitalize="characters"
                className="inset h-[52px] w-full pr-4 pl-11 text-[16px] tracking-wide uppercase outline-none"
                style={{ color: 'var(--text)' }}
              />
            </div>
          </label>

          <label className="block">
            <span className="eyebrow">Phone number given at booking</span>
            <div className="relative mt-2">
              <Phone
                className="absolute top-1/2 left-4 size-4 -translate-y-1/2"
                style={{ color: 'var(--text-faint)' }}
              />
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="98470 12345"
                // type="tel" so a phone shows the number pad. Most people open
                // this on the handset the parcel is coming to.
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                className="inset h-[52px] w-full pr-4 pl-11 text-[16px] outline-none"
                style={{ color: 'var(--text)' }}
              />
            </div>
          </label>

          {lookup.isError ? (
            <p
              className="tx-in-fade rounded-[10px] px-4 py-3 text-[13px] leading-relaxed"
              style={{
                background: 'color-mix(in oklab, var(--danger) 12%, transparent)',
                color: 'var(--danger)',
              }}
              role="alert"
            >
              {apiErrorMessage(lookup.error, 'We could not find that delivery.')}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={!ready || lookup.isPending}
            className="group flex h-[52px] w-full items-center justify-center gap-2 rounded-[10px] text-[14.5px] font-semibold transition-all disabled:opacity-40"
            style={{
              background: 'var(--accent-grad)',
              color: 'var(--accent-fg)',
              boxShadow: ready ? 'var(--glow)' : 'none',
            }}
          >
            {lookup.isPending ? 'Finding your delivery…' : 'Track my delivery'}
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </button>
        </form>

        <p
          className="tx-in mt-6 flex items-start gap-2 text-[12px] leading-relaxed"
          style={{ ['--d' as string]: '160ms', color: 'var(--text-faint)' }}
        >
          <ShieldCheck className="mt-px size-3.5 shrink-0" />
          We ask for your phone number so that only you can see your delivery. We
          never show anyone else's consignment, and nothing about the other stops
          on the same run.
        </p>
      </main>
    </div>
  )
}
