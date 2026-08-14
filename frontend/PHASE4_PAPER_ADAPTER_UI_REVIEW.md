# 企业级 AI 加密量化交易控制台 Paper Adapter UI 适配与契约回归报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第九阶段 Paper Adapter 状态 UI 适配、只读契约复核、降级隔离与构建验收结果。

---

## 1. 适配器端点契约审查与阻塞项记录

依据 `backend/app/api/v1/` 现存模块（`audit.py`, `execution.py`, `governance.py`, `market.py`, `order.py`, `position.py`, `research.py`, `risk.py`, `strategy.py`, `system.py`）核查：

- **行情 API**：`GET /api/v1/market/symbols` 与 `GET /api/v1/market/tickers` 已接入。
- **只读治理 API**：`GET /api/v1/governance/approvals` 与 `GET /api/v1/governance/kill-switch` 已接入。
- **Adapter 状态 API**：后端目前尚未暴露独立的 `/api/v1/adapters/status` 端点。
- **处理策略**：遵循指导方针，“若合同尚未落地，先保持现有 Demo/Mock 降级并在报告中记录阻塞，不伪造 API”。在 `Settings.tsx` 交易所连接模块显式标注 `(注意：后端 Adapter 状态端点尚未提供，以下为 [Demo / Mock 适配器视图])`。

---

## 2. 三类状态隔离复核 (State Disambiguation)

为防止控制台状态互相误导，对三类重要状态建立了清晰的视觉区分：

1. **Governance Approvals (治理审批)**：只读展示 `/api/v1/governance/approvals` 后端返回的真实单据，写动作保持沙盒/Demo 提示。
2. **System Kill Switch (系统熔断)**：只读展示 `/api/v1/governance/kill-switch` 后端状态，开关按钮带 `(只读防线 | 须后端二次鉴权)` 说明。
3. **Adapter Status (交易所适配器)**：标明 `[Demo / Mock Adapter Status]`，说明后端 WebSocket 连通性尚未提供独立 REST 探针。

---

## 3. 安全防护与 Trace 留存

- 全站固定显示 `paper / simulation` 标识。
- 所有 API 请求失败时保留 `status`, `code`, `message`, `trace_id` 信息，不吞掉异常。
- 响应式自适应在 1200px 与 768px 断点下流畅防溢出。

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
  # dist/assets/index-DA5icVS_.js   342.82 kB
  # ✓ built in 548ms
  ```

---

## 5. 修改文件清单

- `frontend/src/pages/Settings.tsx` (强化 Adapter 状态 Demo 降级说明)
- `frontend/PHASE4_PAPER_ADAPTER_UI_REVIEW.md` (本阶段验收报告)
