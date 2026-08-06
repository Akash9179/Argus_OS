# ARGUS Integration Notes — Reverse-Engineering the `Remo` Drive Controller

**Target project:** `RemoV1/` (Go module `remo`)
**Goal:** Understand the existing control interface so an external WebRTC cockpit can inject normalized `{steer, throttle}` commands by reusing the existing actuation layer.

## TL;DR (read this first)

- **This is NOT a ROS 2 system.** ROS 2 Foxy is installed on the Jetson, but `Remo` does not touch it at all (no ROS imports, no rclpy/rclcpp, no topics). See §3.
- The entire "drive-by-wire" software in this repo is a **~100-line Go program** (`RemoV1/main.go`) that is a **dumb pass-through bridge**: browser → WebSocket (text) → **USB-serial** → **Arduino (or similar MCU)**. The Go program does *no* command interpretation.
- The **real actuation logic lives in firmware on the microcontroller**, which is **not present in this repo**. The Go code's "write to hardware" is a single serial write of ASCII tokens (`RemoV1/main.go:88`).
- Commands are **ASCII text tokens terminated by `\n`**:
  - Steering (bang-bang, momentary): `L1`/`L0`/`R1`/`R0`
  - Throttle (level): `P<n>` where `n` ∈ `[42, 214]`, neutral/stop = `P42`
- **The cleanest integration seam is the existing WebSocket endpoint `/ws`** — your WebRTC bridge becomes just another WS client sending the same tokens. Zero changes to the actuation layer or firmware. See §7.
- **Major caveats:** no proportional steering in the protocol, no watchdog/failsafe/E-stop anywhere in the Go layer, last command is **held** on disconnect, and the serial port is shared by all clients with **no mutex** (multi-writer race). See §5, §6, §7.

---

## 1. ACTUATION PATH

There is exactly one actuation path, identical in transport for steering and throttle — they differ only in the token sent.

### Full chain (UI input → hardware)

```
Browser UI (public/index.html)
    │  button press / slider drag
    │  → JS send(cmd): socket.send("L1" | "L0" | "R1" | "R0" | "P<42..214>")
    ▼
WebSocket "ws://<host>/ws"  (text frame, NO trailing newline)
    ▼
Go server (main.go), per-connection read loop
    │  ws.ReadMessage() → msg                     (main.go:78)
    │  port.Write(append(msg, '\n'))              (main.go:88)  ← THE HARDWARE WRITE
    ▼
USB-serial port  /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0  @ 115200 8N1
    │  (CH340 USB↔UART adapter, vendor 1a86:7523)
    ▼
Microcontroller firmware (Arduino — NOT in this repo)
    │  parses "L1\n"/"P150\n"/... and drives the actual steering + throttle hardware
    ▼
UGV hardware (steering actuator + accelerator/ESC) — PWM/GPIO done ON the MCU
```

### Mechanism: USB-serial / UART (not ROS, not CAN, not host GPIO/PWM)

- The transport to hardware is a **serial port over a CH340 USB-UART adapter**. Evidence:
  - Serial library import: `github.com/tarm/serial` (`RemoV1/main.go:10`, `RemoV1/go.mod:6`).
  - Port opened at `RemoV1/main.go:23-31`:
    ```go
    serialConfig := &serial.Config{
        Name: "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",
        Baud: 115200,
    }
    port, err := serial.OpenPort(serialConfig)
    ```
  - The CH340 adapter is explicitly the device: udev rule `RemoV1/99-ch340-serial.rules` matches `idVendor=1a86 idProduct=7523` (the CH340) and grants the `gpio` group `0660` access so the bridge can open it without root/dialout.
  - The peer is referred to as **"Arduino"** in the UI log (`RemoV1/public/index.html:241`: `console.log("Arduino:", e.data)`).

### The exact code that writes steering AND throttle to hardware

Both go through the **same single line** — the Go layer does not distinguish them:

```go
// RemoV1/main.go:88  (inside the /ws handler's read loop, main.go:76-92)
_, err = port.Write(append(msg, '\n'))
```

- `msg` is whatever the browser sent verbatim (`L1`, `R0`, `P150`, …) read at `RemoV1/main.go:78`.
- The Go server appends `'\n'` as the frame terminator. **The browser does not send a newline** — the server adds it. (Important if you bypass the server and write the device directly — see §7.)
- There is **no PWM/GPIO/CAN code on the Jetson side**. Whatever converts these tokens into PWM duty / servo pulses / motor direction happens in the **MCU firmware**, which is not in this repository.

