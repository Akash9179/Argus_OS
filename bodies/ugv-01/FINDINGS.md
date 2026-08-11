# Hardware survey findings - ugv-01

Filled in by the agent running on the Jetson. Brief and rules:
`SURVEY.md` in this folder. Nothing here is written from the old
`ARGUS_INTEGRATION_NOTES.md`; that file is stale and describes hardware since
upgraded.

- **Surveyed on:** 2026-08-11
- **Surveyed by:** Claude Code (Opus 5, 1M context), with Akash present at the
  vehicle. All commands below were run on the Jetson itself.
- **Anything skipped, and why:**
  - **No serial port was opened.** Not by me, not read-only. Rule zero plus
    the FTDI-DTR reset hazard (see section 4) means the only honest way to
    capture the MCU's telemetry is with the human present and the drive wheels
    off the ground. That leaves several cells in the section-4 table
    "unknown"; they are unknown *on purpose*, not by omission.
  - `v4l2-ctl` is not installed on this machine, so the camera listing in
    step 2 came from `/dev/video*` and `lsusb` instead.
  - `dmesg` and `iptables -S` needed a sudo password I was not given;
    `dmesg` worked unprivileged, the firewall rule dump did not (section 6).
  - Step 7 was run (mock adapter only, which cannot reach the MCU). See
    section 7 for how far it got.

An unanswered section is a finding. Write "NOT FOUND on this machine" or
"could not determine, because ..." rather than leaving a heading empty.

---

## 1. System identity

```
$ cat /etc/nv_tegra_release
# R36 (release), REVISION: 5.0, GCID: 43688277, BOARD: generic, EABI: aarch64, DATE: Fri Jan 16 03:50:45 UTC 2026
# KERNEL_VARIANT: oot
TARGET_USERSPACE_LIB_DIR=nvidia
TARGET_USERSPACE_LIB_DIR_PATH=usr/lib/aarch64-linux-gnu/nvidia

$ cat /etc/os-release
PRETTY_NAME="Ubuntu 22.04.5 LTS"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
VERSION_CODENAME=jammy

$ uname -a
Linux ubuntu 5.15.185-tegra #1 SMP PREEMPT Thu Jan 15 19:24:38 PST 2026 aarch64 aarch64 aarch64 GNU/Linux

$ cat /proc/device-tree/model
NVIDIA Jetson AGX Orin Developer Kit

$ nvpmodel -q
NV Power Mode: MAXN
0

$ free -h
               total        used        free      shared  buff/cache   available
Mem:            61Gi       4.9Gi        53Gi        29Mi       3.1Gi        55Gi
Swap:           30Gi          0B        30Gi

$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p1  915G   30G  839G   4% /
```

**In plain language:** This is a Jetson AGX Orin **Developer Kit** (not a
production module on a custom carrier), running **L4T R36.5.0**, which is
**JetPack 6.2**, on Ubuntu 22.04.5 with the 5.15.185-tegra kernel. Power model
is **MAXN** — the unrestricted mode, full clocks, maximum draw. Worth knowing
for a battery vehicle: nothing here is power-limited.

Resources are not a constraint: **61 GB RAM** with 55 GB available, 30 GB swap,
and a **915 GB NVMe** that is 4% used (839 GB free). The rootfs is on NVMe, not
SD — good for sustained logging and SVO recording.

On the ZED question: **JetPack 6.2 is new enough for the ZED SDK we want, and
in fact the SDK is already installed** (5.4.1, section 3). The caveat is not
the SDK but the ZED **X** GMSL driver — see section 5, where the bundled
drivers turn out to be for the wrong L4T generation.

## 2. Buses and devices

```
$ lsusb
Bus 002 Device 002: ID 0bda:0420 Realtek Semiconductor Corp. 4-Port USB 3.0 Hub
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 005: ID 0403:6001 Future Technology Devices International, Ltd FT232 Serial (UART) IC
Bus 001 Device 004: ID 046d:c534 Logitech, Inc. Unifying Receiver
Bus 001 Device 003: ID 0bda:5420 Realtek Semiconductor Corp. 4-Port USB 2.0 Hub
Bus 001 Device 002: ID 13d3:3549 IMC Networks Bluetooth Radio
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub

$ lspci
0001:00:00.0 PCI bridge: NVIDIA Corporation Device 229e (rev a1)
0001:01:00.0 Network controller: Realtek Semiconductor Co., Ltd. RTL8822CE 802.11ac PCIe Wireless Network Adapter
0004:00:00.0 PCI bridge: NVIDIA Corporation Device 229c (rev a1)
0004:01:00.0 Non-Volatile memory controller: Sandisk Corp Device 5017 (rev 01)

$ ls -l /dev/ttyUSB* /dev/ttyACM* /dev/ttyTHS*
ls: cannot access '/dev/ttyACM*': No such file or directory
crw-rw---- 1 root dialout 240, 1 Jun  5 21:10 /dev/ttyTHS1
crw-rw---- 1 root dialout 240, 2 Jun  5 21:10 /dev/ttyTHS2
crw-rw---- 1 root dialout 188, 0 Aug  4 18:09 /dev/ttyUSB0

$ udevadm info -q property -n /dev/ttyUSB0      # sysfs query; does NOT open the port
ID_VENDOR=FTDI
ID_MODEL=FT232R_USB_UART
ID_MODEL_ID=6001
ID_VENDOR_ID=0403
ID_SERIAL=FTDI_FT232R_USB_UART_A5069RR4
ID_SERIAL_SHORT=A5069RR4
ID_USB_DRIVER=ftdi_sio
DEVPATH=/devices/platform/bus@0/3610000.usb/usb1/1-4/1-4.4/1-4.4:1.0/ttyUSB0/tty/ttyUSB0

$ ls -l /dev/serial/by-id/
usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0 -> ../../ttyUSB0

$ ls /dev/video*
ls: cannot access '/dev/video*': No such file or directory
$ v4l2-ctl --list-devices
v4l2-ctl: command not found          # package not installed

$ ls /dev/i2c-*
/dev/i2c-0  /dev/i2c-1  /dev/i2c-2  /dev/i2c-3  /dev/i2c-4
/dev/i2c-5  /dev/i2c-6  /dev/i2c-7  /dev/i2c-8  /dev/i2c-9

$ id
uid=1000(tessy_01) gid=1000(tessy_01) groups=...,20(dialout is NOT listed),44(video),
116(i2c),994(docker),999(gpio),1001(zed)
```

(Note on that last line: the login user is in `gpio`, `i2c`, `video`, `docker`
and `zed`, but **not** in `dialout` — and `/dev/ttyUSB0` is `root:dialout 0660`.
So the current user cannot open the MCU port without sudo or a group change.
That is an accidental safety interlock, and it is worth keeping deliberately.)

```
$ ip a        # abridged; full output in section 6
2: wlP1p1s0  UP    inet 192.168.1.10/24
3: can0      DOWN  link/can
4: can1      DOWN  link/can
5: eno1      NO-CARRIER
9: tailscale0 UP   inet 100.116.120.118/32
10: docker0  DOWN  inet 172.17.0.1/16
```

**In plain language:** The only USB serial device on the machine is an **FTDI
FT232R, serial A5069RR4, at `/dev/ttyUSB0`** — and that is almost certainly the
MCU link. Three things point at it: it is the sole USB-serial adapter present;
the current host-side bridge (`bridge.py`, section 4) defaults to exactly
`/dev/ttyUSB0` at 115200; and there is no other candidate — `/dev/ttyACM*`
does not exist, and `ttyTHS1`/`ttyTHS2` are the SoC's own Tegra UARTs on the
carrier header, bound to the `serial-tegra` platform driver with nothing
identifiable attached.

**The USB-serial adapter has been swapped since the old notes.** The Remo repo
ships a udev rule and a hardcoded port path for a **CH340 (1a86:7523)**, and
that device is not on this machine — what is here is an **FTDI (0403:6001)**.
This is direct physical evidence of the MCU-side upgrade the README warns
about, and it means the old Go binary cannot even open the port any more
(section 4).

**No camera of any kind is attached right now** — `/dev/video*` does not exist
at all, so there is no USB webcam and no CSI camera, not just no ZED. Ten I2C
buses are exposed. Two **CAN interfaces (can0, can1) exist and are DOWN** —
these are the Orin's built-in `mttcan` controllers, so CAN is available at the
SoC if the vehicle ever needs it, but nothing is currently configured on it.
Also plugged in: a Logitech Unifying receiver (keyboard/mouse) and a Bluetooth
radio. Networking is a Realtek RTL8822CE wifi card; storage is a SanDisk NVMe.

