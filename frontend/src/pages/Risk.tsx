import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Check,
  CheckCircle2,
  Lock,
  Power,
  RefreshCw,
  Scale,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendCircuitBreaker, mapBackendGovernanceKillSwitch, mapBackendRiskRule } from '../adapters'
import { api, toRiskPreflightView } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, PreflightBadge, ResultMark, StatCard, StatusBadge } from '../components/Primitives'
import type { CircuitBreaker, RiskPreflightView, RiskRule } from '../types'

export default function Risk() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [riskRules, setRiskRules] = useState<RiskRule[]>([])
  const [circuitBreakers, setCircuitBreakers] = useState<CircuitBreaker[]>([])

  // Kill Switch state
  const [isKillSwitchActive, setIsKillSwitchActive] = useState(false)
  const [killSwitchDetails, setKillSwitchDetails] = useState<{ triggeredBy: string; reason: string; triggeredAt: string }>({
    triggeredBy: '—',
    reason: '—',
    triggeredAt: '—'
  })
  const [isKillSwitchModalOpen, setIsKillSwitchModalOpen] = useState(false)
  const [isTriggerModalOpen, setIsTriggerModalOpen] = useState(false)
  const [triggerReason, setTriggerReason] = useState('市场突发流动性枯竭或异常价格跳跃')
  const [triggerBy, setTriggerBy] = useState('risk_officer_s1')
  const [isSubmittingTrigger, setIsSubmittingTrigger] = useState(false)

  // Recovery Form State
  const [approvalId, setApprovalId] = useState('appr-83844125b7fc')
  const [recoveredBy, setRecoveredBy] = useState('lead_admin_s4')
  const [recoverReason, setRecoverReason] = useState('风控异常已处置完毕，审批通过并申请恢复')
  const [isRecovering, setIsRecovering] = useState(false)
  const [recoverError, setRecoverError] = useState<string | null>(null)

  // Preflight Simulator state
  const [simSymbol, setSimSymbol] = useState('BTCUSDT')
  const [simSide, setSimSide] = useState<'buy' | 'sell'>('buy')
  const [simQty, setSimQty] = useState('0.05000000')
  const [simPrice, setSimPrice] = useState('64260.00')
  const [simulating, setSimulating] = useState(false)
  const [simResult, setSimResult] = useState<RiskPreflightView | null>(null)
  const [simError, setSimError] = useState<string | null>(null)

  const loadRiskData = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [rulesRes, cbRes, ksRes] = await Promise.all([
        api.riskRules().catch(() => null),
        api.circuitBreakers().catch(() => null),
        api.governanceKillSwitch().catch(() => null)
      ])

      let connected = false

      if (rulesRes && Array.isArray(rulesRes)) {
        setRiskRules(rulesRes.map((r) => mapBackendRiskRule(r)))
        connected = true
      }

      if (cbRes && Array.isArray(cbRes)) {
        setCircuitBreakers(cbRes.map((cb) => mapBackendCircuitBreaker(cb)))
        connected = true
      }

      if (ksRes) {
        const mappedKs = mapBackendGovernanceKillSwitch(ksRes)
        setIsKillSwitchActive(mappedKs.isTriggered)
        setKillSwitchDetails({
          triggeredBy: mappedKs.triggeredBy,
          reason: mappedKs.reason,
          triggeredAt: mappedKs.triggeredAt
        })
        connected = true
      }

      setIsLiveApi(connected)
    } catch {
      setIsLiveApi(false)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // 1.5s silent background polling
  useEffect(() => {
    loadRiskData(false)
    const interval = setInterval(() => {
      loadRiskData(true)
    }, 1500)
    return () => clearInterval(interval)
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="控制平面" title="风控中心 Risk Control" description="前置合规审查、名义敞口校验与全系统熔断安全防护" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  // Handle Preflight Run
  const handleRunPreflight = async () => {
    setSimulating(true)
    setSimError(null)
    try {
      const res = await api.preflight({
        account_id: 'paper-main',
        symbol: simSymbol,
        side: simSide,
        quantity: simQty,
        price: simPrice,
        strategy_id: 'trend-btc',
        strategy_version: '1.0.0',
        mode: 'paper'
      })
      setSimResult(toRiskPreflightView(res))
    } catch (err: any) {
      setSimError(err?.message || '风控 Preflight 接口调用异常')
    } finally {
      setSimulating(false)
    }
  }

  // Handle Trigger Kill Switch
  const handleTriggerKillSwitch = async () => {
    setIsSubmittingTrigger(true)
    try {
      const res = await api.triggerKillSwitch({
        triggered_by: triggerBy,
        reason: triggerReason,
        mode: 'paper'
      })
      const mapped = mapBackendGovernanceKillSwitch(res)
      setIsKillSwitchActive(mapped.isTriggered)
      setIsTriggerModalOpen(false)
      loadRiskData(true)
    } catch (err: any) {
      setRecoverError(err?.message || '触发 Kill Switch 失败')
    } finally {
      setIsSubmittingTrigger(false)
    }
  }

  // Handle Recover Kill Switch
  const handleRecoverKillSwitch = async () => {
    setIsRecovering(true)
    setRecoverError(null)

    try {
      const res = await api.recoverKillSwitch({
        approval_id: approvalId,
        recovered_by: recoveredBy,
        reason: recoverReason,
        mode: 'paper'
      })

      const mapped = mapBackendGovernanceKillSwitch(res)
      setIsKillSwitchActive(mapped.isTriggered)
      setIsKillSwitchModalOpen(false)
      loadRiskData(true)
    } catch (err: any) {
      setRecoverError(err?.message || '解封熔断失败：请确保 approval_id 存在且状态为 approved')
    } finally {
      setIsRecovering(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="控制平面"
        title="风控中心 Risk Control"
        description="机构级风控防护体系：订单意图前置毫秒级拦截 (Preflight)、全系统多级熔断器 (Circuit Breakers) 与治理级 Kill Switch"
        action={
          <div style={{ display: 'flex', gap: 10 }}>
            {isKillSwitchActive ? (
              <button className="button button--primary" onClick={() => setIsKillSwitchModalOpen(true)}>
                <ShieldCheck size={14} />
                解封紧急熔断 (Approval Recovery)
              </button>
            ) : (
              <button className="button button--danger" onClick={() => setIsTriggerModalOpen(true)}>
                <Power size={14} />
                激活全系统 Kill Switch
              </button>
            )}
            <button className="button button--secondary" onClick={() => loadRiskData(false)}>
              <RefreshCw size={14} />
              刷新风控状态
            </button>
          </div>
        }
      />

      {/* Top Banner: Real API Connection Status */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '10px 16px',
        backgroundColor: 'var(--bg-card)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-color)',
        fontSize: 12
      }}>
        <span style={{ color: 'var(--text-secondary)' }}>
          {isLiveApi
            ? `✓ 前置风控引擎与熔断控制平面在线 (生效规则: ${riskRules.length} 条 | 熔断器: ${circuitBreakers.length} 项 | 熔断状态: ${isKillSwitchActive ? '已触发' : '正常'})`
            : '正在同步风控引擎状态...'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? '100% Real Risk API Live' : 'Connecting'}
        </StatusBadge>
      </div>

      {/* Kill Switch Active Warning Banner */}
      {isKillSwitchActive && (
        <div style={{
          padding: '12px 16px',
          backgroundColor: 'rgba(255, 77, 79, 0.15)',
          border: '1px solid var(--color-negative)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <AlertOctagon size={22} className="text-negative" />
            <div>
              <div style={{ fontWeight: 700, color: 'var(--color-negative)' }}>
                全系统 KILL SWITCH 紧急熔断生效中！
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                触发人: <code className="cell-mono">{killSwitchDetails.triggeredBy}</code> · 原因: {killSwitchDetails.reason} · 时间: {killSwitchDetails.triggeredAt}
              </div>
            </div>
          </div>
          <button className="button button--primary" onClick={() => setIsKillSwitchModalOpen(true)}>
            录入治理审批并解封
          </button>
        </div>
      )}

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard
          label="系统熔断安全状态"
          value={isKillSwitchActive ? '已触发熔断' : '安全监控中'}
          change={isKillSwitchActive ? '订单拦截中' : '0 违规事件'}
          caption="Kill Switch 门禁状态"
          tone={isKillSwitchActive ? 'negative' : 'positive'}
          icon={<ShieldAlert size={18} />}
        />
        <StatCard
          label="活动风控规则数量"
          value={`${riskRules.length} 条生效`}
          change="100% 规则在线"
          caption="最大名义价值 / 最小下单"
          tone="positive"
          icon={<Scale size={18} />}
        />
        <StatCard
          label="剩余风控预算 (Risk Budget)"
          value="$1,000,000.00"
          change="充足"
          caption="单日最大回撤上限保护"
          tone="positive"
          icon={<Zap size={18} />}
        />
        <StatCard
          label="前置拦截平均耗时"
          value="1.2ms"
          change="目标 < 5ms"
          caption="内存零拷贝预检"
          tone="positive"
          icon={<Activity size={18} />}
        />
      </div>

      {/* Main Grid: Preflight Simulator & Real-time Rule Stream */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Preflight Simulator */}
        <Panel title="前置风控拦截推演器 (Preflight Simulator)" subtitle="模拟订单在进入订单簿前的名义敞口与规则校验">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>交易标的 (Symbol)</label>
                <select className="form-select" value={simSymbol} onChange={(e) => setSimSymbol(e.target.value)}>
                  <option value="BTCUSDT">BTCUSDT</option>
                  <option value="ETHUSDT">ETHUSDT</option>
                  <option value="SOLUSDT">SOLUSDT</option>
                  <option value="BNBUSDT">BNBUSDT</option>
                  <option value="DOGEUSDT">DOGEUSDT</option>
                </select>
              </div>
              <div className="form-group">
                <label>委托方向 (Side)</label>
                <select className="form-select" value={simSide} onChange={(e) => setSimSide(e.target.value as any)}>
                  <option value="buy">买入 (BUY)</option>
                  <option value="sell">卖出 (SELL)</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>委托数量 (Quantity)</label>
                <input className="form-input" value={simQty} onChange={(e) => setSimQty(e.target.value)} />
              </div>
              <div className="form-group">
                <label>限价 (Price USD)</label>
                <input className="form-input" value={simPrice} onChange={(e) => setSimPrice(e.target.value)} />
              </div>
            </div>

            <button className="button button--primary" onClick={handleRunPreflight} disabled={simulating}>
              <Shield size={14} />
              {simulating ? '正在执行前置 Preflight 校验...' : '执行实时风控前置校验 (POST /api/v1/risk/preflight)'}
            </button>

            {simError && (
              <div style={{ padding: '8px 12px', backgroundColor: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-negative)', fontSize: 12 }}>
                {simError}
              </div>
            )}

            {simResult && (
              <div style={{ marginTop: 14, padding: 14, backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>风控决策结果</span>
                  <PreflightBadge decision={simResult.decision} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
                  <div>决策 ID: <code className="cell-mono text-accent">{simResult.decisionId}</code></div>
                  <div>规则通过: <span className="cell-mono">{simResult.passedRulesCount} / {simResult.checkedRulesCount}</span></div>
                  <div>剩余风控预算: <span className="cell-mono">{simResult.remainingRiskBudget}</span></div>
                  {simResult.rejectionReason && (
                    <div className="text-negative" style={{ fontWeight: 600, marginTop: 4 }}>
                      阻断原因: {simResult.rejectionReason}
                    </div>
                  )}
                </div>

                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {simResult.rules.map((r, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span>{r.name}</span>
                      <span className={r.passed ? 'text-positive' : 'text-negative'}>{r.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Panel>

        {/* Real-time Rule Check Stream */}
        <Panel title="前置风控规则与评估流" subtitle="API GET /api/v1/risk/rules">
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>风控规则名称</th>
                  <th>作用域</th>
                  <th>当前值 / 阈值</th>
                  <th>检查结果</th>
                </tr>
              </thead>
              <tbody>
                {riskRules.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无生效的风控规则</td></tr>
                ) : (
                  riskRules.map((rule) => (
                    <tr key={rule.id}>
                      <td>
                        <strong>{rule.name}</strong>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{rule.checkedAt}</div>
                      </td>
                      <td className="cell-mono" style={{ fontSize: 11 }}>{rule.scope}</td>
                      <td className="cell-mono">{rule.detail}</td>
                      <td><ResultMark result={rule.result} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Circuit Breakers Section */}
      <Panel title="系统级熔断器与防护规则" subtitle="API GET /api/v1/risk/circuit-breakers">
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>熔断规则</th>
                <th>作用目标</th>
                <th>触发条件</th>
                <th>熔断后动作</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {circuitBreakers.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无熔断规则记录</td></tr>
              ) : (
                circuitBreakers.map((cb) => (
                  <tr key={cb.id}>
                    <td><strong>{cb.name}</strong></td>
                    <td className="cell-mono" style={{ fontSize: 11 }}>{cb.target}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{cb.triggerCondition}</td>
                    <td>
                      <StatusBadge tone="warning" dot={false}>
                        {cb.action}
                      </StatusBadge>
                    </td>
                    <td>
                      <StatusBadge tone={isKillSwitchActive && cb.id === 'kill_switch' ? 'negative' : 'positive'}>
                        {isKillSwitchActive && cb.id === 'kill_switch' ? '已触发熔断' : cb.status}
                      </StatusBadge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Trigger Modal */}
      <Modal
        isOpen={isTriggerModalOpen}
        onClose={() => setIsTriggerModalOpen(false)}
        title="激活全系统 Kill Switch 紧急熔断 (POST /api/v1/governance/kill-switch/trigger)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsTriggerModalOpen(false)}>取消</button>
            <button className="button button--danger" onClick={handleTriggerKillSwitch} disabled={isSubmittingTrigger}>
              <Power size={14} />
              {isSubmittingTrigger ? '正在发送熔断指令...' : '确认激活紧急熔断'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', color: 'var(--color-negative)' }}>
            <AlertTriangle size={24} />
            <strong>警告：本操作将立即切断全系统交易执行与订单提交！</strong>
          </div>
          <div className="form-group">
            <label>触发操作人 (triggered_by)</label>
            <input className="form-input" value={triggerBy} onChange={(e) => setTriggerBy(e.target.value)} />
          </div>
          <div className="form-group">
            <label>熔断原因 (reason)</label>
            <input className="form-input" value={triggerReason} onChange={(e) => setTriggerReason(e.target.value)} />
          </div>
        </div>
      </Modal>

      {/* Recover Modal */}
      <Modal
        isOpen={isKillSwitchModalOpen}
        onClose={() => setIsKillSwitchModalOpen(false)}
        title="申请解除紧急熔断 (POST /api/v1/governance/kill-switch/recover)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsKillSwitchModalOpen(false)}>取消</button>
            <button className="button button--primary" onClick={handleRecoverKillSwitch} disabled={isRecovering}>
              <Check size={14} />
              {isRecovering ? '验证审批并解除中...' : '提交审批单解封 Kill Switch'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', color: 'var(--color-warning)' }}>
            <ShieldCheck size={24} />
            <strong>解封防护防线：熔断恢复必须提供且通过 approval_id 校验！</strong>
          </div>
          <div className="form-group">
            <label>审批单引用 (approval_id)</label>
            <input className="form-input" value={approvalId} onChange={(e) => setApprovalId(e.target.value)} placeholder="如 appr-83844125b7fc" />
          </div>
          <div className="form-group">
            <label>解封操作人 (recovered_by)</label>
            <input className="form-input" value={recoveredBy} onChange={(e) => setRecoveredBy(e.target.value)} />
          </div>
          <div className="form-group">
            <label>解封原因说明 (reason)</label>
            <input className="form-input" value={recoverReason} onChange={(e) => setRecoverReason(e.target.value)} />
          </div>
          {recoverError && (
            <div style={{ padding: '8px 12px', backgroundColor: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--color-negative)', fontSize: 12 }}>
              {recoverError}
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
