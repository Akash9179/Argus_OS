"""Stage 4's definition of done, as a test.

Three criteria from the plan: an operator with no briefing beyond "push to
talk" can ask what is happening and send a machine to a named place by
voice; every exchange is printed; and a deliberately ambiguous order
produces a clarifying question rather than an action.

The language service is scripted here rather than called. That is not a
shortcut around the hard part: what these tests check is the part this
repository wrote, which is what the system does with an interpretation
once it has one. Whether a particular model interprets a particular
sentence well is a property of that model, it changes when the model
changes, and a test that asserted it would be testing the weather.

The world model is real. Voice reaches it over the same HTTP interfaces
C2 uses, carrying the operator's own token, so an order issued here goes
through the same endpoint, the same authorisation, and the same audit
trail as an order issued from the map.
"""

from __future__ import annotations

import httpx
import pytest
from link.v1.ontology_pb2 import TaskState

from gateway.capabilities import (
    Capability,
    LanguageResponse,
    Speech,
    Transcription,
)
from gateway.policy import Profile
from gateway.service import Gateway
from voice import intent as intents
from voice.service import VoiceService, load_character
from voice.world import WorldModel

from tests.conftest import OPERATOR_TOKEN, SITE_LAT, SITE_LON, a_manifest, wait_until


# -- a language service that says exactly what a test tells it to say ------


class ScriptedLanguage:
    """Stands in for whichever model the profile would have picked."""

    name = "scripted"

    def __init__(self, answers: list[dict] | None = None):
        self.answers = list(answers or [])
        self.seen: list = []

    def capabilities(self) -> set[Capability]:
        return {Capability.UNDERSTAND_ORDER, Capability.ANSWER_QUESTION}

    @property
    def leaves_the_machine(self) -> bool:
        return False

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    def understand(self, request) -> LanguageResponse:
        self.seen.append(request)
        data = self.answers.pop(0) if self.answers else {"kind": "unclear"}
        return LanguageResponse(text="", data=data)


class SilentSpeech:
    """Speech, without spending a second per test rendering audio."""

    name = "silent"

    def capabilities(self) -> set[Capability]:
        return {Capability.TRANSCRIBE, Capability.SPEAK}

    @property
    def leaves_the_machine(self) -> bool:
        return False

    def available(self) -> tuple[bool, str]:
        return True, "ready"

    def transcribe(self, request) -> Transcription:
        return Transcription(text=request.audio.decode(), confidence=None)

    def speak(self, request) -> Speech:
        return Speech(audio=b"RIFF....", audio_format="wav", text=request.text)


def an_order(**changes) -> dict:
    """What a language service returns when it understood an order."""
    answer = {
        "kind": "order",
        "answer": "",
        "clarifying_question": "",
        "readback": "Send Scout 1 to Gate 3?",
        "machine_name": "Scout 1",
        "task_type": "navigate",
        "place_name": "Gate 3",
    }
    answer.update(changes)
    return answer


def a_question(answer: str) -> dict:
    return {
        "kind": "question",
        "answer": answer,
        "clarifying_question": "",
        "readback": "",
        "machine_name": "",
        "task_type": "",
        "place_name": "",
    }


def an_ambiguity(question: str) -> dict:
    return {
        "kind": "unclear",
        "answer": "",
        "clarifying_question": question,
        "readback": "",
        "machine_name": "",
        "task_type": "",
        "place_name": "",
    }


@pytest.fixture
def voice(app, gate_zone):
    """A voice service wired to the real world model over HTTP."""

    def _make(answers: list[dict] | None = None) -> tuple[VoiceService, ScriptedLanguage]:
        language = ScriptedLanguage(answers)
        gateway = Gateway(
            profile=Profile(
                name="test",
                adapters={
                    "transcribe": ["silent"],
                    "speak": ["silent"],
                    "understand_order": ["scripted"],
                    "answer_question": ["scripted"],
                },
                allows_cloud=False,
            ),
            adapters={"scripted": language, "silent": SilentSpeech()},
        )
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://server"
        )
        world = WorldModel(base_url="http://server", token=OPERATOR_TOKEN, client=client)
        return (
            VoiceService(gateway=gateway, world=world, character=load_character("ops")),
            language,
        )

    return _make


