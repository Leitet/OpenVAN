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

    async def switches(self) -> list[dict]:
        """The node's controllable switch entities: [{key, object_id, name}]."""
        entities, _services = await self._cli.list_entities_services()
        return [
            {"key": e.key, "object_id": e.object_id, "name": getattr(e, "name", e.object_id)}
            for e in entities
            if type(e).__name__ == "SwitchInfo" and getattr(e, "object_id", None)
        ]

    async def switch_command(self, key: int, state: bool) -> None:
        self._cli.switch_command(key, state)

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
    _client: _EspClient | None = None
    _switch_keys: dict  # signal -> native-API key (populated per connection)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None
        self._switch_keys = {}

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

    async def setup_sim_controls(self) -> None:
        # The sim cabin node carries a relay (say, an awning light) so the whole
        # command path — intent → safety → send_command → twin echo → entity —
        # is exercisable with no hardware (Rule 1).
        await self.register_control(
            "esphome.cabin_node.relay", "switch.esphome_cabin_node_relay", "Cabin Node Relay"
        )

    async def send_command(self, signal: str, value) -> None:
        # Live node: push over the native API; the device's state echo comes back
        # via subscribe_states → twin → entity. Otherwise: the sim twin write.
        key = self._switch_keys.get(signal)
        if self.live and self._client is not None and key is not None:
            await self._client.switch_command(key, bool(value))
            return
        await super().send_command(signal, value)

    async def run_transport(self) -> None:
        if self.transport_mode() != "native_api":
            raise NotImplementedError
        host = self.config.get("host")
        if not host:
            raise NotImplementedError  # nothing to connect to → stay simulated

        queue: asyncio.Queue = asyncio.Queue()
        client = await self._open_client(host, int(self.config.get("port") or 6053), lambda *a: queue.put_nowait(_STOP))
        try:
            self._client = client
            device = await client.device_name()
            keymap = await client.entity_keys()
            # Announce the node's switches as safety-checked controls.
            for sw in await client.switches():
                signal = esphome_signal(device, sw["object_id"])
                self._switch_keys[signal] = sw["key"]
                await self.register_control(
                    signal, "switch." + signal.replace(".", "_"), sw["name"]
                )

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
            self._client = None
            self._switch_keys = {}
            await client.disconnect()

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        # A cabin node reads a touch below the twin's cabin sensor, tracking it.
        temp = _f(twin, "cabin.temperature", 20.0) - 0.4
        rh = _f(twin, "cabin.humidity_pct", 55.0)
        await twin.set_signal("esphome.cabin_node.temperature", round(temp, 1), source="esphome")
        await twin.set_signal("esphome.cabin_node.humidity", round(rh, 1), source="esphome")
