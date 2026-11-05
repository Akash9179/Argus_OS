#pragma once

#include <Arduino.h>

void feedbackBegin();

bool     brakeValid();
uint16_t brakeValue();

bool     steerValid();
uint16_t steerValue();
