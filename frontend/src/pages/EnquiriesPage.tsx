/* The office's side of the landing page's enquiry form.
 *
 * Built as a pipeline rather than a table, because that is what it is: a lead
 * is worth something for about a day and then it is worth nothing. The newest
 * enquiry is the loudest thing on the screen, and the only question the screen
 * asks is "has anyone called them yet".
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2,
  Check,
  Inbox,
  Mail,
  MapPin,
  MessageCircle,
  Package,
  Phone,
  X,
} from 'lucide-react'
import { useState } from 'react'

import { Badge, Card, EmptyState, ErrorNote, PageHeader, Spinner } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'
import { stagger } from '@/lib/motion'
import { useList } from '@/lib/resources'

type EnquiryStatus = 'NEW' | 'CONTACTED' | 'QUOTED' | 'WON' | 'LOST' | 'SPAM'

interface Enquiry {
  id: string
  company_name: string
  contact_name: string
  phone: string
  email: string | null
  goods_type: string | null
  origin_city: string | null
  monthly_volume: string | null
  message: string | null
  status: EnquiryStatus
  internal_note: string | null
  contacted_at: string | null
  created_at: string
}

const STATUS_TONE: Record<EnquiryStatus, 'accent' | 'info' | 'warning' | 'success' | 'neutral' | 'danger'> = {
  NEW: 'accent',
  CONTACTED: 'info',
  QUOTED: 'warning',
  WON: 'success',
  LOST: 'neutral',
  SPAM: 'danger',
}

const STATUS_LABEL: Record<EnquiryStatus, string> = {
  NEW: 'New',
  CONTACTED: 'Called',
  QUOTED: 'Quoted',
  WON: 'Won',
  LOST: 'Lost',
  SPAM: 'Spam',
}

/* The order the office works them in. SPAM is reachable but not on the main
   path — it is a correction, not a stage. */
const PIPELINE: EnquiryStatus[] = ['NEW', 'CONTACTED', 'QUOTED', 'WON', 'LOST']

