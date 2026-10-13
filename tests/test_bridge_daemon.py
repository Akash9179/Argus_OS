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
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)   # a session starts released
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"

    clock["t"] += 1.0                      # silence past the timeout
    assert dog.check() is True             # trips exactly once
    assert dog.state == "LATCHED"
    assert dog.check() is False
    released_through_the_drain(dog, clock)

    # a press with throttle during latch does not re-arm
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.5, ready=True) is False
    assert dog.state == "LATCHED"
    # the explicit re-arm gesture does: release, then press at zero throttle
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"


def test_estop_latches_even_while_fed():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    dog.command(arm=True, estop=False, throttle=0.0, ready=True)
    assert dog.state == "DRIVING"
    assert dog.command(arm=True, estop=True, throttle=0.0, ready=True) is False
    assert dog.state == "LATCHED"


def test_voluntary_disarm_goes_to_stopped_not_latched():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    dog.command(arm=True, estop=False, throttle=0.0, ready=True)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    dog.disarm()
    assert dog.state == "STOPPED"
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


def test_link_lost_while_driving_latches():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    dog.command(arm=True, estop=False, throttle=0.0, ready=True)
    assert dog.link_lost() is True
    assert dog.state == "LATCHED"


# ------------------------------------------------- arm is a rising edge only
# The rule under test: the watchdog arms only on a false-to-true edge of the
# arm bit, never on a frame that merely continues arm=true. A session starts
# as if arm were held, so it needs one arm=false frame before a press counts.
# Every latch resets the detector the same way. A voluntary disarm keeps
# the bit of the frame that caused it. Frames
# queued in a stalled socket keep their stale arm and so can never re-arm.

def released_through_the_drain(dog, clock, step: float = 0.05):
    """A cockpit back after a silence: arm=false frames at its normal
    cadence for one watchdog window and a step. Frames received inside the
    window after a stall cannot release or press, so a test that re-arms
    after a silence streams through it first, as a real cockpit does."""
    held_until = clock["t"] + dog.timeout_s + step
    while clock["t"] <= held_until:
        dog.command(arm=False, estop=False, throttle=0.0, ready=True)
        clock["t"] += step


def fresh_driving_dog():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"
    return dog, clock


def test_a_latch_ignores_a_run_of_held_arm_frames():
    dog, clock = fresh_driving_dog()
    clock["t"] += 1.0
    assert dog.check() is True
    assert dog.state == "LATCHED"
    for _ in range(10):                    # stale frames draining a socket
        assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
        assert dog.state == "LATCHED"


def test_a_latch_rearms_on_release_then_press_at_zero_throttle():
    dog, clock = fresh_driving_dog()
    clock["t"] += 1.0
    dog.check()
    released_through_the_drain(dog, clock)
    assert dog.command(arm=False, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "LATCHED"
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"


def test_a_press_with_throttle_is_spent_and_holding_it_does_not_rearm():
    dog, clock = fresh_driving_dog()
    clock["t"] += 1.0
    dog.check()
    released_through_the_drain(dog, clock)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.5, ready=True) is False
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "LATCHED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


def test_the_confirmation_window_arms_once_and_stays_driving():
    """The cockpit asserts arm for up to 500 ms after a press: about 25
    frames at 50 Hz. The first arms; the rest are idempotent."""
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    for _ in range(25):
        clock["t"] += 0.02
        assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
        assert dog.state == "DRIVING"
        assert dog.check() is False


def test_a_session_first_frame_with_arm_does_not_arm():
    dog = Watchdog(timeout_s=0.7)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "STOPPED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


def test_after_link_loss_the_next_session_needs_a_fresh_press():
    dog, _ = fresh_driving_dog()
    assert dog.link_lost() is True
    # The reconnected session's first frames still carry the old arm.
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "LATCHED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"


def test_a_driver_change_while_stopped_also_needs_a_fresh_press():
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.link_lost() is False       # was not driving, nothing trips
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "STOPPED"


