# ADR-0007: Action verification and the safety governor

**Status:** accepted-direction (not yet implemented). **Date:** 2026-08-18.
**Affected:** `core.action_verifier`, `core.safety_governor`, `core.skills`.
Implements law 12; informed by R3 (Do What You Say, ICRA 2026).

## Context

Runtime research confirms what the safety hierarchy already implies: correct
reasoning does not guarantee a matching action. Today no model is in any
acting loop (voice requires a structural readback confirmation; the brain
prototype's bounded nudge is archived), so law 12 is true by absence. The
cognitive runtime ends that by construction, so the enforcement must move
from absence to mechanism before any model proposes actions.

## Decision

Two distinct layers, both deterministic:

1. **ActionVerifier**: before any physical skill executes, verify the
   proposed action matches the stated plan, the skill is available on this
   machine, parameters are within manifest limits, the ontology and mission
   permit the action, and current world state has not invalidated the plan's
   assumptions. Rejection routes to replan, operator review, or contingency;
   never to silent execution, and every verdict is recorded (law 16).
2. **Safety governor**: the deterministic gate below all reasoning, above the
   domain controllers, itself below the domain safety controller, the safety
   MCU watchdog, and human emergency controls. Higher intelligence can never
   bypass a lower layer.

The safety hierarchy, top intelligence to bottom authority: reasoning and
planner, skill executor, Argus safety governor, domain safety controller,
safety MCU / low-level watchdog, human emergency controls.

## Alternatives considered

Prompt-level guardrails: not deterministic, not auditable, and exactly what
R3 shows failing. One combined verifier-governor: mixes "is this action
coherent" with "is this action permitted", which age at different rates.

## Consequences

The bad-model-action acceptance test becomes implementable. Voice's readback
rule remains, unchanged, as the human-facing instance of the same principle.
The MCU-level end of the hierarchy is gated by the bench work in
ARCHITECTURE.md section 6; no governor in software compensates for firmware
that latches throttle on link loss.
