// Throttle board logic, firmware AC 1.3: AC 1.2 plus a silence watchdog.
// Pure C++ with no Arduino dependency so it is tested on a laptop
// (test/test_throttle_logic.cpp) and compiled unchanged into the sketch.
//
// Protocol (unchanged from AC 1.2 where it existed):
//   0x01            -> 0x01;OK;AC0103                 identity
//   0x02;<hex 0-64> -> 0x02;OK;<hex> | 0x02;ERR;INVALID_DUTY | 0x02;ERR;TIMEOUT
//   0x03            -> 0x03;OK;<duty hex>;<timeouts hex>   read-back (new)
//   anything else   -> ERR;UNKNOWN_COMMAND
//
// The watchdog: while duty is above zero, the board must receive a valid
// line (any of the three commands) within TIMEOUT_MS, or it sets the
// throttle to rest (PWM 42) and latches. At zero duty nothing is
// required, so a console that only sends on change is unaffected at
// rest. After a timeout the first positive duty is refused with
// 0x02;ERR;TIMEOUT; an explicit 0x02;00 clears the latch. Expiry is
// checked before every command is accepted, so a line that arrives late
// cannot erase a deadline that has already passed.
//
// Time is uint32_t milliseconds, as millis() returns on the Nano; the
// subtraction is wrap-safe. PWM is AC 1.2's map(d, 0, 100, 42, 214)
// exactly: 42 + d * 172 / 100, truncated.
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

class Throttle {
public:
    static const uint32_t TIMEOUT_MS = 800;
    static const int PWM_REST = 42;
    static const int PWM_FULL = 214;

    Throttle() : duty_(0), lastValidMs_(0), timedOut_(false), timeouts_(0) {}

    // Call often. Returns true when the watchdog just fired (PWM changed).
    bool tick(uint32_t nowMs) {
        if (duty_ == 0) return false;
        if ((uint32_t)(nowMs - lastValidMs_) > TIMEOUT_MS) {
            duty_ = 0;
            timedOut_ = true;
            if (timeouts_ < 0xFFFF) timeouts_++;
            return true;
        }
        return false;
    }

    // One complete line (no newline). Writes the reply into out. Returns
    // true if the line was valid, which refreshes the keepalive. Checks
    // expiry first: a late line finds the throttle already at rest.
    bool handleLine(const char* line, uint32_t nowMs, char* out, size_t outLen) {
        tick(nowMs);
        while (*line == ' ') line++;
        if (strcmp(line, "0x01") == 0 || strcmp(line, "01") == 0) {
            snprintf(out, outLen, "0x01;OK;AC0103");
            lastValidMs_ = nowMs;
            return true;
        }
        if (strcmp(line, "0x03") == 0 || strcmp(line, "03") == 0) {
            unsigned t = timeouts_ > 255 ? 255u : (unsigned)timeouts_;
            snprintf(out, outLen, "0x03;OK;%02X;%02X", (unsigned)duty_, t);
            lastValidMs_ = nowMs;
            return true;
        }
        if (strncmp(line, "0x02;", 5) == 0 || strncmp(line, "02;", 3) == 0) {
            const char* hex = strchr(line, ';') + 1;
            char* end = nullptr;
            long d = (*hex) ? strtol(hex, &end, 16) : -1;
            if (*hex == '\0' || end == hex || *end != '\0' || d < 0 || d > 100) {
                snprintf(out, outLen, "0x02;ERR;INVALID_DUTY");
                return false;
            }
            if (timedOut_ && d > 0) {
                snprintf(out, outLen, "0x02;ERR;TIMEOUT");
                lastValidMs_ = nowMs;          // a valid line, but the latch holds
                return true;
            }
            duty_ = (int)d;
            if (d == 0) timedOut_ = false;
            lastValidMs_ = nowMs;
            snprintf(out, outLen, "0x02;OK;%02lX", d);
            return true;
        }
        snprintf(out, outLen, "ERR;UNKNOWN_COMMAND");
        return false;
    }

    int duty() const { return duty_; }
    int pwm() const { return PWM_REST + (int)(((long)duty_ * (PWM_FULL - PWM_REST)) / 100); }
    bool timedOut() const { return timedOut_; }
    unsigned long timeouts() const { return timeouts_; }

private:
    int duty_;
    uint32_t lastValidMs_;
    bool timedOut_;
    uint32_t timeouts_;
};

// Assembles lines from bytes. An overlong line is discarded up to its
// delimiter, so nothing inside it can become a command. A control byte
// (other than CR and LF) drops the line it is in.
class LineReader {
public:
    static const size_t MAX = 31;
    LineReader() : len_(0), discarding_(false) { buf_[0] = '\0'; }

    // Returns true when a complete, clean line is available in line().
    bool feed(char c) {
        if (c == '\n' || c == '\r') {
            bool ready = !discarding_ && len_ > 0;
            buf_[len_] = '\0';
            len_ = 0;
            discarding_ = false;
            return ready;
        }
        if (discarding_) return false;
        if ((unsigned char)c < 0x20 || (unsigned char)c > 0x7E) {
            discarding_ = true;
            len_ = 0;
            return false;
        }
        if (len_ >= MAX) {
            discarding_ = true;
            len_ = 0;
            return false;
        }
        buf_[len_++] = c;
        return false;
    }

    const char* line() const { return buf_; }

private:
    char buf_[MAX + 1];
    size_t len_;
    bool discarding_;
};
