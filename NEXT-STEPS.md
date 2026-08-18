# Next steps (reconciled roadmap, 18 August 2026)

Prioritized and dependency-aware. Supersedes the 4 August proposal, most of
which either landed (the firmware was obtained, the Jetson was reflashed to
JetPack 6.2 / L4T 36.5 before the 11 August survey) or moved into the plan
and the graph. Target architecture: `ARCHITECTURE.md`. Current truth:
`STATUS.md`. A checkbox here is done only when its acceptance line passes.

The campaign order, once through the blockers: fix the seams, prove the
Jetson, then build the brain. Not the other way around.

---

## Track 0: blocked on the founder, everything else queues behind these

1. ~~Stereolabs email (D-2)~~ **PARKED 18 Aug 2026, founder instruction.**
   Off the critical path; the ZED question reopens only when real
   perception is scheduled. The updated draft context is preserved in the
   D-2 entry in `architecture/graph/decisions.yaml`.
2. ~~Decide the near-term demo (OD-20)~~ **DECIDED 18 Aug 2026: both.**
   Manual remote-control driving AND autonomous waypoint patrol (A to B to
   C to D). Consequence: autonomous outdoor patrol needs a localization
   source on a vehicle that has none attached; with ZED parked, a GNSS/IMU
   receiver is the shortest path and is a purchase decision (item 4).
3. **Gate-2 review of the running C2** (about 30 minutes), and approve or
   hold the Stage 5 remainder (brand pass, event-language pass, offline
   bundle, demo script).
4. **GNSS receiver for ugv-01: deferred by founder choice, 18 Aug 2026.**
   Not needed until the vehicle drives to map waypoints outdoors, so the
   purchase waits. Standing recommendation when the time comes: a u-blox
   ZED-F9P based board (SparkFun GPS-RTK-SMA or Ardusimple simpleRTK2B)
   plus ANN-MB antenna; the ZED SDK's GNSS fusion is documented around
   that chip, and the ZED X's built-in IMU covers the IMU half. Verify
   current price and stock at purchase time.

Update 18 Aug 2026: a **ZED X is ordered and arrives within days, with the
ZED Link GMSL2 capture card and cable confirmed in the order**, so Track 3
has its camera and its connection path. Remaining on arrival: install the
SDK/driver package matching L4T 36.5 (the installed 5.4.1 bundles L4T 35.x
drivers). The D-2 licensing question stays parked per founder instruction.

## Track 1: the hard safety gate (hardware bench, no autonomy before it)

Order matters; every later line builds on the earlier. Wheels off the
ground for all of it. Full context: `ARCHITECTURE.md` section 6 and
`bodies/ugv-01/`.

- [ ] Re-verify the current physical state of ugv-01 before anything (the
      survey describes 11 August; assume nothing survived the gap).
      Acceptance: dated note in `bodies/ugv-01/` recording what was checked.
- [ ] Bench-verify the relay map, one relay at a time, starting with "R5 is
      neutral" because every failsafe builds on it. Acceptance:
      `MCU-PROTOCOL.md` loses its "unverified" marks line by line, each with
      a date.
- [ ] Verify steering feedback, brake relays, and e-stop/ignition wiring
      state; reconnect or record what is physically absent. Acceptance:
      updated FINDINGS with photographs or measurements.
- [ ] Flash and bench-verify the v4 watchdog firmware: link loss latches a
      stop, re-arm is explicit, break-before-make holds on both reversing
      pairs. Acceptance: a written bench protocol executed twice, recorded
      in `bodies/ugv-01/`, and `bodies.ugv01.firmware_v4` promoted to
      `hardware_integrated` in the graph with that evidence.
- [ ] Only after all of the above: powered actuation tests, still wheels-up.

**Nothing autonomous moves on this vehicle until every box above is
checked.** This gate does not expire; re-check before each hardware session.

## Track 2: seam fixes, no hardware needed (the recommended first slice)

The three refactors the alignment ranks above everything else, plus the
debts that keep them honest. All CI-provable on the Mac. Keep behavior
identical while the seams move; the sim loop and pilot criteria stay green
throughout.

