#include "lights.h"
#include "config.h"

static uint8_t mode = LIGHT_OFF_ALL;

static const uint8_t pins[3] = {
    LIGHT_RING_PIN, LIGHT_HIGH_PIN, LIGHT_LOW_PIN
};

void lightBegin() {
    for (uint8_t i = 0; i < 3; i++) digitalWrite(pins[i], LIGHT_OFF);

    pinMode(LIGHT_RING_PIN, OUTPUT);
    pinMode(LIGHT_HIGH_PIN, OUTPUT);
    pinMode(LIGHT_LOW_PIN, OUTPUT);
}

bool lightSetMode(uint8_t newMode) {
    if (newMode > LIGHT_LOW) return false;
    mode = newMode;
    for (uint8_t i = 0; i < 3; i++) {
        digitalWrite(pins[i], (mode == (i + 1)) ? LIGHT_ON : LIGHT_OFF);
    }
    return true;
}

uint8_t lightMode() {
    return mode;
}
