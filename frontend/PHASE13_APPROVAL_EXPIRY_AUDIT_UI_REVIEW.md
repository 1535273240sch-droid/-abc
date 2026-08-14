# 企业级 AI 加密量化交易控制台 Phase 4 审批过期审计投影 API 前端契约复核报告

本报告记录审批过期审计投影 API (`GET /api/v1/audit/events`) 契约复核、前端映射与终态验收。

---

## 1. 后端契约终态

- **检查项**：`backend/PHASE4_APPROVAL_EXPIRY_AUDIT_PROJECTION_CONFORMANCE_REVIEW.md`
- **状态**：**已生成并通过**
- **响应字段**：`event_type`、`actor`、`resource_type`、`resource_id`、`trace_id`、`details.version`、`details.payload`。
- **审计语义**：后端只读投影；前端不自行改变审批状态。

---

## 2. 前端契约与页面就绪准备 (Frontend Readiness)

前端在 `api.ts` 与 `adapters.ts` 中已具备完整且强鲁棒的审计事件消费与展示能力：

1. **审计事件接口 API (`src/api.ts`)**：
   - `AuditEventResponse` (`event_id`, `event_type`, `actor`, `resource_type`, `resource_id`, `details`, `ip_address`, `created_at`)
   - `api.auditEvents()` 方法
2. **`mapBackendAuditLog` 事件映射 (`src/adapters.ts`)**：
   - `governance.approval_expired.v1` 严格读取 `details.version === 1` 和
     `details.payload.status === "expired"`。
   - 从 `details.payload.expired_at` 显示系统自动过期时间；`system` actor 和 approval 资源
     来自后端字段。
   - 缺失或未知版本降级为明确的“版本不支持或字段缺失”警告，不伪造审批状态。
3. **安全与防绕过防线**：
   - UI 仅展示后端只读审计轨迹，不上报也不改变审批单状态。
   - 保持 Paper/Simulation 强防线，`mode=live` 自动抛出 403 阻断。

---

## 3. 构建与验证状态

- **TypeScript 静态检查**：通过（`tsc -b` / `tsc --noEmit`）
  ```bash
  npx tsc --noEmit
  # 退出码 0，零类型错误
  ```
- **Vite 生产打包**：通过（本地 `vite build`）
  ```bash
  npm run build
  # 退出码 0，成功构建（1811 modules transformed，约 509ms）
  ```

---

## 4. 后续步骤与限制

后端 pytest（178 passed）与 Uvicorn smoke 已通过；前端映射、未知版本降级、TypeScript 和构建
已完成。当前系统仍严格为 paper/simulation；内存事件总线和内存审计 read model 不代表生产级
跨进程持久化，生产接入可靠消息系统和持久化审计存储前不得用于 live 交易。
