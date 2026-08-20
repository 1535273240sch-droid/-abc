# 更新说明书（中文版）· RELEASE_NOTES

> **企业级 AI 量化交易系统** · v0.2.0 → v0.2.1 更新记录
> **更新日期**：2026-08-20
> **提交哈希**：`fa90875`
> **作者**：Quant Deploy Bot

---

## 一、本次更新总览

本次更新是一次**综合性维护更新**，主要包含三大方向：

1. **🧹 仓库大扫除** —— 清理 53 个过时的评审/测试/挑战赛文档
2. **🔧 后端服务优化** —— 改进 AI 服务、生产环境配置、连接管理
3. **🎨 前端全面改版** —— 样式重构、布局优化、多个页面升级
4. **🚀 部署与运维增强** —— 新增部署/备份脚本、运维手册、代码质量钩子

### 变更统计

| 指标 | 数值 |
|------|------|
| 文件总数变更 | 81 个 |
| 新增 | 14 个 |
| 修改 | 14 个 |
| 删除 | 53 个 |
| 新增代码 | +2,242 行 |
| 删除代码 | -4,628 行 |
| 净变化 | -2,386 行（精简） |

---

## 二、🧹 清理工作（删除 53 个文件）

### 2.1 后端评审文档清理（16 个）

| 删除文件 | 用途说明 |
|----------|----------|
| `backend/ARCHITECTURE_CONFORMANCE_REVIEW.md` | 架构一致性评审 |
| `backend/PAPER_ADAPTER_CONFORMANCE_REVIEW.md` | 模拟盘适配器评审 |
| `backend/PAPER_ADAPTER_RECONCILIATION_CONFORMANCE_REVIEW.md` | 模拟盘对账评审 |
| `backend/PAPER_EXECUTION_CONFORMANCE_REVIEW.md` | 模拟盘执行评审 |
| `backend/PHASE2_RESEARCH_CONFORMANCE_REVIEW.md` | 第二阶段研究评审 |
| `backend/PHASE3_MARK_TO_MARKET_PNL_CONFORMANCE_REVIEW.md` | 阶段3 标记市价盈亏评审 |
| `backend/PHASE3_PORTFOLIO_TARGET_CONFORMANCE_REVIEW.md` | 阶段3 组合目标评审 |
| `backend/PHASE4_APPROVAL_EXPIRY_AUDIT_PROJECTION_CONFORMANCE_REVIEW.md` | 阶段4 审批过期审计 |
| `backend/PHASE4_APPROVAL_EXPIRY_LIFECYCLE_CONFORMANCE_REVIEW.md` | 阶段4 审批过期生命周期 |
| `backend/PHASE4_KILL_SWITCH_ATOMICITY_CONFORMANCE_REVIEW.md` | 阶段4 紧急熔断原子性 |
| `backend/PHASE4_KILL_SWITCH_RECOVERY_APPROVAL_CONFORMANCE_REVIEW.md` | 阶段4 紧急熔断恢复审批 |
| `backend/PHASE4_RECONCILIATION_RESOLUTION_CONFORMANCE_REVIEW.md` | 阶段4 对账解决方案 |
| `backend/PRODUCTION_GUARDRAILS_CONFORMANCE_REVIEW.md` | 生产守门员评审 |
| `backend/RESEARCH_CONFORMANCE_REVIEW.md` | 研究模块评审 |

### 2.2 后端脚本与报告清理（10 个，已迁移到 `scripts/dev/`）

| 删除文件 | 迁移位置 |
|----------|----------|
| `backend/challenge_results.json` | `backend/scripts/dev/challenge_results.json` |
| `backend/challenger_stress_results.json` | `backend/scripts/dev/challenger_stress_results.json` |
| `backend/challenger_stress_suite.py` | `backend/scripts/dev/challenger_stress_suite.py` |
| `backend/e2e_test_report.json` | `backend/scripts/dev/e2e_test_report.json` |
| `backend/install_framework.py` | `backend/scripts/dev/install_framework.py` |
| `backend/run_e2e_tests.py` | `backend/scripts/dev/run_e2e_tests.py` |
| `backend/stress_harness.py` | `backend/scripts/dev/stress_harness.py` |
| `backend/verify_all.py` | `backend/scripts/dev/verify_all.py` |
| `backend/verify_framework.py` | `backend/scripts/dev/verify_framework.py` |

