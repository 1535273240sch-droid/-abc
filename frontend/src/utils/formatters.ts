/**
 * Institutional Grade Financial Number & Date Formatters
 * 彭博/机构级量化金融数值与时间自适应格式化工具库
 */

export type Tone = 'positive' | 'negative' | 'neutral' | 'warning' | 'accent'

/**
 * 辅助解析：将 string | number | null | undefined 安全转为 number
 */
export function parseNumber(val: number | string | null | undefined): number | null {
  if (val === null || val === undefined || val === '') return null
  if (typeof val === 'number') return isNaN(val) ? null : val
  const clean = String(val).replace(/[\$,\s%]/g, '')
  const num = Number(clean)
  return isNaN(num) ? null : num
}

/**
 * 1. 货币金额格式化（支持千分位、自定义精度与前缀）
 * 示例: formatCurrency(248920.5) -> "$248,920.50"
 * 示例: formatCurrency(-1250) -> "-$1,250.00"
 */
export function formatCurrency(
  val: number | string | null | undefined,
  decimals: number = 2,
  prefix: string = '$',
  fallback: string = '—'
): string {
  const num = parseNumber(val)
  if (num === null) return fallback

  const isNegative = num < 0
  const absNum = Math.abs(num)
  const fixedStr = absNum.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })

  return `${isNegative ? '-' : ''}${prefix}${fixedStr}`
}

/**
 * 2. 机构级大数 K/M/B/T 缩写格式化
 * 示例: formatKMB(1250000) -> "1.25M"
 * 示例: formatKMB(450200, 1) -> "450.2K"
 * 示例: formatKMB(2450000000, 2, '$') -> "$2.45B"
 */
export function formatKMB(
  val: number | string | null | undefined,
  decimals: number = 2,
  prefix: string = '',
  fallback: string = '—'
): string {
  const num = parseNumber(val)
  if (num === null) return fallback

  const isNegative = num < 0
  const absNum = Math.abs(num)

  let formatted = ''
  let unit = ''

  if (absNum >= 1e12) {
    formatted = (absNum / 1e12).toFixed(decimals)
    unit = 'T'
  } else if (absNum >= 1e9) {
    formatted = (absNum / 1e9).toFixed(decimals)
    unit = 'B'
  } else if (absNum >= 1e6) {
    formatted = (absNum / 1e6).toFixed(decimals)
    unit = 'M'
  } else if (absNum >= 1e3) {
    formatted = (absNum / 1e3).toFixed(decimals)
    unit = 'K'
  } else {
    formatted = absNum.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    })
  }

  return `${isNegative ? '-' : ''}${prefix}${formatted}${unit}`
}

/**
 * 3. 标准千分位纯数字格式化
 * 示例: formatNumber(1234567.89, 2) -> "1,234,567.89"
 */
export function formatNumber(
  val: number | string | null | undefined,
  decimals: number = 2,
  fallback: string = '—'
): string {
  const num = parseNumber(val)
  if (num === null) return fallback

  return num.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
}

/**
 * 4. 百分比格式化（显式 + / - 符号）
 * 示例: formatPercent(1.39) -> "+1.39%"
 * 示例: formatPercent(-0.45) -> "-0.45%"
 * 示例: formatPercent(0.0139, true, 2, true) -> "+1.39%" (isFraction: true)
 */
export function formatPercent(
  val: number | string | null | undefined,
  includeSign: boolean = true,
  decimals: number = 2,
  isFraction: boolean = false,
  fallback: string = '0.00%'
): string {
  const rawNum = parseNumber(val)
  if (rawNum === null) return fallback

  const num = isFraction ? rawNum * 100 : rawNum
  const fixedStr = Math.abs(num).toFixed(decimals)

  if (num > 0 && includeSign) {
    return `+${fixedStr}%`
  } else if (num < 0) {
    return `-${fixedStr}%`
  }
  return `${fixedStr}%`
}

/**
 * 5. 加密货币价格自适应动态精度格式化
 * - val >= 100: 2 位小数 (BTC, ETH, SOL)
 * - 1 <= val < 100: 4 位小数 (LINK, UNI)
 * - 0.01 <= val < 1: 5 位小数 (DOGE, XRP)
 * - 0.0001 <= val < 0.01: 6 位小数
 * - val < 0.0001: 8 位小数 (PEPE, SHIB)
 */
