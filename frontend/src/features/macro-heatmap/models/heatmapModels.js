import {
  CAPTURED_FACTOR_DISPLAY_OPTIONS,
  CORRELATION_SERIES_COLORS,
  FAIR_VALUE_CORE_LEG_OPTIONS,
  FAIR_VALUE_DISPLAY_STABILITY_SAMPLE_LIMIT,
  FAIR_VALUE_DISPLAY_STABILITY_WINDOW_MINUTES,
  FAIR_VALUE_SHADOW_LEG_OPTIONS,
  GAMMA_OVERLAY_OPTIONS,
} from './config'
import {
  formatCompactFloat,
  formatPrice,
  formatSignedFloat,
  formatSignedPoints,
  formatSignedQuantity,
  toNumber,
} from '../../../utils/marketFormatters'
import {
  buildNormalizedSeries,
  formatBiasLabel,
  formatCurveMacroRegime,
  formatCurvePercent,
  formatCurveShapeLabel,
  getCurveRegimeRanking,
} from './macroCurve'

export function formatTime(value) {
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '--:--'
  return dt.toLocaleTimeString('pt-BR', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatDayKey(value) {
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  const year = dt.getFullYear()
  const month = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatAxisTime(value) {
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '--:--'
  return dt.toLocaleTimeString('pt-BR', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function scopeSamplesToTradingSession(samples, startHour = 9, startMinute = 0) {
  const orderedSamples = (Array.isArray(samples) ? samples : [])
    .filter((sample) => sample && Number.isFinite(sample.ts))
    .sort((left, right) => left.ts - right.ts)
  if (!orderedSamples.length) return []
  const latestSample = orderedSamples[orderedSamples.length - 1] || null
  const latestDayKey = formatDayKey(latestSample?.ts)
  const sameDaySamples = latestDayKey
    ? orderedSamples.filter((sample) => formatDayKey(sample.ts) === latestDayKey)
    : orderedSamples
  if (!sameDaySamples.length) return []
  const sessionStart = new Date(sameDaySamples[sameDaySamples.length - 1].ts)
  sessionStart.setHours(startHour, startMinute, 0, 0)
  const sessionStartTs = sessionStart.getTime()
  const inSessionSamples = sameDaySamples.filter((sample) => sample.ts >= sessionStartTs)
  return inSessionSamples.length ? inSessionSamples : sameDaySamples
}

export function clamp(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value))
}


export function formatImplicitSentiment(value) {
  if (!value) return '--'
  if (value === 'bullish_confirmed') return 'Bullish Confirmed'
  if (value === 'bullish_fragile') return 'Bullish Fragile'
  if (value === 'bearish_confirmed') return 'Bearish Confirmed'
  if (value === 'bearish_fragile') return 'Bearish Fragile'
  if (value === 'neutral') return 'Neutral'
  if (value === 'divergent') return 'Divergent'
  if (value === 'latent_stress') return 'Latent Stress'
  if (value === 'overextended_fragile') return 'Overextended Fragile'
  if (value === 'recovery_candidate') return 'Recovery Candidate'
  if (value === 'squeeze_risk') return 'Squeeze Risk'
  if (value === 'stress_risk') return 'Stress Risk'
  if (value === 'carry_unwind_risk') return 'Carry Unwind Risk'
  return String(value).replaceAll('_', ' ')
}

export function getImplicitSentimentBias(value) {
  if (value === 'bullish_confirmed' || value === 'recovery_candidate') return 1
  if (value === 'bullish_fragile' || value === 'overextended_fragile') return 0.65
  if (value === 'squeeze_risk') return 0.35
  if (value === 'bearish_confirmed' || value === 'stress_risk' || value === 'carry_unwind_risk') return -1
  if (value === 'bearish_fragile' || value === 'latent_stress') return -0.65
  return 0
}

export function fairValueSentimentClass(value) {
  if (value === 'bullish_confirmed' || value === 'recovery_candidate') return 'bullish'
  if (value === 'bullish_fragile' || value === 'overextended_fragile') return 'bullish-fragile'
  if (value === 'bearish_confirmed' || value === 'stress_risk' || value === 'carry_unwind_risk') return 'bearish'
  if (value === 'bearish_fragile' || value === 'latent_stress') return 'bearish-fragile'
  if (value === 'divergent' || value === 'squeeze_risk') return 'divergent'
  return 'neutral'
}

export function fairValueGaugeClass(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return 'weak'
  if (numeric < 30) return 'weak'
  if (numeric < 60) return 'fragile'
  if (numeric < 80) return 'good'
  return 'strong'
}

export function buildCurveVisualization(curveConditions) {
  if (!curveConditions || typeof curveConditions !== 'object') return null
  const width = 328
  const height = 126
  const paddingX = 18
  const paddingY = 18
  const dayChangeValues = [
    ...((Array.isArray(curveConditions.curve_points) ? curveConditions.curve_points : []).map((point) => toNumber(point?.daily_change_pct))),
    ...((Array.isArray(curveConditions.inflation_points) ? curveConditions.inflation_points : []).map((point) => toNumber(point?.daily_change_pct))),
  ].filter((value) => Number.isFinite(value))
  const sharedScale = dayChangeValues.length
    ? {
      minValue: Math.min(...dayChangeValues),
      maxValue: Math.max(...dayChangeValues),
    }
    : null
  const nominal = buildNormalizedSeries(curveConditions.curve_points, 'daily_change_pct', width, height, paddingX, paddingY, sharedScale)
  const inflation = buildNormalizedSeries(curveConditions.inflation_points, 'daily_change_pct', width, height, paddingX, paddingY, sharedScale)
  if (!nominal && !inflation) return null
  const plotHeight = height - (paddingY * 2)
  const scaleMin = toNumber(sharedScale?.minValue)
  const scaleMax = toNumber(sharedScale?.maxValue)
  const valueRange = Math.max((scaleMax ?? 0) - (scaleMin ?? 0), 0.0001)
  const zeroLineY = Number.isFinite(scaleMin) && Number.isFinite(scaleMax) && scaleMin <= 0 && scaleMax >= 0
    ? paddingY + (plotHeight - (((0 - scaleMin) / valueRange) * plotHeight))
    : null
  return {
    width,
    height,
    nominal,
    inflation,
    zeroLineY,
  }
}

export function formatFlexibleConfidence(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  return formatConfidenceScore(numeric <= 1 ? numeric * 100 : numeric)
}

export function getFairValueLegContributionValue(leg) {
  return toNumber(leg?.contribution_points ?? leg?.quality_impact) ?? 0
}

export function getFairValueLegRanking(legs, legType, direction, limit = 4) {
  const options = legType === 'shadow' ? FAIR_VALUE_SHADOW_LEG_OPTIONS : FAIR_VALUE_CORE_LEG_OPTIONS
  const minContribution = legType === 'shadow' ? 0.25 : 0.5
  return options
    .map((option) => {
      const leg = legs?.[option.key]
      if (!leg || typeof leg !== 'object') return null
      const contributionValue = getFairValueLegContributionValue(leg)
      if (Math.abs(contributionValue) < minContribution) return null
      if (direction === 'up' && contributionValue <= 0) return null
      if (direction === 'down' && contributionValue >= 0) return null
      return {
        ...option,
        ...leg,
        contributionValue,
      }
    })
    .filter(Boolean)
    .sort((left, right) => (
      direction === 'up'
        ? right.contributionValue - left.contributionValue
        : left.contributionValue - right.contributionValue
    ))
    .slice(0, limit)
}

export function getFairValueShadowRanking(legs, limit = 6) {
  return FAIR_VALUE_SHADOW_LEG_OPTIONS
    .map((option) => {
      const leg = legs?.[option.key]
      if (!leg || typeof leg !== 'object') return null
      const qualityImpactValue = toNumber(leg?.quality_impact) ?? 0
      const bandImpactValue = toNumber(leg?.band_impact) ?? 0
      const convergenceImpactValue = toNumber(leg?.convergence_impact) ?? 0
      const magnitude = Math.max(
        Math.abs(qualityImpactValue),
        Math.abs(bandImpactValue) * 100,
        Math.abs(convergenceImpactValue) * 100,
      )
      if (magnitude < 0.25) return null
      return {
        ...option,
        ...leg,
        qualityImpactValue,
        bandImpactValue,
        convergenceImpactValue,
        magnitude,
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.magnitude - left.magnitude)
    .slice(0, limit)
}

export function averageFinite(values) {
  const numbers = values.filter((value) => Number.isFinite(value))
  if (!numbers.length) return null
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length
}

export function getStableQualityWindowSamples(samples, referenceTs) {
  if (!Array.isArray(samples) || !samples.length) return []
  const windowMs = FAIR_VALUE_DISPLAY_STABILITY_WINDOW_MINUTES * 60 * 1000
  const scopedSamples = Number.isFinite(referenceTs)
    ? samples.filter((sample) => Number.isFinite(sample?.ts) && sample.ts <= referenceTs && sample.ts >= (referenceTs - windowMs))
    : samples
  const baseSamples = scopedSamples.length ? scopedSamples : samples
  return baseSamples.slice(-FAIR_VALUE_DISPLAY_STABILITY_SAMPLE_LIMIT)
}

export function buildStableLegMap(samples, legType) {
  const options = legType === 'shadow' ? FAIR_VALUE_SHADOW_LEG_OPTIONS : FAIR_VALUE_CORE_LEG_OPTIONS
  const legBucketKey = legType === 'shadow' ? 'shadowLegs' : 'coreLegs'
  const averagedFieldKeys = legType === 'shadow'
    ? ['confidence', 'score', 'quality_impact', 'band_impact', 'convergence_impact', 'implied_fair_value_xb1', 'model_relative_implied_fair_value_xb1', 'isolated_implied_fair_value_xb1']
    : ['confidence', 'score', 'strength', 'contribution_points', 'implied_fair_value_xb1', 'model_relative_implied_fair_value_xb1', 'isolated_implied_fair_value_xb1']
  const stableMap = {}

  options.forEach((option) => {
    const supportingLegs = samples
      .map((sample) => sample?.[legBucketKey]?.[option.key])
      .filter((leg) => leg && typeof leg === 'object')
    if (!supportingLegs.length) return

    const latestLeg = { ...supportingLegs[supportingLegs.length - 1] }
    averagedFieldKeys.forEach((fieldKey) => {
      const averagedValue = averageFinite(supportingLegs.map((leg) => toNumber(leg?.[fieldKey])))
      if (Number.isFinite(averagedValue)) {
        latestLeg[fieldKey] = averagedValue
      }
    })

    if (legType === 'core') {
      const contributionPoints = toNumber(latestLeg.contribution_points) || 0
      latestLeg.direction = contributionPoints > 0 ? 'bullish' : contributionPoints < 0 ? 'bearish' : 'neutral'
    }

    stableMap[option.key] = {
      ...latestLeg,
      enabled: supportingLegs.some((leg) => leg?.enabled !== false),
    }
  })

  return stableMap
}

export function buildQualityHealthScore(sample) {
  if (!sample || typeof sample !== 'object') return null
  const gauge = toNumber(sample?.qualityGauge)
  const coherence = toNumber(sample?.coherenceScore)
  const alignment = toNumber(sample?.coreShadowAlignment)
  const riskQuality = toNumber(sample?.riskQualityScore)
  const qualityComponents = []
  if (Number.isFinite(gauge)) qualityComponents.push(gauge)
  if (Number.isFinite(coherence)) qualityComponents.push(coherence * 100)
  if (Number.isFinite(alignment)) qualityComponents.push(alignment * 100)
  if (Number.isFinite(riskQuality)) {
    const normalizedRiskQuality = riskQuality <= 1 ? riskQuality * 100 : riskQuality
    qualityComponents.push(100 - clamp(normalizedRiskQuality, 0, 100))
  }
  qualityComponents.push(50 + (getImplicitSentimentBias(sample?.implicitSentiment) * 18))
  return averageFinite(qualityComponents)
}

export function buildQualityPulse(samples) {
  const scopedSamples = (Array.isArray(samples) ? samples : [])
    .filter((sample) => sample && Number.isFinite(sample.ts))
    .sort((left, right) => left.ts - right.ts)
  if (!scopedSamples.length) return null

  const startSample = scopedSamples[0]
  const endSample = scopedSamples[scopedSamples.length - 1]
  const previousSample = scopedSamples[scopedSamples.length - 2] || null
  const startHealthScore = buildQualityHealthScore(startSample)
  const endHealthScore = buildQualityHealthScore(endSample)
  const healthDelta = Number.isFinite(startHealthScore) && Number.isFinite(endHealthScore)
    ? endHealthScore - startHealthScore
    : null

  const readQualityGap = (sample) => {
    const qualityAdjusted = toNumber(sample?.qualityAdjustedPrice)
    const coreFairValue = toNumber(sample?.coreFairValue ?? sample?.price)
    return Number.isFinite(qualityAdjusted) && Number.isFinite(coreFairValue)
      ? qualityAdjusted - coreFairValue
      : null
  }

  const startQualityGap = readQualityGap(startSample)
  const endQualityGap = readQualityGap(endSample)
  const previousQualityGap = readQualityGap(previousSample)
  const qualityGapDelta = Number.isFinite(startQualityGap) && Number.isFinite(endQualityGap)
    ? endQualityGap - startQualityGap
    : null
  const qualityGapImpulse = Number.isFinite(previousQualityGap) && Number.isFinite(endQualityGap)
    ? endQualityGap - previousQualityGap
    : qualityGapDelta

  const startPrice = toNumber(startSample?.currentPrice)
  const endPrice = toNumber(endSample?.currentPrice)
  const priceDelta = Number.isFinite(startPrice) && Number.isFinite(endPrice)
    ? endPrice - startPrice
    : null

  const startQualityAdjusted = toNumber(startSample?.qualityAdjustedPrice)
  const endQualityAdjusted = toNumber(endSample?.qualityAdjustedPrice)
  const qualityAdjustedDelta = Number.isFinite(startQualityAdjusted) && Number.isFinite(endQualityAdjusted)
    ? endQualityAdjusted - startQualityAdjusted
    : null

  const sentimentBias = getImplicitSentimentBias(endSample?.implicitSentiment)
  const currentGapScore = Number.isFinite(endQualityGap)
    ? clamp((endQualityGap / 45) * 100, -100, 100)
    : sentimentBias * 45
  const gapTrendScore = Number.isFinite(qualityGapImpulse)
    ? clamp((qualityGapImpulse / 18) * 100, -100, 100)
    : 0
  const healthTrendScore = Number.isFinite(healthDelta)
    ? clamp((healthDelta / 10) * 100, -100, 100)
    : 0
  const directionScore = averageFinite([
    currentGapScore,
    currentGapScore,
    gapTrendScore,
    healthTrendScore,
    sentimentBias * 100,
  ]) ?? 0
  const direction = directionScore > 14
    ? 'up'
    : directionScore < -14
      ? 'down'
      : 'flat'
  const toneClass = direction === 'up' ? 'up' : direction === 'down' ? 'down' : 'flat'
  const strengthPercent = clamp(Math.abs(directionScore), 10, 100)
  const qualityDriverDelta = Number.isFinite(qualityGapDelta) && Math.abs(qualityGapDelta) >= 2
    ? qualityGapDelta
    : qualityAdjustedDelta

  let followThroughClass = 'waiting'
  let followThroughLabel = 'Preco ainda sem reacao clara'
  if (Number.isFinite(priceDelta) && Number.isFinite(qualityDriverDelta) && Math.abs(qualityDriverDelta) >= 1.5) {
    if (Math.sign(priceDelta) === Math.sign(qualityDriverDelta) && Math.sign(qualityDriverDelta) !== 0) {
      const ratio = Math.abs(priceDelta) / Math.max(Math.abs(qualityDriverDelta), 1)
      if (ratio < 0.35) {
        followThroughClass = 'lagging'
        followThroughLabel = 'Preco atrasado contra a qualidade'
      } else if (ratio > 1.65) {
        followThroughClass = 'leading'
        followThroughLabel = 'Preco correu na frente da qualidade'
      } else {
        followThroughClass = 'following'
        followThroughLabel = 'Preco acompanhando a qualidade'
      }
    } else if (Math.abs(priceDelta) < Math.max(Math.abs(qualityDriverDelta) * 0.2, 1.5)) {
      followThroughClass = 'waiting'
      followThroughLabel = 'Preco ainda quase nao reagiu'
    } else {
      followThroughClass = 'negating'
      followThroughLabel = 'Preco negando a leitura da qualidade'
    }
  }

  let directionLabel = 'Sem pressao clara'
  let headline = 'Qualidade lateral'
  if (direction === 'up') {
    directionLabel = 'Pressao de alta'
    headline = Number.isFinite(healthDelta) && healthDelta >= 1.5
      ? 'Qualidade subindo com apoio comprador'
      : 'Shadow ainda inclina a leitura para cima'
  } else if (direction === 'down') {
    directionLabel = 'Pressao de baixa'
    headline = Number.isFinite(healthDelta) && healthDelta <= -1.5
      ? 'Qualidade piorando com perda de sustentacao'
      : 'Shadow ainda inclina a leitura para baixo'
  } else if (Number.isFinite(healthDelta) && healthDelta >= 1.5) {
    headline = 'Qualidade melhora, mas sem empurrao claro'
  } else if (Number.isFinite(healthDelta) && healthDelta <= -1.5) {
    headline = 'Qualidade piora, mas sem direcao dominante'
  }

  const healthRead = Number.isFinite(healthDelta)
    ? healthDelta >= 1.5
      ? 'A saude geral do bloco melhora na janela recente.'
      : healthDelta <= -1.5
        ? 'A saude geral do bloco piora na janela recente.'
        : 'A saude geral do bloco segue relativamente estavel.'
    : 'A saude geral do bloco ainda esta em formacao.'
  const directionRead = direction === 'up'
    ? 'O shadow esta ficando mais comprador e reduz a motivacao de venda.'
    : direction === 'down'
      ? 'O shadow esta ficando mais vendedor e reduz a motivacao de compra.'
      : 'O shadow ainda nao entrega um vetor direcional limpo.'
  const followRead = followThroughClass === 'following'
    ? 'O preco ja acompanha esse vetor.'
    : followThroughClass === 'lagging'
      ? 'O preco ainda esta atrasado contra esse vetor.'
      : followThroughClass === 'leading'
        ? 'O preco correu antes da qualidade e pode estar adiantado.'
        : followThroughClass === 'negating'
          ? 'O preco esta negando essa leitura por enquanto.'
          : 'O preco ainda quase nao reagiu.'

  const windowMinutes = scopedSamples.length >= 2
    ? Math.max(1, Math.round((endSample.ts - startSample.ts) / 60000))
    : null

  return {
    sampleCount: scopedSamples.length,
    toneClass,
    direction,
    directionLabel,
    headline,
    summary: `${healthRead} ${directionRead} ${followRead}`,
    strengthPercent,
    strengthLabel: `${Math.round(strengthPercent)}/100`,
    sentimentLabel: formatImplicitSentiment(endSample?.implicitSentiment),
    windowLabel: windowMinutes ? `${windowMinutes}m / ${scopedSamples.length} pts` : `${scopedSamples.length} pt`,
    healthDeltaLabel: formatSignedFloat(healthDelta),
    shadowGapLabel: formatSignedPoints(endQualityGap),
    shadowGapDeltaLabel: formatSignedPoints(qualityGapDelta),
    priceDeltaLabel: formatSignedPoints(priceDelta),
    followThroughClass,
    followThroughLabel,
    series: scopedSamples.map((sample, index) => {
      const healthScore = buildQualityHealthScore(sample)
      const sampleBias = getImplicitSentimentBias(sample?.implicitSentiment)
      return {
        key: sample?.key || `quality-pulse-${index}`,
        heightPercent: clamp(Number.isFinite(healthScore) ? healthScore : 18, 18, 100),
        toneClass: sampleBias > 0.2 ? 'up' : sampleBias < -0.2 ? 'down' : 'flat',
      }
    }),
  }
}

export function formatNaturalList(values) {
  const labels = (Array.isArray(values) ? values : [])
    .map((value) => String(value || '').trim())
    .filter(Boolean)
  if (!labels.length) return ''
  if (labels.length === 1) return labels[0]
  if (labels.length === 2) return `${labels[0]} e ${labels[1]}`
  return `${labels.slice(0, -1).join(', ')} e ${labels[labels.length - 1]}`
}

export function formatQualityScore(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  return `${Math.round(numeric)}/100`
}

export function buildSvgLinePath(points) {
  const scopedPoints = (Array.isArray(points) ? points : [])
    .filter((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))
  if (!scopedPoints.length) return ''
  return scopedPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ')
}

export function buildSvgAreaPath(points, baselineY) {
  const scopedPoints = (Array.isArray(points) ? points : [])
    .filter((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))
  if (!scopedPoints.length || !Number.isFinite(baselineY)) return ''
  const linePath = buildSvgLinePath(scopedPoints)
  if (!linePath) return ''
  const firstPoint = scopedPoints[0]
  const lastPoint = scopedPoints[scopedPoints.length - 1]
  return `${linePath} L ${lastPoint.x.toFixed(2)} ${baselineY.toFixed(2)} L ${firstPoint.x.toFixed(2)} ${baselineY.toFixed(2)} Z`
}

export function buildSvgSegmentedLinePath(points) {
  const scopedPoints = (Array.isArray(points) ? points : [])
    .filter((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))
  if (!scopedPoints.length) return ''
  return scopedPoints
    .map((point, index) => {
      const command = index === 0 || point.breakBefore ? 'M' : 'L'
      return `${command} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
    })
    .join(' ')
}

export function buildQualityHistory(samples, qualityPulse) {
  const scopedSamples = scopeSamplesToTradingSession(samples)
  const preparedSamples = scopedSamples
    .map((sample, index) => {
      const score = buildQualityHealthScore(sample)
      if (!Number.isFinite(score)) return null
      return {
        key: sample?.key || `quality-history-${index}`,
        sample,
        score,
      }
    })
    .filter(Boolean)
  if (preparedSamples.length < 2) return null

  const width = 960
  const height = 184
  const plotLeft = 10
  const plotRight = width - 10
  const plotTop = 12
  const plotBottom = 132

  const scoreValues = preparedSamples.map((item) => item.score)
  let minScore = Math.min(...scoreValues)
  let maxScore = Math.max(...scoreValues)
  minScore = Math.max(0, Math.min(38, Math.floor((minScore - 6) / 5) * 5))
  maxScore = Math.min(100, Math.max(62, Math.ceil((maxScore + 6) / 5) * 5))
  if (!Number.isFinite(minScore) || !Number.isFinite(maxScore) || maxScore <= minScore) {
    minScore = 0
    maxScore = 100
  }

  const xSpan = Math.max(plotRight - plotLeft, 1)
  const ySpan = Math.max(plotBottom - plotTop, 1)
  const points = preparedSamples.map((item, index) => {
    const x = plotLeft + ((preparedSamples.length === 1 ? 0 : index / (preparedSamples.length - 1)) * xSpan)
    const y = plotBottom - (((item.score - minScore) / Math.max(maxScore - minScore, 1)) * ySpan)
    return {
      key: item.key,
      x,
      y,
      radius: index === preparedSamples.length - 1 ? 4.2 : 2.8,
      toneClass: item.score >= 56 ? 'up' : item.score <= 44 ? 'down' : 'flat',
      isLatest: index === preparedSamples.length - 1,
      label: formatTime(item.sample.ts),
      sample: item.sample,
      score: item.score,
    }
  })

  const firstPoint = points[0]
  const latestPoint = points[points.length - 1]
  const previousPoint = points[points.length - 2] || null
  const delta = latestPoint.score - firstPoint.score
  const impulse = previousPoint ? latestPoint.score - previousPoint.score : delta
  const toneClass = delta > 2 ? 'up' : delta < -2 ? 'down' : 'flat'
  const baselineY = plotBottom - (((50 - minScore) / Math.max(maxScore - minScore, 1)) * ySpan)
  const latestShadowGap = (() => {
    const qualityAdjusted = toNumber(latestPoint.sample?.qualityAdjustedPrice)
    const coreFairValue = toNumber(latestPoint.sample?.coreFairValue ?? latestPoint.sample?.price)
    return Number.isFinite(qualityAdjusted) && Number.isFinite(coreFairValue)
      ? qualityAdjusted - coreFairValue
      : null
  })()
  const scoreRead = toneClass === 'up'
    ? 'A saude do bloco melhora ao longo do dia.'
    : toneClass === 'down'
      ? 'A saude do bloco perde qualidade ao longo do dia.'
      : 'A saude do bloco segue mais lateral no dia.'
  const followRead = String(qualityPulse?.followThroughLabel || 'Preco ainda sem reacao clara')
  const tickIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])]

  return {
    width,
    height,
    plotLeft,
    plotRight,
    plotTop,
    plotBottom,
    baselineY,
    toneClass,
    headline: toneClass === 'up'
      ? 'Qualidade ganhou tracao no tempo'
      : toneClass === 'down'
        ? 'Qualidade perdeu tracao no tempo'
        : 'Qualidade segue sem grande deslocamento',
    summary: `${scoreRead} ${followRead}.`,
    latestScoreLabel: formatQualityScore(latestPoint.score),
    deltaLabel: formatSignedFloat(delta),
    impulseLabel: formatSignedFloat(impulse),
    latestGapLabel: formatSignedPoints(latestShadowGap),
    windowLabel: `${formatAxisTime(firstPoint.sample?.ts)}-${formatAxisTime(latestPoint.sample?.ts)} / dia / ${points.length} pts`,
    linePath: buildSvgLinePath(points),
    areaPath: buildSvgAreaPath(points, baselineY),
    guideLines: [40, 50, 60]
      .filter((value) => value >= minScore && value <= maxScore)
      .map((value) => ({
        value,
        label: `${Math.round(value)}`,
        y: plotBottom - (((value - minScore) / Math.max(maxScore - minScore, 1)) * ySpan),
        emphasis: value === 50,
      })),
    points,
    ticks: tickIndexes.map((index) => ({
      key: `quality-history-tick-${index}`,
      label: points[index]?.label || '--',
    })),
  }
}

export function buildIntradayCorrelationHistoryPanel(payload, options = {}) {
  const selectedModes = Array.isArray(options.selectedModes) ? options.selectedModes : []
  const isLoading = Boolean(options.loading)
  const data = payload && typeof payload === 'object' ? payload : null
  if (!data) return null
  try {
    const availableFactors = Array.isArray(data.available_factors)
      ? data.available_factors
        .map((item) => ({
          factor: String(item?.factor || ''),
          label: String(item?.label || item?.factor || ''),
          block: String(item?.block || ''),
          latestPureCorrelation: toNumber(item?.latest_pure_correlation),
          latestNeuralCorrelation: toNumber(item?.latest_neural_correlation),
          sampleCount: toNumber(item?.sample_count) || 0,
          selected: Boolean(item?.selected),
          neuralStatus: String(item?.neural_status || ''),
        }))
        .filter((item) => item.factor)
      : []

    const requestedModes = new Set(
      selectedModes
        .map((item) => String(item || '').trim().toLowerCase())
        .filter(Boolean),
    )
    const rawSeries = Array.isArray(data.series) ? data.series : []
    const filteredSeries = rawSeries.filter((entry) => {
      const mode = String(entry?.mode || 'pure').trim().toLowerCase()
      return !requestedModes.size || requestedModes.has(mode)
    })
    const flattenedTimestamps = filteredSeries.flatMap((series) => (
      Array.isArray(series?.points)
        ? series.points.map((point) => new Date(point?.timestamp || '').getTime())
        : []
    )).filter(Number.isFinite)
    const uniqueTimestamps = [...new Set(flattenedTimestamps)].sort((left, right) => left - right)
    const hasSeries = uniqueTimestamps.length >= 2 && filteredSeries.length > 0
    const width = 960
    const height = 228
    const plotLeft = 44
    const plotRight = width - 14
    const plotTop = 16
    const plotBottom = 164
    const xSpan = Math.max(plotRight - plotLeft, 1)
    const ySpan = Math.max(plotBottom - plotTop, 1)
    const minTs = uniqueTimestamps[0] || 0
    const maxTs = uniqueTimestamps[uniqueTimestamps.length - 1] || minTs
    const totalSpan = Math.max(maxTs - minTs, 60 * 1000)
    const xFromTs = (ts) => {
      if (!Number.isFinite(ts)) return plotLeft
      return plotLeft + (((ts - minTs) / totalSpan) * xSpan)
    }
    const yFromValue = (value) => {
      const numeric = clamp(toNumber(value) || 0, -1, 1)
      const ratio = (numeric + 1) / 2
      return plotBottom - (ratio * ySpan)
    }

    const factorOrder = availableFactors.map((item) => item.factor)
    const factorIndex = new Map(factorOrder.map((factor, index) => [factor, index]))
    const series = filteredSeries.map((entry, index) => {
      const factor = String(entry?.factor || '')
      const mode = String(entry?.mode || 'pure')
      const color = CORRELATION_SERIES_COLORS[(factorIndex.get(factor) ?? index) % CORRELATION_SERIES_COLORS.length]
      const preparedPoints = (Array.isArray(entry?.points) ? entry.points : [])
        .map((point, pointIndex, list) => {
          const ts = new Date(point?.timestamp || '').getTime()
          const value = toNumber(point?.value)
          if (!Number.isFinite(ts) || !Number.isFinite(value)) return null
          const previous = pointIndex > 0 ? list[pointIndex - 1] : null
          const previousTs = previous ? new Date(previous?.timestamp || '').getTime() : null
          return {
            key: `${entry?.key || factor}-${pointIndex}`,
            ts,
            x: xFromTs(ts),
            y: yFromValue(value),
            value,
            label: formatAxisTime(ts),
            fullLabel: formatTime(ts),
            factorMove: toNumber(point?.factor_move),
            targetReturn: toNumber(point?.target_return),
            predictedReturn: toNumber(point?.predicted_return),
            sensitivity: toNumber(point?.local_sensitivity),
            sampleCount: toNumber(point?.sample_count),
            breakBefore: Number.isFinite(previousTs) && formatDayKey(previousTs) !== formatDayKey(ts),
          }
        })
        .filter(Boolean)
      const latestPoint = preparedPoints[preparedPoints.length - 1] || null
      return {
        key: String(entry?.key || `${factor}:${mode}`),
        factor,
        label: String(entry?.label || factor),
        mode,
        lineStyle: String(entry?.line_style || 'solid'),
        dashArray: mode === 'neural' ? '8 5' : '0',
        color,
        latestValue: toNumber(entry?.latest_value),
        windowMinutes: toNumber(entry?.window_minutes),
        points: preparedPoints,
        path: buildSvgSegmentedLinePath(preparedPoints),
        latestPoint,
        legendLabel: `${String(entry?.label || factor)} ${mode === 'neural' ? 'neural' : 'puro'}`,
      }
    }).filter((entry) => entry.points.length >= 2)

    const selectedSessions = Array.isArray(data.selected_sessions)
      ? data.selected_sessions.map((item) => String(item || '')).filter(Boolean)
      : []
    const lookbackDays = toNumber(data.lookback_days) || 1
    const horizonMinutes = toNumber(data.horizon_minutes) || 5
    const rowCount = toNumber(data.row_count) || 0
    const guideLines = [-1, -0.5, 0, 0.5, 1].map((value) => ({
      value,
      label: `${value > 0 ? '+' : ''}${value.toFixed(1)}`,
      y: yFromValue(value),
      emphasis: value === 0,
    }))
    const baselineY = yFromValue(0)
    const tickIndexes = uniqueTimestamps.length
      ? [...new Set([0, Math.floor((uniqueTimestamps.length - 1) / 2), uniqueTimestamps.length - 1])]
      : []
    const ticks = tickIndexes.map((index) => ({
      key: `corr-tick-${index}`,
      x: xFromTs(uniqueTimestamps[index]),
      label: formatAxisTime(uniqueTimestamps[index]),
    }))
    const latestValues = series
      .map((entry) => entry.latestValue)
      .filter((value) => Number.isFinite(value))
    const averageLatest = latestValues.length
      ? latestValues.reduce((sum, value) => sum + value, 0) / latestValues.length
      : 0
    const toneClass = averageLatest > 0.2 ? 'up' : averageLatest < -0.2 ? 'down' : 'flat'
    const neuralTraining = (data.training && typeof data.training === 'object' ? data.training.neural : null) || {}
    const trainedNeuralCount = Object.values(neuralTraining).filter((item) => String(item?.status || '') === 'trained').length
    const firstTs = uniqueTimestamps[0]
    const lastTs = uniqueTimestamps[uniqueTimestamps.length - 1]
    const status = String(data.status || '')
    const statusLabel = isLoading
      ? 'atualizando'
      : status === 'ready'
        ? 'pronto'
        : 'hist curto'
    const note = selectedModes.includes('neural')
      ? 'Puro = correlacao de Pearson rolante entre a perna e o retorno futuro do XB1. Neural = correlacao rolante entre o retorno previsto pela rede e o retorno realizado.'
      : 'Puro = correlacao de Pearson rolante entre a perna e o retorno futuro do XB1.'

    return {
      width,
      height,
      plotLeft,
      plotRight,
      plotTop,
      plotBottom,
      baselineY,
      guideLines,
      ticks,
      availableFactors,
      series,
      hasSeries,
      toneClass,
      statusLabel,
      headline: `Correlacao intradiaria ${horizonMinutes}m | ${lookbackDays} dia${lookbackDays > 1 ? 's' : ''}`,
      summary: hasSeries
        ? `${series.length} leituras ativas entre ${formatAxisTime(firstTs)} e ${formatAxisTime(lastTs)}. Janela rolante media de ${Math.round(averageFinite(series.map((entry) => entry.windowMinutes)) || 0)} min.`
        : 'Historico ainda curto para montar a serie completa neste recorte.',
      sessionsLabel: selectedSessions.join(' | ') || '--',
      rowCountLabel: `${Math.round(rowCount)} barras`,
      neuralLabel: `${trainedNeuralCount} fator${trainedNeuralCount === 1 ? '' : 'es'} com treino neural`,
      note,
    }
  } catch {
    const lookbackDays = toNumber(data.lookback_days) || 1
    const horizonMinutes = toNumber(data.horizon_minutes) || 5
    const availableFactors = Array.isArray(data.available_factors)
      ? data.available_factors
        .map((item) => ({
          factor: String(item?.factor || ''),
          label: String(item?.label || item?.factor || ''),
        }))
        .filter((item) => item.factor)
      : []
    return {
      width: 960,
      height: 228,
      plotLeft: 44,
      plotRight: 946,
      plotTop: 16,
      plotBottom: 164,
      baselineY: 90,
      guideLines: [],
      ticks: [],
      availableFactors,
      series: [],
      hasSeries: false,
      toneClass: 'flat',
      statusLabel: 'fallback',
      headline: `Correlacao intradiaria ${horizonMinutes}m | ${lookbackDays} dia${lookbackDays > 1 ? 's' : ''}`,
      summary: 'O payload chegou, mas a montagem visual falhou neste refresh.',
      sessionsLabel: Array.isArray(data.selected_sessions) ? data.selected_sessions.join(' | ') : '--',
      rowCountLabel: `${Math.round(toNumber(data.row_count) || 0)} barras`,
      neuralLabel: 'fallback visual ativo',
      note: 'Recarregue ou ajuste os filtros. O backend respondeu e os dados estao disponiveis.',
    }
  }
}

export function humanizeCapturedFactorLabel(key) {
  const raw = String(key || '').trim()
  if (!raw) return '--'
  const syntheticLabels = {
    __xb1_last: 'XB1 futuro',
    __ibov_spot: 'IBOV spot',
  }
  if (syntheticLabels[raw]) return syntheticLabels[raw]
  const forceUpper = new Set([
    'br', 'brl', 'cds', 'cdx', 'clp', 'cnh', 'di', 'dxy', 'eem', 'embiv', 'em',
    'ewz', 'fxi', 'ibov', 'itrx', 'jpy', 'mes', 'move', 'odf', 'ois', 'petr4',
    'spx', 'us', 'vale3', 'vix', 'vvix', 'vxbr', 'wdo', 'win', 'xb1', 'zar',
  ])
  return raw
    .replace(/^__/, '')
    .split('_')
    .filter(Boolean)
    .map((part) => {
      const normalized = String(part || '').trim()
      if (!normalized) return normalized
      const lower = normalized.toLowerCase()
      if (forceUpper.has(lower) || /[0-9]/.test(normalized)) {
        return normalized.toUpperCase()
      }
      return normalized.charAt(0).toUpperCase() + normalized.slice(1)
    })
    .join(' ')
}

export function formatCapturedFactorMetric(value, modeKey) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  const mode = String(modeKey || 'day_pct')
  if (mode === 'rebase_100') {
    return numeric.toLocaleString('pt-BR', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    })
  }
  if (mode === 'delta_raw') {
    const digits = Math.abs(numeric) >= 100 ? 1 : 2
    return numeric.toLocaleString('pt-BR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: 'always',
    })
  }
  const digits = Math.abs(numeric) >= 10 ? 1 : 2
  return `${numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: 'always',
  })}%`
}

export function aggregateCapturedFactorSamplesByMinute(samples) {
  if (!Array.isArray(samples) || !samples.length) return []
  const minuteBuckets = new Map()
  samples
    .filter((sample) => Number.isFinite(sample?.ts))
    .sort((left, right) => left.ts - right.ts)
    .forEach((sample) => {
      const minuteBucketTs = Math.floor(sample.ts / 60000) * 60000
      const previous = minuteBuckets.get(minuteBucketTs)
      if (!previous || sample.ts >= previous.ts) {
        minuteBuckets.set(minuteBucketTs, {
          ...sample,
          minuteBucketTs,
        })
      }
    })
  return [...minuteBuckets.values()]
    .sort((left, right) => left.ts - right.ts)
    .map((sample, index) => ({
      ...sample,
      key: `${sample.key || 'captured'}-m${sample.minuteBucketTs || index}`,
    }))
}

export function extractWorkbookSecurityFromSource(source) {
  const text = String(source || '').trim()
  const prefix = 'reference_asset:excel_fair_value_basket:'
  if (!text.startsWith(prefix)) return null
  return text.slice(prefix.length).trim() || null
}

export function buildCapturedFactorGuideLines(minValue, maxValue, baselineValue, yFromValue, modeKey) {
  const values = new Set([
    minValue,
    maxValue,
    (minValue + maxValue) / 2,
  ])
  if (Number.isFinite(baselineValue) && baselineValue >= minValue && baselineValue <= maxValue) {
    values.add(baselineValue)
  }
  return [...values]
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right)
    .map((value) => ({
      value,
      y: yFromValue(value),
      label: formatCapturedFactorMetric(value, modeKey),
      emphasis: Number.isFinite(baselineValue) && Math.abs(value - baselineValue) <= 1e-9,
    }))
}

export function buildCapturedFactorHistoryPanel(asset, correlationPayload, options = {}) {
  if (!asset || asset.key !== 'win') return null
  const liveHistory = asset?.live_capture_history && typeof asset.live_capture_history === 'object'
    ? asset.live_capture_history
    : {}
  const snapshots = Array.isArray(liveHistory.snapshots)
    ? liveHistory.snapshots
      .map((snapshot) => ({
        ...snapshot,
        ts: new Date(snapshot?.captured_at || '').getTime(),
      }))
      .filter((snapshot) => Number.isFinite(snapshot.ts))
      .sort((left, right) => left.ts - right.ts)
    : []
  if (!snapshots.length) return null

  const labelLookup = new Map()
  const blockLookup = new Map()
  ;(Array.isArray(correlationPayload?.available_factors) ? correlationPayload.available_factors : []).forEach((item) => {
    const factor = String(item?.factor || '').trim()
    if (!factor) return
    labelLookup.set(factor, String(item?.label || factor))
    blockLookup.set(factor, String(item?.block || 'capturado'))
  })

  const factorSamples = new Map()
  const pushSample = (factor, meta, sample) => {
    const key = String(factor || '').trim()
    if (!key || !Number.isFinite(sample?.ts)) return
    const hasRawValue = Number.isFinite(sample?.rawValue)
    const hasDayPct = Number.isFinite(sample?.dayPct)
    if (!hasRawValue && !hasDayPct) return
    if (!factorSamples.has(key)) {
      factorSamples.set(key, {
        factor: key,
        label: String(meta?.label || labelLookup.get(key) || humanizeCapturedFactorLabel(key)),
        block: String(meta?.block || blockLookup.get(key) || 'capturado'),
        points: [],
      })
    }
    factorSamples.get(key).points.push({
      key: `${key}-${factorSamples.get(key).points.length}`,
      ts: sample.ts,
      rawValue: toNumber(sample?.rawValue),
      dayPct: toNumber(sample?.dayPct),
      source: String(sample?.source || ''),
    })
  }

  snapshots.forEach((snapshot) => {
    pushSample('__xb1_last', { label: 'XB1 futuro', block: 'underlying' }, {
      ts: snapshot.ts,
      rawValue: toNumber(snapshot?.current_future_price),
      dayPct: null,
      source: String(snapshot?.current_price_source || ''),
    })
    pushSample('__ibov_spot', { label: 'IBOV spot', block: 'underlying' }, {
      ts: snapshot.ts,
      rawValue: toNumber(snapshot?.current_spot_price),
      dayPct: null,
      source: String(snapshot?.current_spot_source || ''),
    })
    const workbookValues = snapshot?.workbook_values && typeof snapshot.workbook_values === 'object'
      ? snapshot.workbook_values
      : {}
    const workbookSnapshotKeys = new Set(Object.keys(workbookValues).map((security) => String(security || '').trim()).filter(Boolean))
    Object.entries(workbookValues).forEach(([security, dynamic]) => {
      pushSample(`asset::${security}`, {
        label: String(security || '').trim(),
        block: 'planilha',
      }, {
        ts: snapshot.ts,
        rawValue: toNumber(dynamic?.raw_value),
        dayPct: toNumber(dynamic?.daily_change_pct),
        source: String(dynamic?.fallback_source || 'excel_fair_value_basket'),
      })
    })
    const factorValues = snapshot?.factor_values && typeof snapshot.factor_values === 'object'
      ? snapshot.factor_values
      : {}
    Object.entries(factorValues).forEach(([factor, dynamic]) => {
      const source = String(dynamic?.live_source || '')
      const workbookSecurity = extractWorkbookSecurityFromSource(source)
      if (workbookSecurity) {
        if (workbookSnapshotKeys.has(workbookSecurity)) return
        pushSample(`asset::${workbookSecurity}`, {
          label: String(workbookSecurity || '').trim(),
          block: 'planilha',
        }, {
          ts: snapshot.ts,
          rawValue: toNumber(dynamic?.raw_value),
          dayPct: toNumber(dynamic?.daily_change_pct),
          source,
        })
        return
      }
      pushSample(`factor::${factor}`, {
        label: String(dynamic?.label || labelLookup.get(factor) || humanizeCapturedFactorLabel(factor)),
        block: String(dynamic?.block || blockLookup.get(factor) || 'modelo'),
      }, {
        ts: snapshot.ts,
        rawValue: toNumber(dynamic?.raw_value),
        dayPct: toNumber(dynamic?.daily_change_pct),
        source,
      })
    })
  })

  const normalizedFactors = [...factorSamples.values()]
    .map((item) => {
      const scopedPoints = scopeSamplesToTradingSession(aggregateCapturedFactorSamplesByMinute(item.points))
      if (!scopedPoints.length) return null
      const latestPoint = scopedPoints[scopedPoints.length - 1] || null
      const firstRawPoint = scopedPoints.find((point) => Number.isFinite(point?.rawValue)) || null
      const firstRawValue = toNumber(firstRawPoint?.rawValue)
      const latestRawValue = toNumber(latestPoint?.rawValue)
      const latestDayPct = Number.isFinite(toNumber(latestPoint?.dayPct))
        ? toNumber(latestPoint?.dayPct)
        : Number.isFinite(firstRawValue) && Number.isFinite(latestRawValue) && Math.abs(firstRawValue) > 1e-9
          ? ((latestRawValue / firstRawValue) - 1) * 100
          : null
      const latestDeltaRaw = Number.isFinite(firstRawValue) && Number.isFinite(latestRawValue)
        ? latestRawValue - firstRawValue
        : null
      return {
        ...item,
        points: scopedPoints,
        sampleCount: scopedPoints.length,
        latestRawValue,
        latestDayPct,
        latestDeltaRaw,
        searchText: `${item.label} ${item.factor} ${item.block}`.toLowerCase(),
      }
    })
    .filter(Boolean)

  if (!normalizedFactors.length) return null

  const rankedFactors = [...normalizedFactors].sort((left, right) => {
    const leftMagnitude = Math.abs(toNumber(left.latestDayPct) ?? toNumber(left.latestDeltaRaw) ?? 0)
    const rightMagnitude = Math.abs(toNumber(right.latestDayPct) ?? toNumber(right.latestDeltaRaw) ?? 0)
    return rightMagnitude - leftMagnitude
  })
  const availableFactors = [...normalizedFactors].sort((left, right) => (
    String(left.label || '').localeCompare(String(right.label || ''), 'pt-BR')
  ))
  const defaultFactors = rankedFactors
    .slice(0, Math.min(6, rankedFactors.length))
    .map((item) => item.factor)
  const searchNeedle = String(options.filterText || '').trim().toLowerCase()
  const visibleFactors = searchNeedle
    ? availableFactors.filter((item) => item.searchText.includes(searchNeedle))
    : availableFactors
  const factorIndex = new Map(availableFactors.map((item, index) => [item.factor, index]))
  const factorMap = new Map(normalizedFactors.map((item) => [item.factor, item]))
  const requestedFactors = Array.isArray(options.selectedFactorKeys) ? options.selectedFactorKeys : []
  const selectedFactors = requestedFactors.filter((factor) => factorMap.has(factor))
  const resolvedFactors = selectedFactors
  const displayMode = String(options.displayMode || 'day_pct')

  const rawSeries = resolvedFactors
    .map((factor) => {
      const factorState = factorMap.get(factor)
      if (!factorState) return null
      const firstRawPoint = factorState.points.find((point) => Number.isFinite(point?.rawValue)) || null
      const firstRawValue = toNumber(firstRawPoint?.rawValue)
      const seriesPoints = factorState.points
        .map((point, index, list) => {
          const rawValue = toNumber(point?.rawValue)
          const rawDayPct = toNumber(point?.dayPct)
          let value = null
          if (displayMode === 'rebase_100') {
            value = Number.isFinite(rawValue) && Number.isFinite(firstRawValue)
              ? Math.abs(firstRawValue) > 1e-9
                ? (rawValue / firstRawValue) * 100
                : 100 + (rawValue - firstRawValue)
              : null
          } else if (displayMode === 'delta_raw') {
            value = Number.isFinite(rawValue) && Number.isFinite(firstRawValue)
              ? rawValue - firstRawValue
              : null
          } else {
            value = Number.isFinite(rawDayPct)
              ? rawDayPct
              : Number.isFinite(rawValue) && Number.isFinite(firstRawValue) && Math.abs(firstRawValue) > 1e-9
                ? ((rawValue / firstRawValue) - 1) * 100
                : Number.isFinite(rawValue) && Number.isFinite(firstRawValue)
                  ? rawValue - firstRawValue
                  : null
          }
          if (!Number.isFinite(value)) return null
          const previous = index > 0 ? list[index - 1] : null
          const previousTs = previous ? toNumber(previous?.ts) : null
          return {
            key: `${factor}-${index}`,
            ts: point.ts,
            value,
            rawValue,
            dayPct: rawDayPct,
            label: formatAxisTime(point.ts),
            fullLabel: formatTime(point.ts),
            breakBefore: Number.isFinite(previousTs) && formatDayKey(previousTs) !== formatDayKey(point.ts),
          }
        })
        .filter(Boolean)
      if (seriesPoints.length < 2) return null
      const latestValue = toNumber(seriesPoints[seriesPoints.length - 1]?.value)
      return {
        key: `captured-${factor}`,
        factor,
        label: factorState.label,
        block: factorState.block,
        color: CORRELATION_SERIES_COLORS[(factorIndex.get(factor) ?? 0) % CORRELATION_SERIES_COLORS.length],
        points: seriesPoints,
        latestValue,
        latestValueLabel: formatCapturedFactorMetric(latestValue, displayMode),
      }
    })
    .filter(Boolean)

  const flattenedPoints = rawSeries.flatMap((series) => series.points || [])
  const uniqueTimestamps = [...new Set(flattenedPoints.map((point) => point.ts))].sort((left, right) => left - right)
  const hasSeries = uniqueTimestamps.length >= 2 && rawSeries.length > 0
  const width = 960
  const height = 248
  const plotLeft = 44
  const plotRight = width - 14
  const plotTop = 16
  const plotBottom = 180
  const xSpan = Math.max(plotRight - plotLeft, 1)
  const ySpan = Math.max(plotBottom - plotTop, 1)
  const minTs = uniqueTimestamps[0] || 0
  const maxTs = uniqueTimestamps[uniqueTimestamps.length - 1] || minTs
  const totalSpan = Math.max(maxTs - minTs, 60 * 1000)
  const xFromTs = (ts) => {
    if (!Number.isFinite(ts)) return plotLeft
    return plotLeft + (((ts - minTs) / totalSpan) * xSpan)
  }
  const baselineValue = displayMode === 'rebase_100' ? 100 : 0
  const plottedValues = flattenedPoints
    .map((point) => toNumber(point?.value))
    .filter((value) => Number.isFinite(value))
  const minObserved = plottedValues.length ? Math.min(...plottedValues, baselineValue) : baselineValue - 1
  const maxObserved = plottedValues.length ? Math.max(...plottedValues, baselineValue) : baselineValue + 1
  const observedSpan = Math.max(maxObserved - minObserved, 0)
  const padding = observedSpan > 0
    ? observedSpan * 0.14
    : displayMode === 'day_pct'
      ? 0.25
      : displayMode === 'rebase_100'
        ? 1.0
        : 0.5
  const minValue = minObserved - padding
  const maxValue = maxObserved + padding
  const yFromValue = (value) => {
    const numeric = toNumber(value)
    if (!Number.isFinite(numeric)) return plotBottom
    return plotBottom - (((numeric - minValue) / Math.max(maxValue - minValue, 1e-9)) * ySpan)
  }
  const series = rawSeries.map((entry) => {
    const points = entry.points.map((point) => ({
      ...point,
      x: xFromTs(point.ts),
      y: yFromValue(point.value),
    }))
    return {
      ...entry,
      points,
      path: buildSvgSegmentedLinePath(points),
      latestPoint: points[points.length - 1] || null,
      legendLabel: entry.label,
    }
  })
  const tickIndexes = uniqueTimestamps.length
    ? [...new Set([0, Math.floor((uniqueTimestamps.length - 1) / 2), uniqueTimestamps.length - 1])]
    : []
  const ticks = tickIndexes.map((index) => ({
    key: `captured-factor-tick-${index}`,
    x: xFromTs(uniqueTimestamps[index]),
    label: formatAxisTime(uniqueTimestamps[index]),
  }))
  const averageLatest = averageFinite(series.map((item) => toNumber(item.latestValue)).filter(Number.isFinite)) ?? baselineValue
  const toneClass = averageLatest > baselineValue ? 'up' : averageLatest < baselineValue ? 'down' : 'flat'
  const modeLabel = CAPTURED_FACTOR_DISPLAY_OPTIONS.find((option) => option.key === displayMode)?.label || 'var % dia'
  const firstTs = uniqueTimestamps[0]
  const lastTs = uniqueTimestamps[uniqueTimestamps.length - 1]
  return {
    width,
    height,
    plotLeft,
    plotRight,
    plotTop,
    plotBottom,
    baselineY: yFromValue(baselineValue),
    guideLines: buildCapturedFactorGuideLines(minValue, maxValue, baselineValue, yFromValue, displayMode),
    ticks,
    hasSeries,
    toneClass,
    displayMode,
    modeLabel,
    rowCountLabel: `${snapshots.length} snapshots`,
    selectionLabel: `${resolvedFactors.length}/${availableFactors.length} ativos`,
    searchLabel: searchNeedle
      ? `${visibleFactors.length} filtrados`
      : `${availableFactors.length} ativos disponiveis`,
    availableFactors,
    visibleFactors,
    defaultFactors,
    series,
    headline: 'Historico dos ativos capturados',
    summary: hasSeries
      ? `${series.length} series entre ${formatAxisTime(firstTs)} e ${formatAxisTime(lastTs)} usando ${modeLabel}.`
      : 'Selecione pelo menos um ativo com historico suficiente neste pregao.',
    statusLabel: `${resolvedFactors.length} ativos`,
    note: displayMode === 'day_pct'
      ? 'Var % dia prioriza o CHG_PCT_1D capturado da planilha. Quando ele faltar, a serie recompõe a variacao desde o primeiro ponto do pregão.'
      : displayMode === 'rebase_100'
        ? 'Rebase 100 coloca todos os ativos na mesma base intradiaria para comparar trajetorias, mesmo com unidades diferentes.'
        : 'Delta abs mostra o deslocamento contra o primeiro ponto do pregão na unidade original de cada ativo.',
  }
}

export function formatAbsolutePoints(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  const absolute = Math.abs(numeric)
  return absolute.toLocaleString('pt-BR', {
    minimumFractionDigits: absolute >= 1000 ? 0 : 1,
    maximumFractionDigits: absolute >= 1000 ? 0 : 1,
  })
}

export function getFairValueCoreDirection(chart) {
  const currentPrice = toNumber(chart?.currentPrice)
  const coreFairValue = toNumber(chart?.currentFairValue)
  if (!Number.isFinite(currentPrice) || !Number.isFinite(coreFairValue)) return 'neutral'
  if (coreFairValue > currentPrice) return 'bullish'
  if (coreFairValue < currentPrice) return 'bearish'
  return 'neutral'
}

export function getFairValueShadowHaircutPoints(chart, qualityModel) {
  const modelHaircut = toNumber(qualityModel?.shadowHaircutPoints)
  if (Number.isFinite(modelHaircut)) return modelHaircut
  const qualityAdjusted = toNumber(chart?.currentQualityAdjusted)
  const coreFairValue = toNumber(chart?.currentFairValue)
  if (!Number.isFinite(qualityAdjusted) || !Number.isFinite(coreFairValue)) return null
  return qualityAdjusted - coreFairValue
}

export function getFairValueGrossGap(chart) {
  const currentPrice = toNumber(chart?.currentPrice)
  const coreFairValue = toNumber(chart?.currentFairValue)
  return Number.isFinite(currentPrice) && Number.isFinite(coreFairValue)
    ? coreFairValue - currentPrice
    : null
}

export function getFairValueNetGap(chart) {
  const currentPrice = toNumber(chart?.currentPrice)
  const qualityAdjusted = toNumber(chart?.currentQualityAdjusted)
  return Number.isFinite(currentPrice) && Number.isFinite(qualityAdjusted)
    ? qualityAdjusted - currentPrice
    : null
}

export function getFairValueDominantBlockers(qualityModel) {
  return Array.isArray(qualityModel?.explanation?.dominant_blockers)
    ? qualityModel.explanation.dominant_blockers.filter((item) => item && typeof item === 'object')
    : []
}

export function getFairValueConfirmationTriggers(qualityModel) {
  return Array.isArray(qualityModel?.explanation?.confirmation_triggers)
    ? qualityModel.explanation.confirmation_triggers.filter((item) => item && typeof item === 'object')
    : []
}

export function getFairValueAlignedSupportLegs(chart, qualityModel, limit = 3) {
  const coreDirection = getFairValueCoreDirection(chart)
  const rankingDirection = coreDirection === 'bearish' ? 'down' : 'up'
  return getFairValueLegRanking(qualityModel?.coreLegs, 'core', rankingDirection, limit)
}

export function getFairValueFollowThroughStateLabel(qualityModel) {
  const followClass = String(qualityModel?.qualityPulse?.followThroughClass || '')
  if (followClass === 'following') return 'acompanhando'
  if (followClass === 'lagging') return 'atrasado'
  if (followClass === 'leading') return 'adiantado'
  if (followClass === 'negating') return 'negando'
  return 'aguardando'
}

export function getFairValueBlockerPressureTheme(blockers) {
  const themeMap = {
    rates: 'rates_pressure',
    curve_medium_long: 'rates_pressure',
    us_rates: 'rates_pressure',
    funding: 'funding_vol_pressure',
    volatility: 'funding_vol_pressure',
    fx: 'fx_pressure',
    credit: 'brazil_risk_pressure',
    credit_brazil: 'brazil_risk_pressure',
    sovereign_credit: 'brazil_risk_pressure',
    brazil_relative: 'brazil_risk_pressure',
    credit_shadow: 'brazil_risk_pressure',
    corporate_credit: 'brazil_risk_pressure',
    em_stress: 'brazil_risk_pressure',
    bond_quality: 'brazil_risk_pressure',
    equity_brazil: 'local_absorption',
    equity: 'global_beta',
    commodities: 'global_beta',
  }
  const themeScores = {}
  ;(Array.isArray(blockers) ? blockers : []).forEach((item) => {
    const key = String(item?.key || '')
    const theme = themeMap[key] || 'mixed'
    const amount = Math.abs(toNumber(item?.adverse_points) ?? toNumber(item?.impact_points) ?? 0)
    themeScores[theme] = (themeScores[theme] || 0) + amount
  })
  return Object.entries(themeScores).sort((left, right) => right[1] - left[1])[0]?.[0] || 'mixed'
}

export function getFairValueCompositeRegimeLabel(chart, qualityModel) {
  const coreDirection = getFairValueCoreDirection(chart)
  const blockers = getFairValueDominantBlockers(qualityModel)
  const theme = getFairValueBlockerPressureTheme(blockers)
  const followState = getFairValueFollowThroughStateLabel(qualityModel)
  const shadowHaircutPoints = getFairValueShadowHaircutPoints(chart, qualityModel)

  if (coreDirection === 'bullish') {
    if (theme === 'rates_pressure' || theme === 'funding_vol_pressure') return 'risk_on_fragile com rates_pressure'
    if (theme === 'local_absorption' || followState === 'negando') return 'macro bullish divergente / absorcao local'
    if (shadowHaircutPoints < -8 || followState === 'atrasado') return 'upside existe, mas nao e compra limpa'
    if (followState === 'acompanhando') return 'macro bullish em confirmacao'
    return 'macro bullish com confirmacao parcial'
  }

  if (coreDirection === 'bearish') {
    if (theme === 'brazil_risk_pressure' || theme === 'funding_vol_pressure') return 'risk_off confirmado por risco'
    if (theme === 'local_absorption' || followState === 'negando') return 'macro bearish divergente / suporte local'
    if (shadowHaircutPoints > 8 || followState === 'atrasado') return 'downside existe, mas nao e venda limpa'
    if (followState === 'acompanhando') return 'macro bearish em confirmacao'
    return 'macro bearish com confirmacao parcial'
  }

  return 'macro neutro / transicao'
}

export function getFairValueLocalAcceptanceLabel(chart, qualityModel) {
  const coreDirection = getFairValueCoreDirection(chart)
  const brazilEquity = toNumber(qualityModel?.coreLegs?.equity_brazil?.contribution_points) ?? 0
  const brazilCredit = toNumber(qualityModel?.coreLegs?.credit_brazil?.contribution_points) ?? 0

  if (coreDirection === 'bullish') {
    if (brazilEquity >= 8 && brazilCredit >= 4) return 'confirma'
    if (brazilEquity <= -4 || brazilCredit <= -4) return 'diverge'
    return 'misto'
  }

  if (coreDirection === 'bearish') {
    if (brazilEquity <= -8 && brazilCredit <= -4) return 'confirma'
    if (brazilEquity >= 4 || brazilCredit >= 4) return 'diverge'
    return 'misto'
  }

  return 'misto'
}

export function describeFairValueHaircut(coreDirection, shadowHaircutPoints) {
  if (!Number.isFinite(shadowHaircutPoints)) return 'shadow sem ajuste material sobre o gap bruto'
  const cutsConviction = coreDirection === 'bullish'
    ? shadowHaircutPoints < -0.5
    : coreDirection === 'bearish'
      ? shadowHaircutPoints > 0.5
      : false
  const reinforcesCore = coreDirection === 'bullish'
    ? shadowHaircutPoints > 0.5
    : coreDirection === 'bearish'
      ? shadowHaircutPoints < -0.5
      : false
  if (cutsConviction) return `shadow corta ${formatAbsolutePoints(shadowHaircutPoints)} pts do gap bruto`
  if (reinforcesCore) return `shadow reforca ${formatAbsolutePoints(shadowHaircutPoints)} pts no vetor do core`
  return 'shadow esta quase neutro sobre o gap bruto'
}

export function buildFairValueFollowThroughRead(qualityModel) {
  const followClass = String(qualityModel?.qualityPulse?.followThroughClass || '')
  if (followClass === 'following') return 'O preco acompanha bem a qualidade.'
  if (followClass === 'lagging') return 'O preco ainda esta atrasado contra a qualidade.'
  if (followClass === 'leading') return 'O preco correu na frente da qualidade.'
  if (followClass === 'negating') return 'O preco segue negando a leitura de qualidade.'
  return 'O preco ainda responde pouco ao sinal de qualidade.'
}

export function buildFairValueSupportBalanceCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const coreDirection = getFairValueCoreDirection(chart)
  const supports = getFairValueAlignedSupportLegs(chart, qualityModel, 3)
  const blockers = getFairValueDominantBlockers(qualityModel).slice(0, 3)
  const supportRead = formatNaturalList(supports.map((item) => item.label)) || 'sem perna dominante'
  const blockerRead = formatNaturalList(blockers.map((item) => item.label)) || 'sem bloqueio material'
  if (coreDirection === 'bearish') {
    return `Vetores que empurram a convergencia: ${supportRead}. Suportes que ainda seguram a venda: ${blockerRead}.`
  }
  return `Suportes que puxam a convergencia: ${supportRead}. Bloqueios que ainda barram a convergencia: ${blockerRead}.`
}

export function buildFairValuePriceDriverCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const coreDirection = getFairValueCoreDirection(chart)
  const blockers = getFairValueDominantBlockers(qualityModel).slice(0, 2)
  const supports = getFairValueAlignedSupportLegs(chart, qualityModel, 2)
  const blockerRead = formatNaturalList(blockers.map((item) => item.label))
  const supportRead = formatNaturalList(supports.map((item) => item.label))

  if (coreDirection === 'bearish') {
    if (blockerRead && supportRead) {
      return `Hoje o preco responde mais ao bloco vendedor ${supportRead} do que aos alivios de ${blockerRead}. O downside existe, mas ainda disputa espaco com suportes residuais.`
    }
    if (supportRead) return `Hoje o preco responde mais ao bloco vendedor ${supportRead}, e a leitura de baixa ganha tracao.`
    return 'Sem driver dominante novo; o preco depende mais de continuidade do que de uma perna isolada.'
  }

  if (blockerRead && supportRead) {
    return `Hoje o preco responde mais a ${blockerRead} do que ao bloco ${supportRead}. As pernas positivas existem, mas ainda nao fazem preco cheias.`
  }
  if (supportRead) return `Hoje o preco ja comeca a responder ao bloco ${supportRead}, e a convergencia ganha mais tracao.`
  return 'Sem driver dominante novo; o preco depende mais de continuidade do que de uma perna isolada.'
}

export function buildFairValueCompositeRegimeCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const label = getFairValueCompositeRegimeLabel(chart, qualityModel)
  const coreDirection = getFairValueCoreDirection(chart)
  const blockers = getFairValueDominantBlockers(qualityModel).slice(0, 2)
  const blockerRead = formatNaturalList(blockers.map((item) => item.label))
  const followState = getFairValueFollowThroughStateLabel(qualityModel)
  const shadowHaircutPoints = getFairValueShadowHaircutPoints(chart, qualityModel)
  const regimeLead = label.startsWith('upside ') || label.startsWith('downside ')
    ? `Leitura ${label}.`
    : `Regime ${label}.`
  const cleanlinessRead = coreDirection === 'bullish'
    ? shadowHaircutPoints < -8
      ? label.includes('nao e compra limpa')
        ? 'O shadow ainda corta parte do gap bruto.'
        : 'O upside existe, mas nao e compra limpa.'
      : shadowHaircutPoints > 8
        ? 'O shadow reforca bem o vetor comprador.'
        : 'O shadow esta quase neutro sobre o gap.'
    : coreDirection === 'bearish'
      ? shadowHaircutPoints > 8
        ? label.includes('nao e venda limpa')
          ? 'O shadow ainda corta parte da conviccao vendedora.'
          : 'O downside existe, mas nao e venda limpa.'
        : shadowHaircutPoints < -8
          ? 'O shadow reforca a perna de baixa.'
          : 'O shadow esta quase neutro sobre o gap.'
      : 'O shadow ainda nao cria assimetria suficiente.'
  const followRead = followState === 'acompanhando'
    ? 'Preco acompanhando.'
    : followState === 'atrasado'
      ? 'Preco atrasado.'
      : followState === 'negando'
        ? 'Preco negando.'
        : followState === 'adiantado'
          ? 'Preco adiantado.'
          : 'Preco aguardando confirmacao.'
  const blockerNote = blockerRead
    ? `Hoje ${blockerRead} ainda fazem parte importante do price action.`
    : 'Sem bloqueio dominante material agora.'
  return `${regimeLead} ${cleanlinessRead} ${followRead} ${blockerNote}`
}

export function buildFairValueLocalConfirmationCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const coreDirection = getFairValueCoreDirection(chart)
  const localAcceptance = getFairValueLocalAcceptanceLabel(chart, qualityModel)
  if (coreDirection === 'bearish') {
    if (localAcceptance === 'confirma') {
      return 'EWZ, SMALL/ICON e o bloco local de credito acompanham melhor a pressao de baixa, entao o Brasil confirma a leitura macro.'
    }
    if (localAcceptance === 'diverge') {
      return 'EWZ, IFNC e pesos locais como PETR/VALE ainda sustentam parte do mercado, entao o Brasil alivia a leitura de baixa.'
    }
    return 'EWZ, SMALL/ICON, IFNC e os pesos locais entregam um quadro misto; o Brasil local nao invalida o macro, mas tambem nao carimba a venda.'
  }
  if (localAcceptance === 'confirma') {
    return 'EWZ, IFNC/SMALL e o bloco local de risco ajudam a validar o suporte macro; PETR/VALE deixam a leitura mais aceita.'
  }
  if (localAcceptance === 'diverge') {
    return 'EWZ, SMALL/ICON e o credito Brasil ainda freiam a convergencia; PETR/VALE ajudam pontualmente, mas o local nao confirma por completo o macro.'
  }
  return 'EWZ, IFNC/SMALL e pesos locais como PETR/VALE entregam confirmacao parcial; o macro existe, mas a aceitacao local ainda e incompleta.'
}

export function buildFairValueModelCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const currentPrice = toNumber(chart.currentPrice)
  const coreFairValue = toNumber(chart.currentFairValue)
  const qualityAdjusted = toNumber(chart.currentQualityAdjusted)
  const coreGap = Number.isFinite(currentPrice) && Number.isFinite(coreFairValue) ? coreFairValue - currentPrice : null
  const netGap = Number.isFinite(currentPrice) && Number.isFinite(qualityAdjusted) ? qualityAdjusted - currentPrice : null
  const shadowHaircutPoints = getFairValueShadowHaircutPoints(chart, qualityModel)
  const implicitSentiment = formatImplicitSentiment(qualityModel.implicitSentiment)
  const coreDirection = getFairValueCoreDirection(chart)
  const followState = getFairValueFollowThroughStateLabel(qualityModel)
  if (!Number.isFinite(currentPrice) || !Number.isFinite(coreFairValue)) {
    return `${implicitSentiment}; sem preco suficiente para comparar com o fair value agora.`
  }
  const gapRead = Number.isFinite(coreGap)
    ? `Core FV roda ${formatSignedPoints(coreGap)} contra o preco`
    : `Core FV referencia ${formatPrice(coreFairValue)}`
  const netGapRead = Number.isFinite(netGap)
    ? `gap liquido fica em ${formatSignedPoints(netGap)}`
    : 'gap liquido sem leitura suficiente'
  const followRead = followState === 'acompanhando'
    ? 'Preco acompanha esse vetor.'
    : followState === 'atrasado'
      ? 'Preco ainda esta atrasado contra esse vetor.'
      : followState === 'negando'
        ? 'Preco ainda nega esse vetor.'
        : followState === 'adiantado'
          ? 'Preco corre na frente da qualidade.'
          : 'Preco ainda espera confirmacao.'
  return `${gapRead}; ${describeFairValueHaircut(coreDirection, shadowHaircutPoints)} e ${netGapRead}. ${followRead} Leitura ${implicitSentiment}.`
}

export function buildFairValueReactionCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const currentPrice = toNumber(chart.currentPrice)
  const bandLow = toNumber(chart.currentBandLow)
  const bandHigh = toNumber(chart.currentBandHigh)
  const ribbonLow = toNumber(chart.currentQualityRibbonLow)
  const ribbonHigh = toNumber(chart.currentQualityRibbonHigh)
  const convergenceProbability = toNumber(qualityModel.convergenceProbability)
  const regimeBreakProbability = toNumber(qualityModel.regimeBreakProbability)
  let bandState = 'fora das bandas informadas'
  if (Number.isFinite(currentPrice) && Number.isFinite(bandLow) && Number.isFinite(bandHigh)) {
    bandState = currentPrice < bandLow
      ? 'abaixo da banda principal'
      : currentPrice > bandHigh
        ? 'acima da banda principal'
        : 'dentro da banda principal'
  }
  let ribbonState = 'sem ribbon util'
  if (Number.isFinite(currentPrice) && Number.isFinite(ribbonLow) && Number.isFinite(ribbonHigh)) {
    ribbonState = currentPrice < ribbonLow
      ? 'abaixo do quality ribbon'
      : currentPrice > ribbonHigh
        ? 'acima do quality ribbon'
        : 'dentro do quality ribbon'
  }
  const probabilityRead = (convergenceProbability || 0) > ((regimeBreakProbability || 0) + 0.06)
    ? 'A convergencia ainda domina o risco de ruptura.'
    : (regimeBreakProbability || 0) > ((convergenceProbability || 0) + 0.06)
      ? 'O risco de ruptura ainda compete forte com a convergencia.'
      : 'Convergencia e ruptura seguem equilibradas.'
  return `${buildFairValueFollowThroughRead(qualityModel)} O preco esta ${bandState} e ${ribbonState}; convergencia em ${formatConfidenceScore((convergenceProbability || 0) * 100)} contra break em ${formatConfidenceScore((regimeBreakProbability || 0) * 100)}. ${probabilityRead}`
}

export function buildFairValueConvergenceCommentary(chart, qualityModel) {
  if (!chart || !qualityModel) return '--'
  const coreDirection = getFairValueCoreDirection(chart)
  const blockers = getFairValueDominantBlockers(qualityModel)
  const triggers = getFairValueConfirmationTriggers(qualityModel)
  const topBlockers = blockers.slice(0, 2).map((item) => item.label)
  if (coreDirection === 'bullish') {
    if (topBlockers.length) {
      return `Para o preco convergir para cima, os bloqueios abaixo precisam aliviar. Hoje ${topBlockers.join(' e ')} ainda fazem mais preco contra o modelo.`
    }
    return triggers.length
      ? 'O vetor comprador esta relativamente limpo; agora a convergencia depende mais de continuidade do que de remover um bloqueio dominante.'
      : 'O vetor comprador esta limpo e sem bloqueio material novo no snapshot atual.'
  }
  if (coreDirection === 'bearish') {
    if (topBlockers.length) {
      return `Para o preco convergir para baixo, os bloqueios abaixo precisam parar de sustentar o mercado. Hoje ${topBlockers.join(' e ')} ainda aliviam parte da pressao do modelo.`
    }
    return triggers.length
      ? 'O vetor vendedor esta relativamente limpo; a convergencia depende mais de continuidade do que de remover um bloqueio dominante.'
      : 'O vetor vendedor esta limpo e sem bloqueio material novo no snapshot atual.'
  }
  return 'O modelo esta quase neutro; use os gatilhos abaixo como confirmacao antes de assumir convergencia.'
}

export function buildFairValueCurveDeskCommentary(curveConditions) {
  if (!curveConditions || typeof curveConditions !== 'object' || !Object.keys(curveConditions).length) return '--'
  const shape = formatCurveShapeLabel(curveConditions.state)
  const macroRegime = formatCurveMacroRegime(curveConditions)
  const regimeRanking = getCurveRegimeRanking(curveConditions, 2)
  const inclination = String(curveConditions.inclination_label || '--')
  const mediumLongBias = formatBiasLabel(curveConditions.medium_long_bias)
  const shortDelta = formatCurvePercent(curveConditions.short_day_change_pct ?? curveConditions.short_change)
  const bellyDelta = formatCurvePercent(curveConditions.belly_day_change_pct ?? curveConditions.belly_change)
  const longDelta = formatCurvePercent(curveConditions.long_day_change_pct ?? curveConditions.long_change)
  const slopeDelta = formatCurvePercent(curveConditions.slope_change)
  const inflationDelta = formatCurvePercent(curveConditions.inflation_day_change_pct)
  const fiscalRead = curveConditions.fiscal_risk_flag ? 'com alerta de risco fiscal/duration' : 'sem stress fiscal dominante'
  const regimeRead = regimeRanking.length
    ? `${macroRegime} (${regimeRanking[0].probability.toFixed(0)}%)`
    : macroRegime
  const shapeRead = curveConditions.state === 'bull_steepening'
    ? 'As duas pontas aliviaram, mas a curta caiu mais do que a longa, entao a inclinacao subiu.'
    : curveConditions.state === 'bear_steepening'
      ? 'A curva abriu com inclinacao maior; hoje o belly e a longa pressionam mais do que a curta.'
      : curveConditions.state === 'bull_flattening'
        ? 'A curva cedeu, mas a longa caiu mais do que a curta, achatando a inclinacao.'
        : curveConditions.state === 'bear_flattening'
          ? 'A curva abriu, mas a curta subiu mais do que a longa, achatando a inclinacao.'
          : 'A leitura de inclinacao esta sendo definida pelo balanceamento entre curta, longa e slope.'
  const inflationRead = Number.isFinite(toNumber(curveConditions.inflation_day_change_pct))
    ? `A inflacao implicita media roda em ${inflationDelta}.`
    : 'Sem inflacao implicita suficiente para complementar a leitura agora.'
  const probableDriver = curveConditions.probable_driver ? `Motivo provavel: ${curveConditions.probable_driver}.` : ''
  return `${shape} em regime de ${regimeRead}, com curva ${inclination} e medio-longo ${mediumLongBias}; curta ${shortDelta}, belly ${bellyDelta}, longa ${longDelta} e slope ${slopeDelta}, ${fiscalRead}. ${shapeRead} ${inflationRead} ${probableDriver}`.trim()
}

export function buildFairValueShadowCommentary(qualityModel, chart) {
  if (!qualityModel || !chart) return '--'
  const coherenceScore = toNumber(qualityModel.coherenceScore)
  const alignment = toNumber(qualityModel.coreShadowAlignment)
  const riskQuality = toNumber(qualityModel.riskQualityScore)
  const price = toNumber(chart.currentPrice)
  const qualityAdjusted = toNumber(chart.currentQualityAdjusted)
  const qualityGap = Number.isFinite(price) && Number.isFinite(qualityAdjusted) ? qualityAdjusted - price : null
  const qualityGapRead = Number.isFinite(qualityGap)
    ? qualityGap > 0
      ? 'o q-adjusted ainda deixa upside contra o preco'
      : qualityGap < 0
        ? 'o q-adjusted ja penaliza o preco corrente'
        : 'o q-adjusted esta em linha com o preco'
    : 'o q-adjusted nao traz leitura adicional clara'
  const riskQualityRead = Number.isFinite(riskQuality)
    ? riskQuality <= 15
      ? 'penalidade qualitativa baixa'
      : riskQuality >= 60
        ? 'penalidade qualitativa alta'
        : 'penalidade qualitativa moderada'
    : 'penalidade qualitativa sem leitura clara'
  return `Coherence em ${formatCompactFloat((coherenceScore || 0) * 100)} e alinhamento core-shadow em ${formatCompactFloat((alignment || 0) * 100)}; risk quality ${formatConfidenceScore(riskQuality)} (${riskQualityRead}) e ${qualityGapRead}.`
}

export function buildFairValueShadowSectionLead(shadowLegs) {
  const dominant = getFairValueShadowRanking(shadowLegs, 1)[0]
  if (!dominant) return 'Sem perna shadow dominante com impacto material na janela recente.'
  return `${dominant.label} e a principal fonte de ajuste qualitativo na janela recente, com impacto de qualidade ${formatSignedPoints(dominant.qualityImpactValue)} e leitura de banda ${formatCompactFloat(dominant.bandImpactValue)}.`
}

export function formatValuePosition(value) {
  if (value === 'above_value') return 'acima do value'
  if (value === 'below_value') return 'abaixo do value'
  if (value === 'inside_value') return 'dentro do value'
  return 'sem value'
}

export function formatFlowRegimeLabel(value) {
  if (!value) return '--'
  if (value === 'initiative_break_buy') return 'break comprador'
  if (value === 'initiative_break_sell') return 'break vendedor'
  if (value === 'responsive_rejection_buy') return 'rejeicao compra'
  if (value === 'responsive_rejection_sell') return 'rejeicao venda'
  if (value === 'absorption_buy') return 'absorcao compra'
  if (value === 'absorption_sell') return 'absorcao venda'
  if (value === 'divergence_buy') return 'divergencia compra'
  if (value === 'divergence_sell') return 'divergencia venda'
  if (value === 'exhaustion_buy') return 'exaustao compra'
  if (value === 'exhaustion_sell') return 'exaustao venda'
  if (value === 'balanced_transition') return 'transicao balanceada'
  if (value === 'inactive') return 'inativo'
  return String(value).replaceAll('_', ' ')
}

export function formatConfidenceScore(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  return `${Math.round(numeric)}%`
}

export function formatCompactSignedQuantity(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  const abs = Math.abs(numeric)
  if (abs >= 1_000_000) {
    return `${numeric >= 0 ? '+' : '-'}${(abs / 1_000_000).toFixed(1)}M`
  }
  if (abs >= 1_000) {
    return `${numeric >= 0 ? '+' : '-'}${(abs / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`
  }
  return formatSignedQuantity(numeric)
}

export function formatProjectedMove(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  const abs = Math.abs(numeric)
  const maximumFractionDigits = abs >= 1000 ? 0 : abs >= 10 ? 1 : 3
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: maximumFractionDigits,
    maximumFractionDigits,
    signDisplay: 'always',
  })
}

export function getValueCohortColor(cohortKey) {
  if (cohortKey === 'foreign') return '#60a5fa'
  if (cohortKey === 'retail') return '#34d399'
  return '#fbbf24'
}

export function getPoolOverlayKey(poolType) {
  if (poolType === 'short_cover_above') return 'short_cover'
  if (poolType === 'long_flush_below') return 'long_flush'
  if (poolType === 'bull_trap_offer' || poolType === 'sell_trap_bid') return 'traps'
  if (poolType === 'offer_wall_near_price' || poolType === 'bid_wall_near_price') return 'walls'
  if (poolType === 'inventory_balance_poc') return 'inventory_poc'
  return 'two_way'
}

export function getPoolOverlayMeta(poolType) {
  const overlayKey = getPoolOverlayKey(poolType)
  if (overlayKey === 'short_cover') {
    return {
      shortLabel: 'SC',
      label: 'short cover',
      description: 'fechamento forcado de vendidos se a banda acima for rompida',
      color: '#60a5fa',
      fill: '#60a5fa',
      stroke: '#60a5fa',
    }
  }
  if (overlayKey === 'long_flush') {
    return {
      shortLabel: 'LF',
      label: 'long flush',
      description: 'liquidacao forcada de comprados se a banda abaixo for perdida',
      color: '#f97316',
      fill: '#f97316',
      stroke: '#f97316',
    }
  }
  if (overlayKey === 'traps') {
    return {
      shortLabel: 'TR',
      label: 'trap zone',
      description: 'regiao de armadilha com inventario vulneravel a reversao e stop',
      color: '#fbbf24',
      fill: '#fbbf24',
      stroke: '#fbbf24',
    }
  }
  if (overlayKey === 'walls') {
    return {
      shortLabel: 'WL',
      label: 'wall',
      description: 'parede defensiva de bid ou oferta perto do preco atual',
      color: '#a78bfa',
      fill: '#a78bfa',
      stroke: '#a78bfa',
    }
  }
  if (overlayKey === 'inventory_poc') {
    return {
      shortLabel: 'POC',
      label: 'inventory POC',
      description: 'nivel de maior concentracao de inventario sintetico na janela',
      color: '#22c55e',
      fill: '#22c55e',
      stroke: '#22c55e',
    }
  }
  return {
    shortLabel: 'TW',
    label: 'two-way',
    description: 'zona de inventario bilateral sem vies claro de squeeze',
    color: '#94a3b8',
    fill: '#94a3b8',
    stroke: '#94a3b8',
  }
}

export function getGammaOverlayKey(region) {
  const kind = String(region?.kind || '')
  const gammaSign = String(region?.gamma_sign || '')
  if (kind === 'special_region') return 'special'
  if (gammaSign === 'positive') return 'positive'
  if (gammaSign === 'negative') return 'negative'
  return 'special'
}

export function getGammaOverlayMeta(region) {
  const overlayKey = getGammaOverlayKey(region)
  return GAMMA_OVERLAY_OPTIONS.find((item) => item.key === overlayKey) || GAMMA_OVERLAY_OPTIONS[2]
}

export function getAssetFairValueSummary(asset) {
  const alignment = asset?.options_flow_alignment || {}
  const latestSample = asset?.fair_value_history?.latest_sample || {}
  const fairValuePrice = toNumber(alignment?.fair_value_price)
    ?? toNumber(latestSample?.fair_value_final_future)
  const currentPrice = toNumber(alignment?.current_price)
    ?? toNumber(latestSample?.current_future_price)
    ?? toNumber(asset?.latest_price)
  let mispricingValue = toNumber(alignment?.mispricing_value)
  if (!Number.isFinite(mispricingValue) && Number.isFinite(currentPrice) && Number.isFinite(fairValuePrice)) {
    mispricingValue = currentPrice - fairValuePrice
  }
  const mispricingZscore = toNumber(alignment?.mispricing_zscore)
    ?? toNumber(latestSample?.mispricing_zscore)
  const fairValueState = alignment?.fair_value_state
    || latestSample?.market_regime
    || null
  const nearestRegionLabel = alignment?.nearest_region?.display_label || null
  const nearestRegionPrice = toNumber(alignment?.nearest_region?.price)
  if (!Number.isFinite(fairValuePrice)) return null
  return {
    fairValuePrice,
    currentPrice: Number.isFinite(currentPrice) ? currentPrice : null,
    mispricingValue: Number.isFinite(mispricingValue) ? mispricingValue : null,
    mispricingZscore: Number.isFinite(mispricingZscore) ? mispricingZscore : null,
    fairValueState,
    nearestRegionLabel,
    nearestRegionPrice: Number.isFinite(nearestRegionPrice) ? nearestRegionPrice : null,
  }
}

export function formatPoolTriggerLabel(value) {
  if (value === 'buy') return 'gatilho de compra'
  if (value === 'sell') return 'gatilho de venda'
  return 'gatilho bilateral'
}

export function formatPoolDirectionLabel(value) {
  if (value === 'up') return 'projeta alta'
  if (value === 'down') return 'projeta queda'
  return 'simetrico'
}

export function formatPoolAggregationScopeLabel(value) {
  if (value === 'market_total') return 'mercado total'
  if (value === 'cohort_context') return 'coorte'
  return 'escopo misto'
}

export function getValueLevelTypeMeta(levelKey) {
  if (levelKey === 'value_area_low') {
    return { label: 'VAL', dashArray: '7 5', strokeWidth: 1.3 }
  }
  if (levelKey === 'value_area_high') {
    return { label: 'VAH', dashArray: '7 5', strokeWidth: 1.3 }
  }
  return { label: 'POC', dashArray: null, strokeWidth: 2.1 }
}

export function getIndicatorMetricMeta(metricKey) {
  if (metricKey === 'efficiency') {
    return { label: 'eff', dashArray: '7 5', opacity: 0.92 }
  }
  return { label: 'press', dashArray: '0', opacity: 0.95 }
}

export function pressureClass(value) {
  const numeric = toNumber(value) || 0
  if (numeric >= 20) return 'buy'
  if (numeric <= -20) return 'sell'
  return 'balanced'
}

export function flowRegimeClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.regime_state || '')
  const bias = String(entry.bias_side || '')
  if (state.includes('buy') || bias === 'buy') return 'buy'
  if (state.includes('sell') || bias === 'sell') return 'sell'
  return 'balanced'
}

export function formatLevelDefenseStateLabel(value) {
  if (!value) return '--'
  if (value === 'support_defense') return 'defesa de suporte'
  if (value === 'resistance_defense') return 'defesa de resistencia'
  if (value === 'accepted_value') return 'value aceito'
  if (value === 'rejection_above_value') return 'rejeicao acima'
  if (value === 'rejection_below_value') return 'rejeicao abaixo'
  if (value === 'responsive_rejection') return 'rejeicao responsiva'
  if (value === 'two_sided_balance') return 'defesa bilateral'
  if (value === 'mixed_level_map') return 'mapa misto'
  if (value === 'active_bid_defense') return 'defesa compradora'
  if (value === 'active_offer_defense') return 'defesa vendedora'
  if (value === 'memory_support') return 'memoria de suporte'
  if (value === 'memory_resistance') return 'memoria de resistencia'
  if (value === 'inactive') return 'inativo'
  return String(value).replaceAll('_', ' ')
}

export function levelDefenseClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.primary_state || '')
  const bias = String(entry.bias_side || '')
  if (bias === 'buy' || state.includes('support') || state.includes('below')) return 'buy'
  if (bias === 'sell' || state.includes('resistance') || state.includes('above')) return 'sell'
  return 'balanced'
}

export function formatConcentrationStateLabel(value) {
  if (!value) return '--'
  if (value === 'single_name_push') return 'single name push'
  if (value === 'concentrated_drive') return 'drive concentrado'
  if (value === 'two_way_participation') return 'duas pontas'
  if (value === 'broad_participation') return 'participacao ampla'
  if (value === 'mixed_participation') return 'participacao mista'
  if (value === 'inactive') return 'inativo'
  return String(value).replaceAll('_', ' ')
}

export function concentrationClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.state || '')
  const bias = String(entry.bias_side || '')
  const breadth = toNumber(entry.breadth_score) || 0
  const concentration = toNumber(entry.concentration_score) || 0
  if (state === 'broad_participation') return 'buy'
  if (state === 'single_name_push' || state === 'concentrated_drive') {
    return bias === 'buy' ? 'buy' : bias === 'sell' ? 'sell' : 'balanced'
  }
  if (breadth >= concentration + 10) return 'buy'
  if (concentration >= breadth + 10) return bias === 'buy' ? 'buy' : bias === 'sell' ? 'sell' : 'sell'
  return 'balanced'
}

export function formatLocalPackageStateLabel(value) {
  if (!value) return '--'
  if (value === 'risk_on_package') return 'pacote risk-on'
  if (value === 'risk_off_package') return 'pacote risk-off'
  if (value === 'partial_risk_on') return 'parcial risk-on'
  if (value === 'partial_risk_off') return 'parcial risk-off'
  if (value === 'mixed_local_package') return 'pacote misto'
  if (value === 'neutral_transition') return 'transicao neutra'
  return String(value).replaceAll('_', ' ')
}

export function localPackageClass(value) {
  const numeric = toNumber(value) || 0
  if (numeric >= 12) return 'buy'
  if (numeric <= -12) return 'sell'
  return 'balanced'
}

export function formatStructuralDivergenceStateLabel(value) {
  if (!value) return '--'
  if (value === 'confirmed_bullish') return 'confirmacao bullish'
  if (value === 'confirmed_bearish') return 'confirmacao bearish'
  if (value === 'bullish_non_confirmation') return 'bullish non-confirmation'
  if (value === 'bearish_non_confirmation') return 'bearish non-confirmation'
  if (value === 'cross_asset_dissonance') return 'dissonancia cross-asset'
  if (value === 'mixed_confirmation') return 'confirmacao mista'
  if (value === 'neutral_balance') return 'equilibrio neutro'
  return String(value).replaceAll('_', ' ')
}

export function structuralDivergenceClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.state || '')
  const bias = String(entry.bias_side || '')
  if (state.includes('bullish') || bias === 'buy') return 'buy'
  if (state.includes('bearish') || bias === 'sell') return 'sell'
  return 'balanced'
}

export function formatContinuationStateLabel(value) {
  if (!value) return '--'
  if (value === 'continuation_up') return 'continuacao alta'
  if (value === 'continuation_down') return 'continuacao baixa'
  if (value === 'reversal_up') return 'reversao para cima'
  if (value === 'reversal_down') return 'reversao para baixo'
  if (value === 'balanced_transition') return 'transicao balanceada'
  return String(value).replaceAll('_', ' ')
}

export function continuationClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.state || '')
  const bias = String(entry.bias_side || '')
  const continuation = toNumber(entry.continuation_probability) || 0
  const reversal = toNumber(entry.reversal_probability) || 0
  if (state.includes('continuation')) return bias === 'sell' ? 'sell' : 'buy'
  if (state.includes('reversal')) return bias === 'sell' ? 'sell' : 'buy'
  if (continuation >= reversal + 8) return bias === 'sell' ? 'sell' : 'buy'
  if (reversal >= continuation + 8) return bias === 'sell' ? 'sell' : 'buy'
  return 'balanced'
}

export function formatTradeSignalLabel(value) {
  if (!value) return '--'
  if (value === 'strong_buy') return 'strong buy'
  if (value === 'buy') return 'buy'
  if (value === 'cautious_buy') return 'cautious buy'
  if (value === 'strong_sell') return 'strong sell'
  if (value === 'sell') return 'sell'
  if (value === 'cautious_sell') return 'cautious sell'
  if (value === 'watch_only') return 'watch only'
  if (value === 'neutral') return 'neutral'
  return String(value).replaceAll('_', ' ')
}

export function formatNewsMarkerLabel(value) {
  if (!value) return '--'
  if (value === 'risk-on') return 'risk-on'
  if (value === 'risk-off') return 'risk-off'
  if (value === 'neutral') return 'neutral'
  return String(value).replaceAll('_', ' ')
}

export function formatNewsBiasLabel(value) {
  if (!value) return '--'
  if (value === 'buy') return 'bias buy'
  if (value === 'sell') return 'bias sell'
  if (value === 'watch') return 'bias watch'
  return String(value).replaceAll('_', ' ')
}

export function formatNewsAlignmentLabel(value) {
  if (!value) return '--'
  if (value === 'aligned') return 'news alinhada'
  if (value === 'conflicted') return 'news conflitante'
  if (value === 'neutral') return 'news neutra'
  return String(value).replaceAll('_', ' ')
}

export function formatTradeActionLabel(value) {
  if (!value) return '--'
  if (value === 'buy') return 'entrada compradora'
  if (value === 'sell') return 'entrada vendedora'
  if (value === 'stand_aside') return 'sem trade'
  return String(value).replaceAll('_', ' ')
}

export function formatEntryStyleLabel(value) {
  if (!value) return '--'
  if (value === 'continuation') return 'continuation'
  if (value === 'reversal') return 'reversal'
  if (value === 'breakout') return 'breakout'
  if (value === 'fade') return 'fade'
  if (value === 'no_trade') return 'no trade'
  return String(value).replaceAll('_', ' ')
}

export function formatLiquidityProviderLabel(value) {
  if (!value) return '--'
  if (value === 'foreign_absorbing_offers') return 'estrangeiro absorvendo oferta'
  if (value === 'foreign_absorbing_bids') return 'estrangeiro absorvendo bid'
  if (value === 'retail_serving_liquidity') return 'varejo servindo liquidez'
  if (value === 'two_way_liquidity') return 'liquidez bilateral'
  if (value === 'thin_liquidity') return 'liquidez fina'
  if (value === 'mixed_liquidity') return 'liquidez mista'
  return String(value).replaceAll('_', ' ')
}

export function formatTrapStateLabel(value) {
  if (!value) return '--'
  if (value === 'bull_trap_risk') return 'risco de bull trap'
  if (value === 'sell_trap_risk') return 'risco de sell trap'
  if (value === 'balanced_liquidity') return 'sem trap dominante'
  return String(value).replaceAll('_', ' ')
}

export function formatSqueezeStateLabel(value) {
  if (!value) return '--'
  if (value === 'short_squeeze_risk') return 'risco de short squeeze'
  if (value === 'long_liquidation_risk') return 'risco de liquidacao longa'
  if (value === 'contained_squeeze') return 'squeeze contido'
  return String(value).replaceAll('_', ' ')
}

export function formatStopRunStateLabel(value) {
  if (!value) return '--'
  if (value === 'stop_run_above_risk') return 'stop acima vulneravel'
  if (value === 'stop_run_below_risk') return 'stop abaixo vulneravel'
  if (value === 'contained_stop_risk') return 'stop risk contido'
  return String(value).replaceAll('_', ' ')
}

export function formatRetailMicrostructureLabel(value) {
  if (!value) return '--'
  if (value === 'retail_buying_top') return 'varejo comprando topo'
  if (value === 'retail_selling_bottom') return 'varejo vendendo fundo'
  if (value === 'retail_adding_against_trend') return 'varejo contra tendencia'
  if (value === 'retail_balanced') return 'varejo balanceado'
  return String(value).replaceAll('_', ' ')
}

export function formatLiquidityRegionRoleLabel(value) {
  if (!value) return '--'
  if (value === 'inventory_poc') return 'POC inventario'
  if (value === 'bid_support_inventory') return 'suporte comprador'
  if (value === 'offer_resistance_inventory') return 'resistencia vendedora'
  if (value === 'bull_trap_offer_zone') return 'zona bull trap'
  if (value === 'sell_trap_bid_zone') return 'zona sell trap'
  if (value === 'two_way_inventory') return 'inventario bilateral'
  return String(value).replaceAll('_', ' ')
}

export function formatLiquidityPoolStateLabel(value) {
  if (!value) return '--'
  if (value === 'short_cover_pool_dominant') return 'pool de short cover'
  if (value === 'long_flush_pool_dominant') return 'pool de long flush'
  if (value === 'two_sided_stop_coil') return 'coil bilateral de stops'
  if (value === 'inventory_balance_near_price') return 'inventario balanceado no preco'
  if (value === 'distributed_inventory') return 'inventario distribuido'
  return String(value).replaceAll('_', ' ')
}

export function formatLiquidityPoolTypeLabel(value) {
  if (!value) return '--'
  if (value === 'short_cover_above') return 'short cover acima'
  if (value === 'long_flush_below') return 'long flush abaixo'
  if (value === 'offer_wall_near_price') return 'parede de oferta'
  if (value === 'bid_wall_near_price') return 'parede de bid'
  if (value === 'inventory_balance_poc') return 'POC de inventario'
  if (value === 'bull_trap_offer') return 'oferta de bull trap'
  if (value === 'sell_trap_bid') return 'bid de sell trap'
  if (value === 'two_way_inventory') return 'inventario bilateral'
  return String(value).replaceAll('_', ' ')
}

export function formatGammaRoleLabel(value) {
  if (!value) return '--'
  if (value === 'pinning_support') return 'pinning'
  if (value === 'acceleration_zone') return 'aceleracao'
  if (value === 'inventory_balance') return 'balance'
  if (value === 'vol_release') return 'vol release'
  return String(value).replaceAll('_', ' ')
}

export function formatGammaStateLabel(value) {
  if (!value) return '--'
  if (value === 'positive_gamma_near') return 'gamma + perto'
  if (value === 'positive_gamma_far') return 'gamma + longe'
  if (value === 'negative_gamma_near') return 'gamma - perto'
  if (value === 'negative_gamma_far') return 'gamma - longe'
  if (value === 'balance_region_near') return 'balance perto'
  if (value === 'balance_region_far') return 'balance longe'
  return String(value).replaceAll('_', ' ')
}

export function formatFairValueStateLabel(value) {
  if (!value) return '--'
  if (value === 'overpriced_vs_fair_value') return 'acima do fair value'
  if (value === 'underpriced_vs_fair_value') return 'abaixo do fair value'
  if (value === 'fair_value_balanced') return 'equilibrado'
  return String(value).replaceAll('_', ' ')
}

export function formatLocationLabel(value) {
  if (!value) return '--'
  if (value === 'above') return 'acima'
  if (value === 'below') return 'abaixo'
  if (value === 'near') return 'prox'
  return String(value).replaceAll('_', ' ')
}

export function formatReferenceLabel(reference) {
  if (!reference || typeof reference !== 'object') return '--'
  const label = String(reference.label || '')
  if (!label) return '--'
  return label.replaceAll('_', ' ')
}

export function thermometerClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const signal = String(entry.signal || '')
  const action = String(entry.action || '')
  const bias = String(entry.bias_side || '')
  const directional = toNumber(entry.directional_score) || 0
  if (signal.includes('buy') || action === 'buy' || bias === 'buy' || directional >= 18) return 'buy'
  if (signal.includes('sell') || action === 'sell' || bias === 'sell' || directional <= -18) return 'sell'
  return 'balanced'
}

export function riskClass(value) {
  const numeric = toNumber(value) || 0
  if (numeric >= 70) return 'sell'
  if (numeric <= 45) return 'buy'
  return 'balanced'
}

export function newsBiasClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const bias = String(entry.bias || '')
  const score = toNumber(entry.directional_score) || 0
  if (bias === 'buy' || score >= 12) return 'buy'
  if (bias === 'sell' || score <= -12) return 'sell'
  return 'balanced'
}

export function newsAlignmentClass(value) {
  if (value === 'aligned') return 'buy'
  if (value === 'conflicted') return 'sell'
  return 'balanced'
}

export function liquidityIntelClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const trapBias = String(entry.trap_bias_side || '')
  const squeezeBias = String(entry.squeeze_bias_side || '')
  const stopBias = String(entry.stop_run_bias_side || '')
  const bias = String(entry.bias_side || '')
  const state = String(entry.state || '')
  if (
    trapBias === 'buy'
    || squeezeBias === 'buy'
    || stopBias === 'buy'
    || bias === 'buy'
    || state.includes('buy')
  ) {
    return 'buy'
  }
  if (
    trapBias === 'sell'
    || squeezeBias === 'sell'
    || stopBias === 'sell'
    || bias === 'sell'
    || state.includes('sell')
    || state.includes('trap')
  ) {
    return 'sell'
  }
  return 'balanced'
}

export function liquidityPoolClass(entry) {
  if (!entry || typeof entry !== 'object') return 'balanced'
  const state = String(entry.state || '')
  const bias = String(entry.bias_side || '')
  const shortRisk = toNumber(entry.short_cover_risk_score) || 0
  const longRisk = toNumber(entry.long_flush_risk_score) || 0
  if (state.includes('short_cover') || bias === 'buy' || shortRisk >= longRisk + 8) return 'buy'
  if (state.includes('long_flush') || bias === 'sell' || longRisk >= shortRisk + 8) return 'sell'
  return 'balanced'
}

export function formatAnnotationTypeLabel(value) {
  if (!value) return '--'
  if (value === 'bull_trap') return 'bull trap'
  if (value === 'sell_trap') return 'sell trap'
  if (value === 'retail_buying_top') return 'varejo compra topo'
  if (value === 'retail_selling_bottom') return 'varejo vende fundo'
  if (value === 'foreign_buy_aligned') return 'estrangeiro compra cenario'
  if (value === 'foreign_sell_aligned') return 'estrangeiro vende cenario'
  if (value === 'short_squeeze') return 'short squeeze'
  if (value === 'long_flush') return 'long flush'
  if (value === 'thin_liquidity') return 'liquidez fina'
  if (value === 'foreign_absorption_buy') return 'absorcao compra'
  if (value === 'foreign_absorption_sell') return 'absorcao venda'
  if (value === 'stop_above') return 'stop acima'
  if (value === 'stop_below') return 'stop abaixo'
  if (value === 'retail_contra_trend') return 'varejo contratendencia'
  return String(value).replaceAll('_', ' ')
}

export function formatAnnotationShortLabel(value) {
  if (!value) return '--'
  if (value === 'bull_trap') return 'BT'
  if (value === 'sell_trap') return 'ST'
  if (value === 'retail_buying_top') return 'VT'
  if (value === 'retail_selling_bottom') return 'VF'
  if (value === 'foreign_buy_aligned') return 'FC'
  if (value === 'foreign_sell_aligned') return 'FV'
  if (value === 'short_squeeze') return 'SQ'
  if (value === 'long_flush') return 'LF'
  if (value === 'thin_liquidity') return 'LQ'
  if (value === 'foreign_absorption_buy') return 'AB'
  if (value === 'foreign_absorption_sell') return 'AV'
  if (value === 'stop_above') return 'SA'
  if (value === 'stop_below') return 'SB'
  if (value === 'retail_contra_trend') return 'CT'
  return String(value).slice(0, 2).toUpperCase()
}

export function annotationToneClass(value) {
  const text = String(value || '')
  if (text.includes('buy') || text.includes('sell_trap') || text.includes('short_squeeze') || text.includes('stop_below')) return 'buy'
  if (text.includes('sell') || text.includes('bull_trap') || text.includes('long_flush') || text.includes('stop_above')) return 'sell'
  return 'balanced'
}

export function formatDivergenceStateLabel(value) {
  if (!value) return '--'
  if (value === 'aligned_buy') return 'alinhado compra'
  if (value === 'aligned_sell') return 'alinhado venda'
  if (value === 'foreign_buy_vs_retail_sell') return 'gringa compra x varejo vende'
  if (value === 'foreign_sell_vs_retail_buy') return 'gringa vende x varejo compra'
  if (value === 'foreign_dominant_buy') return 'gringa domina compra'
  if (value === 'foreign_dominant_sell') return 'gringa domina venda'
  if (value === 'retail_dominant_buy') return 'varejo domina compra'
  if (value === 'retail_dominant_sell') return 'varejo domina venda'
  if (value === 'mixed_transition') return 'transicao mista'
  if (value === 'inactive') return 'inativo'
  return String(value).replaceAll('_', ' ')
}

export function divergenceClass(value) {
  const numeric = toNumber(value) || 0
  if (numeric >= 14) return 'buy'
  if (numeric <= -14) return 'sell'
  return 'balanced'
}

export function computeBucketDivergenceMetrics(metrics) {
  const foreign = metrics?.foreign || {}
  const retail = metrics?.retail || {}
  const foreignPressure = toNumber(foreign.pressureScore) || 0
  const retailPressure = toNumber(retail.pressureScore) || 0
  const foreignNet = toNumber(foreign.netQuantity) || 0
  const retailNet = toNumber(retail.netQuantity) || 0
  const foreignStrength = clamp(
    (Math.abs(foreignPressure) * 0.48)
      + ((Math.abs(toNumber(foreign.efficiencyScore) || 0)) * 0.24)
      + ((toNumber(foreign.confidenceScore) || 0) * 0.16)
      + ((clamp(toNumber(foreign.grossShare) || 0, 0, 1)) * 100 * 0.12),
    0,
    100,
  )
  const retailStrength = clamp(
    (Math.abs(retailPressure) * 0.48)
      + ((Math.abs(toNumber(retail.efficiencyScore) || 0)) * 0.24)
      + ((toNumber(retail.confidenceScore) || 0) * 0.16)
      + ((clamp(toNumber(retail.grossShare) || 0, 0, 1)) * 100 * 0.12),
    0,
    100,
  )
  const foreignDirection = foreignPressure >= 8 || foreignNet > 0 ? 1 : foreignPressure <= -8 || foreignNet < 0 ? -1 : 0
  const retailDirection = retailPressure >= 8 || retailNet > 0 ? 1 : retailPressure <= -8 || retailNet < 0 ? -1 : 0
  const sharedStrength = Math.min(foreignStrength, retailStrength)
  const pressureGap = Math.abs(foreignPressure - retailPressure)
  let alignmentScore = 0
  let divergenceScore = 0
  if (foreignDirection !== 0 && foreignDirection === retailDirection) {
    alignmentScore = foreignDirection * clamp((0.72 * sharedStrength) + (0.28 * pressureGap), 0, 100)
  } else if (foreignDirection !== 0 && retailDirection !== 0 && foreignDirection !== retailDirection) {
    divergenceScore = foreignDirection * clamp((0.72 * sharedStrength) + (0.28 * pressureGap), 0, 100)
  } else {
    alignmentScore = clamp((foreignStrength * foreignDirection) - (retailStrength * retailDirection), -100, 100)
  }

  let state = 'mixed_transition'
  if (foreignStrength < 10 && retailStrength < 10) {
    state = 'inactive'
  } else if (foreignDirection !== 0 && foreignDirection === retailDirection) {
    state = foreignDirection > 0 ? 'aligned_buy' : 'aligned_sell'
  } else if (foreignDirection === 1 && retailDirection === -1) {
    state = 'foreign_buy_vs_retail_sell'
  } else if (foreignDirection === -1 && retailDirection === 1) {
    state = 'foreign_sell_vs_retail_buy'
  } else if (foreignStrength >= retailStrength + 14) {
    state = foreignDirection > 0 ? 'foreign_dominant_buy' : foreignDirection < 0 ? 'foreign_dominant_sell' : 'mixed_transition'
  } else if (retailStrength >= foreignStrength + 14) {
    state = retailDirection > 0 ? 'retail_dominant_buy' : retailDirection < 0 ? 'retail_dominant_sell' : 'mixed_transition'
  }

  return {
    alignmentScore,
    divergenceScore,
    leadScore: clamp((foreignStrength * foreignDirection) - (retailStrength * retailDirection), -100, 100),
    state,
  }
}

export function classifyBucketResponse(netRatio, priceRatio, alignment) {
  if (Math.abs(netRatio) < 0.08) return 'inactive'
  if (Math.abs(netRatio) >= 0.35 && Math.abs(priceRatio) <= 0.18) return 'absorption'
  if (alignment < 0 && Math.abs(netRatio) >= 0.22) return 'divergence'
  if (alignment > 0 && Math.abs(netRatio) >= 0.2 && Math.abs(priceRatio) >= 0.35) return 'initiative'
  return 'balanced'
}

export function classifyBucketEfficiency(netQuantity, efficiencyScore, absorptionScore, fragilityScore, alignment, priceMovePoints) {
  if (Math.abs(netQuantity) < 0.000001) return 'inactive'
  if (absorptionScore >= 55) return netQuantity > 0 ? 'absorbed_buy' : 'absorbed_sell'
  if (fragilityScore >= 55 && Math.abs(priceMovePoints) > 0) return priceMovePoints > 0 ? 'fragile_up' : 'fragile_down'
  if (efficiencyScore >= 30) return netQuantity > 0 ? 'efficient_buy' : 'efficient_sell'
  if (alignment < 0 && Math.abs(netQuantity) > 0) return 'non_confirming'
  return 'mixed'
}

export function resolveBucketValuePosition(closePrice, cohortValue) {
  const close = toNumber(closePrice)
  const valueLow = toNumber(cohortValue?.value_area_low)
  const valueHigh = toNumber(cohortValue?.value_area_high)
  if (!Number.isFinite(close) || !Number.isFinite(valueLow) || !Number.isFinite(valueHigh)) return 'unavailable'
  if (close < valueLow) return 'below_value'
  if (close > valueHigh) return 'above_value'
  return 'inside_value'
}

export function classifyBucketFlowRegime(metricEntry, cohortValue, candle) {
  const grossQuantity = toNumber(metricEntry?.grossQuantity) || 0
  const netQuantity = toNumber(metricEntry?.netQuantity) || 0
  const pressureScore = toNumber(metricEntry?.pressureScore) || 0
  const efficiencyScore = toNumber(metricEntry?.efficiencyScore) || 0
  const absorptionScore = toNumber(metricEntry?.absorptionScore) || 0
  const fragilityScore = toNumber(metricEntry?.fragilityScore) || 0
  const confidenceScore = toNumber(metricEntry?.confidenceScore) || 0
  const grossShare = toNumber(metricEntry?.grossShare) || 0
  const eventCount = toNumber(metricEntry?.eventCount) || 0
  const responseState = String(metricEntry?.responseState || 'inactive')
  const efficiencyState = String(metricEntry?.efficiencyState || 'inactive')
  const currentPosition = resolveBucketValuePosition(candle?.close, cohortValue)
  const netRatioScore = toNumber(cohortValue?.net_ratio_score) || 0

  const biasSide = pressureScore >= 6 || netQuantity > 0
    ? 'buy'
    : pressureScore <= -6 || netQuantity < 0
      ? 'sell'
      : 'neutral'

  let baseSignalStrength = (
    (Math.abs(pressureScore) * 0.34)
    + (Math.abs(efficiencyScore) * 0.24)
    + (Math.max(absorptionScore, fragilityScore) * 0.16)
    + (confidenceScore * 0.14)
    + (clamp(grossShare, 0, 1) * 100 * 0.12)
  )
  baseSignalStrength = clamp(baseSignalStrength, 0, 100)

  let regimeState = 'balanced_transition'
  let regimeConfidence = baseSignalStrength
  let hasSignal = true
  if (grossQuantity <= 0 || eventCount <= 0) {
    regimeState = 'inactive'
    regimeConfidence = 0
    hasSignal = false
  } else if (Math.abs(pressureScore) < 12 && Math.abs(efficiencyScore) < 10 && Math.max(absorptionScore, fragilityScore) < 20) {
    regimeState = 'inactive'
    regimeConfidence = Math.min(regimeConfidence, 24)
  } else if (responseState === 'absorption' || absorptionScore >= 55) {
    regimeState = biasSide !== 'neutral' ? `absorption_${biasSide}` : 'absorption'
    regimeConfidence = clamp(regimeConfidence + 8, 0, 100)
  } else if (
    (
      biasSide === 'buy'
      && Math.abs(pressureScore) >= 30
      && Math.abs(efficiencyScore) >= 22
      && currentPosition === 'above_value'
    )
    || (
      biasSide === 'sell'
      && Math.abs(pressureScore) >= 30
      && Math.abs(efficiencyScore) >= 22
      && currentPosition === 'below_value'
    )
    || (
      responseState === 'initiative'
      && Math.abs(efficiencyScore) >= 24
      && biasSide !== 'neutral'
    )
  ) {
    regimeState = biasSide !== 'neutral' ? `initiative_break_${biasSide}` : 'initiative_break'
    regimeConfidence = clamp(regimeConfidence + 10, 0, 100)
  } else if (
    (biasSide === 'buy' && currentPosition === 'below_value' && Math.abs(pressureScore) >= 18)
    || (biasSide === 'sell' && currentPosition === 'above_value' && Math.abs(pressureScore) >= 18)
  ) {
    regimeState = biasSide !== 'neutral' ? `responsive_rejection_${biasSide}` : 'responsive_rejection'
    regimeConfidence = clamp(regimeConfidence + 6, 0, 100)
  } else if (responseState === 'divergence' || efficiencyState === 'non_confirming') {
    regimeState = biasSide !== 'neutral' ? `divergence_${biasSide}` : 'divergence'
    regimeConfidence = clamp(regimeConfidence + 4, 0, 100)
  } else if (fragilityScore >= 55 || efficiencyState.startsWith('fragile')) {
    regimeState = biasSide !== 'neutral' ? `exhaustion_${biasSide}` : 'exhaustion'
    regimeConfidence = clamp(regimeConfidence + 5, 0, 100)
  } else {
    regimeState = 'balanced_transition'
    regimeConfidence = Math.min(regimeConfidence, 52)
  }

  const regimeScoreMap = {
    initiative_break_buy: 95,
    responsive_rejection_buy: 70,
    absorption_buy: 42,
    divergence_buy: 22,
    exhaustion_buy: 14,
    balanced_transition: 0,
    inactive: 0,
    exhaustion_sell: -14,
    divergence_sell: -22,
    absorption_sell: -42,
    responsive_rejection_sell: -70,
    initiative_break_sell: -95,
  }
  const regimeScore = regimeScoreMap[regimeState] ?? 0
  const rationale = [
    `pressure ${Math.round(pressureScore)}`,
    `eff ${Math.round(efficiencyScore)}`,
    responseState,
    currentPosition === 'unavailable' ? 'sem value' : currentPosition.replaceAll('_', ' '),
    regimeState.startsWith('absorption')
      ? `abs ${Math.round(absorptionScore)}`
      : regimeState.startsWith('exhaustion')
        ? `frag ${Math.round(fragilityScore)}`
        : `skew ${Math.round(netRatioScore)}`,
  ].join(' | ')

  return {
    regimeState,
    regimeScore,
    confidenceScore: regimeConfidence,
    hasSignal,
    biasSide,
    currentPosition,
    responseState,
    efficiencyState,
    rationale,
  }
}
