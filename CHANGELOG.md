# Changelog

All notable changes to Enterprise AI Quant System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] / v0.2.0 - 2026-08-18

### Commit
- **Hash**: `b5ac6e0e5e1ac30e91420b37cf15e2b0aa1ed9e1`
- **Message**: `feat: complete v0.2.0 - E2E testing, adversarial challenger, alpha mining, portfolio optimizer, strategy evolution`
- **Author**: Quant Deploy Bot
- **Stats**: 84 files changed, ~3500 lines added/modified

---

## Added (新增功能 / 32 files)

### Backend Services (新增服务模块)

| 文件 | 说明 |
|------|------|
| `backend/app/services/alpha_mining_service.py` | **Alpha 因子挖掘服务** - 自动化因子发现与评估流水线，支持因子有效性、稳定性、IC 值计算 |
| `backend/app/services/portfolio_optimizer_service.py` | **投资组合优化器** - 风险调整后的多资产配置（均值方差/风险平价/最大分散度） |
| `backend/app/services/strategy_evolution_service.py` | **策略进化引擎** - 基于遗传算法的策略参数优化，支持多代种群进化 |
| `backend/app/services/okx_market_stream.py` | **OKX 行情流** - 实时行情 WebSocket 接入，支持私有频道与公共行情 |
| `backend/app/adapters/websocket_manager.py` | **WebSocket 管理器** - 增强的实时数据推送、断线重连、订阅管理 |

### Frontend Components (新增前端组件)

| 文件 | 说明 |
|------|------|
| `frontend/src/components/AIModelGateway.tsx` | **AI 模型网关** - 统一接入多种 LLM 模型的配置 UI（OpenAI / Claude / 本地模型） |
| `frontend/src/components/ExchangeCredentialsManager.tsx` | **交易所凭证管理** - 加密存储 API Key/Secret，支持多交易所切换 |
| `frontend/src/components/HeartbeatIndicator.tsx` | **心跳指示器** - 实时显示系统/连接/数据流的活跃状态 |
| `frontend/src/utils/formatters.ts` | 通用格式化工具（数字、百分比、时间、货币） |
| `frontend/src/adapters/adapters.ts` | 适配器聚合导出 |
| `frontend/src/adapters/api.ts` | API 客户端适配器 |
| `frontend/src/adapters/index.ts` | 适配器模块入口 |

### Backend Tests (新增测试套件 - 9 files)

| 文件 | 测试范围 |
|------|----------|
| `backend/tests/test_adversarial_challenger.py` | 对抗性鲁棒性测试 - 模拟异常输入、边界条件、攻击场景 |
| `backend/tests/test_alert_webhooks.py` | 告警 Webhook 集成测试（Slack / 钉钉 / 企业微信） |
| `backend/tests/test_alpha_mining.py` | Alpha 因子挖掘单元测试 |
| `backend/tests/test_auth_rbac.py` | 权限与角色访问控制测试 |
| `backend/tests/test_backtest_metrics.py` | 回测指标计算准确性测试 |
| `backend/tests/test_live_exchange.py` | 实盘交易所适配器集成测试 |
| `backend/tests/test_live_market_feeds.py` | 实时行情流测试 |
| `backend/tests/test_portfolio_and_evolution.py` | 组合优化与策略进化测试 |
| `backend/tests/e2e/test_tier1_features.py` | E2E Tier1 - 核心功能端到端 |
| `backend/tests/e2e/test_tier2_boundaries.py` | E2E Tier2 - 边界条件端到端 |
| `backend/tests/e2e/test_tier3_pairwise.py` | E2E Tier3 - 模块两两交互端到端 |
| `backend/tests/e2e/test_tier4_scenarios.py` | E2E Tier4 - 复杂业务场景端到端 |
| `backend/tests/e2e/__init__.py` / `conftest.py` | E2E 测试基础设施 |

### Stress Testing & Audit (新增压测与审计工具 - 7 files)

| 文件 | 说明 |
|------|------|
| `backend/challenger_stress_suite.py` | 压测挑战者套件 - 并发、限流、降级场景 |
| `backend/challenger_stress_results.json` | 压测结果数据 |
| `backend/challenge_results.json` | 挑战赛结果 |
| `backend/stress_harness.py` | 压测执行框架 |
| `backend/run_e2e_tests.py` | E2E 测试运行器 |
| `backend/e2e_test_report.json` | E2E 报告数据 |
| `challenger_e2e_audit_results.json` | E2E 审计结果 |
| `challenger_e2e_deep_audit.py` | E2E 深度审计脚本 |
| `inspect_routes.py` | 路由自检工具 |
| `test_e2e_integration.py` | 集成测试入口 |

