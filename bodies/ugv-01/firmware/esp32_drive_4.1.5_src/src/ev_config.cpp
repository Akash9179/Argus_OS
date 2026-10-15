#include "ev_config.h"
#include "config.h"

#define OUT_ON   LOW
#define OUT_OFF  HIGH

static uint8_t speedVal = EV_SPEED_DEFAULT;
static uint8_t gearVal  = EV_GEAR_D;

static void writeSpeedPins(uint8_t speed) {
    digitalWrite(SPEED_1_PIN, (speed == 1) ? OUT_ON : OUT_OFF);
    digitalWrite(SPEED_3_PIN, (speed == 3) ? OUT_ON : OUT_OFF);
}

static void writeGearPins(uint8_t gear) {
    digitalWrite(GEAR_N_PIN, (gear == EV_GEAR_N) ? OUT_ON : OUT_OFF);
    digitalWrite(GEAR_R_PIN, (gear == EV_GEAR_R) ? OUT_ON : OUT_OFF);
}

void evBegin() {
    pinMode(SPEED_1_PIN, OUTPUT);
    pinMode(SPEED_3_PIN, OUTPUT);
    pinMode(GEAR_N_PIN, OUTPUT);
    pinMode(GEAR_R_PIN, OUTPUT);

    writeSpeedPins(speedVal);
    writeGearPins(gearVal);
}

bool evSetSpeed(uint8_t speed) {
    if (speed < 1 || speed > 3) return false;
    speedVal = speed;
    writeSpeedPins(speedVal);
    return true;
}

bool evSetGear(uint8_t gear) {
    if (gear < 1 || gear > 3) return false;
    gearVal = gear;
    writeGearPins(gearVal);
    return true;
}

uint8_t evSpeed() {
    return speedVal;
}

uint8_t evGear() {
    return gearVal;
}
