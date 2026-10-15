#pragma once

#include <Arduino.h>

void pwmBegin();
void pwmSetAccel(float percent);
void pwmOff();
float pwmDuty();
