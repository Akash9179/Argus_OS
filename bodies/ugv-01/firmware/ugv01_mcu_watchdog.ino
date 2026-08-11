// ugv-01 MCU firmware, with a link-loss failsafe.
//
// WHAT CHANGED, and why it matters
// --------------------------------
// The firmware currently on the vehicle has no timeout of any kind. Its loop
// does nothing unless a serial byte is waiting. So if the USB cable falls out
// at throttle 150, the vehicle stays at throttle 150 indefinitely, until
// someone removes power. Nothing in software can stop it, because the stop
// command cannot be delivered over the cable that just failed.
//
// This version adds that missing timeout. If no command arrives for
// LINK_TIMEOUT_MS, the board puts itself into a safe state on its own:
// throttle to rest, steering released, neutral engaged. Lights are left
// alone deliberately, because going dark is its own hazard.
//
// READ THIS BEFORE FLASHING
// -------------------------
// 1. THIS BREAKS THE EXISTING WEB CONSOLE unless the console is updated.
//    That console only sends when the operator moves a control, so holding a
//    steady throttle sends nothing and the failsafe would trip mid-drive.
//    The host MUST send a keepalive. This sketch accepts "H" for that: it
//    resets the timer and does nothing else. Send it every 200 ms.
//    One line in the browser console does it:
//        setInterval(() => send('H'), 200);
//
// 2. THE RELAY NUMBERS BELOW ARE UNVERIFIED. They come from the team's map,
//    not from anything anyone has watched happen. If RELAY_NEUTRAL is wrong,
//    the failsafe energises the wrong thing at the worst moment. Verify on
//    the bench, wheels off the ground, before trusting this.
//
// 3. Flash and test with the wheels off the ground or the drive power
//    isolated, and a person at the vehicle. Test the failsafe deliberately:
//    command a throttle, then unplug the USB cable, and confirm the vehicle
//    goes to rest and out of gear.
//
// The command protocol is otherwise unchanged: R<n><0|1> and P<42..214>.

const byte relayPins[14] = {
  2,3,4,5,6,7,8,10,11,12,A0,A1,A2,A3
};

const byte pwmPin = 9;

// ---- failsafe configuration: VERIFY THESE AGAINST THE VEHICLE ----
const int RELAY_NEUTRAL     = 5;    // team's map: 5 = neutral
const int RELAY_STEER_RIGHT = 13;   // team's map: 13 = steering right
const int RELAY_STEER_LEFT  = 14;   // team's map: 14 = steering left
const unsigned long LINK_TIMEOUT_MS = 600;   // 3 missed 200ms keepalives
const int THROTTLE_REST = 42;       // firmware's own rest value, not 0

unsigned long lastCommandMs = 0;
bool failsafeActive = false;

void setRelay(int relay, bool on) {
  if (relay < 1 || relay > 14) return;
  digitalWrite(relayPins[relay - 1], on ? LOW : HIGH);   // relays are active LOW
}

void enterFailsafe() {
  analogWrite(pwmPin, THROTTLE_REST);
  setRelay(RELAY_STEER_RIGHT, false);
  setRelay(RELAY_STEER_LEFT, false);
  setRelay(RELAY_NEUTRAL, true);
  failsafeActive = true;
  Serial.println("FAILSAFE");   // the board's first ever transmission
}

void setup() {

  Serial.begin(115200);
  Serial.setTimeout(50);   // so a partial line cannot block the failsafe check

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

  // the whole point of this version
  if (!failsafeActive && (millis() - lastCommandMs) > LINK_TIMEOUT_MS) {
    enterFailsafe();
  }

  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd.length() == 0) return;

  // any valid traffic proves the link is alive
  lastCommandMs = millis();
  failsafeActive = false;

  if (cmd == "H") return;   // keepalive, nothing else

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
