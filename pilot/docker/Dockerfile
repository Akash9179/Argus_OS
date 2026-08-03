# The edge runtime, containerized.
#
# ROS2 Humble has no supported native macOS path, and the production target
# is a Jetson running Linux anyway, so the runtime is built and run in a
# container on every machine including the developer's. This is closer to
# how it ships than a local install would be.
#
# The base is ros-base rather than desktop: nothing here needs a GUI, and
# an image that cannot open a window is an image that cannot accidentally
# depend on one.

FROM ros:humble-ros-base

SHELL ["/bin/bash", "-lc"]

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-pip \
      ros-humble-navigation2 \
      ros-humble-nav2-bringup \
      ros-humble-nav2-simple-commander \
      ros-humble-tf-transformations \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/argus

# Ubuntu 22.04 ships a setuptools too old to read the contract package's
# PEP 621 metadata, which fails quietly by installing a package called
# UNKNOWN with nothing in it. Upgrading the build tooling first.
RUN pip3 install --no-cache-dir --upgrade "pip>=24" "setuptools>=68" wheel

# Dependencies next, so a code change does not re-resolve the world.
COPY requirements.txt /opt/argus/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Installed normally rather than editable: the container is a build
# artifact, not a place anyone edits the contract.
#
# Built from /tmp and then removed on purpose. Left under /opt/argus the
# source directory would shadow the installed package, because PYTHONPATH
# makes it importable as a namespace package with none of the generated
# bindings inside it.
COPY link /tmp/link
RUN pip3 install --no-cache-dir /tmp/link && rm -rf /tmp/link

COPY pilot /opt/argus/pilot

# The ROS2 tests run in here too. ROS2 ships a `launch_testing` pytest
# plugin written against an older hook signature, so it is disabled for
# our tests rather than pinning pytest back to match it.
COPY pilot/docker/pytest.ini /opt/argus/pytest.ini

ENV PYTHONPATH=/opt/argus
ENV ROS_DOMAIN_ID=42

# Nav2 talks to the machine through the locomotion driver and nothing else.
# The entrypoint sources ROS then hands over, so anything run in this
# container has the same environment the runtime has.
COPY pilot/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-m", "pilot.main", "--manifest", "/opt/argus/pilot/manifests/ugv-reference.yaml"]
