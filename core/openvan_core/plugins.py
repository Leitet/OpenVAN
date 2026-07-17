"""Plugin system.

Everything that touches the van — sensors, lights, heaters, water, batteries,
navigation — is a plugin. A plugin declares a ``domain`` and one or more
``categories`` (e.g. "lighting", "climate", "energy"), then registers entities
on the hub during ``async_setup``.

Plugins receive a :class:`~openvan_core.backends.Backend`, never raw hardware,
so every plugin runs against the simulator by construction.

Discovery is directory-based for the monorepo: each folder under ``plugins/``
that contains an ``__init__.py`` defining a :class:`Plugin` subclass is loaded.
Subclasses self-register via ``__init_subclass__``.
"""

from __future__ import annotations

import importlib
import logging
import sys
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .backends import Backend

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub

logger = logging.getLogger(__name__)

_REGISTRY: list[type["Plugin"]] = []


def registered_plugins() -> list[type["Plugin"]]:
    return list(_REGISTRY)


def clear_registry() -> None:
    """Test helper — the registry is process-global."""
    _REGISTRY.clear()


class Plugin(ABC):
    domain: str = ""
    name: str = ""
    version: str = "0.0.0"
    categories: list[str] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "domain", ""):
            _REGISTRY.append(cls)

    def __init__(self, hub: "Hub", backend: Backend, config: dict[str, Any] | None = None):
        self.hub = hub
        self.backend = backend
        self.config = config or {}

    async def async_setup(self) -> None:
        """Register entities and subscribe to backend signals."""

    async def async_teardown(self) -> None:
        """Release resources (unwatch signals, close connections)."""


class PluginManager:
    def __init__(self, hub: "Hub", backend: Backend) -> None:
        self.hub = hub
        self.backend = backend
        self.plugins: list[Plugin] = []

    def get(self, domain: str) -> "Plugin | None":
        return next((p for p in self.plugins if p.domain == domain), None)

    def discover(self, plugins_dir: Path | str) -> None:
        plugins_dir = Path(plugins_dir)
        if not plugins_dir.is_dir():
            logger.warning("plugins directory %s does not exist", plugins_dir)
            return
        if str(plugins_dir) not in sys.path:
            sys.path.insert(0, str(plugins_dir))
        for child in sorted(plugins_dir.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                logger.info("loading plugin package: %s", child.name)
                importlib.import_module(child.name)

    async def setup_all(self, configs: dict[str, dict[str, Any]] | None = None) -> None:
        configs = configs or {}
        for plugin_cls in registered_plugins():
            instance = plugin_cls(self.hub, self.backend, configs.get(plugin_cls.domain))
            await instance.async_setup()
            self.plugins.append(instance)
            logger.info("plugin ready: %s (%s)", plugin_cls.name or plugin_cls.domain, plugin_cls.domain)

    async def teardown_all(self) -> None:
        for instance in reversed(self.plugins):
            await instance.async_teardown()
        self.plugins.clear()
