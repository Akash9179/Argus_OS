#include "pwm_output.h"
#include "config.h"

#define RES_MAX   14
#define LEDC_CLK  40000000ULL
#define DIV_MAX   1023.99

static uint8_t  bits = 0;
static float    duty = 0.0f;

static bool configurePwm(uint32_t freq) {
    bits = 0;
    for (int b = RES_MAX; b >= 1; b--) {
        double div = (double)LEDC_CLK / ((double)freq * (double)(1UL << b));
        if (div < 1.0) continue;
        if (div > DIV_MAX) return false;
        if (ledcSetup(LEDC_CH, freq, (uint8_t)b) != 0) {
            bits = (uint8_t)b;
            return true;
        }
    }
    return false;
}

static void writeDuty() {
    if (bits == 0) {
        ledcWrite(LEDC_CH, 0);
        return;
    }
    uint32_t maxDuty = (1UL << bits) - 1UL;
    ledcWrite(LEDC_CH, (uint32_t)((duty / 100.0f) * (float)maxDuty + 0.5f));
}

void pwmBegin() {
    duty = DUTY_MIN;
    configurePwm(PWM_FREQ_HZ);
    ledcAttachPin(PWM_PIN, LEDC_CH);
    writeDuty();
}

void pwmSetAccel(float percent) {
    if (percent < DUTY_MIN) percent = DUTY_MIN;
    if (percent > DUTY_MAX) percent = DUTY_MAX;
    duty = percent;
    writeDuty();
}

void pwmOff() {
    duty = 0.0f;
    writeDuty();
}

float pwmDuty() {
    return duty;
}
