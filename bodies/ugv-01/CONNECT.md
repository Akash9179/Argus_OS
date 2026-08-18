# Connecting to ugv-01 - what to bring to the Jetson

Written 2026-08-11 from repo state `1f3a4f4`. This is the card you carry to
the vehicle: what is actually installable today, the exact commands, and every
address, port and secret needed to make a link.

## Honest readiness

| Piece | State on the Jetson today |
|---|---|
| **Survey brief** (`SURVEY.md`) | **Ready.** Read-only; run it first. |
| **Bridge daemon** (`drive/bridge`) | **Installable, mock only.** Pure stdlib, runs on stock python3. `--vehicle` accepts `mock` and nothing else - there is no adapter that can talk to this vehicle's MCU yet. Good for proving network + cockpit link. **It cannot drive the UGV.** |
| **PILOT** (`drive/pilot`) | Installable in a container, but the Dockerfile is `ros:humble-ros-base` - no CUDA, no TensorRT. Simulated drivers only (Stage 3A). Don't expect real sensors or real locomotion. |
| **Cockpit** | Runs on the operator laptop, never on the Jetson. |

**The real vehicle adapter is written from the survey, not before it.** That
is why session one on the Jetson is a survey and not an install.

## 1. Get the code onto the Jetson

The repo is **private** (`github.com/Akash9179/Argus_OS`), so the Jetson needs
credentials: `gh auth login` (device flow, easiest), a PAT, or a deploy key.

```bash
# Sparse: the vehicle carries only what it needs
git clone --filter=blob:none --sparse https://github.com/Akash9179/Argus_OS.git argus
cd argus
git sparse-checkout set link drive/pilot drive/bridge bodies/ugv-01
```

`bodies/ugv-01` is included on purpose - the survey brief and this file live
there, and the findings get committed back from the Jetson.

If the Jetson has no network at all: clone on the laptop, copy over USB, and
plan to commit locally and carry the branch back.

## 2. Session one: the survey (read-only, do this first)

On the Jetson, run `claude` from inside the `argus` directory and paste this:

```
Read bodies/ugv-01/SURVEY.md and do the hardware survey it describes.
Rule zero applies: this machine can move, so run nothing that could
actuate. Write your findings into bodies/ugv-01/FINDINGS.md, tick the
checklist in bodies/ugv-01/README.md, then commit on branch survey/ugv-01
and push. The ZED camera is not connected right now, so record what IS
here instead. Do not build or install anything this session.
```

Findings go in `FINDINGS.md` (skeleton already there, one section per survey
step), checklist in `README.md`, branch `survey/ugv-01`.

The one thing that matters most: **the MCU firmware source and its serial
command set.** If it is not on the Jetson, say so loudly rather than guessing
from the stale `ARGUS_INTEGRATION_NOTES.md`.

## 3. Optional bench test: mock bridge on the Jetson, cockpit on the laptop

Proves the network path and the cockpit link with the wheels never involved
(the mock vehicle is software; the real MCU is untouched).

On the Jetson:
```bash
cd argus
python3 -m drive.bridge                                      # listens 0.0.0.0:8090
```
First run creates `var/bridge_operators.json` with one starter operator;
read the token out of that file (or add a line per person). The old
`ARGUS_PASSWORD` shared secret is gone (ADR-0009). Sessions log to
`var/bridge_sessions.jsonl`. Add `--port N` / `--watchdog-ms N` if needed. Do **not** pass `--report` on the
Jetson: it needs paho-mqtt and a reachable broker, which is a laptop-side
concern.

On the laptop, cockpit dev server on :5174:
```
http://localhost:5174/?bridge=<jetson-ip>:8090&key=<your-operator-token>
```
Or through the C2 shell's Drive app if the shell is running on :5180.

What you should see: cockpit connects, ignition triggers the pre-arm
SELF-TEST, green light gates arming, telemetry streams into the HUD, and
pulling the network latches the vehicle stopped until you explicitly re-arm.

## 4. Addresses, ports, secrets

| Thing | Value |
|---|---|
| Bridge WebSocket | `ws://<jetson-ip>:8090` (auth-first frame: `{"t":"auth","token":...}`; `password` key also accepted for the cockpit) |
| Bridge operators | `var/bridge_operators.json` on the machine, one token per person (18 Aug 2026: replaced the shared `ARGUS_PASSWORD`) |
| Cockpit dev server | laptop `:5174`, param `?bridge=host:port&key=...` |
| C2 shell dev server | laptop `:5180` (proxies `/v1`) |
| TRACK | laptop `:8100` |
| MQTT broker | laptop `:1883` (mosquitto) - only for `--report`/PILOT |
| PILOT registry | `localhost:8200/registry` on the machine |
| Operator laptop LAN IP | `192.168.1.164` (verify - DHCP) |
| Repo | `https://github.com/Akash9179/Argus_OS.git`, branch `main`, **private** |

**Network:** Jetson and laptop on the same LAN is the simple path. Tailscale is
installed on the laptop but currently stopped - start it on both ends if the
vehicle is off-LAN. Cloudflared quick tunnels are laptop-side only and are not
wired for the Drive bridge yet.

**Firewall:** the bridge binds `0.0.0.0`; if the cockpit can't reach it, check
the Jetson's ufw rules for 8090 before suspecting the code.

## 5. What comes back from the vehicle

1. Branch `survey/ugv-01` with `FINDINGS.md` written and the `README.md` checklist ticked.
2. The MCU serial protocol, in full, or a clear statement of where it lives.
3. A yes/no on whether the mock-bridge bench test linked over the real network.

From that: the real `VehicleAdapter` in `drive/bridge/vehicle.py`, the point-A-to-B
autonomy decision for the demo, and the ZED integration path.