### Documentation (新增文档 - 3 files)

| 文件 | 说明 |
|------|------|
| `DEVELOPER_HANDOFF.md` | 开发者交接手册 - 环境搭建、模块说明、调试技巧 |
| `TODO.md` | 项目状态与待办清单（含所有模块完成度） |
| `TODO_HANDOVER.md` | 详细交接指南 - 含已知问题与下一步建议 |

---

## Changed (修改 / 44 files)

### Backend Core (核心代码优化)

| 文件 | 变更内容 |
|------|----------|
| `backend/app/main.py` | FastAPI 启动流程优化、新增中间件、改进异常处理 |
| `backend/app/core/auth.py` | JWT 鉴权增强 - 刷新令牌、token 黑名单、过期处理 |
| `backend/app/core/config.py` | 配置系统重构 - 环境变量校验、热重载、敏感字段加密 |
| `backend/app/core/dependencies.py` | 依赖注入改进 - 复用 DB 会话、统一异常注入 |
| `backend/app/core/secrets.py` | 密钥管理服务化 - 支持多种后端（Vault / 本地 / 环境变量） |
| `backend/app/db/db_store.py` | 数据库访问层重构 - 批量操作、连接池调优、查询优化 |
| `backend/app/db/memory.py` | 内存数据库适配（测试用）增强 |
| `backend/app/strategies/registry.py` | 策略注册表 - 插件化发现、版本管理、热加载 |

### Backend API Layer (API 层)

| 文件 | 变更内容 |
|------|----------|
| `backend/app/api/v1/auth.py` | 登录/注册/刷新/登出流程完善、密码强度校验 |
| `backend/app/api/v1/alert.py` | 告警 API 增强 - 静默规则、升级策略、批量确认 |
| `backend/app/api/v1/framework.py` | 框架管理 API - 插件启用/禁用、配置热更新 |
| `backend/app/api/v1/live.py` | 实盘交易 API - 风控前置、审批流集成、Kill-Switch 检查 |
| `backend/app/api/v1/research.py` | 研究 API - 回测/因子/参数优化统一接口 |
| `backend/app/schemas/adapters.py` | 适配器数据模型扩展 |
| `backend/app/schemas/auth.py` | 认证请求/响应模型增强 |
| `backend/app/schemas/control.py` | 控制台模型 - 审批、Kill-Switch 等 |
| `backend/app/schemas/execution.py` | 执行模型 - 订单、成交、持仓 |
| `backend/app/schemas/research.py` | 研究模型 - 回测任务、因子定义、参数集 |

### Backend Services (服务层)

| 文件 | 变更内容 |
|------|----------|
| `backend/app/services/ai_service.py` | AI 服务增强 - 多模型路由、限流、降级 |
| `backend/app/services/alert_notification_service.py` | 告警通知服务 - 多渠道、降噪、聚合 |
| `backend/app/services/backtest_engine.py` | 回测引擎 - 多账户、滑点模型、撮合优化 |
| `backend/app/services/backtest_service.py` | 回测服务 - 任务调度、进度跟踪、结果缓存 |
| `backend/app/services/control_service.py` | 控制服务 - 紧急操作统一入口 |
| `backend/app/services/credential_service.py` | 凭证服务 - 加密存储、轮换、访问审计 |
| `backend/app/services/historical_data_service.py` | 历史数据服务 - 多源聚合、缓存、增量更新 |
| `backend/app/services/kill_switch_service.py` | Kill Switch 服务 - 触发/恢复/审计 |
| `backend/app/services/live_mode_service.py` | 实盘模式管理 - 模式切换、风险等级 |
| `backend/app/services/market_providers.py` | 行情提供方 - 多交易所适配、故障转移 |
| `backend/app/services/market_service.py` | 行情服务 - 缓存、订阅、广播 |
| `backend/app/adapters/live_exchange_adapters.py` | 实盘交易所适配器 - 统一接口、限频、重试 |

### Backend Tests (测试)

