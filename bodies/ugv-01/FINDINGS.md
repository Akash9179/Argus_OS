# Hardware survey findings - ugv-01

Filled in by the agent running on the Jetson. Brief and rules:
`SURVEY.md` in this folder. Nothing here is written from the old
`ARGUS_INTEGRATION_NOTES.md`; that file is stale and describes hardware since
upgraded.

- **Surveyed on:** (date)
- **Surveyed by:** (agent + model, and the human present)
- **Anything skipped, and why:**

An unanswered section is a finding. Write "NOT FOUND on this machine" or
"could not determine, because ..." rather than leaving a heading empty.

---

## 1. System identity

```
(raw output: nv_tegra_release, os-release, uname -a, nvpmodel -q, free -h, df -h /)
```

**In plain language:** (L4T and therefore JetPack version, Ubuntu release,
power model, RAM, free disk. Say whether JetPack is new enough for the ZED SDK
version we would want.)

## 2. Buses and devices

```
(raw output: lsusb, lspci, ls -l /dev/ttyUSB* /dev/ttyACM* /dev/ttyTHS*, /dev/video*, /dev/i2c-*, ip a)
```

**In plain language:** (what is plugged in; which serial device is almost
certainly the MCU and what makes you think so; which video devices exist.)

## 3. Software already on the machine

```
(raw output: dpkg -l greps, /usr/local/zed, /opt, running services, docker ps -a, ss -tlnp)
```

**In plain language:** (CUDA / TensorRT / ROS / OpenCV / ZED SDK present or
not, with versions. What is already listening on a port, and what owns it.
Whether Docker is installed and usable.)

## 4. The drive controller (the important one)

**Firmware source found:** yes / NO (if no, say so loudly and where it might live)

```
(raw output: the finds; then the firmware source read in full)
```

Fill this table only from firmware or driver source actually read on this
machine. Leave a cell as "unknown" rather than guessing.

| Question | Answer |
|---|---|
| Serial port and baud | |
| Framing (bytes, terminator) | |
| Steering command, and is it proportional now | |
| Throttle command and its units | |
| Brake command | |
| Gear F/N/R command | |
| Ignition command | |
| Lights command | |
| Telemetry the MCU sends up (battery, pedals, gear, speed) | |
| Behaviour on serial silence: failsafe stop, or hold last command | |
| Anything that moves the vehicle at power-on | |

**In plain language:** (how a command actually gets from a socket to a wheel
today, and what the biggest risk is in writing a real adapter against it.)

## 5. Sensors

```
(raw output: zed tools listing, gnss/gps/imu finds, dmesg greps)
```

**In plain language:** (every sensor physically present: model, interface,
driver or SDK installed or not.)

- **ZED X:** not connected as of 2026-08-11. Is the SDK installed anyway?
- **Cameras actually present today:** (USB webcam is enough for the video pane)
- **GNSS / IMU:** (present or not; this decides whether dead reckoning is the
  only option for the demo)

## 6. Network reality

```
(raw output: ip a, tailscale status, nmcli or equivalent)
```

**In plain language:** (how this Jetson reaches the world: wifi, ethernet,
tailscale, cellular. Its address on the current network. Whether the operator
laptop at 192.168.1.164 is reachable from here, and whether a firewall would
block an inbound connection on 8090.)

## 7. Mock bridge bench test (optional, only if the human was present)

- **Ran it:** yes / no
- **Bridge started:** yes / no, with output
- **Cockpit on the laptop reached it:** yes / no, at which address
- **Anything in the way:** (firewall, IP, python version)

---

## What this changes

Three things get decided from the above, with the human, after this session.
Say what you believe the answer is and how confident you are.

1. **The real VehicleAdapter:** is the MCU protocol known well enough to write
   `drive/bridge/vehicle.py` against it? What is still missing?
2. **Point-A-to-B autonomy for the demo:** is there enough sensing on this
   machine (GNSS, IMU, any camera) for it, or is manual teleop the honest
   demo?
3. **The ZED integration path:** what would have to be true on this Jetson
   before a ZED X works here, given the JetPack version found above.
