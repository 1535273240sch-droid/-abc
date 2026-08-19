import type { ReactNode } from 'react'

export interface HeartbeatIndicatorProps {
  /** 实时网络延迟 (ms)，若为 null/undefined 表示离线或探测中 */
  latencyMs?: number | null
  /** 微服务/适配器运行状态 */
  status?: 'connected' | 'degraded' | 'disconnected' | 'idle'
  /** 主标题 (默认: "系统运行正常") */
  label?: string
  /** 副标题 (默认自适应: "心跳响应 · 12ms (UTC)") */
  sublabel?: string
  /** 是否紧凑单行模式 (用于顶部栏或表格单元格) */
  compact?: boolean
  /** 是否展示毫秒数字 */
  showLatency?: boolean
  /** 自定义外层 CSS 类 */
  className?: string
  /** 自定义提示信息 */
  tooltip?: string
  /** 点击回调事件 */
  onClick?: () => void
}

/**
 * 根据延迟与状态计算色调:
 * - latency < 50ms 或 connected -> positive (翡翠绿 #00C087)
 * - 50ms <= latency < 200ms 或 degraded -> warning (琥珀黄 #FAAD14 / 彭博金 #D4AF37)
 * - latency >= 200ms 或 disconnected -> negative (霓虹红 #FF4D4F)
 * - idle -> neutral / muted (暗灰 #5A6878)
 */
function resolveStatusTone(
  status?: 'connected' | 'degraded' | 'disconnected' | 'idle',
  latencyMs?: number | null
): { tone: 'positive' | 'warning' | 'negative' | 'neutral'; textStatus: string } {
  if (status === 'disconnected' || (latencyMs !== undefined && latencyMs !== null && latencyMs >= 200)) {
    return { tone: 'negative', textStatus: '连接异常/断开' }
  }
  if (status === 'degraded' || (latencyMs !== undefined && latencyMs !== null && latencyMs >= 50)) {
    return { tone: 'warning', textStatus: '延迟偏高' }
  }
  if (status === 'idle') {
    return { tone: 'neutral', textStatus: '待命/就绪' }
  }
  return { tone: 'positive', textStatus: '运行正常' }
}

export function HeartbeatIndicator({
  latencyMs = 12,
  status = 'connected',
  label,
  sublabel,
  compact = false,
  showLatency = true,
  className = '',
  tooltip,
  onClick
}: HeartbeatIndicatorProps) {
  const { tone, textStatus } = resolveStatusTone(status, latencyMs)
  const displayLabel = label || `系统${textStatus}`
  const latencyText = latencyMs !== null && latencyMs !== undefined ? `${latencyMs}ms` : '—'
  const displaySublabel = sublabel || `心跳响应 · ${latencyText} (UTC)`
  const finalTooltip = tooltip || `${displayLabel} | 往返延迟: ${latencyText}`

  if (compact) {
    return (
      <div
        className={`heartbeat-chip heartbeat-chip--${tone} ${className}`}
        title={finalTooltip}
        onClick={onClick}
        role={onClick ? 'button' : undefined}
      >
        <span className={`pulse-dot pulse-dot--${tone}`} />
        <span className="heartbeat-chip__label">{displayLabel}</span>
        {showLatency && latencyMs !== null && (
          <span className="heartbeat-chip__latency">{latencyText}</span>
        )}
      </div>
    )
  }

  return (
    <div
      className={`sidebar-status heartbeat-widget heartbeat-widget--${tone} ${className}`}
      title={finalTooltip}
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <span className={`pulse-dot pulse-dot--${tone}`} />
      <div className="heartbeat-widget__content">
        <b>{displayLabel}</b>
        <small>{displaySublabel}</small>
      </div>
    </div>
  )
}