# -- criterion 1: ask what is happening ------------------------------------


async def test_an_operator_can_ask_what_is_happening(voice, world, make_machine):
    """And is answered honestly, in words, without system terms."""
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    service, language = voice(
        [a_question("Scout 1 is standing by. Nothing else is happening.")]
    )
    exchange = await service.listen(b"what is happening")

    assert exchange.heard == "what is happening"
    assert exchange.spoken == "Scout 1 is standing by. Nothing else is happening."
    assert exchange.kind == intents.KIND_QUESTION
    assert exchange.needs_confirmation is False

    # The language service was given the world in plain words, with no
    # schema terms and no raw confidence numbers to round away.
    given = language.seen[0].world
    assert "machines" in given and "places" in given and "contacts" in given
    flat = str(given).lower()
    for forbidden in ("asset_class", "track_state", "entity_id", "ontology"):
        assert forbidden not in flat


async def test_uncertainty_survives_the_trip_to_the_language_service(voice, world, make_machine):
    """The honesty law at the boundary: a weak contact is handed over as a
    weak contact, in the words an operator would hear, not as a number the
    language service could describe however it liked."""
    from tests.conftest import a_camera_seeing_a_person

    machine = make_machine(
        a_manifest(drivers=a_manifest()["drivers"] + [a_camera_seeing_a_person()])
    )
    machine.start()
    await wait_until(lambda: world.store.list_tracks())

    service, language = voice([a_question("There is a possible person, low confidence.")])
    await service.listen(b"anything out there")

    contacts = language.seen[0].world["contacts"]
    assert contacts, "the contact never reached the language service"
    assert contacts[0]["how_sure"] == "low confidence"
    assert "confidence" not in str(contacts[0].get("what", "")).lower()


# -- criterion 2: send a machine to a named place --------------------------


async def test_a_voice_order_waits_for_a_readback_then_goes_through_the_map_endpoint(
    voice, world, client, make_machine, gate_zone
):
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order()])
    exchange = await service.listen(b"send scout one to gate three")

    # It proposes. It does not act.
    assert exchange.kind == intents.KIND_ORDER
    assert exchange.needs_confirmation is True
    assert exchange.spoken == "Send Scout 1 to Gate 3?"
    assert exchange.action == {
        "machine": "Scout 1",
        "task_type": "navigate",
        "place": "Gate 3",
    }
    assert world.store.list_tasks() == [], "an order was issued before it was confirmed"

    # Confirmed, it goes.
    done = await service.confirm(exchange.exchange_id, confirmed=True)
    assert done.spoken == "Sent."

    tasks = await wait_until(lambda: world.store.list_tasks())
    assert len(tasks) == 1
    task = tasks[0]
    assert task.asset_id == machine.asset_id
    assert task.task_type == "navigate"

    # Through the same endpoint the map uses, recording the person and the
    # path. Not "the voice service": the operator.
    assert task.issued_by.channel == "voice"
    assert task.issued_by.principal_id == "operator-1"

    # And it went somewhere: the centre of the named place, not its edge.
    assert task.parameters.waypoints
    await wait_until(
        lambda: world.store.get_task(task.task_id).status
        in (TaskState.TASK_STATE_ACCEPTED, TaskState.TASK_STATE_RUNNING, TaskState.TASK_STATE_DONE),
        timeout=15,
    )


async def test_saying_no_to_a_readback_issues_nothing(voice, world, make_machine, gate_zone):
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order()])
    exchange = await service.listen(b"send scout one to gate three")
    assert exchange.needs_confirmation

    refused = await service.confirm(exchange.exchange_id, confirmed=False)
    assert refused.spoken == "Cancelled."
    assert world.store.list_tasks() == []
    assert service.pending_count == 0


async def test_a_readback_cannot_be_confirmed_twice(voice, world, make_machine, gate_zone):
    """A repeated yes must not send a second machine on its way."""
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order()])
    exchange = await service.listen(b"send scout one to gate three")
    await service.confirm(exchange.exchange_id, confirmed=True)
    await wait_until(lambda: world.store.list_tasks())

    again = await service.confirm(exchange.exchange_id, confirmed=True)
    assert again.spoken == "Cancelled."
    assert len(world.store.list_tasks()) == 1, "confirming twice issued two orders"


