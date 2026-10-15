#include "serial_protocol.h"
#include "config.h"
#include "pwm_output.h"
#include "feedback.h"
#include "actuators.h"
#include "ev_config.h"
#include "lights.h"
#include "indicators.h"
#include "horn.h"
#include "wifi_setup.h"
#include "angle_limits.h"
#include "steer_center.h"
#include "watchdog.h"

#define CMD_BUF_SIZE 128

static char cmdBuf[CMD_BUF_SIZE];
static uint8_t cmdLen = 0;
static bool cmdDiscard = false;   // 4.1.5: an overlong line is dropped to its end

void serialReply(uint8_t cmd, const char* status, const char* data) {
    if (strcmp(status, "OK") == 0) wdNoteAccepted();   // 4.1.5: only accepted commands keep actuators alive
    Serial.printf("0x%02X;%s;%s\n", cmd, status, data);
}

static void cmdInfo(uint8_t cmd, const char*) {
    char ver[7];
    snprintf(ver, sizeof(ver), "%02X%02X%02X",
             FW_VERSION_MAJOR, FW_VERSION_MINOR, FW_VERSION_PATCH);
    serialReply(cmd, "OK", ver);
}

static void cmdAccel(uint8_t cmd, const char* args) {
    if (actBrakeState() != 0) {
        serialReply(cmd, "ERR", "BRAKE_ACTIVE");
        return;
    }

    while (*args == ' ') args++;

    char* end = nullptr;
    unsigned long accel = strtoul(args, &end, 16);
    if (end == args) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }

    pwmSetAccel((float)accel);

    char d[3];
    snprintf(d, sizeof(d), "%02X", (uint8_t)(pwmDuty() + 0.5f));
    serialReply(cmd, "OK", d);
}

static void cmdBrake(uint8_t cmd, const char*) {
    if (!brakeValid()) {
        serialReply(cmd, "ERR", "NO_SIGNAL");
        return;
    }
    char d[5];
    snprintf(d, sizeof(d), "%04X", brakeValue());
    serialReply(cmd, "OK", d);
}

static void cmdSteer(uint8_t cmd, const char*) {
    if (!steerValid()) {
        serialReply(cmd, "ERR", "NO_SIGNAL");
        return;
    }
    char d[5];
    snprintf(d, sizeof(d), "%04X", steerValue());
    serialReply(cmd, "OK", d);
}

static bool parseHex(const char* args, uint8_t& out) {
    while (*args == ' ') args++;
    char* end = nullptr;
    unsigned long v = strtoul(args, &end, 16);
    if (end == args || v > 0xFF) return false;
    while (*end == ' ') end++;
    if (*end != '\0') return false;   // 4.1.5: trailing text is not an argument
    out = (uint8_t)v;
    return true;
}

static void replyDir(uint8_t cmd, uint8_t dir) {
    char d[3];
    snprintf(d, sizeof(d), "%02X", dir);
    serialReply(cmd, "OK", d);
}

static void cmdSteerSw(uint8_t cmd, const char* args) {
    uint8_t dir;
    if (!parseHex(args, dir) || dir > 2) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    if (dir == 0) wdClear();
    else if (!wdMoveAllowed()) { serialReply(cmd, "ERR", "WD_TRIPPED"); return; }
    ctrCancel();
    limitsSteerBypass(false);
    const char* why = limitsBlockReason(dir);
    if (why) {
        actSetSteer(0);
        serialReply(cmd, "ERR", why);
        return;
    }
    actSetSteer(dir);
    replyDir(cmd, actSteerState());
}

static void cmdSteerAdm(uint8_t cmd, const char* args) {
    uint8_t dir;
    if (!parseHex(args, dir) || dir > 2) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    if (dir == 0) wdClear();
    else if (!wdMoveAllowed()) { serialReply(cmd, "ERR", "WD_TRIPPED"); return; }
    ctrCancel();
    limitsSteerBypass(true);
    actSetSteer(dir);
    replyDir(cmd, actSteerState());
}

static void cmdBrakeAdm(uint8_t cmd, const char* args) {
    uint8_t dir;
    if (!parseHex(args, dir) || dir > 2) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    if (dir == 0) wdClear();
    else if (!wdMoveAllowed()) { serialReply(cmd, "ERR", "WD_TRIPPED"); return; }
    limitsBrakeBypass(true);
    actSetBrake(dir);
    if (dir != 0) pwmOff();
    replyDir(cmd, actBrakeState());
}

