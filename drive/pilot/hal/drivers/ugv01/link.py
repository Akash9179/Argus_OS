"""One serial port, as these boards need it.

The controls layer talks to a `Port`: open, close, write, readline,
is_open. `PySerialPort` is the real one. Tests hand in a fake. Nothing
imports pyserial until a real port is built, so a laptop checkout never
touches a serial device by accident.

Opening a port on either ugv-01 board may reset it (the accelerator
board's own host code says it does: Arduino auto-reset on DTR). Closing
may do the same. The controls layer treats every open as a reset and
never assumes a close left the board in a known state.
"""
from __future__ import annotations

from typing import Protocol


class Port(Protocol):
    is_open: bool

    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> None: ...
    def readline(self) -> bytes: ...


class PySerialPort:
    """pyserial behind the Port protocol. 115200 8N1, exclusive, short
    read timeout so the reader thread can notice a stop request."""

    def __init__(self, device: str, baud: int = 115200, read_timeout_s: float = 0.2,
                 write_timeout_s: float = 0.5) -> None:
        self.device = device
        self.baud = baud
        self._read_timeout = read_timeout_s
        self._write_timeout = write_timeout_s
        self._ser = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        import serial  # pyserial, only here
        self._ser = serial.Serial(
            self.device, self.baud, timeout=self._read_timeout,
            write_timeout=self._write_timeout, exclusive=True,
        )

    def close(self) -> None:
        ser, self._ser = self._ser, None
        if ser is not None:
            ser.close()

    def write(self, data: bytes) -> None:
        ser = self._ser
        if ser is None:
            raise OSError("port closed")
        ser.write(data)

    def readline(self) -> bytes:
        ser = self._ser
        if ser is None:
            return b""
        return ser.readline()
