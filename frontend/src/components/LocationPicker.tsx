import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Crosshair, MapPin, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { Button, Field, Input } from '@/components/ui'

/* Pick a delivery location, either by dropping a pin or by typing coordinates.
 *
 * OpenStreetMap rather than Google Maps: no API key, no billing account, and
 * nothing to expire. Navigation still hands off to Google Maps on the driver's
 * phone, which is what drivers actually use.
 */

const KERALA_CENTRE: [number, number] = [10.0159, 76.3419]

/* Leaflet's default marker images resolve to paths that a bundler cannot see,
   so the pin is drawn instead. */
const PIN = L.divIcon({
  className: '',
  html: `<div style="
    width:22px;height:22px;border-radius:50% 50% 50% 0;
    background:#12151c;border:2.5px solid #fff;
    transform:rotate(-45deg);
    box-shadow:0 2px 8px rgba(0,0,0,.4);
  "></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 22],
})

export interface LatLng {
  lat: number
  lng: number
}

function ClickToPlace({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({
    click(e) {
      onPick({ lat: e.latlng.lat, lng: e.latlng.lng })
    },
  })
  return null
}

function Recentre({ position }: { position: [number, number] | null }) {
  const map = useMap()
  useEffect(() => {
    if (position) map.setView(position, Math.max(map.getZoom(), 14))
  }, [position, map])
  return null
}

export function LocationPicker({
  value,
  onChange,
  height = 260,
}: {
  value: LatLng | null
  onChange: (p: LatLng | null) => void
  height?: number
}) {
  const [latText, setLatText] = useState(value ? String(value.lat) : '')
  const [lngText, setLngText] = useState(value ? String(value.lng) : '')
  const [pasted, setPasted] = useState('')
  const [note, setNote] = useState<string | null>(null)

  const position = useMemo<[number, number] | null>(
    () => (value ? [value.lat, value.lng] : null),
    [value],
  )

  function set(p: LatLng | null) {
    onChange(p)
    setLatText(p ? p.lat.toFixed(6) : '')
    setLngText(p ? p.lng.toFixed(6) : '')
  }

  /** Accepts what people actually paste out of Google Maps: "10.0159, 76.3419",
   *  or a maps URL with an @lat,lng or ?q=lat,lng in it. */
  function applyPasted() {
    setNote(null)
    const text = pasted.trim()
    if (!text) return

    const match =
      text.match(/@(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ??
      text.match(/[?&]q=(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ??
      text.match(/(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)/)

    if (!match) {
      setNote('Could not find coordinates in that. Paste "10.0159, 76.3419" or a Google Maps link.')
      return
    }
    const lat = Number(match[1])
    const lng = Number(match[2])
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
      setNote('Those numbers are not a valid latitude and longitude.')
      return
    }
    set({ lat, lng })
    setPasted('')
  }

  function useMyLocation() {
    setNote(null)
    if (!navigator.geolocation) {
      setNote('This browser cannot report a location.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => set({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setNote('Location permission was refused.'),
      { enableHighAccuracy: true, timeout: 8000 },
    )
  }

  return (
    <div className="space-y-3">
      <div
        className="overflow-hidden"
        style={{ height, borderRadius: 'var(--radius-control)', boxShadow: 'var(--neu-inset)' }}
      >
        <MapContainer
          center={position ?? KERALA_CENTRE}
          zoom={position ? 14 : 8}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickToPlace onPick={set} />
          <Recentre position={position} />
          {position ? <Marker position={position} icon={PIN} /> : null}
        </MapContainer>
      </div>

      <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
        <MapPin className="mr-1 inline size-3.5" />
        Click the map to drop a pin, paste coordinates, or use this device's location.
      </p>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[16rem] flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
            style={{ color: 'var(--text-faint)' }}
          />
          <Input
            className="pl-10"
            placeholder="Paste coordinates or a Google Maps link"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                applyPasted()
              }
            }}
          />
        </div>
        <Button type="button" variant="secondary" onClick={applyPasted}>
          Use it
        </Button>
        <Button
          type="button"
          variant="secondary"
          icon={<Crosshair className="size-4" />}
          onClick={useMyLocation}
        >
          My location
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Latitude">
          <Input
            className="tnum"
            inputMode="decimal"
            placeholder="10.015900"
            value={latText}
            onChange={(e) => {
              setLatText(e.target.value)
              const lat = Number(e.target.value)
              const lng = Number(lngText)
              if (Number.isFinite(lat) && Number.isFinite(lng) && e.target.value && lngText) {
                onChange({ lat, lng })
              }
            }}
          />
        </Field>
        <Field label="Longitude">
          <Input
            className="tnum"
            inputMode="decimal"
            placeholder="76.341900"
            value={lngText}
            onChange={(e) => {
              setLngText(e.target.value)
              const lat = Number(latText)
              const lng = Number(e.target.value)
              if (Number.isFinite(lat) && Number.isFinite(lng) && latText && e.target.value) {
                onChange({ lat, lng })
              }
            }}
          />
        </Field>
      </div>

      {note ? (
        <p className="text-[12px]" style={{ color: 'var(--warning)' }}>
          {note}
        </p>
      ) : null}

      {value ? (
        <button
          type="button"
          onClick={() => set(null)}
          className="text-[12px] underline underline-offset-2"
          style={{ color: 'var(--text-faint)' }}
        >
          Clear the pin
        </button>
      ) : null}
    </div>
  )
}
