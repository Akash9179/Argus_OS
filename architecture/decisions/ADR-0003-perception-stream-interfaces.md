# ADR-0003: Perception stream interfaces

**Status:** accepted-direction (not yet implemented). **Date:** 2026-08-18.
**Affected:** `edge.hal.sensor_interface` (superseded),
`core.perception_interface`, `perception.zed`, `perception.detector`,
`edge.navigator`. Closes risk R-1, the audit's highest architectural risk.

## Context

The implemented sensor seam is `SensorDriver.poll() -> list[Detection]`.
Nothing but finished detections crosses the HAL: no images, depth, point
clouds, IMU, or GNSS. Consequences already visible: the detector must live
inside each camera driver, so swapping models is a per-sensor rewrite; Nav2's
costmaps can never receive obstacle data; localization fusion has no inputs.
The original plan promised standardized raw outputs; the code narrowed it.
Cheap to fix now, expensive after three real drivers exist.

## Decision

Perception becomes a set of typed stream interfaces: frames, depth, point
clouds, IMU, GNSS, detections, tracks, semantics, occupancy, plus calibration
and sensor health providers. Sensors declare which streams they provide in
their manifest; capabilities are discoverable; no sensor must provide
everything. High-rate data stays on a local sensor bus and in the recording
pipeline; LINK carries semantic messages only; streamed video is explicit and
out of band. The existing `poll()` seam remains as a compatibility shim until
every consumer has migrated, then is removed.

The first real provider is the ZED adapter, which consumes Stereolabs
capabilities (depth, tracking, spatial AI) rather than rebuilding them: ZED
is the eyes, not the brain.

## Alternatives considered

Keeping Detection-only and putting raw data on ad hoc side channels: recreates
the parallel-stack problem inside one runtime. Making everything ROS topics:
prejudges OD-15 and couples the HAL to ROS, which the core deliberately never
imports.

## Consequences

This is the highest-priority refactor and lands before any real sensor
driver is written. The detector becomes a stream consumer, restoring the
"perception is swappable" story the sovereignty pitch depends on. OD-15 (API
shape: Python-native, ROS-native, or neutral with adapters) is decided on the
real Jetson when the ZED provider is written.
