import type { RiskPreflightView } from './types'

/**
 * Backend wire contracts. These names intentionally stay snake_case because
 * the FastAPI endpoints currently return snake_case JSON. Presentation and
 * demo models remain in types.ts/mockData.ts and must not be treated as API
 * responses without an explicit adapter.
 */

export interface HealthResponse {
  status: string
  timestamp: string
}

export interface SystemStatusResponse {
  app_name: string
  app_version: string
  mode: string
  uptime_seconds: number
  status: string
  timestamp: string
}

export interface SymbolResponse {
  symbol: string
  base_asset: string
  quote_asset: string
  market_type: string
  min_qty: string
  max_qty: string
  tick_size: string
  status: string
}

export interface TickerResponse {
  symbol: string
  last_price: string
  bid_price: string
  ask_price: string
  volume_24h: string
  change_24h: string
  high_24h: string
  low_24h: string
}

export interface PreflightRequest {
  account_id: string
  symbol: string
  side: string
  quantity: string
  price: string
  strategy_id: string
  strategy_version: string
  mode?: string
  idempotency_key?: string | null
}

export interface PreflightResponse {
  decision: 'approved' | 'rejected'
  decision_id: string
  account_id: string
  symbol: string
  side: string
  quantity: string
  reject_reason: string | null
  remaining_risk_budget: string
  rules_checked: Record<string, unknown>[]
  mode: string
  created_at: string
}

export interface OrderIntentRequest {
  client_order_id: string
  account_id: string
  strategy_id: string
  strategy_version: string
  symbol: string
  market_type?: string
  side: string
  order_type?: string
  quantity: string
  limit_price?: string | null
  mode?: string
  risk_decision_id: string
}

export interface OrderResponse {
  client_order_id: string
  account_id: string
  strategy_id: string
  strategy_version: string
  symbol: string
  market_type: string
  side: string
  order_type: string
  quantity: string
  limit_price: string | null
  mode: string
  risk_decision_id: string | null
  status: string
  filled_quantity: string
  average_price: string | null
  reject_reason: string | null
  created_at: string
  updated_at: string
}

export interface PositionResponse {
  position_id: string
  account_id: string
  symbol: string
  market_type: string
  side: string
  quantity: string
  entry_price: string
  current_price: string
  unrealized_pnl: string
  realized_pnl: string
  created_at: string
  updated_at: string
}

export interface StrategyResponse {
  strategy_id: string
  name: string
  version: string
  description: string
  parameters: Record<string, unknown>
  code_ref?: string
  owner?: string
  kind?: string
  status: string
  created_at: string
  updated_at: string
}

export interface AuditEventResponse {
  event_id: string
  event_type: string
  actor: string
  resource_type: string
  resource_id: string
  details: Record<string, unknown>
  ip_address: string | null
  trace_id: string | null
  created_at: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = 'HTTP_ERROR',
    readonly trace_id?: string,
    readonly details?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

function requestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `frontend-${Date.now()}`
}

