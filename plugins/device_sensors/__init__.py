"""Device sensors — auto-surface an integration's arbitrary readings as entities.

Most of OpenVan's plugins map *known* signals to entities (battery SoC, cabin temp).
But an ESPHome node or a RuuviTag exposes whatever the user defined — a fridge probe,
a bedroom sensor, a pressure reading — with keys not known ahead of time. Rather than
hand-write a plugin per device, this one **watches a set of signal prefixes** (e.g.
``ruuvitag.``, ``esphome.``) and registers a `sensor.<…>` entity for each key it sees,
guessing a unit and a friendly name from the key. So enabling an integration makes its
readings appear in the UI with no extra code — the "protocols not per-model" philosophy,
extended from signals to entities.

Reads only through the backend (via ``watch_prefix`` / ``snapshot``), so it runs against
the twin today and a real backend tomorrow. Read-only; category "sensors".
"""

from __future__ import annotations

import re

from openvan_core import Entity, Plugin

# Signal namespaces to surface. Kept to device-owned extras — the *core* van signals
# (battery, water, climate) already have their own dedicated plugins/entities.
DEFAULT_PREFIXES = ("ruuvitag.", "esphome.", "signalk.", "bthome.", "mopeka.", "blebms.", "tpms.", "victronble.", "epever.", "cdh.")

# Unit guessed from the last path segment (best-effort — a raw signal carries none).
_UNIT_HINTS = (
    ("temperature", "°C"),
    ("humidity", "%"),
    ("battery", "V"),
    ("power", "W"),
    ("pressure", "hPa"),
    ("signal", "%"),
    ("voltage", "V"),
    ("current", "A"),
)


def entity_id_for(key: str) -> str:
    return "sensor." + re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def name_for(key: str) -> str:
    # Drop the ecosystem prefix; humanise the rest ("cabin_node.temperature" → "Cabin Node Temperature").
    parts = key.split(".")[1:] or [key]
    return " ".join(p.replace("_", " ").title() for p in parts)


def unit_for(key: str) -> str | None:
    last = key.rsplit(".", 1)[-1]
    for hint, unit in _UNIT_HINTS:
        if hint in last:
            return unit
    return None


class DeviceSensors(Plugin):
    domain = "device_sensors"
    name = "Device Sensors"
    version = "0.1.0"
    categories = ["sensors"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []
        self._known: set[str] = set()

    def _prefixes(self) -> tuple[str, ...]:
        configured = tuple(self.config.get("prefixes") or DEFAULT_PREFIXES)
        # Self-contained drivers: prefixes declared by enabled integrations
        # (descriptor `provides`) are honoured automatically — no edit to the
        # bundled list needed. The manager caches this, so it's cheap per event.
        manager = getattr(self.hub, "integrations", None)
        dynamic = manager.declared_prefixes() if manager is not None else ()
        return tuple(dict.fromkeys(configured + dynamic))

    async def async_setup(self) -> None:
        # Surface anything already present, then watch *all* signals and filter
        # per event — the dynamic prefix set grows when integrations are enabled
        # later, so a fixed per-prefix watcher registration would miss them.
        for key, value in self.backend.snapshot().items():
            if key.startswith(self._prefixes()):
                await self._apply(key, value)
        self._unwatchers.append(self.backend.watch_prefix("", self._on_signal))

    async def _on_signal(self, key: str, value) -> None:
        if key.startswith(self._prefixes()):
            await self._apply(key, value)

    async def _apply(self, key: str, value) -> None:
        # A signal owned by a *control* entity (a switch an integration registered
        # through the safety layer) must not be duplicated as a read-only sensor.
        for other in self.hub.entities.values():
            attrs = other.attributes or {}
            if attrs.get("device_control") and attrs.get("signal") == key:
                return
        eid = entity_id_for(key)
        # Never hijack an entity another plugin owns (e.g. a driver whose
        # `provides` also lists core mirrors like house_battery.soc — the
        # dedicated battery entity already covers it).
        if eid not in self._known and eid in self.hub.entities:
            return
        if eid not in self._known:
            self._known.add(eid)
            await self.hub.register_entity(
                Entity(
                    entity_id=eid,
                    name=name_for(key),
                    domain="sensor",
                    category="sensors",
                    state=value,
                    unit=unit_for(key),
                    attributes={"device_sensor": True, "signal": key},
                )
            )
        else:
            await self.hub.set_state(eid, value)

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
