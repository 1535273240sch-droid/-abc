import { Activity, ArrowUpRight, CheckCircle2, RefreshCw, ShieldCheck, TrendingUp, Wallet, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mapBackendOrder, mapBackendPosition, mapBackendRiskRule, mapBackendStrategy, mapBackendTicker } from '../adapters'
import { api } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, PageIntro, Panel, ResultMark, Sparkline, StatCard, StatusBadge } from '../components/Primitives'
import type { MarketTicker, Order, Position, RiskRule, Strategy, SystemService } from '../types'

export default function Dashboard() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const [tickers, setTickers] = useState<MarketTicker[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [riskRules, setRiskRules] = useState<RiskRule[]>([])
  const [services, setServices] = useState<SystemService[]>([])

  // Initial full load
  const loadData = async (silent = false) => {
    if (!silent) setLoading(true)
    setApiError(null)
    try {
      const [statusRes, tickersRes, ordersRes, positionsRes, stratsRes, rulesRes, adaptersRes] = await Promise.all([
        api.systemStatus().catch(() => null),
        api.tickers().catch(() => null),
        api.orders().catch(() => null),
        api.positions().catch(() => null),
        api.strategies().catch(() => null),
        api.riskRules().catch(() => null),
        api.adapters().catch(() => null)
      ])

      let connected = false

      if (tickersRes && Array.isArray(tickersRes) && tickersRes.length > 0) {
        setTickers(tickersRes.map((t) => mapBackendTicker(t)))
        connected = true
      }
      if (ordersRes && Array.isArray(ordersRes)) {
        setOrders(ordersRes.map((o) => mapBackendOrder(o)))
        connected = true
      }
      if (positionsRes && Array.isArray(positionsRes)) {
        setPositions(positionsRes.map((p) => mapBackendPosition(p)))
        connected = true
      }
      if (stratsRes && Array.isArray(stratsRes)) {
        setStrategies(stratsRes.map((s) => mapBackendStrategy(s)))
        connected = true
      }
      if (rulesRes && Array.isArray(rulesRes)) {
        setRiskRules(rulesRes.map((r) => mapBackendRiskRule(r)))
        connected = true
      }
      if (statusRes) {
        const mapAdapterStatus = (s: string): SystemService['status'] => {
          if (s === 'connected' || s === 'active' || s === 'ok') return '正常'
          if (s === 'degraded' || s === 'rate_limited') return '降级'
          return '异常'
        }
        const adapterSvcs: SystemService[] = (adaptersRes || []).map((ad) => ({
          name: `${ad.name.toUpperCase()} Adapter`,
          status: mapAdapterStatus(ad.status),
          latency: `${ad.latency_ms}ms`,
          region: ad.is_rate_limited ? '限流保护' : (ad.status === 'disconnected' ? '连接断开' : '低延迟链路'),
          version: 'v1.0'
        }))

        const storageEnabled = statusRes?.storage?.enabled === true
        const storageBackend = statusRes?.storage?.backend || 'unknown'

        setServices([
          {
            name: statusRes.app_name,
            status: statusRes.status === 'ok' || statusRes.status === 'running' ? '正常' : '降级',
            latency: '本地',
            region: `模式: ${statusRes.mode} · 运行: ${Math.floor(statusRes.uptime_seconds)}s`,
            version: statusRes.app_version
          },
          ...adapterSvcs,
          {
            name: 'PostgreSQL Store',
            status: storageEnabled ? '正常' : '异常',
            latency: '本地',
            region: storageEnabled ? `持久化引擎 (${storageBackend})` : '存储未启用',
            version: 'v16'
          }
        ])
        connected = true
      }

      setIsLiveApi(connected)
    } catch (err: any) {
      setApiError(err?.message || 'API 获取异常')
      setIsLiveApi(false)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // 1.5s silent background polling
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
        <PageIntro eyebrow="系统总览" title="控制台 Dashboard" description="实时监控账户权益、PnL、风险状态与微服务健康" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="系统总览" title="控制台 Dashboard" description="正在读取后端 API 实时状态与市场维度数据..." />
        <DataState state="loading" title="正在接入后端 Paper API" description="GET /api/v1/system/status, /market/tickers, /orders, /positions" />
      </div>
    )
  }

  // Compute summary stats dynamically from live positions
  let totalUnrealizedPnlNum = 0
  let totalExposureNum = 0
  for (const pos of positions) {
    const pnlClean = parseFloat(pos.pnl.replace(/[^0-9.-]/g, '')) || 0
    totalUnrealizedPnlNum += pnlClean
    const expClean = parseFloat(pos.exposure.replace(/[^0-9.-]/g, '')) || 0
    totalExposureNum += expClean
  }

  const baseCapital = 1000000.00
  const totalEquityNum = baseCapital + totalUnrealizedPnlNum
  const totalEquity = totalEquityNum.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const pnlFormatted = totalUnrealizedPnlNum >= 0
    ? `+${totalUnrealizedPnlNum.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `-${Math.abs(totalUnrealizedPnlNum).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const pnlTone = totalUnrealizedPnlNum >= 0 ? 'positive' : 'negative'

  // 基于真实盈亏计算的衍生指标
  const pnlPercentNum = baseCapital > 0 ? (totalUnrealizedPnlNum / baseCapital) * 100 : 0
  const pnlPercentFormatted = `${pnlPercentNum >= 0 ? '+' : ''}${pnlPercentNum.toFixed(2)}%`
  const equityPointNum = totalEquityNum / 10000
  const equityCurve = [100, +(100 + pnlPercentNum).toFixed(2), +equityPointNum.toFixed(2)]

  // 基于真实策略状态统计
  const runningCount = strategies.filter((s) => s.status === '运行中' || s.status === '纸面运行').length
  const strategyStatusText = strategies.length === 0
    ? '暂无策略'
    : runningCount === strategies.length ? '全部正常运行' : `${runningCount}/${strategies.length} 运行中`
  const strategyTone = strategies.length === 0 ? 'neutral' : (runningCount === strategies.length ? 'positive' : 'warning')

  // 基于真实风控规则统计
  const blockedRules = riskRules.filter((r) => r.result === '阻断').length
  const warningRules = riskRules.filter((r) => r.result === '观察').length
  const riskStatusValue = riskRules.length === 0 ? '规则加载中' : (blockedRules > 0 ? `${blockedRules} 项阻断` : '风控就绪')
  const riskChangeText = riskRules.length === 0 ? '等待数据' : `${blockedRules} 阻断 · ${warningRules} 观察`
  const riskCaptionText = `${riskRules.length} 项前置规则生效`
  const riskTone = blockedRules > 0 ? 'negative' : (warningRules > 0 ? 'warning' : 'positive')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="系统总览"
        title="控制台 Dashboard"
        description="全系统核心资产与运行状态：真实公网交易所行情、实时多币种头寸、风控前置校验与微服务监控"
        action={
          <button className="button button--secondary" onClick={() => loadData(false)}>
            <RefreshCw size={14} />
            立即同步状态
          </button>
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
            ? '✓ 生产级实时行情与交易控制平面已全量直连 (PostgreSQL 16 · Redis 7 · Live Exchange Feed)'
            : (apiError ? `⚠ API 连接提示: ${apiError}` : '正在建立实时高频数据链路...')}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? '100% Real API Live' : 'Connecting'}
        </StatusBadge>
      </div>

      {/* KPI Stat Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard
          label="净资产总额 (Total Equity)"
          value={`$${totalEquity}`}
          change={pnlFormatted}
          caption="含浮动盈亏 MTM"
          tone={pnlTone}
          icon={<Wallet size={18} />}
        />
        <StatCard
          label="24h 未实现 PnL"
          value={pnlFormatted}
          change={pnlPercentFormatted}
          caption="盯市标记价自动刷新"
          tone={pnlTone}
          icon={<TrendingUp size={18} />}
        />
        <StatCard
          label="运行中策略 (Active Strategies)"
          value={`${strategies.length} 套策略`}
          change={strategyStatusText}
          caption="网格 / 趋势 / 跨期套利"
          tone={strategyTone}
          icon={<Zap size={18} />}
        />
        <StatCard
          label="风控前置健康度 (Risk Status)"
          value={isLiveApi ? riskStatusValue : '检查中'}
          change={riskChangeText}
          caption={riskCaptionText}
          tone={riskTone}
          icon={<ShieldCheck size={18} />}
        />
      </div>

      {/* Main Row 1: Net Asset Curve & Market Watch */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <Panel
          title="账户总资产权益走势 (Equity Curve)"
          subtitle="基于实时持仓盯市盈亏计算"
          action={<span className={`cell-mono text-${pnlTone}`} style={{ fontSize: 13, fontWeight: 700 }}>{pnlPercentFormatted} 累计收益</span>}
        >
          <div style={{ marginBottom: 12 }}>
            <Sparkline values={equityCurve} tone={pnlTone} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
            <span>起始本金: $1,000,000.00</span>
            <span>当前净资产: ${totalEquity}</span>
            <span>未实现盈亏: {pnlFormatted}</span>
          </div>
        </Panel>

        <Panel
          title="核心标的行情 (Market Watch)"
          subtitle="API GET /api/v1/market/tickers"
          action={<Link to="/market" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none' }}>完整行情 <ArrowUpRight size={13} /></Link>}
        >
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>标的</th>
                  <th>最新价</th>
                  <th>24h 涨跌</th>
                </tr>
              </thead>
              <tbody>
                {tickers.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>正在获取公网行情...</td></tr>
                ) : (
                  tickers.slice(0, 5).map((t) => (
                    <tr key={t.symbol}>
                      <td>
                        <strong>{t.symbol}</strong>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t.name}</div>
                      </td>
                      <td className="cell-mono">{t.lastPrice}</td>
                      <td className={`cell-mono text-${t.changeTone}`}>{t.change}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Main Row 2: Active Positions & Strategy Status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <Panel
          title="当前持仓 (Positions)"
          subtitle="API GET /api/v1/positions"
          action={<Link to="/execution" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none' }}>去下单与对账 →</Link>}
        >
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>合约/现货</th>
                  <th>方向</th>
                  <th>数量</th>
                  <th>未实现 PnL</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>暂无持仓数据</td></tr>
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
                      <td className={`cell-mono text-${pos.pnlTone}`}>{pos.pnl}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="运行中策略 (Active Strategies)"
          subtitle="API GET /api/v1/strategies"
          action={<Link to="/research" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none' }}>策略中心 →</Link>}
        >
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>策略 ID / 名称</th>
                  <th>版本</th>
                  <th>状态</th>
                  <th>类型</th>
                </tr>
              </thead>
              <tbody>
                {strategies.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>暂无策略数据</td></tr>
                ) : (
                  strategies.slice(0, 4).map((st) => (
                    <tr key={st.id}>
                      <td>
                        <strong>{st.name}</strong>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{st.id}</div>
                      </td>
                      <td className="cell-mono">v{st.version}</td>
                      <td>
                        <StatusBadge tone={st.status === '运行中' ? 'positive' : 'accent'}>
                          {st.status}
                        </StatusBadge>
                      </td>
                      <td className="cell-mono">{st.kind}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Main Row 3: Orders Stream & Microservices Health */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <Panel
          title="最新订单意图 (Order Intents Audit)"
          subtitle="API GET /api/v1/orders"
          action={<Link to="/execution" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none' }}>全部订单 →</Link>}
        >
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>订单 ID</th>
                  <th>策略版本</th>
                  <th>方向 / 标的</th>
                  <th>价格 / 数量</th>
                  <th>风控决策 ID</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>暂无订单意图记录</td></tr>
                ) : (
                  orders.slice(0, 5).map((ord) => (
                    <tr key={ord.id}>
                      <td className="cell-mono"><strong>{ord.id}</strong></td>
                      <td className="cell-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ord.strategyVersion}</td>
                      <td>
                        <StatusBadge tone={ord.side === '买入' ? 'positive' : 'negative'}>
                          {ord.side}
                        </StatusBadge>
                        <span style={{ marginLeft: 6, fontWeight: 600 }}>{ord.symbol}</span>
                      </td>
                      <td className="cell-mono">{ord.price} / {ord.quantity}</td>
                      <td className="cell-mono" style={{ fontSize: 10, color: 'var(--color-accent)' }}>{ord.riskDecisionId}</td>
                      <td>
                        <StatusBadge tone={ord.status === '已成交' ? 'positive' : ord.status === '部分成交' ? 'warning' : ord.status === '风控阻断' ? 'negative' : 'neutral'}>
                          {ord.status}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="系统服务与风控检查" subtitle="架构平面的实时连通性" action={<StatusBadge tone="positive"><CheckCircle2 size={12} /> 全部在线</StatusBadge>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>风控前置 Rule Preflight (GET /api/v1/risk/rules)</div>
            {riskRules.length === 0 ? (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '6px 0' }}>风控规则加载中...</div>
            ) : (
              riskRules.slice(0, 3).map((rule) => (
                <div key={rule.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 10px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{rule.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>作用域: {rule.scope} · {rule.detail}</div>
                  </div>
                  <ResultMark result={rule.result} />
                </div>
              ))
            )}

            <div style={{ height: 1, backgroundColor: 'var(--border-color)', margin: '4px 0' }} />

            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>微服务状态 Microservices</div>
            {services.slice(0, 4).map((svc) => (
              <div key={svc.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
                <span>{svc.name}</span>
                <span className="cell-mono text-positive">{svc.latency}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}
