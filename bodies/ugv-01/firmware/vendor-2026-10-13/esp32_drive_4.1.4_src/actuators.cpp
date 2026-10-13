#include "actuators.h"
#include "config.h"

#define RELAY_ON   LOW
#define RELAY_OFF  HIGH
#define BREAK_MS   50

static uint8_t steerState = 0;
static uint8_t brakeState = 0;

static void switchPair(uint8_t pinA, uint8_t pinB, uint8_t dir) {
    digitalWrite(pinA, RELAY_OFF);
    digitalWrite(pinB, RELAY_OFF);
    delay(BREAK_MS);
    if (dir == 1)      digitalWrite(pinA, RELAY_ON);
    else if (dir == 2) digitalWrite(pinB, RELAY_ON);
}

void actBegin() {
    digitalWrite(STEER_LEFT_PIN, RELAY_OFF);
    digitalWrite(STEER_RIGHT_PIN, RELAY_OFF);
    digitalWrite(BRAKE_FWD_PIN, RELAY_OFF);
    digitalWrite(BRAKE_REV_PIN, RELAY_OFF);

    pinMode(STEER_LEFT_PIN, OUTPUT);
    pinMode(STEER_RIGHT_PIN, OUTPUT);
    pinMode(BRAKE_FWD_PIN, OUTPUT);
    pinMode(BRAKE_REV_PIN, OUTPUT);
}

bool actSetSteer(uint8_t dir) {
    if (dir > 2) return false;
    if (dir == steerState) return true;
    switchPair(STEER_LEFT_PIN, STEER_RIGHT_PIN, dir);
    steerState = dir;
    return true;
}

bool actSetBrake(uint8_t dir) {
    if (dir > 2) return false;
    if (dir == brakeState) return true;
    switchPair(BRAKE_FWD_PIN, BRAKE_REV_PIN, dir);
    brakeState = dir;
    return true;
}

uint8_t actSteerState() {
    return steerState;
}

uint8_t actBrakeState() {
    return brakeState;
}
