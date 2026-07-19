"""Integration framework — the driver + descriptor layer.

An **integration** connects OpenVan to a hardware *ecosystem* (Victron, ESPHome,
Home Assistant/MQTT, Modbus, …) over one or more *transports*, and **normalises**
what the devices report into the twin's raw-signal schema. Plugins
(:mod:`~openvan_core.plugins`) then turn those signals into semantic entities.

Two things travel together in every integration:

* a machine-readable **descriptor** (:class:`IntegrationInfo`) — transport list,
  local/offline flags, permissions, safety class, confidence/status, an optional
  warning — so the UI can honestly show *how robust* the support is, and
* a **driver** — on real hardware it talks the protocol; in simulation it
  injects the characteristic raw signals a device of that type would emit, so the
  integration is exercisable against the twin with no hardware (Rule 1).

The full strategy (protocols, priorities, phases, top-10) lives in
``docs/OPENVAN-INTEGRATION-LANDSCAPE.md``.

Discovery mirrors :mod:`~openvan_core.plugins`: each folder under
``integrations/`` that defines an :class:`Integration` subclass is imported, and
subclasses self-register via ``__init_subclass__``.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from abc import ABC
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .events import EventBus
    from .twin import VanTwin

logger = logging.getLogger(__name__)

# Reconnect backoff for a real transport that drops or can't be reached (seconds).
_RECONNECT_MIN = 3.0
_RECONNECT_MAX = 60.0


# --- taxonomy (kept as plain strings so descriptors stay JSON-friendly) -------

class Transport:
    MQTT = "mqtt"
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    VE_DIRECT = "ve_direct"
    BLE = "ble"
    SERIAL = "serial"
    HTTP = "http"
    WEBSOCKET = "websocket"
    CANBUS = "canbus"
    RV_C = "rv_c"
    NMEA2000 = "nmea2000"
    SIGNALK = "signalk"
    CLOUD_REST = "cloud_rest"
    NATIVE_API = "native_api"
    ZIGBEE = "zigbee"


class Status:
    """Confidence taxonomy, most robust → most fragile (what the user sees)."""

    NATIVE = "native"
    CERTIFIED = "certified"
    OPEN = "open"
    COMMUNITY = "community"
    EXPERIMENTAL = "experimental"
    REVERSE_ENGINEERED = "reverse_engineered"
    CLOUD_DEPENDENT = "cloud_dependent"
    READ_ONLY = "read_only"
    UNSUPPORTED = "unsupported"


@dataclass
class Permissions:
    """Each is ``True`` / ``False`` / the string ``"limited"``."""

    read: Any = True
    control: Any = False
    configure: Any = False


@dataclass
class IntegrationInfo:
    """The machine-readable descriptor an integration exposes."""

    id: str
    name: str
    category: str  # matches the plugin categories: energy, climate, water, …
    vendor: str = ""
    transports: list[str] = field(default_factory=list)
    local: bool = True
    offline_capable: bool = True
    discovery: str = ""  # mdns / dhcp / ble_scan / manual / ""
    permissions: Permissions = field(default_factory=Permissions)
    safety_class: int = 0  # 0 safest read-only … 4 critical / cloud / reverse-eng
    status: str = Status.EXPERIMENTAL
    priority: str = "P2"  # P0 launch … P3 niche
    provides: list[str] = field(default_factory=list)  # normalised signal keys it feeds
    description: str = ""
    warning: str = ""  # honest caveat (fragile driver, cloud, reverse-engineered)
    # Connection settings the user fills in to point the driver at real hardware
    # (host, port, mode, credentials). Each: {key, label, type, options?, secret?}.
    # Empty → the integration is sim-only for now.
    config_fields: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# Built-in integrations are installed out of the box and can't be removed — they're
# part of the platform, not optional add-ons. The simulator (the twin itself) is the
# one standard integration every install needs. Everything else is opt-in from the
# library. Keep this set tiny: only what is genuinely universal and always-present.
BUILTIN: frozenset[str] = frozenset({"simulated_van"})


_REGISTRY: list[type["Integration"]] = []


def registered_integrations() -> list[type["Integration"]]:
    return list(_REGISTRY)


def clear_registry() -> None:
    """Test helper — the registry is process-global."""
    _REGISTRY.clear()


class Integration(ABC):
    """Base class for an ecosystem driver.

    Subclasses set the :attr:`info` descriptor and, for Rule 1, implement
    :meth:`simulate` to inject the raw signals a real device would emit. On real
    hardware they'd instead open the transport in :meth:`async_setup` and stream
    device data into the twin — the same normalised signal keys either way.
    """

    info: IntegrationInfo

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "info", None) is not None:
            _REGISTRY.append(cls)

    def __init__(self, twin: "VanTwin", bus: "EventBus", config: dict[str, Any] | None = None):
        self.twin = twin
        self.bus = bus
        self.config = config or {}
        self.enabled = False
        # True while a real transport is connected and owns the signals; the sim
        # driver stands down (offline-first: sim only fills in when no hardware).
        self.live = False
        self._transport_task: asyncio.Task | None = None

    def transport_mode(self) -> str:
        """The configured connection mode. ``"sim"`` (the default) means no real
        transport — the driver's :meth:`simulate` provides the signals."""
        return str(self.config.get("mode", "sim") or "sim")

    async def async_setup(self) -> None:
        """Start the real transport if one is configured; otherwise stay in sim."""
        await self.start_transport()

    async def async_teardown(self) -> None:
        """Release resources (close sockets, unsubscribe)."""
        await self.stop_transport()

    async def start_transport(self) -> None:
        if self.transport_mode() == "sim" or self._transport_task is not None:
            return
        self._transport_task = asyncio.create_task(self._transport_supervisor())

    async def stop_transport(self) -> None:
        self.live = False
        task, self._transport_task = self._transport_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _transport_supervisor(self) -> None:
        """Keep the real transport connected, reconnecting with backoff. On a clean
        offline fallback (driver has no real path) it steps aside for the sim."""
        backoff = _RECONNECT_MIN
        while True:
            try:
                await self.run_transport()
            except asyncio.CancelledError:
                raise
            except NotImplementedError:
                logger.info("integration %s has no real transport yet — staying simulated", self.info.id)
                self.live = False
                return
            except Exception as exc:  # pragma: no cover - network/hardware paths
                logger.warning("integration %s transport error: %s", self.info.id, exc)
            self.live = False
            await self.bus.publish("integration.changed", {"id": self.info.id, "live": False})
            await asyncio.sleep(backoff)
            backoff = min(_RECONNECT_MAX, backoff * 2)

    async def run_transport(self) -> None:
        """Override to connect the real device: set ``self.live = True`` once
        connected and stream normalised signals into the twin until it drops.
        The default raises so sim-only integrations fall back cleanly."""
        raise NotImplementedError

    async def simulate(self, dt: float) -> None:
        """Inject the characteristic raw signals this ecosystem would produce.

        Only called while enabled *and not live* — real hardware, when connected,
        owns the signals. Keep it offline and deterministic (no wall-clock / RNG)
        so tests stay stable.
        """


