"""ARGUS PILOT: the edge runtime.

One program that runs on every machine. What differs between machines lives
in a capability manifest and behind three driver interfaces, and nothing
else in this package may know what kind of machine it is running on.

PILOT does not import the world model or the simulated vehicle. It is a
separate deployable that speaks the LINK contract and nothing more.
"""
