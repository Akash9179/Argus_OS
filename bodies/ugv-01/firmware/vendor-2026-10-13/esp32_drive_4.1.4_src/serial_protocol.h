#pragma once

#include <Arduino.h>

void serialPoll();
void serialReply(uint8_t cmd, const char* status, const char* data);
