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
import { byName, useFilters } from '@/components/Filters'
import { Fact, Facts, TileGrid, TileHead } from '@/components/TileGrid'
import { DriverDetail } from '@/components/Profiles'
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { Driver, Vehicle, VehicleOwner } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'
import { useOpenOnNewParam } from '@/lib/motion'

export default function DriversPage() {
  const [open, setOpen] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)

  // The command palette's "New …" lands here with ?new=1.
  useOpenOnNewParam(useCallback(() => setOpen(true), []))
  const drivers = useList<Driver>('/drivers')
  const vehicles = useList<Vehicle>('/vehicles')
  const owners = useList<VehicleOwner>('/vehicle-owners')

  // Every owner, for the form: a man is given to an owner who has nobody yet.
  const ownerOptions = (owners.data ?? []).map((o) => ({ value: o.id, label: o.name }))

  const all = drivers.data ?? []

  /* Only the owners somebody is actually on, for the filter. A choice that
     empties the list is a dead end, and most owners here have no driver on
     file at all. */
  const withDrivers = new Set(all.map((d) => d.vehicle_owner_id).filter(Boolean))
  const view = useFilters<Driver>({
    rows: all,
    placeholder: 'Search by name or phone',
    search: (d) => [d.name, d.phone, d.licence_no, d.vehicle_owner_name],
    filters: [
      {
        /* Whose man he is, which is also who pays him.
           One owner with four lorries and three drivers is ordinary, so
           "on a rented vehicle" was not a useful answer on its own — the
           question people ask is "who are Ibrahim's drivers". */
        key: 'whose',
        label: 'Whose driver',
        choices: [
          ...(all.some((d) => !d.vehicle_owner_id)
            ? [{ value: 'ours', label: 'Target Express' }]
            : []),
          ...ownerOptions.filter((o) => withDrivers.has(o.value)),
        ],
        matches: (d, v) =>
          v === 'ours' ? !d.vehicle_owner_id : d.vehicle_owner_id === v,
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
        key: 'whose',
        label: 'By whose they are',
        // Ours first, then each owner's men together.
        compare: (a, b) =>
          (a.vehicle_owner_name ?? '').localeCompare(b.vehicle_owner_name ?? '') ||
          a.name.localeCompare(b.name),
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
                  /* Whose man he is, not just that he is somebody's.
                     A name is the answer people are after, and "on a rented
                     vehicle" against three men from three owners tells them
                     nothing they can act on. */
                  <Badge tone={d.vehicle_owner_id ? 'info' : 'success'}>
                    {d.vehicle_owner_id
                      ? d.is_the_owner
                        ? 'Owner-driver'
                        : (d.vehicle_owner_name ?? "An owner's man")
                      : 'Target Express'}
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
                      {
                        name: 'vehicle_owner_id',
                        label: 'Whose driver is he',
                        kind: 'select' as const,
                        blank: 'Target Express',
                        hint: 'An owner pays his own men out of what we pay for the lorry',
                        options: ownerOptions,
                        // Null is a real answer here, so it travels with a flag.
                        sendWith: { set_owner: true },
                      },
                    ]}
                  />
                }
              />
              <Facts>
                {/* Who pays him for driving, which is the one thing about an
                    outside driver that changes what the office does. */}
                <Fact
                  label="Paid by"
                  value={d.vehicle_owner_id ? (d.vehicle_owner_name ?? 'His owner') : 'Target Express'}
                />
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

      <DriverForm
        open={open}
        onClose={() => setOpen(false)}
        vehicles={vehicles.data ?? []}
        owners={owners.data ?? []}
      />
    </div>
  )
}

function DriverForm({
  open,
  onClose,
  vehicles,
  owners,
}: {
  open: boolean
  onClose: () => void
  vehicles: Vehicle[]
  owners: VehicleOwner[]
}) {
  const blank = {
    name: '',
    phone: '',
    vehicle_owner_id: '',
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
  /* Whose man he is decides everything else on this form: who pays him by
     the kilometre, whether he is shown money at all, and which lorries he
     should be offered for. One question instead of an `engagement` the
     office had to keep in step by hand. */
  const onRental = form.vehicle_owner_id !== ''
  const owner = owners.find((o) => o.id === form.vehicle_owner_id)

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
              vehicle_owner_id: form.vehicle_owner_id || null,
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

        <Field
          label="Whose driver is he"
          hint="An outside lorry's driver is paid by its owner, not by us"
        >
          <Select
            value={form.vehicle_owner_id}
            onChange={(e) => setForm({ ...form, vehicle_owner_id: e.target.value })}
          >
            <option value="">Target Express — our own staff</option>
            {owners.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>

        {onRental ? (
          <p
            className="rounded-lg border px-3.5 py-2.5 text-[12.5px]"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            An outside lorry is paid for as a lorry: one amount to{' '}
            {owner?.name ?? 'its owner'} covering the run and the unloading both. Whatever{' '}
            {owner?.name ?? 'he'} pays this man is between the two of them, so there is no
            per-km rate to set here and his earnings screen is switched off. He gets a
            login to run trips and update deliveries, nothing more.
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
