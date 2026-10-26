import { Plus, UserRound } from 'lucide-react'
import { useCallback, useState } from 'react'

import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
} from '@/components/ui'
import { byName, choicesFrom, useFilters } from '@/components/Filters'
import { Fact, Facts, TileGrid, TileHead } from '@/components/TileGrid'
import { DriverDetail } from '@/components/Profiles'
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { Driver, Vehicle } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function DriversPage() {
  const [open, setOpen] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen(true), []))
  const drivers = useList<Driver>('/drivers')
  const vehicles = useList<Vehicle>('/vehicles')

  const all = drivers.data ?? []
  const view = useFilters<Driver>({
    rows: all,
    placeholder: 'Search by name or phone',
    search: (d) => [d.name, d.phone, d.licence_no],
    filters: [
      {
        key: 'engagement',
        label: 'Paid by',
        choices: choicesFrom(all, (d) => d.engagement, (v) =>
          v === 'OWN_STAFF' ? 'Target Express' : "the vehicle's owner",
        ),
        matches: (d, v) => d.engagement === v,
      },
      {
        // The gap that stops a man working: no login, no phone, no trip.
        key: 'login',
        label: 'Login',
        choices: [
          { value: 'yes', label: 'has one' },
          { value: 'no', label: 'none yet' },
        ],
        matches: (d, v) => (v === 'yes' ? !!d.user_id : !d.user_id),
      },
    ],
    sorts: [
      { key: 'name', label: 'A to Z', compare: byName<Driver>((d) => d.name) },
      {
        key: 'engagement',
        label: 'By who pays',
        compare: (a, b) =>
          a.engagement.localeCompare(b.engagement) || a.name.localeCompare(b.name),
      },
    ],
  })

  return (
    <div className="space-y-6">
      <PageHeader
        description="Drivers are paid on distance, plus the unloading cash they hand to the labourers at each point."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New driver
          </Button>
        }
      />

      {view.controls}

      {drivers.isLoading ? (
        <Card>
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        </Card>
      ) : (
        <TileGrid
          rows={view.rows}
          rowKey={(d) => d.id}
          onRowClick={(d) => setViewing(d.id)}
          empty={
            <EmptyState
              icon={<UserRound className="size-7" />}
              title={view.narrowed ? 'Nobody matches' : 'No drivers yet'}
              description={
                view.narrowed
                  ? 'Try a different name, or clear the filters.'
                  : 'A driver needs a login before he can run a trip from his phone.'
              }
              action={
                view.narrowed ? (
                  <Button variant="secondary" onClick={view.clear}>
                    Clear
                  </Button>
                ) : (
                  <Button onClick={() => setOpen(true)}>New driver</Button>
                )
              }
            />
          }
          render={(d) => (
            <>
              <TileHead
                title={d.name}
                // His phone is also his username, so it belongs beside his
                // name rather than three columns away.
                sub={<span className="tnum">{d.phone}</span>}
                badge={
                  <Badge tone={d.engagement === 'OWN_STAFF' ? 'success' : 'info'}>
                    {d.engagement === 'OWN_STAFF' ? 'Own staff' : 'On a rented vehicle'}
                  </Badge>
                }
                actions={
                  <RowActions
                    path={'/drivers'}
                    row={d as unknown as Record<string, unknown> & { id: string }}
                    label="Driver"
                    fields={[
                      { name: 'name', label: 'Name', required: true },
                      {
                        name: 'phone',
                        label: 'Phone',
                        kind: 'tel' as const,
                        hint: 'Also his login username',
                      },
                      { name: 'licence_no', label: 'Licence number' },
                    ]}
                  />
                }
              />
              <Facts>
                <Fact
                  label="Licence"
                  value={d.licence_no ?? 'Not on file'}
                  tone={d.licence_no ? undefined : 'muted'}
                />
                {/* Without a login he cannot run a trip from his phone, which
                    is the one thing about him worth seeing from here. */}
                <Fact
                  label="Phone login"
                  value={d.user_id ? 'Yes' : 'Not created'}
                  tone={d.user_id ? 'success' : 'warning'}
                />
              </Facts>
              <p className="mt-2.5 text-[11.5px]" style={{ color: 'var(--text-faint)' }}>
                Open for his trips, earnings, settlements and advances
              </p>
            </>
          )}
        />
      )}

      <DriverDetail driverId={viewing} open={viewing !== null} onClose={() => setViewing(null)} />

      <DriverForm open={open} onClose={() => setOpen(false)} vehicles={vehicles.data ?? []} />
    </div>
  )
}

