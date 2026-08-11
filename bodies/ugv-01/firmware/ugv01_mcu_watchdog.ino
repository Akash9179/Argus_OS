// ugv-01 MCU firmware v3: link-loss failsafe, without breaking anything that
// works today.
//
// THE PROBLEM THIS FIXES
// ----------------------
// The firmware on the vehicle has no timeout of any kind. Its loop does
// nothing unless a serial byte is waiting. If the USB cable falls out at
// throttle 150, the vehicle stays at throttle 150 indefinitely, until someone
// removes power. The developer confirms this independently: "it keeps doing
// the last command". No software can stop it, because the stop command cannot
// be delivered over the cable that just failed.
//
// DESIGN RULE: NOTHING THAT WORKS TODAY MAY STOP WORKING
// ------------------------------------------------------
// The existing web console only transmits when an operator moves a control,
// so a naive watchdog would trip mid-drive and be worse than none.
//
// This watchdog therefore stays ASLEEP until it receives its first "H"
// keepalive. Until then the firmware behaves exactly like the current one.
//
//   Old console, never sends H  ->  watchdog never arms, behaviour unchanged
//   Updated host, sends H       ->  watchdog arms and protects, automatically
//
// Send "H" every 200 ms. In a browser:  setInterval(() => send('H'), 200);
//
// v3 CHANGES, all four from review of v2
// --------------------------------------
// 1. THE WATCHDOG IS NO LONGER FED BY NOISE. v2 reset its timer on any
//    non-empty line. A failing USB connector on a vibrating vehicle does not
//    go cleanly silent: it produces framing errors and junk bytes, and every
//    junk line would have convinced the watchdog the link was healthy. The
//    exact failure this exists to catch was the one most able to suppress it.
//    Now only RECOGNISED commands feed the timer.
// 2. It emits ALERT:FAILSAFE, not FAILSAFE. The ros2 console raises alerts on
//    lines containing ERR, FAULT or ALERT. "FAILSAFE" matched none of them, so
//    the most important thing this board can ever say would have arrived as
//    ordinary chatter with the alert rail silent.
// 3. THE FAILSAFE NOW LATCHES until an explicit "C". v2 cleared it on the next
//    byte. The bridge above it treats a safety stop as a state a human must
//    deliberately leave, so a firmware that self-clears makes the two layers
//    disagree about what a failsafe is. While latched, throttle is held at
//    rest and the steering legs will not energise. Brake, lights, horn and
//    gear still work, because those are not how you get hurt.
// 4. See the reset warning below.
//
// THE RESET WINDOW IS NOT SAFE, EVEN THOUGH THE POWER-ON STATE IS
// ---------------------------------------------------------------
// After setup() runs, all relays are released and PWM is at rest. But DURING
// a reset, before setup() executes, every pin is a high-impedance INPUT. On a
// Nano bootloader that window is one to two seconds. What the relays do in
// that window is decided by the relay board's own pull resistors and opto
// bias, which nobody has characterised. Opening the USB serial port can cause
// exactly this reset.
//
// So: first connection to this board, and first flash, WHEELS OFF THE GROUND.
// Not merely drive power isolated.
//
// WHAT THE FAILSAFE DOES NOT DO
// -----------------------------
// It does not energise any relay. Engaging neutral would be better, but
// neutral is relay 5 according to a verbal map nobody has watched happen, and
// energising an unverified relay during a link failure adds a failure mode
// while fixing one. After the bench confirms relay 5, set
// ENGAGE_NEUTRAL_ON_FAILSAFE to 1 and reflash. Also verify once what neutral
// does at speed: coasting is the intended outcome, but observe it rather than
// assume it.
//
// STEERING FEEDBACK, WHEN YOU ADD IT
// ----------------------------------
// A0 to A3 are used as relay outputs here, so they are not available for a
// potentiometer. On a Nano, A6 and A7 are analog-input-only pins and are the
// natural choice. A4 and A5 work but are also the I2C pins.
// Please emit position as RAW COUNTS, never pre-converted degrees, as
// key=value pairs on their own line at about 10 Hz, for example:
//     steer=-3 brake=7 pwm=150 fs=0
// Raw counts plus a stated scale let the host be corrected without a reflash.
// `steer=` is deliberate: the existing console already scans for it, so it
// will display a live angle with no changes on its side.
// And enforce the travel limits HERE, in firmware, not in the host. The link
// can drop mid-pulse, and an actuator driving into its stop with nobody
// watching is the damage mechanism we are trying to remove.
//
// Protocol unchanged: R<n><0|1> and P<42..214>.
// Added, all optional and harmless to ignore:
//     H = keepalive    V = version    C = clear a latched failsafe

