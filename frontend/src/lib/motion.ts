/* Motion primitives.
 *
 * Three rules this file exists to enforce:
 *   1. Motion explains a change. Something arrived, something is live, something
 *      is loading. Nothing animates for decoration.
 *   2. Everything respects prefers-reduced-motion, and respects it by jumping to
 *      the final state — never by getting stuck at the start.
 *   3. Nothing runs off the main thread budget. IntersectionObserver for reveals,
 *      rAF for counters, and both unhook themselves.
 */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Stagger helper: `style={stagger(i)}` on a list gives each row its own delay.
 *  Capped, because the twentieth row of a table should not wait a second and a
 *  half to appear. */
export function stagger(index: number, step = 45, max = 320): React.CSSProperties {
  return { ['--d' as string]: `${Math.min(index * step, max)}ms` }
}

/** Reveals children as they scroll into view.
 *
 *  Returns a ref for the container; every descendant carrying `.tx-reveal` gets
 *  `.is-in` once it has been seen, and is then unobserved — a section that has
 *  arrived should not animate again when you scroll back up. */
export function useRevealOnScroll<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null)

  useEffect(() => {
    const root = ref.current
    if (!root) return

    const targets = Array.from(root.querySelectorAll<HTMLElement>('.tx-reveal'))
    if (targets.length === 0) return

    if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined') {
      targets.forEach((el) => el.classList.add('is-in'))
      return
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add('is-in')
          io.unobserve(entry.target)
        }
      },
      // Fire a little before the element reaches the fold, so it is already
      // settled by the time it is properly in view.
      { rootMargin: '0px 0px -12% 0px', threshold: 0.08 },
    )

    targets.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  return ref
}

/** Counts a number up when it changes.
 *
 *  Used on dashboard headline figures. The point is not the flourish — it is
 *  that a number which MOVED is visibly different from one that was always
 *  there, so a figure updating under you is noticed rather than missed. */
export function useCountUp(target: number, duration = 900): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0))
  const fromRef = useRef(0)

  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target)
      return
    }

    const from = fromRef.current
    const delta = target - from
    if (delta === 0) {
      setValue(target)
      return
    }

    let raf = 0
    const started = performance.now()

    const tick = (now: number) => {
      const t = Math.min((now - started) / duration, 1)
      // easeOutExpo: fast to begin with, so the figure is readable early and
      // only the last digit is still settling.
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
      setValue(Math.round(from + delta * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = target
    }

    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return value
}

/** True once the component has been mounted for a moment — for entrance states
 *  that cannot be expressed as a CSS animation-delay alone. */
export function useMounted(delay = 0): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setOn(true), delay)
    return () => clearTimeout(id)
  }, [delay])
  return on
}

/** Fires once when the URL carries `?new=1`, then strips the flag.
 *
 *  The command palette's "New vendor" sends you to /vendors?new=1 rather than
 *  carrying its own copy of the create form. One form per thing, in the screen
 *  that owns it — a second copy in the palette is a second copy to keep in step.
 *
 *  The flag is removed with `replace`, so Back does not reopen the dialog.
 */
export function useOpenOnNewParam(onOpen: () => void) {
  const [params, setParams] = useSearchParams()
  const fired = useRef(false)

  useEffect(() => {
    if (fired.current || params.get('new') !== '1') return
    fired.current = true

    const next = new URLSearchParams(params)
    next.delete('new')
    setParams(next, { replace: true })
    onOpen()
  }, [params, setParams, onOpen])
}
