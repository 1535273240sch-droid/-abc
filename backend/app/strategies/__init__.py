"""Pluggable strategy framework.

Public API:
- Strategy / StrategyMeta / ParamSpec / DataRequirement  (contract)
- Signal / SignalType / Bar                              (intents & data)
- StrategyContext                                        (runtime facade)
- PositionSizer and implementations                      (money management)
- registry / register_strategy / autodiscover            (plug-and-play)
"""

from app.strategies.base import (
    DataRequirement,
    ParamSpec,
    Strategy,
    StrategyMeta,
)
from app.strategies.context import StrategyContext
from app.strategies.registry import autodiscover, register_strategy, registry
from app.strategies.signal import Bar, Signal, SignalType
from app.strategies.sizer import (
    AtrRiskSizer,
    DefaultSizer,
    FixedCashSizer,
    KellySizer,
    PercentCashSizer,
    PositionSizer,
)

__all__ = [
    "DataRequirement",
    "ParamSpec",
    "Strategy",
    "StrategyMeta",
    "StrategyContext",
    "Bar",
    "Signal",
    "SignalType",
    "PositionSizer",
    "DefaultSizer",
    "FixedCashSizer",
    "PercentCashSizer",
    "KellySizer",
    "AtrRiskSizer",
    "registry",
    "register_strategy",
    "autodiscover",
]