### Return path (telemetry)

A background goroutine reads lines from the serial port and broadcasts them to all WebSocket clients:
- `RemoV1/main.go:35-61`: `reader.ReadString('\n')` → for each client `client.WriteMessage(TextMessage, msg)`.
- The browser just logs these (`RemoV1/public/index.html:238-245`). This is the only "feedback" channel; its content/format is defined by the firmware (unknown here).

---

## 2. COMMAND CONTRACT

**Common transport for both:**
- **Device path:** `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0` (`RemoV1/main.go:24`)
- **Baud:** `115200` (`RemoV1/main.go:25`)
- **Framing:** `8N1`, no flow control — `tarm/serial` defaults when `Size`/`Parity`/`StopBits` are unset (only `Name` + `Baud` are set, `RemoV1/main.go:23-26`).
- **Line terminator:** `\n` (`0x0A`), appended by the server (`RemoV1/main.go:88`). No `\r`.
- **Encoding:** plain ASCII text tokens.
- **Or, if going through the bridge:** WebSocket text frame to `ws://<host>:8080/ws` carrying the token **without** the newline (`RemoV1/public/index.html:261` `socket.send(cmd)`).

### Steering

| Property | Value |
|---|---|
| Tokens | `L1`, `L0`, `R1`, `R0` (ASCII) |
| Type | Discrete / **bang-bang**, momentary (NOT proportional, NOT an angle) |
| Meaning | `L1` = steer left ON; `L0` = stop steering left; `R1` = steer right ON; `R0` = stop steering right |
| Range/units | None — boolean per direction. No magnitude, no degrees, no normalized value. |
| "Centered" | There is **no explicit center token**. Centered = "not actively steering" = send `L0` and `R0` (i.e. release both). |

Evidence (`RemoV1/public/index.html`):
- Left button: `mousedown → send("L1")` (line 276); `mouseup → send("L0")` (281); `mouseleave → send("L0")` (287); `touchstart → send("L1")` (295); `touchend → send("L0")` (306).
- Right button: `mousedown → send("R1")` (321); `mouseup → send("R0")` (326); `mouseleave → send("R0")` (331); `touchstart → send("R1")` (339); `touchend → send("R0")` (351).

The "hold to steer, release to straighten" behavior is implied: the firmware presumably holds the steer command while `*1` and ceases on `*0`. **The exact actuation (steady GPIO direction vs. timed nudge vs. proportional ramp) is firmware-defined and not visible here.**

### Throttle / Accelerator

| Property | Value |
|---|---|
| Token | `P<n>` where `n` is the integer slider value (e.g. `P42`, `P150`, `P214`) |
| Type | Level / setpoint (integer) |
| Range | `n` ∈ `[42, 214]` (slider `min="42"`, `max="214"`) |
| Units | **Raw firmware counts of unknown scale** — likely a PWM duty (`0..255`, since 214<255) or a servo/ESC value. Cannot be confirmed without the firmware. Do NOT assume m/s. |
| Neutral / stopped | `P42` (slider `value="42"`, the minimum). This is the idle/no-throttle value. |
| Max | `P214` |

Evidence (`RemoV1/public/index.html`):
- Slider definition (lines 145-151):
  ```html
  <input type="range" id="slider" min="42" max="214" value="42">
  ```
- Emit on change (lines 362-372): `slider.addEventListener("input", () => send("P" + slider.value))`.
- The slider is rendered vertical (`writing-mode:bt-lr; -webkit-appearance:slider-vertical`, lines 101-109), bottom = `42` (stop), top = `214` (full).

### Ordering / arm / gear / rate limit

- **None present in this codebase.** There is no arm/enable bit, no gear selector, no required handshake or command ordering, and no rate limiting on the Go side. The server forwards every token immediately (`RemoV1/main.go:88`).
- The slider only fires on `input` (i.e. when the user moves it), so the firmware receives throttle updates only on change, not as a continuous stream.
- ⚠️ Any arming/sequencing/rate-limit requirement would be enforced (if at all) by the **firmware** — verify against the MCU sketch before driving.

---

## 3. ROS 2

- **Is this a ROS 2 system? No.** The `Remo` project does not use ROS in any form:
  - No ROS imports — `RemoV1/main.go` imports only `bufio`, `fmt`, `log`, `net/http`, `gorilla/websocket`, `tarm/serial` (`RemoV1/main.go:3-11`). The full dependency set is just those two third-party modules (`RemoV1/go.sum`).
  - No nodes, no topics, no `.msg`, no launch files, no `package.xml`/`CMakeLists.txt`, no rclcpp/rclpy anywhere in the repo.
