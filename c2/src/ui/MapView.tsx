/**
 * The map.
 *
 * Everything the operator can act on is here: our machines, the things that
 * have been seen, and the places that matter. Clicking the ground sends the
 * selected machine there, which is the whole tasking interface.
 */

import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { TERRAIN_DARK, TERRAIN_DAY, TerrainLayer } from '../map/terrain'
import { lastHeardAt, positionOf, type World } from '../state/world'
import { assetStatus, clockAt, outOfTen, say } from './wording'

function confidenceLabel(confidence: number | undefined): string {
  const tenths = outOfTen(confidence)
  return tenths === null ? say.detail.noFigure : `${tenths} in 10`
}

const STATUS_COLOUR: Record<string, string> = {
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  act: 'var(--act)',
  off: 'var(--off)',
}

interface Props {
  world: World
  theme: 'dark' | 'day'
  selectedAssetId: string | null
  selectedTrackId: string | null
  answering: (assetId: string) => boolean
  canSend: boolean
  onSelectAsset: (assetId: string) => void
  onSelectTrack: (trackId: string) => void
  onSendTo: (lat: number, lon: number) => void
}

/**
 * Names and place labels are data an administrator typed. They go through
 * here before they reach a marker, so a name can never become markup.
 */
function escape(text: string): string {
  return text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string,
  )
}

/** A machine: a heading arrow, with a ring when it is the one selected. */
function machineIcon(colour: string, headingDeg: number, selected: boolean, name: string): L.DivIcon {
  return L.divIcon({
    className: 'marker',
    iconSize: [64, 64],
    iconAnchor: [32, 32],
    html: `
      <div class="machine-marker">
        ${selected ? '<div class="machine-ring"></div>' : ''}
        <svg viewBox="0 0 64 64" class="machine-glyph" style="transform: rotate(${headingDeg}deg)">
          <circle cx="32" cy="32" r="15" class="machine-disc"/>
          <polygon points="32,20 41,42 23,42" fill="${colour}"/>
        </svg>
        <span class="marker-label">${escape(name)}</span>
      </div>`,
  })
}

/** A contact: a diamond, with how sure the machine is beside it. */
function contactIcon(label: string, selected: boolean): L.DivIcon {
  return L.divIcon({
    className: 'marker',
    iconSize: [64, 64],
    iconAnchor: [32, 32],
    html: `
      <div class="contact-marker ${selected ? 'is-selected' : ''}">
        <div class="contact-halo"></div>
        <div class="contact-diamond"></div>
        <span class="marker-label">${escape(label)}</span>
      </div>`,
  })
}

