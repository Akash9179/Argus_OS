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

void wdNoteAccepted() {
    lastAcceptedMs = millis();
}

void wdUpdate() {
    uint32_t now = millis();
    bool steerOn = actSteerState() != 0;
    bool brakeOn = actBrakeState() != 0;
    bool moving = steerOn || brakeOn || ctrActive();

    // feedback: no reading, no motion (the horn takes the sensor down)
    if (steerOn && !steerValid()) {
        if (steerNoSignalSince == 0) steerNoSignalSince = now;
        else if ((uint32_t)(now - steerNoSignalSince) > WD_NO_SIGNAL_MS) { allOff("NO_SIGNAL"); steerNoSignalSince = 0; return; }
    } else {
        steerNoSignalSince = 0;
    }
    if (brakeOn && !brakeValid()) {
        if (brakeNoSignalSince == 0) brakeNoSignalSince = now;
        else if ((uint32_t)(now - brakeNoSignalSince) > WD_NO_SIGNAL_MS) { allOff("NO_SIGNAL"); brakeNoSignalSince = 0; return; }
    } else {
        brakeNoSignalSince = 0;
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