- **Distro present on the machine (but unused by Remo):** ROS 2 **Foxy** is installed at `/opt/ros/foxy/` (and `$ROS_DISTRO=foxy` in the environment). Foxy is the JetPack-5/Ubuntu-20.04-era distro. It is simply not wired into this project.
- **Nodes / topics / message types relevant to driving:** none — driving is done over raw serial tokens (§1, §2), not ROS topics.
- **`geometry_msgs/Twist`:** not present anywhere in this project. Nothing consumes Twist; there is no Twist→hardware mapping in this codebase. (If you want a Twist interface, you would have to add it — see §7.)

---

## 4. ENVIRONMENT

**Platform:** NVIDIA Jetson AGX Orin, `aarch64`.

| Item | Value | Source |
|---|---|---|
| L4T / JetPack | **L4T R35.4.1** (= **JetPack 5.1.2**), built 2023-08-01 | `/etc/nv_tegra_release`; `nvidia-l4t-core 35.4.1-20230801124926` |
| Ubuntu base | 20.04 (Focal — matches L4T R35.x / ROS Foxy) | inferred from L4T R35 + Foxy |
| ROS 2 | Foxy installed at `/opt/ros/foxy` (not used by Remo) | `ls /opt/ros`; `$ROS_DISTRO` |
| Go toolchain | **go1.26.4 linux/arm64** | `go version`; `RemoV1/go.mod:3` (`go 1.26.4`) |
| Go deps | `github.com/gorilla/websocket v1.5.3`, `github.com/tarm/serial v0.0.0-20180830185346`, `golang.org/x/sys v0.43.0` (indirect) | `RemoV1/go.mod`, `RemoV1/go.sum` |
| Serial driver | CH340 USB-UART (`1a86:7523`), udev rule grants `gpio` group `0660` | `RemoV1/99-ch340-serial.rules` |

### Camera / video source

- **No application-level camera or streaming pipeline exists in this project.** `Remo` has no GStreamer, no NVENC usage, no WebRTC, no video code at all — it is steering+throttle only. (`RemoV1/main.go` serves static files + WS; `RemoV1/public/index.html` has no `<video>`/`getUserMedia`.)
- **Hardware encode IS available on the platform** for you to build the WebRTC video path on:
  - GStreamer present (`/usr/bin/gst-launch-1.0`) with NVIDIA HW encoders: `nvv4l2h264enc`, `nvv4l2h265enc`, `nvv4l2vp9enc`, `nvv4l2av1enc`, plus `nvv4l2decoder` and `nvv4l2camerasrc` (from `gst-inspect-1.0`).
  - **No camera device was attached at inspection time** (`/dev/video*` absent) — plug in / enable the camera before relying on it. Likewise the serial adapter was not attached at inspection (`/dev/serial/by-id/` empty), so the bridge will `log.Fatal` on start until the CH340/Arduino is connected (`RemoV1/main.go:28-31`).

### Build / run (exact commands)

From `RemoV1/`:
```bash
make build          # → go build -o bin/remo .        (Makefile)
make run            # → go run . $(ARGS)
# or directly:
go run .
go build -o bin/remo . && ./bin/remo
```
- Server listens on **`:8080`** (`RemoV1/main.go:99`), serves `./public` at `/` (`RemoV1/main.go:95`) and WebSocket at `/ws` (`RemoV1/main.go:63`). Open `http://localhost:8080`.
- A prebuilt arm64 binary already exists at `RemoV1/bin/remo`.
- ⚠️ The serial device **must** be present at startup or the process exits (`log.Fatal(err)`, `RemoV1/main.go:30`). Install the udev rule (`99-ch340-serial.rules` → `/etc/udev/rules.d/`) and add the user to the `gpio` group for non-root access.
- Note: `RemoV1/README.md` is a **stale Go-template README** (mentions a nonexistent `internal/greeting` package and a "Hello, world" CLI). Ignore it; the real app is the WS/serial bridge described here.

---

## 5. SAFETY

**Summary: the Go bridge has essentially no safety logic. On loss of input it HOLDS the last command. Plan to add all failsafe behavior in your bridge.**

