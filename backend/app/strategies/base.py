"""Declarative strategy contract for the pluggable framework.

A strategy is a self-describing class: it declares its metadata (kind,
params schema, data requirements, warmup), and implements ``on_bar``.
The framework takes care of data feeding, indicator computation,
position sizing, state persistence and order translation.

Adding a new strategy = dropping a new file into ``app/strategies/library/``
and registering it. No changes to the runtime service.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.strategies.signal import Bar, Signal

if TYPE_CHECKING:
    from app.strategies.context import StrategyContext


class DataRequirement(str, Enum):
    TICKER = "ticker"            # realtime ticker snapshot
    KLINE_1M = "kline_1m"
    KLINE_5M = "kline_5m"
    KLINE_15M = "kline_15m"
    KLINE_1H = "kline_1h"
    KLINE_4H = "kline_4h"
    KLINE_1D = "kline_1d"
    ORDERBOOK = "orderbook"


@dataclass(frozen=True)
class ParamSpec:
    """Declaration of a single strategy parameter."""

    name: str
    type: type                   # int / float / str / bool
    default: Any
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""

    def validate(self, raw: Any) -> Any:
        try:
            if self.type is bool:
                if isinstance(raw, str):
                    value = raw.strip().lower() in {"1", "true", "yes", "on"}
                else:
                    value = bool(raw)
            elif self.type is int:
                value = int(Decimal(str(raw)))
            elif self.type is float:
                value = float(raw)
            else:
                value = self.type(raw)
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise ValueError(f"param '{self.name}': cannot convert {raw!r} to {self.type.__name__}") from exc
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.min_value is not None and value < self.min_value:
                raise ValueError(f"param '{self.name}' = {value} < min {self.min_value}")
            if self.max_value is not None and value > self.max_value:
                raise ValueError(f"param '{self.name}' = {value} > max {self.max_value}")
        return value


@dataclass(frozen=True)
class StrategyMeta:
    """Self-description of a strategy, declared as a class attribute."""

    kind: str                                # unique key, e.g. "dual_ma"
    name: str                                # display name
    version: str                             # strategy's own version
    description: str = ""
    params: tuple[ParamSpec, ...] = ()
    data_requirements: frozenset[DataRequirement] = frozenset({DataRequirement.TICKER})
    warmup_bars: int = 0                     # bars required before first on_bar
    symbols: tuple[str, ...] = ()            # default symbols; empty = user-configured


class Strategy(ABC):
    """Base class for all pluggable strategies.

    Subclasses MUST define ``meta`` and implement ``on_bar``.
    Lifecycle hooks ``on_init`` / ``on_fill`` / ``on_stop`` are optional.
    """

    meta: StrategyMeta

    def __init__(self, params: dict[str, Any] | None = None):
        self.p = self.validate_params(params or {})

    # ── parameter handling ────────────────────────────────────────────

    def validate_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate raw params against the declared schema, fill defaults."""
        declared = {spec.name: spec for spec in self.meta.params}
        unknown = set(raw) - set(declared)
        if unknown:
            raise ValueError(f"unknown params for {self.meta.kind}: {sorted(unknown)}")
        validated: dict[str, Any] = {}
        for name, spec in declared.items():
            validated[name] = spec.validate(raw.get(name, spec.default))
        return validated

    @classmethod
    def params_schema(cls) -> list[dict[str, Any]]:
        """Machine-readable schema, usable for auto-generating UI forms."""
        return [
            {
                "name": s.name,
                "type": s.type.__name__,
                "default": s.default,
                "min": s.min_value,
                "max": s.max_value,
                "description": s.description,
            }
            for s in cls.meta.params
        ]

    # ── lifecycle hooks ───────────────────────────────────────────────

    def on_init(self, ctx: "StrategyContext") -> None:
        """Called once when the strategy instance starts."""

    @abstractmethod
    def on_bar(self, ctx: "StrategyContext", bar: Bar) -> list[Signal]:
        """Called on every new bar (and on ticker ticks for ticker-only
        strategies). This is the single entry point shared by backtest,
        paper and live runtimes."""
        ...

    def on_fill(self, ctx: "StrategyContext", fill: dict[str, Any]) -> None:
        """Called when an order generated by this strategy is (partially)
        filled. Use it to update internal state (entry price, grid level...)."""

    def on_stop(self, ctx: "StrategyContext") -> None:
        """Called when the strategy is stopped. Clean up state here."""
