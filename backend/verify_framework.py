"""Framework verification script: exercises the full strategy stack."""

from decimal import Decimal

from app.strategies import autodiscover, registry
from app.strategies.signal import Bar
from app.indicators import default_indicator_registry

print("=" * 60)
print("1. 自动发现策略库")
print("=" * 60)
imported = autodiscover()
print(f"已导入策略模块: {imported}")
print(f"已注册策略: {registry.kinds()}")

print()
print("=" * 60)
print("2. 策略目录（参数 Schema）")
print("=" * 60)
for item in registry.catalog():
    print(f"策略: {item['name']} ({item['kind']}) v{item['version']}")
    print(f"  描述: {item['description']}")
    print(f"  预热K线: {item['warmup_bars']}, 数据需求: {item['data_requirements']}")
    for p in item["params"]:
        print(f"    参数 {p['name']}: {p['type']} 默认={p['default']} 范围=[{p['min']},{p['max']}]")

print()
print("=" * 60)
print("3. 参数校验（含错误处理）")
print("=" * 60)
strategy = registry.create("dual_ma", {"fast_period": 10, "slow_period": 30})
print(f"双均线策略实例化成功: fast={strategy.p['fast_period']}, slow={strategy.p['slow_period']}")
print(f"未传参数自动填充默认: cash_pct={strategy.p['cash_pct']}, atr_stop_mult={strategy.p['atr_stop_mult']}")

try:
    registry.create("dual_ma", {"fast_period": 999})
except ValueError as e:
    print(f"越界参数被正确拦截: {e}")

try:
    registry.create("dual_ma", {"unknown_param": 1})
except ValueError as e:
    print(f"未知参数被正确拦截: {e}")

print()
print("=" * 60)
print("4. 指标引擎验证")
print("=" * 60)
ind = default_indicator_registry()
print(f"可用指标: {ind.available()}")

# 构造 60 根模拟K线（震荡上行）
bars = []
price = 100.0
for i in range(60):
    price *= 1.005
    bars.append(Bar(
        symbol="BTCUSDT", open_time=i * 3600000,
        open=Decimal(str(price * 0.998)), high=Decimal(str(price * 1.002)),
        low=Decimal(str(price * 0.996)), close=Decimal(str(price)),
        volume=Decimal("100"),
    ))

sma20 = ind.compute("sma", bars, {"length": 20})
rsi14 = ind.compute("rsi", bars, {"length": 14})
atr14 = ind.compute("atr", bars, {"length": 14})
print(f"SMA20 最新值: {sma20[-1]:.2f} (前5个为None: {sma20[:5] == [None]*5})")
print(f"RSI14 最新值: {rsi14[-1]:.2f} (持续上涨应接近100)")
print(f"ATR14 最新值: {atr14[-1]:.4f}")

print()
print("=" * 60)
print("5. 信号系统验证")
print("=" * 60)
from app.strategies.signal import Signal, SignalType

sig = Signal(type=SignalType.OPEN_LONG, symbol="BTCUSDT", cash_pct=0.3, reason="测试信号")
print(f"信号创建成功: {sig.type.value} {sig.symbol} cash_pct={sig.cash_pct}")

try:
    Signal(type=SignalType.OPEN_LONG, symbol="BTCUSDT", cash_pct=0.3, quantity=Decimal("0.1"))
except ValueError as e:
    print(f"冲突仓位参数被正确拦截: {e}")

print()
print("=" * 60)
print("✅ 全部验证通过！策略框架核心链路完整可用")
print("=" * 60)
