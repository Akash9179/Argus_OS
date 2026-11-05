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

## 15 Oct 2026, the founder's Mac (Apple Silicon), the watchdog-authority images

Tools, user-local under `~/argus-tools` as `build.sh` expects: PlatformIO
Core 6.2.0 in a venv (platform espressif32 7.1.3, the same pin), and the
Homebrew arduino-cli 1.5.1 with `arduino:avr` 1.8.8 symlinked in. The
three ESP32 images built; `build.sh` then stopped at the first Nano image
with `avr-g++: bad CPU type in executable`: Arduino's AVR toolchain is
x86 only and this Mac has no Rosetta (PlatformIO's atmelavr toolchain is
x86 only as well). So the Nano images are not built here; the AC 1.4
logic is proven by its laptop test and the sketch glue is AC 1.3's with
new comments. Log: `bench-logs/2026-10-15/build-sh-mac.log`.

| image | source | SHA-256 (this Mac, this build) |
|---|---|---|
| drive module 4.1.4 | `vendor-2026-10-13/esp32_drive_4.1.4_src` | `50ce2ee7f4577a07b0d02a8c970a1c00a320f20637a5af8a4d6df55b26598b71` |
| drive module 4.1.5 | `esp32_drive_4.1.5_src/src` | `b73263dc861275a8e5203e8ea5f358045a69aa8fbc43e6b933b2a2f5c6488c69` |
| drive module 4.1.6 | `esp32_drive_4.1.6_src/src` | `b2a61ba335680c676932f814c7d1300dfe25ea7589e66b69bfdfb5d8ae367495` |
| throttle Nano AC 1.4 | `nano_throttle_AC0104/` | not built here (x86 toolchain) |

4.1.6 is 707520 bytes, 13.4 percent of RAM, the same footprint as 4.1.5
within a few hundred bytes. ESP32 hashes identify a build, not a tree
(see above); the 4.1.6 tree is identified by
`git log -1 -- bodies/ugv-01/firmware/esp32_drive_4.1.6_src`, and the
patch `esp32_drive_watchdog/esp32_4.1.6_watchdog.patch` reproduces it
from the vendor tree exactly (checked 15 Oct).

Nothing was flashed. The flash session rebuilds on the Jetson with
`build.sh` (all six images there, about a minute after the first time)
and records the hashes it flashes in that day's bench record.

## 5 Nov 2026, Jetson (tessy), rebuild from `aa53341`, and the first flash of the authority images

All six images rebuilt by `build.sh` on the Jetson in about a minute
(tools already installed). Log: `bench-logs/2026-11-05/build-sh.log`.

| image | SHA-256 |
|---|---|
| drive module 4.1.4 | `98490929d45efe424d7114400f3378a57e52f1eff9c6ef938c032dc5264a8f1f` |
| drive module 4.1.5 | `1932f70856717914eb2010f7c642c9795fd48f7cd5936225a5bc87cdd51804f9` |
| drive module 4.1.6 | `ca77e4735ad2e09139998e3eb7d79e2ab1e3323ba019e197dcb92991a1125963` |
| throttle Nano AC 1.2 | `78f465a178b4afd398ef935813f66ed21de680dbe88390a047df5b7d737f32dc` |
| throttle Nano AC 1.3 | `da0f82b24e10afd0fb9d2f5865e842e64fdfbdd03c95e62642330a83cf668fe5` |
| throttle Nano AC 1.4 | `d010c49b0457ee35cc57c288add1be4dde9767206f3b816bfdd3c7311e0a285f` |

The Nano hex files for AC 1.2 and AC 1.3 match 15 Oct byte for byte.
The ESP32 images differ from every earlier build, as expected (see
above: an ESP32 hash identifies a build, not a tree). AC 1.4 was built
for the first time here; the Mac cannot build AVR images.

**Flashed, 5 Nov 2026, founder at the jeep pasting each command:**
- Drive module 4.1.6, image `ca77e473...`, over `/dev/ttyUSB0` (CH340)
  at 460800 baud. The first attempt stopped at 17 percent with "chip
  stopped responding": the team's ROS node `serial_control/cmd` held
  both ports throughout. The team's stack was stopped and the second
  attempt wrote all four regions with every hash verified.
- Throttle Nano AC 1.4, image `d010c49b...`, over `/dev/ttyUSB1` (FTDI)
  with `--fqbn arduino:avr:nano` (new bootloader; the old-bootloader
  variant was not needed).
- Identity read straight after: drive `040106`, accelerator AC 1.4,
  STATUS `WI=00,WD=00` (`bench-logs/2026-11-05/identity.jsonl`).
