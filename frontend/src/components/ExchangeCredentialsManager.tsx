import React, { useState, useEffect } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Key,
  Lock,
  Eye,
  EyeOff,
  Trash2,
  RefreshCw,
  Plus,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Check,
  Copy,
  Info,
  Server,
  HelpCircle,
} from 'lucide-react'
import { api, type CredentialRedactedResponse, type CredentialSaveRequest, type CredentialTestResponse } from '../api'
import { Modal, StatusBadge } from './Primitives'

interface TestResultMap {
  [connectionId: string]: {
    loading: boolean
    result?: CredentialTestResponse
    error?: string
  }
}

const SERVER_OUTBOUND_IP = '43.108.98.174'

const SUPPORTED_EXCHANGES = [
  { id: 'binance', name: 'Binance (币安)', defaultBaseUrl: 'https://api.binance.com', requiresPassphrase: false, tip: '支持现货与 U 本位合约。如开启 IP 限制请添加白名单。' },
  { id: 'okx', name: 'OKX (欧易)', defaultBaseUrl: 'https://www.okx.com', requiresPassphrase: true, tip: '必须填写 Passphrase（创建 API 时自行设置的密码短语）。' },
  { id: 'coinbase', name: 'Coinbase Advanced', defaultBaseUrl: 'https://api.coinbase.com', requiresPassphrase: false, tip: '支持 Coinbase Advanced 交易通道。' },
]

