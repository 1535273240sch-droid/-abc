# 量化项目企业级改造待办事项

> **服务器**：43.108.98.174（1C / 896MB RAM / 30GB 磁盘，剩余 19GB）
> **项目路径**：/root/abc-project
> **当前评分**：3.5/10 → **目标评分**：7.0/10
> **约束**：内存新增 ≤300MB，不中断服务，不 OOM，不写满磁盘
> **创建时间**：2026-08-20

---

## 🔴 安全红线（执行前必读）

1. **不中断服务**：所有操作需确保 quant.service、nginx、PostgreSQL、Redis 持续可用
2. **不 OOM**：内存新增严格控制在 300MB 以内，操作前检查当前内存使用
3. **不写满磁盘**：磁盘剩余空间保持 ≥5GB，操作前检查 `df -h`
4. **不改 SSH/防火墙**：除任务 1、2 外，不得修改其他网络配置
5. **不删数据**：禁止删除任何业务数据、日志、数据库文件
6. **不装重型组件**：禁止安装 Kubernetes、ELK、Prometheus 等内存大户

---

## 一、安全加固（P0 - 最高优先级）

### 任务 1：关闭 SSH 密码登录，改为密钥认证
- **风险等级**：🔴 高（操作不当会锁死 SSH）
- **前置检查**：
  - [ ] 确认已添加公钥到 `~/.ssh/authorized_keys`
  - [ ] 确认使用密钥可正常登录
- **操作步骤**：
  1. 备份配置：`cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d)`
  2. 编辑 `/etc/ssh/sshd_config`，设置：
     ```
     PasswordAuthentication no
     PubkeyAuthentication yes
     ```
  3. 重启 sshd：`systemctl restart sshd`
  4. **不要关闭当前终端**，新开终端测试密钥登录
- **验证方式**：新终端使用密钥登录成功，密码登录被拒绝
- **预计耗时**：10 分钟
- **内存影响**：无

### 任务 2：配置 fail2ban 防护 SSH 暴力破解
- **风险等级**：🟡 中
- **操作步骤**：
  1. 安装：`apt update && apt install fail2ban -y`
  2. 创建配置 `/etc/fail2ban/jail.local`：
     ```ini
     [DEFAULT]
     bantime = 3600
     findtime = 600
     maxretry = 3
     backend = systemd
     
     [sshd]
     enabled = true
     port = ssh
     filter = sshd
     logpath = /var/log/auth.log
     maxretry = 3
     ```
  3. 启动：`systemctl enable fail2ban && systemctl start fail2ban`
- **验证方式**：`fail2ban-client status sshd` 显示 active
- **预计耗时**：15 分钟
- **内存影响**：+30MB

### 任务 3：为 admin 用户配置 sudo 密码保护
- **风险等级**：🟡 中
- **操作步骤**：
  1. 确认 admin 用户已设置密码：`passwd admin`
  2. 编辑 sudoers：`visudo`
  3. 找到 `admin ALL=(ALL) NOPASSWD:ALL`，改为 `admin ALL=(ALL) ALL`
- **验证方式**：`sudo -l -U admin` 需要输入密码
- **预计耗时**：5 分钟
- **内存影响**：无

### 任务 4：关闭 FastAPI /docs 公开暴露
- **风险等级**：🟢 低
- **操作步骤**：
  1. 修改 `/root/abc-project/app/main.py`：
     ```python
     # 方式1：完全关闭
     app = FastAPI(docs_url=None, redoc_url=None)
     
     # 方式2：环境变量控制（推荐）
     docs_url = "/docs" if os.getenv("ENV") == "dev" else None
     app = FastAPI(docs_url=docs_url, redoc_url=None)
     ```
  2. 重启服务：`systemctl restart quant`
- **验证方式**：访问 `http://43.108.98.174/docs` 返回 404
- **预计耗时**：10 分钟
- **内存影响**：无

### 任务 5：启用 API 认证中间件
- **风险等级**：🟡 中
- **操作步骤**：
  1. 检查 `/root/abc-project/app/middleware/auth.py` 是否存在且启用
  2. 确认 JWT 验证逻辑正确，密钥从环境变量读取
  3. 在 nginx 配置中添加：
     ```nginx
     location /api/ {
         proxy_pass http://127.0.0.1:8000;
         proxy_set_header Authorization $http_authorization;
         proxy_set_header X-Real-IP $remote_addr;
     }
     ```
  4. 重启 nginx 和 quant 服务