- **No watchdog, no heartbeat, no timeout, no E-stop, no rate limit** anywhere in `RemoV1/main.go`. The server only forwards bytes.
- **On WebSocket disconnect / browser death:** the handler simply removes the client and closes the socket — it does **NOT** send any stop/neutral command to the serial port:
  ```go
  // RemoV1/main.go:78-84
  _, msg, err := ws.ReadMessage()
  if err != nil {
      delete(clients, ws)
      ws.Close()
      fmt.Println("Browser disconnected")
      break
  }
  ```
  Therefore the **last command persists**: if the browser dies while throttle is `P150` (or while `L1` is held), the MCU keeps receiving nothing new and continues whatever it last latched. **There is no software dead-man here.**
- **Steering during normal use** is self-centering only because the UI sends `L0`/`R0` on `mouseup`/`mouseleave`/`touchend` (`RemoV1/public/index.html:281-351`). A hard disconnect, dropped frame, or crashed tab bypasses these — no `L0`/`R0` is sent.
- **Throttle** has no auto-return; the slider value is only changed by the user dragging it. Nothing forces it back to `P42`.
- **The only possible failsafe is in the MCU firmware** (e.g., a serial-timeout that zeroes outputs). That firmware is not in this repo — **you must verify whether it exists before trusting it.** Assume it does not until proven.

**Implication for ARGUS:** your WebRTC bridge must implement its own heartbeat/watchdog and, on signal loss or operator release, actively send `P42` + `L0` + `R0`. Do not rely on the existing stack to fail safe.

---

## 6. CONCURRENCY

- **Current UI:** a single static **web page** (`RemoV1/public/index.html`) served by the Go binary. It transmits commands over **one WebSocket** to `/ws` as ASCII text (§1).
- **Multiple concurrent clients ARE allowed by the code — the system does NOT assume a single controller:**
  - Clients are tracked in a shared map: `var clients = make(map[*websocket.Conn]bool)` (`RemoV1/main.go:13`); every new connection is added (`clients[ws] = true`, `RemoV1/main.go:73`).
  - Each connection runs its **own** read loop and they **all write to the same `port`** (`RemoV1/main.go:88`). So N browsers can drive simultaneously, **last-writer-wins**, with commands **interleaved** on the serial line.
- **This is a concurrency hazard, not a feature:**
  - `port.Write` is called from multiple goroutines with **no mutex / no serialization** (`RemoV1/main.go:88`). Concurrent writes can interleave bytes within a line and corrupt a token (e.g. `P150\n` + `L1\n` → garbled). `append(msg, '\n')` is per-call but the underlying `Write` is not atomic across goroutines.
  - The `clients` map is also read/written from the broadcast goroutine (`RemoV1/main.go:48-58`) and the per-connection handlers (`73`, `80`) **without a lock** — a classic Go data race on a built-in map (can panic).
- **Device-level exclusivity:** the OS serial device is opened **once** by this single process (`RemoV1/main.go:28`); two *processes* can't both open it cleanly. But *within* the process it is freely shared by all WS clients (above).

**Implication for ARGUS:** if your bridge connects as another WS client alongside a human browser, both will write concurrently with no arbitration. Prefer making the bridge the **sole** controller (close/disallow other clients), or add a mutex + single-owner gate.

---

## 7. INTEGRATION ASSESSMENT

**Feasibility: High and low-effort — but with real caveats around steering fidelity and safety.** The existing stack already exposes a clean text command bus; you reuse it without touching the actuation/firmware layer.

### Recommended seam: connect as a WebSocket client to `/ws`

Have the ARGUS WebRTC→ROS-bridge (or any backend) open `ws://localhost:8080/ws` and send the **same ASCII tokens** the browser sends. This is the path of least resistance:
- Reuses the exact code that already reaches hardware (`RemoV1/main.go:88`) — zero changes to actuation or firmware.
- The server appends `\n` for you; send tokens **without** a trailing newline (`RemoV1/public/index.html:261`).
- You get telemetry back on the same socket for free (`RemoV1/main.go:48-59`).

**Mapping normalized `{steer, throttle}` → existing protocol:**
- `throttle` `0..1` → `P = round(42 + throttle * (214 - 42))` = `round(42 + 172*throttle)`; clamp to `[42,214]`; neutral/stop = `P42`. (If your throttle is `-1..1`, treat ≤0 as `P42`, i.e. no reverse is exposed by this protocol.)
- `steer` `-1..1` → bang-bang with a deadband: `steer > +d → R1` (else `R0`); `steer < -d → L1` (else `L0`). Send the matching `*0` as soon as `|steer|` drops below the deadband.

### Alternative seam: write the serial device directly