export function MapView(props: Props) {
  const { world, theme, selectedAssetId, selectedTrackId, answering, canSend } = props
  const holder = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map>()
  const terrain = useRef<TerrainLayer>()
  const layers = useRef<L.LayerGroup>()
  const fitted = useRef(false)

  // Handlers change every render; keeping them in a ref means the map is
  // built once and never torn down underneath the operator.
  const handlers = useRef(props)
  handlers.current = props

  useEffect(() => {
    if (!holder.current || map.current) return

    const created = L.map(holder.current, {
      zoomControl: false,
      attributionControl: false,
      center: [51.5045, -0.12],
      zoom: 17,
      // The whole interface is one screen: no scroll traps, no surprises.
      preferCanvas: true,
    })
    terrain.current = new TerrainLayer(theme === 'day' ? TERRAIN_DAY : TERRAIN_DARK)
    terrain.current.addTo(created)
    layers.current = L.layerGroup().addTo(created)
    L.control.zoom({ position: 'topright' }).addTo(created)
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(created)

    created.on('click', (event: L.LeafletMouseEvent) => {
      if (!handlers.current.canSend) return
      handlers.current.onSendTo(event.latlng.lat, event.latlng.lng)
    })

    map.current = created
    return () => {
      created.remove()
      map.current = undefined
    }
  }, [])

  useEffect(() => {
    terrain.current?.setColours(theme === 'day' ? TERRAIN_DAY : TERRAIN_DARK)
  }, [theme])

  useEffect(() => {
    const container = map.current?.getContainer()
    if (container) container.style.cursor = canSend ? 'crosshair' : ''
  }, [canSend])

  const machines = useMemo(() => [...world.assets.values()], [world.assets])
  const contacts = useMemo(
    () => [...world.tracks.values()].filter((t) => t.state !== 'TRACK_STATE_CLOSED'),
    [world.tracks],
  )
  const zones = useMemo(() => [...world.zones.values()], [world.zones])

  useEffect(() => {
    const group = layers.current
    const created = map.current
    if (!group || !created) return
    group.clearLayers()

    for (const zone of zones) {
      const ring = (zone.geometry?.exterior ?? [])
        .filter((p) => p.latitude_deg !== undefined && p.longitude_deg !== undefined)
        .map((p) => [p.latitude_deg!, p.longitude_deg!] as [number, number])
      if (ring.length < 3) continue
      L.polygon(ring, {
        className: 'zone',
        color: 'var(--warn)',
        weight: 1.2,
        opacity: 0.6,
        fillOpacity: 0.04,
        dashArray: '8 5',
        interactive: false,
      })
        .bindTooltip(escape(zone.name ?? ''), { permanent: true, direction: 'top', className: 'map-chip' })
        .addTo(group)
    }

    for (const asset of machines) {
      const at = positionOf(world, asset)
      if (!at) continue
      const live = world.telemetry.get(asset.asset_id)
      const isAnswering = answering(asset.asset_id)
      const status = assetStatus(asset.status, isAnswering)
      const marker = L.marker([at.lat, at.lon], {
        icon: machineIcon(
          STATUS_COLOUR[status],
          live?.heading_deg ?? 0,
          asset.asset_id === selectedAssetId,
          asset.display_name,
        ),
        zIndexOffset: 400,
      })
      marker.on('click', (event) => {
        L.DomEvent.stopPropagation(event)
        handlers.current.onSelectAsset(asset.asset_id)
      })
      // A machine that has gone quiet must never read as live on the map.
      // The label is permanent rather than on hover: an operator scanning
      // the map has to be able to see which markers are stale without
      // pointing at each one.
      if (!isAnswering) {
        const heard = lastHeardAt(world, asset)
        const when = heard ? `${say.map.lastHeard} ${clockAt(heard)}` : say.map.notHeard
        marker.bindTooltip(escape(when), {
          permanent: true,
          direction: 'bottom',
          className: 'map-chip is-stale',
        })
      }
      marker.addTo(group)
    }

    for (const contact of contacts) {
      const at = contact.position
      if (at?.latitude_deg === undefined || at?.longitude_deg === undefined) continue
      const marker = L.marker([at.latitude_deg, at.longitude_deg], {
        icon: contactIcon(confidenceLabel(contact.confidence), contact.track_id === selectedTrackId),
        zIndexOffset: 300,
      })
      marker.on('click', (event) => {
        L.DomEvent.stopPropagation(event)
        handlers.current.onSelectTrack(contact.track_id)
      })
      marker.addTo(group)

      // Where it has been, so an operator can see which way it is going.
      const trail = (contact.history ?? [])
        .filter((h) => h.position?.latitude_deg !== undefined)
        .map((h) => [h.position!.latitude_deg!, h.position!.longitude_deg!] as [number, number])
      if (trail.length > 1) {
        L.polyline(trail, {
          color: 'var(--warn)',
          weight: 1.2,
          opacity: 0.45,
          dashArray: '3 4',
          interactive: false,
        }).addTo(group)
      }
    }

    // Frame the site once, then leave the view where the operator put it.
    if (!fitted.current) {
      const points: [number, number][] = []
      for (const asset of machines) {
        const at = positionOf(world, asset)
        if (at) points.push([at.lat, at.lon])
      }
      for (const contact of contacts) {
        const at = contact.position
        if (at?.latitude_deg !== undefined && at?.longitude_deg !== undefined) {
          points.push([at.latitude_deg, at.longitude_deg])
        }
      }
      if (points.length > 0) {
        fitted.current = true
        created.fitBounds(L.latLngBounds(points).pad(1.2), { maxZoom: 16, animate: false })
      }
    }
  }, [world, machines, contacts, zones, selectedAssetId, selectedTrackId, answering])

  return <div className="map" ref={holder} />
}
