"""drive/bridge: contract, mock vehicle, watchdog, and daemon-over-socket."""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import time

import pytest

from bridge.contract import Command, Telemetry
from bridge.identity import Operator, OperatorDirectory
from bridge.session_log import read_events
from bridge.vehicle import MockVehicle
from bridge.watchdog import Watchdog
from bridge.daemon import BridgeDaemon
from bridge import wsproto


# ------------------------------------------------------------------ contract
def test_command_round_trip_preserves_all_fields():
    cmd = Command(steer=-0.5, throttle=0.8, gear="R", ignition=True,
                  headlights=True, blinker="left", horn=True, record=True,
                  arm=True, estop=False)
    again = Command.from_wire(cmd.to_wire())
    assert again == cmd


def test_command_from_wire_clamps_and_defaults_garbage():
    cmd = Command.from_wire({"steer": -9, "throttle": "lots", "gear": "X",
                             "aux": {"blinker": "party"}, "safety": None})
    assert cmd.steer == -1.0
    assert cmd.throttle == 0.0
    assert cmd.gear == "N"
    assert cmd.blinker == "off"
    assert cmd.arm is False


def test_telemetry_wire_shape_matches_cockpit_contract():
    wire = Telemetry().to_wire()
    for key in ("speedKmh", "gear", "steerAngleDeg", "mode", "armed",
                "safetyState", "battery", "lights", "recording", "ignition"):
        assert key in wire
    assert wire["t"] == "telemetry"


# -------------------------------------------------------------- mock vehicle
def advance(v: MockVehicle, seconds: float, dt: float = 0.02):
    t = 0.0
    while t < seconds:
        v.tick(dt)
        t += dt


def test_no_motion_without_ignition():
    v = MockVehicle()
    v.apply(Command(throttle=1.0, gear="F", ignition=False, arm=True))
    advance(v, 2.0)
    assert v.read().speedKmh == 0.0


def test_no_motion_in_neutral():
    v = MockVehicle()
    v.apply(Command(throttle=1.0, gear="N", ignition=True, arm=True))
    advance(v, 2.0)
    assert v.read().speedKmh == 0.0


def test_drives_forward_and_safe_stop_halts_but_keeps_ignition():
    v = MockVehicle()
    v.apply(Command(throttle=0.5, gear="F", ignition=True, headlights=True, arm=True))
    advance(v, 3.0)
    assert v.read().speedKmh > 5.0
    v.safe_stop()
    advance(v, 3.0)
    tel = v.read()
    assert tel.speedKmh == 0.0
    assert tel.ignition is True
    assert tel.lights["headlights"] is True


def test_battery_drains_under_throttle():
    v = MockVehicle()
    v.apply(Command(throttle=1.0, gear="F", ignition=True, arm=True))
    advance(v, 10.0)
    assert v.read().battery["percent"] < 100.0


# ----------------------------------------------------------------- watchdog
def test_watchdog_full_cycle_stopped_driving_latched_rearm():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    assert dog.state == "STOPPED"
    assert dog.command(arm=True, estop=False, throttle=0.0) is True
    assert dog.state == "DRIVING"

    clock["t"] += 1.0                      # silence past the timeout
    assert dog.check() is True             # trips exactly once
    assert dog.state == "LATCHED"
    assert dog.check() is False

    # throttle during latch does not re-arm
    assert dog.command(arm=True, estop=False, throttle=0.5) is False
    assert dog.state == "LATCHED"
    # the explicit re-arm gesture does
    assert dog.command(arm=True, estop=False, throttle=0.0) is True
    assert dog.state == "DRIVING"


def test_estop_latches_even_while_fed():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=True, estop=False, throttle=0.0)
    assert dog.command(arm=True, estop=True, throttle=0.0) is False
    assert dog.state == "LATCHED"


def test_voluntary_disarm_goes_to_stopped_not_latched():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=True, estop=False, throttle=0.0)
    dog.disarm()
    assert dog.state == "STOPPED"
    assert dog.command(arm=True, estop=False, throttle=0.0) is True


def test_link_lost_while_driving_latches():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=True, estop=False, throttle=0.0)
    assert dog.link_lost() is True
    assert dog.state == "LATCHED"