### 2.3 前端评审文档清理（27 个）

| 类别 | 文件数 | 说明 |
|------|--------|------|
| 总评审类 | 8 个 | `FINAL_*` `INTEGRATION_*` `CONSOLE_*` 等 |
| 阶段评审类 | 15 个 | `PHASE4_*` 至 `PHASE13_*` |
| 任务/反馈类 | 4 个 | `ASSIGNMENT.md` `REVIEW_FEEDBACK.md` 等 |

**清理原因**：这些是一次性的内部评审记录，已通过归档（`docs-archive/`）保存，不再纳入主仓库以保持结构清晰。

### 2.4 项目级文档清理（3 个）

- `DEVELOPER_HANDOFF.md`（开发者交接手册）
- `TODO.md`（项目待办清单）
- `TODO_HANDOVER.md`（详细交接指南）

> 💡 新的运维手册已整合到 `docs/OPERATIONS.md`，内容更全面、结构更清晰。

---

## 三、🔧 后端服务优化（修改 4 个文件）

### 3.1 `backend/app/main.py` · 13 行变更

**改进点**：生产环境 API 文档自动隐藏

```python
# 之前：API 文档永远暴露
app = FastAPI(title=..., version=..., lifespan=lifespan)

# 之后：生产环境自动关闭 /docs 和 /openapi.json
docs_url = "/docs" if (settings.environment.lower() not in {"production", "prod"} or settings.debug) else None
redoc_url = "/redoc" if (...) else None
openapi_url = "/openapi.json" if (...) else None

app = FastAPI(..., docs_url=docs_url, redoc_url=redoc_url, openapi_url=openapi_url)
```

**好处**：
- ✅ 生产环境不再泄露 API 文档
- ✅ 减少被恶意探测攻击面
- ✅ 调试模式下仍可访问

### 3.2 `backend/app/services/ai_service.py` · 58 行变更

**改进点**：AI 助手具备实时金融上下文

新增 `_build_system_context()` 方法，给 AI 大模型提供：
- **当前时间**（北京时间 UTC+8 格式）
- **实时行情数据**（从 `market_service` 获取最新报价）
- **最多 8 个交易对**的实时价格

```python
# 之前：AI 没有实时数据，回答可能过时
# 之后：每次对话都有最新市场行情作为上下文
cst_time_str = f"{now_utc.year}年{now_utc.month:02d}月{...}日 {cst_hour:02d}:... (北京时间 UTC+8)"
tickers = self._store.market_service.get_tickers()
for t in tickers[:8]:
    market_lines.append(f"- {t['symbol']}: ${t['last']}")
```

**好处**：
- ✅ AI 回答基于实时行情，更准确
- ✅ 用户无需手动告知当前时间/价格
- ✅ 提升交易决策辅助质量

### 3.3 `backend/app/services/credential_service.py` · 2 行变更

**改进点**：演示账户支持真实下单

```python
# 之前：演示账户也强制 dry_run
dry_run=not settings.live_trading_enabled

# 之后：演示账户可单独启用实盘
dry_run=not settings.live_trading_enabled and not is_demo
```

**好处**：
- ✅ 演示账户可独立控制是否实盘
- ✅ 便于对接 OKX 模拟盘（demo）
- ✅ 测试环境更灵活

### 3.4 `backend/app/adapters/connection_manager.py` · 8 行变更

**改进点**：连接管理器真实调用适配器

```python
# 之前：模拟连接延迟
self._latency_ms = 42 if self.name in ("binance",) else 58
self._status = AdapterConnectionStatus.CONNECTED

# 之后：真实调用适配器连接方法
if hasattr(self._adapter, "connect"):
    try:
        self._adapter.connect()
    except Exception as e:
        self._status = AdapterConnectionStatus.FAILED
        self._last_error = str(e)
        raise
```

