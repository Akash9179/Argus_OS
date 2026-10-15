#pragma once

#include <Arduino.h>

void limitsBegin();

bool limitsSetBrake(uint16_t minV, uint16_t maxV);
bool limitsSetSteer(uint16_t minV, uint16_t maxV);

void limitsGetBrake(uint16_t& minV, uint16_t& maxV);
void limitsGetSteer(uint16_t& minV, uint16_t& maxV);

uint16_t limitsSteerCenter();

void limitsSteerBypass(bool on);
void limitsBrakeBypass(bool on);

void limitsSetEnabled(bool on);
bool limitsEnabled();

const char* limitsBlockReason(uint8_t dir);
const char* limitsBrakeBlockReason(uint8_t dir);

void limitsUpdate();
