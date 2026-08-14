import { AlertTriangle, Check, Play, Power, ShieldAlert, ShieldCheck, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, PreflightBadge, ProgressBar, ResultMark, StatCard, StatusBadge } from '../components/Primitives'
import { mockCircuitBreakers, mockRiskRules } from '../mockData'
import { api, toRiskPreflightView } from '../api'
import type { RiskPreflightView } from '../types'

export default function Risk() {
  const { globalState, setGlobalState } = useAppState()
  const [isKillSwitchModalOpen, setIsKillSwitchModalOpen] = useState(false)
  const [isKillSwitchActive, setIsKillSwitchActive] = useState(false)

  // Simulator Form State
  const [simSymbol, setSimSymbol] = useState('BTCUSDT')
  const [simSide, setSimSide] = useState<'buy' | 'sell'>('buy')
  const [simQty, setSimQty] = useState('0.01200000')
  const [simPrice, setSimPrice] = useState('104180.00')
  const [simAccountId, setSimAccountId] = useState('paper-main')
  const [simStrategyId, setSimStrategyId] = useState('trend-btc')
  const [simStrategyVersion, setSimStrategyVersion] = useState('1.0.0')
  const [simResult, setSimResult] = useState<RiskPreflightView | null>(null)
  const [simError, setSimError] = useState<string | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)
  // Recovery Approval state
  const [approvalId, setApprovalId] = useState('appr_ks_recover_001')
  const [recoveredBy, setRecoveredBy] = useState('risk_officer')
  const [recoverReason, setRecoverReason] = useState('已排查并确认盘口回归正常')
  const [recoverError, setRecoverError] = useState<string | null>(null)
  const [isRecovering, setIsRecovering] = useState(false)
  const [isLiveKsApi, setIsLiveKsApi] = useState(false)
  const [ksDetails, setKsDetails] = useState<string | null>(null)

  const handleRecoverKillSwitch = async () => {
    setIsRecovering(true)
    setRecoverError(null)
    try {
      const res = await api.recoverKillSwitch({
        approval_id: approvalId,
        recovered_by: recoveredBy,
        reason: recoverReason,
        mode: 'paper',
      })
      setIsKillSwitchActive(res.status === 'triggered')
      setIsKillSwitchModalOpen(false)
    } catch (err: any) {
      setRecoverError(`熔断恢复失败: [${err?.code || 'ERROR'}] ${err?.message || '未知错误'}`)
    } finally {
      setIsRecovering(false)
    }
  }

  useEffect(() => {
    api.governanceKillSwitch()
      .then((res) => {
        if (res && res.status) {
          setIsKillSwitchActive(res.status === 'triggered')
          setIsLiveKsApi(true)
          if (res.status === 'triggered') {
            setKsDetails(`触发人: ${res.triggered_by || '系统'} · 原因: ${res.trigger_reason || '未知'}`)
          }
        }
      })
      .catch(() => {
        setIsLiveKsApi(false)
      })
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="交易安全平面" title="风控中心 Risk Control" description="风控前置检查、风险预算控制、熔断机制与 Kill Switch" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  const handleRunSimulator = async () => {
    setIsSimulating(true)
    setSimResult(null)
    setSimError(null)
    try {
      const response = await api.preflight({
        account_id: simAccountId,
        symbol: simSymbol,
        side: simSide,
        quantity: simQty,
        price: simPrice,
        strategy_id: simStrategyId,
        strategy_version: simStrategyVersion,
        mode: 'paper',
      })
      setSimResult(toRiskPreflightView(response))
    } catch (error) {
      setSimError(error instanceof Error ? error.message : '风控前置检查请求失败')
    } finally {
      setIsSimulating(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="交易安全平面"
        title="风控中心 Risk Preflight Control"
        description="不可绕过规则防线：所有真实与纸面订单意图必须通过 risk.preflight 获得决策授权"
        dataSource="mixed"
        action={
          <button
            className={`button ${isKillSwitchActive ? 'button--danger' : 'button--secondary'}`}
            onClick={() => setIsKillSwitchModalOpen(true)}
          >
            <Power size={14} />
            {isKillSwitchActive ? '紧急熔断生效中' : '触发全系统 Kill Switch'}
          </button>
        }
      />

      {/* Risk Budget Progress Cards */}
      <div className="grid-cols-3">
        <Panel title="单策略名义敞口预算" subtitle="trend-btc@1.4.2">
          <ProgressBar value={84.8} tone="accent" label="当前敞口 38.2%" detail="上限 45.0%" />
        </Panel>
        <Panel title="账户杠杆倍数预算" subtitle="paper-main 账户">
          <ProgressBar value={47.3} tone="positive" label="当前杠杆 1.42x" detail="上限 3.00x" />
        </Panel>
        <Panel title="组合日内亏损预算" subtitle="日内最大容忍度">
          <ProgressBar value={11.3} tone="positive" label="当前亏损 0.34%" detail="上限 3.00%" />
        </Panel>
      </div>

      {/* Interactive Risk Preflight Simulator & Rules Evaluation */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Simulator */}
        <Panel
          title="风控前置检查模拟器 (Preflight Simulator)"
          subtitle="POST /api/v1/risk/preflight · 仅执行纸面风控检查，不创建订单"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>账户 (Account ID)</label>
                <input className="form-input" value={simAccountId} onChange={(e) => setSimAccountId(e.target.value)} />
              </div>
              <div className="form-group">
                <label>策略 (Strategy ID)</label>
                <input className="form-input" value={simStrategyId} onChange={(e) => setSimStrategyId(e.target.value)} />
              </div>
              <div className="form-group">
                <label>策略版本 (Version)</label>
                <input className="form-input" value={simStrategyVersion} onChange={(e) => setSimStrategyVersion(e.target.value)} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>交易标的 (Symbol)</label>
                <select className="form-select" value={simSymbol} onChange={(e) => setSimSymbol(e.target.value)}>
                  <option value="BTCUSDT">BTCUSDT</option>
                  <option value="ETHUSDT">ETHUSDT</option>
                  <option value="SOLUSDT">SOLUSDT</option>
                </select>
              </div>
              <div className="form-group">
                <label>方向 (Side)</label>
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
                <label>委托价格 (Price)</label>
                <input className="form-input" value={simPrice} onChange={(e) => setSimPrice(e.target.value)} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button className="button button--primary" onClick={handleRunSimulator} disabled={isSimulating}>
                <Play size={14} />
                {isSimulating ? '正在请求后端风控 Preflight...' : '执行风控前置检查'}
              </button>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>* 当前请求固定为 paper；响应来自后端，不会创建订单</span>
            </div>

            {simError && <div className="text-negative" style={{ fontSize: 12 }}>{simError}</div>}

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
        <Panel title="前置风控规则与评估流 (Demo 模拟列表)" subtitle="Preflight 动态引擎测试 · 规则列表为 Demo 预置数据">
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
                {mockRiskRules.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <strong>{rule.name}</strong>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{rule.checkedAt}</div>
                    </td>
                    <td className="cell-mono" style={{ fontSize: 11 }}>{rule.scope}</td>
                    <td className="cell-mono">{rule.detail}</td>
                    <td><ResultMark result={rule.result} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Circuit Breakers Section */}
      <Panel title="系统级熔断与 Kill Switch 控制器" subtitle="包含盘口滑点异常、Websocket 断连及紧急平仓程序">
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
              {mockCircuitBreakers.map((cb) => (
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
                    <StatusBadge tone={isKillSwitchActive ? 'negative' : 'positive'}>
                      {isKillSwitchActive ? '已触发熔断' : cb.status}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Kill Switch Modal */}
      <Modal
        isOpen={isKillSwitchModalOpen}
        onClose={() => setIsKillSwitchModalOpen(false)}
        title={isKillSwitchActive ? '申请解除紧急熔断 (POST /api/v1/governance/kill-switch/recover)' : '激活全系统 Kill Switch 紧急熔断'}
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsKillSwitchModalOpen(false)}>取消</button>
            {isKillSwitchActive ? (
              <button className="button button--primary" onClick={handleRecoverKillSwitch} disabled={isRecovering}>
                <Check size={14} />
                {isRecovering ? '验证审批并解除中...' : '提交审批单解封 Kill Switch'}
              </button>
            ) : (
              <button
                className="button button--danger"
                onClick={() => {
                  setIsKillSwitchActive(true)
                  setIsKillSwitchModalOpen(false)
                }}
              >
                <Power size={14} />
                立即激活 Kill Switch
              </button>
            )}
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', color: 'var(--color-negative)' }}>
            <AlertTriangle size={24} />
            <strong>{isKillSwitchActive ? '解封安全门校验中' : '警告：本操作将向控制平面发送高优先级紧急指令！'}</strong>
          </div>

          {isKillSwitchActive ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--color-warning)', fontWeight: 600 }}>
                解封防护防线：熔断恢复必须提供且通过 approval_id (Governance 审批引用) 校验！
              </div>
              <div className="form-group">
                <label>审批单引用 (approval_id)</label>
                <input className="form-input" value={approvalId} onChange={(e) => setApprovalId(e.target.value)} placeholder="如 appr_ks_recover_001" />
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
          ) : (
            <>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                激活 Kill Switch 后，系统将立即：
              </p>
              <ul style={{ fontSize: 12, color: 'var(--text-secondary)', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <li>拒绝所有新的订单意图提交 (`POST /api/v1/orders/intents`)</li>
                <li>向纸面与真实 Adapter 发起一键撤销挂单</li>
                <li>在系统审计日志记录带有高优先级的操作轨迹</li>
              </ul>
            </>
          )}
        </div>
      </Modal>
    </div>
  )
}
