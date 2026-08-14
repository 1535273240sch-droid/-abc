import { Code2, Play, FileText, FlaskConical, GitBranch, Layers, LineChart, Plus, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendBacktest, mapBackendStrategy } from '../adapters'
import { api, type BacktestRequest } from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, Sparkline, StatCard, StatusBadge } from '../components/Primitives'
import { mockBacktestResult, mockStrategies } from '../mockData'
import type { BacktestResult, Strategy } from '../types'

export default function Research() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [strategies, setStrategies] = useState<Strategy[]>(mockStrategies)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy>(mockStrategies[0])
  const [backtestResult, setBacktestResult] = useState<BacktestResult>(mockBacktestResult)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Backtest form state
  const [formSnapshot, setFormSnapshot] = useState('snap_parquet_20260801_utc')
  const [formCapital, setFormCapital] = useState('100000.00')
  const [formFeeModel, setFormFeeModel] = useState('maker_0.02pct_taker_0.04pct')
  const [formSlippageModel, setFormSlippageModel] = useState('conservative_1.5bps')
  const [isSubmittingBacktest, setIsSubmittingBacktest] = useState(false)

  const loadResearchData = async () => {
    setLoading(true)
    try {
      const [stratsRes, backtestsRes] = await Promise.all([
        api.strategies().catch(() => null),
        api.backtests().catch(() => null)
      ])

      let connected = false
      if (stratsRes && Array.isArray(stratsRes) && stratsRes.length > 0) {
        const mappedStrats = stratsRes.map((s) => mapBackendStrategy(s))
        setStrategies(mappedStrats)
        setSelectedStrategy(mappedStrats[0])
        connected = true
      }

      if (backtestsRes && Array.isArray(backtestsRes) && backtestsRes.length > 0) {
        const mappedBt = mapBackendBacktest(backtestsRes[0])
        setBacktestResult(mappedBt)
        connected = true
      }

      setIsLiveApi(connected)
    } catch {
      setIsLiveApi(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadResearchData()
  }, [])

  const handleExecuteBacktest = async () => {
    setIsSubmittingBacktest(true)
    try {
      const payload: BacktestRequest = {
        strategy_id: selectedStrategy.id,
        strategy_version: selectedStrategy.version,
        data_snapshot: formSnapshot,
        fee_model: formFeeModel,
        slippage_model: formSlippageModel,
        initial_capital: formCapital,
        mode: 'paper'
      }

      const res = await api.createBacktest(payload)
      const mapped = mapBackendBacktest(res)
      setBacktestResult(mapped)
      setIsModalOpen(false)
      setIsLiveApi(true)
    } catch (err: any) {
      alert(`提交回测失败: ${err?.message || '未知错误'}`)
    } finally {
      setIsSubmittingBacktest(false)
    }
  }

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="研究平面" title="量化研究 Research" description="因子研发、策略版本管理、样本内外回测与可追溯归因报告" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="研究平面" title="量化研究 Research" description="正在读取后端 API 策略与回测结果..." />
        <DataState state="loading" title="读取研究与回测中" description="GET /api/v1/strategies, GET /api/v1/research/backtests" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageIntro
        eyebrow="研究平面"
        title="量化研究与策略中心"
        description="策略全生命周期管理：strategy_id + version + parameters + code_ref，支持精确回测复现 (Paper-Only)"
        action={
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="button button--secondary" onClick={loadResearchData}>
              <RefreshCw size={14} />
              刷新策略 API
            </button>
            <button className="button button--primary" onClick={() => setIsModalOpen(true)}>
              <Plus size={14} />
              新建回测任务
            </button>
          </div>
        }
      />

      {/* API Status Banner */}
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
            ? '✓ 已接入 API POST/GET /api/v1/research/backtests & /strategies (Paper-Only Engine)'
            : '⚠ 回测 API 未连接，当前展示 [Demo / Mock 模拟回测数据源]'}
        </span>
        <StatusBadge tone={isLiveApi ? 'positive' : 'warning'} dot={true}>
          {isLiveApi ? 'Research API Live' : 'Demo Strategies'}
        </StatusBadge>
      </div>

      {/* Top Metrics for Selected Strategy */}
      <div className="grid-cols-4">
        <StatCard
          label="回测夏普比率 (Sharpe Ratio)"
          value={backtestResult.sharpeRatio}
          change="样本外评估"
          caption="无风险利率按 3.0% 计"
          tone="positive"
          icon={<LineChart size={18} />}
        />
        <StatCard
          label="最大回撤 (Max Drawdown)"
          value={backtestResult.maxDrawdown}
          change="风控阈值 -12.0%"
          caption="锁定样本快照"
          tone="warning"
          icon={<Layers size={18} />}
        />
        <StatCard
          label="回测胜率 (Win Rate)"
          value={backtestResult.winRate}
          change={`共 ${backtestResult.totalTrades} 笔交易`}
          caption="盈亏比 1: 1.85"
          tone="accent"
          icon={<FlaskConical size={18} />}
        />
        <StatCard
          label="回测净收益 (Net Profit)"
          value={backtestResult.netProfit}
          change={`初始本金 ${backtestResult.initialCapital}`}
          caption={`扣除手续费 & 滑点`}
          tone="positive"
          icon={<GitBranch size={18} />}
        />
      </div>

      {/* Main Grid: Strategy Registry & Backtest Report */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20 }}>
        {/* Left Column: Strategy List */}
        <Panel title="策略注册表 (Strategy Registry)" subtitle={isLiveApi ? 'API GET /api/v1/strategies' : 'Demo 策略清单'}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {strategies.map((st) => {
              const isSelected = st.id === selectedStrategy.id
              return (
                <div
                  key={st.id}
                  onClick={() => setSelectedStrategy(st)}
                  style={{
                    padding: 12,
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${isSelected ? 'var(--color-accent)' : 'var(--border-color)'}`,
                    backgroundColor: isSelected ? 'var(--bg-card-hover)' : 'var(--bg-card-subtle)',
                    cursor: 'pointer',
                    transition: 'all 0.12s ease'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <strong style={{ fontSize: 13 }}>{st.name}</strong>
                    <StatusBadge tone={st.status === '运行中' ? 'positive' : st.status === '纸面运行' ? 'accent' : 'neutral'}>
                      {st.status}
                    </StatusBadge>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                    <span>ID: <code className="cell-mono">{st.id}</code></span>
                    <span>版本: <code className="cell-mono">v{st.version}</code></span>
                    <span>类型: {st.kind}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 11, borderTop: '1px solid var(--border-subtle)', paddingTop: 6 }}>
                    <span>夏普: <b className="cell-mono text-positive">{st.sharpe}</b></span>
                    <span>最大回撤: <b className="cell-mono text-warning">{st.maxDrawdown}</b></span>
                    <span>负责人: {st.owner}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </Panel>

        {/* Right Column: Detailed Backtest Report & Parameters */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Panel
            title={`${selectedStrategy.name} (v${selectedStrategy.version}) 回测报告与指标`}
            subtitle={`数据快照: ${backtestResult.dataSnapshotId} · ID: ${backtestResult.id}`}
            action={
              <button className="button button--secondary">
                <FileText size={14} />
                导出 Markdown 报告
              </button>
            }
          >
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>回测 Equity 累计收益曲线 (USD Demo Visual)</div>
              <Sparkline values={backtestResult.equityCurve} tone="positive" />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border-color)' }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>回测工程约束与滑点模型</div>
                <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6, color: 'var(--text-secondary)' }}>
                  <div>手 续 费 模型: <code className="cell-mono">{backtestResult.feeModel}</code></div>
                  <div>滑 点 损 耗: <code className="cell-mono">{backtestResult.slippageModel}</code></div>
                  <div>代码存储引用: <code className="cell-mono">{selectedStrategy.codeRef}</code></div>
                  <div>数据快照 Checksum: <code className="cell-mono">sha256:8f2a1b9c…</code></div>
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>策略核心参数配置 (Parameters Snapshot)</div>
                <div className="code-block">
                  {JSON.stringify(selectedStrategy.parameters || {}, null, 2)}
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="策略代码与因子定义快照 (Strategy Definition)" subtitle="不允许直接在控制台编辑策略代码；需提交 git commit">
            <div className="code-block">
              {`# Strategy: ${selectedStrategy.name} (${selectedStrategy.id})
# Version: ${selectedStrategy.version}
# Author: ${selectedStrategy.owner}

class TrendStrategy(QuantStrategyBase):
    def on_ticker(self, ticker: MarketTicker) -> List[OrderIntent]:
        fast_ma = self.compute_ma(ticker.symbol, period=10)
        slow_ma = self.compute_ma(ticker.symbol, period=20)
        
        if fast_ma > slow_ma * 1.002 and not self.has_position(ticker.symbol):
            return [self.create_buy_intent(symbol=ticker.symbol, quantity="0.012")]
        return []`}
            </div>
          </Panel>
        </div>
      </div>

      {/* New Backtest Task Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="新建策略回测任务 (POST /api/v1/research/backtests)"
        footer={
          <>
            <button className="button button--secondary" onClick={() => setIsModalOpen(false)}>取消</button>
            <button className="button button--primary" onClick={handleExecuteBacktest} disabled={isSubmittingBacktest}>
              <Play size={14} />
              {isSubmittingBacktest ? '正在提交回测算法 Engine...' : '提交 Paper 回测任务'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="form-group">
            <label>目标策略</label>
            <select
              className="form-select"
              value={selectedStrategy.id}
              onChange={(e) => {
                const found = strategies.find((s) => s.id === e.target.value)
                if (found) setSelectedStrategy(found)
              }}
            >
              {strategies.map((st) => (
                <option key={st.id} value={st.id}>{st.name} (v{st.version})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>历史行情数据快照 (data_snapshot)</label>
            <select className="form-select" value={formSnapshot} onChange={(e) => setFormSnapshot(e.target.value)}>
              <option value="snap_parquet_20260801_utc">snap_parquet_20260801_utc (2025-01 至 2026-08)</option>
              <option value="snap_parquet_20260101_utc">snap_parquet_20260101_utc (2024-01 至 2026-01)</option>
            </select>
          </div>
          <div className="form-group">
            <label>初始本金 (initial_capital USD)</label>
            <input className="form-input" type="text" value={formCapital} onChange={(e) => setFormCapital(e.target.value)} />
          </div>
          <div className="form-group">
            <label>手续费模型 (fee_model)</label>
            <input className="form-input" type="text" value={formFeeModel} onChange={(e) => setFormFeeModel(e.target.value)} />
          </div>
          <div className="form-group">
            <label>滑点模型 (slippage_model)</label>
            <input className="form-input" type="text" value={formSlippageModel} onChange={(e) => setFormSlippageModel(e.target.value)} />
          </div>
        </div>
      </Modal>
    </div>
  )
}