- **验证方式**：无 token 访问 API 返回 401，带有效 token 正常访问
- **预计耗时**：20 分钟
- **内存影响**：无

---

## 二、高可用改造（P1 - 高优先级）

### 任务 6：配置 uvicorn 多 worker 进程
- **风险等级**：🔴 高（内存风险最高）
- **前置检查**：
  - [ ] 当前内存使用 ≤500MB：`free -h`
  - [ ] 已完成任务 2（fail2ban）和任务 7（自动重启）
- **操作步骤**：
  1. 编辑 `/etc/systemd/system/quant.service`
  2. 修改 ExecStart，添加 `--workers 2`：
     ```ini
     ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
     ```
  3. 重载并重启：`systemctl daemon-reload && systemctl restart quant`
  4. 监控内存：`watch -n 1 free -h`，持续 5 分钟
- **验证方式**：`ps aux | grep uvicorn` 显示 2 个 worker 进程，内存稳定
- **回滚方案**：若 OOM，立即改回 `--workers 1` 并重启
- **预计耗时**：10 分钟
- **内存影响**：+200MB

### 任务 7：添加 systemd 自动重启策略
- **风险等级**：🟢 低
- **操作步骤**：
  1. 编辑 `/etc/systemd/system/quant.service`，在 [Service] 段添加：
     ```ini
     Restart=always
     RestartSec=10
     StartLimitInterval=60s
     StartLimitBurst=3
     ```
  2. 重载：`systemctl daemon-reload`
- **验证方式**：`systemctl show quant | grep Restart` 显示 always
- **预计耗时**：5 分钟
- **内存影响**：无

### 任务 8：配置 PostgreSQL 自动备份
- **风险等级**：🟢 低
- **操作步骤**：
  1. 创建备份目录：`mkdir -p /root/abc-project/backups`
  2. 创建备份脚本 `/root/abc-project/deploy/backup.sh`：
     ```bash
     #!/bin/bash
     BACKUP_DIR="/root/abc-project/backups"
     DATE=$(date +%Y%m%d_%H%M%S)
     docker exec enterprise-ai-quant-postgres pg_dump -U postgres quant | gzip > "$BACKUP_DIR/quant_$DATE.sql.gz"
     # 保留最近 7 天
     find $BACKUP_DIR -name "quant_*.sql.gz" -mtime +7 -delete
     ```
  3. 添加执行权限：`chmod +x /root/abc-project/deploy/backup.sh`
  4. 添加 cron：`crontab -e`，添加行：
     ```
     0 3 * * * /root/abc-project/deploy/backup.sh >> /var/log/backup.log 2>&1
     ```
- **验证方式**：手动执行脚本，检查 `/root/abc-project/backups/` 生成文件
- **预计耗时**：15 分钟
- **内存影响**：备份时短暂 +50MB

### 任务 9：配置 Redis 持久化（AOF + RDB 混合）
- **风险等级**：🟡 中
- **操作步骤**：
  1. 进入 Redis 容器：`docker exec -it enterprise-ai-quant-redis sh`
  2. 编辑配置：`vi /etc/redis/redis.conf`（或挂载的配置文件）
  3. 修改：
     ```
     appendonly yes
     appendfsync everysec
     aof-use-rdb-preamble yes
     save 900 1
     save 300 10
     save 60 10000
     ```
  4. 重启 Redis：`docker restart enterprise-ai-quant-redis`
- **验证方式**：`docker exec enterprise-ai-quant-redis redis-cli info persistence` 显示 aof_enabled:1
- **预计耗时**：10 分钟
- **内存影响**：+10MB

### 任务 10：添加健康检查端点
- **风险等级**：🟢 低
- **操作步骤**：
  1. 在 `/root/abc-project/app/api/health.py` 创建：
     ```python
     from fastapi import APIRouter
     from app.core.database import engine
     from app.core.redis import redis_client
     
     router = APIRouter()
     
     @router.get("/health")
     async def health_check():
         try:
             # 检查数据库
             with engine.connect() as conn:
                 conn.execute("SELECT 1")
             # 检查 Redis
             redis_client.ping()
             return {"status": "healthy", "db": "ok", "redis": "ok"}
         except Exception as e:
             return {"status": "unhealthy", "error": str(e)}, 503
     ```
  2. 注册路由到 main.py
  3. 重启服务
- **验证方式**：`curl http://localhost:8000/health` 返回 healthy
- **预计耗时**：15 分钟
- **内存影响**：无

---

## 三、可观测性（P1 - 高优先级）

