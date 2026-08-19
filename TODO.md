# 量化交易系统开发交接与待办事项 (TODO / Roadmap)

本文档由开发环境自动生成，记录了当前云服务器上的系统现状、已完成功能以及后续接手 AI / 开发者需要继续推进的待办清单。

---

## 一、系统当前环境信息
- **部署路径**：`/root/abc-project`
  - 后端：`/root/abc-project/backend` (FastAPI + Python 3.11, systemd 服务: `quant.service`)
  - 前端：`/root/abc-project/frontend` (React 18 + Vite, 编译产物在 `dist/`, Nginx 代理)
- **运行组件**：
  - PostgreSQL 16 (Docker: `quant_postgres_dev`)
  - Redis 7 (Docker: `quant_redis_dev`)
  - Nginx (80 端口，统一反向代理前端与 API)
- **在线访问**：
  - 前端界面：`http://43.108.98.174/`
  - Swagger 接口文档：`http://43.108.98.174/docs`
  - 系统健康检查：`http://43.108.98.174/health`

---

## 二、已完成功能 (Completed)

1. **基础架构与持久化**
   - 20 张业务核心数据表（订单、持仓、成交、策略、风控日志、审批流等）。
   - PostgreSQL 异步存储与内存缓存双向同步机制 (`DBStore`)。
   - Redis 分布式锁、限流器与事件总线。
   - 三级健康检查与 Prometheus 指标上报。

2. **模拟交易与撮合引擎 (Paper Trading)**
   - 逐笔成交撮合与滑点/手续费计算。
   - 预设策略模板（EMA 趋势、动量网格、跨市套利策略）。
   - 实时风控拦截、熔断开关 (Kill-Switch) 与多级审批流程。

3. **前端控制台与可视化**
   - 仪表盘、订单管理、持仓明细、风控日志、策略管理界面。
   - AI 对话与意图分析控制台。

---

## 三、待接手 AI / 开发者完成的待办事项 (TODO List)

### 🔴 优先级 P0：实盘交易所适配接入 (Live Exchange Adapters)
- [ ] **币安 (Binance) 现货/合约 API 对接**
  - 文件参考：`app/engine/adapters/binance_adapter.py`
  - 实现 HMAC-SHA256 签名、下单 (`POST /api/v3/order`)、撤单、查询余额与持仓。
  - 实现 Binance WebSocket 实时行情与订单状态推送（`wss://stream.binance.com`）。
- [ ] **OKX 现货/合约 API 对接**
  - 实现 OKX V5 签名规范（Passphrase + Timestamp + Base64 签名）。
  - 实现 OKX 批量下单、快速撤单与逐仓/全仓保证金模式适配。
- [ ] **实盘交易模式切换安全守卫**
  - 完善 `app/config.py` 中的 `TRADE_MODE=live` 切换与前置硬件/资金风控校验。

### 🟡 优先级 P1：高级回测引擎与历史数据驱动 (Backtest & Data Pipeline)
- [ ] **历史大周期 K 线/Tick 数据自动下载器**
  - 实现从 Binance/OKX 公共归档数据源批量拉取 1m/5m/1h K 线并入库（PostgreSQL/TimescaleDB/Parquet）。
- [ ] **多参数组合网格搜索与策略参数优化器 (Optimizer)**
  - 支持网格搜索 (Grid Search) 与遗传算法优化，输出最优夏普比率参数矩阵。
- [ ] **资金费率与深度盘口滑点模型**
  - 针对高杠杆合约交易，在回测中引入动态资金费率 (Funding Rate) 扣除与多档订单薄冲击滑点。

### 🟢 优先级 P2：多渠道通知与多租户用户体系 (Notification & Multi-Tenancy)
- [ ] **企业微信 / 飞书 / 钉钉 Webhook 告警集成**
  - 补齐熔断触发、大额强平风险时的即时消息群机器人推送。
- [ ] **多用户系统与权限隔离 (RBAC / OAuth2)**
  - 实现 JWT 认证、用户注册登录、多账户策略与资产完全隔离。

---

## 四、接手开发指引 (Quick Start for Developers)

1. 进入后端目录：
   ```bash
   cd /root/abc-project/backend
   source .venv/bin/activate
   ```
2. 运行自动化测试：
   ```bash
   pytest tests/ -v
   ```
3. 重启后端服务：
   ```bash
   systemctl restart quant.service
   systemctl status quant.service
   ```
4. 重新构建前端（如有修改前端代码）：
   ```bash
   cd /root/abc-project/frontend
   npm run build
   ```