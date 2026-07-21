"""Home Assistant bridge — the van federates into the home over MQTT.

When the van is on the home network, OpenVan announces its entities with **HA MQTT
Discovery** (retained config topics), streams their state, and accepts commands
back. Two principles shape it:

* **The van never dissolves into HA.** OpenVan stays the source of truth: HA gets
  a mirror (one "OpenVan" device with `sensor.openvan_*`, `light.openvan_*`, …)
  plus an availability topic backed by an MQTT Last Will — drive away and the
  entities go *unavailable*, they don't lie.
* **HA commands go through the safety layer** (Rule 2). A toggle flipped in HA
  becomes an `Intent` through `Hub.execute_intent` like any other command — if
  safety refuses (say, load-shedding at critical battery), the bridge re-publishes
  the *actual* state so the HA UI snaps back instead of showing fiction.

The mapping logic (entity → discovery config / state payload, command topic →
intent) is pure functions, unit-testable without a broker. :class:`HaBridge` is
the runtime that wires them to an :class:`~openvan_core.transports.AsyncMqttClient`
and the event bus; the ``mqtt_homeassistant`` integration owns its lifecycle.

The **import direction** rides HA's official *MQTT Statestream* integration:
HA publishes ``<statestream_base>/<domain>/<object_id>/state`` and the bridge
maps selected domains into ``ha.<domain>.<object_id>`` twin signals (auto-
surfaced as entities). Our own exported mirror (``openvan_*`` object ids) is
filtered out so the van never re-imports itself.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from .intents import Intent

if TYPE_CHECKING:  # pragma: no cover
    from .entities import Entity
    from .hub import Hub
    from .transports import AsyncMqttClient

logger = logging.getLogger(__name__)

# Entity domains we can express in HA's MQTT schema today. Cameras need an image
# transport; anything unknown is skipped rather than mis-announced.
_EXPORTABLE = {"sensor", "binary_sensor", "switch", "light", "climate"}


def object_id(entity_id: str) -> str:
    return entity_id.replace(".", "_")


def state_topic(base: str, entity_id: str) -> str:
    return f"{base}/{entity_id}/state"


def command_topics(base: str) -> list[str]:
    """The subscription filters for inbound commands (narrow — never our own
    state topics, or we'd hear our own echoes)."""
    return [f"{base}/+/set", f"{base}/+/+/set"]


# Domains worth importing as readings. Actuating *HA* devices from the van is a
# separate, later step — imports are strictly read-only.
_IMPORTABLE = {"sensor", "binary_sensor", "switch", "light", "device_tracker"}


def parse_statestream(prefix: str, topic: str, payload: bytes) -> tuple[str, Any] | None:
    """An HA MQTT-Statestream state message → ``("ha.<domain>.<object_id>", value)``.

    Filters: only importable domains; never our own exported ``openvan_*``
    mirror (no self-echo); ``unknown``/``unavailable`` yield nothing rather
    than a fake reading. Values: numbers parse to float, on/off-ish states to
    bool, anything else stays a (truncated) string."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != prefix or parts[3] != "state":
        return None
    domain, obj = parts[1], parts[2]
    if domain not in _IMPORTABLE or not obj or obj.startswith("openvan"):
        return None
    text = payload.decode("utf-8", "replace").strip()
    if not text or text.lower() in ("unknown", "unavailable", "none"):
        return None
    lowered = text.lower()
    value: Any
    if lowered in ("on", "true", "home", "open", "detected"):
        value = True
    elif lowered in ("off", "false", "not_home", "closed", "clear"):
        value = False
    else:
        try:
            value = float(text)
        except ValueError:
            value = text[:100]
    return f"ha.{domain}.{obj}", value


def _is_on(state: Any) -> bool:
    return state in (True, "on", "ON", "heating", 1)


def render_state(entity: "Entity") -> str:
    """The state payload HA reads for this entity."""
    if entity.domain in ("binary_sensor", "switch", "light"):
        return "ON" if _is_on(entity.state) else "OFF"
    if entity.domain == "climate":
        return "heat" if _is_on(entity.state) else "off"
    return "" if entity.state is None else str(entity.state)


def discovery(entity: "Entity", *, prefix: str, base: str, device: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The retained HA discovery announcement for one entity: (topic, payload).

    Returns None for domains we can't express (skipped, never mis-announced).
    """
    if entity.domain not in _EXPORTABLE:
        return None
    obj = object_id(entity.entity_id)
    payload: dict[str, Any] = {
        "name": entity.name,
        "unique_id": f"openvan_{obj}",
        "state_topic": state_topic(base, entity.entity_id),
        "availability_topic": f"{base}/availability",
        "device": device,
    }
    if entity.domain == "sensor":
        if entity.unit:
            payload["unit_of_measurement"] = entity.unit
        component = "sensor"
    elif entity.domain == "binary_sensor":
        component = "binary_sensor"
    elif entity.domain in ("switch", "light"):
        payload["command_topic"] = f"{base}/{entity.entity_id}/set"
        component = entity.domain
    else:  # climate
        setpoint = (entity.attributes or {}).get("setpoint")
        payload.pop("state_topic")  # climate uses per-facet topics
        payload.update(
            {
                "modes": ["off", "heat"],
                "mode_state_topic": state_topic(base, entity.entity_id),
                "mode_command_topic": f"{base}/{entity.entity_id}/mode/set",
                "temperature_state_topic": f"{base}/{entity.entity_id}/temp/state",
                "temperature_command_topic": f"{base}/{entity.entity_id}/temp/set",
                "min_temp": 5,
                "max_temp": 30,
                "temp_step": 0.5,
            }
        )
        if setpoint is not None:
            payload["initial"] = setpoint
        component = "climate"
    return f"{prefix}/{component}/openvan/{obj}/config", payload


def parse_command(base: str, topic: str, payload: bytes) -> Intent | None:
    """An inbound MQTT command topic → a safety-checked Intent (or None)."""
    if not topic.startswith(base + "/") or not topic.endswith("/set"):
        return None
    parts = topic[len(base) + 1 : -len("/set")].rstrip("/").split("/")
    text = payload.decode("utf-8", "replace").strip()
    entity_id = parts[0]
    if len(parts) == 1:  # switch / light: ON | OFF
        command = "turn_on" if text.upper() == "ON" else "turn_off"
        return Intent(entity_id, command, source="automation", raw_text=f"HA: {text}")
    facet = parts[1]
    if facet == "mode":  # climate: heat | off
        command = "turn_on" if text.lower() == "heat" else "turn_off"
        return Intent(entity_id, command, source="automation", raw_text=f"HA: {text}")
    if facet == "temp":
        try:
            return Intent(
                entity_id, "set_temperature", params={"temperature": float(text)},
                source="automation", raw_text=f"HA: {text}",
            )
        except ValueError:
            return None
    return None


class HaBridge:
    """Runs the export + command loop over a connected MQTT client."""

    def __init__(
        self,
        client: "AsyncMqttClient",
        hub: "Hub",
        bus: Any,
        *,
        prefix: str = "homeassistant",
        base: str = "openvan",
        twin: Any = None,
        import_prefix: str | None = None,
        import_source: str = "mqtt_homeassistant",
    ) -> None:
        self.client = client
        self.hub = hub
        self.bus = bus
        self.prefix = prefix
        self.base = base
        # Statestream import (read-only): set both to enable.
        self.twin = twin
        self.import_prefix = import_prefix
        self.import_source = import_source
        from . import __version__

        self.device = {
            "identifiers": ["openvan"],
            "name": "OpenVan",
            "manufacturer": "OpenVan",
            "sw_version": __version__,
        }
        self._unsubs: list[Callable[[], None]] = []

    @property
    def availability_topic(self) -> str:
        return f"{self.base}/availability"

    # --- publishing -------------------------------------------------------

    async def announce_entity(self, entity: "Entity") -> None:
        found = discovery(entity, prefix=self.prefix, base=self.base, device=self.device)
        if found is None:
            return
        topic, payload = found
        await self.client.publish(topic, json.dumps(payload).encode(), retain=True)
        await self.publish_state(entity)

    async def publish_state(self, entity: "Entity") -> None:
        if entity.domain not in _EXPORTABLE:
            return
        await self.client.publish(
            state_topic(self.base, entity.entity_id), render_state(entity).encode(), retain=True
        )
        if entity.domain == "climate":
            setpoint = (entity.attributes or {}).get("setpoint")
            if setpoint is not None:
                await self.client.publish(
                    f"{self.base}/{entity.entity_id}/temp/state", str(setpoint).encode(), retain=True
                )

    async def announce_all(self) -> None:
        await self.client.publish(self.availability_topic, b"online", retain=True)
        for entity in list(self.hub.entities.values()):
            await self.announce_entity(entity)

    async def remove_entity(self, entity_id: str) -> None:
        # An empty retained payload deletes the discovery entry in HA.
        for component in ("sensor", "binary_sensor", "switch", "light", "climate"):
            await self.client.publish(
                f"{self.prefix}/{component}/openvan/{object_id(entity_id)}/config", b"", retain=True
            )

    # --- the loop ---------------------------------------------------------

    async def run(self) -> None:
        """Announce, then serve until the connection drops. Assumes a connected
        client subscribed by us; cleans up its bus taps on the way out."""
        for f in command_topics(self.base):
            await self.client.subscribe(f)
        await self.client.subscribe(f"{self.prefix}/status")
        if self.twin is not None and self.import_prefix:
            await self.client.subscribe(f"{self.import_prefix}/+/+/state")
        await self.announce_all()

        async def _on_state(event) -> None:
            entity = self.hub.entities.get(event.data.get("entity", {}).get("entity_id", ""))
            if entity is not None:
                await self.publish_state(entity)

        async def _on_registered(event) -> None:
            entity = self.hub.entities.get(event.data.get("entity", {}).get("entity_id", ""))
            if entity is not None:
                await self.announce_entity(entity)

        async def _on_removed(event) -> None:
            entity_id = event.data.get("entity_id")
            if entity_id:
                await self.remove_entity(entity_id)

        self._unsubs = [
            self.bus.subscribe("entity.state_changed", _on_state),
            self.bus.subscribe("entity.registered", _on_registered),
            self.bus.subscribe("entity.removed", _on_removed),
        ]
        try:
            async for topic, payload in self.client.messages():
                if topic == f"{self.prefix}/status":
                    # HA restarted → it lost non-retained context; announce again.
                    if payload.decode("utf-8", "replace").strip() == "online":
                        await self.announce_all()
                    continue
                if self.twin is not None and self.import_prefix:
                    hit = parse_statestream(self.import_prefix, topic, payload)
                    if hit is not None:
                        await self.twin.set_signal(hit[0], hit[1], source=self.import_source)
                        continue
                await self._handle_command(topic, payload)
        finally:
            for unsub in self._unsubs:
                unsub()
            self._unsubs = []

    async def _handle_command(self, topic: str, payload: bytes) -> None:
        intent = parse_command(self.base, topic, payload)
        if intent is None:
            return
        result = await self.hub.execute_intent(intent)
        if not result.ok:
            logger.info("HA command %s refused: %s", topic, result.reason)
        # Either way, re-publish the *actual* state — a safety-refused toggle must
        # snap back in the HA UI rather than pretend it happened.
        entity = self.hub.entities.get(intent.entity_id)
        if entity is not None:
            await self.publish_state(entity)