## 3. Software already on the machine

```
$ dpkg -l | grep -iE 'cuda|tensorrt|libnvinfer|opencv|zed'   # abridged
ii  cuda-toolkit-12-6            12.6.11-1     CUDA Toolkit 12.6 meta-package
ii  cuda-nvcc-12-6               12.6.68-1     CUDA nvcc
ii  cuda-runtime-12-6            12.6.11-1     CUDA Runtime 12.6 meta-package
ii  libnvinfer10                 10.3.0.30-1+cuda12.5   (TensorRT)
ii  libnvinfer-dev               10.3.0.30-1+cuda12.5
ii  libnvonnxparsers10           10.3.0.30-1+cuda12.5
ii  libopencv                    4.8.0-1-g6371ee1       (NVIDIA build)
ii  libopencv-dev                4.8.0-1-g6371ee1
ii  libopencv-core4.5d:arm64     4.5.4+dfsg-9ubuntu4    (distro build, also present)

$ nvcc --version
Cuda compilation tools, release 12.6, V12.6.68

$ ls /usr/local/zed
doc  drivers  firmware  get_python_api.py  include  lib  resources  samples
settings  tools  zed-config.cmake  zed-config-version.cmake

$ grep VERSION /usr/local/zed/zed-config-version.cmake
set(PACKAGE_VERSION "5.4.1")

$ ls /opt
containerd  nvidia  ota_package  ros
$ ls /opt/ros
humble
$ ls /opt/ros/humble/share | wc -l
298
$ ls /opt/ros/humble/share | grep -iE 'nav2|slam_toolbox|zed_wrapper|robot_localization'
robot_localization
zed_description
zed_msgs
                                  # nav2, slam_toolbox, zed_wrapper: ABSENT

$ python3 --version
Python 3.10.12
$ python3 -c "import serial, websockets, pyzed.sl, numpy"     # import only, opens nothing
serial: OK 3.5
websockets: OK 12.0
pyzed.sl: OK  -> reports SDK 5.4.1
numpy: OK 2.2.6
cv2: MISSING (ImportError - NumPy 1.x/2.x ABI clash)
paho.mqtt: MISSING (ModuleNotFoundError)

$ systemctl list-units --type=service --state=running   # abridged
anydesk.service            AnyDesk
rustdesk.service           RustDesk
containerd.service         containerd container runtime
docker.service             Docker Application Container Engine
gdm.service                GNOME Display Manager
ModemManager.service       Modem Manager
nvargus-daemon.service     Argus daemon
nvfancontrol.service       nvfancontrol service
nvs-service.service        NVS-SERVICE Embedded Sensor HAL Daemon
NetworkManager.service     Network Manager

$ docker ps -a
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
                                   (no containers at all, running or stopped)

$ ss -tlnp
LISTEN  0.0.0.0:7070                       (AnyDesk/RustDesk remote desktop)
LISTEN  0.0.0.0:22                         (sshd)
LISTEN  0.0.0.0:111                        (rpcbind)
LISTEN  127.0.0.53:53                      (systemd-resolved)
LISTEN  100.116.120.118:48745              (tailscaled, on the tailnet IP)
LISTEN  127.0.0.1:39181/40379/44973/42369  users:(("code-df53daabb1"))   VS Code Remote
LISTEN  127.0.0.1:49160/61116/64532        users:(("MainThread"))
                                   # nothing on :8080 and nothing on :8090
```

**In plain language:** This machine is already well provisioned for perception
work. **CUDA 12.6**, **TensorRT 10.3**, and NVIDIA's **OpenCV 4.8** are all
installed, alongside **ROS 2 Humble** (298 packages) at `/opt/ros/humble`.
**Docker is installed and running** with the containerd backend, and has never
run a container here — so `drive/pilot`'s compose setup would be starting from
a clean slate and would need to pull its base image.

Two gaps matter for later. ROS Humble is present but **Nav2 is not installed**,
nor is `slam_toolbox`, nor the ZED ROS wrapper — only `robot_localization`,
`zed_msgs` and `zed_description` are there. So `drive/pilot`'s Nav2 path is not
runnable natively today; it would come from the container. And **Python `cv2`
is broken** for the system Python 3.10: the installed cv2 was built against
NumPy 1.x while NumPy 2.2.6 is installed, so `import cv2` raises. Anything doing
Python-side image work needs a venv with pinned NumPy. `paho-mqtt` is also
absent, which matches the brief's warning not to pass `--report` to the bridge.

**The ZED SDK is installed: version 5.4.1**, with a working Python API
(`pyzed.sl` imports and reports 5.4.1) — even though no camera is attached.

Nothing is listening on **:8080** (the port the old Remo used) or **:8090** (the
bridge), so neither was running when I surveyed. What *is* exposed to the
network is worth flagging on a vehicle: **SSH on 22, rpcbind on 111, and a
remote-desktop stack (AnyDesk + RustDesk) on 7070**, all bound to `0.0.0.0`.

## 4. The drive controller (the important one)

**Firmware source found:** **NO.**

> ### The MCU firmware source is NOT on this machine.
>
> I searched the whole filesystem. There is no `.ino`, no `firmware*`, no
> `*sketch*`, no `platformio.ini`, no Arduino/ESP project of any kind anywhere
> under `/`, `/home`, `/all-folders` or `/opt`. **Everything about the MCU's
> actual behaviour below is inferred from the host-side software that talks to
> it, which is a strictly weaker source.** Someone must fetch the firmware from
> wherever it lives — the laptop, the Arduino IDE machine, a phone, or a repo
> nobody has cloned here — before a real `VehicleAdapter` is written.

```
$ find / -maxdepth 4 -iname '*remo*' -not -path '*/proc/*'    # real hits only
/all-folders/Remo-20260731T115814Z-1-001/Remo
/all-folders/RemoV1-20260731T115741Z-1-001/RemoV1
/all-folders/Remo-20260731T115814Z-1-001/Remo/mock_remo.py
/all-folders/Remo-20260731T115814Z-1-001/Remo/RemoV1
/home/tessy_01/Desktop/Remote
/home/tessy_01/Downloads/RemoV1-20260731T115741Z-1-001.zip
/home/tessy_01/Downloads/RemoV1-20260731T115649Z-1-001.zip
/home/tessy_01/Downloads/Remo-20260731T115814Z-1-001.zip
(rest of the hits were /usr/sbin/lvremove, git-remote, vtk headers, etc.)

$ find /home -iname '*.ino' -o -iname 'firmware*' -o -iname '*sketch*'
(no output)

$ find /all-folders /home/tessy_01 /opt -maxdepth 6 \
    \( -iname '*.ino' -o -iname '*firmware*' -o -iname '*sketch*' \
       -o -iname '*arduino*' -o -iname '*esp32*' -o -iname '*platformio*' \)
(no output)                          <-- NO FIRMWARE SOURCE ANYWHERE
```

### What IS on the machine

Three host-side programs, all of which I read in full:

| File | Date | What it is |
|---|---|---|
| `/all-folders/RemoV1-.../RemoV1/main.go` | 2026-07-31 | Go WS↔serial bridge, 100 lines |
| `/all-folders/Remo-.../Remo/RemoV1/main.go` | 2026-07-31 | **byte-identical** to the above (`diff` clean) |
| `/home/tessy_01/Desktop/Remote/bridge.py` | **2026-08-11 13:11** | Python port of the same bridge — **modified today** |

```
$ diff .../RemoV1/main.go .../Remo/RemoV1/main.go   ->   IDENTICAL

# main.go, the operative lines:
serialConfig := &serial.Config{
    Name: "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",     # CH340 - DOES NOT EXIST NOW
    Baud: 115200,
}
...
msg, err := reader.ReadString('\n')          # serial -> every websocket client, verbatim
...
_, err = port.Write(append(msg, '\n'))       # websocket -> serial, verbatim + '\n'
http.Handle("/", http.FileServer(http.Dir("./public")))
log.Fatal(http.ListenAndServe(":8080", nil))

# 99-ch340-serial.rules, shipped alongside it:
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", GROUP="gpio", MODE="0660"

# bridge.py, today's version - same design, different defaults:
parser.add_argument("--serial", default="/dev/ttyUSB0", help="serial device")   # FTDI - MATCHES
parser.add_argument("--baud", type=int, default=115200)
parser.add_argument("--http", type=int, default=8080)
port = serial.Serial(args.serial, args.baud, timeout=0.1)
...
line, _, rest = buf.partition(b"\n")         # newline-framed
msg = line.decode("utf-8", "replace").rstrip("\r")
loop.call_soon_threadsafe(asyncio.create_task, broadcast(msg + "\n"))
...
await asyncio.to_thread(serial_write, msg.encode() + b"\n")
```