**好处**：
- ✅ 真实反映适配器连接状态
- ✅ 错误信息更准确
- ✅ 健康检查更可信

---

## 四、🎨 前端全面改版（修改 9 个文件）

### 4.1 样式重构 `frontend/src/styles.css` · 2,012 行变更

| 维度 | 改进 |
|------|------|
| **设计语言** | 全面统一为现代扁平化风格 |
| **主题色** | 优化配色方案，对比度更合理 |
| **响应式** | 多设备适配增强 |
| **动效** | 添加过渡动画 |
| **可访问性** | 改进键盘导航和屏幕阅读器支持 |

### 4.2 入口与客户端

| 文件 | 变更 |
|------|------|
| `frontend/index.html` | meta 标签优化、SEO 改进、PWA 配置 |
| `frontend/src/api.ts` | API 客户端增强，类型定义更严格 |

### 4.3 布局组件

| 文件 | 变更 |
|------|------|
| `frontend/src/components/Layout.tsx` | **56 行变更**，导航结构优化、侧边栏改进 |
| `frontend/src/components/ExchangeCredentialsManager.tsx` | UI 优化，更直观的密钥管理界面 |

### 4.4 页面升级

| 页面 | 主要变化 |
|------|----------|
| `Dashboard.tsx` | 仪表盘数据展示优化、图表组件升级 |
| `MarketData.tsx` | 行情页面 K线/深度图优化 |
| `Risk.tsx` | 风控页面增加审批流展示 |
| `Agents.tsx` | 智能体页面交互改进 |
| `Settings.tsx` | 设置页面分组优化 |

---

## 五、🚀 部署与运维增强（新增 14 个文件）

### 5.1 代码质量钩子 `.pre-commit-config.yaml`

启用 Git 提交前的自动检查：

| 钩子 | 功能 |
|------|------|
| `check-yaml` | YAML 文件语法检查 |
| `end-of-file-fixer` | 自动修复文件末尾换行 |
| `trailing-whitespace` | 自动去除行尾空格 |
| `ruff` | Python 代码 lint 检查（自动修复） |
| `ruff-format` | Python 代码格式化（PEP 8） |

**使用方法**：
```bash
pip install pre-commit
pre-commit install
# 之后每次 git commit 都会自动运行
```

### 5.2 部署脚本 `deploy/deploy.sh`

**功能**：自动化部署流程

执行步骤：
1. ✅ 运行部署前验证测试（`test_fixes.py` + `test_persistence.py`）
2. ✅ 重启 systemd 服务 `quant`
3. ✅ 等待服务健康检查通过（最多重试 10 次）
4. ✅ 输出部署结果

```bash
# 使用方法
/root/abc-project/deploy/deploy.sh
```

### 5.3 备份脚本 `deploy/backup.sh`

**功能**：自动化数据库备份

特性：
- ✅ 每日 03:00 自动执行（需配合 cron）
- ✅ 压缩备份（gzip 格式）
- ✅ 自动清理 7 天前的旧备份
- ✅ 记录日志到 `/var/log/quant-backup.log`

```bash
# 手动执行
/root/abc-project/deploy/backup.sh

# 添加 cron 任务（每天 03:00）
echo "0 3 * * * /root/abc-project/deploy/backup.sh" | crontab -
```

### 5.4 部署任务清单 `deploy/TODO.md`

完整的部署任务跟踪与检查清单（495 行），包括：
- 部署前检查项
- 部署步骤分解
- 部署后验证
- 常见问题排查

### 5.5 运维手册 `docs/OPERATIONS.md`

**生产环境运维标准操作流程（SOP）**：

| 章节 | 内容 |
|------|------|
| 服务清单 | Nginx / Quant Backend / PostgreSQL / Redis / fail2ban |
| 日常运维 | 状态检查 / 重启 / 日志查看 |
| 备份恢复 | 自动备份策略 / 手动恢复步骤 |
| 内存优化 | 1C/896MB 内存下的 OOM 防护 |

