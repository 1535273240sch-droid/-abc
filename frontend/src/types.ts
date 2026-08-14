export type AsyncState = 'loading' | 'success' | 'empty' | 'error'

export type Tone = 'positive' | 'negative' | 'neutral' | 'warning' | 'accent'

export interface MarketTicker {
  symbol: string
  name: string
  lastPrice: string
  change: string
  changeTone: Tone
  volume: string
  spread: string
  source: 'binance' | 'okx' | 'bybit'
  eventTime: string
  quality: '正常' | '延迟' | '异常'
  spark: number[]
  bidPrice: string
  askPrice: string
  marketType: 'spot' | 'perp'
}

export interface OrderBookEntry {
  price: string
  amount: string
  total: string
  depthPercent: number
}

export interface OrderBookData {
  symbol: string
  bids: OrderBookEntry[]
  asks: OrderBookEntry[]
  updatedAt: string
}

export interface TradeEntry {
  id: string
  symbol: string
  price: string
  quantity: string
  side: 'buy' | 'sell'
  time: string
}

export interface FundingRate {
  symbol: string
  rate: string
  predictedRate: string
  nextSettlement: string
  openInterest: string
  openInterestChange: string
}

export interface Strategy {
  id: string
  name: string
  version: string
  kind: '趋势' | '套利' | '现货' | '组合'
  status: '运行中' | '纸面运行' | '草稿' | '已归档'
  owner: string
  updatedAt: string
  sharpe: string
  maxDrawdown: string
  winRate?: string
  totalReturn?: string
  codeRef?: string
  parameters?: Record<string, string | number>
}

export interface BacktestResult {
  id: string
  strategyId: string
  version: string
  timeframe: string
  initialCapital: string
  netProfit: string
  sharpeRatio: string
  maxDrawdown: string
  winRate: string
  totalTrades: number
  feeModel: string
  slippageModel: string
  dataSnapshotId: string
  codeRef?: string
  createdAt: string
  equityCurve: number[]
}

export interface Order {
  id: string
  clientOrderId: string
  accountId: string
  symbol: string
  side: '买入' | '卖出'
  type: '限价' | '市价'
  quantity: string
  price: string
  status: '已成交' | '部分成交' | '待执行' | '已撤销' | '风控阻断'
  mode: 'paper' | 'live'
  strategyVersion: string
  riskDecisionId: string
  createdAt: string
  filledQuantity: string
  avgPrice: string
}

export interface Position {
  symbol: string
  side: '多头' | '空头'
  quantity: string
  entryPrice: string
  markPrice: string
  pnl: string
  pnlTone: Tone
  exposure: string
  liquidationPrice: string
  marginRatio: string
}

export interface ReconciliationLog {
  id: string
  timestamp: string
  account: string
  type: '仓位对账' | '资金对账' | '订单对账'
  status: '一致' | '偏差已修正' | '警报待查'
  detail: string
}

export interface RiskRule {
  id: string
  name: string
  scope: string
  result: '通过' | '观察' | '阻断'
  detail: string
  checkedAt: string
  threshold: string
  currentValue: string
}

/** Display-only shape returned by the explicit adapter in api.ts. */
export interface RiskPreflightView {
  decision: 'PASSED' | 'REJECTED' | 'WARNING'
  decisionId: string
  checkedRulesCount: number
  passedRulesCount: number
  remainingRiskBudget: string
  rejectionReason?: string
  rules: { name: string; passed: boolean; detail: string }[]
}

export interface CircuitBreaker {
  id: string
  name: string
  target: string
  status: '正常' | '已触发熔断' | '维护中'
  triggerCondition: string
  triggeredAt?: string
  action: '暂停下单' | '强制撤单' | '全平仓位'
}

export interface AgentTask {
  id: string
  title: string
  type: '研究分析' | '报告生成' | '策略发布' | '数据巡检' | '风控审查'
  status: '执行中' | '已完成' | '待审批' | '已暂停'
  operator: string
  startedAt: string
  duration: string
  evidenceChain?: string[]
  toolPermissionsUsed?: string[]
}

export interface ApprovalItem {
  id: string
  title: string
  type: '策略上线' | '实盘模式切换' | '风控限额修改' | 'API Key变更'
  requestedBy: string
  createdAt: string
  riskLevel: '高' | '中' | '低'
  status: '待审批' | '已通过' | '已拒绝' | '已过期'
  details: string
}

export interface ExchangeConnection {
  id: string
  exchange: 'Binance' | 'OKX' | 'Bybit'
  name: string
  mode: 'paper' | 'live'
  secretRef: string
  status: '已连接' | '连接中断' | '延迟偏高'
  ping: string
  lastSync: string
}

export interface AuditLog {
  id: string
  eventTime: string
  eventType: string
  operator: string
  module: 'control' | 'risk' | 'execution' | 'agent' | 'market'
  action: string
  result: '成功' | '失败' | '警告'
  ip: string
  traceId: string
  payloadSummary: string
}

export interface SystemService {
  name: string
  status: '正常' | '纸面' | '降级' | '异常'
  latency: string
  region: string
  version: string
}
