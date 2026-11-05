#include "horn.h"
#include "config.h"

static bool active = false;
static uint32_t deadline = 0;

static const uint32_t HORN_MS[4] = {0, 500, 1000, 2000};

void hornBegin() {
    digitalWrite(HORN_PIN, HORN_OFF);
    pinMode(HORN_PIN, OUTPUT);
}

bool hornStart(uint8_t mode) {
    if (mode < 1 || mode > 3) return false;
    digitalWrite(HORN_PIN, HORN_ON);
    active = true;
    deadline = millis() + HORN_MS[mode];
    return true;
}

void hornUpdate() {
    if (active && (int32_t)(millis() - deadline) >= 0) {
        digitalWrite(HORN_PIN, HORN_OFF);
        active = false;
    }
}

bool hornActive() {
    return active;
}
