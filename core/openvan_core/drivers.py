"""The driver registry — how third-party code joins OpenVan safely.

OpenVan is built to grow an ecosystem: anyone can write a **driver** (an
integration, plugin or camp source) for whatever hardware or software they care
about, drop it in a driver directory, and the van picks it up. The core stays
small; everything at the edges is a driver. That only works if the loading layer
is paranoid on the core's behalf:

* **Manifest-first.** Every driver ships a ``driver.toml`` declaring its identity
  (id, name, version), its ``kind`` and its ``api`` level — readable *without
  importing any code* (stdlib ``tomllib``). No manifest? Bundled repo dirs get an
  implicit record (they ship with core); anything else is refused: unidentified
  third-party code doesn't load.
* **API versioning.** Core exposes ``DRIVER_API``; a driver declaring an
  unsupported level is listed as *incompatible* — clearly, instead of exploding
  at import time three releases later.
* **Signing & trust** (``signing.py``): the store signs official drivers, users
  can trust additional publisher keys, and unsigned drivers are allowed (your
  van, your call — flagged clearly, or refused entirely with
  ``require_signed``). The one hard rule: a package whose signature no longer
  matches its contents (**tampered**) never loads.
* **Containment.** A driver that fails to import or set up becomes an ``error``
  record — core keeps running, the catalog shows what broke. One bad community
  driver must never brick the van.

Drivers still run in-process with full access once loaded — that's Python. The
trust tiers exist so the *user* makes that call with honest information, exactly
like the integration catalog's status/safety badges.
"""

from __future__ import annotations

import logging
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .signing import verify_driver

logger = logging.getLogger(__name__)

# The driver API level this core supports. Bump on breaking changes to the
# Plugin/Integration/CampSource contracts; support ranges when it grows.
DRIVER_API = 1
SUPPORTED_APIS = {1}

MANIFEST = "driver.toml"
KINDS = {"integration", "plugin", "campsource"}

# Trust tiers, most to least trusted.
TRUST_BUNDLED = "bundled"          # ships inside the core repo
TRUST_OFFICIAL = "official"        # signed by an OpenVan store key
TRUST_COMMUNITY = "community"      # signed by a key the user chose to trust
TRUST_UNKNOWN_SIGNER = "unknown_signer"  # valid signature, unrecognised key
TRUST_UNSIGNED = "unsigned"        # no signature

# States
STATE_AVAILABLE = "available"
STATE_LOADED = "loaded"
STATE_BLOCKED = "blocked"          # tampered, or unsigned under require_signed
STATE_INCOMPATIBLE = "incompatible"
STATE_ERROR = "error"


@dataclass
class DriverRecord:
    id: str
    kind: str
    path: Path
    name: str = ""
    version: str = "0.0.0"
    api: int = DRIVER_API
    entry: str = ""
    trust: str = TRUST_UNSIGNED
    state: str = STATE_AVAILABLE
    error: str = ""
    signer: str = ""  # hex public key when signed
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name or self.id,
            "version": self.version,
            "api": self.api,
            "trust": self.trust,
            "state": self.state,
            "error": self.error,
            "signer": self.signer,
        }


def _load_keys(paths: list[Path]) -> set[bytes]:
    keys: set[bytes] = set()
    for base in paths:
        if not base.is_dir():
            continue
        for f in sorted(base.glob("*.pub")):
            try:
                keys.add(bytes.fromhex(f.read_text().strip()))
            except ValueError:
                logger.warning("ignoring malformed trust key %s", f)
    return keys


