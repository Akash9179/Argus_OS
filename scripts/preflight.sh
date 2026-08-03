#!/usr/bin/env bash
#
# Preflight. Run this before installing anything.
#
# It decides nothing and installs nothing. It tells an installer what this
# machine is, what is already here, what is missing, and which parts of
# ARGUS have actually been run on a target like this one. The last of those
# matters most: a step that has never been executed on this architecture is
# not a step that is known to work, and saying so up front is cheaper than
# discovering it forty minutes into a container build.
#
# Exit codes:
#   0  this target is supported and everything required is present
#   1  something required is missing (the report says what)
#   2  this target is not supported by this build

set -uo pipefail

PLATFORM_GAP=0
MACHINE_GAP=0
BOTH_GAP=0
UNSUPPORTED=0

# Which set of requirements the verdict is judged against. A box being set
# up as one or the other should say so, rather than be failed for the half
# it will never run.
SCOPE=both
case "${1:-}" in
  --platform) SCOPE=platform ;;
  --machine)  SCOPE=machine ;;
  "" ) ;;
  *) printf 'usage: %s [--platform|--machine]\n' "$0" >&2; exit 64 ;;
esac

say()  { printf '%s\n' "$*"; }
head2() { printf '\n%s\n' "$*"; }
ok()   { printf '  ok       %s\n' "$*"; }
gap()  { printf '  MISSING  %s\n' "$*"; PLATFORM_GAP=1; }
mgap() { printf '  MISSING  %s\n' "$*"; MACHINE_GAP=1; }
# Neither install can proceed without these, so they count against both.
bgap() { printf '  MISSING  %s\n' "$*"; BOTH_GAP=1; }
warn() { printf '  note     %s\n' "$*"; }

need() {
  # need <command> <what it is for>
  if command -v "$1" >/dev/null 2>&1; then
    ok "$1 ($(command -v "$1"))"
  else
    gap "$1 is not installed, needed for: $2"
  fi
}

say "ARGUS preflight"
say "==============="

# -- what is this machine ---------------------------------------------------

head2 "What this machine is"

ARCH="$(uname -m)"
OS="$(uname -s)"
say "  architecture   $ARCH"
say "  kernel         $OS"

IS_JETSON=0
if [ -f /etc/nv_tegra_release ]; then
  IS_JETSON=1
  say "  target         Jetson (a machine: PILOT)"
  say "  L4T            $(head -1 /etc/nv_tegra_release 2>/dev/null || echo unknown)"
elif [ "$OS" = "Darwin" ]; then
  say "  target         macOS (the platform: TRACK, gateway, voice, C2)"
else
  say "  target         Linux, not a Jetson (probably the platform)"
fi

if [ -f /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  say "  distribution   ${PRETTY_NAME:-unknown}"
fi
say "  checking for    $SCOPE"

# Nothing here has ever been built for anything else. Saying so now is the
# whole point of running this first.
case "$ARCH" in
  x86_64|amd64|arm64|aarch64) ;;
  *) UNSUPPORTED=1 ;;
esac
case "$OS" in
  Linux|Darwin) ;;
  *) UNSUPPORTED=1 ;;
esac

# -- what has actually been run on a target like this -----------------------

head2 "What has actually been run on a target like this"

if [ "$IS_JETSON" = "1" ]; then
  warn "No part of ARGUS has ever been installed on a Jetson."
  warn "The Python side runs on arm64 (it is developed on Apple Silicon),"
  warn "but L4T is a different operating system with a different CUDA and"
  warn "a different glibc, and nothing here has been exercised against it."
  warn "Treat every step as unverified and report what breaks."
  say ""
  warn "The container base image is wrong for real hardware. The Dockerfile"
  warn "uses ros:humble-ros-base, which carries no CUDA and no TensorRT."
  warn "That is correct while perception is simulated (Stage 3A) and wrong"
  warn "for real sensors (Stage 3B). The L4T base image does not exist yet."
  say ""
  warn "Proceed only if you are installing the simulated-driver machine."
elif [ "$OS" = "Darwin" ]; then
  ok "The platform is developed and run on macOS daily. This path is exercised."
  warn "ROS2 Humble has no supported native macOS path, so a machine (PILOT)"
  warn "runs containerized here and cannot run natively."
else
  warn "The platform is developed on macOS and tested in CI on Linux x86_64."
  warn "A Linux platform install is expected to work but is less travelled."
fi

# -- what is required -------------------------------------------------------

head2 "Required for the platform"

if ! command -v python3 >/dev/null 2>&1; then
  bgap "python3 is not installed, needed by both installs"