**All three are dumb byte pipes.** They parse nothing, validate nothing,
rate-limit nothing, and implement no watchdog, no timeout and no failsafe. The
protocol lives entirely in (a) the browser UI that generates the strings and
(b) the firmware that interprets them. Only (a) is on this machine.

### The command vocabulary, from the current UI

`/home/tessy_01/Desktop/Remote/public/index.html`, modified today, titled
**"Arduino Relay Controller"**:

```html
<title>Arduino Relay Controller</title>

function send(cmd){ if(socket && socket.readyState===1){ socket.send(cmd+"\n"); } }

for(let i=1;i<=14;i++){                          // 14 relay cards
  <button class="on"  onclick="send('R${i}1')">ON</button>
  <button class="off" onclick="send('R${i}0')">OFF</button>
}

<h2>PWM Control (D9)</h2>
<input type="range" id="pwm" min="42" max="214" value="42">
pwm.oninput=function(){ pwmValue.innerHTML=this.value; send("P"+this.value); };
```

For contrast, the **old** UI (`RemoV1/public/index.html`, 2026-07-31) — this is
the bang-bang design the stale notes describe:

```js
leftBtn  -> send("L1") on press, send("L0") on release
rightBtn -> send("R1") on press, send("R0") on release
slider   -> send("P"+slider.value)
socket.onmessage=(e)=>{ console.log("Arduino:", e.data); }   // telemetry logged, never parsed
```

### The table

Filled only from source actually read on this machine. "unknown" means unknown.

| Question | Answer |
|---|---|
| Serial port and baud | **`/dev/ttyUSB0` (FTDI FT232R, S/N A5069RR4) at 115200**, from `bridge.py` defaults + the fact that it is the only USB serial device present. The Go program's hardcoded CH340 path `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0` **no longer exists** — that binary would `log.Fatal` on startup today. Data bits/parity/stop: unknown (pyserial default 8N1 is what `bridge.py` gets, but the firmware side is unverified) |
| Framing (bytes, terminator) | **ASCII, newline-terminated (`\n`)**, `\r` tolerated and stripped on the way up. No checksum, no length prefix, no sequence number, no ACK. Confirmed on the host side in all three programs |
| Steering command, and is it proportional now | **UNKNOWN — and this is the single biggest gap.** The current UI has *no* named steering control at all: it exposes 14 generic relays and one PWM channel, with no labels tying any of them to a vehicle function. The old UI's bang-bang `L1/L0/R1/R0` commands **are gone from the current UI**, which is consistent with the "upgraded" story but does **not** tell us what replaced them. Whether steering is now a relay pair, or the `P` PWM channel, or something the UI does not expose, cannot be determined without the firmware or a relay map |
| Throttle command and its units | **UNKNOWN.** The plausible candidate is `P<value>` (PWM on pin D9), but this is inference, not evidence. Units would be **raw 8-bit PWM counts, not a physical unit**, and the slider is clamped to **42–214, not 0–255** (see the risk note below) |
| Brake command | **UNKNOWN** — presumably one of `R1..R14`, unmapped |
| Gear F/N/R command | **UNKNOWN** — presumably relays, unmapped |
| Ignition command | **UNKNOWN** — presumably a relay, unmapped |
| Lights command | **UNKNOWN** — presumably a relay, unmapped |
| Telemetry the MCU sends up (battery, pedals, gear, speed) | **UNKNOWN, and not captured.** Structurally: both bridges forward *any* newline-terminated line the MCU emits to every connected client (`bridge.py` also prints it as `System: <line>`), so the MCU *can* talk upward and the transport supports it. But **neither UI parses a single field** — the old one `console.log`s it, the new one has no `onmessage` handler at all and discards it. Reading the actual lines requires opening the port, which I deliberately did not do |
| Behaviour on serial silence: failsafe stop, or hold last command | **UNKNOWN, and must be assumed to be HOLD (no failsafe) until proven otherwise.** What I can state with certainty: **nothing on the host side implements a watchdog.** No timeout, no keepalive, no safe-stop on disconnect exists in `main.go`, `bridge.py`, or either UI. If the browser closes, the wifi drops, or the bridge is killed, the host simply stops sending — the last commanded relay and PWM state is whatever the MCU is still holding. Any failsafe would have to live in the firmware, and the firmware is absent |
| Anything that moves the vehicle at power-on | **UNKNOWN — and there is a specific hazard here.** Cannot be answered without the firmware. Additionally: the FTDI adapter asserts DTR when the port is opened, which **resets many Arduino-class boards**. So merely opening `/dev/ttyUSB0` — even read-only, even just to sniff telemetry — may reboot the MCU into whatever its power-on state is. This is exactly why I opened nothing |

**In plain language:** Today, a command gets from a socket to a wheel like
this — a browser sends an ASCII string like `R31` or `P120` over a WebSocket;
a ~100-line bridge with no knowledge of what those mean appends a newline and
writes the bytes straight to `/dev/ttyUSB0` at 115200; an Arduino-class MCU
whose source code nobody here has parses them and closes relays or sets a PWM
duty cycle. There is no arbitration, no authentication, no rate limit, no
watchdog, and no state validation anywhere in that chain.

**The biggest risk in writing a real adapter against this is that the semantic
layer does not exist yet — not in code, and not written down.** We know the
*syntax* (`R<n><0|1>`, `P<value>`, newline-framed, 115200) with reasonable
confidence. We do not know the *mapping*, and the mapping is the part that
moves a two-tonne vehicle. Writing `vehicle.py` now would mean guessing which
of 14 relays is ignition and which is gear-reverse, and a wrong guess is not a
failed unit test.

Three specific hazards for whoever writes it:

1. **The PWM band is 42–214, not 0–255, and rests at 42.** That is a
   deliberately clamped window with a non-zero floor — the signature of a
   calibrated analogue pedal emulation (an idle voltage that must never go to
   zero) rather than a raw duty cycle. Sending `P0` may not mean "no throttle";
   it may mean out-of-range, or worse, a valid-but-unintended value. **Do not
   assume 0 is safe.** The resting value observed in the UI is **42**.
2. **The `R<n><state>` grammar is ambiguous on its face.** `R10` could be
   "relay 1 off" or a truncated "relay 10". `R101` could be "relay 10 on" or
   "relay 1 off, stray 1". Only the firmware's parser resolves this, and we do
   not have it. An adapter that formats commands slightly differently from the
   UI could actuate a different relay than intended.
3. **Opening the port may reset the MCU** (FTDI DTR, above). The first person
   to sniff telemetry should do it with the wheels off the ground.

## 5. Sensors

```
$ ls /dev/video*
ls: cannot access '/dev/video*': No such file or directory      # NO cameras at all

$ ls /sys/bus/iio/devices/
(empty)                                                          # NO IMU exposed to Linux

$ find / -maxdepth 3 \( -iname '*gnss*' -o -iname '*gps*' -o -iname '*imu*' \)
/usr/games/gamemode-simulate-game        # false positive, nothing else

$ dmesg | grep -iE 'camera|imu|gps|gnss|tty' | tail
[    2.395997] gpio-394 (camera-control-output-low): hogged as output/low
[    2.396025] gpio-397 (camera-control-output-low): hogged as output/low
[    2.396051] gpio-487 (camera-control-output-low): hogged as output/low
[    2.403965] 3100000.serial: ttyTHS1 at MMIO 0x3100000 is a TEGRA_UART
[    2.405065] 3110000.serial: ttyTHS2 at MMIO 0x3110000 is a TEGRA_UART
[   10.533134] ftdi_sio ttyUSB0: Unable to read latency timer: -32
[   10.535612] usb 1-4.4: FTDI USB Serial Device converter now attached to ttyUSB0
                          # no camera, no IMU, no GNSS probe anywhere in the log

$ ls /usr/local/zed/tools
ZED360  ZED_Calibration  ZED_Depth_Viewer  ZED_Diagnostic  ZED_Explorer
ZEDfu   ZED_Media_Server ZED_Sensor_Placer ZED_Sensor_Viewer ZED_Studio ZED_SVO_Editor

$ ls /usr/local/zed/firmware
ZED  ZED2  ZED2i  ZED-M  ZEDX

$ ls -l /usr/local/zed/settings          # calibration files left behind by past cameras
-rw-rw-r-- 1 tessy_01 tessy_01 1080 2026-08-01 19:48 SN11316.conf
-rw-rw-r-- 1 tessy_01 tessy_01 1341 2026-08-01 19:53 SN24605000.conf
-rw-rw-r-- 1 tessy_01 tessy_01 1082 2026-08-01 19:43 SN3206.conf

$ ls /usr/local/zed/drivers               # the ZED X GMSL drivers bundled with the SDK
L4T_35.1/  L4T_35.2/  L4T_35.3/  README.md
  stereolabs-zedx_0.5.1-MAX9296-L4T35.x_arm64.deb
  stereolabs-zedx_0.5.1-MAX96712-L4T35.x_arm64.deb
                          # note: L4T 35.x only. This machine is L4T 36.5.
```

