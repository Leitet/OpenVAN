"""Assembly of a running OpenVan Core.

Wires the event bus, digital twin, simulation backend, safety validator, hub and
plugin manager together. Kept separate from the API so tests (and, later,
non-HTTP front-ends like a voice loop) can drive a fully-formed Core directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing import Any

from .backends import Backend, SimBackend
from .camp import CampService
from .companion import Companion
from .config import Config
from .events import EventBus
from .hub import Hub
from .intents import Intent, IntentResolver
from .llm import (
    OPENAI_URL,
    AnthropicClient,
    LLMIntentResolver,
    ModelRouter,
    OllamaClient,
    OpenAICompatibleClient,
    filter_chat_models,
)
from .memory import TravelMemory
from .notices import AdvisorEngine, RainSoon, default_advisors
from .personalities import PersonalityStore
from .plugins import PluginManager
from .safety import (
    CriticalBatteryLoadShedding,
    FuelRequiredToStart,
    PumpDryRunProtection,
    SafetyValidator,
)
from .simulation import VanSimulation
from .telemetry import TelemetryRecorder, TelemetryStore
from .twin import VanTwin
from .weather import WeatherService


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
    telemetry: TelemetryStore
    telemetry_recorder: TelemetryRecorder
    weather: WeatherService
    memory: TravelMemory
    camp: CampService

    async def start(self) -> None:
        # Open telemetry and start recording before seeding, so the initial
        # state is captured as the first samples.
        if self.config.telemetry_enabled:
            self.telemetry.open()
            self.telemetry_recorder.start()  # records + rolls up + prunes
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
        if self.config.weather_enabled:
            await self.weather.start()
        if self.config.memory_enabled:
            await self.memory.start()
        if self.config.camp_enabled:
            self.camp.discover()

    async def stop(self) -> None:
        if self.config.memory_enabled:
            await self.memory.stop()
        if self.config.weather_enabled:
            await self.weather.stop()
        await self.advisors.stop()
        await self.simulation.stop()
        if self.config.telemetry_enabled:
            await self.telemetry_recorder.stop()
            self.telemetry.close()
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

    async def chat(self, text: str) -> dict[str, Any]:
        """Conversational assistant entry point. A message is either a device command
        (runs through the safety-checked intent path) or a question (answered from live
        van state, read-only). The AI never controls hardware except via an intent the
        safety layer has approved (Rule 2), and a *question* is never mistaken for a
        command — with a model that decision is made explicitly in one call."""
        resolver = self.hub.resolver
        entities = self.hub.entities
        notices = self.advisors.active_notices()
        persona = self.personalities.get_active().style

        language = self.config.language

        if getattr(resolver, "active", False):
            status = self.companion.build_context(self.hub, notices)
            intent, reply, camp = await resolver.converse(
                text, entities, status, persona, language
            )
            if intent is not None:
                return await self._chat_action(intent)
            if camp is not None:
                return await self._chat_camp(camp, notices, persona, language)
            if reply is not None:
                return {"reply": reply, "action": False, "ok": True, "blocked_by_safety": False}
            # Model gave nothing usable — answer from state, don't guess a command.
            answer = await self.companion.answer(
                self.hub, notices, text, use_llm=True, persona=persona, language=language
            )
            return {"reply": answer, "action": False, "ok": True, "blocked_by_safety": False}

        # Offline: the rule resolver is conservative (only known command phrases);
        # everything else gets a templated status answer.
        intent = await resolver.resolve(text, entities)
        if intent is not None:
            return await self._chat_action(intent)
        answer = await self.companion.answer(
            self.hub, notices, text, use_llm=False, persona=persona, language=language
        )
        return {"reply": answer, "action": False, "ok": True, "blocked_by_safety": False}

    async def _chat_action(self, intent: Intent) -> dict[str, Any]:
        result = await self.hub.execute_intent(intent)
        return {
            "reply": result.reason or ("Done." if result.ok else "I couldn't do that."),
            "action": True,
            "ok": result.ok,
            "blocked_by_safety": result.blocked_by_safety,
        }

    async def _chat_camp(
        self, camp: dict[str, Any], notices, persona, language
    ) -> dict[str, Any]:
        """Search nearby camp spots and let the van recommend one (read-only)."""
        result = (
            await self.camp.search(camp.get("radius_km"))
            if self.config.camp_enabled
            else {"spots": []}
        )
        spots = result.get("spots", [])
        reply = await self.companion.recommend_camp(
            self.hub,
            notices,
            spots,
            camp.get("wants") or [],
            use_llm=self.router.active,
            persona=persona,
            language=language,
        )
        return {
            "reply": reply,
            "action": False,
            "ok": True,
            "blocked_by_safety": False,
            "spots": spots,
        }

    # --- runtime settings (Admin UI / API / MCP) -------------------------
    def settings(self) -> dict[str, Any]:
        from . import __version__

        return {
            "version": __version__,
            "host": self.config.host,
            "port": self.config.port,
            "ai_enabled": self.config.ai_enabled,
            "connectivity": self.config.connectivity,
            "language": self.config.language,
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
        connectivity: str | None = None,
        language: str | None = None,
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
        if connectivity is not None:
            self.config.connectivity = connectivity
        if language is not None:
            self.config.language = language
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

        self._save_settings()
        result = self.settings()
        await self.bus.publish("settings.changed", {"settings": result})
        await self.bus.publish("assistant.changed", self.assistant_state())
        return result

    async def set_camp_source(self, source_id: str, enabled: bool) -> bool:
        if not self.camp.set_enabled(source_id, enabled):
            return False
        self._save_settings()
        await self.bus.publish("settings.changed", {"settings": self.settings()})
        return True

    def _save_settings(self) -> None:
        from .config import settings_path

        path = settings_path(self.config.data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.config.persistable(), indent=2))

    def predictions(self) -> dict[str, Any]:
        from .predictions import compute_predictions

        telemetry = self.telemetry if self.config.telemetry_enabled else None
        weather = self.weather.snapshot() if self.config.weather_enabled else None
        return compute_predictions(
            self.twin, telemetry, weather=weather, solar_capacity_w=self.config.solar_capacity_w
        )

    async def available_models(self, connectivity: str = "offline") -> list[str]:
        if connectivity == "online":
            provider = self.config.online_provider
            if provider == "anthropic":
                client = AnthropicClient(self.config.online_api_key, self.config.online_model)
            else:
                base = OPENAI_URL if provider == "openai" else self.config.online_base_url
                if not base:
                    return []
                client = OpenAICompatibleClient(
                    base, self.config.online_model, self.config.online_api_key
                )
            # Only chat-capable models — drop embeddings, audio, image, etc.
            return filter_chat_models(await client.list_models())
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
    router = ModelRouter(config)
    resolver = LLMIntentResolver(router, fallback=IntentResolver())
    hub = Hub(bus, twin, safety, resolver)
    plugins = PluginManager(hub, backend)
    simulation = VanSimulation(bus, twin)
    weather = WeatherService(
        config,
        get_location=lambda: (twin.get("gps.lat"), twin.get("gps.lon")),
        bus=bus,
    )
    advisors = AdvisorEngine(bus, hub, default_advisors() + [RainSoon(weather)])
    telemetry = TelemetryStore(
        config.data_dir / "telemetry.db", config.telemetry_retention_days
    )
    telemetry_recorder = TelemetryRecorder(
        bus,
        telemetry,
        roll_interval=config.telemetry_roll_interval_s,
        raw_retention_days=config.telemetry_retention_days,
        rollup_retention_days=config.telemetry_rollup_days,
    )
    memory = TravelMemory(config, twin, weather=weather, telemetry=telemetry)
    companion = Companion(router, telemetry, weather, memory)
    camp = CampService(
        config, get_location=lambda: (twin.get("gps.lat"), twin.get("gps.lon"))
    )
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
        telemetry=telemetry,
        telemetry_recorder=telemetry_recorder,
        weather=weather,
        memory=memory,
        camp=camp,
        router=router,
    )
