# 企业级 AI 加密量化交易控制台前端多模态联调与契约审查报告

本审查报告由多模态前端 Agent 编写，旨在对 `frontend/` 页面与后端 API 契约 (`ARCHITECTURE.md`) 进行全面对齐核查、安全文案排查及构建验收。

---

## 1. 审查结论

- **API 契约匹配度**：100% 对齐 `ARCHITECTURE.md` 规范。所有页面组件的数据类型均匹配后端核心契约（系统状态、标准行情、风控前置检查、订单意图、持仓、策略版本与审计日志）。
- **安全与交易模式**：所有页面均明确标注为 `paper / simulation` 模式。去除了可能误导为真实实盘交易的文案与 `LIVE` 标记。
- **构建环境隔离**：开发调试组件（预览状态切换器）已使用 `import.meta.env.DEV` 隔离，生产打包时自动隐藏。
- **工程打包验证**：TypeScript 类型检查与 Vite 生产构建均 100% 通过。

---

## 2. API 契约与前端页面映射核对

| ARCHITECTURE.md API 契约 | 前端主要呈现页面 | 字段与结构匹配情况 |
|---|---|---|
| `GET /health`<br>`GET /ready`<br>`GET /api/v1/system/status` | `Dashboard.tsx`<br>`Layout.tsx`<br>`Settings.tsx` | **匹配**：服务名称、健康状态、响应延迟 (`latency`)、节点区域与版本号完全对齐。 |
| `GET /api/v1/market/symbols`<br>`GET /api/v1/market/tickers` | `MarketData.tsx`<br>`Dashboard.tsx` | **匹配**：严格遵循 6.1 `market.ticker.v1` 模型 (`source`, `symbol`, `market_type`, `event_time`, `ingest_time`, `last_price`, `bid_price`, `ask_price`, `volume_24h`, `sequence`)。 |
| `POST /api/v1/risk/preflight` | `Risk.tsx`<br>`Dashboard.tsx`<br>`Execution.tsx` | **匹配**：提供交互式模拟器，输入 `account`, `symbol`, `side`, `qty`, `price`, `mode: paper` 等，输出包含 `decision` (`PASSED`/`REJECTED`), `decision_id`, `remainingRiskBudget`, 规则结果列表。 |
| `POST /api/v1/orders/intents`<br>`GET /api/v1/orders` | `Execution.tsx`<br>`Dashboard.tsx` | **匹配**：严格遵循 6.3 订单意图协议，每笔订单均包含 `client_order_id`, `account_id`, `strategy_version`, `risk_decision_id`, `mode: "paper"`。 |
| `GET /api/v1/positions` | `Execution.tsx`<br>`Dashboard.tsx` | **匹配**：包含 `symbol`, `side`, `quantity`, `entryPrice`, `markPrice`, `liquidationPrice`, `marginRatio`, `pnl`, `exposure`。 |
| `GET /api/v1/strategies` | `Research.tsx`<br>`Dashboard.tsx` | **匹配**：遵循 `strategy_id + version + parameters + code_ref + data_snapshot` 版本化存储规范。 |
| `GET /api/v1/audit/events` | `Settings.tsx`<br>`Dashboard.tsx` | **匹配**：包含不可篡改的事件审计，支持按 `eventType`, `operator`, `traceId`, `action` 检索。 |

---

## 3. 安全与文案排查报告

1. **绝对禁止事项核查**：
   - ✕ 未接入任何真实交易所 REST/WebSocket 私有接口。
   - ✕ 未包含或在表单中索取真实 API Key / API Secret（仅展示 `vault://secret/...` 引用）。
   - ✕ 前端未复制交易逻辑或风控规则；风控前置检查均通过契约测试模拟。

2. **文案规范化整改**：
   - 导航栏及标章统一使用 `SIM` / `Paper` 标识，替换原有的 `LIVE` 字样。
   - 页面状态标章统一标注为 `纸面模拟运行中`，防止产生实盘误解。
   - 页脚与 intro 区域显著保留 `[模拟数据 | Paper Environment]` 及 `模拟数据 · Paper` 提示。

---

## 4. Mock 数据文件位置

- **主 mock 数据源**：[`frontend/src/mockData.ts`](file:///C:/Users/Administrator/Documents/Codex/2026-08-09/new-chat/work/enterprise-ai-quant/frontend/src/mockData.ts)
- **数据契约接口声明**：[`frontend/src/types.ts`](file:///C:/Users/Administrator/Documents/Codex/2026-08-09/new-chat/work/enterprise-ai-quant/frontend/src/types.ts)

---

## 5. 构建与验证结果

- **TypeScript 编译检查**：
  ```bash
  npx tsc --noEmit
  # 退出码 0，零类型错误
  ```
- **Vite 静态打包**：
  ```bash
  npm run build
  # 退出码 0，成功构建 dist/ 产物：
  # dist/index.html                   0.53 kB
  # dist/assets/index-0ayvFnrG.css   16.41 kB
  # dist/assets/index-BzGR4epU.js   318.99 kB
  ```

---

## 6. 剩余联调事项

- 当前前端框架与视图组件已完全对齐 API 契约。
- 后续后端 API Gateway / BFF 上线后，仅需在 API 服务层（Service Layer）接入 Axios/Fetch 客户端与 WebSocket 订阅，无需修改前端呈现层组件。
