# 企业级 AI 加密量化交易控制台前端 API 接入与视觉验收报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第二阶段前端页面接入真实后端 Paper API、数据适配器构建、视觉自适应检查与打包验收结果。

---

## 1. 后端 API 接入范围 (Integration Scope)

本轮在**不修改后端代码**的前提下，使用 `frontend/src/api.ts` 与新建的适配器层 `frontend/src/adapters.ts`，完成了 5 个核心页面的 Paper API 接线：

| 页面 | 调用的后端 API 端点 | 接入状态 | 备注 |
|---|---|---|---|
| **Dashboard** | `GET /api/v1/system/status`<br>`GET /api/v1/market/tickers`<br>`GET /api/v1/orders`<br>`GET /api/v1/positions`<br>`GET /api/v1/strategies` | **已接入** | 支持 API 响应与 Demo/Mock 自动降级 |
| **MarketData** | `GET /api/v1/market/symbols`<br>`GET /api/v1/market/tickers` | **已接入** | 盘口 (L2 Orderbook) 与成交流目前后端无接口，保留 Demo 标识 |
| **Execution** | `GET /api/v1/orders`<br>`GET /api/v1/positions`<br>`POST /api/v1/orders/intents` | **已接入** | 支持通过 Modal 提交具备 `risk_decision_id` 的订单意图 |
| **Research** | `GET /api/v1/strategies` | **已接入** | 回测计算端点后端暂无，回测曲线保留 Demo 展示 |
| **Settings** | `GET /api/v1/system/status`<br>`GET /api/v1/audit/events` | **已接入** | 实时拉取审计事件与系统版本 |
| **Risk** | `POST /api/v1/risk/preflight` | **第一阶段已接入** | 实时风险前置算子模拟测试 |
| **Agents** | 暂无对应后端 API | 保留 Demo 视图 | 显式标注 Demo 标识 |

---

## 2. 数据适配层与类型转换 (Adapters - `src/adapters.ts`)

后端 API 返回规范的 `snake_case` JSON 响应。为防止将后端原始数据类型污染前端 UI 呈现模型，构建了强类型的转换适配器：

- `mapBackendTicker`: 将 `TickerResponse` + `SymbolResponse` 映射为 `MarketTicker`（处理 `last_price`, `bid_price`, `ask_price`, `volume_24h` 及涨跌幅 Tone）。
- `mapBackendOrder`: 将 `OrderResponse` 映射为 `Order`（映射 `client_order_id`, `strategy_version`, `risk_decision_id` 及订单状态枚举 `'filled' -> '已成交'`, `'risk_rejected' -> '风控阻断'`）。
- `mapBackendPosition`: 将 `PositionResponse` 映射为 `Position`（映射 `unrealized_pnl`, `entry_price`, `current_price`）。
- `mapBackendStrategy`: 将 `StrategyResponse` 映射为 `Strategy`（映射 `strategy_id`, `parameters`）。
- `mapBackendAuditLog`: 将 `AuditEventResponse` 映射为 `AuditLog`（映射 `event_id`, `actor`, `event_type`）。
- `mapBackendSystemStatus`: 将 `SystemStatusResponse` 映射为 `SystemService`。
- **错误提取增强**：更新 `api.ts` 的 `request()` 函数，支持自动从 `{"error": { "message": "..." }}` 或 `{"detail": "..."}` 结构中提取后端精准错误信息。

---

## 3. 降级行为与 Loading / Error / Empty 状态

1. **API 未连接/失败降级**：
   - 当后端 API 未在线（如端口 8000 未启动或网络超时）时，页面捕捉异常并无缝触发降级机制，在页面顶部呈现醒目的 Banner：
     `⚠ 后端 API 未在线，当前已降级为 [Demo/Mock 模拟数据源] 展示`
   - 提供「重新拉取 API」重试按钮。
2. **三态完整覆盖**：
   - **Loading 状态**：数据请求期间自动显示 `DataState state="loading"` 脉冲动画与文字提示。
   - **Empty 状态**：当后端 API 返回空数组 `[]` 时，显示 `无数据` 空态插图与提示。
   - **Error 状态**：网络失败时提示可重试按钮。

---

## 4. 多模态与视觉检查结果 (Visual Audit)

- **深色高对比金融科技视觉**：全站采用 `#090B0E` 深色基调与高密度 Data Grid。
- **等宽数值对齐**：所有价格、数量、算子 ID 与时间戳统一应用 `font-variant-numeric: tabular-nums`。
- **表格防溢出**：所有表格外层包裹 `.data-table-wrap` 并开启 `overflow-x: auto`，保障窄窗口下表格横向平滑滚动而不破坏页面布局。
- **响应式 Media Queries**：在 `styles.css` 中增加了 1200px 与 768px 响应式断点，窄屏时 4 列卡片自动重排为 2 列或单列。
- **生产环境安全隔离**：顶栏预览状态控制按钮被 `import.meta.env.DEV` 隔离，生产打包中已自动隐藏。

---

## 5. 构建与类型验证

- **TypeScript 类型检查**：
  ```bash
  npx tsc --noEmit
  # 退出码 0，零类型错误
  ```
- **Vite 生产打包**：
  ```bash
  npm run build
  # 退出码 0，顺利完成构建：
  # dist/index.html                   0.53 kB
  # dist/assets/index-BwhuTa21.css   16.82 kB
  # dist/assets/index-Czb6-Wv3.js   334.54 kB
  # ✓ built in 459ms
  ```

---

## 6. 修改文件清单

- `frontend/src/adapters.ts` (新建 API 转换适配器)
- `frontend/src/api.ts` (增强错误消息解析)
- `frontend/src/styles.css` (新增响应式媒体查询)
- `frontend/src/pages/Dashboard.tsx` (接入 systemStatus/tickers/orders/positions/strategies API)
- `frontend/src/pages/MarketData.tsx` (接入 symbols/tickers API)
- `frontend/src/pages/Execution.tsx` (接入 orders/positions/createOrderIntent API)
- `frontend/src/pages/Research.tsx` (接入 strategies API)
- `frontend/src/pages/Settings.tsx` (接入 systemStatus/auditEvents API)
- `frontend/FRONTEND_RUNTIME_INTEGRATION.md` (本验收报告)
