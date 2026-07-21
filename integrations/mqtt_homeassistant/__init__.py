"""Home Assistant / MQTT — the smart-home bridge.

This is what makes the van part of the home. In ``mqtt`` mode the driver connects
to the home's MQTT broker and runs the **HA bridge**
(:mod:`openvan_core.habridge`): OpenVan's entities are announced with HA MQTT
Discovery (one "OpenVan" device: ``sensor.openvan_*``, ``light.openvan_*``,
``climate.openvan_*``, …), their state streams live, and commands flipped in HA
come back as Intents **through the safety layer** (Rule 2). An availability topic
backed by an MQTT Last Will means driving away marks the entities *unavailable* in
HA — the van federates into the home, it never dissolves into it.

Modes (Settings → Integrations):

* ``sim`` (default) — advertises the bridge as connected and reflects the bench's
  `home_assistant.van_home` presence flag; the bridge logic itself is exercised
  in tests against a loopback broker (Rule 1).
* ``mqtt`` — the real thing, against the home broker (host/port/credentials in the
  integration config). Falls back to sim whenever the broker is unreachable.

Importing *other* HA devices into the van is a later step (see backlog).
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.habridge import HaBridge
from openvan_core.transports import AsyncMqttClient


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
        safety_class=2,  # inbound commands — but always via the safety layer
        status=Status.NATIVE,
        priority="P0",
        provides=["home_assistant.connected", "home_assistant.van_home",
                  "ha.<domain>.<object_id> (imported via MQTT Statestream)"],
        description=(
            "MQTT discovery both ways: export OpenVan's entities to Home Assistant "
            "(one OpenVan device, commands returning through the safety layer) AND "
            "import the home's sensors via HA's MQTT Statestream — the van "
            "federates into the home when it arrives, never dissolves into it."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "mqtt"], "default": "sim"},
            {"key": "host", "label": "Broker host / IP", "type": "text"},
            {"key": "port", "label": "Port", "type": "text", "default": "1883"},
            {"key": "username", "label": "Username", "type": "text"},
            {"key": "password", "label": "Password", "type": "text", "secret": True},
            {"key": "discovery_prefix", "label": "Discovery prefix", "type": "text",
             "default": "homeassistant"},
            {"key": "base_topic", "label": "Base topic", "type": "text", "default": "openvan"},
            {"key": "import_statestream", "label": "Import HA sensors (Statestream)",
             "type": "select", "options": ["yes", "no"], "default": "yes"},
            {"key": "statestream_prefix", "label": "Statestream base topic", "type": "text",
             "default": "homeassistant_statestream"},
        ],
    )

    async def run_transport(self) -> None:
        if self.transport_mode() != "mqtt":
            raise NotImplementedError
        host = self.config.get("host")
        if not host or self.hub is None:
            raise NotImplementedError  # nothing to connect to → stay simulated

        base = str(self.config.get("base_topic") or "openvan")
        client = AsyncMqttClient(
            host,
            int(self.config.get("port") or 1883),
            client_id="openvan-ha-bridge",
            username=self.config.get("username") or None,
            password=self.config.get("password") or None,
            # The broker announces our death: availability → offline, retained.
            will_topic=f"{base}/availability",
            will_payload=b"offline",
        )
        await client.connect()
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        await self.twin.set_signal("home_assistant.connected", True, source=self.info.id)
        wants_import = str(self.config.get("import_statestream", "yes")) != "no"
        bridge = HaBridge(
            client,
            self.hub,
            self.bus,
            prefix=str(self.config.get("discovery_prefix") or "homeassistant"),
            base=base,
            twin=self.twin if wants_import else None,
            import_prefix=(
                str(self.config.get("statestream_prefix") or "homeassistant_statestream")
                if wants_import else None
            ),
            import_source=self.info.id,
        )
        try:
            await bridge.run()
        finally:
            await self.twin.set_signal("home_assistant.connected", False, source=self.info.id)
            await client.close()

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
        # A taste of the import direction with no broker (Rule 1): one imported
        # home sensor, so the ha.* auto-entities are visible in the catalog demo.
        await twin.set_signal(
            "ha.sensor.home_temperature", 21.5, source="mqtt_homeassistant"
        )
