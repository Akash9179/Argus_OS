#!/usr/bin/env python3
"""
ARGUS test bridge — THROWAWAY scaffolding for bench-testing the Remo drive controller.

Talks to the existing Remo Go server over its WebSocket /ws using the same ASCII
tokens the Remo web UI sends:
    steering : L1/L0/R1/R0   (bang-bang, hold-to-steer)
    throttle : P<n>, n in [42,214], neutral/stop = P42

Zero dependencies (pure stdlib) because the Jetson has no pip / no websocket lib.

SAFETY: always run first with the drive wheels OFF THE GROUND. On exit / Ctrl-C
the bridge actively sends P42 + L0 + R0 (full neutral). It is the SOLE controller
— close the Remo web UI before using this (Remo writes the serial port with no
mutex; two writers corrupt tokens).

Usage:
    python3 argus_test_bridge.py                  # interactive REPL (default localhost:8080)
    python3 argus_test_bridge.py --mode neutral   # connect, send neutral, watch telemetry, exit (safe smoke test)
    python3 argus_test_bridge.py --host 1.2.3.4 --port 8080

REPL commands:
    t <0..1>      throttle, proportional   (P = round(42 + 172*x))
    p <42..214>   throttle, raw P value
    s <-1..1>     steer, using the current steer mode (bang or pwm)
    mode bang     steering = bang-bang with deadband (what the Remo UI does)
    mode pwm      steering = software PWM: pulse L1/L0 at duty=|s| to approximate proportional steer  [EXPERIMENT]
    L1 L0 R1 R0   send a raw token verbatim (any UPPERCASE line is sent as-is)
    stop          full neutral: P42 + L0 + R0
    help          show this
    q / quit      stop, then exit
"""
import argparse, atexit, base64, os, signal, socket, struct, sys, threading, time

# ---------- minimal RFC6455 WebSocket client (text frames only) ----------
class WS:
    def __init__(self, host, port, path="/ws"):
        self.sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key)
        )
        self.sock.sendall(req.encode())
        resp = self._read_until(b"\r\n\r\n")
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError("WebSocket handshake failed: %r" % resp[:120])
        self._buf = b""
        self._lock = threading.Lock()

    def _read_until(self, marker):
        data = b""
        while marker not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("connection closed during handshake")
            data += chunk
        return data

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send_text(self, s):
        payload = s.encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        header = bytes([0x81])
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        with self._lock:
            self.sock.sendall(header + mask + masked)

    def recv_text(self):
        """Return next text-frame payload as str, or None on close."""
        while True:
            b0, b1 = self._recv_exact(2)
            opcode = b0 & 0x0F
            masked = b1 & 0x80
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            data = self._recv_exact(ln) if ln else b""
            if masked:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if opcode == 0x8:      # close
                return None
            if opcode == 0x9:      # ping -> pong
                self.send_text("")  # best-effort; server tolerates
                continue
            if opcode in (0x1, 0x2):
                return data.decode("utf-8", "replace")
            # ignore other control frames

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------- bridge ----------
DEADBAND = 0.12
PWM_HZ = 12.0  # software-PWM steering frequency

def throttle_to_P(x):
    x = max(0.0, min(1.0, x))
    return "P%d" % round(42 + 172 * x)