# -- criterion 3: ambiguity produces a question, not an action -------------


async def test_an_ambiguous_order_asks_rather_than_acting(voice, world, make_machine, gate_zone):
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    service, _ = voice([an_ambiguity("Which machine should go?")])
    exchange = await service.listen(b"send it over there")

    assert exchange.kind == intents.KIND_UNCLEAR
    assert exchange.spoken == "Which machine should go?"
    assert exchange.needs_confirmation is False
    assert world.store.list_tasks() == []


async def test_an_order_naming_an_unknown_machine_is_not_guessed_at(
    voice, world, make_machine, gate_zone
):
    """The language service can name anything. The system checks.

    This is the case that matters most: a model that confidently names a
    machine which does not exist must not cause the nearest one to drive
    away.
    """
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order(machine_name="Reaper 6", readback="Send Reaper 6 to Gate 3?")])
    exchange = await service.listen(b"send reaper six to gate three")

    assert exchange.kind == intents.KIND_UNCLEAR
    assert exchange.spoken == "I do not have a machine by that name."
    assert world.store.list_tasks() == []


async def test_an_order_naming_an_unknown_place_is_not_guessed_at(
    voice, world, make_machine, gate_zone
):
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order(place_name="The North Bridge")])
    exchange = await service.listen(b"send scout one to the north bridge")

    assert exchange.kind == intents.KIND_UNCLEAR
    assert exchange.spoken == "I do not have a place by that name."
    assert world.store.list_tasks() == []


async def test_an_order_with_no_readback_is_refused(voice, world, make_machine, gate_zone):
    """The readback is the safety mechanism, so a missing one is not
    papered over with a sentence composed here. An operator can only agree
    to words they were actually offered."""
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    service, _ = voice([an_order(readback="")])
    exchange = await service.listen(b"send scout one to gate three")

    assert exchange.kind == intents.KIND_UNCLEAR
    assert world.store.list_tasks() == []


# -- everything spoken is printed ------------------------------------------


async def test_everything_heard_and_everything_spoken_is_printed(voice, world, make_machine):
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    service, _ = voice([a_question("Scout 1 is standing by.")])
    exchange = await service.listen(b"what is scout one doing")

    # Both halves of the exchange are text, and the audio is the extra
    # rather than the record.
    assert exchange.heard
    assert exchange.spoken
    assert exchange.audio is not None
    assert exchange.spoken == "Scout 1 is standing by."


async def test_a_voice_that_cannot_speak_still_answers(voice, world, make_machine):
    """Losing the synthesiser must not lose the reply."""
    from gateway.capabilities import GatewayError

    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    service, _ = voice([a_question("Scout 1 is standing by.")])

    def _broken(_request):
        raise GatewayError("the synthesiser is not installed")

    service.gateway.speak = _broken

    exchange = await service.listen(b"what is scout one doing")
    assert exchange.spoken == "Scout 1 is standing by."
    assert exchange.audio is None


# -- over the interface C2 actually uses -----------------------------------


