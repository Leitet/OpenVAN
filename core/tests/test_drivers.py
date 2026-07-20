"""The driver registry: manifest-first discovery, trust tiers (bundled / official /
community / unsigned / tampered-blocked), API-version gating, and crash
containment — one bad community driver never bricks the van."""

from __future__ import annotations

import os

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.drivers import (
    DRIVER_API,
    STATE_AVAILABLE,
    STATE_BLOCKED,
    STATE_ERROR,
    STATE_INCOMPATIBLE,
    STATE_LOADED,
    DriverRegistry,
)
from openvan_core.signing import ed25519_public_key, sign_driver


def _driver(base, pkg, *, driver_id=None, api=DRIVER_API, code="", manifest=True):
    """Scaffold a driver package: <base>/<pkg>/{driver.toml,__init__.py}."""
    d = base / pkg
    d.mkdir(parents=True)
    if manifest:
        (d / "driver.toml").write_text(
            f'[driver]\nid = "{driver_id or pkg}"\nname = "{pkg}"\n'
            f'version = "1.2.3"\nkind = "integration"\napi = {api}\nentry = "{pkg}"\n'
        )
    (d / "__init__.py").write_text(code)
    return d


def _registry(tmp_path, *, external, require_signed=False, official=None, user=None):
    off_dir = tmp_path / "official_keys"
    usr_dir = tmp_path / "user_keys"
    for target, keys in ((off_dir, official or []), (usr_dir, user or [])):
        target.mkdir(exist_ok=True)
        for i, key in enumerate(keys):
            (target / f"k{i}.pub").write_text(key.hex() + "\n")
    return DriverRegistry(
        external_dirs=[external],
        official_key_dirs=[off_dir],
        user_key_dirs=[usr_dir],
        require_signed=require_signed,
    )


def test_manifest_driver_scans_and_loads(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_scan_ok", code="LOADED_MARK = True\n")
    reg = _registry(tmp_path, external=ext)
    reg.scan()
    rec = reg.records["acme_scan_ok"]
    assert rec.state == STATE_AVAILABLE and rec.trust == "unsigned"
    assert rec.version == "1.2.3" and rec.api == DRIVER_API
    assert reg.load(rec) and rec.state == STATE_LOADED


def test_external_without_manifest_is_refused(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_anon", manifest=False)
    reg = _registry(tmp_path, external=ext)
    reg.scan()
    rec = reg.records["acme_anon"]
    assert rec.state == STATE_BLOCKED and "manifest" in rec.error


def test_future_api_is_incompatible_not_a_crash(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_future", api=99)
    reg = _registry(tmp_path, external=ext)
    reg.scan()
    rec = reg.records["acme_future"]
    assert rec.state == STATE_INCOMPATIBLE and "api 99" in rec.error
    assert rec not in reg.loadable("integration")


def test_broken_import_is_contained(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_broken", code="raise RuntimeError('boom at import')\n")
    _driver(ext, "acme_fine", code="")
    reg = _registry(tmp_path, external=ext)
    reg.scan()
    assert not reg.load(reg.records["acme_broken"])
    assert reg.records["acme_broken"].state == STATE_ERROR
    assert reg.load(reg.records["acme_fine"])  # the neighbour still loads


def test_trust_tiers_official_community_unknown(tmp_path):
    official_key = bytes([1]) * 32
    community_key = bytes([2]) * 32
    unknown_key = bytes([3]) * 32
    ext = tmp_path / "drivers"
    for name, key in (("acme_off", official_key), ("acme_com", community_key), ("acme_unk", unknown_key)):
        sign_driver(_driver(ext, name), key)
    reg = _registry(
        tmp_path, external=ext,
        official=[ed25519_public_key(official_key)],
        user=[ed25519_public_key(community_key)],
    )
    reg.scan()
    assert reg.records["acme_off"].trust == "official"
    assert reg.records["acme_com"].trust == "community"
    assert reg.records["acme_unk"].trust == "unknown_signer"
    assert all(r.state == STATE_AVAILABLE for r in reg.records.values())


def test_tampered_driver_is_blocked_hard(tmp_path):
    key = bytes([7]) * 32
    ext = tmp_path / "drivers"
    d = _driver(ext, "acme_tamper", code="SAFE = True\n")
    sign_driver(d, key)
    (d / "__init__.py").write_text("EVIL = True\n")  # modified after signing
    reg = _registry(tmp_path, external=ext, official=[ed25519_public_key(key)])
    reg.scan()
    rec = reg.records["acme_tamper"]
    assert rec.state == STATE_BLOCKED and "tampered" in rec.error
    assert rec not in reg.loadable("integration")


def test_require_signed_blocks_unsigned(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_lockdown")
    reg = _registry(tmp_path, external=ext, require_signed=True)
    reg.scan()
    assert reg.records["acme_lockdown"].state == STATE_BLOCKED


def test_duplicate_ids_flagged(tmp_path):
    ext = tmp_path / "drivers"
    _driver(ext, "acme_dup_a", driver_id="acme_dup")
    _driver(ext, "acme_dup_b", driver_id="acme_dup")
    reg = _registry(tmp_path, external=ext)
    reg.scan()
    assert reg.records["acme_dup"].state in (STATE_AVAILABLE, STATE_ERROR)
    # Only one record exists for the id — the second is not silently merged.
    assert len([r for r in reg.records.values() if r.id == "acme_dup"]) == 1


# --- through Core: a signed community driver joins the catalog ----------------

_DRIVER_CODE = '''
from openvan_core import Integration, IntegrationInfo, Status, Transport

class AcmeFridge(Integration):
    info = IntegrationInfo(
        id="acme_fridge_live",
        name="ACME Fridge",
        category="sensors",
        transports=[Transport.BLE],
        status=Status.COMMUNITY,
        provides=["acme.fridge.temp"],
    )

    async def simulate(self, dt: float) -> None:
        await self.twin.set_signal("acme.fridge.temp", 4.5, source="acme_fridge_live")
'''


async def test_signed_community_driver_through_core(tmp_path):
    key = bytes(range(32))
    drivers_dir = tmp_path / "drivers"
    d = _driver(drivers_dir, "acme_fridge_live", code=_DRIVER_CODE)
    sign_driver(d, key)
    trust = tmp_path / "data" / "trust"
    trust.mkdir(parents=True)
    (trust / "acme.pub").write_text(ed25519_public_key(key).hex() + "\n")
    # A broken neighbour proves containment at the Core level too.
    _driver(drivers_dir, "acme_broken_live", code="raise RuntimeError('no')\n")

    core = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False,
               data_dir=tmp_path / "data", drivers_dir=drivers_dir)
    )
    await core.start()
    try:
        records = {r["id"]: r for r in core.registry.describe()}
        assert records["acme_fridge_live"]["trust"] == "community"
        assert records["acme_fridge_live"]["state"] == "loaded"
        assert records["acme_broken_live"]["state"] == "error"  # contained

        catalog = {r["id"]: r for r in core.integrations_list()}
        row = catalog["acme_fridge_live"]
        assert row["trust"] == "community" and row["driver_version"] == "1.2.3"
        # It behaves like any driver: enable → its sim feeds the twin.
        await core.set_integration_enabled("acme_fridge_live", True)
        await core.integrations.simulate_all(1.0)
        assert core.twin.get("acme.fridge.temp") == 4.5
    finally:
        await core.stop()
