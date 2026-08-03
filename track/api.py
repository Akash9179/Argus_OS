"""The service interfaces.

These are the only ways into the world model. C2 uses exactly these and
nothing else, no direct database access and no private endpoints, because
C2 is application number one on what later becomes the published SDK. If an
application needs something these interfaces cannot express, the interface
is what changes.

Every route passes through the permissions check, including the ones where
the policy is currently trivial.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from google.protobuf.json_format import MessageToDict
from link.v1.ontology_pb2 import Asset, Issuer, Polygon, Position, TaskParameters, Zone, ZoneRule
from pydantic import BaseModel, Field

from track import live
from track.codec import (
    asset_to_dict,
    assets_to_dicts,
    task_to_dict,
    tasks_to_dicts,
    to_dict,
    to_dicts,
)
from track.identity import ROLE_ADMIN, ROLE_OPERATOR, Principal
from track.ids import new_id
from track.worldmodel import TaskRejected, WorldModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


# -- request bodies --------------------------------------------------------


class PositionIn(BaseModel):
    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None = None

    def to_proto(self) -> Position:
        p = Position(latitude_deg=self.latitude_deg, longitude_deg=self.longitude_deg)
        if self.altitude_m is not None:
            p.altitude_m = self.altitude_m
        return p


class TaskIn(BaseModel):
    """An order, as an application asks for it."""

    asset_id: str
    # Open vocabulary: any string is accepted and forwarded as sent. An
    # asset that cannot perform the order reports failure; the server does
    # not second-guess the vocabulary, because doing so would block every
    # capability added after this build shipped.
    task_type: str
    waypoints: list[PositionIn] = Field(default_factory=list)
    target_track_id: str = ""
    speed_mps: float | None = None
    priority: int = 0
    # How the order reached the system, for the audit trail.
    channel: str = "map"
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_parameters(self) -> TaskParameters:
        params = TaskParameters(
            waypoints=[w.to_proto() for w in self.waypoints],
            target_track_id=self.target_track_id,
        )
        if self.speed_mps is not None:
            params.speed_mps = self.speed_mps
        if self.extras:
            params.extras.update(self.extras)
        return params


class ZoneRuleIn(BaseModel):
    rule_type: str
    parameters: dict[str, str] = Field(default_factory=dict)


class ZoneIn(BaseModel):
    name: str
    zone_type: str
    geometry: list[PositionIn]
    rules: list[ZoneRuleIn] = Field(default_factory=list)


# -- permissions -----------------------------------------------------------


def _world(request: Request) -> WorldModel:
    return request.app.state.world


def _say(request, name: str, **kwargs) -> str:
    """Operator-facing wording for a refusal, from the language data file."""
    return request.app.state.world.language.error(name, **kwargs)


async def current_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    """Resolve the caller, or refuse."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    principal = request.app.state.tokens.lookup(token) if token else None
    if principal is None:
        raise HTTPException(status_code=401, detail=_say(request, "not_signed_in"))
    return principal


def requires(role: str):
    """Dependency factory: the caller must hold at least this role."""

    async def _check(
        request: Request, principal: Annotated[Principal, Depends(current_principal)]
    ) -> Principal:
        if not principal.has_role(role):
            raise HTTPException(status_code=403, detail=_say(request, "not_allowed"))
        return principal

    return _check


Operator = Annotated[Principal, Depends(requires(ROLE_OPERATOR))]
Admin = Annotated[Principal, Depends(requires(ROLE_ADMIN))]


# -- who is signed in -----------------------------------------------------


@router.get("/me")
async def whoami(principal: Operator) -> dict:
    """Who this token belongs to, in the name an operator should see.

    The identifier stays on this side of the waterline. An application that
    wanted to put the caller on screen would otherwise have nothing to show
    but `principal_id`, which is exactly the kind of thing operators never
    read.
    """
    return {"display_name": principal.display_name, "role": principal.role}


# -- assets and their motion ----------------------------------------------


