"""Shared setup for the tests that need ROS2.

rclpy is initialised once for the whole session and shut down once at the
end. Doing it per module looks tidier and is wrong: a module that shuts
rclpy down leaves the next module unable to bring it back, and the symptom
is the next module's Nav2 never activating, which reads like a Nav2 problem
rather than a fixture problem. It cost an afternoon once; hence this file.
"""

from __future__ import annotations

import pytest
import rclpy


@pytest.fixture(scope="session")
def ros():
    rclpy.init()
    yield
    rclpy.shutdown()
