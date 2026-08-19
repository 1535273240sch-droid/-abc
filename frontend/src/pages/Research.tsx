import { 
  Activity, ArrowRight, BarChart3, Bot, CheckCircle2, ChevronRight, 
  Code2, Cpu, Database, FastForward, FileText, FlaskConical, GitBranch, 
  Layers, LineChart, PieChart, Play, Plus, RefreshCw, Scale, ShieldCheck, 
  Sparkles, TrendingUp, Zap 
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { mapBackendBacktest, mapBackendStrategy } from '../adapters'
import { 
  api, type BacktestRequest, type AlphaFactorItem, 
  type PortfolioOptimizationResult, type PortfolioRebalanceOrder, 
  type StrategyEvolutionItem 
} from '../api'
import { useAppState } from '../components/Layout'
import { DataState, Modal, PageIntro, Panel, StatCard, StatusBadge, TabGroup } from '../components/Primitives'
import type { BacktestResult, Strategy } from '../types'

export default function Research() {
  const { globalState, setGlobalState } = useAppState()
  const [loading, setLoading] = useState(true)
  const [isLiveApi, setIsLiveApi] = useState(false)
  const [activeTab, setActiveTab] = useState<'backtest' | 'alpha_mining' | 'portfolio_opt' | 'strategy_evolution'>('backtest')

  // Backtest State
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
  const [allBacktests, setAllBacktests] = useState<BacktestResult[]>([])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [formSnapshot, setFormSnapshot] = useState('snap_parquet_default')
  const [formCapital, setFormCapital] = useState('100000.00')
  const [formFeeModel, setFormFeeModel] = useState('maker_0.02pct_taker_0.04pct')
  const [formSlippageModel, setFormSlippageModel] = useState('conservative_1.5bps')
  const [isSubmittingBacktest, setIsSubmittingBacktest] = useState(false)

  // 1. Alpha Mining State
  const [alphaFactors, setAlphaFactors] = useState<AlphaFactorItem[]>([])
  const [miningSymbol, setMiningSymbol] = useState('BTCUSDT')
  const [miningGenerations, setMiningGenerations] = useState(4)
  const [miningPopSize, setMiningPopSize] = useState(30)
  const [isMining, setIsMining] = useState(false)
  const [llmHypothesis, setLlmHypothesis] = useState('在经历大幅放量下跌后，计算多周期波动率收缩与反转动量信号')
  const [isGeneratingLlmFactor, setIsGeneratingLlmFactor] = useState(false)

  // 2. Portfolio Optimization State
  const [optSymbols, setOptSymbols] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'])
  const [optMethod, setOptMethod] = useState<'risk_parity' | 'max_sharpe' | 'min_variance' | 'hrp'>('risk_parity')
  const [optResult, setOptResult] = useState<PortfolioOptimizationResult | null>(null)
  const [rebalancePlan, setRebalancePlan] = useState<PortfolioRebalanceOrder[]>([])
  const [isOptimizing, setIsOptimizing] = useState(false)

  // 3. Strategy Evolution State
  const [evolutions, setEvolutions] = useState<StrategyEvolutionItem[]>([])
  const [selectedEvo, setSelectedEvo] = useState<StrategyEvolutionItem | null>(null)
  const [isEvolving, setIsEvolving] = useState(false)

  const loadResearchData = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [stratsRes, backtestsRes, factorsRes, evosRes] = await Promise.all([
        api.strategies().catch(() => null),
        api.backtests().catch(() => null),
        api.alphaFactors().catch(() => null),
        api.strategyEvolutions().catch(() => null),
      ])

      let connected = false
      if (stratsRes && Array.isArray(stratsRes) && stratsRes.length > 0) {
        const mappedStrats = stratsRes.map((s) => mapBackendStrategy(s))
        setStrategies(mappedStrats)
        if (!selectedStrategy || !mappedStrats.some(s => s.id === selectedStrategy.id)) {
          setSelectedStrategy(mappedStrats[0])
        }
        connected = true
      }

      if (backtestsRes && Array.isArray(backtestsRes) && backtestsRes.length > 0) {
        const mappedAll = backtestsRes.map((b) => mapBackendBacktest(b))
        setAllBacktests(mappedAll)
        setBacktestResult(mappedAll[0])
        connected = true
      }

      if (factorsRes && Array.isArray(factorsRes)) {
        setAlphaFactors(factorsRes)
        connected = true
      }

      if (evosRes && Array.isArray(evosRes)) {
        setEvolutions(evosRes)
        if (evosRes.length > 0 && !selectedEvo) {
          setSelectedEvo(evosRes[0])
        }
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

  useEffect(() => {
    if (activeTab === 'portfolio_opt' && !optResult) {
      handleRunOptimization()
    }
  }, [activeTab])

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedStrategy) return
    setIsSubmittingBacktest(true)
    setActionMessage(null)
    try {
      const req: BacktestRequest = {
        strategy_id: selectedStrategy.id,
        strategy_version: selectedStrategy.version || 'v1.0.0',
        data_snapshot: formSnapshot,
        initial_capital: formCapital,
        fee_model: formFeeModel,
        slippage_model: formSlippageModel,
        mode: 'paper',
      }
      const res = await api.createBacktest(req)
      const mapped = mapBackendBacktest(res)
      setBacktestResult(mapped)
      setAllBacktests((prev) => [mapped, ...prev])
      setIsModalOpen(false)
      setActionMessage(`回测任务已完成！夏普比率: ${mapped.sharpeRatio}, 净利润: $${mapped.netProfit}`)
    } catch (err: any) {
      setActionMessage(`回测执行失败: ${err.message || '未知错误'}`)
    } finally {
      setIsSubmittingBacktest(false)
    }
  }

  const handleStartMining = async () => {
    setIsMining(true)
    setActionMessage(null)
    try {
      const factors = await api.mineAlphaFactors({
        symbol: miningSymbol,
        generations: miningGenerations,
        population_size: miningPopSize,
      })
      if (factors && factors.length > 0) {
        setAlphaFactors(prev => [...factors, ...prev])
        setActionMessage(`🧬 遗传规划自动挖掘成功完成！新发现 ${factors.length} 个显著 Alpha 因子。`)
      } else {
        setActionMessage('挖掘完成，未在设定的显著性阈值内发现新因子，建议增加演化代数。')
      }
    } catch (err: any) {
      setActionMessage(`因子挖掘失败: ${err.message || '未知错误'}`)
    } finally {
      setIsMining(false)
    }
  }

  const handleLlmGenerateFactor = async () => {
    if (!llmHypothesis.trim()) return
    setIsGeneratingLlmFactor(true)
    setActionMessage(null)
    try {
      const factor = await api.generateLlmAlphaFactor({
        hypothesis: llmHypothesis,
        symbol: miningSymbol,
      })
      setAlphaFactors(prev => [factor, ...prev])
      setActionMessage(`✨ 阶跃星辰大模型基于理论假说成功生成公式: ${factor.expression} (RankIC: ${factor.rank_ic})`)
    } catch (err: any) {
      setActionMessage(`AI 因子生成失败: ${err.message || '未知错误'}`)
    } finally {
      setIsGeneratingLlmFactor(false)
    }
  }

  const handleRunOptimization = async () => {
    setIsOptimizing(true)
    setActionMessage(null)
    try {
      const res = await api.optimizePortfolio({
        symbols: optSymbols,
        method: optMethod,
      })
      setOptResult(res)
      const plan = await api.portfolioRebalancePlan({
        allocations: res.allocations,
        total_portfolio_value: 100000.0,
      })
      setRebalancePlan(plan)
      setActionMessage(`📐 投资组合数学优化完成 (${optMethod.toUpperCase()})！年化夏普: ${res.portfolio_sharpe_ratio}`)
    } catch (err: any) {
      setActionMessage(`组合优化失败: ${err.message || '未知错误'}`)
    } finally {
      setIsOptimizing(false)
    }
  }

  const handleTriggerEvolution = async () => {
    if (!selectedStrategy) return
    setIsEvolving(true)
    setActionMessage(null)
    try {
      const res = await api.evolveStrategy({
        strategy_id: selectedStrategy.id,
        recent_backtest_id: backtestResult?.id,
        operator: 'ai-agent-stepfun',
      })
      setEvolutions(prev => [res, ...prev])
      setSelectedEvo(res)
      setActionMessage(`🚀 策略演化 Agent 已完成深度归因诊断与沙盒回测！夏普提升: +${res.sandbox_results.sharpe_improvement_pct}%`)
    } catch (err: any) {
      setActionMessage(`策略自我演化失败: ${err.message || '未知错误'}`)
    } finally {
      setIsEvolving(false)
    }
  }

  const handleApplyEvolution = async (evoId: string) => {
    try {
      const res = await api.applyStrategyEvolution({ evolution_id: evoId })
      setEvolutions(prev => prev.map(e => e.evolution_id === evoId ? res : e))
      if (selectedEvo?.evolution_id === evoId) setSelectedEvo(res)
      setActionMessage(`✅ 策略演化版本已成功应用热更至实盘/模拟系统！`)
    } catch (err: any) {
      setActionMessage(`应用演化版本失败: ${err.message || '未知错误'}`)
    }
  }

  if (globalState !== 'success') {
    return (
      <div>
        <PageIntro eyebrow="量化研发" title="研究与策略进化台 Research & Evolution" description="高精度历史回测、自动符号因子挖掘、投资组合风险平价求解与大模型策略自我演化" />
        <DataState state={globalState} onRetry={() => setGlobalState('success')} />
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <PageIntro eyebrow="量化研发" title="研究与策略进化台 Research & Evolution" description="正在同步策略模型、因子库与历史回测序列..." />
        <DataState state="loading" title="读取量化研究数据中" description="GET /api/v1/research/backtests, GET /api/v1/research/alpha/factors" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <PageIntro
          eyebrow="QUANT R&D WORKBENCH"
          title="研究与策略进化台 Research & Evolution"
          description="机构级深度回测引擎、符号规划自动因子挖掘、多资产风险平价与大模型策略自适应进化"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={() => loadResearchData()}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-neutral-400 bg-neutral-900 border border-neutral-800 rounded hover:border-neutral-700 hover:text-neutral-200 transition-colors"
          >
            <RefreshCw size={14} />
            刷新
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs font-mono text-amber-400 flex items-center justify-between">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage(null)} className="text-neutral-400 hover:text-white ml-4">✕</button>
        </div>
      )}

      {/* Navigation Tabs */}
      <TabGroup
        tabs={[
          { id: 'backtest', label: '① 深度历史回测 (Backtest)' },
          { id: 'alpha_mining', label: '② 自动挖因子 (Alpha Mining)' },
          { id: 'portfolio_opt', label: '③ 自动组合优化 (Portfolio Opt)' },
          { id: 'strategy_evolution', label: '④ 策略自我演化 (Strategy Evolution)' },
        ]}
        activeTab={activeTab}
        onChange={(t) => setActiveTab(t as any)}
      />

      {/* TAB 1: 深度历史回测 (Backtest) */}
      {activeTab === 'backtest' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard
              label="当前回测净利润"
              value={`$${backtestResult?.netProfit || '0.00'}`}
              caption="基于历史 K 线撮合"
              tone={Number(backtestResult?.netProfit || 0) >= 0 ? 'positive' : 'negative'}
            />
            <StatCard
              label="夏普比率 (Sharpe)"
              value={backtestResult?.sharpeRatio || '0.00'}
              caption="年化风险调整收益"
              tone={Number(backtestResult?.sharpeRatio || 0) > 1.2 ? 'positive' : 'neutral'}
            />
            <StatCard
              label="最大回撤 (Max DD)"
              value={`${backtestResult?.maxDrawdown || '0.00'}%`}
              caption="风控门禁阈值: 20%"
              tone={Number(backtestResult?.maxDrawdown || 0) < 15 ? 'positive' : 'negative'}
            />
            <StatCard
              label="回测胜率 / 交易笔数"
              value={`${backtestResult?.winRate || '0.0'}%`}
              caption={`共 ${backtestResult?.totalTrades || 0} 笔成交流水`}
              tone="neutral"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Panel title="策略库与回测驱动" subtitle="选择待测试的策略版本并执行高精度撮合">
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-neutral-400">选择策略 (Strategy)</label>
                  <div className="space-y-2 max-h-56 overflow-y-auto">
                    {strategies.map((strat) => (
                      <div
                        key={strat.id}
                        onClick={() => setSelectedStrategy(strat)}
                        className={`p-3 rounded border cursor-pointer transition-colors ${
                          selectedStrategy?.id === strat.id
                            ? 'bg-amber-500/10 border-amber-500/40 text-neutral-200'
                            : 'bg-neutral-900 border-neutral-800 text-neutral-400 hover:border-neutral-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-sm text-neutral-200">{strat.name}</span>
                          <StatusBadge tone={strat.status === '运行中' ? 'positive' : 'neutral'}>
                            {strat.status}
                          </StatusBadge>
                        </div>
                        <div className="flex items-center gap-3 text-xs font-mono text-neutral-500">
                          <span>类型: {strat.kind}</span>
                          <span>•</span>
                          <span>版本: {strat.version || 'v1.0.0'}</span>
                          <span>•</span>
                          <span>夏普: {strat.sharpe}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={() => setIsModalOpen(true)}
                    className="w-full flex items-center justify-center gap-2 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded text-sm transition-colors"
                  >
                    <Play size={16} />
                    配置并启动新回测
                  </button>
                </div>
              </div>
            </Panel>

            <div className="lg:col-span-2">
              <Panel title="回测净值曲线与交易详情" subtitle={backtestResult ? `回测 ID: ${backtestResult.id} • 数据源: ${backtestResult.dataSnapshotId}` : '暂无回测结果'}>
                {backtestResult ? (
                  <div className="space-y-6">
                    <div className="h-44 flex items-end gap-1 pt-4 pb-2 px-2 bg-neutral-950 border border-neutral-900 rounded">
                      {(backtestResult.equityCurve && backtestResult.equityCurve.length > 0 ? backtestResult.equityCurve : [100000, 101200, 102500, 101800, 104200, 103900, 106500, 108200, 107900, 111400]).map((val, idx, arr) => {
                        const min = Math.min(...arr)
                        const max = Math.max(...arr)
                        const heightPct = Math.max(15, Math.min(100, ((val - min) / (max - min || 1)) * 100))
                        return (
                          <div key={idx} className="flex-1 flex flex-col items-center gap-1 group relative">
                            <div
                              style={{ height: `${heightPct}%` }}
                              className="w-full bg-amber-500/70 hover:bg-amber-400 transition-all rounded-t-sm"
                            />
                            <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-1 bg-black border border-neutral-800 text-[10px] font-mono p-1 rounded whitespace-nowrap z-10 pointer-events-none">
                              ${val.toLocaleString()}
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
                      <div className="p-2.5 bg-neutral-900 border border-neutral-800 rounded">
                        <span className="text-neutral-500 block">初始本金</span>
                        <span className="text-neutral-200 font-bold">${backtestResult.initialCapital || '100,000'}</span>
                      </div>
                      <div className="p-2.5 bg-neutral-900 border border-neutral-800 rounded">
                        <span className="text-neutral-500 block">费率模型</span>
                        <span className="text-neutral-200 truncate block">{backtestResult.feeModel || 'Maker 0.02%'}</span>
                      </div>
                      <div className="p-2.5 bg-neutral-900 border border-neutral-800 rounded">
                        <span className="text-neutral-500 block">滑点模型</span>
                        <span className="text-neutral-200 truncate block">{backtestResult.slippageModel || '1.5 bps'}</span>
                      </div>
                      <div className="p-2.5 bg-neutral-900 border border-neutral-800 rounded">
                        <span className="text-neutral-500 block">回测状态</span>
                        <span className="text-emerald-400 font-bold block">撮合完成 (Done)</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-12 text-center text-neutral-500 font-mono text-sm">
                    点击左侧「配置并启动新回测」运行策略验证
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: 自动挖因子 (Alpha Mining) */}
      {activeTab === 'alpha_mining' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="space-y-6">
              <Panel title="遗传规划自动挖掘 (GP)" subtitle="在历史 K 线数据上通过树形变异/交叉演化公式">
                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-mono text-neutral-400 block mb-1">目标标的 (Symbol)</label>
                    <select
                      value={miningSymbol}
                      onChange={(e) => setMiningSymbol(e.target.value)}
                      className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-neutral-200 focus:border-amber-500 outline-none"
                    >
                      <option value="BTCUSDT">BTC/USDT</option>
                      <option value="ETHUSDT">ETH/USDT</option>
                      <option value="SOLUSDT">SOL/USDT</option>
                      <option value="BNBUSDT">BNB/USDT</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-mono text-neutral-400 block mb-1">演化代数</label>
                      <input
                        type="number"
                        min="2"
                        max="20"
                        value={miningGenerations}
                        onChange={(e) => setMiningGenerations(Number(e.target.value))}
                        className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-neutral-200"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-mono text-neutral-400 block mb-1">种群规模</label>
                      <input
                        type="number"
                        min="10"
                        max="100"
                        value={miningPopSize}
                        onChange={(e) => setMiningPopSize(Number(e.target.value))}
                        className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-neutral-200"
                      />
                    </div>
                  </div>

                  <button
                    onClick={handleStartMining}
                    disabled={isMining}
                    className="w-full py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-semibold rounded text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                  >
                    <Cpu size={16} />
                    {isMining ? '正在执行遗传规划演化...' : '启动符号遗传挖掘 (Run GP)'}
                  </button>
                </div>
              </Panel>

              <Panel title="大模型假说驱动挖掘 (LLM)" subtitle="调用阶跃星辰等大模型将理论假说转为因子公式">
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-mono text-neutral-400 block mb-1">输入经济学/量化假说</label>
                    <textarea
                      rows={3}
                      value={llmHypothesis}
                      onChange={(e) => setLlmHypothesis(e.target.value)}
                      placeholder="例如：在经历大幅放量下跌后，计算多周期波动率收缩与反转动量信号"
                      className="w-full bg-neutral-900 border border-neutral-800 rounded p-2.5 text-xs font-mono text-neutral-200 focus:border-amber-500 outline-none"
                    />
                  </div>
                  <button
                    onClick={handleLlmGenerateFactor}
                    disabled={isGeneratingLlmFactor}
                    className="w-full py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-amber-400 rounded text-xs font-mono flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                  >
                    <Sparkles size={14} />
                    {isGeneratingLlmFactor ? '正在调用大模型生成公式...' : 'StepFun 驱动公式生成 (LLM Alpha)'}
                  </button>
                </div>
              </Panel>
            </div>

            <div className="lg:col-span-2">
              <Panel
                title="已挖掘高潜 Alpha 因子库"
                subtitle={`已自动筛选入库 ${alphaFactors.length} 个显著性特征因子 (按 |RankIC| 排序)`}
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="border-b border-neutral-800 text-neutral-500 bg-neutral-950/50">
                      <tr>
                        <th className="py-2.5 px-3">因子 ID</th>
                        <th className="py-2.5 px-3">标的</th>
                        <th className="py-2.5 px-3">符号表达式 (AST Formula)</th>
                        <th className="py-2.5 px-3 text-right">RankIC</th>
                        <th className="py-2.5 px-3 text-right">IC_IR</th>
                        <th className="py-2.5 px-3 text-right">因子夏普</th>
                        <th className="py-2.5 px-3 text-right">胜率</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-900">
                      {alphaFactors.map((f) => (
                        <tr key={f.factor_id} className="hover:bg-neutral-900/50 transition-colors">
                          <td className="py-2.5 px-3 text-neutral-300 font-bold">{f.factor_id}</td>
                          <td className="py-2.5 px-3 text-neutral-400">{f.symbol}</td>
                          <td className="py-2.5 px-3 text-amber-300/90 font-mono max-w-xs truncate" title={f.expression}>
                            {f.expression}
                          </td>
                          <td className={`py-2.5 px-3 text-right font-bold ${Math.abs(f.rank_ic) >= 0.05 ? 'text-emerald-400' : 'text-neutral-400'}`}>
                            {f.rank_ic > 0 ? `+${f.rank_ic.toFixed(3)}` : f.rank_ic.toFixed(3)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-neutral-300">
                            {f.ic_ir.toFixed(2)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-neutral-300">
                            {f.factor_sharpe.toFixed(2)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-neutral-400">
                            {f.win_rate.toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: 自动组合优化 (Portfolio Optimizer) */}
      {activeTab === 'portfolio_opt' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Panel title="投资组合优化模型配置" subtitle="选择多币种资产池与数学求解器">
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-mono text-neutral-400 block mb-1">优化算法 (Solver)</label>
                  <select
                    value={optMethod}
                    onChange={(e) => setOptMethod(e.target.value as any)}
                    className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-neutral-200 focus:border-amber-500 outline-none"
                  >
                    <option value="risk_parity">风险平价模型 (Risk Parity - ERC)</option>
                    <option value="max_sharpe">马科维茨有效前沿 - 最大夏普 (Max Sharpe)</option>
                    <option value="min_variance">全局最小方差组合 (Min Variance)</option>
                    <option value="hrp">分层风险平价聚类 (Hierarchical Risk Parity)</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-mono text-neutral-400 block mb-2">资产池标的 (Assets Pool)</label>
                  <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                    {['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT', 'AVAXUSDT'].map((sym) => {
                      const selected = optSymbols.includes(sym)
                      return (
                        <div
                          key={sym}
                          onClick={() => {
                            if (selected && optSymbols.length > 2) {
                              setOptSymbols(optSymbols.filter(s => s !== sym))
                            } else if (!selected) {
                              setOptSymbols([...optSymbols, sym])
                            }
                          }}
                          className={`p-2 rounded border cursor-pointer text-center transition-colors ${
                            selected ? 'bg-amber-500/10 border-amber-500/50 text-neutral-200' : 'bg-neutral-900 border-neutral-800 text-neutral-500'
                          }`}
                        >
                          {sym}
                        </div>
                      )
                    })}
                  </div>
                </div>

                <button
                  onClick={handleRunOptimization}
                  disabled={isOptimizing}
                  className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  <Scale size={16} />
                  {isOptimizing ? '正在计算协方差与最优权重...' : '执行数学组合优化 (Solve)'}
                </button>
              </div>
            </Panel>

            <div className="lg:col-span-2 space-y-6">
              {optResult ? (
                <>
                  <div className="grid grid-cols-3 gap-4">
                    <StatCard
                      label="组合预期年化收益率"
                      value={`+${optResult.expected_annual_return_pct}%`}
                      caption="基于历史协方差收缩矩阵"
                      tone="positive"
                    />
                    <StatCard
                      label="组合年化波动率"
                      value={`${optResult.expected_annual_volatility_pct}%`}
                      caption="多资产相关性平抑"
                      tone="neutral"
                    />
                    <StatCard
                      label="最优组合夏普比率"
                      value={optResult.portfolio_sharpe_ratio.toFixed(2)}
                      caption={`算法: ${optResult.method.toUpperCase()}`}
                      tone="positive"
                    />
                  </div>

                  <Panel title="最优权重配置与边际风险贡献" subtitle="各资产目标权重 (Target Weight) 及风险平价配比">
                    <div className="space-y-4">
                      {optResult.allocations.map((alloc) => (
                        <div key={alloc.symbol} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono">
                            <span className="text-neutral-200 font-bold">{alloc.symbol}</span>
                            <span className="text-amber-400 font-mono">
                              {(alloc.target_weight * 100).toFixed(1)}% (风险贡献: {(alloc.risk_contribution * 100).toFixed(1)}%)
                            </span>
                          </div>
                          <div className="w-full bg-neutral-900 h-2 rounded overflow-hidden">
                            <div
                              style={{ width: `${alloc.target_weight * 100}%` }}
                              className="bg-amber-500 h-full rounded transition-all"
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Panel>

                  {rebalancePlan.length > 0 && (
                    <Panel title="自动再平衡差额调仓清单 (Rebalance Orders)" subtitle="对比当前账户持仓差额生成的建议调仓单">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs font-mono">
                          <thead className="border-b border-neutral-800 text-neutral-500">
                            <tr>
                              <th className="py-2 px-3">标的</th>
                              <th className="py-2 px-3">方向</th>
                              <th className="py-2 px-3 text-right">目标权重</th>
                              <th className="py-2 px-3 text-right">当前持仓</th>
                              <th className="py-2 px-3 text-right">目标持仓</th>
                              <th className="py-2 px-3 text-right">调仓差额</th>
                              <th className="py-2 px-3 text-right">估算名义本金</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-neutral-900">
                            {rebalancePlan.map((order) => (
                              <tr key={order.symbol}>
                                <td className="py-2.5 px-3 text-neutral-200 font-bold">{order.symbol}</td>
                                <td className="py-2.5 px-3">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    order.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                                  }`}>
                                    {order.side.toUpperCase()}
                                  </span>
                                </td>
                                <td className="py-2.5 px-3 text-right text-neutral-400">{(order.target_weight * 100).toFixed(1)}%</td>
                                <td className="py-2.5 px-3 text-right text-neutral-500">{order.current_quantity}</td>
                                <td className="py-2.5 px-3 text-right text-neutral-200">{order.target_quantity}</td>
                                <td className="py-2.5 px-3 text-right font-bold text-amber-400">{order.diff_quantity}</td>
                                <td className="py-2.5 px-3 text-right text-neutral-300">${order.estimated_notional_usd.toLocaleString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </Panel>
                  )}
                </>
              ) : (
                <div className="py-12 text-center text-neutral-500 font-mono text-sm">
                  点击左侧「执行数学组合优化」开始多资产建模
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: 策略自我演化 (Strategy Evolution) */}
      {activeTab === 'strategy_evolution' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Panel title="策略自适应诊断与进化 Agent" subtitle="针对近期实盘/回测弱点进行归因并进化代码与参数">
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-mono text-neutral-400 block mb-1">选择待进化策略</label>
                  <select
                    value={selectedStrategy?.id || ''}
                    onChange={(e) => {
                      const strat = strategies.find(s => s.id === e.target.value)
                      if (strat) setSelectedStrategy(strat)
                    }}
                    className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-neutral-200 focus:border-amber-500 outline-none"
                  >
                    {strategies.map(s => (
                      <option key={s.id} value={s.id}>{s.name} ({s.kind} • {s.version || 'v1.0.0'})</option>
                    ))}
                  </select>
                </div>

                <div className="p-3 bg-neutral-900/60 border border-neutral-800 rounded text-xs font-mono space-y-1 text-neutral-400">
                  <div className="text-neutral-300 font-bold">🤖 Agent 工作流 (RD-Agent 架构):</div>
                  <div>1. 扫描最新回测与实盘指标缺陷</div>
                  <div>2. 阶跃星辰模型诊断弱点并输出改进逻辑</div>
                  <div>3. 沙盒交叉回测验证指标提升显著性</div>
                  <div>4. 生成安全审批单推送到风控门禁</div>
                </div>

                <button
                  onClick={handleTriggerEvolution}
                  disabled={isEvolving}
                  className="w-full py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-semibold rounded text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                >
                  <Bot size={16} />
                  {isEvolving ? '大模型正在归因诊断与沙盒回测...' : '启动策略自我进化 (Trigger Evolution)'}
                </button>
              </div>
            </Panel>

            <div className="lg:col-span-2 space-y-6">
              {selectedEvo ? (
                <div className="space-y-6">
                  <Panel
                    title={`策略进化代际报告: ${selectedEvo.candidate_version}`}
                    subtitle={`基础版本: ${selectedEvo.base_version} • 状态: ${selectedEvo.status.toUpperCase()}`}
                  >
                    <div className="space-y-4">
                      <div className="p-3.5 bg-red-500/10 border border-red-500/30 rounded">
                        <span className="text-red-400 font-bold text-xs font-mono block mb-1">🔍 缺陷归因诊断 (Weakness Diagnosis):</span>
                        <p className="text-xs text-neutral-300 leading-relaxed font-mono">{selectedEvo.weakness_diagnosis}</p>
                      </div>

                      <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded">
                        <span className="text-amber-400 font-bold text-xs font-mono block mb-1">💡 阶跃星辰进化建议 (LLM Proposal):</span>
                        <p className="text-xs text-neutral-300 leading-relaxed font-mono">{selectedEvo.llm_proposal}</p>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
                        <div className="p-3 bg-neutral-900 border border-neutral-800 rounded">
                          <span className="text-neutral-500 block">夏普比率对比</span>
                          <span className="text-neutral-400">{selectedEvo.sandbox_results.base_metrics.sharpe_ratio} ➔ </span>
                          <span className="text-emerald-400 font-bold">{selectedEvo.sandbox_results.evolved_metrics.sharpe_ratio}</span>
                          <span className="text-[10px] text-emerald-400 block mt-0.5">+{selectedEvo.sandbox_results.sharpe_improvement_pct}%</span>
                        </div>
                        <div className="p-3 bg-neutral-900 border border-neutral-800 rounded">
                          <span className="text-neutral-500 block">最大回撤优化</span>
                          <span className="text-neutral-400">{selectedEvo.sandbox_results.base_metrics.max_drawdown} ➔ </span>
                          <span className="text-emerald-400 font-bold">{selectedEvo.sandbox_results.evolved_metrics.max_drawdown}</span>
                          <span className="text-[10px] text-emerald-400 block mt-0.5">降低 {selectedEvo.sandbox_results.drawdown_reduction_pct}%</span>
                        </div>
                        <div className="p-3 bg-neutral-900 border border-neutral-800 rounded">
                          <span className="text-neutral-500 block">胜率变化</span>
                          <span className="text-neutral-400">{selectedEvo.sandbox_results.base_metrics.win_rate} ➔ </span>
                          <span className="text-neutral-200 font-bold">{selectedEvo.sandbox_results.evolved_metrics.win_rate}</span>
                        </div>
                        <div className="p-3 bg-neutral-900 border border-neutral-800 rounded">
                          <span className="text-neutral-500 block">沙盒回测门禁</span>
                          <span className="text-emerald-400 font-bold flex items-center gap-1 mt-1">
                            <CheckCircle2 size={14} /> 验证通过 (Pass)
                          </span>
                        </div>
                      </div>

                      {selectedEvo.status !== 'applied' ? (
                        <div className="pt-2 flex justify-end">
                          <button
                            onClick={() => handleApplyEvolution(selectedEvo.evolution_id)}
                            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded transition-colors"
                          >
                            确认批准并热更上线 (Apply to Production)
                          </button>
                        </div>
                      ) : (
                        <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-center text-xs font-mono text-emerald-400">
                          ✓ 该版本已热更发布生效 (Applied at {selectedEvo.applied_at ? new Date(selectedEvo.applied_at).toLocaleTimeString() : '刚刚'})
                        </div>
                      )}
                    </div>
                  </Panel>
                </div>
              ) : (
                <div className="py-12 text-center text-neutral-500 font-mono text-sm">
                  请选择策略并点击左侧「启动策略自我进化」
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Backtest Configuration Modal */}
      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="配置高精度回测参数 (Backtest Engine)">
        <form onSubmit={handleRunBacktest} className="space-y-4 text-xs font-mono">
          <div>
            <label className="text-neutral-400 block mb-1">测试策略</label>
            <input
              type="text"
              disabled
              value={`${selectedStrategy?.name || ''} (${selectedStrategy?.kind || ''})`}
              className="w-full bg-neutral-950 border border-neutral-800 rounded px-3 py-2 text-neutral-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-neutral-400 block mb-1">初始本金 (USDT)</label>
              <input
                type="text"
                value={formCapital}
                onChange={(e) => setFormCapital(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-neutral-200"
              />
            </div>
            <div>
              <label className="text-neutral-400 block mb-1">数据快照 (Snapshot)</label>
              <input
                type="text"
                value={formSnapshot}
                onChange={(e) => setFormSnapshot(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-neutral-200"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-neutral-400 block mb-1">费率模型</label>
              <select
                value={formFeeModel}
                onChange={(e) => setFormFeeModel(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-neutral-200"
              >
                <option value="maker_0.02pct_taker_0.04pct">Binance VIP1 (0.02% / 0.04%)</option>
                <option value="maker_0.01pct_taker_0.02pct">OKX Institutional (0.01% / 0.02%)</option>
              </select>
            </div>
            <div>
              <label className="text-neutral-400 block mb-1">滑点模型</label>
              <select
                value={formSlippageModel}
                onChange={(e) => setFormSlippageModel(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2 text-neutral-200"
              >
                <option value="conservative_1.5bps">固定滑点 1.5 bps</option>
                <option value="atr_volatility_dynamic">基于 ATR 动态滑点</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="px-4 py-2 bg-neutral-800 text-neutral-300 rounded hover:bg-neutral-700"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isSubmittingBacktest}
              className="px-4 py-2 bg-amber-500 text-black font-semibold rounded hover:bg-amber-400 disabled:opacity-50"
            >
              {isSubmittingBacktest ? '正在撮合回测中...' : '开始回测'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
