# ugv-01 MCU serial protocol

Source of the relay map: Akash's team, supplied 2026-08-11. Source of the
syntax: the host-side testers on the Jetson, read during the hardware survey
(`bodies/ugv-01/FINDINGS.md`).

**Status: UNVERIFIED.** The map below is what the team says the relays do. No
relay has been observed firing. Nothing here has been tested against the
vehicle. Verify at the bench, wheels off the ground, one relay at a time,
before any of it reaches a driver.

## Link

| Property | Value |
|---|---|
| Device | `/dev/ttyUSB0`, FTDI FT232R, serial A5069RR4 |
| Baud | 115200 |
| Encoding | ASCII, newline framed, no checksum, no acknowledgement |
| Direction | Host to MCU. Telemetry format still unknown. |

The USB adapter changed from CH340 to FTDI at some point. Every host-side
program on the Jetson still hardcodes the old CH340 by-id path and would fail
to open the port today.

## Relays: `R<n><0|1>`, n = 1..14

| n | Function | Notes |
|---|---|---|
| 1 | Ring light | |
| 2 | Right indicator | |
| 3 | Left indicator | |
| 4 | Reverse | gear |
| 5 | Neutral | gear |
| 6 | High beam | |
| 7 | Low beam | |
| 8 | Horn | |
| 9 | Brake | **DISCONNECTED** |
| 10 | Brake | **DISCONNECTED** |
| 11 | Speed 1 | preset |
| 12 | Speed 3 | preset |
| 13 | Steering right | on/off, not proportional |
| 14 | Steering left | on/off, not proportional |

## Throttle: `P<value>`, 42..214

Resting value is 42, not 0. The `commands.js` vocabulary in the ros2_new
workspace documents `ACCEL:<level>` as 0..172, and 214 - 42 = 172 exactly,
which is consistent with the firmware writing PWM duty as `42 + level`. That
arithmetic is a hypothesis, not an observation. Test it before trusting it.

## What this map tells us, and it is not all good news

**Steering is still bang-bang.** Two relays, left and right, on or off. It is
not proportional. The old integration notes were right about this and the
"hardware has been upgraded" assumption was wrong. Teleop steering will be
discrete, and the cockpit must not present a continuous steering input that
the vehicle cannot honour (waterline law: do not show the operator a control
that lies).

**There is no brake TODAY, and the reason is benign.** Both brake relays are
disconnected because the team is working on that subsystem (founder,
2026-08-11). So this is a temporary state, not a design limitation, and the
brakes are expected back. Until they are, the only way to slow this vehicle
remotely is to drop throttle to 42 and coast, and any safety argument that
assumes remote braking is false.

Two things follow. First, ask when they are reconnected, because the answer
changes `safe_stop()` from "coast and hope" into a real deceleration path, and
it softens the no-passive-safe-state problem considerably. Second, brake
presence belongs in this body's capability manifest as a declared capability,
not as an assumption in the adapter. The adapter must run correctly on a
vehicle whose brake is absent, because that is the vehicle we have this week.

**The brake numbers do not add up yet.** The ros2 console offers `BRAKE:<0..15>`,
sixteen levels, but only two relays are allocated to braking. Two relays encode
four states, not sixteen. So either braking has a PWM channel nobody has found,
or one relay is brake-apply and the other is something else, or the sixteen
levels are aspirational like the rest of that console. Resolve this at the
bench, and ask the team directly what R9 and R10 each do once reconnected.

**There is no ignition relay and no e-stop relay.** Ignition appears to be
physical. There is no remote emergency stop in hardware at all. The cockpit's
ignition control and pre-arm self-test have no hardware counterpart on this
body yet, and must be honest about that.

**Drive appears to be the de-energized default.** There are relays for Reverse
and for Neutral, and none for Drive. So with every relay off, the vehicle is
in Drive. That means a power loss or a de-energizing failsafe leaves it in
gear rather than in neutral, which is backwards from what a failsafe should
do. Confirm this with the team before relying on either reading.

**Speed 2 is unaccounted for.** Relays exist for Speed 1 and Speed 3 only.
Whether Speed 2 is both off, both on, or absent is unknown.

## Consequence for the adapter

`safe_stop()` on this body can be implemented, and it is:

1. `P42` (throttle to rest)
2. `R51` (engage neutral)
3. `R130` and `R140` (release both steering relays)

