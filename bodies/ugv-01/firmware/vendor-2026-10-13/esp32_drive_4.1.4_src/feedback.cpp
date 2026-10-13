#include "feedback.h"
#include "config.h"

#define PULSE_TIMEOUT 2000UL
#define NODE_PERIOD   50

static volatile uint16_t brakeRaw = 0;
static volatile bool     brakeOk  = false;
static volatile uint16_t steerRaw = 0;
static volatile bool     steerOk  = false;

static bool readDuty(uint8_t pin, float& duty) {
    unsigned long hi = pulseIn(pin, HIGH, PULSE_TIMEOUT);
    unsigned long lo = pulseIn(pin, LOW, PULSE_TIMEOUT);
    if (hi == 0 || lo == 0) return false;
    duty = (float)hi / (float)(hi + lo);
    return true;
}

static void brakeTask(void*) {
    float d;
    for (;;) {
        if (readDuty(BRAKE_FB_PIN, d)) {
            float deg = d * 3600.0f;
            if (deg < 0) deg = 0;
            if (deg > BRAKE_FB_MAX) deg = BRAKE_FB_MAX;
            brakeRaw = (uint16_t)(deg + 0.5f);
            brakeOk  = true;
        } else {
            brakeOk = false;
        }
        vTaskDelay(pdMS_TO_TICKS(NODE_PERIOD));
    }
}

static void steerTask(void*) {
    float d;
    for (;;) {
        if (readDuty(STEER_FB_PIN, d)) {
            float deg = d * 3600.0f;
            if (deg < 0) deg = 0;
            if (deg > STEER_FB_MAX) deg = STEER_FB_MAX;
            steerRaw = (uint16_t)(deg + 0.5f);
            steerOk  = true;
        } else {
            steerOk = false;
        }
        vTaskDelay(pdMS_TO_TICKS(NODE_PERIOD));
    }
}

void feedbackBegin() {
    pinMode(BRAKE_FB_PIN, INPUT);
    pinMode(STEER_FB_PIN, INPUT);

    xTaskCreatePinnedToCore(brakeTask, "brake_fb", 4096, nullptr, 1, nullptr, 0);
    xTaskCreatePinnedToCore(steerTask, "steer_fb", 4096, nullptr, 1, nullptr, 0);
}

bool brakeValid() {
    return brakeOk;
}

uint16_t brakeValue() {
    return brakeRaw;
}

bool steerValid() {
    return steerOk;
}

uint16_t steerValue() {
    return steerRaw;
}
