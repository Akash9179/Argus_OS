#pragma once

#include <Arduino.h>

#define MODE_WIFI_OFF 0
#define MODE_WIFI_STA 1
#define MODE_WIFI_AP  2

void wifiBegin();

bool wifiSetCredentials(const char* ssid, const char* pass);
bool wifiSetMode(uint8_t mode);

uint8_t wifiMode();
const char* wifiSsid();
