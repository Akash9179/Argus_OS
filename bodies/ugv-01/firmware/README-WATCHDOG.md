# The silence watchdogs for ugv-01's two boards (14 Oct 2026; authority narrowed 15 Oct)

Why: on 13 Oct, with the throttle at 20 percent and the computer silent
for 15 s, the wheels kept turning (BENCH-RESULTS-2026-10-13.md, Phase E).
A vehicle that drives itself must stop by itself when its computer goes
quiet. These two changes are meant to make both boards do that; until
they are flashed and the silence test passes on the vehicle, that is a
design, not a fact. Reviewed three times by Codex Astra; the blockers
from each review are fixed in this revision.

Two things worth knowing before the test. First, the boards take their
power from the Jetson's USB, so pulling the cable or powering the
Jetson off stops the throttle by cutting power (Gulshan, 14 Oct). The
watchdog covers the other case, the one measured on 13 Oct: Jetson on,
cable in, program silent. Second, on the drive module 4.1.5 any
accepted command refreshes the silence timer, including angle polls, so
a host that keeps polling while its command logic is stuck would keep a
steering move alive; 4.1.6 and AC 1.4 close that (the authority section
below), and the ARGUS controls' own heartbeat rule covers it on the host
side. The drive module's `allOff()` does not
touch its own throttle output (pin 4), which the 13 Oct inventory
believes is unwired since throttle moved to the Nano; confirm on the
wiring photos before relying on it.

## Watchdog authority (15 Oct 2026): drive module 4.1.6, throttle board AC 1.4

On the vehicle on 15 Oct both watchdogs tripped on true silence. They
could not trip on a half-dead host: in 4.1.5 and AC 1.3 any accepted
line refreshes the timer, so a host whose command logic has died but
whose poller lives (angle polls, STATUS, the read-back) keeps a move
alive for as long as it polls. Codex Astra called that a blocker on the
plan's review; this change removes it on both boards.

