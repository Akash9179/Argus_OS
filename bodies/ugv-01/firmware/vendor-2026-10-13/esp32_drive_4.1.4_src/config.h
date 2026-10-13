#pragma once

#define FW_VERSION_MAJOR    4
#define FW_VERSION_MINOR    1
#define FW_VERSION_PATCH    4

#define SERIAL_BAUD         115200

#define PWM_PIN             4
#define LEDC_CH             0
#define PWM_FREQ_HZ         1000
#define DUTY_MIN            20.0f
#define DUTY_MAX            90.0f

#define BRAKE_FB_PIN        15
#define STEER_FB_PIN        16

#define BRAKE_FB_MAX        3600    // x10 deg, same scale as steer
#define STEER_FB_MAX        3600

#define STEER_CTR_TOL       20
#define CTR_TIMEOUT_MS      10000UL
#define STEER_LIM_HYST      50    // x10 units = 5.0 deg, trip latch release
#define STEER_STALL_MS      400UL // relay on + angle unchanged -> stop

#define BRK_LIM_HYST        50    // x10 units = 5.0 deg, trip latch release
#define BRK_STALL_MS        400UL // relay on + value unchanged -> stop

#define STEER_LEFT_PIN      8
#define STEER_RIGHT_PIN     7
#define BRAKE_FWD_PIN       5
#define BRAKE_REV_PIN       6

#define SPEED_1_PIN         13
#define SPEED_3_PIN         12
#define GEAR_N_PIN          21
#define GEAR_R_PIN          1

#define LIGHT_RING_PIN      17
#define LIGHT_HIGH_PIN      14
#define LIGHT_LOW_PIN       11
#define LIGHT_ON            LOW
#define LIGHT_OFF           HIGH

#define IND_LEFT_PIN        18
#define IND_RIGHT_PIN       2
#define IND_ON              LOW
#define IND_OFF_LEVEL       HIGH

#define HORN_PIN            9
#define HORN_ON             LOW
#define HORN_OFF            HIGH

#define WIFI_DEFAULT_SSID   "AVX26-S3"
#define WIFI_DEFAULT_PASS   "12345678"
#define WIFI_CMD_LOCKED     1   // 1 = 0x0D / 0x0E refused with ERR;LOCKED
#define HORN_LONG_LOCKED    1   // 1 = 0x0B 02/03 (1s/2s) refused, 0.5s ok
#define LIMIT_EN_CMD_LOCKED 1   // 1 = 0x11 00/01 refused with ERR;LOCKED

#define EV_SPEED_DEFAULT    2
#define EV_GEAR_D           1
#define EV_GEAR_N           2
#define EV_GEAR_R           3
