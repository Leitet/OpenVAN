"""Chinese diesel heater ("blue wire") — the Vevor/Hcalory/eBay heater family.

The highest-unit-volume heater in the van world speaks a half-duplex single-wire
UART ("blue wire"): the controller sends a 24-byte frame, the heater answers with
its own 24-byte frame. The protocol was reverse-engineered by Ray Jones for the
Afterburner project (gitlab.com/mrjones.id.au/bluetoothheater) — frame layout,
command bytes (0xA0 start / 0x05 stop) and the Modbus CRC-16 stored MSB-first
are taken from his ``Protocol.h``/``Protocol.cpp``, not guessed.

Thanks to the pluggable link layer the wire is reachable several ways:

* ``link: tcp`` — a UART↔WiFi bridge (EW11-style; it must be set to the heater's
  non-standard **25000 baud**). Pure stdlib, works today.
* ``link: serial`` — a USB-UART adapter (optional ``serial`` extra; the adapter
  must support 25000 baud — most CP210x/FTDI do).
* ``mode: sim`` — the catalog demo against the twin (Rule 1).

**Control path (Rule 2).** This driver never accepts commands directly. It
follows the twin's ``diesel_heater.on`` / ``diesel_heater.setpoint`` signals —
which are only ever written by the diesel-heater plugin *after* an intent passed
the safety layer (battery load-shedding, fuel-required). A refused command never
changes those signals, so it never reaches this wire. Heater telemetry flows
back as ``cdh.*`` signals (auto-surfaced as sensor entities).

> Protocol per Afterburner's reverse engineering — **unvalidated on a real
> heater here** (hardware-validation backlog). A heater is a combustion
> appliance: keep the OEM controller until this driver is validated.
"""

from __future__ import annotations

import asyncio

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports.links import create_link
from openvan_core.transports.modbus_rtu import crc16

FRAME_LEN = 24
HEADER = 0x76  # active mode; 0x78 = passive (heater won't persist tuning bytes)
LEN_BYTE = 0x16  # 22 — payload length before the CRC

CMD_NOP = 0x00
CMD_START = 0xA0
CMD_STOP = 0x05

MODE_THERMOSTAT = 0x32
MODE_FIXED_HZ = 0xCD

# The heaters run a fixed, non-standard baud rate.
CDH_BAUD = 25000

RUN_STATES = {
    0: "Off / Standby",
    1: "Start acknowledge",
    2: "Glow plug pre-heat",
    3: "Failed ignition — retrying",
    4: "Ignited — heating up",
    5: "Running",
    6: "Stop acknowledge",
    7: "Stopping — post glow",
    8: "Cooldown",
}

# Raw ErrState byte: 0 = off (no error), 1 = running (no error), 2+ = E-0(n-1).
ERROR_CODES = {
    0: "No error",
    1: "No error (running)",
    2: "Supply voltage too low",
    3: "Supply voltage too high",
    4: "Glow plug failure",
    5: "Fuel pump failure — over current",
    6: "Too hot",
    7: "Fan/motor failure",
    8: "Serial connection lost",
    9: "Flame extinguished",
    10: "Temperature sensor failure",
}

# States a STOP command applies to; 6/7/8 are already shutting down.
ACTIVE_STATES = frozenset({1, 2, 3, 4, 5})


def _crc_ok(frame: bytes) -> bool:
    # Modbus CRC-16 over the first 22 bytes, stored MSB-first (unlike RTU wire order).
    return ((frame[22] << 8) | frame[23]) == crc16(frame[:22])


