/* Scanning cartons off the vehicle with the phone's camera.
 *
 * Two decoders, chosen at runtime:
 *
 *   BarcodeDetector  Native, built into Chrome on Android. Costs no bytes, runs
 *                    on the GPU, and keeps up at 10fps on a cheap handset. Most
 *                    Target Express drivers are on Android Chrome, so this is
 *                    the path that matters.
 *   jsQR             Pure JavaScript fallback for iOS Safari and older Android.
 *                    Loaded only when the native one is missing, so the common
 *                    case never downloads it.
 *
 * Things learned from how this is actually used, which shape the whole file:
 *
 *   - A driver holds a carton in one hand. Every control is thumb-reachable at
 *     the bottom, and nothing requires precision.
 *   - It is often dark. There is a torch toggle where the camera supports one.
 *   - Scanning the same sticker twice in a second is normal, because the camera
 *     sees it on many frames. The same code is ignored for two seconds rather
 *     than fired at the server repeatedly.
 *   - Cameras fail. There is always a way to type the code instead, and the
 *     whole screen degrades to that rather than becoming a dead end.
 *   - Feedback has to be felt, not read: a phone in a noisy godown vibrates.
 */

import { Camera, CameraOff, Flashlight, Keyboard, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button, Field, Input } from '@/components/ui'

/** The native detector, where the browser has one. Not in TypeScript's DOM lib
 *  yet, so it is described here rather than cast away. */
interface NativeBarcodeDetector {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>
}
declare global {
  interface Window {
    BarcodeDetector?: {
      new (options?: { formats?: string[] }): NativeBarcodeDetector
      getSupportedFormats?: () => Promise<string[]>
    }
  }
}

/** Ignore a code we have just seen. The camera reads the same sticker on every
 *  frame; without this one carton would hit the server thirty times. */
const REPEAT_BLOCK_MS = 2000

