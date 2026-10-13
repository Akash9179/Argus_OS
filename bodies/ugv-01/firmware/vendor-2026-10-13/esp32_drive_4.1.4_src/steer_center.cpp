#include "steer_center.h"
#include "config.h"
#include "feedback.h"
#include "actuators.h"
#include "angle_limits.h"
#include "serial_protocol.h"

#define CTR_CMD        0x14
#define CTR_FB_MISSES  5

static bool     active = false;
static bool     started = false;
static uint16_t target = 0;
static uint16_t prev = 0;
static uint8_t  dir = 1;
static uint8_t  awayCount = 0;
static bool     flipped = false;
static uint8_t  missCount = 0;
static unsigned long startMs = 0;

static void finish(const char* status, const char* data) {
    actSetSteer(0);
    active = false;
    started = false;
    serialReply(CTR_CMD, status, data);
}

bool ctrStart() {
    if (active) return false;

    target     = limitsSteerCenter();
    if (steerValid()) {
        uint16_t v = steerValue();
        dir        = (v > target) ? 2 : 1;
        prev       = v;
    } else {
        dir        = 1;
        prev       = target;
    }
    awayCount  = 0;
    flipped    = false;
    missCount  = 0;
    started    = false;
    startMs    = millis();
    active     = true;
    return true;
}

bool ctrActive() {
    return active;
}

void ctrCancel() {
    active = false;
    started = false;
}

void ctrUpdate() {
    if (!active) return;

    if (!steerValid()) {
        if (++missCount >= CTR_FB_MISSES) {
            finish("ERR", "NO_SIGNAL");
            return;
        }
    } else {
        missCount = 0;
    }

    if (millis() - startMs > CTR_TIMEOUT_MS) {
        finish("ERR", "TIMEOUT");
        return;
    }

    uint16_t v = steerValue();
    int32_t d = (int32_t)v - (int32_t)target;
    if (d < 0) d = -d;

    if (d <= STEER_CTR_TOL) {
        finish("OK", "02");
        return;
    }

    if (started) {
        int32_t pd = (int32_t)prev - (int32_t)target;
        if (pd < 0) pd = -pd;

        if (d > pd) {
            if (++awayCount >= 2 && !flipped) {
                dir = (dir == 1) ? 2 : 1;
                flipped = true;
                awayCount = 0;
            }
        } else {
            awayCount = 0;
        }
    }

    prev = v;
    started = true;

    const char* why = limitsBlockReason(dir);
    if (why) {
        finish("ERR", why);
        return;
    }

    if (actSteerState() != dir) actSetSteer(dir);
}
