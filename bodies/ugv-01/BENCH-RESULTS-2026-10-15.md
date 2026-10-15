# ugv-01 bench results, 15 Oct 2026 (evening IST)

The silence watchdogs on the vehicle, from our side. Drive wheels on a
jack, Gulshan Shah at the jeep as hands and eyes, the founder on his
phone pasting each command into the session and relaying what Gulshan
said; the agent read every line and chose the next command. All code
and all commands from our side over Tailscale to the Jetson (`tessy`),
per the 14 Oct direction. Every frame sent and received is in
`bench-logs/2026-10-15/` (JSON lines, one file per run). Runner:
`bench-logs/2026-10-14/bench_run.py` (commit `ee0f615`), copied to
`~/argus/var/bench_run_2026-10-14.py` on the Jetson. Jetson checkout
`6d64355`.

Three kinds of evidence, kept apart as on 13 Oct: what the board said on
the wire, what the sensors read, and what the human saw. The human's
words are Gulshan's, relayed by the founder.

## Context

The team had put 4.1.4 back on the drive module earlier on 15 Oct and
called the cause "firmware side", without saying what it saw. Our
re-read of the 4.1.5 patch against the vendor source found nothing that
touches boot, relays, lights, indicators or horn (details in the wiki
and in `firmware/README-WATCHDOG.md`). Today's runs test the firmware
itself, on the vehicle.

## Setup

- Ports as on 13 Oct: drive module `usb-1a86_USB_Serial-if00-port0`
  (CH340), accelerator `usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0`
  (FTDI). Nothing else held them; the team's ROS 2 stack was not running.
- Each run opens both boards once (the drive module resets on open, see
  the ignition test), reads identity, STATUS, limits and angles, sends
  duty zero to the accelerator, runs its steps with a 250 ms keepalive
  while anything moves, and closes with a stop. No brake in the
  automatic stop. Bench cap 30 percent duty; today used 20.
- The harness refused the agent every command that opens a port, so the
  founder pasted each line himself. Flashing was done the same way.

## Identity (run0, before anything else)

| Item | Reading | Source |
|---|---|---|
| Drive module firmware | 4.1.4 (`0x01;OK;040104`); STATUS without a WD field | wire |
| Accelerator firmware | AC 1.3 (`0x01;OK;AC0103`), read-back `0x03;OK;00;00` | wire |
| Steering at rest | 161.4 deg | sensor |
| Brake at rest | 61.7 deg (released end stop, as on 13 Oct) | sensor |
| STATUS at rest | `A=14,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=00,CT=00` | wire |

So the team's rollback was real and limited to the drive module; the
accelerator still carried the ARGUS watchdog build with zero timeouts
since its last boot. Wi-Fi off (`WI=00`). `A=14` is the drive module's
own throttle output at its 20 percent floor, the pin the 13 Oct
inventory believes is unwired; the accelerator's duty read 0.

## Ignition test (ignition_monitor.py, 75 s, nothing sent)

| Event | Wire | Seen |
|---|---|---|
| port open | drive module ROM banner, `rst:0x1 (POWERON)`, then `0x00;OK;040104` 200 ms later | |
| the next 74 s | no line from either board | not yet relayed |

The drive module resets on every port open even with DTR and RTS held
low before opening (the CH340 adapter pulls EN). From reset to the
application's first line is about 200 ms after the ROM lines; the
application then waits a further 200 ms before it drives the relay pins.
The 200 ms is the startup delay in `main.cpp`, read from the source,
not measured. During that window the four steering and brake relay
inputs are not driven; that they float is inferred from the absence of
pull-ups in what we know of the wiring, not measured. Identical in
4.1.4 and 4.1.5.

Whether Gulshan turned the key during the window, and whether anything
flickered, was not relayed before this record was written. If he did,
the absence of any reset line says the drive module keeps running
through ignition and the flicker is the relay module's own power-up.
Until that answer arrives the test is incomplete and will be repeated.

## Run 1 and run 1b: accelerator silence (AC 1.3; drive module 4.1.4, then 4.1.5)

Steps: `snap [status] gear:D expect:GR=01 brake:release:300
throttle_silence:20:1500 snap clear throttle:20:1000 snap`.

| Step | Wire | Seen (run 1b) |
|---|---|---|
| gear D | `GR=01` already; acknowledged | |
| brake release 300 ms | 61.7 before and after (released end) | |
| throttle 20 percent, then host silent 1500 ms | `0x02;OK;14`; first read-back after the silence `0x03;OK;00;01`: duty at rest, timeout count 1 | "The wheel spun, then stopped, and then spun again" |
| host fallback stop after the silence | duty zero sent, acknowledged | |
| clear | latch cleared with an explicit zero; faults empty | |
| throttle 20 percent for 1000 ms | `0x03;OK;14;01` four times, then `00;01` after the zero | (the second spin) |

