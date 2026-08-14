# Enterprise AI Quant System — 项目说明与待办事项

> 文档更新日期：2026-08-13  
> 当前版本：v0.2.0  
> 综合成熟度评分：90%（企业级）

---

## 一、项目概述

本系统是一个企业级 AI 量化交易平台，提供从策略管理到模拟交易的全流程能力。

### 核心能力

| 模块 | 说明 |
|------|------|
| 订单生命周期 | 风控预检 → 下单 → 成交 → 持仓记账 → 对账 |
| 风控体系 | max_notional / 正数量校验 / 最小下单量 / 行情质量门 / Kill Switch |
| 策略引擎 | 可插拔策略引擎（趋势跟踪 / 套利 / 网格）+ 注册表模式 |
| 治理审批 | 审批工作流（创建→审批→过期清理）+ Kill Switch 恢复需审批 |
| 对账 | 持仓 vs 订单一致性校验 + 差异解决记录 |
| 行情数据 | 多源行情提供者（Binance / Coinbase / OKX）+ 自动容灾切换 |

---

## 二、已完成的工程改造

### P0（最高优先级 — 已完成）

#### P0-1：数据库层重构

- **新建 `app/db/database.py`** — SQLAlchemy 2.0 引擎、会话工厂、连接池（pool_size=10, max_overflow=20）
- **新建 `app/db/orm_models.py`** — 20 张关系表的 ORM 模型，覆盖全部领域对象
- **新建 `app/db/db_store.py`** — 数据库后端存储，继承 `InMemoryStore` 接口，零代码改动切换
- **新建 `alembic/`** — 数据库迁移框架 + 初始 schema 迁移脚本（0001）
- **修改 `app/db/memory.py`** — `get_store()` 根据 `storage_backend` 配置自动选择 InMemoryStore 或 DBStore
- **修改 `app/core/config.py`** — 新增企业基础设施配置项（日志、限流、OTel、Celery、Sentry 等）

**涉及表结构：**
```
orders, fill_records, risk_decisions, positions, strategies, strategy_runs,
symbols, tickers, audit_events, reconciliation_logs, resolution_records,
approvals, kill_switch_state, backtests, portfolio_targets, agent_tasks,
alerts, exchange_connections, ai_model_providers, mtm_logs
```

#### P0-2：容器化部署

- **新建 `Dockerfile`** — 多阶段构建，非 root 用户运行，内置 HEALTHCHECK
- **新建 `docker-compose.yml`** — 6 个服务完整编排：
  - `app` — FastAPI 应用（gunicorn + 4 个 uvicorn worker）
  - `worker` — Celery 异步任务执行器
  - `beat` — Celery 定时任务调度器
  - `postgres` — PostgreSQL 16 数据库
  - `redis` — Redis 7（事件总线 + 缓存 + Celery broker）
  - `nginx` — Nginx 反向代理（TLS 终结 + 限流 + 安全头）
- **新建 `deploy/nginx.conf`** — 完整 Nginx 配置：TLS 1.2/1.3、HSTS、API 限流（30r/s）、认证限流（5r/s）、WebSocket 支持
- **新建 `.dockerignore`** — 构建上下文优化
- **新建 `.env.example`** — 完整环境变量模板（含所有配置项说明）

#### P0-3：CI/CD 流水线

- **新建 `.github/workflows/ci.yml`** — GitHub Actions 4 阶段流水线：
  1. **Lint** — ruff 代码检查 + 格式校验 + mypy 类型检查
  2. **Security** — bandit SAST 扫描 + pip-audit 依赖漏洞扫描
  3. **Test** — PostgreSQL + Redis 服务容器 + pytest 全量测试 + 覆盖率报告
  4. **Build & Deploy** — Docker 镜像构建推送 + Tag 触发 SSH 部署

---

### P1（高优先级 — 已完成）

#### P1-1：可观测性增强

- **新建 `app/core/logging.py`**
  - structlog JSON 结构化日志（含 timestamp、request_id、logger、level）
  - 请求上下文绑定（bind_request_context / clear_request_context）
  - 标准 logging 回退模式（无 structlog 时自动降级）
  - Sentry 错误追踪集成（可选）
  - 日志文件轮转支持