def test_estop_release_with_arm_held_stays_latched():
    dog, _ = fresh_driving_dog()
    dog.command(arm=True, estop=True, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "LATCHED"


def test_a_press_before_the_self_test_passed_does_not_arm_later():
    """The edge is on the operator's own arm bit. A press made while the
    self-test had not passed is spent; the green light arriving while the
    arm is still held is not a fresh act."""
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=False)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=False) is False
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
    assert dog.state == "STOPPED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


def test_ready_must_be_stated_by_every_caller():
    """No default: a caller that forgets the self-test verdict cannot
    fail open."""
    dog = Watchdog(timeout_s=0.7)
    with pytest.raises(TypeError):
        dog.command(arm=False, estop=False, throttle=0.0)
    with pytest.raises(TypeError):
        dog.command(False, False, 0.0, True)    # keyword only


def test_a_first_arm_also_needs_zero_throttle():
    """The bridge does not trust the cockpit's neutral-stick gate: arming
    from STOPPED needs zero throttle, as re-arming from LATCHED does."""
    dog = Watchdog(timeout_s=0.7)
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.3, ready=True) is False
    assert dog.state == "STOPPED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"


# ------------------------------------- a receive gap is a stall in any state
# The rule under test: a gap between two command frames, on the watchdog's
# own clock, longer than its window is a stall, whatever the state. After a
# stall the edge detector holds for one more window: frames that drain in a
# burst land inside it, so no frame in the burst can be the release or the
# press. An edge proves order, not freshness.

def test_a_burst_after_a_stall_cannot_arm_from_stopped():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    clock["t"] += 1.0                      # the socket stalls while STOPPED
    # the queue drains at once: releases, a press, then throttle
    burst = [(False, 0.0), (False, 0.0), (True, 0.0), (True, 0.5), (True, 0.5)]
    for arm, throttle in burst:
        assert dog.command(arm=arm, estop=False, throttle=throttle, ready=True) is False
        assert dog.state == "STOPPED"


def test_the_first_late_frame_reports_the_stall():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.stalled is False
    clock["t"] += 0.71
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.stalled is True
    clock["t"] += 0.05
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.stalled is False


def test_a_gap_inside_the_window_is_not_a_stall():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    clock["t"] += 0.69
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.stalled is False
    assert dog.state == "DRIVING"


def test_after_a_stall_a_release_then_press_past_the_window_arms():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    clock["t"] += 1.0
    dog.command(arm=True, estop=False, throttle=0.0, ready=True)   # the drain
    released_through_the_drain(dog, clock)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True
    assert dog.state == "DRIVING"


def test_a_held_arm_through_the_window_still_needs_a_release():
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    clock["t"] += 1.0
    for _ in range(30):                    # arm held, frames at 20 Hz
        assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is False
        clock["t"] += 0.05
    assert dog.state == "STOPPED"
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


def test_a_command_gap_while_driving_latches_even_with_heartbeats():
    """Heartbeats keep the silence check fed, but a command frame that
    comes after a gap longer than the window is still a stall. While
    DRIVING it latches on that frame, before its throttle reaches the
    vehicle."""
    dog, clock = fresh_driving_dog()
    for _ in range(10):                    # heartbeats only, 100 ms apart
        clock["t"] += 0.1
        dog.feed()
        assert dog.check() is False
    assert dog.command(arm=True, estop=False, throttle=0.5, ready=True) is False
    assert dog.state == "LATCHED"
    assert dog.stalled is True


def test_a_new_session_does_not_inherit_the_last_frame_time():
    """link_lost starts the next driver's session clean: its first command
    frame has no predecessor to measure a gap from."""
    clock = {"t": 0.0}
    dog = Watchdog(timeout_s=0.7, now=lambda: clock["t"])
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    dog.link_lost()
    clock["t"] += 5.0
    dog.command(arm=False, estop=False, throttle=0.0, ready=True)
    assert dog.stalled is False
    assert dog.command(arm=True, estop=False, throttle=0.0, ready=True) is True


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

    c.send(drive_frame(arm=False))     # a session's first frame never arms
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
    c.send(drive_frame(arm=False))     # a session's first frame never arms
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


def make_reporter(vehicle, name=None):
    from bridge.link_reporter import LinkReporter
    r = LinkReporter.__new__(LinkReporter)
    from sim.link_client import LinkClient
    r.vehicle = vehicle
    r.lat, r.lon = 51.5055, -0.118
    r.name = name
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