**In plain language:** **No sensor of any kind is currently attached to this
Jetson.** Not a camera, not an IMU, not a GNSS receiver. That is a stronger
statement than "the ZED is unplugged", and it is the central fact of this
section. The only USB peripherals are two hubs, the FTDI MCU link, a Logitech
keyboard/mouse receiver, and a Bluetooth radio.

- **ZED X:** not connected, as expected (founder, 2026-08-11). **But the ZED
  SDK IS installed anyway: version 5.4.1**, complete with all the tools
  (`ZED_Explorer`, `ZED_Depth_Viewer`, `ZED_Diagnostic`, …), firmware bundles
  including a `ZEDX` directory, and a **working Python API** — `import pyzed.sl`
  succeeds and reports SDK 5.4.1. So the software side of the ZED path is
  already in place and does not need installing.

  One catch found while checking: the **ZED X GMSL driver** `.deb`s bundled
  with the SDK are built for **L4T 35.1/35.2/35.3 only**, and this machine runs
  **L4T 36.5**. A ZED X is not a USB camera — it needs that kernel-side GMSL
  capture driver for the MAX9296/MAX96712 deserialiser plus the ZED X Daemon.
  Neither is installed here (`zed_x_daemon` not on PATH; the only ZED unit file
  is `zed_media_server_cli.service`, which is disabled). Plugging a ZED X in
  today would not produce a working camera. See decision 3 below.

  Also present: **three calibration files** (`SN11316`, `SN24605000`,
  `SN3206`), dated 2026-08-01. These are auto-downloaded per camera serial, so
  they suggest ZED cameras have been attached to this machine at some point —
  but they are *not* evidence of any camera being present now.

- **Cameras actually present today:** **NONE.** `/dev/video*` does not exist,
  so there is no USB webcam either. `nvargus-daemon` is running but has no CSI
  sensor behind it. **The cockpit video pane has no source on this machine
  right now** — the cheapest fix by far is to plug in any USB webcam, which
  needs no driver work at all (`v4l2-ctl` would be worth installing too, it is
  currently missing).

- **GNSS / IMU:** **NOT FOUND on this machine — neither one.** `/sys/bus/iio/devices`
  is completely empty, so no IMU is exposed to Linux. There is no `/dev/ttyACM*`
  (the usual home of a USB GNSS puck), nothing GPS-shaped in `dmesg`, and
  `ModemManager` is running but has no modem. The AGX Orin Developer Kit has no
  onboard IMU, and the IMU we would otherwise have inherited lives *inside* the
  ZED, which is absent. **This machine currently has no source of position,
  heading, or attitude whatsoever.** That decides the autonomy question below.

- **Other:** two **CAN** interfaces (`can0`, `can1`, Tegra `mttcan`) exist and
  are DOWN — a future vehicle-bus option, unused today. Ten I2C buses are
  exposed, none with an identified device.

## 6. Network reality

```
$ ip a
2: wlP1p1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    link/ether f0:68:e3:7f:a9:4f
    inet 192.168.1.10/24 brd 192.168.1.255 scope global dynamic wlP1p1s0
    inet6 2401:4900:1c09:68cf:13b3:9421:6632:ea2/64 scope global temporary dynamic
3: can0: <NOARP,ECHO> mtu 16 state DOWN
4: can1: <NOARP,ECHO> mtu 16 state DOWN
5: eno1: <NO-CARRIER,BROADCAST,MULTICAST,UP> state DOWN      # ethernet unplugged
9: tailscale0: <POINTOPOINT,...,UP,LOWER_UP> mtu 1280 state UNKNOWN
    inet 100.116.120.118/32 scope global tailscale0
10: docker0: <NO-CARRIER,...> inet 172.17.0.1/16  state DOWN

$ ip route
default via 192.168.1.1 dev wlP1p1s0 proto dhcp metric 600
192.168.1.0/24 dev wlP1p1s0 proto kernel scope link src 192.168.1.10 metric 600

$ nmcli -t -f NAME,TYPE,DEVICE con show --active
Airtel_raje_1652:802-11-wireless:wlP1p1s0
tailscale0:tun:tailscale0
docker0:bridge:docker0

$ tailscale status
100.116.120.118  ubuntu-1           akash@  linux  -
100.113.68.39    akash-macbook-pro  akash@  macOS  active; direct 47.211.210.229:41641, tx 584156 rx 210412
100.81.28.60     ubuntu             dev@    linux  offline, last seen 11d ago
# Health check:
#  - enabling connmark rules: ... iptables v1.8.7 (legacy): unknown option "--restore-mark"

$ ping -c2 -W2 192.168.1.164          # the operator laptop per CONNECT.md
2 packets transmitted, 0 received, 100% packet loss
$ ip neigh | grep 192.168.1.164
192.168.1.164 dev wlP1p1s0  INCOMPLETE

$ ping -c2 -W2 100.113.68.39          # the MacBook over tailscale
2 packets transmitted, 2 received, 0% packet loss
rtt min/avg/max/mdev = 265.815/271.588/277.362/5.773 ms

$ ip neigh                             # who is actually on this LAN
192.168.1.1  lladdr 0c:36:23:f2:32:40 REACHABLE      (router)
192.168.1.3  lladdr 30:f6:ef:6d:42:32 REACHABLE
192.168.1.7  FAILED
192.168.1.164 INCOMPLETE

$ systemctl is-enabled ufw
Failed to get unit file state for ufw.service: No such file or directory
$ sudo -n iptables -S INPUT
sudo: a password is required            # could not verify raw rules
```

**In plain language:** This Jetson reaches the world **over wifi only**, on the
`Airtel_raje_1652` network as **192.168.1.10/24**, gateway 192.168.1.1. It also
has a global IPv6 address. **Ethernet (`eno1`) is physically unplugged**
(NO-CARRIER) — worth knowing, because a cabled link is the more reliable option
for a bench session. **There is no cellular**: `ModemManager` is running but no
modem device exists, so the vehicle has no independent uplink and is entirely
dependent on whatever wifi it is in range of. For a field demo that is the
weakest link in the whole chain.

**Tailscale is up and healthy**, as `ubuntu-1` at **100.116.120.118** on
akash@'s tailnet. The MacBook (`akash-macbook-pro`, 100.113.68.39) is online
with a direct connection, and pings at **~271 ms** — usable for control-plane
traffic and shell access, but that latency is far too high for a responsive
teleop video/drive loop; teleop wants the LAN path. A third node (`ubuntu`,
100.81.28.60) has been offline 11 days. Tailscale reports one health warning:
it cannot install its connmark rules because this system has legacy iptables
without `--restore-mark`. That has not stopped it working, but it is a known
cause of odd routing behaviour and is worth cleaning up.

**Firewall: nothing is blocking inbound 8090.** `ufw` is not installed at all
on this machine, so there is no host firewall in the way — as confirmed
empirically in section 7, where the bridge bound `0.0.0.0:8090` and accepted a
connection. I could not dump the raw iptables rules (`sudo` wanted a password),
so I am reporting "no ufw, and the port demonstrably accepted a connection"
rather than claiming the full ruleset is clean.

**On the operator laptop at 192.168.1.164: it is NOT reachable from here.**
100% packet loss and an `INCOMPLETE` ARP entry mean nothing answered at that
address on this segment — the address is unused, not merely firewalled (a
firewalled host would still ARP). The only hosts actually present on this LAN
are the router (192.168.1.1) and **192.168.1.3**. Akash confirmed the laptop is
connected for testing, so **the laptop's address has almost certainly changed
from the 192.168.1.164 recorded in `CONNECT.md`** — 192.168.1.3 is the likely
candidate. `CONNECT.md` should be updated once the real address is confirmed.

