"""The ROS2 side of the edge runtime.

Everything in this package requires ROS2 and runs only inside the
container. Nothing above the hardware abstraction layer imports it, which
is why the autonomy core can be built and tested on a laptop with no ROS2
installed at all.
"""