class DriverRegistry:
    """Scans driver directories into records and loads them with containment."""

    def __init__(
        self,
        *,
        bundled_dirs: list[Path] | None = None,
        external_dirs: list[Path] | None = None,
        official_key_dirs: list[Path] | None = None,
        user_key_dirs: list[Path] | None = None,
        require_signed: bool = False,
    ) -> None:
        self.bundled_dirs = [Path(p) for p in (bundled_dirs or [])]
        self.external_dirs = [Path(p) for p in (external_dirs or [])]
        self.require_signed = require_signed
        self.official_keys = _load_keys(official_key_dirs or [])
        self.user_keys = _load_keys(user_key_dirs or [])
        self.records: dict[str, DriverRecord] = {}

    # --- scanning ---------------------------------------------------------

    def scan(self) -> list[DriverRecord]:
        self.records = {}
        for base in self.bundled_dirs:
            self._scan_dir(base, bundled=True)
        for base in self.external_dirs:
            self._scan_dir(base, bundled=False)
        return list(self.records.values())

    def _scan_dir(self, base: Path, *, bundled: bool) -> None:
        if not base.is_dir():
            return
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            record = self._record_for(child, bundled=bundled)
            if record is None:
                continue
            if record.id in self.records:
                record.state = STATE_ERROR
                record.error = f"duplicate driver id '{record.id}'"
            self.records.setdefault(record.id, record)

    def _record_for(self, path: Path, *, bundled: bool) -> DriverRecord | None:
        manifest = path / MANIFEST
        if manifest.is_file():
            try:
                data = tomllib.loads(manifest.read_text())["driver"]
                record = DriverRecord(
                    id=str(data["id"]),
                    kind=str(data.get("kind", "integration")),
                    path=path,
                    name=str(data.get("name", data["id"])),
                    version=str(data.get("version", "0.0.0")),
                    api=int(data.get("api", 0)),
                    entry=str(data.get("entry", path.name)),
                )
            except (tomllib.TOMLDecodeError, KeyError, ValueError, TypeError) as exc:
                record = DriverRecord(id=path.name, kind="integration", path=path)
                record.state = STATE_ERROR
                record.error = f"invalid {MANIFEST}: {exc}"
                return record
        elif bundled and (path / "__init__.py").exists():
            # Legacy bundled package without a manifest — it ships with core.
            record = DriverRecord(
                id=path.name, kind="integration", path=path, entry=path.name, api=DRIVER_API
            )
        elif (path / "__init__.py").exists():
            # Third-party code without identity: refuse to touch it.
            record = DriverRecord(id=path.name, kind="integration", path=path)
            record.state = STATE_BLOCKED
            record.error = f"no {MANIFEST} — external drivers must declare a manifest"
            return record
        else:
            return None

        if record.kind not in KINDS:
            record.state = STATE_ERROR
            record.error = f"unknown driver kind '{record.kind}'"
            return record
        if record.api not in SUPPORTED_APIS:
            record.state = STATE_INCOMPATIBLE
            record.error = (
                f"driver api {record.api} not supported by this core (supports {sorted(SUPPORTED_APIS)})"
            )
            return record

        self._evaluate_trust(record, bundled=bundled)
        return record

    def _evaluate_trust(self, record: DriverRecord, *, bundled: bool) -> None:
        ok, public = verify_driver(record.path)
        if public is not None:
            record.signer = public.hex()
            if not ok:
                # Signed then modified — the one thing that must never run.
                record.state = STATE_BLOCKED
                record.error = "signature does not match contents (tampered)"
                record.trust = TRUST_UNSIGNED
                return
            if public in self.official_keys:
                record.trust = TRUST_OFFICIAL
            elif public in self.user_keys:
                record.trust = TRUST_COMMUNITY
            else:
                record.trust = TRUST_UNKNOWN_SIGNER
        elif bundled:
            record.trust = TRUST_BUNDLED
        else:
            record.trust = TRUST_UNSIGNED

        if self.require_signed and record.trust in (TRUST_UNSIGNED, TRUST_UNKNOWN_SIGNER):
            record.state = STATE_BLOCKED
            record.error = "unsigned drivers are disabled (require_signed)"

    # --- loading ----------------------------------------------------------

    def loadable(self, kind: str) -> list[DriverRecord]:
        return [r for r in self.records.values() if r.kind == kind and r.state == STATE_AVAILABLE]

    def load(self, record: DriverRecord) -> bool:
        """Import the driver's entry package, containing any failure."""
        import importlib

        parent = str(record.path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        try:
            importlib.import_module(record.entry)
        except Exception as exc:
            record.state = STATE_ERROR
            record.error = f"import failed: {exc}"
            logger.exception("driver %s failed to import", record.id)
            return False
        record.state = STATE_LOADED
        return True

    def mark_error(self, driver_id: str, message: str) -> None:
        record = self.records.get(driver_id)
        if record is not None:
            record.state = STATE_ERROR
            record.error = message

    def describe(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in sorted(self.records.values(), key=lambda r: r.id)]
