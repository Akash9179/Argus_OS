# ugv-01 bench results, 13 Oct 2026 (evening IST)

The first time ARGUS code commanded this vehicle. Wheels on multiple
jacks, people around the vehicle for observation, Gulshan Shah at the
ignition key, the founder relaying every line and every observation from
the Mac. Every frame sent and received is in `bench-logs/2026-10-13/`
(JSON lines, one file per run) with the runner that produced them. Code:
`drive/pilot/hal/drivers/ugv01/` on branch `bench/ugv-01`, commits
`ddc4641` (Phase A) to `50be640` (Phase D onward); the Jetson checkout at
`~/argus` was pulled to each commit before the run that needed it.

This record separates three kinds of evidence, as Codex asked: what the
board acknowledged on the wire, what the sensors read, and what the
humans saw. A line in the "seen" column is the team's words, relayed.

## Setup

- Ports: drive module on `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`
  (CH340, `/dev/ttyUSB1`), accelerator board on
  `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0`
  (FTDI, `/dev/ttyUSB0`). 115200 8N1 both.
- The team's ROS 2 stack held both ports until Gulshan stopped it from
  the Jetson terminal. It was relaunched twice by an agent session on the
  Jetson during the preparation; a start with a shared port fails closed
  (replies split between two readers arrive garbled, the drive board
  "did not identify itself", nothing sent but INFO). Logged in
  `bench_ugv01_phaseA.jsonl` before the last `started` record.
- Each run opens both ports (the accelerator board reboots on open),
  reads INFO, STATUS, both limit pairs and both angles, sends duty zero
  then INFO to the accelerator, and only then runs its steps. Every run
  closes with duty zero, brake actuator stop, steering stop, duty zero.
  Bench cap on duty: 30 percent. Brake was not part of the automatic
  stop (`brake_on_stop` off) because the stroke was uncharacterised.

## Identity and state at rest

| Item | Reading | Source |
|---|---|---|
| Drive module firmware | 4.1.4 (`0x01;OK;040104`) | wire |
| Accelerator firmware | 1.2 (`0x01;OK;AC0102`) | wire |
| STATUS at rest | `A=00,ST=00,BR=00,SP=02,GR=03,LI=00,IN=00,HO=00,WI=00,CT=00` | wire |
| Steering limits | 67.0 to 243.0 deg (`0x10;OK;029E097E`) | wire |
| Brake limits | 70.0 to 170.0 deg (`0x0F;OK;02BC06A4`) | wire |
| Steering at rest | 153.7 deg | sensor |
| Brake at rest, fully released | 61.7 deg (below the 70 "min": the released end stop) | sensor; Gulshan: "the brake is already released" |

STATUS fields, read from the reply shape: A accel, ST steer switch, BR
brake switch, SP speed mode, GR gear (01 D, 02 N, 03 R), LI light, IN
indicator, HO horn, WI Wi-Fi, CT centring. The vehicle rested in gear
REVERSE (GR=03) at the start of the session.

## Phase A: lights, indicators, horn (no motion)

| Step | Frame | Reply | Seen |
|---|---|---|---|
| low beam on | `0x09 03` | `0x09;OK;03` | team confirmed Phase A |
| low beam off | `0x09 00` | `0x09;OK;00` | |
| left indicator | `0x0A 01` | `0x0A;OK;01` | |
| right indicator | `0x0A 02` | `0x0A;OK;02` | |
| indicators off | `0x0A 00` | `0x0A;OK;00` | |
| horn 0.5 s | `0x0B 01` | `0x0B;OK;01` | |

**Horn disturbs both angle sensors.** 33 ms after the horn frame the
steering reading went 153.7 to 352.6, then the board answered
`0x04;ERR;NO_SIGNAL`, then 60.3 (below its 67 minimum); the brake reading
went 61.7 to 183.2, 343.9, 252.3 (above its 170 maximum). The last
samples fell inside the horn's 0.5 s pulse. A read-only re-open two
minutes later read 153.7 and 61.7 again: the disturbance lasts while the
horn sounds and the sensors recover. Hazard for the firmware: its
steering limit enforcement reads the same sensor, so a horn during a
steering move is unprotected. Hardware question for the team: horn
current path versus sensor supply or ground.

Consequence in ARGUS (commit `b2c4fa8`): an ERR or unreadable angle
reply, a jump over 30 deg between polls, or a steering reading outside
the limits latches a fault and stops; a steering move is refused without
a fresh reading.

## Phase B: steering pulses

| Step | Reading before | Reading after | Seen |
|---|---|---|---|
| `0x05 01` for 300 ms, then `0x05 00` | 153.7 | 173.9 | "The wheel turned a little bit left" |
| `0x05 02` for 300 ms, then `0x05 00` | 173.9 | 152.9 | |

