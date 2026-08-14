import { Activity, CandlestickChart, Clock, Database, RefreshCw, ShieldAlert, Sparkles, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendTicker } from '../adapters'
import { api, type SymbolResponse } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, OrderbookViewer, PageIntro, Panel, Sparkline, StatusBadge, TabGroup } from '../components/Primitives'
import { mockFundingRates, mockMarketTickers, mockOrderBook, mockTrades } from '../mockData'
import type { MarketTicker } from '../types'

export default function MarketData() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT')
  const [activeTab, setActiveTab] = useState('depth')
  const [tickers, setTickers] = useState<MarketTicker[]>(mockMarketTickers)
  const [symbols, setSymbols] = useState<SymbolResponse[]>([])
  const [apiErrorDetail, setApiErrorDetail] = useState<{ status?: number; code?: string; message?: string; traceId?: string } | null>(null)

  const loadMarketData = async () => {
    setLoading(true)
    setApiErrorDetail(null)
    try {
      let connected = false

      let symsRes: SymbolResponse[] | null = null
      try {
        symsRes = await api.symbols()
        if (Array.isArray(symsRes)) {
          setSymbols(symsRes)
          connected = true
        }
      } catch (err: any) {
        setApiErrorDetail({
          status: err?.status ?? 503,
          code: err?.code ?? 'ADAPTER_NOT_CONNECTED',
          message: err?.message ?? 'Market symbols feed offline',
          traceId: err?.trace_id ?? 'trace-market-err'
        })
      }

      try {
        const tickersRes = await api.tickers()
        if (Array.isArray(tickersRes) && tickersRes.length > 0) {
          const symbolMap = new Map((symsRes || []).map((s) => [s.symbol, s]))
          const mapped = tickersRes.map((t) => mapBackendTicker(t, symbolMap.get(t.symbol)))
          setTickers(mapped)
          connected = true
        }
      } catch (err: any) {
        if (!apiErrorDetail) {
          setApiErrorDetail({
            status: err?.status ?? 503,
            code: err?.code ?? 'ADAPTER_NOT_CONNECTED',
            message: err?.message ?? 'Market tickers feed offline',
            traceId: err?.trace_id ?? 'trace-market-err'
          })
        }
      }

      setIsLiveApi(connected)
    } catch {
      setIsLiveApi(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMarketData()
  }, [])

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="数据平面" title="市场数据 Market Data" description="跨交易所行情标准化、盘口深度、成交流与数据质量巡检" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="数据平面" title="市场数据 Market Data" description="正在向 API 获取最新的 Symbol 与 Ticker 列表..." />
        <DataState state="loading" title="读取行情数据中" description="GET /api/v1/market/symbols, /api/v1/market/tickers" />
      </div>
    )
  }

  const activeTicker = tickers.find((t) => t.symbol === selectedSymbol) || tickers[0] || mockMarketTickers[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="数据平面"
        title="市场数据 Market Data"
        description="统一标准行情模型：跨 Binance / OKX / Bybit 实时 Tick、L2 盘口、资金费率与数据质量防线"
        action={
          <button className="button button--secondary" onClick={loadMarketData}>
            <RefreshCw size={14} />
            刷新 Tick API
          </button>
        }
      />

      {/* API Connection Status Banner */}
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
            ? '✓ 已接入 API GET /api/v1/market/symbols & /tickers'
            : apiErrorDetail
            ? `⚠ 行情端点断开 [HTTP ${apiErrorDetail.status ?? 503}]: ${apiErrorDetail.code} - ${apiErrorDetail.message} (trace_id: ${apiErrorDetail.traceId}) · 已降级为 Demo/Mock`
            : '⚠ 行情 API 未连接，当前显示 [Demo / Mock 模拟行情源] (盘口与成交流目前后端尚未提供接口)'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'API Tickers Live' : 'Demo Market Data'}
        </StatusBadge>
      </div>

      {/* Symbol Selection Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        {tickers.map((t) => {
          const isSelected = t.symbol === selectedSymbol
          return (
            <div
              key={t.symbol}
              onClick={() => setSelectedSymbol(t.symbol)}
              style={{
                backgroundColor: isSelected ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: `1px solid ${isSelected ? 'var(--color-accent)' : 'var(--border-color)'}`,
                borderRadius: 'var(--radius-lg)',
                padding: '12px 14px',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{t.symbol}</span>
                <StatusBadge tone={t.quality === '正常' ? 'positive' : 'warning'}>{t.source}</StatusBadge>
              </div>
              <div className="cell-mono" style={{ fontSize: 16, fontWeight: 700 }}>{t.lastPrice}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4, fontSize: 11 }}>
                <span className={`cell-mono text-${t.changeTone}`}>{t.change}</span>
                <span style={{ color: 'var(--text-muted)' }}>24h: {t.volume}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Main Grid: Orderbook Depth & Trade Stream */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <Panel
          title={`${activeTicker.symbol} 盘口深度 & 行情分析`}
          subtitle={`数据源: ${activeTicker.source} · 更新于 ${activeTicker.eventTime}`}
          action={
            <TabGroup
              tabs={[
                { id: 'depth', label: 'L2 盘口深度 (Demo)' },
                { id: 'funding', label: '资金费率与持仓量 (Demo)' },
                { id: 'quality', label: '数据质量检测' },
              ]}
              activeTab={activeTab}
              onChange={setActiveTab}
            />
          }
        >
          {activeTab === 'depth' && (
            <div>
              <div style={{ display: 'flex', gap: 20, marginBottom: 16, padding: '10px 14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                <div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>买一价 (Bid)</span>
                  <div className="cell-mono text-positive" style={{ fontWeight: 700 }}>{activeTicker.bidPrice}</div>
                </div>
                <div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>卖一价 (Ask)</span>
                  <div className="cell-mono text-negative" style={{ fontWeight: 700 }}>{activeTicker.askPrice}</div>
                </div>
                <div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>买卖价差 (Spread)</span>
                  <div className="cell-mono" style={{ fontWeight: 600 }}>{activeTicker.spread}</div>
                </div>
                <div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>质量状态</span>
                  <div><StatusBadge tone="positive">正常 · 无丢包</StatusBadge></div>
                </div>
              </div>
              <OrderbookViewer data={mockOrderBook} />
            </div>
          )}

          {activeTab === 'funding' && (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>合约代码</th>
                    <th>当前资金费率</th>
                    <th>预测费率</th>
                    <th>下次结算时间</th>
                    <th>全网持仓量 (OI)</th>
                    <th>OI 24h 变化</th>
                  </tr>
                </thead>
                <tbody>
                  {mockFundingRates.map((f) => (
                    <tr key={f.symbol}>
                      <td><strong>{f.symbol}</strong></td>
                      <td className="cell-mono text-positive">{f.rate}</td>
                      <td className="cell-mono">{f.predictedRate}</td>
                      <td className="cell-mono">{f.nextSettlement}</td>
                      <td className="cell-mono">{f.openInterest}</td>
                      <td className="cell-mono text-positive">{f.openInterestChange}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'quality' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                <div style={{ padding: 12, backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>网络与接入延迟 (Ingest Latency)</div>
                  <div className="cell-mono" style={{ fontSize: 18, fontWeight: 700, marginTop: 4 }}>42.8 ms</div>
                  <div style={{ fontSize: 10, color: 'var(--color-positive)', marginTop: 2 }}>目标 &lt; 100ms (优良)</div>
                </div>
                <div style={{ padding: 12, backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Sequence 序列连续性</div>
                  <div className="cell-mono" style={{ fontSize: 18, fontWeight: 700, marginTop: 4 }}>100%</div>
                  <div style={{ fontSize: 10, color: 'var(--color-positive)', marginTop: 2 }}>零跳跃，无乱序</div>
                </div>
                <div style={{ padding: 12, backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>异常价格/数量刺头检测</div>
                  <div className="cell-mono" style={{ fontSize: 18, fontWeight: 700, marginTop: 4 }}>0 次触发</div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>3-Sigma 离群过滤器激活</div>
                </div>
              </div>
              <div className="code-block">
                {`{
  "event_type": "market.ticker.v1",
  "source": "${activeTicker.source}",
  "symbol": "${activeTicker.symbol}",
  "market_type": "${activeTicker.marketType}",
  "event_time": "2026-08-09T01:26:18.420Z",
  "ingest_time": "2026-08-09T01:26:18.462Z",
  "last_price": "${activeTicker.lastPrice.replace(',', '')}",
  "sequence": 19482104
}`}
              </div>
            </div>
          )}
        </Panel>

        {/* Time & Sales Feed */}
        <Panel title="逐笔成交流 (Time & Sales)" subtitle="Demo/Mock Stream">
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>价格</th>
                  <th>数量</th>
                  <th>方向</th>
                </tr>
              </thead>
              <tbody>
                {mockTrades.map((tr) => (
                  <tr key={tr.id}>
                    <td className="cell-mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{tr.time}</td>
                    <td className={`cell-mono text-${tr.side === 'buy' ? 'positive' : 'negative'}`}>{tr.price}</td>
                    <td className="cell-mono">{tr.quantity}</td>
                    <td>
                      <StatusBadge tone={tr.side === 'buy' ? 'positive' : 'negative'} dot={false}>
                        {tr.side.toUpperCase()}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  )
}
