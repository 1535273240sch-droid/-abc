import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { PerformanceDailyPoint, PerformanceReport } from '../api'

const DAY_OPTIONS = [30, 90, 180]

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return `${(v * 100).toFixed(2)}%`
}

function pnlClass(v: number): string {
  return v > 0 ? 'an-pos' : v < 0 ? 'an-neg' : 'an-flat'
}

function DailyPnlChart({ data }: { data: PerformanceDailyPoint[] }) {
  if (data.length === 0) return <div className="an-empty">暂无每日盈亏数据（依赖 MTM 标记记录）</div>
  const W = 820
  const H = 220
  const PAD = 20
  const values = data.map((d) => d.pnl)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const y = (v: number) => PAD + (H - 2 * PAD) * (1 - (v - min) / range)
  const slot = (W - 2 * PAD) / data.length
  const bw = Math.max(2, slot - 1.5)
  const zeroY = y(0)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="an-svg" preserveAspectRatio="none">
      <line x1={PAD} x2={W - PAD} y1={zeroY} y2={zeroY} className="an-zero" vectorEffect="non-scaling-stroke" />
      {data.map((d, i) => {
        const x = PAD + i * slot
        const top = d.pnl >= 0 ? y(d.pnl) : zeroY
        const h = Math.max(1, Math.abs(zeroY - y(d.pnl)))
        return (
          <rect key={d.date} x={x} y={top} width={bw} height={h} className={d.pnl >= 0 ? 'an-bar-pos' : 'an-bar-neg'}>
            <title>{`${d.date}  盈亏 ${fmt(d.pnl)}`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

function CumulativeChart({ data }: { data: PerformanceDailyPoint[] }) {
  if (data.length === 0) return <div className="an-empty">暂无累计曲线数据</div>
  const W = 820
  const H = 220
  const PAD = 20
  const values = data.map((d) => d.cumulative)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const x = (i: number) => PAD + ((W - 2 * PAD) * i) / Math.max(1, data.length - 1)
  const y = (v: number) => PAD + (H - 2 * PAD) * (1 - (v - min) / range)
  const points = data.map((d, i) => `${x(i)},${y(d.cumulative)}`).join(' ')
  const zeroY = y(0)
  const area = `M ${PAD},${zeroY} L ${data.map((d, i) => `${x(i)},${y(d.cumulative)}`).join(' L ')} L ${W - PAD},${zeroY} Z`
  const last = data[data.length - 1]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="an-svg" preserveAspectRatio="none">
      <line x1={PAD} x2={W - PAD} y1={zeroY} y2={zeroY} className="an-zero" vectorEffect="non-scaling-stroke" />
      <path d={area} className="an-area" />
      <polyline points={points} className="an-line" vectorEffect="non-scaling-stroke" />
      <circle cx={x(data.length - 1)} cy={y(last.cumulative)} r={3} className={last.cumulative >= 0 ? 'an-dot-pos' : 'an-dot-neg'} />
    </svg>
  )
}

export default function Analytics() {
  const [report, setReport] = useState<PerformanceReport | null>(null)
  const [days, setDays] = useState(90)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setReport(await api.performance(days))
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void load()
  }, [load])

  const s = report?.summary

  return (
    <div className="an-page">
      <div className="an-head">
        <div>
          <h1>盈亏分析</h1>
          <p className="an-sub">
            基于成交、持仓与 MTM 标记数据的绩效报表
            {report ? ` · 更新于 ${new Date(report.generated_at).toLocaleString()}` : ''}
          </p>
        </div>
        <div className="an-controls">
          {DAY_OPTIONS.map((d) => (
            <button key={d} className={`an-btn ${days === d ? 'an-btn--active' : ''}`} onClick={() => setDays(d)}>
              近 {d} 天
            </button>
          ))}
          <button className="an-btn" onClick={() => void load()}>
            刷新
          </button>
        </div>
      </div>

      {error && <div className="an-error">{error}</div>}
      {loading && !report && <div className="an-empty">加载中…</div>}

      {s && (
        <>
          <div className="an-grid">
            <div className="an-card">
              <div className="an-card-label">总盈亏 (USDT)</div>
              <div className={`an-card-value ${pnlClass(s.total_pnl)}`}>{fmt(s.total_pnl)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">已实现盈亏</div>
              <div className={`an-card-value ${pnlClass(s.realized_pnl)}`}>{fmt(s.realized_pnl)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">未实现盈亏</div>
              <div className={`an-card-value ${pnlClass(s.unrealized_pnl)}`}>{fmt(s.unrealized_pnl)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">胜率（按日）</div>
              <div className="an-card-value">{fmtPct(s.win_rate)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">夏普比率（年化）</div>
              <div className="an-card-value">{fmt(s.sharpe)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">最大回撤</div>
              <div className="an-card-value an-neg">{fmt(s.max_drawdown)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">盈亏比</div>
              <div className="an-card-value">{s.profit_factor === null ? '--' : fmt(s.profit_factor)}</div>
            </div>
            <div className="an-card">
              <div className="an-card-label">成交笔数 / 持仓数</div>
              <div className="an-card-value">
                {s.total_fills} / {s.open_positions}
              </div>
            </div>
            <div className="an-card">
              <div className="an-card-label">最佳单日 / 最差单日</div>
              <div className="an-card-value">
                <span className="an-pos">{fmt(s.best_day)}</span>
                {' / '}
                <span className="an-neg">{fmt(s.worst_day)}</span>
              </div>
            </div>
            <div className="an-card">
              <div className="an-card-label">日均盈亏 / 日波动</div>
              <div className="an-card-value">
                {fmt(s.avg_daily_pnl)} / {fmt(s.volatility_daily)}
              </div>
            </div>
          </div>

          <div className="an-chart">
            <h3 className="an-chart-title">每日盈亏（MTM 口径）</h3>
            <DailyPnlChart data={report?.daily_series ?? []} />
          </div>

          <div className="an-chart">
            <h3 className="an-chart-title">累计盈亏曲线</h3>
            <CumulativeChart data={report?.daily_series ?? []} />
          </div>

          <div className="an-chart">
            <h3 className="an-chart-title">按币种分解</h3>
            {report.symbols.length === 0 ? (
              <div className="an-empty">暂无持仓与成交数据</div>
            ) : (
              <table className="an-table">
                <thead>
                  <tr>
                    <th>币种</th>
                    <th>已实现</th>
                    <th>未实现</th>
                    <th>总盈亏</th>
                    <th>数量</th>
                    <th>开仓价</th>
                    <th>现价</th>
                    <th>成交</th>
                    <th>名义额</th>
                  </tr>
                </thead>
                <tbody>
                  {report.symbols.map((r) => (
                    <tr key={r.symbol}>
                      <td>{r.symbol}</td>
                      <td className={pnlClass(r.realized_pnl)}>{fmt(r.realized_pnl)}</td>
                      <td className={pnlClass(r.unrealized_pnl)}>{fmt(r.unrealized_pnl)}</td>
                      <td className={pnlClass(r.total_pnl)}>{fmt(r.total_pnl)}</td>
                      <td>{fmt(r.quantity, 6)}</td>
                      <td>{fmt(r.entry_price, 4)}</td>
                      <td>{fmt(r.current_price, 4)}</td>
                      <td>{r.fills}</td>
                      <td>{fmt(r.notional)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
