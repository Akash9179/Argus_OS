#pragma once
#include <stdint.h>

// Silence and feedback watchdog for the ARGUS DRIVE module, firmware
// 4.1.5 (added by ARGUS on 14 Oct 2026 to Gulshan Shah's 4.1.4; see the
// patch beside this file).
//
// Silence: while a steering or brake actuator is on, or centring is
// running, the module must answer an accepted command (one it replied
// OK to) within WD_TIMEOUT_MS, or all four actuator relays are switched
// off at once, centring is cancelled, "0x00;WD;TIMEOUT" is printed once
// and the trip is latched. At rest nothing is required.
//
// Feedback: while a steering actuator is on without a valid steering
// reading for WD_NO_SIGNAL_MS (the horn causes exactly this), it is
// switched off the same way with "0x00;WD;NO_SIGNAL"; the brake likewise.
//
// While tripped, every command that would energise an actuator
// (0x05/0x06/0x12/0x13 with a direction, 0x14) is refused with
// ERR;WD_TRIPPED. An explicit stop (0x05 00 or 0x06 00) clears the trip.
// STATUS gains WD=<trip count, capped at FF>.
void wdNoteAccepted();     // called by serialReply for every OK reply
void wdUpdate();           // call from loop(), before serial work
bool wdMoveAllowed();      // false while tripped
void wdClear();            // an explicit stop command clears the trip
uint8_t wdTimeouts();      // for STATUS
bool wdTripped();
