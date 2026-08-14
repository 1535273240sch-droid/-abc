# 企业级 AI 加密量化交易控制台 Phase 2 研究闭环前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第十七阶段 Phase 2 研究闭环（策略版本与确定性 Paper 回测引擎）前端契约审计与 Vite 构建验证结果。

---

## 1. API 契约与传输 Wire Schema

前端在 `api.ts` 与 `adapters.ts` 中完成了与后端 FastAPI 研究闭环端点的 100% 契约无缝对接：

| 研究 API 端点 | HTTP 方法 | 前端 Wire Contract | 对应 UI 页面 / 适配器 | 状态 |
|---|---|---|---|---|
| `/api/v1/strategies` | GET | `StrategyResponse[]` | `Research.tsx` / `mapBackendStrategy()` | **200 OK** |
| `/api/v1/research/backtests` | POST | `BacktestRequest` → `BacktestResponse` | `Research.tsx` 点击 "发起 Paper 回测" | **201 Created** |
| `/api/v1/research/backtests` | GET | `BacktestResponse[]` | `Research.tsx` 回测历史列表 | **200 OK** |
| `/api/v1/research/backtests/{id}` | GET | `BacktestResponse` | `Research.tsx` 提取单一回测详情 | **200 OK** |

---

## 2. 字段可追溯性与适配器规则 (`src/adapters.ts`)

- **`BacktestResponse` 关键字段映射**：
  - `strategy_id` + `strategy_version` (策略唯一版本锁定)
  - `parameters` (执行参数快照，如快慢均线、止损比例)
  - `data_snapshot` (数据快照引用，如 `parquet://2026Q1-btc-tick`)
  - `fee_model` (手续费模型，如 `maker_0.02pct_taker_0.04pct`)
  - `slippage_model` (滑点模型，如 `conservative_1.5bps`)
  - `run_environment` (只读运行环境标记 `paper-backtest-engine-v1`)
  - `initial_capital` (初始资金 Decimal 字符串)
  - `mode` (只读标记 `paper`)
  - `net_profit`, `sharpe_ratio`, `max_drawdown`, `win_rate`, `total_trades` (确定性回测指标)

---

## 3. 安全防护与只读防线

1. **研究页面零下单入口**：`Research.tsx` 不包含任何直接创建真实/纸面交易订单、自动连接交易所 API Key 或触发 live 交易的接口。
2. **Paper Mode 强制隔离**：回测请求体 `mode` 100% 为 `paper`，发送 `mode=live` 自动触发后端 403 `LIVE_TRADING_NOT_ALLOWED` 阻断。
3. **报错高可追踪性**：报错透传 `status`, `code`, `message`, `trace_id`。

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
  # 退出码 0，成功构建 (511ms)
  ```

---

## 5. 文件变动清单

- `frontend/PHASE6_RESEARCH_UI_REVIEW.md` (本阶段研究闭环前端契约审计报告)