function idempotencyKey(): string {
  return `preflight-${requestId()}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      'X-Request-ID': requestId(),
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    let code = 'HTTP_ERROR'
    let traceId: string | undefined = undefined

    if (typeof payload === 'object' && payload !== null) {
      const obj = payload as Record<string, any>
      if (obj.trace_id) traceId = String(obj.trace_id)

      if (obj.error && typeof obj.error === 'object') {
        detail = obj.error.message || detail
        if (obj.error.code) code = String(obj.error.code)
        if (obj.error.trace_id) traceId = String(obj.error.trace_id)
      } else if (obj.detail) {
        detail = String(obj.detail)
        if (obj.code) code = String(obj.code)
      }
    }
    throw new ApiError(detail, response.status, code, traceId, payload)
  }

  return payload as T
}

export interface BacktestRequest {
  strategy_id: string
  strategy_version: string
  data_snapshot: string
  fee_model: string
  slippage_model: string
  initial_capital: string
  mode?: string
  idempotency_key?: string | null
}

export interface BacktestResponse {
  backtest_id: string
  strategy_id: string
  strategy_version: string
  parameters: Record<string, unknown>
  code_ref?: string
  data_snapshot: string
  fee_model: string
  slippage_model: string
  run_environment: string
  initial_capital: string
  mode: string
  status: string
  net_profit: string | null
  sharpe_ratio: string | null
  max_drawdown: string | null
  win_rate: string | null
  total_trades: number
  created_at: string
  completed_at: string | null
}

export interface FillRequest {
  client_order_id: string
  fill_quantity: string
  fill_price: string
}

export interface FillResponse {
  client_order_id: string
  fill_id: string
  status: string
  filled_quantity: string
  average_price: string | null
  position_updates: Record<string, unknown> | null
}

export interface AdapterExecuteResponse {
  client_order_id: string
  status: string
  filled_quantity: string
  average_price: string | null
  position_updates: Record<string, unknown> | null
  adapter_result: Record<string, unknown>
}

export interface CancelRequest {
  client_order_id: string
}

export interface CancelResponse {
  client_order_id: string
  status: string
  reject_reason: string | null
}

export interface ReconciliationResponse {
  reconciliation_id: string
  account_id: string
  status: string
  details: string
  summary: Record<string, unknown>
  created_at: string
}

export interface ResolutionRequest {
  decision: 'acknowledged' | 'rejected'
  reason: string
  actor?: string
  mode?: string
  idempotency_key?: string | null
}

export interface ResolutionResponse {
  resolution_id: string
  reconciliation_id: string
  account_id: string
  decision: string
  reason: string
  actor: string
  idempotency_key: string | null
  created_at: string
}

export interface GovernanceApprovalResponse {
  approval_id: string
  resource_type: string
  resource_id: string
  requested_by: string
  title: string
  details: string
  status: string
  decided_by: string | null
  reject_reason: string | null
  created_at: string
  decided_at: string | null
  expires_at: string
}

export interface GovernanceKillSwitchResponse {
  status: string
  triggered_by: string | null
  trigger_reason: string | null
  triggered_at: string | null
  recovered_by: string | null
  recovered_at: string | null
}

export interface KillSwitchRecoverRequest {
  approval_id: string
  recovered_by: string
  reason: string
  mode?: string
}

export interface AdapterHealthResponse {
  name: string
  status: string
  latency_ms: number
  is_rate_limited: boolean
  last_error: string | null
}

export interface PortfolioTargetRequest {
  account_id: string
  strategy_id: string
  strategy_version: string
  symbol: string
  target_quantity: string
  target_weight?: string | null
  mode?: string
  idempotency_key?: string | null
}

export interface PortfolioTargetResponse {
  target_id: string
  account_id: string
  strategy_id: string
  strategy_version: string
  symbol: string
  target_quantity: string
  current_quantity: string
  delta: string
  target_weight: string | null
  mode: string
  idempotency_key: string | null
  created_at: string
  updated_at: string
}

export interface MarkToMarketRequest {
  account_id?: string
  symbol: string
  mark_price: string
  mode?: string
  idempotency_key?: string | null
}

export interface MarkToMarketResponse {
  account_id: string
  symbol: string
  mark_price: string
  positions_updated: number
  updates: Array<{
    position_id: string
    symbol: string
    side: string
    quantity: string
    entry_price: string
    current_price: string
    unrealized_pnl: string
  }>
}

export const api = {
  health: () => request<HealthResponse>('/health'),
  ready: () => request<HealthResponse>('/ready'),
  systemStatus: () => request<SystemStatusResponse>('/api/v1/system/status'),
  symbols: () => request<SymbolResponse[]>('/api/v1/market/symbols'),
  tickers: () => request<TickerResponse[]>('/api/v1/market/tickers'),
  preflight: (body: PreflightRequest) => request<PreflightResponse>('/api/v1/risk/preflight', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
      idempotency_key: body.idempotency_key ?? idempotencyKey(),
    }),
  }),
  createOrderIntent: (body: OrderIntentRequest) => request<OrderResponse>('/api/v1/orders/intents', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      market_type: body.market_type ?? 'spot',
      order_type: body.order_type ?? 'limit',
      mode: body.mode ?? 'paper',
    }),
  }),
  orders: (accountId?: string) => request<OrderResponse[]>(`/api/v1/orders${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  positions: (accountId?: string) => request<PositionResponse[]>(`/api/v1/positions${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  fillOrder: (body: FillRequest) => request<FillResponse>('/api/v1/execution/fills', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  executeOrder: (clientOrderId: string) => request<AdapterExecuteResponse>(`/api/v1/execution/orders/${encodeURIComponent(clientOrderId)}/execute`, {
    method: 'POST',
  }),
  cancelOrder: (clientOrderId: string) => request<CancelResponse>(`/api/v1/execution/orders/${encodeURIComponent(clientOrderId)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ client_order_id: clientOrderId }),
  }),
  rejectOrder: (clientOrderId: string) => request<CancelResponse>(`/api/v1/execution/orders/${encodeURIComponent(clientOrderId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ client_order_id: clientOrderId }),
  }),
  runReconciliation: (accountId = 'paper-main') => request<ReconciliationResponse>(`/api/v1/execution/reconciliation?account_id=${encodeURIComponent(accountId)}`, {
    method: 'POST',
  }),
  reconciliations: (accountId?: string) => request<ReconciliationResponse[]>(`/api/v1/execution/reconciliation${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  resolveReconciliation: (reconciliationId: string, body: ResolutionRequest) => request<ResolutionResponse>(`/api/v1/execution/reconciliation/${encodeURIComponent(reconciliationId)}/resolution`, {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      actor: body.actor ?? 'risk_officer',
      mode: body.mode ?? 'paper',
    }),
  }),
  governanceApprovals: (status?: string) => request<GovernanceApprovalResponse[]>(`/api/v1/governance/approvals${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  governanceKillSwitch: () => request<GovernanceKillSwitchResponse>('/api/v1/governance/kill-switch'),
  recoverKillSwitch: (body: KillSwitchRecoverRequest) => request<GovernanceKillSwitchResponse>('/api/v1/governance/kill-switch/recover', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),
  adapters: () => request<AdapterHealthResponse[]>('/api/v1/adapters'),
  adapter: (name: string) => request<AdapterHealthResponse>(`/api/v1/adapters/${encodeURIComponent(name)}`),
  strategies: () => request<StrategyResponse[]>('/api/v1/strategies'),
  createBacktest: (body: BacktestRequest) => request<BacktestResponse>('/api/v1/research/backtests', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),
  backtests: () => request<BacktestResponse[]>('/api/v1/research/backtests'),
  backtest: (backtestId: string) => request<BacktestResponse>(`/api/v1/research/backtests/${encodeURIComponent(backtestId)}`),
  createPortfolioTarget: (body: PortfolioTargetRequest) => request<PortfolioTargetResponse>('/api/v1/portfolio/targets', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),
  portfolioTargets: (accountId?: string) => request<PortfolioTargetResponse[]>(`/api/v1/portfolio/targets${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  portfolioTarget: (targetId: string) => request<PortfolioTargetResponse>(`/api/v1/portfolio/targets/${encodeURIComponent(targetId)}`),
  markToMarket: (body: MarkToMarketRequest) => request<MarkToMarketResponse>('/api/v1/positions/mark-to-market', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      account_id: body.account_id ?? 'paper-main',
      mode: body.mode ?? 'paper',
    }),
  }),
  auditEvents: (limit = 100, offset = 0) => request<AuditEventResponse[]>(`/api/v1/audit/events?limit=${limit}&offset=${offset}`),
}

/**
 * Maps only fields the backend actually returns. It deliberately does not
 * fabricate audit references, timestamps, exposure, liquidation prices, or
 * rule semantics that are absent from the current response contract.
 */
export function toRiskPreflightView(response: PreflightResponse): RiskPreflightView {
  const rules = response.rules_checked.map((rule, index) => {
    const passed = rule.passed === true
    const name = typeof rule.rule === 'string' ? rule.rule : `rule_${index + 1}`
    const detail = Object.entries(rule)
      .filter(([key]) => key !== 'rule' && key !== 'passed')
      .map(([key, value]) => `${key}=${String(value)}`)
      .join(' ')

    return { name, passed, detail: detail || (passed ? 'passed=true' : 'passed=false') }
  })

  return {
    decision: response.decision === 'approved' ? 'PASSED' : 'REJECTED',
    decisionId: response.decision_id,
    checkedRulesCount: rules.length,
    passedRulesCount: rules.filter((rule) => rule.passed).length,
    remainingRiskBudget: response.remaining_risk_budget,
    rejectionReason: response.reject_reason ?? undefined,
    rules,
  }
}