Note that this is an ACTIVE safe stop: it requires the link to be alive and
the MCU to be listening. Because Drive is the de-energized default and there
is no brake, this vehicle has no passive safe state. That is the single most
important fact on this page, and it is an argument for replacing the firmware
with one that fails to neutral on serial silence.

## Steering, in detail

Answers from the team, 2026-08-11:

- The steering actuator is driven **on/off with reversing polarity**. R13 and
  R14 are the two polarity legs, which is why steering is bang-bang: the
  actuator runs while a leg is energized and stops when it is released.
- There is **no PWM speed control** on the actuator. It runs at one speed.
- **An angle sensor exists but is currently DISCONNECTED.**
- What limits over-travel is **that same steering feedback sensor**.

Read those last two together, because together they are a problem. The part
that stops the actuator running past its travel is the part that is unplugged.
With the sensor disconnected, holding a steering relay drives the actuator
into its mechanical stop with nothing commanding it to stop, every time. That
risks a stalled actuator, a burnt motor, a damaged linkage, or a blown fuse,
and it happens on every long press from the existing console today.

**Reconnecting the steering angle sensor is the highest-value hardware fix on
this vehicle.** It buys two things at once:

1. Over-travel protection comes back.
2. It gives closed-loop feedback, which means proportional steering can be
   built in SOFTWARE on top of the existing relays: pulse a leg, read the
   angle, stop at the target. Same hardware, real steering.

Until then, an adapter must treat steering as open-loop and time-limited: no
steering pulse longer than a conservative fixed duration, and never a
continuous hold.

**Never energize R13 and R14 at the same time.** They are the two polarity
legs of one actuator, so simultaneous energization is at best undefined and at
worst a short across the driver. The adapter must enforce mutual exclusion in
code, not by convention.

## Corroboration

The relay map arrived from the team with no supporting documents. It has since
been cross-checked against the code on the Jetson, which was written by people
who had never seen it:

- **Twelve of the fourteen relays** have a matching named command in
  `ros2_new`'s `commands.js` (ring light, both indicators, reverse, neutral,
  high beam, low beam, horn, speed 1, speed 3, steer right, steer left). An
  unusual name like "ring light" appearing independently in both is not
  coincidence. The functional inventory is corroborated. The exact wire
  tokens are still unverified.
- **Steering is bang-bang in three independent artifacts.** That console uses
  a press-and-hold control that sends steer-left on press and centre on
  release, which is relay behaviour, not slider behaviour. The older Remo UI
  did the same. Now the team confirms reversing polarity. Three sources, one
  answer.
- **The 42 offset holds up.** The relay tester's PWM slider is 42 to 214, and
  the ros2 console's acceleration control is 0 to 172. The widths match
  exactly. Still a hypothesis, but a well-supported one.
- **Drive as the de-energized default** is corroborated: the console offers
  gear D, N and R while relays exist only for reverse and neutral, so D can
  only mean energize neither.

## The existing console is not safe to drive with

The `ros2_new` web console exposes three controls this hardware cannot
perform, and warns about none of them:

- A **brake slider** with 16 levels, styled in stop-red. Both brake relays are
  disconnected. The operator drags it and nothing slows.
- A **latching E-stop button** that sets the UI to "stopped" and emits a token
  no relay implements. An E-stop that reports success and does nothing is
  worse than no button at all, because it will be trusted at the exact moment
  it matters.
- A **park toggle** with no relay behind it. Its hazard-lights half does work.

Speed 2 and gear D are also offered with no relay behind them.

Nobody should drive this vehicle from that console until those controls are
removed or visibly disabled. This is the waterline law with a physical
consequence: a control that lies to the operator is worse than an absent one.

## No component asserts a safe state, ever

None of the three host programs on the Jetson writes anything to the MCU on
connect, on disconnect, or on error. They are all pure byte pipes. The ROS
node raises an alert to a human on link loss but sends no command to the
vehicle. So after a crashed browser or a pulled cable, the vehicle holds
whatever it was last told.

Combined with drive being the de-energized default and there being no brake,
**this body has no passive safe state today.**

It does have a reachable one. R5 is neutral. So the highest-value line in the
adapter is "assert neutral", and it must run on startup, on client
disconnect, on watchdog trip, and on self-test failure. Nothing does that
today.

## THE FIRMWARE, read 2026-08-11