def build_controller_frame(
    command: int = CMD_NOP,
    actual_temp: float = 18.0,
    desired_temp: float = 20.0,
    *,
    thermostat: bool = True,
    prime: bool = False,
) -> bytes:
    """The 24-byte controller (TX) frame, defaults per Afterburner's ``Init()``."""
    b = bytearray(FRAME_LEN)
    b[0] = HEADER
    b[1] = LEN_BYTE
    b[2] = command & 0xFF  # 0x00 NOP / 0xA0 START / 0x05 STOP
    b[3] = int(round(actual_temp)) & 0xFF  # current cabin temp, 1°C/digit
    b[4] = int(round(desired_temp)) & 0xFF  # demand: °C (thermostat) or Hz (fixed)
    b[5], b[6] = 14, 43  # pump 1.4–4.3 Hz (0.1 Hz/digit)
    b[7:9] = (1450).to_bytes(2, "big")  # min fan RPM
    b[9:11] = (4500).to_bytes(2, "big")  # max fan RPM
    b[11] = 120  # operating voltage: 12 V system (0.1 V/digit)
    b[12] = 1  # fan sensor SN-1
    b[13] = MODE_THERMOSTAT if thermostat else MODE_FIXED_HZ
    b[14], b[15] = 8, 35  # settable temperature range
    b[16] = 5  # glow plug drive
    b[17] = 0x5A if prime else 0x00  # fuel prime
    b[18], b[19] = 0x01, 0x2C  # constant ("300 s max run without burn"?)
    b[20], b[21] = 0x0D, 0xAC  # altitude 3500 — basic-controller constant
    crc = crc16(bytes(b[:22]))
    b[22], b[23] = crc >> 8, crc & 0xFF
    return bytes(b)


def parse_heater_frame(frame: bytes) -> dict | None:
    """The 24-byte heater (RX) frame → measures. ``None`` if malformed."""
    if len(frame) != FRAME_LEN or frame[0] != HEADER or frame[1] != LEN_BYTE:
        return None
    if not _crc_ok(frame):
        return None

    def be(i: int) -> int:
        return (frame[i] << 8) | frame[i + 1]

    run, err = frame[2], frame[3]
    return {
        "run_state": run,
        "state": RUN_STATES.get(run, f"State {run}"),
        "on": run in ACTIVE_STATES,
        "error": err,
        "error_text": ERROR_CODES.get(err, f"E-{max(err - 1, 0):02d}"),
        "supply_voltage": round(be(4) * 0.1, 1),
        "fan_rpm": be(6),
        "fan_voltage": round(be(8) * 0.1, 1),
        "heat_exchanger_temp": be(10),  # 1°C/digit
        "glow_plug_voltage": round(be(12) * 0.1, 1),
        "glow_plug_current": round(be(14) * 0.01, 2),
        "pump_hz": round(frame[16] * 0.1, 1),
        "stored_error": frame[17],
        "fixed_pump_hz": round(frame[19] * 0.1, 1),
    }