static void cmdSteerCtr(uint8_t cmd, const char* args) {
    while (*args == ' ') args++;

    if (*args != '\0') {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    if (!wdMoveAllowed()) {
        serialReply(cmd, "ERR", "WD_TRIPPED");
        return;
    }
    if (ctrActive()) {
        serialReply(cmd, "ERR", "BUSY");
        return;
    }
    if (!steerValid()) {
        serialReply(cmd, "ERR", "NO_SIGNAL");
        return;
    }
    limitsSteerBypass(false);
    ctrStart();
    serialReply(cmd, "OK", "01");
}

static void cmdBrakeSw(uint8_t cmd, const char* args) {
    uint8_t dir;
    if (!parseHex(args, dir) || dir > 2) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    if (dir == 0) wdClear();
    else if (!wdMoveAllowed()) { serialReply(cmd, "ERR", "WD_TRIPPED"); return; }
    limitsBrakeBypass(false);
    const char* why = limitsBrakeBlockReason(dir);
    if (why) {
        actSetBrake(0);
        serialReply(cmd, "ERR", why);
        return;
    }
    actSetBrake(dir);
    if (dir != 0) pwmOff();
    replyDir(cmd, actBrakeState());
}

static void cmdSpeed(uint8_t cmd, const char* args) {
    uint8_t v;
    if (!parseHex(args, v) || v < 1 || v > 3) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    evSetSpeed(v);
    replyDir(cmd, evSpeed());
}

static void cmdGear(uint8_t cmd, const char* args) {
    uint8_t v;
    if (!parseHex(args, v) || v < 1 || v > 3) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    evSetGear(v);
    replyDir(cmd, evGear());
}

static void cmdLight(uint8_t cmd, const char* args) {
    uint8_t v;
    if (!parseHex(args, v) || v > LIGHT_LOW) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    lightSetMode(v);
    replyDir(cmd, lightMode());
}

static void cmdInd(uint8_t cmd, const char* args) {
    uint8_t v;
    while (*args == ' ') args++;
    if (*args == '\0') {
        replyDir(cmd, indMode());
        return;
    }
    if (!parseHex(args, v) || v > IND_BOTH) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    indSet(v);
    replyDir(cmd, indMode());
}

static void cmdHorn(uint8_t cmd, const char* args) {
    uint8_t v;
    if (!parseHex(args, v) || v < 1 || v > 3) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
#if HORN_LONG_LOCKED
    if (v > 1) {
        serialReply(cmd, "ERR", "LOCKED");
        return;
    }
#endif
    hornStart(v);
    replyDir(cmd, v);
}

static void cmdStatus(uint8_t cmd, const char* args) {
    while (*args == ' ') args++;
    if (*args != '\0') {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    char d[80];
    snprintf(d, sizeof(d),
             "A=%02X,ST=%02X,BR=%02X,SP=%02X,GR=%02X,LI=%02X,IN=%02X,HO=%02X,WI=%02X,CT=%02X,WD=%02X",
             (uint8_t)(pwmDuty() + 0.5f),
             actSteerState(),
             actBrakeState(),
             evSpeed(),
             evGear(),
             lightMode(),
             indMode(),
             hornActive() ? 1 : 0,
             wifiMode(),
             ctrActive() ? 1 : 0,
             wdTimeouts());
    serialReply(cmd, "OK", d);
}

static void cmdReset(uint8_t cmd, const char*) {
    serialReply(cmd, "OK", "01");
    Serial.flush();
    delay(50);
    ESP.restart();
}

static bool wifiCmdLocked() {
#if WIFI_CMD_LOCKED
    return true;
#else
    return false;
#endif
}

static void cmdWifiSet(uint8_t cmd, const char* args) {
    if (wifiCmdLocked()) {
        serialReply(cmd, "ERR", "LOCKED");
        return;
    }

    while (*args == ' ') args++;

    const char* sp = strchr(args, ' ');
    if (sp == nullptr) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }

    char newSsid[33];
    char newPass[65];
    size_t slen = (size_t)(sp - args);
    if (slen >= sizeof(newSsid)) slen = sizeof(newSsid) - 1;
    memcpy(newSsid, args, slen);
    newSsid[slen] = '\0';

    const char* p = sp;
    while (*p == ' ') p++;
    strncpy(newPass, p, sizeof(newPass) - 1);
    newPass[sizeof(newPass) - 1] = '\0';

    if (!wifiSetCredentials(newSsid, newPass)) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    serialReply(cmd, "OK", "01");
}

static void cmdWifi(uint8_t cmd, const char* args) {
    if (wifiCmdLocked()) {
        serialReply(cmd, "ERR", "LOCKED");
        return;
    }

    uint8_t v;
    if (!parseHex(args, v) || v > MODE_WIFI_AP) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    wifiSetMode(v);
    replyDir(cmd, wifiMode());
}

static void cmdLim(uint8_t cmd, const char* args, bool brake) {
    uint16_t minV, maxV;
    if (brake) limitsGetBrake(minV, maxV);
    else       limitsGetSteer(minV, maxV);

    while (*args == ' ') args++;

    if (*args != '\0') {
        char* end = nullptr;
        unsigned long a = strtoul(args, &end, 16);
        if (end == args || a > 0xFFFFUL) {
            serialReply(cmd, "ERR", "BAD_ARG");
            return;
        }
        while (*end == ' ') end++;

        const char* p2 = end;
        unsigned long b = strtoul(p2, &end, 16);
        if (end == p2 || b > 0xFFFFUL) {
            serialReply(cmd, "ERR", "BAD_ARG");
            return;
        }
        while (*end == ' ') end++;
        if (*end != '\0') {
            serialReply(cmd, "ERR", "BAD_ARG");
            return;
        }

        bool ok = brake ? limitsSetBrake((uint16_t)a, (uint16_t)b)
                        : limitsSetSteer((uint16_t)a, (uint16_t)b);
        if (!ok) {
            serialReply(cmd, "ERR", "BAD_RANGE");
            return;
        }
        minV = (uint16_t)a;
        maxV = (uint16_t)b;
    }

    char d[9];
    snprintf(d, sizeof(d), "%04X%04X", minV, maxV);
    serialReply(cmd, "OK", d);
}

static void cmdBrakeLim(uint8_t cmd, const char* args) {
    cmdLim(cmd, args, true);
}

static void cmdSteerLim(uint8_t cmd, const char* args) {
    cmdLim(cmd, args, false);
}

static void cmdLimEn(uint8_t cmd, const char* args) {
    while (*args == ' ') args++;
    if (*args == '\0') {
        serialReply(cmd, "OK", limitsEnabled() ? "01" : "00");
        return;
    }
#if LIMIT_EN_CMD_LOCKED
    serialReply(cmd, "ERR", "LOCKED");
#else
    uint8_t v;
    if (!parseHex(args, v) || v > 1) {
        serialReply(cmd, "ERR", "BAD_ARG");
        return;
    }
    limitsSetEnabled(v != 0);
    serialReply(cmd, "OK", v ? "01" : "00");
#endif
}

static void dispatch(uint8_t cmd, const char* args) {
    switch (cmd) {
        case 0x01: cmdInfo(cmd, args);  break;
        case 0x02: cmdAccel(cmd, args); break;
        case 0x03: cmdBrake(cmd, args); break;
        case 0x04: cmdSteer(cmd, args); break;
        case 0x05: cmdSteerSw(cmd, args); break;
        case 0x06: cmdBrakeSw(cmd, args); break;
        case 0x07: cmdSpeed(cmd, args); break;
        case 0x08: cmdGear(cmd, args);  break;
        case 0x09: cmdLight(cmd, args); break;
        case 0x0A: cmdInd(cmd, args);   break;
        case 0x0B: cmdHorn(cmd, args);  break;
        case 0x0C: cmdReset(cmd, args); break;
        case 0x0D: cmdWifiSet(cmd, args); break;
        case 0x0E: cmdWifi(cmd, args);  break;
        case 0x0F: cmdBrakeLim(cmd, args); break;
        case 0x10: cmdSteerLim(cmd, args); break;
        case 0x11: cmdLimEn(cmd, args);    break;
        case 0x12: cmdSteerAdm(cmd, args); break;
        case 0x13: cmdBrakeAdm(cmd, args); break;
        case 0x14: cmdSteerCtr(cmd, args); break;
        case 0x16: cmdStatus(cmd, args);   break;

        default:
            serialReply(cmd, "ERR", "UNKNOWN_COMMAND");
            break;
    }
}

static void processLine(char* line) {
    while (*line == ' ') line++;

    char* end = nullptr;
    if (line[0] == '0' && (line[1] == 'x' || line[1] == 'X')) line += 2;

    unsigned long op = strtoul(line, &end, 16);
    if (end == line || op > 0xFF || (*end != '\0' && *end != ' ')) {
        serialReply(0x00, "ERR", "BAD_FORMAT");   // 4.1.5: a whole opcode, nothing glued to it
        return;
    }
    uint8_t cmd = (uint8_t)op;

    dispatch(cmd, end);
}

void serialPoll() {
    uint8_t budget = 32;                      // 4.1.5: bounded work per pass
    while (budget-- && Serial.available()) {
        char c = (char)Serial.read();

        if (c == '\n' || c == '\r') {
            bool ready = !cmdDiscard && cmdLen > 0;
            cmdBuf[cmdLen] = '\0';
            cmdLen = 0;
            cmdDiscard = false;
            if (ready) {
                processLine(cmdBuf);
                return;                       // one line per pass; the watchdog runs between lines
            }
        } else if (cmdDiscard) {
            continue;
        } else if ((unsigned char)c < 0x20 || (unsigned char)c > 0x7E || cmdLen >= CMD_BUF_SIZE - 1) {
            cmdDiscard = true;                // control byte or overlong: drop the whole line
            cmdLen = 0;
        } else {
            cmdBuf[cmdLen++] = c;
        }
    }
}
