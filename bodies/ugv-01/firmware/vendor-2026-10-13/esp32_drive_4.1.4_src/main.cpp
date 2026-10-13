#include <Arduino.h>
#include "config.h"
#include "serial_protocol.h"
#include "pwm_output.h"
#include "feedback.h"
#include "actuators.h"
#include "ev_config.h"
#include "lights.h"
#include "indicators.h"
#include "horn.h"
#include "wifi_setup.h"
#include "angle_limits.h"
#include "steer_center.h"

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(200);
    pwmBegin();
    feedbackBegin();
    actBegin();
    evBegin();
    lightBegin();
    indBegin();
    hornBegin();
    wifiBegin();
    limitsBegin();
    char ver[7];
    snprintf(ver, sizeof(ver), "%02X%02X%02X",
             FW_VERSION_MAJOR, FW_VERSION_MINOR, FW_VERSION_PATCH);
    serialReply(0x00, "OK", ver);
}

void loop() {
    serialPoll();
    hornUpdate();
    limitsUpdate();
    ctrUpdate();
}