function sinceLabel(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export default function EnquiriesPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<EnquiryStatus | 'ALL'>('ALL')

  const enquiries = useList<Enquiry>('/enquiries')

  const patch = useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Partial<Enquiry>) =>
      (await api.patch(`/enquiries/${id}`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['/enquiries'] }),
    onError: (e) => setError(apiErrorMessage(e)),
  })

  const all = enquiries.data ?? []
  const rows = filter === 'ALL' ? all : all.filter((e) => e.status === filter)
  const newCount = all.filter((e) => e.status === 'NEW').length

  return (
    <div className="space-y-5">
      <PageHeader description="Businesses who filled in the form on targetexpress. A lead is worth something for about a day — the newest is at the top, and the only question is whether anyone has called them yet." />

      <ErrorNote>{error}</ErrorNote>

      <div className="flex flex-wrap items-center gap-2">
        {(['ALL', ...PIPELINE] as const).map((key) => {
          const count = key === 'ALL' ? all.length : all.filter((e) => e.status === key).length
          const active = filter === key
          return (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className="rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-all"
              style={{
                background: active ? 'var(--accent-dim)' : 'var(--surface)',
                border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                color: active ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {key === 'ALL' ? 'All' : STATUS_LABEL[key]}
              <span className="tnum ml-1.5 opacity-60">{count}</span>
            </button>
          )
        })}

        {newCount > 0 ? (
          <span
            className="ml-auto flex items-center gap-2 text-[12.5px]"
            style={{ color: 'var(--accent)' }}
          >
            <span className="live-dot" />
            {newCount} waiting for a call
          </span>
        ) : null}
      </div>

      {enquiries.isLoading ? (
        <div className="flex justify-center py-20">
          <Spinner className="size-5" />
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Inbox className="size-7" />}
            title={filter === 'ALL' ? 'No enquiries yet' : `Nothing at "${STATUS_LABEL[filter as EnquiryStatus]}"`}
            description={
              filter === 'ALL'
                ? 'When somebody fills in the form on the website, they land here within seconds.'
                : 'Try another stage, or All.'
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {rows.map((enquiry, i) => (
            <Card
              key={enquiry.id}
              className={clsxCard(enquiry.status)}
              style={stagger(i)}
            >
              <div className="flex items-start justify-between gap-3 p-4 pb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Building2 className="size-3.5 shrink-0" style={{ color: 'var(--text-faint)' }} />
                    <h3 className="truncate text-[14.5px] font-semibold">{enquiry.company_name}</h3>
                  </div>
                  <p className="mt-0.5 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                    {enquiry.contact_name} · {sinceLabel(enquiry.created_at)}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[enquiry.status]}>{STATUS_LABEL[enquiry.status]}</Badge>
              </div>

              {/* Phone and WhatsApp as real controls. The whole point of this
                  screen is that somebody picks up the phone. */}
              <div className="flex flex-wrap gap-2 px-4 pb-3">
                <a
                  href={`tel:${enquiry.phone.replace(/\s/g, '')}`}
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium transition-colors"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                >
                  <Phone className="size-3.5" />
                  {enquiry.phone}
                </a>
                <a
                  href={`https://wa.me/${enquiry.phone.replace(/\D/g, '')}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] transition-colors"
                  style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
                >
                  <MessageCircle className="size-3.5" />
                  WhatsApp
                </a>
                {enquiry.email ? (
                  <a
                    href={`mailto:${enquiry.email}`}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] transition-colors"
                    style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
                  >
                    <Mail className="size-3.5" />
                    <span className="max-w-[16ch] truncate">{enquiry.email}</span>
                  </a>
                ) : null}
              </div>

              <div className="groove mx-4" />

              <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 p-4 text-[12.5px]">
                <Detail icon={<Package className="size-3.5" />} label="Moves" value={enquiry.goods_type} />
                <Detail icon={<MapPin className="size-3.5" />} label="From" value={enquiry.origin_city} />
                <Detail
                  icon={<Inbox className="size-3.5" />}
                  label="Volume"
                  value={enquiry.monthly_volume}
                  span
                />
              </dl>

              {enquiry.message ? (
                <p
                  className="mx-4 mb-4 rounded-[10px] px-3 py-2.5 text-[12.5px] leading-relaxed"
                  style={{ background: 'var(--bg)', color: 'var(--text-muted)' }}
                >
                  {enquiry.message}
                </p>
              ) : null}

              <div
                className="flex flex-wrap items-center gap-1.5 px-4 py-3"
                style={{ borderTop: '1px solid var(--border)' }}
              >
                <span className="eyebrow mr-1">Mark as</span>
                {PIPELINE.filter((s) => s !== enquiry.status).map((s) => (
                  <button
                    key={s}
                    onClick={() => patch.mutate({ id: enquiry.id, status: s })}
                    disabled={patch.isPending}
                    className="rounded-full px-2.5 py-1 text-[11.5px] font-medium transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-40"
                    style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
                  >
                    {s === 'WON' ? <Check className="mr-1 inline size-3" /> : null}
                    {STATUS_LABEL[s]}
                  </button>
                ))}
                <button
                  onClick={() => patch.mutate({ id: enquiry.id, status: 'SPAM' })}
                  disabled={patch.isPending}
                  className="ml-auto rounded-full p-1.5 transition-colors hover:bg-[var(--surface-hover)]"
                  style={{ color: 'var(--text-faint)' }}
                  title="Not a real enquiry"
                  aria-label="Mark as spam"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

/** A new enquiry is lit. Everything else is a normal card — the glow is the
 *  screen's one job, so it is spent on the one state that needs action. */
function clsxCard(status: EnquiryStatus): string {
  return status === 'NEW' ? 'lit overflow-hidden hoverable' : 'overflow-hidden hoverable'
}

function Detail({
  icon,
  label,
  value,
  span,
}: {
  icon: React.ReactNode
  label: string
  value: string | null
  span?: boolean
}) {
  if (!value) return null
  return (
    <div className={span ? 'col-span-2' : undefined}>
      <dt className="flex items-center gap-1.5" style={{ color: 'var(--text-faint)' }}>
        {icon}
        <span className="text-[11px] tracking-wide uppercase">{label}</span>
      </dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  )
}
