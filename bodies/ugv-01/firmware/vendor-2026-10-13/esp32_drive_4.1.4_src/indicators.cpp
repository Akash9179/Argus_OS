#include "indicators.h"
#include "config.h"

static uint8_t mode = IND_OFF;

void indBegin() {
    digitalWrite(IND_LEFT_PIN, IND_OFF_LEVEL);
    digitalWrite(IND_RIGHT_PIN, IND_OFF_LEVEL);

    pinMode(IND_LEFT_PIN, OUTPUT);
    pinMode(IND_RIGHT_PIN, OUTPUT);
}

bool indSet(uint8_t newMode) {
    if (newMode > IND_BOTH) return false;
    mode = newMode;
    digitalWrite(IND_LEFT_PIN,  (mode == IND_LEFT || mode == IND_BOTH) ? IND_ON : IND_OFF_LEVEL);
    digitalWrite(IND_RIGHT_PIN, (mode == IND_RIGHT || mode == IND_BOTH) ? IND_ON : IND_OFF_LEVEL);
    return true;
}

uint8_t indMode() {
    return mode;
}