Trajectory (5 Hz polls): 153.7, 159.8, 173.1, 173.9, hold. About 67
sensor-degrees per second while moving; the reading settled within 100 ms
of the stop acknowledgement; 1.8 deg between the last two moving samples
on the return, which sampling cannot split into overrun versus latency.
All four frames acknowledged OK.

**Result: `0x05 01` is left, and the sensor reading increases to the
left. ARGUS steering sense: `left_increases`.** The spec's page 2 ("01 is
right") is wrong; pages 3 and 5 are right.

## Phase C: gear and throttle

| Step | Wire | Seen |
|---|---|---|
| gear D `0x08 01` | `0x08;OK;01`; STATUS re-read `GR=03` then `GR=01` after the change | |
| brake release `0x06 02` with the brake at its released end | `0x06;ERR;AT_LIMIT` | |
| throttle 20 percent `0x02;14` for 1.0 s, then `0x02;00` | `0x02;OK;14` in 2 ms, `0x02;OK;00` in 3 ms | first run: team unsure |
| throttle 20 percent for 1.5 s (repeat) | same acknowledgements | "Yes, it did. The wheel moved and then stopped." |

Two refusals on the way are the interlocks working: with no release in
the step list the throttle was refused ("brake applied or not known
released"), and with the release answered `AT_LIMIT` it was refused
again until commit `ada6c52` taught the controls that a release refused
because the brake is already at its released end counts as released.
Codex's caution stands: that acknowledgement proves the firmware refused
further release motion, not brake clearance; today it was paired with
Gulshan's statement and the 61.7 end-stop reading.

## Phase D: brake

| Step | Reading before | Reading after | Seen |
|---|---|---|---|
| apply `0x06 01` 300 ms, then `0x06 00` | 61.7 | 91.0 | "moved forward" |
| apply again 300 ms | 91.0 | 114.5 | |
| release `0x06 02` 300 ms | 114.5 | 84.5 | "moved back" |
| release again 300 ms | 84.5 | 61.7 | released |

The brake reading rises as the brake applies: about 98 deg/s on the
first stroke, 78 deg/s on the second (slower as it loads), about 100 deg/s
releasing. After a stop acknowledgement the actuator keeps moving about
150 ms before it settles. The second release reached 61.7 in under 300 ms
and stayed: the released end stop ends a release by itself, with no
AT_LIMIT message while moving. All frames acknowledged OK. Braking force
and holding behaviour were not measured; the wheels were in the air.

## Phase E: the computer goes silent with throttle held

The decisive test. Throttle held at 20 percent (`0x02;OK;14`), then the
host sent nothing at all, no heartbeat, no poll, no probe, ports open,
for 15.0 s (`silence_begin` to `silence_end` in
`bench_ugv01_phaseE2.jsonl`), then `0x02;00`.

**Seen: the wheels turned for 19 seconds on a phone stopwatch,** from
the throttle frame through the whole silence until the zero arrived and
the wheels spun down. A first run with 5 s of silence gave "5 to 7
seconds, maybe", consistent with the same conclusion.

**Result: the accelerator board holds its last duty with no watchdog.
A dead host leaves the vehicle driving.** This is the section 6 hazard,
measured. The hardware safety gate stays shut until the accelerator
firmware stops on its own after a short silence, and that is proven the
same way.

Not tested today: the drive module's behaviour on silence (no move was
in progress during the silence), USB unplug, and host death with a port
close (which may reset the board; a different test).

## What is proven and what is not

Proven on the vehicle, from ARGUS code on the Jetson: identity of both
boards; STATUS format; lights, indicators, horn commanded and
acknowledged; gear D commanded and proven by STATUS; steering left and
right with feedback and sense; throttle commanded, acknowledged and the
wheels turned; brake applied and released with feedback; fail-closed
start on a shared port; the interlocks refusing throttle without a
known-released brake; the horn interference; the missing accelerator
watchdog.

Not proven: braking force; the drive module on link loss; what the
accelerator does when its port closes; physical gear engagement beyond
the STATUS field; vehicle speed at any duty (no speed sensor); anything
with the wheels on the ground.

## Open items carried forward

1. Accelerator firmware needs a silence timeout (Gulshan has the
   source). Re-run Phase E after.
2. Horn versus sensor supply.
3. Drive module on link loss during a steering or brake move.
4. The brake "released end stop" at 61.7 against the configured 70 to
   170: either fix the configured limits or document 61.7 as released.
5. Speed sensor, vehicle geometry, position source: still absent, still
   needed before any driving logic.

Codex Astra reviewed the plan (checkpoint 1), the diff (checkpoint 2),
Phase A's log, and the B/C logs during the session. Its reviews are in
the session thread `01a13592`; the items it raised that are still open
are in the graph entry `edge.hal.ugv01`.
