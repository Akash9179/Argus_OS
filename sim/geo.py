"""Geographic helpers for the simulated vehicle.

Deliberately a separate copy from the server's. A vehicle and the world
model are different deployables, and a real vehicle would never import
server code. Keeping them apart is what lets the claim "the server cannot
tell the simulated vehicle from a real one" mean anything.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing, degrees clockwise from true north, 0.0 to under 360.0."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def step_toward(
    lat: float, lon: float, target_lat: float, target_lon: float, meters: float
) -> tuple[float, float]:
    """Move from one point toward another by a number of meters."""
    remaining = distance_m(lat, lon, target_lat, target_lon)
    if remaining <= meters or remaining == 0.0:
        return target_lat, target_lon
    fraction = meters / remaining
    return lat + (target_lat - lat) * fraction, lon + (target_lon - lon) * fraction


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """A point offset by meters north and east."""
    dlat = (north_m / EARTH_RADIUS_M) * (180.0 / math.pi)
    dlon = (east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))) * (180.0 / math.pi)
    return lat + dlat, lon + dlon
