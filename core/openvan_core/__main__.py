"""Run OpenVan Core: ``python -m openvan_core``."""

from __future__ import annotations

import logging

import uvicorn

from .api import build_app
from .config import Config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = Config.resolve()
    app = build_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
