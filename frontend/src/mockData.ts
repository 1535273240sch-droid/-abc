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
  ReconciliationLog,
  RiskRule,
  Strategy,
  SystemService,
  TradeEntry
} from './types'

export const mockMarketTickers: MarketTicker[] = [
  { symbol: 'BTCUSDT', name: 'Bitcoin', lastPrice: '104,286.40', change: '+2.84%', changeTone: 'positive', volume: '1.28B', spread: '0.01%', source: 'binance', eventTime: '01:26:18 UTC', quality: '正常', spark: [42, 46, 44, 49, 48, 56, 53, 61, 58, 68, 65, 72], bidPrice: '104,286.10', askPrice: '104,286.80', marketType: 'spot' },
  { symbol: 'ETHUSDT', name: 'Ethereum', lastPrice: '3,842.12', change: '+1.17%', changeTone: 'positive', volume: '682.4M', spread: '0.02%', source: 'binance', eventTime: '01:26:17 UTC', quality: '正常', spark: [42, 44, 43, 48, 46, 51, 49, 54, 53, 57, 56, 62], bidPrice: '3,842.00', askPrice: '3,842.30', marketType: 'spot' },
  { symbol: 'SOLUSDT', name: 'Solana', lastPrice: '188.64', change: '-0.46%', changeTone: 'negative', volume: '246.8M', spread: '0.03%', source: 'okx', eventTime: '01:26:16 UTC', quality: '正常', spark: [64, 61, 65, 60, 58, 62, 56, 57, 53, 55, 50, 52], bidPrice: '188.60', askPrice: '188.68', marketType: 'perp' },
  { symbol: 'BNBUSDT', name: 'BNB', lastPrice: '712.85', change: '+0.72%', changeTone: 'positive', volume: '90.1M', spread: '0.02%', source: 'bybit', eventTime: '01:26:14 UTC', quality: '延迟', spark: [43, 42, 45, 48, 47, 49, 50, 48, 53, 52, 55, 57], bidPrice: '712.80', askPrice: '712.90', marketType: 'spot' },
  { symbol: 'XRPUSDT', name: 'XRP', lastPrice: '2.4184', change: '-1.08%', changeTone: 'negative', volume: '314.2M', spread: '0.05%', source: 'binance', eventTime: '01:26:08 UTC', quality: '正常', spark: [68, 65, 63, 64, 60, 62, 58, 61, 55, 53, 55, 49], bidPrice: '2.4180', askPrice: '2.4188', marketType: 'perp' },
]

export const mockOrderBook: OrderBookData = {
  symbol: 'BTCUSDT',
  updatedAt: '01:26:19.420 UTC',
  asks: [
    { price: '104,290.00', amount: '1.428', total: '1.428', depthPercent: 85 },
    { price: '104,288.50', amount: '0.850', total: '2.278', depthPercent: 62 },
    { price: '104,287.80', amount: '0.312', total: '2.590', depthPercent: 35 },
    { price: '104,287.00', amount: '0.145', total: '2.735', depthPercent: 20 },
    { price: '104,286.80', amount: '0.082', total: '2.817', depthPercent: 10 },
  ],
  bids: [
    { price: '104,286.10', amount: '0.105', total: '0.105', depthPercent: 12 },
    { price: '104,285.50', amount: '0.420', total: '0.525', depthPercent: 32 },
    { price: '104,284.00', amount: '1.104', total: '1.629', depthPercent: 55 },
    { price: '104,282.20', amount: '2.350', total: '3.979', depthPercent: 78 },
    { price: '104,280.00', amount: '3.800', total: '7.779', depthPercent: 95 },
  ]
}

export const mockTrades: TradeEntry[] = [
  { id: 'trd_9912', symbol: 'BTCUSDT', price: '104,286.40', quantity: '0.0420', side: 'buy', time: '01:26:18.820' },
  { id: 'trd_9911', symbol: 'BTCUSDT', price: '104,286.10', quantity: '0.1200', side: 'sell', time: '01:26:18.410' },
  { id: 'trd_9910', symbol: 'ETHUSDT', price: '3,842.12', quantity: '1.5000', side: 'buy', time: '01:26:17.900' },
  { id: 'trd_9909', symbol: 'BTCUSDT', price: '104,286.40', quantity: '0.0100', side: 'buy', time: '01:26:17.320' },
  { id: 'trd_9908', symbol: 'SOLUSDT', price: '188.64', quantity: '12.400', side: 'sell', time: '01:26:16.850' },
]

