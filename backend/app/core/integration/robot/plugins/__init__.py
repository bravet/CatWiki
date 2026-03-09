from __future__ import annotations

import importlib

from app.core.infra.config import settings

BUILTIN_PLUGINS = [
    "wecom_kefu",
    "wecom_app",
]


def load_plugins(providers: list[str] | None = None) -> None:
    allowlist = list(settings.ROBOT_PLUGIN_ALLOWLIST or [])
    if allowlist:
        providers = [p for p in allowlist if p in BUILTIN_PLUGINS]
    providers = providers or BUILTIN_PLUGINS
    for provider in providers:
        importlib.import_module(f"app.core.integration.robot.plugins.builtin.{provider}")


def load_market_plugins(providers: list[str]) -> None:
    for provider in providers:
        importlib.import_module(f"app.core.integration.robot.plugins.market.{provider}")
