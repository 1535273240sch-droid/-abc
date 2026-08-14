import { Activity, Database, Key, Lock, RefreshCw, Search, ShieldCheck, UserCheck, Users, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendAdapterHealth, mapBackendAuditLog } from '../adapters'
import { api, type SystemStatusResponse } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, PageIntro, Panel, StatusBadge, TabGroup } from '../components/Primitives'
import { mockAuditLogs, mockExchangeConnections } from '../mockData'
import type { AuditLog, ExchangeConnection } from '../types'

export default function Settings() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [isLiveAdapterApi, setIsLiveAdapterApi] = useState(false)
  const [activeTab, setActiveTab] = useState<'exchanges' | 'rbac' | 'audit' | 'system'>('exchanges')
  const [auditSearch, setAuditSearch] = useState('')
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>(mockAuditLogs)
  const [exchangeConnections, setExchangeConnections] = useState<ExchangeConnection[]>(mockExchangeConnections)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null)

  const loadSettingsData = async () => {
    setLoading(true)
    try {
      const [statusRes, auditRes, adaptersRes] = await Promise.all([
        api.systemStatus().catch(() => null),
        api.auditEvents(50, 0).catch(() => null),
        api.adapters().catch(() => null)
      ])

      let connected = false
      if (statusRes) {
        setSystemStatus(statusRes)
        connected = true
      }
      if (auditRes && Array.isArray(auditRes) && auditRes.length > 0) {
        setAuditLogs(auditRes.map((a) => mapBackendAuditLog(a)))
        connected = true
      }
      if (adaptersRes && Array.isArray(adaptersRes) && adaptersRes.length > 0) {
        setExchangeConnections(adaptersRes.map((ad) => mapBackendAdapterHealth(ad)))
        setIsLiveAdapterApi(true)
        connected = true
      } else {
        setIsLiveAdapterApi(false)
      }

      setIsLiveApi(connected)
    } catch {
      setIsLiveApi(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettingsData()
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="控制平面" title="系统设置 Settings" description="交易所密钥引用、RBAC 角色权限、系统全局配置与不可篡改审计日志" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="控制平面" title="系统设置 Settings" description="正在读取系统状态与 API 审计事件..." />
        <DataState state="loading" title="读取系统设置中" description="GET /api/v1/system/status, GET /api/v1/audit/events, GET /api/v1/adapters" />
      </div>
    )
  }

  const filteredAuditLogs = auditLogs.filter(
    (log) =>
      log.action.toLowerCase().includes(auditSearch.toLowerCase()) ||
      log.eventType.toLowerCase().includes(auditSearch.toLowerCase()) ||
      log.operator.toLowerCase().includes(auditSearch.toLowerCase())
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="控制平面"
        title="系统设置与安全审计 (Phase 4 契约对齐)"
        description="符合企业级合规：API Key 仅通过 Secret Manager 引用管理，系统不可篡改审计追踪"
        action={
          <button className="button button--secondary" onClick={loadSettingsData}>
            <RefreshCw size={14} />
            刷新 API 状态
          </button>
        }
      />

      {/* API Status Banner */}
      <div
        style={{
          padding: '8px 14px',
          backgroundColor: isLiveApi ? 'rgba(0, 192, 135, 0.1)' : 'rgba(250, 173, 20, 0.1)',
          border: `1px solid ${isLiveApi ? 'rgba(0, 192, 135, 0.3)' : 'rgba(250, 173, 20, 0.3)'}`,
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 12
        }}
      >
        <span style={{ color: isLiveApi ? 'var(--color-positive)' : 'var(--color-warning)' }}>
          {isLiveApi
            ? `✓ 已接入 API GET /api/v1/system/status, /audit/events ${isLiveAdapterApi ? '& /api/v1/adapters (Paper Adapter)' : ''}`
            : '⚠ 系统设置 API 未连接，当前展示 [Demo / Mock 审计与连接数据源]'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'Settings & Adapters API Live' : 'Demo Settings'}
        </StatusBadge>
      </div>

      <Panel
        title="控制平面配置中心"
        subtitle="权限隔离、密钥安全与合规审计"
        action={
          <TabGroup
            tabs={[
              { id: 'exchanges', label: '交易所连接 (Connections)', badge: `${exchangeConnections.length}` },
              { id: 'rbac', label: '角色与 RBAC 权限' },
              { id: 'audit', label: '审计日志 (Audit Log)', badge: `${auditLogs.length}` },
              { id: 'system', label: '系统全局参数' },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as any)}
          />
        }
      >
        {activeTab === 'exchanges' && (
          <div>
            <div style={{ padding: 12, backgroundColor: 'rgba(53, 114, 239, 0.1)', border: '1px solid rgba(53, 114, 239, 0.25)', borderRadius: 'var(--radius-md)', marginBottom: 16, fontSize: 12, color: '#93C5FD' }}>
              <Lock size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
              <strong>安全约束提醒：</strong> API Key 和 Secret 仅存放在机构级 Secret Manager / HashiCorp Vault 中。前端与代码库禁止包含或输入明文 Key。
              {isLiveAdapterApi ? ' (数据源: GET /api/v1/adapters 真实只读状态)' : ' (注意：API 未连接时展示 [Demo / Mock 适配器视图])'}
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>连接名称</th>
                    <th>交易所</th>
                    <th>环境</th>
                    <th>Secret Manager 引用 ID</th>
                    <th>网络延迟 (Ping)</th>
                    <th>最近同步</th>
                    <th>连接状态</th>
                  </tr>
                </thead>
                <tbody>
                  {exchangeConnections.map((conn) => (
                    <tr key={conn.id}>
                      <td><strong>{conn.name}</strong></td>
                      <td>{conn.exchange}</td>
                      <td>
                        <StatusBadge tone="accent" dot={false}>
                          {conn.mode}
                        </StatusBadge>
                      </td>
                      <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{conn.secretRef}</td>
                      <td className="cell-mono text-positive">{conn.ping}</td>
                      <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{conn.lastSync}</td>
                      <td>
                        <StatusBadge tone={conn.status === '已连接' ? 'positive' : 'warning'}>
                          {conn.status}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'rbac' && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>角色</th>
                  <th>策略研发</th>
                  <th>风控阈值修改</th>
                  <th>纸面下单</th>
                  <th>实盘生产授权</th>
                  <th>API 密钥管理</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>平台管理员 (Admin)</strong></td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-warning">⚠ 需双人复核</td>
                  <td className="text-positive">✓ Vault 管理</td>
                </tr>
                <tr>
                  <td><strong>量化研究员 (Quant)</strong></td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-positive">✓ 仅纸面环境</td>
                  <td className="text-muted">✗ 无权限</td>
                  <td className="text-muted">✗ 无权限</td>
                </tr>
                <tr>
                  <td><strong>风控主管 (Risk Officer)</strong></td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-positive">✓ 核心规则配置</td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-warning">⚠ 审批权</td>
                  <td className="text-muted">✗ 无权限</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'audit' && (
          <div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
              <div className="search-box" style={{ width: 300 }}>
                <Search size={15} />
                <input
                  type="text"
                  placeholder="搜索事件名称、操作员或 Trace ID..."
                  value={auditSearch}
                  onChange={(e) => setAuditSearch(e.target.value)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-primary)', outline: 'none', width: '100%', fontSize: 12 }}
                />
              </div>
              <button className="button button--secondary" onClick={() => setAuditSearch('')}>清空筛选</button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>事件 ID</th>
                    <th>时间 (UTC)</th>
                    <th>模块</th>
                    <th>事件类型</th>
                    <th>操作员</th>
                    <th>动作摘要</th>
                    <th>Trace ID</th>
                    <th>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAuditLogs.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>无匹配审计事件</td></tr>
                  ) : (
                    filteredAuditLogs.map((log) => (
                      <tr key={log.id}>
                        <td className="cell-mono"><strong>{log.id}</strong></td>
                        <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{log.eventTime}</td>
                        <td>
                          <StatusBadge tone="neutral" dot={false}>{log.module}</StatusBadge>
                        </td>
                        <td className="cell-mono" style={{ fontSize: 11 }}>{log.eventType}</td>
                        <td style={{ fontSize: 12 }}>{log.operator}</td>
                        <td style={{ fontSize: 12 }}>{log.action}</td>
                        <td className="cell-mono" style={{ fontSize: 10, color: 'var(--color-accent)' }}>{log.traceId}</td>
                        <td>
                          <StatusBadge tone={log.result === '成功' ? 'positive' : 'warning'}>
                            {log.result}
                          </StatusBadge>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'system' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>数据契约与时间基准</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                <div>时间标准: <code className="cell-mono">UTC ISO 8601 (YYYY-MM-DDTHH:mm:ss.sssZ)</code></div>
                <div>金额/数量语义: <code className="cell-mono">Decimal (精确字符串传输，禁止二进制浮点)</code></div>
                <div>全局交易模式: <code className="cell-mono text-accent">paper ({systemStatus?.mode || 'default paper'})</code></div>
                <div>系统版本: <code className="cell-mono">{systemStatus?.app_version || 'v0.1.0'}</code></div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>API Gateway & BFF 节点</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                <div>应用名称: <code className="cell-mono">{systemStatus?.app_name || 'enterprise-ai-quant'}</code></div>
                <div>应用运行时间: <code className="cell-mono">{systemStatus?.uptime_seconds ? `${systemStatus.uptime_seconds}s` : '—'}</code></div>
                <div>Redis 缓存集群: <code className="cell-mono">redis_quant_cache (v7.2)</code></div>
                <div>事件总线 Channel: <code className="cell-mono">quant.events.v1</code></div>
              </div>
            </div>
          </div>
        )}
      </Panel>
    </div>
  )
}