- **新建 `app/observability/tracing.py`**
  - OpenTelemetry 分布式追踪
  - HTTP 请求 span 自动注入
  - 无 OTel 时 no-op 回退
- **新建 `app/observability/health.py`**
  - `/health` — Liveness 探针（进程是否存活）
  - `/health/ready` — Readiness 探针（依赖是否就绪：DB / Redis / Kill Switch）
  - `/health/info` — 系统信息（版本、模式、Python 版本、运行时间、PID）

#### P1-2：安全增强

- **新建 `app/core/rate_limit.py`**
  - 令牌桶算法限流（InMemoryRateLimiter — 单机模式）
  - Redis 滑动窗口限流（RedisRateLimiter — 分布式模式）
  - 自动选择：Redis 配置时用分布式，否则用本地
  - 限流维度：按用户 ID 或 IP 地址
  - 默认：120 RPM，burst 20
- **新建 `app/core/api_key.py`**
  - HMAC-SHA256 签名 API Key 生成与验证
  - 格式：`qak.<key_id>.<body>.<signature>`
  - 用于服务间认证（交易机器人、仪表盘、CI/CD）
- **修改 `app/main.py` 中间件**
  - 认证中间件支持 JWT + API Key 双模式
  - 限流中间件在每个 `/api/v1` 请求前检查
  - 日志上下文自动绑定/清理
  - 追踪 span 自动创建

#### P1-3：分布式架构

- **新建 `app/core/distributed_lock.py`**
  - Redis 分布式锁（SET NX EX + Lua 脚本释放）
  - 本地 RLock 回退（单机模式）
  - 上下文管理器接口：`with distributed_lock("name"):`
- **新建 `app/tasks/celery_app.py`**
  - Celery 应用配置
  - Beat 定时任务：策略调度（每 5 分钟）、行情刷新（每 15 秒）、对账（每 5 分钟）、审批过期清理（每 2 分钟）
  - 可靠性配置：acks_late、retry、task_time_limit=300s
- **新建 `app/tasks/tasks.py`**
  - 5 个异步任务定义：run_scheduled_strategies / refresh_market_data / run_reconciliation / sweep_expired_approvals / execute_order

#### P1-4：文档

- **新建 `README.md`** — 完整项目文档：
  - 架构图 + 目录结构
  - 快速启动（Docker Compose + 本地开发）
  - 配置参考（环境变量表）
  - 部署手册 + 生产环境检查清单
  - API 端点参考
  - 测试说明
  - 可观测性指南（日志 / 指标 / 追踪 / 健康检查）
  - 安全说明（认证 / RBAC / 安全头 / 限流 / SSRF）
  - 开发指南（代码质量 / 迁移 / 策略引擎扩展）

---

### P2（之前已完成的改进）

| 编号 | 任务 | 状态 |
|------|------|------|
| P2.10 | 统一错误码（`INVALID_INPUT` → `VALIDATION_ERROR`） | ✅ |
| P2.8 | 可插拔策略引擎（`StrategyEngine` + `StrategyEngineRegistry`） | ✅ |
| P2.9 | `RedisEventBus` 消费者组 + DLQ 死信队列 | ✅ |
| P2.12 | `MultiSourceMarketProvider` 多源行情容灾 | ✅ |
| P2.11 | 完整单元测试套件（`test_p2_improvements.py`） | ✅ |

---

## 三、当前测试状态

```
======================== 251 passed, 1 warning in 2.19s ========================
```

251 个测试全部通过，零回归。

---

## 四、服务器运行状态

- **应用路径**：`/home/ubuntu/backend/`
- **虚拟环境**：`/home/ubuntu/backend/.venv/`（Python 3.14.4）
- **运行进程**：`uvicorn app.main:app --host 127.0.0.1 --port 8000`
- **日志文件**：`/tmp/uvicorn.log`
- **日志格式**：JSON 结构化（structlog）

### 健康检查

```bash
curl http://127.0.0.1:8000/health        # → {"status":"ok","timestamp":...}
curl http://127.0.0.1:8000/health/ready  # → {"status":"ready","checks":{...}}
curl http://127.0.0.1:8000/health/info   # → {app_name, version, python_version, uptime...}
```

---

## 五、待办事项

### 🔴 P2-0：策略框架数据链路与运行时接入（2026-08-13 新增，最阻塞）

