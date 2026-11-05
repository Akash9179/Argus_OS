// Host-side tests for the throttle board's logic, firmware AC 1.4. Build and run:
//   clang++ -std=c++17 -I.. test_throttle_logic.cpp -o /tmp/tl14 && /tmp/tl14
// No Arduino here: the logic is pure, the sketch is glue.
//
// AC 1.4 changes the watchdog's authority: only a duty frame (0x02) and the
// explicit keepalive (0x04) refresh it. INFO (0x01) and the read-back (0x03)
// are polls and refresh nothing, so a host whose command path has died but
// whose poller lives cannot keep the throttle on.
#include <cstdio>
#include <cstring>
#include <string>
#include "throttle_logic.h"

static int fails = 0;
#define CHECK(cond) do { if (!(cond)) { fails++; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define CHECK_EQ(a, b) do { std::string _a = (a), _b = (b); if (_a != _b) { fails++; std::printf("FAIL %s:%d got %s want %s\n", __FILE__, __LINE__, _a.c_str(), _b.c_str()); } } while (0)

static std::string reply(Throttle& t, const char* line, uint32_t now) {
    char out[32];
    t.handleLine(line, now, out, sizeof(out));
    return out;
}

int main() {
    // identity, read-back and the new keepalive
    { Throttle t; CHECK_EQ(reply(t, "0x01", 0), "0x01;OK;AC0104");
      CHECK_EQ(reply(t, "01", 0), "0x01;OK;AC0104");
      CHECK_EQ(reply(t, "0x03", 0), "0x03;OK;00;00");
      CHECK_EQ(reply(t, "0x04", 0), "0x04;OK;00;00");
      CHECK_EQ(reply(t, "04", 0), "0x04;OK;00;00"); }

    // the keepalive reply carries the duty the board holds and its timeout count
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x04", 100), "0x04;OK;14;00");
      CHECK_EQ(reply(t, "0x04 ", 200), "ERR;UNKNOWN_COMMAND");     // exact match only
      CHECK_EQ(reply(t, "0x04;01", 300), "ERR;UNKNOWN_COMMAND"); }

    // duty mapping is exactly AC 1.2's map(d, 0, 100, 42, 214): 42 + d*172/100 truncated
    { Throttle t; CHECK_EQ(reply(t, "0x02;00", 0), "0x02;OK;00"); CHECK(t.pwm() == 42);
      CHECK_EQ(reply(t, "0x02;64", 0), "0x02;OK;64"); CHECK(t.pwm() == 214);
      CHECK_EQ(reply(t, "0x02;32", 0), "0x02;OK;32"); CHECK(t.pwm() == 128);
      CHECK_EQ(reply(t, "02;14", 0), "0x02;OK;14"); CHECK(t.pwm() == 76);
      CHECK_EQ(reply(t, "0x02;01", 0), "0x02;OK;01"); CHECK(t.pwm() == 43); }

    // WATCHDOG AUTHORITY: a duty frame refreshes, the keepalive refreshes
    { Throttle t; reply(t, "0x02;14", 0);
      reply(t, "0x02;14", 600); CHECK(!t.tick(1300));
      reply(t, "0x04", 1300); CHECK(!t.tick(2000));
      reply(t, "0x04", 2000); CHECK(!t.tick(2700));
      CHECK(t.duty() == 20); CHECK(!t.timedOut()); }

    // WATCHDOG AUTHORITY: INFO and the read-back are polls; they refresh nothing
    { Throttle t; reply(t, "0x02;14", 0);
      reply(t, "0x01", 300); reply(t, "0x03", 600); reply(t, "0x01", 700); reply(t, "0x03", 790);
      CHECK(!t.tick(800));                                  // exactly TIMEOUT_MS after the duty frame: not yet
      CHECK(t.tick(801));                                   // and then it rests, polls or no polls
      CHECK(t.duty() == 0); CHECK(t.pwm() == 42); CHECK(t.timedOut()); CHECK(t.timeouts() == 1); }

    // a poll that arrives after the deadline finds the throttle already at rest
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x03", Throttle::TIMEOUT_MS + 1), "0x03;OK;00;01");
      CHECK(t.duty() == 0); CHECK(t.timedOut());
      CHECK_EQ(reply(t, "0x02;14", Throttle::TIMEOUT_MS + 2), "0x02;ERR;TIMEOUT"); }

    // a keepalive that arrives after the deadline is too late as well
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x04", Throttle::TIMEOUT_MS + 1), "0x04;OK;00;01");
      CHECK(t.duty() == 0); CHECK(t.timedOut()); }

    // the keepalive at zero duty is accepted and changes nothing
    { Throttle t; CHECK_EQ(reply(t, "0x04", 5000), "0x04;OK;00;00");
      CHECK(!t.tick(100000)); CHECK(!t.timedOut()); }

    // the line feeder: overlong lines are discarded to the delimiter, control bytes drop the line
    { LineReader r;
      std::string flood(40, 'x'); flood += "0x02;14\n";
      bool got = false; for (char c : flood) got |= r.feed(c);
      CHECK(!got);
      std::string good = "0x02;14\n"; got = false; for (char c : good) got |= r.feed(c);
      CHECK(got); CHECK_EQ(r.line(), "0x02;14");
      std::string ctl = std::string("0x02;") + '\x01' + "14\n"; got = false; for (char c : ctl) got |= r.feed(c);
      CHECK(!got); }

    // invalid duty is refused and changes nothing, and is not a keepalive
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x02;65", 1), "0x02;ERR;INVALID_DUTY"); CHECK(t.duty() == 20);
      CHECK_EQ(reply(t, "0x02;zz", 2), "0x02;ERR;INVALID_DUTY");
      CHECK_EQ(reply(t, "0x02;", 3), "0x02;ERR;INVALID_DUTY");
      CHECK_EQ(reply(t, "0x09", 4), "ERR;UNKNOWN_COMMAND");
      reply(t, "0x02;65", 700);
      CHECK(t.tick(801)); CHECK(t.duty() == 0); }

    // the watchdog: duty above zero and silence for TIMEOUT_MS -> zero, fires once
    { Throttle t; reply(t, "0x02;14", 1000);
      CHECK(!t.tick(1000 + Throttle::TIMEOUT_MS));
      CHECK(t.duty() == 20);
      CHECK(t.tick(1000 + Throttle::TIMEOUT_MS + 1));
      CHECK(t.duty() == 0); CHECK(t.pwm() == 42);
      CHECK(t.timedOut()); CHECK(t.timeouts() == 1);
      CHECK(!t.tick(5000)); CHECK(t.timeouts() == 1); }

    // silence at zero duty never times out
    { Throttle t; reply(t, "0x02;00", 0);
      CHECK(!t.tick(100000)); CHECK(!t.timedOut()); }

    // after a timeout, positive duty is refused until an explicit zero
    { Throttle t; reply(t, "0x02;14", 0); t.tick(Throttle::TIMEOUT_MS + 1);
      CHECK_EQ(reply(t, "0x02;14", 2000), "0x02;ERR;TIMEOUT"); CHECK(t.duty() == 0);
      CHECK_EQ(reply(t, "0x04", 2001), "0x04;OK;00;01");       // the keepalive does not clear the latch
      CHECK(t.timedOut());
      CHECK_EQ(reply(t, "0x02;00", 2002), "0x02;OK;00"); CHECK(!t.timedOut());
      CHECK_EQ(reply(t, "0x02;14", 2003), "0x02;OK;14"); CHECK(t.duty() == 20); }

    // millis() wrap-around (32-bit on the Nano) does not break the timer
    { Throttle t; reply(t, "0x02;14", 0xFFFFFFF0u);
      CHECK(!t.tick((uint32_t)(0xFFFFFFF0u + 100u)));
      CHECK(!t.tick((uint32_t)(0xFFFFFFF0u + 800u)));
      CHECK(t.tick((uint32_t)(0xFFFFFFF0u + 801u))); }

    if (fails == 0) std::printf("all AC 1.4 throttle logic tests passed\n");
    return fails ? 1 : 0;
}
