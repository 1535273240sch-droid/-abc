import type { ReactNode } from 'react'
import { AlertCircle, Check, Inbox, LoaderCircle, Minus, RefreshCw, X } from 'lucide-react'
import type { AsyncState, OrderBookData, Tone } from '../types'

export function MockLabel({ label = '模拟数据 · Paper' }: { label?: string }) {
  return (
    <span className="mock-tag" title="当前展示数据由模拟引擎提供，未连接真实交易所下单">
      {label}
    </span>
  )
}

export function PageIntro({
  eyebrow,
  title,
  description,
  action,
  dataSource = 'mock'
}: {
  eyebrow: string
  title: string
  description: string
  action?: ReactNode
  dataSource?: 'mock' | 'mixed' | 'api'
}) {
  const sourceLabel = dataSource === 'api' ? '后端 API · Paper' : dataSource === 'mixed' ? '混合数据 · API + mock' : '模拟数据 · Paper'
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow">
          {eyebrow}
          <MockLabel label={sourceLabel} />
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-intro__action">{action}</div>}
    </div>
  )
}

export function Panel({
  title,
  subtitle,
  action,
  children,
  className = ''
}: {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel__header">
        <div>
          <h2>{title}</h2>
          {subtitle && <span>{subtitle}</span>}
        </div>
        {action && <div className="panel__action">{action}</div>}
      </div>
      {children}
    </section>
  )
}

export function StatusBadge({
  children,
  tone = 'neutral',
  dot = true
}: {
  children: ReactNode
  tone?: Tone
  dot?: boolean
}) {
  return (
    <span className={`status-badge status-badge--${tone}`}>
      {dot && <i className="status-dot" />}
      {children}
    </span>
  )
}

export function DataState({
  state,
  title,
  description,
  onRetry
}: {
  state: AsyncState
  title?: string
  description?: string
  onRetry?: () => void
}) {
  const content = {
    loading: {
      icon: <LoaderCircle className="spin" size={22} />,
      title: title ?? '正在读取核心数据',
      description: description ?? '正在向系统 API 网关发起数据获取请求...'
    },
    empty: {
      icon: <Inbox size={22} />,
      title: title ?? '暂无匹配数据',
      description: description ?? '当前筛选条件或检索粒度下没有相关记录'
    },
    error: {
      icon: <AlertCircle size={22} />,
      title: title ?? '数据读取异常',
      description: description ?? '网络超时或服务端响应 503，请检查服务状态后重试'
    },
    success: {
      icon: <Check size={22} />,
      title: title ?? '数据已就绪',
      description: description ?? ''
    }
  }[state]

  return (
    <div className={`data-state data-state--${state}`}>
      <div className="data-state__icon">{content.icon}</div>
      <div>
        <strong>{content.title}</strong>
        {content.description && <p>{content.description}</p>}
      </div>
      {state === 'error' && onRetry && (
        <button className="button button--secondary" onClick={onRetry}>
          <RefreshCw size={13} />
          重试读取
        </button>
      )}
    </div>
  )
}

export function StatCard({
  label,
  value,
  change,
  caption,
  tone = 'neutral',
  icon,
  className = ''
}: {
  label: string
  value: string
  change?: string
  caption?: string
  tone?: Tone
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={`stat-card ${className}`}>
      <div className="stat-card__top">
        <span>{label}</span>
        {icon && <span className="stat-card__icon">{icon}</span>}
      </div>
      <div className="stat-card__value">{value}</div>
      {(change || caption) && (
        <div className="stat-card__meta">
          {change && <span className={`text-${tone}`}>{change}</span>}
          {caption && <span>{caption}</span>}
        </div>
      )}
    </div>
  )
}

export function Sparkline({
  values,
  tone = 'neutral',
  className = ''
}: {
  values: number[]
  tone?: Tone
  className?: string
}) {
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min || 1
  const points = values
    .map((val, idx) => `${(idx / (values.length - 1)) * 100},${36 - ((val - min) / range) * 30}`)
    .join(' ')
  return (
    <svg className={`sparkline sparkline--${tone} ${className}`} viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function ProgressBar({
  value,
  tone = 'accent',
  label,
  detail
}: {
  value: number
  tone?: Tone
  label?: string
  detail?: string
}) {
  return (
    <div className="progress-wrap">
      {(label || detail) && (
        <div className="progress-label">
          <span>{label}</span>
          <b>{detail}</b>
        </div>
      )}
      <div className="progress-track">
        <div className={`progress-fill progress-fill--${tone}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  )
}

export function OrderbookViewer({ data }: { data: OrderBookData }) {
  return (
    <div className="orderbook-grid">
      <div>
        <div style={{ color: 'var(--color-negative)', fontWeight: 600, marginBottom: 6 }}>卖盘 (Asks)</div>
        {data.asks.map((item, i) => (
          <div className="orderbook-row" key={i}>
            <div className="orderbook-bg orderbook-bg--ask" style={{ width: `${item.depthPercent}%` }} />
            <span className="text-negative">{item.price}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{item.amount}</span>
          </div>
        ))}
      </div>
      <div>
        <div style={{ color: 'var(--color-positive)', fontWeight: 600, marginBottom: 6 }}>买盘 (Bids)</div>
        {data.bids.map((item, i) => (
          <div className="orderbook-row" key={i}>
            <div className="orderbook-bg orderbook-bg--bid" style={{ width: `${item.depthPercent}%` }} />
            <span className="text-positive">{item.price}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{item.amount}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ResultMark({ result }: { result: '通过' | '观察' | '阻断' }) {
  const tone = result === '通过' ? 'positive' : result === '观察' ? 'warning' : 'negative'
  const Icon = result === '通过' ? Check : result === '观察' ? Minus : AlertCircle
  return (
    <StatusBadge tone={tone}>
      <Icon size={12} />
      {result}
    </StatusBadge>
  )
}

export function PreflightBadge({ decision }: { decision: 'PASSED' | 'REJECTED' | 'WARNING' }) {
  const tone = decision === 'PASSED' ? 'positive' : decision === 'WARNING' ? 'warning' : 'negative'
  return (
    <StatusBadge tone={tone}>
      {decision === 'PASSED' ? '放行 (PASSED)' : decision === 'WARNING' ? '观察放行' : '风控阻断 (REJECTED)'}
    </StatusBadge>
  )
}

export function TabGroup({
  tabs,
  activeTab,
  onChange
}: {
  tabs: { id: string; label: string; badge?: string }[]
  activeTab: string
  onChange: (id: string) => void
}) {
  return (
    <div className="tab-group">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`tab-item ${activeTab === tab.id ? 'tab-item--active' : ''}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.badge && <span className="nav-badge" style={{ marginLeft: 6 }}>{tab.badge}</span>}
        </button>
      ))}
    </div>
  )
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer
}: {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
}) {
  if (!isOpen) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="icon-button" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

export function IconButton({ label, children, onClick }: { label: string; children: ReactNode; onClick?: () => void }) {
  return (
    <button className="icon-button" aria-label={label} title={label} onClick={onClick}>
      {children}
    </button>
  )
}
