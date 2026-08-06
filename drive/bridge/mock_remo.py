#!/usr/bin/env python3
"""
Mock Remo server — stands in for the real Go /ws bridge so we can verify the
ARGUS test bridge WITHOUT the Arduino connected.

Mimics RemoV1/main.go: accepts a WebSocket at /ws, prints every token it
receives (this is what would hit the serial port), and echoes a fake telemetry
line back so we can confirm the return path. Pure stdlib, no deps.

    python3 mock_remo.py            # listen on :8080
"""
import base64, hashlib, socket, struct, sys, threading, time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def handshake(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk
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

def recv_frame(conn, buf):
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

def send_text(conn, s):
    p = s.encode()
    conn.sendall(bytes([0x81, len(p)]) + p)  # server frames unmasked, <126 bytes

def handle(conn, addr):
    print("[mock] client connected: %s" % (addr,))
    if not handshake(conn):
        conn.close(); return
    buf = bytearray()
    try:
        while True:
            opcode, data = recv_frame(conn, buf)
            if opcode == 0x8:
                break
            if opcode in (0x1, 0x2):
                tok = data.decode("utf-8", "replace")
                print("[mock] SERIAL <- %r" % tok)  # this is what reaches the Arduino
                send_text(conn, "ack:%s" % tok)
    except (ConnectionError, OSError):
        pass
    finally:
        print("[mock] client disconnected: %s" % (addr,))
        conn.close()

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print("[mock] Remo stand-in listening on :%d  (/ws)" % port)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
