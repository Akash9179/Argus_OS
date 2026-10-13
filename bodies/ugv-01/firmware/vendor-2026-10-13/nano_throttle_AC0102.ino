// Throttle board sketch as sent by Gulshan Shah, 13 Oct 2026. Firmware AC 1.2.
// Pin 9 PWM goes straight to the motor controller's input. No watchdog.
const byte pwmPin = 9;
const byte firmwareVersion[] = {0xAC, 0x01, 0x02};
void setup() { Serial.begin(115200); pinMode(pwmPin, OUTPUT); TCCR1B = (TCCR1B & 0b11111000) | 0x01; analogWrite(pwmPin, 42); }
void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n'); cmd.trim();
  if (cmd == "0x01" || cmd == "01") { Serial.println("0x01;OK;AC0102"); return; }
  if (cmd.startsWith("0x02;") || cmd.startsWith("02;")) {
    int separator = cmd.indexOf(';'); String hexValue = cmd.substring(separator + 1);
    char *endPtr; long duty = strtol(hexValue.c_str(), &endPtr, 16);
    if (hexValue.length() == 0 || *endPtr != '\0' || duty < 0 || duty > 100) { Serial.println("0x02;ERR;INVALID_DUTY"); return; }
    int pwmValue = map(duty, 0, 100, 42, 214); pwmValue = constrain(pwmValue, 42, 214);
    analogWrite(pwmPin, pwmValue);
    char response[20]; snprintf(response, sizeof(response), "0x02;OK;%02lX", duty); Serial.println(response); return;
  }
  Serial.println("ERR;UNKNOWN_COMMAND");
}
