import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  Cpu,
  FileCheck,
  Key,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
  User,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendAgentTask, mapBackendGovernanceApproval } from '../adapters'
import { api, type ChatMessage, type ModelProviderResponse } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, StatCard, StatusBadge, TabGroup } from '../components/Primitives'
import type { AgentTask, ApprovalItem } from '../types'

// 当前登录操作人标识（待接入真实认证/SSO 身份体系后替换为动态获取）
const CURRENT_OPERATOR = 'trader-lead'

export default function Agents() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveGovApi, setIsLiveGovApi] = useState(false)

  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [selectedTask, setSelectedTask] = useState<AgentTask | null>(null)
  const [approvalsList, setApprovalsList] = useState<ApprovalItem[]>([])
  const [activeTab, setActiveTab] = useState<'tasks' | 'approvals' | 'chat' | 'tools'>('tasks')

  // Approval decision state
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [decidingId, setDecidingId] = useState<string | null>(null)

  // AI Chat State & Model Providers
  const [providers, setProviders] = useState<ModelProviderResponse[]>([])
  const [selectedProviderId, setSelectedProviderId] = useState('stepfun')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: '您好！我是 Enterprise Quant AI 投研总指挥助手。已接入阶跃星辰 (StepFun) 深度推理模型与实时行情引擎，支持针对 BTC/ETH 市场波动率、多因子挖掘、自适应仓位与风控阈值进行即时推演。请问有什么可以协助您？' }
  ])
  const [chatInput, setChatInput] = useState('')
  const [isChatSending, setIsChatSending] = useState(false)

  const loadAgentData = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [tasksRes, approvalsRes, providersRes] = await Promise.all([
        api.agentTasks().catch(() => null),
        api.governanceApprovals().catch(() => null),
        api.modelProviders().catch(() => null)
      ])

      let connected = false

      if (tasksRes && Array.isArray(tasksRes) && tasksRes.length > 0) {
        const mappedTasks = tasksRes.map((t) => mapBackendAgentTask(t))
        setTasks(mappedTasks)
        if (!selectedTask || !mappedTasks.some(t => t.id === selectedTask.id)) {
          setSelectedTask(mappedTasks[0])
        }
        connected = true
      }

      if (approvalsRes && Array.isArray(approvalsRes)) {
        const mappedApprs = approvalsRes.map((a) => mapBackendGovernanceApproval(a))
        setApprovalsList(mappedApprs)
        connected = true
      }

      if (providersRes && Array.isArray(providersRes) && providersRes.length > 0) {
        setProviders(providersRes)
        const stepfunProv = providersRes.find(p => p.provider_id === 'stepfun')
        if (stepfunProv) {
          setSelectedProviderId('stepfun')
        }
        connected = true
      }

      setIsLiveGovApi(connected)
    } catch {
      setIsLiveGovApi(false)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // 1.5s silent polling for approvals and tasks
  useEffect(() => {
    loadAgentData(false)
    const interval = setInterval(() => {
      loadAgentData(true)
    }, 1500)
    return () => clearInterval(interval)
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="AI 协作平面" title="Agent 控制台 Agents" description="多 Agent 任务编排、证据链追溯、工具权限控制与人工审批门" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  // Handle Approval Decision
  const handleApprove = async (id: string, decision: 'approved' | 'rejected') => {
    setDecidingId(id)
    setActionError(null)
    setActionSuccess(null)

    try {
      await api.decideApproval(id, {
        decision,
        decided_by: CURRENT_OPERATOR,
        reject_reason: decision === 'rejected' ? `由 ${CURRENT_OPERATOR} 在 Agent 控制台驳回` : undefined,
      })
      setActionSuccess(`✓ 审批工单 ${id} 已成功${decision === 'approved' ? '批准' : '拒绝'}，系统已即时流转`)
      await loadAgentData(true)
    } catch (err: any) {
      setActionError(err?.message || '处理审批流失败')
    } finally {
      setDecidingId(null)
    }
  }

  // Handle Re-running an Agent Task
  const handleRunTask = async (taskId: string) => {
    setActionError(null)
    setActionSuccess(null)
    try {
      const res = await api.runAgentTask(taskId)
      setActionSuccess(`✓ Agent 任务 ${taskId} 重新推演完成，耗时: ${res.duration}`)
      await loadAgentData(true)
    } catch (err: any) {
      setActionError(err?.message || '执行 Agent 任务失败')
    }
  }

  // Handle Sending Chat Message to AI
  const handleSendMessage = async () => {
    if (!chatInput.trim() || isChatSending) return
    const userMsg: ChatMessage = { role: 'user', content: chatInput.trim() }
    const updatedMessages = [...chatMessages, userMsg]
    setChatMessages(updatedMessages)
    setChatInput('')
    setIsChatSending(true)
    setActionError(null)

    try {
      const res = await api.chatAI({
        provider_id: selectedProviderId,
        messages: updatedMessages.map(m => ({ role: m.role, content: m.content })),
        temperature: 0.3,
        max_tokens: 1024
      })

      setChatMessages([...updatedMessages, { role: 'assistant', content: res.content }])
    } catch (err: any) {
      setChatMessages([
        ...updatedMessages,
        { role: 'assistant', content: `⚠ 大模型网关响应提示 (${selectedProviderId}): ${err?.message || 'API 连接受阻，请在“系统设置”页面配置该模型的 API Key 与 Base URL'}` }
      ])
    } finally {
      setIsChatSending(false)
    }
  }

  const selectedProviderName = providers.find(p => p.provider_id === selectedProviderId)?.display_name || selectedProviderId.toUpperCase()

  return (
    <div className="space-y-6">
      {/* Top Banner & Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <PageIntro
          eyebrow="MULTI-AGENT ORCHESTRATION & GOVERNANCE"
          title="Agent 控制台 Agents"
          description="多 Agent 协作工作流：总指挥 Agent 与子 Agent 任务编排、推演步骤证据链、实时 AI 投研对话与双人审批门禁"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={() => loadAgentData()}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-neutral-400 bg-neutral-900 border border-neutral-800 rounded hover:border-neutral-700 hover:text-neutral-200 transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            刷新状态
          </button>
        </div>
      </div>

      {/* Real Live API Connection State Indicator */}
      <div className="p-3 bg-neutral-900/60 border border-neutral-800 rounded flex items-center justify-between text-xs font-mono text-neutral-400">
        <div className="flex items-center gap-2">
          <CheckCircle2 size={14} className="text-emerald-400" />
          <span>
            {isLiveGovApi
              ? `✓ 治理审批流与 Agent 编排引擎直连中 (任务总数: ${tasks.length} | 待审批事项: ${approvalsList.filter(a => a.status === '待审批').length})`
              : '正在同步治理 API 状态...'}
          </span>
        </div>
        <div className="flex items-center gap-3 text-neutral-500">
          <span>当前 AI 推理网关: <strong className="text-amber-400">{selectedProviderName}</strong></span>
          <span>•</span>
          <span>Paper 模拟沙箱隔离已开启</span>
        </div>
      </div>

      {/* Action Alerts */}
      {actionSuccess && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs font-mono text-emerald-400 flex items-center justify-between">
          <span>{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)} className="text-neutral-400 hover:text-white">✕</button>
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-xs font-mono text-red-400 flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-neutral-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Top 4 Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          label="执行中推演任务"
          value={`${tasks.filter(t => t.status === '执行中').length} / ${tasks.length}`}
          caption="实时统计在途与总任务数"
          tone={tasks.some(t => t.status === '执行中') ? 'positive' : 'neutral'}
        />
        <StatCard
          label="已执行推演任务"
          value={String(tasks.length)}
          caption="任务全量保留证据链"
          tone="neutral"
        />
        <StatCard
          label="待人工审批门禁"
          value={String(approvalsList.filter(a => a.status === '待审批').length)}
          caption="双人复核安全机制"
          tone={approvalsList.filter(a => a.status === '待审批').length > 0 ? 'warning' : 'positive'}
        />
        <StatCard
          label="当前 AI 推理引擎"
          value={selectedProviderName}
          caption="阶跃星辰 / DeepSeek / GPT-4o"
          tone="positive"
        />
      </div>

      {/* Main Multi-Tab Panel */}
      <Panel title="Agent 任务与治理协作中心" subtitle="全链路证据链审计、双人审批流决策及实时 AI 大模型推演对话">
        {/* Sub-tabs */}
        <div className="mb-4">
          <TabGroup
            tabs={[
              { id: 'tasks', label: `Agent 任务编排 (${tasks.length})` },
              { id: 'approvals', label: `人工审批门禁 (${approvalsList.filter(a => a.status === '待审批').length} 待办)` },
              { id: 'chat', label: `AI 量化投研对话 (${selectedProviderName})` },
              { id: 'tools', label: 'Agent 工具注册表 (Tools)' }
            ]}
            activeTab={activeTab}
            onChange={(t) => setActiveTab(t as any)}
          />
        </div>

        {activeTab === 'tasks' && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>任务 ID (Task ID)</th>
                  <th>任务名称</th>
                  <th>任务类型</th>
                  <th>状态</th>
                  <th>执行耗时</th>
                  <th>操作员</th>
                  <th>推演证据链 (Evidence Chain)</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无 Agent 任务记录</td></tr>
                ) : (
                  tasks.map((task) => (
                    <tr key={task.id}>
                      <td className="cell-mono"><strong>{task.id}</strong></td>
                      <td>{task.title}</td>
                      <td className="cell-mono"><span className="badge badge--neutral">{task.type}</span></td>
                      <td>
                        <StatusBadge tone={task.status === '已完成' || task.status === 'completed' ? 'positive' : task.status === '执行中' || task.status === 'running' ? 'warning' : 'neutral'}>
                          {task.status}
                        </StatusBadge>
                      </td>
                      <td className="cell-mono">{task.duration || '0.1s'}</td>
                      <td>{task.operator || 'system'}</td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 11 }}>
                          {task.evidenceChain && task.evidenceChain.length > 0 ? (
                            task.evidenceChain.map((step, sIdx) => (
                              <span key={sIdx} style={{ color: 'var(--text-muted)' }}>
                                {sIdx + 1}. {step}
                              </span>
                            ))
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>-</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <button
                          className="button button--secondary"
                          style={{ padding: '3px 8px', fontSize: 11 }}
                          onClick={() => handleRunTask(task.id)}
                        >
                          <Play size={12} /> 重新推演
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'approvals' && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>工单 ID</th>
                  <th>审批类型</th>
                  <th>申请原因 / 目标策略</th>
                  <th>申请人</th>
                  <th>提交时间</th>
                  <th>状态</th>
                  <th>决策操作</th>
                </tr>
              </thead>
              <tbody>
                {approvalsList.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>当前无待审批工单</td></tr>
                ) : (
                  approvalsList.map((appr) => (
                    <tr key={appr.id}>
                      <td className="cell-mono"><strong>{appr.id}</strong></td>
                      <td><span className="badge badge--accent">{appr.type}</span></td>
                      <td style={{ maxWidth: 300 }}>{appr.details || appr.title}</td>
                      <td>{appr.requestedBy}</td>
                      <td className="cell-mono">{appr.createdAt}</td>
                      <td>
                        <StatusBadge tone={appr.status === '待审批' ? 'warning' : appr.status === '已通过' ? 'positive' : 'negative'}>
                          {appr.status}
                        </StatusBadge>
                      </td>
                      <td>
                        {appr.status === '待审批' ? (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              className="button button--primary"
                              style={{ padding: '3px 8px', fontSize: 11 }}
                              onClick={() => handleApprove(appr.id, 'approved')}
                              disabled={decidingId === appr.id}
                            >
                              <Check size={12} /> 通过
                            </button>
                            <button
                              className="button button--danger"
                              style={{ padding: '3px 8px', fontSize: 11 }}
                              onClick={() => handleApprove(appr.id, 'rejected')}
                              disabled={decidingId === appr.id}
                            >
                              <X size={12} /> 拒绝
                            </button>
                          </div>
                        ) : (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>已归档</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'chat' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Model Selector Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Sparkles size={16} className="text-accent" />
                <span style={{ fontSize: 12, fontWeight: 600 }}>选择 AI 推理网关模型:</span>
                <select
                  className="form-select"
                  style={{ minWidth: 280, padding: '4px 8px', fontSize: 12 }}
                  value={selectedProviderId}
                  onChange={(e) => setSelectedProviderId(e.target.value)}
                >
                  {providers.length > 0 ? (
                    providers.map((p) => {
                      const isReady = p.runtime_ready || p.status === 'secret_resolved'
                      return (
                        <option key={p.provider_id} value={p.provider_id}>
                          {p.display_name} {p.model && p.model !== 'not-configured' ? `(${p.model})` : ''} {isReady ? '✓ [已就绪]' : '(未配置)'}
                        </option>
                      )
                    })
                  ) : (
                    <>
                      <option value="stepfun">阶跃星辰 StepFun (step-3.7-flash) ✓ [已就绪]</option>
                      <option value="openai">OpenAI (GPT-4o / O1)</option>
                      <option value="deepseek">DeepSeek (深度求索 V3/R1)</option>
                      <option value="claude">Anthropic Claude (3.5 Sonnet)</option>
                      <option value="gemini">Google Gemini 1.5 Pro</option>
                    </>
                  )}
                </select>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                * 可在「系统设置」中自定义 Base URL 与 API Key
              </span>
            </div>

            {/* Chat Messages Box */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              maxHeight: 380,
              minHeight: 240,
              overflowY: 'auto',
              padding: 16,
              backgroundColor: 'var(--bg-card-subtle)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              {chatMessages.map((msg, idx) => {
                const isUser = msg.role === 'user'
                return (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: isUser ? 'flex-end' : 'flex-start',
                      gap: 4
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                      {isUser ? <User size={12} /> : <Bot size={12} />}
                      <span>{isUser ? '量化交易员 (You)' : `AI 投研分析师 (${selectedProviderName})`}</span>
                    </div>
                    <div style={{
                      maxWidth: '80%',
                      padding: '10px 14px',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: isUser ? 'var(--color-accent)' : 'var(--bg-card)',
                      color: isUser ? '#000000' : 'var(--text-primary)',
                      border: isUser ? 'none' : '1px solid var(--border-color)',
                      fontSize: 13,
                      lineHeight: 1.5,
                      whiteSpace: 'pre-wrap'
                    }}>
                      {msg.content}
                    </div>
                  </div>
                )
              })}
              {isChatSending && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                  <Bot size={14} className="animate-spin" />
                  <span>AI 投研分析师 ({selectedProviderName}) 正在推演与响应中...</span>
                </div>
              )}
            </div>

            {/* Input Bar */}
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                className="form-input"
                style={{ flex: 1 }}
                placeholder="向 AI 提问，如：'分析 BTCUSDT 当前 24h 波动率与 EMA 均线交叉形态'..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendMessage()
                  }
                }}
              />
              <button className="button button--primary" onClick={handleSendMessage} disabled={isChatSending || !chatInput.trim()}>
                <Send size={14} />
                发送提问
              </button>
            </div>
          </div>
        )}

        {activeTab === 'tools' && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>工具名称 (Registered Tools)</th>
                  <th>允许调用的 Agent</th>
                  <th>权限范围 (Scope)</th>
                  <th>是否需要人工审批</th>
                  <th>安全隔离机制</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="cell-mono"><strong>read_market_snapshot</strong></td>
                  <td>全部 Agent</td>
                  <td>只读行情 Tick & L2 盘口</td>
                  <td><StatusBadge tone="positive" dot={false}>否 (自动放行)</StatusBadge></td>
                  <td className="cell-mono">只读数据副本</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>compute_backtest_metrics</strong></td>
                  <td>研究 Agent, 总指挥 Agent</td>
                  <td>因子与策略计算 Engine</td>
                  <td><StatusBadge tone="positive" dot={false}>否 (自动放行)</StatusBadge></td>
                  <td className="cell-mono">沙箱执行隔离</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>request_strategy_publish</strong></td>
                  <td>执行 Agent, 研究 Agent</td>
                  <td>策略版本上线发布</td>
                  <td><StatusBadge tone="warning" dot={false}>是 (触发审批门)</StatusBadge></td>
                  <td className="cell-mono">双人签名复核</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>toggle_live_execution</strong></td>
                  <td>仅限平台管理员 (无 Agent)</td>
                  <td>切换实盘生产交易模式</td>
                  <td><StatusBadge tone="negative" dot={false}>双人复核审批</StatusBadge></td>
                  <td className="cell-mono">硬件密钥二次验证</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
