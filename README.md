# Enterprise AI Quant System

> 企业级 AI 量化交易平台 · v0.2.0
> 从策略研究、模拟交易到实盘风控的完整闭环，综合成熟度约 90%（企业标准）。

---

## 一、项目简介

本系统是一套面向加密货币的企业级 AI 量化交易平台，提供完整交易闭环：

| 模块 | 说明 |
|------|------|
| 订单生命周期管理 | 订单预检 → 下单 → 成交 → 持仓管理 → 对账 |
| 风控体系 | max_notional 限额 / 重复单校验 / 最小下单量 / 价格偏离保护 / Kill Switch |
| 策略研究 | 可插拔研究引擎（因子研究 / 回测 / 参数+注册模式） |
| 审批治理 | 审批单生命周期（创建 / 过期 / 审计投影）+ Kill Switch 恢复审批 |
| 对账 | 持仓 vs 交易所一致性核对 + 差异处理记录 |
| 交易所适配 | 数据源抽象提供者（Binance / Coinbase / OKX）+ 自动降级切换 |
| 模拟交易 | Paper Trading 适配器，与实盘共用同一订单流水线 |

### 技术栈

- **后端**：Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · Celery · Pydantic v2
- **前端**：TypeScript · Vite（SPA，构建后由 Nginx 静态托管）
- **基础设施**：PostgreSQL 16 · Redis 7 · Docker Compose · Nginx · systemd
- **可观测性**：structlog 结构化日志 · OpenTelemetry · Prometheus `/metrics` · Sentry

---

## 二、目录结构

```
.
├── backend/                 # FastAPI 后端（核心）
│   ├── app/
│   │   ├── api/             # REST 路由层
│   │   ├── services/        # 业务服务（订单/风控/对账/审批…）
│   │   ├── adapters/        # 交易所适配器（Binance/Coinbase/OKX/Paper）
│   │   ├── strategies/      # 策略引擎
│   │   ├── db/              # SQLAlchemy ORM + 存储后端
│   │   ├── events/          # 领域事件（Redis Stream）
│   │   ├── observability/   # 日志/指标/追踪
│   │   └── main.py          # 应用入口
│   ├── alembic/             # 数据库迁移
│   ├── tests/               # pytest 测试
│   ├── Dockerfile           # 多阶段构建，非 root 运行
│   ├── docker-compose.yml   # 全容器化编排（可选）
│   ├── requirements.txt
│   └── .env.example         # 环境变量模板
├── frontend/                # Vite + TypeScript 前端控制台
├── deploy/
│   ├── nginx.conf           # Nginx 站点配置（反代 + 静态托管）
│   ├── quant.service        # systemd 服务单元（后端进程）
│   └── docker-compose.infra.yml  # 基础设施：PostgreSQL + Redis
└── PROJECT_STATUS.md        # 项目进度与功能清单
```

---

## 三、部署手册

生产环境采用「**Docker 跑基础设施 + systemd 跑后端 + Nginx 反代前端**」的混合架构（当前线上 124.223.44.141 即此方案）。

### 0. 架构总览

```
公网请求 → Nginx(:80)
            ├─ /           → /var/www/enterprise-ai-quant（前端静态文件）
            └─ /api /health /ready /metrics /ws → 127.0.0.1:8000
                                                   ↑
                                            uvicorn（systemd: quant.service）
                                                   ↓
                              PostgreSQL(:5432) · Redis(:6379)  ← Docker 容器，仅绑定 127.0.0.1
```

### 1. 环境要求

- Ubuntu 22.04+（本项目在 Ubuntu 26.04 LTS 验证）
- Python 3.12+、Docker、Docker Compose、Nginx
- 最低 2C2G（数据库与 Redis 均在本机）

### 2. 启动基础设施（PostgreSQL + Redis）

```bash
cd deploy
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml ps   # 等待 healthy
```

两个容器均只绑定 `127.0.0.1`，不对外暴露。

### 3. 后端部署

```bash
cd backend

# 创建虚拟环境并安装依赖
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 配置环境变量（务必修改密钥与管理员密码）
cp .env.example .env
vim .env          # QUANT_AUTH_SECRET / QUANT_POSTGRES_DSN / QUANT_REDIS_URL 等

# 初始化数据库
.venv/bin/alembic upgrade head

# 本地验证启动
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

> 路径说明：`deploy/quant.service` 中 WorkingDirectory 与 EnvironmentFile 默认指向
> `/home/ubuntu/backend`，如部署路径不同请同步修改。

注册为 systemd 服务：

```bash
sudo cp deploy/quant.service /etc/systemd/system/quant.service
sudo systemctl daemon-reload
sudo systemctl enable --now quant
sudo systemctl status quant          # 查看状态
journalctl -u quant -f               # 跟踪日志
```

### 4. 前端部署

```bash
cd frontend
npm install
npm run build                 # 产出 dist/

sudo mkdir -p /var/www/enterprise-ai-quant
sudo rsync -a dist/ /var/www/enterprise-ai-quant/
```

### 5. Nginx 配置

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/enterprise-ai-quant.conf
sudo nginx -t && sudo systemctl reload nginx
```

配置要点：`/health`、`/ready`、`/metrics`、API 与 WebSocket 反代至 `127.0.0.1:8000`，其余请求回落到前端静态目录。

### 6. 验证

```bash
curl http://<服务器IP>/health     # 后端健康检查
curl http://<服务器IP>/ready      # 就绪检查（含依赖探测）
curl http://<服务器IP>/metrics    # Prometheus 指标
# 浏览器打开 http://<服务器IP>/   # 前端控制台
```

### 7. 全容器化部署（可选替代方案）

`backend/docker-compose.yml` 提供 6 服务一键编排（app + worker + beat + postgres + redis + nginx），适合全新环境：

```bash
cd backend
cp .env.example .env && vim .env
docker compose up -d --build
```

---

## 四、关键配置说明（.env）

| 变量 | 说明 |
|------|------|
| `QUANT_ENVIRONMENT` | `development` / `production` |
| `QUANT_MODE` | `paper`（模拟盘）/ `live`（实盘，开发环境被强制拦截） |
| `QUANT_AUTH_SECRET` | 认证密钥，生产必须替换为 32 位随机串 |
| `QUANT_AUTH_ADMIN_USERNAME/PASSWORD` | 管理员账号，生产必须修改 |
| `QUANT_POSTGRES_DSN` | PostgreSQL 连接串 |
| `QUANT_REDIS_URL` | Redis 连接串（事件流 + 缓存） |
| `QUANT_LOG_FORMAT` | `json`（生产）/ `text`（开发） |

完整清单见 [backend/.env.example](backend/.env.example)。

---

## 五、常用运维命令

```bash
# 更新部署
git pull
cd backend && .venv/bin/pip install -r requirements.txt && .venv/bin/alembic upgrade head
sudo systemctl restart quant

# 基础设施维护
docker compose -f deploy/docker-compose.infra.yml logs -f postgres
docker compose -f deploy/docker-compose.infra.yml restart redis

# 测试
cd backend && .venv/bin/pytest -q
```

---

## 六、安全注意事项

- `.env`、`*.pkl`、`*.db` 等运行时数据与密钥已被 `.gitignore` 排除，**切勿提交**。
- 生产环境开启 `QUANT_FORCE_HTTPS=true` 并配置 TLS 证书。
- Kill Switch 触发后需走审批流程恢复，防止误操作直接恢复实盘。

---

详细功能清单与各阶段交付记录见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。
