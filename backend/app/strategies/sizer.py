"""Position sizing: turns a Signal's intent into a concrete quantity.

Strategies express *conviction* ("use 20% of cash"), sizers express
*money management* (fixed cash, percent, Kelly, ATR risk). The two are
independently composable and independently testable.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

from app.strategies.signal import Signal, SignalType

if TYPE_CHECKING:
    from app.strategies.context import StrategyContext


class PositionSizer(ABC):
    """Resolves a Signal into a base-asset quantity (Decimal)."""

    @abstractmethod
    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        """Return the quantity to trade. Must be > 0 for the order to proceed."""
        ...


class DefaultSizer(PositionSizer):
    """Framework default: honours exactly what the signal asked for.

    - quantity      → used as-is
    - cash_pct      → pct of available cash / ref_price
    - position_pct  → pct of current position quantity (for reduce/close)
    """

    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        if signal.quantity is not None:
            return signal.quantity

        if signal.cash_pct is not None:
            if ref_price <= 0:
                return Decimal("0")
            cash = ctx.available_cash() * Decimal(str(signal.cash_pct))
            return (cash / ref_price).quantize(Decimal("0.00000001"))

        if signal.position_pct is not None:
            pos = ctx.position(signal.symbol)
            if pos is None:
                return Decimal("0")
            held = Decimal(str(getattr(pos, "quantity", "0")))
            return (held * Decimal(str(signal.position_pct))).quantize(Decimal("0.00000001"))

        return Decimal("0")


class FixedCashSizer(PositionSizer):
    """Always trade a fixed cash amount, regardless of signal sizing."""

    def __init__(self, cash_amount: str):
        self.cash_amount = Decimal(cash_amount)

    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        if signal.type in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            return DefaultSizer().size(signal, ctx, ref_price)
        if ref_price <= 0:
            return Decimal("0")
        return (self.cash_amount / ref_price).quantize(Decimal("0.00000001"))


class PercentCashSizer(PositionSizer):
    """Cap every entry at a fixed fraction of available cash."""

    def __init__(self, pct: float):
        if not (0 < pct <= 1):
            raise ValueError(f"pct must be in (0, 1], got {pct}")
        self.pct = Decimal(str(pct))

    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        if signal.type in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            return DefaultSizer().size(signal, ctx, ref_price)
        if ref_price <= 0:
            return Decimal("0")
        cash = ctx.available_cash() * self.pct
        return (cash / ref_price).quantize(Decimal("0.00000001"))


class KellySizer(PositionSizer):
    """Kelly criterion: f* = p - (1-p)/b, capped by max_pct.

    win_rate and payoff_ratio come from the strategy's own track record
    (or a priori estimates). Conservative in practice: most traders use
    half-Kelly, configurable via ``fraction``.
    """

    def __init__(self, win_rate: float, payoff_ratio: float, fraction: float = 0.5, max_pct: float = 0.25):
        self.win_rate = Decimal(str(win_rate))
        self.payoff = Decimal(str(payoff_ratio))
        self.fraction = Decimal(str(fraction))
        self.max_pct = Decimal(str(max_pct))

    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        if signal.type in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            return DefaultSizer().size(signal, ctx, ref_price)
        if ref_price <= 0 or self.payoff <= 0:
            return Decimal("0")
        kelly = self.win_rate - (Decimal("1") - self.win_rate) / self.payoff
        kelly = max(Decimal("0"), min(kelly * self.fraction, self.max_pct))
        cash = ctx.available_cash() * kelly
        return (cash / ref_price).quantize(Decimal("0.00000001"))


class AtrRiskSizer(PositionSizer):
    """Volatility-based sizing (Turtle-style): risk a fixed % of equity
    per trade, with the stop distance derived from ATR.

    quantity = (equity * risk_pct) / (atr * atr_mult)
    """

    def __init__(self, risk_pct: float = 0.01, atr_mult: float = 2.0):
        self.risk_pct = Decimal(str(risk_pct))
        self.atr_mult = Decimal(str(atr_mult))

    def size(self, signal: Signal, ctx: "StrategyContext", ref_price: Decimal) -> Decimal:
        if signal.type in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            return DefaultSizer().size(signal, ctx, ref_price)
        atr = ctx.indicator("atr", signal.symbol, length=14)
        if atr is None or atr <= 0:
            return Decimal("0")
        risk_cash = ctx.portfolio_value() * self.risk_pct
        stop_distance = Decimal(str(atr)) * self.atr_mult
        return (risk_cash / stop_distance).quantize(Decimal("0.00000001"))
