import type { LucideIcon } from 'lucide-react'
import { Activity, Bell, Bot, CandlestickChart, ChevronDown, CircleHelp, Command, FlaskConical, LayoutDashboard, Menu, PanelLeftClose, Search, Settings2, ShieldCheck, Sparkles, WalletCards, Wifi } from 'lucide-react'
import { BarChart3, TrendingUp } from 'lucide-react'
import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import type { AsyncState } from '../types'
import { HeartbeatIndicator, IconButton, StatusBadge } from './Primitives'

interface AppStateContextType {
  globalState: AsyncState
  setGlobalState: (state: AsyncState) => void
  theme: 'liquid-glass' | 'liquid-glass-light' | 'institutional-dark'
  setTheme: (theme: 'liquid-glass' | 'liquid-glass-light' | 'institutional-dark') => void
}

export const AppStateContext = createContext<AppStateContextType>({
  globalState: 'success',
  setGlobalState: () => {},
  theme: 'liquid-glass',
  setTheme: () => {},
})

export const useAppState = () => useContext(AppStateContext)

interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  badge?: string
}

const navigation: { label: string; items: NavItem[] }[] = [
  { label: '工作台', items: [{ label: '总览', to: '/dashboard', icon: LayoutDashboard }] },
  {
    label: '交易与研究',
    items: [
      { label: '市场数据', to: '/market', icon: CandlestickChart, badge: 'LIVE' },
      { label: 'K线图表', to: '/kline', icon: TrendingUp },
      { label: '盈亏分析', to: '/analytics', icon: BarChart3 },
      { label: '量化研究', to: '/research', icon: FlaskConical },
      { label: '交易执行', to: '/execution', icon: WalletCards },
    ]
  },
  {
    label: '控制平面',
    items: [
      { label: '风控中心', to: '/risk', icon: ShieldCheck },
      { label: 'Agent 控制台', to: '/agents', icon: Bot, badge: '1 待审批' },
      { label: '系统设置', to: '/settings', icon: Settings2 },
    ]
  },
]

