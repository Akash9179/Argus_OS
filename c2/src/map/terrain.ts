/**
 * The ground, drawn locally.
 *
 * The sovereignty law forbids cloud services in mission paths, and the
 * targets are air-gapped, so there is no tile server to call. This layer
 * paints each tile itself from a deterministic height field: fractal value
 * noise, lit from the north west, with the same colour ramp as the approved
 * mockup.
 *
 * It is honest about what it is. This is terrain-shaped ground, not a
 * survey, and it carries no place names or features it has not been told
 * about. Real imagery arrives as a locally hosted tile source later, behind
 * this same interface: swap the layer, change nothing else.
 */

import L from 'leaflet'

/** Noise is sampled at this zoom so the ground stays put as you zoom. */
const REFERENCE_ZOOM = 16

function hash(x: number, y: number): number {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123
  return n - Math.floor(n)
}

function smooth(t: number): number {
  return t * t * (3 - 2 * t)
}

function valueNoise(x: number, y: number): number {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const xf = smooth(x - xi)
  const yf = smooth(y - yi)
  const a = hash(xi, yi)
  const b = hash(xi + 1, yi)
  const c = hash(xi, yi + 1)
  const d = hash(xi + 1, yi + 1)
  return a + (b - a) * xf + (c - a) * yf + (a - b - c + d) * xf * yf
}

/** Five octaves is enough for ridges and gullies without looking like static. */
function height(x: number, y: number): number {
  let total = 0
  let amplitude = 0.5
  let frequency = 1
  let norm = 0
  for (let octave = 0; octave < 7; octave++) {
    total += valueNoise(x * frequency, y * frequency) * amplitude
    norm += amplitude
    amplitude *= 0.5
    frequency *= 2
  }
  return total / norm
}

export interface TerrainColours {
  /** Lowest ground. */
  low: [number, number, number]
  /** Highest ground. */
  high: [number, number, number]
  /** How hard the hillshade bites, 0 to 1. */
  shade: number
}

export const TERRAIN_DARK: TerrainColours = {
  low: [29, 28, 24],
  high: [58, 55, 45],
  shade: 0.5,
}

export const TERRAIN_DAY: TerrainColours = {
  low: [150, 143, 123],
  high: [198, 190, 171],
  shade: 0.38,
}

export class TerrainLayer extends L.GridLayer {
  private colours: TerrainColours

  constructor(colours: TerrainColours, options?: L.GridLayerOptions) {
    super({ tileSize: 256, ...options })
    this.colours = colours
  }

  setColours(colours: TerrainColours): void {
    this.colours = colours
    this.redraw()
  }

  protected createTile(coords: L.Coords): HTMLElement {
    const size = this.getTileSize()
    const tile = document.createElement('canvas')
    tile.width = size.x
    tile.height = size.y
    const context = tile.getContext('2d')
    if (!context) return tile

    // Step in 2px blocks: at a glance it is indistinguishable from per-pixel
    // and it keeps panning smooth on the kind of machine that sits in a
    // control room rather than on a bench.
    const step = 2
    const scale = Math.pow(2, REFERENCE_ZOOM - coords.z)
    // One noise cell per ~40 metres of ground at the reference zoom. Seven
    // octaves take the detail down to roughly half a metre, so the ground
    // still reads as ground when the operator zooms right in.
    const frequency = 1 / 40
    const { low, high, shade } = this.colours

    const image = context.createImageData(size.x, size.y)
    const data = image.data

    for (let py = 0; py < size.y; py += step) {
      for (let px = 0; px < size.x; px += step) {
        const wx = (coords.x * size.x + px) * scale * frequency
        const wy = (coords.y * size.y + py) * scale * frequency

        const h = height(wx, wy)
        // Slope towards the north west light, from the height field itself.
        const dx = height(wx + 0.35, wy) - h
        const dy = height(wx, wy + 0.35) - h
        const lit = Math.max(0, Math.min(1, 0.55 + (dx + dy) * 1.9))
        const light = 1 - shade + shade * lit

        const r = (low[0] + (high[0] - low[0]) * h) * light
        const g = (low[1] + (high[1] - low[1]) * h) * light
        const b = (low[2] + (high[2] - low[2]) * h) * light

        for (let by = 0; by < step && py + by < size.y; by++) {
          for (let bx = 0; bx < step && px + bx < size.x; bx++) {
            const offset = ((py + by) * size.x + (px + bx)) * 4
            data[offset] = r
            data[offset + 1] = g
            data[offset + 2] = b
            data[offset + 3] = 255
          }
        }
      }
    }

    context.putImageData(image, 0, 0)
    return tile
  }
}
