"""Assembly of a running OpenVan Core.

Wires the event bus, digital twin, simulation backend, safety validator, hub and
plugin manager together. Kept separate from the API so tests (and, later,
non-HTTP front-ends like a voice loop) can drive a fully-formed Core directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from typing import Any

from .backends import Backend, SimBackend
from .camp import CampService
from .companion import Companion
from .config import DEFAULT_TUNING, Config
from .conversation import ChatMemory
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
from .integrations import IntegrationManager
from .memory import TravelMemory
from .maintenance import MaintenanceLog
from .coverage import CoverageMemory
from .notices import (
    AdvisorEngine,
    Intrusion,
    RainSoon,
    ServiceDue,
    SolarWindow,
    WeakSignal,
    default_advisors,
)
from .personalities import PersonalityStore
from .plugins import PluginManager, registered_plugins
from .safety import (
    CriticalBatteryLoadShedding,
    FuelRequiredToStart,
    PumpDryRunProtection,
    SafetyValidator,
)
from .roads import RoadNetwork
from .scenes import SceneEngine, default_scenes
from .security import SecuritySystem
from .simulation import VanSimulation
from .store import ConfigStore
from .telemetry import TelemetryRecorder, TelemetryStore
from .twin import VanTwin
from .weather import WeatherService

# Phrase hints that a message is asking where to spend the night. Deterministic so a
# weak/offline model can't mistake "where should we sleep?" for a device command.
# Phrase-based (not bare "camp") to avoid false positives like "the campervan".
_CAMP_HINTS = (
    "campsite", "camping", "campground", "camp for the night", "camp tonight",
    "where to camp", "somewhere to camp", "place to camp", "find a camp", "wild camp",
    "an aire", "overnight spot", "overnight stay", "stay overnight", "park overnight",
    "sleep tonight", "somewhere to sleep", "where to sleep", "where should we sleep",
    "spend the night", "stay the night", "spot for the night", "pitch for the night",
    "park for the night", "park up for the night", "place to stay tonight",
    # sv
    "campingplats", "ställplats", "övernatta", "sova i natt", "var ska vi sova",
    "stå för natten", "plats för natten",
    # de
    "campingplatz", "stellplatz", "übernachten", "wo schlafen wir", "platz für die nacht",
)
_CAMP_RE = re.compile("|".join(re.escape(h) for h in _CAMP_HINTS), re.IGNORECASE)


def _looks_like_camp_query(text: str) -> bool:
    return bool(_CAMP_RE.search(text))


# Explicit spoken triggers for scenes. Kept fairly specific so a stray "let's go"
# doesn't switch the van off — running a scene actuates devices (via safety).
_SCENE_PATTERNS = [
    ("goodnight", re.compile(r"\bgood ?night\b|\bnight night\b|going to (bed|sleep)|\bbed ?time\b", re.I)),
    ("morning", re.compile(r"\bgood morning\b|\bmorning routine\b|time to (wake|get up)", re.I)),
    ("setup_camp", re.compile(r"\bset ?up camp\b|\bmake camp\b|\bwe'?re here\b|\bwe'?ve arrived\b|\barrived\b", re.I)),
    ("leaving", re.compile(r"\b(leaving|heading out|packing up|pack up|hit the road)\b|time to (go|drive|leave)", re.I)),
]


def _match_scene(text: str) -> str | None:
    for scene_id, rx in _SCENE_PATTERNS:
        if rx.search(text):
            return scene_id
    return None


def _build_advisors(config, weather, maintenance, security, coverage):
    """The complete advisor list, all thresholds from config tuning. Reused at
    build time and whenever tuning changes, so live edits take effect."""
    return default_advisors(config) + [
        RainSoon(weather, threshold_h=config.tune("rain_soon_hours")),
        ServiceDue(maintenance),
        Intrusion(security),
        WeakSignal(config.tune("signal_weak_pct"), coverage),
        SolarWindow(
            weather,
            config.solar_capacity_w,
            min_w=config.tune("solar_window_min_w"),
            soc_pct=config.tune("solar_window_soc_pct"),
        ),
    ]


@dataclass
class Core:
    config: Config
    bus: EventBus
    twin: VanTwin
    backend: Backend
    hub: Hub
    plugins: PluginManager
    integrations: IntegrationManager
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
    store: ConfigStore
    memory_chat: ChatMemory
    scenes: SceneEngine
    maintenance: MaintenanceLog
    security: SecuritySystem
    coverage: CoverageMemory
    roads: RoadNetwork | None = None

    async def start(self) -> None:
        # The config store holds plugin / camp-source settings (incl. credentials)
        # and the assistant's learned memory (summary + preferences).
        self.store.open()
        self.memory_chat.load()
        self.maintenance.load()
        # Open telemetry and start recording before seeding, so the initial
        # state is captured as the first samples.
        if self.config.telemetry_enabled:
            self.telemetry.open()
            self.telemetry_recorder.start()  # records + rolls up + prunes
        # Seed the twin first so plugins read sensible values on setup.
        for key, value in self.config.seed_twin.items():
            await self.twin.set_signal(key, value, source="seed")
        self.plugins.discover(self.config.plugins_dir)
        # Plugin config comes from the store (namespace "plugin:<domain>"), not env.
        plugin_configs = {
            cls.domain: self.store.get_all(f"plugin:{cls.domain}")
            for cls in registered_plugins()
        }
        await self.plugins.setup_all(plugin_configs)
        # Integration drivers normalise hardware ecosystems into twin signals. In
        # sim mode their enabled drivers inject characteristic signals each tick.
        self.integrations.discover(self.config.integrations_dir)
        await self.integrations.setup_all()
        await self.router.refresh()  # probe the effective model for the active profile
        if self.roads is not None:
            self.roads.load_cache()  # last-known road graph, for instant offline follow
        if self.config.simulate:
            self.simulation.start()
        # Record the coverage trail, then subscribe advisors and evaluate once
        # against the seeded state.
        self.coverage.start()
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
        self.coverage.stop()
        await self.advisors.stop()
        await self.simulation.stop()
        if self.config.telemetry_enabled:
            await self.telemetry_recorder.stop()
            self.telemetry.close()
        await self.integrations.teardown_all()
        await self.plugins.teardown_all()
        self.store.close()

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
        persona = self.personalities.get_active().style
        language = self.config.language

        result = await self._route(text, persona, language)

        # Record the turn, then let the model fold older context into the long-term
        # summary and update learned preferences (every few turns, when available).
        self.memory_chat.record("user", text)
        reply = result.get("reply")
        if reply:
            self.memory_chat.record("assistant", reply)
        await self.memory_chat.maybe_consolidate(persona, language)
        return result

    async def _route(self, text: str, persona: str | None, language: str) -> dict[str, Any]:
        resolver = self.hub.resolver
        entities = self.hub.entities
        notices = self.advisors.active_notices()
        preferences = self.memory_chat.preferences

        # A spoken routine ("goodnight", "we're leaving") runs a whole scene — the
        # safety layer still vets every step. Checked first, deterministically.
        scene_id = _match_scene(text)
        if scene_id is not None:
            return await self._run_scene_reply(scene_id)

        # Camp queries route to a camp search regardless of model strength, so a weak
        # or offline model can't mistake "where should we sleep?" for a device command.
        if self.config.camp_enabled and _looks_like_camp_query(text):
            return await self._chat_camp(
                {"radius_km": None, "wants": []}, notices, persona, language, request=text
            )

        if getattr(resolver, "active", False):
            status = self.companion.build_context(self.hub, notices)
            # Recent turns for follow-ups, plus the long-term summary + learned
            # preferences so the van tailors its answer to how you like things.
            intent, reply, camp = await resolver.converse(
                text,
                entities,
                status,
                persona,
                language,
                history=self.memory_chat.recent(),
                memory=self.memory_chat.context(),
            )
            if intent is not None:
                return await self._chat_action(intent)
            if camp is not None:
                return await self._chat_camp(camp, notices, persona, language, request=text)
            if reply is not None:
                return {"reply": reply, "action": False, "ok": True, "blocked_by_safety": False}
            # Model gave nothing usable — answer from state, don't guess a command.
            answer = await self.companion.answer(
                self.hub, notices, text, use_llm=True, persona=persona,
                language=language, preferences=preferences,
            )
            return {"reply": answer, "action": False, "ok": True, "blocked_by_safety": False}

        # Offline: the rule resolver is conservative (only known command phrases);
        # everything else gets a templated status answer.
        intent = await resolver.resolve(text, entities)
        if intent is not None:
            return await self._chat_action(intent)
        answer = await self.companion.answer(
            self.hub, notices, text, use_llm=False, persona=persona,
            language=language, preferences=preferences,
        )
        return {"reply": answer, "action": False, "ok": True, "blocked_by_safety": False}

    async def run_scene(self, scene_id: str) -> dict[str, Any] | None:
        """Run a scene's steps through the safety-checked intent path."""
        return await self.scenes.run(scene_id)

    # --- vehicle profile -------------------------------------------------
    def vehicle_state(self) -> dict[str, Any]:
        from .vehicle import CATEGORIES, presets_list

        return {
            "profile": dict(self.config.vehicle),
            "presets": presets_list(),
            "categories": CATEGORIES,
        }

    async def set_vehicle(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Replace the vehicle profile (drop blanks), persist it, and rebuild the
        leveling advisor which uses the wheelbase/track."""
        self.config.vehicle = {k: v for k, v in profile.items() if v not in (None, "")}
        self._apply_tunables()  # leveling geometry comes from the vehicle now
        self._save_settings()
        await self.bus.publish("settings.changed", {"settings": self.settings()})
        return self.vehicle_state()

    # --- integrations (hardware ecosystem drivers) -----------------------
    def integrations_list(self) -> list[dict[str, Any]]:
        """The integration catalog: every driver's descriptor + live enabled state."""
        return self.integrations.list()

    async def set_integration_enabled(self, integration_id: str, enabled: bool) -> bool:
        """Enable/disable an integration and persist the choice."""
        return await self.integrations.set_enabled(integration_id, enabled)

    async def set_integration_config(self, integration_id: str, values: dict[str, Any]) -> bool:
        """Persist a driver's connection settings (host/port/mode/credentials) and
        reconnect its transport so the change takes effect live."""
        return await self.integrations.set_config(integration_id, values)

    # --- cameras (dynamic) ----------------------------------------------
    def cameras(self) -> list[dict[str, str]]:
        plugin = self.plugins.get("cameras")
        return plugin.list() if plugin is not None else []

    async def add_camera(self, cam_id: str, label: str, location: str, connection: str) -> bool:
        plugin = self.plugins.get("cameras")
        if plugin is None or not await plugin.add_camera(cam_id, label, location, connection):
            return False
        self.store.set_many("plugin:cameras", {"list": plugin.list()})
        return True

    async def remove_camera(self, cam_id: str) -> bool:
        plugin = self.plugins.get("cameras")
        if plugin is None or not await plugin.remove_camera(cam_id):
            return False
        self.store.set_many("plugin:cameras", {"list": plugin.list()})
        return True

    def maintenance_status(self) -> list[dict[str, Any]]:
        from datetime import datetime

        odo = self.twin.get("vehicle.odometer_km")
        return self.maintenance.status(odo, datetime.now().date())

    def complete_maintenance(self, item_id: str) -> bool:
        from datetime import datetime

        odo = self.twin.get("vehicle.odometer_km")
        return self.maintenance.complete(item_id, odo, datetime.now().date())

    def _apply_tunables(self) -> None:
        """Rebuild the config-driven advisors/scenes/maintenance after a tuning
        change, so overrides take effect without a restart."""
        self.advisors.advisors = _build_advisors(
            self.config, self.weather, self.maintenance, self.security, self.coverage
        )
        self.scenes = SceneEngine(
            self.hub,
            default_scenes(self.config.tune("scene_sleep_c"), self.config.tune("scene_comfort_c")),
        )
        self.maintenance.intervals = self.config.maintenance_intervals
        self.maintenance.load()

    async def set_security_armed(self, armed: bool) -> dict[str, Any]:
        """Arm/disarm away mode, then re-run advisors so an intrusion notice
        appears or clears immediately."""
        self.security.set_armed(armed)
        await self.advisors.evaluate()
        return self.security.status()

    async def _run_scene_reply(self, scene_id: str) -> dict[str, Any]:
        result = await self.scenes.run(scene_id)
        if result is None:
            return {"reply": "I don't know that routine.", "action": False,
                    "ok": False, "blocked_by_safety": False}
        name = result["scene"]["name"]
        blocked = [r for r in result["steps"] if r.get("blocked_by_safety")]
        if blocked:
            reply = f"{name}: done — but I held back {len(blocked)} step(s) for safety."
        else:
            reply = f"{name}: all set. {result['scene']['description']}"
        return {"reply": reply, "action": True, "ok": result["ok"],
                "blocked_by_safety": bool(blocked), "scene": result["scene"]["id"]}

    async def _chat_action(self, intent: Intent) -> dict[str, Any]:
        result = await self.hub.execute_intent(intent)
        return {
            "reply": result.reason or ("Done." if result.ok else "I couldn't do that."),
            "action": True,
            "ok": result.ok,
            "blocked_by_safety": result.blocked_by_safety,
        }

    async def _chat_camp(
        self, camp: dict[str, Any], notices, persona, language, request: str = ""
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
            request=request,
            use_llm=self.router.active,
            persona=persona,
            language=language,
            preferences=self.memory_chat.preferences,
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
            # Feature tuning — current values + built-in defaults so the UI can edit
            # and reset. Nothing here is hardcoded in the logic.
            "tuning": dict(self.config.tuning),
            "tuning_defaults": dict(DEFAULT_TUNING),
            "maintenance_intervals": dict(self.config.maintenance_intervals),
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
        tuning: dict[str, Any] | None = None,
        maintenance_intervals: dict[str, Any] | None = None,
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

        # Feature tuning — merge overrides, then rebuild the advisors/scenes that
        # use them so the change takes effect live (not just on restart).
        tunables_changed = False
        if tuning:
            self.config.tuning.update({k: float(v) for k, v in tuning.items()})
            tunables_changed = True
        if maintenance_intervals:
            self.config.maintenance_intervals.update(
                {k: float(v) for k, v in maintenance_intervals.items()}
            )
            tunables_changed = True
        if tunables_changed:
            self._apply_tunables()

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

    async def set_camp_source_config(self, source_id: str, values: dict[str, Any]) -> bool:
        """Persist a camp source's settings (keys, endpoints) to the config database."""
        if not self.camp.set_config(source_id, values):
            return False
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
    store = ConfigStore(config.data_dir / "store.db")
    integrations = IntegrationManager(twin, bus, store)
    roads = RoadNetwork(config) if config.roads_enabled else None
    simulation = VanSimulation(bus, twin, roads=roads, integrations=integrations)
    weather = WeatherService(
        config,
        get_location=lambda: (twin.get("gps.lat"), twin.get("gps.lon")),
        bus=bus,
    )
    advisors = AdvisorEngine(bus, hub, [])
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
    companion = Companion(router, telemetry, weather, memory, config=config)
    camp = CampService(
        config,
        get_location=lambda: (twin.get("gps.lat"), twin.get("gps.lon")),
        store=store,
    )
    memory_chat = ChatMemory(store, router)
    scenes = SceneEngine(
        hub, default_scenes(config.tune("scene_sleep_c"), config.tune("scene_comfort_c"))
    )
    maintenance = MaintenanceLog(
        store,
        get_odometer=lambda: twin.get("vehicle.odometer_km"),
        intervals=config.maintenance_intervals,
    )
    security = SecuritySystem()
    coverage = CoverageMemory(bus, twin)
    # Build the full advisor set from config-driven thresholds (nothing hardcoded).
    advisors.advisors = _build_advisors(config, weather, maintenance, security, coverage)
    return Core(
        config=config,
        bus=bus,
        twin=twin,
        backend=backend,
        hub=hub,
        plugins=plugins,
        integrations=integrations,
        simulation=simulation,
        advisors=advisors,
        companion=companion,
        personalities=personalities,
        telemetry=telemetry,
        telemetry_recorder=telemetry_recorder,
        weather=weather,
        memory=memory,
        camp=camp,
        store=store,
        memory_chat=memory_chat,
        scenes=scenes,
        maintenance=maintenance,
        security=security,
        coverage=coverage,
        router=router,
        roads=roads,
    )