@router.get("/assets")
async def list_assets(request: Request, _: Operator) -> list[dict]:
    world = _world(request)
    return assets_to_dicts(world.store.list_assets(), world.language)


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, request: Request, _: Operator) -> dict:
    world = _world(request)
    asset = world.store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_such_asset"))
    return asset_to_dict(asset, world.language.asset_name(asset))


@router.get("/assets/{asset_id}/registry")
async def get_asset_registry(asset_id: str, request: Request, _: Admin) -> dict:
    """What a machine's hardware layer says it is made of.

    Installed drivers and versions, the manifest it booted on, what its
    buses report, the configuration in force, and each driver's health.
    The machine serves the same structure locally; this is the mirror, so
    the question can be answered without reaching the machine.

    Admin, not operator. Driver versions and bus scans are exactly the
    system internals the waterline law keeps away from operators, and the
    plan separates admin functions from operator surfaces for precisely
    this kind of data.

    A machine that has never reported one is not an error worth a 500: it
    is a machine running an older runtime, or one that has not been heard
    from yet.
    """
    world = _world(request)
    if world.store.get_asset(asset_id) is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_such_asset"))
    registry = world.store.get_registry(asset_id)
    if registry is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_registry_yet"))
    return registry


class AssetIn(BaseModel):
    """Administrative facts about a machine.

    Machines that run the edge runtime report their own name, capabilities,
    drivers and health through the hardware layer's registry, and that is
    the path to prefer: it is the machine's own declaration rather than
    someone's note about it.

    This endpoint remains for two cases the registry cannot cover: a machine
    registered before it has ever been switched on, and a third-party asset
    that speaks the contract but carries no ARGUS runtime and therefore has
    no registry to send.
    """

    name: str | None = None
    asset_class: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


@router.put("/assets/{asset_id}")
async def upsert_asset(asset_id: str, body: AssetIn, request: Request, _: Admin) -> dict:
    """Register a machine or update what we know about it.

    A machine may be registered before it has ever connected, which is how
    a site is set up ahead of the hardware arriving.
    """
    world = _world(request)
    asset = world.store.get_asset(asset_id) or Asset(asset_id=asset_id)
    if body.asset_class is not None:
        asset.asset_class = body.asset_class

    capabilities = dict(body.capabilities)
    if body.name is not None:
        capabilities["name"] = body.name
    if capabilities:
        merged = MessageToDict(asset.capabilities) if asset.HasField("capabilities") else {}
        merged.update(capabilities)
        asset.capabilities.update(merged)

    world.store.put_asset(asset)
    view = asset_to_dict(asset, world.language.asset_name(asset))
    await world.bus.publish(live.ASSET_UPDATED, view)
    return view


@router.get("/telemetry")
async def list_telemetry(request: Request, _: Operator) -> list[dict]:
    """Latest motion sample per asset, for a map that has just loaded."""
    return [t.to_dict() for t in _world(request).telemetry.values()]


# -- the world -------------------------------------------------------------


@router.get("/tracks")
async def list_tracks(
    request: Request,
    _: Operator,
    state: Annotated[list[int] | None, Query()] = None,
    limit: int = 500,
) -> list[dict]:
    world = _world(request)
    return world.track_views(world.store.list_tracks(states=state, limit=limit))


@router.get("/tracks/{track_id}")
async def get_track(track_id: str, request: Request, _: Operator) -> dict:
    world = _world(request)
    track = world.store.get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_such_track"))
    return world.track_view(track)


@router.get("/entities")
async def list_entities(request: Request, _: Operator, limit: int = 500) -> list[dict]:
    return to_dicts(_world(request).store.list_entities(limit=limit))


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str, request: Request, _: Operator) -> dict:
    world = _world(request)
    entity = world.store.get_entity(world.store.resolve_entity(entity_id))
    if entity is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_such_entity"))
    return to_dict(entity)


@router.get("/observations")
async def list_observations(
    request: Request, _: Operator, entity_id: str | None = None, limit: int = 200
) -> list[dict]:
    return to_dicts(_world(request).store.list_observations(entity_id=entity_id, limit=limit))