The team supplied the sketch (`bodies/ugv-01/firmware/ugv01_mcu.ino`) and
confirmed they had just driven the vehicle with it: throttle, lights and
steering all responding from a laptop. It corroborates the wire protocol we
had reconstructed independently. Treat it as the running firmware.

It is 70 lines. Reading it settles most of this document and changes two
things we believed.

### 1. There is no failsafe. On link loss the vehicle holds throttle forever.

```cpp
void loop() {
  if(!Serial.available()) return;
  ...
}
```

That is the entire loop. It acts only when a byte arrives. There is no
`millis()`, no timeout, no watchdog, no heartbeat, nowhere in the sketch.

So if the USB cable falls out at throttle 150, the PWM stays at 150 and the
relays stay latched **indefinitely**. Not until a timeout. Not degrading.
Forever, until something removes power.

This is the most important fact about this vehicle, and it invalidates an
assumption in our own design. The bridge watchdog can command a safe stop on
OPERATOR silence, because the link is still up. It can do nothing about LINK
LOSS, because the safe stop it wants to send is exactly what cannot be
delivered. On this body, in that failure mode, there is no software anywhere
that can stop the vehicle.

**The fix is about ten lines of firmware** and it is now writable, because we
have the source: record `millis()` on every accepted command, and in `loop()`
when the gap exceeds a timeout, `analogWrite(pwmPin,42)` and either release
every relay or assert the neutral relay. That single change gives this vehicle
a passive safe state for the first time.

### 2. The MCU never transmits. There is no telemetry at all.

`Serial.begin(115200)` is called and `Serial.print` is never called, anywhere.
The board is receive-only in practice. Consequences:

- **Reconnecting the steering angle sensor changes nothing on its own.** This
  firmware reads no analog input and reports no angle. The sensor can be
  perfectly wired and the software will never see it. Earlier notes in this
  repo said reconnecting the sensor would give us feedback for proportional
  steering; that was wrong as written. It requires the sensor **and** a
  firmware change to read it and emit it.
- **"The steering feedback sensor limits travel" cannot be true in this
  firmware.** Nothing reads any sensor. If over-travel is limited, it is
  limited mechanically or electrically, not in code. Ask the team again,
  because one of the two statements does not hold.
- `parseTelemetry()` in the ros2 console parses a stream that does not exist.
- No battery, no gear state, no speed, no acknowledgement of any command. The
  bridge cannot confirm that anything it sent was applied.

Note also that A0 through A3 are used as relay **outputs** here, so the free
analog inputs for a future angle sensor are A4 and A5.

### 3. Relays are active LOW

```cpp
digitalWrite(relayPins[i],HIGH);          // setup: HIGH means OFF
digitalWrite(relayPins[relay-1], state ? LOW : HIGH);
```

The wire protocol is unchanged (`R51` energizes relay 5), but on the board a
de-energized relay reads HIGH. Anyone metering the board should know that
before concluding a relay is stuck on.

### 4. Power-on state is now known, and it makes the bench session safer

`setup()` drives all fourteen relays OFF and writes PWM 42. So a reset, whether
from power-up or from the FTDI DTR pulse when a port is opened, produces:
throttle at rest, every relay released, steering legs released.

Read against the team's map, all relays released also means **not in neutral**,
because neutral is an energized relay. So a reset leaves the vehicle in drive
at idle.

The practical consequence is good news for the bench: opening the serial port
at standstill causes a reset that drops throttle to rest and releases
everything. That is close to a stop, not a lurch. It remains true that this
must be done with drive power isolated or wheels up, because "close to a stop"
is not a guarantee and the gear outcome is drive.

### 5. The board is an ATmega328P class Arduino

Pins 2 to 12 plus A0 to A3, PWM on pin 9 with `TCCR1B` reprogrammed, pin 13
left free. That is an Uno or a Nano. The Timer1 prescaler is set to 1, giving
roughly 31 kHz PWM on pin 9, which is above audible and typical for driving a
motor controller.

This also tells us the toolchain (`arduino-cli` or the Arduino IDE with an
AVR core), and that flashing is over the same USB serial port, via the
bootloader. No programmer is required.

### 6. Parsing is fragile, but it fails toward idle

`toInt()` returns 0 for anything non-numeric, so a corrupted `P` command
becomes `constrain(0,42,214)` which is 42, that is rest. A corrupted `R`
command usually resolves to relay 0 or state 0 and is either ignored or turns
a relay off. There is no checksum and no acknowledgement, so corruption is
silent, but its bias is toward off rather than toward on. That is luck rather
than design, and it should not be relied on.

