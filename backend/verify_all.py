"""Comprehensive verification of all newly installed modules."""

import sys

ok, fail = [], []


def check(name, fn):
    try:
        fn()
        ok.append(name)
    except Exception as e:  # noqa: BLE001
        fail.append(f"{name}: {e}")


# 1. strategy framework core
check("策略框架导入", lambda: __import__("app.strategies", fromlist=["autodiscover"]))
check("指标引擎导入", lambda: __import__("app.indicators", fromlist=["default_indicator_registry"]))

# 2. new services
check("KlineService导入", lambda: __import__("app.services.kline_service", fromlist=["KlineService"]))
check("告警通知服务导入", lambda: __import__("app.services.alert_notification_service", fromlist=["AlertNotificationService"]))
check("实盘风控服务导入", lambda: __import__("app.services.live_guard_service", fromlist=["LiveGuardService"]))

# 3. API router
check("框架API路由导入", lambda: __import__("app.api.v1.framework", fromlist=["router"]))

# 4. Celery tasks
check("Celery任务导入", lambda: __import__("app.tasks.tasks", fromlist=["refresh_klines"]))

# 5. ORM model
check("历史K线ORM导入", lambda: getattr(__import__("app.db.orm_models", fromlist=["HistoricalKlineModel"]), "HistoricalKlineModel"))


# 6. store integration (new services instantiated)
def store_check():
    from app.db.memory import reset_store, get_store
    reset_store()
    store = get_store()
    assert hasattr(store, "kline_service"), "kline_service missing"
    assert hasattr(store, "alert_notification_service"), "alert service missing"
    assert hasattr(store, "live_guard_service"), "live_guard missing"
    assert hasattr(store, "strategy_states"), "strategy_states missing"
    assert "strategy_states" in store._persisted_fields, "not in persisted_fields"


check("store集成(含新服务)", store_check)


# 7. strategy auto-discovery + instantiation
def strategy_check():
    from app.strategies import autodiscover, registry
    autodiscover()
    assert "dual_ma" in registry.kinds()
    assert "rsi_reversion" in registry.kinds()


check("策略自动发现", strategy_check)

# 8. main app import (router mounting, no circular deps)
check("主应用导入", lambda: __import__("app.main", fromlist=["app"]))

print("=" * 50)
print(f"✅ 通过: {len(ok)}/{len(ok) + len(fail)}")
for n in ok:
    print(f"  ✓ {n}")
if fail:
    print(f"❌ 失败: {len(fail)}")
    for f in fail:
        print(f"  ✗ {f}")
    sys.exit(1)
else:
    print("=" * 50)
    print("🎉 全部模块验证通过，应用可正常初始化")
