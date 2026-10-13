// Host-side tests for the throttle board's logic. Build and run:
//   clang++ -std=c++17 -I.. test_throttle_logic.cpp -o /tmp/tl && /tmp/tl
// No Arduino here: the logic is pure, the sketch is glue.
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
    // identity and the new read-back command
    { Throttle t; CHECK_EQ(reply(t, "0x01", 0), "0x01;OK;AC0103");
      CHECK_EQ(reply(t, "01", 0), "0x01;OK;AC0103");
      CHECK_EQ(reply(t, "0x03", 0), "0x03;OK;00;00"); }

    // duty mapping is exactly AC 1.2's map(d, 0, 100, 42, 214): 42 + d*172/100 truncated
    { Throttle t; CHECK_EQ(reply(t, "0x02;00", 0), "0x02;OK;00"); CHECK(t.pwm() == 42);
      CHECK_EQ(reply(t, "0x02;64", 0), "0x02;OK;64"); CHECK(t.pwm() == 214);
      CHECK_EQ(reply(t, "0x02;32", 0), "0x02;OK;32"); CHECK(t.pwm() == 128);
      CHECK_EQ(reply(t, "02;14", 0), "0x02;OK;14"); CHECK(t.pwm() == 76);
      CHECK_EQ(reply(t, "0x02;01", 0), "0x02;OK;01"); CHECK(t.pwm() == 43); }

    // a command that arrives after the deadline finds the throttle already at rest
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x01", Throttle::TIMEOUT_MS + 1), "0x01;OK;AC0103");
      CHECK(t.duty() == 0); CHECK(t.timedOut()); CHECK(t.timeouts() == 1);
      CHECK_EQ(reply(t, "0x02;14", Throttle::TIMEOUT_MS + 2), "0x02;ERR;TIMEOUT"); }

    // the line feeder: overlong lines are discarded to the delimiter, control bytes drop the line
    { LineReader r;
      std::string flood(40, 'x'); flood += "0x02;14\n";
      bool got = false; for (char c : flood) got |= r.feed(c);
      CHECK(!got);                                   // the smuggled command never surfaces
      std::string good = "0x02;14\n"; got = false; for (char c : good) got |= r.feed(c);
      CHECK(got); CHECK_EQ(r.line(), "0x02;14");
      std::string ctl = std::string("0x02;") + '\x01' + "14\n"; got = false; for (char c : ctl) got |= r.feed(c);
      CHECK(!got); }

    // invalid duty is refused and changes nothing
    { Throttle t; reply(t, "0x02;14", 0);
      CHECK_EQ(reply(t, "0x02;65", 1), "0x02;ERR;INVALID_DUTY"); CHECK(t.duty() == 20);
      CHECK_EQ(reply(t, "0x02;zz", 2), "0x02;ERR;INVALID_DUTY");
      CHECK_EQ(reply(t, "0x02;", 3), "0x02;ERR;INVALID_DUTY");
      CHECK_EQ(reply(t, "0x09", 4), "ERR;UNKNOWN_COMMAND"); }

    // the watchdog: duty above zero and silence for TIMEOUT_MS -> zero
    { Throttle t; reply(t, "0x02;14", 1000);
      CHECK(!t.tick(1000 + Throttle::TIMEOUT_MS));          // not yet
      CHECK(t.duty() == 20);
      CHECK(t.tick(1000 + Throttle::TIMEOUT_MS + 1));       // fired: pwm changed
      CHECK(t.duty() == 0); CHECK(t.pwm() == 42);
      CHECK(t.timedOut()); CHECK(t.timeouts() == 1);
      CHECK(!t.tick(5000));                                 // fires once, not every tick
      CHECK(t.timeouts() == 1); }

    // silence at zero duty never times out
    { Throttle t; reply(t, "0x02;00", 0);
      CHECK(!t.tick(100000)); CHECK(!t.timedOut()); }

    // any valid line is a keepalive: INFO, read-back, or a duty frame
    { Throttle t; reply(t, "0x02;14", 0);
      reply(t, "0x01", 600); CHECK(!t.tick(1300));
      reply(t, "0x03", 1300); CHECK(!t.tick(2000));
      reply(t, "0x02;14", 2000); CHECK(!t.tick(2700));
      CHECK(t.duty() == 20); }

    // an invalid line is NOT a keepalive
    { Throttle t; reply(t, "0x02;14", 0);
      reply(t, "garbage", 700);
      CHECK(t.tick(0 + Throttle::TIMEOUT_MS + 1)); CHECK(t.duty() == 0); }

    // after a timeout, positive duty is refused until an explicit zero
    { Throttle t; reply(t, "0x02;14", 0); t.tick(Throttle::TIMEOUT_MS + 1);
      CHECK_EQ(reply(t, "0x02;14", 2000), "0x02;ERR;TIMEOUT"); CHECK(t.duty() == 0);
      CHECK_EQ(reply(t, "0x03", 2001), "0x03;OK;00;01");
      CHECK_EQ(reply(t, "0x02;00", 2002), "0x02;OK;00"); CHECK(!t.timedOut());
      CHECK_EQ(reply(t, "0x02;14", 2003), "0x02;OK;14"); CHECK(t.duty() == 20); }

    // millis() wrap-around (32-bit on the Nano) does not break the timer
    { Throttle t; reply(t, "0x02;14", 0xFFFFFFF0u);
      CHECK(!t.tick((uint32_t)(0xFFFFFFF0u + 100u)));       // 90 ms later, across the wrap
      CHECK(!t.tick((uint32_t)(0xFFFFFFF0u + 800u)));       // exactly TIMEOUT_MS: not yet
      CHECK(t.tick((uint32_t)(0xFFFFFFF0u + 801u))); }      // past it

    if (fails == 0) std::printf("all throttle logic tests passed\n");
    return fails ? 1 : 0;
}
