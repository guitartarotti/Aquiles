<template>
  <div class="peb-root">
    <div class="peb-header">
      <span class="peb-title">Pinning vs Expansion</span>
      <div class="peb-controls">
        <span class="peb-underlying">{{ shortUnderlying }}</span>
        <button type="button" class="peb-btn" :class="{ loading }" :disabled="loading" @click="reload">
          {{ loading ? '...' : 'Reload' }}
        </button>
      </div>
    </div>

    <div v-if="error && !snapshot" class="peb-empty">{{ error }}</div>
    <div v-else-if="!snapshot" class="peb-empty">Waiting for enough option, IV and intraday data.</div>

    <template v-else>
      <div class="peb-top">
        <div class="peb-battle-card">
          <div class="peb-battle-head">
            <div class="peb-score-block left">
              <span class="peb-score-label">Pinning</span>
              <span class="peb-score-value">{{ formatScore(snapshot.pinningScore) }}</span>
            </div>
            <div class="peb-score-center">
              <span class="peb-state">{{ snapshot.state }}</span>
              <span class="peb-badge" :class="snapshot.badgeTone">{{ snapshot.badge }}</span>
            </div>
            <div class="peb-score-block right">
              <span class="peb-score-label">Expansion</span>
              <span class="peb-score-value">{{ formatScore(snapshot.expansionScore) }}</span>
            </div>
          </div>

          <div class="peb-battle-bar">
            <div class="peb-battle-track">
              <div class="peb-battle-fill pin" :style="{ width: `${snapshot.pinningScore}%` }"></div>
              <div class="peb-battle-fill exp" :style="{ width: `${snapshot.expansionScore}%` }"></div>
              <div class="peb-battle-divider"></div>
              <div class="peb-battle-indicator" :style="{ left: `${snapshot.battlePosition}%` }"></div>
            </div>
            <div class="peb-battle-scale">
              <span>Pinning</span>
              <span>Balanced</span>
              <span>Expansion</span>
            </div>
          </div>

          <div class="peb-reading">{{ snapshot.reading }}</div>

          <div class="peb-meta-row">
            <span>Dominante pinning: <b>{{ snapshot.dominantPinningLabel }}</b></span>
            <span>Dominante expansion: <b>{{ snapshot.dominantExpansionLabel }}</b></span>
          </div>
        </div>

        <div class="peb-summary-grid">
          <div class="peb-kpi">
            <span class="peb-kpi-label">Battle</span>
            <span class="peb-kpi-value" :class="battleTone(snapshot.battleScore)">{{ signed(snapshot.battleScore, 1) }}</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Nivel critico</span>
            <span class="peb-kpi-value">{{ formatLevel(snapshot.breakoutLevel) }}</span>
            <span class="peb-kpi-sub">{{ snapshot.breakoutLabel }}</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Retorno ao pin</span>
            <span class="peb-kpi-value">{{ formatLevel(snapshot.returnLevel) }}</span>
            <span class="peb-kpi-sub">{{ snapshot.returnLabel }}</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Spot</span>
            <span class="peb-kpi-value">{{ formatLevel(snapshot.spot) }}</span>
            <span class="peb-kpi-sub">{{ snapshot.sessionStamp }}</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">IV ATM</span>
            <span class="peb-kpi-value">{{ pct(snapshot.latest.iv_atm) }}</span>
            <span class="peb-kpi-sub" :class="deltaTone(snapshot.ivDelta15mPts)">{{ signed(snapshot.ivDelta15mPts, 2) }} pts / 15m</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Vol of vol</span>
            <span class="peb-kpi-value">{{ formatScore(snapshot.surfaceMotionScore) }}</span>
            <span class="peb-kpi-sub" :class="deltaTone(snapshot.surfaceMotionDelta)">{{ signed(snapshot.surfaceMotionDelta, 1) }} vs 15m</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Trend efficiency</span>
            <span class="peb-kpi-value">{{ formatScore(snapshot.trendEfficiencyScore) }}</span>
            <span class="peb-kpi-sub">{{ snapshot.dayRangeLabel }}</span>
          </div>
          <div class="peb-kpi">
            <span class="peb-kpi-label">Fluxo dir.</span>
            <span class="peb-kpi-value">{{ formatScore(snapshot.directionalFlowScore) }}</span>
            <span class="peb-kpi-sub">{{ snapshot.flowDirectionLabel }}</span>
          </div>
        </div>
      </div>

      <div v-if="snapshot.alerts.length" class="peb-alerts">
        <span v-for="alert in snapshot.alerts" :key="alert" class="peb-alert-pill">{{ alert }}</span>
      </div>

      <div class="peb-history-block">
        <div class="peb-block-head">
          <span class="peb-block-title">Historico intraday</span>
          <span class="peb-block-sub">{{ battleChartLabel }}</span>
        </div>
        <div class="peb-history-wrap" ref="battleWrap">
          <canvas v-if="battleChartHistory.length > 1" ref="battleCanvas" class="peb-history-canvas"></canvas>
          <div v-else class="peb-history-empty">Waiting for 1m history from today.</div>
        </div>
        <div class="peb-history-footer">
          <span class="peb-line-key"><i class="peb-line-chip pin"></i> Pinning</span>
          <span class="peb-line-key"><i class="peb-line-chip exp"></i> Expansion</span>
        </div>
      </div>

      <div class="peb-columns">
        <div class="peb-column">
          <div class="peb-block-head">
            <span class="peb-block-title">Forcas de pinning</span>
            <span class="peb-block-sub">{{ snapshot.pinningRegime }}</span>
          </div>
          <div v-for="item in snapshot.pinningComponents" :key="item.key" class="peb-factor-row">
            <span class="peb-factor-name">{{ item.label }}</span>
            <div class="peb-factor-track">
              <div class="peb-factor-bar pin" :style="{ width: `${clamp(item.score, 0, 100)}%` }"></div>
            </div>
            <span class="peb-factor-score">{{ formatScore(item.score) }}</span>
          </div>
        </div>

        <div class="peb-column">
          <div class="peb-block-head">
            <span class="peb-block-title">Forcas de expansion</span>
            <span class="peb-block-sub">{{ snapshot.expansionRegime }}</span>
          </div>
          <div v-for="item in snapshot.expansionComponents" :key="item.key" class="peb-factor-row">
            <span class="peb-factor-name">{{ item.label }}</span>
            <div class="peb-factor-track">
              <div class="peb-factor-bar exp" :style="{ width: `${clamp(item.score, 0, 100)}%` }"></div>
            </div>
            <span class="peb-factor-score">{{ formatScore(item.score) }}</span>
          </div>
        </div>
      </div>

      <div class="peb-footer-note">
        Fluxo direcional e agressao usam proxy intraday de fluxo de opcoes e acao de preco do XB1.
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getVolIndexHistory, getVolumeActivity } from '@/api/options'

