# Architecture Decision Records

One file per decision that shapes the architecture. ADRs explain why; the
graph (`../graph/decisions.yaml`) tracks what is open and what each decision
touches. A frozen boundary (LINK v1, the HAL seam, a safety gate) is not
changed without reading its ADR and writing a superseding one.

Statuses: `accepted` (in force), `accepted-direction` (in force as target,
implementation not yet started or complete; the graph says how far along),
`superseded` (points at its successor).

| ADR | Title | Status |
|---|---|---|
| 0001 | Edge-first autonomy | accepted |
| 0002 | One cognitive architecture, many bodies | accepted |
| 0003 | Perception stream interfaces | accepted (seam built 18 Aug) |
| 0004 | Localization as a first-class provider | accepted (seam built 18 Aug) |
| 0005 | Persistent local world store | accepted-direction |
| 0006 | Capability gateway and model registry | accepted |
| 0007 | Action verification and the safety governor | accepted-direction |
| 0008 | The Engineering Knowledge Graph | accepted |
| 0009 | Teleop converges onto the HAL | accepted-direction |
| 0010 | Fleet distribution: Ansible first, signed releases later | accepted-direction |
