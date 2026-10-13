#include "wifi_setup.h"
#include "config.h"

#include <WiFi.h>
#include <Preferences.h>

static Preferences prefs;

static char    ssid[33] = "";
static char    pass[65] = "";
static uint8_t mode = MODE_WIFI_OFF;

static void applyMode() {
    if (mode == MODE_WIFI_STA) {
        WiFi.mode(WIFI_STA);
        if (ssid[0] != '\0') WiFi.begin(ssid, pass);
    } else if (mode == MODE_WIFI_AP) {
        WiFi.mode(WIFI_AP);
        WiFi.softAP(ssid[0] ? ssid : WIFI_DEFAULT_SSID,
                    pass[0] ? pass : WIFI_DEFAULT_PASS);
    } else {
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
    }
}

void wifiBegin() {
    prefs.begin("wifi", false);
    String s = prefs.getString("ssid", "");
    String p = prefs.getString("pass", "");
    mode = prefs.getUChar("mode", MODE_WIFI_OFF);
    prefs.end();

    strncpy(ssid, s.c_str(), sizeof(ssid) - 1);
    strncpy(pass, p.c_str(), sizeof(pass) - 1);

    applyMode();
}

bool wifiSetCredentials(const char* newSsid, const char* newPass) {
    if (newSsid[0] == '\0') return false;

    strncpy(ssid, newSsid, sizeof(ssid) - 1);
    ssid[sizeof(ssid) - 1] = '\0';
    strncpy(pass, newPass, sizeof(pass) - 1);
    pass[sizeof(pass) - 1] = '\0';

    prefs.begin("wifi", false);
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    prefs.end();

    if (mode != MODE_WIFI_OFF) applyMode();
    return true;
}

bool wifiSetMode(uint8_t newMode) {
    if (newMode > MODE_WIFI_AP) return false;
    mode = newMode;

    prefs.begin("wifi", false);
    prefs.putUChar("mode", mode);
    prefs.end();

    applyMode();
    return true;
}

uint8_t wifiMode() {
    return mode;
}

const char* wifiSsid() {
    return ssid;
}
