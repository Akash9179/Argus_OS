"""Minimal server-side WebSocket (RFC 6455), stdlib only.

Just enough for the bridge: text frames, ping/pong, close. One reader per
connection. No extensions, no fragmentation support beyond coalescing
continuation frames.
"""
from __future__ import annotations

import base64
import hashlib
import socket
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WsError(Exception):
    pass


def server_handshake(conn: socket.socket) -> bool:
    """Perform the HTTP upgrade. Returns False on a malformed request."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk
        if len(data) > 65536:
            return False
    key = None
    for line in data.split(b"\r\n"):
        if line.lower().startswith(b"sec-websocket-key:"):
            key = line.split(b":", 1)[1].strip()
    if not key:
        return False
    accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()).decode()
    conn.sendall(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        ).encode()
    )
    return True


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise WsError("socket closed")
        buf += chunk
    return buf


def read_text(conn: socket.socket) -> str | None:
    """Read the next text message. Returns None on a clean close.
    Transparently answers pings and skips pongs and binary frames."""
    message = b""
    while True:
        head = _recv_exact(conn, 2)
        fin = head[0] & 0x80
        opcode = head[0] & 0x0F
        masked = head[1] & 0x80
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", _recv_exact(conn, 2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _recv_exact(conn, 8))[0]
        if length > 1 << 20:
            raise WsError("frame too large")
        mask = _recv_exact(conn, 4) if masked else b""
        payload = _recv_exact(conn, length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

        if opcode == 0x8:  # close
            try:
                conn.sendall(_frame(0x8, b""))
            except OSError:
                pass
            return None
        if opcode == 0x9:  # ping
            conn.sendall(_frame(0xA, payload))
            continue
        if opcode in (0xA, 0x2):  # pong / binary: ignore
            continue
        if opcode in (0x1, 0x0):  # text / continuation
            message += payload
            if fin:
                return message.decode("utf-8", errors="replace")
            continue
        raise WsError(f"unsupported opcode {opcode}")


def _frame(opcode: int, payload: bytes) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 1 << 16:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def send_text(conn: socket.socket, text: str) -> None:
    conn.sendall(_frame(0x1, text.encode()))
