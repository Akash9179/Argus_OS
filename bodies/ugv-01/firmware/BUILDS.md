# Firmware builds from our side

Record of images built from this repository with `build.sh`. Flashing
is a separate, human-gated act; the hash of what was flashed goes into
the bench record of that day.

## 15 Oct 2026, Jetson (tessy, JetPack R36.5, aarch64), first build from our side

Tools, user-local under `~/argus-tools`: PlatformIO Core 6.2.0 in a venv
(platform espressif32 7.1.3, framework arduinoespressif32 4.20017,
toolchain xtensa-esp32s3 8.4.0), arduino-cli with `arduino:avr` 1.8.8.
Install took one download of about 1.9 GB; a clean build of both ESP32
images and both Nano images takes about nine minutes, a rebuild seconds.

| image | source | SHA-256 |
|---|---|---|
| drive module 4.1.4 | `vendor-2026-10-13/esp32_drive_4.1.4_src` | `81e45b6e17697a99afba770f3ecee5ca82d2e009dd97b3269fefc5c17f4645e0` |
| drive module 4.1.5 | `esp32_drive_4.1.5_src/src` | `c33a05ad880f712d11da9404e3e4eacf94848ab1ac2a829e74f1f8d19b3ad021` |
| throttle Nano AC 1.2 | `vendor-2026-10-13/nano_throttle_AC0102.ino` | `78f465a178b4afd398ef935813f66ed21de680dbe88390a047df5b7d737f32dc` |
| throttle Nano AC 1.3 | `nano_throttle_watchdog/` | `da0f82b24e10afd0fb9d2f5865e842e64fdfbdd03c95e62642330a83cf668fe5` |

Sizes: 4.1.4 and 4.1.5 both about 706 kB of 3.3 MB flash, 13 percent
of RAM. AC 1.2 uses 6590 bytes of program memory, AC 1.3 uses 5492.

Determinism: the two Nano hex files are identical across builds. The
ESP32 images are not, because the Arduino core embeds the build date
and time in the application description; two builds of the same tree
on the same day gave `9fce1dda...` and `81e45b6e...` for 4.1.4. So an
ESP32 hash identifies one build, not a source tree. The source tree is
identified by `git log -1 -- bodies/ugv-01/firmware/esp32_drive_4.1.5_src`.

Nothing was flashed on 15 Oct. The images the team flashed on 14 Oct
were built on the team's Windows PC from the ARGUS zip; their hashes
were never recorded, which is one reason compile and flash move here.
The zip itself, `ugv01_firmware_watchdog_2026-10-14.zip`, has SHA-256
`8ef8429262ba59f618d1f67d016b5c3eeef89ce4094b2291b13bb93f35a6072f`;
its `esp32_watchdog_src/` is identical to `esp32_drive_4.1.5_src/src/`
(checked file for file on 15 Oct).