def extract_heater_frame(buffer: bytearray, skip: bytes | None = None) -> bytes | None:
    """Pop the first valid frame from ``buffer`` (mutating it), resyncing past
    garbage. ``skip`` drops an echo of our own TX — on the half-duplex single
    wire the controller hears itself before the heater's reply."""
    while True:
        i = 0
        found = None
        while i + FRAME_LEN <= len(buffer):
            if buffer[i] == HEADER and buffer[i + 1] == LEN_BYTE:
                candidate = bytes(buffer[i : i + FRAME_LEN])
                if _crc_ok(candidate):
                    found = candidate
                    del buffer[: i + FRAME_LEN]
                    break
            i += 1
        if found is None:
            if i:
                del buffer[:i]  # scanned and ruled out; keep a possible partial tail
            return None
        if skip is not None and found == skip:
            continue  # our own echo — keep scanning for the heater's reply
        return found


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class ChineseHeater(Integration):
    info = IntegrationInfo(
        id="chinese_heater",
        name="Chinese diesel heater (blue wire)",
        category="climate",
        vendor="Generic (Vevor, Hcalory, …)",
        transports=[Transport.SERIAL],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control="limited", configure=True),
        safety_class=3,
        status=Status.REVERSE_ENGINEERED,
        priority="P0",
        provides=[
            "cdh.run_state", "cdh.supply_voltage", "cdh.heat_exchanger_temp",
            "cdh.fan_rpm", "cdh.pump_hz", "cdh.error",
        ],
        description=(
            "The generic 'blue wire' diesel heaters (Vevor, Hcalory, …) over their "
            "single-wire UART, per the Afterburner project's reverse engineering. "
            "Follows the diesel-heater plugin's safety-approved state — start/stop "
            "and setpoint go through OpenVan's safety rules, never directly."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "link"], "default": "sim"},
            {"key": "link", "label": "Link", "type": "select",
             "options": ["tcp", "serial"], "default": "tcp"},
            {"key": "host", "label": "Bridge host (tcp link)", "type": "text"},
            {"key": "port", "label": "Bridge port", "type": "text", "default": "8899"},
            {"key": "device", "label": "Serial device (serial link)", "type": "text"},
            {"key": "baud", "label": "Baud", "type": "text", "default": "25000"},
            {"key": "poll_s", "label": "Poll interval (s)", "type": "text", "default": "1"},
        ],
        warning=(
            "Reverse-engineered protocol on a combustion appliance — control always "
            "passes OpenVan's safety rules, and the driver is unvalidated on real "
            "hardware. Keep the OEM controller available."
        ),
    )

    def transport_mode(self) -> str:
        return str(self.config.get("mode", "sim") or "sim")

    def _make_link(self):
        cfg = dict(self.config)
        cfg.setdefault("baud", CDH_BAUD)  # the heaters' fixed non-standard rate
        return create_link(cfg)

    def _desired(self) -> tuple[bool, float, float]:
        """The safety-approved desired state: only the diesel-heater plugin writes
        these signals, and only after ``Hub.execute_intent`` passed safety (Rule 2)."""
        want_on = bool(self.twin.get("diesel_heater.on"))
        setpoint = _f(self.twin, "diesel_heater.setpoint", 20.0)
        cabin = _f(self.twin, "cabin.temperature", 18.0)
        return want_on, setpoint, cabin

    async def run_transport(self) -> None:
        if self.transport_mode() != "link":
            raise NotImplementedError
        if not (self.config.get("host") or self.config.get("device")):
            raise NotImplementedError  # nowhere to connect → stay simulated
        try:
            poll_s = float(self.config.get("poll_s") or 1.0)
        except (TypeError, ValueError):
            poll_s = 1.0
        link = self._make_link()
        await link.open()
        rx = bytearray()
        run_state = 0
        loop = asyncio.get_event_loop()
        try:
            self.live = True
            await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
            while True:
                want_on, setpoint, cabin = self._desired()
                if want_on and run_state == 0:
                    command = CMD_START
                elif not want_on and run_state in ACTIVE_STATES:
                    command = CMD_STOP
                else:
                    command = CMD_NOP
                tx = build_controller_frame(command, cabin, setpoint)
                await link.write(tx)
                # Collect the heater's reply (skipping our own half-duplex echo).
                frame = None
                deadline = loop.time() + min(1.0, poll_s)
                while frame is None:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    chunk = await link.read(64, timeout=remaining)
                    if not chunk:
                        break
                    rx += chunk
                    frame = extract_heater_frame(rx, skip=tx)
                if frame is not None:
                    data = parse_heater_frame(frame)
                    if data is not None:
                        run_state = int(data["run_state"])
                        for measure, value in data.items():
                            await self.twin.set_signal(
                                f"cdh.{measure}", value, source=self.info.id
                            )
                await asyncio.sleep(poll_s)
        finally:
            await link.close()

    async def simulate(self, dt: float) -> None:
        """Reflect the twin's heater state as the readings a real unit would report."""
        twin = self.twin
        on = bool(twin.get("diesel_heater.on"))
        cabin = _f(twin, "cabin.temperature", 18.0)
        await twin.set_signal("cdh.run_state", 5 if on else 0, source=self.info.id)
        await twin.set_signal(
            "cdh.state", RUN_STATES[5 if on else 0], source=self.info.id
        )
        await twin.set_signal(
            "cdh.supply_voltage", round(_f(twin, "house_battery.voltage", 12.8), 1),
            source=self.info.id,
        )
        await twin.set_signal(
            "cdh.heat_exchanger_temp", round(150.0 if on else cabin, 1),
            source=self.info.id,
        )
        await twin.set_signal("cdh.pump_hz", 2.8 if on else 0.0, source=self.info.id)
        await twin.set_signal("cdh.fan_rpm", 3200 if on else 0, source=self.info.id)
