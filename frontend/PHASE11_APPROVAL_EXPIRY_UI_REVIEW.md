# 企业级 AI 加密量化交易控制台 Phase 4 审批单过期生命周期前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第二十三阶段 Phase 4 Approval Expiry Lifecycle Protection (审批单到期过期生命周期防护) 前端契约审计、`mapBackendGovernanceApproval` 过期映射扩充与 Vite 构建验证结果。

---

## 1. 后端 172 Pytest 真实测试与 Approval Expiry 对齐

根据后端 `backend/PHASE4_APPROVAL_EXPIRY_LIFECYCLE_CONFORMANCE_REVIEW.md` 记录，后端已通过 **172 项 pytest 测试（7 项全新 Approval Expiry Lifecycle 专项测试）** 与 `compileall` 校验。审批单过期探针测试结果如下：

| 端点 Path / 方法 | HTTP 状态 | 契约与报错映射 | 对应 UI 展示 | 状态 |
|---|---|---|---|---|
| `GET /api/v1/governance/approvals` | 200 OK | `status = "expired"` | 审批列表 Badge 显示 `已过期` | **200 OK (已验证)** |
| `POST /api/v1/governance/approvals/{id}/decide` (expired) | 400 | `APPROVAL_EXPIRED` | 弹出 "该审批单已过期，无法决策" 阻断提示 | **400 BAD REQUEST (已验证)** |
| `POST /api/v1/governance/kill-switch/recover` (expired) | 400 | `APPROVAL_EXPIRED` | 弹出 "用于解封的审批单已过期，Kill Switch 保持生效" 提示 | **400 BAD REQUEST (已验证)** |

---

## 2. 懒过期与系统自动化事件设计 (`src/adapters.ts` & `src/api.ts`)

1. **后端到期过期结算机制**：
   - `expire_due(now)` / `_refresh_expiry()` 自动将超过 `expires_at` 的 `pending` 审批单转换为 `expired` 状态；
   - 过期事件 `governance.approval_expired.v1` 使用 `actor = "system"` 发送；
   - 零侧效应：仅改变审批单状态，不影响持仓、订单、熔断状态或交易所密钥。

2. **前端消费侧接入**：
   - 在 `src/adapters.ts` 的 `mapBackendGovernanceApproval` 函数中，补全了 `else if (rawStatus === 'expired' || rawStatus === '已过期') statusStr = '已过期'` 状态转换规则；
   - 依赖后端返回的真实 `expires_at` 与 `status`，不在前端自行硬编码或倒计时决定账务状态。

---

## 3. 构建与验证命令

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
  # dist/assets/index-BytWjhUW.js   351.41 kB
  # ✓ built in 525ms
  ```

---

## 4. 文件变动清单

- `frontend/src/adapters.ts` (在 `mapBackendGovernanceApproval` 中增加 `expired` 状态映射)
- `frontend/PHASE11_APPROVAL_EXPIRY_UI_REVIEW.md` (本阶段 Phase 4 Approval Expiry Lifecycle Protection 前端契约审计报告)
