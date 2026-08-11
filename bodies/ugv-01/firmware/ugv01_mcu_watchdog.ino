// ugv-01 MCU firmware v2: adds a link-loss failsafe WITHOUT breaking anything
// that works today.
//
// THE PROBLEM THIS FIXES
// ----------------------
// The firmware on the vehicle has no timeout of any kind. Its loop does
// nothing unless a serial byte is waiting. If the USB cable falls out at
// throttle 150, the vehicle stays at throttle 150 indefinitely, until someone
// removes power. No software anywhere can stop it, because the stop command
// cannot be delivered over the cable that just failed.
//
// THE DESIGN RULE HERE: NOTHING THAT WORKS TODAY MAY STOP WORKING
// ---------------------------------------------------------------
// The existing web console only transmits when an operator moves a control.
// Holding a steady throttle sends nothing. So a naive watchdog would trip
// mid-drive and would be worse than no watchdog at all.
//
// So the watchdog DISARMS ITSELF until it has proof the host can keep it fed.
// It stays asleep until it receives its first "H" keepalive. Until then this
// firmware behaves EXACTLY like the current one, byte for byte.
//
//   Old console, never sends H  ->  watchdog never arms, behaviour unchanged
//   Updated host, sends H       ->  watchdog arms and protects, automatically
//
// No flag to remember, no way to get it wrong, and the protection switches on
// the moment the host is ready for it. Send "H" every 200 ms. In a browser:
//     setInterval(() => send('H'), 200);
//
// WHAT THE FAILSAFE DOES, AND WHAT IT DELIBERATELY DOES NOT DO
// ------------------------------------------------------------
// On timeout it does only things that are unambiguously "stop doing
// something": throttle to rest, both steering legs released. It does NOT
// energise any relay by default.
//
// That is deliberate. Engaging neutral would be better, but neutral is relay 5
// only according to a verbal map that nobody has watched happen. Energising an
// unverified relay during a link failure would be introducing a new failure
// mode while fixing one. Once the bench session confirms relay 5 really is
// neutral, set ENGAGE_NEUTRAL_ON_FAILSAFE to 1 below and reflash. That is the
// version worth running long term.
//
// BEFORE FLASHING
// ---------------
// Wheels off the ground or drive power isolated, and a person at the vehicle.
// Then test the failsafe on purpose: send H for a few seconds, command a
// throttle, pull the USB cable, and confirm the vehicle drops to rest.
//
// Protocol is otherwise unchanged: R<n><0|1> and P<42..214>.
// New, both optional and harmless to ignore:  H = keepalive,  V = version.

#define FIRMWARE_VERSION "ugv01-mcu v2 watchdog"

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
bool watchdogArmed  = false;   // stays false until the first "H" ever seen
bool failsafeActive = false;

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
  Serial.println("FAILSAFE");
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

  // Only ever runs for a host that has proven it sends keepalives.
  if (watchdogArmed && !failsafeActive &&
      (millis() - lastCommandMs) > LINK_TIMEOUT_MS) {
    enterFailsafe();
  }

  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd.length() == 0) return;

  // any valid traffic proves the link is alive
  lastCommandMs = millis();
  failsafeActive = false;

  if (cmd == "H") {         // keepalive. First one ever seen arms the watchdog.
    watchdogArmed = true;
    return;
  }

  if (cmd == "V") {         // so a host can tell which firmware is flashed
    Serial.println(FIRMWARE_VERSION);
    return;
  }

  if (cmd.startsWith("P")) {

    int value = cmd.substring(1).toInt();

    value = constrain(value, 42, 214);

    analogWrite(pwmPin, value);

    return;
  }

  if (cmd.startsWith("R")) {

    int len = cmd.length();

    int state = cmd.substring(len - 1).toInt();

    int relay = cmd.substring(1, len - 1).toInt();

    if (relay >= 1 && relay <= 14) {

      digitalWrite(
        relayPins[relay - 1],
        state ? LOW : HIGH
      );

    }

  }

}
