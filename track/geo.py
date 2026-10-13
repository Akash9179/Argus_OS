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


# -- does a route cross a place ---------------------------------------------
#
# Planar, like point_in_polygon: at the scale of a site, treating degrees
# as a flat grid is accurate enough, and a route is checked before it is
# sent, where a false "crosses" costs an operator one look at the map and a
# false "clear" costs a machine driving somewhere it should not.


def _orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    """Sign of the turn a-b-c: positive anticlockwise, negative clockwise, zero collinear."""
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _within(p: float, a: float, b: float) -> bool:
    return min(a, b) <= p <= max(a, b)


def segments_intersect(p1: Position, p2: Position, q1: Position, q2: Position) -> bool:
    """Whether segment p1-p2 meets segment q1-q2, touching included.

    Touching counts. A route that grazes the edge of a place it must stay
    out of is worth an operator's look, and a planner that treats the
    boundary as free space is one rounding error from being inside it.
    """
    ax, ay = p1.longitude_deg, p1.latitude_deg
    bx, by = p2.longitude_deg, p2.latitude_deg
    cx, cy = q1.longitude_deg, q1.latitude_deg
    dx, dy = q2.longitude_deg, q2.latitude_deg

    o1 = _orientation(ax, ay, bx, by, cx, cy)
    o2 = _orientation(ax, ay, bx, by, dx, dy)
    o3 = _orientation(cx, cy, dx, dy, ax, ay)
    o4 = _orientation(cx, cy, dx, dy, bx, by)

    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0:
        return True

    # Collinear or touching cases: an endpoint of one lies on the other.
    if o1 == 0 and _within(cx, ax, bx) and _within(cy, ay, by):
        return True
    if o2 == 0 and _within(dx, ax, bx) and _within(dy, ay, by):
        return True
    if o3 == 0 and _within(ax, cx, dx) and _within(ay, cy, dy):
        return True
    if o4 == 0 and _within(bx, cx, dx) and _within(by, cy, dy):
        return True
    return False


def segment_crosses_polygon(a: Position, b: Position, polygon: Polygon) -> bool:
    """Whether the straight leg from a to b passes through a polygon.

    True if either end is inside, or the leg meets any edge. A polygon with
    fewer than three vertices encloses nothing and is never crossed.
    """
    verts = list(polygon.exterior)
    if len(verts) < 3:
        return False
    if point_in_polygon(a, polygon) or point_in_polygon(b, polygon):
        return True
    for i, v in enumerate(verts):
        w = verts[(i + 1) % len(verts)]
        if segments_intersect(a, b, v, w):
            return True
    return False


def path_crosses_polygon(path: Iterable[Position], polygon: Polygon) -> bool:
    """Whether any leg of a route passes through a polygon.

    A route with a single point is a place, not a leg, and counts as
    crossing only if that point is inside.
    """
    points = list(path)
    if not points:
        return False
    if len(points) == 1:
        return len(polygon.exterior) >= 3 and point_in_polygon(points[0], polygon)
    return any(
        segment_crosses_polygon(points[i], points[i + 1], polygon) for i in range(len(points) - 1)
    )
