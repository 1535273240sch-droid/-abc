import { useCallback, useEffect, useRef, useState } from 'react'
import { dispose, init } from 'klinecharts'
import type { Chart, KLineData } from 'klinecharts'
import { api } from '../api'

interface IndicatorConfig {
  key: string
  label: string
  type: string
  paneId: string
}

const INDICATORS: IndicatorConfig[] = [
  { key: 'ma', label: 'MA', type: 'MA', paneId: 'candle_pane' },
  { key: 'vol', label: 'VOL', type: 'VOL', paneId: 'vol_pane' },
  { key: 'boll', label: 'BOLL', type: 'BOLL', paneId: 'candle_pane' },
  { key: 'macd', label: 'MACD', type: 'MACD', paneId: 'macd_pane' },
  { key: 'rsi', label: 'RSI', type: 'RSI', paneId: 'rsi_pane' },
  { key: 'kdj', label: 'KDJ', type: 'KDJ', paneId: 'kdj_pane' },
]

const PERIODS = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
]

const DRAW_TOOLS = [
  { label: '趋势线', type: 'segment' },
  { label: '射线', type: 'rayLine' },
  { label: '水平线', type: 'horizontalStraightLine' },
  { label: '垂直线', type: 'verticalStraightLine' },
  { label: '矩形', type: 'rect' },
  { label: '斐波那契', type: 'fibonacciLine' },
  { label: '价格线', type: 'priceLine' },
]

/* eslint-disable @typescript-eslint/no-explicit-any */
const DARK_STYLES: any = {
  grid: {
    horizontal: { color: '#1c2937' },
    vertical: { color: '#1c2937' },
  },
  candle: {
    bar: {
      upColor: '#26a69a',
      downColor: '#ef5350',
      upWickColor: '#26a69a',
      downWickColor: '#ef5350',
      upBorderColor: '#26a69a',
      downBorderColor: '#ef5350',
    },
    priceMark: {
      high: { color: '#7d8da1' },
      low: { color: '#7d8da1' },
      last: { upColor: '#26a69a', downColor: '#ef5350' },
    },
  },
  indicator: {
    bars: [{ upColor: '#26a69a', downColor: '#ef5350' }],
    lines: [{ color: '#f5a623' }, { color: '#e14eca' }, { color: '#4fc3f7' }],
  },
  xAxis: {
    axisLine: { color: '#2a3a4d' },
    tickText: { color: '#7d8da1' },
    tickLine: { color: '#2a3a4d' },
  },
  yAxis: {
    axisLine: { color: '#2a3a4d' },
    tickText: { color: '#7d8da1' },
    tickLine: { color: '#2a3a4d' },
  },
  crosshair: {
    horizontal: { text: { backgroundColor: '#2a4a6b', color: '#e6edf7' } },
    vertical: { text: { backgroundColor: '#2a4a6b', color: '#e6edf7' } },
  },
  separator: { color: '#1c2937' },
}

function toKlineData(bar: { timestamp: number; open: number; high: number; low: number; close: number; volume: number }): KLineData {
  return {
    timestamp: bar.timestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.volume,
  }
}

export default function KlineChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<Chart | null>(null)
  const [period, setPeriod] = useState('1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTool, setActiveTool] = useState<string | null>(null)
  const [indicatorState, setIndicatorState] = useState<Record<string, boolean>>({
    ma: true,
    vol: true,
    boll: false,
    macd: false,
    rsi: false,
    kdj: false,
  })

  // ── init chart once ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return
    const chart = init(containerRef.current)
    if (!chart) return
    chartRef.current = chart
    chart.setStyles(DARK_STYLES)
    chart.createIndicator('MA', false, { id: 'candle_pane' })
    chart.createIndicator('VOL', false, { id: 'vol_pane' })
    return () => {
      if (containerRef.current) dispose(containerRef.current)
      chartRef.current = null
    }
  }, [])

  // ── load full history when symbol / period changes ─────────────────
  const loadAll = useCallback(async () => {
    const chart = chartRef.current
    if (!chart) return
    setLoading(true)
    setError(null)
    try {
      const bars = await api.klines(symbol, period, 500)
      if (!chartRef.current) return
      if (!bars || bars.length === 0) {
        setError('暂无K线数据')
        return
      }
      chartRef.current.applyNewData(bars.map((b) => toKlineData(b)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'K线加载失败')
    } finally {
      setLoading(false)
    }
  }, [symbol, period])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  // ── poll latest bar every 6s ──────────────────────────────────────
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const bars = await api.klines(symbol, period, 2)
        const chart = chartRef.current
        if (chart && bars && bars.length > 0) {
          chart.updateData(toKlineData(bars[bars.length - 1]))
        }
      } catch {
        /* 轮询失败静默忽略 */
      }
    }, 6000)
    return () => clearInterval(timer)
  }, [symbol, period])

  const toggleIndicator = (cfg: IndicatorConfig) => {
    const chart = chartRef.current
    if (!chart) return
    setIndicatorState((prev) => {
      const next = { ...prev, [cfg.key]: !prev[cfg.key] }
      if (next[cfg.key]) {
        chart.createIndicator(cfg.type, false, { id: cfg.paneId })
      } else {
        chart.removeIndicator(cfg.paneId, cfg.type)
      }
      return next
    })
  }

  const startDraw = (type: string) => {
    const chart = chartRef.current
    if (!chart) return
    chart.createOverlay(type)
    setActiveTool(type)
  }

  const clearDraw = () => {
    if (chartRef.current) chartRef.current.removeOverlay()
    setActiveTool(null)
  }

  return (
    <div className="kl-chart">
      <div className="kl-toolbar">
        <div className="kl-toolbar__group">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              className={`kl-btn ${period === p.value ? 'kl-btn--active' : ''}`}
              onClick={() => setPeriod(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="kl-toolbar__group">
          {INDICATORS.map((ind) => (
            <button
              key={ind.key}
              className={`kl-btn ${indicatorState[ind.key] ? 'kl-btn--active' : ''}`}
              onClick={() => toggleIndicator(ind)}
            >
              {ind.label}
            </button>
          ))}
        </div>
        <div className="kl-toolbar__group">
          {DRAW_TOOLS.map((tool) => (
            <button
              key={tool.type}
              className={`kl-btn ${activeTool === tool.type ? 'kl-btn--active' : ''}`}
              onClick={() => startDraw(tool.type)}
            >
              {tool.label}
            </button>
          ))}
          <button className="kl-btn kl-btn--clear" onClick={clearDraw}>
            清除画线
          </button>
        </div>
      </div>
      {error && <div className="kl-error">{error}</div>}
      <div ref={containerRef} className="kl-container" />
      {loading && <div className="kl-loading">加载 {symbol} · {period} K线中…</div>}
    </div>
  )
}
