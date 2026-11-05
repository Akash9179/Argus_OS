#pragma once
#include <stdint.h>

// Silence and feedback watchdog for the ARGUS DRIVE module, firmware
// 4.1.6 (added by ARGUS on 14 Oct 2026 to Gulshan Shah's 4.1.4 as 4.1.5;
// authority narrowed on 15 Oct 2026 as 4.1.6; see the patch beside this
// file).
//
// Silence: while a steering or brake actuator is on, or centring is
// running, the module must have accepted a motion command (0x05, 0x06,
// 0x12, 0x13, 0x14, answered OK) or the explicit keepalive (0x15) within
// WD_TIMEOUT_MS, or all four actuator relays are switched off at once,
// centring is cancelled, "0x00;WD;TIMEOUT" is printed once and the trip
// is latched. Polls (INFO, angles, STATUS, limits) answer and refresh
// nothing: in 4.1.5 any accepted command counted, so a host whose
// command path had died but whose poller lived kept a move alive. At
// rest nothing is required.
//
// Feedback: while a steering actuator is on without a valid steering
// reading for WD_NO_SIGNAL_MS (the horn causes exactly this), it is
// switched off the same way with "0x00;WD;NO_SIGNAL"; the brake likewise.
//
// While tripped, every command that would energise an actuator
// (0x05/0x06/0x12/0x13 with a direction, 0x14) is refused with
// ERR;WD_TRIPPED. An explicit stop (0x05 00 or 0x06 00) clears the trip.
// STATUS gains WD=<trip count, capped at FF>.
void wdNoteAccepted();     // called after the OK reply of a motion command or 0x15, nothing else (4.1.6)
void wdUpdate();           // call from loop(), before serial work
bool wdMoveAllowed();      // false while tripped
void wdClear();            // an explicit stop command clears the trip
uint8_t wdTimeouts();      // for STATUS
bool wdTripped();
