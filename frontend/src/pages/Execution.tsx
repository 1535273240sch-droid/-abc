import { CheckCircle2, Clock, Filter, Play, Plus, RefreshCw, ShieldCheck, Wallet, XCircle, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendOrder, mapBackendPosition, mapBackendReconciliation } from '../adapters'
import { api, type OrderIntentRequest } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, ResultMark, StatusBadge, TabGroup } from '../components/Primitives'
import { mockOrders, mockPositions, mockReconciliation } from '../mockData'
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
  const [orders, setOrders] = useState<Order[]>(mockOrders)
  const [positions, setPositions] = useState<Position[]>(mockPositions)
  const [reconciliations, setReconciliations] = useState<ReconciliationItem[]>(
    mockReconciliation.map((r) => ({
      id: r.id,
      accountId: r.account,
      status: r.status,
      details: r.detail,
      summary: JSON.stringify({ diff_count: 0 }),
      createdAt: r.timestamp
    }))
  )

  // Order Intent Modal state
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false)
  const [newOrderSymbol, setNewOrderSymbol] = useState('BTCUSDT')
  const [newOrderSide, setNewOrderSide] = useState<'buy' | 'sell'>('buy')
  const [newOrderQty, setNewOrderQty] = useState('0.01000000')
  const [newOrderPrice, setNewOrderPrice] = useState('99900.00')
  const [newOrderRiskRef, setNewOrderRiskRef] = useState('risk_preflight_001')
  const [submittingOrder, setSubmittingOrder] = useState(false)

  // Fill Modal state
  const [fillOrderTarget, setFillOrderTarget] = useState<Order | null>(null)
  const [fillQty, setFillQty] = useState('0.01000000')
  const [fillPrice, setFillPrice] = useState('99900.00')
  const [isFilling, setIsFilling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Mark-to-Market Modal state
  const [isMtmModalOpen, setIsMtmModalOpen] = useState(false)
  const [mtmSymbol, setMtmSymbol] = useState('BTCUSDT')
  const [mtmPrice, setMtmPrice] = useState('105000.00')
  const [isSubmittingMtm, setIsSubmittingMtm] = useState(false)

  // Reconciliation Resolution Modal state
  const [resolutionTargetId, setResolutionTargetId] = useState<string | null>(null)
  const [resolutionDecision, setResolutionDecision] = useState<'acknowledged' | 'rejected'>('acknowledged')
  const [resolutionReason, setResolutionReason] = useState('人工核对确认允许微小数据迟滞')
  const [isSubmittingResolution, setIsSubmittingResolution] = useState(false)

  const loadExecutionData = async () => {
    setLoading(true)
    try {
      const [ordersRes, positionsRes, recsRes] = await Promise.all([
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
      if (recsRes && Array.isArray(recsRes) && recsRes.length > 0) {
        setReconciliations(recsRes.map((r) => mapBackendReconciliation(r)))
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
    loadExecutionData()
  }, [])

  const handleCreateOrderIntent = async () => {
    setSubmittingOrder(true)
    setActionError(null)
    try {
      const payload: OrderIntentRequest = {
        client_order_id: `intent-${Date.now()}`,
        account_id: 'paper-main',
        strategy_id: 'trend-btc',
        strategy_version: '1.4.2',
        symbol: newOrderSymbol,
        market_type: 'spot',
        side: newOrderSide,
        order_type: 'limit',
        quantity: newOrderQty,
        limit_price: newOrderPrice,
        mode: 'paper',
        risk_decision_id: newOrderRiskRef
      }

      const res = await api.createOrderIntent(payload)
      const mapped = mapBackendOrder(res)
      setOrders((prev) => [mapped, ...prev])
      setIsOrderModalOpen(false)
      setIsLiveApi(true)
    } catch (err: any) {
      setActionError(`创建订单意图失败: ${err?.message || '未知错误'}`)
    } finally {
      setSubmittingOrder(false)
    }
  }

  const handleFillOrder = async () => {
    if (!fillOrderTarget) return
    setIsFilling(true)
    setActionError(null)
    try {
      const res = await api.fillOrder({
        client_order_id: fillOrderTarget.clientOrderId,
        fill_quantity: fillQty,
        fill_price: fillPrice
      })

      // Update local order list & reload positions
      setOrders((prev) =>
        prev.map((o) => {
          if (o.clientOrderId === fillOrderTarget.clientOrderId) {
            return {
              ...o,
              status: res.status === 'filled' ? '已成交' : '部分成交',
              filledQuantity: res.filled_quantity,
              avgPrice: res.average_price ?? fillPrice
            }
          }
          return o
        })
      )
      setFillOrderTarget(null)
      loadExecutionData()
    } catch (err: any) {
      setActionError(`成交录入失败: ${err?.message || '未知错误'}`)
    } finally {
      setIsFilling(false)
    }
  }

  const handleCancelOrder = async (clientOrderId: string) => {
    setActionError(null)
    try {
      const res = await api.cancelOrder(clientOrderId)
      setOrders((prev) =>
        prev.map((o) => (o.clientOrderId === clientOrderId ? { ...o, status: '已撤销' } : o))
      )
    } catch (err: any) {
      setActionError(`撤单请求失败: ${err?.message || '未知错误'}`)
    }
  }

  const handleRejectOrder = async (clientOrderId: string) => {
    setActionError(null)
    try {
      const res = await api.rejectOrder(clientOrderId)
      setOrders((prev) =>
        prev.map((o) => (o.clientOrderId === clientOrderId ? { ...o, status: '风控阻断' } : o))
      )
    } catch (err: any) {
      setActionError(`拒单处理失败: ${err?.message || '未知错误'}`)
    }
  }

  const handleExecuteOrderViaAdapter = async (clientOrderId: string) => {
    setActionError(null)
    try {
      await api.executeOrder(clientOrderId)
      loadExecutionData()
    } catch (err: any) {
      setActionError(`Paper Adapter 撮合执行失败: [${err?.code || 'ERROR'}] ${err?.message || '未知错误'}`)
    }
  }

  const handleRunReconciliation = async () => {
    setActionError(null)
    try {
      const res = await api.runReconciliation('paper-main')
      const mapped = mapBackendReconciliation(res)
      setReconciliations((prev) => [mapped, ...prev])
      setIsLiveApi(true)
    } catch (err: any) {
      setActionError(`对账触发失败: ${err?.message || '未知错误'}`)
    }
  }

  const handleRunMarkToMarket = async () => {
    setIsSubmittingMtm(true)
    setActionError(null)
    try {
      await api.markToMarket({ symbol: mtmSymbol, mark_price: mtmPrice })
      setIsMtmModalOpen(false)
      loadExecutionData()
    } catch (err: any) {
      setActionError(`按标记价盯市 (MTM) 失败: [${err?.code || 'ERROR'}] ${err?.message || '未知错误'}`)
    } finally {
      setIsSubmittingMtm(false)
    }
  }

  const handleResolveReconciliation = async () => {
    if (!resolutionTargetId) return
    setIsSubmittingResolution(true)
    setActionError(null)
    try {
      await api.resolveReconciliation(resolutionTargetId, {
        decision: resolutionDecision,
        reason: resolutionReason,
        actor: 'risk_officer'
      })
      setResolutionTargetId(null)
      loadExecutionData()
    } catch (err: any) {
      setActionError(`对账处置记录失败: [${err?.code || 'ERROR'}] ${err?.message || '未知错误'}`)
    } finally {
      setIsSubmittingResolution(false)
    }
  }

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="交易平面" title="交易执行 Execution" description="订单意图生命周期、持仓管理、成交延迟与自动/手动对账" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="交易平面" title="交易执行 Execution" description="正在读取后端 API 的订单与持仓数据..." />
        <DataState state="loading" title="读取订单与持仓中" description="GET /api/v1/orders, GET /api/v1/positions" />
      </div>
    )
  }

  const filteredOrders = orders.filter((ord) => {
    if (statusFilter === 'ALL') return true
    return ord.status === statusFilter
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="交易平面"
        title="交易执行与持仓对账 (Paper Mode)"
        description="订单生命周期与路由：所有订单必须携带 risk_decision_id，默认 paper 纸面模式运行"
        action={
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="button button--primary" onClick={() => setIsOrderModalOpen(true)}>
              <Plus size={14} />
              创建订单意图
            </button>
            <button className="button button--secondary" onClick={loadExecutionData}>
              <RefreshCw size={14} />
              刷新订单 API
            </button>
          </div>
        }
      />

      {/* Action Error Banner */}
      {actionError && (
        <div style={{ padding: '10px 14px', backgroundColor: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.3)', borderRadius: 'var(--radius-md)', color: 'var(--color-negative)', fontSize: 12 }}>
          {actionError}
        </div>
      )}

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
            ? '✓ 已接入 API GET /api/v1/orders, /positions, POST /execution/fills, /cancel, /reconciliation (Paper Environment)'
            : '⚠ 交易 API 未连接，当前展示 [Demo / Mock 模拟订单数据源]'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'Execution API Live' : 'Demo Execution'}
        </StatusBadge>
      </div>

      {/* Main Content Tabs */}
      <Panel
        title="交易平面仪表盘 (Paper Execution)"
        subtitle="包含纸面执行适配器 (Paper Adapter) 与交易所订单回报"
        action={
          <TabGroup
            tabs={[
              { id: 'orders', label: '订单意图 (Orders)', badge: `${orders.length}` },
              { id: 'positions', label: '实时持仓 (Positions)', badge: `${positions.length}` },
              { id: 'reconciliation', label: '对账日志 (Reconciliation)', badge: `${reconciliations.length}` },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as any)}
          />
        }
      >
        {activeTab === 'orders' && (
          <div>
            {/* Filter Sub-bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Filter size={14} style={{ color: 'var(--text-muted)' }} />
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>状态筛选:</span>
                {['ALL', '部分成交', '已成交', '待执行', '风控阻断', '已撤销'].map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    style={{
                      padding: '3px 8px',
                      fontSize: 11,
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-color)',
                      backgroundColor: statusFilter === st ? 'var(--color-accent-bg)' : 'transparent',
                      color: statusFilter === st ? 'var(--color-accent)' : 'var(--text-secondary)',
                      cursor: 'pointer'
                    }}
                  >
                    {st === 'ALL' ? '全部订单' : st}
                  </button>
                ))}
              </div>

              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                客户端订单 ID 具备幂等校验
              </span>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>客户端 Intent ID</th>
                    <th>标的</th>
                    <th>方向 / 类型</th>
                    <th>委托价 / 委托量</th>
                    <th>已成交 / 均价</th>
                    <th>风控决策 ID</th>
                    <th>运行模式</th>
                    <th>状态</th>
                    <th>时间</th>
                    <th>纸面执行动作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.length === 0 ? (
                    <tr><td colSpan={10} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>无匹配订单数据</td></tr>
                  ) : (
                    filteredOrders.map((ord) => (
                      <tr key={ord.id}>
                        <td className="cell-mono">
                          <strong>{ord.clientOrderId}</strong>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>ID: {ord.id}</div>
                        </td>
                        <td><strong>{ord.symbol}</strong></td>
                        <td>
                          <StatusBadge tone={ord.side === '买入' ? 'positive' : 'negative'}>
                            {ord.side} · {ord.type}
                          </StatusBadge>
                        </td>
                        <td className="cell-mono">{ord.price} / {ord.quantity}</td>
                        <td className="cell-mono">{ord.filledQuantity} / {ord.avgPrice}</td>
                        <td className="cell-mono" style={{ fontSize: 10, color: 'var(--color-accent)' }}>{ord.riskDecisionId}</td>
                        <td>
                          <StatusBadge tone="accent" dot={false}>
                            {ord.mode}
                          </StatusBadge>
                        </td>
                        <td>
                          <StatusBadge tone={ord.status === '已成交' ? 'positive' : ord.status === '部分成交' ? 'warning' : ord.status === '风控阻断' ? 'negative' : 'neutral'}>
                            {ord.status}
                          </StatusBadge>
                        </td>
                        <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ord.createdAt}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4 }}>
                            <button
                              className="button button--primary"
                              style={{ padding: '2px 6px', fontSize: 10 }}
                              onClick={() => handleExecuteOrderViaAdapter(ord.clientOrderId)}
                            >
                              Adapter 撮合
                            </button>
                            <button
                              className="button button--secondary"
                              style={{ padding: '2px 6px', fontSize: 10 }}
                              onClick={() => {
                                setFillOrderTarget(ord)
                                setFillQty(ord.quantity)
                                setFillPrice(ord.price === '—' ? '99900.00' : ord.price)
                              }}
                            >
                              模拟成交
                            </button>
                            <button
                              className="button button--subtle"
                              style={{ padding: '2px 6px', fontSize: 10 }}
                              onClick={() => handleCancelOrder(ord.clientOrderId)}
                            >
                              撤单
                            </button>
                            <button
                              className="button button--danger"
                              style={{ padding: '2px 6px', fontSize: 10 }}
                              onClick={() => handleRejectOrder(ord.clientOrderId)}
                            >
                              拒单
                            </button>
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
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                盯市计算引擎 (Mark-to-Market Engine) 根据最新标记价格 (mark_price) 更新持仓未实现盈亏 (unrealized_pnl)
              </div>
              <button className="button button--secondary" onClick={() => setIsMtmModalOpen(true)}>
                <RefreshCw size={14} />
                按标记价盯市 (POST /api/v1/positions/mark-to-market)
              </button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>标的代码</th>
                    <th>持仓方向</th>
                    <th>持仓数量</th>
                    <th>开仓均价</th>
                    <th>标记价格 (Mark Price)</th>
                    <th>强平预估价</th>
                    <th>保证金率</th>
                    <th>未实现 PnL</th>
                    <th>组合敞口 %</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.length === 0 ? (
                    <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>无当前持仓</td></tr>
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
                        <td className="cell-mono">{pos.entryPrice}</td>
                        <td className="cell-mono">{pos.markPrice}</td>
                        <td className="cell-mono text-warning">{pos.liquidationPrice}</td>
                        <td className="cell-mono">{pos.marginRatio}</td>
                        <td className={`cell-mono text-${pos.pnlTone}`} style={{ fontWeight: 700 }}>{pos.pnl}</td>
                        <td className="cell-mono">{pos.exposure}</td>
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
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                对账服务 (Reconciliation Service) 定时对比 PostgreSQL 订单状态、Redis 缓存与交易所 Adapter 回报：
              </div>
              <button className="button button--primary" onClick={handleRunReconciliation}>
                <Play size={14} />
                触发对账引擎 (POST /api/v1/execution/reconciliation)
              </button>
            </div>

            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>对账编号 (Reconciliation ID)</th>
                    <th>账户</th>
                    <th>结果</th>
                    <th>时间</th>
                    <th>对账明细说明</th>
                    <th>Summary 结构</th>
                    <th>差异处置</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliations.length === 0 ? (
                    <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>无对账记录</td></tr>
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
        title="提交纸面订单意图 (POST /api/v1/orders/intents)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsOrderModalOpen(false)}>取消</button>
            <button className="button button--primary" onClick={handleCreateOrderIntent} disabled={submittingOrder}>
              <Zap size={14} />
              {submittingOrder ? '正在提交意图...' : '提交 Paper 订单意图'}
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
          </div>
        </div>
      </Modal>

      {/* Fill Modal */}
      <Modal
        isOpen={!!fillOrderTarget}
        onClose={() => setFillOrderTarget(null)}
        title="模拟纸面成交 (POST /api/v1/execution/fills)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setFillOrderTarget(null)}>取消</button>
            <button className="button button--primary" onClick={handleFillOrder} disabled={isFilling}>
              <CheckCircle2 size={14} />
              {isFilling ? '正在录入成交...' : '确认模拟成交'}
            </button>
          </>
        }
      >
        {fillOrderTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              目标订单: <code className="cell-mono">{fillOrderTarget.clientOrderId}</code> ({fillOrderTarget.symbol} {fillOrderTarget.side})
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
