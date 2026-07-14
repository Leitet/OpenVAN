"""Runtime configuration for OpenVan Core.

Kept deliberately small and env-driven (offline-first: sensible defaults, no
config server required). ``plugins_dir`` defaults to the monorepo ``plugins/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent.parent  # .../core
_REPO_ROOT = _CORE_DIR.parent  # repo root


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
    # Local, model-agnostic AI assistant (Ollama by default). Optional: if the
    # model is unreachable, OpenVan falls back to the offline rule-based resolver.
    ai_enabled: bool = True
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "llama3.2"
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
        }
    )

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        cfg.host = os.environ.get("OPENVAN_HOST", cfg.host)
        cfg.port = int(os.environ.get("OPENVAN_PORT", cfg.port))
        if os.environ.get("OPENVAN_PLUGINS_DIR"):
            cfg.plugins_dir = Path(os.environ["OPENVAN_PLUGINS_DIR"])
        if os.environ.get("OPENVAN_DATA_DIR"):
            cfg.data_dir = Path(os.environ["OPENVAN_DATA_DIR"])
        if os.environ.get("OPENVAN_AI") is not None:
            cfg.ai_enabled = os.environ["OPENVAN_AI"] not in ("0", "false", "False")
        cfg.llm_base_url = os.environ.get("OPENVAN_LLM_URL", cfg.llm_base_url)
        cfg.llm_model = os.environ.get("OPENVAN_LLM_MODEL", cfg.llm_model)
        return cfg