- **Drive module 4.1.6** (`esp32_drive_4.1.6_src/`, patch
  `esp32_drive_watchdog/esp32_4.1.6_watchdog.patch`): only the OK reply
  of a motion command (`0x05`, `0x06`, `0x12`, `0x13`, `0x14`) or the new
  **`0x15` keepalive** refreshes the silence watchdog. INFO, the angle
  reads, STATUS and the limit reads answer as before and refresh
  nothing. `0x15` takes no argument and answers `0x15;OK;<trip count>`,
  the same number STATUS reports as `WD`; while tripped it still
  answers, and only an explicit stop clears the trip. `0x02` (this
  module's own PWM, believed unwired) is outside the watchdog and does
  not refresh it. `0x01` answers `040106`. Timeouts, the feedback rule,
  the refusals while latched and the parser are 4.1.5's, unchanged.
- **Throttle board AC 1.4** (`nano_throttle_AC0104/`): only a duty frame
  (`0x02;<hex>`) or the new **`0x04` keepalive** refreshes the watchdog.
  `0x01` and the `0x03` read-back are polls. `0x04` answers
  `0x04;OK;<duty>;<timeouts>`, the read-back's data, so a host can keep
  the throttle alive and check what the board holds in one frame. The
  keepalive does not clear the latch; `0x02;00` does. `0x01` answers
  `AC0104`. Tested on a laptop:
  `cd nano_throttle_AC0104/test && clang++ -std=c++17 -I.. test_throttle_logic.cpp -o /tmp/tl14 && /tmp/tl14`.
- **Host (the ARGUS controls)**: motion is armed only when the drive
  module answers 4.1.6 or later, the throttle board AC 1.4 or later, and
  STATUS says `WI=00`. Older boards start, identify and answer reads so
  the bench can look at them; every move (steer, brake apply or release,
  throttle above zero, steer_to) is refused with the reason, and no
  keepalive is sent to a board that does not know the opcode. Wi-Fi
  coming on later in a session is a fault. While an actuator is
  commanded on the controls send `0x15` at least every 250 ms, but only
  while their own heartbeat (fed by the command path above) is live;
  when the heartbeat dies the controls stop first and the keepalive
  stops with it. The one exception is the brake apply the stop itself
  sends when `brake_on_stop` is set: that move is kept alive for at most
  `brake_stroke_max_s` (2.0 s; the stroke measured 1.3 s on 15 Oct), then
  halted where it is. With the throttle on, the keepalive to the Nano is
  `0x04`; at rest the liveness probe is the `0x03` poll, so a dead command
  path with a live tick thread keeps nothing on. A rising trip count in
  STATUS or in the keepalive reply that no WD line announced is a fault.
- **Simulator and runner**: `bench-logs/2026-10-14/simboards.py` has
  `Drive416` and `Nano14` (default; `--fw old` gives 4.1.5 and AC 1.3),
  unit-tested in `tests/test_ugv01_simboards.py`. The runner gained
  `poll_only_silence:DIR:MS`: steering moves, then the host polls angles
  and STATUS every 50 ms with no heartbeat, no tick and no keepalive,
  and the board must print `WD;TIMEOUT` on its own. The firmware's
  nominal timeout is 800 ms; the runner's acceptance bound is 1000 ms
  from the OK to the WD line as the host sees them (its loop and the
  serial path add latency), and it fails on any `0x15` the host sent
  in the window. On the simulator the line comes 807 ms after the OK
  with 43 polls in between, and the host faults exactly once. This is a
  host-observed bound, not a measured physical stop; the trace on the
  relay coils is the proof. The same sequence against `--fw old`
  is refused at the first move: `not armed: drive module firmware 4.1.5
  is older than 4.1.6`.
- **Not done**: nothing flashed, nothing on the vehicle. Flashing waits
  for a session with a person at the jeep; the done-criterion from the
  plan is that a host whose command thread is killed while its poller
  runs produces a trip within the deadline on the bench, by the trace.
  The team's own ROS 2 stack cannot drive the jeep through 4.1.6 or AC
  1.4 without sending motion or keepalive frames inside 800 ms (founder
  decision 4 in the plan). The firmware does not apply the brake on a
  trip (founder decision 5, open).

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

Source of the build: `esp32_drive_4.1.5_src/` holds the complete 4.1.5
tree, byte for byte the one the team was given and flashed on 14 Oct,
with a `platformio.ini` pinned to the platform that built it
(espressif32 7.1.3, board `esp32-s3-devkitc-1`, framework arduino).
Build it with `pio run` in that folder, or build every image at once
with `bash build.sh` from this folder (prints the SHA-256 of each image,
flashes nothing). Both have run on the Jetson.

For reading: `esp32_drive_watchdog/` keeps the watchdog's two files and
`esp32_4.1.5_watchdog.patch`, the exact difference from the vendor tree.
The patch was regenerated on 15 Oct against the vendor tree as stored:
three vendor files have CRLF line endings, and the 14 Oct patch did not
apply to them (every hunk of `serial_protocol.cpp` was rejected, which
left a build that reports 4.1.5 but never feeds or checks the
watchdog). The 14 Oct zip carried the full tree, not the patch, so the
team's build was not affected. To reproduce from the vendor tree:
`patch -p1 < esp32_4.1.5_watchdog.patch` from the folder that contains
`src/`, then `diff -r` against `esp32_drive_4.1.5_src/src` must be
silent.

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
throttle is on or an actuator moves (`0x04` and `0x15` on AC 1.4 and
4.1.6, the only versions they arm; see the authority section above),
treat `0x02;ERR;TIMEOUT`, `0x00;WD;TIMEOUT` and `0x00;WD;NO_SIGNAL` as
faults, stop without re-energising the brake when a board reports its
own trip, and clear the throttle latch with an explicit zero. A rising
timeout count or a duty the board holds that differs from what was
acknowledged is also a fault.

- Feedback, refined after review: a reading is trusted only while it
  answers and moves plausibly; a jump of more than 30 degrees between
  two 50 ms samples counts as no signal for that loop. Known gap
  (Codex Astra, 15 Oct 2026, kept in 4.1.6 unchanged): the jump drops
  the last good sample, so the very next valid-looking sample is
  trusted again, cached or fresh. One plausible sample after a dropout
  restores trust; only a dropout longer than WD_NO_SIGNAL_MS trips. The
  host's single-miss rule is the stricter one and stays.
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
