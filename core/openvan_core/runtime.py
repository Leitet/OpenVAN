"""Assembly of a running OpenVan Core.

Wires the event bus, digital twin, simulation backend, safety validator, hub and
plugin manager together. Kept separate from the API so tests (and, later,
non-HTTP front-ends like a voice loop) can drive a fully-formed Core directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .backends import Backend, SimBackend
from .config import Config
from .events import EventBus
from .hub import Hub
from .intents import IntentResolver
from .plugins import PluginManager
from .safety import (
    CriticalBatteryLoadShedding,
    FuelRequiredToStart,
    PumpDryRunProtection,
    SafetyValidator,
)
from .simulation import VanSimulation
from .twin import VanTwin


@dataclass
class Core:
    config: Config
    bus: EventBus
    twin: VanTwin
    backend: Backend
    hub: Hub
    plugins: PluginManager
    simulation: VanSimulation

    async def start(self) -> None:
        # Seed the twin first so plugins read sensible values on setup.
        for key, value in self.config.seed_twin.items():
            await self.twin.set_signal(key, value, source="seed")
        self.plugins.discover(self.config.plugins_dir)
        await self.plugins.setup_all()
        if self.config.simulate:
            self.simulation.start()

    async def stop(self) -> None:
        await self.simulation.stop()
        await self.plugins.teardown_all()


def build_core(config: Config | None = None) -> Core:
    config = config or Config()
    bus = EventBus()
    twin = VanTwin(bus)
    backend = SimBackend(bus, twin)
    safety = SafetyValidator(
        rules=[
            CriticalBatteryLoadShedding(),
            FuelRequiredToStart(),
            PumpDryRunProtection(),
        ]
    )
    hub = Hub(bus, twin, safety, IntentResolver())
    plugins = PluginManager(hub, backend)
    simulation = VanSimulation(bus, twin)
    return Core(
        config=config,
        bus=bus,
        twin=twin,
        backend=backend,
        hub=hub,
        plugins=plugins,
        simulation=simulation,
    )
