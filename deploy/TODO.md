# 部署任务跟踪

> 详细的待办事项见根目录的 [UPDATE_LOG.md](../UPDATE_LOG.md) 第「待办事项跟踪」章节。
> 本文件仅保留**部署阶段**的轻量任务清单。

## 当前部署任务

- [x] 部署 quant systemd 服务
- [x] 部署 PostgreSQL + Redis Docker 容器
- [x] 配置 Nginx 反向代理
- [x] 配置前端静态托管
- [x] 创建 SOCKS5 代理
- [x] 创建 VMess + WebSocket 代理
- [x] 添加 pre-commit 钩子
- [x] 创建自动化部署脚本（deploy.sh）
- [x] 创建自动化备份脚本（backup.sh）
- [x] 创建运维手册（docs/OPERATIONS.md）

## 待办（参考 UPDATE_LOG.md）

详细 P0/P1/P2/P3 优先级任务见 `UPDATE_LOG.md` 末尾的"待办事项跟踪"章节。

## 部署验证

```bash
# 健康检查
curl http://43.108.98.174/health
curl http://43.108.98.174/ready

# 服务状态
systemctl status quant
systemctl status nginx
docker ps
```

最后更新：2026-08-20