def declarations(r):
    """The telemetry messages the reporter sent that carry a payload."""
    from link.v1.messages_pb2 import Telemetry as LinkTelemetry

    out = []
    for topic, raw in r._link.published:
        if not topic.endswith("telemetry"):
            continue
        tel = LinkTelemetry(); tel.ParseFromString(raw)
        if tel.HasField("payload"):
            out.append(tel)
    return out


def test_reporter_with_a_name_declares_it_in_a_registry_manifest():
    """The same declaration the sim makes, so TRACK shows the name."""
    from google.protobuf.json_format import MessageToDict

    r = make_reporter(MockVehicle(), name="Tessy")
    r.declare()
    r.step(dt=0.5, send_heartbeat=True)

    declared = declarations(r)
    assert len(declared) == 1
    payload = MessageToDict(declared[0].payload)
    assert payload == {"registry": {"manifest": {"name": "Tessy"}}}
    assert declared[0].asset_id == "01BENCHUGV0000000000000001"


def test_reporter_without_a_name_declares_nothing():
    """No name was given, so none is invented: TRACK keeps its fallback."""
    r = make_reporter(MockVehicle())
    r.declare()
    r.step(dt=0.5, send_heartbeat=True)

    assert declarations(r) == []
    # Ordinary reporting is unaffected.
    assert any(t.endswith("telemetry") for t, _ in r._link.published)
    assert any(t.endswith("heartbeat") for t, _ in r._link.published)


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
    c.send(drive_frame(arm=False))            # release the stop and the arm
    c.send(drive_frame(throttle=0.0))         # explicit re-arm: a fresh press
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


def wait_for_event(d, predicate, timeout: float = 2.0) -> list:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = read_events(d.log.path)
        if any(predicate(e) for e in events):
            return events
        time.sleep(0.02)
    raise AssertionError("expected log event never arrived")


def test_queued_armed_frames_after_a_lost_link_do_not_rearm(daemon):
    """The stalled-socket gap. A driver's link dies while DRIVING and the
    vehicle latches. The next session's first frames still carry arm=true,
    as frames queued before the cockpit noticed would. They must not
    re-arm. Only a release then a press does, and the log records it as a
    re-arm in that session, as before."""
    d, port = daemon
    a = WsClient(port)
    a.send({"t": "auth", "password": "pw"})
    a.recv_until("role")
    a.send(drive_frame(arm=False))
    a.recv_until("preflight")
    a.send(drive_frame())
    deadline = time.monotonic() + 2
    while a.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    a.close()
    wait_for_event(d, lambda e: e["event"] == "latched" and e.get("reason") == "link_lost")
    assert d.watchdog.state == "LATCHED"

    b = WsClient(port)
    b.send({"t": "auth", "password": "pw"})
    assert b.recv_until("role")["role"] == "DRIVER"
    for _ in range(5):                       # the stale burst, all armed
        b.send(drive_frame(throttle=0.0))
    b.send({"t": "preflight"})               # read in order after the burst
    b.recv_until("preflight")
    assert d.watchdog.state == "LATCHED"

    b.send(drive_frame(arm=False))           # release
    b.send(drive_frame(throttle=0.0))        # fresh press
    deadline = time.monotonic() + 2
    while b.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    b.send(drive_frame(arm=False))           # disarm before leaving
    b.send({"t": "preflight"})
    b.recv_until("preflight")
    b.close()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        events = read_events(d.log.path)
        if sum(e["event"] == "session_close" for e in events) == 2:
            break
        time.sleep(0.02)
    sessions = [e["session"] for e in events if e["event"] == "session_open"]
    story_b = [e["event"] for e in events if e.get("session") == sessions[1]]
    assert story_b == [
        "session_open", "preflight", "rearmed", "disarmed", "preflight",
        "session_close",
    ]


