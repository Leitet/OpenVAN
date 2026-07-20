"""Victron Instant Readout — SmartShunt/SmartSolar over BLE, no GX needed.

Most vans have a Victron SmartShunt or SmartSolar but **no** Cerbo/Venus device —
the fleet our `victron_venus` driver can't reach. Victron broadcasts "Instant
Readout" advertisements (manufacturer id 0x02E1), AES-CTR-encrypted with a
per-device key the user copies from VictronConnect (device → Settings → Product
info → Encryption data).

Format per Victron's published documentation and the reference `victron-ble`
implementation: header `[prefix u16][model u16][record u8][iv u16le][keycheck]`,
then ciphertext; AES-128-CTR (little-endian counter = iv) via our FIPS-pinned
pure-stdlib `aesctr`. Records are LSB-first bit-packed; v1 parses the two big
ones — battery monitor (0x02) and solar charger (0x01).

> Unvalidated against real devices here — flagged in the hardware-validation
> backlog. Bit layouts are pinned by synthetic round-trip vectors.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.aesctr import aes128_ctr

VICTRON_MANUFACTURER_ID = 0x02E1
RECORD_SOLAR = 0x01
RECORD_BATTERY_MONITOR = 0x02


class BitReader:
    """LSB-first bit reader (victron-ble semantics)."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def unsigned(self, n: int) -> int:
        v = 0
        for i in range(n):
            if self.pos >> 3 >= len(self.data):
                break
            v |= ((self.data[self.pos >> 3] >> (self.pos & 7)) & 1) << i
            self.pos += 1
        return v

    def signed(self, n: int) -> int:
        v = self.unsigned(n)
        return v - (1 << n) if v & (1 << (n - 1)) else v


def decrypt(data: bytes, key: bytes) -> tuple[int, bytes] | None:
    """Manufacturer payload → (record_type, plaintext) or None (wrong key/frame)."""
    if len(data) < 9:
        return None
    record_type = data[4]
    iv = int.from_bytes(data[5:7], "little")
    if data[7] != key[0]:  # Victron's key-check byte
        return None
    return record_type, aes128_ctr(key, iv, data[8:])


def parse_battery_monitor(plain: bytes) -> dict[str, float]:
    r = BitReader(plain)
    out: dict[str, float] = {}
    ttg = r.unsigned(16)
    if ttg != 0xFFFF:
        out["ttg_min"] = float(ttg)
    v = r.unsigned(16)
    if v != 0x7FFF:
        out["voltage"] = round((v - (1 << 16) if v & 0x8000 else v) * 0.01, 2)
    out["alarm"] = float(r.unsigned(16))
    r.unsigned(16)  # aux value (starter/midpoint/temp — by mode; v2)
    r.unsigned(2)  # aux mode
    cur = r.unsigned(22)
    if cur != 0x3FFFFF:
        out["current"] = round((cur - (1 << 22) if cur & (1 << 21) else cur) * 0.001, 3)
    consumed = r.unsigned(20)
    if consumed != 0xFFFFF:
        out["consumed_ah"] = round(consumed * 0.1, 1)
    soc = r.unsigned(10)
    if soc != 0x3FF:
        out["soc"] = round(soc * 0.1, 1)
    return out


def parse_solar(plain: bytes) -> dict[str, float]:
    r = BitReader(plain)
    out: dict[str, float] = {}
    state = r.unsigned(8)
    if state != 0xFF:
        out["charge_state"] = float(state)
    error = r.unsigned(8)
    if error != 0xFF:
        out["error"] = float(error)
    v = r.unsigned(16)
    if v != 0x7FFF:
        out["battery_voltage"] = round((v - (1 << 16) if v & 0x8000 else v) * 0.01, 2)
    i = r.unsigned(16)
    if i != 0x7FFF:
        out["battery_current"] = round((i - (1 << 16) if i & 0x8000 else i) * 0.1, 1)
    y = r.unsigned(16)
    if y != 0xFFFF:
        out["yield_today_wh"] = float(y * 10)
    pv = r.unsigned(16)
    if pv != 0xFFFF:
        out["pv_power"] = float(pv)
    load = r.unsigned(9)
    if load != 0x1FF:
        out["load_current"] = round(load * 0.1, 1)
    return out


def parse_keys(raw: str) -> dict[str, bytes]:
    """'AA:BB:..=32hex, ...' → {mac(lower): key bytes}. Bad entries are skipped."""
    keys: dict[str, bytes] = {}
    for part in (raw or "").split(","):
        if "=" not in part:
            continue
        mac, _, hexkey = part.strip().partition("=")
        try:
            key = bytes.fromhex(hexkey.strip())
        except ValueError:
            continue
        if len(key) == 16:
            keys[mac.strip().lower()] = key
    return keys


class VictronBle(Integration):
    info = IntegrationInfo(
        id="victron_ble",
        name="Victron Instant Readout (BLE)",
        category="energy",
        vendor="Victron Energy",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.OPEN,  # officially documented broadcast format
        priority="P1",
        provides=["victronble.<id>.soc", "victronble.<id>.voltage",
                  "victronble.<id>.pv_power", "house_battery.* (optional mirror)"],
        description=(
            "SmartShunt / SmartSolar broadcasts — full battery and solar telemetry "
            "with no GX device. Paste each device's encryption key from "
            "VictronConnect."
        ),
        config_fields=[
            {"key": "keys", "label": "Device keys (MAC=hex, comma-sep)", "type": "text", "secret": True},
            {"key": "feeds_house_battery", "label": "Shunt feeds house battery", "type": "select",
             "options": ["no", "yes"], "default": "no"},
        ],
        warning="Record layouts per Victron docs + the victron-ble reference — validate on real devices.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsub = None

    async def async_setup(self) -> None:
        await super().async_setup()
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, manufacturer_id=VICTRON_MANUFACTURER_ID)
            self.live = getattr(self.ble, "plan", None) == "bleak"

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_teardown()

    async def _on_adv(self, adv) -> None:
        keys = parse_keys(str(self.config.get("keys") or ""))
        key = keys.get(adv.address.lower())
        if key is None:
            return
        result = decrypt(adv.manufacturer_data.get(VICTRON_MANUFACTURER_ID, b""), key)
        if result is None:
            return
        record_type, plain = result
        if record_type == RECORD_BATTERY_MONITOR:
            data = parse_battery_monitor(plain)
        elif record_type == RECORD_SOLAR:
            data = parse_solar(plain)
        else:
            return
        device = adv.address.replace(":", "").lower()[-4:] or "dev"
        for measure, value in data.items():
            await self.twin.set_signal(f"victronble.{device}.{measure}", value, source=self.info.id)
        if record_type == RECORD_BATTERY_MONITOR and str(self.config.get("feeds_house_battery")) == "yes":
            for src, dst in (("soc", "house_battery.soc"), ("voltage", "house_battery.voltage"),
                             ("current", "house_battery.current")):
                if src in data:
                    await self.twin.set_signal(dst, data[src], source=self.info.id)

    async def simulate(self, dt: float) -> None:
        def _f(key, default):
            try:
                return float(self.twin.get(key))
            except (TypeError, ValueError):
                return default

        await self.twin.set_signal("victronble.demo.soc", _f("house_battery.soc", 82.0), source="victron_ble")
        await self.twin.set_signal("victronble.demo.pv_power", _f("solar.power", 240.0), source="victron_ble")
