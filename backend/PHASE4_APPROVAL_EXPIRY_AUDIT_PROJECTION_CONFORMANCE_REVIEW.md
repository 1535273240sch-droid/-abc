# Phase 4 审批过期审计投影一致性复核报告

## 结论

**通过（paper/simulation 范围）**。审批过期状态变化现在同时产生版本化领域事件
`governance.approval_expired.v1` 和可由 `GET /api/v1/audit/events` 读取的审计 read
model。显式 `expire_due()` 与审批读取接口的惰性过期刷新共用相同投影逻辑；审计服务在
store lock 内按 `(event_type, resource_id)` 原子去重，重复刷新不会生成重复审计记录。

## 实现边界

- `ApprovalService._publish_expiry()` 统一构造事件和审计投影，字段均使用 UTC ISO 8601。
- 审计 `details` 包含 `version: 1`、原始 `event_id`、`event_type` 和完整 `payload`：
  `approval_id`、资源类型/ID、`expired` 状态及 `expired_at`。
- 投影仅记录审批状态事件，不创建订单、不修改持仓、不触发交易所调用。
- 当前是开发环境内存事件总线和内存 read model；生产环境仍需接入可靠消息系统与持久化审计存储。

## 验收证据

### 后端

```text
python -m pytest -q
178 passed, 1 warning in 2.32s

python -m compileall -q app tests
exit code 0
```

新增测试覆盖：

1. 显式过期扫描通过 HTTP 审计接口返回 `governance.approval_expired.v1`、system actor、
   approval resource、version 1 和完整 payload。
2. 惰性 `get_approval()` 重复读取及 `list_approvals()` 不重复投影。
3. 过期流程不改变 orders/positions 集合。

### Uvicorn smoke test

在本地启动 Uvicorn（`127.0.0.1:8799`，paper mode）并读取真实 HTTP 响应：

```text
/health=200 {"status":"ok", ...}
/api/v1/system/status=200 {"mode":"paper", "status":"running", ...}
/api/v1/audit/events=200 [{"event_type":"system.startup", ...}]
```

单元/API 测试负责构造确定性过期时间并验证审批过期投影；Uvicorn smoke 负责验证运行时路由、
序列化和审计接口可用性。

## 安全与限制

实现没有真实交易所连接、真实密钥、live 下单或生产部署路径。`live` 仍由既有防护和审批门
阻断。内存 read model 不提供跨进程一致性，不能作为生产持久化方案；该限制已明确保留在
Phase 4 架构边界内。