export function BoxScanner({
  open,
  onClose,
  onCode,
  title,
  subtitle,
}: {
  open: boolean
  onClose: () => void
  /** Fired once per distinct code. The caller decides what it means. */
  onCode: (code: string) => void
  title: string
  subtitle?: string
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const rafRef = useRef<number>(0)
  const lastCode = useRef<{ code: string; at: number }>({ code: '', at: 0 })

  const [error, setError] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
  const [manual, setManual] = useState('')
  const [torchOn, setTorchOn] = useState(false)
  const [hasTorch, setHasTorch] = useState(false)

  const emit = useCallback(
    (code: string) => {
      const clean = code.trim()
      if (!clean) return

      const now = Date.now()
      if (clean === lastCode.current.code && now - lastCode.current.at < REPEAT_BLOCK_MS) return
      lastCode.current = { code: clean, at: now }

      // Felt, not read. A driver is looking at the carton, not the screen.
      navigator.vibrate?.(60)
      onCode(clean)
    },
    [onCode],
  )

  useEffect(() => {
    if (!open) return

    let cancelled = false
    let detector: NativeBarcodeDetector | null = null
    let jsQR: typeof import('jsqr').default | null = null

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          // The back camera, and a resolution high enough to resolve QR modules
          // at arm's length without asking a budget phone for 4K.
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }

        streamRef.current = stream
        const video = videoRef.current
        if (video) {
          video.srcObject = stream
          // iOS Safari refuses to play an inline video without both of these.
          video.setAttribute('playsinline', 'true')
          video.muted = true
          await video.play().catch(() => {})
        }

        const track = stream.getVideoTracks()[0]
        const caps = track?.getCapabilities?.() as { torch?: boolean } | undefined
        setHasTorch(!!caps?.torch)

        if (window.BarcodeDetector) {
          detector = new window.BarcodeDetector({ formats: ['qr_code'] })
        } else {
          // Only downloaded when the native decoder is absent.
          jsQR = (await import('jsqr')).default
        }

        tick()
      } catch (err) {
        if (cancelled) return
        const name = (err as DOMException)?.name
        setError(
          name === 'NotAllowedError'
            ? 'The camera is blocked. Allow camera access for this site, or type the code instead.'
            : name === 'NotFoundError'
              ? 'No camera found on this device. Type the code instead.'
              : 'The camera could not be started. Type the code instead.',
        )
        setTyping(true)
      }
    }

    async function tick() {
      if (cancelled) return
      const video = videoRef.current
      const canvas = canvasRef.current

      if (video && canvas && video.readyState === video.HAVE_ENOUGH_DATA) {
        try {
          if (detector) {
            const found = await detector.detect(video)
            if (found.length) emit(found[0].rawValue)
          } else if (jsQR) {
            const w = video.videoWidth
            const h = video.videoHeight
            if (w && h) {
              canvas.width = w
              canvas.height = h
              const ctx = canvas.getContext('2d', { willReadFrequently: true })
              if (ctx) {
                ctx.drawImage(video, 0, 0, w, h)
                const found = jsQR(ctx.getImageData(0, 0, w, h).data, w, h, {
                  inversionAttempts: 'dontInvert',
                })
                if (found?.data) emit(found.data)
              }
            }
          }
        } catch {
          // A frame that will not decode is the normal case, not a failure.
        }
      }

      rafRef.current = requestAnimationFrame(tick)
    }

    start()

    return () => {
      cancelled = true
      cancelAnimationFrame(rafRef.current)
      // Releasing the camera matters: a stream left running keeps the torch on
      // and the phone warm, and Android shows a recording indicator for it.
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [open, emit])

  async function toggleTorch() {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track) return
    const next = !torchOn
    try {
      // `torch` is a real constraint on Android Chrome but is not in the DOM
      // typings, so it goes through `unknown` rather than being faked into the
      // standard type.
      await track.applyConstraints({
        advanced: [{ torch: next }],
      } as unknown as MediaTrackConstraints)
      setTorchOn(next)
    } catch {
      setHasTorch(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[80] flex flex-col" style={{ background: '#000' }}>
      <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-white">{title}</p>
          {subtitle ? <p className="truncate text-[12.5px] text-white/60">{subtitle}</p> : null}
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-2 text-white/80"
          aria-label="Close the scanner"
        >
          <X className="size-5" />
        </button>
      </div>

      <div className="relative flex-1 overflow-hidden">
        <video
          ref={videoRef}
          className="absolute inset-0 h-full w-full object-cover"
          playsInline
          muted
        />
        <canvas ref={canvasRef} className="hidden" />

        {/* A frame to aim with. Nothing enforces it — the decoder reads the
            whole frame — but people centre a code inside a box without being
            told to, and that is what gets it in focus. */}
        {!error ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center">
            <div
              className="size-[62vw] max-h-[280px] max-w-[280px] rounded-3xl"
              style={{ boxShadow: '0 0 0 100vmax rgba(0,0,0,0.45)', border: '2px solid rgba(255,255,255,0.85)' }}
            />
          </div>
        ) : null}

        {error ? (
          <div className="absolute inset-0 grid place-items-center px-8 text-center">
            <div>
              <CameraOff className="mx-auto size-8 text-white/50" />
              <p className="mt-4 text-[13.5px] leading-relaxed text-white/80">{error}</p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="space-y-3 px-4 pt-3 pb-6" style={{ background: 'var(--bg)' }}>
        {typing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!manual.trim()) return
              emit(manual)
              setManual('')
            }}
            className="space-y-3"
          >
            <Field label="Type the code from the sticker">
              <Input
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                placeholder="TE-A7K2M-003"
                autoCapitalize="characters"
                autoFocus
              />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" size="lg" className="flex-1">
                Confirm box
              </Button>
              {!error ? (
                <Button
                  type="button"
                  size="lg"
                  variant="secondary"
                  onClick={() => setTyping(false)}
                  icon={<Camera className="size-4" />}
                >
                  Camera
                </Button>
              ) : null}
            </div>
          </form>
        ) : (
          <div className="flex gap-2">
            <Button
              size="lg"
              variant="secondary"
              className="flex-1"
              onClick={() => setTyping(true)}
              icon={<Keyboard className="size-4" />}
            >
              Type it instead
            </Button>
            {hasTorch ? (
              <Button
                size="lg"
                variant={torchOn ? 'primary' : 'secondary'}
                onClick={toggleTorch}
                icon={<Flashlight className="size-4" />}
                aria-pressed={torchOn}
              >
                Light
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
