# ADR-0004: Localization as a first-class provider

**Status:** accepted, seam implemented 2026-08-18 (ROS bridge migration and real providers pending hardware). **Date:** 2026-08-18.
**Affected:** `edge.hal.locomotion_interface` (loses `pose()`),
`core.localization_provider`. Closes risk R-2.

## Context

Pose currently comes from `LocomotionDriver.pose()`: "where am I" is answered
by the thing that turns wheels. That fits dead reckoning and possibly
ZED-native tracking, but a GNSS + IMU + VSLAM fusion has no home on that
seam, and the open provider choice (D-1, cuVSLAM vs ZED-native vs fused)
would be distorted by which option fits the existing interface rather than
which is better.

## Decision

Localization becomes its own provider kind on the HAL: a
`LocalizationProvider` producing a `PoseEstimate` carrying timestamp, frame,
position, orientation, velocities, covariance, source contributions, health,
and confidence. Locomotion keeps motion commands and loses pose ownership
(wheel odometry becomes one input to localization, not the answer). The rest
of Argus never knows which provider is active; D-1 stays a provider swap
decided on the bench.

## Alternatives considered

Leaving `pose()` on locomotion and fusing inside each locomotion driver:
copies fusion into every body and hides uncertainty. A ROS-only TF answer:
couples the core to ROS and dies with it if MPPI loses the bang-bang fight
(OD-13).

## Consequences

The locomotion interface change is a refactor with a shim during migration
(the sim driver keeps dead reckoning as a trivial provider). PoseEstimate
uncertainty becomes available to the contingency policy
(localization_lost behavior) and to law 16 provenance. Frame and calibration
truth get one owner; where transforms live is part of the implementation
design, recorded when written.
