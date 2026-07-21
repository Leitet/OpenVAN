"""Tasmota — MQTT smart switches/plugs/sensors (the VanPi-adjacent ecosystem).

Tasmota's MQTT interface is stable and documented: a device with topic ``t``
publishes ``stat/<t>/POWER`` (``ON``/``OFF``), ``tele/<t>/STATE`` (JSON with
``POWER``, Wi-Fi RSSI…) and ``tele/<t>/SENSOR`` (JSON with whatever sensors are
attached — energy monitors, temperature probes…); it is commanded via
``cmnd/<t>/POWER``. Rides OpenVan's pure-stdlib MQTT client.

The device list is **configuration** on this card (the dedicated settings
page): each row = one Tasmota device (its MQTT topic + a friendly name). Per
device you get a safety-checked switch entity and auto-surfaced sensor
entities (``tasmota.<topic>.<measure>``).

**Rule 2**: commands only arrive via ``Hub.execute_intent`` → safety →
``send_command`` — live, that publishes ``cmnd/<t>/POWER`` and the device's own
``stat`` echo drives the entity; a safety-refused command never reaches the
broker. Sim mode exercises the same path against the twin.

> Interface per Tasmota's documented MQTT API — **unvalidated against a real
> Tasmota device here** (hardware-validation backlog).
"""

from __future__ import annotations

import json
import re
from typing import Any

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports.mqtt import AsyncMqttClient

DEFAULT_DEVICES = [{"topic": "tasmota_plug", "name": "Tasmota plug"}]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_")


def flatten_sensor(payload: bytes) -> dict[str, float]:
    """``tele/<t>/SENSOR`` JSON → flat numeric measures:
    ``{"ENERGY": {"Power": 12.4}, "AM2301": {"Temperature": 21.5}}`` →
    ``{"energy_power": 12.4, "am2301_temperature": 21.5}``. Non-numeric leaves
    and malformed payloads are skipped."""
    try:
        data = json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, UnicodeError):
        return {}
    out: dict[str, float] = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() == "time":
                    continue
                walk(f"{prefix}_{_slug(key)}" if prefix else _slug(key), value)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if prefix:
                out[prefix] = float(node)

    if isinstance(data, dict):
        walk("", data)
    return out


def parse_power(payload: bytes) -> bool | None:
    text = payload.decode("utf-8", "replace").strip().upper()
    if text in ("ON", "1", "TRUE"):
        return True
    if text in ("OFF", "0", "FALSE"):
        return False
    return None


class Tasmota(Integration):
    info = IntegrationInfo(
        id="tasmota",
        name="Tasmota devices",
        category="energy",
        vendor="Tasmota / open source",
        transports=[Transport.MQTT],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control=True, configure=True),
        safety_class=1,
        status=Status.OPEN,
        priority="P1",
        provides=["tasmota.<topic>.on", "tasmota.<topic>.energy_power"],
        description=(
            "Tasmota smart switches, plugs and sensor nodes over their documented "
            "MQTT interface — add each device's topic on this card; you get a "
            "safety-checked switch plus auto-surfaced sensor readings. "
            "VanPi-ecosystem friendly."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "mqtt"], "default": "sim"},
            {"key": "host", "label": "MQTT broker host", "type": "text"},
            {"key": "port", "label": "MQTT port", "type": "text", "default": "1883"},
            {"key": "username", "label": "Username", "type": "text"},
            {"key": "password", "label": "Password", "type": "text", "secret": True},
            {
                "key": "devices",
                "label": "Devices",
                "type": "list",
                "default": DEFAULT_DEVICES,
                "item_fields": [
                    {"key": "topic", "label": "MQTT topic", "type": "text"},
                    {"key": "name", "label": "Name", "type": "text"},
                ],
            },
        ],
        warning="MQTT interface per Tasmota docs — validate against a real device.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client: AsyncMqttClient | None = None

    def transport_mode(self) -> str:
        return str(self.config.get("mode", "sim") or "sim")

    def devices(self) -> list[dict[str, str]]:
        configured = self.config.get("devices")
        rows = configured if isinstance(configured, list) else DEFAULT_DEVICES
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            topic = _slug(row.get("topic", ""))
            if not topic or topic in seen:
                continue
            seen.add(topic)
            out.append({"topic": topic, "name": str(row.get("name") or topic)})
        return out

    # --- controls (Rule 2) ------------------------------------------------

    async def setup_sim_controls(self) -> None:
        await self._register_device_controls()

    async def _register_device_controls(self) -> None:
        for device in self.devices():
            await self.register_control(
                signal=f"tasmota.{device['topic']}.on",
                entity_id=f"switch.tasmota_{device['topic']}",
                name=device["name"],
                category="energy",
            )

    async def send_command(self, signal: str, value: Any) -> None:
        # Only ever called AFTER the safety layer approved the intent. Live: the
        # command goes to the broker and the device's stat echo drives the state.
        if self.live and self._client is not None:
            topic = signal.split(".")[1]
            await self._client.publish(
                f"cmnd/{topic}/POWER", b"ON" if value else b"OFF"
            )
            return
        await super().send_command(signal, value)

    # --- transport --------------------------------------------------------

    async def run_transport(self) -> None:
        if self.transport_mode() != "mqtt" or not self.config.get("host"):
            raise NotImplementedError
        client = AsyncMqttClient(
            str(self.config.get("host")),
            int(self.config.get("port") or 1883),
            client_id="openvan-tasmota",
            username=self.config.get("username") or None,
            password=self.config.get("password") or None,
        )
        await client.connect()
        topics = {d["topic"] for d in self.devices()}
        for topic in topics:
            await client.subscribe(f"stat/{topic}/POWER")
            await client.subscribe(f"tele/{topic}/+")
        self._client = client
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        await self._register_device_controls()
        try:
            async for topic, payload in client.messages():
                parts = topic.split("/")
                if len(parts) != 3 or parts[1] not in topics:
                    continue
                device = parts[1]
                if parts[0] == "stat" and parts[2] == "POWER":
                    power = parse_power(payload)
                    if power is not None:
                        await self.twin.set_signal(
                            f"tasmota.{device}.on", power, source=self.info.id
                        )
                elif parts[0] == "tele" and parts[2] == "SENSOR":
                    for measure, value in flatten_sensor(payload).items():
                        await self.twin.set_signal(
                            f"tasmota.{device}.{measure}", value, source=self.info.id
                        )
                elif parts[0] == "tele" and parts[2] == "STATE":
                    power = None
                    try:
                        power = json.loads(payload.decode("utf-8", "replace")).get("POWER")
                    except (ValueError, UnicodeError, AttributeError):
                        pass
                    if isinstance(power, str):
                        await self.twin.set_signal(
                            f"tasmota.{device}.on", power.upper() == "ON",
                            source=self.info.id,
                        )
        finally:
            self._client = None
            await client.close()

    async def simulate(self, dt: float) -> None:
        # A plugged-in load draws when switched on — illustrative, bench-drivable.
        for device in self.devices():
            on = bool(self.twin.get(f"tasmota.{device['topic']}.on"))
            await self.twin.set_signal(
                f"tasmota.{device['topic']}.energy_power",
                8.5 if on else 0.0,
                source=self.info.id,
            )