export const mockFundingRates: FundingRate[] = [
  { symbol: 'BTCUSDT-PERP', rate: '+0.0100%', predictedRate: '+0.0125%', nextSettlement: '04:00:00 UTC', openInterest: '$2.84B', openInterestChange: '+4.2%' },
  { symbol: 'ETHUSDT-PERP', rate: '+0.0085%', predictedRate: '+0.0090%', nextSettlement: '04:00:00 UTC', openInterest: '$1.42B', openInterestChange: '+1.8%' },
  { symbol: 'SOLUSDT-PERP', rate: '-0.0042%', predictedRate: '-0.0020%', nextSettlement: '04:00:00 UTC', openInterest: '$480M', openInterestChange: '-2.1%' },
]

export const mockStrategies: Strategy[] = [
  {
    id: 'trend-btc',
    name: 'BTC 趋势跟随策略',
    version: '1.4.2',
    kind: '趋势',
    status: '纸面运行',
    owner: '研究组 A',
    updatedAt: '今天 00:48',
    sharpe: '1.82',
    maxDrawdown: '-8.4%',
    winRate: '58.4%',
    totalReturn: '+42.6%',
    codeRef: 'git:quant-repo/strategies/trend_btc_v142.py',
    parameters: { lookback: 20, breakThreshold: 1.5, stopLossPct: 0.02, trailingTakeProfit: 0.05 }
  },
  {
    id: 'basis-eth',
    name: 'ETH 资金费率跨期套利',
    version: '0.9.7',
    kind: '套利',
    status: '运行中',
    owner: '研究组 B',
    updatedAt: '昨天 18:24',
    sharpe: '2.14',
    maxDrawdown: '-3.1%',
    winRate: '84.2%',
    totalReturn: '+18.9%',
    codeRef: 'git:quant-repo/strategies/arbitrage_eth_v097.py',
    parameters: { minSpread: 0.0008, hedgeDelayMs: 50, rebalanceThreshold: 0.05 }
  },
  {
    id: 'mean-sol',
    name: 'SOL 动量与均值回归',
    version: '2.1.0',
    kind: '现货',
    status: '草稿',
    owner: '林默',
    updatedAt: '08-08 14:10',
    sharpe: '—',
    maxDrawdown: '—',
    winRate: '—',
    totalReturn: '—',
    codeRef: 'git:quant-repo/strategies/sol_mom_v210.py',
    parameters: { rsiPeriod: 14, overbought: 75, oversold: 25 }
  },
  {
    id: 'basket-v2',
    name: '多资产风险平价组合',
    version: '3.0.1',
    kind: '组合',
    status: '已归档',
    owner: '研究组 A',
    updatedAt: '08-06 09:35',
    sharpe: '1.36',
    maxDrawdown: '-11.8%',
    winRate: '52.1%',
    totalReturn: '+14.2%',
    codeRef: 'git:quant-repo/strategies/risk_parity_v301.py',
    parameters: { rebalanceInterval: '1d', targetVol: 0.15 }
  },
]

export const mockBacktestResult: BacktestResult = {
  id: 'bt_20260809_001',
  strategyId: 'trend-btc',
  version: '1.4.2',
  timeframe: '2025-01-01 至 2026-08-01 (1h 级别)',
  initialCapital: '$100,000.00',
  netProfit: '+$42,650.00 (+42.65%)',
  sharpeRatio: '1.82',
  maxDrawdown: '-8.40%',
  winRate: '58.4%',
  totalTrades: 342,
  feeModel: 'Maker 0.02% / Taker 0.04%',
  slippageModel: '保守型 1.5 bps',
  dataSnapshotId: 'snap_parquet_20260801_utc',
  createdAt: '2026-08-08T16:20:00Z',
  equityCurve: [100, 102, 101, 105, 108, 106, 112, 115, 111, 120, 126, 124, 131, 138, 135, 142]
}

