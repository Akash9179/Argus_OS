# Bench verification brief - ugv-01

## If you are an agent running on the Jetson, START HERE

The hardware survey is DONE. Do not run it again. `SURVEY.md` is history now;
its findings are in `FINDINGS.md` and the synthesis is in `MCU-PROTOCOL.md`.
Read `MCU-PROTOCOL.md` first, completely, before doing anything.

This session is the BENCH VERIFICATION. Everything we believe about this
vehicle came from the team verbally plus code archaeology. Not one relay has
been observed firing. Your job is to turn belief into observation, with a
human at the vehicle, and to write down what actually happened.

## Rule zero, unchanged, and now with a specific new hazard

- Nothing that actuates without the preconditions below being met and a named
  human confirming.
- **WHEELS OFF THE GROUND for the first connection.** Not merely drive power
  isolated. Opening the serial port can reset the Nano, and during the one to
  two second bootloader window every pin is high impedance. What the relay
  board does in that window is decided by its own pull resistors and opto
  bias, which nobody has characterised.
- The emergency stop on this vehicle is the IGNITION KEY. It is physical. The
  human present must know where it is and be able to reach it before anything
  is energised. There is no remote kill.
- There are no brakes right now. Both brake relays were disconnected while the
  team works on that subsystem. Confirm whether they are back before assuming.

## Preconditions, all of them, before a single command

1. Drive wheels off the ground, on stands.
2. Drive power isolated if the test allows it.
3. A named human at the vehicle, who knows a test is running.
4. That human can reach the ignition key.
5. Nobody else near the vehicle.

If any one of these is not true, stop and say so.

## What is already known

Read `MCU-PROTOCOL.md`. In brief: Arduino Nano, `/dev/ttyUSB0` at 115200,
ASCII, newline framed. `R<n><0|1>` for fourteen relays, active LOW on the
board. `P<42..214>` for throttle PWM, 42 is rest. The firmware source is at
`firmware/ugv01_mcu.ino` and it has no failsafe and sends nothing back.

The relay map below is the TEAM'S CLAIM. Verifying it is the point of this
session.

    1 ring light        8  horn
    2 right indicator   9  brake actuator forward
    3 left indicator    10 brake actuator reverse
    4 reverse           11 speed 1
    5 neutral           12 speed 3
    6 high beam         13 steering right
    7 low beam          14 steering left

## Order of work. Do not reorder this.

### 0. Listen first, before commanding anything

Run `listen.py` in this folder. It never writes. Expect silence, because this
firmware transmits nothing, and record that silence as a result. If the board
has been reflashed with v3 it will answer `V` with a version string, but do
not send anything until step 1 has established that commanding is safe.

### 0b. Prove the link with a light, before touching the drivetrain

Before any drivetrain relay, send `R11` (ring light) or `R61` (high beam) and
have the human confirm it lit, then release it. This costs one minute and it
confirms three things with zero consequence: that commands reach the hardware
at all, that the `R<n><0|1>` framing is right, and that the relay board is
responding. If R1 does not light, you learn that with the drivetrain
untouched rather than while commanding gear.

The first drivetrain command should be sent by someone who already knows the
link works.

### 1. Verify R5 is neutral. First, alone, and after the light.

The entire failsafe design rests on relay 5 being neutral. It is the one that
must not be wrong. Energise `R51`, have the human confirm what physically
happened, then `R50`. Record exactly what they observed, in their words.

If R5 is not neutral, STOP. Do not continue down the list. Report it, because
everything downstream changes.

### 2. What gear is the vehicle in with every relay released?

Our reading is that drive is the de-energized default, because there are
relays for reverse and neutral but none for drive. Confirm or kill that.

### 3. Each remaining relay, one at a time

Human watches and listens, and names what responded. Settle what Speed 2 is:
relays exist for speed 1 and speed 3 only.

### 4. Throttle, only after gear behaviour is understood

Verify that P42 is genuinely rest and the vehicle does not creep. Then step
upward in small increments. The `ACCEL:0..172` to `P42..214` offset theory
predicts `P42` is zero throttle; test it rather than trust it.

### 5. Steering legs, briefly, and never both at once

R13 and R14 are the two polarity legs of one actuator. Never energise both.
Pulse each for a short fixed time only. The angle sensor is disconnected and
the firmware would not read it anyway, so there is NOTHING limiting travel:
a long press drives the actuator into its mechanical stop.

### 6. Brake actuator, same rules

R9 and R10 are one actuator driven by polarity reversal, same pattern as
steering. Same two rules: never both, and time limited.

### 7. The failsafe, if v3 has been flashed

This is the whole reason v3 exists, so test it deliberately:
send `H` every 200ms for a few seconds, command a throttle above rest, then
PULL THE USB CABLE. The vehicle must go to rest throttle and refuse steering.
Reconnect, confirm it is still latched, then send `C` to clear.
If that does not happen, say so loudly. It means the vehicle has no failsafe.

## What to produce

Write `bodies/ugv-01/BENCH-RESULTS.md`, one section per step above, in the
same style as `FINDINGS.md`: what was commanded, what the human observed in
their own words, and whether it matched the claim. An unverified step is a
result too. Commit on branch `bench/ugv-01` and push.

Then update the relay table in `MCU-PROTOCOL.md`, marking each row VERIFIED or
CORRECTED, and delete the "Verify this document before anything relies on it"
warning only for the rows that have actually been verified.

## What to ask the humans present, while you have them

- Photographs of the MCU board and the relay board with its wiring loom, if
  not already taken.
- **Is the brake actuator physically connected to R9/R10 RIGHT NOW?** Yes or
  no, today, on this vehicle. The team has described what it IS (one actuator
  on reversing polarity, sixteen levels of position) and separately said the
  brake relays were DISCONNECTED. Both can be true at once. Only the wiring
  answer decides whether this vehicle can decelerate under command.
- **Is the steering potentiometer wired to the Nano right now, and to which
  pin?** Same distinction: a described sensor is not a connected one. Neither
  sketch reads any analog input.
- The steering limit contradiction: this firmware reads no sensor at all, so
  the feedback sensor cannot be what stops over-travel. Is the limit
  mechanical, or is there another firmware?
- Which analog pin did the steering potentiometer end up on? A0 to A3 are
  relay outputs; on a Nano, A6 or A7 are the natural choice.

## After the bench

The real `VehicleAdapter` gets written from these results, not before them.
