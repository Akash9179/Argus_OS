# Argus Drive — Teleoperation System Design

**Date:** 2026-06-18
**Status:** Approved design, pre-implementation
**Owner:** Akash Suryavanshi (Argus)

## 1. Purpose

Argus Drive is the remote teleoperation system for the Argus UGV. It lets an
operator drive the vehicle in real time, with a polished cockpit UI, from
anywhere on the internet (for example from the US while the vehicle is in
India). The vehicle is built on an NVIDIA Jetson AGX Orin running ROS 2.

This spec covers the **teleop transport and the operator UI only**. It is built
"contract-first" against a defined command and telemetry boundary, so it does
not depend on the vehicle's motor wiring, which does not exist yet. When the
actuation layer is built later, it plugs in underneath the same contract.

## 2. Scope

### In scope
- Operator cockpit UI (browser based, custom, design-led).
- WebRTC transport: video plus a control and telemetry DataChannel.
- ROS 2 bridge node on the AGX.
- Safety watchdog (loss-of-link failsafe).
- A `dummy_vehicle` stand-in so the whole stack runs with no hardware.
- Network access via Tailscale (Phase 0 and 1).
- Full design (build later) of the ZED X perception layer.

### Out of scope (separate, later efforts)
- The actuation / drive-by-wire layer (AGX to motor controllers, steering).
- Physical hardware E-stop and motor-controller integration.
- Autonomy / self-driving. This is human teleoperation only.

## 3. Constraints and key facts

- **Latency:** US to India round trip is ~200 to 400 ms. The operator is always
  "driving in the past." This drives every design choice: lowest-latency
  transport, prominent latency display, conservative speed limits, and a
  loss-of-link failsafe.
- **Connectivity:** Workshop WiFi now; cellular dongle in the field later
  (carrier-grade NAT, packet loss, variable latency).
- **Cost:** Everything is free and open-source. The only real costs are the
  cellular data plan and (later) the ZED X camera plus its GMSL2 capture card.
- **Access control:** Tailscale network gating only for now (single private
  operator). App-level auth is a later addition for the public cellular path.

## 4. The contract (decoupling boundary)

Everything above the bridge speaks one small contract, so the hardware below can
change freely. The `dummy_vehicle` now, and the real actuation layer later, both
implement this same contract.

### 4.1 Command (operator to vehicle)
- **Primary drive:** `geometry_msgs/Twist` on `/cmd_vel` (topic configurable).
  The browser sends normalized `{ steer, throttle, brake }` each in -1..1; the
  bridge maps to `linear.x` and `angular.z` using configurable max-speed limits.
- **Gear / direction:** Forward, Neutral, Reverse.
- **Auxiliary commands:** blinkers (left / right / hazard), headlights / work
  lights, horn, drive mode (slow / normal speed cap).
- **Safety commands:** arm / disarm (re-arm after a safety stop), E-stop.
- Every command frame carries a monotonic `seq` and a `heartbeat` timestamp.

### 4.2 Telemetry (vehicle to operator)
- Current speed, gear state (F/N/R), battery percentage and estimated runtime.
- Steering angle, drive mode, confirmed light / blinker / horn state.
- System temperatures (Jetson and, later, motor controllers).
- Fault / warning messages.
- Armed / disarmed and safety state (DRIVING / STOPPED / LATCHED).
- (Perception phase) the derived ZED X fields in section 8.

Telemetry is bundled into one small JSON message published a few times per
second over the DataChannel.

## 5. Architecture

