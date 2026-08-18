# ADR-0009: Teleop converges onto the HAL

**Status:** accepted-direction (not yet implemented). **Date:** 2026-08-18.
**Affected:** `teleop.bridge`, `teleop.cockpit`, `teleop.watchdog`,
`edge.hal`, `edge.pilot`. Closes risks R-3 and R-8.

## Context

Two parallel vehicle stacks exist: PILOT (HAL, LINK, manifests) and the
teleop bridge (its own VehicleAdapter, its own JSON wire contract, its own
watchdog, its own mock). Both will claim the same serial port on the same
vehicle, the real MCU adapter would otherwise be written twice against an
unverified relay map, and the safety stories would diverge exactly where they
must not. Teleop is also the current demo path while being far below the rest
of the system's security discipline: one static password, no per-operator
identity, zero logging.

## Decision

One real vehicle interface, one safety story, one device owner:

1. **Exactly one process owns physical control devices.** The bridge's
   VehicleAdapter becomes a thin shim over the HAL locomotion driver (plus
   the future control surface), so the real MCU adapter is written once,
   against the bench-verified map, behind the HAL.
2. **One watchdog story.** The bridge's proven STOPPED/DRIVING/LATCHED
   machine and the pre-arm self-test remain the manual-mode safety layer,
   relocated below the shared seam rather than beside it.
3. **Teleop is a permanent capability, not a temporary scaffold.** Manual
   drive remains a first-class fallback and maintenance mode in the target
   architecture (Manual / Assisted / Autonomous in C2).
4. **Security and observability reach parity before the real adapter
   exists**: structured session logging in the daemon (it currently has
   none), per-operator identity instead of one shared password, and no live
   drive control exposed through a public funnel with a static secret.

The cockpit's proven interaction design (gamepad, dead-man, override,
latched stop) is kept; its transport moves to the converged contract.

## Alternatives considered

Port teleop's code into PILOT wholesale: it predates the laws and would
import violations. Keep two stacks and merge later: the merge cost grows
with every commit, and hardware attention is currently flowing to the
non-architectural stack.

## Consequences

The mock bridge remains the only safe actuation-shaped thing to run on a
vehicle checkout (CLAUDE.md rule zero). Sequencing note: the shim depends on
a real locomotion driver existing, which depends on the bench-verified relay
map (the section 6 safety gate), so logging and identity work can start now
while the seam work waits for the gate.
