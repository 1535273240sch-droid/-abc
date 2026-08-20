# 更新日志 · UPDATE_LOG

> 本文档记录项目的**每次更新内容**与**具体日期**。
> 每次推送到 GitHub 的内容都会在这里追加一条新记录。

---

## 📅 2026-08-20 · 新增功能：盈亏分析报表 + 专业K线图表

**提交哈希**：`4599ccc`
**Commit 标题**：`feat: add performance analytics report and professional kline chart`

### 🆕 新增：盈亏分析报表（盈亏分析页 `/analytics`）
- 后端新增 `PerformanceAnalyticsService`：聚合成交/持仓/MTM 数据，纯内存计算零负担
- 新 API `GET /api/v1/analytics/performance`：
  - 总盈亏、已实现/未实现盈亏、胜率、盈亏比
  - 夏普比率（年化）、最大回撤、最佳/最差单日、日均盈亏/日波动
  - 每日盈亏序列（MTM 口径）+ 累计盈亏曲线
  - 按币种分解（盈亏、数量、开仓价、现价、成交数、名义额）
- 前端新增「盈亏分析」页面：指标卡片、每日盈亏柱状图、累计盈亏曲线（纯 SVG）、币种明细表、30/90/180 天窗口切换

### 🆕 新增：专业K线图表（K线图表页 `/kline`）
- 集成 klinecharts 9.8（交易所级开源K线库）
- 新 API `GET /api/v1/market/klines`：OHLCV 数据，带过期自动刷新（缓存超过 3 个周期自动从 Binance 拉新，修复了旧回测数据污染缓冲区的问题）
- 6 个周期：1m / 5m / 15m / 1h / 4h / 1d
- 6 个技术指标：MA、VOL、BOLL、MACD、RSI、KDJ（可自由叠加）
- 7 个画线工具：趋势线、射线、水平线、垂直线、矩形、斐波那契、价格线
- 每 6 秒自动刷新最新K线，暗色主题匹配控制台风格

### 🔧 涉及文件（15 个：5 新增 + 10 修改）
- 后端新增：`performance_analytics_service.py`、`api/v1/analytics.py`
- 后端修改：`market.py`（K线端点）、`memory.py` / `db_store.py`（服务接线）、`main.py`（路由注册）
- 前端新增：`KlineChart.tsx`、`Kline.tsx`、`Analytics.tsx`
- 前端修改：`api.ts`、`App.tsx`、`Layout.tsx`（导航）、`styles.css`、`package.json`（klinecharts 依赖）

---

## 📅 2026-08-20 · 仓库大扫除 + 后端优化 + 前端改版

**提交哈希**：`fa90875` + `cb7490a`
**Commit 标题**：`chore: cleanup, update .gitignore, refactor backend services, UI overhaul` + `docs: add Chinese RELEASE_NOTES.md`

### 🧹 清理工作（删除 53 个文件）
- 删除 16 个后端一致性评审文档（Phase 1-13）
- 删除 27 个前端评审/验收文档
- 删除 10 个旧脚本/测试结果（已迁移到 `backend/scripts/dev/`）
- 删除 3 个项目级旧文档（已归档到 `docs-archive/`）

### 🔧 后端服务优化（修改 4 个文件）
- `app/main.py`：生产环境自动隐藏 API 文档
- `app/services/ai_service.py`：新增实时金融上下文（北京时间 + 行情）
- `app/services/credential_service.py`：演示账户可独立控制是否实盘
- `app/adapters/connection_manager.py`：真实调用适配器连接方法

### 🎨 前端全面改版（修改 9 个文件）
- `styles.css`：2012 行重构，统一设计语言
- `Layout.tsx`、`Dashboard.tsx`、`MarketData.tsx`、`Risk.tsx` 等页面升级
- `ExchangeCredentialsManager.tsx` UI 优化
- `index.html` meta 标签优化

### 🚀 部署与运维增强（新增 14 个文件）
- `.pre-commit-config.yaml`：代码质量钩子（ruff + 格式检查）
- `deploy/deploy.sh`：自动化部署脚本（前置测试 + 重启 + 健康检查）
- `deploy/backup.sh`：自动化备份脚本（gzip + 7天清理）
- `docs/OPERATIONS.md`：生产环境 SOP 运维手册
- `deploy/TODO.md`：部署任务清单（本次清理后已重置）
- `backend/scripts/dev/`：开发辅助脚本（OKX 调试、AI 测试等）

### 🔒 安全性改进
- `.gitignore` 新增排除：`deploy/.env`、`backups/`、`docs-archive/`、`*.sql.gz`、`*.bak`
- 生产环境 `/docs`、`/openapi.json` 自动关闭

### 📊 数据
- 文件变更：81 个（+2,242 / -4,628 行）
- 净精简：2,386 行

---

## 📅 2026-08-19 · CHANGELOG 文档完善