const titles: Record<string, string> = {
  '/dashboard': '总览 Dashboard',
  '/market': '市场数据 Market Data', '/kline': 'K线图表', '/analytics': '盈亏分析',
  '/research': '量化研究 Research',
  '/execution': '交易执行 Execution',
  '/risk': '风控中心 Risk Control',
  '/agents': 'Agent 控制台 Agents',
  '/settings': '系统设置 Settings'
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const title = titles[location.pathname] ?? '总览'
  const [globalState, setGlobalState] = useState<AsyncState>('success')
  const [showNotifications, setShowNotifications] = useState(false)
  
  // Theme state: defaults to 'liquid-glass'
  const themes: ('liquid-glass' | 'liquid-glass-light' | 'institutional-dark')[] = ['liquid-glass', 'liquid-glass-light', 'institutional-dark']
  const themeLabels: Record<string, string> = {
    'liquid-glass': '液态浮空玻璃',
    'liquid-glass-light': '珍珠白玻璃',
    'institutional-dark': '经典深炭'
  }

  const [theme, setThemeState] = useState<'liquid-glass' | 'liquid-glass-light' | 'institutional-dark'>(() => {
    return (localStorage.getItem('quant_theme') as any) || 'liquid-glass'
  })

  const setTheme = (newTheme: 'liquid-glass' | 'liquid-glass-light' | 'institutional-dark') => {
    setThemeState(newTheme)
    localStorage.setItem('quant_theme', newTheme)
    document.documentElement.setAttribute('data-theme', newTheme)
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const toggleTheme = () => {
    const currentIndex = themes.indexOf(theme)
    const nextTheme = themes[(currentIndex + 1) % themes.length]
    setTheme(nextTheme)
  }

  return (
    <AppStateContext.Provider value={{ globalState, setGlobalState, theme, setTheme }}>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">量</div>
            <div>
              <strong>量策 QUANT</strong>
              <span>ENTERPRISE AI TRADING</span>
            </div>
          </div>
          <div className="workspace-switcher">
            <div className="workspace-avatar">Q</div>
            <div className="workspace-name">
              <span>Quantum Labs</span>
              <small>主工作区 · 机构专区</small>
            </div>
            <ChevronDown size={15} />
          </div>

          <nav className="primary-nav">
            {navigation.map((group) => (
              <div className="nav-group" key={group.label}>
                <div className="nav-group__label">{group.label}</div>
                {group.items.map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}
                    >
                      <Icon size={17} strokeWidth={1.8} />
                      <span>{item.label}</span>
                      {item.badge && (
                        <em className={`nav-badge ${item.badge === 'LIVE' ? 'nav-badge--live' : item.badge === 'SIM' ? 'nav-badge--sim' : ''}`}>
                          {item.badge}
                        </em>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </nav>

          <div className="sidebar-bottom">
            <HeartbeatIndicator latencyMs={12} status="connected" />
            <div className="sidebar-links">
              <a href="#docs"><CircleHelp size={14} /> 架构文档</a>
              <a href="#shortcuts"><Command size={14} /> 快捷键</a>
            </div>
            <div className="user-profile">
              <div className="user-avatar">LM</div>
              <div>
                <b>林默</b>
                <small>量化平台主管 · Admin</small>
              </div>
              <ChevronDown size={14} />
            </div>
          </div>
        </aside>

        <div className="main-shell">
          <header className="topbar">
            <div className="topbar__left">
              <IconButton label="收起侧栏"><PanelLeftClose size={17} /></IconButton>
              <div className="breadcrumb">
                <span>控制台</span>
                <b>/</b>
                <strong>{title}</strong>
              </div>
            </div>

            <div className="topbar__right">
              {/* Liquid Glass Theme Switcher Pill */}
              <button
                className="theme-switch-pill"
                onClick={toggleTheme}
                title="点击循环切换：液态浮空玻璃 → 珍珠白玻璃 → 经典深炭"
              >
                <Sparkles size={13} />
                <span>{themeLabels[theme]}</span>
              </button>

              <div className="topbar-divider" />

              {import.meta.env.DEV && (
                <div className="state-controller" title="开发预览：切换当前页面的响应状态">
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', paddingLeft: 4 }}>状态:</span>
                  <button className={`state-btn ${globalState === 'success' ? 'state-btn--active' : ''}`} onClick={() => setGlobalState('success')}>就绪</button>
                  <button className={`state-btn ${globalState === 'loading' ? 'state-btn--active' : ''}`} onClick={() => setGlobalState('loading')}>加载中</button>
                  <button className={`state-btn ${globalState === 'empty' ? 'state-btn--active' : ''}`} onClick={() => setGlobalState('empty')}>空态</button>
                  <button className={`state-btn ${globalState === 'error' ? 'state-btn--active' : ''}`} onClick={() => setGlobalState('error')}>错误态</button>
                </div>
              )}

              <div className="search-box">
                <Search size={15} />
                <span>搜索策略、订单、风控规则...</span>
                <kbd>⌘ K</kbd>
              </div>

              <StatusBadge tone="positive">
                <Wifi size={12} />
                系统就绪 (Live)
              </StatusBadge>

              <IconButton label="通知" onClick={() => setShowNotifications(!showNotifications)}>
                <Bell size={17} />
                <i className="notification-dot" />
              </IconButton>
              <IconButton label="菜单"><Menu size={17} /></IconButton>
            </div>
          </header>

          <main className="main-content">
            {children}
          </main>

          <footer className="app-footer">
            <span>Quant Console v0.2.0</span>
            <span>API 契约 v1.0.0</span>
            <span>UTC+0 (Zulu Time)</span>
            <span className="footer-spacer" />
            <span>
              <Activity size={13} /> [生产级实时数据流 | Live Production]
            </span>
          </footer>
        </div>
      </div>
    </AppStateContext.Provider>
  )
}
