import type {
  AdapterHealthResponse,
  AgentTaskResponse,
  AuditEventResponse,
  BacktestResponse,
  CircuitBreakerResponse,
  ExchangeConnectionResponse,
  FundingRateResponse,
  GovernanceApprovalResponse,
  GovernanceKillSwitchResponse,
  OrderBookResponse,
  OrderResponse,
  PortfolioTargetResponse,
  PositionResponse,
  ReconciliationResponse,
  RiskRuleResponse,
  StrategyResponse,
  SymbolResponse,
  SystemStatusResponse,
  TickerResponse,
  TradeResponse,
} from './api'
import type {
  AgentTask,
  ApprovalItem,
  AuditLog,
  BacktestResult,
  CircuitBreaker,
  ExchangeConnection,
  FundingRate,
  MarketTicker,
  Order,
  OrderBookData,
  Position,
  RiskRule,
  Strategy,
  SystemService,
  Trade,
} from './types'

export function mapBackendTicker(resp: TickerResponse, symbolMeta?: SymbolResponse): MarketTicker {
  const changeStr = resp.change_24h || '0.00'
  const isNegative = changeStr.startsWith('-')
  const baseAsset = symbolMeta?.base_asset ?? (resp.symbol.replace(/USDT|USD|BUSD|BTC/g, '') || resp.symbol)
  const quoteAsset = symbolMeta?.quote_asset ?? 'USDT'

  return {
    symbol: resp.symbol,
    name: symbolMeta ? `${symbolMeta.base_asset}/${symbolMeta.quote_asset}` : `${baseAsset}/${quoteAsset}`,
    lastPrice: Number(resp.last_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    bidPrice: Number(resp.bid_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    askPrice: Number(resp.ask_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    change: changeStr.startsWith('+') || isNegative ? `${changeStr}%` : `+${changeStr}%`,
    changeTone: isNegative ? 'negative' : 'positive',
    volume: Number(resp.volume_24h).toLocaleString('en-US', { maximumFractionDigits: 2 }),
    spread: '0.01%',
    source: resp.source || 'binance-public',
    eventTime: resp.event_time ? resp.event_time.substring(11, 19) + ' UTC' : new Date().toISOString().substring(11, 19) + ' UTC',
    quality: '正常',
    spark: [50, 52, 51, 55, 53, 58, 56, 60],
    marketType: (symbolMeta?.market_type as 'spot' | 'perp') || 'spot'
  }
}

export function mapBackendOrderBook(resp: OrderBookResponse): OrderBookData {
  const bids = resp.bids || []
  const asks = resp.asks || []

  // Calculate cumulative max for depth percent
  const allAmounts = [...bids.map(b => Number(b[1]) || 0), ...asks.map(a => Number(a[1]) || 0)]
  const maxAmount = Math.max(...allAmounts, 1)

  let bidTotal = 0
  const mappedBids = bids.map(([price, amount]) => {
    const amtNum = Number(amount) || 0
    bidTotal += amtNum
    return {
      price: Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
      amount: amtNum.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }),
      total: bidTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }),
      depthPercent: Math.min(100, Math.round((amtNum / maxAmount) * 100))
    }
  })

  let askTotal = 0
  const mappedAsks = asks.map(([price, amount]) => {
    const amtNum = Number(amount) || 0
    askTotal += amtNum
    return {
      price: Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
      amount: amtNum.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }),
      total: askTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }),
      depthPercent: Math.min(100, Math.round((amtNum / maxAmount) * 100))
    }
  })

  return {
    symbol: resp.symbol,
    bids: mappedBids,
    asks: mappedAsks,
    updatedAt: resp.updated_at ? resp.updated_at.substring(11, 19) + ' UTC' : '实时'
  }
}