Both runs identical on the wire: faults exactly
`['accel board took a timeout on its own (1)']`, count 0 to 1, clear
accepted, throttle after the clear accepted. Run 1 had 4.1.4 on the
drive module, run 1b had 4.1.5; the accelerator result does not depend
on it. The read-back polls at about 300 ms, so the board's own stop is
bounded only to "inside the 1.5 s silence"; its 800 ms deadline is not
measured here. Gulshan's words match the sequence: spin, stop on its
own, spin once more after the clear.

## Flash of 4.1.5 from the Jetson (key off)

`pio run -t upload` from `~/argus-tools/build-script/esp32_drive_4.1.5`,
image SHA-256 `c33a05ad880f712d11da9404e3e4eacf94848ab1ac2a829e74f1f8d19b3ad021`
(the 15 Oct Jetson build, `firmware/BUILDS.md`). 707264 bytes written at
0x10000, hash verified by esptool, hard reset by RTS. Key off during the
flash so the actuators had no power while the relay inputs floated. The
next open answered `0x01;OK;040105` and STATUS gained `WD=00`.

## Run 2, 2b: steering silence refused by the bench (no fault)

| Attempt | Wire | Why |
|---|---|---|
| `steer:left:450` | 161.4 to 192.6 deg in 450 ms, acknowledged; 4.1.5 moved normally under the 250 ms keepalive | first left turn done |
| second `steer:left:450` | refused by the bench: room 50.4 deg toward the upper limit (243), need 54.0 | the margin rule, not the board |
| `steer:right:1500` (2b) | refused: room 125.6 toward the lower limit (67), need 127.5 | same |

The bench's room rule assumes 70 deg/s plus 22.5 deg for a timed move,
and 70 deg/s over the silence plus 0.9 s plus 10 deg for a silence
move. Both refusals closed with a stop and nothing moved. Kept here
because they show 4.1.5 steering normally and the admission rules
holding.

## Run 2c: drive module silence (4.1.5), `--max-angle-step 120`

Steps: `snap steer:right:1400 snap steer_silence:left:900 status snap
clear steer:right:300 snap`.

| Step | Wire | Sensor | Seen |
|---|---|---|---|
| steer right 1400 ms | acknowledged, keepalive throughout | 192.6 to 92.0 deg | awaiting Gulshan's words |
| room check | 151.0 deg toward the upper limit, need 136.0 | | |
| steer left, then host silent 900 ms | `0x05;OK;01` at t=0; `0x00;WD;TIMEOUT` from the board at t=851 ms; host fallback stop sent at t=852 ms, `0x05;OK;00` at t=858 ms | 92.0 to 154.7 deg (62.7 deg in about 0.9 s of motion including coast) | |
| STATUS after | `...,CT=00,WD=01`: trip count 0 to 1 | | |
| clear | faults empty, latch cleared | | |
| steer right 300 ms | accepted, `0x05;OK;02` | 154.7 to 134.2 deg | |

Faults after the silence exactly
`['drive module WD TIMEOUT: it stopped its actuators itself']`. The
board announced its own stop 851 ms after accepting the move, against
an 800 ms deadline measured from its OK reply; the 51 ms difference is
not explained by measurement (loop period and USB latency are the
candidates). The host had sent nothing between the OK and the
notice.

## Ignition test, second run (ignition_2026-10-15b.jsonl, 75 s)

Same shape as the first: the drive module reset at open (POWERON), the
4.1.5 banner 200 ms after the ROM lines, then no line from either board
for the remaining 74 s. Gulshan's answer, relayed by the founder after
the run: he turned the key off and on twice inside the window, and
nothing flickered. So the drive module keeps running through ignition
(no reset line), and the flicker reported by Mohit on 14 Oct did not
reproduce tonight with 4.1.5. The flicker, when it happens, is not a
board reset and not the firmware.

Reset at open is not every open: the traffic run below opened the
port and found the trip counter still at 1 from the run before, so
that open did not reset the board. The CH340's auto-reset depends on
how DTR and RTS move at open; not characterised.

## Run 2d: drive module silence the other way (4.1.5)

Steps: `snap steer:left:1000 snap steer_silence:right:900 status snap
clear steer:left:300 snap`, `--max-angle-step 120`. No human
observation requested (founder instruction: no more questions to
Gulshan).

| Step | Wire | Sensor |
|---|---|---|
| steer left 1000 ms | acknowledged, keepalive throughout | 178 region before the silence step (see log) |
| steer right, then host silent 900 ms | `0x00;WD;TIMEOUT` from the board, host fallback stop acknowledged | stopped at 157.3 deg |
| STATUS | `WD=01` | |
| clear, steer left 300 ms | accepted | 157.3 to 178.2 deg |

