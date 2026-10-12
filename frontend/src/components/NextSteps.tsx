import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Card } from '@/components/ui'
import { api } from '@/lib/api'

/* "What do I do now."
 *
 * The people using this have no software background, and the thing that trips
 * them up is not a confusing screen — it is that nothing anywhere says which
 * screen to be on. A bill sits unassigned, a freight is never dispatched, a
 * finished trip is never invoiced, and each stays invisible until somebody
 * happens to open the right list.
 *
 * So the work is listed, in plain instructions, with the number and a way
 * straight there. Every item is derived from a real count — nothing appears
 * because it might be useful, because advice that is always on screen is
 * advice people stop reading.
 */

interface Step {
  key: string
  title: string
  detail: string
  count: number
  to: string
  urgency: 'now' | 'soon' | string
}

interface NextStepsOut {
  steps: Step[]
  all_clear: boolean
}

export function NextSteps({ limit }: { limit?: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['/next-steps'],
    queryFn: async () => (await api.get<NextStepsOut>('/next-steps')).data,
    // The counts move as the day is worked through, and a stale list sends
    // somebody to a screen with nothing on it.
    refetchInterval: 120_000,
  })

  if (isLoading || !data) return <div className="skeleton h-24" />

  if (data.all_clear) {
    return (
      <Card className="flex items-center gap-3 px-4 py-3.5">
        <CheckCircle2 className="size-5 shrink-0" style={{ color: 'var(--success)' }} />
        <div>
          <p className="text-[13.5px] font-medium">Nothing waiting</p>
          <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Every trip is billed, every bill is on a freight, and nobody is waiting for a call.
          </p>
        </div>
      </Card>
    )
  }

  const steps = limit ? data.steps.slice(0, limit) : data.steps
  const hidden = data.steps.length - steps.length

  return (
    <section>
      <h2 className="eyebrow mb-2">What to do next</h2>
      <div className="space-y-2">
        {steps.map((step) => (
          <StepRow key={step.key} step={step} />
        ))}
        {hidden > 0 ? (
          <p className="pl-1 text-[12px]" style={{ color: 'var(--text-faint)' }}>
            and {hidden} more
          </p>
        ) : null}
      </div>
    </section>
  )
}

/* One instruction.
 *
 * The whole row is the link. A small "go" target is the wrong shape for a phone
 * in a godown and for somebody who does not reach for a mouse confidently. */
function StepRow({ step }: { step: Step }) {
  const now = step.urgency === 'now'
  return (
    <Link
      to={step.to}
      className="hoverable flex items-center gap-3 rounded-[var(--radius-card)] border px-4 py-3 no-underline"
      style={{
        borderColor: now
          ? 'color-mix(in oklab, var(--warning) 35%, transparent)'
          : 'var(--border)',
        background: now
          ? 'color-mix(in oklab, var(--warning) 7%, var(--surface))'
          : 'var(--surface)',
      }}
    >
      {/* The count, big enough to read across a desk. */}
      <span
        className="tnum grid size-9 shrink-0 place-items-center rounded-[10px] text-[14px] font-semibold"
        style={{
          background: now ? 'var(--warning)' : 'var(--accent-dim)',
          color: now ? '#1a1205' : 'var(--accent)',
        }}
      >
        {step.count}
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium">{step.title}</p>
        <p className="text-[12px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {step.detail}
        </p>
      </div>

      <ArrowRight className="size-4 shrink-0" style={{ color: 'var(--text-faint)' }} aria-hidden />
    </Link>
  )
}
