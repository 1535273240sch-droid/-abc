import { Activity, ArrowUpRight, CheckCircle2, RefreshCw, ShieldCheck, TrendingUp, Wallet, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mapBackendOrder, mapBackendPosition, mapBackendStrategy, mapBackendTicker } from '../adapters'
import { api } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, PageIntro, Panel, ResultMark, Sparkline, StatCard, StatusBadge } from '../components/Primitives'
import { mockMarketTickers, mockOrders, mockPositions, mockRiskRules, mockServices, mockStrategies } from '../mockData'
import type { MarketTicker, Order, Position, RiskRule, Strategy, SystemService } from '../types'

export default function Dashboard() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const [tickers, setTickers] = useState<MarketTicker[]>(mockMarketTickers)
  const [orders, setOrders] = useState<Order[]>(mockOrders)
  const [positions, setPositions] = useState<Position[]>(mockPositions)
  const [strategies, setStrategies] = useState<Strategy[]>(mockStrategies)
  const [services, setServices] = useState<SystemService[]>(mockServices)

  const loadData = async () => {
    setLoading(true)
    setApiError(null)
    try {
      const [statusRes, tickersRes, ordersRes, positionsRes, stratsRes] = await Promise.all([
        api.systemStatus().catch(() => null),
        api.tickers().catch(() => null),
        api.orders().catch(() => null),
        api.positions().catch(() => null),
        api.strategies().catch(() => null)
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
      if (statusRes) {
        setServices([
          {
            name: statusRes.app_name,
            status: statusRes.status === 'ok' ? '正常' : '降级',
            latency: '8ms',
            region: `Uptime: ${statusRes.uptime_seconds}s`,
            version: statusRes.app_version
          },
          ...mockServices.slice(1)
        ])
        connected = true
      }

      setIsLiveApi(connected)
    } catch (err: any) {
      setApiError(err?.message || '后端 API 无法连接，已降级使用 Demo/Mock 数据')
      setIsLiveApi(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="系统总览"
        title="控制台 Dashboard"
        description="机构级 AI 交易总览：权益、PnL、实时风控状态与 Agent 协作 (Paper Mode)"
        action={
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button className="button button--secondary" onClick={loadData}>
              <RefreshCw size={14} />
              重新拉取 API
            </button>
            <Link to="/risk" className="button button--secondary">
              <ShieldCheck size={14} />
              风控检查
            </Link>
            <Link to="/execution" className="button button--primary">
              <Zap size={14} />
              交易执行
            </Link>
          </div>
        }
      />

      {/* API Source Banner */}
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
            ? '✓ 已接入真实后端 Paper API (http://127.0.0.1:8000)'
            : '⚠ 后端 API 未在线，当前已降级为 [Demo/Mock 模拟数据源] 展示'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'Paper API Live' : 'Demo / Mock Fallback'}
        </StatusBadge>
      </div>

      {/* Top Key Metrics */}
      <div className="grid-cols-4">
        <StatCard
          label="账户总权益 (Paper Net Equity)"
          value="$248,920.50"
          change="+$3,412.18 (24h)"
          caption="基准: USDT"
          tone="positive"
          icon={<Wallet size={18} />}
        />
        <StatCard
          label="24h 累计 PnL"
          value="+$3,412.18"
          change="+1.39%"
          caption="年化夏普: 1.94"
          tone="positive"
          icon={<TrendingUp size={18} />}
        />
        <StatCard
          label="风险预算与杠杆 (Leverage)"
          value="1.42x"
          change="安全限额 < 3.00x"
          caption="最高单标敞口 38.2%"
          tone="accent"
          icon={<ShieldCheck size={18} />}
        />
        <StatCard
          label="系统健康度 (System Health)"
          value={isLiveApi ? '100% API 就绪' : 'Demo 模拟'}
          change="延迟 12ms (UTC)"
          caption="Paper Mode 运行中"
          tone="positive"
          icon={<Activity size={18} />}
        />
      </div>

      {/* Main Row 1: Equity Trend & Market Snapshot */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <Panel
          title="权益与 PnL 收益曲线 (24h 模拟)"
          subtitle={isLiveApi ? '后端 API 数据映射' : 'Demo/Mock Environment'}
          action={<StatusBadge tone="positive">纸面模拟运行中</StatusBadge>}
        >
          <div style={{ padding: '10px 0' }}>
            <Sparkline values={[241000, 242500, 241800, 243900, 244200, 243000, 246100, 245800, 247200, 248920]} tone="positive" />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
              <span>00:00 UTC ($241,000.00)</span>
              <span>06:00 UTC</span>
              <span>12:00 UTC</span>
              <span>18:00 UTC</span>
              <span>当前 ($248,920.50)</span>
            </div>
          </div>
        </Panel>

        <Panel
          title="主力标的行情快照"
          subtitle={isLiveApi ? 'API GET /api/v1/market/tickers' : 'Demo 模拟 Tick'}
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
                {tickers.slice(0, 4).map((t) => (
                  <tr key={t.symbol}>
                    <td>
                      <strong>{t.symbol}</strong>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t.name}</div>
                    </td>
                    <td className="cell-mono">{t.lastPrice}</td>
                    <td className={`cell-mono text-${t.changeTone}`}>{t.change}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Main Row 2: Active Positions & Strategy Status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <Panel
          title="当前持仓 (Positions)"
          subtitle={isLiveApi ? 'API GET /api/v1/positions' : 'Demo 持仓明细'}
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
          subtitle={isLiveApi ? 'API GET /api/v1/strategies' : 'Demo 策略清单'}
          action={<Link to="/research" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none' }}>策略中心 →</Link>}
        >
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>策略 ID / 名称</th>
                  <th>版本</th>
                  <th>状态</th>
                  <th>夏普比率</th>
                </tr>
              </thead>
              <tbody>
                {strategies.slice(0, 3).map((st) => (
                  <tr key={st.id}>
                    <td>
                      <strong>{st.name}</strong>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{st.id}</div>
                    </td>
                    <td className="cell-mono">{st.version}</td>
                    <td>
                      <StatusBadge tone={st.status === '运行中' ? 'positive' : st.status === '纸面运行' ? 'accent' : 'neutral'}>
                        {st.status}
                      </StatusBadge>
                    </td>
                    <td className="cell-mono">{st.sharpe}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Main Row 3: Orders Stream & Microservices Health */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <Panel
          title="最新订单意图 (Order Intents Audit)"
          subtitle={isLiveApi ? 'API GET /api/v1/orders' : 'Demo 订单意图'}
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
                  orders.map((ord) => (
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
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>风控前置 Rule Preflight</div>
            {mockRiskRules.slice(0, 3).map((rule) => (
              <div key={rule.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 10px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{rule.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{rule.detail}</div>
                </div>
                <ResultMark result={rule.result} />
              </div>
            ))}

            <div style={{ height: 1, backgroundColor: 'var(--border-color)', margin: '4px 0' }} />

            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>微服务状态 Microservices</div>
            {services.slice(0, 3).map((svc) => (
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
