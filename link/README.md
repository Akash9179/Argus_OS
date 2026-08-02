# LINK: the contract

LINK is the language every machine in the system speaks. It defines, precisely and permanently, what the things in our world are (an entity, a track, a task, a zone) and the five messages a machine sends and receives. Any machine that speaks LINK, whether it is a ground vehicle, a drone, a boat, or a fixed camera, can join the force and be commanded from the same map. This package is self-contained: it depends on nothing else in the system, and the system depends on it.

This is version 1 of the contract (`link_version 1`, `ontology_version 1`). Once frozen, it does not change quietly. Any change is a new version, announced and documented, so a machine built against version 1 keeps working.

## The objects

The contract first defines the things the system talks about. These live in `proto/link/v1/ontology.proto`:

- **Entity**: something in the world that is not ours. A person, a car, an animal. It has a durable identity, so seeing the same person twice does not create two people.
- **Observation**: one report from one sensor at one moment: "I saw something, here, and I am this confident about it." Observations are never edited after the fact.
- **Track**: the live, combined picture of one entity, built from many observations. Tracks are what an operator sees on the map, with a position, a direction, a threat level, and a confidence that is always shown honestly.
- **Asset**: one of our machines or sensors, with its status, position, battery, and what it is currently doing.
- **Task**: one unit of work given to one asset, for example "drive to these waypoints", with a full record of who ordered it and every state it passed through.
- **Zone**: a named place on the map that means something, like "Gate 3", optionally with rules such as "alert me when something enters".
- **Mission**: a group of tasks working toward one objective.
- **Relationship**: a recorded connection between any two of the above, like "this vehicle was seen with that person". Over time these connections become the site's accumulated intelligence.

## The five messages

These live in `proto/link/v1/messages.proto`. Direction is relative to the asset.

**HEARTBEAT (asset to platform, about once a second).** The asset's pulse. A short, regular message saying "I am here, I am healthy, my battery is at 87 percent, I am at this position, and this is what I am working on." If heartbeats stop arriving, the platform marks the asset offline and reacts. The heartbeat is how the map always knows which of our machines are alive.

**TELEMETRY (asset to platform, several times a second while moving).** The asset's motion. Position, heading, and speed, sent fast enough that the icon on the map moves smoothly and honestly. Machines with extra instruments, such as a camera gimbal, include those readings here too.

**OBSERVATION (asset to platform, whenever something is seen).** The asset's report about the world. "I detected a possible person, at this location, with 40 percent confidence, and here is a one-line description an operator can read." The platform combines observations from every sensor into tracks. An observation is a permanent record; it is never altered later.

**TASK (platform to asset).** An order. "Drive to these waypoints", "patrol this route", "follow that track", "hold position", "return home." The order carries everything the machine needs to execute it, plus a record of who gave it and how. A machine that receives a task must answer quickly: accepted, or failed with a plain reason. Silence is treated as failure.

**TASK_STATUS (asset to platform, whenever the situation changes).** The asset's answer and running commentary on an order: accepted, underway with 50 percent done and two minutes remaining, completed, or failed and why, in plain words an operator can read directly.

## Rules of the contract

- **Open vocabularies.** Fields like the kind of entity ("person", "vehicle") or the kind of task ("navigate", "patrol") are open lists. A newer machine may send a value an older receiver has never heard of. The receiver must keep and pass on that value, never discard it. This is how the system grows to new domains without breaking anyone.
- **Multi-domain by design.** Nothing in the contract assumes a ground vehicle. Altitude, vertical speed, and hovering exist in the schema from day one. Version 1 implements ground vehicles first; adding an air or sea machine adds new vocabulary values and drivers, never new skeleton.
- **Transport-agnostic.** The contract assumes only that messages eventually arrive and that connections can drop. Version 1 carries these messages over MQTT (topics `{prefix}/{asset_id}/{message_type}` upward and `{prefix}/{asset_id}/task` downward, protobuf-encoded), but the same messages must run unchanged over mesh radio or satellite.
- **IDs and time.** Every identifier is a ULID. Every timestamp is UTC, and appears as an ISO 8601 string in every JSON representation.
- **Honest by construction.** Every observation and track carries a confidence, and the schema requires plain-language, operator-readable text in the places operators will see.

## Layout and code generation

```
proto/link/v1/ontology.proto   the eight world objects and shared types
proto/link/v1/messages.proto   the five wire messages
gen/python/                    generated Python bindings (committed)
gen/ts/                        generated TypeScript bindings (committed)
```

Generated code is the only code: no hand-written parallel definitions anywhere. To regenerate after a schema change (requires `buf`, `protoc`, and `npm install` in this directory):

```
buf lint && buf generate
```
