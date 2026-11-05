#include "angle_limits.h"
#include "config.h"
#include "feedback.h"
#include "actuators.h"
#include "serial_protocol.h"

#include <Preferences.h>

static Preferences prefs;
static void clearTrips();
static void clearBrakeTrips();

static uint16_t brakeMin = 0;
static uint16_t brakeMax = BRAKE_FB_MAX;
static uint16_t steerMin = 0;
static uint16_t steerMax = STEER_FB_MAX;

static bool     steerBypass = false;
static bool     brakeBypass = false;
static bool     limEnabled = true;

static void store(const char* kMin, const char* kMax, uint16_t minV, uint16_t maxV) {
    prefs.begin("limits", false);
    prefs.putUShort(kMin, minV);
    prefs.putUShort(kMax, maxV);
    prefs.end();
}

void limitsBegin() {
    prefs.begin("limits", true);
    brakeMin = prefs.getUShort("brkmin", 0);
    brakeMax = prefs.getUShort("brkmax", BRAKE_FB_MAX);
    steerMin = prefs.getUShort("smin", 0);
    steerMax = prefs.getUShort("smax", STEER_FB_MAX);
    prefs.end();

    if (brakeMin >= brakeMax || brakeMax > BRAKE_FB_MAX) {
        brakeMin = 0;
        brakeMax = BRAKE_FB_MAX;
    }
    if (steerMin >= steerMax || steerMax > STEER_FB_MAX) {
        steerMin = 0;
        steerMax = STEER_FB_MAX;
    }
}

bool limitsSetBrake(uint16_t minV, uint16_t maxV) {
    if (minV >= maxV || maxV > BRAKE_FB_MAX) return false;
    brakeMin = minV;
    brakeMax = maxV;
    store("brkmin", "brkmax", minV, maxV);
    clearBrakeTrips();
    return true;
}

bool limitsSetSteer(uint16_t minV, uint16_t maxV) {
    if (minV >= maxV || maxV > STEER_FB_MAX) return false;
    steerMin = minV;
    steerMax = maxV;
    store("smin", "smax", minV, maxV);
    clearTrips();
    return true;
}

void limitsGetBrake(uint16_t& minV, uint16_t& maxV) {
    minV = brakeMin;
    maxV = brakeMax;
}

void limitsGetSteer(uint16_t& minV, uint16_t& maxV) {
    minV = steerMin;
    maxV = steerMax;
}

uint16_t limitsSteerCenter() {
    return (uint16_t)(((uint32_t)steerMin + (uint32_t)steerMax) / 2U);
}

void limitsSteerBypass(bool on) {
    steerBypass = on;
}

void limitsBrakeBypass(bool on) {
    brakeBypass = on;
}

static bool     limitTrip = false;
static uint8_t  limitTripDir = 0;
static bool     stallTrip = false;
static uint8_t  stallTripDir = 0;
static uint16_t stallTripAngle = 0;
static bool     tracking = false;
static uint8_t  trackDir = 0;
static uint16_t trackAngle = 0;
static unsigned long trackMs = 0;

static bool     brkLimitTrip = false;
static uint8_t  brkLimitTripDir = 0;
static bool     brkStallTrip = false;
static uint8_t  brkStallTripDir = 0;
static uint16_t brkStallTripAngle = 0;
static bool     brkTracking = false;
static uint8_t  brkTrackDir = 0;
static uint16_t brkTrackAngle = 0;
static unsigned long brkTrackMs = 0;

static void clearTrips() {
    limitTrip = false;
    limitTripDir = 0;
    stallTrip = false;
    stallTripDir = 0;
}

static void clearBrakeTrips() {
    brkLimitTrip = false;
    brkLimitTripDir = 0;
    brkStallTrip = false;
    brkStallTripDir = 0;
}

void limitsSetEnabled(bool on) {
    if (on == limEnabled) return;
    limEnabled = on;
    clearTrips();
    clearBrakeTrips();
    tracking = false;
    brkTracking = false;
}

bool limitsEnabled() {
    return limEnabled;
}

const char* limitsBlockReason(uint8_t dir) {
    if (dir == 0 || !limEnabled) return nullptr;
    if (stallTrip && dir == stallTripDir) return "STALL";
    if (limitTrip && dir == limitTripDir) return "AT_LIMIT";
    if (steerBypass || !steerValid()) return nullptr;

    uint16_t v = steerValue();
    if (dir == 1 && v >= steerMax) return "AT_LIMIT";
    if (dir == 2 && v <= steerMin) return "AT_LIMIT";
    return nullptr;
}