@router.get("/relationships")
async def list_relationships(
    request: Request, _: Operator, subject_id: str | None = None, limit: int = 200
) -> list[dict]:
    return to_dicts(_world(request).store.list_relationships(subject_id=subject_id, limit=limit))


# -- orders ----------------------------------------------------------------


@router.get("/tasks")
async def list_tasks(
    request: Request, _: Operator, asset_id: str | None = None, limit: int = 200
) -> list[dict]:
    world = _world(request)
    return world.task_views(world.store.list_tasks(asset_id=asset_id, limit=limit))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request, _: Operator) -> dict:
    world = _world(request)
    task = world.store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=_say(request, "no_such_task"))
    return world.task_view(task)


@router.post("/tasks", status_code=201)
async def create_task(body: TaskIn, request: Request, principal: Operator) -> dict:
    """Issue an order. Every path into the system ends here."""
    world = _world(request)
    issuer = Issuer(principal_id=principal.principal_id, channel=body.channel)
    try:
        task = await world.issue_task(
            asset_id=body.asset_id,
            task_type=body.task_type,
            parameters=body.to_parameters(),
            issuer=issuer,
            priority=body.priority,
        )
    except TaskRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return world.task_view(task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request, _: Operator) -> dict:
    world = _world(request)
    try:
        cancelled = await world.cancel_task(task_id)
        return world.task_view(cancelled)
    except TaskRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# -- places ----------------------------------------------------------------


@router.get("/zones")
async def list_zones(request: Request, _: Operator) -> list[dict]:
    return to_dicts(_world(request).store.list_zones())


@router.post("/zones", status_code=201)
async def create_zone(body: ZoneIn, request: Request, _: Admin) -> dict:
    """Zones are configuration, so creating one is an admin action."""
    world = _world(request)
    zone = Zone(
        zone_id=new_id(),
        name=body.name,
        zone_type=body.zone_type,
        geometry=Polygon(exterior=[p.to_proto() for p in body.geometry]),
        rules=[ZoneRule(rule_type=r.rule_type, parameters=r.parameters) for r in body.rules],
    )
    world.store.put_zone(zone)
    await world.bus.publish(live.ZONE_UPDATED, to_dict(zone))
    return to_dict(zone)


@router.get("/missions")
async def list_missions(request: Request, _: Operator) -> list[dict]:
    return to_dicts(_world(request).store.list_missions())


# -- what happened ---------------------------------------------------------


@router.get("/events")
async def list_events(request: Request, _: Operator, limit: int = 100) -> list[dict]:
    return [e.to_dict() for e in _world(request).store.list_events(limit=limit)]


# -- the live stream -------------------------------------------------------


@router.websocket("/stream")
async def stream(websocket: WebSocket, token: str = Query(default="")) -> None:
    """Live updates.

    The token arrives as a query parameter because a browser cannot set
    headers when opening a WebSocket. The same tokens and the same roles
    apply as on every other interface.
    """
    principal = websocket.app.state.tokens.lookup(token) if token else None
    if principal is None or not principal.has_role(ROLE_OPERATOR):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    world: WorldModel = websocket.app.state.world

    # A snapshot first, so an application that has just connected can draw
    # the whole picture without a second round of requests.
    await websocket.send_json(
        {
            "kind": "snapshot",
            "data": {
                "assets": assets_to_dicts(world.store.list_assets(), world.language),
                "telemetry": [t.to_dict() for t in world.telemetry.values()],
                "tracks": world.track_views(world.store.list_tracks()),
                "zones": to_dicts(world.store.list_zones()),
                "tasks": world.task_views(world.store.list_tasks(limit=50)),
                "events": [e.to_dict() for e in world.store.list_events(limit=50)],
            },
        }
    )

    subscription = world.bus.subscribe()
    try:
        while True:
            message = await subscription.queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("live stream ended unexpectedly")
    finally:
        subscription.close()