export function ExchangeCredentialsManager() {
  const [credentials, setCredentials] = useState<CredentialRedactedResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')
  const [testResults, setTestResults] = useState<TestResultMap>({})
  const [copySuccessId, setCopySuccessId] = useState<string | null>(null)
  const [ipCopied, setIpCopied] = useState(false)

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccessMessage, setFormSuccessMessage] = useState<string | null>(null)

  // Form Fields
  const [connectionId, setConnectionId] = useState('')
  const [exchange, setExchange] = useState('binance')
  const [environment, setEnvironment] = useState<'live' | 'testnet'>('live')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [showApiSecret, setShowApiSecret] = useState(false)
  const [showPassphrase, setShowPassphrase] = useState(false)

  // Delete confirmation
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const fetchCredentials = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.liveCredentials()
      setCredentials(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setError(err?.message || '读取交易所 API 凭据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCredentials()
  }, [])

  const resetForm = () => {
    setConnectionId('')
    setExchange('binance')
    setEnvironment('live')
    setApiKey('')
    setApiSecret('')
    setPassphrase('')
    setBaseUrl('')
    setShowApiKey(false)
    setShowApiSecret(false)
    setShowPassphrase(false)
    setFormError(null)
    setFormSuccessMessage(null)
  }

  const handleOpenModal = () => {
    resetForm()
    const autoId = `conn-${exchange}-live`
    setConnectionId(autoId)
    setIsModalOpen(true)
  }

  const handleExchangeChange = (newEx: string) => {
    setExchange(newEx)
    setConnectionId(`conn-${newEx}-${environment}`)
  }

  const handleEnvironmentChange = (newEnv: 'live' | 'testnet') => {
    setEnvironment(newEnv)
    setConnectionId(`conn-${exchange}-${newEnv}`)
  }

  const handleCopyIP = () => {
    navigator.clipboard.writeText(SERVER_OUTBOUND_IP)
    setIpCopied(true)
    setTimeout(() => setIpCopied(false), 2000)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setFormSuccessMessage(null)

    // Form Validation
    const cleanConnId = connectionId.trim().toLowerCase()
    if (!cleanConnId || !/^[a-z0-9_-]+$/.test(cleanConnId)) {
      setFormError('连接标识 (Connection ID) 仅支持小写字母、数字、下划线与短横线，长度 2-64')
      return
    }

    if (!apiKey.trim() || apiKey.trim().length < 8) {
      setFormError('API Key 必须至少包含 8 个字符（请检查是否遗漏）')
      return
    }

    if (!apiSecret.trim() || apiSecret.trim().length < 8) {
      setFormError('API Secret 必须至少包含 8 个字符（请检查是否遗漏）')
      return
    }

    const currentExMeta = SUPPORTED_EXCHANGES.find(item => item.id === exchange)
    if (currentExMeta?.requiresPassphrase && !passphrase.trim()) {
      setFormError(`交易所 ${currentExMeta.name} 强制要求输入 API Passphrase 口令（创建 API 时您自行设定的口令）`)
      return
    }

    setFormSubmitting(true)

    const payload: CredentialSaveRequest = {
      connection_id: cleanConnId,
      exchange: exchange.trim().toLowerCase(),
      api_key: apiKey.trim(),
      api_secret: apiSecret.trim(),
      environment: environment,
      passphrase: passphrase.trim() ? passphrase.trim() : null,
      base_url: baseUrl.trim() ? baseUrl.trim() : null,
    }

    try {
      const saved = await api.saveLiveCredential(payload)
      setFormSuccessMessage(`凭据 [${saved.connection_id}] 已成功通过 AES-256 加密保存！正在自动验证连通性...`)
      
      // Clear sensitive plaintexts immediately
      setApiKey('')
      setApiSecret('')
      setPassphrase('')
      
      // Refresh credentials list
      await fetchCredentials()

      // Auto trigger test
      handleTestCredential(saved.connection_id)

      setTimeout(() => {
        setIsModalOpen(false)
        resetForm()
      }, 1500)
    } catch (err: any) {
      setFormError(err?.message || '保存凭据失败，请检查网络或后端接口')
    } finally {
      setFormSubmitting(false)
    }
  }

  const handleTestCredential = async (connId: string) => {
    setTestResults(prev => ({
      ...prev,
      [connId]: { loading: true }
    }))

    try {
      const res = await api.testLiveCredential(connId)
      setTestResults(prev => ({
        ...prev,
        [connId]: {
          loading: false,
          result: res
        }
      }))
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [connId]: {
          loading: false,
          error: err?.message || '连通性测试异常'
        }
      }))
    }
  }

  const handleDelete = async (connId: string) => {
    setDeletingId(connId)
    try {
      await api.deleteLiveCredential(connId)
      setDeleteConfirmId(null)
      await fetchCredentials()
    } catch (err: any) {
      alert(`删除凭据失败: ${err?.message || '未知错误'}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleCopyFingerprint = (connId: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopySuccessId(connId)
    setTimeout(() => setCopySuccessId(null), 2000)
  }

  const selectedExInfo = SUPPORTED_EXCHANGES.find(item => item.id === exchange)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            已安全配置 <strong style={{ color: 'var(--color-gold)' }}>{credentials.length}</strong> 组机构级交易所凭据
          </div>
          <button
            className="button button--secondary"
            onClick={fetchCredentials}
            disabled={loading}
            style={{ padding: '4px 10px', fontSize: 12 }}
          >
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            刷新凭据
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* IP Whitelist Badge */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 10px',
              background: 'rgba(255, 180, 0, 0.08)',
              border: '1px solid rgba(255, 180, 0, 0.25)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 11,
              color: 'var(--color-gold)',
            }}
          >
            <Server size={12} />
            <span>出口 IP: <strong>{SERVER_OUTBOUND_IP}</strong></span>
            <button
              onClick={handleCopyIP}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-gold)',
                cursor: 'pointer',
                padding: '2px 4px',
                display: 'flex',
                alignItems: 'center',
              }}
              title="复制服务器出口 IP 用于交易所白名单"
            >
              {ipCopied ? <Check size={12} color="var(--color-positive)" /> : <Copy size={12} />}
            </button>
          </div>

          {/* View Toggle */}
          <div style={{ display: 'flex', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
            <button
              onClick={() => setViewMode('cards')}
              style={{
                padding: '4px 10px',
                fontSize: 11,
                border: 'none',
                background: viewMode === 'cards' ? 'var(--bg-card-active)' : 'transparent',
                color: viewMode === 'cards' ? 'var(--color-gold)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontWeight: viewMode === 'cards' ? 600 : 400
              }}
            >
              卡片视图
            </button>
            <button
              onClick={() => setViewMode('table')}
              style={{
                padding: '4px 10px',
                fontSize: 11,
                border: 'none',
                background: viewMode === 'table' ? 'var(--bg-card-active)' : 'transparent',
                color: viewMode === 'table' ? 'var(--color-gold)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontWeight: viewMode === 'table' ? 600 : 400
              }}
            >
              表格视图
            </button>
          </div>

          <button
            className="button button--gold"
            onClick={handleOpenModal}
            style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Plus size={14} />
            录入交易所 API 凭据
          </button>
        </div>
      </div>

      {/* Security Notice */}
      <div
        style={{
          padding: '10px 14px',
          backgroundColor: 'rgba(53, 114, 239, 0.08)',
          border: '1px solid rgba(53, 114, 239, 0.22)',
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          fontSize: 12,
          color: '#93C5FD'
        }}
      >
        <ShieldCheck size={18} style={{ flexShrink: 0, color: 'var(--color-accent)' }} />
        <div>
          <strong>零信任加密存证：</strong> 所有 API Secret 与 Passphrase 经 AES-256 CTR 信封加密后持久化，前端永不回显明文。若交易所开启了 IP 白名单限制，请将服务器出口 IP <strong style={{ color: '#FCD34D' }}>{SERVER_OUTBOUND_IP}</strong> 加入交易所白名单。
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, backgroundColor: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-md)', color: 'var(--color-negative)', fontSize: 12 }}>
          <AlertTriangle size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
          {error}
        </div>
      )}

      {/* Credentials Container */}
      {credentials.length === 0 && !loading ? (
        <div style={{ padding: '36px 20px', textAlign: 'center', background: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)', border: '1px dashed var(--border-color)' }}>
          <Key size={32} style={{ color: 'var(--text-muted)', marginBottom: 10 }} />
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>暂无已录入的交易所 API 凭据</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>点击右上角按钮录入 Binance、OKX 或 Coinbase 的 API 访问密钥</div>
          <button className="button button--primary" onClick={handleOpenModal} style={{ fontSize: 12 }}>
            <Plus size={13} />
            立即录入首个凭据
          </button>
        </div>
      ) : viewMode === 'cards' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: 14 }}>
          {credentials.map((conn) => {
            const testState = testResults[conn.connection_id]
            const isLive = conn.environment === 'live'
            const isFailed = testState?.result?.status === 'failed' || Boolean(testState?.error)

            return (
              <div
                key={conn.connection_id}
                style={{
                  background: 'var(--bg-card)',
                  border: isLive ? '1px solid rgba(255, 77, 79, 0.35)' : '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  boxShadow: 'var(--shadow-card)',
                  position: 'relative'
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <strong style={{ fontSize: 14, color: 'var(--text-primary)' }}>{conn.connection_id}</strong>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: 'var(--radius-xs)',
                          fontSize: 10,
                          fontWeight: 700,
                          backgroundColor: isLive ? 'rgba(255, 77, 79, 0.15)' : 'rgba(53, 114, 239, 0.15)',
                          color: isLive ? 'var(--color-negative)' : 'var(--color-accent)',
                          border: isLive ? '1px solid rgba(255, 77, 79, 0.3)' : '1px solid rgba(53, 114, 239, 0.3)'
                        }}
                      >
                        {isLive ? '🔥 LIVE 实盘' : '🛡️ TESTNET 模拟'}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                      交易所: <span style={{ color: 'var(--color-gold)', fontWeight: 600 }}>{(conn.exchange || '').toUpperCase()}</span>
                    </div>
                  </div>

                  <StatusBadge tone={conn.enabled ? 'positive' : 'neutral'} dot={true}>
                    {conn.enabled ? 'ACTIVE' : 'DISABLED'}
                  </StatusBadge>
                </div>

                {/* Fingerprint Field */}
                <div style={{ padding: '8px 10px', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>SHA-256 脱敏指纹</span>
                    <button
                      onClick={() => handleCopyFingerprint(conn.connection_id, conn.credential_fingerprint || '')}
                      style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3, fontSize: 10 }}
                    >
                      {copySuccessId === conn.connection_id ? (
                        <>
                          <Check size={10} color="var(--color-positive)" />
                          <span style={{ color: 'var(--color-positive)' }}>已复制</span>
                        </>
                      ) : (
                        <>
                          <Copy size={10} />
                          <span>复制指纹</span>
                        </>
                      )}
                    </button>
                  </div>
                  <div className="cell-mono" style={{ fontSize: 11, color: 'var(--text-primary)', wordBreak: 'break-all', marginTop: 4 }}>
                    {conn.credential_fingerprint || '—'}
                  </div>
                </div>

                {/* Meta details */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11 }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>存储状态: </span>
                    <span style={{ color: 'var(--color-positive)', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                      <Lock size={10} />
                      {conn.credential_status}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Passphrase: </span>
                    <span>{conn.has_passphrase ? '✓ 已配置口令' : '无口令'}</span>
                  </div>
                  <div style={{ gridColumn: 'span 2', color: 'var(--text-muted)', fontSize: 10 }}>
                    更新时间: {conn.updated_at ? new Date(conn.updated_at).toLocaleString('zh-CN', { hour12: false }) : '—'}
                  </div>
                </div>

                {/* Probe / Test Feedback */}
                {testState?.loading && (
                  <div style={{ padding: '6px 10px', background: 'rgba(53, 114, 239, 0.1)', borderRadius: 'var(--radius-xs)', fontSize: 11, color: '#93C5FD', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <RefreshCw size={12} className="spin" />
                    正在向交易所发起 Dry-run 连通性探测...
                  </div>
                )}
                {testState?.result && (
                  <div
                    style={{
                      padding: '8px 10px',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: 11,
                      backgroundColor: testState.result.status === 'connected' ? 'rgba(0, 192, 135, 0.12)' : 'rgba(255, 77, 79, 0.12)',
                      border: `1px solid ${testState.result.status === 'connected' ? 'rgba(0, 192, 135, 0.3)' : 'rgba(255, 77, 79, 0.3)'}`,
                      color: testState.result.status === 'connected' ? 'var(--color-positive)' : 'var(--color-negative)'
                    }}
                  >
                    <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                      {testState.result.status === 'connected' ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                      测试状态: {testState.result.status.toUpperCase()}
                    </div>
                    <div style={{ marginTop: 2, fontSize: 10.5, opacity: 0.9 }}>
                      {testState.result.message}
                    </div>
                  </div>
                )}
                {testState?.error && (
                  <div style={{ padding: '8px 10px', borderRadius: 'var(--radius-xs)', fontSize: 11, background: 'rgba(255, 77, 79, 0.12)', color: 'var(--color-negative)' }}>
                    探针异常: {testState.error}
                  </div>
                )}

                {/* Troubleshooting Guide for 401 / Failed Tests */}
                {isFailed && (
                  <div
                    style={{
                      padding: '8px 10px',
                      background: 'rgba(255, 180, 0, 0.08)',
                      border: '1px solid rgba(255, 180, 0, 0.25)',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: 11,
                      color: '#FDE68A',
                      lineHeight: 1.5,
                    }}
                  >
                    <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, color: 'var(--color-gold)' }}>
                      <HelpCircle size={12} />
                      连通性未通过排查指引：
                    </div>
                    <div>1. <strong>环境核对</strong>：若在 OKX 模拟盘创建的 Key 请选【模拟盘】，实盘创建请选【实盘】；</div>
                    <div>2. <strong>Passphrase</strong>：OKX 必填创建 API 时自定义的密码短语；</div>
                    <div>3. <strong>IP 白名单</strong>：若开启了 IP 白名单，请添加本机 IP: <span style={{ color: '#FFF' }}>{SERVER_OUTBOUND_IP}</span>；</div>
                    <div>4. <strong>API 权限</strong>：请确认已开通【读取】与【交易】权限。</div>
                  </div>
                )}

                {/* Actions Bottom */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
                  <button
                    className="button button--secondary"
                    onClick={() => handleTestCredential(conn.connection_id)}
                    disabled={testState?.loading}
                    style={{ fontSize: 11, padding: '4px 8px' }}
                  >
                    <RefreshCw size={12} className={testState?.loading ? 'spin' : ''} />
                    Dry-run 连通性测试
                  </button>

                  {deleteConfirmId === conn.connection_id ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <button
                        className="button button--danger"
                        onClick={() => handleDelete(conn.connection_id)}
                        disabled={deletingId === conn.connection_id}
                        style={{ fontSize: 10, padding: '3px 8px' }}
                      >
                        {deletingId === conn.connection_id ? '删除中...' : '确认销毁'}
                      </button>
                      <button
                        className="button button--secondary"
                        onClick={() => setDeleteConfirmId(null)}
                        style={{ fontSize: 10, padding: '3px 6px' }}
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setDeleteConfirmId(conn.connection_id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        padding: 4,
                        display: 'flex',
                        alignItems: 'center'
                      }}
                      title="删除凭据"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* Table View */
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>连接标识</th>
                <th>交易所</th>
                <th>环境</th>
                <th>AES 加密状态</th>
                <th>脱敏指纹 (Fingerprint)</th>
                <th>Passphrase</th>
                <th>更新时间</th>
                <th>连通性探测</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map((conn) => {
                const testState = testResults[conn.connection_id]
                const isLive = conn.environment === 'live'

                return (
                  <tr key={conn.connection_id}>
                    <td>
                      <strong className="cell-mono">{conn.connection_id}</strong>
                    </td>
                    <td>
                      <span style={{ color: 'var(--color-gold)', fontWeight: 600 }}>{(conn.exchange || '').toUpperCase()}</span>
                    </td>
                    <td>
                      <span
                        style={{
                          padding: '1px 5px',
                          borderRadius: 'var(--radius-xs)',
                          fontSize: 10,
                          fontWeight: 700,
                          backgroundColor: isLive ? 'rgba(255, 77, 79, 0.15)' : 'rgba(53, 114, 239, 0.15)',
                          color: isLive ? 'var(--color-negative)' : 'var(--color-accent)'
                        }}
                      >
                        {isLive ? 'LIVE 实盘' : 'TESTNET 模拟'}
                      </span>
                    </td>
                    <td>
                      <span style={{ color: 'var(--color-positive)', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                        <Lock size={10} />
                        {conn.credential_status}
                      </span>
                    </td>
                    <td className="cell-mono" style={{ fontSize: 11 }}>
                      {conn.credential_fingerprint ? (
                        <span title={conn.credential_fingerprint}>
                          {conn.credential_fingerprint.substring(0, 18)}...
                        </span>
                      ) : '—'}
                    </td>
                    <td>
                      {conn.has_passphrase ? (
                        <span style={{ color: 'var(--color-positive)', fontSize: 11 }}>✓ 已配置</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>无</span>
                      )}
                    </td>
                    <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {conn.updated_at ? new Date(conn.updated_at).toLocaleString('zh-CN', { hour12: false }) : '—'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button
                          className="button button--secondary"
                          onClick={() => handleTestCredential(conn.connection_id)}
                          disabled={testState?.loading}
                          style={{ fontSize: 11, padding: '2px 6px' }}
                        >
                          <RefreshCw size={11} className={testState?.loading ? 'spin' : ''} />
                          测试
                        </button>
                        {testState?.result && (
                          <StatusBadge tone={testState.result.status === 'connected' ? 'positive' : 'negative'} dot={true}>
                            {testState.result.status}
                          </StatusBadge>
                        )}
                      </div>
                    </td>
                    <td>
                      {deleteConfirmId === conn.connection_id ? (
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button
                            className="button button--danger"
                            onClick={() => handleDelete(conn.connection_id)}
                            style={{ fontSize: 10, padding: '2px 6px' }}
                          >
                            确认
                          </button>
                          <button
                            className="button button--secondary"
                            onClick={() => setDeleteConfirmId(null)}
                            style={{ fontSize: 10, padding: '2px 4px' }}
                          >
                            取消
                          </button>
                        </div>
                      ) : (
                        <button
                          className="icon-button"
                          onClick={() => setDeleteConfirmId(conn.connection_id)}
                          style={{ color: 'var(--text-muted)' }}
                          title="删除"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal for Creating New Credential */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          if (!formSubmitting) setIsModalOpen(false)
        }}
        title="录入交易所 API 访问凭据 (AES-256 加密存证)"
      >
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Exchange Selection */}
          <div className="form-group">
            <label>目标交易所 (Target Exchange) *</label>
            <select
              className="form-select"
              value={exchange}
              onChange={(e) => handleExchangeChange(e.target.value)}
              disabled={formSubmitting}
            >
              {SUPPORTED_EXCHANGES.map(item => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            {selectedExInfo && (
              <span style={{ fontSize: 11, color: 'var(--color-gold)', marginTop: 4 }}>
                ℹ️ {selectedExInfo.tip}
              </span>
            )}
          </div>

          {/* Environment Selector */}
          <div className="form-group">
            <label>运行环境 (Trading Environment) *</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button
                type="button"
                onClick={() => handleEnvironmentChange('live')}
                style={{
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: environment === 'live' ? '1px solid var(--color-negative)' : '1px solid var(--border-color)',
                  background: environment === 'live' ? 'rgba(255, 77, 79, 0.15)' : 'var(--bg-input)',
                  color: environment === 'live' ? '#FFA39E' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontWeight: environment === 'live' ? 600 : 400,
                  textAlign: 'left'
                }}
              >
                <div>🔥 Live 实盘环境 (推荐)</div>
                <div style={{ fontSize: 10, opacity: 0.8, marginTop: 2 }}>交易所正式账户与真实资金</div>
              </button>

              <button
                type="button"
                onClick={() => handleEnvironmentChange('testnet')}
                style={{
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: environment === 'testnet' ? '1px solid var(--color-accent)' : '1px solid var(--border-color)',
                  background: environment === 'testnet' ? 'rgba(53, 114, 239, 0.15)' : 'var(--bg-input)',
                  color: environment === 'testnet' ? '#93C5FD' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontWeight: environment === 'testnet' ? 600 : 400,
                  textAlign: 'left'
                }}
              >
                <div>🛡️ Paper / Testnet 模拟</div>
                <div style={{ fontSize: 10, opacity: 0.8, marginTop: 2 }}>OKX 模拟盘或测试网络</div>
              </button>
            </div>
          </div>

          {/* Connection ID */}
          <div className="form-group">
            <label>连接标识 (Connection ID) *</label>
            <input
              type="text"
              className="form-input cell-mono"
              placeholder="如 binance-live-01"
              value={connectionId}
              onChange={(e) => setConnectionId(e.target.value)}
              required
              disabled={formSubmitting}
            />
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              内部唯一路由标识，系统自动生成，可按需修改
            </span>
          </div>

          {/* Server IP Whitelist Notice inside Modal */}
          <div
            style={{
              padding: '8px 12px',
              background: 'rgba(255, 180, 0, 0.08)',
              border: '1px solid rgba(255, 180, 0, 0.25)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 11,
              color: '#FDE68A',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <div>
              <strong>服务器 IP 白名单：</strong> <span style={{ color: '#FFF' }}>{SERVER_OUTBOUND_IP}</span>
            </div>
            <button
              type="button"
              onClick={handleCopyIP}
              className="button button--secondary"
              style={{ padding: '2px 8px', fontSize: 10 }}
            >
              {ipCopied ? '已复制' : '复制 IP'}
            </button>
          </div>

          {/* API Key */}
          <div className="form-group">
            <label>API Key (访问公钥) *</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showApiKey ? 'text' : 'password'}
                className="form-input cell-mono"
                style={{ width: '100%', paddingRight: 36 }}
                placeholder="输入交易所生成的 API Key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
                disabled={formSubmitting}
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                style={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer'
                }}
              >
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* API Secret */}
          <div className="form-group">
            <label>API Secret (私密密钥) *</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showApiSecret ? 'text' : 'password'}
                className="form-input cell-mono"
                style={{ width: '100%', paddingRight: 36 }}
                placeholder="输入交易所生成的 API Secret"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                required
                disabled={formSubmitting}
              />
              <button
                type="button"
                onClick={() => setShowApiSecret(!showApiSecret)}
                style={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer'
                }}
              >
                {showApiSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* Passphrase (Dynamic for OKX) */}
          <div className="form-group">
            <label style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>API Passphrase (口令) {selectedExInfo?.requiresPassphrase ? <strong style={{ color: 'var(--color-negative)' }}>* (OKX 必填)</strong> : '(选填)'}</span>
              {selectedExInfo?.requiresPassphrase && (
                <span style={{ color: 'var(--color-gold)', fontSize: 10 }}>OKX 协议鉴权必备口令</span>
              )}
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassphrase ? 'text' : 'password'}
                className="form-input cell-mono"
                style={{ width: '100%', paddingRight: 36 }}
                placeholder={selectedExInfo?.requiresPassphrase ? '输入创建 OKX Key 时设定的 Passphrase 口令' : '非 OKX 交易所通常无需填写'}
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                required={selectedExInfo?.requiresPassphrase}
                disabled={formSubmitting}
              />
              <button
                type="button"
                onClick={() => setShowPassphrase(!showPassphrase)}
                style={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer'
                }}
              >
                {showPassphrase ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* Optional Base URL */}
          <div className="form-group">
            <label>自定义 REST Base URL (选填)</label>
            <input
              type="url"
              className="form-input cell-mono"
              placeholder={`默认: ${selectedExInfo?.defaultBaseUrl || 'https://api.exchange.com'}`}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              disabled={formSubmitting}
            />
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              留空即使用官方默认端点，可填专属内网反向代理
            </span>
          </div>

          {/* Feedback banners */}
          {formError && (
            <div style={{ padding: 10, backgroundColor: 'rgba(255, 77, 79, 0.15)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-negative)', fontSize: 12 }}>
              {formError}
            </div>
          )}

          {formSuccessMessage && (
            <div style={{ padding: 10, backgroundColor: 'rgba(0, 192, 135, 0.15)', border: '1px solid rgba(0, 192, 135, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-positive)', fontSize: 12 }}>
              {formSuccessMessage}
            </div>
          )}

          {/* Modal Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => setIsModalOpen(false)}
              disabled={formSubmitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="button button--gold"
              disabled={formSubmitting}
            >
              {formSubmitting ? (
                <>
                  <RefreshCw size={13} className="spin" />
                  AES 加密提交中...
                </>
              ) : (
                <>
                  <Lock size={13} />
                  安全加密并保存
                </>
              )}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
