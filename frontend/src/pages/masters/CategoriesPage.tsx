import { Package, Plus } from 'lucide-react'
import { useState } from 'react'

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
  Spinner,
  Table,
} from '@/components/ui'
import { RowActions } from '@/components/RowActions'
import { apiErrorMessage } from '@/lib/api'
import type { GoodsCategory } from '@/lib/resources'
import { useCreate, useList } from '@/lib/resources'

export default function CategoriesPage() {
  const [open, setOpen] = useState(false)
  const categories = useList<GoodsCategory & { is_fragile: boolean; is_bulky: boolean }>(
    '/goods-categories',
  )

  return (
    <div className="space-y-6">
      <PageHeader
        description="Spare parts, furniture, appliances. A category is attached to a vendor division, and it is what decides whether unloading is billed at all — spare parts are not, furniture is."
        action={
          <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New category
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {categories.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-5" />
          </div>
        ) : (
          <Table
            rows={categories.data ?? []}
            rowKey={(c) => c.id}
            empty={
              <EmptyState
                icon={<Package className="size-7" />}
                title="No goods categories yet"
                description="Add these first — a vendor division points at one, and it drives how unloading is charged."
                action={<Button onClick={() => setOpen(true)}>New category</Button>}
              />
            }
            columns={[
              {
                key: 'name',
                header: 'Category',
                render: (c) => <span className="font-medium">{c.name}</span>,
              },
              { key: 'code', header: 'Code', render: (c) => <span className="tnum">{c.code}</span> },
              {
                key: 'handling',
                header: 'Handling',
                render: (c) => (
                  <span className="flex flex-wrap gap-1.5">
                    {c.is_fragile ? <Badge tone="warning">Fragile</Badge> : null}
                    {c.is_bulky ? <Badge tone="info">Bulky</Badge> : null}
                    {!c.is_fragile && !c.is_bulky ? (
                      <span style={{ color: 'var(--text-faint)' }}>Standard</span>
                    ) : null}
                  </span>
                ),
              },
                          {
                key: 'actions',
                header: '',
                align: 'right' as const,
                render: (r) => (
                  <RowActions
                    path={'/goods-categories'}
                    row={r as unknown as Record<string, unknown> & { id: string }}
                    label="Category"
                    fields={[
                      { name: 'name', label: 'Name', required: true },
                      { name: 'code', label: 'Code', required: true },
                      { name: 'is_fragile', label: 'Fragile', kind: 'checkbox' as const },
                      { name: 'is_bulky', label: 'Bulky', kind: 'checkbox' as const },
                    ]}
                  />
                ),
              },
]}
          />
        )}
      </Card>

      <CategoryForm open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

function CategoryForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const blank = { name: '', code: '', is_fragile: false, is_bulky: false }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)

  const create = useCreate<typeof form>('/goods-categories', {
    onSuccess: () => {
      setForm(blank)
      onClose()
    },
  })

  return (
    <Modal open={open} onClose={onClose} title="New goods category">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          create.mutate(
            { ...form, code: form.code.toUpperCase() },
            { onError: (err) => setError(apiErrorMessage(err)) },
          )
        }}
      >
        <Field label="Name">
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Spare Parts"
            required
          />
        </Field>
        <Field label="Code" hint="Short identifier used across the system">
          <Input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="SPARES"
            required
          />
        </Field>

        <div className="space-y-2.5">
          <Checkbox
            label="Fragile — handle with care at sorting and loading"
            checked={form.is_fragile}
            onChange={(e) => setForm({ ...form, is_fragile: e.target.checked })}
          />
          <Checkbox
            label="Bulky — unloading is priced per article rather than per box"
            checked={form.is_bulky}
            onChange={(e) => setForm({ ...form, is_bulky: e.target.checked })}
          />
        </div>

        <ErrorNote>{error}</ErrorNote>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create category
          </Button>
        </div>
      </form>
    </Modal>
  )
}