Faults exactly `['drive module WD TIMEOUT: it stopped its actuators
itself']`. The steering watchdog has now tripped once in each
direction.

## Ten minute traffic run (bench_ugv01_2026-10-15_traffic10.jsonl): stopped at 21 s by the host, not by a board

120 cycles of the same traffic as the 90 s run were requested. At
20.62 s, during the third cycle's `steer:right:400`, a steering angle
poll answered `0x04;ERR;NO_SIGNAL`. The poll had been sent at 20.619 s;
the host sent the step's own steering stop at 20.622 s, so the bad
sample coincides with the steering relay switching off. The host's rule
latches a fault on a single unreadable angle (`steering feedback
failed: NO_SIGNAL`), stopped everything and abandoned the run. The
next poll 200 ms later read 179.7 deg normally. No `WD;NO_SIGNAL` from
the board: its rule needs four consecutive 50 ms misses and saw one.

| Run | steering polls | `NO_SIGNAL` |
|---|---|---|
| 90 s traffic (20 cycles, 40 relay switchings) | 561 | 0 |
| ten minute attempt (3 cycles) | 89 | 1 |
| all other runs today | 180 | 0 |

So the angle sensor drops an occasional sample when a steering relay
switches, the same coupling the horn shows at full strength. The
watchdogs are not involved. Consequence for driving: under the present
host rule the vehicle stops by itself on a single dropped sample. Two
fixes, not exclusive: the sensor and relay wiring; and a host rule that
tolerates one miss while an actuator is on, with the firmware's four
miss rule behind it. The second is a safety logic change and gets a
test and a review before it ships. The ten minute run is not done.

## Traffic test (bench_ugv01_2026-10-15_traffic.jsonl, about 90 s)

Twenty cycles of `throttle:20:1000 wait:300 steer:left:400
steer:right:400 wait:300` under the 250 ms keepalive, then STATUS and
read-back. README-WATCHDOG.md step 9 in short form.