export function formatPrice(
  val: number | string | null | undefined,
  symbol: string = '',
  includePrefix: boolean = false,
  fallback: string = '—'
): string {
  const num = parseNumber(val)
  if (num === null) return fallback

  const absNum = Math.abs(num)
  let decimals = 2

  if (absNum >= 100) {
    decimals = 2
  } else if (absNum >= 1) {
    decimals = 4
  } else if (absNum >= 0.01) {
    decimals = 5
  } else if (absNum >= 0.0001) {
    decimals = 6
  } else {
    decimals = 8
  }

  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })

  const prefix = includePrefix ? '$' : ''
  return symbol ? `${prefix}${formatted} ${symbol}` : `${prefix}${formatted}`
}

/**
 * 6. 时间戳格式化（支持 ISO 字符串、秒级/毫秒级时间戳、Date）
 * 示例: formatTimestamp(1723982400000, 'time') -> "12:00:00 UTC"
 * 示例: formatTimestamp("2026-08-18T11:20:00Z", 'datetime') -> "2026-08-18 11:20:00 UTC"
 */
export function formatTimestamp(
  ts: number | string | Date | null | undefined,
  formatType: 'time' | 'short' | 'datetime' | 'iso' | 'relative' = 'datetime',
  fallback: string = '—'
): string {
  if (!ts) return fallback

  let date: Date
  if (ts instanceof Date) {
    date = ts
  } else if (typeof ts === 'number') {
    date = ts < 1e11 ? new Date(ts * 1000) : new Date(ts)
  } else {
    const num = Number(ts)
    if (!isNaN(num) && num > 0) {
      date = num < 1e11 ? new Date(num * 1000) : new Date(num)
    } else {
      date = new Date(ts)
    }
  }

  if (isNaN(date.getTime())) return fallback

  if (formatType === 'iso') return date.toISOString()

  if (formatType === 'relative') {
    const now = Date.now()
    const diffSec = Math.floor((now - date.getTime()) / 1000)
    if (diffSec < 5) return '刚刚'
    if (diffSec < 60) return `${diffSec}秒前`
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分钟前`
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}小时前`
    return `${Math.floor(diffSec / 86400)}天前`
  }

  const Y = date.getUTCFullYear()
  const M = String(date.getUTCMonth() + 1).padStart(2, '0')
  const D = String(date.getUTCDate()).padStart(2, '0')
  const h = String(date.getUTCHours()).padStart(2, '0')
  const m = String(date.getUTCMinutes()).padStart(2, '0')
  const s = String(date.getUTCSeconds()).padStart(2, '0')

  if (formatType === 'time') return `${h}:${m}:${s} UTC`
  if (formatType === 'short') return `${M}-${D} ${h}:${m}:${s}`
  return `${Y}-${M}-${D} ${h}:${m}:${s} UTC`
}

/**
 * 7. 根据数值符号返回 Tone 色调 ('positive' | 'negative' | 'neutral')
 */
export function getSignedTone(val: number | string | null | undefined): Tone {
  const num = parseNumber(val)
  if (num === null || num === 0) return 'neutral'
  return num > 0 ? 'positive' : 'negative'
}

/**
 * 8. 根据数值符号返回 CSS 类名 ('text-positive' | 'text-negative' | 'text-neutral')
 */
export function getSignedToneClass(
  val: number | string | null | undefined,
  prefix: 'text-' | 'bg-' | 'badge-' = 'text-'
): string {
  const tone = getSignedTone(val)
  return `${prefix}${tone}`
}

/**
 * 9. 合约资金费率格式化
 * 示例: formatFundingRate(0.0001) -> "+0.0100% (8h)"
 */
export function formatFundingRate(
  val: number | string | null | undefined,
  interval: string = '8h'
): string {
  const num = parseNumber(val)
  if (num === null) return '—'
  const pct = formatPercent(num, true, 4, true)
  return `${pct} (${interval})`
}

/**
 * 10. 杠杆倍数格式化
 * 示例: formatLeverage(1.42) -> "1.42x"
 */
export function formatLeverage(val: number | string | null | undefined): string {
  const num = parseNumber(val)
  if (num === null) return '1.00x'
  return `${num.toFixed(2)}x`
}
