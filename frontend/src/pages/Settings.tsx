import { Activity, Bot, Database, Key, Lock, RefreshCw, Search, ShieldCheck, UserCheck, Users, Zap, Sparkles, Cpu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendAuditLog } from '../adapters'
import { api, type SystemStatusResponse } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, PageIntro, Panel, StatusBadge, TabGroup } from '../components/Primitives'
import { ExchangeCredentialsManager } from '../components/ExchangeCredentialsManager'
import { AIModelGateway } from '../components/AIModelGateway'
import type { AuditLog } from '../types'

export default function Settings() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [activeTab, setActiveTab] = useState<'exchanges' | 'ai_models' | 'rbac' | 'audit' | 'system'>('exchanges')
  const [auditSearch, setAuditSearch] = useState('')
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null)
  const [credentialCount, setCredentialCount] = useState<number>(0)
  const [providerCount, setProviderCount] = useState<number>(0)

  const loadSettingsData = async () => {
    setLoading(true)
    try {
      const [statusRes, auditRes, credsRes, providersRes] = await Promise.all([
        api.systemStatus().catch(() => null),
        api.auditEvents(100, 0).catch(() => null),
        api.liveCredentials().catch(() => null),
        api.modelProviders().catch(() => null),
      ])

      let connected = false
      if (statusRes) {
        setSystemStatus(statusRes)
        connected = true
      }
      if (auditRes && Array.isArray(auditRes)) {
        setAuditLogs(auditRes.map((a) => mapBackendAuditLog(a)))
        connected = true
      } else {
        setAuditLogs([])
      }
      if (credsRes && Array.isArray(credsRes)) {
        setCredentialCount(credsRes.length)
        connected = true
      }
      if (providersRes && Array.isArray(providersRes)) {
        setProviderCount(providersRes.length)
        connected = true
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
        <PageIntro eyebrow="控制平面" title="系统设置 Settings" description="交易所密钥管理、AI 大模型网关、RBAC 角色权限与不可篡改审计日志" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="控制平面" title="系统设置 Settings" description="正在读取系统状态与 API 审计事件..." />
        <DataState state="loading" title="读取系统设置中" description="GET /api/v1/system/status, GET /api/v1/live/credentials, GET /api/v1/control/model-providers" />
      </div>
    )
  }

  const filteredAuditLogs = auditLogs.filter(
    (log) =>
      log.action.toLowerCase().includes(auditSearch.toLowerCase()) ||
      log.eventType.toLowerCase().includes(auditSearch.toLowerCase()) ||
      log.operator.toLowerCase().includes(auditSearch.toLowerCase()) ||
      (log.traceId && log.traceId.toLowerCase().includes(auditSearch.toLowerCase()))
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="控制平面"
        title="系统设置与 API 网关中心 (Milestone M4 生产就绪)"
        description="机构级安全凭据存证（Binance / OKX / Coinbase）、AI 大模型推理网关（OpenAI / Gemini / Claude / DeepSeek）与不可篡改合规审计"
        action={
          <button className="button button--secondary" onClick={loadSettingsData}>
            <RefreshCw size={14} />
            刷新全局状态
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
            ? '✓ 已接入生产级 API 控制平面: /api/v1/live/credentials, /api/v1/control/model-providers, /api/v1/audit/events'
            : '⚠ 控制平面后端 API 暂未连接，请检查网关服务状态'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'Control & Gateway API Live' : 'Offline Mode'}
        </StatusBadge>
      </div>

      <Panel
        title="控制平面配置中心"
        subtitle="凭证加密隔离、AI 推理网关路由与合规审计追踪"
        action={
          <TabGroup
            tabs={[
              { id: 'exchanges', label: '交易所 API 凭据中心', badge: credentialCount > 0 ? `${credentialCount}` : undefined },
              { id: 'ai_models', label: 'AI 大模型网关', badge: providerCount > 0 ? `${providerCount}` : undefined },
              { id: 'rbac', label: '角色与 RBAC 权限' },
              { id: 'audit', label: '合规审计日志 (Audit Log)', badge: auditLogs.length > 0 ? `${auditLogs.length}` : undefined },
              { id: 'system', label: '系统全局参数 & BFF 节点' },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as any)}
          />
        }
      >
        {activeTab === 'exchanges' && (
          <ExchangeCredentialsManager />
        )}

        {activeTab === 'ai_models' && (
          <AIModelGateway />
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
                  <th>AI 网关配置</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>平台管理员 (Admin)</strong></td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-warning">⚠ 需双人复核</td>
                  <td className="text-positive">✓ AES-256 存证</td>
                  <td className="text-positive">✓ 完全控制</td>
                </tr>
                <tr>
                  <td><strong>量化研究员 (Quant)</strong></td>
                  <td className="text-positive">✓ 完全控制</td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-positive">✓ 仅纸面环境</td>
                  <td className="text-muted">✗ 无权限</td>
                  <td className="text-muted">✗ 无权限</td>
                  <td className="text-positive">✓ 策略调用</td>
                </tr>
                <tr>
                  <td><strong>风控主管 (Risk Officer)</strong></td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-positive">✓ 核心规则配置</td>
                  <td className="text-muted">✗ 只读查看</td>
                  <td className="text-warning">⚠ 审批权</td>
                  <td className="text-muted">✗ 无权限</td>
                  <td className="text-positive">✓ 风控审计调用</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'audit' && (
          <div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
              <div className="search-box" style={{ width: 320 }}>
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
                    <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无匹配的审计事件记录</td></tr>
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
                <div>全局交易模式: <code className="cell-mono text-accent">{systemStatus?.mode || 'paper'}</code></div>
                <div>系统版本: <code className="cell-mono">{systemStatus?.app_version || 'v0.1.0'}</code></div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>API Gateway & BFF 节点</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                <div>应用名称: <code className="cell-mono">{systemStatus?.app_name || 'enterprise-ai-quant'}</code></div>
                <div>应用运行时间: <code className="cell-mono">{systemStatus?.uptime_seconds ? `${Math.floor(systemStatus.uptime_seconds)}s` : '—'}</code></div>
                <div>持久化存储: <code className={`cell-mono text-${systemStatus?.storage?.enabled ? 'positive' : 'negative'}`}>{systemStatus?.storage?.enabled ? `${systemStatus.storage.backend} (已启用)` : '未启用'}</code></div>
                <div>存储 DSN: <code className="cell-mono">{systemStatus?.storage?.dsn_configured ? '已配置' : '未配置'}</code></div>
              </div>
            </div>
          </div>
        )}
      </Panel>
    </div>
  )
}