| Item | Result |
|---|---|
| faults | none, all cycles |
| drive module WD count | 00 before and after (the counter resets on the board's reset at open) |
| accelerator timeout count | 0 before and after |
| throttle | `0x02;OK;14` every cycle, read-back `14` while on, `00` after each zero |
| steering | 145 to 174 deg and back every cycle, same excursion each time; 146.5 at the end |
| brake | 61.7 throughout |

Gulshan's observation not relayed. No nuisance trip on either board
under normal driving traffic with 4.1.5 and AC 1.3.

## Horn during steering (bench_ugv01_2026-10-15_horn.jsonl): the horn alone faults the host

Steps `snap horn steer:left:600 ...`. The steering never started: the
horn alone corrupted both angle readings and the host latched.

| t from the horn's OK | Wire | Reading |
|---|---|---|
| 0 ms | `0x0B 01`, `0x0B;OK;01` | steering 146.5, brake 61.7 |
| +203 ms | `0x04;OK;0DED` | steering 356.5 (above the 243 limit) |
| +404 ms | `0x04;OK;05B9`, `0x03;OK;03B6` | steering back at 146.5, brake 95.0 (was 61.7) |
| +597 ms | host faults and stops | `steering feedback jumped 146.5 to 356.5 deg`, `brake feedback jumped 61.7 to 95.0 deg` |

One bad sample on each sensor during the horn's 0.5 s pulse, at 5 Hz
polling, exactly as on 13 Oct, now with 4.1.5. The firmware's own
NO_SIGNAL path was not exercised because no actuator was on. Nothing
moved; the run closed with a stop. Consequence: with the present
wiring, sounding the horn while an actuator moves will stop the vehicle
through the host's plausibility rule, and the firmware's 200 ms
no-signal rule would do the same on a longer dropout. The fix is in the
wiring (horn current path against the sensors' supply or ground), not
in software; it heads the list for the wiring capture.

## Brake stroke (bench_ugv01_2026-10-15_brakeA to F.jsonl): the first time the brake moved through its range

Timed 300 ms steps with the host's keepalive, the angle read after each.
Configured limits 70 to 170 deg (`0x0F;OK;02BC06A4`).

| Run | Steps | Angles | Rate |
|---|---|---|---|
| A apply | 3 x 300 ms from the released end | 61.7, 91.0, 115.1, 139.0 | 98, 80, 80 deg/s |
| B release | 4 x 300 ms | 139.0, 113.7, 83.0, 61.0, 61.0 (fourth refused at the end) | 84, 102, 73 |
| C apply | 5 x 300 ms | 61.0, 90.3, 114.3, 138.3, 161.0, 176.7 | 98, 80, 80, 76, 52 |
| D release | 5 x 300 ms | 176.8, 149.1, 123.1, 96.0, 67.5, 67.5 (fifth refused below 70) | 92, 87, 90, 95 |
| E apply | 3 x 300 ms then 800 ms | 67.5, 95.7, 119.2, 143.4, then 157.2 at 0.32 s, 173.7 at 0.54 s, 179.1 at 0.73 s, 178.9 after the stop at 0.80 s | 75 deg/s, then slowing to a stop at 179 before the host's stop |
| F release | 5 x 300 ms | see the log | |

Facts from this:

- The physical range is about 61 (released end stop) to 179 (applied
  end) sensor degrees; end to end takes about 1.3 s at 80 to 95 deg/s,
  the apply slowing over the last 10 deg as the actuator loads up.
- The firmware refuses a brake command at command time when the
  reading is already past a limit (release at 61 and at 67.5, both
  below the 70 minimum, answered AT_LIMIT), so a release can rest
  anywhere between 61 and 70 depending on where the host's stop lands,
  and the host cannot then command it lower. Whether a brake resting at
  67.5 drags is a step 2 question.
- Whether the firmware halts a moving brake at the 170 maximum is NOT
  established. In run E the reading was already 173.7 at 0.54 s and
  reached 179.1 by 0.73 s, where the actuator stopped on its own before
  the host's stop at 0.80 s. That is consistent with the mechanical end
  and with a firmware halt near 170 followed by 8 deg of coast; the 5 Hz
  polls cannot separate them. The code (`angle_limits.cpp`,
  `brakeLimitsUpdate`) does halt at `brakeMax` when limits are enabled,
  and they are enabled by default and locked. The oscilloscope on the
  relay coil (step 1) answers it. Until then the host bounds every
  brake move by time, and a long move can run the actuator onto its
  end stop.
- The host did not fault on a reading 9 deg past the configured
  maximum; its out-of-range rule is written for steering only.
- The brake was left at 67.5 or wherever the last release stopped.
  After a watchdog trip the brake stays wherever it was: this is the
  stopping-architecture question in the plan's step 0.

## What is proven, and what is not

Proven on the vehicle, by the board's own report over the wire and,
for the throttle, by a human's eyes:

- The accelerator board (AC 1.3) rests its output on its own when the
  host goes silent with the throttle on, counts the trip, and accepts
  the next throttle after the host's explicit zero. Twice, and seen by
  Gulshan on run 1b.
- The drive module (4.1.5) switches its steering off on its own after
  800 ms of host silence, announces it, counts the trip, and accepts
  the next move after the host's explicit stop. Twice, once each way,
  by the wire and the angle sensor; no human observation of these.
- The drive module keeps running through ignition: two key cycles
  inside a listening window produced no reset line, and nothing
  flickered (Gulshan, relayed).
- 4.1.5 and AC 1.3 run normal driving traffic (twenty throttle and
  steering cycles under the 250 ms keepalive) with no fault and no trip
  on either board.
- The horn still corrupts both angle sensors (one sample each inside
  its 0.5 s pulse), and the host stops on it. Wiring, not firmware.
- The host receives both boards' notices, faults, stops, and clears
  only on command.

Not proven, so the section 6 gate stays shut:

- No electrical measurement of either stop (meter on the Nano's pin 9,
  on the relay coils). Read-back and eyes bound the stop; they do not
  time it. README-WATCHDOG.md steps 2 and 4 "electrically".
- Brake silence and centring silence on the drive module untested.
- Refusal while latched (`0x02;ERR;TIMEOUT`, `ERR;WD_TRIPPED`) was not
  exercised: the host sent its own zero or stop at once after every
  silence and no move was attempted while a board was latched. That
  behaviour rests on the Nano unit test and the team's 14 Oct report.
- No feedback-loss test (step 5: sensor disconnected during a move), no
  late-command or malformed-frame tests (steps 3 and 6), no port-close,
  unplug or reset cases (step 7). The ten minute no-nuisance run (step
  9) passed in a 90 s form and failed at 21 s on the host's
  single-miss sensor rule, not on a board.
- Gulshan's words for the steering run and for the ignition test were
  not relayed before this record was written.
- The undriven relay-input window at every reset and port open is
  unaddressed and its effect unmeasured (hardware pull-ups are the
  expected fix).
- The esptool transcript of the flash exists only as the tail pasted
  into the session, saved as `bench-logs/2026-10-15/flash_4.1.5_esptool.txt`.

## Open with the team, still unanswered

What Gulshan saw with 4.1.5 that made him roll it back. Whether he
turned the key during the ignition window and what flickered. The
compiled images he flashed on 14 Oct (never hashed). Whether the motor
was wired during his PowerShell test on 14 Oct.