export const mockOrders: Order[] = [
  { id: 'ord_01J8F2', clientOrderId: 'intent-trend-btc-0891', accountId: 'paper-main', symbol: 'BTCUSDT', side: '买入', type: '限价', quantity: '0.01200000', price: '104,180.00', status: '部分成交', mode: 'paper', strategyVersion: 'trend-btc@1.4.2', riskDecisionId: 'risk_82af91c2', createdAt: '01:24:12', filledQuantity: '0.00600000', avgPrice: '104,180.00' },
  { id: 'ord_01J8EF', clientOrderId: 'intent-basis-eth-0412', accountId: 'paper-main', symbol: 'ETHUSDT', side: '卖出', type: '市价', quantity: '0.84000000', price: '3,842.12', status: '已成交', mode: 'paper', strategyVersion: 'basis-eth@0.9.7', riskDecisionId: 'risk_7c1d4890', createdAt: '01:21:47', filledQuantity: '0.84000000', avgPrice: '3,842.12' },
  { id: 'ord_01J8EA', clientOrderId: 'intent-mean-sol-0105', accountId: 'paper-main', symbol: 'SOLUSDT', side: '买入', type: '限价', quantity: '12.00000000', price: '187.90', status: '待执行', mode: 'paper', strategyVersion: 'mean-sol@2.1.0', riskDecisionId: 'risk_a91421e0', createdAt: '01:17:06', filledQuantity: '0.00000000', avgPrice: '0.00' },
  { id: 'ord_01J8D3', clientOrderId: 'intent-basket-v2-0044', accountId: 'paper-main', symbol: 'BNBUSDT', side: '卖出', type: '限价', quantity: '1.20000000', price: '714.40', status: '已撤销', mode: 'paper', strategyVersion: 'basket-v2@3.0.1', riskDecisionId: 'risk_351e88f1', createdAt: '00:52:31', filledQuantity: '0.00000000', avgPrice: '0.00' },
  { id: 'ord_01J8C1', clientOrderId: 'intent-trend-btc-0890', accountId: 'paper-main', symbol: 'BTCUSDT', side: '买入', type: '限价', quantity: '0.05000000', price: '106,000.00', status: '风控阻断', mode: 'paper', strategyVersion: 'trend-btc@1.4.2', riskDecisionId: 'risk_rej_991b', createdAt: '00:30:15', filledQuantity: '0.00000000', avgPrice: '0.00' },
]

export const mockPositions: Position[] = [
  { symbol: 'BTCUSDT', side: '多头', quantity: '0.0842 BTC', entryPrice: '101,824.00', markPrice: '104,286.40', pnl: '+$207.14 (+2.42%)', pnlTone: 'positive', exposure: '38.2%', liquidationPrice: '$78,400.00', marginRatio: '14.2%' },
  { symbol: 'ETHUSDT', side: '多头', quantity: '1.84 ETH', entryPrice: '3,766.20', markPrice: '3,842.12', pnl: '+$139.69 (+2.02%)', pnlTone: 'positive', exposure: '24.8%', liquidationPrice: '$2,910.00', marginRatio: '18.5%' },
  { symbol: 'SOLUSDT', side: '空头', quantity: '24.00 SOL', entryPrice: '190.04', markPrice: '188.64', pnl: '+$33.60 (+0.74%)', pnlTone: 'positive', exposure: '7.6%', liquidationPrice: '$245.00', marginRatio: '22.0%' },
]

export const mockReconciliation: ReconciliationLog[] = [
  { id: 'rec_01', timestamp: '01:25:00 UTC', account: 'paper-main', type: '仓位对账', status: '一致', detail: 'Binance / OKX 组合目标仓位与本地状态匹配 100%' },
  { id: 'rec_02', timestamp: '01:00:00 UTC', account: 'paper-main', type: '资金对账', status: '一致', detail: '净权益 $248,920.50 与未实现 PnL 结算一致' },
  { id: 'rec_03', timestamp: '00:00:00 UTC', account: 'paper-main', type: '订单对账', status: '偏差已修正', detail: '自动修正 1 笔滑点挂单的微小尾数误差 (+0.0001 BTC)' },
]

