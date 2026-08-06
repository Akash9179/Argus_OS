"""Driver implementations.

One module per family. Importing a module registers the drivers it carries
with the loader, which is how a manifest can name a driver by string.

Stage 3A carries `simulated` (a driver set with no hardware behind it) and
`mqtt` (the version 1 comms driver, which is real and needs no hardware
beyond a network). Stage 3B adds the sensor and locomotion drivers for the
actual machine here, next to these, changing nothing above.
"""

from pilot.hal.drivers import mqtt as _mqtt  # noqa: F401
from pilot.hal.drivers import simulated as _simulated  # noqa: F401
