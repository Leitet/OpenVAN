"""ESPHome — DIY sensors and IO over the native API.

ESPHome nodes (ESP32/ESP8266) are how most builders add their own sensors,
relays and buttons. They speak a documented local **native API** (and can also
publish over MQTT), work fully offline, and are trivially discoverable via mDNS.
This is the second-most-important integration after Victron: it's the seam for
everything the reference van doesn't ship natively.

In simulation this driver models a small cabin sensor node — an SHT-class
temperature/humidity sensor — deriving believable readings from the twin's cabin
climate so the node's data tracks the environment.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class ESPHome(Integration):
    info = IntegrationInfo(
        id="esphome",
        name="ESPHome",
        category="sensors",
        vendor="ESPHome / Open source",
        transports=[Transport.NATIVE_API, Transport.MQTT],
        local=True,
        offline_capable=True,
        discovery="mdns",
        permissions=Permissions(read=True, control=True, configure=True),
        safety_class=1,  # can toggle relays / GPIO
        status=Status.NATIVE,
        priority="P0",
        provides=["esphome.cabin_node.temperature", "esphome.cabin_node.humidity"],
        description=(
            "ESP32/ESP8266 nodes over the documented native API. The seam for "
            "custom sensors, relays and buttons — fully local and offline."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        # A cabin node reads a touch below the twin's cabin sensor, tracking it.
        temp = _f(twin, "cabin.temperature", 20.0) - 0.4
        rh = _f(twin, "cabin.humidity_pct", 55.0)
        await twin.set_signal("esphome.cabin_node.temperature", round(temp, 1), source="esphome")
        await twin.set_signal("esphome.cabin_node.humidity", round(rh, 1), source="esphome")
