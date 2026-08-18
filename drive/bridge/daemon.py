"""The bridge daemon: cockpit WebSocket in, VehicleAdapter out.

Session rules (inherited from the relay that preceded this daemon):
  - AUTH FIRST: the first frame must be {"t":"auth", ...} carrying a
    per-operator token (under "token", or "password" for the cockpit's
    older frame shape). An unknown or absent token: the connection drops
    before anything else happens, and the failure is logged without the
    secret that failed.
  - SINGLE DRIVER: one authenticated client is the DRIVER; its commands
    reach the vehicle. Everyone else is a SPECTATOR receiving telemetry.
    When the driver leaves, the watchdog trips (if driving), the vehicle
    safe-stops, and the oldest spectator is promoted.
  - WATCHDOG: operator silence beyond the timeout while driving latches
    the vehicle stopped. Re-arm is explicit (arm=true, throttle=0).

Every safety-relevant transition lands in the session log as it happens
(ADR-0009): who connected, ignition, preflight verdicts, armed, latched
and why, re-armed, who left. An incident review reads the log, not the
operators' memories.

Threads: one accept loop, one reader per client, one tick loop
(vehicle physics + watchdog poll + telemetry broadcast).
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid

from .contract import Command
from .identity import Operator, OperatorDirectory
from .session_log import SessionLog
from .vehicle import VehicleAdapter
from .watchdog import Watchdog
from . import wsproto

TICK_HZ = 50
TELEMETRY_HZ = 10


class _Client:
    def __init__(self, conn: socket.socket, addr, operator: Operator) -> None:
        self.conn = conn
        self.addr = addr
        self.operator = operator
        self.session = uuid.uuid4().hex[:12]
        self.joined = time.monotonic()
        self.send_lock = threading.Lock()

    def send(self, obj: dict) -> bool:
        try:
            with self.send_lock:
                wsproto.send_text(self.conn, json.dumps(obj))
            return True
        except OSError:
            return False


class BridgeDaemon:
    def __init__(
        self,
        vehicle: VehicleAdapter,
        operators: OperatorDirectory,
        host: str = "0.0.0.0",
        port: int = 8090,
        watchdog_timeout_s: float = 0.7,
        log_path=None,
        auth_max_failures: int = 5,
        auth_window_s: float = 60.0,
    ) -> None:
        if len(operators) == 0:
            raise ValueError(
                "at least one operator token is required; see the operators file"
            )
        self.vehicle = vehicle
        self.operators = operators
        self.host = host
        self.port = port
        self.log = SessionLog(log_path)
        # Failed-auth rate limiting, per source address (risk R-8). Enough
        # failures inside the window lock that address out, correct token
        # included, until the window passes. A success clears the slate:
        # one typo then the right token is a person, not an attack.
        self._auth_max_failures = auth_max_failures
        self._auth_window_s = auth_window_s
        self._auth_failures: dict[str, list[float]] = {}
        self.watchdog = Watchdog(timeout_s=watchdog_timeout_s)
        # Serializes watchdog transitions against their log lines: without
        # it the tick thread can trip the dog between a reader thread's
        # before-read and its command, and the log would then miss a
        # re-arm that really happened. The log must never understate.
        self._wd_lock = threading.Lock()
        self.preflight: dict = {"ran": False, "pass": False, "checks": []}
        self._ignition_was_on = False
        self._clients: list[_Client] = []
        self._driver: _Client | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._server: socket.socket | None = None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._server = socket.create_server((self.host, self.port))
        self.log.event("daemon_start", vehicle=type(self.vehicle).__name__)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._tick_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.vehicle.safe_stop()
        if self._server:
            self._server.close()
        self.log.event("daemon_stop")
        self.log.close()

    # ------------------------------------------------------------ accept/read
    def _accept_loop(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, addr = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve_client, args=(conn, addr), daemon=True).start()

    def _serve_client(self, conn: socket.socket, addr) -> None:
        try:
            conn.settimeout(10)
            if not wsproto.server_handshake(conn):
                conn.close()
                return
            first = wsproto.read_text(conn)
            msg = _parse(first)
            if self._rate_limited(str(addr[0])):
                # Said plainly, not disguised as a wrong token: an operator
                # who locked themselves out deserves to know which problem
                # they have.
                self.log.event("auth_rate_limited", addr=str(addr[0]))
                try:
                    wsproto.send_text(conn, json.dumps({"t": "error", "reason": "rate_limited"}))
                finally:
                    conn.close()
                return
            # The cockpit's frame carries the secret under "password";
            # "token" is the same thing said plainly. Either way the value
            # is a per-operator token, and the shared password is gone.
            token = (msg or {}).get("token") or (msg or {}).get("password") or ""
            operator = self.operators.lookup(token) if msg and msg.get("t") == "auth" else None
            if operator is None:
                # The fact of the failure is logged; the secret never is.
                self._record_auth_failure(str(addr[0]))
                self.log.event("auth_failed", addr=str(addr[0]))
                try:
                    wsproto.send_text(conn, json.dumps({"t": "error", "reason": "auth"}))
                finally:
                    conn.close()
                return
            self._clear_auth_failures(str(addr[0]))
            conn.settimeout(None)
        except (OSError, wsproto.WsError):
            conn.close()
            return

        client = _Client(conn, addr, operator)
        with self._lock:
            self._clients.append(client)
            if self._driver is None:
                self._driver = client
        role = self._role_of(client)
        self.log.event(
            "session_open", session=client.session,
            operator_id=operator.operator_id, addr=str(addr[0]), role=role,
        )
        client.send({"t": "role", "role": role})

        try:
            while not self._stop.is_set():
                text = wsproto.read_text(conn)
                if text is None:
                    break
                msg = _parse(text)
                if not msg:
                    continue
                self._handle(client, msg)
        except (OSError, wsproto.WsError):
            pass
        finally:
            self._drop(client)

    # ------------------------------------------------------- auth limiting
    def _rate_limited(self, addr: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._auth_failures.get(addr, []) if now - t < self._auth_window_s]
            if recent:
                self._auth_failures[addr] = recent
            else:
                self._auth_failures.pop(addr, None)
            return len(recent) >= self._auth_max_failures

    def _record_auth_failure(self, addr: str) -> None:
        with self._lock:
            self._auth_failures.setdefault(addr, []).append(time.monotonic())

    def _clear_auth_failures(self, addr: str) -> None:
        with self._lock:
            self._auth_failures.pop(addr, None)

    # ---------------------------------------------------------------- logic
    def _role_of(self, client: _Client) -> str:
        return "DRIVER" if client is self._driver else "SPECTATOR"

    def _handle(self, client: _Client, msg: dict) -> None:
        t = msg.get("t")
        if t == "hb":
            if client is self._driver:
                self.watchdog.feed()
            return
        if t == "preflight" and client is self._driver:
            self._run_preflight(client)
            return
        if t != "cmd" or client is not self._driver:
            return
        cmd = Command.from_wire(msg)
        if cmd.ignition and not self._ignition_was_on:
            self.log.event("ignition", session=client.session, on=True)
            self._run_preflight(client)    # ignition just came on
        elif not cmd.ignition and self._ignition_was_on:
            self.log.event("ignition", session=client.session, on=False)
            self.preflight = {"ran": False, "pass": False, "checks": []}
            self._broadcast_preflight()    # ignition off invalidates the green light
        self._ignition_was_on = cmd.ignition
        # the green light gates arming; nothing arms on a failed or absent self-test
        effective_arm = cmd.arm and self.preflight["pass"]
        with self._wd_lock:
            before = self.watchdog.state
            may_drive = self.watchdog.command(effective_arm, cmd.estop, cmd.throttle)
            if self.watchdog.state == "DRIVING" and not effective_arm:
                self.watchdog.disarm()
                may_drive = False
            self._log_transition(client, before, self.watchdog.state, cmd.estop)
        if not may_drive:
            # state controls (ignition, lights, gear) still apply; motion does not
            cmd = Command(
                steer=0.0, throttle=0.0, gear=cmd.gear, mode=cmd.mode,
                ignition=cmd.ignition, headlights=cmd.headlights,
                blinker=cmd.blinker, horn=cmd.horn, record=cmd.record,
                arm=cmd.arm, estop=cmd.estop,
            )
        self.vehicle.apply(cmd)

    def _log_transition(self, client: _Client, before: str, after: str, estop: bool) -> None:
        """One watchdog transition, one line, with the reason stated."""
        if before == after:
            return
        if after == "DRIVING":
            event = "rearmed" if before == "LATCHED" else "armed"
            self.log.event(event, session=client.session)
        elif after == "LATCHED":
            self.log.event(
                "latched", session=client.session,
                reason="estop" if estop else "operator_silence",
            )
        elif after == "STOPPED":
            self.log.event("disarmed", session=client.session)

    def _drop(self, client: _Client) -> None:
        with self._lock:
            if client not in self._clients:
                return  # already dropped once; a send failure races the reader
            self._clients.remove(client)
            if client is self._driver:
                with self._wd_lock:
                    tripped = self.watchdog.link_lost()
                    if tripped:
                        self.log.event("latched", session=client.session, reason="link_lost")
                if tripped:
                    self.vehicle.safe_stop()
                self._driver = min(self._clients, key=lambda c: c.joined) if self._clients else None
                promoted = self._driver
            else:
                promoted = None
        self.log.event(
            "session_close", session=client.session,
            duration_s=round(time.monotonic() - client.joined, 3),
        )
        try:
            client.conn.close()
        except OSError:
            pass
        if promoted:
            self.log.event("role_promoted", session=promoted.session,
                           operator_id=promoted.operator.operator_id)
            promoted.send({"t": "role", "role": "DRIVER"})

    # ----------------------------------------------------------------- tick
    def _tick_loop(self) -> None:
        dt = 1.0 / TICK_HZ
        telemetry_every = TICK_HZ // TELEMETRY_HZ
        n = 0
        while not self._stop.is_set():
            tick = getattr(self.vehicle, "tick", None)
            if tick:
                tick(dt)
            with self._wd_lock:
                tripped = self.watchdog.check()
                if tripped:
                    driver = self._driver
                    self.log.event(
                        "latched", session=driver.session if driver else None,
                        reason="operator_silence",
                    )
            if tripped:
                self.vehicle.safe_stop()
            n += 1
            if n % telemetry_every == 0:
                self._broadcast_telemetry()
            time.sleep(dt)

    def _run_preflight(self, client: _Client) -> None:
        checks = self.vehicle.self_test()
        self.preflight = {
            "ran": True,
            "pass": all(c["ok"] for c in checks),
            "checks": checks,
        }
        self.log.event(
            "preflight", session=client.session,
            **{"pass": self.preflight["pass"]},
            failed=[c["name"] for c in checks if not c["ok"]],
        )
        self._broadcast_preflight()

    def _broadcast_preflight(self) -> None:
        msg = {"t": "preflight", **self.preflight}
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            c.send(msg)

    def _broadcast_telemetry(self) -> None:
        tel = self.vehicle.read()
        tel.safetyState = self.watchdog.state
        tel.armed = self.watchdog.state == "DRIVING"
        wire = tel.to_wire()
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            if not c.send(wire):
                self._drop(c)


def _parse(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None
