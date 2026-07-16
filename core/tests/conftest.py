"""Shared pytest setup."""

from __future__ import annotations

import os

# Isolate the test suite from the repo's real `.env` (which may hold a developer's
# API key). Point Core's .env loader at an empty device so no ambient secrets or
# overrides leak into tests. Set before any test imports Core config.
os.environ.setdefault("OPENVAN_ENV_FILE", os.devnull)