**特别说明**：文档原编码为 GBK，已在此说明书中以 UTF-8 重新整理展示。

### 5.6 开发工具脚本 `backend/scripts/dev/`

整理后的开发辅助脚本：

| 脚本 | 功能 |
|------|------|
| `debug_okx_order.py` | OKX 下单调试 |
| `deep_probe_okx.py` | OKX 深度探测 |
| `diagnose_exchange.py` | 交易所诊断 |
| `fetch_okx_pending_orders.py` | 获取 OKX 待成交订单 |
| `patch_live_wiring.py` | 实盘连线修复 |
| `test_ai_time.py` | AI 时间测试 |
| `test_okx_connection.py` | OKX 连接测试 |
| `test_real_okx_order.py` | OKX 真实下单测试 |

---

## 六、🔒 安全性改进

### 6.1 `.gitignore` 更新

新增排除规则：

```gitignore
# 敏感文件 - 永不提交
deploy/.env           # 数据库/Redis 密码
backups/              # 数据库备份（800KB，包含全部数据）
docs-archive/         # 旧文档归档
*.sql.gz              # SQL 备份文件
*.tar.gz              # 压缩包
*.bak                 # 备份文件
```

### 6.2 生产环境加固

- ✅ `/docs` `/redoc` `/openapi.json` 在生产环境自动关闭
- ✅ API 文档不再泄露
- ✅ 减少攻击面

---

## 七、📦 部署验证步骤

### 7.1 拉取最新代码

```bash
cd /root/abc-project
git pull origin main
# 预期：更新到 fa90875
```

### 7.2 应用新的依赖（如有）

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt  # 一般无变化
```

### 7.3 执行部署

```bash
# 方式一：使用新部署脚本
sudo /root/abc-project/deploy/deploy.sh

# 方式二：传统方式
sudo systemctl restart quant
sudo systemctl reload nginx
```

### 7.4 验证服务

```bash
# 健康检查
curl http://43.108.98.174/health
curl http://43.108.98.174/ready

# 前端
open http://43.108.98.174/

# 后端 API（生产环境应已关闭）
# open http://43.108.98.174/docs
```

### 7.5 验证备份

```bash
# 手动执行一次备份，确认脚本可用
/root/abc-project/deploy/backup.sh
ls -la /root/abc-project/backups/
```

---

## 八、🔙 回滚方案

如新版本出现问题，可快速回滚：

```bash
cd /root/abc-project
git log --oneline -3
# 9046fdb docs: add CHANGELOG.md with detailed v0.2.0 release notes  ← 回滚目标

# 软回滚（推荐）：只回滚代码，保留数据库
git reset --hard 9046fdb
sudo systemctl restart quant

# 硬回滚：完全回到 v0.2.0
git reset --hard b5ac6e0
sudo systemctl restart quant
```

---

## 九、📋 完整 Git 历史

```
fa90875 (HEAD -> main, origin/main) chore: cleanup, update .gitignore, refactor backend services, UI overhaul
9046fdb docs: add CHANGELOG.md with detailed v0.2.0 release notes
b5ac6e0 feat: complete v0.2.0 - E2E testing, adversarial challenger, alpha mining, portfolio optimizer, strategy evolution
c6361b6 docs: add project overview and full deployment guide README
7aeae13 Initial commit: Enterprise AI Quant System v0.2.0 (backend + frontend + deploy)
```

---

## 十、📞 反馈与支持

如有问题，请检查：
1. 服务日志：`journalctl -u quant -f`
2. Nginx 日志：`/var/log/nginx/error.log`
3. 备份日志：`/var/log/quant-backup.log`
4. 运维手册：`docs/OPERATIONS.md`
5. 部署清单：`deploy/TODO.md`

---

> 本说明书由 Quant Deploy Bot 自动生成
> 仓库地址：https://github.com/1535273240sch-droid/-abc
