import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { PlusIcon, MinusIcon } from '../ui/icons'

export type MapView = 'map' | 'sat'

// Placeholder home position until GPS / odometry telemetry exists (Phase 2 ZED GNSS).
const HOME: [number, number] = [12.9716, 77.5946]
const ALERT: [number, number] = [HOME[0] + 0.0007, HOME[1] + 0.0009]

const TILES: Record<MapView, { url: string; attribution: string; maxZoom: number }> = {
  sat: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
  },
  map: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '© OpenStreetMap, © CARTO',
    maxZoom: 20,
  },
}

function trajectoryPoints(steer: number): [number, number][] {
  const N = 16
  const forwardM = 45
  const latPerM = 1 / 111111
  const lngPerM = 1 / (111111 * Math.cos((HOME[0] * Math.PI) / 180))
  const pts: [number, number][] = []
  for (let i = 0; i <= N; i++) {
    const t = i / N
    pts.push([HOME[0] + forwardM * t * latPerM, HOME[1] + steer * 30 * t * t * lngPerM])
  }
  return pts
}

export function LeafletMap({
  view,
  steer,
  interactive = true,
  showZoom = true,
}: {
  view: MapView
  steer: number
  interactive?: boolean
  showZoom?: boolean
}) {
  const elRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const tileRef = useRef<L.TileLayer | null>(null)
  const trajRef = useRef<L.Polyline | null>(null)

  // init once
  useEffect(() => {
    if (!elRef.current) return
    const map = L.map(elRef.current, {
      center: HOME,
      zoom: 17,
      zoomControl: false,
      attributionControl: true,
      dragging: interactive,
      scrollWheelZoom: interactive,
      doubleClickZoom: interactive,
      boxZoom: interactive,
      keyboard: interactive,
      touchZoom: interactive,
      zoomSnap: 0.5,
    })
    mapRef.current = map

    const t = TILES[view]
    tileRef.current = L.tileLayer(t.url, { attribution: t.attribution, maxZoom: t.maxZoom, subdomains: 'abcd' }).addTo(map)

    L.circleMarker(HOME, { radius: 5, color: '#2E8FFF', weight: 10, opacity: 0.2, fillColor: '#2E8FFF', fillOpacity: 1 })
      .addTo(map)
      .bindTooltip('GR-1', { permanent: true, direction: 'top', className: 'argus-tip', offset: [0, -6] })
    L.circleMarker(ALERT, { radius: 5, color: '#FF4D4D', weight: 10, opacity: 0.22, fillColor: '#FF4D4D', fillOpacity: 1 }).addTo(map)

    trajRef.current = L.polyline(trajectoryPoints(steer), { color: '#2E8FFF', weight: 3, opacity: 0.9, dashArray: '6 6' }).addTo(map)

    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(elRef.current)
    setTimeout(() => map.invalidateSize(), 0)

    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // swap tiles on view change
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    tileRef.current?.remove()
    const t = TILES[view]
    tileRef.current = L.tileLayer(t.url, { attribution: t.attribution, maxZoom: t.maxZoom, subdomains: 'abcd' }).addTo(map)
  }, [view])

  // update trajectory on steer
  useEffect(() => {
    trajRef.current?.setLatLngs(trajectoryPoints(steer))
  }, [steer])

  return (
    <>
      <div ref={elRef} className="absolute inset-0 z-0 bg-surface-inset" />
      {interactive && showZoom && (
        <div className="absolute bottom-4 right-4 z-[500] flex flex-col overflow-hidden rounded-control border border-line bg-surface-2">
          <button onClick={() => mapRef.current?.zoomIn()} className="grid h-8 w-8 place-items-center text-text-2 hover:bg-surface-3 hover:text-text">
            <PlusIcon width={16} height={16} />
          </button>
          <span className="h-px w-full bg-line" />
          <button onClick={() => mapRef.current?.zoomOut()} className="grid h-8 w-8 place-items-center text-text-2 hover:bg-surface-3 hover:text-text">
            <MinusIcon width={16} height={16} />
          </button>
        </div>
      )}
    </>
  )
}