export function mapBackendTrade(resp: TradeResponse): Trade {
  const isBuy = resp.side.toLowerCase() === 'buy' || resp.side === '买入'
  return {
    id: resp.trade_id,
    symbol: resp.symbol,
    time: resp.time ? resp.time.substring(11, 19) : new Date().toISOString().substring(11, 19),
    price: Number(resp.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    quantity: Number(resp.quantity).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    side: isBuy ? 'buy' : 'sell'
  }
}

export function mapBackendFundingRate(resp: FundingRateResponse): FundingRate {
  return {
    symbol: resp.symbol,
    rate: resp.rate,
    predictedRate: resp.predicted_rate,
    nextSettlement: resp.next_settlement,
    openInterest: resp.open_interest,
    openInterestChange: resp.open_interest_change
  }
}

export function mapBackendOrder(resp: OrderResponse): Order {
  let statusStr: Order['status'] = '待执行'
  const rawStatus = resp.status.toLowerCase()
  if (rawStatus === 'filled' || rawStatus === '已成交') statusStr = '已成交'
  else if (rawStatus === 'partially_filled' || rawStatus === '部分成交') statusStr = '部分成交'
  else if (rawStatus === 'cancelled' || rawStatus === '已撤销') statusStr = '已撤销'
  else if (rawStatus === 'rejected' || rawStatus === 'risk_rejected' || rawStatus === '风控阻断') statusStr = '风控阻断'

  return {
    id: resp.client_order_id,
    clientOrderId: resp.client_order_id,
    accountId: resp.account_id || 'paper-main',
    symbol: resp.symbol,
    side: resp.side.toLowerCase() === 'buy' || resp.side === '买入' ? '买入' : '卖出',
    type: resp.order_type.toLowerCase() === 'limit' ? '限价' : '市价',
    quantity: resp.quantity,
    price: resp.limit_price ?? '—',
    status: statusStr,
    mode: (resp.mode as 'paper' | 'live') || 'paper',
    strategyVersion: resp.strategy_version,
    riskDecisionId: resp.risk_decision_id ?? 'risk_preflight',
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) : new Date().toISOString().substring(11, 19),
    filledQuantity: resp.filled_quantity ?? '0.00',
    avgPrice: resp.average_price ?? '—'
  }
}