def test_a_withdrawn_self_test_under_a_held_arm_does_not_rearm(daemon):
    """DRIVING, then ignition off with the arm still held: the self-test is
    withdrawn and the daemon disarms. Ignition back on with the arm still
    held passes the self-test again, but that is not a fresh press."""
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
    c.send(drive_frame(ignition=False))       # arm held, green light gone
    assert c.recv_until("preflight")["pass"] is False
    assert d.watchdog.state == "STOPPED"
    c.send(drive_frame())                     # ignition back, arm still held
    assert c.recv_until("preflight")["pass"] is True
    assert d.watchdog.state == "STOPPED"
    c.send(drive_frame(arm=False))            # release, then a fresh press
    c.send(drive_frame())
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    c.close()


def test_a_press_with_throttle_does_not_arm_and_logs_nothing(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")
    c.send(drive_frame(arm=False))
    c.recv_until("preflight")
    c.send(drive_frame(throttle=0.3))         # press with throttle held
    c.send({"t": "preflight"})                # read in order after it
    c.recv_until("preflight")
    assert d.watchdog.state == "STOPPED"
    assert not any(e["event"] in ("armed", "rearmed")
                   for e in read_events(d.log.path))
    c.send(drive_frame(arm=False))            # release, then press at zero
    c.send(drive_frame(throttle=0.0))
    deadline = time.monotonic() + 2
    while c.recv_until("telemetry")["safetyState"] != "DRIVING":
        assert time.monotonic() < deadline
    c.send(drive_frame(arm=False))
    c.send({"t": "preflight"})
    c.recv_until("preflight")
    armed = [e for e in read_events(d.log.path) if e["event"] == "armed"]
    assert len(armed) == 1
    c.close()


class RecordingVehicle(MockVehicle):
    """The mock, with every command that reached it kept."""

    def __init__(self) -> None:
        super().__init__()
        self.applied: list[Command] = []

    def apply(self, cmd: Command) -> None:
        self.applied.append(cmd)
        super().apply(cmd)


def test_a_queued_press_drained_after_a_stall_does_not_arm_or_move(tmp_path):
    """Codex P1. STOPPED; the socket stalls; the operator presses arm and
    pushes throttle inside the cockpit's confirmation window; the request
    expires. When the queue drains, its frames hold a valid release then
    press edge at zero throttle. They arrive past the watchdog window, so
    they are a stall's drain: nothing arms and nothing moves. A release and
    a press sent after the drain, at a cockpit's cadence, arm as normal."""
    vehicle = RecordingVehicle()
    d = BridgeDaemon(vehicle, operators=two_operators(),
                     host="127.0.0.1", port=0, watchdog_timeout_s=0.3,
                     log_path=tmp_path / "sessions.jsonl")
    d.start()
    try:
        c = WsClient(d._server.getsockname()[1])
        c.send({"t": "auth", "password": "pw"})
        c.recv_until("role")
        c.send(drive_frame(arm=False))           # STOPPED, ignition on
        c.recv_until("preflight")
        assert d.watchdog.state == "STOPPED"

        time.sleep(0.5)                           # the stall, past 300 ms
        burst = ([drive_frame(arm=False)] * 3 + [drive_frame(throttle=0.0)]
                 + [drive_frame(throttle=0.6)] * 5 + [drive_frame(arm=False)])
        for frame in burst:                       # the queue drains at once
            c.send(frame)
        c.send({"t": "preflight"})                # read in order after it
        c.recv_until("preflight")

        assert d.watchdog.state == "STOPPED"
        events = read_events(d.log.path)
        assert not any(e["event"] in ("armed", "rearmed") for e in events)
        assert any(e["event"] == "stall" for e in events)
        assert all(cmd.throttle == 0.0 for cmd in vehicle.applied)
        assert vehicle.read().speedKmh == 0.0

        deadline = time.monotonic() + 0.4         # released past the window
        while time.monotonic() < deadline:
            c.send(drive_frame(arm=False))
            time.sleep(0.05)
        c.send(drive_frame(throttle=0.0))         # the fresh press
        deadline = time.monotonic() + 2
        while c.recv_until("telemetry")["safetyState"] != "DRIVING":
            assert time.monotonic() < deadline
        c.close()
    finally:
        d.stop()


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


def test_hammering_the_door_locks_it_even_for_the_right_key(tmp_path):
    """Auth rate limiting (the last daemon-side R-8 item): repeated failed
    attempts from one address shut that address out for the window, and
    the lockout applies to a correct token too, which is what makes a
    brute-force sweep pointless. The lockout expires; a person who fat
    fingered their token twice is not locked out forever."""
    d = BridgeDaemon(MockVehicle(), operators=two_operators(),
                     host="127.0.0.1", port=0, watchdog_timeout_s=0.3,
                     log_path=tmp_path / "sessions.jsonl",
                     auth_max_failures=2, auth_window_s=0.5)
    d.start()
    port = d._server.getsockname()[1]
    try:
        for _ in range(2):
            c = WsClient(port)
            c.send({"t": "auth", "token": "wrong"})
            assert c.recv().get("reason") == "auth"

        blocked = WsClient(port)
        blocked.send({"t": "auth", "token": "pw"})     # right key, locked door
        assert blocked.recv().get("reason") == "rate_limited"

        events = read_events(d.log.path)
        assert any(e["event"] == "auth_rate_limited" for e in events)

        time.sleep(0.6)                                # the window passes
        again = WsClient(port)
        again.send({"t": "auth", "token": "pw"})
        assert again.recv_until("role")["role"] == "DRIVER"
        again.close()
    finally:
        d.stop()


def test_a_successful_auth_clears_the_slate(tmp_path):
    """Typos then the right token is a person, not an attack: a success
    wipes the address's failure count, so the same number of typos again
    does not add up to a lockout across the success."""
    d = BridgeDaemon(MockVehicle(), operators=two_operators(),
                     host="127.0.0.1", port=0, watchdog_timeout_s=0.3,
                     log_path=tmp_path / "sessions.jsonl",
                     auth_max_failures=5, auth_window_s=60.0)
    d.start()
    port = d._server.getsockname()[1]
    try:
        for _ in range(4):                      # one short of the limit
            c = WsClient(port)
            c.send({"t": "auth", "token": "typo"})
            assert c.recv().get("reason") == "auth"

        ok = WsClient(port)
        ok.send({"t": "auth", "token": "pw"})   # the person gets in
        assert ok.recv_until("role")["role"] == "DRIVER"
        ok.close()

        for _ in range(4):                      # 4 + 4 > 5, but the slate is clean
            c = WsClient(port)
            c.send({"t": "auth", "token": "typo"})
            assert c.recv().get("reason") == "auth"

        again = WsClient(port)
        again.send({"t": "auth", "token": "pw2"})
        assert again.recv_until("role")["role"] == "DRIVER"
        again.close()
    finally:
        d.stop()


# --------------------------------------------------------- session facts


def test_role_carries_the_session_facts_a_cockpit_shows(daemon):
    """Driver name, the machine's name (none here), and the watchdog window,
    so the cockpit states link-loss behaviour with the daemon's own figure."""
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    role = c.recv_until("role")
    assert role["role"] == "DRIVER"
    assert role["driver"] == "Akash"
    assert role["vehicle"] is None
    assert role["watchdog_ms"] == 300
    c.close()


def test_preflight_checks_carry_a_sentence(daemon):
    d, port = daemon
    c = WsClient(port)
    c.send({"t": "auth", "password": "pw"})
    c.recv_until("role")
    cmd = Command(gear="F", ignition=True).to_wire(); cmd["t"] = "cmd"
    c.send(cmd)
    pf = c.recv_until("preflight")
    labels = {chk["name"]: chk["label"] for chk in pf["checks"]}
    assert labels["mcu_link"] == "Control link answers"
    assert labels["watchdog"] == "Watchdog armed"
    # the firmware's own fields survive beside the sentence
    assert all({"name", "ok", "detail", "label"} <= set(chk) for chk in pf["checks"])
    c.close()


def test_a_frame_that_may_not_drive_still_carries_the_brake():
    """The rebuilt not-armed Command must keep aux.brake: dropping it would
    send the vehicle a brake release the operator never asked for."""
    from bridge.daemon import BridgeDaemon
    from bridge.identity import OperatorDirectory
    import inspect
    src = inspect.getsource(BridgeDaemon._handle)
    assert "brake=cmd.brake" in src
