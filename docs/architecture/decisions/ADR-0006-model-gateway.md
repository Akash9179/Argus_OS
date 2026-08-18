# ADR-0006: Capability gateway and model registry

**Status:** accepted (built for language and speech; registry and new
capabilities are direction). **Date:** 2026-08-18 (records the gateway built
3 Aug 2026 and extends it).
**Affected:** `platform.gateway`, `core.cognitive_runtime`.

## Context

The gateway law has been enforced since Stage 4: four capabilities
(transcribe, speak, understand_order, answer_question), adapters registered
on import, policy profiles choosing adapters per capability, sovereignty
enforced per request against each adapter's own `leaves_the_machine`
declaration, `deployed` fail-closed. The alignment requires the same pattern
to carry the cognitive layer, and law 5 of the alignment requires a formal
model approval trail.

## Decision

The existing gateway grows into the Argus Model Gateway rather than being
replaced. Additions, in order of need:

1. **Cognitive capabilities** as they become real: physical scene reasoning,
   mission reasoning, tool calling, memory summarization, embedding, future
   prediction. Capability-by-capability provider defaults; never one
   universal model chosen for convenience (OD-19).
2. **A model registry**: every deployable model records id, provider, family,
   version, origin country, license, weights hash, quantization,
   capabilities, approved profiles, benchmark evidence, and approver. A model
   that fails policy does not load. This makes laws 5, 8, and 9 data instead
   of vigilance, and `MODELS.md` is created when the first entry exists.
3. **Benchmarks on the target.** Candidates (Nemotron, Gemma 4, Phi-4 Mini
   class, Cosmos for physical reasoning) are measured on the actual Orin
   64GB with Argus-specific tasks, latency, memory, power, thermals, and
   structured-output discipline, before anything freezes.

## Alternatives considered

A new ModelGateway beside the existing gateway: two enforcement points for
one law is how violations happen. Direct SDK use inside the cognitive
runtime: already tried by `drive/brain/`, already flagged as the one live
gateway-law violation, now archived.

## Consequences

The unproven `llama_local` path (risk R-6) is exercised end to end before the
cognitive runtime depends on local inference. The known lesson from D-3a
applies to every registry entry: check the backbone, not the badge.
