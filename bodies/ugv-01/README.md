# Body: ugv-01 — Jeep-chassis ground vehicle

The first steel. Jetson AGX Orin 64GB onboard; ZED X planned as primary
sensor. This folder holds everything body-specific: hardware notes, the MCU
serial protocol, wiring, and (eventually) the capability manifest this body
ships with.

Bodies differ only through HAL drivers and a capability manifest. If anything
in this folder forces a change above `drive/pilot/hal/`, that is an
architecture bug (HAL law).

## Status: hardware survey pending

`ARGUS_INTEGRATION_NOTES.md` in this folder documents the ORIGINAL Remo
controller (bang-bang steering, throttle levels, no watchdog). **It is
outdated:** the vehicle's MCU side and sensors have been upgraded since it was
written (founder, 2026-08-06). Treat it as historical reference only.

Next connection to the vehicle, capture into this folder:

- [ ] Current MCU firmware version and full serial/command protocol
      (ignition, gear F/N/R, lights, steering, throttle, brake)
- [ ] Whether steering is now proportional
- [ ] Telemetry available (battery, accelerator, brake positions, gear state)
- [ ] Watchdog/failsafe behavior on link loss, if any
- [ ] Sensor inventory as installed (cameras, GNSS/IMU, anything added)
- [ ] Jetson JetPack/L4T version currently flashed

The point-A-to-B autonomy decision for the demo is made from this survey,
not from the old notes.
