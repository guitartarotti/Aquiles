import {
  b3MonthOrder,
  cdaSides,
  cdaTargets,
  nportSides,
  nportTargets,
} from '../config/fundsFlowWidgetConfig'
import {
  formatCount as fmtCount,
  formatMoney as fmtMoney,
  formatNumber as fmtNum,
  formatPercent as fmtPctPlain,
  formatRatio as fmtPct,
  formatUsd as fmtUsd,
  formatUsdMillions as fmtUsdMn,
  shortDate,
} from './fundsFlowFormatters'

export function linePath(points) {
  if (!points.length) return ''
  return points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

export function heatColor(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'rgba(51, 65, 85, 0.35)'
  const strength = Math.min(Math.abs(parsed) / 2.5, 1)
  if (parsed > 0) return `rgba(34, 197, 94, ${0.16 + strength * 0.68})`
  if (parsed < 0) return `rgba(239, 68, 68, ${0.16 + strength * 0.68})`
  return 'rgba(100, 116, 139, 0.22)'
}

export function flowHeatColor(value, maxAbs) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'rgba(51, 65, 85, 0.35)'
  const strength = Math.min(Math.abs(parsed) / Math.max(Number(maxAbs || 0), 1), 1)
  if (parsed > 0) return `rgba(34, 197, 94, ${0.18 + strength * 0.68})`
  if (parsed < 0) return `rgba(239, 68, 68, ${0.18 + strength * 0.68})`
  return 'rgba(100, 116, 139, 0.22)'
}

export function radarBurnColor(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'rgba(100, 116, 139, 0.22)'
  const clamped = Math.max(0, Math.min(parsed, 1))
  const green = Math.max(28, Math.round(180 - clamped * 120))
  const red = Math.min(245, Math.round(60 + clamped * 180))
  return `rgba(${red}, ${green}, 108, ${0.22 + clamped * 0.58})`
}

export function radarHeatTitle(cell) {
  return [
    `${cell.radar_group || cell.fund_type_group || cell.macro_classe || '-'}`,
    `${cell.bucket_label || '-'}`,
    `queima plaus.: ${fmtPctPlain(Number((cell.plausible_burn_pct ?? cell.burn_pct) || 0) * 100)}`,
    `consumido plaus.: ${fmtMoney(cell.plausible_consumed_since_cda ?? cell.consumed_since_cda)}`,
    `restante plaus.: ${fmtMoney(cell.plausible_remaining_inventory ?? cell.remaining_inventory)}`,
    `consumido tec.: ${fmtMoney(cell.consumed_since_cda)}`,
    `restante tec.: ${fmtMoney(cell.remaining_inventory)}`,
    `fundos: ${fmtCount(cell.fund_count)}`,
  ].join(' | ')
}

export function nportDivergingColor(value, maxAbs = 100) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '#94a3b8'
  const strength = Math.min(Math.abs(parsed) / Math.max(Number(maxAbs || 0), 1), 1)
  if (parsed > 0) return `rgba(45, 212, 191, ${0.42 + strength * 0.48})`
  if (parsed < 0) return `rgba(248, 113, 113, ${0.42 + strength * 0.48})`
  return 'rgba(148, 163, 184, 0.55)'
}

export function nportCellTint(value, maxAbs) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return {}
  const strength = Math.min(Math.abs(parsed) / Math.max(Number(maxAbs || 0), 1), 1)
  const color = parsed >= 0 ? '34, 197, 94' : '239, 68, 68'
  return {
    background: `linear-gradient(90deg, rgba(${color}, ${0.06 + strength * 0.22}), rgba(${color}, ${0.02 + strength * 0.08}))`,
    color: parsed >= 0 ? '#bbf7d0' : '#fecaca',
  }
}

export function nportRowTint(value, maxAbs) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed === 0) return {}
  const strength = Math.min(Math.abs(parsed) / Math.max(Number(maxAbs || 0), 1), 1)
  const color = parsed > 0 ? '20, 184, 166' : '244, 63, 94'
  return {
    background: `linear-gradient(90deg, rgba(${color}, ${0.035 + strength * 0.11}), rgba(15, 23, 42, 0) 72%)`,
  }
}

export function nportTileBackground(value, strength) {
  const color = Number(value) >= 0 ? '20, 184, 166' : '244, 63, 94'
  return `radial-gradient(circle at 18% 18%, rgba(255,255,255,0.08), rgba(255,255,255,0) 42%), linear-gradient(135deg, rgba(${color}, ${0.24 + strength * 0.48}), rgba(15, 23, 42, 0.72))`
}

export function nportCountryPillStyle(country) {
  const text = String(country || '??')
  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) % 360
  }
  return {
    color: `hsl(${hash}, 82%, 78%)`,
    background: `hsla(${hash}, 70%, 44%, 0.16)`,
    borderColor: `hsla(${hash}, 76%, 62%, 0.34)`,
  }
}

export function totalPages(payloadLike) {
  const total = Number(payloadLike?.total || 0)
  const perPage = Number(payloadLike?.per_page || 1)
  if (!Number.isFinite(total) || !Number.isFinite(perPage) || perPage <= 0) return 1
  return Math.max(1, Math.ceil(total / perPage))
}

