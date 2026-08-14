# 企业级 AI 加密量化交易控制台 Phase 4 熔断恢复审批门前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第二十二阶段 Phase 4 Kill-Switch Recovery Approval (熔断恢复审批门校验) 前端契约审计、`KillSwitchRecoverRequest` Wire Contract 对接与 Vite 构建验证结果。

---

## 1. 后端 165 Pytest 真实测试与 Kill-Switch Approval Gate 对齐

根据后端 `backend/PHASE4_KILL_SWITCH_RECOVERY_APPROVAL_CONFORMANCE_REVIEW.md` 记录，后端已通过 **165 项 pytest 测试（6 项全新 Kill-Switch Recovery Approval Gate 专项测试）** 与 `compileall` 校验。熔断解封审批门探针测试结果如下：

| 端点 Path | HTTP 方法 | 前端 Wire Contract | 对应 UI 页面 / 报错映射 | 状态 |
|---|---|---|---|---|
| `/api/v1/governance/kill-switch/recover` | POST | `KillSwitchRecoverRequest` → `GovernanceKillSwitchResponse` | `Risk.tsx` 点击 "提交审批单解封" 弹窗 | **200 OK (已验证)** |
| `/api/v1/governance/kill-switch/recover (missing)` | POST | — | 自动捕获 404 `NOT_FOUND` 错误 | **404 NOT FOUND (已验证)** |
| `/api/v1/governance/kill-switch/recover (pending)` | POST | — | 自动捕获 400 `APPROVAL_PENDING` 错误 | **400 BAD REQUEST (已验证)** |
| `/api/v1/governance/kill-switch/recover (rejected)` | POST | — | 自动捕获 400 `APPROVAL_REJECTED` 错误 | **400 BAD REQUEST (已验证)** |
| `/api/v1/governance/kill-switch/recover (wrong type)` | POST | — | 自动捕获 400 `INVALID_APPROVAL_TYPE` 错误 | **400 BAD REQUEST (已验证)** |
| `/api/v1/governance/kill-switch/recover (mode=live)` | POST | — | 自动阻断抛出 `LIVE_TRADING_NOT_ALLOWED` | **403 LIVE_TRADING_NOT_ALLOWED** |

---

## 2. 审批门解封防线与防护逻辑 (`src/api.ts` & `src/pages/Risk.tsx`)

前端在 `api.ts` 中补全了 `KillSwitchRecoverRequest` 接口，并在 `Risk.tsx` 熔断控制台中接入了强校验解封 Modal：

1. **后端解封审批门校验规则**：
   - 必须包含 `approval_id`
   - 审批单资源类型必须为 `kill_switch_recovery`
   - 审批单状态必须为 `approved`（`pending` 报 400, `rejected` 报 400, `expired` 报 400）
   - `mode` 必须为 `paper`

2. **`Risk.tsx` 页面交互**：
   - 处于紧急熔断激活状态时，解封操作引导用户填入 `approval_id`、`recovered_by` 与 `reason`；
   - 提交解封请求时，若无合规审批单，UI 将展示后端抛出的对应阻断提示（如 `APPROVAL_PENDING` 或 `NOT_FOUND`）。

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
  # dist/assets/index-CfR8xopG.js   351.36 kB
  # ✓ built in 606ms
  ```

---

## 4. 文件变动清单

- `frontend/src/api.ts` (新增 `KillSwitchRecoverRequest` 接口与 `recoverKillSwitch` API 方法)
- `frontend/src/pages/Risk.tsx` (在风控中心增加 Kill Switch 解封审批单引用输入框与解封 handler)
- `frontend/PHASE10_KILL_SWITCH_RECOVERY_APPROVAL_UI_REVIEW.md` (本阶段 Phase 4 Kill-Switch Recovery Approval Gate 前端契约审计报告)