## 7. Mock bridge bench test (optional, only if the human was present)

- **Ran it:** **yes** — Akash was present and confirmed the laptop was
  connected for testing.

  Before running it I verified from source that it cannot touch the vehicle:
  ```
  $ grep -rn "import serial|/dev/tty|Serial(" drive/bridge/
  (no output)          # the bridge package never opens a serial port, at all
  $ grep -n "vehicle" drive/bridge/__main__.py
  ap.add_argument("--vehicle", choices=["mock"], default="mock")   # mock is the only option
  ```

- **Bridge started:** **yes.**
  ```
  $ ARGUS_PASSWORD='Argus@2026' python3 -m drive.bridge
  $ ss -tlnp | grep 8090
  LISTEN 0 128  0.0.0.0:8090  0.0.0.0:*  users:(("python3",pid=25186,fd=3))
  ```
  It binds `0.0.0.0:8090` as documented and stays up. It logs nothing on
  startup and nothing on an incoming connection.

- **Cockpit on the laptop reached it:** **not on the first attempt; YES on the
  second.** See section 10b — the LAN path is blocked by AP client isolation,
  but the cockpit reached the bridge over Tailscale and a full 30-second drive
  test was completed. The first-attempt notes below are left as written.

  No peer appeared against port 8090 during the first attempt
  (`ss -tnp | grep 8090` stayed empty).
  This is a *negative result on the laptop side only*, not a bridge fault:
  the laptop never became reachable from the Jetson at all (section 6 —
  192.168.1.164 does not answer and has no ARP entry).

  **What I did prove:** the full WebSocket path works end to end on the
  Jetson itself —
  ```
  $ python3 -c "websockets.connect('ws://127.0.0.1:8090')"
  WS handshake: OK
  connected, no unsolicited message within 5s
  ```
  So the daemon runs, binds the documented port, completes a real WebSocket
  handshake, and is not blocked by any host firewall. The untested link is
  exactly one hop: laptop → `ws://192.168.1.10:8090`.

- **Anything in the way:**
  - **The laptop's IP is wrong in `CONNECT.md`.** 192.168.1.164 is dead on
    this network; the only other live host is **192.168.1.3**. Retry the
    cockpit against `ws://192.168.1.10:8090` from whatever address the laptop
    actually holds — the Jetson's address, 192.168.1.10, is the correct target
    and is confirmed.
  - No firewall obstacle: `ufw` is not installed and the port accepted a
    connection.
  - Python version is fine: 3.10.12, and the bridge is pure stdlib as
    documented — no venv needed, nothing was installed.
  - `--report` was **not** passed, correctly: `paho-mqtt` is not installed on
    this machine (section 3).
  - The bridge was stopped after the test; nothing was left running.

---

## 8. ADDENDUM - a second pass found things the first pass missed

Added later the same session, after a deeper hunt for the firmware. **Two of
these correct errors in the sections above.** The originals are left standing
rather than quietly edited, so the mistakes are visible.

### 8a. CORRECTION: the `dialout` interlock does not exist

In section 2 I reported that `tessy_01` is **not** in the `dialout` group, and
in decision 1 I recommended keeping that as a safety interlock. **That was
wrong.**

```
$ getent group dialout
dialout:x:20:tessy_01                      # the user IS in dialout

$ tail -1 ~/.bash_history
! sudo usermod -aG dialout $USER           # run today, via Claude Code's ! prefix
```

I read the group list from `id` in my own shell, and that shell was started
*before* the `usermod` ran, so it reported stale membership. `getent` reads the
real database. **Any process started from a new login as `tessy_01` can open
`/dev/ttyUSB0` with no sudo.** There is no interlock between a mistake and the
drive controller. Restoring one (`gpasswd -d`, or a udev rule) is a deliberate
decision for the human, not something this survey should do silently.

### 8b. CORRECTION: there is an entire ROS 2 workspace I missed

**`/home/tessy_01/Desktop/ros2_new/`** — a real git repository, **31 commits**,
last commit **2026-08-03**, already built (13 packages in `build/`). My first
pass missed it because I searched for `*remo*`, `*.ino` and `firmware*`
patterns, and this directory matches none of them.

```
$ ls /home/tessy_01/Desktop/ros2_new/src
bms_monitor  phone_gps  serial_control  status_check
system_terminal  web_server  zed_bringup  zed-ros2-wrapper

$ ls /home/tessy_01/Desktop/ros2_new/build
bms_monitor  phone_gps  serial_control  status_check  status_interfaces
system_terminal  web_server  zed_bringup  zed_components  zed_ros2  zed_wrapper

$ git -C /home/tessy_01/Desktop/ros2_new remote -v
(empty - NO remote. 31 commits exist only on this machine.)
```

**This corrects two claims in section 3 and section 5.** The ZED ROS wrapper is
**not** absent — `src/zed-ros2-wrapper` is checked out from upstream Stereolabs
and `zed_wrapper`, `zed_components`, `zed_ros2` and `zed_bringup` are all
built. It is absent from `/opt/ros/humble`, which is what I actually checked.

### 8c. A second, competing command vocabulary — and it is explicitly fake

`src/web_server/frontend/src/config/commands.js` (2026-08-03) defines a full
named protocol. **Read its header before using any of it:**

```js
/*
 * Vehicle command vocabulary + telemetry parsing.
 *
 * `cmd_node` (serial_control) writes every /cmd message VERBATIM to the
 * serial device, so the exact tokens below are the firmware's protocol —
 * not anything ROS interprets. These are mnemonic placeholders. When you
 * know the real firmware tokens, this is the ONE file to edit; the UI reads
 * everything from here.
 */

export const CMD = {
  steer: { left: 'STEER:L', right: 'STEER:R', center: 'STEER:C' },
  ring: { on: 'LIGHT:RING:ON', off: 'LIGHT:RING:OFF' },
  beam: { high: 'BEAM:HIGH', low: 'BEAM:LOW', off: 'BEAM:OFF' },
  horn: { on: 'HORN:ON', off: 'HORN:OFF' },
  park: { on: 'PARK:ON', off: 'PARK:OFF' },
  indicator: { left: 'IND:L', right: 'IND:R', off: 'IND:OFF' },
  gear: { D: 'GEAR:D', R: 'GEAR:R', N: 'GEAR:N' },
  mode: { manual: 'MODE:MANUAL', auto: 'MODE:AUTO' },
  speed: { 1: 'SPEED:1', 2: 'SPEED:2', 3: 'SPEED:3' },
  brake: (level) => `BRAKE:${level}`,   // 0..15
  accel: (level) => `ACCEL:${level}`,   // 0..172
  estop: 'ESTOP',
  nav: { start/end (lat,lon), go: 'NAV:GO', abort: 'NAV:ABORT' },   // PLACEHOLDER
  auto: { maxSpeed, roadDetect, objClass },                          // PLACEHOLDER
};
```

**These tokens are mnemonic placeholders by the author's own statement — a
wish list, not an observed protocol.** They must not be used to write an
adapter. Doing so is precisely the "guessing the protocol from something that
looks authoritative" failure this survey exists to prevent.

**Which vocabulary is actually current? The dates favour the crude one:**

| Artifact | Date | Protocol |
|---|---|---|
| `ros2_new` `commands.js` | 2026-08-03 18:17 | named tokens, self-declared placeholders |
| `ros2_new` last commit | 2026-08-03 19:31 | — |
| `Desktop/Remote/bridge.py` + `index.html` | **2026-08-11 13:11** | `R<n><0|1>` relays + `P<42..214>` |

The newest artifact on the machine, by eight days, is the **14-relay tester**,
not the named vocabulary. That is what someone builds while *discovering* a
protocol, not after they have one.

**One numeric link between the two, offered as a hypothesis and not a finding:**
`ACCEL` is documented `0..172`; the relay UI's PWM slider runs `42..214`.
**214 − 42 = 172, exactly.** That is consistent with `ACCEL:<n>` being emitted
as PWM duty `42+n` — a 42-count idle floor with 172 counts of travel. If it
holds, it independently confirms **42 = idle and 0 is NOT "no throttle"**.
Test at the bench before trusting it.

`serial_control/serial_link.py` and `cmd_node.py` are pure transport
(reconnect loop, thread-safe write, alerts on `ERR`/`FAULT`/`ALERT` substrings)
and know no vehicle function. `serial_link.py` still hardcodes
`DEFAULT_DEVICE = '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'` — the
**CH340 path that no longer exists**, same stale assumption as the Go program.