```
   OPERATOR SIDE (US)                          VEHICLE SIDE (AGX Orin, India)
┌──────────────────────────┐                ┌────────────────────────────────────┐
│  Browser cockpit (React)  │                │  argus_teleop_bridge (ROS 2, Python) │
│  ┌─────────────────────┐  │   WebRTC       │  ┌────────────────────────────────┐ │
│  │ Video + overlays    │◀─┼─ video track ──┼──│ NVENC encode ← video source     │ │
│  │ HUD / telemetry     │◀─┼─ DataChannel ──┼──│ telemetry ← ROS topics          │ │
│  │ Input layer (DS5/kb)│──┼─ DataChannel ──┼─▶│ cmd → publish Twist + aux topics │ │
│  └─────────────────────┘  │  (one peer     │  │ heartbeat handling              │ │
│                           │   connection)  │  └────────────────────────────────┘ │
└──────────────────────────┘                │     │ /cmd_vel, aux   ▲ telemetry     │
            ▲                                │     ▼                 │               │
   ┌────────┴─────────┐                      │  ┌────────────────────────────────┐  │
   │ signaling (WS)   │  ← on AGX            │  │ argus_safety_watchdog (separate) │ │
   └──────────────────┘                      │  └────────────────────────────────┘  │
                                             │     │                                 │
   all traffic over Tailscale (Phase 0/1)    │  ┌────────────────────────────────┐  │
   TURN relay added for cellular (Phase 2)   │  │ STAND-IN: dummy_vehicle node     │ │
                                             │  │ LATER: real actuation layer      │ │
                                             │  └────────────────────────────────┘  │
                                             └────────────────────────────────────┘
```

### 5.1 Components (each isolated, single-purpose, independently testable)

**On the AGX (Python ROS 2 package `argus_teleop_bridge`):**

1. **WebRTC bridge node** — owns the single `aiortc` peer connection. Adds the
   video track, owns the control and telemetry DataChannels, and translates
   between DataChannel messages and ROS topics. Depends on ROS topics plus a
   video source. Interface: WebRTC offer/answer and JSON DataChannel messages.

2. **Video source** — an abstraction with one job: "give me encoded frames."
   Backed by GStreamer with NVENC hardware encode. Pluggable: USB webcam now,
   ZED X left rectified image later. The bridge never knows which camera it is.

3. **Safety watchdog node** (`argus_safety_watchdog`) — independent of the
   bridge. Subscribes to the command stream and heartbeat. If no valid command
   or heartbeat arrives within the timeout (default 300 ms), it publishes a
   zero-velocity `Twist` and latches a STOPPED state until explicitly re-armed.
   It is a separate process so it keeps protecting the vehicle even if the
   bridge crashes.

4. **Signaling server** — a minimal WebSocket service for the one-time WebRTC
   handshake. Runs on the AGX, reachable over Tailscale.

5. **`dummy_vehicle` node** — test stand-in. Subscribes `/cmd_vel` and the aux
   topics, publishes believable telemetry (speed integrates from commands,
   battery drains slowly, etc.). Swapped for the real actuation layer later
   behind the same contract.

**On the operator side (browser, React SPA):**

6. **Connection manager** — establishes the WebRTC session via signaling,
   manages reconnect, exposes connection state and measured RTT.

7. **Input layer** — normalizes DualSense / keyboard / wheel into one
   `{ steer, throttle, brake, gear, aux }` shape and sends it over the control
   DataChannel at a fixed rate (target 20 to 50 Hz) with `seq` and heartbeat.

8. **HUD and overlay components** — video layer, telemetry HUD, perception
   overlays, and the disconnect takeover. See section 7.

## 6. Data flow and safety behavior

### 6.1 The three flows
- **Driving loop:** input read ~30 Hz in the browser, normalized to `steer` and
  `throttle` plus `seq` and heartbeat, sent over the control DataChannel. The
  bridge applies speed limits and publishes `Twist` on `/cmd_vel`.
- **Video:** camera frames hardware-encoded (NVENC) on the AGX, streamed back
  over WebRTC (UDP), so packet loss degrades gracefully instead of freezing.
- **Telemetry:** ROS topics bundled into a small status message, sent back over
  the DataChannel to drive the gauges and overlays.

### 6.2 Safety model

Rule: **if the vehicle is unsure whether the operator is in control, it stops.**

| Situation | Behavior | Reason |
|---|---|---|
| No command/heartbeat for ~300 ms | Watchdog publishes zero velocity; vehicle stops | A dropped link must never mean "keep going" |
| Connection fully drops | Same stop, plus the UI shows a full red LINK LOST takeover | Operator instantly knows they are not in control |
| Operator releases controls | Throttle returns to 0; vehicle stops | Normal driving |
| After any safety stop | Vehicle stays LATCHED/stopped until the operator deliberately re-arms | Never silently lurch back to life when the link returns mid-motion |
| Emergency stop | Dedicated E-STOP button (and controller button); immediate latched stop | One obvious "make it stop NOW" |
| Speed limit | Bridge caps max speed via config; start low for first drives | First teleop should crawl, not sprint |