const props = defineProps({
  modelData: { type: Object, default: null },
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const VOV_COMPONENTS = [
  { key: 'atm', mode: 'log', weight: 0.25 },
  { key: 'skew', mode: 'diff', weight: 0.25 },
  { key: 'putWing', mode: 'log', weight: 0.20 },
  { key: 'callWing', mode: 'log', weight: 0.15 },
  { key: 'term', mode: 'diff', weight: 0.15 },
]

const WINDOW_5 = { minutes: 5, weight: 0.4 }
const WINDOW_15 = { minutes: 15, weight: 0.6 }
const AUTO_REFRESH_MS = 120_000
const MIN_FETCH_INTERVAL_MS = 75_000
const BATTLE_PAD = { top: 16, right: 14, bottom: 30, left: 46 }
const BATTLE_HEIGHT = 150

const loading = ref(false)
const error = ref(null)
const dailyHistory = ref([])
const intradayHistory = ref([])
const flowEvents = ref([])
const battleWrap = ref(null)
const battleCanvas = ref(null)

let refreshTimer = null
let lastLoadAt = 0

const underlying = computed(() => props.underlyingSecurity || props.modelData?.underlying_security || 'IBOVE Index')
const shortUnderlying = computed(() => {
  const raw = String(underlying.value || '')
  if (!raw) return 'IBOV'
  return raw.replace(/\s+Index$/i, '')
})

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, Number(value)))
}

function safeNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function mean(values) {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function std(values) {
  if (values.length < 2) return null
  const avg = mean(values)
  if (avg == null) return null
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length
  return Math.sqrt(Math.max(variance, 0))
}

function erf(value) {
  const sign = value < 0 ? -1 : 1
  const abs = Math.abs(value)
  const t = 1 / (1 + 0.3275911 * abs)
  const a1 = 0.254829592
  const a2 = -0.284496736
  const a3 = 1.421413741
  const a4 = -1.453152027
  const a5 = 1.061405429
  const poly = (((((a5 * t) + a4) * t) + a3) * t + a2) * t + a1
  const y = 1 - (poly * t * Math.exp(-(abs * abs)))
  return sign * y
}

function normalCdf(z) {
  return 0.5 * (1 + erf(z / Math.sqrt(2)))
}

function scoreFromZ(z) {
  return clamp(normalCdf(z) * 100, 0, 100)
}

function normalizeVolRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || normalized.reference_price_at || '').trim()
  const date = String(normalized.date || capturedAt.slice(0, 10) || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  const price = safeNumber(normalized.reference_price ?? normalized.spot ?? normalized.reference_spot)
  normalized.captured_at = capturedAt || null
  normalized.date = date || null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = date || null
  normalized._price = price
  return normalized
}

