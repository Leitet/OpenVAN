"""Mopeka Pro Check — BLE ultrasonic tank sensors (LPG, water, diesel).

The RV answer to "tank gauges that actually work": a puck magnet-mounted under
the tank broadcasts liquid height over BLE. This driver parses the Pro Check
advertisement (manufacturer id 0x0059) per the community-documented format used
by the ESPHome/HA integrations, and — the layering payoff — can mirror the level
into a core tank signal (``propane.level_pct`` by default), so the existing
LowPropane advisor works with real hardware unchanged.

Built on the shared BLE substrate (no radio ownership; sim radio = bench-injected
frames, ``ble`` extra = real air).

> Format and speed-of-sound coefficients follow the community reverse
> engineering (ESPHome ``mopeka_pro_check``) and are **unvalidated against a
> real puck here** — flagged in the hardware-validation backlog.
"""

from __future__ import annotations

from openvan_core.ble import alias_for, find_alias
from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

MOPEKA_MANUFACTURER_ID = 0x0059

# Tank height presets (mm) for the percent conversion; overridable in config.
_DEFAULT_TANK_MM = 254.0  # a common vertical 20 lb / 5 kg LPG cylinder


def parse_mopeka(payload: bytes) -> dict[str, float] | None:
    """Pro Check advertisement → readings (community-RE'd format).

    battery = (b1 & 0x7f)/32 V · temp = (b2 & 0x7f)-40 °C ·
    raw level = ((b4<<8)|b3) & 0x3fff · quality = b4>>6 ·
    mm = raw × lpg speed-of-sound poly(temp).
    """
    if len(payload) < 5:
        return None
    battery_v = (payload[1] & 0x7F) / 32.0
    temp_c = float(payload[2] & 0x7F) - 40.0
    raw = ((payload[4] << 8) | payload[3]) & 0x3FFF
    quality = payload[4] >> 6
    coef = 0.573045 - 0.002822 * temp_c - 0.00000535 * temp_c * temp_c
    level_mm = max(0.0, raw * coef)
    return {
        "battery_v": round(battery_v, 3),
        "temperature": round(temp_c, 1),
        "level_mm": round(level_mm, 1),
        "quality": float(quality),
    }


def level_pct(level_mm: float, tank_mm: float) -> float:
    if tank_mm <= 0:
        return 0.0
    return round(max(0.0, min(100.0, level_mm / tank_mm * 100.0)), 1)


class Mopeka(Integration):
    info = IntegrationInfo(
        id="mopeka",
        name="Mopeka Pro Check",
        category="water",
        vendor="Mopeka",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.COMMUNITY,
        priority="P1",
        provides=["mopeka.<device>.level_pct", "mopeka.<device>.level_mm",
                  "mopeka.<device>.battery_v", "propane.level_pct (mirrored)"],
        description=(
            "Ultrasonic BLE tank pucks for LPG/water/diesel — the 'gauge that "
            "works'. Mirrors into the van's tank level so tank advisors run on "
            "real hardware."
        ),
        config_fields=[
            {"key": "aliases", "label": "Devices", "type": "list", "default": [],
             "item_fields": [
                 {"key": "id", "label": "MAC / id", "type": "text"},
                 {"key": "alias", "label": "Name", "type": "text"},
                 {"key": "tank", "label": "Feeds tank", "type": "select",
                  "options": ["", "propane", "fresh", "grey", "diesel", "none"]},
             ]},
            {"key": "tank", "label": "Feeds tank", "type": "select",
             "options": ["propane", "fresh", "grey", "diesel", "none"], "default": "propane"},
            {"key": "tank_height_mm", "label": "Tank height (mm)", "type": "text", "default": "254"},
        ],
        warning="Advertisement format per community reverse engineering — validate against a real puck.",
    )

    _TANK_SIGNAL = {
        "propane": "propane.level_pct",
        "fresh": "fresh_water.level_pct",
        "grey": "grey_water.level_pct",
        "diesel": "diesel_tank.level_pct",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsub = None

    def _tank_mm(self) -> float:
        try:
            return float(self.config.get("tank_height_mm") or _DEFAULT_TANK_MM)
        except (TypeError, ValueError):
            return _DEFAULT_TANK_MM

    async def async_setup(self) -> None:
        await super().async_setup()
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, manufacturer_id=MOPEKA_MANUFACTURER_ID)
            self.live = getattr(self.ble, "plan", None) == "bleak"

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_teardown()

    async def _on_adv(self, adv) -> None:
        data = parse_mopeka(adv.manufacturer_data.get(MOPEKA_MANUFACTURER_ID, b""))
        if data is None:
            return
        fallback = adv.address.replace(":", "").lower()[-4:] or "puck"
        device = alias_for(self.config.get("aliases"), adv.address, fallback)
        pct = level_pct(data["level_mm"], self._tank_mm())
        for measure, value in {**data, "level_pct": pct}.items():
            await self.twin.set_signal(f"mopeka.{device}.{measure}", value, source=self.info.id)
        # The layering payoff: feed the core tank signal so existing advisors
        # (LowPropane, water) run on real hardware unchanged.
        # Per-device tank assignment beats the card-wide default — two pucks can
        # feed two different tanks.
        row = find_alias(self.config.get("aliases"), adv.address)
        tank = (row or {}).get("tank") or self.config.get("tank") or "propane"
        signal = self._TANK_SIGNAL.get(str(tank))
        if signal:
            await self.twin.set_signal(signal, pct, source=self.info.id)

    async def simulate(self, dt: float) -> None:
        # A canned puck mirroring the seeded propane level, so the catalog demo
        # shows plausible data with zero setup.
        try:
            pct = float(self.twin.get("propane.level_pct"))
        except (TypeError, ValueError):
            pct = 60.0
        await self.twin.set_signal("mopeka.demo.level_pct", round(pct, 1), source="mopeka")
        await self.twin.set_signal("mopeka.demo.battery_v", 2.9, source="mopeka")
