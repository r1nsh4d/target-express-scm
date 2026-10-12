import { api } from '@/lib/api'

/* Sending the lorry's position while the trip is running.
 *
 * The customer's tracking page has always been able to draw a vehicle. This is
 * what finally gives it one.
 *
 * Written around the fact that a lorry on the Kasaragod road loses signal for
 * twenty minutes at a time, and that the points collected during those twenty
 * minutes are the interesting ones. So nothing is sent directly: every fix goes
 * into a buffer in the phone's own storage first, and the buffer is flushed
 * when there is a connection. If the send fails the points stay put and go with
 * the next attempt.
 *
 * It survives the browser being closed, because a driver checking WhatsApp
 * mid-route is the normal case rather than an edge one.
 */

const KEY = 'tx.pings'
const MAX_BUFFERED = 400

interface Ping {
  latitude: number
  longitude: number
  accuracy_m?: number
  speed_kmph?: number
  recorded_at: string
}

function read(): Record<string, Ping[]> {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Record<string, Ping[]>) : {}
  } catch {
    // Corrupt or blocked storage must not stop a delivery being recorded.
    return {}
  }
}

function write(all: Record<string, Ping[]>) {
  try {
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    /* full or private — the points for this stretch are simply lost */
  }
}

function buffer(legId: string, ping: Ping) {
  const all = read()
  const existing = all[legId] ?? []
  // A phone out of signal for three hours should not accumulate a backlog so
  // large that the first successful send times out. The oldest go first: a
  // position from two hours ago is worth less than the one from a minute ago.
  all[legId] = [...existing, ping].slice(-MAX_BUFFERED)
  write(all)
}

/** Send whatever is buffered for this leg. Keeps it on failure. */
export async function flushPings(legId: string): Promise<void> {
  const all = read()
  const pending = all[legId]
  if (!pending?.length) return

  try {
    await api.post(`/driver/legs/${legId}/pings`, { pings: pending })
    // Re-read rather than reusing `all`: a fix may have been buffered while
    // the request was in flight, and overwriting would discard it.
    const after = read()
    after[legId] = (after[legId] ?? []).slice(pending.length)
    write(after)
  } catch {
    /* No signal, or the server is unreachable. They stay buffered. */
  }
}

/* Watch the phone's position for as long as the trip is open.
 *
 * Returns a function that stops the watch and makes one last attempt to send
 * what is left — the driver closing the app at the end of a run should not
 * take the last stretch of the route with him.
 */
export function trackLeg(legId: string): () => void {
  if (!navigator.geolocation) return () => {}

  const onFix = (pos: GeolocationPosition) => {
    buffer(legId, {
      latitude: pos.coords.latitude,
      longitude: pos.coords.longitude,
      accuracy_m: pos.coords.accuracy ? Math.round(pos.coords.accuracy) : undefined,
      speed_kmph:
        pos.coords.speed != null && pos.coords.speed >= 0
          ? Math.round(pos.coords.speed * 3.6 * 10) / 10
          : undefined,
      recorded_at: new Date(pos.timestamp).toISOString(),
    })
  }

  const watch = navigator.geolocation.watchPosition(onFix, () => {}, {
    enableHighAccuracy: true,
    // A fix up to a minute old is fine for a lorry and saves a great deal of
    // battery over insisting on a fresh one.
    maximumAge: 60_000,
    timeout: 30_000,
  })

  // Every 90 seconds. Often enough that a customer watching the map sees
  // movement, rare enough that it is not a drain on a phone that also has to
  // last the day.
  const timer = window.setInterval(() => void flushPings(legId), 90_000)
  void flushPings(legId)

  // The app going to the background is the most likely moment to lose points,
  // so flush on the way out rather than waiting for the next interval.
  const onHide = () => {
    if (document.visibilityState === 'hidden') void flushPings(legId)
  }
  document.addEventListener('visibilitychange', onHide)

  return () => {
    navigator.geolocation.clearWatch(watch)
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', onHide)
    void flushPings(legId)
  }
}

/** How many fixes are waiting to be sent, for the driver's own reassurance. */
export function bufferedCount(legId: string): number {
  return read()[legId]?.length ?? 0
}
