import React, { useState, useEffect } from 'react'
import {
  Bot,
  Sparkles,
  Zap,
  Globe,
  Lock,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Send,
  Sliders,
  Check,
  ShieldCheck,
  Cpu,
  Clock,
  Terminal,
  Activity,
  Plus
} from 'lucide-react'
import {
  api,
  type ModelProviderResponse,
  type ModelProviderUpsertRequest,
  type ProviderTestResponse,
  type ChatResponse,
} from '../api'
import { StatusBadge, Modal } from './Primitives'

interface ProviderTestState {
  [providerId: string]: {
    loading: boolean
    result?: ProviderTestResponse
    latencyMs?: number
    error?: string
  }
}

interface ProviderMetaConfig {
  id: string
  name: string
  defaultBaseUrl: string
  defaultModel: string
  suggestedModels: string[]
  defaultSecretRef: string
  accentColor: string
  description: string
  iconLabel: string
}

const PRESET_PROVIDERS: ProviderMetaConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI (GPT-4o / O1)',
    defaultBaseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o',
    suggestedModels: ['gpt-4o', 'gpt-4o-mini', 'o1-preview', 'o1-mini'],
    defaultSecretRef: 'env://OPENAI_API_KEY',
    accentColor: '#10A37F',
    description: '业界标杆大模型，支持高级推理、策略代码生成与量化研究报告撰写',
    iconLabel: 'GPT'
  },
  {
    id: 'deepseek',
    name: 'DeepSeek (深度求索)',
    defaultBaseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    suggestedModels: ['deepseek-chat', 'deepseek-reasoner'],
    defaultSecretRef: 'env://DEEPSEEK_API_KEY',
    accentColor: '#4D6BFE',
    description: '深度推理与数学逻辑专精模型，极高性价比与强大的代码/行情推理能力',
    iconLabel: 'DS'
  },
  {
    id: 'gemini',
    name: 'Google Gemini (双子座)',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    defaultModel: 'gemini-1.5-pro',
    suggestedModels: ['gemini-1.5-pro', 'gemini-1.5-flash'],
    defaultSecretRef: 'env://GEMINI_API_KEY',
    accentColor: '#8E75FF',
    description: '超长上下文窗口多模态大模型，适合海量研报研读与全天候市场信息提炼',
    iconLabel: 'GEM'
  },
  {
    id: 'claude',
    name: 'Anthropic Claude (克劳德)',
    defaultBaseUrl: 'https://api.anthropic.com/v1',
    defaultModel: 'claude-3-5-sonnet-20241022',
    suggestedModels: ['claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307', 'claude-3-opus-20240229'],
    defaultSecretRef: 'env://ANTHROPIC_API_KEY',
    accentColor: '#D97706',
    description: '精细化逻辑与代码能力，适合编写严谨的风控规则引擎与回测算法',
    iconLabel: 'CL'
  },
  {
    id: 'stepfun',
    name: '阶跃星辰 StepFun',
    defaultBaseUrl: 'https://api.stepfun.com/step_plan/v1',
    defaultModel: 'step-3.7-flash',
    suggestedModels: ['step-2-16k', 'step-1-8k', 'step-1-32k', 'step-1v-32k', 'step-2-16k-nightly'],
    defaultSecretRef: 'env://STEPFUN_API_KEY',
    accentColor: '#FF6B35',
    description: '国产高性能推理大模型，擅长深度思考与复杂逻辑推理，适合策略分析与市场研判',
    iconLabel: 'SF'
  }
]

const ALL_CAPABILITIES = [
  { id: 'chat', label: '对话交互 (chat)' },
  { id: 'market_analysis', label: '市场行情分析 (market_analysis)' },
  { id: 'code_generation', label: '策略代码生成 (code_generation)' },
  { id: 'risk_audit', label: '风控安全审查 (risk_audit)' },
  { id: 'reasoning', label: '深度逻辑推理 (reasoning)' }
]

