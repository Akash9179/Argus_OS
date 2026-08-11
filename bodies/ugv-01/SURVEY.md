# Hardware survey brief - ugv-01

> **THIS SURVEY IS COMPLETE (2026-08-11). DO NOT RUN IT AGAIN.**
> Its results are in `FINDINGS.md` and the synthesis is in `MCU-PROTOCOL.md`.
> The firmware was later supplied by the team and is in `firmware/`.
>
> **If you are an agent starting a session on the Jetson, open `BENCH.md`.**
> That is the current brief. This file is kept as the record of how the
> survey was run.


## If you are an agent running on the Jetson, start here

You are Claude Code running on the Jetson AGX Orin inside ugv-01, the
Jeep-chassis ground vehicle. Your job in this session is the HARDWARE
SURVEY: discover everything true about this machine and write it down.
The real vehicle adapter, the perception stack, and the demo all get
built from what you record here. Nobody has done this survey; the old
integration notes in this folder describe hardware that has since been
upgraded and must not be trusted.

## Rule zero: this machine can move

- Run NOTHING that could actuate: no writes to serial ports, no motor
  test commands, no scripts named anything like drive, test_bridge, or
  remo unless the human confirms the drive wheels are off the ground
  and says go.
- Reading files, listing devices, and querying versions is always safe.
  Opening a serial port even read-only can reset some microcontrollers:
  read source code and configs FIRST, touch live ports LAST, and only
  after telling the human what you are about to open.
- If any step is ambiguous about whether it could actuate, stop and ask.

## What to produce

**Write everything into `bodies/ugv-01/FINDINGS.md`**, which already exists in
this folder as a skeleton with one section per survey step. Fill each section
in place: raw command output first inside a fenced block, then one short
plain-language paragraph saying what it means. Do not edit this brief. Then
tick the checklist in `README.md` in this folder.

An unanswered section is a finding too. Write "NOT FOUND on this machine" or
"could not determine, because ..." rather than leaving a heading empty or
filling it from the old notes. Honesty law: never claim more certainty than
you hold.

### Handing it back

```bash
git checkout -b survey/ugv-01
git add bodies/ugv-01/FINDINGS.md bodies/ugv-01/README.md
git commit -m "Hardware survey of ugv-01"
git push -u origin survey/ugv-01
```

Set an identity first if git complains: `git config user.name` and
`git config user.email`. The repo is private, so the push needs credentials
(`gh auth login` device flow is easiest). If this machine is offline or the
push is refused, commit locally anyway and tell the human the branch name and
that it needs carrying back by hand. A survey that exists only in a chat
transcript is a survey that gets lost.

## The survey, in order

### 1. System identity
```bash
cat /etc/nv_tegra_release          # L4T version -> JetPack version
cat /etc/os-release
uname -a
nvpmodel -q 2>/dev/null            # power model
free -h && df -h /
```

### 2. Buses and devices (all read-only)
```bash
lsusb
lspci
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/ttyTHS* 2>/dev/null   # serial: the MCU lives here
ls /dev/video* 2>/dev/null && v4l2-ctl --list-devices 2>/dev/null
ls /dev/i2c-* 2>/dev/null
ip a                                # interfaces; note anything cellular or radio
```

### 3. Software already on the machine
```bash
dpkg -l | grep -iE 'zed|cuda|tensorrt|ros|opencv' | head -40
ls /usr/local/zed 2>/dev/null       # ZED SDK, if installed
ls /opt 2>/dev/null
systemctl list-units --type=service --state=running | head -30
docker ps -a 2>/dev/null
ss -tlnp 2>/dev/null | head -20     # what is listening; Remo used :8080
```

### 4. The drive controller (the important one)
The old notes describe a Go program ("Remo") bridging WebSocket to a
microcontroller over USB serial, with bang-bang steering. The MCU and
firmware have been UPGRADED since. Find the truth:
```bash
find / -maxdepth 4 -iname '*remo*' -not -path '*/proc/*' 2>/dev/null
find /home -iname '*.ino' -o -iname 'firmware*' -o -iname '*sketch*' 2>/dev/null | head
```
- Read every firmware source file you find, fully. Record: the exact
  serial command set (steering, throttle, brake, gear, ignition, lights),
  whether steering is now proportional, every telemetry message the MCU
  sends up (battery, pedal positions, gear state), baud rate and port,
  and what the firmware does on serial silence (failsafe or hold).
- If the firmware source is not on this machine, say so loudly in the
  findings; the human then gets it from wherever it lives. Do not guess
  the protocol from the old notes.

### 5. Sensors
```bash
ls /usr/local/zed/tools 2>/dev/null          # ZED tools; -l lists cameras, safe
find / -maxdepth 3 -iname '*gnss*' -o -iname '*gps*' -o -iname '*imu*' 2>/dev/null | head
dmesg | grep -iE 'camera|imu|gps|gnss|tty' | tail -30
```
Record every sensor physically present: model, interface, and whether a
driver or SDK for it is already installed.

**The ZED X is NOT connected right now** (founder, 2026-08-11). Do not hunt
for it and do not treat its absence as a fault. What matters instead: whether
the ZED SDK is installed on this machine anyway, and what cameras ARE present
today (a USB webcam is enough for the cockpit video pane). Record both.

### 6. Network reality
Record how this Jetson reaches the world today: wifi, ethernet, tailscale
(`tailscale status`), cellular. The teleop and LINK designs depend on it.

### 7. Optional, only with the human present: the mock bridge

This is safe. The bridge has exactly one vehicle adapter, `mock`, which is
software with toy physics: it opens no serial port and cannot reach the MCU.
Running it proves the network path and the cockpit link with the vehicle
untouched.

```bash
ARGUS_PASSWORD='Argus@2026' python3 -m drive.bridge     # listens 0.0.0.0:8090
```

Pure stdlib, no venv needed. Do not pass `--report` here; it needs paho-mqtt
and a broker on the laptop. Record in FINDINGS.md whether it started, whether
the laptop cockpit reached it at `ws://<jetson-ip>:8090`, and the Jetson's IP
and any firewall rule you had to notice. Then stop it with Ctrl-C.

## After the survey

Do not build anything in this session. The findings feed three decisions
made with the human afterward: the real VehicleAdapter for drive/bridge,
whether point-A-to-B autonomy makes the demo, and the ZED integration
path. Survey first, honestly and completely.

---

## Findings

(appended by the survey agent, dated)
