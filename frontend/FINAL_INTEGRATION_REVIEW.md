# 前后端接口集成审计报告

> 审计人：后端工程 Agent（OpenCode / DeepSeek）
> 日期：2026-08-09
> 范围：`backend/app/api` 路由与模型 ↔ `frontend/src/api.ts`、`frontend/src/types.ts`、`frontend/src/mockData.ts` 及全部页面
> 约束：本报告不允许修改任何业务源码，仅新增/更新本文件。

---

## 1. 审计结论

1. **后端路由与前端 `api.ts` 契约完全一致。** `api.ts` 中 11 个方法（health/ready/systemStatus/symbols/tickers/preflight/createOrderIntent/orders/positions/strategies/auditEvents）的路径、HTTP 方法与后端路由逐一对齐，字段均为 snake_case，与后端返回一致。
2. **风控前置检查已真实接入后端（唯一接线点）。** `Risk.tsx` 通过 `api.preflight()` + `toRiskPreflightView()` 调用 `POST /api/v1/risk/preflight`，并固定 `mode: 'paper'`，符合「默认 paper、禁止实盘」的安全约束。
3. **其余 6 个页面仍全部使用 mock 数据，未接入后端。** 详见第 3 节。
4. **paper/live 模式约束一致。** 前端除 Risk 模拟器固定 `paper` 外，无任何页面发起 `live` 请求；后端默认 `paper` 且拒绝 live preflight。不存在「伪造已连接实盘」状态。
5. **存在 6 处契约/字段语义差异，接线前必须先做映射（见第 4 节）。**

---

## 2. 端点对照表

| 后端路由 | HTTP | 前端 api.ts 方法 | 页面调用状态 |
|---|---|---|---|
| `/health` | GET | `api.health()` | 未调用 |
| `/ready` | GET | `api.ready()` | 未调用 |
| `/api/v1/system/status` | GET | `api.systemStatus()` | 未调用 |
| `/api/v1/market/symbols` | GET | `api.symbols()` | 未调用 |
| `/api/v1/market/tickers` | GET | `api.tickers()` | 未调用 |
| `/api/v1/risk/preflight` | POST | `api.preflight()` | **已接入**（Risk.tsx） |
| `/api/v1/orders/intents` | POST | `api.createOrderIntent()` | 未调用 |
| `/api/v1/orders` | GET | `api.orders()` | 未调用 |
| `/api/v1/positions` | GET | `api.positions()` | 未调用 |
| `/api/v1/strategies` | GET | `api.strategies()` | 未调用 |
| `/api/v1/audit/events` | GET | `api.auditEvents()` | 未调用 |

路径、方法、字段名（snake_case）均一致，无接口号、无方法冲突。

---

## 3. 仍使用 mock 数据、尚未接入后端的页面

| 页面 | 数据源 | 应接端点 | 备注 |
|---|---|---|---|
| **Dashboard** | 100% mock（tickers/orders/positions/strategies/riskRules/services） | `tickers`、`orders`、`positions`、`strategies`、`systemStatus` | 顶部权益/PnL/健康度为硬编码，后端暂未提供结算级接口 |
| **MarketData** | 100% mock（tickers/orderBook/trades/fundingRates） | `tickers`、`symbols` | 后端尚无盘口/逐笔/资金费率端点，仅 tickers/symbols 可接 |
| **Research** | 100% mock（strategies/backtest） | `strategies` | 后端无回测端点，策略列表可接 |
| **Execution** | 100% mock（orders/positions/reconciliation） | `createOrderIntent`、`orders`、`positions` | 后端无对账端点；创建订单流程未接线 |
| **Agents** | 100% mock（tasks/approvals/tools） | 无对应后端端点 | 控制平面 Agent 端点尚未实现 |
| **Settings** | 100% mock（audit/exchangeConnections） | `auditEvents` | Audit 标签页标注「GET /api/v1/audit/events」但仍渲染 mock |
| **Risk** | **部分接入**：preflight 模拟器已接后端；规则表/熔断仍 mock | `preflight` ✅ | 规则表 `mockRiskRules`、熔断 `mockCircuitBreakers` 无后端端点 |

**重点提示**：`api.createOrderIntent()`、`api.orders()`、`api.positions()`、`api.strategies()`、`api.auditEvents()`、`api.systemStatus()`、`api.symbols()`、`api.tickers()`、`api.health()`、`api.ready()` 均已定义但**无任何页面调用**。

---

## 4. 发现的契约/字段差异（接线前必须映射）

1. **订单状态枚举不一致**：后端返回 `new / partially_filled / filled / cancelled / rejected / risk_rejected / pending`；前端 `Order.status` 使用中文 `已成交 / 部分成交 / 待执行 / 已撤销 / 风控阻断`。需状态映射函数。
2. **持仓字段差异**：后端 `PositionResponse` 含 `current_price / unrealized_pnl`，**无** `mark_price / liquidation_price / margin_ratio / exposure / avg_price`；前端 `Position` 依赖后四者。字段既有命名差异也有语义缺失。
3. **策略字段差异**：后端 `StrategyResponse` 含 `strategy_id / description / status`，**无** `kind / owner / sharpe / maxDrawdown / winRate / totalReturn / codeRef`；前端 `Strategy` 依赖这些展示字段。
4. **审计字段差异**：后端 `AuditEventResponse` 用 `event_id / actor / resource_type / resource_id / details / ip_address / created_at`；前端 `AuditLog` 用 `id / operator / module / action / result / traceId / payloadSummary`。字段命名与语义几乎全不同。
5. **Ticker 字段差异**：后端 `TickerResponse` 用 `last_price / volume_24h / change_24h / high_24h / low_24h`，**无** `name / source / quality / spark / spread / market_type`；前端 `MarketTicker` 依赖展示字段。
6. **错误格式提取不匹配**：`api.ts` 的 `request()` 只检查 `payload.detail`，而后端统一错误格式为 `{"error": {code, message, details}}`，因此后端错误码/消息无法透传到前端 `ApiError`，会退化为 `HTTP <status>`。
7. **枚举小差异**：后端 `MarketType` = `spot/future/perpetual`；前端 mock 用 `spot/perp`。
8. **审计事件类型**：后端触发 `risk.preflight`、`order.created`、`system.startup`；前端 mock 用 `risk.preflight.passed`、`order.intent.submitted` 等，命名不同。

---

## 5. 建议（仅供后续迭代，非本次改动）

- 增加 `api.ts` 对后端 `{"error":{...}}` 的解析，使错误码/消息可展示。
- 为订单/持仓/策略/审计提供显式 adapter（参考现有 `toRiskPreflightView`），不可把 `api.ts` 的 snake_case 响应直接当展示模型。
- 优先级接线建议：Dashboard → Execution → Settings(audit) → MarketData/Research → Agents（需后端补齐端点）。
- Layout 的 `globalState` 当前恒为 `success` 且硬编码「纸面环境」，建议接入 `api.health()/systemStatus()` 作真实启动自检。

---

## 6. 测试结果

后端 pytest 全量通过（见下方验证记录）。

| 检查项 | 结果 |
|---|---|
| 后端 pytest | 通过 |
| 后端 compileall | 通过 |
| uvicorn smoke test | `/health`、`/api/v1/system/status` 200 |

本报告仅新增 `frontend/FINAL_INTEGRATION_REVIEW.md`，未修改任何业务源码。