class Bridge:
    def __init__(self, ws):
        self.ws = ws
        self.steer_mode = "bang"
        self._steer_target = 0.0
        self._steer_state = 0       # -1 left, 0 center, +1 right (last token sent)
        self._stop_flag = threading.Event()
        self._closed = threading.Event()
        self._steer_thread = threading.Thread(target=self._steer_loop, daemon=True)
        self._steer_thread.start()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def send(self, tok):
        if self._closed.is_set():
            return
        try:
            self.ws.send_text(tok)
        except Exception as e:
            print("  [send failed: %s]" % e)

    def _rx_loop(self):
        try:
            while not self._stop_flag.is_set():
                msg = self.ws.recv_text()
                if msg is None:
                    print("\n  [server closed connection]")
                    return
                if msg:
                    print("\n  << telemetry: %s" % msg.strip())
        except Exception:
            return

    # --- steering ---
    def set_steer(self, v):
        self._steer_target = max(-1.0, min(1.0, v))
        if self.steer_mode == "bang":
            self._apply_bang()

    def _apply_bang(self):
        v = self._steer_target
        want = 1 if v > DEADBAND else (-1 if v < -DEADBAND else 0)
        if want == self._steer_state:
            return
        # release the old direction, engage the new
        if self._steer_state == 1: self.send("R0")
        if self._steer_state == -1: self.send("L0")
        if want == 1: self.send("R1")
        if want == -1: self.send("L1")
        self._steer_state = want

    def _steer_loop(self):
        """Software-PWM steering (experimental): only active in pwm mode."""
        while not self._stop_flag.is_set():
            if self.steer_mode != "pwm":
                time.sleep(0.05)
                continue
            v = self._steer_target
            duty = min(1.0, abs(v))
            if duty < DEADBAND:
                if self._steer_state == 1: self.send("R0")
                if self._steer_state == -1: self.send("L0")
                self._steer_state = 0
                time.sleep(0.05)
                continue
            on_tok, off_tok = ("R1", "R0") if v > 0 else ("L1", "L0")
            period = 1.0 / PWM_HZ
            on_t = period * duty
            off_t = period - on_t
            self.send(on_tok); self._steer_state = 1 if v > 0 else -1
            time.sleep(on_t)
            self.send(off_tok); self._steer_state = 0
            if off_t > 0:
                time.sleep(off_t)

    def set_throttle(self, x):
        self.send(throttle_to_P(x))

    def stop(self):
        self._steer_target = 0.0
        self.send("P42"); self.send("L0"); self.send("R0")
        self._steer_state = 0

    def shutdown(self):
        if self._closed.is_set():
            return
        self._stop_flag.set()
        # active neutral straight to the socket BEFORE marking closed / closing
        try:
            self.ws.send_text("P42"); self.ws.send_text("L0"); self.ws.send_text("R0")
        except Exception:
            pass
        self._steer_state = 0
        self._closed.set()
        self.ws.close()


def repl(bridge):
    print(__doc__.split("REPL commands:")[1])
    print("steer mode: %s   (type 'mode pwm' to try proportional steering)\n" % bridge.steer_mode)
    while True:
        try:
            line = input("argus> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        low = line.lower()
        try:
            if low in ("q", "quit", "exit"):
                break
            elif low == "help":
                print(__doc__.split("REPL commands:")[1])
            elif low == "stop":
                bridge.stop(); print("  -> neutral (P42 L0 R0)")
            elif low.startswith("mode "):
                m = low.split()[1]
                if m in ("bang", "pwm"):
                    bridge.steer_mode = m; bridge.stop()
                    print("  -> steer mode = %s" % m)
                else:
                    print("  modes: bang | pwm")
            elif low.startswith("t "):
                x = float(low.split()[1]); bridge.set_throttle(x)
                print("  -> %s" % throttle_to_P(x))
            elif low.startswith("p "):
                n = int(low.split()[1]); bridge.send("P%d" % n)
                print("  -> P%d" % n)
            elif low.startswith("s "):
                v = float(low.split()[1]); bridge.set_steer(v)
                print("  -> steer %.2f (%s)" % (v, bridge.steer_mode))
            elif line.isupper():
                bridge.send(line); print("  -> %s" % line)
            else:
                print("  ? type 'help'")
        except (ValueError, IndexError):
            print("  bad args — type 'help'")
    bridge.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--mode", choices=["repl", "neutral"], default="repl")
    args = ap.parse_args()

    print("connecting to ws://%s:%d/ws ..." % (args.host, args.port))
    ws = WS(args.host, args.port)
    bridge = Bridge(ws)
    print("connected. SAFETY: wheels off the ground. Sending neutral first.")
    bridge.stop()

    def _safe_exit(*_):
        bridge.shutdown()
        os._exit(0)
    signal.signal(signal.SIGINT, _safe_exit)
    signal.signal(signal.SIGTERM, _safe_exit)
    atexit.register(lambda: bridge.shutdown())

    if args.mode == "neutral":
        print("neutral mode: listening 3s for telemetry, then exit...")
        time.sleep(3.0)
        bridge.shutdown()
        print("done.")
    else:
        repl(bridge)
        bridge.shutdown()


if __name__ == "__main__":
    main()
