
export interface AlphaFactorItem {
  factor_id: string
  expression: string
  symbol: string
  hypothesis?: string
  rank_ic: number
  ic: number
  ic_ir: number
  factor_sharpe: number
  win_rate: number
  source: string
  status: string
  discovered_at: string
}

export interface PortfolioOptimizationAllocation {
  symbol: string
  target_weight: number
  risk_contribution: number
  expected_annual_return: number
  annual_volatility: number
  latest_price: number
}

export interface PortfolioOptimizationResult {
  method: string
  optimized_at: string
  symbols_count: number
  expected_annual_return_pct: number
  expected_annual_volatility_pct: number
  portfolio_sharpe_ratio: number
  allocations: PortfolioOptimizationAllocation[]
}

export interface PortfolioRebalanceOrder {
  symbol: string
  side: 'buy' | 'sell'
  target_weight: number
  current_quantity: number
  target_quantity: number
  diff_quantity: number
  estimated_notional_usd: number
  current_price: number
}

export interface StrategyEvolutionItem {
  evolution_id: string
  strategy_id: string
  base_version: string
  candidate_version: string
  status: string
  weakness_diagnosis: string
  llm_proposal: string
  parameter_changes: Record<string, { old: any; new: any }>
  sandbox_results: {
    base_metrics: Record<string, any>
    evolved_metrics: Record<string, any>
    sharpe_improvement_pct: number
    drawdown_reduction_pct: number
    passed_verification_gate?: boolean
  }
  approval_id?: string
  operator?: string
  created_at: string
  applied_at?: string
}

import type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  CredentialRedactedResponse,
  CredentialSaveRequest,
  CredentialTestResponse,
  ModelProviderResponse,
  ModelProviderUpsertRequest,
  ProviderTestResponse,
  RiskPreflightView,
} from './types'

export type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  CredentialRedactedResponse,
  CredentialSaveRequest,
  CredentialTestResponse,
  ModelProviderResponse,
  ModelProviderUpsertRequest,
  ProviderTestResponse,
}

/**
 * Backend wire contracts matching FastAPI endpoints in snake_case.
 */

export interface HealthResponse {
  status: string
  timestamp?: string
}

export interface SystemStatusStorage {
  enabled: boolean
  backend: string
  format?: string | null
  path?: string | null
  dsn_configured?: boolean
  error?: string | null
}

export interface SystemStatusResponse {
  app_name: string
  app_version: string
  mode: string
  uptime_seconds: number
  status: string
  timestamp: string
  storage?: SystemStatusStorage
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
  source?: string
  event_time?: string | null
  ingest_time?: string | null
  sequence?: number | null
}

export interface OrderBookResponse {
  symbol: string
  source: string
  updated_at: string
  bids: [string, string][]
  asks: [string, string][]
}

export interface TradeResponse {
  trade_id: string
  symbol: string
  price: string
  quantity: string
  side: string
  time: string
}

export interface FundingRateResponse {
  symbol: string
  rate: string
  predicted_rate: string
  next_settlement: string
  open_interest: string
  open_interest_change: string
  source: string
}

