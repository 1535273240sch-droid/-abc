# 企业级 AI 加密量化交易控制台 UX 与交互验收报告

本报告由多模态前端 Agent（Antigravity/Gemini）编写，记录第三阶段控制台 Agent/风险交互收口、视觉体验自适应与构建验收结果。

---

## 1. UX 收口与修正明细

1. **Agent 控制台收口 (`Agents.tsx`)**：
   - 为 Agent 任务队列、步骤证据链（Evidence Chain）、工具权限矩阵及人工审批门增加了明确的 Banner 提示：
     `⚠ 说明：后端 Agent 编排微服务 (agent_orchestrator) 尚未对外暴露 API；本页面当前为 [Demo / Mock 静态推演视图]`
   - 确保完全符合不伪装“已连接真实 Agent 编排后端”的验收标准。

2. **风控中心收口 (`Risk.tsx`)**：
   - 明确区分真实的 `POST /api/v1/risk/preflight` API 模拟测试与 Demo 预置的风控规则/熔断数据。
   - 确认 Preflight Simulator 请求固定为 `mode: "paper"`，不触发任何真实或纸面下单，仅输出决策授权结果。

3. **全站文案规范审查**：
   - 确认全部页面均无“实盘已连接”、“真实成交”、“已执行真实 Agent 动作”等模糊误导表述，统一保持 `paper / simulation / Demo` 标准。

---

## 2. 仍待后端扩展支持的功能

| 控制台功能模块 | 当前前端呈现形式 | 待后端支持的 API 扩展 |
|---|---|---|
| **Agent 编排与证据链** | Demo / Mock 静态证据链与推演 | 待 `agent_orchestrator` 提供任务列表与日志查询端点 |
| **L2 盘口与逐笔成交流** | Demo 模拟 Orderbook Viewer | 待 Market Data 模块提供 WebSocket/REST L2 深度端点 |
| **策略动态回测与归因** | Demo 样本外回测指标与 Equity 曲线 | 待 Research 模块提供回测提交与报告查询端点 |
| **自动化对账服务** | Demo 对账结果与差异记录 | 待 Execution 模块提供差异审计与修正端点 |

---

## 3. 视觉与多模态交互验收

- **高密度暗黑金融科技主题**：布局稳定，主题色 `#090B0E` / `#14181F`，数据对齐度高。
- **等宽数字与表格防溢出**：全站数值字段应用 `font-variant-numeric: tabular-nums`；表格包裹 `.data-table-wrap` 支持横向平滑滚动。
- **响应式断点自适应**：在 1200px 与 768px 断点下，卡片与网格自动折叠重排，保证窄屏可读性。
- **生产构建隔离**：开发调窗按钮仅在 `import.meta.env.DEV` 下渲染，构建包已自动剥离。

---

## 4. 构建与验证结果

- **TypeScript 编译校验**：
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
  # dist/assets/index-IhrrEml3.js   335.22 kB
  # ✓ built in 568ms
  ```
