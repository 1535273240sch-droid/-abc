"""Trading signal system for the pluggable strategy framework.

Replaces the legacy buy/sell/hold tri-state with rich order intents:
open/close/add/reduce positions, stop-loss and take-profit orders.

Strategies express *what they want* (e.g. "open long with 20% of cash"),
the framework (PositionSizer + OrderService) translates it into concrete
quantities and orders.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class SignalType(str, Enum):
    OPEN_LONG = "open_long"          # 开多
    CLOSE_LONG = "close_long"        # 平多（全部）
    ADD_LONG = "add_long"            # 加多
    REDUCE_LONG = "reduce_long"      # 减多（部分止盈/减仓）
    STOP_LOSS = "stop_loss"          # 止损单
    TAKE_PROFIT = "take_profit"      # 止盈单
    CANCEL_ALL = "cancel_all"        # 撤销该 symbol 全部挂单


@dataclass(frozen=True)
class Signal:
    """A single trading intent produced by a strategy.

    Quantity is expressed in exactly one of three ways; the framework's
    PositionSizer resolves it into a concrete Decimal quantity:

    - ``quantity``:      absolute amount in base asset (e.g. 0.01 BTC)
    - ``cash_pct``:      fraction of available cash to spend (0.0-1.0)
    - ``position_pct``:  fraction of current position to close/reduce (0.0-1.0)
    """

    type: SignalType
    symbol: str
    reason: str = ""                     # human-readable trigger reason (for audit/replay)

    quantity: Decimal | None = None
    cash_pct: float | None = None
    position_pct: float | None = None

    limit_price: Decimal | None = None   # None = market order
    trigger_price: Decimal | None = None # for STOP_LOSS / TAKE_PROFIT
    tag: str = ""                        # strategy-defined label (e.g. grid level id)

    def __post_init__(self) -> None:
        sizing = [self.quantity is not None, self.cash_pct is not None, self.position_pct is not None]
        if self.type in (SignalType.CANCEL_ALL,):
            return  # no sizing needed
        if sum(sizing) != 1:
            raise ValueError(
                f"Signal must specify exactly one of quantity/cash_pct/position_pct, got {sizing}"
            )
        if self.cash_pct is not None and not (0 < self.cash_pct <= 1):
            raise ValueError(f"cash_pct must be in (0, 1], got {self.cash_pct}")
        if self.position_pct is not None and not (0 < self.position_pct <= 1):
            raise ValueError(f"position_pct must be in (0, 1], got {self.position_pct}")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")


@dataclass(frozen=True)
class Bar:
    """A single OHLCV candlestick bar."""

    symbol: str
    open_time: int          # unix ms
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: int = 0     # unix ms

    @classmethod
    def from_list(cls, symbol: str, row: list) -> "Bar":
        """Build from a Binance-style kline array:
        [open_time, open, high, low, close, volume, close_time, ...]
        """
        return cls(
            symbol=symbol,
            open_time=int(row[0]),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            close_time=int(row[6]) if len(row) > 6 else 0,
        )