export const mockRiskRules: RiskRule[] = [
  { id: 'rr_1', name: '单策略名义敞口', scope: 'trend-btc@1.4.2', result: '通过', detail: '38.2% / 上限 45.0%', checkedAt: '01:24:11 UTC', threshold: '45.0%', currentValue: '38.2%' },
  { id: 'rr_2', name: '账户杠杆倍数', scope: 'paper-main', result: '通过', detail: '1.42x / 上限 3.00x', checkedAt: '01:24:11 UTC', threshold: '3.00x', currentValue: '1.42x' },
  { id: 'rr_3', name: '数据新鲜度', scope: 'BTCUSDT / binance', result: '观察', detail: '延迟 1.8s / 目标 < 1.0s', checkedAt: '01:24:11 UTC', threshold: '1.0s', currentValue: '1.8s' },
  { id: 'rr_4', name: '组合日内亏损', scope: 'paper-main', result: '通过', detail: '0.34% / 上限 3.00%', checkedAt: '01:24:11 UTC', threshold: '3.00%', currentValue: '0.34%' },
  { id: 'rr_5', name: '单笔订单金额', scope: 'paper-main', result: '通过', detail: '$1,250.00 / 上限 $50,000.00', checkedAt: '01:24:11 UTC', threshold: '$50,000.00', currentValue: '$1,250.00' },
]

export const mockCircuitBreakers: CircuitBreaker[] = [
  { id: 'cb_1', name: '行情极大滑点熔断', target: 'BTCUSDT / ETHUSDT', status: '正常', triggerCondition: '滑动窗口 10 秒内在盘口滑点偏离 > 2.5%', action: '暂停下单' },
  { id: 'cb_2', name: '极端单日亏损 Kill Switch', target: '全账户组合', status: '正常', triggerCondition: '日内组合累计亏损 > 5.00%', action: '全平仓位' },
  { id: 'cb_3', name: '交易所 WebSocket 断连熔断', target: 'Binance Adapter', status: '正常', triggerCondition: '连续 5 秒未收到心跳包', action: '强制撤单' },
]

export const mockAgentTasks: AgentTask[] = [
  {
    id: 'task_2401',
    title: '复核 BTC 趋势策略回测偏差',
    type: '研究分析',
    status: '执行中',
    operator: '总指挥 Agent',
    startedAt: '01:18:24 UTC',
    duration: '08m 12s',
    evidenceChain: [
      '01:18:24 - 从 Parquet 存储拉取 snap_parquet_20260801 行情快照',
      '01:19:02 - 对比现货与合约在 1h 级别的 K 线插值',
      '01:21:40 - 发现 2026-07-14 04:00 UTC 处存在 2 个 Tick 乱序缺失'
    ],
    toolPermissionsUsed: ['read_market_snapshot', 'compute_backtest_metrics']
  },
  {
    id: 'task_2398',
    title: '生成昨日组合归因报告',
    type: '报告生成',
    status: '已完成',
    operator: '研究 Agent',
    startedAt: '00:42:10 UTC',
    duration: '03m 46s',
    evidenceChain: [
      '00:42:10 - 统计以太坊资金费率套利收益 $139.69',
      '00:44:20 - 导出归因 PDF/Markdown 报告至对象存储'
    ],
    toolPermissionsUsed: ['read_portfolio_state', 'generate_report']
  },
  {
    id: 'task_2395',
    title: '请求发布 basis-eth@0.9.7 到实盘环境',
    type: '策略发布',
    status: '待审批',
    operator: '执行 Agent',
    startedAt: '昨天 23:16 UTC',
    duration: '—',
    evidenceChain: [
      '昨天 23:16 - 回测 Sharpe 2.14 达标，提交审核申请',
      '等待安全主管与风控负责人联合批准'
    ],
    toolPermissionsUsed: ['request_strategy_publish']
  },
  {
    id: 'task_2388',
    title: '检查 OKX 行情数据质量延迟异常',
    type: '数据巡检',
    status: '已暂停',
    operator: '数据 Agent',
    startedAt: '昨天 20:02 UTC',
    duration: '12m 09s',
    evidenceChain: [
      '昨天 20:02 - 触发数据延迟告警 (1.8s > 1.0s)',
      '昨天 20:14 - 自动切换至 WebSocket 备用连接通道'
    ],
    toolPermissionsUsed: ['inspect_adapter_health']
  },
]

