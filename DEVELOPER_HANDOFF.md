# 开发者交接文档 (Developer Handoff Guide)

欢迎继续开发 **Enterprise AI Quant System**！

## 1. 架构总览
- **后端架构**: Python 3.11 + FastAPI + SQLAlchemy + PostgreSQL 16 + Redis 7
- **前端架构**: React 18 + TypeScript + Vite + Tailwind CSS
- **网关与代理**: Nginx (托管前端静态文件并反向代理 `/api/`, `/ws`, `/docs`)
- **系统服务**: systemd 管理后端守护进程 (`quant.service`)

## 2. 关键代码路径
- 后端入口: `/root/abc-project/backend/app/main.py`
- 数据模型: `/root/abc-project/backend/app/models/`
- 业务服务: `/root/abc-project/backend/app/services/`
- 交易所适配器: `/root/abc-project/backend/app/services/adapters/`
- 回测引擎: `/root/abc-project/backend/app/services/backtest_service.py`
- 前端源码: `/root/abc-project/frontend/src/`

## 3. 下一步建议开发顺序
1. 按照 `TODO.md` 中的第 **一** 部分完善 `BinanceExchangeAdapter`。
2. 按照 `TODO.md` 中的第 **二** 部分丰富回测指标计算与数据源。
3. 运行 pytest 测试并重启 `quant.service` 验证接口。
