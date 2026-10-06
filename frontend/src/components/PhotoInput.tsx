import { useMutation } from '@tanstack/react-query'
import { Camera, Check, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { Spinner } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

/* Take or choose a photograph and store it.
 *
 * `capture="environment"` opens the rear camera straight away on a phone, which
 * is what a driver at a doorstep wants — not a file browser.
 */

export type PhotoKind = 'loading' | 'delivery' | 'odometer' | 'receipt' | 'signature' | 'other'

export function PhotoInput({
  kind,
  value,
  onChange,
  label = 'Add photo',
}: {
  kind: PhotoKind
  value: string | null
  onChange: (url: string | null) => void
  label?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData()
      body.append('file', file)
      body.append('kind', kind)
      const res = await api.post<{ url: string }>('/uploads', body, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data.url
    },
    onSuccess: (url) => {
      setError(null)
      onChange(url)
    },
    onError: (e) => setError(apiErrorMessage(e, 'Could not upload that photo')),
  })

  if (value) {
    return (
      <div className="space-y-2">
        <div
          className="relative overflow-hidden"
          style={{ borderRadius: 'var(--radius-control)', boxShadow: 'var(--neu-inset)' }}
        >
          <img src={value} alt="" className="h-36 w-full object-cover" />
          <button
            type="button"
            onClick={() => onChange(null)}
            className="absolute top-2 right-2 grid size-7 place-items-center rounded-full"
            style={{ background: 'rgba(0,0,0,0.6)', color: '#fff' }}
            aria-label="Remove photo"
          >
            <X className="size-3.5" />
          </button>
        </div>
        <p className="flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--success)' }}>
          <Check className="size-3.5" />
          Photo attached
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload.mutate(file)
          e.target.value = ''
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
        className="flex h-24 w-full flex-col items-center justify-center gap-2 text-[13px] transition-[box-shadow] active:[box-shadow:var(--neu-pressed)]"
        style={{
          background: 'var(--bg)',
          color: 'var(--text-muted)',
          borderRadius: 'var(--radius-control)',
          boxShadow: 'var(--neu-inset)',
        }}
      >
        {upload.isPending ? (
          <>
            <Spinner className="size-5" />
            Uploading…
          </>
        ) : (
          <>
            <Camera className="size-5" />
            {label}
          </>
        )}
      </button>
      {error ? (
        <p className="text-[12px]" style={{ color: 'var(--danger)' }}>
          {error}
        </p>
      ) : null}
    </div>
  )
}