export const mockApprovals: ApprovalItem[] = [
  { id: 'appr_01', title: '策略上线: basis-eth@0.9.7 申请切换至纸面模拟运行', type: '策略上线', requestedBy: '执行 Agent (DeepSeek)', createdAt: '昨天 23:16 UTC', riskLevel: '中', status: '待审批', details: '该策略已完成 30 天样本外验证，Sharpe 2.14，最大回撤 -3.1%' },
  { id: 'appr_02', title: '修改风控限额: 提升 BTCUSDT 单策略敞口上限至 50%', type: '风控限额修改', requestedBy: '林默 (量化平台主管)', createdAt: '08-07 15:40 UTC', riskLevel: '高', status: '已拒绝', details: '拒因：市场波幅近期偏高，不宜单向扩大比特币集中度' },
]

export const mockExchangeConnections: ExchangeConnection[] = [
  { id: 'conn_1', exchange: 'Binance', name: 'Binance 现货/合约 Adapter', mode: 'paper', secretRef: 'vault://secret/binance/paper-main', status: '已连接', ping: '24ms', lastSync: '01:26:18 UTC' },
  { id: 'conn_2', exchange: 'OKX', name: 'OKX 统一账户 Adapter', mode: 'paper', secretRef: 'vault://secret/okx/paper-main', status: '已连接', ping: '42ms', lastSync: '01:26:17 UTC' },
  { id: 'conn_3', exchange: 'Bybit', name: 'Bybit 衍生品 Adapter', mode: 'paper', secretRef: 'vault://secret/bybit/paper-main', status: '延迟偏高', ping: '128ms', lastSync: '01:26:14 UTC' },
]

export const mockAuditLogs: AuditLog[] = [
  { id: 'aud_9021', eventTime: '01:24:12 UTC', eventType: 'risk.preflight.passed', operator: 'risk_engine', module: 'risk', action: '放行订单意图 intent-trend-btc-0891', result: '成功', ip: '10.0.4.12', traceId: 'tr_82af91c2', payloadSummary: 'symbol=BTCUSDT side=buy qty=0.012 price=104180' },
  { id: 'aud_9020', eventTime: '01:21:47 UTC', eventType: 'order.intent.submitted', operator: 'execution_router', module: 'execution', action: '创建纸面订单 ord_01J8EF', result: '成功', ip: '10.0.4.15', traceId: 'tr_7c1d4890', payloadSummary: 'mode=paper decision_id=risk_7c1d4890' },
  { id: 'aud_9019', eventTime: '00:30:15 UTC', eventType: 'risk.preflight.rejected', operator: 'risk_engine', module: 'risk', action: '阻断订单意图 intent-trend-btc-0890', result: '警告', ip: '10.0.4.12', traceId: 'tr_rej_991b', payloadSummary: '原因：超过单笔订单金额上限 $50,000' },
  { id: 'aud_9018', eventTime: '00:00:00 UTC', eventType: 'system.reconciliation.completed', operator: 'reconciliation_svc', module: 'control', action: '系统定时对账完成', result: '成功', ip: '10.0.1.2', traceId: 'tr_rec_daily', payloadSummary: '检查 3 项对账指标，一致率 100%' },
]

export const mockServices: SystemService[] = [
  { name: 'API Gateway / BFF', status: '正常', latency: '12ms', region: '内网 · ap-southeast-1', version: 'v0.1.0' },
  { name: 'Market Data Standardizer', status: '正常', latency: '42ms', region: 'Binance / OKX / Bybit', version: 'v0.1.0' },
  { name: 'Risk Preflight Engine', status: '正常', latency: '8ms', region: 'PostgreSQL + Redis Rule Engine', version: 'v0.1.0' },
  { name: 'Paper Execution Adapter', status: '纸面', latency: '15ms', region: 'Paper Engine', version: 'v0.1.0' },
  { name: 'Agent Orchestrator', status: '正常', latency: '28ms', region: 'Gemini Agent Host', version: 'v0.1.0' },
]