### 8d. Firmware hunt: a much stronger negative

The firmware is not on this disk, and this is now more than "find came up empty":

- **No `~/Arduino`, `~/.arduino15`, `~/.platformio`, `~/snap/arduino`.** The
  Arduino/PlatformIO toolchain has *never been installed here* — so the
  firmware was never built or flashed from this Jetson.
- **`~/.bash_history` (874 bytes, read in full)** contains no `avrdude`,
  `arduino-cli`, `esptool`, `pio`, `stty`, `screen`, `minicom` or `picocom`.
  Nothing has ever opened that port from a shell on this machine.
- **The Remo / RemoV1 / Remote folders are not git repos at all**, so there is
  no deleted-file history to recover from them.
- **`ros2_new` is a git repo, and across all 31 commits** `git log --all
  --pretty=format: --name-only` contains no `.ino`, `firmware`, `sketch` or
  `.hex`. It was never committed and later deleted.
- No firmware-shaped `.hex`/`.bin` anywhere outside NVIDIA/Firefox/Thunderbird
  noise.

### 8e. Where this code came from — and what has no backup

No Dropbox, Syncthing, or Drive client is installed. But the directory names
give it away: `/all-folders/Remo-20260731T115814Z-1-001` and the matching
`~/Downloads/*.zip` use **Google Drive's export naming** (`TIMESTAMP-N-NNN`).
The Remo code arrived as **Google Drive zip downloads on 2026-07-31**.

So **the machine holding the firmware is whoever owns that Google Drive** —
that is the lead worth chasing, not more searching here.

**Flagging a risk that is not about the vehicle at all:** `ros2_new` has **no
git remote**. Thirty-one commits of real work — the console, the BMS monitor,
the GPS node, the serial bridge — exist **only on this Jetson's disk**, on a
machine that gets powered off between sessions. That should be pushed
somewhere before anything else happens to it.

### 8f. What this adds to the sensor picture

- **There IS a position source, and it is a phone.** `phone_gps/gps_node.py`
  takes browser geolocation from a phone over the console's authenticated
  WebSocket and republishes it as `sensor_msgs/NavSatFix` on `~/fix`, with
  compass heading on `~/heading`. So section 5's "no source of position,
  heading or attitude whatsoever" is right about *onboard* hardware but wrong
  in effect: a working phone-as-GNSS path is already written and built. Its
  docstring notes `fix_topic` can be repointed at ZED's GNSS-fused output with
  no frontend change.
- **The battery pack is specified, and it is not on the MCU link.**
  `bms_monitor` carries a full edge-triggered alert engine with real limits:
  pack **39.0–54.6 V**, cell **2800–4250 mV**, imbalance **150 mV**, current
  **50 A**, temperature **−10 to 50 °C**, SOC warning below **15%**. A
  39–54.6 V pack is a **48 V nominal, 13S lithium pack**. It is read over
  **BLE**, separately from the MCU serial link.

---

## 9. The relay map, supplied by the team - and cross-checked against this disk

**Provenance, stated plainly: this map did NOT come from anything on this
machine.** It was supplied by Akash's team during the survey session and
relayed to me by the laptop-side session, which recorded it in
`MCU-PROTOCOL.md` marked UNVERIFIED. **No firmware has been read and no port
has been opened, so nothing below is confirmed against the hardware.** What I
*can* do — and did — is check it against the three artifacts on this disk.

| Relay | Supplied function |
|---|---|
| R1 | ring light |
| R2 | right indicator |
| R3 | left indicator |
| R4 | reverse |
| R5 | **neutral** |
| R6 | high beam |
| R7 | low beam |
| R8 | horn |
| R9 | brake — **DISCONNECTED** |
| R10 | brake — **DISCONNECTED** |
| R11 | speed 1 |
| R12 | speed 3 |
| R13 | steering right |
| R14 | steering left |
| PWM | throttle `P<42..214>` |

### 9a. The relay UI corroborates nothing — it has no semantics at all

`Desktop/Remote/public/index.html` cannot agree or disagree with the map,
because its fourteen buttons are **loop-generated, not authored**:

```js
for(let i=1;i<=14;i++){
  card.innerHTML = `<h3>Relay ${i}</h3>
    <button class="on"  onclick="send('R${i}1')">ON</button>
    <button class="off" onclick="send('R${i}0')">OFF</button>`;
}
```

Every card is literally "Relay 1".."Relay 14". No labels, no grouping, no
tooltips, no aria-labels, no comments, no commented-out blocks. That absence is
itself informative: whoever built this today was **exercising channels, not
driving a vehicle**. Its one corroboration is `<h2>PWM Control (D9)</h2>` with
`min="42" max="214"` — confirming throttle is PWM on pin D9 across that band.

### 9b. `commands.js` corroborates the map strongly — 12 of 14 relays match

| Relay | `commands.js` token | |
|---|---|---|
| R1 ring light | `LIGHT:RING:ON/OFF` | agree |
| R2 / R3 indicators | `IND:R` / `IND:L` | agree |
| R4 reverse | `GEAR:R` | agree |
| R5 neutral | `GEAR:N` | agree |
| R6 / R7 beams | `BEAM:HIGH` / `BEAM:LOW` | agree |
| R8 horn | `HORN:ON/OFF` | agree |
| R11 / R12 speed 1,3 | `SPEED:1` / `SPEED:3` | agree |
| R13 / R14 steering | `STEER:R` / `STEER:L` | agree |
| PWM 42..214 | `ACCEL:0..172` | agree, via the +42 offset |
| R9/R10 brake **disconnected** | `BRAKE:0..15` | **conflict** |
| *(no relay)* | `SPEED:2` | **conflict** |
| *(no relay)* | `GEAR:D` | **conflict** |
| *(no relay)* | `PARK:ON/OFF` | **conflict** |
| *(no relay)* | `ESTOP` | **conflict** |

Twelve of fourteen is not coincidence. **"Ring light" is an unusual thing to
name**, and it appears independently in the team's map and in a file written
2026-08-03 by someone who had not seen that map. Reading: `commands.js` was
written by someone who **did** know the real hardware inventory, and its
"mnemonic placeholders" caveat refers to the exact token **spelling**, not to
the functional list. The inventory is corroborated; the wire format is not.
**The placeholder warning in section 8c stands unchanged.**

**The 42-offset hypothesis gains a second, independent witness.**
`ControlPanel.jsx` renders `<Group title="Acceleration · 0–172">` with
`<FillButton min={0} max={172}>`, beside a hardware PWM band of 42–214 whose
width is exactly 172. Still a hypothesis; now a well-supported one.

### 9c. The console exposes three controls this hardware cannot perform

And **nothing in the code warns about any of them.** I grepped `ControlPanel.jsx`,
`AutonomyTab.jsx` and `commands.js` for disconnect / not-wired / no-relay /
TODO / FIXME / does-nothing. The only `PLACEHOLDER` comments cover the autonomy
NAV/AUTO tokens and the OSRM routing demo — nothing flags brake, estop or park.

1. **Brake.** A 16-level slider, `Group title="Brake · 0–15"`, styled with the
   stop hue. Both brake relays are disconnected. An operator drags a prominent
   red brake control and the vehicle does not slow. **The most dangerous of the
   three, because it looks the most functional.**
2. **E-stop.** `const engageEstop = () => { setEstop(true); send(CMD.estop); };`
   It latches the UI to "stopped" and emits a token no relay implements. **A
   latching E-stop that reports success and does nothing is worse than no
   button at all**, because it gets trusted at the exact moment it matters.
3. **Park.** Toggles, and doubles as hazards (both indicators lit). The hazard
   half is achievable via R2+R3; the park half has no relay.

Plus `SPEED:2` and `GEAR:D`, offered in segmented controls with no relay behind
them.

### 9d. Steering is bang-bang — three independent artifacts agree

Section 4 recorded this as unanswerable. It is now answered, and the answer is
the unwelcome one. `ControlPanel.jsx` does not use a slider for steering:

```jsx
<HoldButton label="Left"  onPress={() => send(CMD.steer.left)}  onRelease={() => send(CMD.steer.center)} />
<HoldButton label="Right" onPress={() => send(CMD.steer.right)} onRelease={() => send(CMD.steer.center)} />
```

Press-to-energize, release-to-centre **is** relay behaviour. The author of that
console already knew steering was not proportional. The old Remo UI did the
same with `L1/L0` and `R1/R0`. Three artifacts, one answer.

### 9e. No program asserts a safe state, ever — and drive is the default

