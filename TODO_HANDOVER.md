# 企业级 AI 量化交易系统（Enterprise AI Quant System）- 开发者交接与待办清单 (TODO & Handover)

> **创建时间**：2026-08-18  
> **项目根目录**：`/root/abc-project`  
> **服务架构**：FastAPI (后端 `uvicorn` systemd 管理) + PostgreSQL 16 (Docker) + Redis 7 (Docker) + Nginx + React 18 / Vite (前端)  
> **当前访问地址**：
> - 前端界面：`http://43.108.98.174/`
> - 后端 API 文档：`http://43.108.98.174/docs`
> - 健康检查：`http://43.108.98.174/health`

---

## 1. 系统当前运行状态与已完成模块 (Status: ~85% Completed)

### 已就绪的基础设施与模块：
1. **持久化与存储**：
   - PostgreSQL 16 容器运行中，Alembic 迁移脚本完整（支持订单、持仓、策略、审计、风控规则等 20 张业务表）。
   - Redis 7 容器运行中，支持分布式锁、事件总线与限流。
2. **模拟交易系统 (Paper Trading)**：
   - 支持多品种现货/合约模拟下单、撮合引擎、逐笔成交回放、持仓记账与每日自动对账。
   - 基础策略引擎：网格策略（Grid）、动量策略（Momentum）、均值回归（Mean Reversion）等原型已就绪。
3. **风控与安全 (Risk & Kill-Switch)**：
   - 包含预检风控规则、紧急一键熔断（Kill-Switch）、双人审批流机制。
4. **前端看板 (Frontend UI)**：
   - React 18 + TypeScript + Tailwind CSS 生产打包完成，Nginx 统一托管。
   - 具备仪表盘、持仓面板、订单管理、风控审批、AI 助手对话窗口。

---

## 2. 待办开发清单 (TODO List for Incoming Developer / AI Agent)

### 🔴 核心待办 1：实盘交易所接入 (Live Exchange Adapters) - 优先级：P0
- [ ] **币安 (Binance) 实盘适配器完善**：
  - 路径：`backend/app/services/exchange/binance_adapter.py`
  - 实现 HMAC-SHA256 签名机制。
  - 对接真实 REST API：下单 (`POST /fapi/v1/order` 或 `/api/v3/order`)、撤单 (`DELETE`)、账户余额查询 (`GET /fapi/v2/account`)、当前持仓查询。
  - 对接真实 WebSocket 行情与订单成交回报推送。
- [ ] **OKX (欧易) 实盘适配器完善**：
  - 路径：`backend/app/services/exchange/okx_adapter.py`
  - 实现 API-KEY + Secret + Passphrase 签名校验。
  - 对接 OKX v5 REST 与 WebSocket 接口。
- [ ] **实盘安全切换开关 (Live Trading Safety Gate)**：
  - 完善从 `is_paper=True` 切换到 `is_paper=False` 时的二级密码/环境变量确认逻辑，防止误操作连接实盘。

---

### 🔴 核心待办 2：深度历史回测引擎 (Advanced Backtesting Engine) - 优先级：P1
- [ ] **历史行情数据管理**：
  - 路径：`backend/app/services/backtest/`
  - 实现 CSV/Parquet 格式的大规模历史 Tick / 1m / 5m / 1h / 1d K 线数据批量导入与存储。
  - 支持从币安/OKX 历史归档接口自动下载补充历史 K 线数据。
- [ ] **撮合与滑点模型增强**：
  - 引入更真实的盘口深度撮合模型（Orderbook-based matching）。
  - 支持固定滑点、百分比滑点以及基于波动率（ATR）的动态滑点模型。
  - 支持 Maker / Taker 差异化手续费率计算与资金费率（Funding Fee）扣除。
- [ ] **量化指标深度计算**：
  - 完善收益率、年化收益率、最大回撤（Max Drawdown）、夏普比率（Sharpe Ratio）、卡玛比率（Calmar Ratio）、索提诺比率（Sortino Ratio）、盈亏比、胜率等指标的精确矩阵计算。
- [ ] **策略参数网格搜索与优化器 (Parameter Grid Search Optimizer)**：
  - 支持多参数组合遍历回测，输出热力图与最优参数建议。

---

### 🟡 核心待办 3：多渠道告警与通知集成 (Notification & Alerting) - 优先级：P2
- [ ] **多平台 Webhook 告警**：
  - 路径：`backend/app/services/notifications/`
  - 企业微信机器人 Webhook 封装（markdown 格式报警卡片）。
  - 飞书 (Feishu/Lark) 自定义机器人 Webhook 封装。
  - 钉钉 (DingTalk) 机器人 Webhook 签名与加签推送。
  - 触发场景：风控熔断触发、大额亏损告警、异常掉线、策略异常报错。

---

### 🟡 核心待办 4：用户认证与权限增强 (Auth & Security) - 优先级：P3
- [ ] 实现标准 OAuth2 / JWT 完整注册与登录流程（当前主要是基于预设账户与 API Key）。
- [ ] 完善 RBAC 细粒度权限控制（交易员 Trader、风控员 Risk Admin、只读审计员 Auditor）。

---

## 3. 开发与测试指南 (Developer Quickstart)

### 环境与路径
- 后端虚拟环境：`/root/abc-project/backend/.venv`
- 激活虚拟环境：`source /root/abc-project/backend/.venv/bin/activate`
- 重启后端服务：`systemctl restart quant.service`
- 查看实时后端日志：`journalctl -u quant.service -f`
- 运行后端自动化测试：
  ```bash
  cd /root/abc-project/backend
  .venv/bin/pytest tests/ -v
  ```
- 前端源码目录：`/root/abc-project/frontend`
- 重新构建前端：
  ```bash
  cd /root/abc-project/frontend
  npm run build
  systemctl reload nginx
  ```
