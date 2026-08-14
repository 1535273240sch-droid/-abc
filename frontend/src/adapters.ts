import type {
  AuditEventResponse,
  BacktestResponse,
  OrderResponse,
  PortfolioTargetResponse,
  PositionResponse,
  StrategyResponse,
  SymbolResponse,
  SystemStatusResponse,
  TickerResponse
} from './api'
import type {
  AuditLog,
  BacktestResult,
  ExchangeConnection,
  MarketTicker,
  Order,
  Position,
  Strategy,
  SystemService
} from './types'

export function mapBackendTicker(resp: TickerResponse, symbolMeta?: SymbolResponse): MarketTicker {
  const isNegative = resp.change_24h.startsWith('-')
  return {
    symbol: resp.symbol,
    name: symbolMeta ? `${symbolMeta.base_asset}/${symbolMeta.quote_asset}` : resp.symbol,
    lastPrice: resp.last_price,
    bidPrice: resp.bid_price,
    askPrice: resp.ask_price,
    change: resp.change_24h.startsWith('+') || isNegative ? resp.change_24h : `+${resp.change_24h}`,
    changeTone: isNegative ? 'negative' : 'positive',
    volume: resp.volume_24h,
    spread: '0.01%',
    source: 'binance',
    eventTime: new Date().toISOString().substring(11, 19) + ' UTC',
    quality: '正常',
    spark: [50, 52, 51, 55, 53, 58, 56, 60],
    marketType: (symbolMeta?.market_type as 'spot' | 'perp') || 'spot'
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
    accountId: resp.account_id,
    symbol: resp.symbol,
    side: resp.side.toLowerCase() === 'buy' || resp.side === '买入' ? '买入' : '卖出',
    type: resp.order_type.toLowerCase() === 'limit' ? '限价' : '市价',
    quantity: resp.quantity,
    price: resp.limit_price ?? '—',
    status: statusStr,
    mode: 'paper',
    strategyVersion: resp.strategy_version,
    riskDecisionId: resp.risk_decision_id ?? 'risk_preflight',
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) : new Date().toISOString().substring(11, 19),
    filledQuantity: resp.filled_quantity ?? '0.00',
    avgPrice: resp.average_price ?? '—'
  }
}

export function mapBackendPosition(resp: PositionResponse): Position {
  const pnl = resp.unrealized_pnl ?? '0.00'
  return {
    symbol: resp.symbol,
    side: resp.side.toLowerCase() === 'long' || resp.side === '多头' ? '多头' : '空头',
    quantity: resp.quantity,
    entryPrice: resp.entry_price,
    markPrice: resp.current_price,
    pnl: pnl.startsWith('-') ? pnl : `+${pnl}`,
    pnlTone: pnl.startsWith('-') ? 'negative' : 'positive',
    exposure: '—',
    liquidationPrice: '—',
    marginRatio: '—'
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
    sharpe: '—',
    maxDrawdown: '—',
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
    createdAt: resp.created_at,
    equityCurve: [100, 102, 101, 105, 108, 106, 112, 115, 111, 120, 126, 124, 131, 138, 135, 142]
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
      actionText = `审批过期审计事件（版本不支持或字段缺失） · 审批单: ${resp.resource_id}`
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
    latency: '12ms',
    region: `Mode: ${resp.mode} · Uptime: ${resp.uptime_seconds}s`,
    version: resp.app_version
  }
}

export function mapBackendReconciliation(resp: { reconciliation_id: string; account_id: string; status: string; details: string; summary: Record<string, unknown>; created_at: string }) {
  return {
    id: resp.reconciliation_id,
    accountId: resp.account_id,
    status: resp.status === 'clean' || resp.status === '一致' ? '一致' : '包含差异',
    details: resp.details,
    summary: JSON.stringify(resp.summary),
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) + ' UTC' : '近期'
  }
}

export function mapBackendGovernanceApproval(resp: { approval_id: string; resource_type: string; resource_id: string; requested_by: string; title: string; details: string; status: string; created_at: string }): any {
  let statusStr = '待审批'
  const rawStatus = resp.status.toLowerCase()
  if (rawStatus === 'approved' || rawStatus === '已通过') statusStr = '已通过'
  else if (rawStatus === 'rejected' || rawStatus === '已拒绝') statusStr = '已拒绝'
  else if (rawStatus === 'expired' || rawStatus === '已过期') statusStr = '已过期'

  return {
    id: resp.approval_id,
    title: resp.title,
    requestedBy: resp.requested_by,
    riskLevel: resp.resource_type.includes('live') || resp.resource_type.includes('kill') ? '高' : '中',
    createdAt: resp.created_at ? resp.created_at.substring(11, 19) + ' UTC' : '近期',
    status: statusStr,
    details: `${resp.details} (Resource: ${resp.resource_type}/${resp.resource_id})`
  }
}

export function mapBackendGovernanceKillSwitch(resp: { status: string; triggered_by: string | null; trigger_reason: string | null; triggered_at: string | null; recovered_by: string | null; recovered_at: string | null }) {
  return {
    status: resp.status === 'triggered' ? '已触发熔断' : '正常运行',
    isTriggered: resp.status === 'triggered',
    triggeredBy: resp.triggered_by ?? '—',
    reason: resp.trigger_reason ?? '无记录',
    triggeredAt: resp.triggered_at ? resp.triggered_at.substring(11, 19) + ' UTC' : '—'
  }
}

export function mapBackendAdapterHealth(resp: { name: string; status: string; latency_ms: number; is_rate_limited: boolean; last_error?: string | null }): ExchangeConnection {
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
