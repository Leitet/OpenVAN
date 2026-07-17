"""Home Assistant / MQTT — the smart-home bridge.

This is what makes the van part of the home. OpenVan both **consumes** entities
published with MQTT discovery and **exports** its own (`sensor.openvan_*`,
`binary_sensor.openvan_home`, …) so that when the van comes home it federates into
Home Assistant instead of disappearing into it.

The transport is a local MQTT broker (Mosquitto), fully offline-capable. In
simulation this driver just advertises the bridge as connected and publishes a
`home_assistant.van_home` presence flag derived from Wi-Fi/known-location state.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


class MqttHomeAssistant(Integration):
    info = IntegrationInfo(
        id="mqtt_homeassistant",
        name="Home Assistant / MQTT",
        category="connectivity",
        vendor="Home Assistant / Eclipse Mosquitto",
        transports=[Transport.MQTT, Transport.HTTP, Transport.WEBSOCKET],
        local=True,
        offline_capable=True,
        discovery="mdns",
        permissions=Permissions(read=True, control=True, configure=True),
        safety_class=2,  # can drive HA-side automations
        status=Status.NATIVE,
        priority="P0",
        provides=["home_assistant.connected", "home_assistant.van_home"],
        description=(
            "MQTT discovery both ways: import HA entities and export OpenVan's, so "
            "the van federates into the home when it arrives — never dissolves into it."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        await twin.set_signal("home_assistant.connected", True, source="mqtt_homeassistant")
        # "At home" when parked on the home Wi-Fi — modelled here as ignition off
        # near the saved home spot; the bench can force it via home_assistant.van_home.
        await twin.set_signal(
            "home_assistant.van_home",
            bool(twin.get("home_assistant.van_home")),
            source="mqtt_homeassistant",
        )