async def test_a_readback_survives_the_request_that_proposed_it(app, world, make_machine, gate_zone):
    """The bug this file originally missed.

    Every test above drives VoiceService directly, so all of them passed
    while the HTTP interface was broken: the service was rebuilt per
    request, pending readbacks lived on the instance, and every
    confirmation therefore found nothing to confirm. A voice order could
    never execute over the only interface C2 uses.

    This one goes through the app, so it fails if that regresses.
    """
    from httpx import ASGITransport, AsyncClient

    from voice.main import create_app

    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    language = ScriptedLanguage([an_order()])
    gateway = Gateway(
        profile=Profile(
            name="test",
            adapters={
                "transcribe": ["silent"],
                "speak": ["silent"],
                "understand_order": ["scripted"],
                "answer_question": ["scripted"],
            },
            allows_cloud=False,
        ),
        adapters={"scripted": language, "silent": SilentSpeech()},
    )

    # The voice service reaches the world model over HTTP; in this test
    # both apps live in the same process, so its client is pointed at the
    # world model's ASGI app rather than at a socket.
    world_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://server")
    voice_app = create_app(
        gateway=gateway,
        track_url="http://server",
        speak_replies=False,
        world_client=world_client,
    )

    async with AsyncClient(
        transport=ASGITransport(app=voice_app), base_url="http://voice"
    ) as caller:
        headers = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}

        # Two separate requests, as C2 makes them.
        proposed = await caller.post("/v1/voice/say", json={"text": "send scout one to gate three"}, headers=headers)
        assert proposed.status_code == 200
        body = proposed.json()
        assert body["needs_confirmation"] is True
        assert world.store.list_tasks() == []

        answered = await caller.post(
            "/v1/voice/confirm",
            json={"exchange_id": body["exchange_id"], "confirmed": True},
            headers=headers,
        )
        assert answered.status_code == 200
        assert answered.json()["spoken"] == "Sent."

    tasks = await wait_until(lambda: world.store.list_tasks())
    assert len(tasks) == 1
    assert tasks[0].issued_by.channel == "voice"
    await world_client.aclose()


async def test_one_operator_cannot_confirm_another_operators_readback(voice, world, make_machine, gate_zone):
    """Pending readbacks are namespaced per caller.

    Sharing the store across requests is what makes confirmation work at
    all; sharing it across people would let anyone signed in send a
    machine somewhere on the strength of an order they never heard.
    """
    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    shared: dict = {}
    first, _ = voice([an_order()])
    first._pending = shared
    first._caller = "operator-a"

    second, _ = voice([])
    second._pending = shared
    second._caller = "operator-b"

    exchange = await first.listen(b"send scout one to gate three")
    assert exchange.needs_confirmation

    stolen = await second.confirm(exchange.exchange_id, confirmed=True)
    assert stolen.spoken == "Cancelled."
    assert world.store.list_tasks() == [], "another operator's readback was confirmed"

    # The operator who was actually asked can still answer it.
    mine = await first.confirm(exchange.exchange_id, confirmed=True)
    assert mine.spoken == "Sent."
    await wait_until(lambda: world.store.list_tasks())


# -- what the audit found: honesty when the world cannot be read ----------


async def test_an_unreachable_world_model_is_not_reported_as_an_empty_one(voice, world, make_machine):
    """"I could not look" and "there is nothing there" are different answers.

    Reads used to be flattened to an empty list on any failure, so a dead
    link made every order come back "I do not have a machine by that
    name" — a confident claim about a world the system could not see.
    """
    from voice.world import WorldUnavailable

    machine = make_machine(a_manifest(name="Scout 1"))
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    service, _ = voice([an_order()])

    async def _blind():
        raise WorldUnavailable("the world model is not answering")

    service.world.view = _blind

    exchange = await service.listen(b"send scout one to gate three")
    assert exchange.kind == intents.KIND_UNCLEAR
    assert exchange.spoken == "I cannot see the map right now."
    assert "machine by that name" not in exchange.spoken
    assert world.store.list_tasks() == []


