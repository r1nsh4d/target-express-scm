import L from 'leaflet'
import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap } from 'react-leaflet'

import 'leaflet/dist/leaflet.css'

/* The lorry and the door, on one map.
 *
 * Read-only on purpose. This is the customer's page: they want to see where it
 * is and roughly how far, not to pan around a map. So it fits both points in
 * the frame, draws the line between them, and leaves the controls off — a
 * dragged map on a phone is a map nobody can get back.
 *
 * The line is straight, and it is drawn dashed for that reason. A solid line
 * would read as the route, which this is not: it is the distance, and the
 * estimate beside it already says the road is longer.
 */

const LORRY = L.divIcon({
  className: '',
  html: `<div style="
    width:30px;height:30px;border-radius:50%;
    background:#22d3ee;border:3px solid #06080d;
    box-shadow:0 2px 10px rgba(0,0,0,.5);
    display:grid;place-items:center;font-size:15px;line-height:1">🚚</div>`,
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

const DOOR = L.divIcon({
  className: '',
  html: `<div style="
    width:22px;height:22px;border-radius:50% 50% 50% 0;
    transform:rotate(-45deg);
    background:#a78bfa;border:3px solid #06080d;
    box-shadow:0 2px 8px rgba(0,0,0,.5)"></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 22],
})

/* Fit both ends in the frame, and keep them there.
 *
 * Also the place where Leaflet is told how big it is: it measures its
 * container once at mount, and on a card that is still settling it caches a
 * size that no longer applies and loads tiles for a viewport that does not
 * exist — a map that comes up half drawn with grey where the rest should be. */
function Frame({ points }: { points: [number, number][] }) {
  const map = useMap()

  useEffect(() => {
    const settle = () => {
      map.invalidateSize({ animate: false })
      if (points.length > 1) {
        map.fitBounds(L.latLngBounds(points), { padding: [38, 38], maxZoom: 14 })
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

export function TrackMap({
  vehicle,
  destination,
  height = 220,
}: {
  vehicle: { latitude: number; longitude: number } | null
  destination: { latitude: number; longitude: number } | null
  height?: number
}) {
  const points: [number, number][] = []
  if (vehicle) points.push([vehicle.latitude, vehicle.longitude])
  if (destination) points.push([destination.latitude, destination.longitude])
  if (!points.length) return null

  return (
    <div
      className="overflow-hidden"
      style={{ height, borderRadius: 'var(--radius-control)' }}
    >
      <MapContainer
        center={points[0]}
        zoom={12}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
        scrollWheelZoom={false}
        dragging={false}
        doubleClickZoom={false}
        touchZoom={false}
        keyboard={false}
        attributionControl={false}
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Frame points={points} />
        {vehicle && destination ? (
          <Polyline
            positions={points}
            pathOptions={{ color: '#22d3ee', weight: 2, opacity: 0.55, dashArray: '5 7' }}
          />
        ) : null}
        {destination ? (
          <Marker position={[destination.latitude, destination.longitude]} icon={DOOR} />
        ) : null}
        {vehicle ? <Marker position={[vehicle.latitude, vehicle.longitude]} icon={LORRY} /> : null}
      </MapContainer>
    </div>
  )
}
