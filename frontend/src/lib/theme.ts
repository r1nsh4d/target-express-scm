import { useSyncExternalStore } from 'react'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'tx.theme'
const listeners = new Set<() => void>()

/** Dark by default, with light fully supported and one click away.
 *
 *  The accent only reads as light against something dark — on a pale canvas a
 *  glow is just a tint. Dark is also the right default for where this is used:
 *  a godown at 5am, a control desk with the lights off, a driver's phone in a
 *  cab. Anyone who reads tables all day flips it in the top right and it sticks. */
function read(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* private browsing - fall through to the default */
  }
  return 'dark'
}

let current: Theme = read()

function emit() {
  document.documentElement.setAttribute('data-theme', current)
  listeners.forEach((l) => l())
}

export function setTheme(theme: Theme) {
  current = theme
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    /* preference simply will not persist */
  }
  emit()
}

export function toggleTheme() {
  setTheme(current === 'dark' ? 'light' : 'dark')
}

/** Apply the stored theme before React renders, so there is no flash. */
export function initTheme() {
  document.documentElement.setAttribute('data-theme', current)
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Shared so the logo can pick its variant without prop-drilling the theme. */
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => 'dark' as Theme,
  )
}