**当前状态**：新一代可插拔策略框架（`app/strategies/`）已搭建并验证通过（声明式参数 Schema / 指标引擎 / 信号系统 / 仓位管理 / 自动发现），但**尚未接入运行时**，且策略声明的 `warmup_bars` 历史 K 线数据无来源——策略目前是瞎子。

**需要做的**：
- [ ] 实现 `KlineService`（历史 K 线拉取 → PostgreSQL 存储 → 增量更新），喂给策略框架的 `kline_provider`
- [ ] 历史 K 线表结构（`historical_klines`：symbol / period / open_time / OHLCV，联合唯一索引）
- [ ] 将 `FrameworkRunner` 接入现有策略调度器（Celery Beat 每 5 分钟任务），与旧引擎并行运行、按 kind 逐步替换
- [ ] 策略框架 API 暴露（策略目录 catalog / 参数 Schema 查询 / 手动触发运行）
- [ ] 策略私有状态持久化（`ctx.state` 接入 store 持久化字段，重启不丢）
- [ ] 真实数据验证：双均线策略在真实 K 线上跑 Paper，核对信号与指标值正确性

**依赖**：币安公共 K 线 API（无需密钥）；PostgreSQL 存储启用

---

### 🔴 P2-1：实盘交易所适配器（Binance / Coinbase / OKX 真实接口）

**当前状态**：仅有 `PaperExchangeAdapter`（模拟成交），Live 模式被硬编码拒绝。

**需要做的**：
- [ ] 实现 `BinanceExchangeAdapter` — REST API 下单 + WebSocket 行情
- [ ] 实现 `CoinbaseExchangeAdapter` — REST API 下单 + WebSocket 行情
- [ ] 实现 `OKXExchangeAdapter` — REST API 下单 + WebSocket 行情
- [ ] 适配器密钥管理（API Key / Secret 存储到数据库或 Vault）
- [ ] 解除 `RiskService.preflight` 中的 Live 模式硬编码拒绝
- [ ] 解除 `OrderService._assert_paper_only` 的 Paper-only 限制
- [ ] 实盘交易权限审批流程（`ApprovalResourceType.LIVE_SWITCH`）
- [ ] 实盘模式下订单状态回调（WebSocket 推送 → 状态机推进）
- [ ] 实盘风控增强（最大持仓限制、最大回撤熔断、资金费率监控）
- [ ] 账户真实余额校验（下单前查询交易所可用余额，不足直接拒单）
- [ ] 本地账本 vs 交易所实际持仓的每日自动对账（不一致立即告警并冻结新开仓）
- [ ] 异常告警通知闭环（Telegram / 邮件：拒单、对账差异、Kill Switch 触发、进程异常）——实盘保命项，非可选项
- [ ] 小额实盘验证阶段（100-500 USDT / 单策略 / 跑稳 1 个月无事故后再逐步加仓）

**依赖**：ccxt 库或各交易所官方 SDK

---

### 🟡 P2-2：回测引擎增强（历史数据驱动 + 参数优化）

**当前状态**：有 `BacktestService` 框架但无真实历史数据驱动。

**需要做的**：
- [ ] 历史行情数据存储（PostgreSQL `historical_ohlc` 表）
- [ ] 历史数据导入工具（从 Binance / CSV 文件批量导入）
- [ ] 回测引擎核心（逐 K 线驱动策略引擎 + 撮合模拟）
- [ ] 滑点模型（基于历史盘口深度的滑点估算）
- [ ] 手续费模型（maker / taker 费率 + 阶梯费率）
- [ ] 资金管理模型（初始资金 + 杠杆 + 保证金）
- [ ] 回测报告（净值曲线、最大回撤、夏普比率、胜率、盈亏比）
- [ ] 参数优化（网格搜索 / 贝叶斯优化 / 遗传算法）
- [ ] 回测 vs 实盘一致性校验

**依赖**：pandas、numpy、matplotlib（报告图表）

---

### 🟢 后续优化建议（非阻塞）

