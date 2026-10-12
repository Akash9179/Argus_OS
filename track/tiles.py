"""The local imagery cache.

Satellite imagery in the operator application comes from this station and
nowhere else. The sovereignty law forbids cloud services in mission paths
and the targets are air-gapped, so there is no tile server to call; the
founder decided on 10 Sep 2026 (D-22) that imagery is a local MBTiles cache
served by TRACK, shipped empty. Sourcing tiles for a site is a founder
action, not something the software does on its own.

An MBTiles file is a SQLite database with two tables: `metadata` (name,
format, bounds, minzoom, maxzoom, attribution) and `tiles` (zoom_level,
tile_column, tile_row, tile_data). Each *.mbtiles file in the cache
directory is one layer, identified by its filename stem. Rows are stored in
the TMS scheme, where the y axis counts up from the south, while the map
asks in XYZ, where it counts down from the north, so every request flips
the row: y_tms = (2**z - 1) - y_xyz.

Files are opened read-only, lazily, one connection per layer. This module
never touches the network.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

WORLD_BOUNDS = (-180.0, -85.0511, 180.0, 85.0511)

# The deepest zoom any layer may claim, whatever its metadata says. A tile
# address is checked against the layer's zoom before any arithmetic is done
# with it, and this keeps that check honest when the metadata is wrong:
# 2**z for a zoom from a request would otherwise stall the server, and a
# flipped row past 2**63 does not fit in a SQLite integer.
ZOOM_CEILING = 24


@dataclass(frozen=True)
class TileLayer:
    """One imagery layer, as an application sees it."""

    id: str
    name: str
    format: str
    attribution: str
    bounds: tuple[float, float, float, float]
    min_zoom: int
    max_zoom: int

    @property
    def content_type(self) -> str:
        return CONTENT_TYPES.get(self.format, "application/octet-stream")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "attribution": self.attribution,
            "bounds": list(self.bounds),
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
        }


def _parse_bounds(text: str | None) -> tuple[float, float, float, float]:
    """MBTiles writes bounds as "w,s,e,n". Anything malformed means the
    whole world, which is honest: we do not know where the tiles are."""
    if not text:
        return WORLD_BOUNDS
    try:
        parts = [float(p) for p in text.split(",")]
    except ValueError:
        return WORLD_BOUNDS
    if len(parts) != 4:
        return WORLD_BOUNDS
    return (parts[0], parts[1], parts[2], parts[3])


def _parse_int(text: str | None, default: int) -> int:
    try:
        return int(text) if text is not None else default
    except ValueError:
        return default


class TileStore:
    """Every *.mbtiles file in a directory, served as a layer."""

    def __init__(self, directory: str | Path):
        self._dir = Path(directory)
        self._connections: dict[str, sqlite3.Connection] = {}
        self._layers: dict[str, TileLayer] = {}
        self._lock = threading.Lock()

    # -- discovery ----------------------------------------------------------

    def _paths(self) -> dict[str, Path]:
        """Layer id to file, rescanned on every call so a file dropped into
        the directory shows up without a restart. A missing directory is an
        empty cache, not an error."""
        if not self._dir.is_dir():
            return {}
        return {p.stem: p for p in sorted(self._dir.glob("*.mbtiles")) if p.is_file()}

    def _connect(self, layer_id: str, path: Path) -> sqlite3.Connection:
        conn = self._connections.get(layer_id)
        if conn is not None:
            return conn
        # Read-only by URI, so the cache can never be altered through the
        # server, whatever the request looks like.
        uri = path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._connections[layer_id] = conn
        return conn

    def _read_layer(self, layer_id: str, path: Path) -> TileLayer | None:
        try:
            conn = self._connect(layer_id, path)
            rows = conn.execute("SELECT name, value FROM metadata").fetchall()
        except sqlite3.Error as exc:
            log.warning("imagery layer %s unreadable: %s", path.name, exc)
            self._forget(layer_id)
            return None
        meta = {name: value for name, value in rows}
        fmt = str(meta.get("format", "png")).lower()
        return TileLayer(
            id=layer_id,
            name=str(meta.get("name") or layer_id),
            format=fmt,
            attribution=str(meta.get("attribution") or ""),
            bounds=_parse_bounds(meta.get("bounds")),
            min_zoom=_parse_int(meta.get("minzoom"), 0),
            max_zoom=min(max(_parse_int(meta.get("maxzoom"), 22), 0), ZOOM_CEILING),
        )

    def _forget(self, layer_id: str) -> None:
        conn = self._connections.pop(layer_id, None)
        if conn is not None:
            conn.close()
        self._layers.pop(layer_id, None)

    # -- the public surface -------------------------------------------------

    def layers(self) -> list[TileLayer]:
        """Every layer in the cache. Empty when the cache is empty."""
        with self._lock:
            paths = self._paths()
            for stale in [k for k in self._layers if k not in paths]:
                self._forget(stale)
            found: list[TileLayer] = []
            for layer_id, path in paths.items():
                layer = self._layers.get(layer_id)
                if layer is None:
                    layer = self._read_layer(layer_id, path)
                    if layer is None:
                        continue
                    self._layers[layer_id] = layer
                found.append(layer)
            return found

    def layer(self, layer_id: str) -> TileLayer | None:
        with self._lock:
            path = self._paths().get(layer_id)
            if path is None:
                self._forget(layer_id)
                return None
            layer = self._layers.get(layer_id)
            if layer is None:
                layer = self._read_layer(layer_id, path)
                if layer is not None:
                    self._layers[layer_id] = layer
            return layer

    def tile(self, layer_id: str, z: int, x: int, y: int) -> bytes | None:
        """One tile in XYZ addressing, or None when the layer has none there.

        The caller has already checked the layer exists, so None here means
        "no imagery at that spot", never "no such layer".
        """
        with self._lock:
            layer = self._layers.get(layer_id)
            conn = self._connections.get(layer_id)
            if layer is None or conn is None:
                return None
            # The zoom first, so nothing below raises 2 to a number nobody
            # has checked. Only then the column and row.
            if not 0 <= z <= layer.max_zoom:
                return None
            side = 1 << z
            if not (0 <= x < side and 0 <= y < side):
                return None
            y_tms = (side - 1) - y
            try:
                row = conn.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (z, x, y_tms),
                ).fetchone()
            except sqlite3.Error as exc:
                log.warning("imagery layer %s failed to read a tile: %s", layer_id, exc)
                return None
        return bytes(row[0]) if row and row[0] is not None else None

    def close(self) -> None:
        with self._lock:
            for conn in self._connections.values():
                conn.close()
            self._connections.clear()
            self._layers.clear()
