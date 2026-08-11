# Body: ugv-01 - Jeep-chassis ground vehicle

The first steel. Jetson AGX Orin 64GB onboard; ZED X planned as primary
sensor. This folder holds everything body-specific: hardware notes, the MCU
serial protocol, wiring, and (eventually) the capability manifest this body
ships with.

Bodies differ only through HAL drivers and a capability manifest. If anything
in this folder forces a change above `drive/pilot/hal/`, that is an
architecture bug (HAL law).

## Status: hardware survey done 2026-08-11 - see `FINDINGS.md`

The survey has been run on the Jetson and the results are in `FINDINGS.md`.
**The headline: the MCU firmware source is NOT on the Jetson**, so the serial
command set is known only in syntax (`R<n><0|1>` relays 1-14, `P<42..214>` PWM,
115200 8N1 on `/dev/ttyUSB0`, newline-framed) and not in meaning - nothing maps
a relay to ignition, gear, brake or lights. Second headline: **no sensors are
attached at all** - no camera, no GNSS, no IMU - so autonomy is off the table
for the demo and manual teleop is the honest one.

> ### Before anyone drives this vehicle again
>
> The steering feedback sensor is **disconnected**, and that sensor is what
> stops the steering actuator over-travelling. R13/R14 are two **polarity legs
> of one actuator**, not independent relays. So on the console that exists
> today, **every press-and-hold of a steering button runs the actuator into its
> mechanical stop with nothing telling it to stop.** Reconnecting that sensor is
> the highest-value hardware fix on the vehicle.
>
> Also true today, and none of it flagged in the UI: there is **no brake**
> (both brake relays disconnected), **no ignition relay**, and **no E-stop
> relay** — while the console shows a 16-level brake slider and a latching
> E-stop button that report success and do nothing. Drive is the
> **de-energized default**, so all-relays-off means in gear.
>
> These come from the team via `MCU-PROTOCOL.md` and are **UNVERIFIED against
> hardware** — no firmware has been read, no port opened. Verify the map before
> relying on it, starting with "R5 is neutral", because that is what any
> failsafe would be built on. Details: `FINDINGS.md` sections 9 and 10.

**Running Claude Code on the Jetson? Open `SURVEY.md` in this folder and
follow it.** It is the whole brief: what to record, in what order, and the
safety rules (rule zero: nothing that actuates).

`ARGUS_INTEGRATION_NOTES.md` in this folder documents the ORIGINAL Remo
controller (bang-bang steering, throttle levels, no watchdog). **It is
outdated:** the vehicle's MCU side and sensors have been upgraded since it was
written (founder, 2026-08-06). Treat it as historical reference only.

Next connection to the vehicle, capture into this folder.
Ticked = captured by the 2026-08-11 survey. Unticked = surveyed for and **not
obtainable on the Jetson**, with the reason given; these still need doing.

- [ ] Current MCU firmware version and full serial/command protocol
      (ignition, gear F/N/R, lights, steering, throttle, brake)
      - **Blocked: the firmware source is not on the Jetson.** Searched the
        whole filesystem - no `.ino`, no sketch, no platformio project. Only
        the wire *syntax* was recoverable, from the host-side bridge and the
        browser UI: `R<n><0|1>` for 14 unlabelled relays and `P<42..214>` PWM
        on D9. **No relay-to-function map exists anywhere on the machine.**
        Someone must bring the firmware from wherever it lives.
- [ ] Whether steering is now proportional
      - **Unknown.** The old bang-bang `L1/L0`/`R1/R0` commands are gone from
        the current UI and nothing named replaced them. Cannot be answered
        without the firmware or a relay map.
- [ ] Telemetry available (battery, accelerator, brake positions, gear state)
      - **Unknown, deliberately not captured.** The transport carries it (both
        bridges forward any line the MCU emits) but neither UI parses a single
        field. Reading it needs the port opened, which rule zero and the FTDI
        DTR-reset hazard put off until the wheels are off the ground.
- [ ] Watchdog/failsafe behavior on link loss, if any
      - **Unknown, and assume the worst until tested.** Confirmed: *nothing*
        host-side implements a watchdog - on disconnect the host simply stops
        sending and the MCU holds its last relay/PWM state. Any failsafe would
        have to be in the firmware, which is absent.
- [x] Sensor inventory as installed (cameras, GNSS/IMU, anything added)
      - **Done: nothing is installed.** No camera at all (`/dev/video*` does
        not exist - no ZED, no USB webcam, no CSI), no GNSS, no IMU
        (`/sys/bus/iio/devices` empty). ZED SDK 5.4.1 *is* installed anyway;
        its bundled ZED X GMSL drivers are L4T 35.x and will not load on this
        36.5 kernel. CAN (can0/can1) exists and is down.
- [x] Jetson JetPack/L4T version currently flashed
      - **Done: L4T R36.5.0 = JetPack 6.2**, Ubuntu 22.04.5, kernel
        5.15.185-tegra, AGX Orin Developer Kit, MAXN power mode, 61 GB RAM,
        839 GB free NVMe. CUDA 12.6, TensorRT 10.3, ROS 2 Humble (no Nav2).

The point-A-to-B autonomy decision for the demo is made from this survey,
not from the old notes.
