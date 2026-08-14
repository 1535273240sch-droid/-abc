# 企业级 AI 加密量化交易控制台研究回测 API 接入与 UI 验收报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第四阶段研究回测 API 接入、`adapters.ts` 数据转换层扩展、交互与打包验收结果。

---

## 1. 后端研究/回测 API 接入范围

本轮在**不修改后端代码**的前提下，将 OpenCode 在 Phase 2 中完成的研究回测 API 安全接入至 `Research.tsx`：

| 后端 API 端点 | HTTP 方法 | 前端 `api.ts` 方法 | UI 交互与接入位置 |
|---|---|---|---|
| `/api/v1/strategies` | GET | `api.strategies()` | 策略注册表清单与目标策略选择 |
| `/api/v1/research/backtests` | POST | `api.createBacktest()` | 「新建回测任务 Modal」，提交 `strategy_id`, `version`, `data_snapshot`, `fee_model`, `slippage_model`, `initial_capital`, `mode: "paper"` |
| `/api/v1/research/backtests` | GET | `api.backtests()` | 回测历史记录列表与首页核心指标区 |
| `/api/v1/research/backtests/{id}` | GET | `api.backtest()` | 单笔回测明细与指标报告 |

---

## 2. 数据转换适配器 (`src/adapters.ts`)

后端 `BacktestResponse` 返回 `snake_case` JSON。前端构建了强类型适配器 `mapBackendBacktest()`：

- `backtest_id` → `id`
- `strategy_id` / `strategy_version` → `strategyId` / `version`
- `initial_capital` → `initialCapital` (`$100,000.00`)
- `net_profit` → `netProfit` (`+$18,078.62`)
- `sharpe_ratio` → `sharpeRatio` (`1.80`)
- `max_drawdown` → `maxDrawdown` (`-8.40%`)
- `win_rate` → `winRate` (`58.4%`)
- `total_trades` → `totalTrades` (`342`)
- `fee_model` / `slippage_model` → `feeModel` / `slippageModel`
- `data_snapshot` → `dataSnapshotId`

---

## 3. 降级与三态体验

- **API 连接成功**：顶部显示 `✓ 已接入 API POST/GET /api/v1/research/backtests & /strategies (Paper-Only Engine)`。
- **API 未连接/失败**：显示 `⚠ 回测 API 未在线，当前显示 [Demo / Mock 模拟回测数据源]`，支持手动触发重试。
- **Paper / Simulation 约束**：回测请求显式锁定为 `mode: "paper"`，全页面标注 `Paper Environment`，不涉及真实交易所下单。

---

## 4. 构建与验证结果

- **TypeScript 类型检查**：
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
  # dist/assets/index-B-gXLgHx.js   336.95 kB
  # ✓ built in 462ms
  ```

---

## 5. 修改文件清单

- `frontend/src/api.ts` (新增 `BacktestRequest`, `BacktestResponse` 接口及 `createBacktest`, `backtests`, `backtest` API)
- `frontend/src/adapters.ts` (新增 `mapBackendBacktest` 适配转换函数)
- `frontend/src/pages/Research.tsx` (接入回测提交与列表 API，完善降级处理)
- `frontend/RESEARCH_UI_ACCEPTANCE.md` (本验收报告)