Bypass Go and open `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0` @ `115200 8N1` from your bridge, writing `L1\n`/`P150\n`/etc. yourself.
- Pro: removes the unsynchronized multi-client Go layer; you become the single owner.
- Con: only one process can hold the port — you must **stop the `remo` server** first (it `log.Fatal`s if it can't open, `RemoV1/main.go:30`); you re-implement the `\n` framing and lose the built-in telemetry broadcast. Recommended only if you are replacing the Go bridge entirely.

### Blockers & risks (flag before building)

1. **No proportional steering (biggest functional blocker).** The protocol only encodes full-left / full-right / off (`L1/L0/R1/R0`). A smooth analog steering wheel in the cockpit cannot be expressed unless the **MCU firmware** secretly supports a richer command — which is **not in this repo**. Verify the Arduino sketch; if it's truly bang-bang, ARGUS steering will be on/off (mitigate with PWM-style pulsing of `L1/L0`, but that's a hack and firmware-dependent).
2. **Unknown firmware = unknown semantics.** The meaning/scale of `P42..214`, the steering actuation behavior, and any arming/failsafe all live in firmware not present here. **Obtain and read the MCU sketch** before driving for real; don't assume `P` is a clean `0..255` PWM or that any timeout exists.
3. **No failsafe in this layer (safety-critical).** Last command is held on disconnect (§5). Your bridge **must** own a watchdog/heartbeat and actively emit `P42`+`L0`+`R0` on operator release, signal loss, or WebRTC teardown. Do not ship without this.
4. **Multi-writer race (§6).** If the bridge and a human browser are both connected, writes interleave with no lock and can corrupt tokens or panic the map. Make the bridge the exclusive controller, or add serialization. Consider disabling the static UI / `/ws` for browsers when ARGUS is in control.
5. **Startup ordering.** The Go server exits if the serial device is absent at boot (`RemoV1/main.go:30`); `/dev/video*` and `/dev/serial/by-id/` were both empty at inspection — ensure the Arduino (and camera, for video) are enumerated before launch.
6. **No auth / `CheckOrigin` is wide open** (`RemoV1/main.go:16-18` returns `true`). Anyone who can reach `:8080` can drive. Lock this down (bind to localhost, add auth, or firewall) once ARGUS is the front-end.

### Suggested target architecture

```
ARGUS WebRTC cockpit (browser)
   │  DataChannel {steer:-1..1, throttle:0..1} + heartbeat
   ▼
ARGUS bridge on Jetson  (new code — does the mapping + watchdog + single-owner)
   │  ASCII tokens "P<42..214>" / "L1|L0|R1|R0"
   ▼
   ├─ Option A: WS client → existing remo /ws  (reuse main.go:88, no firmware change)   ← recommended first
   └─ Option B: direct serial write (replace remo; you own the port)
   ▼
CH340 USB-serial @115200 8N1  →  Arduino firmware  →  steering + throttle hardware

Video (separate path): nvv4l2camerasrc → nvv4l2h264enc (HW NVENC) → WebRTC  (build new; none exists today)
```

The video path is entirely greenfield — no camera/streaming code exists in `Remo` — but the Jetson has the HW encoders (§4) to build it.

---

### Citation index (primary evidence)
- Serial config / device / baud: `RemoV1/main.go:23-31`
- **Hardware write (steer + throttle):** `RemoV1/main.go:88`
- WS read loop / disconnect handling: `RemoV1/main.go:76-92`
- Serial→clients telemetry broadcast: `RemoV1/main.go:35-61`
- Multi-client map / no lock: `RemoV1/main.go:13, 48-58, 73, 80`
- `/ws`, fileserver, port `:8080`, open CheckOrigin: `RemoV1/main.go:15-19, 63, 95, 99`
- Steering tokens `L1/L0/R1/R0`: `RemoV1/public/index.html:274-353`
- Throttle slider range `42..214`, neutral `42`: `RemoV1/public/index.html:145-151`
- Throttle token `P<value>`: `RemoV1/public/index.html:362-372`
- "Arduino" peer + telemetry log: `RemoV1/public/index.html:238-245`
- CH340 adapter (1a86:7523): `RemoV1/99-ch340-serial.rules`
- Deps (websocket + tarm/serial, no ROS): `RemoV1/go.mod`, `RemoV1/go.sum`
- Env: `/etc/nv_tegra_release` (L4T R35.4.1 / JetPack 5.1.2), `go version` (1.26.4), `/opt/ros/foxy` (present, unused), `gst-inspect-1.0` (NVENC encoders)
