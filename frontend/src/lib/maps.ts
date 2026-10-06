/* Google Maps hand-off.
 *
 * Deliberately free of any map library: drivers open these links on a phone,
 * and there is no reason to ship them a mapping bundle to build a URL.
 */

interface Stop {
  latitude?: number | null
  longitude?: number | null
  address?: string | null
}

function asWaypoint(stop: Stop): string | null {
  if (stop.latitude != null && stop.longitude != null) {
    return `${stop.latitude},${stop.longitude}`
  }
  return stop.address ? encodeURIComponent(stop.address) : null
}

/**
 * Directions through every stop in order — the "add stop" route a driver would
 * otherwise build by hand. The last stop becomes the destination and the rest
 * become waypoints, which is how Google Maps expects a multi-stop route.
 */
export function multiStopMapsUrl(stops: Stop[], origin?: Stop | null): string | null {
  const usable = stops.map(asWaypoint).filter((s): s is string => !!s)
  if (!usable.length) return null

  const params = new URLSearchParams({
    api: '1',
    destination: usable[usable.length - 1],
    travelmode: 'driving',
  })

  const waypoints = usable.slice(0, -1)
  if (waypoints.length) params.set('waypoints', waypoints.join('|'))

  const from = origin ? asWaypoint(origin) : null
  if (from) params.set('origin', from)

  return `https://www.google.com/maps/dir/?${params.toString()}`
}

/** Directions to one stop. */
export function singleStopMapsUrl(stop: Stop): string | null {
  const destination = asWaypoint(stop)
  if (!destination) return null
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}&travelmode=driving`
}
