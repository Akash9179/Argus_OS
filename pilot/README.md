# ARGUS PILOT: the edge runtime

One program that runs on every machine.

What differs between machines lives in two places and nowhere else: a
capability manifest, and an implementation of one of three driver
interfaces. Nothing above the hardware abstraction layer knows what kind of
machine it is running on. That is the HAL law, and it is the reason this
package is shaped the way it is.

## What is here

```
pilot/
  hal/                 the hardware abstraction layer
    interfaces.py      three driver protocols: locomotion, sensor, comms
    manifest.py        what one machine is, as a YAML file
    registry.py        what the HAL knows, as queryable structured data
    loader.py          manifest names a driver; this builds it
    drivers/
      simulated.py     a driver set with no hardware behind it
      mqtt.py          the version 1 comms driver
  autonomy/            the part that is the same on every machine
    core.py            take an order, plan it, drive it, report it
    navigator.py       the Navigator protocol and the direct implementation
    nav2.py            the same protocol, backed by Nav2
    worldslice.py      what this machine knows without asking anyone
  ros/                 everything that needs ROS2, and nothing that does not
    bridge.py          /cmd_vel <-> the locomotion driver
  link_client.py       the five contract messages
  runtime.py           boot one machine from its manifest
  manifests/           the machines
```

## The three seams

**The driver interfaces** are the seam between the runtime and the
hardware. Stage 3A ships a simulated set; Stage 3B writes the real ones
next to them. If porting to a new machine ever needs more than a manifest
and drivers, the HAL has failed and the fix belongs below this line, not
above it.

**The Navigator protocol** is the seam between the autonomy core and
whoever plans routes. `DirectNavigator` plans them itself.
`Nav2Navigator` hands them to Nav2. The core cannot tell which it has, so
choosing a planner is configuration rather than architecture.

**The comms driver** is the seam between the machine and the platform.
The autonomy core never asks whether the link is up before deciding what
to do, because under the disconnection law the answer would not change its
behaviour. Observations queue while the link is down and go out when it
returns; heartbeats and telemetry describe now, so they are simply not
sent.

## Two things that are not obvious

**The registry travels in `Telemetry.payload`.** The contract is frozen at
version 1 and has no message for a capability manifest or a driver
registry, and reopening it for this would have been the wrong trade.
`Telemetry.payload` is the contract's own documented extension point for
per-manifest extras, so the registry snapshot goes there under the key
`registry`, only when it changes and when the link returns. This is a
convention chosen during Stage 3A, not something the plan specified. It is
recorded as decision 8 in the plan's open decisions so that it gets
reviewed rather than inherited.

**Nav2 runs on the booted machine's numbers, not the parameter file's.**
`pilot/ros/config/nav2.yaml` has to contain some values, and any values it
contains describe some machine. `Nav2Navigator.apply_manifest` overwrites
them at boot from the manifest that actually booted: top speed, turn rate,
acceleration and deceleration, minimum turning radius, motion model,
footprint radius, inflation radius, and the velocity smoother's limits.
When Nav2 refuses one, the machine says out loud that it is navigating on
numbers that are not its own.

One value is deliberately not manifest-derived. `vx_min` is pinned to zero,
no reverse, and that is a policy rather than a measurement: Nav2 will drive
a differential machine backwards indefinitely whenever reversing is cheaper
than turning, which leaves the camera pointed away from wherever the
machine is going. A machine that must reverse to reach a goal should turn
first.

## Running it

See the commands section of the repository's CLAUDE.md.

## What Stage 3B adds

Real drivers for the ZED X, GNSS and IMU, and the motor controller.
Perception through TensorRT with RF-DETR. The localization source of truth,
decided on the bench. None of it is new architecture: each one is a class
implementing an interface in `hal/interfaces.py` and a line in a manifest.
