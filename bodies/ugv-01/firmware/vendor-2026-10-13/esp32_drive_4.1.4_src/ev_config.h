#pragma once

#include <Arduino.h>

void evBegin();

bool evSetSpeed(uint8_t speed);
bool evSetGear(uint8_t gear);

uint8_t evSpeed();
uint8_t evGear();