### 任务 11：结构化日志改造
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装依赖：`pip install structlog`
  2. 创建 `/root/abc-project/app/core/logging.py`：
     ```python
     import structlog
     import logging
     
     def setup_logging():
         structlog.configure(
             processors=[
                 structlog.stdlib.filter_by_level,
                 structlog.stdlib.add_logger_name,
                 structlog.stdlib.add_log_level,
                 structlog.stdlib.PositionalArgumentsFormatter(),
                 structlog.processors.TimeStamper(fmt="iso"),
                 structlog.processors.StackInfoRenderer(),
                 structlog.processors.format_exc_info,
                 structlog.processors.UnicodeDecoder(),
                 structlog.processors.JSONRenderer()
             ],
             context_class=dict,
             logger_factory=structlog.stdlib.LoggerFactory(),
             wrapper_class=structlog.stdlib.BoundLogger,
             cache_logger_on_first_use=True,
         )
     ```
  3. 在 main.py 中调用 `setup_logging()`
- **验证方式**：日志输出为 JSON 格式
- **预计耗时**：30 分钟
- **内存影响**：+5MB

### 任务 12：添加请求追踪（trace_id）
- **风险等级**：🟢 低
- **操作步骤**：
  1. 创建 `/root/abc-project/app/middleware/trace.py`：
     ```python
     import uuid
     from starlette.middleware.base import BaseHTTPMiddleware
     from starlette.requests import Request
     
     class TraceMiddleware(BaseHTTPMiddleware):
         async def dispatch(self, request: Request, call_next):
             trace_id = str(uuid.uuid4())
             request.state.trace_id = trace_id
             response = await call_next(request)
             response.headers["X-Trace-ID"] = trace_id
             return response
     ```
  2. 在 main.py 中添加中间件
- **验证方式**：响应头包含 X-Trace-ID
- **预计耗时**：15 分钟
- **内存影响**：无

### 任务 13：配置应用级别 metrics 端点
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装依赖：`pip install prometheus-client`
  2. 创建 `/root/abc-project/app/api/metrics.py`：
     ```python
     from prometheus_client import Counter, Histogram, generate_latest
     from fastapi import APIRouter, Response
     
     router = APIRouter()
     
     REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
     REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['endpoint'])
     
     @router.get("/metrics")
     async def metrics():
         return Response(generate_latest(), media_type="text/plain")
     ```
  3. 添加中间件收集 metrics
- **验证方式**：`curl http://localhost:8000/metrics` 返回 Prometheus 格式数据
- **预计耗时**：20 分钟
- **内存影响**：+10MB

### 任务 14：配置日志轮转
- **风险等级**：🟢 低
- **操作步骤**：
  1. 创建日志目录：`mkdir -p /var/log/quant`
  2. 创建 logrotate 配置 `/etc/logrotate.d/quant`：
     ```
     /var/log/quant/*.log {
         daily
         rotate 7
         compress
         delaycompress
         missingok
         notifempty
         create 0644 root root
         sharedscripts
         postrotate
             systemctl reload quant > /dev/null 2>&1 || true
         endscript
     }
     ```
  3. 测试：`logrotate -d /etc/logrotate.d/quant`
- **验证方式**：`logrotate -f /etc/logrotate.d/quant` 执行成功
- **预计耗时**：10 分钟
- **内存影响**：无

---

## 四、CI/CD 基础（P2 - 中优先级）

### 任务 15：创建部署脚本
- **风险等级**：🟡 中
- **操作步骤**：
  1. 创建 `/root/abc-project/deploy/deploy.sh`：
     ```bash
     #!/bin/bash
     set -e
     cd /root/abc-project
     echo "[$(date)] Starting deployment..."
     git pull origin main
     pip install -r requirements.txt --quiet
     pytest tests/ -v --tb=short -x
     systemctl restart quant
     sleep 5
     curl -f http://localhost:8000/health || exit 1
     echo "[$(date)] Deployment completed successfully"
     ```
  2. 添加执行权限：`chmod +x /root/abc-project/deploy/deploy.sh`
- **验证方式**：手动执行脚本成功
- **预计耗时**：20 分钟
- **内存影响**：部署时短暂 +100MB

### 任务 16：添加 pre-commit 钩子
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装：`pip install pre-commit`
  2. 创建 `.pre-commit-config.yaml`：
     ```yaml
     repos:
       - repo: https://github.com/psf/black
         rev: 24.3.0
         hooks:
           - id: black
       - repo: https://github.com/pycqa/isort
         rev: 5.13.2
         hooks:
           - id: isort
       - repo: https://github.com/pycqa/flake8
         rev: 7.0.0
         hooks:
           - id: flake8
       - repo: https://github.com/pre-commit/mirrors-mypy
         rev: v1.9.0
         hooks:
           - id: mypy
     ```
  3. 安装钩子：`pre-commit install`