1. **Perception stream interfaces (ADR-0003). DONE 18 Aug 2026.**
   - [x] Typed stream seam (`drive/pilot/hal/perception.py`) beside the old
         one; `poll()` survives as a compatibility shim via `streams_of()`.
   - [x] SimulatedCamera declares its detections stream; the registry
         reports every sensor's stream kinds (law 10).
   - [x] SimulatedGnss proves a non-camera, non-Detection sensor through
         the same seam (a GnssSample crosses the HAL, CI-tested).
   - Residual: point cloud/semantic/occupancy sample types are additive
     when a consumer exists; the ROS path into costmaps lands with real
     sensor bring-up.
2. **LocalizationProvider (ADR-0004). DONE 18 Aug 2026.**
   - [x] `PoseEstimate` with uncertainty, source, and health; unknown
         uncertainty stays None rather than an invented number.
   - [x] Fourth driver kind (`drive/pilot/hal/localization.py`); every
         machine gets dead reckoning by default; a manifest swaps the
         provider with no code change (CI-proven); the autonomy core and
         DirectNavigator read position only from the provider.
   - Residual: the ROS locomotion bridge and Nav2Navigator still read
     `pose()`; they migrate during the Jetson bring-up.
3. **Persistent local store (ADR-0005).**
   - [ ] `var/argus_local.db` (SQLite WAL) plus append-only journal;
         WorldSlice reads/writes through it.
   - [ ] Reboot recovery: identity, home, unfinished task, world snapshot,
         journal replay; never auto-resume motion.
   - Acceptance: the reboot acceptance test from ARCHITECTURE.md section 8,
     in CI (kill PILOT mid-task, restart, assert recovered state and no
     motion command emitted without re-validation).
4. **Teleop parity debts (ADR-0009, the parts that need no hardware).**
   - [ ] Structured session logging in the bridge daemon (it has none).
   - [ ] Per-operator identity replacing the single static password.
   - Acceptance: a bridge session can be reconstructed from its log in a
     test; auth tests cover per-operator tokens.
5. **Housekeeping that keeps the above honest.**
   - [ ] Sim capabilities derive from its manifest (closes the
         reverse-modeling gap; behavior changes with no code change).
   - [ ] A versioned LINK conventions document in `link/` recording
         registry-in-telemetry, cancel-as-status, laps-in-extras (risk R-4),
         so the shadow contract becomes discoverable.
   - [ ] Graph and STATUS updated with every step above, same commit.

## Track 3: real Jetson proof (needs Track 1 gate for motion; boot needs only the device)

- [ ] PILOT first boot on the Jetson: containerized runtime against
      simulated drivers, registry on :8200, registered in TRACK over the
      real network. Acceptance: `edge.pilot` promoted to
      `hardware_integrated` with the run recorded.
- [ ] Resolve OD-18 (containers vs host) with evidence from that boot.
- [ ] GNSS/IMU driver behind the LocalizationProvider seam once the
      receiver (Track 0 item 4) arrives; this is the demo's localization
      path. ZED integration is parked with D-2 and reopens when real
      perception is scheduled.
- [ ] Localization bench evaluation (D-1) behind the provider seam, on
      whatever sources exist (GNSS/IMU plus wheel odometry to start).
- [ ] Real locomotion driver from the bench-verified map, and the OD-13
      steering answer (pulsed relays vs firmware change vs different
      controller), written as a driver behind the HAL or an honest ADR that
      the HAL had to bend.
- [ ] Experience recording from the first real runs (MCAP/SVO plus journal).
- Acceptance for the track: one real UGV executes a bounded, safe,
  supervised autonomous task outdoors, disconnection behavior included, and
  survives a mid-task reboot per law 15.

## Then, in order (details in ARCHITECTURE.md section 9 and the report)

Cognitive Runtime v1 deterministic-first (phase 4) -> model evaluation on the
Orin, registry first (phase 5, OD-19) -> memory and prediction (6) ->
Maven-like C2 (7) -> Argus Sync (8) -> learning plane (9) -> fleet
deployment hardening (10) -> Air and Sea (11, only after the universal
boundaries survive real Land hardware).

## Standing discipline

- Update `architecture/graph/` and regenerate `STATUS.md` in the same commit
  as any state change; CI enforces it.
- New open questions become entries in `decisions.yaml`, not assumptions.
- Run the law-auditor after substantive changes; escalation protocol per
  `ARGUS-OS-PLAN.md` section 11 still applies.
