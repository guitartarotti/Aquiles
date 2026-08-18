export function formatMoney(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  const sign = parsed < 0 ? '-' : ''
  const absolute = Math.abs(parsed)
  if (absolute >= 1_000_000_000) return `${sign}R$ ${(absolute / 1_000_000_000).toFixed(1)} bi`
  if (absolute >= 1_000_000) return `${sign}R$ ${(absolute / 1_000_000).toFixed(1)} mi`
  return `${sign}R$ ${absolute.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

export function formatBrlMillion(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? formatMoney(parsed * 1_000_000) : '-'
}

export function formatUsdMillions(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  const sign = parsed < 0 ? '-' : ''
  const absolute = Math.abs(parsed)
  if (absolute >= 1_000_000) return `${sign}US$ ${(absolute / 1_000_000).toFixed(1)} tri`
  if (absolute >= 1_000) return `${sign}US$ ${(absolute / 1_000).toFixed(1)} bi`
  return `${sign}US$ ${absolute.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} mi`
}

export function formatUsd(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  const sign = parsed < 0 ? '-' : ''
  const absolute = Math.abs(parsed)
  if (absolute >= 1_000_000_000_000) return `${sign}US$ ${(absolute / 1_000_000_000_000).toFixed(2)} tri`
  if (absolute >= 1_000_000_000) return `${sign}US$ ${(absolute / 1_000_000_000).toFixed(1)} bi`
  if (absolute >= 1_000_000) return `${sign}US$ ${(absolute / 1_000_000).toFixed(1)} mi`
  return `${sign}US$ ${absolute.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

export function formatRatio(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${(parsed * 100).toFixed(2)}%` : '-'
}

export function formatPercent(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${parsed.toFixed(2)}%` : '-'
}

export function formatNumber(value, digits = 2) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : '-'
}

export function formatCount(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed)
    ? parsed.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
    : '-'
}

export function formatDays(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  if (parsed >= 900) return '999d+'
  return `${parsed.toFixed(parsed < 10 ? 1 : 0)}d`
}

export function formatLatency(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  return parsed >= 1000 ? `${(parsed / 1000).toFixed(1)}s` : `${parsed.toFixed(0)}ms`
}

export function formatBytes(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  if (parsed >= 1_073_741_824) return `${(parsed / 1_073_741_824).toFixed(2)} GB`
  if (parsed >= 1_048_576) return `${(parsed / 1_048_576).toFixed(1)} MB`
  if (parsed >= 1024) return `${(parsed / 1024).toFixed(1)} KB`
  return `${parsed.toFixed(0)} B`
}

export function ratioPercent(value, base) {
  const numerator = Number(value)
  const denominator = Number(base)
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return null
  return numerator / denominator * 100
}

export function formatSignedCount(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  const sign = parsed > 0 ? '+' : parsed < 0 ? '-' : ''
  return `${sign}${Math.abs(parsed).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

export function movementClass(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || Math.abs(parsed) < 0.000001) return 'flat'
  return parsed > 0 ? 'up' : 'down'
}

export function formatDate(value) {
  if (!value) return '-'
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00`)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleDateString('pt-BR')
}

export function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function shortDate(value) {
  if (!value) return '-'
  const text = String(value).slice(0, 10)
  return `${text.slice(8, 10)}/${text.slice(5, 7)}`
}

export function formatPeriodDate(value) {
  const text = String(value || '')
  if (!text) return '-'
  return /^\d{4}:Q[1-4]$/.test(text) ? text : shortDate(text)
}
