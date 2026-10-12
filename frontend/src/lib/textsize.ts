import { useSyncExternalStore } from 'react'

export type TextSize = 'normal' | 'large' | 'larger'

const STORAGE_KEY = 'tx.textsize'
const listeners = new Set<() => void>()

/** How big everything is, chosen by the person reading it.
 *
 *  This exists because the people using this are not the people who designed
 *  it. A godown clerk in their fifties reading a bill number off a phone, and
 *  a driver checking a stop in a cab at night, are not served by type chosen
 *  on a large bright monitor — and the honest answer is that nobody can pick
 *  one size that suits a 24-inch desk and a cracked phone screen at once.
 *
 *  So the choice is handed over rather than guessed at. Three steps, kept in
 *  the browser, applied once at the root.
 *
 *  Implemented as a scale on the whole interface rather than a font-size
 *  change, deliberately. The type scale here is in pixels, so a larger root
 *  font would move nothing; scaling moves the text, the padding, the icons and
 *  the tap targets together, which is what someone asking for "bigger" means.
 *  The navigation rail is excluded — it is sized to fit its items exactly, and
 *  scaling it would push the last few off the bottom. */
const SCALE: Record<TextSize, string> = {
  normal: '1',
  large: '1.12',
  larger: '1.25',
}

export const TEXT_SIZE_LABELS: Record<TextSize, string> = {
  normal: 'Normal',
  large: 'Large',
  larger: 'Largest',
}

function read(): TextSize {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'normal' || stored === 'large' || stored === 'larger') return stored
  } catch {
    /* private browsing - fall through to the default */
  }
  return 'normal'
}

let current: TextSize = read()

function apply() {
  const root = document.documentElement
  root.setAttribute('data-text-size', current)
  root.style.setProperty('--tx-scale', SCALE[current])
}

function emit() {
  apply()
  listeners.forEach((l) => l())
}

export function setTextSize(size: TextSize) {
  current = size
  try {
    localStorage.setItem(STORAGE_KEY, size)
  } catch {
    /* preference simply will not persist */
  }
  emit()
}

/** Applied before React renders, so nothing jumps size on load. */
export function initTextSize() {
  apply()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useTextSize(): TextSize {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => 'normal' as TextSize,
  )
}
