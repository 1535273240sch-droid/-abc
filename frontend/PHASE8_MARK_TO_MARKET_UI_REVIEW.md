# 企业级 AI 加密量化交易控制台 Phase 3 Mark-to-Market PnL 前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第二十阶段 Phase 3 Mark-to-Market (MTM 盯市与未实现盈亏计算) 前端契约审计、`MarkToMarketResponse` Wire Contract 对接与 Vite 构建验证结果。

---

## 1. 后端 149 Pytest 真实测试与 MTM 盯市证据对齐

根据后端 `backend/PHASE3_MARK_TO_MARKET_PNL_CONFORMANCE_REVIEW.md` 记录，后端已通过 **149 项 pytest 测试（9 项全新 Mark-to-Market 专项测试）** 与 `compileall` 校验。MTM 探针测试结果如下：

| 端点 Path | HTTP 方法 | 前端 Wire Contract | 对应 UI 页面 / 交互 | 状态 |
|---|---|---|---|---|
| `/api/v1/positions/mark-to-market` | POST | `MarkToMarketRequest` → `MarkToMarketResponse` | `Execution.tsx` 点击 "按标记价盯市" | **200 OK (已验证)** |
| `/api/v1/positions` | GET | `PositionResponse[]` | `Execution.tsx` 持仓列表更新 (反映最新 `unrealized_pnl`) | **200 OK (已验证)** |
| `/api/v1/positions/mark-to-market (mode=live)` | POST | — | 自动阻断并抛出 `ApiError` | **403 LIVE_TRADING_NOT_ALLOWED** |

---

## 2. 盯市公式与 Decimal 高精度展示 (`src/api.ts` & `src/pages/Execution.tsx`)

前端在 `api.ts` 中新增了 `MarkToMarketRequest` 与 `MarkToMarketResponse` 接口，并在 `Execution.tsx` 持仓仪表盘中接入了交互式 MTM 刷新弹窗：

1. **后端 MTM 结算逻辑**：
   - **多头 (BUY)**: `unrealized_pnl = (mark_price - entry_price) × quantity`
   - **空头 (SELL)**: `unrealized_pnl = (entry_price - mark_price) × quantity`
   - `current_price = mark_price`
   - 结果保持 `Decimal` 精确度（保留 2 位小数，如 `+5000.00`），并提供正负色彩提示 (`text-positive` / `text-negative`)。

2. **`Execution.tsx` 页面交互**：
   - 包含 `按标记价盯市 (POST /api/v1/positions/mark-to-market)` 操作按钮；
   - 支持动态选取标的（`BTCUSDT`, `ETHUSDT`, `SOLUSDT`）并输入最新 `mark_price` 提交计算。

---

## 3. 安全防护与零副作用防线 (No Order Side Effects)

- **无订单侧效应**：`POST /api/v1/positions/mark-to-market` 仅更新持仓未实现盈亏，**绝不上报或修改任何订单**（后端通过 `test_mark_to_market_no_order_side_effect` 严格测试，订单总数保持不变）。
- **零真实交易所与零 Key**：完全运行在 Paper Mode 下，`mode=live` 请求抛出 403 `LIVE_TRADING_NOT_ALLOWED`。

---

## 4. 构建与验证命令

- **TypeScript 静态检查**：
  ```bash
  npx tsc --noEmit
  # 退出码 0，零类型错误
  ```
- **Vite 生产打包**：
  ```bash
  npm run build
  # 退出码 0，成功构建：
  # dist/index.html                   0.53 kB
  # dist/assets/index-BwhuTa21.css   16.82 kB
  # dist/assets/index-DGS2J1RF.js   347.20 kB
  # ✓ built in 600ms
  ```

---

## 5. 文件变动清单

- `frontend/src/api.ts` (新增 `MarkToMarketRequest` / `Response` 接口与 `markToMarket` API 方法)
- `frontend/src/pages/Execution.tsx` (在持仓 Tab 中新增 MTM 操作按钮与盯市刷新 Modal)
- `frontend/PHASE8_MARK_TO_MARKET_UI_REVIEW.md` (本阶段 Phase 3 Mark-to-Market PnL 前端契约审计报告)
