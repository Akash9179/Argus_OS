#pragma once

#include <Arduino.h>

void actBegin();

bool actSetSteer(uint8_t dir);
bool actSetBrake(uint8_t dir);

uint8_t actSteerState();
uint8_t actBrakeState();
