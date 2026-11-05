# ugv-01 bench, 5 Nov 2026

Founder at the vehicle in Jabalpur, pasting each port-opening command
from his own session over Tailscale. The agent built, read logs and
kept the record; it opened no vehicle port itself.

## Flash of the watchdog-authority firmware

See `firmware/BUILDS.md` (5 Nov section) for the images and hashes.
The team's stack (`~/Desktop/ros2_new/start.sh`: console with the
serial bridge, phone GPS, route follower, phone remote, cameras) was
running and held both USB ports. The first drive module flash failed
part way because of it and left the module without a valid program
until the second, clean flash. Lesson: before any flash, `fuser` on
both ports must be empty, inside the same command as the flash. Every
flash command after the failure carried that guard. The team's stack
was stopped on the founder's word; only its camera launch was started
again (it opens no serial port).

## Identity read, no motion

`bench-logs/2026-11-05/identity.jsonl`, runner steps `snap status
readback`, then the runner's stop on close (acknowledged).

| field | value |
|---|---|
| drive module | 4.1.6 |
| accelerator | AC 1.4, read-back working, duty 0, timeouts 0 |
| STATUS | `A=14,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=00,CT=00,WD=00` |
| steering | 161.0 to 161.2 deg |
| brake | 174.4 to 174.8 deg |
| faults | none |

Readings worth noting:
- Gear D (`GR=01`, per `_GEAR` in protocol.py). Any wheel test needs
  the drive wheels off the ground.
- Brake at 174.8 deg: near the measured applied end (about 179) and
  above the configured upper limit of 170. The brake is applied. The
  firmware refuses commands past its limits, so a further apply is
  expected to be refused and a release allowed. Not exercised.
- `A=14`: the drive module's own throttle PWM at its 20 percent floor,
  as on every read since 13 Oct (believed unwired).

With these versions and `WI=00` the host controls arm motion. Nothing
moved in this session.

## Not done yet

The poll-only proof on the vehicle (step 0 item 4 of the A to B plan),
brake and centring silence, refusal while latched. These need the
wheels up and a named person at the key.
