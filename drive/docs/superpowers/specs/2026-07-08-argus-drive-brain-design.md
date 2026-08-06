# Argus-Drive-Brain — Autonomy ("Soul") Design

**Date:** 2026-07-08
**Status:** Vision / architecture note — DISCUSSION ONLY, pre-spec, pre-implementation
**Owner:** Akash Suryavanshi (Argus)

> This is a captured brainstorming discussion, not an approved implementation
> spec. Nothing here is built or started. Its job is to pin down the vision, the
> architecture, and the decisions we reached, so Phase 1 can be specced cleanly
> when we're ready.

## 1. The vision

Give the Argus vehicle a "soul": a brain that lives on the Jetson AGX Orin, uses
the camera as an eye and the other sensors as its senses, has a personality and
can talk, runs its own pre-flight checks, reports status — and is smart enough
to make decisions. The goal is a true **AGV** (autonomous ground vehicle): tell
it to go from A to B and it finds its own way; when it doesn't know, it reasons
like a brain instead of freezing.

## 2. The core realization: two very different machines

"A talking soul" and "genuine autonomy" sound unified but are different
disciplines with wildly different difficulty:

- **The soul** (personality, talks, sees, pre-flights) — easy, high-delight, a
  layer on top of what already exists. Weeks.
- **Genuine autonomy** (localize, map, plan, avoid obstacles) — the classic
  robotics stack. An LLM is *not* the thing that does the fast "don't hit the
  wall" loop; it's too slow and too unreliable for it. Months.

The design decision that makes the whole project tractable is to **not** treat
this as one brain.

## 3. Architecture: two brains, one spine

```
        ┌───────────────────────────────────────────────────────┐
        │  SOUL  (slow, smart — LLM, ~1 Hz, cloud-escalation ok)  │
        │  • personality, voice in/out                           │
        │  • scene understanding from camera (VLM)               │
        │  • pre-flight checklist + status narration             │
        │  • goal reasoning: decides WHERE to go, decides when    │
        │    stuck, talks to the operator                         │
        │  • persistent memory (routes, past decisions, terrain)  │
        └───────────────┬────────────────────────▲───────────────┘
                 goals / waypoints          "blocked / unsure" escalation
                        ▼                         │
        ┌───────────────────────────────────────────────────────┐
        │  REFLEX  (fast, dumb — local, 10–50 Hz, NO LLM)         │
        │  • localization: fuse GPS + IMU + wheel odometry        │
        │  • planner: route to next waypoint                      │
        │  • obstacle check: ZED X depth / camera → stop/steer    │
        │  • output: /cmd_vel  (same contract teleop uses)        │
        └───────────────────────────┬───────────────────────────┘
                    /cmd_vel  (Twist — the EXISTING teleop contract)
                                     ▼
        ┌───────────────────────────────────────────────────────┐
        │  SPINE  (already built — see teleop design)            │
        │  ROS 2 bridge → actuation → motors ; telemetry back up  │
        └───────────────────────────────────────────────────────┘
```

**Load-bearing rule:** the Soul never sends motor commands directly (except in
Phase 1 as a stepping stone). It sends *goals*. The Reflex layer owns the fast
safety loop and can always override the Soul by stopping. This is what makes it
safe, and it makes "decide when stuck" nearly free — "stuck" is just the Reflex
layer failing to reach a waypoint and escalating upward.

**Reuses the existing contract:** the Reflex layer outputs `/cmd_vel` — the same
`geometry_msgs/Twist` boundary the teleop operator drives through today (see
`2026-06-18-argus-drive-teleop-design.md`). Autonomy is simply a *second
producer* of that contract. No new spine seam is required.

## 4. Sensing

Confirmed / planned suite: **camera(s)** (incl. **ZED X stereo → depth**),
**wheel odometry**, **IMU**, **GPS**, plus full vehicle telemetry (battery,
steering, lights, drive state).

- **GPS + IMU + odometry** is the classic, mature recipe for **outdoor GPS
  waypoint following** fused with dead-reckoning. This makes "go A→B" real
  engineering, not research.
- **ZED X depth** covers the single highest-leverage need for autonomy: "what is
  directly in front of me." This closes the obstacle-avoidance gap that a
  camera-only setup would leave fragile. (If ZED X isn't available at Phase 2, a
  cheaper 2D LiDAR or depth cam is the one hardware add worth making;
  camera-only monocular depth is the weak fallback.)
- **Operating environment: outdoors, open** — plays directly to GPS as the
  localization backbone. (Indoor/mixed is a later, separate localization mode.)

## 5. Phased roadmap

**Phase 0 — Spine (done / in progress).** Teleop stack: cockpit → relay → ROS 2
bridge → actuation. The `/cmd_vel` contract is the seam everything plugs into.

**Phase 1 — The Soul (talks, sees, pre-flights). ~Weeks.**
LLM + VLM on the Jetson. Camera → scene description. Voice in/out → personality.
Pre-flight checklist that polls each subsystem and narrates status. Can also
take *spoken high-level* commands and translate to `/cmd_vel` (human is still
navigator). Delivers the "it talks & sees" moment. Low risk, high delight, and
it forces the clean Soul→spine interface everything else depends on.

