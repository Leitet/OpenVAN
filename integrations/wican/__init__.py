"""WiCAN — OBD-II vehicle data over MQTT (MeatPi's ESP32 CAN adapter).

The smart-van community's favourite way to get engine data without touching the
CAN bus directly: a WiCAN dongle in the OBD port runs **AutoPID** and publishes
parsed vehicle parameters as flat JSON over MQTT — which rides OpenVan's
pure-stdlib MQTT client with zero new dependencies.

Wire format (from the wican-fw source, `main/autopid.c` / `main/mqtt.c`):

* status:  ``wican/<device_id>/status``  →  ``{"status": "online"}`` (retained)
* AutoPID: ``wican/<device_id>/can/rx`` (or a configured custom destination) →
  ``{"VehicleSpeed": 62, "EngineRPM": 1850, "FuelLevel": 43, "Lock": "on"}``
  — numbers, or "on"/"off" strings for binary parameters.

Parameters normalise to ``obd.<snake_case>`` twin signals (auto-surfaced as
entities via the declared prefix); ``VehicleSpeed`` additionally mirrors into
``vehicle.speed_kmh`` while live so the journey advisors run on real data.

> Topics/payloads per the wican-fw source — **unvalidated against a real WiCAN
> here** (hardware-validation backlog).
"""

from __future__ import annotations

import json
import re

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports.mqtt import AsyncMqttClient


def snake(name: str) -> str:
    """"VehicleSpeed" → "vehicle_speed"; keeps existing snake/kebab keys sane."""
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(name))
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def parse_autopid(payload: bytes) -> dict[str, float | bool]:
    """The AutoPID JSON → normalised measures. Unknown shapes are skipped, a
    malformed payload yields {} — a flaky dongle must never hurt the van."""
    try:
        data = json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, UnicodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, float | bool] = {}
    for key, value in data.items():
        name = snake(key)
        if not name:
            continue
        if isinstance(value, bool):
            out[name] = value
        elif isinstance(value, (int, float)):
            out[name] = float(value)
        elif isinstance(value, str) and value.lower() in ("on", "off"):
            out[name] = value.lower() == "on"
    return out


class Wican(Integration):
    info = IntegrationInfo(
        id="wican",
        name="WiCAN (OBD-II)",
        category="vehicle",
        vendor="MeatPi",
        transports=[Transport.MQTT],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.OPEN,  # open-source firmware, documented interface
        priority="P1",
        provides=[
            "obd.vehicle_speed", "obd.engine_rpm", "obd.fuel_level",
            "obd.coolant_temperature", "vehicle.speed_kmh (mirrored)",
        ],
        description=(
            "MeatPi's WiCAN dongle in the OBD-II port: engine data (speed, RPM, "
            "fuel, coolant…) via its AutoPID MQTT feed — rides the built-in MQTT "
            "client, no extras. Live speed feeds the journey advisors."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "mqtt"], "default": "sim"},
            {"key": "host", "label": "MQTT broker host", "type": "text"},
            {"key": "port", "label": "MQTT port", "type": "text", "default": "1883"},
            {"key": "username", "label": "Username", "type": "text"},
            {"key": "password", "label": "Password", "type": "text", "secret": True},
            {"key": "device_id", "label": "WiCAN device id", "type": "text",
             "default": "wican"},
            {"key": "topic", "label": "AutoPID topic (blank = wican/<id>/can/rx)",
             "type": "text"},
        ],
        warning="Topics per the wican-fw source — validate against a real WiCAN dongle.",
    )

    def transport_mode(self) -> str:
        return str(self.config.get("mode", "sim") or "sim")

    def _autopid_topic(self) -> str:
        custom = str(self.config.get("topic") or "").strip()
        if custom:
            return custom
        device = str(self.config.get("device_id") or "wican").strip() or "wican"
        return f"wican/{device}/can/rx"

    def _make_client(self) -> AsyncMqttClient:
        return AsyncMqttClient(
            str(self.config.get("host")),
            int(self.config.get("port") or 1883),
            client_id="openvan-wican",
            username=self.config.get("username") or None,
            password=self.config.get("password") or None,
        )

    async def run_transport(self) -> None:
        if self.transport_mode() != "mqtt" or not self.config.get("host"):
            raise NotImplementedError
        client = self._make_client()
        await client.connect()
        await client.subscribe(self._autopid_topic())
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        try:
            async for _topic, payload in client.messages():
                measures = parse_autopid(payload)
                for name, value in measures.items():
                    await self.twin.set_signal(f"obd.{name}", value, source=self.info.id)
                # The world's speed signal — live OBD provides it (like GPS would).
                if "vehicle_speed" in measures:
                    await self.twin.set_signal(
                        "vehicle.speed_kmh", measures["vehicle_speed"], source=self.info.id
                    )
        finally:
            await client.close()

    async def simulate(self, dt: float) -> None:
        def _f(key: str, default: float) -> float:
            try:
                return float(self.twin.get(key))
            except (TypeError, ValueError):
                return default

        speed = _f("vehicle.speed_kmh", 0.0)
        await self.twin.set_signal("obd.vehicle_speed", round(speed, 1), source=self.info.id)
        # Idle ~800 rpm, ~55 rpm per km/h in a tall gear — illustrative only.
        await self.twin.set_signal(
            "obd.engine_rpm",
            round(800.0 + speed * 55.0, 0) if self.twin.get("vehicle.ignition") else 0.0,
            source=self.info.id,
        )
        await self.twin.set_signal(
            "obd.fuel_level", _f("diesel_tank.level_pct", 70.0), source=self.info.id
        )
