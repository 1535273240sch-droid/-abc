import { AlertCircle, Bot, Check, CheckCircle2, Clock, Cpu, FileCheck, Key, Layers, ShieldCheck, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendGovernanceApproval } from '../adapters'
import { api } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, StatusBadge, TabGroup } from '../components/Primitives'
import { mockAgentTasks, mockApprovals } from '../mockData'
import type { AgentTask, ApprovalItem } from '../types'

export default function Agents() {
  const { globalState, setGlobalState } = useAppState()
  const [selectedTask, setSelectedTask] = useState<AgentTask>(mockAgentTasks[0])
  const [approvalsList, setApprovalsList] = useState<ApprovalItem[]>(mockApprovals)
  const [activeTab, setActiveTab] = useState<'tasks' | 'approvals' | 'tools'>('tasks')
  const [isLiveGovApi, setIsLiveGovApi] = useState(false)

  useEffect(() => {
    api.governanceApprovals()
      .then((res) => {
        if (Array.isArray(res) && res.length > 0) {
          const mapped = res.map((item) => mapBackendGovernanceApproval(item))
          setApprovalsList(mapped)
          setIsLiveGovApi(true)
        }
      })
      .catch(() => {
        setIsLiveGovApi(false)
      })
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="AI 协作平面" title="Agent 控制台 Agents" description="多 Agent 任务编排、证据链追溯、工具权限控制与人工审批门" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  const handleApprove = (id: string, action: 'pass' | 'reject') => {
    // Read-only boundary constraint: simulate local state change only without guessing mutation contract
    setApprovalsList((prev) =>
      prev.map((item) => {
        if (item.id === id) {
          return { ...item, status: action === 'pass' ? '已通过' : '已拒绝' }
        }
        return item
      })
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="AI 协作平面"
        title="Agent 控制台与审批门 (Phase 4 只读接入)"
        description="总指挥 Agent 与执行 Agent 协作监控：工具授权边界隔离，重大生产变更必须经过审批门"
      />

      {/* Demo / Governance API Status Banner Notice */}
      <div
        style={{
          padding: '8px 14px',
          backgroundColor: isLiveGovApi ? 'rgba(0, 192, 135, 0.1)' : 'rgba(250, 173, 20, 0.1)',
          border: `1px solid ${isLiveGovApi ? 'rgba(0, 192, 135, 0.3)' : 'rgba(250, 173, 20, 0.3)'}`,
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 12
        }}
      >
        <span style={{ color: isLiveGovApi ? 'var(--color-positive)' : 'var(--color-warning)' }}>
          {isLiveGovApi
            ? '✓ 已接入 API GET /api/v1/governance/approvals (只读治理视图)'
            : '⚠ 说明：后端 Agent 编排微服务 (agent_orchestrator) 尚未暴露完整 API；当前为 [Demo / Mock 静态推演视图]'}
        </span>
        <StatusBadge tone={isLiveGovApi ? 'positive' : 'warning'} dot={true}>
          {isLiveGovApi ? 'Governance API Live' : 'Demo Orchestrator'}
        </StatusBadge>
      </div>

      {/* Agents Active Grid */}
      <div className="grid-cols-4">
        <div style={{ padding: 14, backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>总指挥 Agent</strong>
            <StatusBadge tone="positive">在线</StatusBadge>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>模型: Gemini 3.6 Pro</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>职责: 需求分解、架构校验、任务编排</div>
        </div>

        <div style={{ padding: 14, backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>研究 Agent</strong>
            <StatusBadge tone="positive">在线</StatusBadge>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>模型: DeepSeek Quant</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>职责: 因子挖掘、回测与归因分析</div>
        </div>

        <div style={{ padding: 14, backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>执行 Agent</strong>
            <StatusBadge tone="accent">空闲</StatusBadge>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>模型: OpenCode / Backend</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>职责: 订单路由、状态机与对账</div>
        </div>

        <div style={{ padding: 14, backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>数据 Agent</strong>
            <StatusBadge tone="warning">巡检中</StatusBadge>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>模型: Gemini Flash</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>职责: 行情质量监控、离群值过滤</div>
        </div>
      </div>

      {/* Main Panel Tabs */}
      <Panel
        title="Agent 协作与治理面板"
        subtitle="任务证据链与 Human-in-the-Loop 审批门 (只读防线)"
        action={
          <TabGroup
            tabs={[
              { id: 'tasks', label: '运行任务与证据链', badge: `${mockAgentTasks.length}` },
              { id: 'approvals', label: '人工审批门 (Approvals)', badge: `${approvalsList.filter((a) => a.status === '待审批').length}` },
              { id: 'tools', label: '工具权限矩阵 (Permissions)' },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as any)}
          />
        }
      >
        {activeTab === 'tasks' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {/* Task Queue */}
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>任务 ID / 标题</th>
                    <th>发起 Agent</th>
                    <th>类型</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {mockAgentTasks.map((task) => (
                    <tr
                      key={task.id}
                      onClick={() => setSelectedTask(task)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: selectedTask.id === task.id ? 'var(--bg-card-hover)' : undefined
                      }}
                    >
                      <td>
                        <strong>{task.title}</strong>
                        <div className="cell-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{task.id}</div>
                      </td>
                      <td style={{ fontSize: 12 }}>{task.operator}</td>
                      <td>
                        <StatusBadge tone="neutral" dot={false}>{task.type}</StatusBadge>
                      </td>
                      <td>
                        <StatusBadge tone={task.status === '执行中' ? 'accent' : task.status === '已完成' ? 'positive' : 'warning'}>
                          {task.status}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Task Evidence Chain View */}
            <div style={{ backgroundColor: 'var(--bg-card-subtle)', padding: 16, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <strong style={{ fontSize: 14 }}>任务证据链与推演步骤 (Evidence Chain)</strong>
                <span className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{selectedTask.id}</span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                {selectedTask.title}
              </div>

              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                调用工具: {selectedTask.toolPermissionsUsed?.join(', ')}
              </div>

              <div className="code-block">
                {selectedTask.evidenceChain?.join('\n') || '无步骤记录'}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'approvals' && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>审批单 ID</th>
                  <th>事项标题</th>
                  <th>申请 Agent / 用户</th>
                  <th>风险等级</th>
                  <th>申请时间</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {approvalsList.map((appr) => (
                  <tr key={appr.id}>
                    <td className="cell-mono"><strong>{appr.id}</strong></td>
                    <td>
                      <strong>{appr.title}</strong>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{appr.details}</div>
                    </td>
                    <td style={{ fontSize: 12 }}>{appr.requestedBy}</td>
                    <td>
                      <StatusBadge tone={appr.riskLevel === '高' ? 'negative' : 'warning'}>
                        {appr.riskLevel}风险
                      </StatusBadge>
                    </td>
                    <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{appr.createdAt}</td>
                    <td>
                      <StatusBadge tone={appr.status === '已通过' ? 'positive' : appr.status === '已拒绝' ? 'negative' : appr.status === '已过期' ? 'neutral' : 'warning'}>
                        {appr.status}
                      </StatusBadge>
                    </td>
                    <td>
                      {appr.status === '待审批' ? (
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="button button--primary" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => handleApprove(appr.id, 'pass')}>
                            <Check size={12} /> 模拟通过
                          </button>
                          <button className="button button--danger" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => handleApprove(appr.id, 'reject')}>
                            <X size={12} /> 模拟拒绝
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>已归档</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                  <th>调用记录数</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="cell-mono"><strong>read_market_snapshot</strong></td>
                  <td>全部 Agent</td>
                  <td>只读行情 Parquet & Tick</td>
                  <td><StatusBadge tone="positive" dot={false}>否 (自动放行)</StatusBadge></td>
                  <td className="cell-mono">1,482 次</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>compute_backtest_metrics</strong></td>
                  <td>研究 Agent, 总指挥 Agent</td>
                  <td>因子与策略计算 Engine</td>
                  <td><StatusBadge tone="positive" dot={false}>否 (自动放行)</StatusBadge></td>
                  <td className="cell-mono">342 次</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>request_strategy_publish</strong></td>
                  <td>执行 Agent, 研究 Agent</td>
                  <td>策略版本上线发布</td>
                  <td><StatusBadge tone="warning" dot={false}>是 (触发审批门)</StatusBadge></td>
                  <td className="cell-mono">12 次</td>
                </tr>
                <tr>
                  <td className="cell-mono"><strong>toggle_live_execution</strong></td>
                  <td>仅限平台管理员 (无 Agent)</td>
                  <td>切换实盘生产交易模式</td>
                  <td><StatusBadge tone="negative" dot={false}>双人复核审批</StatusBadge></td>
                  <td className="cell-mono">0 次 (保护中)</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