**Phase 2 — Local autonomy: A→B. ~Months.**
Build the Reflex layer: localization (fuse GPS/IMU/odometry), waypoint planner,
obstacle avoidance (ZED X depth). Recommended: **adopt ROS 2 Nav2 +
robot_localization** for this layer rather than rolling our own EKF/planner. The
Soul stops sending raw motor commands and starts issuing waypoints/goals.
Delivers "it goes A→B itself."

**Phase 3 — Judgment: decides when stuck. Ongoing, nearly free.**
When the Reflex layer reports blocked / no path / unexpected, it escalates to
the Soul, which reasons ("path blocked, not on my map — try the left corridor,
or ask the operator") and issues a new plan. This is emergent from the two-brain
split, not a separate system. Delivers "it decides when stuck."

## 6. Compute, model, and memory

- **Hardware:** Jetson **AGX Orin (32/64 GB)** — removes the constraint; can run
  a local LLM *and* a local VLM *and* the reflex stack on one box.
- **Model strategy: tiered / hybrid.** A small **local model** (e.g.
  Nemotron-Nano-class or Qwen/Llama small — decide *empirically* on real prompts)
  as the always-alive, offline-safe brain; **escalate to a cloud frontier model**
  (e.g. Claude) when connectivity exists AND the decision is hard. Outdoors, open
  terrain *will* lose signal, so a local tier is mandatory, not optional.
- **On Nemotron specifically:** a fine choice for the local tier — well-optimized
  for the silicon via TensorRT-LLM — but **not a load-bearing decision.** The
  model sits behind a swappable box; pick it by measuring tokens/sec + judgment
  quality on our own prompts, and keep the winner.
- **SSD (being added):** does NOT increase what can *run* (that's the 32/64 GB
  unified memory), but it is **near-mandatory** for local-model work (weights are
  tens of GB each; eMMC/SD is too small/slow) and — more importantly — it is
  where the brain's **persistent memory** lives: a local vector store + logs of
  routes driven, where it got stuck, terrain notes. Memory = experience and
  judgment over time; arguably closer to the "soul" than raw model size. Also
  enables sensor black-box logging → future fine-tuning data on *our* terrain.

## 7. SDK / platform / fleet strategy

Goal is "millions of AGVs," business is **"both, eventually"** — build our own
AGVs first, open the platform to others later.

- **Do NOT build an SDK now.** You can't design good interfaces for a domain you
  haven't lived in. Durable robotics SDKs (ROS included) are *extracted* from
  working systems, never designed up front. A wrong SDK costs more than no SDK.
- **Keep both doors open for free:** build our own AGV as the *first internal
  customer* of our own clean interfaces (the two-brain seams). Clean boundaries:
  yes. Published/versioned/frozen contracts: no — internal APIs must stay free to
  churn as we learn. (This is the AWS/Twilio path: internal services first,
  exposed years later once proven.)
- **The one "millions" investment worth making now = fleet hooks:** per-unit
  identity, OTA updates, phone-home telemetry, remote monitoring/kill-switch.
  Retrofitting these onto deployed units is brutal; bake the hooks in early. Dual
  purpose — needed for our own fleet AND the foundation of any future platform.
- **SDK trigger, not date:** when we (or a design partner) build the *2nd–3rd
  distinct* robot/behavior on the stack, the abstractions have proven themselves
  and extraction becomes cheap and correct. Until then, the SDK is a distraction.

## 8. Decisions reached (this discussion)

1. Split into **two brains + a spine**; Soul commands, Reflex drives, Soul never
   directly actuates (post-Phase-1).
2. **Sequence the vision:** Soul first (Phase 1), autonomy underneath (Phase 2),
   judgment emerges (Phase 3).
3. **Reuse the existing `/cmd_vel` contract** — autonomy is a second producer.
4. **Outdoor GPS waypoint following** is the Phase-2 backbone; **ZED X depth**
   covers obstacle avoidance.
5. **Adopt ROS 2 Nav2** for the Reflex layer; don't roll our own.
6. **Tiered model:** small local (offline-safe) + cloud escalation. Nemotron is a
   fine local-tier candidate; choose empirically; not load-bearing.
7. **SSD** = weights storage + persistent brain memory + logging; not more
   inference capacity.
8. **No SDK now;** clean internal boundaries + fleet hooks now; extract the SDK
   later on the rule-of-three trigger.

## 9. Open questions (for when we move to spec)

- Voice stack: on-device STT/TTS vs cloud? (ties to offline requirement)
- "Smart LLM something" — is the near-term priority a *more capable model* or a
  *memory that learns the environment*? (leaning memory)
- Exact SSD size and what shares it (weights + vector memory + sensor logs).
- Power/thermal budget for continuous local LLM+VLM on a battery vehicle.
- Phase-1 personality scope: how much character vs. pure operational assistant?

## 10. Next step

When ready to start: **spec Phase 1 (the Soul) only** — it is the fast, real win
and it forces every clean interface underneath. This note is the north star it
plugs into.
