"""Geographic helpers.

Deliberately domain-neutral: everything here works on WGS84 latitude and
longitude and ignores altitude, so the same code serves ground, air,
surface, and fixed assets. Altitude-aware separation is an additive change
if a future domain needs it.
"""

from __future__ import annotations

import math
from typing import Iterable

from link.v1.ontology_pb2 import Polygon, Position

EARTH_RADIUS_M = 6_371_000.0


def distance_m(a: Position, b: Position) -> float:
    """Great-circle distance between two positions, in meters."""
    lat1, lon1 = math.radians(a.latitude_deg), math.radians(a.longitude_deg)
    lat2, lon2 = math.radians(b.latitude_deg), math.radians(b.longitude_deg)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def bearing_deg(a: Position, b: Position) -> float:
    """Initial bearing from a to b, degrees clockwise from true north.

    Returned in the range 0.0 inclusive to 360.0 exclusive, matching the
    contract's course and heading convention.
    """
    lat1, lat2 = math.radians(a.latitude_deg), math.radians(b.latitude_deg)
    dlon = math.radians(b.longitude_deg - a.longitude_deg)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def offset(origin: Position, north_m: float, east_m: float) -> Position:
    """A position offset from origin by the given meters north and east."""
    lat = origin.latitude_deg + (north_m / EARTH_RADIUS_M) * (180.0 / math.pi)
    lon = origin.longitude_deg + (east_m / (EARTH_RADIUS_M * math.cos(math.radians(origin.latitude_deg)))) * (
        180.0 / math.pi
    )
    out = Position(latitude_deg=lat, longitude_deg=lon)
    if origin.HasField("altitude_m"):
        out.altitude_m = origin.altitude_m
    return out


def point_in_polygon(point: Position, polygon: Polygon) -> bool:
    """Whether a position falls inside a polygon, by ray casting.

    Treats latitude and longitude as planar, which is accurate at the scale
    of a site. Polygons that cross the antimeridian are not supported in
    version 1; no deployment site requires it, and support would be an
    additive change.
    """
    ring: Iterable[Position] = polygon.exterior
    verts = list(ring)
    if len(verts) < 3:
        return False

    x, y = point.longitude_deg, point.latitude_deg
    inside = False
    j = len(verts) - 1
    for i, vertex in enumerate(verts):
        xi, yi = vertex.longitude_deg, vertex.latitude_deg
        xj, yj = verts[j].longitude_deg, verts[j].latitude_deg
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside
