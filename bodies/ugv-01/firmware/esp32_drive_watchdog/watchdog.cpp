#include "watchdog.h"
#include "config.h"
#include "actuators.h"
#include "feedback.h"
#include "steer_center.h"
#include <Arduino.h>

// Same levels as actuators.cpp; the pins come from config.h.
#define WD_RELAY_OFF HIGH

static uint32_t lastAcceptedMs = 0;
static uint32_t steerNoSignalSince = 0;
static uint32_t brakeNoSignalSince = 0;
static uint16_t lastSteer = 0;
static uint16_t lastBrake = 0;
static bool haveLastSteer = false;
static bool haveLastBrake = false;
static uint8_t timeouts = 0;
static bool tripped = false;

static void allOff(const char* why) {
    // every relay off in the same instant, no break-before-make delay
    digitalWrite(STEER_LEFT_PIN, WD_RELAY_OFF);
    digitalWrite(STEER_RIGHT_PIN, WD_RELAY_OFF);
    digitalWrite(BRAKE_FWD_PIN, WD_RELAY_OFF);
    digitalWrite(BRAKE_REV_PIN, WD_RELAY_OFF);
    ctrCancel();
    actSetSteer(0);     // keeps the actuator state honest; pins are already off
    actSetBrake(0);
    tripped = true;
    if (timeouts < 0xFF) timeouts++;
    Serial.printf("0x00;WD;%s\n", why);
}

static uint16_t absDiff(uint16_t a, uint16_t b) { return a > b ? a - b : b - a; }

// A sensor is trusted while an actuator is on only if it answers and its
// reading moves plausibly. One valid-looking sample after a dropout does
// not restore trust: a jump larger than WD_MAX_STEP between samples is
// treated as no signal (the horn produces exactly that).
static bool sensorBad(bool valid, uint16_t value, uint16_t& last, bool& haveLast, uint32_t& since, uint32_t now) {
    if (!valid) {
        haveLast = false;
        if (since == 0) since = now;
        return (uint32_t)(now - since) > WD_NO_SIGNAL_MS;
    }
    if (haveLast && absDiff(value, last) > WD_MAX_STEP) {
        haveLast = false;               // implausible: do not trust until it settles
        if (since == 0) since = now;
        return (uint32_t)(now - since) > WD_NO_SIGNAL_MS;
    }
    last = value; haveLast = true; since = 0;
    return false;
}

void wdNoteAccepted() {
    lastAcceptedMs = millis();
}

void wdUpdate() {
    uint32_t now = millis();
    bool steerOn = actSteerState() != 0;
    bool brakeOn = actBrakeState() != 0;
    bool moving = steerOn || brakeOn || ctrActive();

    if (steerOn || ctrActive()) {
        if (sensorBad(steerValid(), steerValue(), lastSteer, haveLastSteer, steerNoSignalSince, now)) {
            allOff("NO_SIGNAL"); steerNoSignalSince = 0; return;
        }
    } else {
        steerNoSignalSince = 0; haveLastSteer = false;
    }
    if (brakeOn) {
        if (sensorBad(brakeValid(), brakeValue(), lastBrake, haveLastBrake, brakeNoSignalSince, now)) {
            allOff("NO_SIGNAL"); brakeNoSignalSince = 0; return;
        }
    } else {
        brakeNoSignalSince = 0; haveLastBrake = false;
    }

    // silence: an accepted command within the window, or everything off
    if (moving && !tripped && (uint32_t)(now - lastAcceptedMs) > WD_TIMEOUT_MS) {
        allOff("TIMEOUT");
    }
}

bool wdMoveAllowed() { return !tripped; }
void wdClear() { tripped = false; lastAcceptedMs = millis(); }
uint8_t wdTimeouts() { return timeouts; }
bool wdTripped() { return tripped; }
