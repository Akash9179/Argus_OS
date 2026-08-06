# ARGUS DRIVE - the vehicle-side product

Everything in this folder ships to a vehicle. Nothing else in this repository does.

## What lives here

| Folder | What it is | Runs on |
|---|---|---|
| `pilot/` | The autonomy core: task execution, Nav2 navigation, local world-model slice, HAL (drivers + manifests + registry). Runs containerized (ROS2 Humble). | Jetson (container) |
| `bridge/` | The vehicle daemon: WebRTC video + control/telemetry, serial link to the MCU, watchdog failsafe. Today: the test bridge and mock vehicle; the real daemon grows here. | Jetson |
| `cockpit/` | The operator's driving UI (manual mode). | Operator laptop, NOT the Jetson |
| `brain/` | The LLM layer: judgment, narration, intent. Sits above the control loop. | Jetson or server (TBD) |
| `docs/` | Teleop design spec and Drive design notes. | Nowhere - reference |

## Installing on the Jetson

The Jetson gets ONLY what it needs: `drive/pilot`, `drive/bridge`, and the
`link/` bindings they import. It does not get TRACK, C2, the gateway, voice,
sim, or the cockpit (the cockpit runs on the operator's laptop and connects
to the vehicle over the network).

Recommended: a sparse checkout, so the vehicle never carries server code.

```bash
git clone --filter=blob:none --sparse <repo-url> argus
cd argus
git sparse-checkout set link drive/pilot drive/bridge
```

Then follow `INSTALL.md` section "PILOT on a Jetson" for the container build
(the Dockerfile is at `drive/pilot/docker/Dockerfile`, built from the repo
root). The bridge runs natively; its install steps land here alongside the
real daemon as it is built.

Update on the vehicle = `git pull` inside the sparse checkout. Nothing outside
the three sparse paths ever lands on the machine.

## Rules that bind this folder

- No code above `pilot/hal/` may reference a specific vehicle, sensor, or
  device (HAL law). Machine differences live in drivers and
  `pilot/manifests/*.yaml`.
- `brain/` must reach models through the AI gateway once integrated with the
  OS (gateway law). Its current direct Anthropic SDK use is prototype-only.
- Nothing here may depend on connectivity to function (disconnection law).
  The link adds capability; it never enables basic operation.
- The watchdog is built and tested before the cockpit ever drives real steel.
