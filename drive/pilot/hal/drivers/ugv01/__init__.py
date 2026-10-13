"""ugv-01: the first steel, as of 13 Oct 2026.

Two boards on two USB serial adapters (bodies/ugv-01/FINDINGS-2026-10-13.md):
the ARGUS DRIVE module (steering, brake, gear, speed mode, lights,
indicators, horn; firmware v4.1.3) on a CH340, and an accelerator board
(throttle duty; firmware AC 1.2) on an FTDI FT232R.

`protocol` is pure encoding and decoding. `link` is one serial port with
the reset-on-open behaviour of these boards made explicit. `controls` is
the single owner of both ports and the only place the safety invariants
live. The teleop bridge's adapter (drive/bridge/ugv01.py) is a shim over
`controls`, per ADR-0009: the hardware is driven from exactly one place.

Nothing in this package is imported by the simulated drivers, so a laptop
checkout never touches a serial port by accident.
"""
