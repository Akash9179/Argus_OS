#!/usr/bin/env bash
# Reproducible builds of ugv-01's board firmware, from this repository,
# on a Linux host (the Jetson is the intended one; founder direction of
# 14 Oct 2026: compile and flash move to our side).
#
# Builds four images and prints their SHA-256:
#   drive module 4.1.4   vendor tree as received        (reference only)
#   drive module 4.1.5   vendor plus the ARGUS watchdog (esp32_drive_4.1.5_src/)
#   throttle Nano AC 1.2 vendor sketch as received      (reference only)
#   throttle Nano AC 1.3 ARGUS watchdog sketch
#
# This script never opens a serial port and never flashes. Flashing is a
# separate, human-gated step (CLAUDE.md rule zero): the upload commands
# are printed at the end for the human at the key to approve.
#
# Tools, both user-local, installed once, versions pinned to the ones
# recorded in BUILDS.md (the espressif32 platform is pinned in platformio.ini):
#   PlatformIO:  python3 -m venv --without-pip $TOOLS/pio-venv
#                (Ubuntu without ensurepip: bootstrap pip with get-pip.py)
#                $TOOLS/pio-venv/bin/pip install platformio==6.2.0
#   arduino-cli: tarball from downloads.arduino.cc into $TOOLS/bin, then
#                arduino-cli core update-index && arduino-cli core install arduino:avr@1.8.8
# This is a hand install on one machine, a known gap in the graph until it
# is scripted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="${ARGUS_FW_TOOLS:-$HOME/argus-tools}"
OUT="${ARGUS_FW_OUT:-$TOOLS/build}"
PIO="$TOOLS/pio-venv/bin/pio"
ACLI="$TOOLS/bin/arduino-cli"
NANO_FQBN="${NANO_FQBN:-arduino:avr:nano}"

for t in "$PIO" "$ACLI"; do
  [ -x "$t" ] || { echo "missing tool: $t (see the header of this script)" >&2; exit 2; }
done
command -v sha256sum >/dev/null || { echo "sha256sum not found" >&2; exit 2; }
mkdir -p "$OUT"

# --- drive module (ESP32-S3) -------------------------------------------
# name, src directory. The vendor tree has no platformio.ini; both trees
# build with the pinned one kept beside the 4.1.5 sources.
build_esp32() {
  local name="$1" src="$2"
  local d="$OUT/$name"
  rm -rf "$d"; mkdir -p "$d"
  cp -r "$src" "$d/src"
  cp "$HERE/esp32_drive_4.1.5_src/platformio.ini" "$d/platformio.ini"
  ( cd "$d" && "$PIO" run --silent )
  cp "$d/.pio/build/esp32s3/firmware.bin" "$OUT/$name.bin"
}
build_esp32 esp32_drive_4.1.4 "$HERE/vendor-2026-10-13/esp32_drive_4.1.4_src"
build_esp32 esp32_drive_4.1.5 "$HERE/esp32_drive_4.1.5_src/src"

# --- throttle board (Arduino Nano) --------------------------------------
# name, sketch file or sketch folder. arduino-cli wants the .ino inside a
# folder of the same name.
build_nano() {
  local name="$1" sketch="$2"
  local d="$OUT/$name"
  rm -rf "$d"; mkdir -p "$d/$name"
  if [ -d "$sketch" ]; then
    cp "$sketch"/*.ino "$d/$name/$name.ino"
    cp "$sketch"/*.h "$d/$name/" 2>/dev/null || true
  else
    cp "$sketch" "$d/$name/$name.ino"
  fi
  "$ACLI" compile --fqbn "$NANO_FQBN" --output-dir "$d/out" "$d/$name" >/dev/null
  cp "$d/out/$name.ino.hex" "$OUT/$name.hex"
}
build_nano nano_throttle_AC0102 "$HERE/vendor-2026-10-13/nano_throttle_AC0102.ino"
build_nano nano_throttle_AC0103 "$HERE/nano_throttle_watchdog"

echo
echo "images in $OUT"
( cd "$OUT" && sha256sum esp32_drive_4.1.4.bin esp32_drive_4.1.5.bin nano_throttle_AC0102.hex nano_throttle_AC0103.hex )
echo
echo "Nothing was flashed. To flash, with the human at the key and the wheels up:"
echo "  drive module:  cd $OUT/esp32_drive_4.1.5 && $PIO run -t upload --upload-port <drive port>"
echo "  throttle Nano: $ACLI upload -p <accel port> --fqbn $NANO_FQBN --input-dir $OUT/nano_throttle_AC0103/out"
echo "  (an old-bootloader Nano needs --fqbn arduino:avr:nano:cpu=atmega328old)"