function DriverForm({
  open,
  onClose,
  vehicles,
}: {
  open: boolean
  onClose: () => void
  vehicles: Vehicle[]
}) {
  const blank = {
    name: '',
    phone: '',
    engagement: 'OWN_STAFF',
    licence_no: '',
    default_vehicle_id: '',
    per_km_amount: '2.50',
    unloading_share_percent: '100',
    unloading_share_basis: 'PAID_AT_POINT',
    create_login: true,
    password: '',
    can_view_earnings: true,
  }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)
  const onRental = form.engagement === 'ATTACHED_TO_HIRED_VEHICLE'

  const create = useCreate<Record<string, unknown>>('/drivers', {
    alsoInvalidate: ['/auth/users'],
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New driver">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            {
              name: form.name,
              phone: form.phone,
              engagement: form.engagement,
              licence_no: form.licence_no || null,
              default_vehicle_id: form.default_vehicle_id || null,
              per_km_amount: onRental ? '0' : form.per_km_amount,
              unloading_share_percent: form.unloading_share_percent,
              unloading_share_basis: form.unloading_share_basis,
              create_login: form.create_login,
              password: form.password || null,
              can_view_earnings: onRental ? false : form.can_view_earnings,
            },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </Field>
          <Field label="Phone" hint="This is also his login">
            <Input
              className="tnum"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              required
            />
          </Field>
        </div>

        <Field label="Engagement">
          <Select
            value={form.engagement}
            onChange={(e) => setForm({ ...form, engagement: e.target.value })}
          >
            <option value="OWN_STAFF">Target Express staff</option>
            <option value="ATTACHED_TO_HIRED_VEHICLE">Comes with a rented vehicle</option>
          </Select>
        </Field>

        {onRental ? (
          <p
            className="rounded-lg border px-3.5 py-2.5 text-[12.5px]"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            Target Express does not pay this driver for driving — his owner does. He still
            receives the unloading cash, and his earnings screen is switched off.
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Licence number">
            <Input
              value={form.licence_no}
              onChange={(e) => setForm({ ...form, licence_no: e.target.value })}
            />
          </Field>
          <Field label="Usual vehicle">
            <Select
              value={form.default_vehicle_id}
              onChange={(e) => setForm({ ...form, default_vehicle_id: e.target.value })}
            >
              <option value="">Not set</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.registration_no}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {!onRental ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Rate per km">
              <Input
                className="tnum"
                type="number"
                step="0.01"
                value={form.per_km_amount}
                onChange={(e) => setForm({ ...form, per_km_amount: e.target.value })}
              />
            </Field>
            <Field label="Unloading share %" hint="Target Express keeps the rest">
              <Input
                className="tnum"
                type="number"
                value={form.unloading_share_percent}
                onChange={(e) => setForm({ ...form, unloading_share_percent: e.target.value })}
              />
            </Field>
            <Field
              label="Share of what"
              hint="The two pay different money on the same trip"
            >
              <Select
                value={form.unloading_share_basis}
                onChange={(e) => setForm({ ...form, unloading_share_basis: e.target.value })}
              >
                <option value="PAID_AT_POINT">What was paid out at the points</option>
                <option value="BILLED_TO_VENDOR">What the vendor was billed</option>
              </Select>
            </Field>
          </div>
        ) : null}

        {/* Which pot the percentage applies to is not a detail — it is the
            difference between paying this driver 420 and 630 on the same run,
            and on a spare-parts run the vendor is billed nothing at all. */}
        {form.unloading_share_basis === 'BILLED_TO_VENDOR' ? (
          <p
            className="rounded-[10px] px-3 py-2.5 text-[12.5px] leading-relaxed"
            style={{
              background: 'color-mix(in oklab, var(--info) 10%, transparent)',
              color: 'var(--text-muted)',
            }}
          >
            On this basis his share is a cut of what the vendor pays for unloading, and
            Target Express keeps the remainder. Spare-parts runs bill the vendor nothing
            for unloading, so on those he is instead reimbursed whatever cash he actually
            handed over — he is never left out of pocket.
          </p>
        ) : null}

        <div className="space-y-3">
          <Checkbox
            label="Create a login for him"
            checked={form.create_login}
            onChange={(e) => setForm({ ...form, create_login: e.target.checked })}
          />
          {form.create_login ? (
            <>
              <Field label="Password" hint="Leave blank to use the last 6 digits of his phone">
                <Input
                  type="text"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
              </Field>
              {!onRental ? (
                <Checkbox
                  label="He can see his own earnings"
                  checked={form.can_view_earnings}
                  onChange={(e) => setForm({ ...form, can_view_earnings: e.target.checked })}
                />
              ) : null}
            </>
          ) : null}
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create driver
          </Button>
        </div>
      </form>
    </Modal>
  )
}