Design choices and rationale:
- The watchdog is a separate node from the bridge, so safety does not depend on
  the most complex (most failure-prone) component.
- Latched-stop plus manual re-arm makes recovery a deliberate human action.
  This is standard practice for real teleoperated robots and is retained even
  though it is slightly less convenient.

Limitation to revisit in the actuation phase: this software watchdog protects
against network and software failures only. It does not replace a physical
hardware E-stop (a real cutoff relay), which should be added when the motors are
wired.

## 7. Operator cockpit UI

**Visual direction:** a dark cockpit canvas (keeps the video dominant and the
operator's eyes adjusted for low-light field footage), one restrained warm
accent in the Argus brand gold `#feda81` reserved for live/active states and
alerts, and a clean geometric sans. Apple/Airbnb-grade restraint: the video is
the hero; instruments sit at the edges; nothing decorative competes with the
drive.

Because the UI is the most design-critical deliverable, it gets a dedicated
design exploration (real references: cockpit/telemetry HUDs, Linear-grade dark
UIs) before implementation, rather than going straight to code.

**Layout (full-screen, video-first):**
```
┌─────────────────────────────────────────────────────────────┐
│ ◉ LINK 142ms  ▮▮▮▯ good     ARMED        ⏺ REC      ⏻ E-STOP │
│            [ full-bleed left-camera video ]                    │
│        ┌───────┐                          person 3.2m          │
│        │ tilt  │   (object boxes + distance drawn on video)    │
│        │ 4° ◣  │                                                │
│        └───────┘                  ⚠ OBSTACLE 1.2m              │
│   ┌──────────┐        ╭─ proximity ring ─╮         ┌─────────┐ │
│   │ ◀ F N R ▶│        │ top-down nearby   │         │  18 km/h│ │
│   │ gear     │        │ objects           │         │  speed  │ │
│   └──────────┘        ╰───────────────────╯         └─────────┘ │
│  🔆lights ⇇blinker ⇉  📢horn   mode: SLOW   🔋 82%  · 41min     │
└─────────────────────────────────────────────────────────────┘
```

**Zones (each an isolated component):**
- **Top strip:** link latency and quality (the single most important number),
  arm/disarm state, record indicator, always-visible E-STOP. Turns red and takes
  over on link loss.
- **Video layer:** the camera feed, with perception overlays drawn on top as
  separate toggleable layers.
- **Bottom HUD:** gear (F/N/R), speed, battery % and estimated runtime, drive
  mode, and light/blinker/horn controls showing their confirmed state (lit only
  when the vehicle reports them actually on).
- **Left/right edges:** tilt/attitude indicator and the top-down proximity ring
  (both perception phase).
- **Disconnect takeover:** full red overlay the instant the link drops, so a
  frozen frame can never be mistaken for a live one.

**Input mapping (DualSense primary):** left stick steer, R2 throttle, L2 brake,
D-pad blinkers, face buttons for gear/horn/lights, a deliberate two-button combo
to re-arm. Keyboard fallback; wheel-ready. All normalized before transmission.

## 8. ZED X perception layer (designed now, built later)

The ZED X is a GMSL2 stereo camera with a global shutter, a built-in IMU, a
neural depth engine, and the ZED SDK, exposed to ROS 2 through
`zed_ros2_wrapper`. Hardware prerequisite: the ZED X needs a **GMSL2 capture
card** (Stereolabs ZED Link or ZED Box) plus the ZED SDK and CUDA on JetPack;
budget for the capture card in addition to the ~$599 camera.

### 8.1 Key architectural decision
All heavy perception runs **on the AGX, on the vehicle**. We do NOT stream point
clouds or depth maps across the ocean. The AGX computes everything locally and
sends only small derived numbers over the existing telemetry DataChannel (a few
hundred bytes). The UI draws overlays from those numbers. This means the
perception layer only **adds telemetry fields** to the contract in section 4; it
changes nothing about the transport or UI architecture.

### 8.2 Capabilities mapped to UI features

| ZED SDK capability | ROS source | Cockpit UI feature | Derived telemetry sent |
|---|---|---|---|
| Left rectified image | `sensor_msgs/Image` | Main driving video (replaces webcam) | (video track, not data) |
| Neural depth | depth image | Collision warning + distance-to-obstacle readout | nearest-obstacle distance, bearing |
| Depth to laserscan | `sensor_msgs/LaserScan` (example node) | Top-down proximity ring around the vehicle | compact range array (downsampled) |
| AI object detection | `zed_msgs` detected objects | Bounding boxes on people/vehicles over video, with distance | list of {class, bbox, distance, bearing} |
| Visual-inertial odometry (SLAM) | `nav_msgs/Odometry`, `PoseStamped` | True speed, heading, and a live mini-map / breadcrumb trail (no GPS needed) | x, y, heading, velocity |
| IMU (accel + gyro) | `sensor_msgs/Imu` | Tilt / attitude indicator (pitch and roll), rollover awareness | pitch, roll |
| GNSS fusion (when GPS added) | `NavSatFix` fused | Geo-position on a real map | lat, lon, fix quality |
| SVO recording | start/stop services | One-click record-the-drive | recording state |

### 8.3 Resource note
Depth, object detection, and odometry use the AGX GPU and add heat and a little
latency. The bridge stays the main video at the left rectified image; the
depth-colored view is an optional, bandwidth-heavy toggle, not the default.

## 9. Tech stack (all free / open-source)

- **Operator UI:** React + Vite + TypeScript + Tailwind. Single-page cockpit
  app, runs in the browser, served locally or from the AGX. Lightweight state
  store; browser WebRTC and Gamepad APIs.
- **AGX bridge:** Python ROS 2 package (`rclpy` + `aiortc`) for the WebRTC peer,
  DataChannels, and ROS bridging. Video uses NVENC hardware encode via
  GStreamer. This is the one real technical risk and is de-risked first (see
  section 11).
- **Network:** Tailscale now; `coturn` plus a tiny signaling service added for
  the cellular phase.
- **ROS 2 distro:** target Humble (Ubuntu 22.04 / JetPack 6); to be confirmed by
  inspecting the AGX over SSH. The ZED SDK 5.x supports Humble and Jazzy.

## 10. Testing strategy

- `dummy_vehicle` node stands in for the real UGV (consumes `/cmd_vel` and aux,
  emits believable telemetry), so the whole stack runs with zero hardware.
- Unit tests on pure logic: input normalization, command mapping, and especially
  the watchdog timeout behavior.
- Loopback integration test: browser → bridge → dummy → back.
- **Latency injection:** artificially add 250 ms+ delay during testing to
  validate the safety stops and UI feel under realistic US↔India lag before any
  real drive.
- **Mock vehicle for UI:** a browser-local (or tiny local server) mock emitting
  the contract's telemetry shape plus a placeholder video loop, so the cockpit
  UI can be built and iterated with zero backend, zero ROS, zero hardware.

## 11. Phasing and sequencing

Because the build is contract-first and the UI is the most design-critical
piece, implementation leads with the UI against the mock contract.

- **Phase 0 (this build):**
  1. NVENC hardware-video spike (de-risk the one hard part early).
  2. Define the contract types (command and telemetry shapes).
  3. UI design exploration, then build the cockpit against the mock vehicle.
  4. WebRTC bridge + `dummy_vehicle` + safety watchdog.
  5. Drive the simulated vehicle over Tailscale, US to India.
- **Phase 1:** deploy the bridge to the AGX; drive the real vehicle over
  workshop WiFi once the actuation layer exists.
- **Phase 2:** cellular field link (TURN + signaling) and the ZED X perception
  layer.

## 12. Open questions / to confirm later

- AGX environment: JetPack version, ROS 2 distro, existing packages (confirm via
  SSH before Phase 1).
- Exact `/cmd_vel` mapping and max-speed limits for the real vehicle (set during
  the actuation phase).
- Whether the cockpit UI is served locally on the operator machine or hosted on
  the AGX over Tailscale.

## 13. Risks

- **Hardware-accelerated WebRTC video** is the main technical unknown; spike it
  first.
- **Intercontinental latency** is a physical limit; mitigated by transport
  choice, conservative speed, the latency meter, and the failsafe, not removed.
- **Cellular reliability** in the field; mitigated by the loss-of-link failsafe
  and the Phase 2 TURN relay.