Nothing in any of the three programs writes to the serial port unsolicited:

- `bridge.py` `main()` opens the port, starts the reader, serves HTTP. It never
  writes unprompted; on `ConnectionClosed` it discards the client and nothing more.
- `main.go` is the same shape — on disconnect it deletes the client, no serial write.
- `cmd_node.py` publishes a `SERIAL_LINK` **critical alert** on link loss — an
  alert to a human, not a command to the vehicle.
- The relay UI's PWM slider has `value="42"` in the DOM but only sends on
  `oninput`, so **loading the page sends nothing** and the MCU keeps whatever
  throttle it was holding.

Combined with the supplied map, the picture for this body is:

> **Drive is the de-energized default** (relays exist for reverse and neutral,
> none for drive, so `GEAR:D` can only mean "energize neither"). **There is no
> brake. There is no ignition relay and no E-stop relay.** No host program
> implements a watchdog or failsafe, and **no component asserts neutral at any
> point in any lifecycle.** After a crashed browser, the vehicle's motion state
> is whatever it was before the crash. This body has **no passive safe state**.

**The actionable qualification, and the single most useful line in this
document:** a safe state *is* reachable — **R5 is neutral**. It is simply never
commanded. Any real adapter should **assert neutral on startup, on client
disconnect, on watchdog trip, and on self-test failure.** That is one relay
write, and it is the difference between this body having a failsafe and not.

---

## 10. Late findings: steering internals, and the bridge under a bad link

### 10a. STEERING: the part that limits travel is the part that is unplugged

Supplied by the team, same provenance caveat as section 9 — **unverified against
hardware, no port opened.** Four facts about R13/R14:

1. Steering **angle sensing exists, but is DISCONNECTED right now.**
2. The actuator is driven on/off with **REVERSING POLARITY** — R13 and R14 are
   the **two polarity legs of one actuator**, not two independent relays.
3. **No PWM speed control** on steering.
4. What stops the actuator over-travelling is **the steering feedback sensor**.

**Read 1 and 4 together: the component that prevents over-travel is the
component that is currently unplugged.** Every long press on the console today
runs the actuator into its mechanical stop with nothing telling it to stop —
stalled actuator, burnt motor, damaged linkage, or a blown fuse.

This is worse than "steering is bang-bang" (section 9d). Bang-bang steering
with a working limit sensor is crude but safe. Bang-bang steering with the
limit sensor unplugged is a **damage mechanism that triggers on ordinary
operator input**, and the current console — with its press-and-hold steering
buttons — invites exactly that input.

**Two rules that must be enforced in the adapter, not left to the operator:**

- **Steering pulses must be open-loop and TIME LIMITED.** No continuous hold,
  ever, until that sensor is reconnected.
- **R13 and R14 must be mutually exclusive IN CODE.** They are two polarity
  legs of one actuator: energizing both is undefined at best, and a short
  across the driver at worst. This cannot be left to UI discipline — the old
  Remo UI and the ROS console both let a fast operator overlap presses.

**Reconnecting that sensor is the highest-value hardware fix on this vehicle.**
It restores over-travel protection *and* it makes proportional steering
achievable in software on the existing relays — pulse a leg, read the angle,
stop at target. Same hardware, real steering. It also converts the `steer`
field that `parseTelemetry()` already looks for (section 8c) from dead code
into a live signal.

### 10b. The mock bridge under a 271 ms relayed link: it holds

The cockpit drove this bridge from the MacBook over Tailscale for 30 seconds at
15 Hz, mock adapter, on the real relayed path. Cockpit-side numbers, measured
by the laptop session:

```
tcp connect                       594 ms
auth to role                      303 ms, role DRIVER
preflight                         ran, pass true (mcu_link, battery, steering all ok)
commands sent                     443, at 15 Hz over 30 s
telemetry frames                  329, against ~330 expected at 10 Hz
gap ms  min/mean/median/p95/max    0 / 100 / 0 / 277 / 311
gaps over 700 ms                  0
safety state                      STOPPED -> DRIVING
LATCHED events                    0
errors                            none
```

Jetson-side, measured here:

```
$ ps -p 35020 -o etime,%cpu,%mem,rss,nlwp
   ELAPSED  %CPU %MEM   RSS  NLWP
     09:29   0.4  0.0  16032    3

load average: 0.17, 0.27, 0.35        cpu-thermal 48.4 C
```

**The 700 ms watchdog survives a 271 ms relayed link with zero latches and
effectively no frame loss**, at 0.4% of one CPU and 16 MB RSS. Teleop *control*
over a bad link is de-risked — that is a real result.

But note the **shape**: median gap 0 ms, p95 277 ms. Frames arrive **clumped,
not evenly spaced** — DERP relay batching. Control tolerates clumping because
each frame carries absolute state. **Video will not**, and video is the thing
that actually dies on this path. So the network fix (section 6 — AP client
isolation is blocking the direct LAN path) stays a hard demo requirement even
though control passed.

### 10c. The bridge daemon is completely silent — no audit trail exists

Worth recording separately, because I went looking for drops and could not
answer the question:

```
$ wc -c < <bridge stdout+stderr capture>
0
$ grep -rnE "print\(|logging\.|logger|log\(" drive/bridge/daemon.py
(no output)
```

Across that entire session — a client connecting, authenticating, being granted
the **DRIVER** role, running a preflight self-test, sending **443 commands** and
receiving **329 telemetry frames** — the daemon wrote **zero bytes**.
`daemon.py` contains no logging calls of any kind.

I therefore **cannot report on dropped connections from this side**, because
nothing records them. That is the honest answer, and the absence is the finding:
a vehicle control daemon with no audit trail cannot answer "who was driving,
when, and what did they command" after an incident. For a machine that moves,
that should be fixed before the real adapter lands, not after.

---

## 11. The firmware arrived - what it confirms, and what I got wrong

The team supplied the sketch late in the session; it is now in
`bodies/ugv-01/firmware/ugv01_mcu.ino`, with the full analysis in
`MCU-PROTOCOL.md`. **It has not been read back off the chip**, so it is the
source we were handed, not verified silicon — but it corroborates the wire
protocol reconstructed independently here (115200, `R<n><0|1>`, `P<42..214>`),
which is strong evidence it is the right sketch. I read it directly rather than
relying on the analysis.

**Section 4's table is now largely answerable from `MCU-PROTOCOL.md`.** Rather
than duplicate it, this section records only what changes *my* conclusions.

### 11a. CORRECTION: the `R<n><0|1>` ambiguity I flagged is not real

Section 4 listed the grammar as ambiguous — `R10` as "relay 1 off" versus a
truncated "relay 10". **The firmware resolves it cleanly and I was wrong:**

```c
int state = cmd.substring(len-1).toInt();      // last char is always the state
int relay = cmd.substring(1, len-1).toInt();   // everything between is the index
```

Positional and unambiguous: `R101` → relay 10 on, `R10` → relay 1 off. **Treat
that hazard as withdrawn.** A phantom risk competing for attention with the
real ones is worse than no note at all.

### 11b. Confirmed: no failsafe, and no telemetry at all

The entire loop guard is `if(!Serial.available()) return;` — no `millis()`, no
timeout. **If the cable falls out at throttle 150, the vehicle holds throttle
150 until someone removes power.** Section 4 recorded this as "unknown, assume
hold"; it is now confirmed as hold, in the strongest form.

`Serial.begin()` is called and `Serial.print`/`println` **never are**. So the
MCU transmits nothing, ever. Two consequences:

- Section 4's telemetry row resolves to **there is none** — not "not captured".
- **Reconnecting the steering angle sensor does nothing on its own.** There is
  no `analogRead` anywhere in the sketch. The team's claim that the feedback
  sensor limits steering travel (section 10a) **cannot be true of this
  firmware**, and that needs putting back to them.

There is also a **pinout constraint** on fixing it. `relayPins[] = {2,3,4,5,6,
7,8,10,11,12,A0,A1,A2,A3}` means relays 11–14 occupy A0–A3 — so **R13 (steer
right) is A2 and R14 (steer left) is A3**, and the four analog pins most
obviously available for a steering potentiometer are consumed as digital relay
outputs. On an Uno/Nano that leaves A4/A5 (also the I2C pins), or A6/A7 on a
Nano. So "reconnect the sensor" is really: reconnect it, free or choose an ADC
pin, add the read and the emission, and reflash. Worth knowing which board it
is — Uno, Nano and Pro Mini differ in exactly the pins that matter.

### 11c. Power-on state is known; the RESET WINDOW is not