export interface MarketQualityResponse {
  status: string
  usable: boolean
  checked_at: string
  symbol_count: number
  ticker_count: number
  issues: Record<string, unknown>[]
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
  price?: string | null
  notional?: string | null
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

export interface StrategyRunResponse {
  run_id: string
  strategy_id: string
  strategy_version: string
  mode: string
  signals_generated: number
  intents_created: number
  orders_executed: number
  errors: string[]
  started_at: string
  completed_at: string
  duration_ms: number
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
  account_id: string
  data_snapshot: string
  fee_model: string
  slippage_model: string
  run_environment?: string
  initial_capital: string
  mode: string
  status: string
  net_profit?: string | null
  sharpe_ratio?: string | null
  max_drawdown?: string | null
  win_rate?: string | null
  total_trades?: number | null
  code_ref?: string
  created_at: string
  completed_at?: string | null
}

export interface RiskRuleResponse {
  id: string
  name: string
  scope: string
  detail: string
  result: string
  checked_at: string
}

export interface CircuitBreakerResponse {
  id: string
  name: string
  target: string
  trigger_condition: string
  action: string
  status: string
}

export interface FillRequest {
  client_order_id: string
  fill_price: string
  fill_quantity: string
  fill_fee?: string
  fee_asset?: string
  mode?: string
}

export interface FillResponse {
  client_order_id: string
  status: string
  filled_quantity: string
  average_price: string
  message: string
}

export interface AdapterExecuteResponse {
  client_order_id: string
  status: string
  exchange_order_id?: string
  mode: string
  message?: string
}

export interface CancelResponse {
  client_order_id: string
  status: string
  message?: string
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
  actor?: string
  decision: 'acknowledged' | 'rejected'
  reason: string
  mode?: string
}

export interface ResolutionResponse {
  reconciliation_id: string
  status: string
  decision: string
  reason: string
  actor: string
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
  decided_by?: string | null
  reject_reason?: string | null
  created_at: string
  decided_at?: string | null
  expires_at: string
}

export interface ApprovalDecideRequest {
  decision: 'approved' | 'rejected'
  decided_by: string
  reject_reason?: string | null
}

export interface GovernanceKillSwitchResponse {
  status: string
  triggered_by: string | null
  trigger_reason: string | null
  triggered_at: string | null
  recovered_by: string | null
  recovered_at: string | null
}

export interface KillSwitchTriggerRequest {
  triggered_by: string
  reason: string
  mode?: string
}

export interface KillSwitchRecoverRequest {
  approval_id: string
  recovered_by: string
  reason: string
  mode?: string
}

export interface AgentTaskResponse {
  task_id: string
  title: string
  task_type: string
  status: string
  operator: string
  started_at: string
  duration: string
  evidence_chain: string[]
  tool_permissions_used: string[]
  created_at: string
  updated_at: string
}

export interface ExchangeConnectionResponse {
  connection_id: string
  adapter_name: string
  display_name: string
  environment: string
  secret_ref: string | null
  enabled: boolean
  adapter_status: string
  credential_status: string
  latency_ms: number | null
  last_error: string | null
  updated_at: string
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

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

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
  const url = `${API_BASE_URL}${path}`
  const response = await fetch(url, {
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
        detail = typeof obj.detail === 'string' ? obj.detail : JSON.stringify(obj.detail)
        if (obj.code) code = String(obj.code)
      }
    }
    throw new ApiError(detail, response.status, code, traceId, payload)
  }

  return payload as T
}

