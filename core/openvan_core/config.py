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

_CORE_DIR = Path(__file__).resolve().parent.parent  # .../core
_REPO_ROOT = _CORE_DIR.parent  # repo root

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
)


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
            "cabin_light.on": False,
            "diesel_heater.on": False,
            "diesel_heater.setpoint": 20.0,
            "diesel_heater.power": 0.0,
            "diesel_tank.level_pct": 70.0,
            # Vehicle / GPS — starting parked in the Dolomites.
            "gps.lat": 46.5405,
            "gps.lon": 11.6553,
            "vehicle.speed_kmh": 0.0,
            "vehicle.heading": 90.0,
            "vehicle.odometer_km": 48210.0,
            "vehicle.ignition": False,
            "vehicle.trip_seconds": 0.0,
        }
    )

    # --- persistence -----------------------------------------------------
    def persistable(self) -> dict:
        """The runtime-changeable settings that survive a restart (no API key)."""
        return {f: getattr(self, f) for f in _PERSISTED_FIELDS}

    def apply(self, data: dict) -> None:
        for f in _PERSISTED_FIELDS:
            if f in data and data[f] is not None:
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