function normalizeFlowEvent(event) {
  const normalized = { ...(event || {}) }
  const capturedAt = String(normalized.captured_at || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = String(normalized.session_date || capturedAt.slice(0, 10) || '').trim() || null
  normalized._spot = safeNumber(normalized.spot_price)
  normalized._strike = safeNumber(normalized.strike)
  normalized._volume = Math.max(safeNumber(normalized.volume_delta) || 0, 0)
  normalized._delta = Math.abs(safeNumber(normalized.observed_delta) || 0.5)
  normalized._days = safeNumber(normalized.days_to_maturity) || null
  normalized._side = String(normalized.put_call || '').toUpperCase() === 'P' ? 'P' : 'C'
  return normalized
}

function levelFor(componentKey, record) {
  if (!record) return null
  if (componentKey === 'atm') return safeNumber(record.iv_atm)
  if (componentKey === 'skew') {
    const skew = safeNumber(record.skew_25d)
    if (skew != null) return skew
    const put25 = safeNumber(record.iv_25d_put)
    const call25 = safeNumber(record.iv_25d_call)
    return put25 != null && call25 != null ? (put25 - call25) : null
  }
  if (componentKey === 'putWing') return safeNumber(record.iv_10d_put ?? record.iv_15d_put)
  if (componentKey === 'callWing') return safeNumber(record.iv_10d_call ?? record.iv_15d_call)
  if (componentKey === 'term') {
    const term = Array.isArray(record.term_structure) ? record.term_structure : []
    const values = term
      .map(item => safeNumber(item?.iv_atm))
      .filter(value => value != null)
    if (values.length >= 2) {
      const near = values[0]
      const rest = values.slice(1)
      const restMean = mean(rest)
      return restMean == null ? null : near - restMean
    }
    const nearAtm = safeNumber(record.iv_atm)
    const medium = safeNumber(record.monthly_term_30d_iv)
    return nearAtm != null && medium != null ? (nearAtm - medium) : null
  }
  return null
}

function buildReturns(values, mode) {
  const returns = []
  for (let index = 1; index < values.length; index += 1) {
    const previous = values[index - 1]
    const current = values[index]
    if (previous == null || current == null) continue
    if (mode === 'log') {
      if (previous <= 0 || current <= 0) continue
      returns.push(Math.log(current / previous))
    } else {
      returns.push(current - previous)
    }
  }
  return returns
}

function trailingRecords(records, index, minutes) {
  if (minutes == null) return records.slice(0, index + 1)
  const currentEpoch = records[index]?._epoch
  if (currentEpoch == null) return []
  const minEpoch = currentEpoch - (minutes * 60 * 1000)
  let start = index
  while (start > 0) {
    const epoch = records[start - 1]?._epoch
    if (epoch == null || epoch < minEpoch) break
    start -= 1
  }
  return records.slice(start, index + 1)
}

function bucketRecordsByMinute(records) {
  const minuteMap = new Map()
  for (const record of records) {
    const epoch = record?._epoch
    if (epoch == null) continue
    const minuteEpoch = Math.floor(epoch / 60_000) * 60_000
    const existing = minuteMap.get(minuteEpoch)
    if (!existing || (record._epoch || 0) >= (existing._epoch || 0)) {
      minuteMap.set(minuteEpoch, {
        ...record,
        _epoch: minuteEpoch,
        _minuteEpoch: minuteEpoch,
      })
    }
  }
  return Array.from(minuteMap.values()).sort((left, right) => (left._epoch || 0) - (right._epoch || 0))
}

function computeWindowSeries(records, windowMinutes) {
  const output = {}
  VOV_COMPONENTS.forEach(component => {
    output[component.key] = new Array(records.length).fill(null)
  })
  for (let index = 0; index < records.length; index += 1) {
    const sample = trailingRecords(records, index, windowMinutes)
    VOV_COMPONENTS.forEach(component => {
      const levels = sample
        .map(record => levelFor(component.key, record))
        .filter(value => value != null)
      const returns = buildReturns(levels, component.mode)
      output[component.key][index] = returns.length >= 2 ? std(returns) : null
    })
  }
  return output
}

function computeStats(seriesMap) {
  const stats = {}
  VOV_COMPONENTS.forEach(component => {
    const values = (seriesMap[component.key] || []).filter(value => value != null)
    stats[component.key] = {
      mean: mean(values),
      std: std(values),
    }
  })
  return stats
}

function computeZScore(value, stats) {
  if (value == null || !stats || stats.mean == null || stats.std == null || stats.std <= 1e-12) return 0
  return (value - stats.mean) / stats.std
}

function buildWindowScoreSeries(records, windowDef, baselineRecords = records) {
  const rawSeries = computeWindowSeries(records, windowDef.minutes)
  const baselineRawSeries = computeWindowSeries(baselineRecords, windowDef.minutes)
  const stats = computeStats(baselineRawSeries)
  const scoreSeries = []
  for (let index = 0; index < records.length; index += 1) {
    let totalWeight = 0
    let totalZ = 0
    const componentZ = {}
    const componentScores = {}
    VOV_COMPONENTS.forEach(component => {
      const z = computeZScore(rawSeries[component.key][index], stats[component.key])
      componentZ[component.key] = z
      componentScores[component.key] = scoreFromZ(z)
      totalWeight += component.weight
      totalZ += component.weight * z
    })
    scoreSeries.push({
      epoch: records[index]?._epoch,
      timestamp: records[index]?.captured_at || null,
      z: totalWeight > 0 ? totalZ / totalWeight : 0,
      score: scoreFromZ(totalWeight > 0 ? totalZ / totalWeight : 0),
      componentZ,
      componentScores,
    })
  }
  return {
    scoreSeries,
    latest: scoreSeries[scoreSeries.length - 1] || null,
  }
}

function nearestByMinutesAtIndex(series, endIndex, targetMinutesAgo) {
  const last = series[endIndex]
  const currentEpoch = last?._epoch ?? last?.epoch
  if (currentEpoch == null) return last || null
  const targetEpoch = currentEpoch - (targetMinutesAgo * 60 * 1000)
  let candidate = last || null
  for (let index = endIndex; index >= 0; index -= 1) {
    const item = series[index]
    const epoch = item?._epoch ?? item?.epoch
    if (epoch == null) continue
    candidate = item
    if (epoch <= targetEpoch) return item
  }
  return candidate
}

function scoreRatio(value, pivot, maxRatio = 1.0) {
  if (pivot <= 0) return 0
  return clamp((value / pivot) / maxRatio, 0, 1) * 100
}

function scoreInverseRatio(value, pivot, maxRatio = 1.0) {
  if (pivot <= 0) return 0
  return clamp(1 - ((value / pivot) / maxRatio), 0, 1) * 100
}

function scoreDistance(value, band) {
  if (band <= 0) return 0
  return clamp(1 - (Math.abs(value) / band), 0, 1) * 100
}

function trendEfficiency(values) {
  if (!Array.isArray(values) || values.length < 2) return 0
  const first = safeNumber(values[0])
  const last = safeNumber(values[values.length - 1])
  if (first == null || last == null) return 0
  let path = 0
  for (let index = 1; index < values.length; index += 1) {
    const previous = safeNumber(values[index - 1])
    const current = safeNumber(values[index])
    if (previous == null || current == null) continue
    path += Math.abs(current - previous)
  }
  if (path <= 0) return 0
  return clamp(Math.abs(last - first) / path, 0, 1)
}

function pct(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${(numeric * 100).toFixed(2)}%`
}

function signed(value, decimals = 1) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  const prefix = numeric > 0 ? '+' : ''
  return `${prefix}${numeric.toFixed(decimals)}`
}

function formatScore(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${Math.round(clamp(numeric, 0, 100))}`
}

function formatLevel(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return Math.round(numeric).toLocaleString('pt-BR')
}

function sessionStampText(record) {
  const value = String(record?.captured_at || '').trim()
  if (!value) return 'sem timestamp'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const latestSessionDate = computed(() => {
  const last = intradayHistory.value[intradayHistory.value.length - 1]
  return last?._sessionDate || null
})

const intradayMinuteHistory = computed(() => bucketRecordsByMinute(intradayHistory.value))

const sessionHistory = computed(() => {
  const sessionDate = latestSessionDate.value
  if (!sessionDate) return []
  return intradayMinuteHistory.value.filter(item => item._sessionDate === sessionDate)
})

const sessionFlow = computed(() => {
  const sessionDate = latestSessionDate.value
  const events = flowEvents.value
    .filter(item => (sessionDate ? item._sessionDate === sessionDate : true))
    .filter(item => item._epoch != null && item._volume > 0)
    .sort((left, right) => (left._epoch || 0) - (right._epoch || 0))
  return events
})

const baseByStrike = computed(() => {
  const rows = props.modelData?.aggregates?.by_strike ?? []
  return rows
    .map(row => {
      const strike = safeNumber(row.strike ?? row.key)
      const gex = safeNumber(row.gex) || 0
      const callOi = safeNumber(row.call_oi) || 0
      const putOi = safeNumber(row.put_oi) || 0
      return {
        strike,
        gex,
        callOi,
        putOi,
        totalOi: callOi + putOi,
      }
    })
    .filter(row => row.strike != null && row.totalOi > 0)
    .sort((left, right) => left.strike - right.strike)
})

const structureMeta = computed(() => {
  const rows = baseByStrike.value
  const totalOi = rows.reduce((sum, row) => sum + row.totalOi, 0)
  const totalAbsGex = rows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const maxOi = Math.max(...rows.map(row => row.totalOi), 1)
  const maxAbsRowGex = Math.max(...rows.map(row => Math.abs(row.gex)), 1)
  const pinningBand = props.modelData?.pressure?.pinning_band ?? {}
  const accelerationBand = props.modelData?.pressure?.acceleration_band ?? {}
  const decompressionBand = props.modelData?.pressure?.decompression_band ?? {}
  const gammaFlipPoints = (props.modelData?.gamma_flip_history?.latest_flip_points ?? [])
    .map(value => safeNumber(value))
    .filter(value => value != null)
  return {
    rows,
    totalOi,
    totalAbsGex,
    maxOi,
    maxAbsRowGex,
    pinningBand,
    accelerationBand,
    decompressionBand,
    gammaFlipPoints,
  }
})

function bandCenter(band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (low == null || high == null) return null
  return (low + high) / 2
}

function bandWidth(band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (low == null || high == null) return null
  return Math.max(high - low, 0)
}

function insideBand(spot, band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (spot == null || low == null || high == null) return false
  return spot >= low && spot <= high
}

function distanceToBand(spot, band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (spot == null || low == null || high == null) return null
  if (spot < low) return low - spot
  if (spot > high) return spot - high
  return 0
}

function nearestGammaFlipDistance(spot, points) {
  if (spot == null || !points.length) return null
  return points.reduce((best, level) => {
    const distance = Math.abs(level - spot)
    return best == null || distance < best ? distance : best
  }, null)
}

function bestMagnetForSpot(meta, spot) {
  const localBand = Math.max((spot || 0) * 0.005, 1000)
  const searchBand = Math.max(localBand * 3, 3500)
  let best = null
  for (const row of meta.rows) {
    const distance = Math.abs(row.strike - spot)
    const proximity = clamp(1 - (distance / searchBand), 0, 1)
    if (proximity <= 0) continue
    const strength = (0.55 * (row.totalOi / meta.maxOi)) + (0.45 * (Math.abs(row.gex) / meta.maxAbsRowGex))
    const score = proximity * strength
    if (!best || score > best.score) {
      best = {
        strike: row.strike,
        distance,
        proximity,
        strength,
        score,
        gex: row.gex,
        totalOi: row.totalOi,
      }
    }
  }
  return best
}

function structureSnapshot(meta, spot) {
  if (!meta.rows.length || spot == null) {
    return {
      localGex: 0,
      pinningScoreComponents: {},
      expansionScoreComponents: {},
      dominantMagnet: null,
      criticalDirection: 0,
    }
  }

  const localBand = Math.max(spot * 0.005, 1000)
  const shellBand = Math.max(spot * 0.012, 2500)
  const localRows = meta.rows.filter(row => Math.abs(row.strike - spot) <= localBand)
  const shellRows = meta.rows.filter(row => Math.abs(row.strike - spot) > localBand && Math.abs(row.strike - spot) <= shellBand)
  const localGex = localRows.reduce((sum, row) => sum + row.gex, 0)
  const localAbsGex = localRows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const localOi = localRows.reduce((sum, row) => sum + row.totalOi, 0)
  const shellAbsGex = shellRows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const shellOi = shellRows.reduce((sum, row) => sum + row.totalOi, 0)
  const dominantMagnet = bestMagnetForSpot(meta, spot)
  const pinCenter = bandCenter(meta.pinningBand)
  const pinWidth = bandWidth(meta.pinningBand)
  const pinDistance = pinCenter != null ? Math.abs(spot - pinCenter) : null
  const distanceInsideCluster = insideBand(spot, meta.pinningBand)
    ? 70 + (30 * clamp(1 - ((pinDistance || 0) / Math.max((pinWidth || 1) / 2, 1)), 0, 1))
    : scoreDistance(distanceToBand(spot, meta.pinningBand) ?? localBand * 1.5, localBand * 1.4)

  const localLongGammaScore = scoreRatio(Math.max(localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const localShortGammaScore = scoreRatio(Math.max(-localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const lowGammaScore = scoreInverseRatio(localAbsGex, Math.max(meta.totalAbsGex * 0.12, 1), 1.0)
  const oiConcentrationNearSpot = scoreRatio(localOi, Math.max(meta.totalOi * 0.22, 1), 1.0)
  const strikeMagnetProximity = dominantMagnet
    ? clamp(dominantMagnet.proximity * dominantMagnet.strength * 140, 0, 100)
    : 0
  const airPocketProximity = clamp(
    (
      (1 - clamp(shellOi / Math.max(meta.totalOi * 0.22, 1), 0, 1)) * 0.55
      + (1 - clamp(shellAbsGex / Math.max(meta.totalAbsGex * 0.20, 1), 0, 1)) * 0.45
    ) * 100,
    0,
    100,
  )

  const flipDistance = nearestGammaFlipDistance(spot, meta.gammaFlipPoints)
  const flipScore = flipDistance != null ? scoreDistance(flipDistance, localBand * 0.75) : 0

  let gammaLevelBreakScore = 10
  if (insideBand(spot, meta.decompressionBand)) gammaLevelBreakScore = 85
  if (!insideBand(spot, meta.decompressionBand) && distanceToBand(spot, meta.decompressionBand) === 0) gammaLevelBreakScore = 100
  else if (insideBand(spot, meta.accelerationBand) || distanceToBand(spot, meta.accelerationBand) === 0) gammaLevelBreakScore = 72
  else if (!insideBand(spot, meta.pinningBand) && distanceToBand(spot, meta.pinningBand) === 0) gammaLevelBreakScore = 58
  gammaLevelBreakScore = clamp(gammaLevelBreakScore + (flipScore * 0.2), 0, 100)

  const pinningComponents = {
    localLongGamma: localLongGammaScore,
    oiConcentration: oiConcentrationNearSpot,
    strikeMagnetProximity,
    distanceInsideCluster,
  }

  const expansionComponents = {
    shortGammaOrLowGamma: Math.max(localShortGammaScore, lowGammaScore),
    gammaLevelBreak: gammaLevelBreakScore,
    airPocketProximity,
  }

  const criticalDirection = dominantMagnet && pinCenter != null
    ? Math.sign(spot - pinCenter || dominantMagnet.gex)
    : Math.sign(localGex)

  return {
    localGex,
    localBand,
    pinCenter,
    dominantMagnet,
    flipDistance,
    pinningComponents,
    expansionComponents,
    criticalDirection: criticalDirection === 0 ? 1 : criticalDirection,
  }
}

function flowScoreForEvent(item, fallbackSpot) {
  const eventSpot = item._spot || fallbackSpot
  const strike = item._strike || eventSpot || fallbackSpot
  const distPct = eventSpot > 0 ? Math.abs(strike - eventSpot) / eventSpot : 0
  const proxWeight = distPct <= 0.015 ? 1.2 : distPct <= 0.04 ? 1.0 : distPct <= 0.08 ? 0.65 : 0.35
  const daysWeight = item._days != null ? (item._days <= 30 ? 1.0 : item._days <= 60 ? 0.8 : 0.6) : 0.85
  const deltaWeight = 0.55 + (0.45 * clamp(item._delta, 0, 1))
  return item._volume * proxWeight * daysWeight * deltaWeight
}

function buildFlowWindowSnapshots(records, flow, fallbackSpot) {
  if (!records.length) return []

  const prepared = flow
    .filter(item => item._epoch != null && item._volume > 0)
    .map(item => ({
      epoch: item._epoch,
      side: item._side,
      score: flowScoreForEvent(item, fallbackSpot),
    }))
    .filter(item => item.score > 0)
    .sort((left, right) => left.epoch - right.epoch)

  let start = 0
  let end = 0
  let callFlow = 0
  let putFlow = 0

  return records.map(record => {
    const currentEpoch = record?._epoch
    if (currentEpoch == null) {
      return {
        callFlow,
        putFlow,
        totalFlow: callFlow + putFlow,
        flowImbalance: 0,
        directionalFlowScore: 0,
      }
    }

    while (end < prepared.length && prepared[end].epoch <= currentEpoch) {
      if (prepared[end].side === 'P') putFlow += prepared[end].score
      else callFlow += prepared[end].score
      end += 1
    }

    const cutoffEpoch = currentEpoch - (30 * 60 * 1000)
    while (start < end && prepared[start].epoch < cutoffEpoch) {
      if (prepared[start].side === 'P') putFlow -= prepared[start].score
      else callFlow -= prepared[start].score
      start += 1
    }

    callFlow = Math.max(callFlow, 0)
    putFlow = Math.max(putFlow, 0)
    const totalFlow = callFlow + putFlow
    const flowImbalance = totalFlow > 0 ? (callFlow - putFlow) / totalFlow : 0
    const directionalFlowScore = totalFlow > 0
      ? clamp(Math.abs(flowImbalance) * Math.sqrt(totalFlow / 2500) * 100, 0, 100)
      : 0

    return {
      callFlow,
      putFlow,
      totalFlow,
      flowImbalance,
      directionalFlowScore,
    }
  })
}

function componentScoresAtIndex(records, index, surfacePack, meta, flowWindow, openPrice) {
  const record = records[index]
  const spot = safeNumber(record?._price)
  if (spot == null) return null

  const structure = structureSnapshot(meta, spot)
  const fifteenSlice = trailingRecords(records, index, 15)
  const thirtySlice = trailingRecords(records, index, 30)
  const priceWindow = fifteenSlice.map(item => item?._price).filter(value => value != null)
  const priceWindow30 = thirtySlice.map(item => item?._price).filter(value => value != null)
  const trendEff = trendEfficiency(priceWindow)
  const latestPrice = priceWindow.at(-1) ?? spot
  const rvCurrent = safeNumber(record.rv_garch_intraday ?? record.rv_live_3d ?? record.rv_live_5d)
  const ivCurrent = safeNumber(record.iv_atm)
  const ivBase15 = nearestByMinutesAtIndex(records, index, 15)
  const ivDelta15mPts = ivCurrent != null && safeNumber(ivBase15?.iv_atm) != null
    ? (ivCurrent - safeNumber(ivBase15.iv_atm)) * 100
    : 0
  const skewCurrent = levelFor('skew', record)
  const skewBase15 = levelFor('skew', ivBase15)
  const skewDelta15m = skewCurrent != null && skewBase15 != null ? (skewCurrent - skewBase15) : 0
  const putWingCurrent = levelFor('putWing', record)
  const putWingBase15 = levelFor('putWing', ivBase15)
  const putWingDelta15mPts = putWingCurrent != null && putWingBase15 != null ? (putWingCurrent - putWingBase15) * 100 : 0
  const callWingCurrent = levelFor('callWing', record)
  const callWingBase15 = levelFor('callWing', ivBase15)
  const callWingDelta15mPts = callWingCurrent != null && callWingBase15 != null ? (callWingCurrent - callWingBase15) * 100 : 0

  const score5 = surfacePack.five.scoreSeries[index]?.score ?? null
  const score15 = surfacePack.fifteen.scoreSeries[index]?.score ?? null
  const surfaceMotionScore = (
    ((score5 ?? score15 ?? 0) * WINDOW_5.weight)
    + ((score15 ?? score5 ?? 0) * WINDOW_15.weight)
  ) / (WINDOW_5.weight + WINDOW_15.weight)

  const prevSurface = nearestByMinutesAtIndex(surfacePack.fifteenAligned, index, 15)
  const surfaceMotionDelta = surfaceMotionScore - (safeNumber(prevSurface?.score) || 0)

  const flowImbalance = flowWindow?.flowImbalance || 0
  const directionalFlowScore = flowWindow?.directionalFlowScore || 0

  const pinAnchor = structure.dominantMagnet?.strike ?? structure.pinCenter ?? latestPrice
  const dayRange = Math.max(...records.slice(0, index + 1).map(item => safeNumber(item._price) || latestPrice)) - Math.min(...records.slice(0, index + 1).map(item => safeNumber(item._price) || latestPrice))
  const open = openPrice ?? latestPrice
  const directionalDistance = Math.abs(latestPrice - pinAnchor)
  const rangeExtension = dayRange > 0 ? Math.abs(latestPrice - open) / dayRange : 0
  const futureAggressionScore = clamp(((trendEff * 0.60) + (clamp(directionalDistance / structure.localBand, 0, 1) * 0.25) + (clamp(rangeExtension, 0, 1) * 0.15)) * 100, 0, 100)

  const priceWindowMaxAnchorDist = priceWindow30.length
    ? Math.max(...priceWindow30.map(price => Math.abs(price - pinAnchor)))
    : directionalDistance
  const meanReversionBehavior = clamp((1 - trendEff) * (1 - clamp(directionalDistance / Math.max(priceWindowMaxAnchorDist || structure.localBand, 1), 0, 1)) * 120, 0, 100)
  const rvGap = ivCurrent != null && rvCurrent != null ? ivCurrent - rvCurrent : null
  const lowRealizedVolScore = rvGap != null
    ? clamp((clamp(rvGap / Math.max(ivCurrent * 0.35, 0.02), 0, 1) * 0.65 + (1 - trendEff) * 0.35) * 100, 0, 100)
    : clamp((1 - trendEff) * 70, 0, 100)

  const stableWingScore = clamp(1 - ((Math.abs(putWingDelta15mPts) + Math.abs(callWingDelta15mPts) + Math.abs(skewDelta15m * 100)) / 3.0), 0, 1) * 100
  const ivCompressionScore = clamp(
    (
      clamp((-ivDelta15mPts) / 0.7, 0, 1) * 0.40
      + (1 - (surfaceMotionScore / 100)) * 0.35
      + (stableWingScore / 100) * 0.25
    ) * 100,
    0,
    100,
  )
  const ivExpansionScore = clamp(
    (
      clamp(ivDelta15mPts / 0.8, 0, 1) * 0.38
      + (surfaceMotionScore / 100) * 0.34
      + clamp((Math.max(putWingDelta15mPts, callWingDelta15mPts, Math.abs(skewDelta15m * 100))) / 1.0, 0, 1) * 0.28
    ) * 100,
    0,
    100,
  )

  const pinningComponents = [
    { key: 'localLongGamma', label: 'Local long gamma', score: structure.pinningComponents.localLongGamma || 0 },
    { key: 'oiConcentration', label: 'OI perto do spot', score: structure.pinningComponents.oiConcentration || 0 },
    { key: 'strikeMagnetProximity', label: 'Magneto de strike', score: structure.pinningComponents.strikeMagnetProximity || 0 },
    { key: 'ivCompression', label: 'IV compression', score: ivCompressionScore },
    { key: 'lowRealizedVol', label: 'Low realized vol', score: lowRealizedVolScore },
    { key: 'meanReversion', label: 'Mean reversion', score: meanReversionBehavior },
    { key: 'distanceInsideCluster', label: 'Dentro do gamma cluster', score: structure.pinningComponents.distanceInsideCluster || 0 },
  ]

  const expansionComponents = [
    { key: 'shortGammaOrLowGamma', label: 'Short/low gamma local', score: structure.expansionComponents.shortGammaOrLowGamma || 0 },
    { key: 'ivExpansion', label: 'IV expansion', score: ivExpansionScore },
    { key: 'volOfVolRising', label: 'Vol of vol rising', score: surfaceMotionScore },
    { key: 'trendEfficiency', label: 'Trend efficiency', score: clamp(trendEff * 100, 0, 100) },
    { key: 'gammaLevelBreak', label: 'Break de gamma level', score: structure.expansionComponents.gammaLevelBreak || 0 },
    { key: 'directionalFlow', label: 'Fluxo direcional', score: directionalFlowScore },
    { key: 'futureAggression', label: 'Agressao do futuro', score: futureAggressionScore },
    { key: 'airPocket', label: 'Air pocket', score: structure.expansionComponents.airPocketProximity || 0 },
  ]

  const pinningScore = mean(pinningComponents.map(item => item.score)) || 0
  const expansionScore = mean(expansionComponents.map(item => item.score)) || 0

  return {
    spot,
    latestPrice,
    pinAnchor,
    pinningComponents,
    expansionComponents,
    pinningScore,
    expansionScore,
    battleScore: expansionScore - pinningScore,
    surfaceMotionScore,
    surfaceMotionDelta,
    trendEfficiencyScore: clamp(trendEff * 100, 0, 100),
    directionalFlowScore,
    flowImbalance,
    ivDelta15mPts,
    putWingDelta15mPts,
    callWingDelta15mPts,
    dayRange,
    structure,
  }
}

function classifyState(snapshot) {
  const pin = snapshot.pinningScore
  const exp = snapshot.expansionScore
  const trend = snapshot.trendEfficiencyScore
  const surface = snapshot.surfaceMotionScore

  if (exp > 85 && trend > 70 && surface > 70) return 'Reflexive Expansion'
  if (exp > 80) return 'Active Expansion'
  if (pin > 75 && exp < 40) return 'Strong Pinning'
  if (exp > pin + 8) return 'Expansion Watch'
  if (pin > exp + 8) return 'Mild Pinning'
  return 'Balanced'
}

function badgeFor(snapshot) {
  if (snapshot.expansionScore > 80) return ['Expansion Active', 'hot']
  if (snapshot.pinningScore > 75 && snapshot.expansionScore < 40) return ['Fade Bias', 'cool']
  if (snapshot.pinningScore > 65 && snapshot.expansionScore > 65) return ['Coiled Market', 'warm']
  if (snapshot.expansionScore > snapshot.pinningScore) return ['Breakout Watch', 'warm']
  return ['Range Trade', 'cool']
}

function currentDirection(snapshot) {
  if ((snapshot.flowImbalance || 0) > 0.08) return 1
  if ((snapshot.flowImbalance || 0) < -0.08) return -1
  const structureDirection = snapshot.structure?.criticalDirection || 1
  return structureDirection === 0 ? 1 : structureDirection
}

function breakoutLevels(snapshot, meta) {
  const direction = currentDirection(snapshot)
  const accel = meta.accelerationBand || {}
  const pin = meta.pinningBand || {}
  const decomp = meta.decompressionBand || {}
  const dominantMagnet = snapshot.structure?.dominantMagnet?.strike ?? bandCenter(pin) ?? snapshot.spot

  let breakoutLevel = null
  if (direction > 0) breakoutLevel = safeNumber(accel.high ?? decomp.high ?? pin.high)
  else breakoutLevel = safeNumber(accel.low ?? decomp.low ?? pin.low)

  let returnLevel = dominantMagnet
  if (direction > 0 && safeNumber(pin.high) != null) returnLevel = safeNumber(pin.high)
  if (direction < 0 && safeNumber(pin.low) != null) returnLevel = safeNumber(pin.low)

  return {
    breakoutLevel,
    breakoutLabel: direction > 0 ? 'acima ativa expansao compradora' : 'abaixo ativa expansao vendedora',
    returnLevel,
    returnLabel: direction > 0 ? 'volta ao pin pelo teto' : 'volta ao pin pelo piso',
    direction,
  }
}

function dominantComponentLabel(components) {
  const best = components.slice().sort((left, right) => (right.score || 0) - (left.score || 0))[0]
  return {
    label: best?.label || '--',
    key: best?.key || null,
  }
}

function buildReading(snapshot, levels) {
  const direction = levels.direction
  const sideText = direction > 0 ? 'comprador' : 'vendedor'
  if (snapshot.state === 'Strong Pinning') {
    return `gamma local, OI perto do spot e comportamento de reversao ainda favorecem fades; o mercado tende a continuar preso enquanto ${sideText} nao atravesse ${formatLevel(levels.breakoutLevel)}.`
  }
  if (snapshot.state === 'Mild Pinning') {
    return `compressao ainda domina, mas sem o mesmo conforto de um pin forte; o spot segue orbitando a regiao magnetica de ${formatLevel(snapshot.structure?.dominantMagnet?.strike)}.`
  }
  if (snapshot.state === 'Balanced') {
    return `pinning e expansao estao perto de equilibrio; qualquer aceleracao de IV ou perda do cluster pode deslocar o regime rapidamente.`
  }
  if (snapshot.state === 'Expansion Watch') {
    return `a compressao ainda existe, mas a superficie ja esta menos estavel e o fluxo esta tentando tomar controle; ${formatLevel(levels.breakoutLevel)} virou gatilho operacional.`
  }
  if (snapshot.state === 'Active Expansion') {
    return `o quadro favorece continuidade; vol of vol, eficiencia de tendencia e quebra de gamma level estao mais fortes que o pinning local.`
  }
  return `o mercado entrou em modo reflexivo: price action eficiente, superficie acelerando e pouca absorcao estrutural nas proximidades.`
}

const analytics = computed(() => {
  const records = sessionHistory.value
  const meta = structureMeta.value
  if (records.length < 6 || !meta.rows.length) return null

  const openPrice = safeNumber(records[0]?._price)
  const surfacePack = {
    five: buildWindowScoreSeries(records, WINDOW_5, intradayMinuteHistory.value),
    fifteen: buildWindowScoreSeries(records, WINDOW_15, intradayMinuteHistory.value),
  }
  const fifteenAligned = surfacePack.fifteen.scoreSeries.map((item, innerIndex) => ({
    ...item,
    _epoch: records[innerIndex]?._epoch,
  }))
  const flowWindows = buildFlowWindowSnapshots(records, sessionFlow.value, openPrice)

  const battleSeries = []
  let latestPoint = null
  for (let index = 0; index < records.length; index += 1) {
    const point = componentScoresAtIndex(
      records,
      index,
      { ...surfacePack, fifteenAligned },
      meta,
      flowWindows[index],
      openPrice,
    )
    if (!point) continue
    const stamp = new Date(records[index]?._epoch || 0)
    battleSeries.push({
      epoch: records[index]?._epoch,
      timestamp: records[index]?.captured_at,
      sessionDate: records[index]?._sessionDate || latestSessionDate.value,
      pinning: point.pinningScore,
      expansion: point.expansionScore,
      battle: point.battleScore,
      isSessionStart: index === 0,
      axisLabel: Number.isNaN(stamp.getTime())
        ? (latestSessionDate.value || 'today')
        : stamp.toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit',
          }),
    })
    latestPoint = point
  }

  if (!latestPoint || !battleSeries.length) return null

  const state = classifyState(latestPoint)
  const [badge, badgeTone] = badgeFor(latestPoint)
  const dominantPinning = dominantComponentLabel(latestPoint.pinningComponents)
  const dominantExpansion = dominantComponentLabel(latestPoint.expansionComponents)
  const levels = breakoutLevels(latestPoint, meta)
  const currentRecord = records[records.length - 1] || {}
  const alerts = []
  const lastThree = battleSeries.slice(-3)

  if (lastThree.length === 3 && lastThree[1].expansion <= lastThree[1].pinning && lastThree[2].expansion > lastThree[2].pinning) {
    alerts.push('Expansion Regime Taking Control')
  }
  if (latestPoint.pinningScore > 75 && latestPoint.expansionScore < 40) alerts.push('Strong Pinning')
  if (latestPoint.pinningScore > 65 && latestPoint.expansionScore > 65) alerts.push('Compressed Instability / Coiled Market')
  if (latestPoint.expansionScore > 80) alerts.push('Active Expansion')

  const flowDirectionLabel = latestPoint.directionalFlowScore < 25
    ? 'fluxo neutro'
    : latestPoint.flowImbalance > 0
      ? 'calls e upside puxando'
      : 'puts e downside puxando'

  return {
    latest: currentRecord,
    spot: latestPoint.spot,
    pinningScore: latestPoint.pinningScore,
    expansionScore: latestPoint.expansionScore,
    battleScore: latestPoint.battleScore,
    battlePosition: clamp(50 + ((latestPoint.battleScore / 100) * 30), 10, 90),
    state,
    badge,
    badgeTone,
    reading: buildReading(latestPoint, levels),
    dominantPinningLabel: dominantPinning.label,
    dominantExpansionLabel: dominantExpansion.label,
    pinningComponents: latestPoint.pinningComponents,
    expansionComponents: latestPoint.expansionComponents,
    breakoutLevel: levels.breakoutLevel,
    breakoutLabel: levels.breakoutLabel,
    returnLevel: levels.returnLevel,
    returnLabel: levels.returnLabel,
    direction: levels.direction,
    surfaceMotionScore: latestPoint.surfaceMotionScore,
    surfaceMotionDelta: latestPoint.surfaceMotionDelta,
    trendEfficiencyScore: latestPoint.trendEfficiencyScore,
    directionalFlowScore: latestPoint.directionalFlowScore,
    flowDirectionLabel,
    flowImbalance: latestPoint.flowImbalance,
    ivDelta15mPts: latestPoint.ivDelta15mPts,
    dayRangeLabel: `range ${Math.round(latestPoint.dayRange || 0).toLocaleString('pt-BR')} pts`,
    sessionStamp: sessionStampText(currentRecord),
    alerts,
    historySeries: battleSeries,
    structure: latestPoint.structure,
    pinningRegime: latestPoint.pinningScore > latestPoint.expansionScore ? 'magnetico / mean-reverting' : 'pressionado',
    expansionRegime: latestPoint.expansionScore > latestPoint.pinningScore ? 'rompimento / continuidade' : 'contido',
  }
})

const snapshot = computed(() => analytics.value)

const battleChartHistory = computed(() => snapshot.value?.historySeries || [])

const battleChartLabel = computed(() => {
  const sessionDate = latestSessionDate.value
  const count = battleChartHistory.value.length
  if (!sessionDate) return '1m / sem base'
  return `${sessionDate} / 1m / ${count} pts`
})

function battleTone(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return ''
  if (numeric > 8) return 'hot'
  if (numeric < -8) return 'cool'
  return ''
}

function deltaTone(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return ''
  if (numeric > 0) return 'hot'
  if (numeric < 0) return 'cool'
  return ''
}

function drawCenteredMessage(ctx, width, height, message) {
  ctx.save()
  ctx.fillStyle = '#6f8399'
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(message, width / 2, height / 2)
  ctx.restore()
}

function drawBattleHistoryChart() {
  const canvas = battleCanvas.value
  const wrap = battleWrap.value
  const data = battleChartHistory.value
  if (!canvas || !wrap) return

  const width = Math.max(wrap.clientWidth || 0, 320)
  const height = Math.max(wrap.clientHeight || 0, BATTLE_HEIGHT)
  const dpr = window.devicePixelRatio || 1

  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0b1624'
  ctx.fillRect(0, 0, width, height)

  if (data.length < 2) {
    drawCenteredMessage(ctx, width, height, 'Waiting for 1m history')
    return
  }

  const chartWidth = width - BATTLE_PAD.left - BATTLE_PAD.right
  const chartHeight = height - BATTLE_PAD.top - BATTLE_PAD.bottom
  const xOf = index => BATTLE_PAD.left + (index / Math.max(data.length - 1, 1)) * chartWidth
  const yOf = value => BATTLE_PAD.top + (1 - (clamp(value, 0, 100) / 100)) * chartHeight

  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.10)'
  ctx.fillStyle = '#607d8b'
  ctx.lineWidth = 1
  ctx.font = '9px monospace'
  ;[0, 20, 40, 60, 80, 100].forEach(tick => {
    const y = yOf(tick)
    ctx.beginPath()
    ctx.moveTo(BATTLE_PAD.left, y)
    ctx.lineTo(width - BATTLE_PAD.right, y)
    ctx.stroke()
    if (tick < 100) ctx.fillText(String(tick), 6, y + 3)
  })
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.14)'
  ctx.fillStyle = '#64748b'
  ctx.font = '8px monospace'
  const labelStep = Math.max(1, Math.floor(data.length / 8))
  data.forEach((point, index) => {
    if (!point.isSessionStart && index % labelStep !== 0 && index !== data.length - 1) return
    const x = xOf(index)
    if (point.isSessionStart && index > 0) {
      ctx.save()
      ctx.strokeStyle = 'rgba(251,191,36,0.22)'
      ctx.setLineDash([3, 4])
      ctx.beginPath()
      ctx.moveTo(x, BATTLE_PAD.top)
      ctx.lineTo(x, height - BATTLE_PAD.bottom)
      ctx.stroke()
      ctx.restore()
    }
    ctx.fillText(point.axisLabel, x - 12, height - 8)
  })
  ctx.restore()

  const drawLine = (key, strokeStyle, fillStyle) => {
    ctx.save()
    ctx.strokeStyle = strokeStyle
    ctx.lineWidth = 1.8
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.beginPath()
    data.forEach((point, index) => {
      const x = xOf(index)
      const y = yOf(point[key])
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    const last = data[data.length - 1]
    ctx.fillStyle = fillStyle
    ctx.beginPath()
    ctx.arc(xOf(data.length - 1), yOf(last[key]), 2.2, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  drawLine('pinning', '#4ade80', '#4ade80')
  drawLine('expansion', '#fb7185', '#fb7185')
}

async function load({ force = false } = {}) {
  const now = Date.now()
  if (!force && now - lastLoadAt < MIN_FETCH_INTERVAL_MS) return
  loading.value = true
  error.value = null
  try {
    const [volResponse, flowResponse] = await Promise.allSettled([
      getVolIndexHistory({
        underlying: underlying.value,
        days: 10,
        intraday_days: 1,
      }),
      getVolumeActivity({
        underlying_security: underlying.value,
        limit: 1200,
        lookback_days: 1,
      }),
    ])

    if (volResponse.status === 'fulfilled') {
      const payload = volResponse.value?.data || {}
      dailyHistory.value = (payload.daily_history || payload.history || []).map(normalizeVolRecord)
      intradayHistory.value = (payload.intraday_history || []).map(normalizeVolRecord)
    }

    if (flowResponse.status === 'fulfilled') {
      const payload = flowResponse.value?.data
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : []
      flowEvents.value = rows.map(normalizeFlowEvent)
    }

    if (volResponse.status !== 'fulfilled' && flowResponse.status !== 'fulfilled') {
      throw new Error('Failed to load intraday history')
    }
    lastLoadAt = Date.now()
    await nextTick()
    drawBattleHistoryChart()
  } catch (err) {
    error.value = err?.response?.data?.error || err?.message || 'Failed to load battle widget data'
  } finally {
    loading.value = false
  }
}

async function reload() {
  await load({ force: true })
}

watch(() => props.underlyingSecurity, async (next, previous) => {
  if (!next || next === previous) return
  await load({ force: true })
})

watch(() => props.refreshNonce, async (next, previous) => {
  if (!next || next === previous) return
  await nextTick()
  drawBattleHistoryChart()
})

watch(battleChartHistory, async () => {
  await nextTick()
  drawBattleHistoryChart()
})

onMounted(async () => {
  await load({ force: true })
  refreshTimer = setInterval(load, AUTO_REFRESH_MS)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.peb-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #08101a;
  color: #dbe7f3;
  font-family: monospace;
  overflow: auto;
}

.peb-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid #162235;
}

.peb-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fbbf24;
}

.peb-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.peb-underlying,
.peb-btn {
  border: 1px solid #223048;
  border-radius: 4px;
  background: #0b1624;
  color: #dbe7f3;
  font-size: 10px;
}

.peb-underlying {
  padding: 2px 6px;
  color: #93c5fd;
}

.peb-btn {
  padding: 3px 8px;
  cursor: pointer;
  color: #fbbf24;
}

.peb-btn.loading {
  opacity: 0.6;
  cursor: wait;
}

.peb-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px 12px;
  color: #72859a;
  font-size: 10px;
}

.peb-top {
  display: grid;
  grid-template-columns: minmax(280px, 1.15fr) minmax(290px, 1fr);
  gap: 10px;
  padding: 10px;
  border-bottom: 1px solid #162235;
}

.peb-battle-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  background:
    radial-gradient(circle at top left, rgba(251, 191, 36, 0.16), rgba(8, 16, 26, 0.95) 48%),
    linear-gradient(135deg, rgba(34, 197, 94, 0.08), rgba(239, 68, 68, 0.08));
  border: 1px solid rgba(251, 191, 36, 0.16);
}

.peb-battle-head {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 10px;
  align-items: center;
}

.peb-score-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.peb-score-block.right {
  align-items: flex-end;
}

.peb-score-label {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #7c8ea5;
}

.peb-score-value {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  color: #f8fafc;
}

.peb-score-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.peb-state,
.peb-badge,
.peb-alert-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.peb-state {
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #f8fafc;
}

.peb-badge.cool {
  background: rgba(34, 197, 94, 0.12);
  color: #86efac;
  border: 1px solid rgba(34, 197, 94, 0.18);
}

.peb-badge.warm,
.peb-alert-pill {
  background: rgba(251, 191, 36, 0.12);
  color: #fde68a;
  border: 1px solid rgba(251, 191, 36, 0.18);
}

.peb-badge.hot {
  background: rgba(248, 113, 113, 0.12);
  color: #fca5a5;
  border: 1px solid rgba(248, 113, 113, 0.18);
}

.peb-battle-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.peb-battle-track {
  position: relative;
  height: 18px;
  border-radius: 999px;
  overflow: hidden;
  background: linear-gradient(90deg, rgba(34, 197, 94, 0.08), rgba(148, 163, 184, 0.05), rgba(239, 68, 68, 0.08));
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.peb-battle-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  opacity: 0.7;
}

.peb-battle-fill.pin {
  left: 0;
  background: linear-gradient(90deg, rgba(34, 197, 94, 0.55), rgba(16, 185, 129, 0.24));
}

.peb-battle-fill.exp {
  right: 0;
  background: linear-gradient(90deg, rgba(251, 146, 60, 0.24), rgba(239, 68, 68, 0.55));
}

.peb-battle-divider {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: 50%;
  width: 1px;
  background: rgba(226, 232, 240, 0.28);
}

.peb-battle-indicator {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f8fafc;
  border: 2px solid #08101a;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 2px rgba(248, 250, 252, 0.14);
}

.peb-battle-scale {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: #7c8ea5;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.peb-reading {
  font-size: 12px;
  line-height: 1.45;
  color: #dbe7f3;
}

.peb-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 10px;
  color: #93a7bd;
}

.peb-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.peb-kpi {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 72px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(11, 22, 36, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.peb-kpi-label {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #7c8ea5;
}

.peb-kpi-value {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
  line-height: 1.1;
}

.peb-kpi-value.hot {
  color: #fca5a5;
}

.peb-kpi-value.cool {
  color: #86efac;
}

.peb-kpi-sub {
  font-size: 10px;
  color: #8ea2b8;
  line-height: 1.3;
}

.peb-kpi-sub.hot {
  color: #fb7185;
}

.peb-kpi-sub.cool {
  color: #4ade80;
}

.peb-alerts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 10px 10px;
  border-bottom: 1px solid #162235;
}

.peb-history-block,
.peb-column {
  padding: 10px;
}

.peb-block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.peb-block-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #e2e8f0;
}

.peb-block-sub {
  font-size: 10px;
  color: #7c8ea5;
}

.peb-history-wrap {
  width: 100%;
  min-height: 150px;
  background: rgba(11, 22, 36, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 10px;
  overflow: hidden;
}

.peb-history-canvas {
  display: block;
  width: 100%;
  height: 150px;
}

.peb-history-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 150px;
  font-size: 10px;
  color: #6f8399;
}

.peb-history-footer {
  display: flex;
  gap: 12px;
  padding-top: 6px;
  font-size: 10px;
  color: #93a7bd;
}

.peb-line-key {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.peb-line-chip {
  display: inline-block;
  width: 10px;
  height: 2px;
  border-radius: 999px;
}

.peb-line-chip.pin {
  background: #4ade80;
}

.peb-line-chip.exp {
  background: #fb7185;
}

.peb-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  border-top: 1px solid #162235;
}

.peb-column {
  border-right: 1px solid #162235;
}

.peb-column:last-child {
  border-right: 0;
}

.peb-factor-row {
  display: grid;
  grid-template-columns: minmax(110px, 1fr) minmax(90px, 1.4fr) auto;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}

.peb-factor-name {
  font-size: 10px;
  color: #dbe7f3;
}

.peb-factor-track {
  position: relative;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(30, 41, 59, 0.9);
}

.peb-factor-bar {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 999px;
}

.peb-factor-bar.pin {
  background: linear-gradient(90deg, #4ade80, #10b981);
}

.peb-factor-bar.exp {
  background: linear-gradient(90deg, #fb923c, #fb7185);
}

.peb-factor-score {
  font-size: 10px;
  color: #f8fafc;
  font-weight: 700;
}

.peb-footer-note {
  padding: 0 10px 10px;
  font-size: 10px;
  color: #6f8399;
}

@media (max-width: 980px) {
  .peb-top,
  .peb-columns {
    grid-template-columns: 1fr;
  }

  .peb-column {
    border-right: 0;
    border-top: 1px solid #162235;
  }
}
</style>
