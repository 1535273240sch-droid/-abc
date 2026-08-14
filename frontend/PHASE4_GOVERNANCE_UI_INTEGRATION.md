# 企业级 AI 加密量化交易控制台 Phase 4 治理只读接入与 UI 验收报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第八阶段 Phase 4 治理只读 API 接入、`adapters.ts` 扩展、只读防护边界与打包验收结果。

---

## 1. 治理只读 API 接入范围

依据 `backend/app/api/v1/governance.py` 暴露的真实接口，在前端完成只读视图连通：

| 接口 Path | HTTP 方法 | 前端 `api.ts` 方法 | UI 展示位置与功能 |
|---|---|---|---|
| `/api/v1/governance/approvals` | GET | `api.governanceApprovals()` | `Agents.tsx` 人工审批门 Tab，展示审批单 ID、事项标题、资源类型与状态 |
| `/api/v1/governance/kill-switch` | GET | `api.governanceKillSwitch()` | `Risk.tsx` 风控中心，展示当前 Kill Switch 运行状态、触发人与原因 |

---

## 2. Wire Contracts & Adapters (`src/adapters.ts`)

前端补充了 Phase 4 治理相关的传输与转换接口：

- `GovernanceApprovalResponse` (`approval_id`, `resource_type`, `resource_id`, `requested_by`, `title`, `details`, `status`, `created_at`, `expires_at`)
- `GovernanceKillSwitchResponse` (`status`, `triggered_by`, `trigger_reason`, `triggered_at`, `recovered_by`, `recovered_at`)
- `mapBackendGovernanceApproval()` 适配函数
- `mapBackendGovernanceKillSwitch()` 适配函数

---

## 3. 只读边界与降级策略

1. **严格只读控制**：不接入未经后端验收的写操作（Mutation），模拟按钮保持沙盒展示，防止越权或绕过审批门。
2. **三态与降级**：
   - API 在线：提示 `✓ 已接入 API GET /api/v1/governance/approvals (只读治理视图)`
   - API 未在线：提示 `⚠ 降级为 [Demo / Mock 静态推演视图]`
3. **Paper/Simulation 安全**：全站显示 `paper / simulation` 标识，保留后端错误 `status`, `code`, `message`, `trace_id`。

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
  # dist/assets/index-BBHsdjko.js   342.72 kB
  # ✓ built in 615ms
  ```

---

## 5. 修改文件清单

- `frontend/src/api.ts` (新增 `GovernanceApprovalResponse`, `GovernanceKillSwitchResponse` 及 GET API)
- `frontend/src/adapters.ts` (新增 `mapBackendGovernanceApproval`, `mapBackendGovernanceKillSwitch` 适配函数)
- `frontend/src/pages/Agents.tsx` (接入只读审批门 API)
- `frontend/src/pages/Risk.tsx` (接入只读 Kill Switch 状态 API)
- `frontend/PHASE4_GOVERNANCE_UI_INTEGRATION.md` (本阶段验收报告)
