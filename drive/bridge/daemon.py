"""The bridge daemon: cockpit WebSocket in, VehicleAdapter out.

Session rules (inherited from the relay that preceded this daemon):
  - AUTH FIRST: the first frame must be {"t":"auth","password":...}.
    Wrong or absent: the connection drops before anything else happens.
  - SINGLE DRIVER: one authenticated client is the DRIVER; its commands
    reach the vehicle. Everyone else is a SPECTATOR receiving telemetry.
    When the driver leaves, the watchdog trips (if driving), the vehicle
    safe-stops, and the oldest spectator is promoted.
  - WATCHDOG: operator silence beyond the timeout while driving latches
    the vehicle stopped. Re-arm is explicit (arm=true, throttle=0).

Threads: one accept loop, one reader per client, one tick loop
(vehicle physics + watchdog poll + telemetry broadcast).
"""
from __future__ import annotations

import json
import socket
import threading
import time

from .contract import Command
from .vehicle import VehicleAdapter
from .watchdog import Watchdog
from . import wsproto

TICK_HZ = 50
TELEMETRY_HZ = 10


class _Client:
    def __init__(self, conn: socket.socket, addr) -> None:
        self.conn = conn
        self.addr = addr
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
        password: str,
        host: str = "0.0.0.0",
        port: int = 8090,
        watchdog_timeout_s: float = 0.7,
    ) -> None:
        if not password:
            raise ValueError("a password is required; set ARGUS_PASSWORD")
        self.vehicle = vehicle
        self.password = password
        self.host = host
        self.port = port
        self.watchdog = Watchdog(timeout_s=watchdog_timeout_s)
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
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._tick_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.vehicle.safe_stop()
        if self._server:
            self._server.close()

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
            if not msg or msg.get("t") != "auth" or msg.get("password") != self.password:
                try:
                    wsproto.send_text(conn, json.dumps({"t": "error", "reason": "auth"}))
                finally:
                    conn.close()
                return
            conn.settimeout(None)
        except (OSError, wsproto.WsError):
            conn.close()
            return

        client = _Client(conn, addr)
        with self._lock:
            self._clients.append(client)
            if self._driver is None:
                self._driver = client
        client.send({"t": "role", "role": self._role_of(client)})

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
            self._run_preflight()
            return
        if t != "cmd" or client is not self._driver:
            return
        cmd = Command.from_wire(msg)
        if cmd.ignition and not self._ignition_was_on:
            self._run_preflight()          # ignition just came on
        elif not cmd.ignition and self._ignition_was_on:
            self.preflight = {"ran": False, "pass": False, "checks": []}
            self._broadcast_preflight()    # ignition off invalidates the green light
        self._ignition_was_on = cmd.ignition
        # the green light gates arming; nothing arms on a failed or absent self-test
        effective_arm = cmd.arm and self.preflight["pass"]
        may_drive = self.watchdog.command(effective_arm, cmd.estop, cmd.throttle)
        if self.watchdog.state == "DRIVING" and not effective_arm:
            self.watchdog.disarm()
            may_drive = False
        if not may_drive:
            # state controls (ignition, lights, gear) still apply; motion does not
            cmd = Command(
                steer=0.0, throttle=0.0, gear=cmd.gear, mode=cmd.mode,
                ignition=cmd.ignition, headlights=cmd.headlights,
                blinker=cmd.blinker, horn=cmd.horn, record=cmd.record,
                arm=cmd.arm, estop=cmd.estop,
            )
        self.vehicle.apply(cmd)

    def _drop(self, client: _Client) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
            if client is self._driver:
                if self.watchdog.link_lost():
                    self.vehicle.safe_stop()
                self._driver = min(self._clients, key=lambda c: c.joined) if self._clients else None
                promoted = self._driver
            else:
                promoted = None
        try:
            client.conn.close()
        except OSError:
            pass
        if promoted:
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
            if self.watchdog.check():
                self.vehicle.safe_stop()
            n += 1
            if n % telemetry_every == 0:
                self._broadcast_telemetry()
            time.sleep(dt)

    def _run_preflight(self) -> None:
        checks = self.vehicle.self_test()
        self.preflight = {
            "ran": True,
            "pass": all(c["ok"] for c in checks),
            "checks": checks,
        }
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
