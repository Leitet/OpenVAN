"""ESPHome — DIY sensors and IO over the native API.

ESPHome nodes (ESP32/ESP8266) are how most builders add their own sensors,
relays and buttons. They speak a documented local **native API** (and can also
publish over MQTT), work fully offline, and are trivially discoverable via mDNS.
This is the second-most-important integration after Victron: it's the seam for
everything the reference van doesn't ship natively.

Two modes (Settings → Integrations):

* ``sim`` (default) — models a small cabin sensor node (SHT-class temp/humidity),
  deriving believable readings from the twin's cabin climate so it tracks the env.
* ``native_api`` — connects to a real node with **aioesphomeapi** (an *optional*
  extra: ``pip install -e ".[esphome]"``), lists its entities and streams their
  state into the twin as ``esphome.<device>.<object_id>`` signals. Falls back to
  ``sim`` when the library isn't installed or the node is unreachable (offline-first).

Unlike Victron's fixed register map, an ESPHome node exposes whatever entities the
user defined, so normalisation is generic — one twin signal per entity. Surfacing
those as semantic entities on a tab is a separate step (see backlog).

> The native-API path is written to the documented aioesphomeapi surface but is
> **unvalidated against a real node here** (no device/library in this env). Confirm
> on real hardware before relying on it.
"""

from __future__ import annotations

import asyncio
import re

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

_STOP = object()  # queue sentinel: the node's connection stopped


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


def _slug(name: str) -> str:
    """Device name → a signal-safe slug ('Cabin Node' → 'cabin_node')."""
    return re.sub(r"[^a-z0-9]+", "_", (name or "esphome").lower()).strip("_") or "esphome"


def esphome_signal(device: str, object_id: str) -> str:
    return f"esphome.{_slug(device)}.{object_id}"


def coerce(value):
    """ESPHome states are typed — keep bools as bools, round numbers, pass the rest."""
    if isinstance(value, bool):
        return value
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return value


class _EspClient:
    """Thin adapter over ``aioesphomeapi.APIClient`` — isolates the vendor surface so
    the transport loop (and its tests) don't depend on the library's exact shape."""

    def __init__(self, cli) -> None:
        self._cli = cli

    async def device_name(self) -> str:
        info = await self._cli.device_info()
        return getattr(info, "name", "esphome")

    async def entity_keys(self) -> dict:
        entities, _services = await self._cli.list_entities_services()
        return {e.key: e.object_id for e in entities if getattr(e, "object_id", None)}

    def subscribe_states(self, on_state) -> None:
        def _cb(state):
            value = getattr(state, "state", None)
            if value is None or getattr(state, "missing_state", False):
                return
            on_state(state.key, value)

        self._cli.subscribe_states(_cb)

    async def disconnect(self) -> None:
        await self._cli.disconnect()


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
        provides=["esphome.<device>.<entity>"],
        description=(
            "ESP32/ESP8266 nodes over the documented native API. The seam for "
            "custom sensors, relays and buttons — fully local and offline."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "native_api"], "default": "sim"},
            {"key": "host", "label": "Node host / IP", "type": "text"},
            {"key": "port", "label": "Port", "type": "text", "default": "6053"},
            {"key": "password", "label": "API password", "type": "text", "secret": True},
            {"key": "encryption_key", "label": "Encryption key (noise PSK)", "type": "text", "secret": True},
        ],
        warning="Native-API transport needs the 'esphome' extra and is unvalidated against real hardware.",
    )

    async def _open_client(self, host: str, port: int, on_stop) -> _EspClient:
        """Connect to a real node. Overridable in tests (inject a fake client)."""
        try:
            from aioesphomeapi import APIClient
        except ImportError as exc:  # optional extra not installed → stay simulated
            raise NotImplementedError("aioesphomeapi not installed (pip install '.[esphome]')") from exc
        cli = APIClient(
            host, port, self.config.get("password") or "",
            noise_psk=self.config.get("encryption_key") or None,
        )
        await cli.connect(on_stop=on_stop, login=True)
        return _EspClient(cli)

    async def run_transport(self) -> None:
        if self.transport_mode() != "native_api":
            raise NotImplementedError
        host = self.config.get("host")
        if not host:
            raise NotImplementedError  # nothing to connect to → stay simulated

        queue: asyncio.Queue = asyncio.Queue()
        client = await self._open_client(host, int(self.config.get("port") or 6053), lambda *a: queue.put_nowait(_STOP))
        try:
            device = await client.device_name()
            keymap = await client.entity_keys()

            def on_state(key, value):
                obj = keymap.get(key)
                if obj is not None:
                    queue.put_nowait((obj, value))

            client.subscribe_states(on_state)
            self.live = True
            await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
            while True:
                item = await queue.get()
                if item is _STOP:
                    raise ConnectionError("esphome node disconnected")
                obj, value = item
                await self.twin.set_signal(esphome_signal(device, obj), coerce(value), source=self.info.id)
        finally:
            await client.disconnect()

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        # A cabin node reads a touch below the twin's cabin sensor, tracking it.
        temp = _f(twin, "cabin.temperature", 20.0) - 0.4
        rh = _f(twin, "cabin.humidity_pct", 55.0)
        await twin.set_signal("esphome.cabin_node.temperature", round(temp, 1), source="esphome")
        await twin.set_signal("esphome.cabin_node.humidity", round(rh, 1), source="esphome")
