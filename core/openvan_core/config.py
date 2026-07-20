"""Runtime configuration for OpenVan Core.

Kept deliberately small and env-driven (offline-first: sensible defaults, no
config server required). ``plugins_dir`` defaults to the monorepo ``plugins/``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

from .vehicle import PRESETS as _VEHICLE_PRESETS

_CORE_DIR = Path(__file__).resolve().parent.parent  # .../core
_REPO_ROOT = _CORE_DIR.parent  # repo root

# Ship with a common European converted-van profile; the user picks their own.
_DEFAULT_VEHICLE = dict(_VEHICLE_PRESETS["citroen_jumper_l3h2"])

# Settings changed at runtime (Admin UI / API) that survive a restart. The API
# key is deliberately NOT here — it stays in memory / env only, never on disk.
_PERSISTED_FIELDS = (
    "ai_enabled",
    "connectivity",
    "language",
    "llm_base_url",
    "llm_model",
    "online_provider",
    "online_base_url",
    "online_model",
    "simulate",
    "camp_sources",
    "camp_search_radius_km",
    "tuning",
    "maintenance_intervals",
    "vehicle",
)

# Feature thresholds/setpoints — sensible DEFAULTS that are all overridable at
# runtime (settings.json / API), so nothing is hardcoded in the advisors, scenes
# or leveling maths. Keys are grouped by feature; see docs and the Settings UI.
DEFAULT_TUNING = {
    # Water / energy / journey (existing advisors)
    "fresh_water_low_pct": 15.0,
    "grey_water_full_pct": 85.0,
    "diesel_low_pct": 15.0,
    "battery_low_hours": 24.0,
    "long_drive_hours": 2.0,
    "rain_soon_hours": 2.0,
    "signal_weak_pct": 25.0,
    "solar_window_min_w": 200.0,
    "solar_window_soc_pct": 80.0,
    # Air & safety
    "co_warn_ppm": 35.0,
    "co_danger_ppm": 70.0,
    "gas_leak_lel": 10.0,
    "co2_high_ppm": 1500.0,
    "condensation_humidity_pct": 60.0,
    "condensation_margin_c": 1.5,
    "cabin_cold_c": 3.0,
    "cabin_hot_c": 30.0,
    # Propane
    "propane_low_pct": 20.0,
    # Fridge
    "fridge_warm_c": 8.0,
    # Leveling
    "level_threshold_deg": 1.5,
    "level_track_m": 2.0,
    "level_wheelbase_m": 3.6,
    # Scenes (heater setpoints)
    "scene_sleep_c": 16.0,
    "scene_comfort_c": 20.0,
}


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "settings.json"


def _load_dotenv(path: Path) -> None:
    """Minimal ``.env`` loader — stdlib only (offline-first, no dependency).

    Loads ``KEY=VALUE`` lines into the environment so secrets like
    ``OPENVAN_ONLINE_API_KEY`` survive restarts without being typed each time.
    Never overrides a variable already set in the real environment, and the file
    is gitignored so the key never lands in git.
    """
    if not path.exists():
        return
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Empty value (e.g. a blank placeholder key) = not set; and never
            # override a variable already set in the real environment.
            if key and value and key not in os.environ:
                os.environ[key] = value
    except OSError:
        logger.warning("could not read .env file %s", path)


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8000
    plugins_dir: Path = field(default_factory=lambda: _REPO_ROOT / "plugins")
    # Integration drivers (Victron, ESPHome, MQTT/HA, Modbus, …) — the layer that
    # normalises hardware ecosystems into twin signals. Discovered like plugins.
    integrations_dir: Path = field(default_factory=lambda: _REPO_ROOT / "integrations")
    # User-installed drivers (community/store packages) live under the data dir,
    # separate from the bundled repo dirs. None → data_dir / "drivers".
    drivers_dir: Path | None = None
    # Lockdown mode: refuse unsigned / unknown-signer drivers entirely. Off by
    # default — your van, your call — but tampered packages NEVER load regardless.
    require_signed: bool = False
    # Local storage for things that must survive restarts (custom personalities,
    # the active choice). Offline-first: a plain local directory, no server.
    data_dir: Path = field(default_factory=lambda: _REPO_ROOT / "data")
    # Run the environment simulation (thermal + water physics) that makes the
    # twin evolve over time. Sim-mode only; a real van gets these from sensors.
    simulate: bool = True
    # Local time-series telemetry (SQLite under data_dir). Records every numeric
    # signal for graphs, trends and predictions.
    telemetry_enabled: bool = True
    telemetry_retention_days: float = 7.0  # raw samples
    telemetry_rollup_days: float = 365.0  # hourly/daily aggregates
    telemetry_roll_interval_s: float = 600.0  # how often to roll up + prune
    # Location-aware weather (open-meteo, keyless). Offline-first: cached forecast
    # when there's no internet. Cloud enhances, never required.
    weather_enabled: bool = True
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_refresh_s: float = 600.0
    # Rated peak of the solar array (W) — powers the weather-aware solar forecast.
    # Illustrative; measure a real install before shipping.
    solar_capacity_w: float = 600.0
    # Camp spots — external providers of places to stay (campsources/). Enabled
    # source ids; the "sim" source is always safe (offline). Others (e.g. keyless
    # OSM "overpass") are opt-in in the Admin UI.
    camp_enabled: bool = True
    camp_sources: list[str] = field(default_factory=lambda: ["sim"])
    camp_search_radius_km: float = 30.0
    camp_sources_dir: Path = field(default_factory=lambda: _REPO_ROOT / "campsources")
    # Road-following: snap simulated driving onto the real OSM road graph so the
    # GPS trace follows actual streets (matches the map tiles). Enhancement only —
    # the sim dead-reckons when this is off or roads can't be fetched (offline).
    roads_enabled: bool = True
    roads_radius_m: float = 1600.0
    # Feature tuning — advisor thresholds, scene setpoints, leveling geometry. All
    # default from DEFAULT_TUNING and are overridable (settings.json / API / UI), so
    # no value is hardcoded in the logic. See Config.tune().
    tuning: dict = field(default_factory=lambda: dict(DEFAULT_TUNING))
    # Per-item maintenance interval overrides, keyed by item id (km or days). Empty
    # = use the built-in defaults in maintenance.DEFAULT_ITEMS.
    maintenance_intervals: dict = field(default_factory=dict)
    # The physical vehicle profile (dimensions, weight, fuel, tyres, category).
    # Drives leveling geometry and gives the assistant decision context. Defaults to
    # a common preset; the user picks their own in Settings > Vehicle.
    vehicle: dict = field(default_factory=lambda: dict(_DEFAULT_VEHICLE))
    # Travel memory — auto-logs "stays" when parked. Offline-first, SQLite.
    memory_enabled: bool = True
    memory_dwell_s: float = 90.0  # parked this long before a stay is logged
    memory_check_s: float = 15.0  # how often to check for park/depart
    # Model-agnostic AI assistant. Optional: if the model is unreachable, OpenVan
    # falls back to the offline rule-based resolver.
    ai_enabled: bool = True
    # The single global connectivity mode: which model answers, local or cloud.
    # Independent of the chosen personality (voice). "offline" | "online".
    connectivity: str = "offline"
    # Language the assistant (model) replies in: "en" | "sv" | "de". Normally the
    # UI sets this to match its own language; the user can override it.
    language: str = "en"
    # Voice pipeline (offline-first STT/TTS; see voice.py). "auto" picks a real
    # engine when its optional library is installed (pip install -e ".[voice]"),
    # else the sim engine in simulate mode, else unavailable — the front-end then
    # keeps using the browser speech APIs. Explicit: "off" | "sim" | "whisper"/"piper".
    voice_stt: str = "auto"
    voice_tts: str = "auto"
    voice_whisper_model: str = "base"  # faster-whisper model size
    voice_piper_model: str = ""  # path to a piper .onnx voice (required for piper)
    # BLE substrate (see ble.py): one shared scanner all BLE drivers subscribe to.
    # "auto" prefers a real adapter via the optional `ble` extra (bleak), else the
    # sim radio in simulate mode. "off" | "sim" | "bleak" pin it.
    ble_radio: str = "auto"
    # Offline models: a local Ollama server.
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "llama3.2"
    # Online models. Provider "openai" targets any OpenAI-compatible endpoint
    # (base_url must serve /chat/completions and /models); provider "anthropic"
    # targets the Claude Messages API (base_url defaults to api.anthropic.com).
    # The API key comes from the environment and is kept in memory, never on disk.
    # "openai" (pinned to api.openai.com) | "openai_compatible" (custom base_url)
    # | "anthropic" (Claude Messages API, own endpoint).
    online_provider: str = "openai"
    online_base_url: str = "https://api.openai.com/v1"
    online_model: str = ""
    online_api_key: str | None = None
    # Seed the twin with a pleasant default van state so the simulator has
    # something to show on first load.
    seed_twin: dict[str, float | bool] = field(
        default_factory=lambda: {
            "house_battery.soc": 82.0,
            "house_battery.voltage": 12.9,
            "house_battery.current": -4.2,
            "solar.power": 240.0,
            "fresh_water.level_pct": 55.0,
            "grey_water.level_pct": 8.0,
            "water_pump.on": False,
            "cabin.temperature": 19.5,
            "outside.temperature": 11.0,
            # Air quality & safety — healthy defaults (CO2 ~600 indoors, RH ~55%).
            "air.co_ppm": 0.0,
            "air.lpg_pct_lel": 0.0,
            "air.co2_ppm": 600.0,
            "air.smoke": False,
            "cabin.humidity_pct": 55.0,
            # Inclinometer — parked dead level by default.
            "imu.pitch_deg": 0.0,
            "imu.roll_deg": 0.0,
            "cabin_light.on": False,
            "diesel_heater.on": False,
            "diesel_heater.setpoint": 20.0,
            "diesel_heater.power": 0.0,
            "diesel_tank.level_pct": 70.0,
            "propane.level_pct": 60.0,
            # Fridge — cold, closed, drawing a typical compressor load.
            "fridge.temp_c": 4.0,
            "fridge.door_open": False,
            "fridge.power": 45.0,
            # The van's DC energy system. These are physical facts of the van
            # (it has an alternator, a shore inlet, an inverter) that the environment
            # simulation evolves and an energy integration (Victron, …) reads on real
            # hardware — not invented by any one integration.
            "shore.connected": False,
            "inverter.on": False,
            "inverter.ac_load": 0.0,
            "inverter.temperature": 19.5,
            "alternator.power": 0.0,
            "solar.yield_today_wh": 0.0,
            # Home-Assistant presence input (van parked on the home network).
            "home_assistant.van_home": False,
            # Connectivity — a physical fact of the van (it has a link, or it
            # doesn't). The simulation/bench drive it; a router integration
            # (Teltonika, Starlink, …) reads it on real hardware. Offline-first:
            # Core never depends on this being True.
            "connectivity.online": True,
            "connectivity.network": "LTE",  # LTE | 5G | WiFi | Starlink | none
            "connectivity.signal_pct": 74.0,
            "connectivity.has_gps_fix": True,
            # Security — quiet by default.
            "security.door_open": False,
            "security.motion": False,
            # Cameras — all online, no motion, not recording.
            "camera.rear.online": True,
            "camera.rear.motion": False,
            "camera.rear.recording": False,
            "camera.cabin.online": True,
            "camera.cabin.motion": False,
            "camera.cabin.recording": False,
            "camera.entry.online": True,
            "camera.entry.motion": False,
            "camera.entry.recording": False,
            "camera.awning.online": True,
            "camera.awning.motion": False,
            "camera.awning.recording": False,
            # Simulated clock — ~2026-07-14 12:00 UTC (midday). clock.rate is a time
            # multiplier (0 = paused). The sim derives sun/day-night from it + GPS.
            "clock.epoch": 1784030400.0,
            "clock.rate": 1.0,
            "sun.elevation_deg": 40.0,
            "environment.is_day": True,
            "environment.phase": "day",
            # Vehicle / GPS — starting parked in the Dolomites.
            "gps.lat": 46.5405,
            "gps.lon": 11.6553,
            "vehicle.speed_kmh": 0.0,
            "vehicle.heading": 90.0,
            "vehicle.odometer_km": 48210.0,
            "vehicle.ignition": False,
            "vehicle.trip_seconds": 0.0,
            # Tightest routing limits on the road ahead (0 = none). Filled from OSM
            # maxheight/maxweight when road data is available; else driven from the
            # bench to simulate approaching a low bridge or a weight-limited road.
            "road.max_height_m": 0.0,
            "road.max_weight_t": 0.0,
        }
    )

    def tune(self, key: str) -> float:
        """A tuning value: the override if set, else the built-in default."""
        return float(self.tuning.get(key, DEFAULT_TUNING[key]))

    # --- persistence -----------------------------------------------------
    def persistable(self) -> dict:
        """The runtime-changeable settings that survive a restart (no API key)."""
        return {f: getattr(self, f) for f in _PERSISTED_FIELDS}

    def apply(self, data: dict) -> None:
        for f in _PERSISTED_FIELDS:
            if f in data and data[f] is not None:
                # Dict settings (tuning, maintenance overrides, vehicle) MERGE, so a
                # partial update keeps the other fields instead of wiping them.
                if f in ("tuning", "maintenance_intervals", "vehicle") and isinstance(data[f], dict):
                    getattr(self, f).update(data[f])
                else:
                    setattr(self, f, data[f])

    @classmethod
    def resolve(cls) -> "Config":
        """Build the effective config: defaults < persisted file < environment."""
        # Populate env from .env before reading it. OPENVAN_ENV_FILE overrides the
        # path (tests point it away from the repo's real .env).
        env_file = os.environ.get("OPENVAN_ENV_FILE")
        _load_dotenv(Path(env_file) if env_file else _REPO_ROOT / ".env")
        cfg = cls()
        if os.environ.get("OPENVAN_DATA_DIR"):
            cfg.data_dir = Path(os.environ["OPENVAN_DATA_DIR"])
        path = settings_path(cfg.data_dir)
        if path.exists():
            try:
                cfg.apply(json.loads(path.read_text()))
            except (OSError, ValueError):
                logger.warning("could not read settings file %s", path)
        cfg._apply_env()  # env has the final say
        return cfg

    @classmethod
    def from_env(cls) -> "Config":
        return cls()._apply_env()

    def _apply_env(self) -> "Config":
        cfg = self
        cfg.host = os.environ.get("OPENVAN_HOST", cfg.host)
        cfg.port = int(os.environ.get("OPENVAN_PORT", cfg.port))
        if os.environ.get("OPENVAN_PLUGINS_DIR"):
            cfg.plugins_dir = Path(os.environ["OPENVAN_PLUGINS_DIR"])
        if os.environ.get("OPENVAN_INTEGRATIONS_DIR"):
            cfg.integrations_dir = Path(os.environ["OPENVAN_INTEGRATIONS_DIR"])
        if os.environ.get("OPENVAN_DRIVERS_DIR"):
            cfg.drivers_dir = Path(os.environ["OPENVAN_DRIVERS_DIR"])
        if os.environ.get("OPENVAN_REQUIRE_SIGNED"):
            cfg.require_signed = os.environ["OPENVAN_REQUIRE_SIGNED"] not in ("0", "false", "")
        cfg.voice_stt = os.environ.get("OPENVAN_VOICE_STT", cfg.voice_stt)
        cfg.voice_tts = os.environ.get("OPENVAN_VOICE_TTS", cfg.voice_tts)
        cfg.voice_whisper_model = os.environ.get("OPENVAN_WHISPER_MODEL", cfg.voice_whisper_model)
        cfg.voice_piper_model = os.environ.get("OPENVAN_PIPER_MODEL", cfg.voice_piper_model)
        cfg.ble_radio = os.environ.get("OPENVAN_BLE_RADIO", cfg.ble_radio)
        if os.environ.get("OPENVAN_DATA_DIR"):
            cfg.data_dir = Path(os.environ["OPENVAN_DATA_DIR"])
        if os.environ.get("OPENVAN_AI") is not None:
            cfg.ai_enabled = os.environ["OPENVAN_AI"] not in ("0", "false", "False")
        if os.environ.get("OPENVAN_TELEMETRY") is not None:
            cfg.telemetry_enabled = os.environ["OPENVAN_TELEMETRY"] not in ("0", "false", "False")
        if os.environ.get("OPENVAN_WEATHER") is not None:
            cfg.weather_enabled = os.environ["OPENVAN_WEATHER"] not in ("0", "false", "False")
        if os.environ.get("OPENVAN_MEMORY") is not None:
            cfg.memory_enabled = os.environ["OPENVAN_MEMORY"] not in ("0", "false", "False")
        cfg.connectivity = os.environ.get(
            "OPENVAN_CONNECTIVITY",
            os.environ.get("OPENVAN_DEFAULT_CONNECTIVITY", cfg.connectivity),
        )
        cfg.language = os.environ.get("OPENVAN_LANGUAGE", cfg.language)
        cfg.llm_base_url = os.environ.get("OPENVAN_LLM_URL", cfg.llm_base_url)
        cfg.llm_model = os.environ.get("OPENVAN_LLM_MODEL", cfg.llm_model)
        cfg.online_provider = os.environ.get("OPENVAN_ONLINE_PROVIDER", cfg.online_provider)
        cfg.online_base_url = os.environ.get("OPENVAN_ONLINE_URL", cfg.online_base_url)
        cfg.online_model = os.environ.get("OPENVAN_ONLINE_MODEL", cfg.online_model)
        cfg.online_api_key = os.environ.get("OPENVAN_ONLINE_API_KEY", cfg.online_api_key)
        return cfg
