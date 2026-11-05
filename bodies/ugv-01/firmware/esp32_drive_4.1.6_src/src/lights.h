#pragma once

#include <Arduino.h>

#define LIGHT_OFF_ALL 0
#define LIGHT_RING    1
#define LIGHT_HIGH    2
#define LIGHT_LOW     3

void lightBegin();
bool lightSetMode(uint8_t mode);
uint8_t lightMode();