### 7. Confirmed absent in firmware

No ignition, no e-stop, no brake logic, no gear interlock, no speed limiting,
no sequencing between relays. The console's E-stop button provably does
nothing: there is no code path for it.

## Answers from the developer, 2026-08-11

- **The board is an Arduino Nano.** Confirms the ATmega328P reading from the
  pin map. Flashing is over the same USB cable, bootloader, no programmer.
- **R9 and R10 are one brake actuator, driven by polarity reversal.** One
  relay drives it forward, the other reverses it. Identical pattern to the
  steering legs on R13/R14. The console's sixteen "brake levels" were brake
  POSITION, not sixteen relay states, which resolves the arithmetic problem
  recorded above.
- **The emergency stop is the ignition key.** A physical key, turned by a
  person at the vehicle. There is no remote kill and there never was.
- **On cable loss the MCU keeps doing the last command.** The developer
  confirms this independently of our reading of the source. Both agree.
- **Steering feedback exists and is already being read somewhere.** Reported
  as 0 at centre, negative to the right and positive to the left, with about
  ten positions per side and a least count near 3 degrees. Exact range needs
  confirming: the description gives both "up to 5" and "10 positions each
  side", which cannot both be counts of the same thing.
- **The developer offers to emit telemetry in any format we specify.** That is
  an invitation to design the uplink properly rather than inherit one.

### What follows from the brake being a polarity-reversal actuator

Brake is bang-bang exactly like steering, so the same two rules apply to it:
R9 and R10 must be mutually exclusive in code, and brake pulses must be
time-limited unless position is being read back. It also means braking is
positional rather than proportional-by-command: the host asks for a position
and something has to drive the actuator until it arrives.

### Travel limits belong in the firmware, not the host

Both steering and brake are actuators with end stops and no software limit
today. Enforcing those limits from the host is wrong for the same reason the
failsafe had to move into firmware: the host link can drop mid-pulse, and an
actuator driving into its stop with nobody watching is exactly the damage
mechanism we already identified. The MCU reads the position, so the MCU should
refuse to drive past the limit regardless of what it is told.

### The uplink format we asked for

Line-based ASCII, newline terminated, key=value pairs separated by spaces, at
about 10 Hz. Raw counts only, never pre-converted degrees, with the scale
declared once so the host does the conversion and can be corrected without a
reflash. Unknown keys must be ignored by consumers rather than treated as
errors, which is the same open-vocabulary rule the LINK contract uses.

This format is deliberately compatible with `parseTelemetry()` in the existing
ros2 console, which already scans for `steer=`. That console starts showing a
live steering angle the moment the firmware emits one, with no changes.

## Verify this document before anything relies on it

Everything above came from the team verbally, relayed through two sessions,
then cross-checked against code. No firmware has been read. No serial port has
been opened. No relay has been observed firing. The cross-checking raises
confidence in the inventory, but it cannot turn a verbal description into an
observation, and this file now reads with more authority than its provenance
earns.

The first bench session, drive power isolated and wheels off the ground,
verifies the map before any of it reaches a driver. Order matters:

1. **R5 really is neutral.** Verify this first and alone. The whole failsafe
   design rests on it, so it is the one that must not be wrong. If R5 is not
   neutral, `safe_stop()` as designed makes things worse rather than better.
2. Reverse on R4, and what gear the vehicle is in with every relay released.
   That confirms or kills the de-energized-drive reading.
3. Each remaining relay, one at a time, with a human watching and listening.
   That also settles what Speed 2 is.
4. Throttle at P42 versus above it, to test the +42 offset arithmetic.
5. Steering legs last, briefly, and never both.

## A consumer for steering angle already exists

Reconnecting the angle sensor is cheaper than it sounds because the software
side is already written and running against nothing. `parseTelemetry()` in
`commands.js` scans every incoming serial line for `steer=`, `steering=` or
`angle=` and publishes a `steer` field that the console renders in degrees.
So the work is a hardware reconnection plus firmware emitting the field. It is
not a software project.

## Still unknown

- What the MCU does on serial silence: failsafe or hold last command
- Telemetry: what the MCU sends up, in what format, if anything
- Whether Speed 1, Speed 3 and the throttle PWM interact or override
- Whether both steering relays energized at once is safe or a short
- The board itself: which microcontroller, and whether its flash can be read
  back before anyone considers reflashing it
