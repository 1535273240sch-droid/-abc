import { CheckCircle2, Clock, Filter, Play, Plus, RefreshCw, ShieldCheck, Wallet, XCircle, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendOrder, mapBackendPosition, mapBackendReconciliation } from '../adapters'
import { api, type OrderIntentRequest } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, ResultMark, StatusBadge, TabGroup } from '../components/Primitives'
import type { Order, Position } from '../types'

interface ReconciliationItem {
  id: string
  accountId: string
  status: string
  details: string
  summary: string
  createdAt: string
}

export default function Execution() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [activeTab, setActiveTab] = useState<'orders' | 'positions' | 'reconciliation'>('orders')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [orders, setOrders] = useState<Order[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [reconciliations, setReconciliations] = useState<ReconciliationItem[]>([])

  // Order Intent Modal state
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false)
  const [newOrderSymbol, setNewOrderSymbol] = useState('BTCUSDT')
  const [newOrderSide, setNewOrderSide] = useState<'buy' | 'sell'>('buy')
  const [newOrderQty, setNewOrderQty] = useState('0.01000000')
  const [newOrderPrice, setNewOrderPrice] = useState('64260.00')
  const [newOrderRiskRef, setNewOrderRiskRef] = useState('risk_preflight_001')
  const [submittingOrder, setSubmittingOrder] = useState(false)

  // Fill Modal state
  const [fillOrderTarget, setFillOrderTarget] = useState<Order | null>(null)
  const [fillQty, setFillQty] = useState('0.01000000')
  const [fillPrice, setFillPrice] = useState('64260.00')
  const [isFilling, setIsFilling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Mark-to-Market Modal state
  const [isMtmModalOpen, setIsMtmModalOpen] = useState(false)
  const [mtmSymbol, setMtmSymbol] = useState('BTCUSDT')
  const [mtmPrice, setMtmPrice] = useState('64300.00')
  const [isSubmittingMtm, setIsSubmittingMtm] = useState(false)

  // Reconciliation Resolution Modal state
  const [resolutionTargetId, setResolutionTargetId] = useState<string | null>(null)
  const [resolutionDecision, setResolutionDecision] = useState<'acknowledged' | 'rejected'>('acknowledged')
  const [resolutionReason, setResolutionReason] = useState('人工核对确认允许微小数据迟滞')
  const [isSubmittingResolution, setIsSubmittingResolution] = useState(false)

  const loadData = async (silent = false) => {
    if (!silent) setLoading(true)
    setActionError(null)

    try {
      const [ordersRes, positionsRes, recRes] = await Promise.all([
        api.orders().catch(() => null),
        api.positions().catch(() => null),
        api.reconciliations().catch(() => null)
      ])

      let connected = false

      if (ordersRes && Array.isArray(ordersRes)) {
        setOrders(ordersRes.map((o) => mapBackendOrder(o)))
        connected = true
      }
      if (positionsRes && Array.isArray(positionsRes)) {
        setPositions(positionsRes.map((p) => mapBackendPosition(p)))
        connected = true
      }
      if (recRes && Array.isArray(recRes)) {
        setReconciliations(recRes.map((r) => mapBackendReconciliation(r)))
        connected = true
      }

      setIsLiveApi(connected)
    } catch (err: any) {
      setActionError(err?.message || '获取执行层数据异常')
      setIsLiveApi(false)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // 1.5s silent background polling for orders and positions
  useEffect(() => {
    loadData(false)
    const interval = setInterval(() => {
      loadData(true)
    }, 1500)
    return () => clearInterval(interval)
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="交易与研究" title="交易执行 Execution" description="管理多资产委托订单、实时持仓监控与对账差异核销" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  // Handle Order Intent Creation with Preflight
  const handleCreateOrderIntent = async () => {
    setSubmittingOrder(true)
    setActionError(null)

    try {
      // Step 1: Execute preflight check first
      const preflightResult = await api.preflight({
        account_id: 'paper-main',
        symbol: newOrderSymbol,
        side: newOrderSide,
        quantity: newOrderQty,
        price: newOrderPrice,
        strategy_id: 'trend-btc',
        strategy_version: '1.0.0',
        mode: 'paper'
      })

      if (preflightResult.decision !== 'approved') {
        throw new Error(`风控前置阻断: ${preflightResult.reject_reason || '超出风险阈值'}`)
      }

      const clientOrderId = `ord-${newOrderSymbol.toLowerCase()}-${Date.now().toString().slice(-6)}`
      const payload: OrderIntentRequest = {
        client_order_id: clientOrderId,
        account_id: 'paper-main',
        strategy_id: 'trend-btc',
        strategy_version: '1.0.0',
        symbol: newOrderSymbol,
        market_type: 'spot',
        side: newOrderSide,
        order_type: 'limit',
        quantity: newOrderQty,
        limit_price: newOrderPrice,
        mode: 'paper',
        risk_decision_id: preflightResult.decision_id
      }

      const res = await api.createOrderIntent(payload)
      const mapped = mapBackendOrder(res)
      setOrders((prev) => [mapped, ...prev])
      setIsOrderModalOpen(false)
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '创建订单意图失败')
    } finally {
      setSubmittingOrder(false)
    }
  }

  // Handle Order Fill Simulation
  const handleFillOrder = async () => {
    if (!fillOrderTarget) return
    setIsFilling(true)
    setActionError(null)

    try {
      const res = await api.fillOrder({
        client_order_id: fillOrderTarget.clientOrderId || fillOrderTarget.id,
        fill_price: fillPrice,
        fill_quantity: fillQty,
        mode: 'paper'
      })

      setOrders((prev) =>
        prev.map((o) => {
          if (o.id === fillOrderTarget.id) {
            return {
              ...o,
              status: res.status === 'filled' ? '已成交' : '部分成交',
              filledQuantity: res.filled_quantity,
              avgPrice: res.average_price
            }
          }
          return o
        })
      )
      setFillOrderTarget(null)
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '模拟成交执行失败')
    } finally {
      setIsFilling(false)
    }
  }

  // Handle Order Cancel
  const handleCancelOrder = async (clientOrderId: string) => {
    try {
      await api.cancelOrder(clientOrderId)
      setOrders((prev) =>
        prev.map((o) => {
          if (o.id === clientOrderId || o.clientOrderId === clientOrderId) {
            return { ...o, status: '已撤销' }
          }
          return o
        })
      )
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '撤销订单失败')
    }
  }

  // Handle Mark to Market
  const handleRunMarkToMarket = async () => {
    setIsSubmittingMtm(true)
    setActionError(null)

    try {
      const res = await api.markToMarket({
        account_id: 'paper-main',
        symbol: mtmSymbol,
        mark_price: mtmPrice,
        mode: 'paper'
      })

      if (res.updates && res.updates.length > 0) {
        setPositions((prev) =>
          prev.map((pos) => {
            const match = res.updates.find((u) => u.symbol === pos.symbol)
            if (match) {
              return {
                ...pos,
                markPrice: Number(match.current_price).toLocaleString('en-US', { minimumFractionDigits: 2 }),
                pnl: match.unrealized_pnl.startsWith('-') ? `$${match.unrealized_pnl}` : `+$${match.unrealized_pnl}`,
                pnlTone: match.unrealized_pnl.startsWith('-') ? 'negative' : 'positive'
              }
            }
            return pos
          })
        )
      }
      setIsMtmModalOpen(false)
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '计算 MTM 盯市失败')
    } finally {
      setIsSubmittingMtm(false)
    }
  }

  // Handle Reconciliation Run
  const handleTriggerReconciliation = async () => {
    try {
      const res = await api.runReconciliation('paper-main')
      const mapped = mapBackendReconciliation(res)
      setReconciliations((prev) => [mapped, ...prev])
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '执行对账失败')
    }
  }

  // Handle Resolution
  const handleResolveReconciliation = async () => {
    if (!resolutionTargetId) return
    setIsSubmittingResolution(true)
    setActionError(null)

    try {
      await api.resolveReconciliation(resolutionTargetId, {
        decision: resolutionDecision,
        reason: resolutionReason,
        actor: 'risk_officer',
        mode: 'paper'
      })

      setReconciliations((prev) =>
        prev.map((r) => {
          if (r.id === resolutionTargetId) {
            return { ...r, status: resolutionDecision === 'acknowledged' ? '一致' : '已否决' }
          }
          return r
        })
      )
      setResolutionTargetId(null)
      loadData(true)
    } catch (err: any) {
      setActionError(err?.message || '提交对账差异处置失败')
    } finally {
      setIsSubmittingResolution(false)
    }
  }

  const filteredOrders = orders.filter((o) => {
    if (statusFilter === 'ALL') return true
    if (statusFilter === 'ACTIVE') return o.status === '待执行' || o.status === '部分成交'
    if (statusFilter === 'FILLED') return o.status === '已成交'
    if (statusFilter === 'CANCELLED') return o.status === '已撤销' || o.status === '风控阻断'
    return true
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="交易与研究"
        title="交易执行 Execution"
        description="机构级真实订单与头寸流转中心：支持订单意图提交、风控前置放行、模拟撮合成交、盯市（MTM）与实时对账"
        action={
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="button button--secondary" onClick={() => setIsMtmModalOpen(true)}>
              <RefreshCw size={14} />
              盯市计算 (MTM)
            </button>
            <button className="button button--primary" onClick={() => setIsOrderModalOpen(true)}>
              <Plus size={14} />
              新建订单意图
            </button>
          </div>
        }
      />

      {/* Top Banner */}
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
            ? `✓ 交易执行与持仓状态机已直连 (Active Orders: ${orders.length} | Open Positions: ${positions.length})`
            : (actionError ? `⚠ 执行层状态: ${actionError}` : '正在同步执行层状态...')}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? '100% Real Execution API Live' : 'Connecting'}
        </StatusBadge>
      </div>

      {actionError && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'rgba(255, 77, 79, 0.1)',
          border: '1px solid rgba(255, 77, 79, 0.3)',
          borderRadius: 'var(--radius-md)',
          color: 'var(--color-negative)',
          fontSize: 12,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>{actionError}</span>
          <button className="button button--subtle" style={{ padding: '2px 8px', fontSize: 11 }} onClick={() => setActionError(null)}>关闭</button>
        </div>
      )}

      <Panel
        title="交易与执行台"
        subtitle="订单生命周期状态机、实时持仓敞口与对账审计"
        action={
          <TabGroup
            tabs={[
              { id: 'orders', label: '订单意图 (Orders)', badge: `${orders.length}` },
              { id: 'positions', label: '实时持仓 (Positions)', badge: `${positions.length}` },
              { id: 'reconciliation', label: '对账与差异分析', badge: `${reconciliations.length}` },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as any)}
          />
        }
      >
        {activeTab === 'orders' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                {['ALL', 'ACTIVE', 'FILLED', 'CANCELLED'].map((filter) => (
                  <button
                    key={filter}
                    className={`button ${statusFilter === filter ? 'button--primary' : 'button--subtle'}`}
                    style={{ padding: '4px 10px', fontSize: 11 }}
                    onClick={() => setStatusFilter(filter)}
                  >
                    {filter === 'ALL' ? '全部订单' : filter === 'ACTIVE' ? '未结订单' : filter === 'FILLED' ? '已成交' : '已撤销/阻断'}
                  </button>
                ))}
              </div>
              <button className="button button--secondary" onClick={() => loadData(false)}>
                <RefreshCw size={13} /> 刷新订单
              </button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>订单 ID</th>
                    <th>标的</th>
                    <th>方向</th>
                    <th>类型</th>
                    <th>限价 / 均价</th>
                    <th>委托数量</th>
                    <th>已成交数量</th>
                    <th>风控决策 ID</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.length === 0 ? (
                    <tr><td colSpan={11} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无匹配的订单记录</td></tr>
                  ) : (
                    filteredOrders.map((ord) => (
                      <tr key={ord.id}>
                        <td className="cell-mono"><strong>{ord.id}</strong></td>
                        <td><strong>{ord.symbol}</strong></td>
                        <td>
                          <StatusBadge tone={ord.side === '买入' ? 'positive' : 'negative'}>
                            {ord.side}
                          </StatusBadge>
                        </td>
                        <td>{ord.type}</td>
                        <td className="cell-mono">{ord.price} / {ord.avgPrice}</td>
                        <td className="cell-mono">{ord.quantity}</td>
                        <td className="cell-mono text-positive">{ord.filledQuantity}</td>
                        <td className="cell-mono" style={{ fontSize: 10, color: 'var(--color-accent)' }}>{ord.riskDecisionId}</td>
                        <td>
                          <StatusBadge tone={ord.status === '已成交' ? 'positive' : ord.status === '部分成交' ? 'warning' : ord.status === '风控阻断' ? 'negative' : 'neutral'}>
                            {ord.status}
                          </StatusBadge>
                        </td>
                        <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ord.createdAt}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {ord.status === '待执行' || ord.status === '部分成交' ? (
                              <>
                                <button
                                  className="button button--primary"
                                  style={{ padding: '2px 6px', fontSize: 10 }}
                                  onClick={() => {
                                    setFillOrderTarget(ord)
                                    setFillPrice(ord.price !== '—' ? ord.price : '64260.00')
                                    setFillQty(ord.quantity)
                                  }}
                                >
                                  成交
                                </button>
                                <button
                                  className="button button--danger"
                                  style={{ padding: '2px 6px', fontSize: 10 }}
                                  onClick={() => handleCancelOrder(ord.clientOrderId || ord.id)}
                                >
                                  撤单
                                </button>
                              </>
                            ) : (
                              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>已完结</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'positions' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                当前多/空持仓头寸 (基于 PostgreSQL 16 实时持久化与盯市计价)
              </div>
              <button className="button button--secondary" onClick={() => setIsMtmModalOpen(true)}>
                <RefreshCw size={13} /> 重新盯市 MTM
              </button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>合约/现货</th>
                    <th>方向</th>
                    <th>持仓数量</th>
                    <th>开仓均价</th>
                    <th>当前标记价</th>
                    <th>名义敞口 (Exposure)</th>
                    <th>未实现 PnL</th>
                    <th>保证金率</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>当前账户无活跃持仓</td></tr>
                  ) : (
                    positions.map((pos, idx) => (
                      <tr key={pos.symbol + idx}>
                        <td><strong>{pos.symbol}</strong></td>
                        <td>
                          <StatusBadge tone={pos.side === '多头' ? 'positive' : 'negative'}>
                            {pos.side}
                          </StatusBadge>
                        </td>
                        <td className="cell-mono">{pos.quantity}</td>
                        <td className="cell-mono">${pos.entryPrice}</td>
                        <td className="cell-mono">${pos.markPrice}</td>
                        <td className="cell-mono">{pos.exposure}</td>
                        <td className={`cell-mono text-${pos.pnlTone}`} style={{ fontWeight: 600 }}>{pos.pnl}</td>
                        <td className="cell-mono text-positive">{pos.marginRatio}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'reconciliation' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                本地数据库订单状态与交易所回报差异自动核验 (Reconciliation Engine)
              </div>
              <button className="button button--primary" onClick={handleTriggerReconciliation}>
                <Play size={13} /> 立即执行全量对账
              </button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>对账单号</th>
                    <th>账户</th>
                    <th>状态</th>
                    <th>对账时间</th>
                    <th>明细描述</th>
                    <th>差异摘要</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliations.length === 0 ? (
                    <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0' }}>暂无对账差异记录</td></tr>
                  ) : (
                    reconciliations.map((rec) => (
                      <tr key={rec.id}>
                        <td className="cell-mono"><strong>{rec.id}</strong></td>
                        <td className="cell-mono">{rec.accountId}</td>
                        <td>
                          <StatusBadge tone={rec.status === '一致' ? 'positive' : 'warning'}>
                            {rec.status}
                          </StatusBadge>
                        </td>
                        <td className="cell-mono">{rec.createdAt}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{rec.details}</td>
                        <td className="cell-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{rec.summary}</td>
                        <td>
                          <button
                            className="button button--subtle"
                            style={{ padding: '2px 6px', fontSize: 10 }}
                            onClick={() => {
                              setResolutionTargetId(rec.id)
                              setResolutionDecision('acknowledged')
                              setResolutionReason('人工核对确认允许微小数据迟滞')
                            }}
                          >
                            差异处置
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>

      {/* Create Order Intent Modal */}
      <Modal
        isOpen={isOrderModalOpen}
        onClose={() => setIsOrderModalOpen(false)}
        title="提交订单意图 (POST /api/v1/orders/intents)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsOrderModalOpen(false)}>取消</button>
            <button className="button button--primary" onClick={handleCreateOrderIntent} disabled={submittingOrder}>
              <Zap size={14} />
              {submittingOrder ? '前置风控核验中...' : '提交订单意图'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="form-group">
            <label>交易标的 (Symbol)</label>
            <select className="form-select" value={newOrderSymbol} onChange={(e) => setNewOrderSymbol(e.target.value)}>
              <option value="BTCUSDT">BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
              <option value="SOLUSDT">SOLUSDT</option>
              <option value="BNBUSDT">BNBUSDT</option>
              <option value="DOGEUSDT">DOGEUSDT</option>
            </select>
          </div>
          <div className="form-group">
            <label>方向 (Side)</label>
            <select className="form-select" value={newOrderSide} onChange={(e) => setNewOrderSide(e.target.value as any)}>
              <option value="buy">买入 (BUY)</option>
              <option value="sell">卖出 (SELL)</option>
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label>委托数量 (Quantity)</label>
              <input className="form-input" value={newOrderQty} onChange={(e) => setNewOrderQty(e.target.value)} />
            </div>
            <div className="form-group">
              <label>限价 (Limit Price)</label>
              <input className="form-input" value={newOrderPrice} onChange={(e) => setNewOrderPrice(e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label>风控前置决策引用 (risk_decision_id)</label>
            <input className="form-input" value={newOrderRiskRef} onChange={(e) => setNewOrderRiskRef(e.target.value)} />
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              * 提交时系统将自动调用 `POST /api/v1/risk/preflight` 实时校验名义价值与敞口预算
            </div>
          </div>
        </div>
      </Modal>

      {/* Fill Modal */}
      <Modal
        isOpen={!!fillOrderTarget}
        onClose={() => setFillOrderTarget(null)}
        title="模拟撮生成交 (POST /api/v1/execution/fills)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setFillOrderTarget(null)}>取消</button>
            <button className="button button--primary" onClick={handleFillOrder} disabled={isFilling}>
              <CheckCircle2 size={14} />
              {isFilling ? '正在录入成交...' : '确认成交'}
            </button>
          </>
        }
      >
        {fillOrderTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              目标订单: <code className="cell-mono">{fillOrderTarget.clientOrderId || fillOrderTarget.id}</code> ({fillOrderTarget.symbol} {fillOrderTarget.side})
            </div>
            <div className="form-group">
              <label>成交数量 (fill_quantity)</label>
              <input className="form-input" value={fillQty} onChange={(e) => setFillQty(e.target.value)} />
            </div>
            <div className="form-group">
              <label>成交价格 (fill_price)</label>
              <input className="form-input" value={fillPrice} onChange={(e) => setFillPrice(e.target.value)} />
            </div>
          </div>
        )}
      </Modal>

      {/* Mark-to-Market Modal */}
      <Modal
        isOpen={isMtmModalOpen}
        onClose={() => setIsMtmModalOpen(false)}
        title="按标记价盯市刷新持仓 (POST /api/v1/positions/mark-to-market)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsMtmModalOpen(false)}>取消</button>
            <button className="button button--primary" onClick={handleRunMarkToMarket} disabled={isSubmittingMtm}>
              <RefreshCw size={14} />
              {isSubmittingMtm ? '正在计算 MTM PnL...' : '计算与刷新未实现 PnL'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="form-group">
            <label>持仓标的 (Symbol)</label>
            <select className="form-select" value={mtmSymbol} onChange={(e) => setMtmSymbol(e.target.value)}>
              <option value="BTCUSDT">BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
              <option value="SOLUSDT">SOLUSDT</option>
              <option value="BNBUSDT">BNBUSDT</option>
              <option value="DOGEUSDT">DOGEUSDT</option>
            </select>
          </div>
          <div className="form-group">
            <label>最新标记价格 (mark_price)</label>
            <input className="form-input" value={mtmPrice} onChange={(e) => setMtmPrice(e.target.value)} />
          </div>
        </div>
      </Modal>

      {/* Reconciliation Resolution Modal */}
      <Modal
        isOpen={!!resolutionTargetId}
        onClose={() => setResolutionTargetId(null)}
        title="录入对账差异处置记录 (POST /api/v1/execution/reconciliation/{id}/resolution)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setResolutionTargetId(null)}>取消</button>
            <button className="button button--primary" onClick={handleResolveReconciliation} disabled={isSubmittingResolution}>
              <CheckCircle2 size={14} />
              {isSubmittingResolution ? '正在录入处置...' : '确认提交处置记录'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            目标对账单编号: <code className="cell-mono">{resolutionTargetId}</code>
          </div>
          <div className="form-group">
            <label>处置决策 (Decision)</label>
            <select className="form-select" value={resolutionDecision} onChange={(e) => setResolutionDecision(e.target.value as any)}>
              <option value="acknowledged">已确认无风险 (acknowledged)</option>
              <option value="rejected">否决并调关 (rejected)</option>
            </select>
          </div>
          <div className="form-group">
            <label>处置原因 (Reason)</label>
            <input className="form-input" value={resolutionReason} onChange={(e) => setResolutionReason(e.target.value)} />
          </div>
        </div>
      </Modal>
    </div>
  )
}