**提交哈希**：`9046fdb`
**Commit 标题**：`docs: add CHANGELOG.md with detailed v0.2.0 release notes`

### 📖 新增内容
- 新增 `CHANGELOG.md`（265 行）：v0.2.0 完整变更日志
- 详细列出 32 个新增、44 个修改、1 个删除文件
- 按模块分类：Alpha Mining、Portfolio Optimizer、Strategy Evolution、AI Gateway、E2E 测试
- 包含部署说明、验证步骤、回滚方案

### 📊 数据
- 新增 1 个文件
- 265 行新增

---

## 📅 2026-08-19 · v0.2.0 主要功能完成

**提交哈希**：`b5ac6e0`
**Commit 标题**：`feat: complete v0.2.0 - E2E testing, adversarial challenger, alpha mining, portfolio optimizer, strategy evolution`

### 🆕 新增 32 个文件
**后端服务（5 个）**：
- `alpha_mining_service.py` - Alpha 因子挖掘
- `portfolio_optimizer_service.py` - 投资组合优化器
- `strategy_evolution_service.py` - 策略进化引擎
- `okx_market_stream.py` - OKX 行情流
- `websocket_manager.py` - WebSocket 管理器

**前端组件（3 个）**：
- `AIModelGateway.tsx` - AI 模型网关
- `ExchangeCredentialsManager.tsx` - 交易所凭证管理
- `HeartbeatIndicator.tsx` - 心跳指示器

**测试套件（12 个）**：
- E2E Tier 1-4 端到端测试
- 对抗性鲁棒性测试
- Auth/RBAC、Live Exchange、Market Feeds 测试
- 投资组合与策略进化测试
- Alpha 挖掘、回测指标、告警 Webhook 测试

**文档与工具（12 个）**：
- `DEVELOPER_HANDOFF.md`、`TODO.md`、`TODO_HANDOVER.md`
- 压测与审计工具：challenger_stress_suite、e2e_test_report 等
- 集成测试入口 `test_e2e_integration.py`

### 🔧 修改 44 个文件
- 后端：auth、config、依赖注入、密钥管理重构
- API：auth、alert、framework、live、research 增强
- 服务：11 个 service 文件改进
- 数据库：db_store、memory 优化
- 前端：api.ts、types.ts、styles.css 重构，8 个页面更新

### 🗑️ 删除 1 个文件
- `frontend/src/mockData.ts`（改为真实 API 适配）

### 📊 数据
- 文件变更：84 个
- 净增大量代码（v0.2.0 主要功能版本）

---

## 📅 2026-08-17 · 项目初始化

**提交哈希**：`7aeae13` + `c6361b6`
**Commit 标题**：`Initial commit: Enterprise AI Quant System v0.2.0` + `docs: add project overview and full deployment guide README`

### 🆕 初始化内容
- 完整后端（FastAPI + SQLAlchemy + Alembic + Celery + Pydantic v2）
- 完整前端（Vite + TypeScript SPA）
- 基础设施（PostgreSQL 16 + Redis 7 + Nginx + Docker Compose）
- 部署手册（混合架构：Docker 跑基础设施 + systemd 跑后端 + Nginx 反代前端）
- 模拟交易系统、风控体系、审批治理、对账系统
- 交易所适配（Binance / Coinbase / OKX）+ 模拟盘

### 📊 数据
- 初始 commit：项目骨架

---

## 📝 待办事项跟踪

> 本节记录**未来需要完成**的事项。每次更新时检查并勾选完成项。

### 🔴 P0 - 最高优先级
- [ ] 修改数据库密码（原密码已暴露在对话中）
- [ ] 修改 Redis 密码（原密码已暴露在对话中）
- [ ] 修改 SSH root 密码
- [ ] 撤销 GitHub Personal Access Token

### 🟡 P1 - 高优先级
- [ ] 配置 SSH 密钥认证（禁用密码登录）
- [ ] 设置 fail2ban 自动封禁异常 IP
- [ ] 启用 HTTPS（Let's Encrypt 证书）
- [ ] 配置自动备份 cron（每天 03:00 执行 backup.sh）
- [ ] 配置自动部署 webhook（push 触发 deploy.sh）

### 🟢 P2 - 优化项
- [ ] 升级服务器内存（当前 896MB，1C，容易 OOM）
- [ ] 添加 Prometheus + Grafana 监控
- [ ] 添加 ELK 日志聚合
- [ ] 多环境配置（dev / staging / production）
- [ ] 完善 E2E 测试覆盖率

### 🔵 P3 - 体验改进
- [ ] 添加用户引导（Onboarding）
- [ ] 移动端响应式优化
- [ ] 多语言支持（中/英）
- [ ] 暗色模式

---

> 💡 **使用说明**：每次推送新内容到 GitHub 后，我会自动在本文件顶部追加新记录。
> 格式：日期 + 提交哈希 + Commit 标题 + 分类变更（清理/优化/新增/删除）
