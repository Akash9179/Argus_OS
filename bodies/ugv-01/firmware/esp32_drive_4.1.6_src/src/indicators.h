#pragma once

#include <Arduino.h>

#define IND_OFF   0
#define IND_LEFT  1
#define IND_RIGHT 2
#define IND_BOTH  3

void indBegin();
bool indSet(uint8_t mode);
uint8_t indMode();
