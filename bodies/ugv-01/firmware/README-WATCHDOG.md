# The silence watchdogs for ugv-01's two boards (14 Oct 2026)

Why: on 13 Oct, with the throttle at 20 percent and the computer silent
for 15 s, the wheels kept turning (BENCH-RESULTS-2026-10-13.md, Phase E).
A vehicle that drives itself must stop by itself when its computer goes
quiet. These two changes make both boards do that. Reviewed twice by
Codex Astra; the second review's blockers are fixed in this revision.

## Throttle board (Arduino Nano), firmware AC 1.2 to AC 1.3

Folder: `nano_throttle_watchdog/`. Open `nano_throttle_watchdog.ino` in
the Arduino IDE (it includes `throttle_logic.h` from the same folder),
board "Arduino Nano", flash as before.

What changes:
- While throttle is above zero, the board must hear a valid line (any
  of `0x01`, `0x02;..`, `0x03`) within 800 ms, or it sets the PWM back to
  rest (42) and latches. At zero throttle nothing is required, so a
  console that only sends on change is unaffected at rest.
- Expiry is checked before every command and between bytes: a line that
  arrives late finds the throttle already at rest, and a burst of serial
  traffic cannot delay the stop.
- After a timeout, the first positive throttle is refused with
  `0x02;ERR;TIMEOUT`. An explicit `0x02;00` clears the latch.
- New `0x03` read-back: `0x03;OK;<duty hex>;<timeouts hex>`.
- `0x01` now answers `0x01;OK;AC0103`.
- The line reader does not block and is bounded; an overlong line is
  discarded to its end, a control byte drops its line.
- The PWM mapping (42 + duty x 172 / 100, truncated) and the Timer1
  prescaler line are AC 1.2's, unchanged.

The logic is in `throttle_logic.h` and is tested on a laptop:
`cd nano_throttle_watchdog/test && clang++ -std=c++17 -I.. test_throttle_logic.cpp -o /tmp/tl && /tmp/tl`.
The sketch could not be compiled on the Mac (the AVR toolchain is x86
only), so the first compile is in the Arduino IDE.

## Drive module (ESP32-S3), firmware 4.1.4 to 4.1.5

Folder: `esp32_drive_watchdog/`. Two new files, `watchdog.h` and
`watchdog.cpp`, go into `src/`, and the patch makes the edits to
`config.h`, `main.cpp` and `serial_protocol.cpp`. From the folder that
contains `src/`:

    patch -p1 < esp32_4.1.5_watchdog.patch

The patched tree compiles clean with PlatformIO for `esp32-s3-devkitc-1`,
framework arduino. Build and flash as before.

What changes:
- Silence: while a steering or brake actuator is on, or centring is
  running, the module must have accepted a command (answered it OK)
  within 800 ms, or all four actuator relays go off at once, centring is
  cancelled, it prints `0x00;WD;TIMEOUT` once and latches. Only accepted
  commands count; errors and garbage do not keep an actuator alive.
- Feedback: an actuator that is on without a valid reading from its
  sensor for 200 ms is switched off the same way (`0x00;WD;NO_SIGNAL`).
  This is what the horn did on 13 Oct.
- While latched, any command that would energise an actuator (`0x05`,
  `0x06`, `0x12`, `0x13` with a direction, `0x14`) is refused with
  `ERR;WD_TRIPPED`. An explicit `0x05 00` or `0x06 00` clears it.
- The watchdog runs before serial work in every loop, and the serial
  handler processes one line per loop, so a stop is never behind a
  burst of commands.
- STATUS gains a last field `WD=<trips>`; its buffer grew to fit.
- `0x01` answers `040105`.

## How ARGUS uses them

The ARGUS controls send a keepalive at least every 250 ms while the
throttle is on or an actuator moves (the read-back `0x03` on AC 1.3,
INFO on older boards), treat `0x02;ERR;TIMEOUT`, `0x00;WD;TIMEOUT` and
`0x00;WD;NO_SIGNAL` as faults, stop without re-energising the brake when
a board reports its own trip, and clear the throttle latch with an
explicit zero. A rising timeout count or a duty the board holds that
differs from what was acknowledged is also a fault.

- Feedback, refined after review: a reading is trusted only while it
  answers and moves plausibly; a jump of more than 30 degrees between
  two 50 ms samples counts as no signal, so one valid-looking sample
  after a dropout does not restore trust.
- Command admission is strict: an opcode must be one byte with nothing
  glued to it (`0x105 01` is refused, not read as `0x05 01`), an argument
  must be one byte with nothing after it (`0x05 00junk` is refused and
  does not clear the latch), overlong lines and lines with control bytes
  are dropped whole, and each pass reads at most 32 bytes.

## Verifying after flashing, before anything moves

Bench first, with propulsion isolated or the drive wheels on stands and
a person at the key. Measure electrically where it matters: a
multimeter or scope on the Nano's pin 9 and on the relay coils, with a
timestamped log of the last accepted command. Eyes and the read-back
confirm, they do not measure.

1. **Identity.** Each port answers its version: Nano `0x01;OK;AC0103`,
   drive module `0x01;OK;040105`. Keep the compiled binaries' hashes
   with the record.
2. **Nano silence.** Throttle 20, then host silent (ports open, board
   powered): pin 9 must return to rest within 800 ms of the last
   accepted line, the read-back must show the timeout count up by one,
   `0x02;14` must be refused with `TIMEOUT`, `0x02;00` must clear it, and
   a throttle after that must be accepted.
3. **Nano traffic.** Late command after the deadline (finds rest);
   malformed, overlong and continuous traffic (no throttle above rest,
   no delayed stop); normal 250 ms keepalive under load for a minute
   with no trip.
4. **Drive module silence.** A steering move running, host silent: both
   steering relays off within 800 ms of the last accepted command, one
   `0x00;WD;TIMEOUT`, `0x05 01` refused with `WD_TRIPPED`, `0x05 00`
   clears. Same for a brake move and for centring.
5. **Drive module feedback.** Disconnect the steering sensor during a
   move: relay off within 200 ms with `NO_SIGNAL`. Then the horn during
   a steering move: record what happens; the sensor dropout the horn
   causes may be shorter than 200 ms, so this is a measurement, not a
   pass or fail. Same for the brake sensor.
6. **Drive module traffic.** `0x105 01`, `0x05 00junk`, an overlong
   line, a control byte: each refused, none actuates, none clears the
   latch, none refreshes the silence timer (the move still trips).
7. **Each direction and each failure separately.** Loss of replies to
   the host, loss of commands to the board, port close by the host, USB
   unplug, board reset: for each, what the outputs do and when.
8. **Host side.** The ARGUS controls receive both notices
   (`WD;TIMEOUT`, `WD;NO_SIGNAL`), fault, and do not re-energise the
   brake on any later stop or on close until a human clears.
9. **No nuisance trips.** Ten minutes of normal driving traffic at
   250 ms, throttle and steering commands interleaved, no trip.

What this does not prove: braking force, stopping distance on the
ground, or anything with wheels down. The section 6 gate opens only
when 2 and 4 pass electrically and the vehicle test then shows the
wheels stopping on their own.