async def test_a_credential_the_world_model_rejects_never_reaches_the_gateway(app, world):
    """The header shape is not a credential.

    Without this check any string beginning with "Bearer " reached the
    gateway, which under a bench profile means an unauthenticated caller
    could spend an API budget and be answered.
    """
    from httpx import ASGITransport, AsyncClient

    from voice.main import create_app

    language = ScriptedLanguage([a_question("this should never be reached")])
    gateway = Gateway(
        profile=Profile(
            name="test",
            adapters={
                "transcribe": ["silent"],
                "speak": ["silent"],
                "understand_order": ["scripted"],
                "answer_question": ["scripted"],
            },
            allows_cloud=False,
        ),
        adapters={"scripted": language, "silent": SilentSpeech()},
    )
    world_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://server")
    voice_app = create_app(
        gateway=gateway,
        track_url="http://server",
        speak_replies=False,
        world_client=world_client,
    )

    async with AsyncClient(
        transport=ASGITransport(app=voice_app), base_url="http://voice"
    ) as caller:
        refused = await caller.post(
            "/v1/voice/say",
            json={"text": "what is happening"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert refused.status_code == 401
    assert refused.json()["detail"] == "You are not signed in."
    assert language.seen == [], "an unauthenticated caller reached the language service"
    await world_client.aclose()


async def test_the_voice_and_the_feed_describe_one_contact_the_same_way():
    """Two phrases for one number would teach an operator to trust neither."""
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    feed = yaml.safe_load((root / "track" / "data" / "event_templates.yaml").read_text())
    voice_words = yaml.safe_load((root / "voice" / "data" / "world_language.yaml").read_text())

    assert feed["confidence"]["bands"] == voice_words["confidence"]["bands"], (
        "the voice and the event feed no longer describe confidence the same way"
    )


async def test_capabilities_cannot_be_asked_without_a_credential(app):
    """Answering it runs every adapter's availability check, and one of
    those makes an outbound request. An unauthenticated caller must not
    reach the gateway at all, however cheaply."""
    from httpx import ASGITransport, AsyncClient

    from voice.main import create_app

    class Counting(SilentSpeech):
        checked = 0

        def available(self):
            Counting.checked += 1
            return True, "ready"

    gateway = Gateway(
        profile=Profile(name="test", adapters={"transcribe": ["silent"]}, allows_cloud=False),
        adapters={"silent": Counting()},
    )
    voice_app = create_app(gateway=gateway, track_url="http://server", speak_replies=False)

    async with AsyncClient(
        transport=ASGITransport(app=voice_app), base_url="http://voice"
    ) as caller:
        refused = await caller.get("/v1/voice/capabilities")

    assert refused.status_code == 401
    assert Counting.checked == 0, "an unauthenticated caller reached the gateway"


async def test_a_blind_service_answers_without_touching_the_gateway(app, world):
    """When the world model is unreachable the credential has not been
    checked, so nothing may reach the gateway: not hearing, not speaking.
    The reply is text, which is the record the honesty law asks for."""
    from httpx import ASGITransport, AsyncClient

    from voice.main import create_app

    class Exploding(SilentSpeech):
        def transcribe(self, request):
            raise AssertionError("an unchecked credential reached the recogniser")

        def speak(self, request):
            raise AssertionError("an unchecked credential reached the synthesiser")

    language = ScriptedLanguage([a_question("never reached")])
    gateway = Gateway(
        profile=Profile(
            name="test",
            adapters={
                "transcribe": ["silent"],
                "speak": ["silent"],
                "understand_order": ["scripted"],
            },
            allows_cloud=False,
        ),
        adapters={"scripted": language, "silent": Exploding()},
    )
    # No world client and a host that does not resolve: unreachable, not
    # unauthorised.
    voice_app = create_app(
        gateway=gateway, track_url="http://127.0.0.1:9", speak_replies=True
    )

    async with AsyncClient(
        transport=ASGITransport(app=voice_app), base_url="http://voice"
    ) as caller:
        answered = await caller.post(
            "/v1/voice/say",
            json={"text": "what is happening"},
            headers={"Authorization": "Bearer unchecked"},
        )

    assert answered.status_code == 200
    body = answered.json()
    assert body["spoken"] == "I cannot see the map right now."
    assert body["audio"] is None
    assert body["needs_confirmation"] is False
    assert language.seen == []


async def test_the_voice_and_the_feed_name_a_contact_the_same_way():
    """A boat in the feed must not be a vessel in the voice."""
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    feed = yaml.safe_load((root / "track" / "data" / "event_templates.yaml").read_text())
    voice_words = yaml.safe_load((root / "voice" / "data" / "world_language.yaml").read_text())

    assert feed["class_labels"] == voice_words["class_labels"]
    assert feed["unknown_class_label"] == voice_words["unknown_class_label"]


async def test_the_voice_refuses_in_the_same_words_the_world_model_does():
    """An operator meets one system, not two."""
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    feed = yaml.safe_load((root / "track" / "data" / "event_templates.yaml").read_text())["errors"]
    mine = yaml.safe_load((root / "voice" / "data" / "refusals.yaml").read_text())["refusals"]

    for shared in ("not_signed_in", "not_allowed"):
        assert mine[shared] == feed[shared], f"{shared} is worded differently by the voice service"