# ----------------------------------------------------- daemon over a socket
class WsClient:
    """Tiny client-side WebSocket for tests (client frames must be masked)."""

    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        key = base64.b64encode(b"0123456789abcdef").decode()
        self.sock.sendall(
            (f"GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
             f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
             f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        data = b""
        while b"\r\n\r\n" not in data:
            data += self.sock.recv(4096)
        assert b"101" in data.split(b"\r\n")[0]

    def send(self, obj: dict):
        payload = json.dumps(obj).encode()
        mask = b"\x11\x22\x33\x44"
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        if n < 126:
            head = bytes([0x81, 0x80 | n])
        else:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        self.sock.sendall(head + mask + masked)

    def recv(self, timeout: float = 3.0) -> dict:
        self.sock.settimeout(timeout)
        return json.loads(wsproto.read_text(self.sock))

    def recv_until(self, t: str, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.recv(timeout=deadline - time.monotonic())
            if msg.get("t") == t:
                return msg
        raise AssertionError(f"no {t!r} message within {timeout}s")

    def close(self):
        self.sock.close()


def two_operators() -> OperatorDirectory:
    """The fixture crew. "pw" stays a valid token so the wire idiom the
    older tests use (the cockpit's auth frame, secret under "password")
    keeps proving it still works."""
    return OperatorDirectory({
        "pw": Operator(operator_id="op-akash", display_name="Akash"),
        "pw2": Operator(operator_id="op-guest", display_name="Guest"),
    })


@pytest.fixture
def daemon(tmp_path):
    d = BridgeDaemon(MockVehicle(), operators=two_operators(),
                     host="127.0.0.1", port=0, watchdog_timeout_s=0.3,
                     log_path=tmp_path / "sessions.jsonl")
    d.start()
    port = d._server.getsockname()[1]
    yield d, port
    d.stop()


def test_wrong_password_is_rejected(daemon):
    _, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "nope"})
    assert c.recv().get("reason") == "auth"


def test_auth_role_telemetry_and_control(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    assert c.recv_until("role")["role"] == "DRIVER"

    cmd = Command(gear="F", ignition=True, arm=True).to_wire()
    cmd["t"] = "cmd"
    c.send(cmd)
    tel = c.recv_until("telemetry")
    deadline = time.monotonic() + 2
    while tel["safetyState"] != "DRIVING" and time.monotonic() < deadline:
        tel = c.recv_until("telemetry")
    assert tel["safetyState"] == "DRIVING"
    assert tel["ignition"] is True
    c.close()


def test_second_client_is_spectator(daemon):
    _, port = daemon
    a, b = WsClient(port), WsClient(port)
    # The daemon assigns DRIVER to whichever auth it processes first, by
    # design. Sending both auths before reading A's role made this a race
    # on which handler thread ran first, so serialize: A must hold the
    # driver seat before B even asks.
    a.send({"t": "auth", "password": "pw"})
    assert a.recv_until("role")["role"] == "DRIVER"
    b.send({"t": "auth", "password": "pw"})
    assert b.recv_until("role")["role"] == "SPECTATOR"
    a.close()
    b.close()


def test_driver_silence_latches_the_vehicle(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")
    cmd = Command(gear="F", throttle=0.0, ignition=True, arm=True).to_wire()
    cmd["t"] = "cmd"
    c.send(cmd)
    # then say nothing: watchdog (300ms) must latch
    deadline = time.monotonic() + 3
    state = None
    while time.monotonic() < deadline:
        state = c.recv_until("telemetry")["safetyState"]
        if state == "LATCHED":
            break
    assert state == "LATCHED"
    c.close()


# ----------------------------------------------------------------- preflight
def test_mock_self_test_passes_when_healthy():
    checks = MockVehicle().self_test()
    assert len(checks) >= 4
    assert all(c["ok"] for c in checks)
    assert {"name", "ok", "detail"} <= set(checks[0].keys())


def test_arm_refused_until_ignition_runs_preflight(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")

    # arm WITHOUT ignition: no preflight has run, so the daemon must not arm
    cmd = Command(gear="F", arm=True, ignition=False).to_wire(); cmd["t"] = "cmd"
    c.send(cmd)
    tel = c.recv_until("telemetry")
    assert tel["safetyState"] == "STOPPED"
    assert d.preflight["ran"] is False

    # ignition on: preflight runs and is broadcast, green light
    cmd = Command(gear="F", ignition=True).to_wire(); cmd["t"] = "cmd"
    c.send(cmd)
    pf = c.recv_until("preflight")
    assert pf["ran"] is True and pf["pass"] is True
    assert all(ch["ok"] for ch in pf["checks"])

    # now arming works
    cmd = Command(gear="F", ignition=True, arm=True).to_wire(); cmd["t"] = "cmd"
    c.send(cmd)
    deadline = time.monotonic() + 2
    state = None
    while time.monotonic() < deadline:
        state = c.recv_until("telemetry")["safetyState"]
        if state == "DRIVING":
            break
    assert state == "DRIVING"

    # ignition off invalidates the green light
    cmd = Command(gear="F", ignition=False).to_wire(); cmd["t"] = "cmd"
    c.send(cmd)
    pf = c.recv_until("preflight")
    assert pf["ran"] is False and pf["pass"] is False
    c.close()


# -------------------------------------------------------------- link reporter
class FakeLink:
    """In-memory VehicleLink capturing publishes."""

    def __init__(self):
        self.published = []
        self._handlers = {}

    def publish(self, topic, payload):
        self.published.append((topic, payload))

    def subscribe(self, topic, handler):
        self._handlers[topic] = handler

    def start(self):
        pass

    def stop(self):
        pass

    @property
    def connected(self):
        return True


def make_reporter(vehicle):
    from bridge.link_reporter import LinkReporter
    r = LinkReporter.__new__(LinkReporter)
    from sim.link_client import LinkClient
    r.vehicle = vehicle
    r.lat, r.lon = 51.5055, -0.118
    r._link = FakeLink()
    r._client = LinkClient("01BENCHUGV0000000000000001", r._link, "argus", on_task=lambda t: None)
    import threading
    r._stop = threading.Event()
    return r


def test_reporter_heartbeat_and_telemetry_reflect_the_vehicle():
    from link.v1.messages_pb2 import Heartbeat, Telemetry as LinkTelemetry

    v = MockVehicle()
    v.apply(Command(gear="F", ignition=True, arm=True, throttle=1.0))
    advance(v, 5.0)
    r = make_reporter(v)
    r.step(dt=1.0, send_heartbeat=True)

    topics = [t for t, _ in r._link.published]
    hb_raw = [p for t, p in r._link.published if t.endswith("heartbeat")]
    tel_raw = [p for t, p in r._link.published if t.endswith("telemetry")]
    assert hb_raw and tel_raw, topics

    hb = Heartbeat(); hb.ParseFromString(hb_raw[0])
    assert hb.asset_class == "ugv"
    assert 0 < hb.battery_fraction <= 1

    tel = LinkTelemetry(); tel.ParseFromString(tel_raw[0])
    assert tel.speed_mps > 1


def test_reporter_dead_reckons_north():
    v = MockVehicle()
    r = make_reporter(v)
    lat0, lon0 = r.lat, r.lon
    r.dead_reckon(speed_mps=5.0, heading_deg=0.0, dt=10.0)  # 50 m north
    assert r.lat > lat0
    assert abs(r.lon - lon0) < 1e-9
    assert abs((r.lat - lat0) * 111_320.0 - 50.0) < 0.5


def test_reporter_standby_when_not_driving():
    from link.v1.messages_pb2 import Heartbeat
    from link.v1.ontology_pb2 import ASSET_STATUS_STANDBY

    v = MockVehicle()  # ignition off, not armed
    r = make_reporter(v)
    r.step(dt=0.5, send_heartbeat=True)
    hb_raw = [p for t, p in r._link.published if t.endswith("heartbeat")][0]
    hb = Heartbeat(); hb.ParseFromString(hb_raw)
    assert hb.status == ASSET_STATUS_STANDBY


# ------------------------------------- identity and the session log (ADR-0009)
def drive_frame(**changes) -> dict:
    kwargs = {"gear": "F", "ignition": True, "arm": True}
    kwargs.update(changes)
    cmd = Command(**kwargs).to_wire()
    cmd["t"] = "cmd"
    return cmd


def test_each_operator_is_who_their_token_says(daemon):
    """Two people, two tokens, two identities; the wire key stays "password"
    for the cockpit and "token" also works."""
    d, port = daemon
    a, b = WsClient(port), WsClient(port)
    a.send({"t": "auth", "password": "pw"})
    assert a.recv_until("role")["role"] == "DRIVER"
    b.send({"t": "auth", "token": "pw2"})
    assert b.recv_until("role")["role"] == "SPECTATOR"
    a.close()
    b.close()

    events = read_events(d.log.path)
    opened = [e for e in events if e["event"] == "session_open"]
    assert [(e["operator_id"], e["role"]) for e in opened] == [
        ("op-akash", "DRIVER"),
        ("op-guest", "SPECTATOR"),
    ]


def test_a_token_nobody_holds_is_refused_and_recorded(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "token": "not-a-token"})
    assert c.recv().get("reason") == "auth"

    events = read_events(d.log.path)
    assert any(e["event"] == "auth_failed" for e in events)
    # A secret that failed must not end up written down.
    assert "not-a-token" not in (d.log.path.read_text())


def test_a_directory_with_no_operators_refuses_to_start():
    with pytest.raises(ValueError):
        BridgeDaemon(MockVehicle(), operators=OperatorDirectory({}),
                     host="127.0.0.1", port=0)


def test_a_session_can_be_reconstructed_from_its_log(daemon, tmp_path):
    """The ADR-0009 acceptance: an incident review can replay who did what.

    One scripted session: connect, ignition on (preflight), arm, estop,
    re-arm, disconnect. The log alone must tell that story, in order,
    attributed to the operator.
    """
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")

    c.send(drive_frame(arm=False))            # ignition on, not yet armed
    c.recv_until("preflight")
    c.send(drive_frame())                     # arm
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    c.send(drive_frame(estop=True))           # emergency stop, latches
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "LATCHED":
        assert time.monotonic() < deadline
    c.send(drive_frame(throttle=0.0))         # explicit re-arm
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    c.close()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        events = read_events(d.log.path)
        if any(e["event"] == "session_close" for e in events):
            break
        time.sleep(0.05)

    mine = [e for e in events if e.get("session")]
    session = mine[0]["session"]
    assert all(e["session"] == session for e in mine), "one session, one id"

    story = [e["event"] for e in mine]
    assert story == [
        "session_open", "ignition", "preflight", "armed",
        "latched", "rearmed", "latched", "session_close",
    ]
    opened = mine[0]
    assert opened["operator_id"] == "op-akash"
    assert opened["role"] == "DRIVER"
    assert mine[story.index("preflight")]["pass"] is True
    latches = [e for e in mine if e["event"] == "latched"]
    assert latches[0]["reason"] == "estop"
    # Closing the socket while DRIVING is a lost link, and the log says so.
    assert latches[1]["reason"] == "link_lost"
    assert all(e["ts"] <= later["ts"] for e, later in zip(mine, mine[1:]))


def test_silence_while_driving_is_latched_in_the_log(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")
    c.send(drive_frame(arm=False))
    c.recv_until("preflight")
    c.send(drive_frame())
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    # then say nothing; the 300ms dog trips
    deadline = time.monotonic() + 3
    while c.recv_until("telemetry", timeout=3)["safetyState"] != "LATCHED":
        assert time.monotonic() < deadline

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        latched = [e for e in read_events(d.log.path) if e["event"] == "latched"]
        if latched:
            break
        time.sleep(0.05)
    assert latched and latched[0]["reason"] == "operator_silence"
    c.close()


def test_operator_directory_round_trips_through_its_file(tmp_path):
    from bridge.identity import OperatorDirectory

    path = tmp_path / "operators.json"
    first = OperatorDirectory.from_file(path)   # creates a starter crew
    assert len(first) > 0
    again = OperatorDirectory.from_file(path)   # loads the same file
    assert len(again) == len(first)
    text = path.read_text()
    assert "operator" in text


def test_an_empty_token_is_refused_at_load_not_at_the_door(tmp_path):
    """A missing auth field reads as ""; an operator whose token was ""
    would authenticate anyone who sent no secret at all."""
    with pytest.raises(ValueError):
        OperatorDirectory({"": Operator(operator_id="op-x", display_name="X")})

    path = tmp_path / "operators.json"
    path.write_text(json.dumps({"operators": [
        {"token": "same", "operator_id": "op-a"},
        {"token": "same", "operator_id": "op-b"},
    ]}))
    with pytest.raises(ValueError):
        OperatorDirectory.from_file(path)
