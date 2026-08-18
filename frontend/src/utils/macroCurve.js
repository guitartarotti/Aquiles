import { toNumber } from './marketFormatters.js'

export function formatBiasLabel(value) {
  const labels = { bullish: 'aliviando', bearish: 'pressionando', neutral: 'neutro' }
  return labels[value] || (value ? String(value).replaceAll('_', ' ') : '--')
}

export function formatCurveShapeLabel(value) {
  const labels = {
    bull_steepening: 'Bull steepening',
    bull_flattening: 'Bull flattening',
    bear_steepening: 'Bear steepening',
    bear_flattening: 'Bear flattening',
    parallel_easing: 'Parallel easing',
    parallel_tightening: 'Parallel tightening',
    steepening_bias: 'Bias de steepening',
    flattening_bias: 'Bias de flattening',
    mixed_curve: 'Curva mista',
  }
  return labels[value] || (value ? String(value).replaceAll('_', ' ') : '--')
}

export function formatCurveMacroRegimeKey(value) {
  const labels = {
    inflacionario: 'inflacionario',
    fiscal: 'fiscal / duration',
    contracao: 'contracao',
    desinflacionario: 'desinflacionario',
    misto: 'misto',
  }
  return labels[value] || (value ? String(value).replaceAll('_', ' ') : '--')
}

export function formatCurveMacroRegime(curveConditions) {
  if (!curveConditions || typeof curveConditions !== 'object') return '--'
  if (curveConditions.macro_regime) return String(curveConditions.macro_regime)
  const state = String(curveConditions.state || '').trim()
  const mediumLongBias = String(curveConditions.medium_long_bias || '').trim()

  if (curveConditions.fiscal_risk_flag) return 'risco fiscal / duration'
  if (state === 'bear_steepening') return 'pressao na longa'
  if (state === 'bear_flattening' || state === 'parallel_tightening') return 'contracao local'
  if (state === 'bull_steepening') return 'alivio com steepening'
  if (state === 'bull_flattening' || state === 'parallel_easing') return 'alivio / bull flattening'
  if (state === 'steepening_bias' && mediumLongBias === 'bearish') return 'stress de inclinacao'
  if (state === 'flattening_bias' && mediumLongBias === 'bullish') return 'fechamento construtivo'
  if (mediumLongBias === 'bearish') return 'medio-longo pressionando'
  if (mediumLongBias === 'bullish') return 'medio-longo aliviando'
  return 'transicao mista'
}

export function formatCurvePercent(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return `${numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
    signDisplay: 'always',
  })}%`
}

export function formatCurveProbability(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return `${numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: numeric >= 10 ? 0 : 1,
    maximumFractionDigits: numeric >= 10 ? 1 : 2,
  })}%`
}

export function formatCurveAngle(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return `${numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: 'always',
  })}°`
}

export function formatCurveAbsoluteShape(value) {
  return value ? String(value).replaceAll('_', ' ') : '--'
}

export function getCurveRegimeRanking(curveConditions, limit = 3) {
  const probabilities = curveConditions?.regime_probabilities
  if (!probabilities || typeof probabilities !== 'object') return []
  return Object.entries(probabilities)
    .map(([key, value]) => ({
      key,
      label: formatCurveMacroRegimeKey(key),
      probability: toNumber(value) ?? 0,
    }))
    .sort((left, right) => right.probability - left.probability)
    .slice(0, limit)
}

export function buildNormalizedSeries(points, valueKey, width, height, paddingX, paddingY, scale = null) {
  const validPoints = (Array.isArray(points) ? points : [])
    .map(point => ({
      ...point,
      tenor: toNumber(point?.tenor),
      value: toNumber(point?.[valueKey]),
    }))
    .filter(point => point.tenor != null && point.value != null)
    .sort((left, right) => left.tenor - right.tenor)
  if (!validPoints.length) return null

  const tenors = validPoints.map(point => point.tenor)
  const values = validPoints.map(point => point.value)
  const minTenor = Math.min(...tenors)
  const maxTenor = Math.max(...tenors)
  const configuredMin = toNumber(scale?.minValue)
  const configuredMax = toNumber(scale?.maxValue)
  const minValue = configuredMin ?? Math.min(...values)
  const maxValue = configuredMax ?? Math.max(...values)
  const tenorRange = Math.max(maxTenor - minTenor, 1)
  const valueRange = Math.max(maxValue - minValue, 0.0001)
  const plotWidth = width - (paddingX * 2)
  const plotHeight = height - (paddingY * 2)
  const nodes = validPoints.map(point => ({
    ...point,
    x: paddingX + (((point.tenor - minTenor) / tenorRange) * plotWidth),
    y: paddingY + (plotHeight - (((point.value - minValue) / valueRange) * plotHeight)),
  }))

  return {
    nodes,
    path: nodes.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' '),
    minValue,
    maxValue,
  }
}
