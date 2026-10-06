import { ArrowLeft, ArrowRight, Lock, Phone } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button, ErrorNote, Field, Input, Logo } from '@/components/ui'
import { apiErrorMessage } from '@/lib/api'
import { homePathForRole, useAuth } from '@/lib/auth'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await login(phone.trim(), password)
      navigate(homePathForRole(user.role), { replace: true })
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not sign you in'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_1.05fr]">
      {/* Brand side. Black in either theme, so the identity holds. */}
      <aside
        className="relative hidden flex-col justify-between overflow-hidden p-12 lg:flex"
        style={{ background: 'var(--rail)', color: 'var(--rail-text)' }}
      >
        {/* Two slow blooms drifting behind the brand side. Decorative, so it
            is aria-hidden and never catches a click. */}
        <div className="aurora" aria-hidden />
        <div className="grid-field" aria-hidden />

        <div className="tx-in relative">
          <Logo onDark size={34} />
        </div>

        <div className="relative">
          <span
            className="tx-in inline-flex items-center gap-2 rounded-full px-3 py-1 text-[10.5px] font-semibold tracking-[0.14em] uppercase"
            style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
          >
            <span className="live-dot" />
            Operations console
          </span>

          <p
            className="tx-in mt-5 max-w-[22ch] text-[2.4rem] leading-[1.08] font-semibold tracking-[-0.03em]"
            style={{ ['--d' as string]: '80ms' }}
          >
            Every box accounted for.
          </p>
          <p
            className="tx-in mt-6 max-w-[46ch] text-[14px] leading-relaxed"
            style={{ color: 'var(--rail-muted)', ['--d' as string]: '160ms' }}
          >
            Freights, drivers, customers and billing — from the vendor's godown to the
            customer's door, in one place.
          </p>
        </div>

        <div
          className="relative text-[10px] tracking-[0.18em] uppercase"
          style={{ color: 'var(--rail-faint)' }}
        >
          Logistics to connect world
        </div>
      </aside>

      {/* Form side */}
      <main className="flex flex-col px-5 py-8 sm:px-10">
        <div className="flex items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-[13px] transition-colors hover:text-[var(--text)]"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft className="size-4" />
            Back
          </Link>
          <div className="lg:hidden">
            <Logo size={26} />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="tx-in w-full max-w-[26rem]">
            <h1 className="text-[26px] leading-tight font-semibold">Sign in</h1>
            <p className="mt-2 text-[13.5px]" style={{ color: 'var(--text-muted)' }}>
              One login for admins, drivers and stakeholders. Your mobile number is your
              username.
            </p>

            <form onSubmit={handleSubmit} className="mt-8 space-y-4">
              <Field label="Mobile number">
                <div className="relative">
                  <Phone
                    className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
                    style={{ color: 'var(--text-faint)' }}
                  />
                  <Input
                    className="tnum pl-10"
                    type="tel"
                    inputMode="numeric"
                    autoComplete="username"
                    placeholder="9876543210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    required
                  />
                </div>
              </Field>

              <Field label="Password">
                <div className="relative">
                  <Lock
                    className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
                    style={{ color: 'var(--text-faint)' }}
                  />
                  <Input
                    className="pl-10"
                    type="password"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
              </Field>

              <ErrorNote>{error}</ErrorNote>

              <Button
                type="submit"
                size="lg"
                loading={busy}
                className="w-full"
                icon={busy ? undefined : <ArrowRight className="size-4" />}
              >
                Sign in
              </Button>
            </form>

            <p className="mt-8 text-center text-[12.5px]" style={{ color: 'var(--text-faint)' }}>
              Trouble signing in? Contact your operations admin.
            </p>

            {/* Customers end up here by guessing. They do not have a login and
                never will — send them where they actually meant to go. */}
            <div className="groove my-6" />
            <p className="text-center text-[12.5px]" style={{ color: 'var(--text-faint)' }}>
              Expecting a delivery?{' '}
              <Link
                to="/track"
                className="font-medium underline-offset-2 hover:underline"
                style={{ color: 'var(--accent)' }}
              >
                Track it here
              </Link>{' '}
              — no login needed.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
