import L from 'leaflet'
import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap } from 'react-leaflet'

import 'leaflet/dist/leaflet.css'

/* The whole run on one map, for the driver.
 *
 * He has had deep links into Google Maps from the start, and those are still
 * the right thing for actually driving — Google knows the roads and this does
 * not. What was missing is the shape of the day: how many stops, in what
 * order, how far apart, and which are already done. A list of six towns does
 * not tell him he is about to double back.
 *
 * So the markers are NUMBERED in delivery order and the done ones go grey,
 * and that is the whole job. The line between them is dashed because it is
 * the order, not the route; drawing a solid line would claim a road exists
 * where there may be a river.
 */

interface Stop {
  sequence: number
  consignee_name: string
  latitude: number | null
  longitude: number | null
  status: string
}

const DONE = new Set(['DELIVERED', 'PART_DELIVERED', 'FAILED', 'SKIPPED'])

function pin(label: string, background: string, muted = false) {
  return L.divIcon({
    className: '',
    html: `<div style="
      width:26px;height:26px;border-radius:50%;
      background:${background};border:2px solid #06080d;
      box-shadow:0 2px 8px rgba(0,0,0,.5);
      display:grid;place-items:center;
      font:600 12px/1 system-ui,sans-serif;
      color:${muted ? '#9aa4b2' : '#04121a'};
      ${muted ? 'opacity:.65;' : ''}">${label}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

const DEPOT = L.divIcon({
  className: '',
  html: `<div style="
    width:24px;height:24px;border-radius:5px;
    background:#e5e7eb;border:2px solid #06080d;
    box-shadow:0 2px 8px rgba(0,0,0,.5);
    display:grid;place-items:center;font-size:12px;line-height:1">🏠</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

const HERE = L.divIcon({
  className: '',
  html: `<div style="
    width:30px;height:30px;border-radius:50%;
    background:#22d3ee;border:3px solid #06080d;
    box-shadow:0 2px 12px rgba(34,211,238,.6);
    display:grid;place-items:center;font-size:15px;line-height:1">🚚</div>`,
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

/* Fit everything in frame, and tell Leaflet how big it is.
   It measures its container once at mount, and inside a card that is still
   settling it caches a size that no longer applies — tiles load for a viewport
   that does not exist and the map comes up half drawn. */
function Frame({ points }: { points: [number, number][] }) {
  const map = useMap()

  useEffect(() => {
    const settle = () => {
      map.invalidateSize({ animate: false })
      if (points.length > 1) {
        map.fitBounds(L.latLngBounds(points), { padding: [34, 34], maxZoom: 13 })
      } else if (points.length === 1) {
        map.setView(points[0], 13)
      }
    }
    const timers = [60, 320].map((ms) => window.setTimeout(settle, ms))
    const observer = new ResizeObserver(settle)
    observer.observe(map.getContainer())
    return () => {
      timers.forEach(window.clearTimeout)
      observer.disconnect()
    }
  }, [map, points])

  return null
}

export function RouteMap({
  stops,
  origin,
  here,
  height = 240,
}: {
  stops: Stop[]
  /** The warehouse the run starts and ends at. */
  origin?: { latitude: number | null; longitude: number | null } | null
  /** Where the lorry is now, if it has reported. */
  here?: { latitude: number; longitude: number } | null
  height?: number
}) {
  const placed = stops
    .filter((s) => s.latitude != null && s.longitude != null)
    .sort((a, b) => a.sequence - b.sequence)

  // A map with nothing on it is worse than no map. The screen says why
  // instead — pins are set on the customer, not here.
  if (!placed.length) return null

  const line: [number, number][] = []
  if (origin?.latitude != null && origin.longitude != null) {
    line.push([origin.latitude, origin.longitude])
  }
  for (const s of placed) line.push([s.latitude as number, s.longitude as number])
  // Back to the warehouse: a freight is finished when the vehicle is home,
  // and the return leg is real distance the driver is paid for.
  if (line.length > 1 && origin?.latitude != null && origin.longitude != null) {
    line.push([origin.latitude, origin.longitude])
  }

  const frame = here ? [...line, [here.latitude, here.longitude] as [number, number]] : line

  return (
    <div className="overflow-hidden" style={{ height, borderRadius: 'var(--radius-control)' }}>
      <MapContainer
        center={line[0]}
        zoom={11}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
        scrollWheelZoom={false}
        attributionControl={false}
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Frame points={frame} />

        {line.length > 1 ? (
          <Polyline
            positions={line}
            pathOptions={{ color: '#22d3ee', weight: 2, opacity: 0.5, dashArray: '5 7' }}
          />
        ) : null}

        {origin?.latitude != null && origin.longitude != null ? (
          <Marker position={[origin.latitude, origin.longitude]} icon={DEPOT} />
        ) : null}

        {placed.map((s) => (
          <Marker
            key={s.sequence}
            position={[s.latitude as number, s.longitude as number]}
            icon={pin(
              String(s.sequence),
              DONE.has(s.status) ? '#4b5563' : '#a78bfa',
              DONE.has(s.status),
            )}
            title={`${s.sequence}. ${s.consignee_name}`}
          />
        ))}

        {here ? <Marker position={[here.latitude, here.longitude]} icon={HERE} /> : null}
      </MapContainer>
    </div>
  )
}
