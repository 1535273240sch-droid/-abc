# 企业级 AI 加密量化交易控制台 Phase 3 Portfolio Target 前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第十九阶段 Phase 3 Portfolio Target（信号 → 组合目标 → 差额计算）前端契约审计、`PortfolioTargetResponse` Wire Contract 对接与 Vite 构建验证结果。

---

## 1. 后端 140 Pytest 真实测试与 Portfolio Target 证据对齐

根据后端 `backend/PHASE3_PORTFOLIO_TARGET_CONFORMANCE_REVIEW.md` 记录，后端已通过 **140 项 pytest 测试（11 项全新 Portfolio Target 专项测试）** 与 `compileall` 校验。Portfolio Target 探针测试结果如下：

| 端点 Path | HTTP 方法 | 前端 Wire Contract | 对应 UI 页面 / 适配器 | 状态 |
|---|---|---|---|---|
| `/api/v1/portfolio/targets` | POST | `PortfolioTargetRequest` → `PortfolioTargetResponse` | `api.createPortfolioTarget()` 信号设置目标 | **201 Created (已验证)** |
| `/api/v1/portfolio/targets` | GET | `PortfolioTargetResponse[]` | `api.portfolioTargets()` 目标列表 | **200 OK (已验证)** |
| `/api/v1/portfolio/targets/{id}` | GET | `PortfolioTargetResponse` | `api.portfolioTarget()` 目标详情 | **200 OK (已验证)** |
| `/api/v1/portfolio/targets (mode=live)` | POST | — | 自动阻断并抛出 `ApiError` | **403 LIVE_TRADING_NOT_ALLOWED** |

---

## 2. 字段计算与前端契约 (`src/api.ts` & `src/adapters.ts`)

前端已在 `api.ts` 与 `adapters.ts` 中完成了 `PortfolioTargetResponse` 的完整类型定义与适配：

1. **核心计算字段**：
   - `target_id`: UUID 目标唯一编号
   - `account_id`: 目标账户
   - `strategy_id` + `strategy_version`: 来源策略与版本锁定
   - `symbol`: 交易标的（如 `BTCUSDT`）
   - `target_quantity`: 目标持仓量（Decimal）
   - `current_quantity`: 实时持仓量（从 `PositionService` 获取）
   - `delta`: 差额 `target_quantity - current_quantity`（由后端自动精准计算）
   - `target_weight`: 组合目标权重（可选）
   - `mode`: 只读标记 `paper`
   - `idempotency_key`: 幂等去重 Key

2. **`mapBackendPortfolioTarget` 适配函数**：
   - 规范输出 UI 消费对象，无缝防范 undefined / null 漏洞。

---

## 3. 安全防护与零下单防线 (No Order Bypass)

- **纯信号目标管理**：`POST /api/v1/portfolio/targets` 仅用于组合目标与 `delta` 差额计算，**绝不自动创建订单**（后端通过 `test_portfolio_target_no_order_creation` 严格测试，`/api/v1/orders` 保持为空）。
- **下单隔离防线**：下发订单必须显式调用 `POST /api/v1/orders/intents` 并且 **强制携带 `risk_decision_id`**，无法通过 Portfolio Target 绕过风控前置拦截。
- **Paper/Simulation 统一标章**：全站维持 Paper Mode，`mode=live` 自动拦截 403。

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
  # dist/assets/index-C73HOUzc.js   345.10 kB
  # ✓ built in 558ms
  ```

---

## 5. 文件变动清单

- `frontend/src/api.ts` (新增 `PortfolioTargetRequest` / `Response` 接口与 `createPortfolioTarget`, `portfolioTargets`, `portfolioTarget` 方法)
- `frontend/src/adapters.ts` (新增 `mapBackendPortfolioTarget` 适配映射)
- `frontend/PHASE7_PORTFOLIO_TARGET_UI_REVIEW.md` (本阶段 Phase 3 Portfolio Target 前端契约审计报告)
