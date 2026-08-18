# ADR-0010: Fleet distribution, Ansible first, signed releases later

**Status:** accepted-direction (not yet implemented). **Date:** 2026-08-18.
**Affected:** `ops.fleet_deployment`, `ops.install`. Implements law 14.

## Context

Today there is one Jetson, an agent-executable INSTALL.md, and no repeatable
device provisioning. `git pull` on a field device is how snowflake machines
are born, and Claude Code on a prototype Jetson is useful for debugging but
must never become a runtime dependency or a deployment mechanism.

## Decision

Git plus reproducible releases define the fleet, in two stages:

1. **Now (first machines):** an Ansible inventory and an idempotent Jetson
   provisioning playbook over SSH, installing a versioned Argus release with
   a health check and a documented rollback procedure. Three access paths
   exist permanently: normal deployment, authenticated SSH for maintenance,
   physical console for recovery. Any SSH fix that should persist returns to
   Git and rides the next release.
2. **Later:** signed releases in a private registry, per-device channels,
   staged rollout, automated rollback on failed health checks, and a fleet
   software view in C2. Base system updates (JetPack, kernel, CUDA) stay on
   NVIDIA-supported image/OTA mechanisms, separate from Argus application
   releases (containers or versioned artifacts; the split is OD-18).

Device lifecycle at provisioning: flash approved base image, enroll device
identity, provision keys, apply the body manifest, install the approved
release, run hardware self-test, register with the fleet.

## Alternatives considered

Building the full signed-release pipeline now: premature for one device and
would stall the hardware campaign. Continuing with hand-installs per
INSTALL.md: correct for the bench, already proven not repeatable enough for
a second machine (`scripts/verify_install.py` exists precisely because pytest
cannot prove a deployment).

## Consequences

`DEPLOYMENT.md` is created when the Ansible inventory exists. Hardened
deployed profiles should ship without development tooling by default. The
"no build on target" rule from the packaging work stands: everything,
including the several-GB ZED SDK, resolves at image build time on a
connected machine.
