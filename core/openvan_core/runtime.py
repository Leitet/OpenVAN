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
from .llm import (
    AnthropicClient,
    LLMIntentResolver,
    ModelRouter,
    OllamaClient,
    OpenAICompatibleClient,
)
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
    router: ModelRouter

    async def start(self) -> None:
        # Seed the twin first so plugins read sensible values on setup.
        for key, value in self.config.seed_twin.items():
            await self.twin.set_signal(key, value, source="seed")
        self.plugins.discover(self.config.plugins_dir)
        await self.plugins.setup_all()
        await self.router.refresh()  # probe the effective model for the active profile
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
        binding = self.router.binding()
        return {
            "llm": self.router.active,
            "connectivity": binding.connectivity,
            "model": binding.model,
            "personality": self.personalities.get_active().name,
            "personality_id": self.personalities.active_id(),
        }

    # --- runtime settings (Admin UI / API / MCP) -------------------------
    def settings(self) -> dict[str, Any]:
        from . import __version__

        return {
            "version": __version__,
            "host": self.config.host,
            "port": self.config.port,
            "ai_enabled": self.config.ai_enabled,
            "default_connectivity": self.config.default_connectivity,
            "offline": {
                "base_url": self.config.llm_base_url,
                "model": self.config.llm_model,
            },
            "online": {
                "provider": self.config.online_provider,
                "base_url": self.config.online_base_url,
                "model": self.config.online_model,
                "has_key": bool(self.config.online_api_key),
            },
            "assistant": self.assistant_state(),
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
        default_connectivity: str | None = None,
        offline_model: str | None = None,
        offline_base_url: str | None = None,
        online_provider: str | None = None,
        online_model: str | None = None,
        online_base_url: str | None = None,
        online_api_key: str | None = None,
        simulate: bool | None = None,
    ) -> dict[str, Any]:
        if ai_enabled is not None:
            self.config.ai_enabled = ai_enabled
        if default_connectivity is not None:
            self.config.default_connectivity = default_connectivity
        if offline_model is not None:
            self.config.llm_model = offline_model
        if offline_base_url is not None:
            self.config.llm_base_url = offline_base_url.rstrip("/")
        if online_provider is not None:
            self.config.online_provider = online_provider
        if online_model is not None:
            self.config.online_model = online_model
        if online_base_url is not None:
            self.config.online_base_url = online_base_url.rstrip("/")
        if online_api_key is not None:
            self.config.online_api_key = online_api_key or None

        # Re-resolve the effective model for the active profile + new config.
        await self.router.refresh()

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

    async def available_models(self, connectivity: str = "offline") -> list[str]:
        if connectivity == "online":
            if self.config.online_provider == "anthropic":
                client = AnthropicClient(
                    self.config.online_api_key,
                    self.config.online_model,
                )
            elif self.config.online_base_url:
                client = OpenAICompatibleClient(
                    self.config.online_base_url,
                    self.config.online_model,
                    self.config.online_api_key,
                )
            else:
                return []
        else:
            client = OllamaClient(self.config.llm_base_url, self.config.llm_model)
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
    personalities = PersonalityStore(config.data_dir / "personalities.json")
    router = ModelRouter(config, personalities)
    resolver = LLMIntentResolver(router, fallback=IntentResolver())
    hub = Hub(bus, twin, safety, resolver)
    plugins = PluginManager(hub, backend)
    simulation = VanSimulation(bus, twin)
    advisors = AdvisorEngine(bus, hub)
    companion = Companion(router)
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
        router=router,
    )