export function AIModelGateway() {
  const [providers, setProviders] = useState<ModelProviderResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [testStates, setTestStates] = useState<ProviderTestState>({})

  // Edit / Configuration Form State
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null)
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editBaseUrl, setEditBaseUrl] = useState('')
  const [editModel, setEditModel] = useState('')
  const [editSecretRef, setEditSecretRef] = useState('')
  const [editEnabled, setEditEnabled] = useState(true)
  const [editCapabilities, setEditCapabilities] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null)
  const [saveErrorMessage, setSaveErrorMessage] = useState<string | null>(null)

  // Interactive Sandbox / Prompt Testing State
  const [selectedChatProvider, setSelectedChatProvider] = useState<string>('deepseek')
  const [promptMessage, setPromptMessage] = useState('请分析当前 BTC/USDT 在波动率放大时的跨交易所套利风险与仓位建议。')
  const [chatSubmitting, setChatSubmitting] = useState(false)
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)

  const fetchProviders = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.modelProviders()
      setProviders(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setError(err?.message || '读取 AI 大模型网关配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
  }, [])

  const handleOpenEdit = (pId: string) => {
    const existing = providers.find(p => p.provider_id === pId)
    const preset = PRESET_PROVIDERS.find(p => p.id === pId)

    setEditingProviderId(pId)
    setEditDisplayName(existing?.display_name || preset?.name || pId)
    setEditBaseUrl(existing?.base_url || preset?.defaultBaseUrl || 'https://api.openai.com/v1')
    setEditModel(existing?.model || preset?.defaultModel || 'gpt-4o')
    setEditSecretRef(existing?.secret_ref || preset?.defaultSecretRef || `env://${pId.toUpperCase()}_API_KEY`)
    setEditEnabled(existing?.enabled ?? true)
    setEditCapabilities(existing?.capabilities && existing.capabilities.length > 0 ? existing.capabilities : ['chat', 'market_analysis'])
    setSaveSuccessMessage(null)
    setSaveErrorMessage(null)
  }

  const handleToggleCapability = (capId: string) => {
    if (editCapabilities.includes(capId)) {
      setEditCapabilities(editCapabilities.filter(c => c !== capId))
    } else {
      setEditCapabilities([...editCapabilities, capId])
    }
  }

  const handleSaveProvider = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingProviderId) return

    setSaveErrorMessage(null)
    setSaveSuccessMessage(null)

    // SSRF & Protocol Validation
    const cleanUrl = editBaseUrl.trim()
    if (!cleanUrl.startsWith('https://')) {
      setSaveErrorMessage('Base URL 必须以 https:// 开头（严格执行安全传输与 SSRF 防护协议）')
      return
    }

    if (!editModel.trim()) {
      setSaveErrorMessage('模型名称不可为空')
      return
    }

    setSaving(true)
    const payload: ModelProviderUpsertRequest = {
      provider_id: editingProviderId,
      display_name: editDisplayName.trim(),
      base_url: cleanUrl,
      model: editModel.trim(),
      secret_ref: editSecretRef.trim() ? editSecretRef.trim() : null,
      enabled: editEnabled,
      capabilities: editCapabilities
    }

    try {
      await api.upsertModelProvider(editingProviderId, payload)
      setSaveSuccessMessage(`模型供应商 [${editDisplayName}] 配置更新成功！`)
      await fetchProviders()
      setTimeout(() => {
        setEditingProviderId(null)
      }, 1000)
    } catch (err: any) {
      setSaveErrorMessage(err?.message || '保存配置失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTestProvider = async (pId: string) => {
    const startTime = performance.now()
    setTestStates(prev => ({
      ...prev,
      [pId]: { loading: true }
    }))

    try {
      const res = await api.testModelProvider(pId)
      const duration = Math.round(performance.now() - startTime)
      setTestStates(prev => ({
        ...prev,
        [pId]: {
          loading: false,
          result: res,
          latencyMs: duration
        }
      }))
      // refresh status
      fetchProviders()
    } catch (err: any) {
      setTestStates(prev => ({
        ...prev,
        [pId]: {
          loading: false,
          error: err?.message || '连通性测试异常'
        }
      }))
    }
  }

  const handleRunChat = async () => {
    if (!promptMessage.trim()) return
    setChatSubmitting(true)
    setChatError(null)
    setChatResponse(null)

    try {
      const res = await api.chatAI({
        provider_id: selectedChatProvider,
        messages: [
          {
            role: 'system',
            content: '你是由机构级量化系统部署的 AI 策略与风控决策助手。请提供精准、专业、客观的量化分析与代码建议。'
          },
          {
            role: 'user',
            content: promptMessage.trim()
          }
        ],
        temperature: 0.2,
        max_tokens: 1024
      })
      setChatResponse(res)
    } catch (err: any) {
      setChatError(err?.message || 'AI 请求失败，请确认模型已启用且后端 Secret Resolver 已装载有效 API Key')
    } finally {
      setChatSubmitting(false)
    }
  }

  // Merge preset and custom providers
  const displayProviderList = PRESET_PROVIDERS.map(preset => {
    const found = providers.find(p => p.provider_id === preset.id)
    return {
      preset,
      data: found || {
        provider_id: preset.id,
        display_name: preset.name,
        base_url: preset.defaultBaseUrl,
        model: preset.defaultModel,
        secret_ref: preset.defaultSecretRef,
        enabled: false,
        capabilities: ['chat'],
        status: 'not_configured',
        runtime_ready: false,
        updated_at: '',
      }
    }
  })

  // Also include any other providers not in preset
  const otherProviders = providers.filter(p => !PRESET_PROVIDERS.some(pr => pr.id === p.provider_id))

  const activeCount = providers.filter(p => p.enabled).length
  const readyCount = providers.filter(p => p.runtime_ready).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Top Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
            已就绪供应商 (Ready)
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--color-positive)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Cpu size={18} />
            {readyCount} / {providers.length}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
            通过连通性探针验证的在线网关
          </div>
        </div>

        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
            已启用网关 (Active)
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--color-accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Bot size={18} />
            {activeCount}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
            随时接受量化策略与风控调用的路由节点
          </div>
        </div>

        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
            安全隔离机制
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-gold)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <ShieldCheck size={16} />
            Vault / Env 环境变量引用
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
            SSRF 防御与零明文泄露策略
          </div>
        </div>
      </div>

      {/* Security notice */}
      <div
        style={{
          padding: '10px 14px',
          backgroundColor: 'rgba(212, 175, 55, 0.08)',
          border: '1px solid rgba(212, 175, 55, 0.25)',
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          fontSize: 12,
          color: 'var(--color-gold)'
        }}
      >
        <Lock size={16} style={{ flexShrink: 0 }} />
        <div>
          <strong>合规引用指引：</strong> 大模型 API Key 应通过服务器端环境变量（如 <code>env://OPENAI_API_KEY</code>）或 HashiCorp Vault 密钥库引用。前端仅管理端点与模型参数，保障大模型调用链路零明文泄露。
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, backgroundColor: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-md)', color: 'var(--color-negative)', fontSize: 12 }}>
          <AlertTriangle size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
          {error}
        </div>
      )}

      {/* Grid of 4 Preset Providers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
        {displayProviderList.map(({ preset, data }) => {
          const testState = testStates[preset.id]
          const isReady = data.runtime_ready
          const isEnabled = data.enabled

          return (
            <div
              key={preset.id}
              style={{
                background: 'var(--bg-card)',
                border: isReady ? '1px solid rgba(0, 192, 135, 0.4)' : isEnabled ? '1px solid var(--border-color)' : '1px dashed var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: 16,
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                position: 'relative',
                boxShadow: isReady ? '0 0 12px rgba(0, 192, 135, 0.1)' : 'var(--shadow-sm)',
                opacity: isEnabled ? 1 : 0.82
              }}
            >
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-card-subtle)',
                      border: `1px solid ${preset.accentColor}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 800,
                      fontSize: 12,
                      color: preset.accentColor
                    }}
                  >
                    {preset.iconLabel}
                  </div>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {data.display_name || preset.name}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      模型: <code className="cell-mono text-accent">{data.model || preset.defaultModel}</code>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <StatusBadge
                    tone={isReady ? 'positive' : isEnabled ? 'warning' : 'neutral'}
                    dot={true}
                  >
                    {isReady ? 'Runtime Ready' : isEnabled ? 'Configured' : 'Disabled'}
                  </StatusBadge>
                </div>
              </div>

              {/* Description */}
              <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                {preset.description}
              </div>

              {/* Config Details Panel */}
              <div style={{ background: 'var(--bg-input)', padding: '10px 12px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Base URL:</span>
                  <span className="cell-mono text-dim" style={{ wordBreak: 'break-all', maxWidth: '70%', textAlign: 'right' }}>
                    {data.base_url || preset.defaultBaseUrl}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Secret 引用:</span>
                  <span className="cell-mono" style={{ color: 'var(--color-gold)' }}>
                    {data.secret_ref || '未配置引用'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)' }}>路由就绪状态:</span>
                  <span style={{ color: isReady ? 'var(--color-positive)' : 'var(--text-muted)', fontWeight: 600 }}>
                    {data.status || '未配置'}
                  </span>
                </div>

                {/* Capabilities tags */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {(data.capabilities || ['chat']).map(cap => (
                    <span
                      key={cap}
                      style={{
                        fontSize: 10,
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-xs)',
                        background: 'rgba(53, 114, 239, 0.12)',
                        color: '#93C5FD',
                        border: '1px solid rgba(53, 114, 239, 0.25)'
                      }}
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </div>

              {/* Ping / Test Latency Output */}
              {testState?.loading && (
                <div style={{ padding: '6px 10px', background: 'rgba(53, 114, 239, 0.1)', borderRadius: 'var(--radius-xs)', fontSize: 11, color: '#93C5FD', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <RefreshCw size={12} className="spin" />
                  正在测试模型端点连通性与 API 延迟...
                </div>
              )}
              {testState?.result && (
                <div
                  style={{
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-xs)',
                    fontSize: 11,
                    backgroundColor: testState.result.runtime_ready ? 'rgba(0, 192, 135, 0.12)' : 'rgba(212, 175, 55, 0.12)',
                    border: `1px solid ${testState.result.runtime_ready ? 'rgba(0, 192, 135, 0.3)' : 'rgba(212, 175, 55, 0.3)'}`,
                    color: testState.result.runtime_ready ? 'var(--color-positive)' : 'var(--color-warning)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 600 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {testState.result.runtime_ready ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                      探针状态: {testState.result.status}
                    </span>
                    {testState.latencyMs !== undefined && (
                      <span className="cell-mono text-positive" style={{ fontSize: 11 }}>
                        ⏱ {testState.latencyMs}ms
                      </span>
                    )}
                  </div>
                  <div style={{ marginTop: 3, fontSize: 10.5, opacity: 0.9 }}>
                    {testState.result.message}
                  </div>
                </div>
              )}
              {testState?.error && (
                <div style={{ padding: '6px 10px', borderRadius: 'var(--radius-xs)', fontSize: 11, background: 'rgba(255, 77, 79, 0.12)', color: 'var(--color-negative)' }}>
                  测试错误: {testState.error}
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8, borderTop: '1px solid var(--border-subtle)', marginTop: 'auto' }}>
                <button
                  className="button button--secondary"
                  onClick={() => handleTestProvider(preset.id)}
                  disabled={testState?.loading}
                  style={{ fontSize: 11, padding: '4px 10px' }}
                >
                  <Activity size={12} className={testState?.loading ? 'spin' : ''} />
                  Ping / 连通性测试
                </button>

                <button
                  className="button button--primary"
                  onClick={() => handleOpenEdit(preset.id)}
                  style={{ fontSize: 11, padding: '4px 10px' }}
                >
                  <Sliders size={12} />
                  配置参数
                </button>
              </div>
            </div>
          )
        })}

        {/* Any custom providers from backend */}
        {otherProviders.map(p => (
          <div
            key={p.provider_id}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: 16,
              display: 'flex',
              flexDirection: 'column',
              gap: 12
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{p.display_name}</div>
              <StatusBadge tone={p.runtime_ready ? 'positive' : 'warning'}>{p.status}</StatusBadge>
            </div>
            <div className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {p.base_url} · {p.model}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'auto' }}>
              <button className="button button--secondary" onClick={() => handleOpenEdit(p.provider_id)} style={{ fontSize: 11 }}>
                编辑
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Interactive AI Strategy & Prompt Testing Sandbox */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-md)',
          padding: 18,
          display: 'flex',
          flexDirection: 'column',
          gap: 14
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Sparkles size={16} color="var(--color-gold)" />
              AI 策略分析与决策探针体验台 (Runtime Sandbox)
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              调用后端 <code>POST /api/v1/ai/chat</code>，端到端验证大模型网关与 AI 策略引擎的实时推理能力
            </div>
          </div>

          {/* Provider selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>指定调用模型:</span>
            <select
              className="form-select cell-mono"
              value={selectedChatProvider}
              onChange={(e) => setSelectedChatProvider(e.target.value)}
              disabled={chatSubmitting}
              style={{ fontSize: 12, padding: '4px 8px' }}
            >
              {PRESET_PROVIDERS.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              {otherProviders.map(p => (
                <option key={p.provider_id} value={p.provider_id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Input box */}
        <div style={{ display: 'flex', gap: 10 }}>
          <textarea
            className="form-input"
            rows={2}
            value={promptMessage}
            onChange={(e) => setPromptMessage(e.target.value)}
            placeholder="输入策略分析 Prompt 指令..."
            style={{ resize: 'vertical', width: '100%', fontSize: 12 }}
            disabled={chatSubmitting}
          />
          <button
            className="button button--gold"
            onClick={handleRunChat}
            disabled={chatSubmitting || !promptMessage.trim()}
            style={{ flexShrink: 0, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            {chatSubmitting ? (
              <>
                <RefreshCw size={14} className="spin" />
                推理中...
              </>
            ) : (
              <>
                <Send size={14} />
                执行 AI 探针
              </>
            )}
          </button>
        </div>

        {/* Chat Error */}
        {chatError && (
          <div style={{ padding: 10, background: 'rgba(255, 77, 79, 0.12)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-negative)', fontSize: 12 }}>
            <AlertTriangle size={13} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
            {chatError}
          </div>
        )}

        {/* Chat Response */}
        {chatResponse && (
          <div
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: 14,
              display: 'flex',
              flexDirection: 'column',
              gap: 10
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>供应商: <strong style={{ color: 'var(--text-primary)' }}>{chatResponse.provider_id}</strong></span>
                <span>模型: <code className="cell-mono text-accent">{chatResponse.model}</code></span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="cell-mono text-positive">⏱ 耗时: {chatResponse.latency_ms}ms</span>
                <StatusBadge tone="positive" dot={false}>状态: {chatResponse.status}</StatusBadge>
              </div>
            </div>

            <div style={{ fontSize: 12.5, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
              {chatResponse.content}
            </div>

            {chatResponse.usage && (
              <div style={{ fontSize: 10.5, color: 'var(--text-dim)', textAlign: 'right' }}>
                Token 消耗统计: {JSON.stringify(chatResponse.usage)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Edit / Configure Modal */}
      <Modal
        isOpen={Boolean(editingProviderId)}
        onClose={() => {
          if (!saving) setEditingProviderId(null)
        }}
        title={`配置 AI 模型网关: ${editDisplayName || editingProviderId}`}
      >
        <form onSubmit={handleSaveProvider} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Display Name */}
          <div className="form-group">
            <label>显示名称 (Display Name) *</label>
            <input
              type="text"
              className="form-input"
              value={editDisplayName}
              onChange={(e) => setEditDisplayName(e.target.value)}
              required
              disabled={saving}
            />
          </div>

          {/* Base URL */}
          <div className="form-group">
            <label>自定义 Base URL (必须为 HTTPS 公网端点) *</label>
            <input
              type="url"
              className="form-input cell-mono"
              placeholder="https://api.openai.com/v1"
              value={editBaseUrl}
              onChange={(e) => setEditBaseUrl(e.target.value)}
              required
              disabled={saving}
            />
            <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
              🔒 严格防御 SSRF：禁止配置私网 IP (如 127.0.0.1、192.168.x.x) 或 AWS Metadata
            </span>
          </div>

          {/* Model Name */}
          <div className="form-group">
            <label>模型标识 (Model Identifier) *</label>
            <input
              type="text"
              className="form-input cell-mono"
              placeholder="如 gpt-4o 或 deepseek-chat"
              value={editModel}
              onChange={(e) => setEditModel(e.target.value)}
              required
              disabled={saving}
            />
            {/* Suggestions */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>常用预设:</span>
              {(PRESET_PROVIDERS.find(p => p.id === editingProviderId)?.suggestedModels || []).map(sugg => (
                <button
                  key={sugg}
                  type="button"
                  onClick={() => setEditModel(sugg)}
                  style={{
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-xs)',
                    fontSize: 10,
                    color: 'var(--color-accent)',
                    cursor: 'pointer',
                    padding: '1px 5px'
                  }}
                >
                  {sugg}
                </button>
              ))}
            </div>
          </div>

          {/* Secret Ref */}
          <div className="form-group">
            <label>API Key 环境变量引用 (Secret Ref) *</label>
            <input
              type="text"
              className="form-input cell-mono"
              placeholder="如 env://OPENAI_API_KEY"
              value={editSecretRef}
              onChange={(e) => setEditSecretRef(e.target.value)}
              disabled={saving}
            />
            <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
              安全格式: <code>env://VARIABLE_NAME</code> 或 <code>vault://secret/path</code>
            </span>
          </div>

          {/* Enabled switch */}
          <div className="form-group">
            <label>网关启用状态</label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 12 }}>
              <input
                type="checkbox"
                checked={editEnabled}
                onChange={(e) => setEditEnabled(e.target.checked)}
                disabled={saving}
              />
              <span>启用此模型网关，允许量化策略和风控系统调用</span>
            </label>
          </div>

          {/* Capabilities */}
          <div className="form-group">
            <label>模型能力标签 (Capabilities)</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ALL_CAPABILITIES.map(cap => {
                const checked = editCapabilities.includes(cap.id)
                return (
                  <button
                    type="button"
                    key={cap.id}
                    onClick={() => handleToggleCapability(cap.id)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: 11,
                      border: checked ? '1px solid var(--color-accent)' : '1px solid var(--border-color)',
                      background: checked ? 'rgba(53, 114, 239, 0.15)' : 'var(--bg-input)',
                      color: checked ? '#93C5FD' : 'var(--text-muted)',
                      cursor: 'pointer'
                    }}
                  >
                    {checked ? '✓ ' : ''}{cap.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Error & Success Feedback */}
          {saveErrorMessage && (
            <div style={{ padding: 8, backgroundColor: 'rgba(255, 77, 79, 0.15)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-negative)', fontSize: 12 }}>
              {saveErrorMessage}
            </div>
          )}
          {saveSuccessMessage && (
            <div style={{ padding: 8, backgroundColor: 'rgba(0, 192, 135, 0.15)', border: '1px solid rgba(0, 192, 135, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-positive)', fontSize: 12 }}>
              {saveSuccessMessage}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => setEditingProviderId(null)}
              disabled={saving}
            >
              取消
            </button>
            <button
              type="submit"
              className="button button--gold"
              disabled={saving}
            >
              {saving ? (
                <>
                  <RefreshCw size={13} className="spin" />
                  保存配置中...
                </>
              ) : (
                <>
                  <Check size={13} />
                  保存模型配置
                </>
              )}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}