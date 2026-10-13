"""Wire encoding for ugv-01's two boards. Pure functions, no I/O.

Source of truth: ARGUS DRIVE Serial Command Interface Specification,
firmware v4.1.3, doc rev 1.0 (bodies/ugv-01/FINDINGS-2026-10-13.md
transcribes it), corrected by what the vehicle accepted on 4 Oct 2026:
the spec says "binary/hex", the board answers raw bytes with
`0x00;ERR;BAD_FORMAT` and accepts the hex written as ASCII text,
arguments after a space, LF terminated: `0x05 01\n`. Replies are text:
`0x<cmd>;<OK|ERR>;<data>`.

The accelerator board (firmware AC 1.2) is ARGUS-shaped but its argument
follows a semicolon: `0x02;32\n` for 50 percent duty. It answers every
frame; silence is a dead link, not a quiet one.

Deliberately absent: 0x0C RESET, 0x0D/0x0E Wi-Fi, 0x11 limit enable,
0x12/0x13 admin actuators, and the write forms of 0x0F/0x10. The
vehicle is not reconfigured and not driven past its limits from above
the HAL. Adding one of those is an ADR, not a commit.
"""
from __future__ import annotations

from dataclasses import dataclass

TERMINATOR = b"\n"

# Drive board command bytes (spec section 2).
INFO = 0x01
READ_BRAKE = 0x03
READ_STEER = 0x04
STR_SW = 0x05
BRK_SW = 0x06
SPEED = 0x07
GEAR = 0x08
LIGHT = 0x09
IND = 0x0A
HORN = 0x0B
BRK_LIM = 0x0F
STR_LIM = 0x10
STR_CTR = 0x14
STATUS = 0x16

ALL_COMMANDS = frozenset({
    INFO, READ_BRAKE, READ_STEER, STR_SW, BRK_SW, SPEED, GEAR, LIGHT, IND,
    HORN, BRK_LIM, STR_LIM, STR_CTR, STATUS,
})

_STEER = {"stop": 0x00, "left": 0x01, "right": 0x02}
_BRAKE = {"stop": 0x00, "apply": 0x01, "release": 0x02}
_GEAR = {"D": 0x01, "N": 0x02, "R": 0x03}
_LIGHT = {"off": 0x00, "ring": 0x01, "high": 0x02, "low": 0x03}
_IND = {"off": 0x00, "left": 0x01, "right": 0x02, "park": 0x03}


def _frame(cmd: int, *args: int) -> bytes:
    text = "0x%02X" % cmd + "".join(" %02X" % a for a in args)
    return text.encode("ascii") + TERMINATOR


def _pick(table: dict[str, int], value: str, what: str) -> int:
    try:
        return table[value]
    except KeyError:
        raise ValueError("%s must be one of %s, got %r" % (what, sorted(table), value)) from None


# ---------------------------------------------------------------- queries

def info() -> bytes:
    return _frame(INFO)


def status() -> bytes:
    return _frame(STATUS)


def read_steer() -> bytes:
    return _frame(READ_STEER)


def read_brake() -> bytes:
    return _frame(READ_BRAKE)


def read_steer_limits() -> bytes:
    """0x10 with no arguments reads; with arguments it would write. Only
    the read form exists here."""
    return _frame(STR_LIM)


def read_brake_limits() -> bytes:
    return _frame(BRK_LIM)


# --------------------------------------------------------------- actuators

def steer(direction: str) -> bytes:
    """Steering actuator: 'left', 'right' or 'stop'. The firmware enforces
    its angle limits and stall protection on this command."""
    return _frame(STR_SW, _pick(_STEER, direction, "steer"))


def brake(action: str) -> bytes:
    """Brake actuator: 'apply' (forward), 'release' (reverse) or 'stop'.
    Applying sets the drive board's own accel to zero and locks it."""
    return _frame(BRK_SW, _pick(_BRAKE, action, "brake"))


def centre_steer() -> bytes:
    """Asynchronous; the completion reply arrives later."""
    return _frame(STR_CTR)


# ------------------------------------------------------- vehicle controls

