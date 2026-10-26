import { useMutation } from '@tanstack/react-query'
import { Check, FileSpreadsheet, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button, ErrorNote, Select } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

/* The vendor's own spreadsheet, dropped straight in.
 *
 * The day's bills arrive as a file long before anybody types them, and typing
 * thirty-eight rows that already exist in a spreadsheet is the most obviously
 * wasted half hour in the whole operation.
 *
 * Two steps on purpose. The file is read and the columns are GUESSED, then the
 * guess is shown and confirmed before a single bill is created. Every vendor's
 * sheet is laid out differently, and being quietly wrong about which column is
 * the box count puts the wrong number on a sticker a driver counts against at
 * the door. A wrong guess costs one dropdown; a silent wrong guess costs a
 * short delivery nobody can explain.
 *
 * What it produces is the same one-bill-per-line text somebody would have
 * typed, handed to the existing parser — so the matching, the duplicate check
 * and the new-customer handling are all the ones already proven.
 */

interface Preview {
  columns: string[]
  sample: string[][]
  row_count: number
  mapping: Record<string, string>
  sheet_name: string | null
  notes: string[]
}

const FIELDS: { value: string; label: string }[] = [
  { value: '', label: 'Ignore this column' },
  { value: 'vendor_bill_no', label: 'Bill number' },
  { value: 'customer', label: 'Customer' },
  { value: 'box_count', label: 'Boxes' },
  { value: 'item_name', label: 'Article' },
]

const NEEDED = ['vendor_bill_no', 'customer', 'box_count']

export function SheetDrop({ onRead }: { onRead: (lines: string) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Record<number, string>>({})
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const read = useMutation({
    mutationFn: async (chosen: File) => {
      const form = new FormData()
      form.append('file', chosen)
      return (await api.post<Preview>('/daysheet/upload', form)).data
    },
    onSuccess: (data) => {
      setPreview(data)
      setMapping(
        Object.fromEntries(Object.entries(data.mapping).map(([k, v]) => [Number(k), v])),
      )
    },
    onError: (e) => {
      setError(apiErrorMessage(e))
      setFile(null)
    },
  })

  const convert = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.append('file', file!)
      form.append('mapping', JSON.stringify(mapping))
      return (await api.post<{ text: string }>('/daysheet/upload/lines', form)).data
    },
    onSuccess: (data) => {
      onRead(data.text)
      reset()
    },
    onError: (e) => setError(apiErrorMessage(e)),
  })

  function take(chosen: File | null | undefined) {
    if (!chosen) return
    setError(null)
    setPreview(null)
    setFile(chosen)
    read.mutate(chosen)
  }

  function reset() {
    setFile(null)
    setPreview(null)
    setMapping({})
    setError(null)
    if (input.current) input.current.value = ''
  }

  const chosen = new Set(Object.values(mapping))
  const missing = NEEDED.filter((f) => !chosen.has(f))

  if (!file) {
    return (
      <>
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            take(e.dataTransfer.files?.[0])
          }}
          className="mb-3 flex w-full items-center justify-center gap-2.5 rounded-[var(--radius-control)] border border-dashed px-4 py-3 text-[13px] transition-colors"
          style={{
            borderColor: dragging ? 'var(--accent)' : 'var(--border-strong)',
            background: dragging ? 'var(--accent-dim)' : 'transparent',
            color: dragging ? 'var(--accent)' : 'var(--text-muted)',
          }}
        >
          <Upload className="size-4" />
          Drop the vendor&rsquo;s Excel here, or click to choose
        </button>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.xlsm,.csv,.txt,.xls"
          className="hidden"
          onChange={(e) => take(e.target.files?.[0])}
        />
        <ErrorNote>{error}</ErrorNote>
      </>
    )
  }

  return (
    <div
      className="mb-3 rounded-[var(--radius-card)] border p-3.5"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
    >
      <div className="flex items-start gap-2.5">
        <FileSpreadsheet className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--accent)' }} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium">{file.name}</p>
          {preview ? (
            <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              {preview.row_count} rows
              {preview.sheet_name ? ` · ${preview.sheet_name}` : ''}
            </p>
          ) : (
            <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              Reading&hellip;
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={reset}
          className="rounded p-1 hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-muted)' }}
          aria-label="Remove this file"
        >
          <X className="size-4" />
        </button>
      </div>

      {preview ? (
        <>
          {preview.notes.length ? (
            <div
              className="mt-3 rounded-[var(--radius-control)] px-3 py-2 text-[12px]"
              style={{
                background: 'color-mix(in oklab, var(--warning) 10%, transparent)',
                color: 'var(--text)',
              }}
            >
              {preview.notes.map((n) => (
                <p key={n}>{n}</p>
              ))}
            </div>
          ) : null}

          {/* The guess, shown for confirmation. Never acted on quietly. */}
          <p className="mt-3 mb-1.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Which column is which?
          </p>
          <div className="space-y-1.5">
            {preview.columns.map((name, i) => (
              <div key={`${name}-${i}`} className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-medium">{name}</p>
                  <p
                    className="truncate font-mono text-[11px]"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    {preview.sample[0]?.[i] || '—'}
                  </p>
                </div>
                {/* The width is on the wrapper, not the control: `Select`
                    carries `w-full` of its own and would win, taking the
                    whole row and pushing the column name out of sight. */}
                <div className="w-[11rem] shrink-0">
                  <Select
                    value={mapping[i] ?? ''}
                    onChange={(e) =>
                      setMapping((current) => {
                        const next = { ...current }
                        if (e.target.value) next[i] = e.target.value
                        else delete next[i]
                        return next
                      })
                    }
                  >
                    {FIELDS.map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.label}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
            ))}
          </div>

          <ErrorNote>{error}</ErrorNote>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-[12px]" style={{ color: missing.length ? 'var(--warning)' : 'var(--text-muted)' }}>
              {missing.length
                ? `Still need: ${missing.map((m) => FIELDS.find((f) => f.value === m)?.label).join(', ')}`
                : `${preview.row_count} rows ready to read`}
            </span>
            <Button
              size="sm"
              icon={<Check className="size-4" />}
              disabled={missing.length > 0}
              loading={convert.isPending}
              onClick={() => {
                setError(null)
                convert.mutate()
              }}
            >
              Use this file
            </Button>
          </div>
        </>
      ) : null}
    </div>
  )
}