`setup()` drives all 14 relay pins HIGH and writes PWM 42, and the command path
is `state ? LOW : HIGH`, so **relays are active-LOW and HIGH is released**.
Steady state after boot: everything released, throttle at rest. Good.

**But that is the state AFTER `setup()` runs, and it is not the state during a
reset.** On DTR reset the MCU reboots, and before `setup()` executes every pin
is an **INPUT — high impedance**. On a stock Uno/Nano bootloader that window is
roughly **1–2 seconds**, not microseconds. Throughout it, the relay board's
inputs float, and what the relays do is decided by that board's pull resistors
and opto bias — hardware **nobody has characterised**. Pin 9 floats too, so the
throttle driver sees an undriven input rather than a commanded 42.

**So: the commanded state after reset is safe and known; the state during the
1–2 second reset window is not.** That is a smaller risk than "unknown power-on
behaviour", and a real one — and it is precisely the window `listen.py` opens
when it touches DTR. It argues for **wheels off the ground**, not merely drive
power isolated, on the first run.

The caution in section 4 was not wasted: it was cheap, and it was correct.

### 11d. Two integration defects found by reading the firmware against the console

Both matter for whoever writes the adapter, and neither is visible from either
file alone:

1. **A failsafe would raise no alert.** The proposed v2 firmware emits
   `Serial.println("FAILSAFE")`, but `cmd_node.py` matches alerts on
   `alert_patterns = ['ERR', 'FAULT', 'ALERT']` by substring. **"FAILSAFE"
   contains none of them**, so the single most important thing the vehicle can
   ever say arrives as ordinary chatter and the alert rail stays quiet.
   Cheapest fix is firmware-side: emit `ALERT:FAILSAFE`, which matches the
   existing list with no ROS change and nothing to remember per deployment.
2. **A noise-fed watchdog may not fire.** v2 resets its timer on *any*
   non-empty line. A cleanly yanked cable is caught, but a **marginal or
   partly-unseated connector on a vibrating vehicle produces spurious bytes**,
   and each junk line convinces the watchdog the link is healthy. The failure
   mode most likely to occur is the one most likely to suppress the guard. Feed
   the timer only from recognised input — `H`, `V`, and successfully parsed `P`
   and `R` commands.

---

## What this changes

> **STALE IN PLACES. Read sections 9 and 10 first.** This block was written
> before the team supplied the relay map and before the steering internals
> arrived. Specifically: decision 1's "the relay map is missing" is now
> answered by section 9 (unverified, but no longer absent), its "is steering
> proportional" is answered by section 10a (no, bang-bang, three artifacts
> agree), and its recommendation to preserve the `dialout` interlock is wrong
> because section 8a shows that interlock was already gone. The synthesis of
> record is `bodies/ugv-01/MCU-PROTOCOL.md`.
>
> **Revised by section 8.** The addendum sharpens decision 1 (there are now
> *two* candidate protocols, and the more official-looking one is explicitly
> fake), softens decision 2 (a phone-based GNSS path already exists and is
> built), and advances decision 3 (the ZED ROS wrapper is present and built,
> not absent). Read section 8 alongside each decision below.

### 1. The real VehicleAdapter — **no, not yet, and the blocker is specific**

**Confidence: high, on the blocker itself.** The MCU protocol is **not** known
well enough to write `drive/bridge/vehicle.py` against it, and the gap is not
"some detail is fuzzy" — it is that **the entire mapping from vehicle function
to wire command is missing**.

What we *do* have, with good confidence: the transport (`/dev/ttyUSB0`, FTDI
FT232R S/N A5069RR4, 115200, ASCII, `\n`-framed, no checksum) and the syntax of
two command families (`R<n><0|1>` for relays 1–14, `P<42..214>` for one PWM
channel on D9).

What is missing, and must come before any adapter:

1. **The firmware source.** It is not on this machine. This is the top of the
   list — it answers everything below at once.
2. **The relay map**: which of `R1..R14` is ignition, gear F, gear N, gear R,
   brake, lights, horn, and which are unused. Fourteen unlabelled relays on a
   vehicle that can move is the definition of unsafe-to-guess.
3. **What actually steers, and whether it is proportional.** The old bang-bang
   `L`/`R` commands are gone from the current UI and nothing named has replaced
   them. This is the question the README asks and I cannot answer it honestly.
4. **The meaning of the 42–214 PWM band**, and specifically what value means
   "no throttle" — the resting value is 42, not 0.
5. **The telemetry format**, which needs one supervised port capture with the
   wheels off the ground.
6. **The failsafe behaviour on serial silence.** Nothing host-side implements
   one, so unless the firmware does, the vehicle holds its last command
   indefinitely after a link loss. `drive/bridge`'s watchdog design assumes it
   can command a safe stop — that assumption is currently unverified against
   real hardware.

Two of these (5 and 6) can be answered in a single short bench session:
wheels off the ground, open `/dev/ttyUSB0` read-only, watch what the MCU emits,
then stop sending and watch what it does. Everything else needs the firmware.

**One thing worth deciding deliberately:** the login user is *not* in the
`dialout` group, so nothing running as `tessy_01` can open the MCU port today.
That accident is currently the best safety interlock on this machine. I would
keep it, and grant access explicitly and temporarily when it is time.

### 2. Point-A-to-B autonomy for the demo — **no. Manual teleop is the honest demo.**

**Confidence: very high.** This is the clearest finding of the survey and it
does not depend on any of the firmware unknowns.

**There is no sensing on this machine at all.** No GNSS (nothing on
`/dev/ttyACM*`, nothing in `dmesg`, no modem). No IMU (`/sys/bus/iio/devices`
is empty; the AGX Orin devkit has none onboard, and the one we would have had
lives inside the absent ZED). No camera of any kind (`/dev/video*` does not
exist). No wheel encoders visible anywhere.

Point-A-to-B autonomy needs to know where the vehicle is and which way it is
pointing. This machine currently cannot answer either question by any means.
Dead reckoning is not a fallback here — dead reckoning still needs a heading
source and an odometry source, and there are none. Nav2 is not even installed
(section 3).

**Recommendation:** demo manual teleop, and make it excellent. The teleop path
is nearly complete already — the bridge runs, the network works, the transport
to the MCU is understood. Add a USB webcam for the video pane (the cheapest
single improvement available: no driver work, and it fills the one obviously
empty panel in the cockpit). If autonomy must be on the roadmap, the minimum
shopping list is a GNSS receiver plus an IMU — or, equivalently, the ZED X
back on the vehicle, which brings its own IMU with it.

### 3. The ZED integration path — **SDK ready, kernel driver is the real work**

**Confidence: high on the facts, medium on the effort estimate.**

The good news is bigger than expected: **JetPack 6.2 / L4T 36.5 is current and
well within range, and the ZED SDK 5.4.1 is already installed** with a working
Python API. CUDA 12.6 and TensorRT 10.3 are in place. Nothing about the
software base needs upgrading, and no reflash is implied.

What has to become true before a **ZED X** works here:

1. **A GMSL capture driver built for L4T 36.x must be installed.** This is the
   actual blocker. A ZED X is not USB — it is a GMSL2 camera that needs the
   kernel-side deserialiser driver (MAX9296 or MAX96712, depending on the
   capture card) plus the **ZED X Daemon**. The drivers bundled in
   `/usr/local/zed/drivers` are **L4T 35.1/35.2/35.3 only** and will not load
   on this 36.5 kernel. The L4T 36-compatible ZED X driver has to be fetched
   from Stereolabs separately.
2. **The GMSL capture card itself must be physically present.** I could find no
   evidence of one — no MAX9296/MAX96712 in `dmesg`, no `/dev/video*` nodes.
   Whether the vehicle has the capture card and which deserialiser it uses
   needs a physical check; it determines which of the two driver variants to
   install.
3. **`zed_x_daemon` must be installed and running.** It is not: not on PATH,
   and the only ZED systemd unit present is `zed_media_server_cli.service`
   (disabled).
4. **For the ROS path, `zed_wrapper` must be installed.** Only `zed_msgs` and
   `zed_description` are here — the wrapper itself is missing.

**A cheaper intermediate step worth considering:** any **USB ZED** (ZED 2i,
ZED Mini) would work on this machine *today* with zero driver work — the SDK is
installed and supports them, and the three leftover calibration files hint that
USB ZEDs have been on this machine before. That would deliver stereo depth and
an IMU immediately, which is exactly what decision 2 is missing, without
waiting on the GMSL driver situation.
