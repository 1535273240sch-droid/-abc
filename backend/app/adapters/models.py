"""Standardized adapter data models.

These are the canonical representation that upper layers consume.
No exchange-private fields leak through these models.
"""

from app.adapters.protocol import (
    AdapterConnectionStatus,
    AdapterHealth,
    AdapterOrderStatus,
    OrderResult,
    StandardSymbol,
    StandardTicker,
    utcnow,
)

__all__ = [
    "AdapterConnectionStatus",
    "AdapterHealth",
    "AdapterOrderStatus",
    "OrderResult",
    "StandardSymbol",
    "StandardTicker",
    "utcnow",
]