"""What the voice service knows about the world, and how it acts on it.

Over HTTP, through the same public interfaces C2 uses, carrying the
operator's own credentials. Two laws make that the only acceptable design:

* The SDK honesty law forbids a private route into the world model. Voice
  is an application on the same interfaces as everything else, and if
  those interfaces are not enough for voice then they are not enough.
* Orders must record who gave them. Forwarding the operator's token means
  `issued_by` names the person and the voice channel, rather than naming
  the voice service and losing the human.

The view handed to the language service is small and already in operator
words. No identifier, class name, or confidence number is in it: the
waterline holds on this side of the gateway, not on the far side of it.

Identifiers are kept in a separate map that never enters a prompt. The
language service names a machine the way an operator does, and the
identifier is looked up here afterwards. Putting a ULID in the payload
would mean a language model could echo one back into an operator's ear.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml

log = logging.getLogger(__name__)

DEFAULT_TRACK = "http://127.0.0.1:8100"
LANGUAGE = Path(__file__).parent / "data" / "world_language.yaml"

# TRACK's list endpoints have their own defaults. Asked for explicitly so a
# site with many contacts does not silently lose the older ones from the
# class join and have them described as unidentified.
PAGE = 2000


class NotSignedIn(RuntimeError):
    """The world model does not recognise this credential."""


class NotAllowed(RuntimeError):
    """The credential is recognised but lacks permission.

    Its own type because telling an authenticated operator they are "not
    signed in" is false, and sends them to fix the wrong thing.
    """


class WorldUnavailable(RuntimeError):
    """The world model could not be reached.

    Its own type because "I could not look" and "there is nothing there"
    are different answers, and the honesty law forbids giving the second
    when the first is true. An operator told "I do not have a machine by
    that name" when the real problem is a dead link has been actively
    misinformed.
    """


@lru_cache(maxsize=2)
def _words(path: str = str(LANGUAGE)) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text()) or {}


class WorldModel:
    """The world model, as the voice service sees it."""

    def __init__(
        self,
        base_url: str = DEFAULT_TRACK,
        token: str = "",
        timeout_s: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_s
        # An injected client lets a test point the voice service at a world
        # model running in the same process. It changes nothing about the
        # path taken: the same HTTP interfaces, the same token, the same
        # refusals. A test that reached past the interface would be
        # testing a system nobody deploys.
        self._client = client
        # Names to identifiers, and names to zone geometry. Both rebuilt on
        # every view, and neither ever leaves this object.
        self._names_to_ids: dict[str, str] = {}
        self._places: dict[str, dict[str, Any]] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def _get(self, path: str) -> Any:
        if self._client is not None:
            response = await self._client.get(
                f"{self._base}{path}", headers=self._headers(), timeout=self._timeout
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base}{path}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    # -- reading -----------------------------------------------------------

    async def view(self) -> dict[str, Any]:
        """A small, plain-language picture of now.

        Keys are chosen for a reader rather than for the schema: machines,
        places, contacts. A language service that never sees the word
        "asset" cannot use it back. Identifiers are deliberately absent;
        `identify` resolves a name to one afterwards.
        """
        self._names_to_ids = {}
        machines = []
        for asset in await self._read("/v1/assets"):
            name = asset.get("display_name", "")
            self._names_to_ids[name] = asset.get("asset_id", "")
            machines.append(
                {
                    "name": name,
                    "status": _plain_status(asset.get("status", "")),
                    "doing": _plain_task(asset),
                    "battery_percent": _percent(asset.get("battery_fraction")),
                }
            )

        # Geometry is kept out of the payload for the same reason
        # identifiers are: the language service needs to know a place is
        # called Gate 3, not where its corners are. Coordinates are looked
        # up here afterwards by `waypoints_for`.
        self._places = {}
        places = []
        for zone in await self._read("/v1/zones"):
            name = zone.get("name", "")
            self._places[name] = zone
            places.append({"name": name, "kind": zone.get("zone_type", "")})

        # A Track carries no class of its own: what a thing is belongs to
        # the Entity it tracks. Reading a field off the track would return
        # nothing forever and look like it worked.
        classes = {
            entity.get("entity_id", ""): entity.get("entity_class", "")
            for entity in await self._read(f"/v1/entities?limit={PAGE}")
        }

        contacts = []
        for track in await self._read(f"/v1/tracks?limit={PAGE}"):
            if track.get("state") == "TRACK_STATE_CLOSED":
                continue
            contacts.append(
                {
                    "what": _plain_class(classes.get(track.get("entity_id", ""))),
                    # The honesty law, at the boundary. The language service
                    # is handed the uncertainty in the same words the
                    # operator will hear it in, so it cannot round it away.
                    #
                    # A confidence of exactly 0.0 is absent from the JSON,
                    # because that is how protobuf encodes a zero on a
                    # field with no presence. Absent therefore means zero
                    # here, not unknown: a track always carries a
                    # confidence, so treating it as unknown would describe
                    # the least certain contact as the one we cannot rate.
                    "how_sure": _plain_confidence(track.get("confidence", 0.0)),
                    "last_seen": _plain_age(track),
                    # A lost track is a track whose position is a guess.
                    "still_seen": track.get("state") != "TRACK_STATE_LOST",
                }
            )

        return {"machines": machines, "places": places, "contacts": contacts}

    def identify(self, name: str) -> str:
        """The identifier for a machine the language service named.

        Looked up here rather than carried in the prompt, so no identifier
        ever reaches a language model or an operator's ear.
        """
        return self._names_to_ids.get(name, "")

    def waypoints_for(self, name: str) -> list[dict[str, float]]:
        """Where a named place is, as somewhere to drive to.

        The centre of the zone rather than its boundary: an operator who
        says "go to Gate 3" means inside it, and a machine that stopped on
        the perimeter would be technically obedient and practically
        useless.
        """
        zone = self._places.get(name)
        if not zone:
            return []
        exterior = (zone.get("geometry") or {}).get("exterior") or []
        points = [
            (p.get("latitude_deg"), p.get("longitude_deg"))
            for p in exterior
            if p.get("latitude_deg") is not None and p.get("longitude_deg") is not None
        ]
        if not points:
            return []
        return [
            {
                "latitude_deg": sum(p[0] for p in points) / len(points),
                "longitude_deg": sum(p[1] for p in points) / len(points),
            }
        ]

    async def check_credentials(self) -> None:
        """Ask the world model whether this operator is who they say.

        One small read, not a full view. The alternative was calling
        `view()` twice per exchange: once to check and once to use, which
        doubles the traffic and can read two different worlds a moment
        apart. The world model is the identity authority, so it is asked
        rather than a second one being invented here.

        Raises NotSignedIn for a rejected credential. An unreachable world
        model raises WorldUnavailable and is *not* treated as a rejection:
        a dead link must not tell an operator their credentials are wrong.
        """
        await self._read("/v1/assets?limit=1")

    async def _read(self, path: str) -> list[dict[str, Any]]:
        """Read, or say why not.

        Failure is raised rather than flattened to an empty list. An empty
        list is a claim about the world: it says there are no machines. If
        the truth is that we could not ask, the caller has to be able to
        tell those apart, because one of them is a sentence an operator
        will be told.
        """
        try:
            value = await self._get(path)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise NotSignedIn(path) from exc
            if exc.response.status_code == 403:
                raise NotAllowed(path) from exc
            raise WorldUnavailable(f"{path}: {exc}") from exc
        except Exception as exc:
            raise WorldUnavailable(f"{path}: {exc}") from exc
        return value if isinstance(value, list) else []

    # -- acting ------------------------------------------------------------

    async def create_task(
        self, asset_id: str, task_type: str, waypoints: list[dict[str, float]]
    ) -> dict[str, Any]:
        """Issue an order, through the endpoint the map uses.

        `channel` is "voice" so the audit trail distinguishes how an order
        arrived, while `issued_by` still names the operator: the same
        person, a different path.
        """
        body: dict[str, Any] = {
            "asset_id": asset_id,
            "task_type": task_type,
            "channel": "voice",
        }
        if waypoints:
            body["waypoints"] = waypoints

        if self._client is not None:
            response = await self._client.post(
                f"{self._base}/v1/tasks",
                json=body,
                headers=self._headers(),
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base}/v1/tasks", json=body, headers=self._headers()
                )
        response.raise_for_status()
        return response.json()


# -- turning schema into words ---------------------------------------------
#
# Every sentence below comes from voice/data/world_language.yaml. None of
# these functions may contain an operator-facing string: the plan puts
# every such string in data, and the first version of this file did not,
# which is why this comment is here.


def _plain_status(status: str) -> str:
    """A status in words.

    A value this build does not recognise is passed through in a readable
    form rather than collapsed to "unknown". The open-vocabulary rule says
    consumers preserve what they do not recognise, and a newer machine
    reporting a status this build predates should not lose it on the way
    to an operator.
    """
    words = _words().get("status", {})
    if status in words:
        return words[status]
    if not status:
        return words.get("not_reported", "")
    return status.removeprefix("ASSET_STATUS_").replace("_", " ").lower()


def _plain_class(entity_class: str | None) -> str:
    """What a contact is, in the words the feed uses for it.

    Same table as the world model's, so one contact is not a "vessel" to
    the voice and a "boat" in the feed. An unrecognised class is passed
    through rather than dropped, per the open-vocabulary rule.
    """
    words = _words()
    if not entity_class:
        return words.get("unknown_class_label", "")
    labels = words.get("class_labels", {})
    if entity_class in labels:
        return labels[entity_class]
    return entity_class.replace("_", " ")


def _plain_task(asset: dict[str, Any]) -> str:
    words = _words().get("task", {})
    return words.get("busy", "") if asset.get("current_task_id") else words.get("idle", "")


def _plain_confidence(confidence: Any) -> str:
    """Confidence as an operator hears it, never as a number.

    The bands come from data and are kept identical to the world model's,
    so the feed and the voice describe one contact the same way. Two
    different phrases for one number would teach an operator to trust
    neither.
    """
    words = _words().get("confidence", {})
    if confidence is None:
        return words.get("unknown", "")
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return words.get("unknown", "")
    for band in words.get("bands", []):
        if value < float(band.get("below", 0)):
            return str(band.get("phrase", ""))
    return words.get("unknown", "")


def _plain_age(track: dict[str, Any]) -> str:
    """How long ago, from the track's own last observation.

    Read from the timestamp rather than from the presence of history. A
    track with any history at all used to be reported as "recently", which
    described a contact last seen hours ago as if it were current.
    """
    words = _words().get("age", {})
    history = track.get("history") or []
    last = history[-1].get("timestamp") if history else None
    if not last:
        return words.get("unknown", "")

    try:
        seen = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if seen.tzinfo is None:
            # A timestamp without a zone would otherwise raise on the
            # subtraction below and surface to the operator as a failure
            # of the whole voice service.
            seen = seen.replace(tzinfo=timezone.utc)
        seconds = (datetime.now(timezone.utc) - seen).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return words.get("unknown", "")

    if seconds < 60:
        return words.get("just_now", "")
    if seconds < 3600:
        minutes = int(seconds // 60)
        if minutes == 1:
            return words.get("minute", "")
        return words.get("minutes", "").format(count=minutes)
    if seconds < 86400:
        hours = int(seconds // 3600)
        if hours == 1:
            return words.get("hour", "")
        return words.get("hours", "").format(count=hours)
    return words.get("older", "")


def _percent(fraction: Any) -> int | None:
    if fraction is None:
        return None
    try:
        return round(float(fraction) * 100)
    except (TypeError, ValueError):
        return None
