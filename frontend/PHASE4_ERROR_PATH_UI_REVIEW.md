# 企业级 AI 加密量化交易控制台 Phase 4 Adapter 断开态错误路径 UI 回归报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第十三阶段 Adapter 断开态（Disconnected State）错误路径回归、503 `ADAPTER_NOT_CONNECTED` 状态透传与 UI 构建验证结果。

---

## 1. 错误路径契约与 UI 呈现

后端 Adapter 默认处于 `disconnected` 状态时，请求具体适配器符号列表 `/api/v1/adapters/{name}/symbols` 将触发统一错误模型：

- **HTTP 响应码**：`503 Service Unavailable` 或 `404 Not Found`
- **错误 JSON Payload**：
  ```json
  {
    "error": {
      "code": "ADAPTER_NOT_CONNECTED",
      "message": "Adapter binance is disconnected",
      "details": { "adapter": "binance", "status": "disconnected" }
    },
    "trace_id": "req-94812a7f"
  }
  ```
- **前端 `MarketData.tsx` 捕获呈现**：
  - 提取 `status`, `code`, `message`, `traceId` 挂载至 `apiErrorDetail` 状态。
  - 渲染警告条：`⚠ 行情端点断开 [HTTP 503]: ADAPTER_NOT_CONNECTED - Market symbols feed offline (trace_id: req-94812a7f) · 已降级为 Demo/Mock`。

---

## 2. 语义隔离与防混淆核查

1. **健康度 200 与行情 503 解耦**：
   - `Settings.tsx` 中的 `GET /api/v1/adapters` 返回 200 OK 并列出适配器为 `status: disconnected`，代表连接探针可达但未开启流数据。
   - `MarketData.tsx` 在收到行情 503/404 时独立呈现 `ADAPTER_NOT_CONNECTED`，不影响系统总体配置控制台。
2. **只读防线**：
   - 遭遇断开态时，前端自动降级为安全的 `Demo / Mock` 视图，绝不自动调用 `POST /api/v1/adapters/{name}/connect` 破坏审批门与风控。

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
  # dist/assets/index-BVVomMVT.js   344.12 kB
  # ✓ built in 451ms
  ```

---

## 4. 文件变动清单

- `frontend/src/pages/MarketData.tsx` (增强 503 `ADAPTER_NOT_CONNECTED` 与 `trace_id` 错误信息捕获与显式渲染)
- `frontend/PHASE4_ERROR_PATH_UI_REVIEW.md` (本阶段错误路径回归报告)
