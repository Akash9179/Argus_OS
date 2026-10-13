/**
 * The map.
 *
 * Everything the operator can act on is here: our machines, the things that
 * have been seen, and the places that matter. Clicking the ground sends the
 * selected machine there, which is the whole tasking interface.
 */

import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { initialFrame } from '../map/frame'
import { imageryLayer } from '../map/imagery'
import { TERRAIN_DARK, TERRAIN_DAY, TerrainLayer } from '../map/terrain'
import type { Position, TileLayerInfo } from '../sdk/types'
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

/**
 * The map draws shapes on a canvas, and a canvas cannot read CSS variables,
 * so a design token is resolved to its colour at the moment it is drawn.
 */
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#3b82f6'
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
  /** A proposed route the assistant has drawn, not yet approved. */
  proposalPath?: Position[] | null
  /** Imagery from the station's cache; null keeps the drawn terrain. */
  imagery?: TileLayerInfo | null
  showZones?: boolean
  showMachines?: boolean
  /** Fly here. The key changes on every request so the same place can be asked for twice. */
  focus?: { lat: number; lon: number; key: number } | null
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
  const {
    world,
    theme,
    selectedAssetId,
    selectedTrackId,
    answering,
    canSend,
    proposalPath = null,
    imagery = null,
    showZones = true,
    showMachines = true,
    focus = null,
  } = props
  const holder = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map>()
  const terrain = useRef<TerrainLayer>()
  const imageryRef = useRef<L.TileLayer>()
  const layers = useRef<L.LayerGroup>()
  const proposal = useRef<L.LayerGroup>()
  const fitted = useRef(false)

  // Handlers change every render; keeping them in a ref means the map is
  // built once and never torn down underneath the operator. The ref is
  // refreshed after each render commits, before any effect or click reads it.
  const handlers = useRef(props)
  useLayoutEffect(() => {
    handlers.current = props
  })

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
    // The theme at build time. The theme effect below follows later changes,
    // so a theme switch recolours the map rather than rebuilding it.
    const initial = handlers.current.theme
    terrain.current = new TerrainLayer(initial === 'day' ? TERRAIN_DAY : TERRAIN_DARK)
    terrain.current.addTo(created)
    layers.current = L.layerGroup().addTo(created)
    proposal.current = L.layerGroup().addTo(created)
    L.control.zoom({ position: 'topright' }).addTo(created)
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(created)

    created.on('click', (event: L.LeafletMouseEvent) => {
      if (!handlers.current.canSend) return
      handlers.current.onSendTo(event.latlng.lat, event.latlng.lng)
    })

    map.current = created
    // The column changes width when the assistant folds to its rail. The
    // map is told, or it keeps drawing for the old size and leaves a blank
    // band where the new room is.
    const resized = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => created.invalidateSize())
    resized?.observe(holder.current)
    return () => {
      resized?.disconnect()
      created.remove()
      map.current = undefined
      // A rebuilt map starts at the default view, so it must frame the site again.
      fitted.current = false
    }
  }, [])

  useEffect(() => {
    terrain.current?.setColours(theme === 'day' ? TERRAIN_DAY : TERRAIN_DARK)
  }, [theme])

  // Imagery sits over the drawn terrain, so outside the cached area the
  // ground is still drawn rather than blank. Swapping the layer changes
  // nothing else: the same interface, as the terrain layer promised.
  useEffect(() => {
    const created = map.current
    if (!created) return
    imageryRef.current?.remove()
    imageryRef.current = undefined
    if (imagery) {
      imageryRef.current = imageryLayer(imagery).addTo(created)
    }
  }, [imagery])

  // The proposed route: drawn in the selection colour because it is an
  // affordance, a thing to approve, and not a status of anything.
  useEffect(() => {
    const group = proposal.current
    if (!group) return
    group.clearLayers()
    const ring = (proposalPath ?? [])
      .filter((p) => p.latitude_deg !== undefined && p.longitude_deg !== undefined)
      .map((p) => [p.latitude_deg!, p.longitude_deg!] as [number, number])
    if (ring.length < 2) return
    const sel = token('--sel')
    L.polyline(ring, { color: sel, weight: 3, opacity: 0.9, dashArray: '10 6', interactive: false }).addTo(group)
    for (const point of ring.slice(1)) {
      L.circleMarker(point, { radius: 5, color: sel, weight: 2, fillColor: token('--bg'), fillOpacity: 1, interactive: false }).addTo(group)
    }
    map.current?.fitBounds(L.latLngBounds(ring).pad(0.4), { maxZoom: 17 })
  }, [proposalPath])

  useEffect(() => {
    if (focus && map.current) map.current.flyTo([focus.lat, focus.lon], Math.max(map.current.getZoom(), 17))
  }, [focus])

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

    for (const zone of showZones ? zones : []) {
      const ring = (zone.geometry?.exterior ?? [])
        .filter((p) => p.latitude_deg !== undefined && p.longitude_deg !== undefined)
        .map((p) => [p.latitude_deg!, p.longitude_deg!] as [number, number])
      if (ring.length < 3) continue
      const keepOut =
        zone.zone_type === 'restricted' ||
        zone.zone_type === 'protected' ||
        (zone.rules ?? []).some((r) => r.rule_type === 'alert_on_entry')
      L.polygon(ring, {
        className: 'zone',
        color: token(keepOut ? '--act' : '--sel'),
        weight: 2,
        opacity: 0.9,
        fillOpacity: keepOut ? 0.18 : 0.03,
        dashArray: keepOut ? undefined : '8 6',
        interactive: false,
      })
        .bindTooltip(escape(zone.name ?? ''), {
          permanent: true,
          direction: 'top',
          className: `map-chip ${keepOut ? 'is-keepout' : 'is-zone'}`,
        })
        .addTo(group)
    }

    for (const asset of showMachines ? machines : []) {
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
          color: token('--warn'),
          weight: 1.2,
          opacity: 0.45,
          dashArray: '3 4',
          interactive: false,
        }).addTo(group)
      }
    }

    // Frame the site once, then leave the view where the operator put it.
    // What counts as the site is decided in map/frame.ts: its zones, else
    // the answering machines, else the machines heard within the day.
    if (!fitted.current) {
      const frame = initialFrame(world, answering, Date.now() / 1000)
      if (frame) {
        fitted.current = true
        created.fitBounds(L.latLngBounds(frame.points).pad(frame.padding), { maxZoom: 16, animate: false })
      }
    }
  }, [world, machines, contacts, zones, selectedAssetId, selectedTrackId, answering, showZones, showMachines])

  return <div className="map" ref={holder} />
}