else
  ok "python3 ($(command -v python3))"
  PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
  MAJOR="${PYV%%.*}"; MINOR="${PYV##*.}"
  if [ "${MAJOR:-0}" -gt 3 ] || { [ "${MAJOR:-0}" -eq 3 ] && [ "${MINOR:-0}" -ge 11 ]; }; then
    ok "python $PYV is new enough (need 3.11 or newer)"
  else
    bgap "python $PYV is too old, need 3.11 or newer"
  fi
fi
need node "building the operator application"
need npm "building the operator application"
need redis-server "the world model's cache"
need mosquitto "the MQTT broker every machine connects to"
need ffmpeg "decoding what the microphone sends"

head2 "Required for a machine"

if command -v docker >/dev/null 2>&1; then
  ok "docker ($(command -v docker))"
  if docker info >/dev/null 2>&1; then
    ok "the docker daemon is running"
  else
    mgap "docker is installed but the daemon is not running"
  fi
else
  mgap "docker is not installed, needed for: PILOT runs containerized"
fi
if [ "$IS_JETSON" = "1" ]; then
  if docker info 2>/dev/null | grep -qi nvidia; then
    ok "the NVIDIA container runtime is registered with docker"
  else
    warn "the NVIDIA container runtime is not registered with docker."
    warn "Not needed while perception is simulated. Needed for Stage 3B."
  fi
fi

head2 "Required for speech (every AI profile)"

# Deliberately not naming the speech binary or the model files. Only the
# gateway's adapters may name a model, and this script is executable code
# rather than documentation. INSTALL.md 2.6 says exactly what belongs here.
if [ -d var/models ] && [ -n "$(ls -A var/models 2>/dev/null)" ]; then
  ok "var/models/ has $(ls -1 var/models | wc -l | tr -d ' ') file(s) in it"
  warn "This does not check which files. INSTALL.md 2.6 lists what is needed."
else
  gap "var/models/ is missing or empty. INSTALL.md 2.6 says what goes in it."
fi

# -- room and reachability --------------------------------------------------

head2 "Room and reachability"

if command -v df >/dev/null 2>&1; then
  FREE_KB="$(df -Pk . 2>/dev/null | awk 'NR==2 {print $4}')"
  FREE_GB=$(( ${FREE_KB:-0} / 1024 / 1024 ))
  if [ "$FREE_GB" -ge 12 ]; then
    ok "${FREE_GB}GB free (the ROS2 image and the models want about 10GB)"
  else
    bgap "only ${FREE_GB}GB free, the ROS2 image and the models want about 10GB"
  fi
fi

# This install path assumes a network. The air-gapped bundle does not exist
# yet, so an installer with no route out cannot finish, and should be told
# now rather than at the first download.
if ! command -v curl >/dev/null 2>&1; then
  warn "curl is not installed, so reachability was not checked."
elif curl -fsS --max-time 6 https://github.com >/dev/null 2>&1; then
  ok "the network is reachable"
else
  bgap "no network. This install path needs one at install time, and the"
  bgap "offline bundle does not exist yet (INSTALL.md section 0)."
fi

# -- verdict ----------------------------------------------------------------

head2 "Verdict"

# The two installs have different requirements, so they get different
# verdicts. Failing a correctly provisioned platform box for docker it does
# not need would teach an installer to ignore this script, which is worse
# than not running it.
if [ "$UNSUPPORTED" = "1" ]; then
  say "  This target is not supported by this build. Stop."
  say "  Nothing here has been built for $ARCH on $OS."
  exit 2
fi

if [ "$BOTH_GAP" = "1" ]; then
  say "  Neither install can proceed. Something both of them need is missing."
fi

if [ "$PLATFORM_GAP" = "0" ] && [ "$BOTH_GAP" = "0" ]; then
  say "  Platform: ready. Follow INSTALL.md section 2."
else
  say "  Platform: not ready. Install what is marked MISSING above."
  say "            INSTALL.md section 2.1 says how."
fi

if [ "$MACHINE_GAP" = "0" ] && [ "$BOTH_GAP" = "0" ]; then
  say "  Machine:  ready. Follow INSTALL.md section 3."
else
  say "  Machine:  not ready. Install what is marked MISSING above."
  say "            INSTALL.md section 3.1 says how."
fi

say ""
say "  Install only what this box is for. One machine does not need both."
say "  When you think you are done, run scripts/verify_install.py."

# Exit nonzero only if the target this box is for cannot be installed. With
# no way to know which that is, either gap is worth stopping on.
if [ "$BOTH_GAP" = "1" ]; then exit 1; fi
if [ "$SCOPE" = "platform" ] && [ "$PLATFORM_GAP" = "1" ]; then exit 1; fi
if [ "$SCOPE" = "machine" ] && [ "$MACHINE_GAP" = "1" ]; then exit 1; fi
if [ "$SCOPE" = "both" ] && { [ "$PLATFORM_GAP" = "1" ] || [ "$MACHINE_GAP" = "1" ]; }; then exit 1; fi
exit 0