def gear(g: str) -> bytes:
    """'D', 'N' or 'R'. The cockpit's 'F' is translated by the adapter."""
    return _frame(GEAR, _pick(_GEAR, g, "gear"))


def speed_mode(mode: int) -> bytes:
    if mode not in (1, 2, 3):
        raise ValueError("speed mode must be 1, 2 or 3, got %r" % (mode,))
    return _frame(SPEED, mode)


def light(which: str) -> bytes:
    """One light channel: 'off', 'ring', 'high' or 'low'."""
    return _frame(LIGHT, _pick(_LIGHT, which, "light"))


def indicator(which: str) -> bytes:
    """One indicator channel: 'off', 'left', 'right' or 'park'."""
    return _frame(IND, _pick(_IND, which, "indicator"))


def horn() -> bytes:
    """0.5 s pulse. The longer pulses (02, 03) are locked in firmware."""
    return _frame(HORN, 0x01)


# ------------------------------------------------------- accelerator board

ACCEL_INFO_CMD = 0x01
ACCEL_DUTY_CMD = 0x02


def accel_info() -> bytes:
    return _frame(ACCEL_INFO_CMD)


def accel_duty(pct: int) -> bytes:
    """Throttle duty 0 to 100 percent as a hex byte after a semicolon."""
    pct = int(pct)
    if not 0 <= pct <= 100:
        raise ValueError("duty must be 0 to 100, got %d" % pct)
    return ("0x%02X;%02X" % (ACCEL_DUTY_CMD, pct)).encode("ascii") + TERMINATOR


ACCEL_ZERO = accel_duty(0)


# ----------------------------------------------------------------- replies

@dataclass(frozen=True)
class Reply:
    cmd: int | None     # None when the board answered without a command byte
    ok: bool
    data: str


def decode_line(raw: bytes) -> str:
    """One line from a board, as text when printable, else as hex."""
    body = raw.rstrip(b"\r\n")
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError:
        text = None
    if text is not None and text.isprintable():
        return text.strip()
    return "hex: " + body.hex(" ")


def parse_reply(line: str) -> Reply | None:
    """'0x01;OK;040103' -> Reply(1, True, '040103'); None if not a reply."""
    parts = line.strip().split(";", 2)
    if len(parts) < 2:
        return None
    head = parts[0]
    if head.upper() in ("OK", "ERR"):
        # 'ERR;UNKNOWN_COMMAND': the accelerator board's shape with no cmd
        return Reply(cmd=None, ok=head.upper() == "OK", data=";".join(parts[1:]))
    verdict = parts[1].upper()
    data = parts[2] if len(parts) > 2 else ""
    if verdict not in ("OK", "ERR"):
        return None
    if not head.lower().startswith("0x"):
        return None
    try:
        cmd = int(head[2:], 16)
    except ValueError:
        return None
    return Reply(cmd=cmd, ok=verdict == "OK", data=data)


def firmware_version(data: str) -> str | None:
    """Drive board INFO data '040103' -> '4.1.3'."""
    if len(data) != 6 or not data.isdigit():
        return None
    return ".".join(str(int(data[i:i + 2])) for i in (0, 2, 4))


def accel_version(data: str) -> str | None:
    """Accelerator INFO data 'AC0102' -> '1.2'."""
    if len(data) != 6 or data[:2].upper() != "AC" or not data[2:].isdigit():
        return None
    return "%d.%d" % (int(data[2:4]), int(data[4:6]))


def _hex_word(text: str) -> int | None:
    if len(text) != 4:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def angle_deg(data: str) -> float | None:
    """READ_STEER and READ_BRAKE data: one hex word in 0.1 degree units."""
    raw = _hex_word(data)
    return None if raw is None else raw / 10.0


def limits_deg(data: str) -> tuple[float, float] | None:
    """STR_LIM and BRK_LIM read data: min then max, 0.1 degree units."""
    if len(data) != 8:
        return None
    lo, hi = _hex_word(data[:4]), _hex_word(data[4:])
    if lo is None or hi is None or lo >= hi:
        return None
    return lo / 10.0, hi / 10.0
