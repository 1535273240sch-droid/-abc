#!/usr/bin/env python3
"""One-shot installer: wires KlineService + strategy framework into the app.

Idempotent — safe to run multiple times; each edit is applied only when
its anchor is found and the target content is not already present.
"""

import re
from pathlib import Path

ROOT = Path("/home/ubuntu/backend")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, content: str) -> None:
    p.write_text(content, encoding="utf-8")


def append_once(path: Path, marker: str, block: str) -> str:
    """Append block to file if marker (unique block signature) not present."""
    content = read(path)
    if marker in content:
        return f"SKIP (already present): {path.name}"
    if not content.endswith("\n"):
        content += "\n"
    write(path, content + block)
    return f"OK (appended): {path.name}"


def insert_after_once(path: Path, anchor: str, block: str, marker: str) -> str:
    """Insert block after the first line containing anchor, once."""
    content = read(path)
    if marker in content:
        return f"SKIP (already present): {path.name}"
    if anchor not in content:
        return f"WARN (anchor not found): {path.name} :: {anchor[:50]}"
    new = content.replace(anchor, anchor + block, 1)
    write(path, new)
    return f"OK (inserted): {path.name}"


results = []

# ── 1. ORM: HistoricalKlineModel ──────────────────────────────────────

orm_path = ROOT / "app/db/orm_models.py"
kline_model = '''

# ─────────────────── Historical Klines ───────────────────

class HistoricalKlineModel(Base):
    __tablename__ = "historical_klines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[str] = mapped_column(String(64), nullable=False)
    high: Mapped[str] = mapped_column(String(64), nullable=False)
    low: Mapped[str] = mapped_column(String(64), nullable=False)
    close: Mapped[str] = mapped_column(String(64), nullable=False)
    volume: Mapped[str] = mapped_column(String(64), nullable=False)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("symbol", "period", "open_time", name="uq_kline_symbol_period_time"),
        Index("ix_kline_symbol_period_time", "symbol", "period", "open_time"),
    )
'''
results.append(append_once(orm_path, "HistoricalKlineModel", kline_model))

# ── 2. memory.py: integrate KlineService ──────────────────────────────

mem_path = ROOT / "app/db/memory.py"
mem = read(mem_path)

# 2a. add import (after the last service import block)
if "kline_service" not in mem:
    # insert import near other service imports
    import_block = "from app.services.kline_service import KlineService\n"
    # place after market_service import if present, else at top of services imports
    m = re.search(r"(from app\.services\.market_service import MarketService\n)", mem)
    if m:
        mem = mem.replace(m.group(1), m.group(1) + import_block, 1)
    else:
        # fallback: after 'from app.services.' first occurrence
        idx = mem.find("from app.services.")
        if idx != -1:
            line_end = mem.find("\n", idx) + 1
            mem = mem[:line_end] + import_block + mem[line_end:]
    write(mem_path, mem)
    results.append("OK (import added): memory.py")
else:
    results.append("SKIP (import present): memory.py")

mem = read(mem_path)

# 2b. instantiate kline_service after risk_service init
if "self.kline_service = KlineService" not in mem:
    anchor = "        self.risk_service = RiskService(self)\n"
    block = "        self.kline_service = KlineService()\n"
    if anchor in mem:
        mem = mem.replace(anchor, anchor + block, 1)
        write(mem_path, mem)
        results.append("OK (kline_service init): memory.py")
    else:
        results.append("WARN (risk_service anchor not found): memory.py")
else:
    results.append("SKIP (kline_service init present): memory.py")

# ── 3. strategy state persistence field ───────────────────────────────

mem = read(mem_path)
if "strategy_states" not in mem:
    # add dict field near other store dicts; find a stable anchor
    anchor = None
    for cand in [
        "        self.strategy_runs",
        "        self.strategies",
        "        self.positions",
    ]:
        if cand in mem:
            anchor = cand
            break
    if anchor:
        line_end = mem.find("\n", mem.find(anchor)) + 1
        block = "        self.strategy_states: dict = {}\n"
        mem = mem[:line_end] + block + mem[line_end:]
        write(mem_path, mem)
        results.append("OK (strategy_states field): memory.py")
    else:
        results.append("WARN (no field anchor found): memory.py")
else:
    results.append("SKIP (strategy_states present): memory.py")

# add to _persisted_fields list
mem = read(mem_path)
if '"strategy_states"' not in mem and "'strategy_states'" not in mem:
    m = re.search(r"(self\._persisted_fields\s*=\s*\[)([^\]]*)(\])", mem, re.DOTALL)
    if m:
        items = m.group(2)
        # append before closing bracket, keeping formatting
        new_items = items.rstrip()
        if new_items and not new_items.endswith(","):
            new_items += ","
        new_items += '\n            "strategy_states",\n        '
        mem = mem[: m.start(2)] + new_items + mem[m.end(2):]
        write(mem_path, mem)
        results.append("OK (persisted_fields += strategy_states): memory.py")
    else:
        results.append("WARN (persisted_fields not found): memory.py")
else:
    results.append("SKIP (strategy_states in persisted_fields): memory.py")

print("\n".join(results))
print("\n=== INSTALL COMPLETE ===")
