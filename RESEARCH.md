# Research mapped to Argus architecture decisions

Research is never decoration. For each work we record what problem it solves,
what we take from it, what we deliberately do not assume, and which Argus
component it influences. The machine-readable mapping is
`architecture/graph/research.yaml`; this file carries the reasoning. If newer
primary research materially supersedes an entry, add the new source, explain
the difference, and propose an ADR; do not cargo-cult papers or vendor
architectures.

Sources were adopted 17 to 18 August 2026 from the architecture alignment
report (Appendix B there has the full link list).

## R1. Vesta: A Generalist Embodied Reasoning Model (NVIDIA, 2026)

Generalist embodied reasoning can consolidate localization, navigation,
reasoning, and planning, and a memory harness matters for long-horizon
behavior. We take: one shared cognitive runtime rather than a swarm of
isolated agents, and memory as a first-class component. We do not assume:
that any one generalist model becomes the Argus brain; models stay behind
capability interfaces (laws 4 and 12). Influences: `core.cognitive_runtime`,
`core.memory`.

## R2. MEM: Multi-Scale Embodied Memory for VLA Models (2026)

Short-horizon visual memory and compressed long-horizon semantic memory serve
different purposes. We take: working/sensory, episodic, and semantic memory
are distinct layers, never one prompt buffer. Influences: `core.memory`.

## R3. Do What You Say: Runtime Reasoning-Action Alignment Verification (ICRA 2026)

Correct textual reasoning does not guarantee the emitted physical action
matches the reasoning. We take: an explicit ActionVerifier between planning
and skill execution, which is why law 12 exists as a runtime mechanism and
not a prompt instruction. Influences: `core.action_verifier` (ADR-0007).

## R4. RISE: Self-Improving Robot Policy with Compositional World Model (2026)

World-model imagination supports policy improvement while reducing physical
trials. We take: controlled model-based and offline learning over naive live
self-training (law 13), and experience collection built early so the data
exists when learning starts. Influences: `learning.experience`,
`learning.isaac`.

## R5. VLA-MBPO: Practical World Model-based RL for VLA Models (2026)

Model-based rollouts need multi-view consistency and control of compounding
model error. We take: multi-camera experience represented as one physical
world, confidence on world-model outputs, bounded imagined horizons unless
validated. Predictive models are advisory until proven. Influences:
`learning.isaac`, `core.local_world_model`.

## R6. World-Task Factorization for Robot Learning (2026)

Separating world structure from task-specific logic improves generalization
across heterogeneous robots. This is the strongest external support for the
central Argus bet: one shared world and ontology plus domain skill modules,
instead of separate Land, Air, and Sea brains (law 11, ADR-0002).
Influences: `core.cognitive_runtime`, `core.skills`, all three domains.

## R7. NVIDIA Isaac Sim / Isaac Lab

Use GPU-accelerated simulation and existing RL and imitation tooling; train
and test in simulation, deploy validated outputs. We take: do not build a
custom RL or physics stack before evaluating Isaac. The Jetson runs
inference, not training. Influences: `learning.isaac`.

## R8. NVIDIA Cosmos

The physical-AI foundation-model direction combines physical reasoning,
prediction, and action modeling. We take: Cosmos is a strong provider
candidate for the imagine and physical-reasoning capabilities. We do not
assume: hardwiring to Cosmos, or that NVIDIA branding clears the sovereignty
law; the Alpamayo review (4 Aug 2026) found a Qwen3-VL backbone under an
NVIDIA badge, so the backbone is checked every time (decision D-3a).
Influences: `core.cognitive_runtime`, `platform.gateway`.

## R9. Stereolabs ZED SDK 5 / TERRA

Use existing vision, depth, and spatial-AI capabilities instead of rebuilding
low-level perception. We take: ZED as the eyes behind the Argus perception
interface, replaceable like any provider. We do not assume: air-gapped
licensing works (open decision D-2, unverified with the vendor), or that the
installed SDK matches the flashed kernel (it currently does not). Influences:
`perception.zed`, `core.perception_interface`.

## R10. Palantir Foundry Ontology

Objects, properties, links, actions, and functions as the operating language
of an operational system. We take: the ontology is the shared language
linking perception, reasoning, C2, and actions, not merely a storage schema.
Also the reason the engineering graph exists as a second, separate ontology
about the codebase itself (law 18). Influences: `platform.link`,
`platform.track`, `engineering.graph`.

## R11. Maven Smart System / Palantir defense pattern

Aggregate heterogeneous operational data into one picture, add contextual AI
reasoning, integrate into human workflows with bounded tasking. We take: the
fleet intelligence layer in C2 and TRACK, where natural-language references
resolve against the ontology and actions become typed tasks through the
normal task API. We do not assume: fleet intelligence may ever replace
machine-local autonomy; disconnected machines stay autonomous (law 6).
Influences: `platform.c2`, `platform.track`.