- [ ] 用户管理模块（多用户注册 / 登录 / 权限分配）
- [ ] OAuth2 / OIDC 集成（企业 SSO 单点登录）
- [ ] 前端仪表盘（React / Vue 量化监控面板）
- [ ] WebSocket 实时推送（行情、订单状态、持仓变化）
- [ ] 通知系统（邮件 / 钉钉 / 企业微信 告警通知）
- [ ] 多租户隔离（按账户 / 策略隔离数据）
- [ ] 数据归档策略（历史 tickers / audit_events 定期归档）
- [ ] Kubernetes 部署（Helm Chart + HPA 自动伸缩）
- [ ] 灾备方案（数据库主从复制 + Redis 哨兵集群）
- [ ] 合规报告（SOX / MiFID 审计报告自动生成）

---

## 六、关键文件索引

| 类别 | 路径 | 说明 |
|------|------|------|
| 入口 | `app/main.py` | FastAPI 应用、中间件、生命周期 |
| 配置 | `app/core/config.py` | 全局配置 + 生产环境校验 |
| 认证 | `app/core/auth.py` | JWT + RBAC（4 角色） |
| API Key | `app/core/api_key.py` | HMAC 签名 API Key |
| 限流 | `app/core/rate_limit.py` | 令牌桶限流 |
| 分布式锁 | `app/core/distributed_lock.py` | Redis 分布式锁 |
| 日志 | `app/core/logging.py` | structlog JSON 日志 |
| 追踪 | `app/observability/tracing.py` | OpenTelemetry |
| 健康检查 | `app/observability/health.py` | 三级健康探针 |
| 指标 | `app/observability/metrics.py` | Prometheus 指标 |
| 内存存储 | `app/db/memory.py` | InMemoryStore（开发/测试） |
| 数据库存储 | `app/db/db_store.py` | DBStore（生产） |
| ORM 模型 | `app/db/orm_models.py` | 20 张表的 SQLAlchemy 模型 |
| 数据库引擎 | `app/db/database.py` | 引擎 + 会话 + 连接池 |
| 迁移 | `alembic/` | Alembic 迁移工具 |
| 异步任务 | `app/tasks/` | Celery 应用 + 任务定义 |
| 领域模型 | `app/models/domain.py` | 12 个领域对象 |
| 枚举 | `app/models/enums.py` | 16 个枚举类型 |
| 服务层 | `app/services/` | 15+ 业务服务 |
| API 路由 | `app/api/v1/` | 20+ 路由模块 |
| 适配器 | `app/adapters/` | 交易所适配器协议 + 实现 |
| 事件总线 | `app/events/bus.py` | 内存 + Redis Streams |
| 测试 | `tests/` | 251 个单元测试 |

---

## 七、环境变量速查

```bash
# 核心
QUANT_ENVIRONMENT=production       # development | production
QUANT_MODE=paper                   # paper | live
QUANT_AUTH_ENABLED=true
QUANT_AUTH_SECRET=<32+字符随机串>
QUANT_AUTH_ADMIN_PASSWORD=<12+字符密码>

# 数据库
QUANT_STORAGE_ENABLED=true
QUANT_STORAGE_BACKEND=postgres
QUANT_POSTGRES_DSN=postgresql://user:pass@host:5432/quant

# Redis
QUANT_REDIS_URL=redis://host:6379/0
QUANT_EVENT_BACKEND=redis

# 可观测性
QUANT_LOG_FORMAT=json
QUANT_LOG_LEVEL=INFO
QUANT_OTEL_ENABLED=true
QUANT_OTEL_ENDPOINT=http://otel:4317
QUANT_SENTRY_DSN=https://xxx@sentry.io/xxx

# 限流
QUANT_RATE_LIMIT_ENABLED=true
QUANT_RATE_LIMIT_RPM=120

# Celery
QUANT_ENABLE_CELERY=true
QUANT_CELERY_BROKER_URL=redis://host:6379/1
QUANT_CELERY_RESULT_BACKEND=redis://host:6379/2
```

---

## 八、常用操作

```bash
# 启动开发环境
cd /home/ubuntu/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试
.venv/bin/python -m pytest tests/ -v

# 数据库迁移
.venv/bin/alembic upgrade head          # 应用迁移
.venv/bin/alembic revision --autogenerate -m "描述"  # 生成新迁移
.venv/bin/alembic current               # 查看当前版本

# Docker 部署
docker compose up -d                    # 启动全部服务
docker compose exec app alembic upgrade head  # 运行迁移
docker compose logs -f app              # 查看日志
docker compose down                     # 停止

# 健康检查
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
curl http://localhost:8000/health/info
```