export function mapBackendPosition(resp: PositionResponse): Position {
  const pnl = resp.unrealized_pnl ?? '0.00'
  const pnlNum = Number(pnl) || 0
  const qty = Number(resp.quantity) || 0
  const mark = Number(resp.current_price) || 0
  const exposureVal = (qty * mark).toFixed(2)

  return {
    symbol: resp.symbol,
    side: resp.side.toLowerCase() === 'long' || resp.side === '多头' || resp.side.toLowerCase() === 'buy' ? '多头' : '空头',
    quantity: resp.quantity,
    entryPrice: Number(resp.entry_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    markPrice: Number(resp.current_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }),
    pnl: pnl.startsWith('-') ? `$${pnl}` : pnlNum > 0 ? `+$${pnl}` : `$${pnl}`,
    pnlTone: pnl.startsWith('-') || pnlNum < 0 ? 'negative' : 'positive',
    exposure: `$${Number(exposureVal).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    liquidationPrice: '—',
    marginRatio: '10.5%'
  }
}

export function mapBackendStrategy(resp: StrategyResponse): Strategy {
  let kindVal: Strategy['kind'] = '趋势'
  if (resp.kind) {
    const k = resp.kind.toLowerCase()
    if (k.includes('套利') || k.includes('arb')) kindVal = '套利'
    else if (k.includes('现货') || k.includes('spot')) kindVal = '现货'
    else if (k.includes('组合') || k.includes('portfolio')) kindVal = '组合'
  }

  return {
    id: resp.strategy_id,
    name: resp.name,
    version: resp.version,
    kind: kindVal,
    status: resp.status === 'active' || resp.status === '运行中' ? '运行中' : '纸面运行',
    owner: resp.owner ?? 'Quant Team',
    updatedAt: resp.updated_at ? resp.updated_at.substring(0, 10) : '近期',
    sharpe: '2.45',
    maxDrawdown: '-4.2%',
    codeRef: resp.code_ref,
    parameters: (resp.parameters as Record<string, string | number>) || {}
  }
}

export function mapBackendBacktest(resp: BacktestResponse): BacktestResult {
  const net = resp.net_profit ? (resp.net_profit.startsWith('$') || resp.net_profit.startsWith('+') || resp.net_profit.startsWith('-') ? resp.net_profit : `+$${resp.net_profit}`) : '—'
  const capital = resp.initial_capital.startsWith('$') ? resp.initial_capital : `$${resp.initial_capital}`
  return {
    id: resp.backtest_id,
    strategyId: resp.strategy_id,
    version: resp.strategy_version,
    timeframe: `Snapshot: ${resp.data_snapshot}`,
    initialCapital: capital,
    netProfit: net,
    sharpeRatio: resp.sharpe_ratio ?? '—',
    maxDrawdown: resp.max_drawdown ?? '—',
    winRate: resp.win_rate ?? '—',
    totalTrades: resp.total_trades ?? 0,
    feeModel: resp.fee_model,
    slippageModel: resp.slippage_model,
    dataSnapshotId: resp.data_snapshot,
    codeRef: resp.code_ref,
    createdAt: resp.created_at ? resp.created_at.substring(0, 19).replace('T', ' ') : '近期',
    equityCurve: [100, 102, 101, 105, 108, 106, 112, 115, 111, 120, 126, 124, 131, 138, 135, 142]
  }
}

export function mapBackendRiskRule(resp: RiskRuleResponse): RiskRule {
  const res = resp.result.toLowerCase()
  const resultVal: '通过' | '观察' | '阻断' = res === 'passed' || res === 'pass' || res === '通过' ? '通过' : res === 'warning' || res === '观察' ? '观察' : '阻断'
  return {
    id: resp.id,
    name: resp.name,
    scope: resp.scope,
    detail: resp.detail,
    result: resultVal,
    checkedAt: resp.checked_at ? resp.checked_at.substring(11, 19) + ' UTC' : '实时',
    threshold: resp.detail,
    currentValue: '实时'
  }
}

export function mapBackendCircuitBreaker(resp: CircuitBreakerResponse): CircuitBreaker {
  return {
    id: resp.id,
    name: resp.name,
    target: resp.target,
    triggerCondition: resp.trigger_condition,
    action: resp.action,
    status: resp.status
  }
}

export function mapBackendAgentTask(resp: AgentTaskResponse): AgentTask {
  let statusVal: AgentTask['status'] = '已完成'
  const rawStatus = resp.status.toLowerCase()
  if (rawStatus === 'running' || rawStatus === 'executing' || rawStatus === '执行中') statusVal = '执行中'
  else if (rawStatus === 'pending' || rawStatus === 'waiting_approval' || rawStatus === '待审批') statusVal = '待审批'

  let typeVal: AgentTask['type'] = '研究分析'
  const rawType = (resp.task_type || '').toLowerCase()
  if (rawType.includes('market') || rawType.includes('scan')) typeVal = '数据巡检'
  else if (rawType.includes('report')) typeVal = '报告生成'
  else if (rawType.includes('risk')) typeVal = '风控审查'
  else if (rawType.includes('publish') || rawType.includes('deploy')) typeVal = '策略发布'

  return {
    id: resp.task_id,
    title: resp.title,
    operator: resp.operator || 'System Agent',
    type: typeVal,
    status: statusVal,
    startedAt: resp.started_at ? resp.started_at.substring(11, 19) : '刚刚',
    duration: resp.duration || '0.1s',
    evidenceChain: resp.evidence_chain || [],
    toolPermissionsUsed: resp.tool_permissions_used || []
  }
}

export function mapBackendAuditLog(resp: AuditEventResponse): AuditLog {
  let actionText = `${resp.event_type} (Resource: ${resp.resource_id})`
  let result: AuditLog['result'] = '成功'
  if (resp.event_type === 'governance.approval_expired.v1') {
    const details = resp.details && typeof resp.details === 'object' ? resp.details : {}
    const payload = details.payload && typeof details.payload === 'object' ? details.payload as Record<string, unknown> : {}
    const version = details.version
    if (version === 1 && payload.status === 'expired') {
      const expiredAt = typeof payload.expired_at === 'string' ? ` · 到期时间: ${payload.expired_at}` : ''
      actionText = `系统自动过期 · 审批单: ${resp.resource_id}${expiredAt}`
    } else {
      actionText = `审批过期审计事件 · 审批单: ${resp.resource_id}`
      result = '警告'
    }
  }

  return {
    id: resp.event_id,
    eventTime: resp.created_at ? resp.created_at.substring(11, 19) + ' UTC' : '近期',
    eventType: resp.event_type,
    operator: resp.actor || 'system',
    module: (resp.resource_type as any) || 'governance',
    action: actionText,
    result,
    ip: resp.ip_address ?? '127.0.0.1',
    traceId: resp.trace_id ?? resp.event_id,
    payloadSummary: JSON.stringify(resp.details || {})
  }
}

export function mapBackendSystemStatus(resp: SystemStatusResponse): SystemService {
  return {
    name: resp.app_name,
    status: resp.status === 'ok' ? '正常' : '降级',
    latency: '8ms',
    region: `Mode: ${resp.mode} · Uptime: ${resp.uptime_seconds}s`,
    version: resp.app_version
  }
}

export function mapBackendReconciliation(resp: ReconciliationResponse) {
  return {
    id: resp.reconciliation_id,
    accountId: resp.account_id,
    status: resp.status === 'clean' || resp.status === '一致' ? '一致' : '包含差异',
    details: resp.details,
    summary: JSON.stringify(resp.summary),
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) + ' UTC' : '近期'
  }
}

export function mapBackendGovernanceApproval(resp: GovernanceApprovalResponse): ApprovalItem {
  let statusStr: ApprovalItem['status'] = '待审批'
  const rawStatus = resp.status.toLowerCase()
  if (rawStatus === 'approved' || rawStatus === '已通过') statusStr = '已通过'
  else if (rawStatus === 'rejected' || rawStatus === '已拒绝') statusStr = '已拒绝'
  else if (rawStatus === 'expired' || rawStatus === '已过期') statusStr = '已过期'

  let typeVal: ApprovalItem['type'] = '风控限额修改'
  const rawType = (resp.resource_type || '').toLowerCase()
  if (rawType.includes('live')) typeVal = '实盘模式切换'
  else if (rawType.includes('strategy')) typeVal = '策略上线'
  else if (rawType.includes('key') || rawType.includes('credential')) typeVal = 'API Key变更'

  return {
    id: resp.approval_id,
    title: resp.title,
    type: typeVal,
    requestedBy: resp.requested_by,
    riskLevel: resp.resource_type.includes('live') || resp.resource_type.includes('kill') ? '高' : '中',
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) + ' UTC' : '近期',
    status: statusStr,
    details: `${resp.details} (Resource: ${resp.resource_type}/${resp.resource_id})`
  }
}

export function mapBackendGovernanceKillSwitch(resp: GovernanceKillSwitchResponse) {
  return {
    status: resp.status === 'active' || resp.status === 'triggered' ? '已触发熔断' : '正常运行',
    isTriggered: resp.status === 'active' || resp.status === 'triggered',
    triggeredBy: resp.triggered_by ?? '—',
    reason: resp.trigger_reason ?? '无记录',
    triggeredAt: resp.triggered_at ? resp.triggered_at.substring(11, 19) + ' UTC' : '—'
  }
}

export function mapBackendExchangeConnection(resp: ExchangeConnectionResponse): ExchangeConnection {
  let statusStr: ExchangeConnection['status'] = '连接中断'
  const rawStatus = (resp.adapter_status || '').toLowerCase()
  if (rawStatus === 'connected' || rawStatus === 'active' || rawStatus === 'ok') statusStr = '已连接'
  else if (rawStatus === 'degraded' || (resp.latency_ms && resp.latency_ms > 200)) statusStr = '延迟偏高'

  let exName: ExchangeConnection['exchange'] = 'Binance'
  const upper = (resp.display_name || resp.adapter_name).toUpperCase()
  if (upper.includes('OKX')) exName = 'OKX'
  else if (upper.includes('COINBASE')) exName = 'Coinbase'
  else if (upper.includes('BYBIT')) exName = 'Bybit'

  return {
    id: resp.connection_id,
    name: resp.display_name || `${exName} Adapter`,
    exchange: exName,
    mode: (resp.environment as 'paper' | 'live') || 'paper',
    status: statusStr,
    ping: resp.latency_ms ? `${resp.latency_ms}ms` : '—',
    lastSync: '实时',
    secretRef: resp.secret_ref || `vault://secret/exchanges/${resp.adapter_name.toLowerCase()}`
  }
}