const char* limitsBrakeBlockReason(uint8_t dir) {
    if (dir == 0 || !limEnabled) return nullptr;
    if (brkStallTrip && dir == brkStallTripDir) return "STALL";
    if (brkLimitTrip && dir == brkLimitTripDir) return "AT_LIMIT";
    if (brakeBypass || !brakeValid()) return nullptr;

    uint16_t v = brakeValue();
    if (dir == 1 && v >= brakeMax) return "AT_LIMIT";
    if (dir == 2 && v <= brakeMin) return "AT_LIMIT";
    return nullptr;
}

static void steerLimitsUpdate() {
    if (!limEnabled || !steerValid()) {
        tracking = false;
        return;
    }

    uint16_t v = steerValue();
    uint8_t dir = actSteerState();

    if (limitTrip) {
        int32_t keep = (limitTripDir == 1)
                     ? (int32_t)steerMax - STEER_LIM_HYST
                     : (int32_t)steerMin + STEER_LIM_HYST;
        if ((limitTripDir == 1 && (int32_t)v <= keep) ||
            (limitTripDir == 2 && (int32_t)v >= keep)) {
            limitTrip = false;
        }
    }
    if (stallTrip) {
        int32_t d = (int32_t)v - (int32_t)stallTripAngle;
        if (d < 0) d = -d;
        if (d >= STEER_LIM_HYST) stallTrip = false;
    }

    if (dir == 0) {
        tracking = false;
        return;
    }

    if (!steerBypass) {
        if (dir == 1 && v >= steerMax) {
            actSetSteer(0);
            limitTrip = true;
            limitTripDir = 1;
            tracking = false;
            return;
        }
        if (dir == 2 && v <= steerMin) {
            actSetSteer(0);
            limitTrip = true;
            limitTripDir = 2;
            tracking = false;
            return;
        }
    }

    if (!tracking || trackDir != dir) {
        tracking = true;
        trackDir = dir;
        trackAngle = v;
        trackMs = millis();
        return;
    }
    if (v != trackAngle) {
        trackAngle = v;
        trackMs = millis();
        return;
    }
    if (millis() - trackMs >= STEER_STALL_MS) {
        actSetSteer(0);
        stallTrip = true;
        stallTripDir = dir;
        stallTripAngle = v;
        tracking = false;
        serialReply(0x05, "ERR", "STALL");
    }
}

static void brakeLimitsUpdate() {
    if (!limEnabled || !brakeValid()) {
        brkTracking = false;
        return;
    }

    uint16_t v = brakeValue();
    uint8_t dir = actBrakeState();

    if (brkLimitTrip) {
        int32_t keep = (brkLimitTripDir == 1)
                     ? (int32_t)brakeMax - BRK_LIM_HYST
                     : (int32_t)brakeMin + BRK_LIM_HYST;
        if ((brkLimitTripDir == 1 && (int32_t)v <= keep) ||
            (brkLimitTripDir == 2 && (int32_t)v >= keep)) {
            brkLimitTrip = false;
        }
    }
    if (brkStallTrip) {
        int32_t d = (int32_t)v - (int32_t)brkStallTripAngle;
        if (d < 0) d = -d;
        if (d >= BRK_LIM_HYST) brkStallTrip = false;
    }

    if (dir == 0) {
        brkTracking = false;
        return;
    }

    if (!brakeBypass) {
        if (dir == 1 && v >= brakeMax) {
            actSetBrake(0);
            brkLimitTrip = true;
            brkLimitTripDir = 1;
            brkTracking = false;
            return;
        }
        if (dir == 2 && v <= brakeMin) {
            actSetBrake(0);
            brkLimitTrip = true;
            brkLimitTripDir = 2;
            brkTracking = false;
            return;
        }
    }

    if (!brkTracking || brkTrackDir != dir) {
        brkTracking = true;
        brkTrackDir = dir;
        brkTrackAngle = v;
        brkTrackMs = millis();
        return;
    }
    if (v != brkTrackAngle) {
        brkTrackAngle = v;
        brkTrackMs = millis();
        return;
    }
    if (millis() - brkTrackMs >= BRK_STALL_MS) {
        actSetBrake(0);
        brkStallTrip = true;
        brkStallTripDir = dir;
        brkStallTripAngle = v;
        brkTracking = false;
        serialReply(0x06, "ERR", "STALL");
    }
}

void limitsUpdate() {
    steerLimitsUpdate();
    brakeLimitsUpdate();
}
