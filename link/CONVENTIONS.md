# LINK conventions registry

**Conventions version 1.0, 18 August 2026.** Contract: `link_version 1`,
`ontology_version 1`.

The frozen contract has deliberate open spots: `Telemetry.payload`,
`TaskParameters.extras`, `Asset.capabilities`, and every open vocabulary.
Anything that rides in them is real protocol the moment two parties rely
on it, whether or not the protos can show it. This file is where those
conventions become discoverable: a partner implementing LINK reads the
protos for the skeleton and this file for the conventions, and needs no
access to our Python to interoperate (closes risk R-4).

Rules of this registry:

- A new convention lands here **in the same change** that ships it.
  Code relying on an unrecorded convention is the bug this file exists
  to prevent.
- Entries are append-and-amend with dates, never silently rewritten.
  Retiring a convention means marking it retired here, with the version
  that absorbed it.
- A convention that proves stable is a candidate for promotion into
  contract v2 as typed fields. Promotion is a contract change and needs
  the full version discipline (see README).
- Receivers treat every convention as optional: a message without it is
  valid v1. Unknown payload keys, extras keys, and capability keys are
  kept and passed on, never dropped (the open-vocabulary rule).

## 1. Registry-in-telemetry

Decision D-8 (2026-08-03).

A machine's self-description rides upward in `Telemetry.payload` under
the key `"registry"`. Sent when it changes and after a reconnect, not at
telemetry rate. The value is the machine's hardware registry snapshot:
installed drivers and versions, detected devices, driver health, applied
configuration, and the key `"manifest"` holding the machine's capability
declaration (see section 4).

The platform accumulates payloads per asset: each arriving payload is
merged over what the machine sent before, so a key present in an earlier
payload survives a later payload that omits it (machines send different
extras at different rates, and the registry only on change). The same
rule applies when `registry["manifest"]` is merged into
`Asset.capabilities`: keys absent from a newer manifest are kept, not
cleared. A producer that needs a key gone must send it with an explicit
empty value. Keys the platform does not recognize are stored and served,
never dropped, so a newer machine's registry survives an older server.

Reserved key: the platform adds `"received_at"` (its receive time) when
serving a stored payload back out. A machine should not use that key for
its own data.

```json
Telemetry.payload = {
  "registry": {
    "manifest": {"name": "UGV-7", "supported_task_types": "navigate, hold"},
    "drivers": [{"kind": "locomotion", "name": "mcu_v4", "healthy": true}]
  }
}
```

## 2. Cancel-as-status

Decision D-9 (2026-08-02).

The contract has no cancel message. Cancellation is a `TaskAssignment`
whose `task.status` is `TASK_STATE_CANCELLED` and whose `task.task_id`
names the task to cancel. A machine receiving one for its current task
stops executing it and reports `TASK_STATE_CANCELLED` back through
TASK_STATUS; for a task it does not hold, it does nothing. A machine
never treats a cancellation as a new order to accept.

## 3. Laps-in-extras

For `task_type: "patrol"`, the number of laps rides in
`TaskParameters.extras` under the key `"laps"` as a JSON number. The
machine clamps it to at least 1. Absent, or present as anything other
than a number, means the machine's own default (1 in current
implementations); a malformed value is not an error, the order still
runs. A patrol route closes itself: the machine returns to the first
waypoint at the end of each lap.

```json
TaskParameters.extras = {"laps": 3}
```

## 4. Capability declaration keys

`Asset.capabilities` is an open struct filled from the machine's own
manifest (see section 1 for how it travels). Keys with agreed meaning:

- `"name"` (string): what to call this machine on screen. The machine is
  the only naming authority; nothing downstream composes a name.
- `"supported_task_types"` (string): comma-joined task types, for
  example `"navigate, patrol, hold, return_home"`. The platform's
  autonomy refuses to route a task type not in this list; a machine with
  no declaration is assumed capable (the machine still refuses in words
  what it cannot do).
- `"sensors"` (string): comma-joined sensor driver names.
- Numeric constraint keys as declared by the manifest
  (`max_speed_mps`, `max_turn_rate_dps`, `min_turn_radius_m`, ...).

Comma-joined strings, not JSON arrays, because that is what shipped
first; a v2 would type these properly. Producers join with `", "`;
consumers must split on `","` and strip whitespace.

## 5. Provisional entity identity

Open decision OD-21; recorded here because both sides already rely on it.

`Observation.entity_id` assigned by an asset is a locally generated ULID
and is **provisional**: nothing on the wire marks it as such. By
convention the platform treats asset-assigned identities as provisional
and resolves them against the fused picture (alias mapping, original
observations never rewritten). Nothing should treat an asset-assigned
`entity_id` as durable across machines until OD-21 is decided.