| 文件 | 变更内容 |
|------|----------|
| `backend/tests/test_persistence.py` | 持久化测试增强 - 事务、回滚、并发 |

### Frontend (前端)

| 文件 | 变更内容 |
|------|----------|
| `frontend/src/api.ts` | API 客户端重构 - 类型安全、拦截器、错误处理 |
| `frontend/src/adapters.ts` | 适配器入口更新 |
| `frontend/src/types.ts` | TypeScript 类型扩展 - 与后端 schema 对齐 |
| `frontend/src/styles.css` | 全局样式 - 暗色主题、响应式、动效 |
| `frontend/src/components/Layout.tsx` | 整体布局 - 侧边栏、顶栏、面包屑 |
| `frontend/src/components/Primitives.tsx` | 基础 UI 组件库 - 按钮、表格、对话框 |
| `frontend/src/pages/Agents.tsx` | 智能体页面 - 列表、详情、对话 |
| `frontend/src/pages/Dashboard.tsx` | 仪表盘 - 关键指标、图表、实时数据 |
| `frontend/src/pages/Execution.tsx` | 执行页面 - 订单、成交、持仓 |
| `frontend/src/pages/MarketData.tsx` | 行情页面 - K线、深度、订单流 |
| `frontend/src/pages/Research.tsx` | 研究页面 - 回测、因子、参数优化 |
| `frontend/src/pages/Risk.tsx` | 风控页面 - 限额、审批、Kill-Switch |
| `frontend/src/pages/Settings.tsx` | 设置页面 - 系统配置、用户管理 |

---

## Removed (删除 / 1 file)

| 文件 | 原因 |
|------|------|
| `frontend/src/mockData.ts` | 重构为真实 API 适配，移除前端硬编码 mock 数据。改用 `frontend/src/adapters/` 目录统一管理 |

---

## Statistics (变更统计)

| 类别 | 数量 |
|------|------|
| **总变更文件** | 84 |
| **新增** | 32 (38.1%) |
| **修改** | 44 (52.4%) |
| **删除** | 1 (1.2%) |
| **后端** | 48 文件 |
| **前端** | 17 文件 |
| **测试** | 11 文件 |
| **文档/工具** | 8 文件 |

### By Module

| 模块 | 文件数 | 状态 |
|------|--------|------|
| Alpha Mining | 2 | 🆕 新增 |
| Portfolio Optimizer | 1 | 🆕 新增 |
| Strategy Evolution | 1 | 🆕 新增 |
| OKX Integration | 1 | 🆕 新增 |
| AI Gateway | 1 | 🆕 新增前端组件 |
| Auth/RBAC | 3 | 🔧 增强 |
| E2E Testing | 4 | 🆕 新增 |
| Adversarial Testing | 1 | 🆕 新增 |
| Frontend Pages | 8 | 🔧 重构 |
| Backend Services | 13 | 🔧 增强 |
| Documentation | 3 | 🆕 新增 |

---

## Deployment Notes (部署说明)

### Required Actions (需要执行的操作)

1. **安装新增依赖**（如果 requirements.txt 有更新）：
   ```bash
   cd backend
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **数据库迁移**（如有 schema 变更）：
   ```bash
   alembic upgrade head
   ```

3. **前端重新构建**：
   ```bash
   cd frontend
   npm install
   npm run build
   ```

4. **重启服务**：
   ```bash
   sudo systemctl restart quant
   sudo systemctl reload nginx
   ```

### Verification (验证步骤)

```bash
# 后端健康检查
curl http://43.108.98.174/health
curl http://43.108.98.174/ready

# 前端访问
open http://43.108.98.174/

# E2E 测试
cd backend
.venv/bin/pytest tests/e2e/ -v
```

### Rollback (回滚方案)

```bash
# 回滚到上一版本
cd /root/abc-project
git log --oneline -3
git reset --hard c6361b6
sudo systemctl restart quant
```

---

## Known Issues (已知问题)

参见 [TODO.md](./TODO.md) 第 2-4 节。

## Contributors (贡献者)

- @1535273240sch-droid - 项目所有者
- Quant Deploy Bot - 自动化部署

---

[Unreleased]: https://github.com/1535273240sch-droid/-abc/compare/c6361b6...b5ac6e0
[0.2.0]: https://github.com/1535273240sch-droid/-abc/releases/tag/v0.2.0