#define FIRMWARE_VERSION "ugv01-mcu v3 watchdog"

// Set to 1 ONLY after the bench session has confirmed relay 5 is neutral.
#define ENGAGE_NEUTRAL_ON_FAILSAFE 0

const byte relayPins[14] = {
  2,3,4,5,6,7,8,10,11,12,A0,A1,A2,A3
};

const byte pwmPin = 9;

// ---- failsafe configuration ----
const int RELAY_NEUTRAL     = 5;    // team's map, UNVERIFIED
const int RELAY_STEER_RIGHT = 13;   // team's map, UNVERIFIED
const int RELAY_STEER_LEFT  = 14;   // team's map, UNVERIFIED
const unsigned long LINK_TIMEOUT_MS = 600;   // 3 missed 200ms keepalives
const int THROTTLE_REST = 42;       // this firmware's rest value, not 0

unsigned long lastCommandMs = 0;
bool watchdogArmed  = false;   // false until the first "H" is ever seen
bool failsafeActive = false;   // latched; only "C" clears it

void feed() {                  // ONLY recognised commands may call this
  lastCommandMs = millis();
}

void setRelay(int relay, bool on) {
  if (relay < 1 || relay > 14) return;
  digitalWrite(relayPins[relay - 1], on ? LOW : HIGH);   // relays are active LOW
}

void enterFailsafe() {
  analogWrite(pwmPin, THROTTLE_REST);
  setRelay(RELAY_STEER_RIGHT, false);
  setRelay(RELAY_STEER_LEFT, false);
#if ENGAGE_NEUTRAL_ON_FAILSAFE
  setRelay(RELAY_NEUTRAL, true);
#endif
  failsafeActive = true;
  Serial.println("ALERT:FAILSAFE");
}

void setup() {

  Serial.begin(115200);
  Serial.setTimeout(100);   // so a partial line cannot stall the failsafe check

  for (int i = 0; i < 14; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], HIGH);
  }

  pinMode(pwmPin, OUTPUT);

  TCCR1B = (TCCR1B & 0b11111000) | 0x01;

  analogWrite(pwmPin, 42);

  lastCommandMs = millis();
}

void loop() {

  if (watchdogArmed && !failsafeActive &&
      (millis() - lastCommandMs) > LINK_TIMEOUT_MS) {
    enterFailsafe();
  }

  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd.length() == 0) return;

  if (cmd == "H") {                 // keepalive; the first one arms the watchdog
    watchdogArmed = true;
    feed();
    return;
  }

  if (cmd == "V") {
    feed();
    Serial.println(FIRMWARE_VERSION);
    return;
  }

  if (cmd == "C") {                 // explicit clear, the only way out of a latch
    feed();
    failsafeActive = false;
    Serial.println("CLEARED");
    return;
  }

  if (cmd.startsWith("P")) {

    int value = cmd.substring(1).toInt();

    value = constrain(value, 42, 214);

    if (failsafeActive) value = THROTTLE_REST;   // latched: no motion until C

    analogWrite(pwmPin, value);

    feed();

    return;
  }

  if (cmd.startsWith("R")) {

    int len = cmd.length();

    int state = cmd.substring(len - 1).toInt();

    int relay = cmd.substring(1, len - 1).toInt();

    if (relay >= 1 && relay <= 14) {

      bool steering = (relay == RELAY_STEER_LEFT || relay == RELAY_STEER_RIGHT);

      // While latched, refuse to energise steering. Brake, lights, horn and
      // gear still pass: those are not how the vehicle hurts anyone.
      if (!(failsafeActive && state && steering)) {
        digitalWrite(
          relayPins[relay - 1],
          state ? LOW : HIGH
        );
      }

      feed();
    }

    return;
  }

  // Unrecognised input deliberately does NOT feed the watchdog.
}
