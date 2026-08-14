# 企业级 AI 加密量化交易控制台纸面执行 API 接入与 UI 验收报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第五阶段纸面执行生命周期 API 接入、`adapters.ts` 扩展、订单状态机交互与构建验收结果。

---

## 1. 纸面执行 API 接入范围

在不修改后端代码的前提下，在 `Execution.tsx` 中全面接入纸面执行生命周期交互：

| 接口 Path | HTTP 方法 | 前端 `api.ts` 方法 | 触发与交互逻辑 |
|---|---|---|---|
| `/api/v1/execution/fills` | POST | `api.fillOrder()` | 订单列表中的「模拟成交」Modal，发送 `client_order_id`, `fill_quantity`, `fill_price` |
| `/api/v1/execution/orders/{id}/cancel` | POST | `api.cancelOrder()` | 订单列表中的「撤单」按钮 |
| `/api/v1/execution/orders/{id}/reject` | POST | `api.rejectOrder()` | 订单列表中的「拒单」按钮 |
| `/api/v1/execution/reconciliation` | POST | `api.runReconciliation()` | 「触发对账引擎」按钮，传入 `account_id` |
| `/api/v1/execution/reconciliation` | GET | `api.reconciliations()` | 对账日志 Tab 列表 |

---

## 2. Wire Contracts & Adapters

前端补齐了后端 `execution.py` Pydantic 模型的对应 TS 接口：

- `FillRequest` / `FillResponse` (`client_order_id`, `fill_id`, `status`, `filled_quantity`, `average_price`, `position_updates`)
- `CancelRequest` / `CancelResponse` (`client_order_id`, `status`, `reject_reason`)
- `ReconciliationResponse` (`reconciliation_id`, `account_id`, `status`, `details`, `summary`, `created_at`)
- `mapBackendReconciliation()` 适配函数

---

## 3. 错误处理与安全约束

1. **保留后端错误轨迹**：所有操作异常捕捉 `err.message` / `detail`，并在页面上层以负向警示框精准展示，不 swallow 异常。
2. **严禁前端重复计算**：仓位、未实现 PnL、成交均价均依赖后端 API，前端仅负责视图呈现与数据映射。
3. **Paper 安全标章**：全站显示 `paper / simulation` 标识，操作按钮包含模拟标注，防止用户误解为真实交易所下单。

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
  # dist/assets/index-CMPKWEpD.js   341.52 kB
  # ✓ built in 408ms
  ```

---

## 5. 修改文件清单

- `frontend/src/api.ts` (新增 Fill, Cancel, Reject, Reconciliation Wire Contracts & API 方法)
- `frontend/src/adapters.ts` (新增 `mapBackendReconciliation` 适配函数)
- `frontend/src/pages/Execution.tsx` (接入纸面成交、撤单、拒单及对账引擎交互)
- `frontend/PAPER_EXECUTION_UI_ACCEPTANCE.md` (本验收报告)
