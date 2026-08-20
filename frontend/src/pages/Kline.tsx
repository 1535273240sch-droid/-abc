import { useEffect, useState } from 'react'
import { api } from '../api'
import KlineChart from '../components/KlineChart'

const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT']

export default function Kline() {
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS)
  const [symbol, setSymbol] = useState('BTCUSDT')

  useEffect(() => {
    api
      .tickers()
      .then((tickers) => {
        const list = tickers.map((t) => t.symbol).filter((s): s is string => Boolean(s))
        if (list.length > 0) {
          setSymbols(list)
          if (!list.includes('BTCUSDT')) setSymbol(list[0])
        }
      })
      .catch(() => {})
  }, [])

  return (
    <div className="kl-page">
      <div className="kl-head">
        <div>
          <h1>K线图表</h1>
          <p className="kl-sub">实时K线 · 技术指标 · 画线工具（数据源：Binance 公共行情，6 秒自动刷新）</p>
        </div>
        <div className="kl-controls">
          <label htmlFor="kl-symbol">交易对</label>
          <select id="kl-symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>
      <KlineChart symbol={symbol} />
      <div className="kl-tips">
        提示：点击画线工具后在图上拖拽绘制；「清除画线」删除全部画线；指标按钮可自由叠加（MA/BOLL 叠加在主图，其余在副图）。
      </div>
    </div>
  )
}