- **验证方式**：`pre-commit run --all-files` 通过
- **预计耗时**：15 分钟
- **内存影响**：无

### 任务 17：配置测试覆盖率门槛
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装：`pip install pytest-cov`
  2. 修改 `pytest.ini` 或 `pyproject.toml`：
     ```ini
     [tool:pytest]
     addopts = --cov=app --cov-report=term-missing --cov-fail-under=60
     ```
  3. 运行测试：`pytest --cov=app --cov-report=html`
- **验证方式**：覆盖率 ≥60% 时测试通过
- **预计耗时**：10 分钟
- **内存影响**：测试时短暂 +50MB

---

## 五、代码质量（P2 - 中优先级）

### 任务 18：统一代码风格
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装：`pip install black isort`
  2. 格式化：`black app/ tests/ && isort app/ tests/`
  3. 提交更改：`git add . && git commit -m "style: format code with black and isort"`
- **验证方式**：`black --check app/ tests/` 无输出
- **预计耗时**：10 分钟
- **内存影响**：无

### 任务 19：添加类型注解覆盖率检查
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装：`pip install mypy`
  2. 运行检查：`mypy app/ --strict --ignore-missing-imports`
  3. 逐步修复类型错误，优先修复核心模块
- **验证方式**：`mypy app/ --strict` 错误数逐步减少
- **预计耗时**：持续进行
- **内存影响**：检查时短暂 +100MB

### 任务 20：清理无用代码和注释
- **风险等级**：🟢 低
- **操作步骤**：
  1. 安装：`pip install vulture`
  2. 扫描：`vulture app/ --min-confidence 80`
  3. 审查并删除确认无用的代码
- **验证方式**：`vulture app/ --min-confidence 80` 无输出
- **预计耗时**：15 分钟
- **内存影响**：无

---

## 六、文档与规范（P3 - 低优先级）

### 任务 21：编写项目 README
- **风险等级**：🟢 低
- **操作步骤**：
  1. 创建 `/root/abc-project/README.md`，包含：
     - 项目简介和架构图
     - 技术栈（FastAPI + React + PostgreSQL + Redis）
     - 本地开发环境搭建
     - 部署流程
     - API 文档链接（如启用）
     - 测试运行方式
- **验证方式**：新开发者可按 README 完成环境搭建
- **预计耗时**：30 分钟
- **内存影响**：无

### 任务 22：添加 API 接口文档注释
- **风险等级**：🟢 低
- **操作步骤**：
  1. 为所有 FastAPI 路由添加 docstring
  2. 添加 response_model 和示例
  3. 使用 `fastapi.openapi.utils.get_openapi` 生成文档
- **验证方式**：`curl http://localhost:8000/openapi.json` 包含完整文档
- **预计耗时**：持续进行
- **内存影响**：无

### 任务 23：创建运维手册
- **风险等级**：🟢 低
- **操作步骤**：
  1. 创建 `/root/abc-project/docs/OPERATIONS.md`，包含：
     - 服务启动/停止/重启流程
     - 日志位置和查看方式
     - 备份和恢复流程
     - 常见故障排查（OOM、连接失败、磁盘满）
     - 监控指标说明
- **验证方式**：运维人员可按手册处理常见故障
- **预计耗时**：30 分钟
- **内存影响**：无

---

## 执行顺序建议

```
第一周（安全加固）：任务 1 → 2 → 3 → 4 → 5
第二周（高可用+可观测）：任务 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 6
第三周（CI/CD+代码质量）：任务 15 → 16 → 17 → 18 → 19 → 20
第四周（文档）：任务 21 → 22 → 23
```

**注意**：任务 6（多 worker）风险最高，建议在完成其他所有任务后，确认系统稳定再执行。

---

## 快速检查清单

执行任何任务前，请确认：

- [ ] 当前内存使用 `free -h` 显示 available ≥300MB
- [ ] 磁盘剩余 `df -h` 显示 ≥5GB
- [ ] 服务状态 `systemctl status quant nginx docker` 均为 active
- [ ] 已备份相关配置文件

---

*本文档由 OrcaTerm AI 生成，供其他执行者使用。如有疑问，请查阅原始巡检报告或联系管理员。*