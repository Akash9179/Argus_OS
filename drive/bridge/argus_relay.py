#!/usr/bin/env python3
"""
ARGUS relay — sits between the public internet (Tailscale Funnel) and the local
Remo Go server, and enforces the two things Remo itself cannot:

  1. PASSWORD  — every client must send `AUTH:<password>` as its first frame.
                 Wrong/absent -> the connection is dropped before any token flows.
  2. SINGLE-OPERATOR LOCK — only ONE authenticated client is the DRIVER at a time;
                 its tokens are forwarded to Remo. Everyone else is a SPECTATOR
                 (their drive tokens are ignored). When the driver leaves, the relay
                 sends neutral (P42/L0/R0) to Remo and promotes the oldest spectator.

Each client is told its role via a `ROLE:DRIVER` / `ROLE:SPECTATOR` text frame, and
upstream telemetry is broadcast to everyone. Pure stdlib (Jetson has no pip).

    ARGUS_PASSWORD=secret python3 argus_relay.py            # listen :8090 -> ws://localhost:8080/ws
    ARGUS_PASSWORD=secret python3 argus_relay.py --port 8090 --upstream ws://localhost:8080/ws

Expose with:  tailscale funnel 8090
"""
import argparse, base64, hashlib, os, socket, struct, sys, threading, time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
NEUTRAL = ["P42", "L0", "R0"]
IDLE_MS = 700        # dead-man: neutralize if the driver goes silent this long
HEARTBEAT = "HB"     # client keepalive — resets the dead-man, never reaches the Arduino

# ───────────────────────── WebSocket frame helpers ─────────────────────────
def _server_handshake(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        c = conn.recv(4096)
        if not c:
            return False
        data += c
    key = None
    for line in data.split(b"\r\n"):
        if line.lower().startswith(b"sec-websocket-key:"):
            key = line.split(b":", 1)[1].strip()
    if not key:
        return False
    accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()).decode()
    conn.sendall((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n\r\n" % accept
    ).encode())
    return True

def _recv_frame(conn, buf):
    def need(n):
        while len(buf) < n:
            c = conn.recv(4096)
            if not c:
                raise ConnectionError
            buf.extend(c)
        out = bytes(buf[:n]); del buf[:n]
        return out
    b0, b1 = need(2)
    opcode = b0 & 0x0F
    masked = b1 & 0x80
    ln = b1 & 0x7F
    if ln == 126: ln = struct.unpack(">H", need(2))[0]
    elif ln == 127: ln = struct.unpack(">Q", need(8))[0]
    mask = need(4) if masked else b""
    data = need(ln) if ln else b""
    if masked:
        data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
    return opcode, data

def _send_text_server(conn, s):
    p = s.encode()
    n = len(p)
    if n < 126:
        header = bytes([0x81, n])
    elif n < 65536:
        header = bytes([0x81, 126]) + struct.pack(">H", n)
    else:
        header = bytes([0x81, 127]) + struct.pack(">Q", n)
    conn.sendall(header + p)

# ───────────────────────── upstream client to Remo ─────────────────────────
class Upstream:
    """Persistent WS client to the Remo server, with auto-reconnect."""
    def __init__(self, url, on_telemetry):
        self.url = url
        self.on_telemetry = on_telemetry
        self.sock = None
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _connect(self):
        # parse ws://host:port/path
        rest = self.url.split("://", 1)[1]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        port = int(port or 80)
        s = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        ).encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += s.recv(4096)
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError("upstream handshake failed")
        s.settimeout(None)   # blocking reads — telemetry is sparse, don't time out idle links
        return s

    def _run(self):
        while True:
            try:
                self.sock = self._connect()
                rbuf = bytearray()          # fresh frame buffer per connection
                print("[relay] upstream connected: %s" % self.url)
                while True:
                    op, data = _recv_frame(self.sock, rbuf)
                    if op == 0x8:
                        break
                    if op in (0x1, 0x2) and data:
                        self.on_telemetry(data.decode("utf-8", "replace"))
            except Exception as e:
                print("[relay] upstream down (%s); retrying in 2s" % e)
                self.sock = None
                time.sleep(2)

    def send(self, token):
        with self.lock:
            s = self.sock
            if not s:
                return False
            try:
                p = token.encode()
                mask = os.urandom(4)
                masked = bytes(b ^ mask[i % 4] for i, b in enumerate(p))
                s.sendall(bytes([0x81, 0x80 | len(p)]) + mask + masked)
                return True
            except OSError:
                return False

# ───────────────────────────── relay state ─────────────────────────────
class Client:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.role = None
        self.wlock = threading.Lock()
    def send(self, msg):
        try:
            with self.wlock:
                _send_text_server(self.conn, msg)
        except OSError:
            pass

