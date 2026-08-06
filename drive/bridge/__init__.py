"""ARGUS DRIVE bridge: the vehicle daemon.

Speaks the cockpit contract (drive/cockpit/src/contract) as JSON over a
WebSocket, drives the vehicle through a VehicleAdapter, and enforces the
watchdog. Pure stdlib on purpose: the Jetson install is a sparse checkout
and `python3 -m drive.bridge`, nothing else.
"""
