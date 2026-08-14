"""Strategy registry: kind → Strategy class, with auto-discovery.

Strategies self-register via the ``@register_strategy`` decorator, or are
registered explicitly. ``autodiscover()`` imports every module under
``app.strategies.library`` so dropping a new file there is enough to make
the strategy available — true plug-and-play.
"""

import importlib
import pkgutil
from typing import Any

from app.strategies.base import Strategy, StrategyMeta


class StrategyRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[Strategy]] = {}

    def register(self, cls: type[Strategy]) -> type[Strategy]:
        kind = cls.meta.kind
        if not kind:
            raise ValueError(f"{cls.__name__}.meta.kind must be non-empty")
        if kind in self._classes:
            raise ValueError(f"duplicate strategy kind '{kind}' ({self._classes[kind].__name__} vs {cls.__name__})")
        self._classes[kind] = cls
        return cls

    def get(self, kind: str) -> type[Strategy] | None:
        return self._classes.get(kind)

    def create(self, kind: str, params: dict[str, Any] | None = None) -> Strategy:
        cls = self._classes.get(kind)
        if cls is None:
            raise KeyError(f"unknown strategy kind '{kind}', registered: {self.kinds()}")
        return cls(params)

    def kinds(self) -> list[str]:
        return sorted(self._classes)

    def catalog(self) -> list[dict[str, Any]]:
        """Metadata + param schema for every registered strategy.

        Powers 'strategy marketplace' UIs: list available strategies,
        render auto-generated parameter forms from the schema.
        """
        out = []
        for kind in self.kinds():
            cls = self._classes[kind]
            meta: StrategyMeta = cls.meta
            out.append({
                "kind": meta.kind,
                "name": meta.name,
                "version": meta.version,
                "description": meta.description,
                "params": cls.params_schema(),
                "data_requirements": sorted(r.value for r in meta.data_requirements),
                "warmup_bars": meta.warmup_bars,
                "symbols": list(meta.symbols),
            })
        return out


# Module-level default registry shared by the app.
registry = StrategyRegistry()


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    """Decorator: @register_strategy on a Strategy subclass."""
    return registry.register(cls)


def autodiscover(package: str = "app.strategies.library") -> list[str]:
    """Import every module in the strategy library package, causing their
    ``@register_strategy`` decorators to fire. Returns imported module names."""
    imported: list[str] = []
    pkg = importlib.import_module(package)
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"{package}.{info.name}")
        imported.append(info.name)
    return imported
