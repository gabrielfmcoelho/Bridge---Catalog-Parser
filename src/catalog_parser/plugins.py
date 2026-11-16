"""Plugin loader: registers custom rules, catalog kinds, reporters, or remote providers.

Plugins can be discovered from installed distribution entry points (`group="catalog_parser.plugins"`)
or listed explicitly in `.catalog-parser.toml` under `[rules] plugins = ["pkg.module:register"]`.

A plugin callable may accept `(registry, reporters)` or `(registry,)`. A module without `:callable`
must define a `register(...)` function.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
from collections.abc import Callable, Iterable
from typing import Any

from .config import ConfigError
from .kinds import DEPENDENCIES, CatalogKind, KindRegistry
from .reporters import REPORTERS, Reporter
from .rules.base import CrossRule, FileRule, Rule


def _invoke_plugin(target: Any, registry: KindRegistry, reporters: dict[str, type[Reporter]]) -> None:
    if isinstance(target, CatalogKind):
        registry.register(target, replace=True)
        return
    if isinstance(target, type) and issubclass(target, Rule):
        target = target()
    if isinstance(target, FileRule):
        deps = registry.get(DEPENDENCIES.filename) or DEPENDENCIES
        if target.code not in {r.code for r in deps.file_rules}:
            updated = CatalogKind(deps.filename, deps.model, (*deps.file_rules, target), deps.cross_rules)
            registry.register(updated, replace=True)
        return
    if isinstance(target, CrossRule):
        deps = registry.get(DEPENDENCIES.filename) or DEPENDENCIES
        if target.code not in {r.code for r in deps.cross_rules}:
            updated = CatalogKind(deps.filename, deps.model, deps.file_rules, (*deps.cross_rules, target))
            registry.register(updated, replace=True)
        return
    if not callable(target):
        raise ConfigError(f"plugin '{target}' is not callable")
    sig = inspect.signature(target)
    params = [
        p for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    if has_varargs or len(params) >= 2:
        target(registry, reporters)
    elif len(params) == 1:
        target(registry)
    else:
        target()


def load_plugin_spec(
    spec: str,
    registry: KindRegistry,
    reporters: dict[str, type[Reporter]] | None = None,
) -> None:
    """Load one plugin from `'module.path'` or `'module.path:attribute'`."""
    active_reporters = REPORTERS if reporters is None else reporters
    mod_name, _, attr_name = spec.partition(":")
    attr_name = attr_name or "register"
    try:
        module = importlib.import_module(mod_name)
    except ImportError as e:
        raise ConfigError(f"cannot import plugin '{spec}': {e}") from e
    if not hasattr(module, attr_name):
        raise ConfigError(f"plugin '{spec}' has no attribute '{attr_name}'")
    _invoke_plugin(getattr(module, attr_name), registry, active_reporters)


def load_plugins(
    registry: KindRegistry,
    specs: Iterable[str] = (),
    reporters: dict[str, type[Reporter]] | None = None,
    include_entry_points: bool = True,
) -> KindRegistry:
    """Load installed `catalog_parser.plugins` entry points and explicit plugin specs into `registry`."""
    active_reporters = REPORTERS if reporters is None else reporters
    if include_entry_points:
        for ep in importlib.metadata.entry_points(group="catalog_parser.plugins"):
            target = ep.load()
            _invoke_plugin(target, registry, active_reporters)
    for spec in specs:
        load_plugin_spec(spec, registry, active_reporters)
    return registry
