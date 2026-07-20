"""BLE substrate — one radio, shared by every BLE driver.

The 2026-07 market research was unambiguous: almost everything van owners want to
integrate speaks BLE (BMS, tank sensors, TPMS, thermometers, fridges, shunts).
This substrate makes those drivers cheap: Core owns **one scanner** on **one
radio**, and drivers subscribe to the advertisement stream with a filter — they
never touch the radio, never fight over it, and are fully exercisable against the
sim (Rule 1).

* :class:`Advertisement` — the normalised frame every driver consumes.
* :class:`BleRadio` — the hardware seam. :class:`SimBleRadio` is the dev
  stand-in (the bench injects canned advertisements exactly like SignalSliders
  inject sensor values); :class:`BleakRadio` drives a real adapter via **bleak**,
  an *optional extra* (``pip install -e ".[ble]"``) so the core stays light.
* :class:`BleScanner` — the shared service: resolves the radio from config
  (``ble_radio``: auto | off | sim | bleak — ``auto`` prefers a real adapter,
  falls back to sim in simulate mode), fans frames out to subscribers, and
  contains subscriber failures (one bad parser never stalls the stream).

> The bleak path is written to bleak's documented API but is **unvalidated on
> real adapters here** (no BLE hardware in the dev env) — flagged in the
> hardware-validation backlog, like the Victron register map.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

AdvHandler = Callable[["Advertisement"], Awaitable[None] | None]


def short_uuid(uuid: str) -> str:
    """Normalise a service UUID: full 128-bit Bluetooth-base UUIDs collapse to
    their 16-bit short form ('0000fcd2-0000-1000-8000-00805f9b34fb' → 'fcd2')."""
    u = uuid.lower()
    if len(u) == 36 and u.startswith("0000") and u.endswith("-0000-1000-8000-00805f9b34fb"):
        return u[4:8]
    return u


@dataclass(frozen=True)
class Advertisement:
    address: str
    rssi: int = 0
    name: str = ""
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)  # company id → payload
    service_data: dict[str, bytes] = field(default_factory=dict)  # short uuid → payload


class BleDevice(ABC):
    """A GATT session with one device (connect via :meth:`BleScanner.connect`)."""

    address: str = ""

    @abstractmethod
    async def read(self, char_uuid: str) -> bytes:
        ...

    @abstractmethod
    async def write(self, char_uuid: str, data: bytes, response: bool = True) -> None:
        ...

    @abstractmethod
    async def start_notify(self, char_uuid: str, handler: Callable[[bytes], Awaitable[None] | None]) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...


class BleRadio(ABC):
    kind: str = "radio"

    @abstractmethod
    async def start(self, on_advertisement: AdvHandler) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    async def connect(self, address: str, timeout: float = 10.0) -> BleDevice:
        raise NotImplementedError("this radio has no GATT support")


class SimBleDevice(BleDevice):
    """A programmable fake GATT device for the sim radio / tests.

    ``characteristics`` seeds read values; ``on_write(char, data)`` lets a test
    script a device's behaviour (e.g. a fake BMS answering a request by calling
    :meth:`notify`)."""

    def __init__(self, address: str, characteristics: dict[str, bytes] | None = None,
                 on_write: Callable[["SimBleDevice", str, bytes], Awaitable[None] | None] | None = None) -> None:
        self.address = address
        self.characteristics = dict(characteristics or {})
        self._on_write = on_write
        self._notify: dict[str, Callable[[bytes], Awaitable[None] | None]] = {}
        self.connected = False
        self.writes: list[tuple[str, bytes]] = []

    async def read(self, char_uuid: str) -> bytes:
        return self.characteristics.get(short_uuid(char_uuid), b"")

    async def write(self, char_uuid: str, data: bytes, response: bool = True) -> None:
        char = short_uuid(char_uuid)
        self.writes.append((char, data))
        if self._on_write is not None:
            result = self._on_write(self, char, data)
            if asyncio.iscoroutine(result):
                await result

    async def start_notify(self, char_uuid: str, handler: Callable[[bytes], Awaitable[None] | None]) -> None:
        self._notify[short_uuid(char_uuid)] = handler

    async def notify(self, char_uuid: str, data: bytes) -> None:
        handler = self._notify.get(short_uuid(char_uuid))
        if handler is not None:
            result = handler(data)
            if asyncio.iscoroutine(result):
                await result

    async def disconnect(self) -> None:
        self.connected = False


class SimBleRadio(BleRadio):
    """The dev stand-in: advertisements are *injected* (bench / tests), not
    received over the air — the BLE analogue of SimBackend. GATT devices are
    registered with :meth:`add_device`."""

    kind = "sim"

    def __init__(self) -> None:
        self._handler: AdvHandler | None = None
        self.devices: dict[str, SimBleDevice] = {}

    async def start(self, on_advertisement: AdvHandler) -> None:
        self._handler = on_advertisement

    async def stop(self) -> None:
        self._handler = None

    async def inject(self, adv: Advertisement) -> None:
        if self._handler is not None:
            result = self._handler(adv)
            if asyncio.iscoroutine(result):
                await result

    def add_device(self, device: SimBleDevice) -> None:
        self.devices[device.address.lower()] = device

    async def connect(self, address: str, timeout: float = 10.0) -> BleDevice:
        device = self.devices.get(address.lower())
        if device is None:
            raise ConnectionError(f"no sim BLE device at {address}")
        device.connected = True
        return device


class BleakRadio(BleRadio):
    """A real adapter via bleak (optional extra). Adapter-isolated so the
    substrate (and its tests) never depend on the library's exact shape."""

    kind = "bleak"

    def __init__(self) -> None:
        from bleak import BleakScanner  # optional extra

        self._scanner_cls = BleakScanner
        self._scanner: Any = None
        self._handler: AdvHandler | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, on_advertisement: AdvHandler) -> None:
        self._handler = on_advertisement
        self._loop = asyncio.get_running_loop()

        def _detected(device: Any, data: Any) -> None:  # pragma: no cover - hw path
            adv = Advertisement(
                address=str(getattr(device, "address", "")),
                rssi=int(getattr(data, "rssi", 0) or 0),
                name=str(getattr(data, "local_name", "") or ""),
                manufacturer_data={int(k): bytes(v) for k, v in (getattr(data, "manufacturer_data", {}) or {}).items()},
                service_data={short_uuid(str(k)): bytes(v) for k, v in (getattr(data, "service_data", {}) or {}).items()},
            )
            handler = self._handler
            if handler is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_maybe_await(handler, adv)))

        self._scanner = self._scanner_cls(detection_callback=_detected)
        await self._scanner.start()

    async def stop(self) -> None:  # pragma: no cover - hw path
        if self._scanner is not None:
            await self._scanner.stop()
            self._scanner = None
        self._handler = None

    async def connect(self, address: str, timeout: float = 10.0) -> BleDevice:  # pragma: no cover - hw path
        from bleak import BleakClient

        client = BleakClient(address, timeout=timeout)
        await client.connect()
        return _BleakDevice(address, client)


