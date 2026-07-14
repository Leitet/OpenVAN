"""Assembly of a running OpenVan Core.

Wires the event bus, digital twin, simulation backend, safety validator, hub and
plugin manager together. Kept separate from the API so tests (and, later,
non-HTTP front-ends like a voice loop) can drive a fully-formed Core directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from .backends import Backend, SimBackend
from .companion import Companion
from .config import Config
from .events import EventBus
from .hub import Hub
from .intents import IntentResolver
from .llm import LLMIntentResolver, OllamaClient
from .notices import AdvisorEngine
from .personalities import PersonalityStore
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
    advisors: AdvisorEngine
    companion: Companion
    personalities: PersonalityStore

    async def start(self) -> None:
        # Seed the twin first so plugins read sensible values on setup.
        for key, value in self.config.seed_twin.items():
            await self.twin.set_signal(key, value, source="seed")
        self.plugins.discover(self.config.plugins_dir)
        await self.plugins.setup_all()
        if self.config.ai_enabled:
            await self.hub.resolver.startup()
        if self.config.simulate:
            self.simulation.start()
        # Subscribe advisors, then evaluate once against the seeded state.
        self.advisors.start()
        await self.advisors.evaluate()

    async def stop(self) -> None:
        await self.advisors.stop()
        await self.simulation.stop()
        await self.plugins.teardown_all()

    def assistant_state(self) -> dict[str, Any]:
        resolver = self.hub.resolver
        return {
            "llm": getattr(resolver, "active", False),
            "model": self.config.llm_model,
            "personality": self.personalities.get_active().name,
            "personality_id": self.personalities.active_id(),
        }

    # --- runtime settings (Admin UI / API / MCP) -------------------------
    def settings(self) -> dict[str, Any]:
        from . import __version__

        resolver = self.hub.resolver
        return {
            "version": __version__,
            "host": self.config.host,
            "port": self.config.port,
            "ai_enabled": self.config.ai_enabled,
            "llm_model": self.config.llm_model,
            "llm_base_url": self.config.llm_base_url,
            "llm_active": getattr(resolver, "active", False),
            "simulate": self.config.simulate,
            "personality": self.personalities.active_id(),
            "plugins": [
                {
                    "domain": p.domain,
                    "name": p.name,
                    "version": p.version,
                    "categories": list(p.categories),
                }
                for p in self.plugins.plugins
            ],
        }

    async def apply_settings(
        self,
        *,
        ai_enabled: bool | None = None,
        llm_model: str | None = None,
        llm_base_url: str | None = None,
        simulate: bool | None = None,
    ) -> dict[str, Any]:
        client = getattr(self.hub.resolver, "client", None)
        if llm_model is not None:
            self.config.llm_model = llm_model
            if client is not None:
                client.model = llm_model
        if llm_base_url is not None:
            self.config.llm_base_url = llm_base_url
            if client is not None:
                client.base_url = llm_base_url.rstrip("/")
        if ai_enabled is not None:
            self.config.ai_enabled = ai_enabled

        # Re-probe (or deactivate) the assistant so model/url/enable take effect.
        if self.config.ai_enabled:
            await self.hub.resolver.startup()
        else:
            self.hub.resolver.deactivate()

        if simulate is not None and simulate != self.config.simulate:
            self.config.simulate = simulate
            if simulate:
                self.simulation.start()
            else:
                await self.simulation.stop()

        result = self.settings()
        await self.bus.publish("settings.changed", {"settings": result})
        await self.bus.publish("assistant.changed", self.assistant_state())
        return result

    async def available_models(self) -> list[str]:
        client = getattr(self.hub.resolver, "client", None)
        if client is None or not hasattr(client, "list_models"):
            return []
        return await client.list_models()


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
    client = OllamaClient(config.llm_base_url, config.llm_model)
    resolver = LLMIntentResolver(client, fallback=IntentResolver())
    hub = Hub(bus, twin, safety, resolver)
    plugins = PluginManager(hub, backend)
    simulation = VanSimulation(bus, twin)
    advisors = AdvisorEngine(bus, hub)
    companion = Companion(client)
    personalities = PersonalityStore(config.data_dir / "personalities.json")
    return Core(
        config=config,
        bus=bus,
        twin=twin,
        backend=backend,
        hub=hub,
        plugins=plugins,
        simulation=simulation,
        advisors=advisors,
        companion=companion,
        personalities=personalities,
    )