export const api = {

  // ─── Alpha Mining & Factor Discovery ───
  alphaFactors: (symbol?: string, minRankIc?: number) =>
    request<AlphaFactorItem[]>(`/api/v1/research/alpha/factors?${symbol ? `symbol=${encodeURIComponent(symbol)}&` : ''}${minRankIc ? `min_rank_ic=${minRankIc}` : ''}`),

  mineAlphaFactors: (body: { symbol?: string; period?: string; generations?: number; population_size?: number; bars_count?: number }) =>
    request<AlphaFactorItem[]>('/api/v1/research/alpha/mine', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  generateLlmAlphaFactor: (body: { hypothesis: string; symbol?: string }) =>
    request<AlphaFactorItem>('/api/v1/research/alpha/llm-generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // ─── Portfolio Optimization ───
  optimizePortfolio: (body: { symbols: string[]; method?: string; period?: string; lookback_bars?: number }) =>
    request<PortfolioOptimizationResult>('/api/v1/research/portfolio/optimize', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  portfolioRebalancePlan: (body: { allocations: PortfolioOptimizationAllocation[]; total_portfolio_value?: number; account_id?: string }) =>
    request<PortfolioRebalanceOrder[]>('/api/v1/research/portfolio/rebalance-plan', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // ─── Strategy Self-Evolution & Auto-Tuning ───
  strategyEvolutions: (strategyId?: string) =>
    request<StrategyEvolutionItem[]>(`/api/v1/research/strategy/evolutions${strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''}`),

  evolveStrategy: (body: { strategy_id: string; recent_backtest_id?: string; operator?: string }) =>
    request<StrategyEvolutionItem>('/api/v1/research/strategy/evolve', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  applyStrategyEvolution: (body: { evolution_id: string; operator?: string }) =>
    request<StrategyEvolutionItem>('/api/v1/research/strategy/apply-evolution', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  health: () => request<HealthResponse>('/health'),
  ready: () => request<HealthResponse>('/ready'),
  systemStatus: () => request<SystemStatusResponse>('/api/v1/system/status'),

  // Market Data (100% Real Live Feeds)
  symbols: () => request<SymbolResponse[]>('/api/v1/market/symbols'),
  tickers: () => request<TickerResponse[]>('/api/v1/market/tickers'),
  klines: (symbol: string, period: string, limit: number = 500) =>
    request<KlineBar[]>(`/api/v1/market/klines?symbol=${encodeURIComponent(symbol)}&period=${period}&limit=${limit}`),
  performance: (days: number = 90) => request<PerformanceReport>(`/api/v1/analytics/performance?days=${days}`),
  orderbook: (symbol: string) => request<OrderBookResponse>(`/api/v1/market/orderbook/${encodeURIComponent(symbol)}`),
  trades: (symbol: string) => request<TradeResponse[]>(`/api/v1/market/trades/${encodeURIComponent(symbol)}`),
  fundingRates: () => request<FundingRateResponse[]>('/api/v1/market/funding'),
  marketQuality: () => request<MarketQualityResponse>('/api/v1/market/quality'),

  // Orders & Execution
  orders: (accountId?: string) => request<OrderResponse[]>(`/api/v1/orders${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  createOrderIntent: (body: OrderIntentRequest) => request<OrderResponse>('/api/v1/orders/intents', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      market_type: body.market_type ?? 'spot',
      order_type: body.order_type ?? 'limit',
      mode: body.mode ?? 'paper',
    }),
  }),
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

  // Positions & Portfolio
  positions: (accountId?: string) => request<PositionResponse[]>(`/api/v1/positions${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  markToMarket: (body: MarkToMarketRequest) => request<MarkToMarketResponse>('/api/v1/positions/mark-to-market', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      account_id: body.account_id ?? 'paper-main',
      mode: body.mode ?? 'paper',
    }),
  }),
  portfolioTargets: (accountId?: string) => request<PortfolioTargetResponse[]>(`/api/v1/portfolio/targets${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  portfolioTarget: (targetId: string) => request<PortfolioTargetResponse>(`/api/v1/portfolio/targets/${encodeURIComponent(targetId)}`),
  createPortfolioTarget: (body: PortfolioTargetRequest) => request<PortfolioTargetResponse>('/api/v1/portfolio/targets', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),

  // Reconciliation
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

  // Strategies & Research
  strategies: () => request<StrategyResponse[]>('/api/v1/strategies'),
  strategy: (strategyId: string) => request<StrategyResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}`),
  runStrategy: (strategyId: string) => request<StrategyRunResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}/run`, {
    method: 'POST',
  }),
  strategyRuns: () => request<StrategyRunResponse[]>('/api/v1/strategies/runs'),
  createBacktest: (body: BacktestRequest) => request<BacktestResponse>('/api/v1/research/backtests', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),
  backtests: () => request<BacktestResponse[]>('/api/v1/research/backtests'),
  backtest: (backtestId: string) => request<BacktestResponse>(`/api/v1/research/backtests/${encodeURIComponent(backtestId)}`),

  // Risk Management
  preflight: (body: PreflightRequest) => request<PreflightResponse>('/api/v1/risk/preflight', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
      idempotency_key: body.idempotency_key ?? idempotencyKey(),
    }),
  }),
  riskRules: () => request<RiskRuleResponse[]>('/api/v1/risk/rules'),
  circuitBreakers: () => request<CircuitBreakerResponse[]>('/api/v1/risk/circuit-breakers'),

  // Governance & Kill Switch
  governanceApprovals: (status?: string) => request<GovernanceApprovalResponse[]>(`/api/v1/governance/approvals${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  governanceApproval: (approvalId: string) => request<GovernanceApprovalResponse>(`/api/v1/governance/approvals/${encodeURIComponent(approvalId)}`),
  decideApproval: (approvalId: string, body: ApprovalDecideRequest) => request<GovernanceApprovalResponse>(`/api/v1/governance/approvals/${encodeURIComponent(approvalId)}/decide`, {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  governanceKillSwitch: () => request<GovernanceKillSwitchResponse>('/api/v1/governance/kill-switch'),
  triggerKillSwitch: (body: KillSwitchTriggerRequest) => request<GovernanceKillSwitchResponse>('/api/v1/governance/kill-switch/trigger', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  recoverKillSwitch: (body: KillSwitchRecoverRequest) => request<GovernanceKillSwitchResponse>('/api/v1/governance/kill-switch/recover', {
    method: 'POST',
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? 'paper',
    }),
  }),

  // AI & Agent Tasks
  agentTasks: () => request<AgentTaskResponse[]>('/api/v1/agents/tasks'),
  runAgentTask: (taskId: string) => request<AgentTaskResponse>(`/api/v1/agents/tasks/${encodeURIComponent(taskId)}/run`, {
    method: 'POST',
  }),
  chatAI: (body: ChatRequest) => request<ChatResponse>('/api/v1/ai/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  // Control: Exchange Connections & Live Credentials
  exchangeConnections: () => request<ExchangeConnectionResponse[]>('/api/v1/control/exchanges'),
  testExchangeConnection: (connectionId: string) => request<CredentialTestResponse>(`/api/v1/control/exchanges/${encodeURIComponent(connectionId)}/test`, {
    method: 'POST',
  }),
  liveCredentials: () => request<CredentialRedactedResponse[]>('/api/v1/live/credentials'),
  saveLiveCredential: (body: CredentialSaveRequest) => request<CredentialRedactedResponse>('/api/v1/live/credentials', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  testLiveCredential: (connectionId: string) => request<CredentialTestResponse>(`/api/v1/live/credentials/${encodeURIComponent(connectionId)}/test`, {
    method: 'POST',
  }),
  deleteLiveCredential: (connectionId: string) => request<{ deleted: string }>(`/api/v1/live/credentials/${encodeURIComponent(connectionId)}`, {
    method: 'DELETE',
  }),

  // Control: AI Model Gateway
  modelProviders: () => request<ModelProviderResponse[]>('/api/v1/control/model-providers'),
  upsertModelProvider: (providerId: string, body: ModelProviderUpsertRequest) => request<ModelProviderResponse>(`/api/v1/control/model-providers/${encodeURIComponent(providerId)}`, {
    method: 'PUT',
    body: JSON.stringify({
      ...body,
      provider_id: providerId,
    }),
  }),
  testModelProvider: (providerId: string) => request<ProviderTestResponse>(`/api/v1/control/model-providers/${encodeURIComponent(providerId)}/test`, {
    method: 'POST',
  }),

  // Adapters & Audit
  adapters: () => request<AdapterHealthResponse[]>('/api/v1/adapters'),
  adapter: (name: string) => request<AdapterHealthResponse>(`/api/v1/adapters/${encodeURIComponent(name)}`),
  auditEvents: (limit = 100, offset = 0) => request<AuditEventResponse[]>(`/api/v1/audit/events?limit=${limit}&offset=${offset}`),
}

export function toRiskPreflightView(response: PreflightResponse): RiskPreflightView {
  const passedRules = response.rules_checked.filter((rule) => {
    const status = String(rule.status ?? rule.result ?? '').toLowerCase()
    return status === 'passed' || status === 'ok' || status === 'true' || rule.passed === true
  }).length

  return {
    decision: response.decision.toUpperCase() as 'PASSED' | 'REJECTED' | 'WARNING',
    decisionId: response.decision_id,
    passedRulesCount: passedRules,
    checkedRulesCount: response.rules_checked.length,
    remainingRiskBudget: response.remaining_risk_budget,
    rejectionReason: response.reject_reason ?? undefined,
    rules: response.rules_checked.map((r, i) => ({
      name: String(r.name ?? r.rule_id ?? `规则 ${i + 1}`),
      detail: String(r.detail ?? r.reason ?? (r.passed ? '校验通过' : '未通过')),
      passed: Boolean(r.passed ?? (r.status === 'passed' || r.result === 'passed')),
    })),
  }
}


export interface KlineBar {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface PerformanceDailyPoint {
  date: string
  pnl: number
  cumulative: number
  unrealized: number
  fills: number
  buy_notional: number
  sell_notional: number
}

export interface PerformanceSymbolRow {
  symbol: string
  realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
  quantity: number
  entry_price: number
  current_price: number
  fills: number
  notional: number
}

export interface PerformanceSummary {
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  total_fills: number
  open_positions: number
  days_reported: number
  win_rate: number
  profit_factor: number | null
  sharpe: number
  max_drawdown: number
  best_day: number
  worst_day: number
  avg_daily_pnl: number
  volatility_daily: number
  positive_days: number
  negative_days: number
}

export interface PerformanceReport {
  generated_at: string
  summary: PerformanceSummary
  daily_series: PerformanceDailyPoint[]
  symbols: PerformanceSymbolRow[]
}