class IntegrationManager:
    """Discovers, enables/disables and ticks integrations.

    Enabled state is persisted in the config store under the ``integrations``
    namespace, so a user's choices survive restarts.
    """

    NS = "integrations"

    def __init__(self, twin: "VanTwin", bus: "EventBus", store: Any = None) -> None:
        self.twin = twin
        self.bus = bus
        self.store = store
        self.integrations: dict[str, Integration] = {}

    def get(self, integration_id: str) -> Integration | None:
        return self.integrations.get(integration_id)

    def discover(self, integrations_dir: Path | str) -> None:
        integrations_dir = Path(integrations_dir)
        if not integrations_dir.is_dir():
            logger.warning("integrations directory %s does not exist", integrations_dir)
            return
        if str(integrations_dir) not in sys.path:
            sys.path.insert(0, str(integrations_dir))
        for child in sorted(integrations_dir.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                logger.info("loading integration package: %s", child.name)
                importlib.import_module(child.name)

    def _persisted_enabled(self) -> dict[str, bool]:
        if self.store is None:
            return {}
        return {k: bool(v) for k, v in self.store.get_all(self.NS).items()}

    async def setup_all(self) -> None:
        """Instantiate every registered integration; enable those the user has
        turned on (defaulting to the descriptor-implied default for un-set ones)."""
        persisted = self._persisted_enabled()
        for cls in registered_integrations():
            info = cls.info
            instance = cls(self.twin, self.bus, self._config_for(info.id))
            self.integrations[info.id] = instance
            want = persisted.get(info.id, _default_enabled(info))
            if want:
                await self._enable(instance)

    def _config_for(self, integration_id: str) -> dict[str, Any]:
        if self.store is None:
            return {}
        return self.store.get_all(f"{self.NS}:{integration_id}")

    async def _enable(self, instance: Integration) -> None:
        if instance.enabled:
            return
        instance.enabled = True
        await instance.async_setup()
        await self.bus.publish("integration.changed", self.describe(instance.info.id))

    async def _disable(self, instance: Integration) -> None:
        if not instance.enabled:
            return
        instance.enabled = False
        await instance.async_teardown()
        await self.bus.publish("integration.changed", self.describe(instance.info.id))

    async def set_enabled(self, integration_id: str, enabled: bool) -> bool:
        instance = self.integrations.get(integration_id)
        if instance is None:
            return False
        # Built-ins are always installed — a request to remove one is a no-op, not
        # an error (the UI hides its remove control, but guard the API too).
        if not enabled and integration_id in BUILTIN:
            return True
        if enabled:
            await self._enable(instance)
        else:
            await self._disable(instance)
        if self.store is not None:
            self.store.set_many(self.NS, {integration_id: enabled})
        return True

    async def teardown_all(self) -> None:
        for instance in self.integrations.values():
            await instance.async_teardown()
        self.integrations.clear()

    async def set_config(self, integration_id: str, values: dict[str, Any]) -> bool:
        """Persist a driver's connection settings (host, port, mode, credentials)
        and reconnect its transport so a change takes effect live."""
        instance = self.integrations.get(integration_id)
        if instance is None:
            return False
        # Drop blank values so clearing a field falls back to the default.
        clean = {k: v for k, v in values.items() if v not in (None, "")}
        instance.config.update(clean)
        if self.store is not None:
            self.store.set_many(f"{self.NS}:{integration_id}", clean)
        if instance.enabled:
            await instance.stop_transport()
            await instance.start_transport()
        await self.bus.publish("integration.changed", self.describe(integration_id))
        return True

    async def simulate_all(self, dt: float) -> None:
        """Tick each enabled *simulated* driver (called from the sim loop). A driver
        connected to real hardware (``live``) owns its signals, so it's skipped."""
        for instance in self.integrations.values():
            if instance.enabled and not instance.live:
                try:
                    await instance.simulate(dt)
                except Exception:  # pragma: no cover - a bad driver must not stall the loop
                    logger.exception("integration %s simulate failed", instance.info.id)

    def describe(self, integration_id: str) -> dict[str, Any] | None:
        instance = self.integrations.get(integration_id)
        if instance is None:
            return None
        d = instance.info.to_dict()
        # "installed" == added by the user (or built-in); "enabled" kept as an alias
        # so existing consumers don't break. "builtin" ones can't be removed.
        d["enabled"] = instance.enabled
        d["installed"] = instance.enabled
        d["builtin"] = instance.info.id in BUILTIN
        # Live transport state: "sim" (driver-simulated), or connected to hardware.
        d["mode"] = instance.transport_mode()
        d["live"] = instance.live
        d["config"] = _config_view(instance.info.config_fields, instance.config)
        return d

    def list(self) -> list[dict[str, Any]]:
        """All integrations with descriptor + live enabled state, sorted by
        priority then name so P0 launch integrations lead the catalog."""
        rows = [self.describe(i) for i in self.integrations]
        rows = [r for r in rows if r is not None]
        rows.sort(key=lambda r: (r.get("priority", "P9"), r.get("name", "")))
        return rows


def _config_view(fields: list[dict[str, Any]], values: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge a driver's declared config fields with the stored values for the UI.
    Secrets are write-only — never echoed; we only report whether one is set."""
    view: list[dict[str, Any]] = []
    for f in fields:
        key = f["key"]
        secret = bool(f.get("secret"))
        entry = {
            "key": key,
            "label": f.get("label", key),
            "type": f.get("type", "text"),
            "options": f.get("options", []),
            "secret": secret,
            "set": key in values and values[key] not in (None, ""),
        }
        if not secret:
            entry["value"] = values.get(key, f.get("default", ""))
        view.append(entry)
    return view


def _default_enabled(info: IntegrationInfo) -> bool:
    """A never-configured integration is not installed by default — the user adds it
    from the library. Only the built-in standard set (the simulator) ships installed."""
    return info.id in BUILTIN