export function mapBackendAdapterHealth(resp: AdapterHealthResponse): ExchangeConnection {
  let statusStr: ExchangeConnection['status'] = '连接中断'
  const rawStatus = resp.status.toLowerCase()
  if (rawStatus === 'connected' || rawStatus === 'active' || rawStatus === 'ok') statusStr = '已连接'
  else if (rawStatus === 'degraded' || resp.is_rate_limited) statusStr = '延迟偏高'

  let exName: ExchangeConnection['exchange'] = 'Binance'
  const upper = resp.name.toUpperCase()
  if (upper.includes('OKX')) exName = 'OKX'
  else if (upper.includes('BYBIT')) exName = 'Bybit'

  return {
    id: `adapter-${resp.name}`,
    name: `${exName} Adapter`,
    exchange: exName,
    mode: 'paper',
    status: statusStr,
    ping: `${resp.latency_ms}ms`,
    lastSync: '实时',
    secretRef: `vault://secret/exchanges/${resp.name.toLowerCase()}/paper_key`
  }
}

export function mapBackendPortfolioTarget(resp: PortfolioTargetResponse) {
  return {
    id: resp.target_id,
    accountId: resp.account_id,
    strategyId: resp.strategy_id,
    version: resp.strategy_version,
    symbol: resp.symbol,
    targetQuantity: resp.target_quantity,
    currentQuantity: resp.current_quantity,
    delta: resp.delta,
    targetWeight: resp.target_weight ?? '—',
    mode: resp.mode,
    idempotencyKey: resp.idempotency_key ?? '—',
    createdAt: resp.created_at
  }
}
