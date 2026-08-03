#!/bin/bash
# Bring Nav2 up, then run the tests that need it.
#
# Do not wait for Nav2 to reach active before starting the tests. Nav2's
# controller server cannot activate until its local costmap can resolve
# base_link to odom, and that transform comes from the locomotion bridge,
# which the tests themselves start. Waiting here first deadlocks the two:
# Nav2 waits for the machine, and the machine waits for Nav2.
#
# So: launch Nav2, give it long enough to spawn its processes, and let the
# test's own wait_until_ready do the synchronising once the bridge is up.
set -e
source /opt/ros/humble/setup.bash
cd /opt/argus

ros2 launch /opt/argus/pilot/ros/launch/pilot_nav2.py > /tmp/nav2.log 2>&1 &
NAV2_PID=$!
trap 'kill $NAV2_PID 2>/dev/null || true' EXIT

echo "nav2 launching, waiting for its nodes to appear"
for i in $(seq 1 40); do
  if ros2 node list 2>/dev/null | grep -q controller_server; then
    echo "nav2 nodes up after ${i}s"
    break
  fi
  sleep 1
done

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest "$@"
