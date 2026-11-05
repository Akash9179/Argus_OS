#pragma once

#include <Arduino.h>

void hornBegin();
bool hornStart(uint8_t mode);
void hornUpdate();
bool hornActive();
