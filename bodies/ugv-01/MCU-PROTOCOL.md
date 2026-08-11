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

**There is no brake.** Both brake relays are disconnected. The only way to
slow this vehicle remotely is to drop throttle to 42 and coast. Any safety
argument that assumes remote braking is false.

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

## Still unknown

- What the MCU does on serial silence: failsafe or hold last command
- Telemetry: what the MCU sends up, in what format, if anything
- Whether Speed 1, Speed 3 and the throttle PWM interact or override
- Whether both steering relays energized at once is safe or a short
- The board itself: which microcontroller, and whether its flash can be read
  back before anyone considers reflashing it