export function nportTargetLabel(key) {
  return nportTargets.find(item => item.key === key)?.label || key
}

export function nportSideLabel(key) {
  return nportSides.find(item => item.key === key)?.label || key
}

export function cdaTargetLabel(key) {
  return cdaTargets.find(item => item.key === key)?.label || key
}

export function cdaSideLabel(key) {
  return cdaSides.find(item => item.key === key)?.label || key
}

export function edgeFactMetricLabel(metrics = {}) {
  const parts = []
  if (Number.isFinite(Number(metrics.fund_count))) parts.push(`${fmtCount(metrics.fund_count)} fundos`)
  if (Number.isFinite(Number(metrics.gross_value))) parts.push(`gross ${fmtMoney(metrics.gross_value)}`)
  if (Number.isFinite(Number(metrics.net_value))) parts.push(`net ${fmtMoney(metrics.net_value)}`)
  if (Number.isFinite(Number(metrics.reported_activity)) && Math.abs(Number(metrics.reported_activity)) > 0.000001) {
    parts.push(`atividade ${fmtMoney(metrics.reported_activity)}`)
  }
  return parts.slice(0, 4).join(' | ')
}

export function portfolioSharedFactorText(item = {}) {
  const direct = [
    ...(item.shared_structures || []),
    ...(item.shared_options || []),
    ...(item.shared_fixed_income || []),
    ...(item.shared_activity || []),
    ...(item.shared_macro || []),
    ...(item.shared_assets || []),
  ].filter(Boolean)
  if (direct.length) return direct.slice(0, 4).join(' | ')
  return (item.shared_factors || []).map(factor => factor.label).filter(Boolean).slice(0, 4).join(' | ') || item.explanation || '-'
}

export function cdaHeatTitle(cell) {
  return `${cell.fund_type} | ${cell.asset_class}: ${fmtMoney(cell.value)} | bruto ${fmtMoney(cell.abs_value)} | fundos ${fmtCount(cell.fund_count)} | posicoes ${fmtCount(cell.holding_count)}`
}

export function cdaScatterTitle(point) {
  const fragility = Number(point.foreign_pct_pl || 0) + Number(point.confidential_pct_pl || 0)
  return `${point.fund_name || point.fund_cnpj} | fragilidade ${fmtPctPlain(fragility)} PL | concentracao ${fmtPctPlain(point.concentration_pct)} | PL ${fmtMoney(point.pl)}`
}

export function nportHeatTitle(cell) {
  return `${cell.country} | ${cell.asset_cat}: net ${fmtUsd(cell.net_value)} | long ${fmtUsd(cell.long_value)} | short ${fmtUsd(cell.short_value)} | fundos ${fmtCount(cell.fund_count)}`
}

export function nportScatterTitle(point) {
  return `${point.series_name || point.accession_number} | EM net ${fmtPctPlain(point.net_pct_aum)} AUM | max pos ${fmtPctPlain(point.max_holding_pct)} | retorno 3m ${fmtPctPlain(point.return_3m_pct)}`
}

export function nportCountryOrbitTitle(point) {
  return `${point.investment_country} | gross ${fmtUsd(point.gross_value)} | long ${fmtUsd(point.long_value)} | short ${fmtUsd(point.short_value)} | net/gross ${fmtPctPlain(point.net_to_gross_pct)}`
}

export function heatTitle(cell) {
  const detail = cell.detail || {}
  return `${cell.name} ${shortDate(cell.date)} | Z ${fmtNum(cell.value, 2)} | fluxo ${fmtMoney(detail.net_flow)} | %PL ${fmtPct(detail.flow_pct_pl)} | fundos ${detail.num_funds ?? '-'}`
}

export function iciHeatTitle(row, cell) {
  return `${row.country} | ${cell.label}: ${fmtUsdMn(cell.value)} | regiao ${row.region}`
}

export function expirationRank(value) {
  const text = String(value || '').toUpperCase()
  const match = text.match(/^([FGHJKMNQUVXZ])(\d{2})$/)
  if (!match) return 999999
  const year = 2000 + Number(match[2])
  return year * 12 + (b3MonthOrder[match[1]] || 0)
}

export function ratioTone(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'flat'
  if (parsed > 0.65) return 'down'
  if (parsed > 0.45) return 'warn'
  return 'up'
}

export function regimeClass(value) {
  const text = String(value || '')
  if (text.includes('stress') || text.includes('resgate')) return 'down'
  if (text.includes('entrada')) return 'up'
  return 'flat'
}

export function regimeLabel(value) {
  const labels = {
    entrada_forte: 'Entrada forte',
    entrada: 'Entrada',
    neutral: 'Neutro',
    resgate: 'Resgate',
    stress: 'Stress',
  }
  return labels[value] || 'Neutro'
}

export function stressLabel(value) {
  if (value === 'high') return 'alto'
  if (value === 'medium') return 'medio'
  return 'baixo'
}

