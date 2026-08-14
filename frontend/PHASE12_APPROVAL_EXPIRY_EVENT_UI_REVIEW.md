# 企业级 AI 加密量化交易控制台 Phase 4 审批过期事件与审计时间线前端契约审计报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第二十四阶段 Phase 4 审批过期事件 (`governance.approval_expired.v1`) 与审计时间线 (Audit Timeline) 契约审计、`mapBackendAuditLog` 映射增强与 Vite 构建验证结果。

---

## 1. 后端 172 Pytest 真实测试与 `governance.approval_expired.v1` 契约对齐

根据后端 `backend/PHASE4_APPROVAL_EXPIRY_LIFECYCLE_CONFORMANCE_REVIEW.md` 与 `backend/app/events/bus.py` 记录，后端已通过 **172 项 pytest 测试** 与 `compileall` 校验。版本化事件契约审计对齐如下：

| 事件属性 | 契约规格 | 真实 JSON Payload / HTTP 证据 | 前端 UI 渲染映射 | 状态 |
|---|---|---|---|---|
| `event_type` | `governance.approval_expired.v1` | `"event_type": "governance.approval_expired.v1"` | Audit Timeline 事件类型 | **已对齐 (200 OK)** |
| `version` | `1` | `1` (DomainEvent version=1) | 默认 v1 兼容解析 | **已对齐 (200 OK)** |
| `resource_type` | `"approval"` | `"resource_type": "approval"` | 审计模块标签 `governance` | **已对齐 (200 OK)** |
| `resource_id` | `approval_id` | `"resource_id": "appr_ks_recover_001"` | 动作显示 `系统自动过期 · 审批单: appr_ks_recover_001` | **已对齐 (200 OK)** |
| `actor` | `"system"` | `"actor": "system"` | 操作人显示 `system` (系统自动化) | **摊平展示 (已验证)** |
| `payload` | dict | `{"approval_id": "...", "resource_type": "approval", "resource_id": "...", "status": "expired", "expired_at": "..."}` | JSON Payload 展开 | **降级/格式化正确** |

---

## 2. 审计时间线与防线逻辑 (`src/adapters.ts` & `src/types.ts`)

1. **`mapBackendAuditLog` 增强**：
   - 针对 `governance.approval_expired.v1` 事件，格式化生成 `系统自动过期 · 审批单: {resource_id} · 到期时间: {expired_at}` 操作描述；
   - 将 `actor` 统一映射为 `"system"`，清晰表达这是系统自动清扫到期单行为，而非用户手动干预。
2. **`ApprovalItem['status']` 规范扩充**：
   - 在 `src/types.ts` 中补齐 `'已过期'` 描述；
   - 在 `src/pages/Agents.tsx` 的审批列表中展示 `neutral` 灰色 Badge 态，与 `positive` (已通过) 和 `negative` (已拒绝) 形成视觉区分。
3. **降级与容错**：
   - 若 `details` 为空或版本未知，UI 自动回退至基线格式化（`governance.approval_expired.v1 (Resource: ...)`），防止 React 抛出空值异常。

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
  # dist/assets/index-CvSokAJt.js   351.66 kB
  # ✓ built in 407ms
  ```

---

## 4. 文件变动清单

- `frontend/src/adapters.ts` (增强 `mapBackendAuditLog` 处理 `governance.approval_expired.v1` 事件)
- `frontend/src/types.ts` (在 `ApprovalItem` 中扩充 `'已过期'` 类型)
- `frontend/src/pages/Agents.tsx` (更新审批单状态 Badge 颜色)
- `frontend/PHASE12_APPROVAL_EXPIRY_EVENT_UI_REVIEW.md` (第二十四阶段 Phase 4 审批过期事件与审计时间线前端契约审计报告)
