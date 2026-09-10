/**
 * Imagery from this station's own tile cache.
 *
 * The sovereignty law forbids cloud tile servers in mission paths, so the
 * only imagery the map will ever show is what an administrator put in the
 * station's cache (an MBTiles file served by the world model). When the
 * cache is empty this layer is never created and the drawn terrain stays.
 *
 * Tiles are images, and a browser cannot send a bearer header for an
 * image, so the token travels as a query parameter, the same as on the
 * live stream. The server applies the same tokens and roles.
 */

import L from 'leaflet'
import { savedToken } from '../sdk/session'
import type { TileLayerInfo } from '../sdk/types'

export function imageryLayer(layer: TileLayerInfo): L.TileLayer {
  const [west, south, east, north] = layer.bounds
  return L.tileLayer(
    `/v1/tiles/${encodeURIComponent(layer.id)}/{z}/{x}/{y}?token=${encodeURIComponent(savedToken())}`,
    {
      minZoom: layer.min_zoom,
      maxNativeZoom: layer.max_zoom,
      maxZoom: 22,
      bounds: L.latLngBounds([south, west], [north, east]),
      attribution: layer.attribution,
      className: 'imagery',
    },
  )
}
