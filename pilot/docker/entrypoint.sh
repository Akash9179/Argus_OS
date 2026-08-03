#!/bin/bash
# Source ROS, then run whatever was asked for. Everything in this container
# gets the same environment the runtime gets, so a debugging shell is not a
# different world from the one that failed.
set -e
source /opt/ros/humble/setup.bash
exec "$@"