class _BleakDevice(BleDevice):  # pragma: no cover - hw path
    def __init__(self, address: str, client: Any) -> None:
        self.address = address
        self._client = client

    async def read(self, char_uuid: str) -> bytes:
        return bytes(await self._client.read_gatt_char(char_uuid))

    async def write(self, char_uuid: str, data: bytes, response: bool = True) -> None:
        await self._client.write_gatt_char(char_uuid, data, response=response)

    async def start_notify(self, char_uuid: str, handler: Callable[[bytes], Awaitable[None] | None]) -> None:
        def _cb(_char: Any, data: bytearray) -> None:
            result = handler(bytes(data))
            if asyncio.iscoroutine(result):
                asyncio.ensure_future(result)

        await self._client.start_notify(char_uuid, _cb)

    async def disconnect(self) -> None:
        await self._client.disconnect()


async def _maybe_await(handler: AdvHandler, adv: Advertisement) -> None:
    result = handler(adv)
    if asyncio.iscoroutine(result):
        await result


def _bleak_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("bleak") is not None


@dataclass
class _Subscription:
    handler: AdvHandler
    manufacturer_id: int | None = None
    service_uuid: str | None = None
    address_prefix: str | None = None

    def matches(self, adv: Advertisement) -> bool:
        if self.manufacturer_id is not None and self.manufacturer_id not in adv.manufacturer_data:
            return False
        if self.service_uuid is not None and self.service_uuid not in adv.service_data:
            return False
        if self.address_prefix is not None and not adv.address.lower().startswith(self.address_prefix.lower()):
            return False
        return True


class BleScanner:
    """The shared scanner service Core owns; drivers subscribe with a filter."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.radio: BleRadio | None = None
        self.plan: str | None = self._plan(str(getattr(config, "ble_radio", "auto")))
        self._subs: list[_Subscription] = []
        self._running = False

    def _plan(self, mode: str) -> str | None:
        if mode == "off":
            return None
        if mode in ("sim", "bleak"):
            return mode
        # auto — a real adapter when the extra is installed, else sim in sim mode.
        if _bleak_available():
            return "bleak"
        return "sim" if getattr(self.config, "simulate", False) else None

    def status(self) -> dict[str, Any]:
        return {"available": self.plan is not None, "radio": self.plan, "running": self._running,
                "subscribers": len(self._subs)}

    async def start(self) -> None:
        if self.plan is None or self._running:
            return
        try:
            self.radio = BleakRadio() if self.plan == "bleak" else SimBleRadio()
            await self.radio.start(self._dispatch)
            self._running = True
        except Exception as exc:
            logger.warning("BLE radio %s failed to start (%s) — BLE drivers stay in sim", self.plan, exc)
            self.radio = None

    async def stop(self) -> None:
        if self.radio is not None:
            await self.radio.stop()
            self.radio = None
        self._running = False

    def subscribe(
        self,
        handler: AdvHandler,
        *,
        manufacturer_id: int | None = None,
        service_uuid: str | None = None,
        address_prefix: str | None = None,
    ) -> Callable[[], None]:
        sub = _Subscription(handler, manufacturer_id,
                            short_uuid(service_uuid) if service_uuid else None, address_prefix)
        self._subs.append(sub)

        def unsubscribe() -> None:
            if sub in self._subs:
                self._subs.remove(sub)

        return unsubscribe

    async def inject(self, adv: Advertisement) -> None:
        """Feed a canned advertisement through the pipeline (bench / tests). Works
        with any radio — it enters at the dispatch stage, like sim signal injection."""
        await self._dispatch(adv)

    async def connect(self, address: str, timeout: float = 10.0) -> BleDevice:
        """Open a GATT session on the shared radio (sim: a registered SimBleDevice)."""
        if self.radio is None:
            raise ConnectionError("BLE radio not running")
        return await self.radio.connect(address, timeout)

    def sim_device(self, device: "SimBleDevice") -> None:
        """Register a programmable GATT device on the sim radio (bench / tests)."""
        if isinstance(self.radio, SimBleRadio):
            self.radio.add_device(device)

    async def _dispatch(self, adv: Advertisement) -> None:
        for sub in list(self._subs):
            if not sub.matches(adv):
                continue
            try:
                result = sub.handler(adv)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - defensive
                logger.exception("BLE subscriber failed for %s", adv.address)
