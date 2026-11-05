// ugv-01 throttle board, firmware AC 1.4: AC 1.3 (AC 1.2 by Gulshan Shah,
// 13 Oct 2026, plus the ARGUS silence watchdog of 14 Oct) with the
// watchdog's authority narrowed. The logic is in throttle_logic.h and is
// tested on a laptop; this file is only the Arduino glue.
//
// Changes from AC 1.3:
//   - only a duty frame (0x02) or the explicit keepalive (0x04) refreshes
//     the watchdog; INFO (0x01) and the read-back (0x03) are polls and
//     refresh nothing
//   - new 0x04 keepalive: answers 0x04;OK;<duty>;<timeouts>, same data as
//     the read-back
//   - identity reports AC0104
// Unchanged from AC 1.3: while duty > 0 the deadline is 800 ms, the PWM
// returns to rest (42) and latches, the latch clears on an explicit
// 0x02;00; expiry is checked before every command and between bytes;
// non-blocking, bounded line reader. The PWM mapping and the Timer1
// prescaler line are AC 1.2's, unchanged.
#include "throttle_logic.h"

const byte pwmPin = 9;
static Throttle throttle;
static LineReader reader;
static int lastPwm = -1;

static void applyPwm() {
  int v = throttle.pwm();
  if (v != lastPwm) {
    analogWrite(pwmPin, v);
    lastPwm = v;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(pwmPin, OUTPUT);
  TCCR1B = (TCCR1B & 0b11111000) | 0x01;   // as AC 1.2: 31 kHz PWM on pin 9 (Timer1, not millis' Timer0)
  analogWrite(pwmPin, Throttle::PWM_REST);
  lastPwm = Throttle::PWM_REST;
}

void loop() {
  // the watchdog first, so a stop is never behind serial work
  if (throttle.tick(millis())) applyPwm();

  // at most one line per pass, at most a few bytes, then the watchdog again
  byte budget = 16;
  while (budget-- && Serial.available()) {
    if (reader.feed((char)Serial.read())) {
      char out[32];
      throttle.handleLine(reader.line(), millis(), out, sizeof(out));
      applyPwm();                             // rest first if it expired, then reply
      Serial.println(out);
      break;
    }
  }
}
