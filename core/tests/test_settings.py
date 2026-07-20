"""Runtime settings (Admin UI / API / MCP backend)."""

from __future__ import annotations

import os

import pytest

from openvan_core import build_core
from openvan_core.config import Config, _load_dotenv


def test_load_dotenv_sets_and_never_overrides(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "OPENVAN_TEST_KEY=sk-from-file\n"
        'OPENVAN_TEST_QUOTED="quoted-value"\n'
        "OPENVAN_TEST_EXISTING=from-file\n"
    )
    monkeypatch.delenv("OPENVAN_TEST_KEY", raising=False)
    monkeypatch.delenv("OPENVAN_TEST_QUOTED", raising=False)
    monkeypatch.setenv("OPENVAN_TEST_EXISTING", "from-real-env")

    _load_dotenv(env)

    assert os.environ["OPENVAN_TEST_KEY"] == "sk-from-file"
    assert os.environ["OPENVAN_TEST_QUOTED"] == "quoted-value"
    # A var already present in the real environment is never overridden by .env.
    assert os.environ["OPENVAN_TEST_EXISTING"] == "from-real-env"


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path,
    ))
    await c.start()
    yield c
    await c.stop()


def _cfg(tmp_path, **kw):
    return Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path, **kw,
    )


async def test_settings_persist_across_restart(tmp_path, monkeypatch):
    c1 = build_core(_cfg(tmp_path))
    await c1.start()
    await c1.apply_settings(
        offline_model="llama3.1:8b", simulate=False, online_api_key="secret-key"
    )
    await c1.stop()

    saved = (tmp_path / "settings.json").read_text()
    assert "llama3.1:8b" in saved
    assert "secret-key" not in saved  # API key is never written to disk

    # A fresh resolve() (pointed at the same data dir) restores the choices.
    monkeypatch.setenv("OPENVAN_DATA_DIR", str(tmp_path))
    restored = Config.resolve()
    assert restored.llm_model == "llama3.1:8b"
    assert restored.simulate is False
    assert restored.online_api_key is None


def test_env_overrides_persisted(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text('{"llm_model": "persisted-model"}')
    monkeypatch.setenv("OPENVAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENVAN_LLM_MODEL", "env-model")
    cfg = Config.resolve()
    assert cfg.llm_model == "env-model"  # env wins over the persisted file


async def test_settings_reports_state_and_plugins(core):
    s = core.settings()
    assert s["ai_enabled"] is False
    assert s["assistant"]["llm"] is False
    assert s["simulate"] is True
    assert s["connectivity"] == "offline"
    assert "has_key" in s["online"]
    domains = {p["domain"] for p in s["plugins"]}
    assert {"battery_monitor", "cabin_light", "diesel_heater", "water_system"} <= domains


async def test_change_offline_model_updates_config(core):
    result = await core.apply_settings(offline_model="llama3.1:8b")
    assert result["offline"]["model"] == "llama3.1:8b"
    assert core.config.llm_model == "llama3.1:8b"


async def test_configure_online_endpoint(core):
    result = await core.apply_settings(
        online_base_url="https://api.example/v1",
        online_model="gpt-x",
        online_api_key="secret",
    )
    assert result["online"]["base_url"] == "https://api.example/v1"
    assert result["online"]["model"] == "gpt-x"
    assert result["online"]["has_key"] is True
    # The key itself is never echoed back in settings.
    assert "secret" not in str(result)


async def test_toggle_simulation(core):
    # The tick loop always runs (per-driver sims must tick on a real van —
    # mixed mode); the toggle pauses only the world physics.
    assert core.simulation._task is not None
    assert core.simulation.physics is True
    await core.apply_settings(simulate=False)
    assert core.simulation._task is not None
    assert core.simulation.physics is False
    await core.apply_settings(simulate=True)
    assert core.simulation.physics is True


async def test_settings_changed_event_published(core):
    seen = []

    async def handler(event):
        seen.append(event.data["settings"]["simulate"])

    core.bus.subscribe("settings.changed", handler)
    await core.apply_settings(simulate=False)
    assert seen == [False]