class Relay:
    def __init__(self, password, upstream_url):
        self.password = password
        self.clients = []          # authed clients, in arrival order
        self.driver = None
        self.driver_last_seen = 0.0
        self.driver_neutralized = False
        self.lock = threading.Lock()
        self.auth_fails = {}       # ip -> fail count, for brute-force backoff
        self.auth_lock = threading.Lock()
        self.upstream = Upstream(upstream_url, self._broadcast)
        threading.Thread(target=self._deadman_loop, daemon=True).start()

    # ── brute-force backoff ──
    def note_auth_fail(self, ip):
        with self.auth_lock:
            c = self.auth_fails.get(ip, 0) + 1
            self.auth_fails[ip] = c
            return min(c, 10) * 0.5      # grows to a 5s delay per attempt

    def clear_auth(self, ip):
        with self.auth_lock:
            self.auth_fails.pop(ip, None)

    # ── dead-man: hold the vehicle at neutral if the driver's link stalls ──
    def _deadman_loop(self):
        while True:
            time.sleep(0.15)
            fire = False
            with self.lock:
                if self.driver is not None:
                    idle = time.monotonic() - self.driver_last_seen
                    if idle > IDLE_MS / 1000.0 and not self.driver_neutralized:
                        self.driver_neutralized = True
                        fire = True
            if fire:
                for t in NEUTRAL:
                    self.upstream.send(t)
                print("[relay] DEAD-MAN: driver silent >%dms -> neutral" % IDLE_MS)

    def _broadcast(self, msg):
        with self.lock:
            targets = list(self.clients)
        for c in targets:
            c.send(msg)

    def _promote_locked(self):
        """Assign a driver if there is none. Caller holds self.lock."""
        if self.driver is None and self.clients:
            self.driver = self.clients[0]
            self.driver.role = "DRIVER"
            self.driver_last_seen = time.monotonic()   # fresh clock for the new driver
            self.driver_neutralized = False
            self.driver.send("ROLE:DRIVER")

    def add(self, client):
        with self.lock:
            self.clients.append(client)
            if self.driver is None:
                self._promote_locked()
            else:
                client.role = "SPECTATOR"
                client.send("ROLE:SPECTATOR")

    def remove(self, client):
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)
            was_driver = client is self.driver
            if was_driver:
                self.driver = None
        if was_driver:
            for t in NEUTRAL:               # vehicle to neutral the instant the driver drops
                self.upstream.send(t)
            with self.lock:
                self._promote_locked()

    def on_token(self, client, token):
        # only the active driver actuates
        if client is not self.driver:
            return
        self.driver_last_seen = time.monotonic()   # any frame keeps the dead-man alive
        self.driver_neutralized = False
        if token == HEARTBEAT:
            return                                  # keepalive only — never forwarded
        self.upstream.send(token)

def serve_client(relay, conn, addr):
    if not _server_handshake(conn):
        conn.close(); return
    client = Client(conn, addr)
    buf = bytearray()
    try:
        conn.settimeout(10)
        op, data = _recv_frame(conn, buf)            # first frame MUST be AUTH
        conn.settimeout(None)
        msg = data.decode("utf-8", "replace") if op in (0x1, 0x2) else ""
        if not msg.startswith("AUTH:") or msg[5:] != relay.password:
            delay = relay.note_auth_fail(addr[0])    # throttle brute-force from this IP
            print("[relay] AUTH failed from %s (backoff %.1fs)" % (addr, delay))
            time.sleep(delay)
            try: _send_text_server(conn, "AUTH:FAIL")
            except OSError: pass
            conn.close(); return
        relay.clear_auth(addr[0])
        print("[relay] AUTH ok from %s" % (addr,))
        relay.add(client)
        while True:
            op, data = _recv_frame(conn, buf)
            if op == 0x8:
                break
            if op in (0x1, 0x2) and data:
                relay.on_token(client, data.decode("utf-8", "replace"))
    except (ConnectionError, OSError):
        pass
    finally:
        relay.remove(client)
        print("[relay] client gone %s (role=%s)" % (addr, client.role))
        conn.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--upstream", default="ws://localhost:8080/ws")
    ap.add_argument("--password", default=os.environ.get("ARGUS_PASSWORD", ""))
    args = ap.parse_args()
    if not args.password:
        sys.exit("Refusing to start without a password. Set ARGUS_PASSWORD or --password.")

    relay = Relay(args.password, args.upstream)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(16)
    print("[relay] listening :%d  ->  %s  (single-operator, password-gated)" % (args.port, args.upstream))
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=serve_client, args=(relay, conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
